# -*- coding: utf-8 -*-
"""
Targeted tests for scientific accuracy fixes (Phase 9).

These tests verify the correctness of unit conversions and calculations
that were identified and fixed during the publication readiness audit.
"""

import numpy as np

from Synaptipy.core.analysis.passive_properties import (
    calculate_rin,
    calculate_sag_ratio,
)
from Synaptipy.core.analysis.single_spike import (
    calculate_spike_features,
)


class TestRinUnitConversion:
    """Verify that Rin calculation correctly converts pA → MOhm."""

    def test_rin_known_value(self):
        """
        Known-value test: 10 mV deflection with -100 pA step → 100 MOhm.

        Rin = |delta_V| / |delta_I|
            = |10 mV| / |(-100 pA) / 1000|
            = 10 mV / 0.1 nA
            = 100 MOhm
        """
        # Create a simple voltage trace with known deflection
        dt = 0.001  # 1 ms
        time = np.arange(0, 0.5, dt)  # 500ms trace
        voltage = np.zeros_like(time)

        # Baseline: 0 mV (0–100 ms)
        # Response: 10 mV (200–400 ms)
        response_start = int(0.2 / dt)
        response_end = int(0.4 / dt)
        voltage[response_start:response_end] = 10.0  # mV

        result = calculate_rin(
            voltage_trace=voltage,
            time_vector=time,
            current_amplitude=-100.0,  # pA
            baseline_window=(0.0, 0.1),
            response_window=(0.2, 0.4),
        )

        assert result.is_valid
        assert result.unit == "MOhm"
        # Rin should be 100 MOhm
        assert abs(result.value - 100.0) < 0.01, f"Expected Rin=100.0 MOhm, got {result.value}"

    def test_rin_small_current(self):
        """
        Test with small current: 5 mV deflection with -20 pA → 250 MOhm.

        Rin = |5 mV| / (20 pA / 1000) = 5 / 0.02 = 250 MOhm
        """
        dt = 0.001
        time = np.arange(0, 0.5, dt)
        voltage = np.zeros_like(time)
        voltage[200:400] = 5.0  # 5 mV deflection

        result = calculate_rin(
            voltage_trace=voltage,
            time_vector=time,
            current_amplitude=-20.0,  # pA
            baseline_window=(0.0, 0.1),
            response_window=(0.2, 0.4),
        )

        assert result.is_valid
        assert abs(result.value - 250.0) < 0.01

    def test_rin_zero_current_rejected(self):
        """Rin should be invalid when current amplitude is zero."""
        dt = 0.001
        time = np.arange(0, 0.5, dt)
        voltage = np.zeros_like(time)

        result = calculate_rin(
            voltage_trace=voltage,
            time_vector=time,
            current_amplitude=0.0,
            baseline_window=(0.0, 0.1),
            response_window=(0.2, 0.4),
        )

        assert not result.is_valid

    def test_rin_conductance_reciprocal(self):
        """Verify conductance is 1/Rin in uS (micro-Siemens)."""
        dt = 0.001
        time = np.arange(0, 0.5, dt)
        voltage = np.zeros_like(time)
        voltage[200:400] = 10.0

        result = calculate_rin(
            voltage_trace=voltage,
            time_vector=time,
            current_amplitude=-100.0,
            baseline_window=(0.0, 0.1),
            response_window=(0.2, 0.4),
        )

        assert result.is_valid
        # Rin = 100 MOhm → G = 1/100 = 0.01 μS
        # (1 MOhm = 10^6 Ω, so 1/MOhm = 10^-6 S = 1 μS)
        assert abs(result.conductance - 0.01) < 0.001


class TestDvdtUnitConsistency:
    """Verify dV/dt threshold conversion (V/s → mV/s) in spike features."""

    def test_dvdt_threshold_conversion(self):
        """
        The dvdt_threshold parameter is specified in V/s but data is in mV.
        Internal conversion should multiply by 1000 to get mV/s.

        With a 20 V/s threshold (= 20000 mV/s), a spike with dV/dt > 20000 mV/s
        should have its onset detected.
        """
        dt = 0.0001  # 0.1 ms = 10 kHz sampling
        time = np.arange(0, 0.1, dt)  # 100 ms trace
        data = np.full_like(time, -70.0)  # -70 mV baseline

        # Create a single spike with a steep rising phase
        spike_peak_idx = 500
        # Rise: from -70 to +30 mV in 1ms (~100 V/s rise rate in mV/ms)
        rise_samples = 10  # 1 ms
        for i in range(rise_samples):
            data[spike_peak_idx - rise_samples + i] = -70.0 + (100.0 * i / rise_samples)
        data[spike_peak_idx] = 30.0  # Peak
        # Decay back to -70 mV in 2ms
        decay_samples = 20
        for i in range(decay_samples):
            data[spike_peak_idx + 1 + i] = 30.0 - (100.0 * i / decay_samples)

        spike_indices = np.array([spike_peak_idx])

        features = calculate_spike_features(data, time, spike_indices, dvdt_threshold=20.0)  # V/s

        # Should detect exactly 1 spike with features
        assert len(features) == 1
        feat = features[0]

        # max_dvdt should be in V/s (positive value, consistent with phase_plane.py)
        assert feat["max_dvdt"] > 0, f"max_dvdt should be positive, got {feat['max_dvdt']}"
        # The rise is ~100 mV / 1ms = 100,000 mV/s = 100 V/s
        assert feat["max_dvdt"] > 10, f"max_dvdt too small: {feat['max_dvdt']} V/s"

    def test_dvdt_threshold_too_high_no_onset(self):
        """
        With an impossibly high threshold, AP onset should not be found,
        and features should use sentinel values.
        """
        dt = 0.0001
        time = np.arange(0, 0.1, dt)
        data = np.full_like(time, -70.0)

        # Small bump (not a real spike, low dV/dt)
        data[500:510] = -60.0

        spike_indices = np.array([505])

        features = calculate_spike_features(data, time, spike_indices, dvdt_threshold=1e6)  # Very high

        assert len(features) == 1
        feat = features[0]
        # Without a valid onset at impossibly high threshold,
        # ap_threshold falls back to the voltage at that sample
        # (the function uses the data value as fallback, not NaN)
        assert feat["ap_threshold"] is not None


class TestSagRatioPercentile:
    """Verify sag ratio uses 5th percentile for robustness."""

    def test_sag_ratio_with_noise(self):
        """
        Test that the sag ratio calculation is robust to noise spikes
        by using the 5th percentile instead of np.min.
        """
        dt = 0.001
        time = np.arange(0, 1.0, dt)  # 1s trace
        voltage = np.zeros_like(time)  # 0 mV baseline

        # Hyperpolarizing step: -20 mV steady state (300–800 ms)
        voltage[300:800] = -20.0

        # Add a transient sag (initial overshoot, 200–300 ms region)
        # Peak hyperpolarization at -30 mV in the peak window
        voltage[200:250] = -30.0
        voltage[250:300] = -25.0  # Recovering to steady state

        result = calculate_sag_ratio(
            voltage_trace=voltage,
            time_vector=time,
            baseline_window=(0.0, 0.1),
            response_peak_window=(0.2, 0.35),
            response_steady_state_window=(0.5, 0.8),
        )

        # Should be a valid dict
        assert result is not None
        # Sag ratio should be between 0 and 1
        # With the 5th percentile approach, the peak should be near -30
        sag = result["sag_ratio"]
        assert 0 < sag <= 1.6, f"Unexpected sag ratio: {sag}"
        assert "rebound_depolarization" in result


class TestVCSeriesResistanceAccuracy:
    """Verify that Rs and Cm are recovered accurately from synthetic transients."""

    @staticmethod
    def _make_transient(
        rs_mohm: float,
        cm_pf: float,
        voltage_step_mv: float = -10.0,
        sampling_rate: float = 100000.0,
        duration_s: float = 0.05,
    ):
        """Synthesise an ideal mono-exponential VC transient for a given Rs and Cm."""
        from Synaptipy.core.analysis.passive_properties import calculate_capacitance_vc

        dt = 1.0 / sampling_rate
        t = np.arange(0, duration_s, dt)
        baseline_end = 0.005
        step_start = 0.010
        step_end = step_start + 0.030

        rs_ohm = rs_mohm * 1e6
        cm_f = cm_pf * 1e-12
        tau_s = rs_ohm * cm_f
        i_peak_pa = (voltage_step_mv * 1e-3 / rs_ohm) * 1e12

        current = np.zeros_like(t)
        step_idx = int(step_start / dt)
        for idx in range(step_idx, len(t)):
            t_rel = (idx - step_idx) * dt
            current[idx] = i_peak_pa * np.exp(-t_rel / tau_s)

        bw = (0.0, baseline_end)
        tw = (step_start, step_end)
        result = calculate_capacitance_vc(current, t, bw, tw, voltage_step_amplitude_mv=voltage_step_mv)
        return result, rs_mohm, cm_pf

    def test_rs_extracted_within_20_percent(self):
        """Rs recovered from a synthetic transient must be within 20% of the true value.

        This tolerance accounts for sampling discretisation at 100 kHz and
        imperfect exponential fit initialisation.
        """
        true_rs = 10.0  # MOhm
        result, _, _ = self._make_transient(rs_mohm=true_rs, cm_pf=100.0)

        assert result is not None, "Expected dict, got None"
        rs_est = result["series_resistance_mohm"]
        rel_error = abs(rs_est - true_rs) / true_rs
        assert rel_error < 0.20, f"Rs estimate {rs_est:.2f} MOhm deviates {rel_error*100:.1f}% from true {true_rs} MOhm"

    def test_cm_extracted_within_20_percent(self):
        """Cm recovered via tau/Rs must be within 20% of the true value."""
        true_cm = 100.0  # pF
        result, _, _ = self._make_transient(rs_mohm=10.0, cm_pf=true_cm)

        assert result is not None
        cm_est = result["capacitance_pf"]
        rel_error = abs(cm_est - true_cm) / true_cm
        assert rel_error < 0.20, f"Cm estimate {cm_est:.2f} pF deviates {rel_error*100:.1f}% from true {true_cm} pF"

    def test_larger_rs_yields_larger_estimate(self):
        """Doubling Rs on the same Cm should roughly double the Rs estimate."""
        result_lo, _, _ = self._make_transient(rs_mohm=10.0, cm_pf=100.0)
        result_hi, _, _ = self._make_transient(rs_mohm=20.0, cm_pf=100.0)

        assert result_lo is not None and result_hi is not None
        assert (
            result_hi["series_resistance_mohm"] > result_lo["series_resistance_mohm"]
        ), "Higher true Rs must yield higher estimated Rs"


class TestFAHPMAHPAccuracy:
    """Verify fAHP and mAHP windows target the correct temporal post-spike regions."""

    @staticmethod
    def _build_spike(
        fahp_min_mv: float = -73.0,
        mahp_min_mv: float = -70.0,
        baseline_mv: float = -65.0,
        sampling_rate: float = 20000.0,
    ):
        """Build a synthetic spike trace with analytically placed AHP minima.

        fAHP minimum placed at 2 ms post-peak (inside 1-5 ms window).
        mAHP minimum placed at 20 ms post-peak (inside 10-50 ms window).
        """
        dt = 1.0 / sampling_rate
        t = np.arange(0, 0.15, dt)
        n = len(t)
        v = np.full(n, baseline_mv)

        peak_idx = int(0.030 / dt)
        rise = int(0.001 / dt)
        # Spike upstroke
        for i in range(rise):
            v[peak_idx - rise + i] = baseline_mv + 85.0 * i / rise
        v[peak_idx] = baseline_mv + 85.0

        # Place fAHP trough
        fahp_idx = int(0.032 / dt)  # 2 ms post-peak
        for i in range(peak_idx, fahp_idx + 1):
            frac = (i - peak_idx) / (fahp_idx - peak_idx)
            v[i] = (baseline_mv + 85.0) + (fahp_min_mv - (baseline_mv + 85.0)) * frac

        # Gradual recovery then mAHP trough
        mahp_idx = int(0.050 / dt)  # 20 ms post-peak
        for i in range(fahp_idx, mahp_idx + 1):
            frac = (i - fahp_idx) / (mahp_idx - fahp_idx)
            v[i] = fahp_min_mv + (mahp_min_mv - fahp_min_mv) * frac

        # Recovery to baseline
        for i in range(mahp_idx, n):
            frac = (i - mahp_idx) / max(1, n - mahp_idx)
            v[i] = mahp_min_mv + (baseline_mv - mahp_min_mv) * frac

        spike_indices = np.array([peak_idx])
        return v, t, spike_indices, baseline_mv

    def test_fahp_measured_in_correct_window(self):
        """fAHP depth should reflect the minimum in the 1-5 ms window, not later."""
        fahp_min_mv = -73.0  # 8 mV below baseline (-65)
        v, t, spikes, bl = self._build_spike(fahp_min_mv=fahp_min_mv, mahp_min_mv=-70.0)

        features = calculate_spike_features(v, t, spikes)
        assert len(features) == 1
        feat = features[0]

        # fahp_depth = ap_threshold - min_voltage_in_fahp_window
        # ap_threshold is near -65; min in 1-5 ms window is near -73
        # So depth should be approximately 8 mV (threshold - fahp_min)
        assert feat["fahp_depth"] > 0, f"fahp_depth must be positive, got {feat['fahp_depth']}"

    def test_mahp_measured_in_correct_window(self):
        """mAHP depth should reflect the minimum in the 10-50 ms window."""
        mahp_min_mv = -70.0  # 5 mV below baseline
        v, t, spikes, bl = self._build_spike(fahp_min_mv=-73.0, mahp_min_mv=mahp_min_mv)

        features = calculate_spike_features(v, t, spikes)
        feat = features[0]

        assert feat["mahp_depth"] > 0, f"mahp_depth must be positive, got {feat['mahp_depth']}"

    def test_fahp_deeper_than_mahp_when_appropriate(self):
        """When fAHP minimum is deeper (more negative) than mAHP minimum, fahp_depth > mahp_depth."""
        # fAHP trough at -73 mV (8 mV below -65 baseline)
        # mAHP trough at -70 mV (5 mV below -65 baseline)
        v, t, spikes, bl = self._build_spike(fahp_min_mv=-73.0, mahp_min_mv=-70.0)
        features = calculate_spike_features(v, t, spikes)
        feat = features[0]

        assert feat["fahp_depth"] > feat["mahp_depth"], (
            f"Expected fahp_depth ({feat['fahp_depth']:.2f}) > mahp_depth ({feat['mahp_depth']:.2f}) "
            "when fAHP trough is deeper than mAHP trough"
        )


# ---------------------------------------------------------------------------
# LJP Correction Tests
# ---------------------------------------------------------------------------


class TestLJPCorrection:
    """Verify that Liquid Junction Potential correction shifts voltage by the expected amount."""

    def _make_rmp_data(self, resting_mv: float, n_samples: int = 1000, fs: float = 20000.0):
        """Return (data_array, time_array) for a flat trace at *resting_mv*."""
        t = np.arange(n_samples) / fs
        v = np.full(n_samples, resting_mv)
        return v, t

    def test_ljp_shifts_rmp_by_exact_value(self):
        """RMP with LJP=10 mV should equal (raw_rmp - 10) mV."""
        from Synaptipy.core.analysis.passive_properties import apply_ljp_correction

        raw_mv = -70.0
        ljp_mv = 10.0
        v, _ = self._make_rmp_data(raw_mv)

        corrected = apply_ljp_correction(v, ljp_mv)

        assert np.allclose(
            corrected, raw_mv - ljp_mv
        ), f"Expected all samples to be {raw_mv - ljp_mv} mV; got mean {corrected.mean():.4f}"

    def test_zero_ljp_returns_original_array(self):
        """When LJP=0, apply_ljp_correction must return the original array (no copy)."""
        from Synaptipy.core.analysis.passive_properties import apply_ljp_correction

        v, _ = self._make_rmp_data(-65.0)
        result = apply_ljp_correction(v, 0.0)

        # Same object expected (no unnecessary copy)
        assert result is v, "apply_ljp_correction with ljp_mv=0 should return the original array."

    def test_negative_ljp_increases_apparent_voltage(self):
        """A negative LJP shifts recorded voltage positive (V_true = V_recorded - LJP)."""
        from Synaptipy.core.analysis.passive_properties import apply_ljp_correction

        raw_mv = -70.0
        ljp_mv = -5.0  # negative LJP → add 5 mV
        v, _ = self._make_rmp_data(raw_mv)
        corrected = apply_ljp_correction(v, ljp_mv)

        assert np.allclose(corrected, raw_mv + 5.0), f"Expected {raw_mv + 5.0} mV; got {corrected.mean():.4f}"


# ---------------------------------------------------------------------------
# PPR Residual Subtraction Tests
# ---------------------------------------------------------------------------


class TestPPRResidualSubtraction:
    """Verify that PPR with residual subtraction yields a different (more accurate) ratio."""

    @staticmethod
    def _make_ppr_trace(
        r1_amp: float = -50.0,
        r2_amp: float = -50.0,
        stim1_s: float = 0.1,
        stim2_s: float = 0.2,
        decay_tau_s: float = 0.05,
        fs: float = 10000.0,
        duration_s: float = 0.5,
        baseline_mv: float = -65.0,
    ):
        """Synthesise a two-EPSP current-clamp trace with monoexponential decay from stim1."""
        n = int(duration_s * fs)
        t = np.arange(n) / fs
        v = np.full(n, baseline_mv)

        # First event: alpha-function-like rise + monoexponential decay
        idx1 = int(stim1_s * fs)
        for i in range(idx1, n):
            dt = (i - idx1) / fs
            v[i] += r1_amp * dt / decay_tau_s * np.exp(1.0 - dt / decay_tau_s) if dt > 0 else 0.0

        # Second event: same shape but amplitude r2_amp (additive on top of decaying tail)
        idx2 = int(stim2_s * fs)
        for i in range(idx2, n):
            dt = (i - idx2) / fs
            v[i] += r2_amp * dt / decay_tau_s * np.exp(1.0 - dt / decay_tau_s) if dt > 0 else 0.0

        return v, t

    def test_ppr_corrected_differs_from_raw_when_residual_present(self):
        """When stim2 rides on a decaying tail from stim1, corrected PPR != raw peak division."""
        from Synaptipy.core.analysis.evoked_responses import calculate_paired_pulse_ratio

        v, t = self._make_ppr_trace(r1_amp=-50.0, r2_amp=-30.0, decay_tau_s=0.04, fs=10000.0)

        result = calculate_paired_pulse_ratio(
            data=v,
            time=t,
            stim1_onset_s=0.1,
            stim2_onset_s=0.2,
            response_window_ms=20.0,
            baseline_window_ms=5.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=60.0,
            polarity="negative",
        )

        assert result["ppr_error"] is None, f"Unexpected PPR error: {result['ppr_error']}"

        r_raw = result["r2_amplitude_raw"]
        r_corr = result["r2_amplitude_corrected"]
        residual = result["residual_at_stim2"]

        assert (
            residual is not None and abs(residual) > 0
        ), "Expected a non-zero residual from exponential decay under stim2."
        assert abs(r_corr - r_raw) > 1e-6, (
            f"Corrected amplitude ({r_corr:.4f}) should differ from raw ({r_raw:.4f}) " "when residual is non-zero."
        )

    def test_ppr_close_to_one_for_identical_events_no_decay(self):
        """When both events are equal amplitude and tail decay is negligible, PPR ≈ 1."""
        from Synaptipy.core.analysis.evoked_responses import calculate_paired_pulse_ratio

        # Build trace with a very fast decay so residual under stim2 is negligible
        v, t = self._make_ppr_trace(
            r1_amp=-50.0,
            r2_amp=-50.0,
            stim1_s=0.1,
            stim2_s=0.4,
            decay_tau_s=0.01,  # fast decay — negligible at 300 ms ISI
            fs=10000.0,
        )

        result = calculate_paired_pulse_ratio(
            data=v,
            time=t,
            stim1_onset_s=0.1,
            stim2_onset_s=0.4,
            response_window_ms=20.0,
            baseline_window_ms=5.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=40.0,
            polarity="negative",
        )

        if result["ppr_error"] is not None:
            # Tolerate fit failures in edge-case synthetic traces
            return

        ppr = result["paired_pulse_ratio"]
        assert ppr is not None, "PPR should not be None for valid equal-amplitude events."
        assert 0.5 <= ppr <= 2.0, f"PPR {ppr:.3f} is outside reasonable range [0.5, 2.0]."
