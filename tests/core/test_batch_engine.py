import pytest
import numpy as np
from pathlib import Path
from typing import Dict, Any
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.data_model import Recording, Channel

class TestBatchAnalysisSystem:

    def setup_method(self):
        # Clear registry before each test to ensure clean state
        # AnalysisRegistry.clear() # We need to implement clear if it doesn't exist, or just mock
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
            return {
                "mean_val": np.mean(data), 
                "threshold_used": threshold,
                "custom_output": "worked"
            }

        # 2. Mock NeoAdapter to return a dummy recording
        # We'll subclass or mock BatchAnalysisEngine's adapter
        engine = BatchAnalysisEngine()
        
        # Create a dummy recording
        rec = Recording(source_file=Path("dummy.abf"))
        
        # Add some dummy data
        t = np.linspace(0, 1, 1000)
        d = np.ones(1000) * 5.0 # Mean is 5.0
        
        # Initialize channel with data_trials
        channel = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[d])
        rec.channels["0"] = channel
        
        # Mock the read_recording method
        # Since we can't easily mock the internal NeoAdapter without patching,
        # we'll use unittest.mock
        from unittest.mock import MagicMock
        engine.neo_adapter.read_recording = MagicMock(return_value=rec)
        
        # 3. Define Pipeline
        pipeline = [
            {
                "analysis": "mock_analysis",
                "scope": "first_trial",
                "params": {"threshold": 10}
            }
        ]
        
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


