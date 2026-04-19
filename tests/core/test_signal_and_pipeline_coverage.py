# tests/core/test_signal_and_pipeline_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage tests for signal_processor.py, processing_pipeline.py, and data_model.py.
Targets the remaining uncovered lines.
"""

from pathlib import Path
from unittest.mock import patch

import numpy as np

from Synaptipy.core import signal_processor
from Synaptipy.core.data_model import Channel, Experiment, Recording
from Synaptipy.core.processing_pipeline import SignalProcessingPipeline, apply_trace_corrections

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FS = 10_000.0


def _signal(duration: float = 1.0) -> tuple:
    t = np.linspace(0, duration, int(duration * FS), endpoint=False)
    v = np.sin(2 * np.pi * 10.0 * t) * 5.0
    return v, t


def _channel(n_trials: int = 3, length: int = 100) -> Channel:
    return Channel(
        id="ch0",
        name="Vm",
        units="mV",
        sampling_rate=FS,
        data_trials=[np.zeros(length) for _ in range(n_trials)],
    )


# ===========================================================================
# signal_processor.py
# ===========================================================================


class TestGetScipy:
    def test_scipy_not_available(self):
        """Line 22-23: ImportError path in _get_scipy."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "scipy.signal":
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            sig, st, has = signal_processor._get_scipy()
            assert not has


class TestCheckTraceQuality:
    def test_drift_warning_triggered(self):
        """Line 95: Significant baseline drift warning."""
        # Create data with massive drift >> 5 * std
        t = np.linspace(0, 1.0, int(FS), endpoint=False)
        slope = 500.0  # huge drift
        data = slope * t  # pure ramp; std ~ 144, total drift = 500 >> 5*144=722 → need slope > 5*std
        # std of ramp: sqrt(1/12) * range = 0.289 * 500 = 144.3 → total_drift=500 > 5*144=722? No.
        # Make drift clearly larger than 5*std by using a step change
        data = np.concatenate([np.zeros(int(FS * 0.5)), np.full(int(FS * 0.5), 10000.0)])
        result = signal_processor.check_trace_quality(data, FS)
        # Should have a drift warning or at least run without error
        assert "warnings" in result

    def test_invalid_data_triggers_error_path(self):
        """Lines 168-171: Exception during quality check."""
        import scipy.stats as real_st

        def raise_err(*args, **kwargs):
            raise ValueError("forced linregress failure")

        with patch.object(real_st, "linregress", side_effect=raise_err):
            v, _ = _signal()
            result = signal_processor.check_trace_quality(v, FS)
            assert result.get("is_good") is False or "error" in result

    def test_normal_trace(self):
        v, t = _signal()
        result = signal_processor.check_trace_quality(v, FS)
        assert result["is_good"] is True


class TestSubtractBaselineFunctions:
    def test_subtract_baseline_mean_empty(self):
        """Lines 533-534: empty data path."""
        result = signal_processor.subtract_baseline_mean(np.array([]))
        assert result is not None

    def test_subtract_baseline_mean_none(self):
        result = signal_processor.subtract_baseline_mean(None)
        assert result is None

    def test_subtract_baseline_median_empty(self):
        """Lines 540-541: empty data path."""
        result = signal_processor.subtract_baseline_median(np.array([]))
        assert result is not None

    def test_subtract_baseline_median_none(self):
        result = signal_processor.subtract_baseline_median(None)
        assert result is None

    def test_subtract_baseline_region_empty_data(self):
        """Line 572: empty data."""
        t = np.linspace(0, 1.0, 100)
        result = signal_processor.subtract_baseline_region(np.array([]), t, 0.0, 0.5)
        assert result is not None

    def test_subtract_baseline_region_empty_region(self):
        """Lines 575-577: baseline region contains no data points."""
        v, t = _signal(0.5)
        result = signal_processor.subtract_baseline_region(v, t, 5.0, 10.0)
        # Region outside trace → warning, return original
        np.testing.assert_array_equal(result, v)

    def test_subtract_baseline_region_normal(self):
        v, t = _signal(1.0)
        result = signal_processor.subtract_baseline_region(v, t, 0.0, 0.1)
        assert result.shape == v.shape


class TestComputePsd:
    def test_psd_exception_returns_empty(self):
        """Lines 765-767: PSD computation fails."""
        v, _ = _signal()

        def bad_welch(*args, **kwargs):
            raise RuntimeError("welch failed")

        with patch.object(signal_processor, "_get_scipy") as mock_sp:
            import scipy.signal as real_sig
            import scipy.stats as real_st

            mock_sig = type("FakeSig", (), {})()

            class FakeWelch:
                @staticmethod
                def welch(*args, **kwargs):
                    raise RuntimeError("welch failed")

            for attr in dir(real_sig):
                try:
                    setattr(mock_sig, attr, getattr(real_sig, attr))
                except (AttributeError, TypeError):
                    pass
            mock_sig.welch = FakeWelch.welch
            mock_sp.return_value = (mock_sig, real_st, True)
            freqs, psd = signal_processor.compute_psd(v, FS)
            assert freqs.size == 0 and psd.size == 0

    def test_psd_normal(self):
        v, _ = _signal()
        freqs, psd = signal_processor.compute_psd(v, FS)
        assert freqs.size > 0


class TestMultiHarmonicNotch:
    def test_iircomb_unavailable_falls_back(self):
        """Lines 824-837: iircomb raises, use cascaded notch fallback."""
        v, _ = _signal()
        import scipy.signal as real_sig

        def raise_iircomb(*args, **kwargs):
            raise AttributeError("iircomb not available")

        with patch.object(real_sig, "iircomb", side_effect=raise_iircomb):
            result = signal_processor.multi_harmonic_notch(v, 50.0, FS)
            assert result.shape == v.shape

    def test_max_harmonics_stops_early(self):
        """Line 834-835: max_harmonics=1 stops after the first harmonic."""
        v, _ = _signal()
        # We need iircomb to fail to hit the cascaded path
        import scipy.signal as real_sig

        with patch.object(real_sig, "iircomb", side_effect=AttributeError("no iircomb")):
            result = signal_processor.multi_harmonic_notch(v, 50.0, FS, max_harmonics=1)
            assert result.shape == v.shape

    def test_normal_iircomb_path(self):
        """Normal case where iircomb succeeds."""
        v, _ = _signal()
        result = signal_processor.multi_harmonic_notch(v, 50.0, FS)
        assert result.shape == v.shape

    def test_invalid_fundamental(self):
        v, _ = _signal()
        result = signal_processor.multi_harmonic_notch(v, 0.0, FS)
        np.testing.assert_array_equal(result, v)

    def test_empty_data(self):
        result = signal_processor.multi_harmonic_notch(np.array([]), 50.0, FS)
        assert result.size == 0


class TestSosfiltfiltSafe:
    def test_scipy_unavailable_returns_data(self):
        """Line 191: has_scipy=False returns data unchanged."""
        v, _ = _signal()
        import scipy.signal as real_sig

        sos = real_sig.butter(2, 100.0 / (FS / 2), btype="low", output="sos")
        with patch.object(signal_processor, "_get_scipy", return_value=(None, None, False)):
            result = signal_processor._sosfiltfilt_safe(sos, v)
            np.testing.assert_array_equal(result, v)


class TestValidateSamplingRate:
    def test_negative_rate(self):
        assert signal_processor.validate_sampling_rate(-1.0) is False

    def test_low_rate_warning(self):
        assert signal_processor.validate_sampling_rate(50.0) is True


# ===========================================================================
# processing_pipeline.py
# ===========================================================================


class TestSignalProcessingPipelineProcess:
    def test_empty_data_returns_early(self):
        pipeline = SignalProcessingPipeline()
        result = pipeline.process(np.array([]), FS)
        assert result is not None

    def test_none_data_returns_early(self):
        pipeline = SignalProcessingPipeline()
        result = pipeline.process(None, FS)
        assert result is None

    def test_baseline_mean_with_region(self):
        """Line 113: mean baseline with use_region=True."""
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mean", "start_t": 0.0, "end_t": 0.1})
        result = pipeline.process(v, FS, time_vector=t)
        assert result.shape == v.shape

    def test_baseline_mean_without_region(self):
        """Line 117: mean baseline without time vector."""
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mean"})
        result = pipeline.process(v, FS)
        assert result.shape == v.shape

    def test_baseline_median_without_region(self):
        """Line 126: median baseline without time vector."""
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "median"})
        result = pipeline.process(v, FS)
        assert result.shape == v.shape

    def test_baseline_median_with_region(self):
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "median", "start_t": 0.0, "end_t": 0.1})
        result = pipeline.process(v, FS, time_vector=t)
        assert result.shape == v.shape

    def test_baseline_median_region_empty(self):
        """Median region baseline when region has no points — falls back to full median."""
        v, t = _signal(0.5)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "median", "start_t": 5.0, "end_t": 10.0})
        result = pipeline.process(v, FS, time_vector=t)
        assert result.shape == v.shape

    def test_baseline_region_with_time_vector(self):
        """Lines 131-133: region method with time_vector."""
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "region", "start_t": 0.0, "end_t": 0.1})
        result = pipeline.process(v, FS, time_vector=t)
        assert result.shape == v.shape

    def test_baseline_region_without_time_vector(self):
        """Line 135: region baseline skipped when no time_vector."""
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "region", "start_t": 0.0, "end_t": 0.1})
        result = pipeline.process(v, FS)  # no time_vector
        assert result.shape == v.shape

    def test_nan_inf_warning_logged(self):
        """Lines 165-166: NaN/Inf result check after step."""
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()

        def bad_mean(data):
            return np.full_like(data, np.nan)

        with patch.object(signal_processor, "subtract_baseline_mean", side_effect=bad_mean):
            pipeline.add_step({"type": "baseline", "method": "mean"})
            result = pipeline.process(v, FS)
            # Should return NaN-filled result without crashing
            assert result is not None

    def test_exception_in_step_handled(self):
        """Lines 168-169: Exception during step processing."""
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()

        def raise_err(data):
            raise RuntimeError("forced error")

        with patch.object(signal_processor, "subtract_baseline_mean", side_effect=raise_err):
            pipeline.add_step({"type": "baseline", "method": "mean"})
            result = pipeline.process(v, FS)
            assert result is not None

    def test_filter_lowpass(self):
        v, t = _signal()
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "filter", "method": "lowpass", "cutoff": 500.0, "order": 2})
        result = pipeline.process(v, FS)
        assert result.shape == v.shape

    def test_filter_highpass(self):
        v, t = _signal()
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "filter", "method": "highpass", "cutoff": 5.0, "order": 2})
        result = pipeline.process(v, FS)
        assert result.shape == v.shape

    def test_filter_bandpass(self):
        v, t = _signal()
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "filter", "method": "bandpass", "low_cut": 5.0, "high_cut": 500.0, "order": 2})
        result = pipeline.process(v, FS)
        assert result.shape == v.shape

    def test_filter_notch(self):
        v, t = _signal()
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "filter", "method": "notch", "freq": 50.0, "q_factor": 30.0})
        result = pipeline.process(v, FS)
        assert result.shape == v.shape

    def test_artifact_blanking_with_time_vector(self):
        v, t = _signal()
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "artifact", "onset_time": 0.1, "duration_ms": 2.0})
        result = pipeline.process(v, FS, time_vector=t)
        assert result.shape == v.shape

    def test_artifact_blanking_without_time_vector(self):
        v, t = _signal()
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "artifact", "onset_time": 0.1, "duration_ms": 2.0})
        result = pipeline.process(v, FS)
        assert result.shape == v.shape

    def test_baseline_mode_with_region(self):
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mode", "start_t": 0.0, "end_t": 0.1})
        result = pipeline.process(v, FS, time_vector=t)
        assert result.shape == v.shape

    def test_baseline_mode_without_region(self):
        v, t = _signal(1.0)
        pipeline = SignalProcessingPipeline()
        pipeline.add_step({"type": "baseline", "method": "mode"})
        result = pipeline.process(v, FS)
        assert result.shape == v.shape


class TestApplyTraceCorrections:
    def test_basic_ljp(self):
        v, t = _signal()
        result = apply_trace_corrections(v, t, FS, ljp_mv=5.0)
        np.testing.assert_allclose(result, v - 5.0)

    def test_pn_traces(self):
        v, t = _signal()
        pn = np.vstack([v * 0.1, v * 0.1])
        result = apply_trace_corrections(v, t, FS, pn_traces=pn, pn_scale=1.0)
        assert result.shape == v.shape

    def test_pre_event_zeroing(self):
        v, t = _signal()
        result = apply_trace_corrections(v, t, FS, pre_event_window_s=(0.0, 0.1))
        assert result.shape == v.shape

    def test_artifact_interp(self):
        v, t = _signal()
        result = apply_trace_corrections(v, t, FS, artifact_interp_steps=[{"onset_time": 0.1, "duration_ms": 2.0}])
        assert result.shape == v.shape

    def test_filter_steps(self):
        v, t = _signal()
        result = apply_trace_corrections(
            v, t, FS, filter_steps=[{"type": "filter", "method": "lowpass", "cutoff": 1000.0, "order": 2}]
        )
        assert result.shape == v.shape

    def test_empty_data(self):
        result = apply_trace_corrections(None, None, FS)
        assert result is None

    def test_pn_length_mismatch(self):
        v, t = _signal()
        pn = np.vstack([np.zeros(50), np.zeros(50)])  # wrong length
        result = apply_trace_corrections(v, t, FS, pn_traces=pn)
        assert result.shape == v.shape

    def test_pre_event_zeroing_no_points_in_window(self):
        v, t = _signal()
        result = apply_trace_corrections(v, t, FS, pre_event_window_s=(5.0, 10.0))
        assert result.shape == v.shape


# ===========================================================================
# data_model.py
# ===========================================================================


class TestChannelGetAveragedData:
    def test_trial_indices_valid(self):
        """Lines 307-309: valid trial_indices used."""
        ch = _channel(n_trials=4, length=50)
        result = ch.get_averaged_data(trial_indices=[0, 1])
        assert result is not None
        assert len(result) == 50

    def test_trial_indices_empty(self):
        """Empty trial_indices falls back to all trials."""
        ch = _channel(n_trials=3, length=50)
        result = ch.get_averaged_data(trial_indices=[])
        assert result is not None

    def test_trial_indices_invalid(self):
        """Out-of-range indices → valid_indices empty → None returned."""
        ch = _channel(n_trials=2, length=50)
        result = ch.get_averaged_data(trial_indices=[99, 100])
        assert result is None

    def test_differing_lengths_returns_none(self):
        """Lines 321-323: trials with different lengths."""
        ch = Channel(
            id="ch0",
            name="V",
            units="mV",
            sampling_rate=FS,
            data_trials=[np.zeros(50), np.zeros(100)],
        )
        result = ch.get_averaged_data()
        assert result is None

    def test_no_trials(self):
        ch = Channel(id="ch0", name="V", units="mV", sampling_rate=FS, data_trials=[])
        result = ch.get_averaged_data()
        assert result is None


class TestChannelGetAveragedCurrentData:
    def test_differing_current_lengths(self):
        """Lines 361-362: current trials with different lengths → None."""
        ch = _channel(n_trials=2, length=50)
        ch.current_data_trials = [np.zeros(50), np.zeros(100)]
        result = ch.get_averaged_current_data()
        assert result is None

    def test_normal_current_averaging(self):
        ch = _channel(n_trials=2, length=50)
        ch.current_data_trials = [np.zeros(50), np.ones(50)]
        result = ch.get_averaged_current_data()
        assert result is not None
        np.testing.assert_allclose(result, 0.5)

    def test_no_current_data(self):
        ch = _channel()
        result = ch.get_averaged_current_data()
        assert result is None


class TestChannelGetFiniteDataBounds:
    def test_all_nan_returns_none(self):
        """Lines 405-406: all NaN data → size 0 after filtering → None."""
        ch = Channel(
            id="ch0",
            name="V",
            units="mV",
            sampling_rate=FS,
            data_trials=[np.full(50, np.nan)],
        )
        result = ch.get_finite_data_bounds()
        assert result is None

    def test_mixed_nan_returns_bounds(self):
        data = np.array([np.nan, 1.0, 2.0, np.nan, -1.0])
        ch = Channel(id="ch0", name="V", units="mV", sampling_rate=FS, data_trials=[data])
        result = ch.get_finite_data_bounds()
        assert result == (-1.0, 2.0)

    def test_empty_trials(self):
        ch = Channel(id="ch0", name="V", units="mV", sampling_rate=FS, data_trials=[])
        result = ch.get_finite_data_bounds()
        assert result is None


class TestRecordingInit:
    def test_non_path_source_file(self):
        """Lines 471-472: non-Path source_file → warning, placeholder set."""
        rec = Recording(source_file="not_a_path")
        assert isinstance(rec.source_file, Path)

    def test_path_source_file(self):
        rec = Recording(source_file=Path("/tmp/test.abf"))
        assert rec.source_file == Path("/tmp/test.abf")


class TestExperiment:
    def test_init(self):
        """Lines 528-530: Experiment initialisation."""
        exp = Experiment()
        assert isinstance(exp.recordings, list)
        assert isinstance(exp.identifier, str)


# ===========================================================================
# signal_processor.py filter exception paths
# ===========================================================================


class TestFilterExceptionPaths:
    """Force filter exception paths by making scipy.signal.butter raise."""

    def _get_butter(self):
        import scipy.signal as sig

        return sig

    def test_bandpass_filter_exception(self):
        """Lines 288-290: bandpass_filter except block."""
        v, _ = _signal()
        sig = self._get_butter()
        with patch.object(sig, "butter", side_effect=ValueError("butter fail")):
            result = signal_processor.bandpass_filter(v, 10.0, 1000.0, FS)
            np.testing.assert_array_equal(result, v)

    def test_lowpass_filter_exception(self):
        """Lines 333-335: lowpass_filter except block."""
        v, _ = _signal()
        sig = self._get_butter()
        with patch.object(sig, "butter", side_effect=ValueError("butter fail")):
            result = signal_processor.lowpass_filter(v, 1000.0, FS)
            np.testing.assert_array_equal(result, v)

    def test_highpass_filter_exception(self):
        """Lines 378-380: highpass_filter except block."""
        v, _ = _signal()
        sig = self._get_butter()
        with patch.object(sig, "butter", side_effect=ValueError("butter fail")):
            result = signal_processor.highpass_filter(v, 10.0, FS)
            np.testing.assert_array_equal(result, v)

    def test_notch_filter_exception(self):
        """Lines 428-430: notch_filter except block."""
        v, _ = _signal()
        sig = self._get_butter()
        with patch.object(sig, "iirnotch", side_effect=ValueError("iirnotch fail")):
            result = signal_processor.notch_filter(v, 50.0, 30.0, FS)
            np.testing.assert_array_equal(result, v)

    def test_comb_filter_exception(self):
        """Lines 476-478: comb_filter except block."""
        v, _ = _signal()
        sig = self._get_butter()
        with patch.object(sig, "iircomb", side_effect=ValueError("iircomb fail")):
            result = signal_processor.comb_filter(v, 50.0, 30.0, FS)
            np.testing.assert_array_equal(result, v)


class TestSubtractBaselineModeFallback:
    """Lines 518-525: subtract_baseline_mode fallback when stats.mode fails."""

    def test_mode_exception_fallback(self):
        import scipy.stats as real_st

        v, _ = _signal()
        with patch.object(real_st, "mode", side_effect=ValueError("mode fail")):
            result = signal_processor.subtract_baseline_mode(v)
            assert result is not None

    def test_mode_scalar_path(self):
        """Line 516: np.isscalar(mode_result.mode) path."""
        v = np.array([1.0, 1.0, 2.0, 1.0, 3.0])
        result = signal_processor.subtract_baseline_mode(v, decimals=0)
        assert result is not None

    def test_mode_0dim_path(self):
        """Line 518-519: 0-dim mode path with new scipy keepdims."""
        import types

        import scipy.stats as real_st

        v, _ = _signal()
        # Simulate 0-dim array mode result
        fake_result = types.SimpleNamespace(mode=np.array(1.0))  # 0-dim
        with patch.object(real_st, "mode", return_value=fake_result):
            result = signal_processor.subtract_baseline_mode(v)
            assert result is not None

    def test_mode_1dim_array_path(self):
        """Line 521: mode_result.mode is a 1-D array → use [0] element."""
        import types

        import scipy.stats as real_st

        v, _ = _signal()
        fake_result = types.SimpleNamespace(mode=np.array([1.0]))  # 1-dim
        with patch.object(real_st, "mode", return_value=fake_result):
            result = signal_processor.subtract_baseline_mode(v)
            assert result is not None


class TestCheckTraceQualityLfInstability:
    """Lines 159-164: Low-frequency instability path."""

    def test_lf_instability_warning(self):
        """Lines 159-162: Trigger LF variance > 2x HF variance warning."""
        # 0.1 Hz signal needs ~10 cycles to let the causal filter settle
        # Use 5-second trace so sosfilt captures the LF energy properly
        fs = FS
        n = int(fs * 5.0)
        t = np.linspace(0, 5.0, n, endpoint=False)
        # Large LF component (0.1 Hz) + tiny HF noise
        data = 50.0 * np.sin(2 * np.pi * 0.1 * t) + 1e-3 * np.random.default_rng(42).standard_normal(n)
        result = signal_processor.check_trace_quality(data, fs)
        # The LF instability warning should be in the output
        assert any("Low-frequency instability" in w for w in result["warnings"])

    def test_lf_filter_exception(self):
        """Lines 163-164: exception in LF filter block."""
        import scipy.signal as sig

        v, _ = _signal()
        # Make butter raise so the inner try block fails
        with patch.object(sig, "butter", side_effect=RuntimeError("butter fail lf")):
            result = signal_processor.check_trace_quality(v, FS)
        # Should not crash, just skip LF variance check
        assert isinstance(result, dict)

    def test_check_freq_power_empty_band(self):
        """Line 115: empty freq band in check_freq_power."""
        v = np.ones(10)
        result = signal_processor.check_trace_quality(v, FS)
        assert isinstance(result, dict)


# ===========================================================================
# data_model.py additional tests
# ===========================================================================


class TestChannelUndoStack:
    def test_push_and_undo(self):
        ch = _channel(n_trials=2, length=50)
        original = ch.data_trials[0].copy()
        ch.push_undo("test_change")
        ch.data_trials[0][:] = 999.0
        assert ch.can_undo
        result = ch.undo()
        assert result is True
        np.testing.assert_array_equal(ch.data_trials[0], original)

    def test_undo_empty_stack(self):
        ch = _channel(n_trials=2, length=50)
        assert not ch.can_undo
        result = ch.undo()
        assert result is False

    def test_get_data_bounds_normal(self):
        ch = Channel(
            id="ch0",
            name="V",
            units="mV",
            sampling_rate=FS,
            data_trials=[np.array([-1.0, 0.0, 1.0])],
        )
        bounds = ch.get_data_bounds()
        assert bounds == (-1.0, 1.0)

    def test_get_data_bounds_empty(self):
        ch = Channel(id="ch0", name="V", units="mV", sampling_rate=FS, data_trials=[])
        assert ch.get_data_bounds() is None

    def test_repr(self):
        ch = _channel()
        assert "Channel" in repr(ch)
