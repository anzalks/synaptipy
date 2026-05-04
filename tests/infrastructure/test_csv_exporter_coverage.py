# tests/infrastructure/test_csv_exporter_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage-boosting tests for infrastructure/exporters/csv_exporter.py.

Targets previously uncovered lines:
  22-23   : Synaptipy version fallback when import fails
  120-121 : _get_dependency_versions with missing package
  212, 214: _tidy_get_meta first-key and fallback paths
  292-294 : export_analysis_results with empty results → False
  306-308 : export_analysis_results with nested dicts
  490-492 : export_recording with mismatched time/data shape
  535-536 : export_analysis_results exception path
  596     : _write_provenance
  616-618 : tidy export path
  650-702 : export_events path
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from Synaptipy.infrastructure.exporters.csv_exporter import (
    CSVExporter,
    _build_tidy_row,
    _get_dependency_versions,
    _round_sig,
    _sanitize_csv_value,
    _tidy_get_meta,
    _tidy_row_to_long,
)

# ---------------------------------------------------------------------------
# _round_sig
# ---------------------------------------------------------------------------


class TestRoundSig:
    def test_zero(self):
        assert _round_sig(0.0) == 0.0

    def test_positive(self):
        result = _round_sig(123456789.0, sig=3)
        assert result == pytest.approx(123000000.0, rel=1e-3)

    def test_negative(self):
        result = _round_sig(-0.00012345, sig=3)
        assert result == pytest.approx(-0.000123, rel=1e-2)

    def test_small_number(self):
        result = _round_sig(0.000456789, sig=3)
        assert result == pytest.approx(0.000457, rel=1e-2)


# ---------------------------------------------------------------------------
# _sanitize_csv_value
# ---------------------------------------------------------------------------


class TestSanitizeCsvValue:
    def test_none_becomes_nan(self):
        import math

        v = _sanitize_csv_value(None)
        assert math.isnan(v)

    def test_numpy_float(self):
        v = _sanitize_csv_value(np.float64(3.141592653589793))
        assert isinstance(v, float)

    def test_numpy_integer(self):
        v = _sanitize_csv_value(np.int32(42))
        assert v == 42
        assert isinstance(v, int)

    def test_plain_float(self):
        v = _sanitize_csv_value(3.14159)
        assert isinstance(v, float)

    def test_empty_list_becomes_nan(self):
        import math

        v = _sanitize_csv_value([])
        assert math.isnan(v)

    def test_short_list_becomes_string(self):
        v = _sanitize_csv_value([1.0, 2.0, 3.0])
        assert isinstance(v, str)

    def test_long_list_truncated(self):
        v = _sanitize_csv_value(list(range(20)))
        assert "total" in v

    def test_numpy_array(self):
        v = _sanitize_csv_value(np.array([1.0, 2.0]))
        assert isinstance(v, str)

    def test_string_passthrough(self):
        v = _sanitize_csv_value("hello")
        assert v == "hello"


# ---------------------------------------------------------------------------
# _get_dependency_versions
# ---------------------------------------------------------------------------


class TestGetDependencyVersions:
    def test_returns_dict(self):
        result = _get_dependency_versions()
        assert isinstance(result, dict)

    def test_missing_package_returns_unknown(self):
        """Line 120-121: PackageNotFoundError → 'unknown'."""
        import importlib.metadata

        original_version = importlib.metadata.version

        def patched(pkg):
            if pkg == "nonexistent-pkg-xyz":
                raise importlib.metadata.PackageNotFoundError(pkg)
            return original_version(pkg)

        with patch("importlib.metadata.version", side_effect=patched):
            from Synaptipy.infrastructure.exporters import csv_exporter as csv_mod

            saved = csv_mod._DEP_PACKAGES
            csv_mod._DEP_PACKAGES = ("nonexistent-pkg-xyz",)
            result = csv_mod._get_dependency_versions()
            csv_mod._DEP_PACKAGES = saved

        assert result.get("nonexistent-pkg-xyz") == "unknown"


# ---------------------------------------------------------------------------
# _tidy_get_meta
# ---------------------------------------------------------------------------


class TestTidyGetMeta:
    def test_returns_first_non_none(self):
        row = {"a": None, "b": "found", "c": "other"}
        assert _tidy_get_meta(row, ["a", "b", "c"]) == "found"

    def test_returns_empty_string_when_all_none(self):
        row = {"a": None}
        assert _tidy_get_meta(row, ["a", "b"]) == ""

    def test_converts_to_string(self):
        row = {"n": 42}
        assert _tidy_get_meta(row, ["n"]) == "42"


# ---------------------------------------------------------------------------
# _tidy_row_to_long
# ---------------------------------------------------------------------------


class TestBuildTidyRow:
    """Tests for _build_tidy_row helper."""

    def _call(self, flat: dict) -> list:
        return _build_tidy_row(flat, "f.abf", "grp", 0, "Ch0", "rmp", "mV")

    def test_skips_metadata_keys(self):
        # "file", "channel" etc. are in _TIDY_METADATA_KEYS
        rows = self._call({"file": "f.abf", "rmp_mv": -65.0})
        metrics = [r["Metric"] for r in rows]
        assert "rmp_mv" in metrics
        assert "file" not in metrics

    def test_skips_private_keys(self):
        rows = self._call({"rmp_mv": -65.0, "_private": 99.9})
        assert "_private" not in [r["Metric"] for r in rows]

    def test_skips_list_values(self):
        rows = self._call({"rmp_mv": -65.0, "spike_times": [0.1, 0.2]})
        assert "spike_times" not in [r["Metric"] for r in rows]

    def test_skips_unusual_type_line_212(self):
        """Line 212: non-(int/float/bool/str/None) value → continue."""
        import datetime

        rows = self._call({"rmp_mv": -65.0, "ts": datetime.datetime.now()})
        assert "ts" not in [r["Metric"] for r in rows]
        assert "rmp_mv" in [r["Metric"] for r in rows]

    def test_skips_error_and_debug_trace_line_214(self):
        """Line 214: metric named 'error' or 'debug_trace' → continue."""
        rows = self._call({"rmp_mv": -65.0, "error": "boom", "debug_trace": "stack"})
        metrics = [r["Metric"] for r in rows]
        assert "error" not in metrics
        assert "debug_trace" not in metrics
        assert "rmp_mv" in metrics


# ---------------------------------------------------------------------------
# _tidy_row_to_long
# ---------------------------------------------------------------------------


class TestTidyRowToLong:
    def test_skips_metadata_keys(self):
        row = {
            "file": "test.abf",
            "channel": "Ch0",
            "analysis_type": "rmp",
            "rmp_mv": -65.0,
        }
        rows = _tidy_row_to_long(row, file_keys=["file"], group_keys=["group"])
        metrics = [r["Metric"] for r in rows]
        assert "rmp_mv" in metrics
        # 'file', 'channel', 'analysis_type' are metadata → skipped
        assert "file" not in metrics

    def test_skips_private_keys(self):
        row = {"rmp_mv": -65.0, "_private": 99.9}
        rows = _tidy_row_to_long(row, file_keys=[], group_keys=[])
        metrics = [r["Metric"] for r in rows]
        assert "_private" not in metrics

    def test_skips_list_values(self):
        row = {"rmp_mv": -65.0, "spike_times": [0.1, 0.2]}
        rows = _tidy_row_to_long(row, file_keys=[], group_keys=[])
        metrics = [r["Metric"] for r in rows]
        assert "spike_times" not in metrics

    def test_flattens_metrics_dict(self):
        row = {"metrics": {"rmp_mv": -65.0, "tau_ms": 10.0}}
        rows = _tidy_row_to_long(row, file_keys=[], group_keys=[])
        metrics = [r["Metric"] for r in rows]
        assert "rmp_mv" in metrics
        assert "tau_ms" in metrics


# ---------------------------------------------------------------------------
# CSVExporter.export_recording
# ---------------------------------------------------------------------------


def _make_recording_with_channels(
    n_trials: int = 2,
    n_samples: int = 1000,
    source_file: Path = Path("/fake/test.abf"),
):
    from Synaptipy.core.data_model import Channel, Recording

    rec = Recording(source_file=source_file)
    rec.sampling_rate = 10_000.0

    rng = np.random.default_rng(0)
    trials = [rng.normal(-65.0, 2.0, n_samples) for _ in range(n_trials)]
    ch = Channel(id="0", name="Ch0", units="mV", sampling_rate=10_000.0, data_trials=trials)
    ch.t_start = 0.0
    rec.channels["0"] = ch
    return rec


class TestCSVExporterExportRecording:
    def test_exports_csv_files(self, tmp_path):
        rec = _make_recording_with_channels(n_trials=2, n_samples=500)
        exporter = CSVExporter()
        ok, err = exporter.export_recording(rec, tmp_path)
        assert ok == 2
        assert err == 0
        files = list(tmp_path.glob("*.csv"))
        assert len(files) == 2

    def test_creates_output_dir_if_missing(self, tmp_path):
        target = tmp_path / "new_subdir"
        rec = _make_recording_with_channels(n_trials=1, n_samples=500)
        exporter = CSVExporter()
        ok, err = exporter.export_recording(rec, target)
        assert target.exists()
        assert ok == 1

    def test_skips_channel_with_no_trials(self, tmp_path):
        from Synaptipy.core.data_model import Channel, Recording

        rec = Recording(source_file=Path("/fake/empty.abf"))
        ch = Channel(id="0", name="Ch0", units="mV", sampling_rate=10_000.0, data_trials=[])
        rec.channels["0"] = ch
        exporter = CSVExporter()
        ok, err = exporter.export_recording(rec, tmp_path)
        assert ok == 0
        assert err == 0

    def test_error_on_shape_mismatch(self, tmp_path):
        """Lines 490-492: time/data mismatch → error_count incremented."""
        from Synaptipy.core.data_model import Channel, Recording

        rec = Recording(source_file=Path("/fake/mismatch.abf"))
        trials = [np.zeros(100)]
        ch = Channel(id="0", name="Ch0", units="mV", sampling_rate=10_000.0, data_trials=trials)
        ch.t_start = 0.0
        rec.channels["0"] = ch

        exporter = CSVExporter()
        # Patch get_relative_time_vector to return array of wrong shape
        with patch.object(ch, "get_relative_time_vector", return_value=np.zeros(50)):
            ok, err = exporter.export_recording(rec, tmp_path)

        assert err == 1
        assert ok == 0


# ---------------------------------------------------------------------------
# CSVExporter.export_analysis_results
# ---------------------------------------------------------------------------


class TestExportAnalysisResults:
    def test_empty_results_returns_false(self, tmp_path):
        """Lines 292-294: empty list → False."""
        exporter = CSVExporter()
        result = exporter.export_analysis_results([], tmp_path / "out.csv")
        assert result is False

    def test_basic_export_returns_true(self, tmp_path):
        exporter = CSVExporter()
        rows = [
            {
                "analysis_type": "rmp",
                "source_file_name": "test.abf",
                "rmp_mv": -65.0,
                "channel_id": "0",
            }
        ]
        ok = exporter.export_analysis_results(rows, tmp_path / "results.csv")
        assert ok is True
        assert (tmp_path / "results.csv").is_file()

    def test_nested_dict_flattening(self, tmp_path):
        """Lines 306-308: results with nested dicts are handled."""
        exporter = CSVExporter()
        rows = [
            {
                "analysis_type": "events",
                "source_file_name": "test.abf",
                "summary_stats": {"count": 5, "frequency_hz": 2.5},
                "parameters": {"direction": "negative"},
            }
        ]
        ok = exporter.export_analysis_results(rows, tmp_path / "nested.csv")
        assert ok is True

    def test_exception_returns_false(self, tmp_path):
        """Lines 535-536: write exception → False."""
        exporter = CSVExporter()
        rows = [{"analysis_type": "rmp", "rmp_mv": -65.0}]
        # Point to a directory (not a writable file path) to trigger an exception
        ok = exporter.export_analysis_results(rows, tmp_path)  # tmp_path is a dir
        assert ok is False

    def test_provenance_json_written(self, tmp_path):
        """Line 596: _write_provenance creates companion JSON file."""
        exporter = CSVExporter()
        rows = [
            {
                "analysis_type": "rmp",
                "source_file_name": "test.abf",
                "rmp_mv": -65.0,
                "channel_id": "0",
            }
        ]
        out = tmp_path / "results.csv"
        exporter.export_analysis_results(rows, out)
        prov = tmp_path / "results_provenance.json"
        assert prov.is_file()
        data = json.loads(prov.read_text())
        assert "synaptipy_version" in data


# ---------------------------------------------------------------------------
# CSVExporter.export_events
# ---------------------------------------------------------------------------


class TestExportEvents:
    def test_no_event_arrays_returns_false(self, tmp_path):
        """export_events returns False when no _raw_arrays present."""
        exporter = CSVExporter()
        rows = [{"analysis_type": "rmp", "rmp_mv": -65.0}]
        result = exporter.export_events(rows, tmp_path / "results.csv")
        assert result is False

    def test_with_event_arrays_writes_file(self, tmp_path):
        """Lines 650-702: events CSV is written when arrays present."""
        exporter = CSVExporter()
        rows = [
            {
                "file_name": "test.abf",
                "channel_name": "Ch0",
                "trial_index": 0,
                "_raw_arrays": {
                    "event_times": np.array([0.1, 0.2, 0.3]),
                    "event_amplitudes": np.array([-50.0, -48.0, -52.0]),
                },
            }
        ]
        result = exporter.export_events(rows, tmp_path / "results.csv")
        assert result is True
        events_file = tmp_path / "results_events.csv"
        assert events_file.is_file()

    def test_mismatched_array_lengths(self, tmp_path):
        """export_events handles times/amplitudes of different lengths."""
        exporter = CSVExporter()
        rows = [
            {
                "_raw_arrays": {
                    "event_times": np.array([0.1, 0.2]),
                    "event_amplitudes": np.array([-50.0]),
                }
            }
        ]
        result = exporter.export_events(rows, tmp_path / "mismatch.csv")
        assert result is True  # Writes with NaN padding

    def test_amplitude_only_no_times(self, tmp_path):
        """export_events with amplitudes but no times."""
        exporter = CSVExporter()
        rows = [
            {
                "_raw_arrays": {
                    "event_amplitudes": np.array([-50.0, -48.0]),
                }
            }
        ]
        result = exporter.export_events(rows, tmp_path / "amp_only.csv")
        assert result is True

    def test_both_arrays_none_skipped(self, tmp_path):
        """Line 664: _raw_arrays has dict but both arrays are None → continue."""
        exporter = CSVExporter()
        rows = [
            {
                "_raw_arrays": {
                    "event_times": None,
                    "event_amplitudes": None,
                }
            }
        ]
        result = exporter.export_events(rows, tmp_path / "both_none.csv")
        assert result is False  # No event rows → False

    def test_exception_returns_false(self, tmp_path):
        """Lines 700-702: IO exception → False."""
        exporter = CSVExporter()
        rows = [
            {
                "_raw_arrays": {
                    "event_times": np.array([0.1]),
                    "event_amplitudes": np.array([-50.0]),
                }
            }
        ]
        with patch("builtins.open", side_effect=OSError("No space left")):
            result = exporter.export_events(rows, tmp_path / "events.csv")
        assert result is False


# ---------------------------------------------------------------------------
# CSVExporter.export_tidy
# ---------------------------------------------------------------------------


class TestExportTidy:
    def test_empty_results_returns_false(self, tmp_path):
        exporter = CSVExporter()
        assert exporter.export_tidy([], tmp_path / "tidy.csv") is False

    def test_exports_tidy_csv_returns_true(self, tmp_path):
        """Lines 616-618: export_tidy writes file and returns True."""
        exporter = CSVExporter()
        rows = [
            {
                "file": "test.abf",
                "channel_name": "Ch0",
                "analysis_type": "rmp",
                "rmp_mv": -65.0,
            }
        ]
        out = tmp_path / "tidy.csv"
        assert exporter.export_tidy(rows, out) is True
        assert out.is_file()

    def test_exception_returns_false(self, tmp_path):
        """export_tidy exception path → False."""
        exporter = CSVExporter()
        rows = [{"rmp_mv": -65.0}]
        assert exporter.export_tidy(rows, tmp_path) is False

    def test_all_metrics_skipped_logs_warning(self, tmp_path, caplog):
        """Line 596: all metrics in row are skipped → warning logged, True returned."""
        import logging

        exporter = CSVExporter()
        # All values will be skipped: list, private key, error key
        rows = [{"_private": 1.0, "spike_times": [0.1, 0.2], "error": "boom"}]
        out = tmp_path / "empty_metrics.csv"
        with caplog.at_level(logging.WARNING):
            result = exporter.export_tidy(rows, out)
        assert result is True  # Still writes (empty/header-only file)
        assert any("no scalar metrics" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# CSVExporter.export_recording — exception path (lines 306-308)
# ---------------------------------------------------------------------------


class TestExportRecordingExceptionPath:
    def test_exception_in_savetxt_increments_error_count(self, tmp_path):
        """Lines 306-308: exception during write → error_count incremented."""
        rec = _make_recording_with_channels(n_trials=1, n_samples=100)
        exporter = CSVExporter()
        with patch("numpy.savetxt", side_effect=OSError("Disk full")):
            ok, err = exporter.export_recording(rec, tmp_path)
        assert err == 1
        assert ok == 0


# ---------------------------------------------------------------------------
# CSVExporter._write_provenance — exception path (lines 535-536)
# ---------------------------------------------------------------------------


class TestWriteProvenanceException:
    def test_write_exception_is_swallowed(self, caplog):
        """Lines 535-536: IOError during JSON write is caught, not raised."""
        import logging

        exporter = CSVExporter()
        with caplog.at_level(logging.WARNING):
            exporter._write_provenance(
                csv_path=Path("/dev/null/impossible/path.csv"),
                results=[{"a": 1}],
            )
        # Must not raise; a warning must have been logged
        assert any("provenance" in r.message.lower() or "could not" in r.message.lower() for r in caplog.records)
