"""Protocol-map domain and protocol-aware batch regression tests."""

from pathlib import Path

import numpy as np
import pytest

from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.data_model import Channel, Recording
from synaptipy.core.protocols import (
    BUILTIN_ANALYSIS_REQUIREMENTS,
    ProtocolAssignment,
    ProtocolMap,
    ProtocolSource,
    apply_builtin_protocol_requirements,
    requirement_for_analysis,
    resolve_protocols,
    slice_segment,
)


def _recording(value: float, name: str) -> Recording:
    recording = Recording(Path(name))
    channel = Channel("Vm", "Vm", "mV", 1_000.0, [np.full(100, value), np.full(100, value + 2)])
    recording.channels = {"Vm": channel}
    return recording


def test_protocol_map_rejects_overlapping_analysis_segments_but_allows_annotations():
    protocol_map = ProtocolMap()
    protocol_map.add(ProtocolAssignment("signal_only", (0,), 0.0, 0.5))
    protocol_map.add(ProtocolAssignment("drug", (0,), 0.2, 0.7, is_analysis_segment=False))

    try:
        protocol_map.add(ProtocolAssignment("current_step", (0,), 0.4, 0.8))
    except ValueError as exc:
        assert "cannot overlap" in str(exc)
    else:
        raise AssertionError("Overlapping analysis segments must be rejected")


def test_explicit_protocol_incompatibility_is_not_silent():
    recording = _recording(-65.0, "manual.abf")
    recording.protocol_map.add(
        ProtocolAssignment("paired_pulse", (0,), 0.0, 0.05, source=ProtocolSource.MANUAL, verified=True)
    )

    resolved = resolve_protocols(recording, 0, 0.1, "rin_analysis")
    assert resolved[0].status == "incompatible"
    assert "current_step" in resolved[0].missing[0]


def test_protocol_map_round_trip_and_verified_manual_requirements():
    source = ProtocolMap()
    source.add(
        ProtocolAssignment(
            "current_step",
            (0, 2),
            0.01,
            0.08,
            profile_id="iv_steps",
            source=ProtocolSource.MANUAL,
            parameters={"current_steps": [-100, -50]},
            verified=True,
        )
    )
    restored = ProtocolMap.from_dict(source.as_dict())
    assignment = restored.assignments[0]
    assert assignment.trial_indices == (0, 2)
    assert assignment.fingerprint == source.assignments[0].fingerprint

    recording = _recording(-65.0, "steps.abf")
    recording.protocol_map = restored
    assert resolve_protocols(recording, 0, 0.1, "rin_analysis")[0].status == "ready"


def test_cross_file_average_honours_selected_trials_and_file_balancing():
    analysis_name = "_protocol_cross_file_average_test"
    AnalysisRegistry.register(analysis_name, label="Test", ui_params=[])(
        lambda data, time, sampling_rate, **kwargs: {"mean": float(np.mean(data))}
    )
    first = _recording(1.0, "first.abf")
    second = _recording(5.0, "second.abf")
    # Select trial 1 in each file: values are 3 and 7, whose file-balanced mean is 5.
    engine = BatchAnalysisEngine()
    result = engine.run_batch(
        [first, second],
        [{"analysis": analysis_name, "scope": "selected_trials_average", "params": {"trial_indices": "1"}}],
        cross_file_average=True,
    )
    assert len(result) == 1
    assert result.iloc[0]["mean"] == 5.0
    assert result.iloc[0]["contributing_file_count"] == 2
    AnalysisRegistry._registry.pop(analysis_name, None)
    AnalysisRegistry._metadata.pop(analysis_name, None)
    AnalysisRegistry._original_metadata.pop(analysis_name, None)


def test_cross_file_average_keeps_explicit_protocol_profiles_separate():
    analysis_name = "_protocol_cross_file_group_test"
    AnalysisRegistry.register(analysis_name, label="Test", ui_params=[])(
        lambda data, time, sampling_rate, **kwargs: {"mean": float(np.mean(data))}
    )
    first = _recording(1.0, "first.abf")
    second = _recording(5.0, "second.abf")
    for recording in (first, second):
        recording.protocol_map.add(
            ProtocolAssignment("signal_only", (0,), profile_id="baseline", source=ProtocolSource.MANUAL, verified=True)
        )
        recording.protocol_map.add(
            ProtocolAssignment("signal_only", (1,), profile_id="drug", source=ProtocolSource.MANUAL, verified=True)
        )
    result = BatchAnalysisEngine().run_batch(
        [first, second], [{"analysis": analysis_name, "scope": "all_trials", "params": {}}], cross_file_average=True
    )
    assert len(result) == 2
    assert set(result["protocol_profile"]) == {"baseline", "drug"}
    assert set(result["contributing_file_count"]) == {2}
    AnalysisRegistry._registry.pop(analysis_name, None)
    AnalysisRegistry._metadata.pop(analysis_name, None)
    AnalysisRegistry._original_metadata.pop(analysis_name, None)


def test_normal_batch_runs_each_explicit_segment_separately():
    analysis_name = "_protocol_segment_test"
    AnalysisRegistry.register(analysis_name, label="Test", ui_params=[])(
        lambda data, time, sampling_rate, **kwargs: {"sample_count": len(data)}
    )
    recording = Recording(Path("segments.abf"))
    recording.channels = {"Vm": Channel("Vm", "Vm", "mV", 100.0, [np.arange(100, dtype=float)])}
    recording.protocol_map.add(
        ProtocolAssignment("signal_only", (0,), 0.0, 0.4, source=ProtocolSource.MANUAL, verified=True)
    )
    recording.protocol_map.add(
        ProtocolAssignment("signal_only", (0,), 0.5, 0.9, source=ProtocolSource.MANUAL, verified=True)
    )
    result = BatchAnalysisEngine().run_batch(
        [recording], [{"analysis": analysis_name, "scope": "all_trials", "params": {}}]
    )
    assert len(result) == 2
    assert set(result["protocol_status"]) == {"ready"}
    assert set(result["sample_count"]) == {41}
    AnalysisRegistry._registry.pop(analysis_name, None)
    AnalysisRegistry._metadata.pop(analysis_name, None)
    AnalysisRegistry._original_metadata.pop(analysis_name, None)


def test_every_supplied_analysis_declares_protocol_requirements():
    import synaptipy.core.analysis  # noqa: F401 - trigger supplied registrations

    supplied = set(AnalysisRegistry.list_analysis())
    assert set(BUILTIN_ANALYSIS_REQUIREMENTS).issubset(supplied)
    for name in BUILTIN_ANALYSIS_REQUIREMENTS:
        metadata = AnalysisRegistry.get_metadata(name)
        assert metadata["protocol_requirements"] == BUILTIN_ANALYSIS_REQUIREMENTS[name].as_dict()
        assert metadata["api_version"] == 1
        assert metadata["result_schema_version"] == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"trial_indices": ()}, "at least one trial"),
        ({"trial_indices": (0,), "start_time": 1.0, "end_time": 1.0}, "later than"),
    ],
)
def test_assignment_validates_required_trials_and_time_order(kwargs, message):
    with pytest.raises(ValueError, match=message):
        ProtocolAssignment("signal_only", **kwargs)


def test_assignment_normalises_trials_source_and_fingerprint():
    assignment = ProtocolAssignment(
        "current_step",
        (3, 1, 3),
        source="manual",
        parameters={"b": 2, "a": 1},
    )
    same = ProtocolAssignment(
        "current_step",
        (1,),
        source=ProtocolSource.MANUAL,
        parameters={"a": 1, "b": 2},
    )

    assert assignment.trial_indices == (1, 3)
    assert assignment.source is ProtocolSource.MANUAL
    assert assignment.fingerprint == same.fingerprint
    assert ProtocolAssignment("current_step", (1,), profile_id="other").fingerprint != assignment.fingerprint


def test_assignment_overlap_respects_trials_and_time_windows():
    base = ProtocolAssignment("signal_only", (0,), 0.1, 0.3)
    assert base.overlaps(ProtocolAssignment("signal_only", (0,), 0.2, 0.4))
    assert not base.overlaps(ProtocolAssignment("signal_only", (1,), 0.2, 0.4))
    assert not base.overlaps(ProtocolAssignment("signal_only", (0,), 0.3, 0.4))
    assert base.overlaps(ProtocolAssignment("signal_only", (0, 1)))


def test_protocol_map_filters_sorts_removes_and_uses_signal_only_fallback():
    first = ProtocolAssignment("signal_only", (0,), 0.4, 0.5)
    second = ProtocolAssignment("signal_only", (0,), 0.1, 0.2)
    note = ProtocolAssignment("drug", (0,), is_analysis_segment=False)
    protocol_map = ProtocolMap([first, second, note])

    assert protocol_map.assignments_for_trial(0) == [second, first, note]
    assert protocol_map.assignments_for_trial(0, include_annotations=False) == [second, first]
    assert protocol_map.remove(first.assignment_id)
    assert not protocol_map.remove("not-present")
    assert protocol_map.analysis_segments_for_trial(2, 0.8)[0].source is ProtocolSource.SIGNAL_ONLY
    fallback = protocol_map.analysis_segments_for_trial(2, 0.8)[0]
    assert fallback.protocol_family == "signal_only"
    assert fallback.start_time == 0.0 and fallback.end_time == 0.8


def test_protocol_map_serialisation_ignores_derived_and_unknown_keys():
    assignment = ProtocolAssignment("signal_only", (0,), source=ProtocolSource.DRAWN)
    payload = assignment.as_dict()
    payload["unknown"] = "ignored"
    rebuilt = ProtocolAssignment.from_dict(payload)

    assert rebuilt.source is ProtocolSource.DRAWN
    assert rebuilt.assignment_id == assignment.assignment_id
    assert ProtocolMap.from_dict(None).assignments == []
    assert ProtocolMap.from_dict({"assignments": [payload]}).assignments[0].as_dict() == rebuilt.as_dict()


def test_protocol_requirements_default_and_registry_application():
    assert requirement_for_analysis("third_party_plugin").families == ("signal_only",)

    class Registry:
        def __init__(self):
            self.applied = {}

        def get_metadata(self, name):
            return {"name": name} if name in {"rmp_analysis", "rin_analysis"} else None

        def set_metadata(self, name, **metadata):
            self.applied[name] = metadata

    registry = Registry()
    apply_builtin_protocol_requirements(registry)
    assert set(registry.applied) == {"rmp_analysis", "rin_analysis"}
    assert registry.applied["rin_analysis"]["protocol_requirements"]["requires_command"]


def test_resolve_protocols_covers_legacy_ready_and_missing_context_states():
    recording = _recording(-65.0, "protocols.abf")

    legacy = resolve_protocols(recording, 0, 0.1, "rin_analysis")[0]
    assert legacy.status == "needs_review"
    assert legacy.missing

    recording.protocol_map.add(
        ProtocolAssignment(
            "current_step",
            (0,),
            source=ProtocolSource.RECORDED,
            verified=True,
        )
    )
    assert resolve_protocols(recording, 0, 0.1, "rin_analysis")[0].status == "ready"

    recording.protocol_map = ProtocolMap(
        [
            ProtocolAssignment(
                "paired_pulse",
                (0,),
                parameters={"stimulus_times": [0.01, 0.03]},
                verified=True,
            )
        ]
    )
    assert resolve_protocols(recording, 0, 0.1, "paired_pulse_ratio")[0].status == "ready"

    recording.protocol_map = object()
    assert resolve_protocols(recording, 0, 0.1, "rmp_analysis")[0].status == "needs_review"


def test_slice_segment_keeps_full_trace_or_applies_inclusive_bounds():
    data = np.arange(5)
    time = np.arange(5, dtype=float) * 0.1
    recording = _recording(-65.0, "slice.abf")
    recording.protocol_map.add(ProtocolAssignment("signal_only", (0,)))
    full = resolve_protocols(recording, 0, 0.4, "rmp_analysis")[0]
    full_data, full_time = slice_segment(data, time, full)
    assert full_data is data and full_time is time

    clipped = full.__class__(
        ProtocolAssignment("signal_only", (0,), 0.1, 0.3),
        0,
        "ready",
    )
    clipped_data, clipped_time = slice_segment(data, time, clipped)
    assert clipped_data.tolist() == [1, 2]
    assert clipped_time.tolist() == [0.1, 0.2]

    empty = full.__class__(ProtocolAssignment("signal_only", (0,), 1.0, 1.1), 0, "ready")
    assert len(slice_segment(data, time, empty)[0]) == 0


def _register_test_analysis(name, function):
    AnalysisRegistry.register(name, label="Protocol coverage test", ui_params=[])(function)
    return name


def _remove_test_analysis(name):
    AnalysisRegistry._registry.pop(name, None)
    AnalysisRegistry._metadata.pop(name, None)
    AnalysisRegistry._original_metadata.pop(name, None)


def test_cross_file_protocol_planner_handles_unknown_analysis_and_invalid_selection():
    recording = _recording(1.0, "invalid-selection.abf")
    engine = BatchAnalysisEngine()

    unknown = engine.run_batch(
        [recording], [{"analysis": "does_not_exist", "scope": "all_trials", "params": {}}], cross_file_average=True
    )
    assert unknown.iloc[0]["error"] == "Analysis is not registered"

    name = "_protocol_invalid_selection_test"
    _register_test_analysis(name, lambda data, time, sampling_rate, **kwargs: {"mean": float(np.mean(data))})
    try:
        invalid = engine.run_batch(
            [recording],
            [{"analysis": name, "scope": "selected_trials", "params": {"trial_indices": "99"}}],
            cross_file_average=True,
        )
        assert "exceeds available trials" in invalid.iloc[0]["error"]
    finally:
        _remove_test_analysis(name)


def test_cross_file_protocol_planner_skips_unsupported_and_incompatible_segments():
    unsupported = _recording(1.0, "unsupported.abf")
    unsupported.channels["Vm"].units = "unsupported-unit"
    assert (
        BatchAnalysisEngine()
        .run_batch(
            [unsupported], [{"analysis": "rmp_analysis", "scope": "all_trials", "params": {}}], cross_file_average=True
        )
        .empty
    )

    incompatible = _recording(1.0, "incompatible.abf")
    incompatible.protocol_map.add(ProtocolAssignment("signal_only", (0,), verified=True))
    assert (
        BatchAnalysisEngine()
        .run_batch(
            [incompatible],
            [{"analysis": "rin_analysis", "scope": "first_trial", "params": {}}],
            cross_file_average=True,
        )
        .empty
    )

    empty_segment = _recording(1.0, "empty-segment.abf")
    empty_segment.protocol_map.add(ProtocolAssignment("signal_only", (0,), 1.0, 1.1, verified=True))
    assert (
        BatchAnalysisEngine()
        .run_batch(
            [empty_segment],
            [{"analysis": "rmp_analysis", "scope": "first_trial", "params": {}}],
            cross_file_average=True,
        )
        .empty
    )


def test_cross_file_protocol_planner_records_timebase_exclusions():
    first = _recording(1.0, "first-time.abf")
    second = _recording(5.0, "second-time.abf")
    second.channels["Vm"].sampling_rate = 500.0
    name = "_protocol_timebase_exclusion_test"
    _register_test_analysis(name, lambda data, time, sampling_rate, **kwargs: {"mean": float(np.mean(data))})
    try:
        result = BatchAnalysisEngine().run_batch(
            [first, second], [{"analysis": name, "scope": "first_trial", "params": {}}], cross_file_average=True
        )
        assert result.iloc[0]["contributing_file_count"] == 1
        assert result.iloc[0]["cross_file_exclusions"] == "list"
        assert "incompatible segment time base" in result.iloc[0]["_cross_file_exclusions_obj"][0]
    finally:
        _remove_test_analysis(name)


def test_cross_file_protocol_planner_normalises_metrics_scalars_and_parameters():
    calls = []

    def metrics_analysis(data, time, sampling_rate, **kwargs):
        calls.append(kwargs)
        return {"metrics": {"mean": float(np.mean(data))}}

    name = "_protocol_metrics_result_test"
    _register_test_analysis(name, metrics_analysis)
    try:
        result = BatchAnalysisEngine().run_batch(
            [_recording(1.0, "metrics.abf")],
            [{"analysis": name, "scope": "specific_trial", "params": {"trial_index": 1, "keep": 7}}],
            cross_file_average=True,
        )
        assert result.iloc[0]["mean"] == 3.0
        assert calls == [{"keep": 7}]
    finally:
        _remove_test_analysis(name)

    scalar = "_protocol_scalar_result_test"
    _register_test_analysis(scalar, lambda data, time, sampling_rate, **kwargs: 42)
    try:
        result = BatchAnalysisEngine().run_batch(
            [_recording(1.0, "scalar.abf")],
            [{"analysis": scalar, "scope": "first_trial", "params": {}}],
            cross_file_average=True,
        )
        assert result.iloc[0]["result"] == 42
    finally:
        _remove_test_analysis(scalar)


def test_cross_file_protocol_planner_reports_analysis_and_load_errors(monkeypatch):
    name = "_protocol_analysis_error_test"

    def raise_error(*args, **kwargs):
        raise RuntimeError("deliberate analysis failure")

    _register_test_analysis(name, raise_error)
    try:
        result = BatchAnalysisEngine().run_batch(
            [_recording(1.0, "error.abf")],
            [{"analysis": name, "scope": "first_trial", "params": {}}],
            cross_file_average=True,
        )
        assert "deliberate analysis failure" in result.iloc[0]["error"]
        assert "RuntimeError" in result.iloc[0]["debug_trace"]
    finally:
        _remove_test_analysis(name)

    engine = BatchAnalysisEngine()
    monkeypatch.setattr(
        engine.neo_adapter, "read_recording", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("bad file"))
    )
    progress = []
    result = engine.run_batch(
        [Path("broken.abf")],
        [{"analysis": "rmp_analysis", "scope": "all_trials", "params": {}}],
        cross_file_average=True,
        progress_callback=lambda *args: progress.append(args),
    )
    assert result.empty
    assert progress[-1][-1] == "Cross-file average complete."
