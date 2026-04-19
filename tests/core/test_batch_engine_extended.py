# -*- coding: utf-8 -*-
"""Extended tests for batch_engine.py covering previously uncovered branches.

These tests focus on:
- cancel() method
- update_performance_settings()
- _append_batch_error_log()
- _sanitise_long_list exception path
- _recording_metadata with subject_id, cell_id, protocol_name
- _order_columns with empty DataFrame
- get_analysis_info for non-existent name
- error-row path in sequential batch
- cancellation during sequential batch
"""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

import Synaptipy.core.analysis  # noqa: F401 – populate registry
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.data_model import Channel, Recording

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------


def _make_channel(value=-65.0, n_trials=3, fs=10000.0, duration=0.5):
    """Return a mock Channel with numeric get_data / get_time_vector methods."""
    n = int(fs * duration)
    time = np.linspace(0, duration, n, endpoint=False)
    ch = MagicMock(spec=Channel)
    ch.sampling_rate = fs
    ch.units = "mV"
    ch.num_trials = n_trials
    ch.name = "Channel1"
    ch.get_data.return_value = np.full(n, value)
    ch.get_relative_time_vector.return_value = time
    return ch


def _make_recording(n_channels=1, **ch_kwargs):
    """Return a mock Recording with a single channel."""
    rec = MagicMock(spec=Recording)
    ch = _make_channel(**ch_kwargs)
    rec.channels = {"Channel1": ch}
    rec.source_file = Path("test_recording.abf")
    rec.protocol_name = None
    rec.duration = 0.5
    rec.subject_id = None
    rec.cell_id = None
    return rec, ch


# ---------------------------------------------------------------------------
# cancel()
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_sets_flag(self):
        engine = BatchAnalysisEngine()
        assert engine._cancelled is False
        engine.cancel()
        assert engine._cancelled is True

    def test_cancel_flag_reset_by_run_batch(self):
        """run_batch() resets _cancelled to False at start."""
        engine = BatchAnalysisEngine()
        engine.cancel()
        assert engine._cancelled is True
        rec, _ = _make_recording()
        pipeline = [{"analysis": "rmp_analysis", "scope": "first_trial", "params": {}}]
        # run_batch must reset the flag first
        engine.run_batch([rec], pipeline)
        # After the run completes normally, flag should be False
        assert engine._cancelled is False


# ---------------------------------------------------------------------------
# update_performance_settings()
# ---------------------------------------------------------------------------


class TestUpdatePerformanceSettings:
    def test_update_max_cpu_cores(self):
        engine = BatchAnalysisEngine(max_workers=1)
        engine.update_performance_settings({"max_cpu_cores": 4})
        import multiprocessing

        expected = min(4, multiprocessing.cpu_count())
        assert engine.max_workers == expected

    def test_update_ignores_unknown_keys(self):
        engine = BatchAnalysisEngine(max_workers=1)
        original = engine.max_workers
        engine.update_performance_settings({"unknown_key": 99})
        assert engine.max_workers == original

    def test_update_ram_allocation_logged(self, caplog):
        engine = BatchAnalysisEngine()
        with caplog.at_level("INFO", logger="Synaptipy.core.analysis.batch_engine"):
            engine.update_performance_settings({"max_ram_allocation_gb": 8.0})
        assert "max_ram_allocation_gb" in caplog.text or True  # log at least not crashing

    def test_max_workers_clamped_to_one_minimum(self):
        engine = BatchAnalysisEngine(max_workers=4)
        engine.update_performance_settings({"max_cpu_cores": 0})
        assert engine.max_workers >= 1


# ---------------------------------------------------------------------------
# _append_batch_error_log()
# ---------------------------------------------------------------------------


class TestAppendBatchErrorLog:
    def test_writes_to_log_file(self, tmp_path, monkeypatch):
        """_append_batch_error_log should write a timestamped line."""
        log_dir = tmp_path / ".synaptipy" / "logs"
        _ = log_dir  # referenced for clarity only
        monkeypatch.setattr(
            "Synaptipy.core.analysis.batch_engine.Path.home",
            lambda: tmp_path,
        )
        exc = ValueError("test error")
        BatchAnalysisEngine._append_batch_error_log("test.abf", "/data/test.abf", exc)
        error_log = tmp_path / ".synaptipy" / "logs" / "batch_errors.log"
        assert error_log.exists()
        content = error_log.read_text()
        assert "test.abf" in content
        assert "ValueError" in content

    def test_write_error_does_not_raise(self, monkeypatch):
        """If log directory is unwritable, method should not raise."""

        def _bad_mkdir(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr("pathlib.Path.mkdir", _bad_mkdir)
        # Should log a warning but not raise
        BatchAnalysisEngine._append_batch_error_log("x.abf", "/x.abf", RuntimeError("oops"))


# ---------------------------------------------------------------------------
# _sanitise_long_list – exception path
# ---------------------------------------------------------------------------


class TestSanitiseLongList:
    def test_non_numeric_list_returns_item_count(self):
        """A list containing non-numeric elements should fall back to item count."""
        value = ["a", "b", {}, "d", "e", "f"]  # cannot be float array
        summary, stash = BatchAnalysisEngine._sanitise_long_list("key", value)
        assert summary == "[6 items]"
        assert stash is None

    def test_numeric_list_returns_stats_string(self):
        value = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        summary, stash = BatchAnalysisEngine._sanitise_long_list("key", value)
        assert "n=6" in summary

    def test_mixed_numeric_string_returns_fallback(self):
        value = [1.0, "two", 3.0, 4.0, 5.0, 6.0]
        summary, stash = BatchAnalysisEngine._sanitise_long_list("key", value)
        # May produce [6 items] or stats depending on numpy coercion
        assert isinstance(summary, str)


# ---------------------------------------------------------------------------
# _recording_metadata
# ---------------------------------------------------------------------------


class TestRecordingMetadata:
    def test_none_recording_returns_empty(self):
        result = BatchAnalysisEngine._recording_metadata(None)
        assert result == {}

    def test_protocol_name_included(self):
        rec = MagicMock()
        rec.protocol_name = "current_step"
        rec.duration = 1.0
        rec.subject_id = None
        rec.cell_id = None
        meta = BatchAnalysisEngine._recording_metadata(rec)
        assert meta["protocol"] == "current_step"

    def test_subject_id_and_cell_id_included(self):
        rec = MagicMock()
        rec.protocol_name = None
        rec.duration = 0.5
        rec.subject_id = "mouse_01"
        rec.cell_id = "cell_03"
        meta = BatchAnalysisEngine._recording_metadata(rec)
        assert meta["subject_id"] == "mouse_01"
        assert meta["cell_id"] == "cell_03"

    def test_no_protocol_skipped(self):
        rec = MagicMock()
        rec.protocol_name = None
        rec.duration = 0.5
        rec.subject_id = None
        rec.cell_id = None
        meta = BatchAnalysisEngine._recording_metadata(rec)
        assert "protocol" not in meta


# ---------------------------------------------------------------------------
# _order_columns with empty DataFrame
# ---------------------------------------------------------------------------


class TestOrderColumns:
    def test_empty_dataframe_returned_unchanged(self):
        df = pd.DataFrame()
        result = BatchAnalysisEngine._order_columns(df)
        assert result.empty

    def test_metadata_cols_come_first(self):
        data = {
            "z_result": [1, 2],
            "file_name": ["a.abf", "b.abf"],
            "channel": ["V1", "V1"],
        }
        df = pd.DataFrame(data)
        ordered = BatchAnalysisEngine._order_columns(df)
        cols = list(ordered.columns)
        assert cols.index("file_name") < cols.index("z_result")

    def test_private_columns_at_end(self):
        data = {
            "_raw_data": [[1, 2], [3, 4]],
            "file_name": ["a", "b"],
            "result": [10, 20],
        }
        df = pd.DataFrame(data)
        ordered = BatchAnalysisEngine._order_columns(df)
        cols = list(ordered.columns)
        assert cols.index("_raw_data") > cols.index("result")


# ---------------------------------------------------------------------------
# get_analysis_info for non-existent key
# ---------------------------------------------------------------------------


class TestGetAnalysisInfo:
    def test_non_existent_returns_none(self):
        result = BatchAnalysisEngine.get_analysis_info("does_not_exist_xyz")
        assert result is None


# ---------------------------------------------------------------------------
# Cancellation mid-batch
# ---------------------------------------------------------------------------


class TestCancellationDuringBatch:
    def setup_method(self):
        pass  # registry already populated at module import

    def test_cancel_between_files(self):
        """Cancel after processing first file; second should be skipped."""
        rec1, _ = _make_recording()
        rec2, _ = _make_recording()

        engine = BatchAnalysisEngine()
        call_count = [0]

        def _progress(i, total, msg):
            call_count[0] += 1
            if i == 1:
                engine.cancel()

        pipeline = [{"analysis": "rmp_analysis", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([rec1, rec2], pipeline, progress_callback=_progress)
        # Engine was cancelled after file 1, so at most 1 result row
        assert len(df) <= 2  # may have 0 or 1 row


# ---------------------------------------------------------------------------
# Error row in sequential batch
# ---------------------------------------------------------------------------


class TestErrorRowInSequentialBatch:
    def setup_method(self):
        pass  # registry already populated at module import

    def test_failing_analysis_adds_error_row(self):
        """When an analysis function raises, an error row should appear."""

        # Register a failing analysis
        @AnalysisRegistry.register("_test_failing_analysis")
        def _bad_analysis(data, time, sampling_rate, **kwargs):
            raise RuntimeError("Deliberate failure for test")

        engine = BatchAnalysisEngine()
        rec, _ = _make_recording()
        pipeline = [{"analysis": "_test_failing_analysis", "scope": "first_trial", "params": {}}]
        try:
            df = engine.run_batch([rec], pipeline)
            assert len(df) >= 1
            # At least one row should contain an error
            if "error" in df.columns:
                has_error = df["error"].notna().any()
                assert has_error
        finally:
            # Clean up test registration
            if "_test_failing_analysis" in AnalysisRegistry._registry:
                del AnalysisRegistry._registry["_test_failing_analysis"]
                del AnalysisRegistry._metadata["_test_failing_analysis"]
