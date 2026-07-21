"""Protocol-map domain and protocol-aware batch regression tests."""

from pathlib import Path

import numpy as np

from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.data_model import Channel, Recording
from synaptipy.core.protocols import (
    BUILTIN_ANALYSIS_REQUIREMENTS,
    ProtocolAssignment,
    ProtocolMap,
    ProtocolSource,
    resolve_protocols,
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
        assert (
            AnalysisRegistry.get_metadata(name)["protocol_requirements"]
            == BUILTIN_ANALYSIS_REQUIREMENTS[name].as_dict()
        )
