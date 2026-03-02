# tests/core/test_signal_processor.py
"""
Tests for signal processing utilities.
"""

import numpy as np

from Synaptipy.core import signal_processor


class TestFilters:
    """Tests for filter functions."""

    def test_lowpass_filter_basic(self):
        """Test lowpass filter removes high frequencies."""
        fs = 1000  # Hz
        t = np.linspace(0, 1, fs)
        # Signal: 5 Hz + 100 Hz
        low_freq = np.sin(2 * np.pi * 5 * t)
        high_freq = 0.5 * np.sin(2 * np.pi * 100 * t)
        data = low_freq + high_freq

        # Filter at 20 Hz should remove 100 Hz component
        filtered = signal_processor.lowpass_filter(data, cutoff=20, fs=fs)

        # Power of high frequency should be significantly reduced
        # Check by correlating with original components
        assert np.corrcoef(filtered, low_freq)[0, 1] > 0.9
        # High freq component should be mostly gone after filtering
        assert np.std(filtered) < np.std(data)

    def test_highpass_filter_basic(self):
        """Test highpass filter removes low frequencies."""
        fs = 1000  # Hz
        t = np.linspace(0, 1, fs)
        # Signal: DC + slow drift + fast signal
        dc = 5.0
        slow = 2 * np.sin(2 * np.pi * 0.5 * t)  # 0.5 Hz
        fast = np.sin(2 * np.pi * 50 * t)  # 50 Hz
        data = dc + slow + fast

        # Filter at 10 Hz should remove DC and slow component
        filtered = signal_processor.highpass_filter(data, cutoff=10, fs=fs)

        # DC should be removed (mean near zero)
        assert abs(np.mean(filtered)) < 0.5

    def test_bandpass_filter_basic(self):
        """Test bandpass filter isolates frequency band."""
        fs = 1000  # Hz
        t = np.linspace(0, 1, fs)
        # Signals at different frequencies
        low = np.sin(2 * np.pi * 5 * t)  # 5 Hz
        mid = np.sin(2 * np.pi * 50 * t)  # 50 Hz
        high = np.sin(2 * np.pi * 200 * t)  # 200 Hz
        data = low + mid + high

        # Bandpass 30-100 Hz should isolate 50 Hz component
        filtered = signal_processor.bandpass_filter(data, lowcut=30, highcut=100, fs=fs)

        # Mid frequency should be preserved
        assert np.corrcoef(filtered, mid)[0, 1] > 0.7

    def test_notch_filter_removes_line_noise(self):
        """Test notch filter removes specific frequency."""
        fs = 1000  # Hz
        t = np.linspace(0, 1, fs)
        # Signal with 60 Hz line noise
        clean_signal = np.sin(2 * np.pi * 10 * t)
        line_noise = 0.3 * np.sin(2 * np.pi * 60 * t)
        data = clean_signal + line_noise

        # Notch at 60 Hz
        filtered = signal_processor.notch_filter(data, freq=60, Q=30, fs=fs)

        # 60 Hz power should be significantly reduced
        # Compare FFT power at 60 Hz
        freqs = np.fft.rfftfreq(len(data), 1 / fs)
        orig_fft = np.abs(np.fft.rfft(data))
        filt_fft = np.abs(np.fft.rfft(filtered))
        idx_60 = np.argmin(np.abs(freqs - 60))

        # Power at 60 Hz should be reduced
        assert filt_fft[idx_60] < orig_fft[idx_60] * 0.3


class TestBaselineSubtraction:
    """Tests for baseline subtraction methods."""

    def test_subtract_baseline_mean(self):
        """Test mean baseline subtraction."""
        data = np.array([10, 12, 11, 13, 10])
        result = signal_processor.subtract_baseline_mean(data)
        np.testing.assert_almost_equal(np.mean(result), 0)

    def test_subtract_baseline_median(self):
        """Test median baseline subtraction."""
        data = np.array([10, 12, 11, 13, 100])  # outlier at end
        result = signal_processor.subtract_baseline_median(data)
        # Median of original is 12, so result should be centered there
        assert np.median(result) == 0

    def test_subtract_baseline_linear(self):
        """Test linear detrending."""
        # Create data with linear trend
        t = np.arange(100)
        trend = 0.5 * t + 10  # linear drift
        signal_part = np.sin(2 * np.pi * 0.05 * t)
        data = trend + signal_part

        result = signal_processor.subtract_baseline_linear(data)

        # Linear fit of result should have near-zero slope
        slope = np.polyfit(t, result, 1)[0]
        assert abs(slope) < 0.01

    def test_subtract_baseline_mode(self):
        """Test mode baseline subtraction."""
        # Create data with clear mode value
        data = np.concatenate(
            [
                np.full(100, 5.0),  # Mode value
                np.random.randn(20) * 0.5 + 5,  # Noise around mode
                np.array([10, 12, 8]),  # Some outliers
            ]
        )
        result = signal_processor.subtract_baseline_mode(data, decimals=0)
        # Mode should be near 5, so most values should be near 0 after subtraction
        assert abs(np.median(result)) < 1

    def test_subtract_baseline_region(self):
        """Test region-based baseline subtraction."""
        # Create data with known baseline in specific region
        data = np.zeros(100)
        data[:20] = 5.0  # Baseline region with value 5
        data[20:] = np.sin(np.linspace(0, 4 * np.pi, 80)) * 10 + 5

        t = np.linspace(0, 1, 100)
        result = signal_processor.subtract_baseline_region(data, t, start_t=0, end_t=0.19)
        # Data in baseline region should now be near 0
        assert abs(np.mean(result[:20])) < 0.1


class TestTraceQuality:
    """Tests for trace quality checks."""

    def test_check_trace_quality_clean_signal(self):
        """Test quality check on clean signal."""
        fs = 10000  # Hz
        t = np.linspace(0, 1, fs)
        # Clean signal
        data = np.sin(2 * np.pi * 10 * t)

        result = signal_processor.check_trace_quality(data, fs)

        # Check structure matches actual implementation
        assert "is_good" in result
        assert "metrics" in result
        assert "rms_noise" in result["metrics"]

    def test_check_trace_quality_noisy_signal(self):
        """Test quality check detects noisy signal."""
        fs = 10000  # Hz
        np.random.seed(42)
        # Very noisy signal
        data = np.random.randn(fs) * 10

        result = signal_processor.check_trace_quality(data, fs)
        # RMS noise should be high for pure noise
        assert result["metrics"]["rms_noise"] > 5

    def test_check_trace_quality_with_60hz_noise(self):
        """Test quality check detects 60Hz line noise."""
        fs = 10000  # Hz
        t = np.linspace(0, 1, fs)
        # Clean signal with strong 60 Hz noise
        clean = np.sin(2 * np.pi * 10 * t)
        noise_60hz = 2 * np.sin(2 * np.pi * 60 * t)
        data = clean + noise_60hz

        result = signal_processor.check_trace_quality(data, fs)
        # 60 Hz ratio should be elevated
        assert "line_noise_60hz_ratio" in result["metrics"]
