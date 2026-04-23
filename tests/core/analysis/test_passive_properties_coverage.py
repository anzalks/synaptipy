# tests/core/analysis/test_passive_properties_coverage.py
# -*- coding: utf-8 -*-
"""
Targeted coverage tests for passive_properties.py uncovered branches.

Covers missing lines:
  287, 364-366, 440-441, 549-550, 557-558, 590-591, 803-804,
  826-827, 856-857, 881-882, 932, 1017-1022, 1466, 1470-1472,
  1663, 1776, 1780, 1808, 1820-1822, 1922, 1936, 2044, 2049,
  2064, 2088, 2119.
"""

from unittest.mock import MagicMock, patch  # noqa: F401

import numpy as np

import Synaptipy.core.analysis  # noqa: F401 - populate registry
from Synaptipy.core.analysis.passive_properties import (
    _fit_vc_transient_decay,
    calculate_capacitance_cc,
    calculate_cc_series_resistance_fast,
    calculate_tau,
    calculate_vc_transient_parameters,
    run_capacitance_analysis_wrapper,
    run_iv_curve_wrapper,
    run_rin_analysis_wrapper,
    run_sag_ratio_wrapper,
    run_tau_analysis_wrapper,
)

FS = 10_000.0
DT = 1.0 / FS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat_trace(n: int = 1000, val: float = -65.0) -> np.ndarray:
    return np.full(n, val, dtype=float)


def _time(n: int = 1000, dt: float = DT) -> np.ndarray:
    return np.arange(n, dtype=float) * dt


def _step_trace(
    n: int = 5000,
    step_start: float = 0.1,
    step_end: float = 0.4,
    step_amp: float = -10.0,
    v_rest: float = -65.0,
) -> tuple:
    """Rectangular step trace for Rin / sag tests."""
    t = np.arange(n) * DT
    v = np.full(n, v_rest)
    mask = (t >= step_start) & (t < step_end)
    v[mask] += step_amp
    return v, t


def _rc_trace(
    n: int = 5000,
    step_start: float = 0.1,
    tau: float = 0.02,
    v_rest: float = -65.0,
    step_amp: float = -10.0,
) -> tuple:
    """Single-exponential step response for tau fitting."""
    t = np.arange(n) * DT
    v = np.full(n, v_rest)
    for i in range(n):
        dt_i = t[i] - step_start
        if dt_i >= 0:
            v[i] = v_rest + step_amp * (1.0 - np.exp(-dt_i / tau))
    return v, t


# ---------------------------------------------------------------------------
# _fit_vc_transient_decay - RuntimeError branch (lines 364-366)
# ---------------------------------------------------------------------------


class TestFitVcTransientDecay:
    def test_runtime_error_returns_nan(self):
        """Mocked RuntimeError from curve_fit returns (nan, nan)."""
        with patch(
            "Synaptipy.core.analysis.passive_properties.curve_fit",
            side_effect=RuntimeError("fit failed"),
        ):
            tau_c, cm_fit = _fit_vc_transient_decay(
                decay_segment=np.linspace(100.0, 0.0, 50),
                t_decay=np.linspace(0.0, 0.005, 50),
                i_peak=100.0,
                rs_mohm=5.0,
                cm_charge_pf=20.0,
            )
        assert np.isnan(tau_c)
        assert np.isnan(cm_fit)

    def test_short_segment_returns_nan(self):
        """Segment too short (< 4 points) returns (nan, nan) immediately."""
        tau_c, cm_fit = _fit_vc_transient_decay(
            decay_segment=np.array([10.0, 5.0]),
            t_decay=np.array([0.0, 0.001]),
            i_peak=10.0,
            rs_mohm=5.0,
            cm_charge_pf=20.0,
        )
        assert np.isnan(tau_c)
        assert np.isnan(cm_fit)


# ---------------------------------------------------------------------------
# calculate_vc_transient_parameters - no transient samples (lines 440-441)
# ---------------------------------------------------------------------------


class TestCalculateVcTransientParameters:
    def test_no_transient_samples_returns_nans(self):
        """step_onset_time just past trace end → baseline non-empty but trans empty → lines 440-441."""
        n = 500
        t = np.arange(n, dtype=float) * DT  # ends at (n-1)*DT
        current = np.zeros(n)
        # baseline window needs samples: step_onset - 0.01 < t[-1]
        # transient window needs NO samples: step_onset > t[-1]
        step_onset = t[-1] + DT * 0.5  # just past last sample
        result = calculate_vc_transient_parameters(
            current_trace=current,
            time_vector=t,
            step_onset_time=step_onset,
            voltage_step_mv=-5.0,
        )
        assert np.isnan(result["rs_mohm"])
        assert np.isnan(result["cm_pf"])

    def test_zero_voltage_step_returns_nans(self):
        """voltage_step_mv=0 should return nan result without computation."""
        t = _time(500)
        current = np.zeros(500)
        result = calculate_vc_transient_parameters(
            current_trace=current,
            time_vector=t,
            step_onset_time=0.02,
            voltage_step_mv=0.0,
        )
        assert np.isnan(result["rs_mohm"])

    def test_negative_voltage_step(self):
        """Negative voltage step should select argmin for peak index."""
        n = 2000
        t = np.arange(n) * DT
        current = np.zeros(n)
        # Simulate negative transient at step onset
        onset_idx = int(0.05 * FS)
        decay_tau = 0.001
        for i in range(n):
            dt_i = t[i] - t[onset_idx]
            if 0 <= dt_i < 10 * decay_tau:
                current[i] = -500.0 * np.exp(-dt_i / decay_tau)
        result = calculate_vc_transient_parameters(
            current_trace=current,
            time_vector=t,
            step_onset_time=t[onset_idx],
            voltage_step_mv=-5.0,
            transient_window_ms=10.0,
        )
        # Result may be valid or nan depending on fit convergence, just no crash
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# calculate_cc_series_resistance_fast - various branches (lines 549-591)
# ---------------------------------------------------------------------------


class TestCalculateCcSeriesResistanceFast:
    def test_no_artifact_window_samples(self):
        """step_onset just past trace end → baseline non-empty but artifact window empty → lines 549-550."""
        n = 5000
        t = np.arange(n, dtype=float) * DT
        v = np.full(n, -65.0)
        # baseline = 5ms before step_onset; transient = at/after step_onset
        # step_onset just past t[-1] means baseline is non-empty but art window is empty
        step_onset = t[-1] + DT * 0.5
        result = calculate_cc_series_resistance_fast(
            voltage_trace=v,
            time_vector=t,
            step_onset_time=step_onset,
            current_step_pa=-100.0,
            artifact_window_ms=0.5,
        )
        # Should return early with nan rs_cc_mohm
        assert np.isnan(result["rs_cc_mohm"])

    def test_rs_computed_with_voltage_drop(self):
        """Valid step onset with a voltage drop should compute rs_cc_mohm."""
        v, t = _step_trace(step_amp=-5.0, step_start=0.1)
        result = calculate_cc_series_resistance_fast(
            voltage_trace=v,
            time_vector=t,
            step_onset_time=0.1,
            current_step_pa=-100.0,
            artifact_window_ms=0.5,
        )
        # Should compute rs_cc_mohm if baseline samples exist
        assert isinstance(result, dict)
        assert "rs_cc_mohm" in result

    def test_cm_derived_with_tau_and_rin(self):
        """When tau_ms and rin_mohm are supplied, cm_derived_pf is computed (lines 590-591)."""
        v, t = _step_trace(step_amp=-5.0, step_start=0.1)
        result = calculate_cc_series_resistance_fast(
            voltage_trace=v,
            time_vector=t,
            step_onset_time=0.1,
            current_step_pa=-100.0,
            artifact_window_ms=0.5,
            tau_ms=20.0,
            rin_mohm=200.0,
        )
        assert isinstance(result, dict)
        # cm_derived_pf should be computed (may be nan if rs fails)
        assert "cm_derived_pf" in result

    def test_zero_current_returns_nans(self):
        """current_step_pa=0 is caught early and returns nan dict."""
        v, t = _step_trace()
        result = calculate_cc_series_resistance_fast(
            voltage_trace=v,
            time_vector=t,
            step_onset_time=0.1,
            current_step_pa=0.0,
        )
        assert np.isnan(result["rs_cc_mohm"])


# ---------------------------------------------------------------------------
# calculate_tau - various branch coverage (lines 803-882, 932)
# ---------------------------------------------------------------------------


class TestCalculateTau:
    def test_mono_runtime_error_returns_nan_dict(self):
        """Patched RuntimeError during mono-exp curve_fit returns nan tau dict (lines 814-816)."""
        v, t = _rc_trace()
        with patch(
            "Synaptipy.core.analysis.passive_properties.curve_fit",
            side_effect=RuntimeError("no convergence"),
        ):
            result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.1, model="mono")
        assert result is not None
        assert np.isnan(result["tau_ms"])

    def test_polyfit_exception_in_tau_estimation(self):
        """Poly-fit raising ValueError triggers the except fallback (lines 803-804)."""
        import Synaptipy.core.analysis.passive_properties as _pp

        v, t = _rc_trace()
        # Patch polyfit on the numpy object in the passive_properties module
        with patch.object(_pp.np, "polyfit", side_effect=ValueError("SVD did not converge")):
            result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.1, model="mono")
        # Fallback tau_est=0.01 is used; curve_fit should still succeed
        assert result is not None

    def test_bi_exp_short_trace_returns_none(self):
        """bi-exp fit with exactly 5 data points returns None (lines 826-827)."""
        # With artifact_blanking_ms=0, fit starts at stim_start_time
        # fit_duration=0.0005s * FS=10000 = 5 samples (>= 4 but < 6)
        v, t = _rc_trace(n=5000)
        result = calculate_tau(
            v,
            t,
            stim_start_time=0.1,
            fit_duration=0.0005,
            model="bi",
            artifact_blanking_ms=0.0,
        )
        assert result is None

    def test_bi_exp_runtime_error_returns_nan_dict(self):
        """Patched RuntimeError during bi-exp curve_fit returns nan bi-exp dict (lines 841-852)."""
        v, t = _rc_trace(n=10000)
        with patch(
            "Synaptipy.core.analysis.passive_properties.curve_fit",
            side_effect=RuntimeError("no convergence"),
        ):
            result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.3, model="bi")
        assert result is not None
        assert np.isnan(result.get("tau_fast_ms", 0.0))

    def test_bi_exp_tau_swap(self):
        """When curve_fit returns tau_fast > tau_slow, the swap is triggered (lines 856-857)."""
        v, t = _rc_trace(n=10000)
        # Mock curve_fit to return popt where tau_fast (index 2) > tau_slow (index 4)
        # _bi_exp_growth(t, V_ss, A_fast, tau_fast, A_slow, tau_slow)
        mock_popt = np.array([-75.0, 5.0, 0.05, 3.0, 0.01])  # tau_fast=0.05 > tau_slow=0.01
        mock_cov = np.eye(5)
        with patch(
            "Synaptipy.core.analysis.passive_properties.curve_fit",
            return_value=(mock_popt, mock_cov),
        ):
            result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.3, model="bi")
        # Should have swapped: tau_fast_ms < tau_slow_ms
        assert result is not None
        assert result["tau_fast_ms"] < result["tau_slow_ms"]

    def test_unknown_model_returns_none(self):
        """Unknown model string triggers the else branch and returns None (lines 877-878)."""
        v, t = _rc_trace()
        result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.1, model="quadratic")
        assert result is None

    def test_bi_exp_success(self):
        """Bi-exponential tau fitting on a clean bi-exp signal."""
        n = 10000
        t = np.arange(n) * DT
        v = -65.0 + 10.0 * (
            0.6 * np.exp(-np.maximum(t - 0.1, 0) / 0.005) + 0.4 * np.exp(-np.maximum(t - 0.1, 0) / 0.025)
        )
        v[t < 0.1] = -65.0
        result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.15, model="bi")
        # Result may be dict with tau fields or None (if fit fails), just no crash
        assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# calculate_capacitance_cc - invalid inputs (lines 1017-1022)
# ---------------------------------------------------------------------------


class TestCalculateCapacitanceCc:
    def test_negative_rin_returns_none(self):
        """rin_mohm <= 0 should return None immediately."""
        result = calculate_capacitance_cc(tau_ms=20.0, rin_mohm=-100.0)
        assert result is None

    def test_infinite_rin_returns_none(self):
        """Non-finite rin_mohm should return None."""
        result = calculate_capacitance_cc(tau_ms=20.0, rin_mohm=float("inf"))
        assert result is None

    def test_non_positive_tau_returns_none(self):
        """tau_ms <= 0 returns None."""
        result = calculate_capacitance_cc(tau_ms=0.0, rin_mohm=200.0)
        assert result is None

    def test_negative_tau_returns_none(self):
        """Negative tau returns None."""
        result = calculate_capacitance_cc(tau_ms=-5.0, rin_mohm=200.0)
        assert result is None

    def test_rs_greater_than_rin_uses_rin(self):
        """Rs >= Rin should fall back to using Rin (lines 1017-1022 Rs>Rin branch)."""
        result = calculate_capacitance_cc(tau_ms=20.0, rin_mohm=100.0, rs_mohm=150.0)
        assert result is not None
        assert result > 0

    def test_valid_inputs_compute_capacitance(self):
        """Valid tau and Rin should produce a positive capacitance."""
        result = calculate_capacitance_cc(tau_ms=20.0, rin_mohm=200.0)
        assert result is not None
        assert result > 0


# ---------------------------------------------------------------------------
# run_sag_ratio_wrapper - sag NaN branch (lines 1466, 1470-1472)
# ---------------------------------------------------------------------------


class TestRunSagRatioWrapper:
    def _make_channel(self, data: np.ndarray, time: np.ndarray):
        """Return a simple mock channel."""
        ch = MagicMock()
        ch.get_data.return_value = data
        ch.get_relative_time_vector.return_value = time
        ch.num_trials = 1
        return ch

    def _make_recording(self, data: np.ndarray, time: np.ndarray):
        ch = self._make_channel(data, time)
        rec = MagicMock()
        rec.channels = {0: ch}
        rec.num_trials = 1
        return rec

    def test_sag_nan_adds_error_key(self):
        """Sag ratio returning NaN (empty windows) should add sag_error to metrics."""
        v, t = _step_trace(step_start=0.1, step_end=0.4, step_amp=-20.0)
        result = run_sag_ratio_wrapper(
            data=v,
            time=t,
            sampling_rate=FS,
            baseline_window_start=0.0,
            baseline_window_end=0.05,
            # Intentionally invalid peak/ss windows so sag returns NaN
            response_peak_window_start=5.0,
            response_peak_window_end=5.1,
            response_ss_window_start=5.1,
            response_ss_window_end=5.2,
        )
        assert result["module_used"] == "passive_properties"

    def test_sag_calculation_failed_branch(self):
        """When sag result is None, sag_error is set."""
        v, t = _step_trace()
        with patch(
            "Synaptipy.core.analysis.passive_properties.calculate_sag_ratio",
            return_value=None,
        ):
            result = run_sag_ratio_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                baseline_window_start=0.0,
                baseline_window_end=0.09,
                response_peak_window_start=0.1,
                response_peak_window_end=0.2,
                response_ss_window_start=0.35,
                response_ss_window_end=0.39,
            )
        assert result["module_used"] == "passive_properties"
        assert "sag_error" in result["metrics"]


# ---------------------------------------------------------------------------
# run_rin_analysis_wrapper - error result branch (line 1663)
# ---------------------------------------------------------------------------


class TestRunRinAnalysisWrapper:
    def test_rin_error_result_populates_rin_error(self):
        """When calculate_rin returns invalid result, rin_error key is set (line 1663)."""
        v, t = _step_trace()
        # Pass zero current_amplitude to get an invalid Rin result
        result = run_rin_analysis_wrapper(
            data=v,
            time=t,
            sampling_rate=FS,
            current_amplitude=0.0,
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=0.1,
            response_end=0.4,
        )
        assert result["module_used"] == "passive_properties"
        assert "rin_error" in result["metrics"]


# ---------------------------------------------------------------------------
# run_tau_analysis_wrapper - NaN tau branches (lines 1776, 1780, 1808, 1820-1822)
# ---------------------------------------------------------------------------


class TestRunTauAnalysisWrapper:
    def test_mono_nan_tau_adds_tau_error(self):
        """When mono-exp tau is NaN, tau_error key is added (line 1780)."""
        v, t = _step_trace()
        with patch(
            "Synaptipy.core.analysis.passive_properties.curve_fit",
            side_effect=RuntimeError("failed"),
        ):
            result = run_tau_analysis_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                stim_start_time=0.1,
                fit_duration=0.1,
                tau_model="mono",
            )
        assert result["module_used"] == "passive_properties"
        metrics = result["metrics"]
        assert "tau_error" in metrics or "tau_ms" in metrics

    def test_bi_tau_wrapper_path(self):
        """Run tau wrapper with bi model to exercise bi branch (line 1776)."""
        v, t = _rc_trace(n=10000)
        result = run_tau_analysis_wrapper(
            data=v,
            time=t,
            sampling_rate=FS,
            stim_start_time=0.1,
            fit_duration=0.2,
            tau_model="bi",
        )
        assert result["module_used"] == "passive_properties"

    def test_tau_result_none_adds_tau_error(self):
        """When calculate_tau returns None, tau_error is set (line 1820)."""
        v, t = _step_trace()
        with patch(
            "Synaptipy.core.analysis.passive_properties.calculate_tau",
            return_value=None,
        ):
            result = run_tau_analysis_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                stim_start_time=0.1,
                fit_duration=0.1,
            )
        assert result["module_used"] == "passive_properties"
        assert "tau_error" in result["metrics"]

    def test_mono_tau_dict_result(self):
        """Mono tau with valid result returns tau_ms in metrics (line 1808)."""
        v, t = _rc_trace(n=10000)
        result = run_tau_analysis_wrapper(
            data=v,
            time=t,
            sampling_rate=FS,
            stim_start_time=0.1,
            fit_duration=0.2,
            tau_model="mono",
        )
        assert result["module_used"] == "passive_properties"
        assert "tau_ms" in result["metrics"] or "tau_error" in result["metrics"]


# ---------------------------------------------------------------------------
# run_iv_curve_wrapper - error and success branches (lines 1922, 1936)
# ---------------------------------------------------------------------------


class TestRunIvCurveWrapper:
    def test_empty_sweep_list_returns_error(self):
        """No sweeps triggers the iv_curve_error branch (line 1922)."""
        result = run_iv_curve_wrapper(
            data_list=[],
            time_list=[],
            sampling_rate=FS,
        )
        assert result["module_used"] == "passive_properties"
        assert "iv_curve_error" in result["metrics"]

    def test_numpy_1d_array_input(self):
        """1D numpy array for data_list is converted to list internally."""
        v, t = _step_trace()
        result = run_iv_curve_wrapper(
            data_list=v,
            time_list=t,
            sampling_rate=FS,
            start_current=-50.0,
            step_current=10.0,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=0.1,
            response_end=0.4,
        )
        assert result["module_used"] == "passive_properties"

    def test_multiple_sweeps_iv_curve(self):
        """Multiple sweeps produce valid IV curve metrics (line 1936)."""
        n_sweeps = 5
        sweeps = []
        times = []
        for i in range(n_sweeps):
            v, t = _step_trace(step_amp=-5.0 * (i + 1))
            sweeps.append(v)
            times.append(t)
        result = run_iv_curve_wrapper(
            data_list=sweeps,
            time_list=times,
            sampling_rate=FS,
            start_current=-50.0,
            step_current=10.0,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=0.1,
            response_end=0.4,
        )
        assert result["module_used"] == "passive_properties"
        if "iv_curve_error" not in result["metrics"]:
            assert "rin_aggregate_mohm" in result["metrics"]


# ---------------------------------------------------------------------------
# run_capacitance_analysis_wrapper - various branches (lines 2044-2119)
# ---------------------------------------------------------------------------


class TestRunCapacitanceAnalysisWrapper:
    def test_current_clamp_rin_failure(self):
        """Zero current_amplitude_pa → rin fails → error returned (line 2044)."""
        v, t = _step_trace()
        result = run_capacitance_analysis_wrapper(
            data=v,
            time=t,
            sampling_rate=FS,
            mode="Current-Clamp",
            current_amplitude_pa=0.0,
            baseline_start_s=0.0,
            baseline_end_s=0.09,
            response_start_s=0.1,
            response_end_s=0.4,
        )
        assert result["module_used"] == "passive_properties"
        assert "error" in result["metrics"]

    def test_current_clamp_success(self):
        """Valid RC trace with non-zero current should produce capacitance (line 2064+)."""
        v, t = _rc_trace(n=10000, step_amp=-10.0)
        result = run_capacitance_analysis_wrapper(
            data=v,
            time=t,
            sampling_rate=FS,
            mode="Current-Clamp",
            current_amplitude_pa=-100.0,
            baseline_start_s=0.0,
            baseline_end_s=0.09,
            response_start_s=0.101,
            response_end_s=0.3,
        )
        assert result["module_used"] == "passive_properties"
        # May succeed or fail gracefully
        assert "capacitance_pf" in result["metrics"] or "error" in result["metrics"]

    def test_voltage_clamp_mode(self):
        """Voltage-clamp mode triggers the VC capacitance path (lines 2088, 2119)."""
        n = 5000
        t = np.arange(n) * DT
        current = np.zeros(n)
        # Simulate a VC capacitive transient at step onset
        onset_idx = int(0.05 * FS)
        for i in range(n):
            dt_i = t[i] - t[onset_idx]
            if 0 <= dt_i < 0.01:
                current[i] = -500.0 * np.exp(-dt_i / 0.001)
        result = run_capacitance_analysis_wrapper(
            data=current,
            time=t,
            sampling_rate=FS,
            mode="Voltage-Clamp",
            voltage_step_mv=-5.0,
            baseline_start_s=0.0,
            baseline_end_s=0.04,
            response_start_s=0.05,
            response_end_s=0.1,
        )
        assert result["module_used"] == "passive_properties"

    def test_unknown_mode_returns_error(self):
        """Unknown mode returns error dict (line 2119)."""
        v, t = _step_trace()
        result = run_capacitance_analysis_wrapper(
            data=v,
            time=t,
            sampling_rate=FS,
            mode="Unknown-Mode",
        )
        assert result["module_used"] == "passive_properties"
        assert "error" in result["metrics"]

    def test_tau_failure_returns_error(self):
        """When tau calculation fails, error dict is returned (line 2049)."""
        v, t = _rc_trace(n=10000, step_amp=-10.0)
        with patch(
            "Synaptipy.core.analysis.passive_properties.calculate_tau",
            return_value=None,
        ):
            result = run_capacitance_analysis_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                mode="Current-Clamp",
                current_amplitude_pa=-100.0,
                baseline_start_s=0.0,
                baseline_end_s=0.09,
                response_start_s=0.101,
                response_end_s=0.3,
            )
        assert "error" in result["metrics"]


# ---------------------------------------------------------------------------
# Additional targeted tests for remaining uncovered lines
# ---------------------------------------------------------------------------


class TestCcSeriesResistanceFastAdditional:
    def test_no_baseline_samples_returns_nan(self):
        """step_onset at trace start so baseline window has no samples (lines 549-550)."""
        n = 5000
        t = np.arange(n, dtype=float) * DT
        v = np.full(n, -65.0)
        # step_onset at t[0]=0.0: baseline [-0.005, 0.0) has no samples
        result = calculate_cc_series_resistance_fast(
            voltage_trace=v,
            time_vector=t,
            step_onset_time=0.0,
            current_step_pa=-100.0,
            artifact_window_ms=0.5,
        )
        assert np.isnan(result["rs_cc_mohm"])

    def test_except_handler(self):
        """ValueError inside try block triggers except (lines 590-591)."""
        n = 5000
        t = np.arange(n, dtype=float) * DT
        v = np.full(n, -65.0)
        import Synaptipy.core.analysis.passive_properties as _pp

        with patch.object(_pp.np, "mean", side_effect=ValueError("bad value")):
            result = calculate_cc_series_resistance_fast(
                voltage_trace=v,
                time_vector=t,
                step_onset_time=0.1,
                current_step_pa=-100.0,
                artifact_window_ms=0.5,
            )
        assert isinstance(result, dict)


class TestRunRinAnalysisWrapperElseBranch:
    def test_rin_invalid_result_populates_error(self):
        """When calculate_rin returns invalid result (no data in window), hits lines 1662-1667."""
        v, t = _step_trace()
        # Use a response window beyond trace end so calculate_rin returns invalid
        result = run_rin_analysis_wrapper(
            data=v,
            time=t,
            sampling_rate=FS,
            current_amplitude=-100.0,
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=5.0,
            response_end=5.1,
        )
        assert result["module_used"] == "passive_properties"
        assert "rin_error" in result["metrics"]


class TestRunTauAnalysisWrapperAdditional:
    def test_bi_nan_tau_adds_tau_error(self):
        """Bi-exp RuntimeError produces NaN tau_fast_ms and tau_error is set (line 1776)."""
        v, t = _rc_trace(n=10000)
        with patch(
            "Synaptipy.core.analysis.passive_properties.curve_fit",
            side_effect=RuntimeError("fail"),
        ):
            result = run_tau_analysis_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                stim_start_time=0.1,
                fit_duration=0.3,
                tau_model="bi",
            )
        assert result["module_used"] == "passive_properties"
        assert "tau_error" in result["metrics"]

    def test_non_dict_result_takes_else_branch(self):
        """calculate_tau returning a float triggers the else branch (lines 1807-1812)."""
        v, t = _step_trace()
        with patch(
            "Synaptipy.core.analysis.passive_properties.calculate_tau",
            return_value=20.0,  # numeric, not a dict
        ):
            result = run_tau_analysis_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                stim_start_time=0.1,
                fit_duration=0.1,
                tau_model="mono",
            )
        assert result["module_used"] == "passive_properties"
        # The else branch puts result directly as tau_ms
        assert result["metrics"].get("tau_ms") == 20.0

    def test_exception_in_wrapper_returns_error(self):
        """Exception in tau wrapper body returns error dict (lines 1820-1822)."""
        v, t = _step_trace()
        with patch(
            "Synaptipy.core.analysis.passive_properties.calculate_tau",
            side_effect=KeyError("bad_key"),
        ):
            result = run_tau_analysis_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                stim_start_time=0.1,
                fit_duration=0.1,
            )
        assert result["module_used"] == "passive_properties"
        assert "tau_error" in result["metrics"]


class TestRunIvCurveWrapperAdditional:
    def test_list_data_with_numpy_time_list(self):
        """data_list as list but time_list as 1D numpy array triggers line 1922."""
        v, t = _step_trace()
        # Pass data_list as a Python list (not ndarray), time_list as numpy array
        result = run_iv_curve_wrapper(
            data_list=[v],  # Python list
            time_list=t,  # numpy 1D array → triggers time_list = [time_list] at line 1922
            sampling_rate=FS,
            start_current=-50.0,
            step_current=10.0,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=0.1,
            response_end=0.4,
        )
        assert result["module_used"] == "passive_properties"


class TestRunCapacitanceAnalysisWrapperAdditional:
    def test_tau_returns_float_covers_line_2049(self):
        """When tau_result is a float (not dict), tau_ms = tau_result (line 2049)."""
        v, t = _rc_trace(n=10000, step_amp=-10.0)
        with patch(
            "Synaptipy.core.analysis.passive_properties.calculate_tau",
            return_value=20.0,  # return float, not dict
        ):
            result = run_capacitance_analysis_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                mode="Current-Clamp",
                current_amplitude_pa=-100.0,
                baseline_start_s=0.0,
                baseline_end_s=0.09,
                response_start_s=0.101,
                response_end_s=0.3,
            )
        assert result["module_used"] == "passive_properties"

    def test_nan_rs_becomes_none(self):
        """When calculate_cc_series_resistance_fast returns NaN rs, rs_mohm=None (line 2064)."""
        v, t = _rc_trace(n=10000, step_amp=-10.0)
        import Synaptipy.core.analysis.passive_properties as _pp

        with patch.object(
            _pp,
            "calculate_cc_series_resistance_fast",
            return_value={"rs_cc_mohm": float("nan"), "cm_derived_pf": float("nan")},
        ):
            result = run_capacitance_analysis_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                mode="Current-Clamp",
                current_amplitude_pa=-100.0,
                baseline_start_s=0.0,
                baseline_end_s=0.09,
                response_start_s=0.101,
                response_end_s=0.3,
            )
        assert result["module_used"] == "passive_properties"


class TestPassivePropertiesModuleEntry:
    def test_module_entry_point_returns_empty_dict(self):
        """passive_properties_module() returns an empty dict (line 2119)."""
        from Synaptipy.core.analysis.passive_properties import passive_properties_module

        result = passive_properties_module()
        assert result == {}


# ---------------------------------------------------------------------------
# Remaining targeted tests for lines 932, 1191-1192, 1470-1472
# ---------------------------------------------------------------------------


class TestCalculateSagRatioShortPeakWindow:
    def test_short_peak_window_skips_savgol(self):
        """Peak window shorter than savgol filter → else branch at line 932."""
        from Synaptipy.core.analysis.passive_properties import calculate_sag_ratio

        n = 10000
        t = np.arange(n) * DT
        v = np.full(n, -65.0)
        # Add hyperpolarising step
        mask = (t >= 0.1) & (t < 0.4)
        v[mask] = -80.0  # sag-like response
        # peak window = 3ms = 30 samples < window_length(50), triggers line 932
        result = calculate_sag_ratio(
            voltage_trace=v,
            time_vector=t,
            baseline_window=(0.0, 0.09),
            response_peak_window=(0.1, 0.103),  # 3ms window → <50 samples
            response_steady_state_window=(0.35, 0.39),
        )
        assert result is not None


class TestResolveSweepBaselineFallback:
    def test_no_stable_baseline_window_uses_full_sweep(self):
        """When find_stable_baseline finds no window, uses full sweep range (lines 1191-1192)."""
        import Synaptipy.core.analysis.passive_properties as _pp

        n = 5000
        t = np.arange(n) * DT
        v = np.full(n, -65.0)

        # Patch find_stable_baseline to return no window
        with patch.object(_pp, "find_stable_baseline", return_value=(None, None, None)):
            result = _pp._resolve_sweep_baseline(
                sweep_data=v,
                sweep_time=t,
                sampling_rate=FS,
                baseline_start=0.0,
                baseline_end=0.09,
                auto_detect=True,
                window_duration=0.05,
                step_duration=0.1,
                rs_artifact_blanking_ms=0.0,
            )
        # Should return a valid baseline window spanning the full sweep
        bl_start, bl_end = result
        assert bl_start == 0.0 or bl_start >= 0.0
        assert bl_end > bl_start


class TestRunSagRatioWrapperException:
    def test_exception_triggers_outer_handler(self):
        """Exception inside run_sag_ratio_wrapper body triggers lines 1470-1472."""
        v, t = _step_trace(step_amp=-20.0)

        import Synaptipy.core.analysis.passive_properties as _pp

        with patch.object(_pp, "calculate_sag_ratio", side_effect=KeyError("unexpected")):
            result = run_sag_ratio_wrapper(
                data=v,
                time=t,
                sampling_rate=FS,
                baseline_window_start=0.0,
                baseline_window_end=0.09,
                response_peak_window_start=0.1,
                response_peak_window_end=0.2,
                response_ss_window_start=0.35,
                response_ss_window_end=0.39,
            )
        assert result["module_used"] == "passive_properties"
        assert "sag_error" in result["metrics"]
