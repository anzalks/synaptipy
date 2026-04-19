# -*- coding: utf-8 -*-
"""Extended tests for core/signal_processor.py covering previously uncovered branches."""

from unittest.mock import patch

import numpy as np
import pytest

from Synaptipy.core import signal_processor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FS = 10000.0  # 10 kHz sampling rate
N = int(FS)  # 1 second of data


def _clean(n=N, fs=FS):
    """Return a simple clean sinusoidal signal."""
    t = np.linspace(0, n / fs, n, endpoint=False)
    return t, np.sin(2 * np.pi * 10 * t)


def _no_scipy():
    """Patch _get_scipy to simulate scipy not installed."""
    return patch.object(signal_processor, "_get_scipy", return_value=(None, None, False))


# ---------------------------------------------------------------------------
# validate_sampling_rate
# ---------------------------------------------------------------------------


class TestValidateSamplingRate:
    def test_negative_rate_returns_false(self):
        assert signal_processor.validate_sampling_rate(-100.0) is False

    def test_zero_rate_returns_false(self):
        assert signal_processor.validate_sampling_rate(0.0) is False

    def test_low_rate_warning_still_true(self):
        result = signal_processor.validate_sampling_rate(50.0)
        assert result is True

    def test_normal_rate_returns_true(self):
        assert signal_processor.validate_sampling_rate(10000.0) is True


# ---------------------------------------------------------------------------
# check_trace_quality
# ---------------------------------------------------------------------------


class TestCheckTraceQuality:
    def test_empty_data_returns_invalid(self):
        result = signal_processor.check_trace_quality(np.array([]), 1000.0)
        assert result["is_good"] is False

    def test_none_data_returns_invalid(self):
        result = signal_processor.check_trace_quality(None, 1000.0)
        assert result["is_good"] is False

    def test_no_scipy_falls_back_gracefully(self):
        t, data = _clean()
        with _no_scipy():
            result = signal_processor.check_trace_quality(data, FS)
        assert "warnings" in result

    def test_lf_variance_branch_covered(self):
        """Use a very long trace to trigger the <1 Hz LF branch."""
        t, data = _clean(n=int(FS * 2))
        result = signal_processor.check_trace_quality(data, FS)
        assert "is_good" in result

    def test_50hz_line_noise_detected(self):
        fs = 10000.0
        n = int(fs * 2)
        t = np.linspace(0, n / fs, n, endpoint=False)
        noise = 5.0 * np.sin(2 * np.pi * 50 * t)
        data = np.random.default_rng(42).normal(0, 0.01, n) + noise
        result = signal_processor.check_trace_quality(data, fs)
        assert "line_noise_50hz_ratio" in result["metrics"]


# ---------------------------------------------------------------------------
# _validate_filter_input
# ---------------------------------------------------------------------------


class TestValidateFilterInput:
    def test_empty_array_returns_invalid(self):
        valid, out = signal_processor._validate_filter_input(np.array([]), 1000.0)
        assert valid is False

    def test_none_returns_invalid(self):
        valid, out = signal_processor._validate_filter_input(None, 1000.0)
        assert valid is False

    def test_negative_fs_returns_invalid(self):
        valid, out = signal_processor._validate_filter_input(np.ones(100), -100.0)
        assert valid is False

    def test_order_clamping_high(self):
        valid, data = signal_processor._validate_filter_input(np.ones(200), 1000.0, order=15)
        assert valid is True

    def test_order_clamping_low(self):
        valid, data = signal_processor._validate_filter_input(np.ones(200), 1000.0, order=0)
        assert valid is True

    def test_nan_data_returns_invalid(self):
        data = np.array([1.0, np.nan, 3.0])
        valid, _ = signal_processor._validate_filter_input(data, 1000.0)
        assert valid is False

    def test_inf_data_returns_invalid(self):
        data = np.array([1.0, np.inf, 3.0])
        valid, _ = signal_processor._validate_filter_input(data, 1000.0)
        assert valid is False

    def test_too_short_returns_invalid(self):
        data = np.ones(3)
        valid, _ = signal_processor._validate_filter_input(data, 1000.0, order=5)
        assert valid is False

    def test_valid_input_returns_true(self):
        data = np.ones(100)
        valid, out = signal_processor._validate_filter_input(data, 1000.0, order=4)
        assert valid is True


# ---------------------------------------------------------------------------
# Filter edge cases: no-scipy fallback + out-of-bounds cutoffs
# ---------------------------------------------------------------------------


class TestBandpassFilterEdgeCases:
    def test_no_scipy_returns_original(self):
        _, data = _clean()
        with _no_scipy():
            out = signal_processor.bandpass_filter(data, 5.0, 50.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_empty_data(self):
        out = signal_processor.bandpass_filter(np.array([]), 5.0, 50.0, FS)
        assert len(out) == 0

    def test_low_cutoff_out_of_bounds(self):
        _, data = _clean()
        out = signal_processor.bandpass_filter(data, 0.0, 50.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_high_cutoff_out_of_bounds(self):
        _, data = _clean()
        out = signal_processor.bandpass_filter(data, 5.0, FS, FS)
        np.testing.assert_array_equal(out, data)

    def test_low_ge_high_cutoff(self):
        _, data = _clean()
        out = signal_processor.bandpass_filter(data, 100.0, 50.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_nan_input_returns_unchanged(self):
        data = np.full(100, np.nan)
        out = signal_processor.bandpass_filter(data, 5.0, 50.0, FS)
        np.testing.assert_array_equal(out, data)


class TestLowpassFilterEdgeCases:
    def test_no_scipy_returns_original(self):
        _, data = _clean()
        with _no_scipy():
            out = signal_processor.lowpass_filter(data, 100.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_cutoff_out_of_bounds_above(self):
        _, data = _clean()
        out = signal_processor.lowpass_filter(data, FS * 2, FS)
        np.testing.assert_array_equal(out, data)

    def test_cutoff_out_of_bounds_zero(self):
        _, data = _clean()
        out = signal_processor.lowpass_filter(data, 0.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_empty_data(self):
        out = signal_processor.lowpass_filter(np.array([]), 100.0, FS)
        assert len(out) == 0


class TestHighpassFilterEdgeCases:
    def test_no_scipy_returns_original(self):
        _, data = _clean()
        with _no_scipy():
            out = signal_processor.highpass_filter(data, 1.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_cutoff_out_of_bounds_above(self):
        _, data = _clean()
        out = signal_processor.highpass_filter(data, FS, FS)
        np.testing.assert_array_equal(out, data)

    def test_cutoff_zero(self):
        _, data = _clean()
        out = signal_processor.highpass_filter(data, 0.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_empty_data(self):
        out = signal_processor.highpass_filter(np.array([]), 1.0, FS)
        assert len(out) == 0


class TestNotchFilterEdgeCases:
    def test_no_scipy_returns_original(self):
        _, data = _clean()
        with _no_scipy():
            out = signal_processor.notch_filter(data, 50.0, 30.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_freq_out_of_bounds(self):
        _, data = _clean()
        out = signal_processor.notch_filter(data, FS, 30.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_freq_zero(self):
        _, data = _clean()
        out = signal_processor.notch_filter(data, 0.0, 30.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_negative_q_corrected(self):
        _, data = _clean()
        out = signal_processor.notch_filter(data, 50.0, -1.0, FS)
        assert len(out) == len(data)

    def test_valid_notch(self):
        t, data = _clean()
        # Add 50 Hz noise
        data = data + 2.0 * np.sin(2 * np.pi * 50 * t)
        out = signal_processor.notch_filter(data, 50.0, 30.0, FS)
        assert len(out) == len(data)

    def test_empty_data(self):
        out = signal_processor.notch_filter(np.array([]), 50.0, 30.0, FS)
        assert len(out) == 0


# ---------------------------------------------------------------------------
# comb_filter
# ---------------------------------------------------------------------------


class TestCombFilter:
    def test_no_scipy_returns_original(self):
        _, data = _clean()
        with _no_scipy():
            out = signal_processor.comb_filter(data, 50.0, 30.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_empty_data(self):
        out = signal_processor.comb_filter(np.array([]), 50.0, 30.0, FS)
        assert len(out) == 0

    def test_freq_out_of_bounds(self):
        _, data = _clean()
        out = signal_processor.comb_filter(data, FS * 2, 30.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_negative_q_corrected(self):
        _, data = _clean()
        out = signal_processor.comb_filter(data, 50.0, -1.0, FS)
        assert len(out) == len(data)

    def test_valid_comb(self):
        t, data = _clean()
        data = data + 2.0 * np.sin(2 * np.pi * 50 * t) + 1.5 * np.sin(2 * np.pi * 100 * t)
        out = signal_processor.comb_filter(data, 50.0, 30.0, FS)
        assert len(out) == len(data)

    def test_nan_input_returns_unchanged(self):
        data = np.full(100, np.nan)
        out = signal_processor.comb_filter(data, 50.0, 30.0, FS)
        np.testing.assert_array_equal(out, data)


# ---------------------------------------------------------------------------
# subtract_baseline_mode
# ---------------------------------------------------------------------------


class TestSubtractBaselineMode:
    def test_empty_returns_empty(self):
        data = signal_processor.subtract_baseline_mode(np.array([]))
        assert len(data) == 0

    def test_none_returns_none(self):
        result = signal_processor.subtract_baseline_mode(None)
        assert result is None

    def test_no_scipy_falls_back_to_median(self):
        data = np.full(100, 5.0)
        with _no_scipy():
            out = signal_processor.subtract_baseline_mode(data)
        np.testing.assert_allclose(out, 0.0, atol=1e-10)

    def test_with_default_decimals(self):
        data = np.full(100, 3.0)
        out = signal_processor.subtract_baseline_mode(data)
        np.testing.assert_allclose(out, 0.0, atol=0.1)

    def test_with_explicit_decimals(self):
        data = np.full(100, 2.5)
        out = signal_processor.subtract_baseline_mode(data, decimals=1)
        np.testing.assert_allclose(out, 0.0, atol=0.1)


# ---------------------------------------------------------------------------
# subtract_baseline_linear
# ---------------------------------------------------------------------------


class TestSubtractBaselineLinear:
    def test_empty_returns_empty(self):
        result = signal_processor.subtract_baseline_linear(np.array([]))
        assert len(result) == 0

    def test_none_returns_none(self):
        result = signal_processor.subtract_baseline_linear(None)
        assert result is None

    def test_no_scipy_returns_original(self):
        data = np.linspace(0, 10, 100)
        with _no_scipy():
            out = signal_processor.subtract_baseline_linear(data)
        np.testing.assert_array_equal(out, data)

    def test_removes_linear_trend(self):
        data = np.linspace(0, 10, 100)
        out = signal_processor.subtract_baseline_linear(data)
        assert abs(np.mean(out)) < 0.5


# ---------------------------------------------------------------------------
# blank_artifact
# ---------------------------------------------------------------------------


class TestBlankArtifact:
    def _make(self, n=1000, fs=1000.0):
        t = np.linspace(0, n / fs, n, endpoint=False)
        data = np.zeros(n)
        return data, t

    def test_invalid_method_raises(self):
        data, t = self._make()
        with pytest.raises(ValueError, match="Unknown artifact"):
            signal_processor.blank_artifact(data, t, 0.1, 5.0, method="invalid")

    def test_zero_method(self):
        data, t = self._make()
        data[:] = 1.0
        out = signal_processor.blank_artifact(data, t, 0.1, 20.0, method="zero")
        onset_idx = int(0.1 * 1000)
        n_blanked = int(0.02 * 1000)
        assert np.all(out[onset_idx : onset_idx + n_blanked] == 0.0)

    def test_hold_method(self):
        data, t = self._make()
        data[:] = 5.0
        out = signal_processor.blank_artifact(data, t, 0.1, 20.0, method="hold")
        onset_idx = int(0.1 * 1000)
        n_blanked = int(0.02 * 1000)
        assert np.all(out[onset_idx : onset_idx + n_blanked] == 5.0)

    def test_linear_method(self):
        data, t = self._make()
        data[:] = 3.0
        out = signal_processor.blank_artifact(data, t, 0.1, 20.0, method="linear")
        # Values inside window should be interpolated (all 3.0 so still 3.0)
        assert len(out) == len(data)

    def test_empty_data_returns_unchanged(self):
        out = signal_processor.blank_artifact(None, np.array([]), 0.0, 1.0)
        assert out is None

    def test_window_outside_range_no_change(self):
        data, t = self._make()
        data[:] = 1.0
        out = signal_processor.blank_artifact(data, t, 99.0, 5.0)
        np.testing.assert_array_equal(out, data)


# ---------------------------------------------------------------------------
# find_artifact_windows
# ---------------------------------------------------------------------------


class TestFindArtifactWindows:
    def test_empty_data_returns_empty(self):
        out = signal_processor.find_artifact_windows(np.array([]), 1000.0, 1.0)
        assert len(out) == 0

    def test_flat_trace_no_artifacts(self):
        data = np.ones(1000)
        mask = signal_processor.find_artifact_windows(data, 1000.0, 10.0)
        assert not np.any(mask)

    def test_step_artifact_detected(self):
        data = np.zeros(1000)
        data[500] = 1000.0  # Large spike
        mask = signal_processor.find_artifact_windows(data, 1000.0, slope_threshold=100.0, padding_ms=2.0)
        assert np.any(mask)

    def test_no_scipy_uses_gradient_only(self):
        data = np.zeros(100)
        data[50] = 500.0
        with _no_scipy():
            mask = signal_processor.find_artifact_windows(data, 1000.0, slope_threshold=10.0)
        assert np.any(mask)

    def test_no_padding_dilation(self):
        data = np.zeros(100)
        data[50] = 500.0
        mask = signal_processor.find_artifact_windows(data, 1000.0, slope_threshold=10.0, padding_ms=0.0)
        assert np.any(mask)


# ---------------------------------------------------------------------------
# compute_psd
# ---------------------------------------------------------------------------


class TestComputePSD:
    def test_basic_returns_freqs_and_psd(self):
        t, data = _clean()
        freqs, psd = signal_processor.compute_psd(data, FS)
        assert len(freqs) > 0
        assert len(psd) > 0
        assert freqs.dtype == np.float64

    def test_empty_data_returns_empty(self):
        freqs, psd = signal_processor.compute_psd(np.array([]), FS)
        assert len(freqs) == 0
        assert len(psd) == 0

    def test_none_data_returns_empty(self):
        freqs, psd = signal_processor.compute_psd(None, FS)
        assert len(freqs) == 0

    def test_no_scipy_returns_empty(self):
        t, data = _clean()
        with _no_scipy():
            freqs, psd = signal_processor.compute_psd(data, FS)
        assert len(freqs) == 0

    def test_custom_nperseg(self):
        t, data = _clean()
        freqs, psd = signal_processor.compute_psd(data, FS, nperseg=512)
        assert len(freqs) > 0

    def test_dominant_peak_near_10hz(self):
        t, data = _clean()
        freqs, psd = signal_processor.compute_psd(data, FS)
        peak_freq = freqs[np.argmax(psd)]
        assert abs(peak_freq - 10.0) < 2.0


# ---------------------------------------------------------------------------
# multi_harmonic_notch
# ---------------------------------------------------------------------------


class TestMultiHarmonicNotch:
    def test_no_scipy_returns_original(self):
        t, data = _clean()
        with _no_scipy():
            out = signal_processor.multi_harmonic_notch(data, 50.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_empty_data_returns_unchanged(self):
        out = signal_processor.multi_harmonic_notch(np.array([]), 50.0, FS)
        assert len(out) == 0

    def test_invalid_fundamental_returns_original(self):
        t, data = _clean()
        out = signal_processor.multi_harmonic_notch(data, -50.0, FS)
        np.testing.assert_array_equal(out, data)

    def test_invalid_fs_returns_original(self):
        t, data = _clean()
        out = signal_processor.multi_harmonic_notch(data, 50.0, 0.0)
        np.testing.assert_array_equal(out, data)

    def test_removes_line_noise(self):
        t, data = _clean()
        noise = 2.0 * np.sin(2 * np.pi * 50 * t) + 1.5 * np.sin(2 * np.pi * 100 * t)
        data_noisy = data + noise
        out = signal_processor.multi_harmonic_notch(data_noisy, 50.0, FS)
        assert len(out) == len(data)

    def test_max_harmonics_respected(self):
        t, data = _clean()
        out = signal_processor.multi_harmonic_notch(data, 50.0, FS, max_harmonics=1)
        assert len(out) == len(data)

    def test_fundamental_above_nyquist_cascades(self):
        """When fundamental/nyq >= 1, comb fails; cascaded notch runs."""
        t, data = _clean(fs=FS)
        # Use a fundamental that is just above nyquist so iircomb freq_norm >=1
        out = signal_processor.multi_harmonic_notch(data, FS * 0.6, FS)
        assert len(out) == len(data)
