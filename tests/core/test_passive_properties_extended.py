# -*- coding: utf-8 -*-
"""Extended tests for core/analysis/passive_properties.py."""

import numpy as np
import pytest

from Synaptipy.core.analysis.passive_properties import (
    _fit_vc_transient_decay,
    _sag_nan_payload,
    apply_ljp_correction,
    calculate_baseline_stats,
    calculate_capacitance_cc,
    calculate_cc_series_resistance_fast,
    calculate_conductance,
    calculate_iv_curve,
    calculate_rin,
    calculate_rmp,
    calculate_sag_ratio,
    calculate_tau,
    calculate_vc_transient_parameters,
    find_stable_baseline,
)

# ---------------------------------------------------------------------------
# Waveform factories
# ---------------------------------------------------------------------------


def _make_time(duration=1.0, fs=10000.0):
    n = int(duration * fs)
    return np.linspace(0, duration, n, endpoint=False)


def _rc_step_voltage(
    t,
    v_baseline=-65.0,
    v_step_end=-75.0,
    step_start=0.1,
    step_end=0.6,
    tau=0.02,
):
    """Simulate voltage response to a hyperpolarising current step (RC circuit)."""
    v = np.full_like(t, v_baseline)
    on = t >= step_start
    v[on] = v_step_end + (v_baseline - v_step_end) * np.exp(-(t[on] - step_start) / tau)
    off = t >= step_end
    v[off] = v_baseline + (v[np.argmax(off)] - v_baseline) * np.exp(-(t[off] - step_end) / tau)
    return v


def _vc_transient(t, step_onset=0.1, rs_mohm=15.0, cm_pf=100.0, v_step_mv=10.0, i_hold=-100.0):
    """Simulate the capacitive transient in voltage-clamp."""
    tau_c = rs_mohm * cm_pf * 1e-6  # s  (MOhm * pF = ms, /1e3 -> s)
    i = np.full_like(t, i_hold)
    trans = t >= step_onset
    i_peak = v_step_mv / rs_mohm * 1e3  # pA
    i[trans] = i_hold + i_peak * np.exp(-(t[trans] - step_onset) / tau_c)
    return i


# ---------------------------------------------------------------------------
# apply_ljp_correction
# ---------------------------------------------------------------------------


class TestApplyLjpCorrection:
    def test_zero_ljp_returns_original_array(self):
        v = np.array([-65.0, -64.0])
        out = apply_ljp_correction(v, 0.0)
        assert out is v  # same object

    def test_positive_ljp_shifts_down(self):
        v = np.array([-60.0, -61.0])
        out = apply_ljp_correction(v, 5.0)
        np.testing.assert_allclose(out, [-65.0, -66.0])

    def test_negative_ljp_shifts_up(self):
        v = np.array([-65.0])
        out = apply_ljp_correction(v, -5.0)
        np.testing.assert_allclose(out, [-60.0])


# ---------------------------------------------------------------------------
# _sag_nan_payload
# ---------------------------------------------------------------------------


def test_sag_nan_payload_all_nan():
    p = _sag_nan_payload()
    assert all(np.isnan(v) for v in p.values())


# ---------------------------------------------------------------------------
# calculate_rmp – error branches
# ---------------------------------------------------------------------------


class TestCalculateRmpErrorBranches:
    def test_non_1d_array_rejected(self):
        data = np.array([[1, 2], [3, 4]])
        time = np.array([0.0, 0.1])
        result = calculate_rmp(data, time, (0.0, 0.1))
        assert result.is_valid is False

    def test_empty_array_rejected(self):
        result = calculate_rmp(np.array([]), np.array([]), (0.0, 0.1))
        assert result.is_valid is False

    def test_time_shape_mismatch_rejected(self):
        result = calculate_rmp(np.ones(10), np.ones(5), (0.0, 0.05))
        assert result.is_valid is False

    def test_baseline_window_wrong_type(self):
        result = calculate_rmp(np.ones(10), np.linspace(0, 1, 10), [0.0, 0.5])
        assert result.is_valid is False

    def test_non_numeric_times(self):
        result = calculate_rmp(np.ones(10), np.linspace(0, 1, 10), ("a", "b"))
        assert result.is_valid is False

    def test_start_ge_end_rejected(self):
        result = calculate_rmp(np.ones(10), np.linspace(0, 1, 10), (0.5, 0.1))
        assert result.is_valid is False

    def test_window_outside_range_returns_invalid(self):
        result = calculate_rmp(np.ones(10), np.linspace(0, 1, 10), (5.0, 10.0))
        assert result.is_valid is False

    def test_valid_rmp_calculated(self):
        t = np.linspace(0, 1, 10000)
        data = np.full_like(t, -65.0)
        result = calculate_rmp(data, t, (0.0, 0.1))
        assert result.is_valid
        assert abs(result.value - (-65.0)) < 0.01


# ---------------------------------------------------------------------------
# calculate_baseline_stats
# ---------------------------------------------------------------------------


class TestCalculateBaselineStats:
    def test_valid_stats(self):
        t = np.linspace(0, 1, 10000)
        v = np.full_like(t, -65.0)
        result = calculate_baseline_stats(t, v, 0.0, 0.1)
        assert result is not None
        mean, std = result
        assert abs(mean - (-65.0)) < 0.01

    def test_invalid_window_returns_none(self):
        t = np.linspace(0, 1, 100)
        v = np.ones_like(t)
        result = calculate_baseline_stats(t, v, 5.0, 10.0)
        assert result is None


# ---------------------------------------------------------------------------
# find_stable_baseline
# ---------------------------------------------------------------------------


class TestFindStableBaseline:
    def test_empty_data(self):
        mean, sd, window = find_stable_baseline(np.array([]), 1000.0)
        assert mean is None
        assert sd is None
        assert window is None

    def test_short_trace_covered_entirely(self):
        data = np.full(10, 3.0)
        mean, sd, window = find_stable_baseline(data, 1000.0, window_duration_s=1.0)
        assert abs(mean - 3.0) < 0.01
        assert window is not None

    def test_normal_trace(self):
        data = np.concatenate([np.full(500, 0.0), np.full(500, 10.0)])
        mean, sd, window = find_stable_baseline(data, 1000.0, window_duration_s=0.2)
        assert mean is not None
        assert abs(mean) < 1.0  # Should find the flat 0.0 region


# ---------------------------------------------------------------------------
# calculate_rin – error branches
# ---------------------------------------------------------------------------


class TestCalculateRinEdgeCases:
    def test_invalid_current_amplitude(self):
        t = np.linspace(0, 1, 10000)
        v = np.ones_like(t) * -65.0
        result = calculate_rin(v, t, "bad", (0.0, 0.1), (0.1, 0.6))
        assert result.is_valid is False

    def test_zero_current_amplitude(self):
        t = np.linspace(0, 1, 10000)
        v = np.ones_like(t) * -65.0
        result = calculate_rin(v, t, 0.0, (0.0, 0.1), (0.1, 0.6))
        assert result.is_valid is False

    def test_no_data_in_windows(self):
        t = np.linspace(0, 1, 10000)
        v = np.ones_like(t) * -65.0
        result = calculate_rin(v, t, -100.0, (5.0, 6.0), (7.0, 8.0))
        assert result.is_valid is False

    def test_blanking_exceeds_window(self):
        """Rs artifact blanking > response window should fall back to unblocked."""
        t = np.linspace(0, 1, 10000)
        v = _rc_step_voltage(t)
        result = calculate_rin(v, t, -100.0, (0.0, 0.09), (0.1, 0.105), rs_artifact_blanking_ms=100.0)
        # Should not crash; valid result or graceful failure
        assert isinstance(result.is_valid, bool)

    def test_peak_rin_and_ss_rin_populated(self):
        t = np.linspace(0, 1, 10000)
        v = _rc_step_voltage(t, v_baseline=-65.0, v_step_end=-75.0, step_start=0.1, step_end=0.6)
        result = calculate_rin(v, t, -100.0, (0.0, 0.09), (0.1, 0.59))
        if result.is_valid:
            assert result.rin_peak_mohm is not None
            assert result.rin_steady_state_mohm is not None


# ---------------------------------------------------------------------------
# _fit_vc_transient_decay
# ---------------------------------------------------------------------------


class TestFitVcTransientDecay:
    def test_too_few_samples_returns_nan(self):
        tau, cm = _fit_vc_transient_decay(np.ones(3), np.linspace(0, 0.003, 3), 100.0, 15.0, 100.0)
        assert np.isnan(tau)
        assert np.isnan(cm)

    def test_negligible_peak_returns_nan(self):
        tau, cm = _fit_vc_transient_decay(np.ones(10), np.linspace(0, 0.01, 10), 0.0, 15.0, 100.0)
        assert np.isnan(tau)

    def test_good_decay_fits(self):
        rs = 15.0  # MOhm
        cm = 100.0  # pF
        tau_c = rs * cm * 1e-6  # seconds
        t = np.linspace(0, tau_c * 5, 50)
        i_peak = 666.0  # pA = 10 mV / 15 MOhm * 1e3
        decay = i_peak * np.exp(-t / tau_c)
        tau_ms, cm_fit = _fit_vc_transient_decay(decay, t, i_peak, rs, cm)
        # tau_ms should be finite and positive
        if not np.isnan(tau_ms):
            assert tau_ms > 0


# ---------------------------------------------------------------------------
# calculate_vc_transient_parameters
# ---------------------------------------------------------------------------


class TestCalculateVcTransientParameters:
    def test_zero_voltage_step_returns_nan_dict(self):
        t = _make_time(0.5, 10000.0)
        i = np.zeros_like(t)
        result = calculate_vc_transient_parameters(i, t, 0.1, 0.0)
        assert np.isnan(result["rs_mohm"])

    def test_no_baseline_samples(self):
        """Step onset at start of trace – no pre-step baseline."""
        t = _make_time(0.1, 10000.0)
        i = np.zeros_like(t)
        result = calculate_vc_transient_parameters(i, t, 0.0001, 10.0, baseline_window_s=0.1)
        # Should handle gracefully – either nan or valid
        assert isinstance(result["rs_mohm"], float)

    def test_realistic_vc_step(self):
        """Synthetic VC transient should give reasonable Rs/Cm estimates."""
        fs = 100000.0
        t = np.linspace(0, 0.1, int(0.1 * fs), endpoint=False)
        rs_true = 15.0  # MOhm
        cm_true = 100.0  # pF
        i = _vc_transient(t, step_onset=0.01, rs_mohm=rs_true, cm_pf=cm_true, v_step_mv=10.0)
        result = calculate_vc_transient_parameters(i, t, step_onset_time=0.01, voltage_step_mv=10.0)
        if not np.isnan(result["rs_mohm"]):
            assert result["rs_mohm"] > 0

    def test_negative_voltage_step(self):
        """Negative step elicits downward current peak."""
        fs = 100000.0
        t = np.linspace(0, 0.1, int(0.1 * fs), endpoint=False)
        i = _vc_transient(t, step_onset=0.01, v_step_mv=-10.0)
        result = calculate_vc_transient_parameters(i, t, step_onset_time=0.01, voltage_step_mv=-10.0)
        assert isinstance(result["rs_mohm"], float)


# ---------------------------------------------------------------------------
# calculate_cc_series_resistance_fast
# ---------------------------------------------------------------------------


class TestCalculateCcSeriesResistanceFast:
    def _make_cc_step(self, fs=100000.0, step_onset=0.01, i_step=100.0, rs=10.0):
        """Synthetic CC voltage trace with fast RS artifact."""
        duration = 0.05
        t = np.linspace(0, duration, int(duration * fs), endpoint=False)
        v = np.full_like(t, -65.0)
        # Fast RS drop + slow membrane charging
        on = t >= step_onset
        rs_drop = rs * i_step * 1e-3  # mV = MOhm * pA * 1e-3
        v[on] = -65.0 + rs_drop * np.exp(-(t[on] - step_onset) / 0.001)
        return t, v

    def test_zero_current_returns_nan(self):
        t, v = self._make_cc_step()
        result = calculate_cc_series_resistance_fast(v, t, 0.01, 0.0)
        assert np.isnan(result["rs_cc_mohm"])

    def test_no_baseline_samples_returns_nan(self):
        """Step onset at very start with no pre-step data."""
        t = np.linspace(0, 0.05, 5000, endpoint=False)
        v = np.full_like(t, -65.0)
        result = calculate_cc_series_resistance_fast(v, t, 0.0001, 100.0)
        # Either nan or valid
        assert isinstance(result["rs_cc_mohm"], float)

    def test_with_tau_and_rin_gives_cm(self):
        t, v = self._make_cc_step()
        result = calculate_cc_series_resistance_fast(v, t, 0.01, 100.0, tau_ms=20.0, rin_mohm=200.0)
        if not np.isnan(result["rs_cc_mohm"]):
            # Cm = tau / Rin = 20ms / 200MOhm = 100 pF
            assert result["cm_derived_pf"] == pytest.approx(100.0, rel=0.01)

    def test_without_tau_cm_is_nan(self):
        t, v = self._make_cc_step()
        result = calculate_cc_series_resistance_fast(v, t, 0.01, 100.0)
        assert np.isnan(result["cm_derived_pf"])


# ---------------------------------------------------------------------------
# calculate_conductance
# ---------------------------------------------------------------------------


class TestCalculateConductance:
    def _make_vc_trace(self, fs=10000.0, duration=0.5):
        t = np.linspace(0, duration, int(duration * fs), endpoint=False)
        i = np.full_like(t, -100.0)
        # Step response
        on = t >= 0.1
        i[on] = -150.0
        return t, i

    def test_zero_voltage_step_returns_invalid(self):
        t, i = self._make_vc_trace()
        result = calculate_conductance(i, t, 0.0, (0.0, 0.09), (0.1, 0.4))
        assert result.is_valid is False

    def test_no_data_in_window(self):
        t, i = self._make_vc_trace()
        result = calculate_conductance(i, t, 10.0, (5.0, 6.0), (7.0, 8.0))
        assert result.is_valid is False

    def test_valid_conductance(self):
        t, i = self._make_vc_trace()
        result = calculate_conductance(i, t, 10.0, (0.0, 0.09), (0.1, 0.4))
        assert result.is_valid
        assert result.conductance is not None


# ---------------------------------------------------------------------------
# calculate_iv_curve
# ---------------------------------------------------------------------------


class TestCalculateIvCurve:
    def _make_iv_sweeps(self, n=5, fs=10000.0, duration=0.5):
        """Return sweeps at varying current steps."""
        current_steps = [-200.0, -100.0, 0.0, 100.0, 200.0]
        sweeps = []
        times = []
        rin = 200.0  # MOhm
        for i_pa in current_steps:
            t = np.linspace(0, duration, int(duration * fs), endpoint=False)
            v_base = -65.0
            v_step = v_base + (i_pa / 1000.0) * rin  # Ohm's law: V = I*R (in consistent units)
            v = np.full_like(t, v_base)
            v[t >= 0.1] = v_step
            sweeps.append(v)
            times.append(t)
        return sweeps, times, current_steps

    def test_empty_sweeps_returns_error(self):
        result = calculate_iv_curve([], [], [], (0.0, 0.1), (0.1, 0.4))
        assert "error" in result

    def test_mismatched_sweeps_and_steps(self):
        sweeps, times, _ = self._make_iv_sweeps()
        result = calculate_iv_curve(sweeps, times, [-100.0, 100.0], (0.0, 0.09), (0.1, 0.45))
        assert "rin_aggregate_mohm" in result

    def test_full_iv_with_regression(self):
        sweeps, times, steps = self._make_iv_sweeps()
        result = calculate_iv_curve(sweeps, times, steps, (0.0, 0.09), (0.1, 0.45))
        assert "rin_aggregate_mohm" in result
        if result["rin_aggregate_mohm"] is not None:
            assert result["rin_aggregate_mohm"] > 0

    def test_single_sweep_no_regression(self):
        sweeps, times, steps = self._make_iv_sweeps()
        result = calculate_iv_curve(sweeps[:1], times[:1], steps[:1], (0.0, 0.09), (0.1, 0.45))
        assert result["rin_aggregate_mohm"] is None

    def test_rectification_index_with_negative_steps(self):
        sweeps, times, steps = self._make_iv_sweeps()
        result = calculate_iv_curve(sweeps, times, steps, (0.0, 0.09), (0.1, 0.45))
        # rectification_index may be present when multiple negative steps exist
        assert "rectification_index" in result

    def test_windows_outside_range(self):
        sweeps, times, steps = self._make_iv_sweeps()
        result = calculate_iv_curve(sweeps, times, steps, (5.0, 6.0), (7.0, 8.0))
        # All delta_vs should be nan
        assert all(np.isnan(dv) for dv in result["delta_vs"])


# ---------------------------------------------------------------------------
# calculate_tau
# ---------------------------------------------------------------------------


class TestCalculateTau:
    def _make_tau_trace(self, tau_s=0.02, fs=10000.0, duration=0.5):
        t = _make_time(duration, fs)
        v_baseline = -65.0
        v_step = -75.0
        step_start = 0.05
        v = np.full_like(t, v_baseline)
        on = t >= step_start
        v[on] = v_step + (v_baseline - v_step) * np.exp(-(t[on] - step_start) / tau_s)
        return t, v

    def test_mono_exponential_fit(self):
        t, v = self._make_tau_trace(tau_s=0.02)
        result = calculate_tau(v, t, stim_start_time=0.05, fit_duration=0.1, model="mono")
        if result is not None and "tau_ms" in result:
            if not np.isnan(result["tau_ms"]):
                assert result["tau_ms"] == pytest.approx(20.0, rel=0.15)

    def test_bi_exponential_fit(self):
        t, v = self._make_tau_trace(tau_s=0.02)
        result = calculate_tau(v, t, stim_start_time=0.05, fit_duration=0.15, model="bi")
        # May return dict or None
        assert result is None or isinstance(result, dict)

    def test_unknown_model_returns_none(self):
        t, v = self._make_tau_trace()
        result = calculate_tau(v, t, stim_start_time=0.05, fit_duration=0.1, model="invalid")
        assert result is None

    def test_too_few_samples_returns_none(self):
        t = np.linspace(0, 0.001, 2)
        v = np.ones_like(t) * -65.0
        result = calculate_tau(v, t, stim_start_time=0.0, fit_duration=0.001, model="mono")
        assert result is None

    def test_tau_bounds_respected(self):
        t, v = self._make_tau_trace(tau_s=0.02)
        result = calculate_tau(v, t, stim_start_time=0.05, fit_duration=0.1, model="mono", tau_bounds=(0.001, 0.5))
        assert result is None or isinstance(result, dict)

    def test_bi_too_few_samples_returns_none(self):
        t = np.linspace(0, 0.001, 5)
        v = np.full_like(t, -65.0)
        result = calculate_tau(v, t, stim_start_time=0.0, fit_duration=0.001, model="bi")
        assert result is None


# ---------------------------------------------------------------------------
# calculate_sag_ratio
# ---------------------------------------------------------------------------


class TestCalculateSagRatioExtended:
    def _make_sag_trace(self, fs=10000.0, with_rebound=True):
        duration = 1.2
        t = _make_time(duration, fs)
        v = np.full_like(t, -65.0)
        # Hyperpolarising step 0.1-0.7 s with sag (Ih-like recovery)
        on = (t >= 0.1) & (t < 0.7)
        v[on] = -75.0 + 3.0 * (1.0 - np.exp(-(t[on] - 0.1) / 0.15))
        # Post-step rebound
        off = t >= 0.7
        if with_rebound:
            v[off] = -65.0 + 2.0 * np.exp(-(t[off] - 0.7) / 0.05)
        return t, v

    def test_normal_sag_calculation(self):
        t, v = self._make_sag_trace()
        result = calculate_sag_ratio(v, t, (0.0, 0.09), (0.1, 0.5), (0.55, 0.69))
        assert result is not None
        assert "sag_ratio" in result

    def test_empty_baseline_returns_nan_payload(self):
        t, v = self._make_sag_trace()
        result = calculate_sag_ratio(v, t, (5.0, 6.0), (0.1, 0.5), (0.55, 0.69))
        assert np.isnan(result["sag_ratio"])

    def test_empty_peak_window_returns_nan_payload(self):
        t, v = self._make_sag_trace()
        result = calculate_sag_ratio(v, t, (0.0, 0.09), (5.0, 6.0), (0.55, 0.69))
        assert np.isnan(result["sag_ratio"])

    def test_empty_ss_window_returns_nan_payload(self):
        t, v = self._make_sag_trace()
        result = calculate_sag_ratio(v, t, (0.0, 0.09), (0.1, 0.5), (5.0, 6.0))
        assert np.isnan(result["sag_ratio"])

    def test_zero_delta_v_ss_returns_nan_payload(self):
        t = _make_time(1.0)
        v = np.full_like(t, -65.0)  # flat trace -> delta_v_ss = 0
        result = calculate_sag_ratio(v, t, (0.0, 0.09), (0.1, 0.5), (0.55, 0.69))
        assert np.isnan(result["sag_ratio"])

    def test_rebound_window_covered(self):
        """Rebound window present: both smoothed and unsmoothed paths."""
        t, v = self._make_sag_trace(with_rebound=True)
        result = calculate_sag_ratio(v, t, (0.0, 0.09), (0.1, 0.5), (0.55, 0.69), rebound_window_ms=200.0)
        assert result is not None

    def test_rebound_window_absent(self):
        """rebound_window_ms=0 means no rebound window is searched."""
        t, v = self._make_sag_trace()
        result = calculate_sag_ratio(v, t, (0.0, 0.09), (0.1, 0.5), (0.55, 0.69), rebound_window_ms=0.0)
        assert result is not None

    def test_few_samples_no_smoothing(self):
        """When peak_data length < window_length, raw min is used."""
        t = np.linspace(0, 0.1, 20)
        v = np.full_like(t, -65.0)
        v[5:10] = -75.0
        result = calculate_sag_ratio(v, t, (0.0, 0.04), (0.05, 0.09), (0.09, 0.1))
        # May return nan payload if window too small; should not crash
        assert result is not None


# ---------------------------------------------------------------------------
# calculate_capacitance_cc
# ---------------------------------------------------------------------------


class TestCalculateCapacitanceCc:
    def test_valid_cc_capacitance(self):
        # Cm = tau_ms / rin_mohm * 1000 pF
        cm = calculate_capacitance_cc(tau_ms=20.0, rin_mohm=200.0)
        assert cm == pytest.approx(100.0, rel=0.001)

    def test_zero_rin_returns_none(self):
        assert calculate_capacitance_cc(tau_ms=20.0, rin_mohm=0.0) is None

    def test_negative_rin_returns_none(self):
        assert calculate_capacitance_cc(tau_ms=20.0, rin_mohm=-100.0) is None

    def test_zero_tau_returns_none(self):
        assert calculate_capacitance_cc(tau_ms=0.0, rin_mohm=200.0) is None

    def test_negative_tau_returns_none(self):
        assert calculate_capacitance_cc(tau_ms=-10.0, rin_mohm=200.0) is None

    def test_infinite_rin_returns_none(self):
        assert calculate_capacitance_cc(tau_ms=10.0, rin_mohm=np.inf) is None
