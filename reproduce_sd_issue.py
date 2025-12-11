
import sys
import unittest
import numpy as np
from unittest.mock import MagicMock

# Mock imports
sys.modules['Synaptipy.core.analysis.registry'] = MagicMock()
sys.modules['Synaptipy.core.results'] = MagicMock()

# Import the functions
from Synaptipy.core.analysis.basic_features import find_stable_baseline
from Synaptipy.core.analysis.event_detection import detect_events_baseline_peak_kinetics

class TestEventDetectionSD(unittest.TestCase):
    def test_sd_too_small_with_flat_segment(self):
        """Test that min-variance baseline picks flat segment, leading to tiny SD and noise detection."""
        fs = 1000.0
        duration = 2.0
        t = np.arange(int(duration * fs)) / fs
        
        # Create signal: 
        # 0.0-0.5s: Perfectly flat (artifact/padding) -> Variance = 0
        # 0.5-2.0s: Gaussian noise (SD=1) + Events
        
        noise_sd = 1.0
        data = np.random.normal(0, noise_sd, len(t))
        
        # Add flat segment
        flat_len = int(0.5 * fs)
        data[:flat_len] = 0.0
        
        # Add an event at 1.0s (Amplitude 5)
        event_idx = int(1.0 * fs)
        data[event_idx] += 5.0
        
        # Run detection with auto-baseline
        # It should pick the flat segment
        indices, stats, _ = detect_events_baseline_peak_kinetics(
            data, fs, 
            direction='positive',
            auto_baseline=True,
            threshold_sd_factor=3.0
        )
        
        print(f"Baseline SD: {stats['baseline_sd']}")
        print(f"Count: {stats['count']}")
        
        # Expectation with MAD fix:
        # Baseline SD might still be small (from flat segment), BUT the threshold calculation 
        # should now use MAD of the whole trace (~1.0), so threshold should be ~3.0.
        # It should detect the event at 5.0, but NOT the noise (amplitude ~1-2).
        
        print(f"Stats: {stats}")
        
        # We expect count to be close to 1. 
        # With threshold=3.0 SD, we expect ~0.13% false positives in Gaussian noise.
        # 1500 points * 0.0013 = ~2 false positives.
        # So count should be around 1 + 2 = 3.
        self.assertLess(stats['count'], 10, "Should NOT detect massive noise peaks")
        self.assertGreaterEqual(stats['count'], 1, "Should detect the real event")
        self.assertLessEqual(stats['count'], 5, "Should not detect too many false positives")

if __name__ == '__main__':
    unittest.main()
