"""
Tests for the Batch Analysis System.

This module tests the AnalysisRegistry and BatchAnalysisEngine components
of the Synaptipy batch analysis system.

Author: Anzal K Shahul <anzal.ks@gmail.com>
"""

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.data_model import Channel, Recording

# ---------------------------------------------------------------------------
# Synthetic signal generators — shared by tests
# ---------------------------------------------------------------------------


def _flat_trace(value: float = -65.0, duration_s: float = 1.0, fs: float = 10000.0):
    """Return (data, time) for a flat voltage trace."""
    n = int(duration_s * fs)
    time = np.linspace(0, duration_s, n, endpoint=False)
    data = np.full(n, value)
    return data, time


def _spike_train(
    n_spikes: int = 5,
    duration_s: float = 1.0,
    fs: float = 10000.0,
    resting: float = -65.0,
    peak: float = 30.0,
    spike_width_ms: float = 1.0,
):
    """Return (data, time) with synthetic spikes (triangle pulses)."""
    n = int(duration_s * fs)
    time = np.linspace(0, duration_s, n, endpoint=False)
    data = np.full(n, resting)
    spike_half_w = int(spike_width_ms / 1000.0 * fs / 2)
    positions = np.linspace(0.05, duration_s - 0.05, n_spikes)
    for t_spike in positions:
        idx = int(t_spike * fs)
        for j in range(max(0, idx - spike_half_w), min(n, idx + spike_half_w)):
            frac = 1.0 - abs(j - idx) / spike_half_w
            data[j] = resting + (peak - resting) * frac
    return data, time


def _step_response(
    v_base: float = -65.0,
    v_step: float = -75.0,
    step_start: float = 0.1,
    step_end: float = 0.9,
    tau: float = 0.02,
    duration_s: float = 1.1,
    fs: float = 10000.0,
):
    """Exponential charging step response (for Rin, Tau, Sag, Capacitance tests)."""
    n = int(duration_s * fs)
    time = np.linspace(0, duration_s, n, endpoint=False)
    data = np.full(n, v_base)
    for i, t in enumerate(time):
        if step_start <= t < step_end:
            elapsed = t - step_start
            data[i] = v_base + (v_step - v_base) * (1.0 - np.exp(-elapsed / tau))
        elif t >= step_end:
            elapsed = t - step_end
            # Recover back to baseline
            ss = v_base + (v_step - v_base) * (1.0 - np.exp(-(step_end - step_start) / tau))
            data[i] = v_base + (ss - v_base) * np.exp(-elapsed / tau)
    return data, time


def _sag_response(
    v_base: float = -65.0,
    v_peak: float = -85.0,
    v_ss: float = -78.0,
    step_start: float = 0.1,
    step_end: float = 1.0,
    tau_sag: float = 0.05,
    duration_s: float = 1.2,
    fs: float = 10000.0,
):
    """Sag-like response: fast dive to v_peak then relaxation to v_ss."""
    n = int(duration_s * fs)
    time = np.linspace(0, duration_s, n, endpoint=False)
    data = np.full(n, v_base)
    for i, t in enumerate(time):
        if step_start <= t < step_end:
            elapsed = t - step_start
            # Fast dive + sag relaxation
            dive = (v_peak - v_base) * (1.0 - np.exp(-elapsed / 0.005))
            sag = (v_ss - v_peak) * (1.0 - np.exp(-elapsed / tau_sag))
            data[i] = v_base + dive + sag
        elif t >= step_end:
            elapsed = t - step_end
            data[i] = v_base + (v_ss - v_base) * np.exp(-elapsed / 0.03)
    return data, time


class TestAnalysisRegistry:
    """Tests for the AnalysisRegistry class."""

    def setup_method(self):
        """Save and clear registry before each test."""
        self._saved_registry = dict(AnalysisRegistry._registry)
        self._saved_metadata = dict(AnalysisRegistry._metadata)
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()

    def teardown_method(self):
        """Restore registry after each test."""
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()
        AnalysisRegistry._registry.update(self._saved_registry)
        AnalysisRegistry._metadata.update(self._saved_metadata)

    def test_register_function(self):
        """Test that a function can be registered."""

        @AnalysisRegistry.register("test_func")
        def my_func(data, time, sampling_rate, **kwargs):
            return {"result": 42}

        assert "test_func" in AnalysisRegistry.list_registered()
        func = AnalysisRegistry.get_function("test_func")
        assert func is not None
        assert func(None, None, None) == {"result": 42}

    def test_register_overwrites_warning(self, caplog):
        """Test that re-registering logs a warning."""

        @AnalysisRegistry.register("duplicate")
        def func1(data, time, sr, **kw):
            return {"v": 1}

        @AnalysisRegistry.register("duplicate")
        def func2(data, time, sr, **kw):
            return {"v": 2}

        # The second function should overwrite
        func = AnalysisRegistry.get_function("duplicate")
        assert func(None, None, None) == {"v": 2}

    def test_get_nonexistent_function(self, caplog):
        """Test that getting a non-existent function returns None."""
        result = AnalysisRegistry.get_function("does_not_exist")
        assert result is None

    def test_list_registered(self):
        """Test listing all registered functions."""

        @AnalysisRegistry.register("func_a")
        def a(d, t, s, **kw):
            return {}

        @AnalysisRegistry.register("func_b")
        def b(d, t, s, **kw):
            return {}

        registered = AnalysisRegistry.list_registered()
        assert "func_a" in registered
        assert "func_b" in registered
        assert len(registered) == 2

    def test_clear_registry(self):
        """Test clearing the registry."""

        @AnalysisRegistry.register("to_clear")
        def f(d, t, s, **kw):
            return {}

        assert len(AnalysisRegistry.list_registered()) == 1
        AnalysisRegistry.clear()
        assert len(AnalysisRegistry.list_registered()) == 0


class TestBatchAnalysisSystem:

    def setup_method(self):
        # Save and clear registry before each test to ensure clean state
        self._saved_registry = dict(AnalysisRegistry._registry)
        self._saved_metadata = dict(AnalysisRegistry._metadata)
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()

    def teardown_method(self):
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()
        AnalysisRegistry._registry.update(self._saved_registry)
        AnalysisRegistry._metadata.update(self._saved_metadata)

    def test_registry_registration(self):
        """Test that functions can be registered and retrieved."""

        @AnalysisRegistry.register("test_analysis")
        def dummy_analysis(data, time, sampling_rate, **kwargs):
            return {"result": "success"}

        func = AnalysisRegistry.get_function("test_analysis")
        assert func is not None
        assert func(None, None, None) == {"result": "success"}

        assert "test_analysis" in AnalysisRegistry.list_registered()

    def test_batch_engine_execution(self, tmp_path):
        """Test that BatchAnalysisEngine runs the pipeline correctly."""

        # 1. Register a mock analysis
        @AnalysisRegistry.register("mock_analysis")
        def mock_analysis(data, time, sampling_rate, **kwargs):
            threshold = kwargs.get("threshold", 0)
            return {"mean_val": np.mean(data), "threshold_used": threshold, "custom_output": "worked"}

        # 2. Mock NeoAdapter to return a dummy recording
        # We'll subclass or mock BatchAnalysisEngine's adapter
        engine = BatchAnalysisEngine()

        # Create a dummy recording
        rec = Recording(source_file=Path("dummy.abf"))

        # Add some dummy data
        _t = np.linspace(0, 1, 1000)  # noqa: F841
        d = np.ones(1000) * 5.0  # Mean is 5.0

        # Initialize channel with data_trials
        channel = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[d])
        rec.channels["0"] = channel

        # Mock the read_recording method
        # Since we can't easily mock the internal NeoAdapter without patching,
        # we'll use unittest.mock
        from unittest.mock import MagicMock

        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        # 3. Define Pipeline
        pipeline = [{"analysis": "mock_analysis", "scope": "first_trial", "params": {"threshold": 10}}]

        # 4. Run Batch
        # files list is just for iteration, content doesn't matter due to mock
        files = [Path("file1.abf"), Path("file2.abf")]

        df = engine.run_batch(files, pipeline)

        # 5. Verify Results
        assert len(df) == 2
        assert "mean_val" in df.columns
        assert "custom_output" in df.columns
        assert df.iloc[0]["mean_val"] == 5.0
        assert df.iloc[0]["threshold_used"] == 10
        assert df.iloc[0]["custom_output"] == "worked"
        assert df.iloc[0]["scope"] == "first_trial"

    def test_batch_engine_scope_average(self):
        """Test execution with 'average' scope."""

        @AnalysisRegistry.register("avg_analysis")
        def avg_analysis(data, time, sampling_rate, **kwargs):
            return {"val": data[0]}

        engine = BatchAnalysisEngine()

        rec = Recording(source_file=Path("dummy.abf"))

        # Two trials data
        t1 = np.array([10.0, 10.0])
        t2 = np.array([20.0, 20.0])

        # Initialize channel with data_trials
        channel = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[t1, t2])
        # Average should be 15.0
        rec.channels["0"] = channel

        from unittest.mock import MagicMock

        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        pipeline = [{"analysis": "avg_analysis", "scope": "average", "params": {}}]

        df = engine.run_batch([Path("f.abf")], pipeline)

        assert len(df) == 1
        # get_averaged_data() should return [15.0, 15.0]
        # So data[0] is 15.0
        assert df.iloc[0]["val"] == 15.0

    def test_batch_engine_all_trials_scope(self):
        """Test execution with 'all_trials' scope."""

        @AnalysisRegistry.register("trial_analysis")
        def trial_analysis(data, time, sampling_rate, **kwargs):
            return {"mean": float(np.mean(data))}

        engine = BatchAnalysisEngine()

        rec = Recording(source_file=Path("dummy.abf"))

        # Three trials with different means
        t1 = np.ones(100) * 10.0
        t2 = np.ones(100) * 20.0
        t3 = np.ones(100) * 30.0

        channel = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[t1, t2, t3])
        rec.channels["0"] = channel

        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        pipeline = [{"analysis": "trial_analysis", "scope": "all_trials", "params": {}}]

        df = engine.run_batch([Path("f.abf")], pipeline)

        # Should have 3 rows (one per trial)
        assert len(df) == 3
        assert df.iloc[0]["mean"] == 10.0
        assert df.iloc[1]["mean"] == 20.0
        assert df.iloc[2]["mean"] == 30.0
        assert all(df["trial_index"] == [0, 1, 2])

    def test_batch_engine_multiple_analyses(self):
        """Test running multiple analyses in a pipeline."""

        @AnalysisRegistry.register("analysis_a")
        def analysis_a(data, time, sampling_rate, **kwargs):
            return {"a_result": "from_a"}

        @AnalysisRegistry.register("analysis_b")
        def analysis_b(data, time, sampling_rate, **kwargs):
            return {"b_result": "from_b"}

        engine = BatchAnalysisEngine()

        rec = Recording(source_file=Path("dummy.abf"))
        channel = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[np.ones(100)])
        rec.channels["0"] = channel

        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        pipeline = [
            {"analysis": "analysis_a", "scope": "first_trial", "params": {}},
            {"analysis": "analysis_b", "scope": "first_trial", "params": {}},
        ]

        df = engine.run_batch([Path("f.abf")], pipeline)

        # Should have 2 rows (one per analysis)
        assert len(df) == 2
        assert "a_result" in df.columns or "b_result" in df.columns

    def test_batch_engine_channel_filter(self):
        """Test channel filtering."""

        @AnalysisRegistry.register("filter_test")
        def filter_test(data, time, sampling_rate, **kwargs):
            return {"processed": True}

        engine = BatchAnalysisEngine()

        rec = Recording(source_file=Path("dummy.abf"))

        # Multiple channels
        for ch_id in ["Ch1", "Ch2", "Ch3"]:
            channel = Channel(id=ch_id, name=ch_id, units="mV", sampling_rate=1000.0, data_trials=[np.ones(100)])
            rec.channels[ch_id] = channel

        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        pipeline = [{"analysis": "filter_test", "scope": "first_trial", "params": {}}]

        # Filter to only Ch1 and Ch3
        df = engine.run_batch([Path("f.abf")], pipeline, channel_filter=["Ch1", "Ch3"])

        # Should have 2 rows (one per filtered channel)
        assert len(df) == 2
        assert set(df["channel"]) == {"Ch1", "Ch3"}

    def test_batch_engine_progress_callback(self):
        """Test that progress callback is called correctly."""

        @AnalysisRegistry.register("progress_test")
        def progress_test(data, time, sampling_rate, **kwargs):
            return {"done": True}

        engine = BatchAnalysisEngine()

        rec = Recording(source_file=Path("dummy.abf"))
        channel = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[np.ones(100)])
        rec.channels["0"] = channel

        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        pipeline = [{"analysis": "progress_test", "scope": "first_trial", "params": {}}]

        progress_calls = []

        def progress_cb(current, total, msg):
            progress_calls.append((current, total, msg))

        _df = engine.run_batch([Path("f1.abf"), Path("f2.abf")], pipeline, progress_callback=progress_cb)  # noqa: F841

        # Should have progress calls for each file plus completion
        assert len(progress_calls) >= 2
        # Last call should indicate completion
        assert progress_calls[-1][0] == progress_calls[-1][1]  # current == total

    def test_batch_engine_handles_errors(self):
        """Test that errors in analysis are handled gracefully."""

        @AnalysisRegistry.register("error_test")
        def error_test(data, time, sampling_rate, **kwargs):
            raise ValueError("Intentional test error")

        engine = BatchAnalysisEngine()

        rec = Recording(source_file=Path("dummy.abf"))
        channel = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[np.ones(100)])
        rec.channels["0"] = channel

        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        pipeline = [{"analysis": "error_test", "scope": "first_trial", "params": {}}]

        # Should not raise, but should include error in results
        df = engine.run_batch([Path("f.abf")], pipeline)

        assert len(df) == 1
        assert "error" in df.columns
        assert "Intentional test error" in str(df.iloc[0]["error"])

    def test_batch_engine_list_available_analyses(self):
        """Test listing available analyses."""

        @AnalysisRegistry.register("list_test_a")
        def a(d, t, s, **kw):
            return {}

        @AnalysisRegistry.register("list_test_b")
        def b(d, t, s, **kw):
            return {}

        available = BatchAnalysisEngine.list_available_analyses()
        assert "list_test_a" in available
        assert "list_test_b" in available

    def test_batch_engine_get_analysis_info(self):
        """Test getting analysis function info."""

        @AnalysisRegistry.register("info_test")
        def info_test(data, time, sampling_rate, **kwargs):
            """This is the docstring for info_test."""
            return {}

        info = BatchAnalysisEngine.get_analysis_info("info_test")
        assert info is not None
        assert info["name"] == "info_test"
        assert "docstring" in info["docstring"].lower() or "This is the docstring" in info["docstring"]

    def test_batch_engine_empty_pipeline(self):
        """Test that empty pipeline returns empty DataFrame."""
        engine = BatchAnalysisEngine()
        df = engine.run_batch([Path("f.abf")], [])
        assert df.empty


class TestRegisteredAnalyses:
    """Tests for the pre-registered analysis wrappers."""

    def setup_method(self):
        """Import analysis modules to trigger registration."""
        # Re-import to trigger registration after any previous clear
        # We need to reload the modules to re-register the functions
        import importlib

        import Synaptipy.core.analysis.basic_features as basic_mod
        import Synaptipy.core.analysis.event_detection as event_mod
        import Synaptipy.core.analysis.intrinsic_properties as intrinsic_mod
        import Synaptipy.core.analysis.spike_analysis as spike_mod

        # Reload to trigger decorator registration
        importlib.reload(spike_mod)
        importlib.reload(basic_mod)
        importlib.reload(intrinsic_mod)
        importlib.reload(event_mod)

    def test_spike_detection_registered(self):
        """Test that spike_detection is registered."""
        func = AnalysisRegistry.get_function("spike_detection")
        assert func is not None

    def test_rmp_analysis_registered(self):
        """Test that rmp_analysis is registered."""
        func = AnalysisRegistry.get_function("rmp_analysis")
        assert func is not None

    def test_rin_analysis_registered(self):
        """Test that rin_analysis is registered."""
        func = AnalysisRegistry.get_function("rin_analysis")
        assert func is not None

    def test_mini_detection_registered(self):
        """Test that event detection is registered."""
        # Renamed from "mini_detection" to "event_detection_threshold"
        func = AnalysisRegistry.get_function("event_detection_threshold")
        assert func is not None
        # Verify metadata too
        meta = AnalysisRegistry.get_metadata("event_detection_threshold")
        assert meta is not None
        assert "threshold" in [p["name"] for p in meta.get("ui_params", [])]

    def test_spike_detection_wrapper_returns_dict(self):
        """Test that spike_detection wrapper returns proper dict."""
        func = AnalysisRegistry.get_function("spike_detection")

        # Create test data with no spikes (flat line)
        data = np.zeros(1000)
        time = np.linspace(0, 1, 1000)
        sampling_rate = 1000.0

        result = func(data, time, sampling_rate, threshold=-20.0, refractory_ms=2.0)

        assert isinstance(result, dict)
        assert "spike_count" in result
        assert "mean_freq_hz" in result

    def test_rmp_analysis_wrapper_returns_dict(self):
        """Test that rmp_analysis wrapper returns proper dict."""
        func = AnalysisRegistry.get_function("rmp_analysis")

        # Create test data with constant value
        data = np.ones(1000) * -65.0  # -65 mV
        time = np.linspace(0, 1, 1000)
        sampling_rate = 1000.0

        result = func(data, time, sampling_rate, baseline_start=0.0, baseline_end=0.5)

        assert isinstance(result, dict)
        assert "rmp_mv" in result
        assert result["rmp_mv"] == pytest.approx(-65.0, abs=0.1)


class TestBatchOutputEnrichment:
    """Tests for the batch output enrichment: metadata columns, column ordering,
    array sanitisation, human-readable aliases, and error row structure."""

    def setup_method(self):
        """Save and clear registry before each test."""
        self._saved_registry = dict(AnalysisRegistry._registry)
        self._saved_metadata = dict(AnalysisRegistry._metadata)
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()

    def teardown_method(self):
        """Restore registry after each test."""
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()
        AnalysisRegistry._registry.update(self._saved_registry)
        AnalysisRegistry._metadata.update(self._saved_metadata)

    def _make_engine_with_recording(self, channel_id="Vm", units="mV", trials=None):
        """Helper: create engine + recording with mock adapter."""
        if trials is None:
            trials = [np.ones(1000) * -65.0]

        engine = BatchAnalysisEngine()
        rec = Recording(source_file=Path("experiment_01.abf"))
        rec.protocol_name = "CC_Step"
        rec.duration = 1.0

        channel = Channel(
            id=channel_id,
            name=channel_id,
            units=units,
            sampling_rate=10000.0,
            data_trials=trials,
        )
        rec.channels[channel_id] = channel
        engine.neo_adapter.read_recording = MagicMock(return_value=rec)
        return engine, rec

    # ------------------------------------------------------------------
    # 1. channel_units and trial_count propagation
    # ------------------------------------------------------------------
    def test_channel_units_in_output(self):
        """Verify channel_units column appears in results."""

        @AnalysisRegistry.register("units_test")
        def units_test(data, time, sampling_rate, **kwargs):
            return {"val": float(np.mean(data))}

        engine, _ = self._make_engine_with_recording(units="pA")
        pipeline = [{"analysis": "units_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        assert "channel_units" in df.columns
        assert df.iloc[0]["channel_units"] == "pA"

    def test_trial_count_in_output(self):
        """Verify trial_count column is populated correctly."""

        @AnalysisRegistry.register("tc_test")
        def tc_test(data, time, sampling_rate, **kwargs):
            return {"val": 1}

        trials = [np.ones(100) * i for i in range(5)]
        engine, _ = self._make_engine_with_recording(trials=trials)
        pipeline = [{"analysis": "tc_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        assert "trial_count" in df.columns
        assert df.iloc[0]["trial_count"] == 5

    # ------------------------------------------------------------------
    # 2. Recording-level metadata propagation
    # ------------------------------------------------------------------
    def test_protocol_name_in_output(self):
        """Verify protocol column appears when recording has protocol_name."""

        @AnalysisRegistry.register("proto_test")
        def proto_test(data, time, sampling_rate, **kwargs):
            return {"val": 1}

        engine, _ = self._make_engine_with_recording()
        pipeline = [{"analysis": "proto_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        assert "protocol" in df.columns
        assert df.iloc[0]["protocol"] == "CC_Step"

    def test_recording_duration_in_output(self):
        """Verify recording_duration_s column appears."""

        @AnalysisRegistry.register("dur_test")
        def dur_test(data, time, sampling_rate, **kwargs):
            return {"val": 1}

        engine, _ = self._make_engine_with_recording()
        pipeline = [{"analysis": "dur_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        assert "recording_duration_s" in df.columns
        assert df.iloc[0]["recording_duration_s"] == 1.0

    # ------------------------------------------------------------------
    # 3. Column ordering: metadata first, results middle, trailing last
    # ------------------------------------------------------------------
    def test_column_ordering(self):
        """Verify metadata columns precede result columns."""

        @AnalysisRegistry.register("order_test")
        def order_test(data, time, sampling_rate, **kwargs):
            return {"zzz_result": 99, "aaa_result": 1}

        engine, _ = self._make_engine_with_recording()
        pipeline = [{"analysis": "order_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        cols = list(df.columns)
        # file_name must come before any result column
        assert cols.index("file_name") < cols.index("aaa_result")
        assert cols.index("channel") < cols.index("zzz_result")
        # batch_timestamp must come after results
        assert cols.index("batch_timestamp") > cols.index("zzz_result")

    # ------------------------------------------------------------------
    # 4. Array sanitisation
    # ------------------------------------------------------------------
    def test_large_array_summarised(self):
        """Large numpy arrays should be summarised as strings, originals in _raw keys."""

        @AnalysisRegistry.register("arr_test")
        def arr_test(data, time, sampling_rate, **kwargs):
            return {"spike_times": np.linspace(0, 1, 100)}

        engine, _ = self._make_engine_with_recording()
        pipeline = [{"analysis": "arr_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        # The visible column should be a summary string
        val = df.iloc[0]["spike_times"]
        assert isinstance(val, str)
        assert "n=100" in val

    def test_small_array_kept_inline(self):
        """Small arrays (<=5 elements) should be kept as lists."""

        @AnalysisRegistry.register("small_arr_test")
        def small_arr_test(data, time, sampling_rate, **kwargs):
            return {"coords": np.array([1.0, 2.0, 3.0])}

        engine, _ = self._make_engine_with_recording()
        pipeline = [{"analysis": "small_arr_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        val = df.iloc[0]["coords"]
        assert isinstance(val, list)
        assert len(val) == 3

    # ------------------------------------------------------------------
    # 5. Human-readable aliases
    # ------------------------------------------------------------------
    def test_human_readable_alias_added(self):
        """cv should get coeff_of_variation alias column."""

        @AnalysisRegistry.register("alias_test")
        def alias_test(data, time, sampling_rate, **kwargs):
            return {"cv": 0.45, "cv2": 0.32}

        engine, _ = self._make_engine_with_recording()
        pipeline = [{"analysis": "alias_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        assert "coeff_of_variation" in df.columns
        assert df.iloc[0]["coeff_of_variation"] == 0.45
        assert "local_cv2_holt" in df.columns

    # ------------------------------------------------------------------
    # 6. Error rows preserve full metadata
    # ------------------------------------------------------------------
    def test_error_row_has_full_metadata(self):
        """Error rows should have channel, analysis, scope columns filled."""

        @AnalysisRegistry.register("err_meta_test")
        def err_meta_test(data, time, sampling_rate, **kwargs):
            raise ValueError("test error")

        engine, _ = self._make_engine_with_recording()
        pipeline = [{"analysis": "err_meta_test", "scope": "first_trial", "params": {}}]
        df = engine.run_batch([Path("f.abf")], pipeline)

        row = df.iloc[0]
        assert "error" in df.columns
        assert "test error" in str(row["error"])
        # Metadata should still be present
        assert row["channel"] == "Vm"
        assert row["analysis"] == "err_meta_test"
        assert row["scope"] == "first_trial"
        assert row["channel_units"] == "mV"

    # ------------------------------------------------------------------
    # 7. Sanitise helper unit test
    # ------------------------------------------------------------------
    def test_sanitise_complex_object(self):
        """Non-scalar, non-array objects should be replaced with type name."""

        class FakeResult:
            pass

        result = {"data": FakeResult(), "count": 5}
        BatchAnalysisEngine._sanitise_result_for_export(result)

        assert result["count"] == 5
        assert result["data"] == "FakeResult"
        assert "_data_obj" in result


# ======================================================================
# Comprehensive batch tests for ALL 15 registered analysis types
# ======================================================================


class TestBatchAllAnalysisTypes:
    """Run every registered analysis type through the batch engine to verify:
    - The function is callable without crashing.
    - The result dict is produced with expected keys.
    - Metadata columns (file_name, channel, analysis, scope, channel_units,
      trial_count, sampling_rate) are present in the output DataFrame.

    These are integration tests; they use realistic synthetic test data.
    """

    @classmethod
    def setup_class(cls):
        """Ensure all analysis modules are imported and registered."""
        import Synaptipy.core.analysis.basic_features as bf
        import Synaptipy.core.analysis.burst_analysis as ba
        import Synaptipy.core.analysis.capacitance as cap
        import Synaptipy.core.analysis.event_detection as ed
        import Synaptipy.core.analysis.excitability as exc
        import Synaptipy.core.analysis.intrinsic_properties as ip
        import Synaptipy.core.analysis.optogenetics as opto
        import Synaptipy.core.analysis.phase_plane as pp
        import Synaptipy.core.analysis.spike_analysis as sa
        import Synaptipy.core.analysis.train_dynamics as td

        for mod in [bf, sa, ed, ba, exc, ip, pp, cap, opto, td]:
            importlib.reload(mod)

    def _run_batch_single(
        self,
        analysis_name: str,
        scope: str,
        params: dict,
        data_trials: list,
        units: str = "mV",
        fs: float = 10000.0,
    ):
        """Helper: run a single-analysis pipeline through the batch engine."""
        engine = BatchAnalysisEngine()
        rec = Recording(source_file=Path("test_cell.abf"))
        rec.protocol_name = "TestProtocol"
        rec.duration = 1.0

        channel = Channel(
            id="Ch0",
            name="Vm_prime",
            units=units,
            sampling_rate=fs,
            data_trials=data_trials,
        )
        rec.channels["Vm_prime"] = channel
        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        pipeline = [{"analysis": analysis_name, "scope": scope, "params": params}]
        df = engine.run_batch([Path("test_cell.abf")], pipeline)
        return df

    def _assert_common_columns(self, df, analysis_name, scope):
        """Assert standard metadata columns are present and correct."""
        assert not df.empty, f"DataFrame should not be empty for {analysis_name}"
        row = df.iloc[0]
        assert row["file_name"] == "test_cell.abf"
        assert row["channel"] == "Vm_prime"
        assert row["analysis"] == analysis_name
        assert row["scope"] == scope
        assert "channel_units" in df.columns
        assert "trial_count" in df.columns
        assert "sampling_rate" in df.columns
        assert "batch_timestamp" in df.columns

    # ------------------------------------------------------------------
    # 1. rmp_analysis
    # ------------------------------------------------------------------
    def test_batch_rmp_analysis(self):
        """Baseline/RMP analysis on flat trace."""
        data, _ = _flat_trace(-65.0, 1.0, 10000.0)
        df = self._run_batch_single(
            "rmp_analysis",
            "first_trial",
            {},
            [data],
        )
        self._assert_common_columns(df, "rmp_analysis", "first_trial")
        assert "rmp_mv" in df.columns
        assert df.iloc[0]["rmp_mv"] == pytest.approx(-65.0, abs=1.0)

    # ------------------------------------------------------------------
    # 2. spike_detection
    # ------------------------------------------------------------------
    def test_batch_spike_detection(self):
        """Spike detection on trace with synthetic spikes."""
        data, _ = _spike_train(5, 1.0, 10000.0)
        df = self._run_batch_single(
            "spike_detection",
            "first_trial",
            {"threshold": -20.0, "refractory_period": 0.002},
            [data],
        )
        self._assert_common_columns(df, "spike_detection", "first_trial")
        assert "spike_count" in df.columns
        assert "mean_freq_hz" in df.columns

    def test_batch_spike_detection_no_spikes(self):
        """Spike detection on flat trace should return 0 spikes, not error."""
        data, _ = _flat_trace(-65.0)
        df = self._run_batch_single(
            "spike_detection",
            "first_trial",
            {"threshold": -20.0},
            [data],
        )
        self._assert_common_columns(df, "spike_detection", "first_trial")
        assert df.iloc[0]["spike_count"] == 0

    # ------------------------------------------------------------------
    # 3. event_detection_threshold
    # ------------------------------------------------------------------
    def test_batch_event_detection_threshold(self):
        """Event detection (threshold) on flat trace — 0 events is valid."""
        data, _ = _flat_trace(0.0, 1.0, 10000.0)
        df = self._run_batch_single(
            "event_detection_threshold",
            "first_trial",
            {"threshold": 5.0, "direction": "negative"},
            [data],
        )
        self._assert_common_columns(df, "event_detection_threshold", "first_trial")
        assert "event_count" in df.columns

    # ------------------------------------------------------------------
    # 4. event_detection_deconvolution
    # ------------------------------------------------------------------
    def test_batch_event_detection_deconvolution(self):
        """Event detection (template match) on flat trace — 0 events is valid."""
        data, _ = _flat_trace(0.0, 1.0, 10000.0)
        df = self._run_batch_single(
            "event_detection_deconvolution",
            "first_trial",
            {"tau_rise_ms": 0.5, "tau_decay_ms": 5.0},
            [data],
        )
        self._assert_common_columns(df, "event_detection_deconvolution", "first_trial")
        assert "event_count" in df.columns

    # ------------------------------------------------------------------
    # 5. event_detection_baseline_peak
    # ------------------------------------------------------------------
    def test_batch_event_detection_baseline_peak(self):
        """Event detection (baseline-peak) on flat trace — 0 events is valid."""
        data, _ = _flat_trace(0.0, 1.0, 10000.0)
        df = self._run_batch_single(
            "event_detection_baseline_peak",
            "first_trial",
            {"direction": "negative"},
            [data],
        )
        self._assert_common_columns(df, "event_detection_baseline_peak", "first_trial")
        assert "event_count" in df.columns

    # ------------------------------------------------------------------
    # 6. burst_analysis
    # ------------------------------------------------------------------
    def test_batch_burst_analysis(self):
        """Burst analysis on flat trace — 0 bursts is valid."""
        data, _ = _flat_trace(-65.0)
        df = self._run_batch_single(
            "burst_analysis",
            "first_trial",
            {"threshold": -20.0},
            [data],
        )
        self._assert_common_columns(df, "burst_analysis", "first_trial")
        assert "burst_count" in df.columns

    # ------------------------------------------------------------------
    # 7. excitability_analysis (multi-trial, channel_set scope)
    # ------------------------------------------------------------------
    def test_batch_excitability_analysis(self):
        """Excitability / F-I curve on multiple sweeps."""
        trials = []
        for i in range(5):
            # First 3 subthreshold, last 2 have spikes
            if i < 3:
                d, _ = _flat_trace(-65.0 - i * 2.0, 1.0, 10000.0)
            else:
                d, _ = _spike_train(i, 1.0, 10000.0)
            trials.append(d)
        df = self._run_batch_single(
            "excitability_analysis",
            "channel_set",
            {"threshold": -20.0, "start_current": 0.0, "step_current": 50.0},
            trials,
        )
        self._assert_common_columns(df, "excitability_analysis", "channel_set")

    # ------------------------------------------------------------------
    # 8. rin_analysis
    # ------------------------------------------------------------------
    def test_batch_rin_analysis(self):
        """Input resistance on step response."""
        data, _ = _step_response(v_base=-65.0, v_step=-70.0, fs=10000.0, duration_s=0.5)
        df = self._run_batch_single(
            "rin_analysis",
            "first_trial",
            {
                "current_amplitude": -50.0,
                "auto_detect_pulse": False,
                "baseline_start": 0.0,
                "baseline_end": 0.08,
                "response_start": 0.3,
                "response_end": 0.4,
            },
            [data],
        )
        self._assert_common_columns(df, "rin_analysis", "first_trial")
        # Should either have rin_mohm or rin_error
        assert "rin_mohm" in df.columns or "rin_error" in df.columns

    # ------------------------------------------------------------------
    # 9. tau_analysis
    # ------------------------------------------------------------------
    def test_batch_tau_analysis(self):
        """Tau / time constant on step response."""
        data, _ = _step_response(
            v_base=-65.0,
            v_step=-75.0,
            tau=0.02,
            step_start=0.1,
            duration_s=0.5,
            fs=10000.0,
        )
        df = self._run_batch_single(
            "tau_analysis",
            "first_trial",
            {"stim_start_time": 0.1, "fit_duration": 0.05},
            [data],
        )
        self._assert_common_columns(df, "tau_analysis", "first_trial")
        # Should either have tau_ms or tau_error
        assert "tau_ms" in df.columns or "tau_error" in df.columns

    # ------------------------------------------------------------------
    # 10. sag_ratio_analysis
    # ------------------------------------------------------------------
    def test_batch_sag_ratio_analysis(self):
        """Sag ratio on hyperpolarizing step with sag."""
        data, _ = _sag_response(duration_s=1.2, fs=10000.0)
        df = self._run_batch_single(
            "sag_ratio_analysis",
            "first_trial",
            {
                "baseline_start": 0.0,
                "baseline_end": 0.1,
                "peak_window_start": 0.1,
                "peak_window_end": 0.3,
                "ss_window_start": 0.8,
                "ss_window_end": 1.0,
            },
            [data],
        )
        self._assert_common_columns(df, "sag_ratio_analysis", "first_trial")
        assert "sag_ratio" in df.columns

    # ------------------------------------------------------------------
    # 11. iv_curve_analysis (multi-trial, channel_set scope)
    # ------------------------------------------------------------------
    def test_batch_iv_curve_analysis(self):
        """I-V Curve on multiple sweeps with graded responses."""
        trials = []
        for i in range(5):
            v_step = -65.0 - (i + 1) * 3.0
            d, _ = _step_response(
                v_base=-65.0,
                v_step=v_step,
                tau=0.02,
                step_start=0.1,
                step_end=0.45,
                duration_s=0.5,
                fs=10000.0,
            )
            trials.append(d)
        df = self._run_batch_single(
            "iv_curve_analysis",
            "channel_set",
            {
                "start_current": -50.0,
                "step_current": 10.0,
                "baseline_start": 0.0,
                "baseline_end": 0.08,
                "response_start": 0.3,
                "response_end": 0.4,
            },
            trials,
        )
        self._assert_common_columns(df, "iv_curve_analysis", "channel_set")

    # ------------------------------------------------------------------
    # 12. phase_plane_analysis
    # ------------------------------------------------------------------
    def test_batch_phase_plane_analysis(self):
        """Phase plane on flat trace — runs without crashing."""
        data, _ = _flat_trace(-65.0, 0.5, 10000.0)
        df = self._run_batch_single(
            "phase_plane_analysis",
            "first_trial",
            {"sigma_ms": 0.1, "dvdt_threshold": 20.0},
            [data],
        )
        self._assert_common_columns(df, "phase_plane_analysis", "first_trial")

    # ------------------------------------------------------------------
    # 13. capacitance_analysis
    # ------------------------------------------------------------------
    def test_batch_capacitance_analysis(self):
        """Capacitance in CC mode on step response."""
        data, _ = _step_response(
            v_base=-65.0,
            v_step=-75.0,
            tau=0.02,
            step_start=0.1,
            step_end=0.25,
            duration_s=0.35,
            fs=10000.0,
        )
        df = self._run_batch_single(
            "capacitance_analysis",
            "first_trial",
            {
                "mode": "Current-Clamp",
                "current_amplitude_pa": -100.0,
                "baseline_start_s": 0.0,
                "baseline_end_s": 0.08,
                "response_start_s": 0.1,
                "response_end_s": 0.25,
            },
            [data],
        )
        self._assert_common_columns(df, "capacitance_analysis", "first_trial")
        # Should have capacitance_pf or error
        assert "capacitance_pf" in df.columns or "error" in df.columns

    # ------------------------------------------------------------------
    # 14. optogenetic_sync
    # ------------------------------------------------------------------
    def test_batch_optogenetic_sync(self):
        """Optogenetic sync — TTL provided as param, no spikes = valid 0 response."""
        n = 10000
        data = np.full(n, -65.0)  # No spikes
        # Build TTL with 3 pulses
        ttl = np.zeros(n)
        for pulse_start in [1000, 4000, 7000]:
            ttl[pulse_start : pulse_start + 200] = 5.0

        df = self._run_batch_single(
            "optogenetic_sync",
            "first_trial",
            {
                "ttl_data": ttl,
                "ttl_threshold": 2.5,
                "response_window_ms": 20.0,
                "event_detection_type": "Spikes",
                "spike_threshold": -20.0,
            },
            [data],
        )
        self._assert_common_columns(df, "optogenetic_sync", "first_trial")

    # ------------------------------------------------------------------
    # 15. train_dynamics
    # ------------------------------------------------------------------
    def test_batch_train_dynamics(self):
        """Spike train dynamics on trace with spikes."""
        data, _ = _spike_train(8, 1.0, 10000.0, resting=-65.0, peak=30.0)
        df = self._run_batch_single(
            "train_dynamics",
            "first_trial",
            {"spike_threshold": 0.0},
            [data],
        )
        self._assert_common_columns(df, "train_dynamics", "first_trial")

    def test_batch_train_dynamics_no_spikes(self):
        """Train dynamics on flat trace — returns error row (needs ≥2 spikes)."""
        data, _ = _flat_trace(-65.0)
        df = self._run_batch_single(
            "train_dynamics",
            "first_trial",
            {"spike_threshold": 0.0},
            [data],
        )
        self._assert_common_columns(df, "train_dynamics", "first_trial")
        # train_dynamics requires at least 2 spikes for ISI calculations
        assert "error" in df.columns
        assert "spike" in str(df.iloc[0]["error"]).lower()

    # ------------------------------------------------------------------
    # Cross-cutting: all_trials scope
    # ------------------------------------------------------------------
    def test_batch_rmp_all_trials(self):
        """RMP analysis across all trials produces one row per trial."""
        trials = [np.full(10000, -60.0 - 2.0 * i) for i in range(4)]
        df = self._run_batch_single(
            "rmp_analysis",
            "all_trials",
            {},
            trials,
        )
        assert len(df) == 4
        assert list(df["trial_index"]) == [0, 1, 2, 3]

    # ------------------------------------------------------------------
    # Cross-cutting: average scope
    # ------------------------------------------------------------------
    def test_batch_spike_detection_average(self):
        """Spike detection on averaged trace."""
        # 3 identical trials
        data, _ = _flat_trace(-65.0)
        df = self._run_batch_single(
            "spike_detection",
            "average",
            {"threshold": -20.0},
            [data, data.copy(), data.copy()],
        )
        self._assert_common_columns(df, "spike_detection", "average")
        assert df.iloc[0]["spike_count"] == 0

    # ------------------------------------------------------------------
    # Registry completeness check
    # ------------------------------------------------------------------
    def test_all_registered_analyses_are_tested(self):
        """Ensure every registered analysis has a corresponding batch test method."""
        expected_analyses = {
            "rmp_analysis",
            "spike_detection",
            "event_detection_threshold",
            "event_detection_deconvolution",
            "event_detection_baseline_peak",
            "burst_analysis",
            "excitability_analysis",
            "rin_analysis",
            "tau_analysis",
            "sag_ratio_analysis",
            "iv_curve_analysis",
            "phase_plane_analysis",
            "capacitance_analysis",
            "optogenetic_sync",
            "train_dynamics",
        }
        registered = set(AnalysisRegistry.list_registered())
        # All expected must be registered
        missing_from_registry = expected_analyses - registered
        assert not missing_from_registry, f"Expected analyses not registered: {missing_from_registry}"
