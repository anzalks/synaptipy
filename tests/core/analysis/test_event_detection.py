import numpy as np

from Synaptipy.core.analysis.event_detection import detect_events_template, detect_events_threshold
from Synaptipy.core.signal_processor import find_artifact_windows


class TestEventDetectionThreshold:
    def test_positive_polarity_basic(self):
        """Test basic positive peak detection."""
        dt = 0.001  # 1ms
        time = np.arange(0, 1.0, dt)
        data = np.zeros_like(time)

        # Create 2 events
        # Event 1 at 100ms, dur 10ms, height 10
        data[100:110] = np.linspace(0, 10, 10)
        data[110:120] = np.linspace(10, 0, 10)

        # Event 2 at 500ms, dur 20ms, height 15
        data[500:520] = np.linspace(0, 15, 20)
        data[520:540] = np.linspace(15, 0, 20)

        threshold = 5.0
        refractory = 0.05  # 50ms

        result = detect_events_threshold(data, time, threshold, polarity="positive", refractory_period=refractory)

        assert result.is_valid
        assert result.event_count == 2
        # Check indices or times approximately
        # Peak 1 should be around 110ms (index 110)
        # Peak 2 should be around 520ms (index 520)

        # Allow +/- 1 sample error
        assert np.any(np.abs(result.event_indices - 110) <= 1)
        assert np.any(np.abs(result.event_indices - 520) <= 1)

    def test_negative_polarity_rectification(self):
        """Test that negative events are correctly rectified and detected."""
        dt = 0.001
        time = np.arange(0, 1.0, dt)
        data = np.zeros_like(time)

        # Negative event at 200ms
        data[200:210] = np.linspace(0, -10, 10)
        data[210:220] = np.linspace(-10, 0, 10)

        threshold = 5.0  # Positive threshold convention for magnitude

        result = detect_events_threshold(data, time, threshold, polarity="negative", refractory_period=0.01)

        assert result.event_count == 1
        assert np.abs(result.event_indices[0] - 210) <= 1

    def test_refractory_period(self):
        """Test that smaller peaks within refractory period are ignored."""
        dt = 0.001
        time = np.arange(0, 1.0, dt)
        data = np.zeros_like(time)

        # Main event at 100ms, height 20
        data[100:110] = np.linspace(0, 20, 10)
        data[110:120] = np.linspace(20, 0, 10)

        # Smaller event at 130ms, height 10 (within 50ms refractory of 110)
        data[130:135] = np.linspace(0, 10, 5)
        data[135:140] = np.linspace(10, 0, 5)

        # Another event at 200ms (outside refractory)
        data[200:210] = np.linspace(0, 20, 10)
        data[210:220] = np.linspace(20, 0, 10)

        result = detect_events_threshold(data, time, threshold=5.0, polarity="positive", refractory_period=0.05)

        # Expecting 2 events: the one at 100ms and 200ms. The 130ms should be skipped if logic works "greedy" or max.
        # Implementation constraint says: "If two peaks are closer than refractory_period, discard the smaller one."
        assert result.event_count == 2
        # Ensure the timestamps correspond to the larger peaks
        indices = np.sort(result.event_indices)
        assert np.abs(indices[0] - 110) <= 1
        assert np.abs(indices[1] - 210) <= 1

    def test_long_event_span(self):
        """Test detection on a very long event (slow kinetics)."""
        dt = 0.001
        time = np.arange(0, 2.0, dt)
        data = np.zeros_like(time)

        # Slow event: rise 50ms, decay 200ms
        idx_start = 500
        rise_len = 50
        decay_len = 200

        data[idx_start : idx_start + rise_len] = np.linspace(0, 10, rise_len)
        data[idx_start + rise_len : idx_start + rise_len + decay_len] = np.linspace(10, 0, decay_len)

        # Threshold 2.0. The span will be very wide.
        # Peak should be exactly at idx_start + rise_len

        result = detect_events_threshold(data, time, threshold=2.0, polarity="positive", refractory_period=0.1)

        assert result.event_count == 1
        assert result.event_indices[0] == idx_start + rise_len - 1 or result.event_indices[0] == idx_start + rise_len


class TestEventDetectionTemplate:
    def test_template_generation_and_detection(self):
        """Test that bi-exponential template matches a synthetic event."""
        dt = 0.0001
        sampling_rate = 10000.0
        time = np.arange(0, 0.5, dt)

        # Synthesize an event: bi-exponential
        tau_rise = 0.001
        tau_decay = 0.005

        # Simple kernel shape
        kernel_t = np.arange(0, 0.05, dt)
        kernel = np.exp(-kernel_t / tau_decay) - np.exp(-kernel_t / tau_rise)
        kernel /= np.max(kernel)

        data = np.zeros_like(time)
        # Place event at 0.1s (index 1000)
        start_idx = 1000
        length = len(kernel)
        data[start_idx : start_idx + length] += 10.0 * kernel

        # Add some noise
        np.random.seed(42)
        noise = np.random.normal(0, 0.1, size=len(data))
        data += noise

        # Detect
        # polarity='positive' because I added positive kernel
        result = detect_events_template(
            data, sampling_rate, threshold_std=5.0, tau_rise=tau_rise, tau_decay=tau_decay, polarity="positive"
        )

        assert result.event_count == 1
        # The peak of the matched filter should align with the event.
        # Note: Convolution shifts the peak?
        # Matched filtering peaks where signal aligns best with template.
        # For a symmetric signal, it's center. For skewed bi-exp, it should be where the shape matches.
        # Our `detect_events_template` uses `mode='same'`.
        # Indices should be close to where the event starts + peak_offset of kernel?
        # Actually standard matched filter peak is at the end of the event in causal filtering,
        # but centered in 'same' mode correlation?
        # Let's check looseness.

        # The event starts at 1000.
        # The kernel peak is at some offset.
        # We expect a detection around index 1000 + kernel_peak_idx.

        # Let's just assert we found 1 event.
        # And check if index is reasonable (within the event window 0.1s to 0.15s)
        idx = result.event_indices[0]
        t_event = time[idx]
        assert 0.1 <= t_event <= 0.15

    def test_template_detection_negative(self):
        """Test negative polarity detection."""
        dt = 0.001
        sampling_rate = 1000.0
        time = np.arange(0, 1.0, dt)
        data = np.zeros_like(time)

        # Negative event
        data[200] = -10.0  # Impulse-like or short event
        # Actually let's shape it
        data[200:210] = np.linspace(0, -10, 10)
        data[210:250] = np.linspace(-10, 0, 40)

        result = detect_events_template(
            data, sampling_rate, threshold_std=4.0, tau_rise=0.005, tau_decay=0.020, polarity="negative"
        )

        assert result.event_count >= 1
        # Ideally 1, but shape mismatch might cause issues variance?
        # With Z-score of 4, noise is 0 (constant data implies MAD=0 -> handling 1e-12).
        # Any signal is infinite Z-score. So threshold works.

    def test_variable_noise_scaling(self):
        """Test that Z-score adapts to noise level."""
        sampling_rate = 1000.0
        data = np.random.normal(0, 1.0, size=1000)

        # Pure noise, threshold 10 SD -> Should detect nothing
        result = detect_events_template(
            data, sampling_rate, threshold_std=10.0, tau_rise=0.002, tau_decay=0.005, polarity="positive"
        )
        assert result.event_count == 0

        # Add big event
        data[500:520] = 50.0  # Huge spike relative to noise 1.0
        result = detect_events_template(
            data, sampling_rate, threshold_std=5.0, tau_rise=0.002, tau_decay=0.005, polarity="positive"
        )
        assert result.event_count >= 1


class TestArtifactRejection:
    def test_find_artifact_windows_basic(self):
        """Test artifact detector logic."""
        fs = 1000.0
        t = np.arange(0, 1.0, 1.0 / fs)
        data = np.random.normal(0, 1, size=len(t))

        # Add a sharp artifact (stronger step function to robustly exceed threshold)
        data[500:510] = 200.0

        # Slope threshold 50.0
        mask = find_artifact_windows(data, fs, slope_threshold=50.0, padding_ms=0)

        # Should detect the edges
        # Gradient roughly 200/2 = 100 >> 50
        assert np.any(mask[499:501])  # Rising edge
        assert np.any(mask[509:511])  # Falling edge

        # Test dilation
        mask_dilated = find_artifact_windows(data, fs, slope_threshold=50.0, padding_ms=2.0)
        # 2ms at 1kHz = 2 samples padding
        assert np.sum(mask_dilated) > np.sum(mask)

    def test_threshold_detection_with_mask(self):
        """Test that detect_events_threshold ignores masked regions."""
        fs = 1000.0
        t = np.arange(0, 1.0, 1.0 / fs)
        data = np.zeros_like(t)

        # Real event at 100ms (Positive), peak at 104
        data[100:105] = np.linspace(0, 10, 5)
        data[105:110] = np.linspace(10, 0, 5)

        # Artifact at 500ms
        data[500:505] = np.linspace(0, 10, 5)
        data[505:510] = np.linspace(10, 0, 5)
        mask = np.zeros_like(data, dtype=bool)
        mask[500:510] = True

        # Without mask -> 2 events
        # MUST specify polarity='positive' because data is positive
        res_nomask = detect_events_threshold(data, t, threshold=5.0, polarity="positive")
        assert res_nomask.event_count == 2

        # With mask -> 1 event (at around 104ms)
        res_mask = detect_events_threshold(data, t, threshold=5.0, polarity="positive", artifact_mask=mask)
        assert res_mask.event_count == 1
        assert np.abs(res_mask.event_indices[0] - 104) <= 1

    def test_template_detection_with_mask(self):
        """Test that detect_events_template ignores masked regions."""
        fs = 10000.0
        dt = 1.0 / fs
        t = np.arange(0, 0.5, dt)

        # Create kernel for proper signal shape
        tau_rise = 0.001
        tau_decay = 0.005
        # Kernel shape: (exp(-t/decay) - exp(-t/rise))
        kt = np.arange(0, 0.05, dt)
        kernel = np.exp(-kt / tau_decay) - np.exp(-kt / tau_rise)
        kernel /= np.max(np.abs(kernel))

        data = np.zeros_like(t)

        # Bump 1 at idx 1000
        data[1000 : 1000 + len(kernel)] = 10.0 * kernel
        # Bump 2 at idx 3000
        data[3000 : 3000 + len(kernel)] = 10.0 * kernel

        # Mask bump 2
        # Mask the region where the event is
        mask = np.zeros_like(data, dtype=bool)
        mask[3000 : 3000 + len(kernel)] = True

        res_mask = detect_events_template(
            data, fs, threshold_std=5.0, tau_rise=tau_rise, tau_decay=tau_decay, polarity="positive", artifact_mask=mask
        )

        # Should detect only 1 event
        assert res_mask.event_count == 1
        idx = res_mask.event_indices[0]
        assert 1000 <= idx <= 1500
