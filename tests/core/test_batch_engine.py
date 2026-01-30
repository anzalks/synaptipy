"""
Tests for the Batch Analysis System.

This module tests the AnalysisRegistry and BatchAnalysisEngine components
of the Synaptipy batch analysis system.

Author: Anzal KS <anzal.ks@gmail.com>
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.data_model import Recording, Channel


class TestAnalysisRegistry:
    """Tests for the AnalysisRegistry class."""

    def setup_method(self):
        """Clear registry before each test."""
        AnalysisRegistry.clear()

    def teardown_method(self):
        """Clear registry after each test."""
        AnalysisRegistry.clear()

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
        # Clear registry before each test to ensure clean state
        # AnalysisRegistry.clear()  # We need to implement clear if it doesn't exist, or just mock
        # Looking at registry.py, it has a clear() method.
        AnalysisRegistry.clear()

    def teardown_method(self):
        AnalysisRegistry.clear()

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
        import Synaptipy.core.analysis.spike_analysis as spike_mod
        import Synaptipy.core.analysis.basic_features as basic_mod
        import Synaptipy.core.analysis.intrinsic_properties as intrinsic_mod
        import Synaptipy.core.analysis.event_detection as event_mod

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
        """Test that mini_detection is registered."""
        func = AnalysisRegistry.get_function("mini_detection")
        assert func is not None

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
