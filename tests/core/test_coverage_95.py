"""Focused behavioural tests for well-defined low-frequency runtime paths."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from synaptipy.core.analysis.contracts import AnalysisResult
from synaptipy.core.analysis.cross_file_utils import (
    CrossFileAverageResult,
    CrossFileCompatibilityReport,
    compute_cross_file_average,
    extract_per_file_trace,
    sampling_rate_from_timebase,
    time_bases_compatible,
)
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.data_model import Recording
from synaptipy.core.protocols import (
    ProtocolAssignment,
    ProtocolMap,
    ProtocolRequirement,
    ProtocolSource,
    requirement_for_analysis,
)
from synaptipy.core.trial_qc import assess_trial_eligibility
from synaptipy.infrastructure.file_readers.format_support import format_support
from synaptipy.shared.data_cache import DataCache
from synaptipy.shared.xlsx_exporter import _cell_xml, _normalise_value


def test_analysis_result_coercion_handles_canonical_scalar_and_list_outputs():
    """The result boundary preserves canonical results and normalises legacy shapes."""
    canonical = AnalysisResult("example", metrics={"value": 1})

    assert AnalysisResult.from_raw("ignored", canonical) is canonical
    assert AnalysisResult.from_raw("scalar", {"metrics": 4}).metrics == {"result": 4}
    assert AnalysisResult.from_raw("list", [1, 2]).metrics == {"list_results": [1, 2]}


def test_trial_qc_serialises_and_rejects_empty_or_non_monotonic_axes():
    """Objective trial-quality exclusions retain their exportable rationale."""
    empty = assess_trial_eligibility([], [], 2)
    non_monotonic = assess_trial_eligibility([1.0, 2.0], [0.1, 0.1], 3)

    assert empty.as_dict() == {"trial_index": 2, "status": "excluded", "reason": "empty trace or time axis"}
    assert non_monotonic.reason == "time axis is not strictly increasing"


def test_registry_execute_missing_and_preprocessor_paths_are_explicit():
    """Missing analyses fail loudly while preprocessors deliberately remain raw."""
    name = "_coverage_preprocessor"
    try:
        with pytest.raises(KeyError, match="not registered"):
            AnalysisRegistry.execute("_not_registered_for_coverage")

        @AnalysisRegistry.register_processor(name)
        def _preprocessor(data, time, sampling_rate):
            return {"samples": len(data), "sampling_rate": sampling_rate}

        assert AnalysisRegistry.execute(name, [1, 2], [], 10.0) == {"samples": 2, "sampling_rate": 10.0}
        assert AnalysisRegistry.set_metadata("_missing_metadata_for_coverage", label="unused") is False
    finally:
        AnalysisRegistry._registry.pop(name, None)
        AnalysisRegistry._metadata.pop(name, None)
        AnalysisRegistry._original_metadata.pop(name, None)


def test_plugin_protocol_requirement_accepts_objects_and_rejects_invalid_declarations():
    """Plugin metadata can opt in safely without destabilising protocol resolution."""
    valid_name = "_coverage_protocol_object"
    invalid_name = "_coverage_protocol_invalid"

    class InvalidRequirement(dict):
        def get(self, key, default=None):
            raise ValueError("invalid requirement metadata")

    requirement = ProtocolRequirement(("optogenetic",), requires_stimulus_timing=True)
    try:
        AnalysisRegistry.register(valid_name, protocol_requirements=requirement)(lambda *_args, **_kwargs: {})
        AnalysisRegistry.register(invalid_name, protocol_requirements=InvalidRequirement())(
            lambda *_args, **_kwargs: {}
        )

        assert requirement_for_analysis(valid_name) is requirement
        assert requirement_for_analysis(invalid_name).families == ("signal_only",)
    finally:
        for name in (valid_name, invalid_name):
            AnalysisRegistry._registry.pop(name, None)
            AnalysisRegistry._metadata.pop(name, None)
            AnalysisRegistry._original_metadata.pop(name, None)


def test_stimulus_timing_requirement_marks_unverified_manual_protocol_incompatible():
    """Timing-dependent analyses cannot silently run on an unverified manual map."""
    from synaptipy.core.protocols import resolve_protocols

    recording = MagicMock()
    recording.protocol_map = ProtocolMap()
    recording.protocol_map.add(ProtocolAssignment("optogenetic", (0,), source=ProtocolSource.MANUAL, verified=False))

    resolved = resolve_protocols(recording, 0, 1.0, "optogenetic_sync")

    assert resolved[0].status == "incompatible"
    assert "requires stimulus timing" in resolved[0].missing


def test_data_cache_invalidates_a_recording_replaced_on_disk(tmp_path):
    """A stale cache entry is released rather than returned after a file changes."""
    DataCache.reset_instance()
    cache = DataCache()
    path = tmp_path / "recording.abf"
    path.write_bytes(b"old")
    recording = Recording(source_file=path)
    cache.put(path, recording)

    path.write_bytes(b"replacement data")

    try:
        assert cache.get(path) is None
        assert cache.size() == 0
    finally:
        DataCache.reset_instance()


def test_cross_file_time_validation_rejects_invalid_physical_grids():
    """Invalid, non-monotonic, and underspecified grids are never pooled."""
    assert CrossFileAverageResult(None, None, 0, False, CrossFileCompatibilityReport("0")).is_empty
    assert not time_bases_compatible([], [0.0])
    assert not time_bases_compatible([0.1, 0.0], [0.0, 0.1])
    assert not time_bases_compatible([0.0, 0.1], [0.1, 0.0])
    assert not time_bases_compatible([0.0], [0.1])
    assert sampling_rate_from_timebase([0.0]) is None


def test_cross_file_average_reports_reader_failures_and_missing_recordings():
    """Every unreadable source remains visible in averaging provenance."""
    failing_adapter = MagicMock()
    failing_adapter.read_recording.side_effect = RuntimeError("unreadable")
    missing_adapter = MagicMock()
    missing_adapter.read_recording.return_value = None
    item = {"path": Path("missing.abf")}

    failed = compute_cross_file_average([item], [0], 0, failing_adapter)
    missing = compute_cross_file_average([item], [0], 0, missing_adapter)

    assert failed.is_empty and "could not load recording" in failed.compatibility_report.entries[0].reason
    assert missing.is_empty and missing.compatibility_report.entries[0].reason == "could not load recording"


def test_cross_file_average_rejects_incompatible_trials_and_physical_dimensions():
    """Averaging excludes mismatched time grids and voltage/current mixtures."""
    channel = MagicMock()
    channel.get_data.side_effect = [np.array([1.0, 2.0]), np.array([3.0, 4.0])]
    channel.get_relative_time_vector.side_effect = [np.array([0.0, 1.0]), np.array([0.0, 0.8])]
    recording = MagicMock(channels={0: channel})
    assert extract_per_file_trace({"path": Path("bad-grid.abf")}, [0, 1], 0, MagicMock(), recording=recording) is None

    voltage_channel = MagicMock(units="mV")
    voltage_channel.get_data.return_value = np.array([1.0, 2.0])
    voltage_channel.get_relative_time_vector.return_value = np.array([0.0, 1.0])
    voltage = SimpleNamespace(channels={0: voltage_channel})
    current = SimpleNamespace(channels={0: SimpleNamespace(units="pA")})
    adapter = MagicMock()
    adapter.read_recording.side_effect = [voltage, current]
    result = compute_cross_file_average([{"path": Path("voltage.abf")}, {"path": Path("current.abf")}], [0], 0, adapter)

    assert result.contributing_file_count == 1
    assert result.compatibility_report.entries[-1].reason == "physical dimension differs from included channels"


def test_export_and_format_helpers_preserve_empty_date_and_tier_values():
    """Portable exports retain XML-safe empties, dates, and format declarations."""
    assert _cell_xml("A1", None) == '<c r="A1"/>'
    assert _normalise_value(float("nan")) is None
    assert _normalise_value(date(2026, 7, 22)) == "2026-07-22"
    assert format_support(".abf").as_dict()["tier"] == "validated"
