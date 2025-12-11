
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from pathlib import Path
import numpy as np

from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine

class TestBatchAnalysisEngine(unittest.TestCase):
    def setUp(self):
        self.mock_neo_adapter = MagicMock()
        self.engine = BatchAnalysisEngine(neo_adapter=self.mock_neo_adapter)
        
    def test_specific_trial_scope(self):
        # Mock Recording and Channel
        mock_recording = MagicMock()
        mock_channel = MagicMock()
        
        # Setup mock channel data
        mock_channel.num_trials = 3
        mock_channel.sampling_rate = 1000.0
        
        # Mock data for different trials
        def get_data(trial_idx):
            return np.array([trial_idx] * 100) # Data is just the trial index repeated
            
        def get_time(trial_idx):
            return np.arange(100) / 1000.0
            
        mock_channel.get_data.side_effect = get_data
        mock_channel.get_relative_time_vector.side_effect = get_time
        
        mock_recording.channels = {'Ch1': mock_channel}
        self.mock_neo_adapter.read_recording.return_value = mock_recording
        
        # Mock analysis function registration
        with patch('Synaptipy.core.analysis.registry.AnalysisRegistry.get_function') as mock_get_func:
            # Create a dummy analysis function
            def dummy_analysis(data, time, fs, **kwargs):
                return {'mean_val': np.mean(data)}
            
            mock_get_func.return_value = dummy_analysis
            
            # Configuration for specific trial 1 (second trial)
            pipeline_config = [{
                'analysis': 'dummy_analysis',
                'scope': 'specific_trial',
                'params': {'trial_index': 1, 'extra_param': 10}
            }]
            
            files = [Path("test_file.abf")]
            
            # Run batch
            df = self.engine.run_batch(files, pipeline_config)
            
            # Verify results
            self.assertFalse(df.empty)
            result = df.iloc[0]
            
            print("\nBatch Result:")
            print(result)
            
            self.assertEqual(result['scope'], 'specific_trial')
            self.assertEqual(result['trial_index'], 1)
            self.assertEqual(result['mean_val'], 1.0) # Data was [1, 1, ...]
            self.assertEqual(result['file_name'], 'test_file.abf')
            
            # Verify calls
            mock_channel.get_data.assert_called_with(1)
            
    def test_specific_trial_out_of_range(self):
        # Mock Recording and Channel
        mock_recording = MagicMock()
        mock_channel = MagicMock()
        mock_channel.num_trials = 3
        mock_recording.channels = {'Ch1': mock_channel}
        self.mock_neo_adapter.read_recording.return_value = mock_recording
        
        with patch('Synaptipy.core.analysis.registry.AnalysisRegistry.get_function') as mock_get_func:
            mock_get_func.return_value = lambda *args, **kwargs: {}
            
            # Request trial 5 (out of range)
            pipeline_config = [{
                'analysis': 'dummy_analysis',
                'scope': 'specific_trial',
                'params': {'trial_index': 5}
            }]
            
            files = [Path("test_file.abf")]
            df = self.engine.run_batch(files, pipeline_config)
            
            self.assertFalse(df.empty)
            result = df.iloc[0]
            
            print("\nOut of Range Result:")
            print(result)
            
            self.assertIn('error', result)
            self.assertIn('Trial 5 out of range', result['error'])

if __name__ == '__main__':
    unittest.main()
