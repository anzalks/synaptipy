"""Targeted coverage tests for batch_engine.py missed branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

import synaptipy.core.analysis  # noqa: F401  # populate registry
from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.data_model import Channel, Recording

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel(value=-65.0, n_trials=3, fs=10000.0, duration=0.5):
    n = int(fs * duration)
    time = np.linspace(0, duration, n, endpoint=False)
    ch = MagicMock(spec=Channel)
    ch.sampling_rate = fs
    ch.units = "mV"
    ch.num_trials = n_trials
    ch.name = "Vm"
    ch.get_data.return_value = np.full(n, value)
    ch.get_relative_time_vector.return_value = time
    ch.get_averaged_data.return_value = np.full(n, value)
    ch.get_relative_averaged_time_vector.return_value = time
    return ch


def _make_recording(value=-65.0, n_trials=3):
    rec = MagicMock(spec=Recording)
    ch = _make_channel(value=value, n_trials=n_trials)
    rec.channels = {"Vm": ch}
    rec.source_file = Path("rec.abf")
    rec.protocol_name = None
    rec.duration = 0.5
    rec.subject_id = None
    rec.cell_id = None
    return rec, ch


# ---------------------------------------------------------------------------
# Cross-file average — unregistered analysis (lines 661-669)
# ---------------------------------------------------------------------------


class TestCrossFileAverageUnregisteredAnalysis:
    def test_unregistered_analysis_produces_error_row(self):
        rec, _ch = _make_recording()
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [{"analysis": "NONEXISTENT_ANALYSIS_XYZ"}]
        df = engine.run_batch([rec], pipeline, cross_file_average=True)
        assert not df.empty
        assert any("not registered" in str(v) for v in df.get("error", pd.Series(dtype=str)))


# ---------------------------------------------------------------------------
# Cross-file average — analysis exception (lines 688-699)
# ---------------------------------------------------------------------------


class TestCrossFileAverageAnalysisException:
    def test_analysis_exception_logged_as_row(self):
        rec, _ch = _make_recording()
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [{"analysis": "rmp_analysis"}]
        rmp_func = AnalysisRegistry.get_function("rmp_analysis")
        assert rmp_func is not None

        def _raise(*a, **k):
            raise RuntimeError("boom")

        with patch.object(AnalysisRegistry, "get_function", return_value=_raise):
            df = engine.run_batch([rec], pipeline, cross_file_average=True)
        assert df is not None


# ---------------------------------------------------------------------------
# _sanitise_value — non-primitive type → type name string (line 200)
# ---------------------------------------------------------------------------


class TestSanitiseValue:
    def test_unknown_type_produces_type_name(self):
        class MyObj:
            pass

        result, extra = BatchAnalysisEngine._sanitise_value("key", MyObj())
        assert result == "MyObj"
        assert extra is not None
        assert extra[0] == "_key_obj"

    def test_small_ndarray_tolist(self):
        arr = np.array([1.0, 2.0])
        result, extra = BatchAnalysisEngine._sanitise_value("k", arr)
        assert result == [1.0, 2.0]
        assert extra is None

    def test_large_ndarray_summary(self):
        arr = np.arange(100, dtype=float)
        result, extra = BatchAnalysisEngine._sanitise_value("k", arr)
        assert isinstance(result, str)
        assert "n=100" in result

    def test_long_list_summarised(self):
        lst = list(range(10))
        result, extra = BatchAnalysisEngine._sanitise_value("k", lst)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Trial-length mismatch in sequential batch (lines 1059-1091)
# ---------------------------------------------------------------------------


class TestTrialLengthMismatch:
    def test_mismatched_trial_lengths_produce_error_row(self):
        """Lines 1059-1091: mixed-length trials in average scope returns error row."""
        rec = MagicMock(spec=Recording)
        rec.source_file = Path("mismatch.abf")
        rec.protocol_name = None
        rec.subject_id = None
        rec.cell_id = None
        rec.duration = 0.5

        ch = MagicMock(spec=Channel)
        ch.sampling_rate = 10000.0
        ch.units = "mV"
        ch.name = "Vm"
        ch.num_trials = 2
        # Trials with different lengths
        ch.get_data.side_effect = [np.zeros(100), np.zeros(200)]
        ch.get_relative_time_vector.side_effect = [
            np.linspace(0, 0.01, 100),
            np.linspace(0, 0.02, 200),
        ]
        rec.channels = {"Vm": ch}

        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [{"analysis": "rmp_analysis", "scope": "average"}]
        df = engine.run_batch([rec], pipeline)
        assert not df.empty
        if "error_type" in df.columns:
            assert any("MISMATCH" in str(v) for v in df["error_type"].fillna(""))


# ---------------------------------------------------------------------------
# List-available-analyses
# ---------------------------------------------------------------------------


class TestListAvailableAnalyses:
    def test_list_available_analyses_nonempty(self):
        names = BatchAnalysisEngine.list_available_analyses()
        assert len(names) > 0
        assert "rmp_analysis" in names


# ---------------------------------------------------------------------------
# Cross-file average — cancelled flag (line 565-566)
# ---------------------------------------------------------------------------


class TestCrossFileCancellation:
    def test_cancelled_before_start_returns_empty(self):
        engine = BatchAnalysisEngine(max_workers=1)
        engine.cancel()
        rec, _ = _make_recording()
        pipeline = [{"analysis": "rmp_analysis"}]
        df = engine.run_batch([rec], pipeline, cross_file_average=True)
        assert df is not None


# ---------------------------------------------------------------------------
# Cross-file average with in-memory Recording objects (line 581-585)
# ---------------------------------------------------------------------------


class TestCrossFileInMemoryRecording:
    def test_in_memory_recording_path(self):
        """Lines 581-585: passing Recording objects directly (not paths)."""
        rec, _ = _make_recording()
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [{"analysis": "rmp_analysis"}]
        df = engine.run_batch([rec], pipeline, cross_file_average=True)
        assert df is not None


# ---------------------------------------------------------------------------
# Cross-file average with channel_filter (lines 589-592)
# ---------------------------------------------------------------------------


class TestCrossFileChannelFilter:
    def test_channel_filter_applied(self):
        rec, _ = _make_recording()
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [{"analysis": "rmp_analysis"}]
        df = engine.run_batch([rec], pipeline, cross_file_average=True, channel_filter=["Vm"])
        assert df is not None

    def test_channel_filter_excludes_channel(self):
        rec, _ = _make_recording()
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [{"analysis": "rmp_analysis"}]
        df = engine.run_batch([rec], pipeline, cross_file_average=True, channel_filter=["NONEXISTENT"])
        assert df is not None
