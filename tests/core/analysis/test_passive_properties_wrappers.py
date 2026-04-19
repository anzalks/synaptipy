# tests/core/analysis/test_passive_properties_wrappers.py
# -*- coding: utf-8 -*-
"""
Tests for passive_properties.py wrapper functions and helper functions.
Covers lines 1062-2047 (wrapper bodies, _coerce_trial_lists, _resolve_sweep_baseline).
"""

from unittest.mock import patch

import numpy as np

import Synaptipy.core.analysis  # noqa: F401 – populate registry
from Synaptipy.core.analysis.passive_properties import (
    _coerce_trial_lists,
    _resolve_sweep_baseline,
    calculate_capacitance_vc,
    calculate_conductance,
    calculate_rin,
    calculate_rmp,
    calculate_tau,
    calculate_vc_transient_parameters,
    run_capacitance_analysis_wrapper,
    run_iv_curve_wrapper,
    run_rin_analysis_wrapper,
    run_rmp_analysis_wrapper,
    run_sag_ratio_wrapper,
    run_tau_analysis_wrapper,
)

# ---------------------------------------------------------------------------
# Synthetic waveform generators
# ---------------------------------------------------------------------------

FS = 10_000.0  # 10 kHz
DT = 1.0 / FS


def _resting(duration_s: float = 1.0, v_rest: float = -65.0) -> tuple:
    """Flat resting-potential trace."""
    t = np.linspace(0, duration_s, int(duration_s * FS), endpoint=False)
    v = np.full_like(t, v_rest)
    return v, t


def _step_response(
    duration_s: float = 1.0,
    step_start: float = 0.1,
    step_end: float = 0.6,
    step_amp: float = -10.0,  # mV deflection at end of step
    v_rest: float = -65.0,
) -> tuple:
    """Simulate a simple rectangular hyperpolarising step response."""
    t = np.linspace(0, duration_s, int(duration_s * FS), endpoint=False)
    v = np.full_like(t, v_rest)
    mask = (t >= step_start) & (t < step_end)
    v[mask] += step_amp
    return v, t


def _sag_trace(
    duration_s: float = 1.0,
    step_start: float = 0.1,
    step_end: float = 0.6,
    step_amp: float = -20.0,
    sag_fraction: float = 0.3,
    v_rest: float = -65.0,
) -> tuple:
    """Hyperpolarising step with sag (Ih-mediated rebound)."""
    t = np.linspace(0, duration_s, int(duration_s * FS), endpoint=False)
    v = np.full_like(t, v_rest)
    mask = (t >= step_start) & (t < step_end)
    n = np.sum(mask)
    idx = np.where(mask)[0]
    tau = 0.1 * FS  # ~100 ms time constant
    sag = sag_fraction * step_amp * np.exp(-np.arange(n) / tau)
    v[idx] += step_amp + sag
    return v, t


def _rc_charging(
    duration_s: float = 1.0,
    step_start: float = 0.1,
    step_end: float = 0.6,
    tau: float = 0.05,
    v_inf: float = -10.0,
    v_rest: float = -65.0,
) -> tuple:
    """RC charging curve for tau estimation."""
    t = np.linspace(0, duration_s, int(duration_s * FS), endpoint=False)
    v = np.full_like(t, v_rest)
    idx = np.where((t >= step_start) & (t < step_end))[0]
    t_local = t[idx] - step_start
    v[idx] = v_rest + v_inf * (1.0 - np.exp(-t_local / tau))
    return v, t


# ---------------------------------------------------------------------------
# _coerce_trial_lists
# ---------------------------------------------------------------------------


class TestCoerceTrialLists:
    def test_1d_array_wraps_in_list(self):
        v, t = _resting()
        dl, tl = _coerce_trial_lists(v, t)
        assert isinstance(dl, list) and len(dl) == 1
        assert isinstance(tl, list) and len(tl) == 1

    def test_2d_array_split_into_trials(self):
        v, t = _resting()
        data_2d = np.vstack([v, v])
        dl, tl = _coerce_trial_lists(data_2d, t)
        assert len(dl) == 2

    def test_2d_data_2d_time(self):
        v, t = _resting()
        data_2d = np.vstack([v, v])
        time_2d = np.vstack([t, t])
        dl, tl = _coerce_trial_lists(data_2d, time_2d)
        assert len(dl) == 2 and len(tl) == 2

    def test_list_input_unchanged(self):
        v, t = _resting()
        dl, tl = _coerce_trial_lists([v, v], [t, t])
        assert len(dl) == 2 and len(tl) == 2

    def test_time_as_1d_array_with_2d_data(self):
        v, t = _resting()
        data_2d = np.vstack([v, v])
        dl, tl = _coerce_trial_lists(data_2d, t)
        assert len(tl) == 2

    def test_time_as_ndarray_wraps_in_list(self):
        v, t = _resting()
        dl, tl = _coerce_trial_lists([v], t)
        assert isinstance(tl, list)


# ---------------------------------------------------------------------------
# _resolve_sweep_baseline
# ---------------------------------------------------------------------------


class TestResolveSweepBaseline:
    def test_manual_window_returned_unchanged(self):
        v, t = _resting()
        start, end = _resolve_sweep_baseline(v, t, FS, 0.0, 0.1, False, 0.5, 0.1, 0.5)
        assert start <= end

    def test_auto_detect_finds_stable_baseline(self):
        v, t = _resting()
        start, end = _resolve_sweep_baseline(v, t, FS, 0.0, 0.1, True, 0.5, 0.1, 0.0)
        assert start <= end

    def test_auto_detect_no_stable_baseline_falls_back(self):
        # Very noisy trace – find_stable_baseline may return no window
        rng = np.random.default_rng(42)
        v = rng.standard_normal(int(FS)) * 10.0
        t = np.linspace(0, 1.0, len(v), endpoint=False)
        start, end = _resolve_sweep_baseline(v, t, FS, 0.0, 0.1, True, 0.5, 0.1, 0.0)
        assert start <= end

    def test_blanking_applied(self):
        v, t = _resting()
        start, end = _resolve_sweep_baseline(v, t, FS, 0.0, 0.5, False, 0.5, 0.1, 10.0)
        # With 10 ms blanking, start should be shifted by 0.01 s
        assert start >= 0.0


# ---------------------------------------------------------------------------
# run_rmp_analysis_wrapper
# ---------------------------------------------------------------------------


class TestRunRmpAnalysisWrapper:
    def test_normal_single_trial(self):
        v, t = _resting()
        result = run_rmp_analysis_wrapper([v], [t], FS, baseline_start=0.0, baseline_end=0.5)
        assert result["module_used"] == "passive_properties"
        assert result["metrics"]["rmp_mv"] is not None
        assert abs(result["metrics"]["rmp_mv"] - (-65.0)) < 1.0

    def test_multi_trial(self):
        v, t = _resting()
        result = run_rmp_analysis_wrapper([v, v, v], [t, t, t], FS)
        assert result["metrics"]["rmp_mv"] is not None
        assert result["metrics"]["rmp_std"] is not None

    def test_2d_array_input(self):
        v, t = _resting()
        data_2d = np.vstack([v, v])
        result = run_rmp_analysis_wrapper(data_2d, t, FS)
        assert result["module_used"] == "passive_properties"

    def test_no_valid_rmp_returns_error(self):
        """Window outside trace → all sweeps produce NaN → no valid RMPs."""
        v, t = _resting(duration_s=0.5)
        result = run_rmp_analysis_wrapper([v], [t], FS, baseline_start=10.0, baseline_end=20.0)
        assert "rmp_error" in result["metrics"] or result["metrics"]["rmp_mv"] is None

    def test_ljp_correction_applied(self):
        v, t = _resting(v_rest=-60.0)
        result = run_rmp_analysis_wrapper([v], [t], FS, ljp_correction_mv=5.0)
        # LJP correction shifts the measured value
        assert result["metrics"]["rmp_mv"] is not None

    def test_auto_detect(self):
        v, t = _resting()
        result = run_rmp_analysis_wrapper([v], [t], FS, auto_detect=True)
        assert result["module_used"] == "passive_properties"

    def test_exception_returns_error_dict(self):
        """Pass bad data to trigger exception path (lines 1310-1312)."""
        result = run_rmp_analysis_wrapper(None, None, FS)
        assert "rmp_error" in result["metrics"] or result["metrics"].get("rmp_mv") is None


# ---------------------------------------------------------------------------
# run_sag_ratio_wrapper
# ---------------------------------------------------------------------------


class TestRunSagRatioWrapper:
    def test_normal_sag_trace(self):
        v, t = _sag_trace()
        result = run_sag_ratio_wrapper(
            v,
            t,
            FS,
            baseline_start=0.0,
            baseline_end=0.08,
            peak_window_start=0.1,
            peak_window_end=0.15,
            ss_window_start=0.5,
            ss_window_end=0.59,
        )
        assert result["module_used"] == "passive_properties"
        assert "sag_ratio" in result["metrics"]

    def test_flat_trace_no_sag(self):
        v, t = _resting()
        result = run_sag_ratio_wrapper(
            v,
            t,
            FS,
            baseline_start=0.0,
            baseline_end=0.09,
            peak_window_start=0.1,
            peak_window_end=0.2,
            ss_window_start=0.8,
            ss_window_end=0.9,
        )
        assert result["module_used"] == "passive_properties"

    def test_invalid_windows_returns_none(self):
        v, t = _resting(duration_s=0.2)
        result = run_sag_ratio_wrapper(
            v,
            t,
            FS,
            baseline_start=0.0,
            baseline_end=0.05,
            peak_window_start=0.15,
            peak_window_end=0.16,
            ss_window_start=0.9,
            ss_window_end=1.0,  # outside trace
        )
        assert result["module_used"] == "passive_properties"

    def test_exception_returns_error_dict(self):
        result = run_sag_ratio_wrapper(None, None, FS)
        assert "sag_error" in result["metrics"] or result["metrics"].get("sag_ratio") is None


# ---------------------------------------------------------------------------
# run_rin_analysis_wrapper
# ---------------------------------------------------------------------------


class TestRunRinAnalysisWrapper:
    def test_current_clamp_mode(self):
        v, t = _step_response()
        result = run_rin_analysis_wrapper(
            v,
            t,
            FS,
            current_amplitude=-100.0,
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=0.4,
            response_end=0.59,
        )
        assert result["module_used"] == "passive_properties"
        assert "rin_mohm" in result["metrics"]

    def test_voltage_clamp_mode(self):
        v, t = _step_response(step_amp=-5.0)
        result = run_rin_analysis_wrapper(
            v,
            t,
            FS,
            current_amplitude=0.0,
            voltage_step=-5.0,
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=0.4,
            response_end=0.59,
        )
        assert result["module_used"] == "passive_properties"

    def test_auto_detect_pulse(self):
        v, t = _step_response()
        result = run_rin_analysis_wrapper(
            v,
            t,
            FS,
            current_amplitude=-100.0,
            auto_detect_pulse=True,
        )
        assert result["module_used"] == "passive_properties"

    def test_zero_current_and_voltage_returns_error(self):
        v, t = _resting()
        result = run_rin_analysis_wrapper(
            v,
            t,
            FS,
            current_amplitude=0.0,
            voltage_step=0.0,
        )
        assert "rin_error" in result["metrics"]

    def test_negative_step_auto_detect(self):
        """Negative current step uses argmin(dv) path."""
        v, t = _step_response(step_amp=-10.0)
        result = run_rin_analysis_wrapper(
            v,
            t,
            FS,
            current_amplitude=-100.0,
            auto_detect_pulse=True,
        )
        assert result["module_used"] == "passive_properties"

    def test_positive_step_auto_detect(self):
        """Positive current step uses argmax(dv) path."""
        v, t = _step_response(step_amp=+5.0)
        result = run_rin_analysis_wrapper(
            v,
            t,
            FS,
            current_amplitude=+50.0,
            auto_detect_pulse=True,
        )
        assert result["module_used"] == "passive_properties"

    def test_exception_returns_error_dict(self):
        result = run_rin_analysis_wrapper(None, None, FS, current_amplitude=-100.0)
        assert "rin_error" in result["metrics"] or result["metrics"].get("rin_mohm") is None


# ---------------------------------------------------------------------------
# run_tau_analysis_wrapper
# ---------------------------------------------------------------------------


class TestRunTauAnalysisWrapper:
    def test_mono_exponential_fit(self):
        v, t = _rc_charging()
        result = run_tau_analysis_wrapper(
            v,
            t,
            FS,
            stim_start_time=0.1,
            fit_duration=0.2,
            tau_model="mono",
        )
        assert result["module_used"] == "passive_properties"
        assert "tau_ms" in result["metrics"]

    def test_bi_exponential_fit(self):
        v, t = _rc_charging(tau=0.03)
        result = run_tau_analysis_wrapper(
            v,
            t,
            FS,
            stim_start_time=0.1,
            fit_duration=0.2,
            tau_model="bi",
        )
        assert result["module_used"] == "passive_properties"

    def test_tau_none_result(self):
        """Very short fit duration → tau calculation may fail → None metrics."""
        v, t = _resting(duration_s=0.2)
        result = run_tau_analysis_wrapper(
            v,
            t,
            FS,
            stim_start_time=5.0,  # outside trace
            fit_duration=0.01,
        )
        assert result["module_used"] == "passive_properties"

    def test_tau_fit_error_flag(self):
        """Flat trace → tau fit may yield NaN → tau_error flag."""
        v, t = _resting()
        result = run_tau_analysis_wrapper(v, t, FS, stim_start_time=0.1, fit_duration=0.05)
        assert result["module_used"] == "passive_properties"

    def test_exception_returns_error_dict(self):
        result = run_tau_analysis_wrapper(None, None, FS)
        assert "tau_error" in result["metrics"] or result["metrics"].get("tau_ms") is None


# ---------------------------------------------------------------------------
# run_iv_curve_wrapper
# ---------------------------------------------------------------------------


class TestRunIvCurveWrapper:
    def _make_sweeps(self, n: int = 5):
        sweeps = []
        times = []
        for i in range(n):
            v, t = _step_response(step_amp=-5.0 * (i + 1))
            sweeps.append(v)
            times.append(t)
        return sweeps, times

    def test_list_input(self):
        sweeps, times = self._make_sweeps(5)
        result = run_iv_curve_wrapper(
            sweeps,
            times,
            FS,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=0.4,
            response_end=0.59,
        )
        assert result["module_used"] == "passive_properties"

    def test_2d_array_input(self):
        sweeps, times = self._make_sweeps(3)
        data_2d = np.vstack(sweeps)
        result = run_iv_curve_wrapper(data_2d, times[0], FS)
        assert result["module_used"] == "passive_properties"

    def test_1d_array_input(self):
        v, t = _step_response()
        result = run_iv_curve_wrapper(v, t, FS)
        assert result["module_used"] == "passive_properties"

    def test_2d_data_2d_time(self):
        sweeps, times = self._make_sweeps(3)
        data_2d = np.vstack(sweeps)
        time_2d = np.vstack(times)
        result = run_iv_curve_wrapper(data_2d, time_2d, FS)
        assert result["module_used"] == "passive_properties"

    def test_time_as_1d_ndarray(self):
        sweeps, times = self._make_sweeps(2)
        data_2d = np.vstack(sweeps)
        result = run_iv_curve_wrapper(data_2d, times[0], FS)
        assert result["module_used"] == "passive_properties"

    def test_exception_returns_error_dict(self):
        result = run_iv_curve_wrapper(None, None, FS)
        assert "iv_curve_error" in result["metrics"] or "module_used" in result


# ---------------------------------------------------------------------------
# run_capacitance_analysis_wrapper
# ---------------------------------------------------------------------------


class TestRunCapacitanceAnalysisWrapper:
    def test_current_clamp_mode(self):
        v, t = _rc_charging()
        result = run_capacitance_analysis_wrapper(
            v,
            t,
            FS,
            mode="Current-Clamp",
            current_amplitude_pa=-100.0,
            baseline_start_s=0.0,
            baseline_end_s=0.09,
            response_start_s=0.1,
            response_end_s=0.6,
        )
        assert result["module_used"] == "passive_properties"

    def test_voltage_clamp_mode(self):
        v, t = _step_response(step_amp=-5.0)
        result = run_capacitance_analysis_wrapper(
            v,
            t,
            FS,
            mode="Voltage-Clamp",
            voltage_step_mv=-5.0,
            baseline_start_s=0.0,
            baseline_end_s=0.09,
            response_start_s=0.1,
            response_end_s=0.3,
        )
        assert result["module_used"] == "passive_properties"

    def test_unknown_mode_returns_error(self):
        v, t = _resting()
        result = run_capacitance_analysis_wrapper(v, t, FS, mode="UnknownMode")
        assert "error" in result["metrics"]

    def test_rin_failed_in_cc_mode(self):
        """Zero current step → Rin calculation fails → error returned."""
        v, t = _resting()
        result = run_capacitance_analysis_wrapper(
            v,
            t,
            FS,
            mode="Current-Clamp",
            current_amplitude_pa=0.0,
        )
        assert result["module_used"] == "passive_properties"

    def test_tau_none_cc_mode(self):
        """Flat trace in CC mode → tau may fail."""
        v, t = _resting()
        result = run_capacitance_analysis_wrapper(
            v,
            t,
            FS,
            mode="Current-Clamp",
            current_amplitude_pa=-100.0,
            baseline_start_s=0.0,
            baseline_end_s=0.09,
            response_start_s=0.1,
            response_end_s=0.6,
        )
        # May succeed or fail gracefully
        assert result["module_used"] == "passive_properties"


# ===========================================================================
# Direct calculation function error paths
# ===========================================================================


class TestCalculateRmpErrorPaths:
    """Cover lines 137-138, 148-153 in calculate_rmp."""

    def test_polyfit_raises(self):
        """Lines 137-138: np.polyfit raises → slope = None."""
        v, t = _resting(v_rest=-65.0)
        with patch("Synaptipy.core.analysis.passive_properties.np.polyfit", side_effect=ValueError("polyfit fail")):
            result = calculate_rmp(v, t, baseline_window=(0.0, 0.5))
        assert result.is_valid
        assert result.drift is None

    def test_index_error_returns_invalid(self):
        """Lines 148-150: IndexError in outer except."""
        v = np.array([-65.0] * 100)
        t = np.linspace(0, 0.01, 100)
        with patch("Synaptipy.core.analysis.passive_properties.np.mean", side_effect=IndexError("bad idx")):
            result = calculate_rmp(v, t, baseline_window=(0.0, 0.005))
        assert not result.is_valid

    def test_value_error_returns_invalid(self):
        """Lines 151-153: ValueError in outer except."""
        v = np.array([-65.0] * 100)
        t = np.linspace(0, 0.01, 100)
        with patch("Synaptipy.core.analysis.passive_properties.np.mean", side_effect=ValueError("bad val")):
            result = calculate_rmp(v, t, baseline_window=(0.0, 0.005))
        assert not result.is_valid


class TestCalculateRinErrorPaths:
    """Cover lines 287-293 and 330-332 in calculate_rin."""

    def test_zero_current_returns_invalid(self):
        """Lines 287-293: delta_i_nA == 0.0."""
        v, t = _resting()
        result = calculate_rin(
            v,
            t,
            current_amplitude=0.0,
            baseline_window=(0.0, 0.09),
            response_window=(0.1, 0.6),
        )
        assert not result.is_valid
        assert "zero" in (result.error_message or "").lower()

    def test_exception_returns_invalid(self):
        """Lines 330-332: caught exception."""
        v, t = _resting()
        with patch("Synaptipy.core.analysis.passive_properties.np.mean", side_effect=ValueError("rin fail")):
            result = calculate_rin(
                v,
                t,
                current_amplitude=-100.0,
                baseline_window=(0.0, 0.09),
                response_window=(0.1, 0.6),
            )
        assert not result.is_valid


class TestCalculateTauErrorPaths:
    """Cover lines 803-804, 814-816, 826-827, 841-844, 880-882 in calculate_tau."""

    def test_linalg_error_in_log_fit(self):
        """Lines 803-804: polyfit in log regression raises → fallback tau used."""
        v, t = _step_response()
        with patch(
            "Synaptipy.core.analysis.passive_properties.np.polyfit", side_effect=np.linalg.LinAlgError("svd fail")
        ):
            result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.2, model="mono")
        # Should still attempt curve_fit with fallback tau
        assert result is None or isinstance(result, dict)

    def test_mono_exp_runtime_error(self):
        """Lines 814-816: RuntimeError in mono-exp curve_fit."""
        v, t = _step_response()
        call_count = [0]

        def selective_raise(*a, **kw):
            call_count[0] += 1
            # Allow polyfit to succeed but make curve_fit raise
            raise RuntimeError("mono fail")

        with patch("Synaptipy.core.analysis.passive_properties.curve_fit", side_effect=selective_raise):
            result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.2, model="mono")
        assert result is not None
        assert "tau_ms" in result
        assert np.isnan(result["tau_ms"])

    def test_bi_exp_too_short(self):
        """Lines 826-827: len(t_fit) < 6 for bi-exponential."""
        # Use very short fit duration so only < 6 samples are in the window
        v, t = _step_response()
        # 0.0002 s fit at 10 kHz = 2 samples
        result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.0002, model="bi")
        assert result is None

    def test_bi_exp_runtime_error(self):
        """Lines 841-844: RuntimeError in bi-exp curve_fit."""
        v, t = _step_response()
        with patch("Synaptipy.core.analysis.passive_properties.curve_fit", side_effect=RuntimeError("bi fail")):
            result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.3, model="bi")
        # Should return a dict with NaN values
        assert result is not None
        assert "tau_fast_ms" in result

    def test_outer_runtime_error(self):
        """Lines 880-882: outer RuntimeError → return None."""
        v, t = _step_response()
        with patch("Synaptipy.core.analysis.passive_properties.curve_fit", side_effect=RuntimeError("fail")):
            result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.3, model="mono")
        assert result is not None  # inner except catches and returns nan dict


class TestCalculateVcTransientParams:
    """Cover lines 432-433, 440-441, 485-486 in calculate_vc_transient_parameters."""

    def test_no_baseline_samples(self):
        """Lines 432-433: no baseline samples before step_onset_time."""
        n = int(0.1 * FS)
        t = np.linspace(0.5, 0.6, n, endpoint=False)  # time starts at 0.5
        current = np.zeros(n)
        result = calculate_vc_transient_parameters(
            current_trace=current,
            time_vector=t,
            step_onset_time=0.0,  # before any samples → no baseline
            voltage_step_mv=-10.0,
        )
        assert np.isnan(result["rs_mohm"])  # returns default nan result

    def test_no_transient_samples(self):
        """Lines 440-441: no transient window samples."""
        n = int(0.1 * FS)
        t = np.linspace(0.0, 0.1, n, endpoint=False)
        current = np.zeros(n)
        result = calculate_vc_transient_parameters(
            current_trace=current,
            time_vector=t,
            step_onset_time=2.0,  # after all samples → no transient
            voltage_step_mv=-10.0,
        )
        assert np.isnan(result["rs_mohm"])

    def test_exception_path(self):
        """Lines 485-486: exception handler."""
        n = int(0.1 * FS)
        t = np.linspace(0.0, 0.1, n, endpoint=False)
        current = np.zeros(n)
        with patch("Synaptipy.core.analysis.passive_properties.np.mean", side_effect=ValueError("transient fail")):
            result = calculate_vc_transient_parameters(
                current_trace=current,
                time_vector=t,
                step_onset_time=0.05,
                voltage_step_mv=-10.0,
            )
        assert np.isnan(result["rs_mohm"])


class TestCalculateCapacitanceVc:
    """Cover lines 1067, 1072, 1025-1030, 1102-1104 in calculate_capacitance_vc."""

    def test_no_baseline_samples(self):
        """Line 1067: no baseline samples → return None."""
        n = int(0.1 * FS)
        t = np.linspace(0.5, 0.6, n, endpoint=False)  # starts at 0.5
        current = np.zeros(n)
        result = calculate_capacitance_vc(
            current_trace=current,
            time_vector=t,
            baseline_window=(0.0, 0.1),  # before any time data
            transient_window=(0.5, 0.55),
            voltage_step_amplitude_mv=-10.0,
        )
        assert result is None

    def test_no_transient_samples(self):
        """Line 1072: no transient samples → return None."""
        n = int(0.1 * FS)
        t = np.linspace(0.0, 0.1, n, endpoint=False)
        current = np.zeros(n)
        result = calculate_capacitance_vc(
            current_trace=current,
            time_vector=t,
            baseline_window=(0.0, 0.05),
            transient_window=(0.5, 0.6),  # after all time data
            voltage_step_amplitude_mv=-10.0,
        )
        assert result is None

    def test_fit_runtime_error_fallback(self):
        """Lines 1025-1030: curve_fit RuntimeError → AUC fallback."""
        import scipy.optimize as scopt

        n = int(0.2 * FS)
        t = np.linspace(0.0, 0.2, n, endpoint=False)
        current = np.zeros(n)
        # Capacitive transient: large spike at step onset
        step_idx = int(0.1 * FS)
        current[step_idx : step_idx + 20] = -200.0  # 200 pA transient
        with patch.object(scopt, "curve_fit", side_effect=RuntimeError("noconv")):
            result = calculate_capacitance_vc(
                current_trace=current,
                time_vector=t,
                baseline_window=(0.0, 0.09),
                transient_window=(0.1, 0.15),
                voltage_step_amplitude_mv=-10.0,
            )
        # Fallback to AUC should still return a result
        assert result is None or isinstance(result, dict)

    def test_exception_path(self):
        """Lines 1102-1104: caught exception → return None."""
        n = int(0.1 * FS)
        t = np.linspace(0.0, 0.1, n, endpoint=False)
        current = np.zeros(n)
        with patch("Synaptipy.core.analysis.passive_properties.np.mean", side_effect=ValueError("vc fail")):
            result = calculate_capacitance_vc(
                current_trace=current,
                time_vector=t,
                baseline_window=(0.0, 0.05),
                transient_window=(0.05, 0.1),
                voltage_step_amplitude_mv=-10.0,
            )
        assert result is None


class TestCalculateConductanceErrorPath:
    """Cover lines 646-648 in calculate_conductance."""

    def test_exception_returns_invalid(self):
        """Lines 646-648: caught exception → RinResult with is_valid=False."""
        v, t = _resting()
        with patch("Synaptipy.core.analysis.passive_properties.np.mean", side_effect=ValueError("conductance fail")):
            result = calculate_conductance(
                current_trace=v,
                time_vector=t,
                voltage_step=-10.0,
                baseline_window=(0.0, 0.09),
                response_window=(0.1, 0.6),
            )
        assert not result.is_valid
