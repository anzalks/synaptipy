
import sys
import numpy as np
import unittest
from scipy.stats import median_abs_deviation

# Mock imports
from unittest.mock import MagicMock
sys.modules['Synaptipy.core.analysis.registry'] = MagicMock()
sys.modules['Synaptipy.core.results'] = MagicMock()

# Import functions
from Synaptipy.core.analysis.basic_features import find_stable_baseline
from Synaptipy.core.analysis.event_detection import detect_events_baseline_peak_kinetics

class TestEventDetectionRobustness(unittest.TestCase):
    def test_quiet_vs_noisy_segments(self):
        """Test detection when signal has a very quiet segment and a noisy segment."""
        fs = 1000.0
        duration = 2.0
        t = np.arange(int(duration * fs)) / fs
        
        # Segment 1: Quiet (SD=0.1) - 0.0 to 0.5s
        # Segment 2: Noisy (SD=1.0) - 0.5 to 2.0s
        
        quiet_len = int(0.5 * fs)
        data = np.zeros(len(t))
        
        # Quiet noise
        data[:quiet_len] = np.random.normal(0, 0.1, quiet_len)
        
        # Noisy noise
        data[quiet_len:] = np.random.normal(0, 1.0, len(data) - quiet_len)
        
        # Add ONE real event in the noisy part (Amplitude 5.0)
        event_idx = int(1.0 * fs)
        data[event_idx] += 5.0
        
        # Run detection
        # We expect threshold to be based on the NOISY part (SD=1.0), so ~3.0.
        # If it uses global percentile of the mix, it might be lower.
        
        indices, stats, _ = detect_events_baseline_peak_kinetics(
            data, fs, 
            direction='positive',
            auto_baseline=True,
            threshold_sd_factor=3.0
        )
        
        print(f"Stats: {stats}")
        
        # If threshold is ~3.0, we detect 1 event (plus maybe 1-2 false positives).
        # If threshold is ~0.3 (based on quiet), we detect HUNDREDS.
        
        self.assertLess(stats['count'], 20, "Should not detect massive noise peaks")
        self.assertGreaterEqual(stats['count'], 1, "Should detect the real event")

if __name__ == '__main__':
    unittest.main()
