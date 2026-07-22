"""Shared, auditable trial eligibility decisions for scientific workflows."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

import numpy as np


@dataclass(frozen=True)
class TrialQCDecision:
    """One trial's eligibility and the reason supporting that decision."""

    trial_index: int
    status: str
    reason: str = ""

    @property
    def included(self) -> bool:
        return self.status == "included"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def assess_trial_eligibility(
    data: Any,
    time: Any,
    trial_index: int,
    manually_excluded: Optional[Iterable[int]] = None,
) -> TrialQCDecision:
    """Return a conservative eligibility decision for one trace.

    This shared baseline intentionally makes only objective exclusion decisions:
    explicit user exclusion, empty data, non-finite values, and invalid time
    axes. Analysis-specific quality checks remain additional evidence rather
    than silently changing a trial's inclusion state.
    """
    if trial_index in set(manually_excluded or ()):
        return TrialQCDecision(trial_index, "excluded", "manual exclusion")
    trace = np.asarray(data, dtype=float)
    axis = np.asarray(time, dtype=float)
    if trace.size == 0 or axis.size == 0:
        return TrialQCDecision(trial_index, "excluded", "empty trace or time axis")
    if trace.size != axis.size:
        return TrialQCDecision(trial_index, "excluded", "trace and time axis length differ")
    if not np.all(np.isfinite(trace)):
        return TrialQCDecision(trial_index, "excluded", "trace contains non-finite values")
    if not np.all(np.isfinite(axis)) or (axis.size > 1 and np.any(np.diff(axis) <= 0)):
        return TrialQCDecision(trial_index, "excluded", "time axis is not strictly increasing")
    return TrialQCDecision(trial_index, "included")


def summarise_trial_qc(decisions: Iterable[TrialQCDecision]) -> Dict[str, Any]:
    """Return export-safe aggregate provenance for trial eligibility."""
    rows: List[TrialQCDecision] = list(decisions)
    included = [row.trial_index for row in rows if row.included]
    excluded = [row for row in rows if not row.included]
    return {
        "qc_included_trial_indices": ",".join(str(index) for index in included),
        "qc_excluded_trial_indices": ",".join(str(row.trial_index) for row in excluded),
        "qc_excluded_reasons": "; ".join(f"{row.trial_index}: {row.reason}" for row in excluded),
        "qc_included_trial_count": len(included),
        "qc_excluded_trial_count": len(excluded),
    }
