# -*- coding: utf-8 -*-
"""Protocol-aware selection and validation for electrophysiology analyses.

The data file remains the container.  A :class:`ProtocolMap` records which
trial/time region is an analysis segment and which regions are annotations.
This keeps protocol provenance outside individual analysis implementations and
lets every built-in analysis make the same compatibility decision.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple


class ProtocolSource(str, Enum):
    RECORDED = "recorded"
    IMPORTED = "imported"
    MANUAL = "manual"
    DRAWN = "drawn"
    SIGNAL_ONLY = "signal_only"


@dataclass(frozen=True)
class ProtocolRequirement:
    """Inputs required for a built-in analysis to be scientifically contextual."""

    families: Tuple[str, ...] = ("signal_only",)
    requires_command: bool = False
    requires_stimulus_timing: bool = False
    requires_multi_trial: bool = False
    description: str = "Signal trace only"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProtocolAssignment:
    """A protocol segment or an overlapping annotation on one or more trials."""

    protocol_family: str
    trial_indices: Tuple[int, ...]
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    profile_id: str = ""
    profile_version: str = "1"
    source: ProtocolSource = ProtocolSource.MANUAL
    parameters: Dict[str, Any] = field(default_factory=dict)
    label: str = ""
    is_analysis_segment: bool = True
    verified: bool = False
    assignment_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        self.protocol_family = str(self.protocol_family or "signal_only")
        self.trial_indices = tuple(sorted({int(index) for index in self.trial_indices}))
        if not self.trial_indices:
            raise ValueError("A protocol assignment needs at least one trial index.")
        if self.start_time is not None:
            self.start_time = float(self.start_time)
        if self.end_time is not None:
            self.end_time = float(self.end_time)
        if self.start_time is not None and self.end_time is not None and self.end_time <= self.start_time:
            raise ValueError("Protocol segment end_time must be later than start_time.")
        if not isinstance(self.source, ProtocolSource):
            self.source = ProtocolSource(str(self.source))

    def applies_to_trial(self, trial_index: int) -> bool:
        return int(trial_index) in self.trial_indices

    def overlaps(self, other: "ProtocolAssignment") -> bool:
        if not set(self.trial_indices).intersection(other.trial_indices):
            return False
        if self.start_time is None or self.end_time is None or other.start_time is None or other.end_time is None:
            return True
        return self.start_time < other.end_time and other.start_time < self.end_time

    @property
    def fingerprint(self) -> str:
        payload = {
            "family": self.protocol_family,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "parameters": self.parameters,
        }
        stable = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.value
        data["trial_indices"] = list(self.trial_indices)
        data["fingerprint"] = self.fingerprint
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolAssignment":
        allowed = {
            "protocol_family",
            "trial_indices",
            "start_time",
            "end_time",
            "profile_id",
            "profile_version",
            "source",
            "parameters",
            "label",
            "is_analysis_segment",
            "verified",
            "assignment_id",
        }
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass(frozen=True)
class ResolvedProtocol:
    """One executable trace region with provenance and compatibility state."""

    assignment: ProtocolAssignment
    trial_index: int
    status: str
    missing: Tuple[str, ...] = ()

    @property
    def protocol_fingerprint(self) -> str:
        return self.assignment.fingerprint

    def as_result_metadata(self) -> Dict[str, Any]:
        return {
            "protocol_family": self.assignment.protocol_family,
            "protocol_profile": self.assignment.profile_id or None,
            "protocol_profile_version": self.assignment.profile_version,
            "protocol_fingerprint": self.protocol_fingerprint,
            "protocol_source": self.assignment.source.value,
            "protocol_verified": self.assignment.verified,
            "protocol_assignment_id": self.assignment.assignment_id,
            "segment_start_s": self.assignment.start_time,
            "segment_end_s": self.assignment.end_time,
            "protocol_status": self.status,
            "protocol_missing": "; ".join(self.missing) if self.missing else "",
        }


class ProtocolMap:
    """Persisted trial/time protocol assignments for a recording.

    Analysis segments are mutually exclusive on a trial.  Annotations are
    allowed to overlap them, which is necessary for drug epochs and artefact
    masks without allowing the same samples to be analysed twice by accident.
    """

    schema_version = 1

    def __init__(self, assignments: Optional[Iterable[ProtocolAssignment]] = None) -> None:
        self._assignments: List[ProtocolAssignment] = []
        for assignment in assignments or ():
            self.add(assignment)

    @property
    def assignments(self) -> List[ProtocolAssignment]:
        return list(self._assignments)

    def add(self, assignment: ProtocolAssignment) -> ProtocolAssignment:
        if assignment.is_analysis_segment:
            conflicts = [
                other for other in self._assignments if other.is_analysis_segment and assignment.overlaps(other)
            ]
            if conflicts:
                raise ValueError("Analysis protocol segments cannot overlap on the same trial.")
        self._assignments.append(assignment)
        return assignment

    def remove(self, assignment_id: str) -> bool:
        for index, assignment in enumerate(self._assignments):
            if assignment.assignment_id == assignment_id:
                self._assignments.pop(index)
                return True
        return False

    def assignments_for_trial(self, trial_index: int, include_annotations: bool = True) -> List[ProtocolAssignment]:
        return sorted(
            [
                assignment
                for assignment in self._assignments
                if assignment.applies_to_trial(trial_index) and (include_annotations or assignment.is_analysis_segment)
            ],
            key=lambda assignment: (assignment.start_time is None, assignment.start_time or 0.0),
        )

    def analysis_segments_for_trial(
        self,
        trial_index: int,
        duration: Optional[float] = None,
    ) -> List[ProtocolAssignment]:
        explicit = self.assignments_for_trial(trial_index, include_annotations=False)
        if explicit:
            return explicit
        return [
            ProtocolAssignment(
                protocol_family="signal_only",
                trial_indices=(trial_index,),
                start_time=0.0,
                end_time=duration,
                source=ProtocolSource.SIGNAL_ONLY,
                label="Signal-only",
                verified=False,
                assignment_id=f"implicit-signal-only-{trial_index}",
            )
        ]

    def as_dict(self) -> Dict[str, Any]:
        return {"schema_version": self.schema_version, "assignments": [item.as_dict() for item in self._assignments]}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ProtocolMap":
        if not data:
            return cls()
        return cls(ProtocolAssignment.from_dict(item) for item in data.get("assignments", []))


_SIGNAL = ProtocolRequirement(description="Signal trace only")
_CURRENT_STEP = ProtocolRequirement(
    families=("current_step",),
    requires_command=True,
    description="Current-step command or a verified manual step table",
)
_CURRENT_STEP_MULTI = ProtocolRequirement(
    families=("current_step",),
    requires_command=True,
    requires_multi_trial=True,
    description="Matched current-step sweeps with command amplitudes",
)
_EVOKED = ProtocolRequirement(
    families=("single_stim", "paired_pulse", "stimulus_train", "optogenetic"),
    requires_stimulus_timing=True,
    description="Stimulus timing from TTL, command, or verified manual timings",
)
_PPR = ProtocolRequirement(
    families=("paired_pulse",),
    requires_stimulus_timing=True,
    description="Paired-pulse stimulus timing from TTL or verified manual timings",
)
_TRAIN = ProtocolRequirement(
    families=("stimulus_train",),
    requires_stimulus_timing=True,
    description="Stimulus-train timing from TTL or verified manual timings",
)


BUILTIN_ANALYSIS_REQUIREMENTS: Dict[str, ProtocolRequirement] = {
    "rmp_analysis": _SIGNAL,
    "sag_ratio_analysis": _CURRENT_STEP,
    "rin_analysis": _CURRENT_STEP,
    "tau_analysis": _CURRENT_STEP,
    "iv_curve_analysis": _CURRENT_STEP_MULTI,
    "capacitance_analysis": _CURRENT_STEP,
    "passive_properties": _CURRENT_STEP,
    "spike_detection": _SIGNAL,
    "phase_plane_analysis": _SIGNAL,
    "single_spike": _SIGNAL,
    "excitability_analysis": _CURRENT_STEP_MULTI,
    "burst_analysis": _SIGNAL,
    "train_dynamics": _SIGNAL,
    "firing_dynamics": _CURRENT_STEP_MULTI,
    "event_detection_threshold": _SIGNAL,
    "event_detection_deconvolution": _SIGNAL,
    "synaptic_events": _SIGNAL,
    "optogenetic_sync": _EVOKED,
    "paired_pulse_ratio": _PPR,
    "stimulus_train_stp": _TRAIN,
    "evoked_responses": _EVOKED,
}


def requirement_for_analysis(name: str) -> ProtocolRequirement:
    """Return the protocol requirement declared by a supplied analysis or plugin.

    Built-in requirements remain the canonical defaults.  Plugins may opt in by
    placing a ``protocol_requirements`` mapping in their registry metadata.  A
    malformed plugin declaration deliberately falls back to signal-only so an
    optional extension cannot prevent the application from starting.
    """
    builtin_requirement = BUILTIN_ANALYSIS_REQUIREMENTS.get(name)
    if builtin_requirement is not None:
        return builtin_requirement

    try:
        from synaptipy.core.analysis.registry import AnalysisRegistry

        declaration = AnalysisRegistry.get_metadata(name).get("protocol_requirements")
    except (ImportError, AttributeError):
        return _SIGNAL

    if isinstance(declaration, ProtocolRequirement):
        return declaration
    if not isinstance(declaration, dict):
        return _SIGNAL

    try:
        families = tuple(str(family) for family in declaration.get("families", _SIGNAL.families))
        return ProtocolRequirement(
            families=families or _SIGNAL.families,
            requires_command=bool(declaration.get("requires_command", False)),
            requires_stimulus_timing=bool(declaration.get("requires_stimulus_timing", False)),
            requires_multi_trial=bool(declaration.get("requires_multi_trial", False)),
            description=str(declaration.get("description", "Plugin-declared protocol requirement")),
        )
    except (TypeError, ValueError):
        return _SIGNAL


def apply_builtin_protocol_requirements(registry: Any) -> None:
    """Attach requirements to built-in registrations without changing plugins."""
    for name, requirement in BUILTIN_ANALYSIS_REQUIREMENTS.items():
        metadata = registry.get_metadata(name)
        if metadata:
            registry.set_metadata(name, protocol_requirements=requirement.as_dict())


def resolve_protocols(
    recording: Any,
    trial_index: int,
    duration: Optional[float],
    analysis_name: str,
) -> List[ResolvedProtocol]:
    """Resolve executable segments and report requirement gaps without guessing.

    Recordings without a map remain executable but are marked ``needs_review``.
    Explicit incompatible assignments are marked ``incompatible`` and should be
    excluded by a batch planner.
    """
    protocol_map = getattr(recording, "protocol_map", None)
    # Readers and third-party callers may provide Recording-like objects without
    # a ProtocolMap. Treat those as an explicit signal-only/review state.
    if not isinstance(protocol_map, ProtocolMap):
        protocol_map = ProtocolMap()
    requirement = requirement_for_analysis(analysis_name)
    segments = protocol_map.analysis_segments_for_trial(trial_index, duration=duration)
    resolved: List[ResolvedProtocol] = []
    for assignment in segments:
        missing: List[str] = []
        explicit = not assignment.assignment_id.startswith("implicit-signal-only-")
        if assignment.protocol_family not in requirement.families:
            missing.append(f"requires protocol family: {', '.join(requirement.families)}")
        if requirement.requires_command and not (
            assignment.source == ProtocolSource.RECORDED
            or assignment.parameters.get("command")
            or "current_steps" in assignment.parameters
        ):
            missing.append("requires command waveform or verified manual step table")
        recorded_timing = assignment.source == ProtocolSource.RECORDED and bool(
            assignment.parameters.get("ttl_channel")
            or assignment.parameters.get("stimulus_times")
            or assignment.parameters.get("command")
        )
        verified_manual_timing = (
            assignment.source in (ProtocolSource.MANUAL, ProtocolSource.DRAWN, ProtocolSource.IMPORTED)
            and assignment.verified
            and bool(assignment.parameters.get("stimulus_times"))
        )
        if requirement.requires_stimulus_timing and not (recorded_timing or verified_manual_timing):
            missing.append("requires stimulus timing")
        if missing and (explicit or requirement.requires_stimulus_timing):
            status = "incompatible"
        elif missing:
            status = "needs_review"
        elif assignment.verified:
            status = "ready"
        else:
            status = "needs_review"
        resolved.append(ResolvedProtocol(assignment, trial_index, status, tuple(missing)))
    return resolved


def slice_segment(data: Any, time: Any, resolved: ResolvedProtocol) -> Tuple[Any, Any]:
    """Return views of a trace restricted to a resolved segment."""
    start = resolved.assignment.start_time
    end = resolved.assignment.end_time
    if start is None and end is None:
        return data, time
    import numpy as np

    values = np.asarray(data)
    times = np.asarray(time)
    mask = np.ones(times.shape, dtype=bool)
    if start is not None:
        mask &= times >= start
    if end is not None:
        mask &= times <= end
    return values[mask], times[mask]
