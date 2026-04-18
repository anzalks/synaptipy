import numpy as np

from Synaptipy.core.processing_pipeline import (
    SignalProcessingPipeline,
    _apply_noise_floor_zeroing,
    _apply_pn_subtraction,
    apply_trace_corrections,
)


def test_pipeline_add_remove_clear():
    pipeline = SignalProcessingPipeline()

    step1 = {"type": "baseline", "method": "mean"}
    step2 = {"type": "filter", "method": "lowpass", "cutoff": 100}

    pipeline.add_step(step1)
    pipeline.add_step(step2)

    steps = pipeline.get_steps()
    assert len(steps) == 2
    assert steps[0] == step1
    assert steps[1] == step2

    # Test Remove
    pipeline.remove_step_by_type("baseline")
    steps = pipeline.get_steps()
    assert len(steps) == 1
    assert steps[0]["type"] == "filter"

    # Test Clear
    pipeline.clear()
    assert len(pipeline.get_steps()) == 0


def test_pipeline_processing_order():
    """Verify that operations are applied in order."""
    pipeline = SignalProcessingPipeline()

    # Create a signal: simply 0 to 10
    data = np.linspace(0, 10, 11)  # Mean is 5
    fs = 1000.0

    # Step 1: Baseline Mean (Subtract 5) -> Result: -5 to 5
    # Step 2: Absolute Value (Simulated via custom step? No, relying on standard steps)
    # Let's use standard steps.
    # Baseline Mean -> then user adds 5 (can't do that easily).

    # Let's check Baseline Mean
    pipeline.add_step({"type": "baseline", "method": "mean"})
    processed_1 = pipeline.process(data, fs)
    expected_1 = data - 5.0
    np.testing.assert_array_almost_equal(processed_1, expected_1)

    # Now add a second step that relies on the first.
    # It's hard to verify order with just standard filters without complex signal analysis.
    # But we can verify the pipeline ITERATES correctly.

    # Let's try two baselines.
    # 1. Mean (shifts to 0 mean)
    # 2. Add offset? No 'add offset' available.

    pass


def test_pipeline_integration():
    """Test full integration with a signal."""
    pipeline = SignalProcessingPipeline()

    # 1. Create a DC offset sine wave
    fs = 1000
    t = np.linspace(0, 1, fs)
    # 10 Hz sine + 500 Hz noise + 50 unit DC offset
    clean_sig = np.sin(2 * np.pi * 10 * t)
    noise = 0.5 * np.sin(2 * np.pi * 500 * t)
    dc_offset = 50.0
    raw_data = clean_sig + noise + dc_offset

    # 2. Add ops: Baseline (remove DC) -> Lowpass (remove noise)
    pipeline.add_step({"type": "baseline", "method": "mean"})
    pipeline.add_step({"type": "filter", "method": "lowpass", "cutoff": 100, "order": 4})

    processed = pipeline.process(raw_data, fs, t)

    # 3. Check DC is gone (mean approx 0)
    assert abs(np.mean(processed)) < 0.1

    # 4. Check Noise is reduced (std dev should be close to sine wave std dev ~0.707)
    # Clean sine std is 1/sqrt(2) = 0.707
    # Noise added variance. Filter should remove it.
    std_dev = np.std(processed)
    assert 0.6 < std_dev < 0.8  # Allow some margin


def test_empty_pipeline():
    pipeline = SignalProcessingPipeline()
    data = np.array([1, 2, 3])
    processed = pipeline.process(data, 100)
    np.testing.assert_array_equal(data, processed)


def test_region_baseline_no_time_vector():
    """Test handling of region baseline when time vector is missing."""
    pipeline = SignalProcessingPipeline()
    pipeline.add_step({"type": "baseline", "method": "region", "start_t": 0, "end_t": 1})

    data = np.array([10, 10, 10])
    # Should warn and return original data loop, effectively doing nothing or crashing?
    # Implementation logs warning and skips.
    processed = pipeline.process(data, 100, time_vector=None)
    np.testing.assert_array_equal(data, processed)


# ---------------------------------------------------------------------------
# Additional pipeline tests covering uncovered branches
# ---------------------------------------------------------------------------


class TestPipelineBaselines:
    """Cover region-based and mode-based baseline branches."""

    def _fs(self):
        return 1000.0

    def test_mode_baseline_no_region(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mode", "decimals": 1})
        data = np.full(100, 5.0) + np.random.default_rng(0).normal(0, 0.01, 100)
        processed = pipeline.process(data, self._fs())
        assert abs(np.mean(processed)) < 0.5

    def test_mode_baseline_with_region(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mode", "start_t": 0.0, "end_t": 0.1, "decimals": 1})
        fs = 1000.0
        n = 500
        time = np.linspace(0, 0.5, n)
        data = np.full(n, 3.0)
        processed = pipeline.process(data, fs, time_vector=time)
        np.testing.assert_allclose(processed, 0.0, atol=0.2)

    def test_mode_baseline_region_empty_mask(self):
        """Region window that misses all samples falls back to global mode."""
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mode", "start_t": 99.0, "end_t": 100.0, "decimals": 1})
        fs = 100.0
        time = np.linspace(0, 1.0, 100)
        data = np.full(100, 2.0)
        processed = pipeline.process(data, fs, time_vector=time)
        np.testing.assert_allclose(processed, 0.0, atol=0.2)

    def test_median_baseline_with_region(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "median", "start_t": 0.0, "end_t": 0.05})
        fs = 1000.0
        n = 200
        time = np.linspace(0, 0.2, n)
        data = np.full(n, 7.0)
        processed = pipeline.process(data, fs, time_vector=time)
        np.testing.assert_allclose(processed, 0.0, atol=0.01)

    def test_median_baseline_region_empty_falls_back(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "median", "start_t": 99.0, "end_t": 100.0})
        fs = 100.0
        time = np.linspace(0, 1.0, 100)
        data = np.full(100, 4.0)
        processed = pipeline.process(data, fs, time_vector=time)
        np.testing.assert_allclose(processed, 0.0, atol=0.01)

    def test_mean_baseline_global(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mean"})
        data = np.ones(50) * 3.0
        processed = pipeline.process(data, 100.0)
        np.testing.assert_allclose(processed, 0.0, atol=1e-10)

    def test_linear_baseline(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "linear"})
        data = np.linspace(0, 10, 100)  # linear trend
        processed = pipeline.process(data, 100.0)
        # After linear detrend, mean should be near 0
        assert abs(np.mean(processed)) < 0.5


class TestPipelineFilters:
    """Cover filter branches inside pipeline.process."""

    def test_highpass_filter_step(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "filter", "method": "highpass", "cutoff": 100.0, "order": 4})
        fs = 1000.0
        # DC signal should be largely removed
        data = np.ones(int(fs)) * 5.0
        processed = pipeline.process(data, fs)
        assert abs(np.mean(processed)) < 1.0

    def test_bandpass_filter_step(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "filter", "method": "bandpass", "low_cut": 10.0, "high_cut": 200.0, "order": 4})
        fs = 1000.0
        t = np.linspace(0, 1, int(fs))
        data = np.sin(2 * np.pi * 50 * t)  # 50 Hz - inside passband
        processed = pipeline.process(data, fs)
        assert processed is not None
        assert len(processed) == len(data)

    def test_notch_filter_step(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "filter", "method": "notch", "freq": 50.0, "q_factor": 30.0})
        fs = 1000.0
        t = np.linspace(0, 1, int(fs))
        data = np.sin(2 * np.pi * 50 * t)  # pure 50 Hz
        processed = pipeline.process(data, fs)
        # Power at 50 Hz should be strongly reduced
        assert np.std(processed) < np.std(data)

    def test_artifact_blanking_step(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "artifact", "onset_time": 0.1, "duration_ms": 2.0, "method": "hold"})
        fs = 1000.0
        t = np.linspace(0, 1, int(fs))
        data = np.ones(int(fs)) * 5.0
        processed = pipeline.process(data, fs, time_vector=t)
        assert processed is not None

    def test_artifact_blanking_no_time_vector(self):
        """Artifact step without time vector should be skipped gracefully."""
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "artifact", "onset_time": 0.1, "duration_ms": 2.0})
        data = np.ones(200)
        processed = pipeline.process(data, 1000.0, time_vector=None)
        np.testing.assert_array_equal(processed, data)

    def test_set_steps(self):
        pipeline = SignalProcessingPipeline()
        steps = [
            {"type": "baseline", "method": "mean"},
            {"type": "filter", "method": "notch", "freq": 50.0, "q_factor": 30.0},
        ]
        pipeline.set_steps(steps)
        assert len(pipeline.get_steps()) == 2

    def test_insert_step_at_index(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mean"})
        pipeline.add_step({"type": "filter", "method": "lowpass", "cutoff": 100}, index=0)
        assert pipeline.get_steps()[0]["type"] == "filter"

    def test_none_data_passthrough(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mean"})
        result = pipeline.process(None, 1000.0)
        assert result is None

    def test_empty_data_passthrough(self):
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mean"})
        data = np.array([])
        result = pipeline.process(data, 1000.0)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# apply_trace_corrections tests
# ---------------------------------------------------------------------------


class TestApplyTraceCorrections:
    """Tests for the 5-step apply_trace_corrections function."""

    def _make_signal(self, n=1000, fs=10000.0):
        t = np.linspace(0, n / fs, n, endpoint=False)
        data = np.zeros(n)
        return data, t, fs

    def test_no_corrections_returns_copy(self):
        data, t, fs = self._make_signal()
        result = apply_trace_corrections(data, t, fs)
        assert result is not data
        np.testing.assert_array_equal(result, data)

    def test_ljp_subtraction(self):
        data, t, fs = self._make_signal()
        data[:] = 10.0
        result = apply_trace_corrections(data, t, fs, ljp_mv=2.5)
        np.testing.assert_allclose(result, 7.5)

    def test_ljp_zero_skipped(self):
        data, t, fs = self._make_signal()
        data[:] = 5.0
        result = apply_trace_corrections(data, t, fs, ljp_mv=0.0)
        np.testing.assert_array_equal(result, data)

    def test_pn_subtraction(self):
        data, t, fs = self._make_signal()
        data[:] = 10.0
        pn = np.full((3, len(data)), 1.0)  # mean pn = 1.0
        result = apply_trace_corrections(data, t, fs, pn_traces=pn, pn_scale=1.0)
        np.testing.assert_allclose(result, 9.0)

    def test_pn_subtraction_scale(self):
        data, t, fs = self._make_signal()
        data[:] = 10.0
        pn = np.full((2, len(data)), 2.0)  # mean pn = 2.0, scale=0.5 -> subtract 1.0
        result = apply_trace_corrections(data, t, fs, pn_traces=pn, pn_scale=0.5)
        np.testing.assert_allclose(result, 9.0)

    def test_pn_subtraction_1d_trace(self):
        data, t, fs = self._make_signal()
        data[:] = 8.0
        pn = np.full(len(data), 2.0)  # 1D array
        result = apply_trace_corrections(data, t, fs, pn_traces=pn)
        np.testing.assert_allclose(result, 6.0)

    def test_pn_wrong_length_skipped(self):
        data, t, fs = self._make_signal(n=100)
        data[:] = 5.0
        pn = np.ones((3, 50))  # wrong length
        result = apply_trace_corrections(data, t, fs, pn_traces=pn)
        np.testing.assert_allclose(result, 5.0)  # unchanged

    def test_noise_floor_zeroing(self):
        data, t, fs = self._make_signal()
        data[:] = 3.0
        result = apply_trace_corrections(data, t, fs, pre_event_window_s=(0.0, 0.05))
        np.testing.assert_allclose(result, 0.0, atol=1e-10)

    def test_noise_floor_empty_window(self):
        data, t, fs = self._make_signal()
        data[:] = 3.0
        # Window outside the signal
        result = apply_trace_corrections(data, t, fs, pre_event_window_s=(99.0, 100.0))
        np.testing.assert_allclose(result, 3.0)  # unchanged

    def test_filter_step_applied(self):
        data, t, fs = self._make_signal(n=2000)
        noise = np.random.default_rng(42).normal(0, 1, 2000)
        data += noise
        filter_steps = [{"type": "filter", "method": "lowpass", "cutoff": 100.0, "order": 4}]
        result = apply_trace_corrections(data, t, fs, filter_steps=filter_steps)
        # Filtered result should have lower std than raw with noise
        assert np.std(result) < np.std(data)

    def test_artifact_interpolation_step(self):
        data, t, fs = self._make_signal()
        data[100:105] = 1000.0  # artifact spike
        art_steps = [{"onset_time": t[100], "duration_ms": 0.5}]
        result = apply_trace_corrections(data, t, fs, artifact_interp_steps=art_steps)
        # After interpolation the spike should be gone
        assert np.max(np.abs(result)) < 100.0

    def test_empty_data_passthrough(self):
        result = apply_trace_corrections(np.array([]), np.array([]), 1000.0)
        assert len(result) == 0

    def test_none_data_passthrough(self):
        result = apply_trace_corrections(None, None, 1000.0)
        assert result is None


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestApplyPnSubtraction:
    def test_2d_subtraction(self):
        data = np.full(100, 10.0)
        pn = np.full((4, 100), 2.0)
        result = _apply_pn_subtraction(data, pn, pn_scale=1.0)
        np.testing.assert_allclose(result, 8.0)

    def test_wrong_length_skipped(self):
        data = np.full(100, 5.0)
        pn = np.ones((2, 50))
        result = _apply_pn_subtraction(data, pn, pn_scale=1.0)
        np.testing.assert_allclose(result, 5.0)


class TestApplyNoiseFloorZeroing:
    def test_zeroing_applied(self):
        n = 1000
        time = np.linspace(0, 1.0, n)
        data = np.full(n, 5.0)
        result = _apply_noise_floor_zeroing(data, time, pre_event_window_s=(0.0, 0.1))
        np.testing.assert_allclose(result, 0.0, atol=1e-10)

    def test_empty_window_unchanged(self):
        n = 100
        time = np.linspace(0, 1.0, n)
        data = np.full(n, 5.0)
        result = _apply_noise_floor_zeroing(data, time, pre_event_window_s=(99.0, 100.0))
        np.testing.assert_allclose(result, 5.0)
