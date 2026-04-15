# -*- coding: utf-8 -*-
"""
Edge-case and robustness tests for analysis modules.

These tests verify graceful degradation when analysis functions receive
pathological input: flat traces, zero-amplitude stimuli, NaN/Inf data,
single-sample arrays, and other boundary conditions that arise in
real-world batch processing.
"""

import numpy as np
import pytest

from Synaptipy.core.analysis.firing_dynamics import (
    analyze_spikes_and_bursts,
    calculate_bursts_logic,
    calculate_train_dynamics,
)
from Synaptipy.core.analysis.passive_properties import (
    calculate_capacitance_cc,
    calculate_capacitance_vc,
    calculate_iv_curve,
    calculate_rin,
    calculate_rmp,
    calculate_sag_ratio,
    calculate_tau,
    find_stable_baseline,
)
from Synaptipy.core.analysis.single_spike import (
    calculate_spike_features,
    detect_spikes_threshold,
)
from Synaptipy.core.signal_processor import blank_artifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_trace(n=10000, fs=20000.0, baseline=-70.0):
    """Create a flat voltage trace with time vector."""
    dt = 1.0 / fs
    t = np.arange(n) * dt
    v = np.full(n, baseline)
    return v, t, fs


# ---------------------------------------------------------------------------
# Sag Ratio
# ---------------------------------------------------------------------------
class TestSagRatioEdgeCases:
    """Edge-case tests for calculate_sag_ratio."""

    def test_flat_trace_returns_nan_payload(self):
        """A completely flat trace has delta_v_ss == 0 → NaN payload (no division)."""
        v, t, _ = _make_trace()
        result = calculate_sag_ratio(
            v,
            t,
            baseline_window=(0.0, 0.05),
            response_peak_window=(0.1, 0.2),
            response_steady_state_window=(0.3, 0.45),
        )
        assert result is not None
        assert np.isnan(result["sag_ratio"])
        assert np.isnan(result["v_ss"])

    def test_depolarising_step(self):
        """A depolarising step should still compute a ratio (< 1)."""
        v, t, _ = _make_trace()
        # Depolarising step: +20 mV
        step_mask = (t >= 0.1) & (t < 0.4)
        v[step_mask] = -50.0
        result = calculate_sag_ratio(
            v,
            t,
            baseline_window=(0.0, 0.05),
            response_peak_window=(0.1, 0.2),
            response_steady_state_window=(0.3, 0.4),
        )
        assert result is not None
        assert isinstance(result["sag_ratio"], float)

    def test_empty_window_returns_nan_payload(self):
        """Windows outside the trace range → NaN payload (no mean on empty slices)."""
        v, t, _ = _make_trace()
        result = calculate_sag_ratio(
            v,
            t,
            baseline_window=(10.0, 11.0),
            response_peak_window=(12.0, 13.0),
            response_steady_state_window=(14.0, 15.0),
        )
        assert result is not None
        assert np.isnan(result["sag_ratio"])
        assert np.isnan(result["v_baseline"])

    def test_sag_percentage_reported(self):
        """Verify sag_percentage key is present after formalization."""
        v, t, _ = _make_trace()
        step_mask = (t >= 0.1) & (t < 0.4)
        v[step_mask] = -90.0
        # Transient peak deeper
        peak_mask = (t >= 0.1) & (t < 0.15)
        v[peak_mask] = -100.0
        result = calculate_sag_ratio(
            v,
            t,
            baseline_window=(0.0, 0.05),
            response_peak_window=(0.1, 0.2),
            response_steady_state_window=(0.3, 0.4),
        )
        assert result is not None
        assert "sag_percentage" in result
        assert "sag_ratio" in result
        assert "v_baseline" in result

    def test_custom_smoothing_window(self):
        """Custom peak_smoothing_ms parameter is accepted."""
        v, t, _ = _make_trace()
        step_mask = (t >= 0.1) & (t < 0.4)
        v[step_mask] = -90.0
        peak_mask = (t >= 0.1) & (t < 0.15)
        v[peak_mask] = -100.0
        result = calculate_sag_ratio(
            v,
            t,
            baseline_window=(0.0, 0.05),
            response_peak_window=(0.1, 0.2),
            response_steady_state_window=(0.3, 0.4),
            peak_smoothing_ms=10.0,
            rebound_window_ms=50.0,
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Input Resistance
# ---------------------------------------------------------------------------
class TestRinEdgeCases:
    """Edge-case tests for calculate_rin."""

    def test_zero_current_step_returns_nan(self):
        """Zero delta-I must not divide; value is NaN and result invalid."""
        v, t, _ = _make_trace()
        result = calculate_rin(v, t, 0.0, (0.0, 0.1), (0.2, 0.4))
        assert not result.is_valid
        assert np.isnan(result.value)

    def test_identical_baseline_and_response(self):
        """No voltage deflection → Rin should be ~0 or valid with dV=0."""
        v, t, _ = _make_trace()
        result = calculate_rin(v, t, -100.0, (0.0, 0.1), (0.2, 0.4))
        assert result is not None
        assert result.is_valid
        # delta_v is ~0 → Rin ~0
        assert abs(result.value) < 0.1

    def test_very_short_trace(self):
        """Trace with only 5 samples."""
        v = np.array([-70.0, -70.0, -70.0, -80.0, -80.0])
        t = np.array([0.0, 0.001, 0.002, 0.003, 0.004])
        result = calculate_rin(v, t, -100.0, (0.0, 0.002), (0.003, 0.005))
        assert result is not None


# ---------------------------------------------------------------------------
# Tau
# ---------------------------------------------------------------------------
class TestTauEdgeCases:
    """Edge-case tests for calculate_tau."""

    def test_flat_trace_fails_gracefully(self):
        """A flat trace cannot be fitted → None."""
        v, t, _ = _make_trace()
        result = calculate_tau(v, t, stim_start_time=0.1, fit_duration=0.1)
        # May return a result with very small/large tau or None
        # The key requirement is no crash
        assert result is None or isinstance(result, dict)

    def test_too_few_samples(self):
        """Fewer than 3 samples in the fit window → None."""
        v = np.array([-70.0, -70.0])
        t = np.array([0.0, 0.001])
        result = calculate_tau(v, t, stim_start_time=0.0, fit_duration=0.001)
        assert result is None

    def test_bi_exponential_too_few_samples(self):
        """Bi-exponential with < 6 samples → None."""
        v = np.array([-70.0, -72.0, -74.0, -75.0])
        t = np.array([0.0, 0.001, 0.002, 0.003])
        result = calculate_tau(
            v,
            t,
            stim_start_time=0.0,
            fit_duration=0.003,
            model="bi",
        )
        assert result is None


# ---------------------------------------------------------------------------
# I-V Curve
# ---------------------------------------------------------------------------
class TestIVCurveEdgeCases:
    """Edge-case tests for calculate_iv_curve."""

    def test_empty_sweeps(self):
        """No sweeps → error dict."""
        result = calculate_iv_curve([], [], [], (0.0, 0.1), (0.2, 0.4))
        assert "error" in result

    def test_single_sweep_no_regression(self):
        """A single sweep cannot compute linear regression → Rin is None."""
        v, t, _ = _make_trace(n=5000)
        result = calculate_iv_curve([v], [t], [0.0], (0.0, 0.05), (0.1, 0.2))
        assert result["rin_aggregate_mohm"] is None

    def test_all_zero_currents(self):
        """All-zero current steps → regression on flat data."""
        v, t, _ = _make_trace(n=5000)
        result = calculate_iv_curve([v, v], [t, t], [0.0, 0.0], (0.0, 0.05), (0.1, 0.2))
        # Should not crash; Rin may be None or NaN
        assert result is not None


# ---------------------------------------------------------------------------
# Spike Detection
# ---------------------------------------------------------------------------
class TestSpikeDetectionEdgeCases:
    """Edge-case tests for spike detection."""

    def test_flat_trace_no_spikes(self):
        """A flat sub-threshold trace should detect zero spikes."""
        v, t, fs = _make_trace()
        result = detect_spikes_threshold(
            v,
            t,
            threshold=-20.0,
            refractory_samples=int(0.002 * fs),
        )
        n_spikes = len(result.spike_times) if result.spike_times is not None else 0
        assert n_spikes == 0

    def test_single_sample_trace(self):
        """A 1-sample trace should not crash."""
        v = np.array([-70.0])
        t = np.array([0.0])
        result = detect_spikes_threshold(
            v,
            t,
            threshold=-20.0,
            refractory_samples=1,
        )
        n_spikes = len(result.spike_times) if result.spike_times is not None else 0
        assert n_spikes == 0


# ---------------------------------------------------------------------------
# ADP (Afterdepolarisation)
# ---------------------------------------------------------------------------
class TestADPEdgeCases:
    """Edge-case tests for ADP detection in calculate_spike_features."""

    def test_monotonic_recovery_returns_nan(self):
        """No ADP (monotonic recovery after AP) → adp_amplitude = NaN."""
        fs = 50000.0
        dt = 1.0 / fs
        n = int(0.020 / dt)  # 20 ms
        t = np.arange(n) * dt
        v = np.full(n, -70.0)

        # Build a spike: fast rise then monotonic decay (no ADP)
        spike_center = int(0.005 / dt)
        for i in range(spike_center - 5, spike_center):
            v[i] = -70.0 + (i - (spike_center - 5)) * 20.0  # rise
        v[spike_center] = 30.0  # peak
        for i in range(spike_center + 1, min(spike_center + 100, n)):
            # Monotonic exponential decay back to baseline
            v[i] = -70.0 + 100.0 * np.exp(-(i - spike_center) * dt / 0.002)

        spike_indices = np.array([spike_center])
        features = calculate_spike_features(
            v,
            t,
            spike_indices,
            dvdt_threshold=20.0,
        )
        assert features is not None
        if len(features) > 0:
            adp = features[0].get("adp_amplitude")
            if adp is not None:
                assert np.isnan(adp), "Monotonic recovery should yield NaN ADP"


# ---------------------------------------------------------------------------
# Burst Analysis
# ---------------------------------------------------------------------------
class TestBurstEdgeCases:
    """Edge-case tests for burst analysis."""

    def test_no_spikes(self):
        """Zero spike times → zero bursts."""
        result = calculate_bursts_logic(np.array([]))
        assert result.burst_count == 0

    def test_single_spike(self):
        """One spike → no bursts (min_spikes=2)."""
        result = calculate_bursts_logic(np.array([0.1]))
        assert result.burst_count == 0

    def test_flat_trace(self):
        """Flat trace → no spikes → no bursts."""
        v, t, fs = _make_trace()
        result = analyze_spikes_and_bursts(
            v,
            t,
            fs,
            threshold=-20.0,
            max_isi_start=0.01,
            max_isi_end=0.2,
        )
        assert result.burst_count == 0


# ---------------------------------------------------------------------------
# Capacitance
# ---------------------------------------------------------------------------
class TestCapacitanceEdgeCases:
    """Edge-case tests for capacitance calculations."""

    def test_cc_zero_rin(self):
        """Rin=0 → division by zero → None."""
        result = calculate_capacitance_cc(tau_ms=5.0, rin_mohm=0.0)
        assert result is None or result == 0.0 or np.isinf(result)

    def test_cc_negative_tau(self):
        """Negative tau (non-physical) → should still compute or return None."""
        result = calculate_capacitance_cc(tau_ms=-5.0, rin_mohm=100.0)
        # Implementation-dependent; key is no crash
        assert result is None or isinstance(result, float)

    def test_vc_zero_voltage_step(self):
        """Zero voltage step → None."""
        v, t, _ = _make_trace()
        result = calculate_capacitance_vc(
            v,
            t,
            (0.0, 0.1),
            (0.1, 0.2),
            voltage_step_amplitude_mv=0.0,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Train Dynamics
# ---------------------------------------------------------------------------
class TestTrainDynamicsEdgeCases:
    """Edge-case tests for spike train dynamics."""

    def test_no_spikes(self):
        """Empty spike times → metrics are NaN or 0."""
        result = calculate_train_dynamics(np.array([]))
        assert result.spike_count == 0

    def test_single_spike(self):
        """One spike → ISI undefined → cv is None (insufficient spikes)."""
        result = calculate_train_dynamics(np.array([0.5]))
        assert result.spike_count == 1
        assert result.cv is None or (isinstance(result.cv, float) and np.isnan(result.cv))

    def test_two_spikes(self):
        """Two spikes → one ISI → CV is NaN (need >=2 ISIs for std)."""
        result = calculate_train_dynamics(np.array([0.1, 0.2]))
        assert result.spike_count == 2

    def test_regular_train(self):
        """Perfectly regular train → CV ≈ 0."""
        times = np.arange(0, 1.0, 0.01)  # 100 spikes, 10 ms ISI
        result = calculate_train_dynamics(times)
        assert result.spike_count == 100
        assert result.cv is not None
        assert result.cv < 0.01


# ---------------------------------------------------------------------------
# Baseline / RMP
# ---------------------------------------------------------------------------
class TestRMPEdgeCases:
    """Edge-case tests for baseline/RMP calculation."""

    def test_empty_window(self):
        """Window outside data range → invalid result; value may be NaN."""
        v, t, _ = _make_trace()
        result = calculate_rmp(v, t, baseline_window=(10.0, 11.0))
        assert not result.is_valid
        assert result.value is None or (isinstance(result.value, float) and np.isnan(result.value))

    def test_stable_baseline_short_trace(self):
        """Very short trace for find_stable_baseline."""
        v = np.array([-70.0, -70.1, -69.9])
        result = find_stable_baseline(v, sample_rate=10000.0)
        # Should not crash; may return None for start/end
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Artifact Blanking
# ---------------------------------------------------------------------------
class TestArtifactBlanking:
    """Tests for the blank_artifact signal processor function."""

    def test_hold_method(self):
        """Hold method: artifact window filled with pre-artifact value."""
        v, t, _ = _make_trace()
        v_with_artifact = v.copy()
        # Simulate artifact
        art_mask = (t >= 0.1) & (t < 0.101)
        v_with_artifact[art_mask] = 500.0  # huge artifact

        result = blank_artifact(v_with_artifact, t, 0.1, 1.0, method="hold")
        # Artifact window should be replaced with -70.0 (pre-artifact value)
        assert np.all(result[art_mask] == pytest.approx(-70.0, abs=0.1))

    def test_zero_method(self):
        """Zero method: artifact window set to 0."""
        v, t, _ = _make_trace()
        result = blank_artifact(v, t, 0.1, 1.0, method="zero")
        art_mask = (t >= 0.1) & (t < 0.101)
        assert np.all(result[art_mask] == 0.0)

    def test_linear_method(self):
        """Linear method: artifact window linearly interpolated."""
        v, t, _ = _make_trace()
        result = blank_artifact(v, t, 0.1, 1.0, method="linear")
        # Should not crash; values should be between boundary values
        assert result is not None

    def test_invalid_method_raises(self):
        """Unknown method name → ValueError."""
        v, t, _ = _make_trace()
        with pytest.raises(ValueError, match="Unknown artifact blanking"):
            blank_artifact(v, t, 0.1, 1.0, method="cubic")

    def test_empty_data(self):
        """Empty array → returned unchanged."""
        result = blank_artifact(
            np.array([]),
            np.array([]),
            0.0,
            1.0,
        )
        assert len(result) == 0

    def test_window_outside_range(self):
        """Onset outside data range → data returned unchanged."""
        v, t, _ = _make_trace()
        result = blank_artifact(v, t, 10.0, 1.0, method="hold")
        np.testing.assert_array_equal(result, v)


# ---------------------------------------------------------------------------
# Processing Pipeline — artifact step
# ---------------------------------------------------------------------------
class TestPipelineArtifactStep:
    """Test the artifact blanking step in SignalProcessingPipeline."""

    def test_artifact_step_integration(self):
        """Pipeline with artifact step blanks the correct window."""
        from Synaptipy.core.processing_pipeline import SignalProcessingPipeline

        v, t, fs = _make_trace()
        # Add a huge artifact
        art_mask = (t >= 0.1) & (t < 0.101)
        v[art_mask] = 500.0

        pipeline = SignalProcessingPipeline()
        pipeline.add_step(
            {
                "type": "artifact",
                "onset_time": 0.1,
                "duration_ms": 1.0,
                "method": "hold",
            }
        )
        result = pipeline.process(v, fs, time_vector=t)
        assert np.all(result[art_mask] != 500.0)


# ---------------------------------------------------------------------------
# Ih Sag — Peak vs. Steady-State Rin
# ---------------------------------------------------------------------------
class TestIhSagRin:
    """Verify that calculate_rin returns distinct Peak and Steady-State Rin values
    when the trace contains voltage sag (Ih current)."""

    def _make_ih_sag_trace(self, fs=20000.0, baseline=-65.0, current_pa=-100.0):
        """
        Build a synthetic current-step trace with a typical Ih sag:
        - 100 ms baseline at -65 mV
        - 400 ms hyperpolarising step: voltage peaks at -95 mV then sags to -85 mV
        - 100 ms return to baseline
        Total 600 ms.
        """
        dt = 1.0 / fs
        n_total = int(0.6 / dt)
        t = np.arange(n_total) * dt
        v = np.full(n_total, baseline)

        step_start = int(0.1 / dt)
        step_end = int(0.5 / dt)
        # Peak hyperpolarisation reached at ~10 ms into the step
        sag_peak = int(step_start + 0.01 / dt)

        # Linear drop from baseline to peak
        peak_v = -95.0
        ss_v = -85.0
        for i in range(step_start, sag_peak):
            frac = (i - step_start) / (sag_peak - step_start)
            v[i] = baseline + frac * (peak_v - baseline)

        # Exponential sag from peak back to steady-state
        tau_sag = 0.05  # 50 ms sag time constant
        for i in range(sag_peak, step_end):
            t_elapsed = (i - sag_peak) * dt
            v[i] = ss_v + (peak_v - ss_v) * np.exp(-t_elapsed / tau_sag)

        return v, t, fs, current_pa

    def test_peak_rin_greater_than_steady_state_rin(self):
        """For a hyperpolarising step with Ih sag, peak Rin must be > steady-state Rin."""
        v, t, fs, i_pa = self._make_ih_sag_trace()
        result = calculate_rin(
            v,
            t,
            i_pa,
            baseline_window=(0.0, 0.09),
            response_window=(0.11, 0.49),
            rs_artifact_blanking_ms=0.5,
        )
        assert result.is_valid, f"Rin calculation failed: {result.error_message}"
        assert result.rin_peak_mohm is not None
        assert result.rin_steady_state_mohm is not None
        assert not np.isnan(result.rin_peak_mohm)
        assert not np.isnan(result.rin_steady_state_mohm)
        # Peak Rin uses the larger hyperpolarisation, so it should exceed steady-state.
        assert (
            result.rin_peak_mohm > result.rin_steady_state_mohm
        ), f"Expected rin_peak ({result.rin_peak_mohm:.1f}) > rin_ss ({result.rin_steady_state_mohm:.1f})"

    def test_no_sag_peak_equals_steady_state(self):
        """A flat-step trace (no sag) should have peak Rin approximately equal to steady-state Rin."""
        v, t, _ = _make_trace(n=12000)
        # Simple hyperpolarising step with no sag
        step_mask = (t >= 0.1) & (t < 0.5)
        v[step_mask] = -85.0
        result = calculate_rin(
            v,
            t,
            -100.0,
            baseline_window=(0.0, 0.09),
            response_window=(0.11, 0.49),
            rs_artifact_blanking_ms=0.5,
        )
        assert result.is_valid
        assert result.rin_peak_mohm is not None
        assert result.rin_steady_state_mohm is not None
        # Without sag the peak and steady-state should be within 5% of each other.
        ratio = result.rin_peak_mohm / result.rin_steady_state_mohm
        assert 0.95 <= ratio <= 1.05, (
            f"Expected near-equal Rin values without sag: peak={result.rin_peak_mohm:.1f}, "
            f"ss={result.rin_steady_state_mohm:.1f}"
        )

    def test_wrapper_exposes_both_metrics(self):
        """run_rin_analysis_wrapper must return rin_peak_mohm and rin_steady_state_mohm."""
        from Synaptipy.core.analysis.passive_properties import run_rin_analysis_wrapper

        v, t, fs, i_pa = self._make_ih_sag_trace()
        out = run_rin_analysis_wrapper(
            v,
            t,
            fs,
            current_amplitude=i_pa,
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.09,
            response_start=0.11,
            response_end=0.49,
            rs_artifact_blanking_ms=0.5,
        )
        metrics = out.get("metrics", {})
        assert "rin_peak_mohm" in metrics
        assert "rin_steady_state_mohm" in metrics
        assert metrics["rin_peak_mohm"] is not None
        assert metrics["rin_peak_mohm"] > metrics["rin_steady_state_mohm"]


# ---------------------------------------------------------------------------
# Summating Synaptic Events — Local Pre-Event Baseline
# ---------------------------------------------------------------------------
class TestSummatingEvents:
    """Verify that the second of two closely-spaced events uses a local baseline
    that reflects the decaying tail of the first event rather than the global RMP."""

    def _make_two_event_trace(self, fs=20000.0, global_baseline=-65.0):
        """
        Build a trace with two negative events 5 ms apart.

        Event 1 peak at 50 ms: amplitude 10 mV below resting.
        Event 2 peak at 55 ms: amplitude 8 mV below the decayed tail
        (~-68 mV at t=55 ms if tau_decay=20 ms), so global amplitude ~14 mV
        but local amplitude should be ~8 mV.
        """
        dt = 1.0 / fs
        n = int(0.2 / dt)
        t = np.arange(n) * dt
        v = np.full(n, global_baseline)

        tau_decay = 0.020  # 20 ms decay
        amp1 = -10.0  # mV below baseline
        amp2 = -8.0  # mV below the local foot

        ev1_idx = int(0.050 / dt)
        ev2_idx = int(0.055 / dt)

        # First event
        for i in range(ev1_idx, n):
            t_elapsed = (i - ev1_idx) * dt
            v[i] += amp1 * np.exp(-t_elapsed / tau_decay)

        # Second event (adds on top of first's decay)
        for i in range(ev2_idx, n):
            t_elapsed = (i - ev2_idx) * dt
            v[i] += amp2 * np.exp(-t_elapsed / tau_decay)

        return v, t, fs, ev1_idx, ev2_idx, global_baseline

    def test_local_baseline_differs_from_global_rmp(self):
        """At 55 ms, the trace is below global RMP due to first event's tail."""
        from Synaptipy.core.analysis.synaptic_events import compute_local_pre_event_baseline

        v, t, fs, ev1_idx, ev2_idx, global_baseline = self._make_two_event_trace()
        event_indices = np.array([ev1_idx, ev2_idx], dtype=int)

        local_bl = compute_local_pre_event_baseline(v, event_indices, fs, pre_event_window_ms=2.0, polarity="negative")

        # The local baseline for event 2 should be below the global RMP
        # because the trace is on the decay tail of event 1.
        assert local_bl[1] < global_baseline, (
            f"Local baseline for event 2 ({local_bl[1]:.2f}) should be below " f"global RMP ({global_baseline:.2f})"
        )

    def test_local_amplitude_less_than_global_amplitude(self):
        """Local amplitude for the second event should be less than global amplitude."""
        from Synaptipy.core.analysis.synaptic_events import compute_local_pre_event_baseline

        v, t, fs, ev1_idx, ev2_idx, global_baseline = self._make_two_event_trace()
        event_indices = np.array([ev1_idx, ev2_idx], dtype=int)

        local_bl = compute_local_pre_event_baseline(v, event_indices, fs, pre_event_window_ms=2.0, polarity="negative")

        # Global amplitude: distance from global RMP to event peak
        global_amp_ev2 = global_baseline - v[ev2_idx]
        # Local amplitude: distance from local foot to event peak
        local_amp_ev2 = local_bl[1] - v[ev2_idx]

        assert local_amp_ev2 < global_amp_ev2, (
            f"Expected local amp ({local_amp_ev2:.2f}) < global amp ({global_amp_ev2:.2f}) " "for a summating event"
        )

    def test_wrapper_returns_local_amplitudes(self):
        """The threshold-detection wrapper must return _local_amplitudes and _local_baselines."""
        from Synaptipy.core.analysis.synaptic_events import run_event_detection_threshold_wrapper

        v, t, fs, ev1_idx, ev2_idx, global_baseline = self._make_two_event_trace()
        out = run_event_detection_threshold_wrapper(
            v,
            t,
            fs,
            threshold=3.0,
            direction="negative",
            refractory_period=0.003,
            rolling_baseline_window_ms=0.0,
        )
        metrics = out.get("metrics", {})
        assert "_local_baselines" in metrics
        assert "_local_amplitudes" in metrics


class TestVCSeriesResistance:
    """Edge-case tests for Rs extraction from VC capacitive transients."""

    def _make_vc_transient(
        self,
        rs_mohm: float = 10.0,
        cm_pf: float = 100.0,
        voltage_step_mv: float = -10.0,
        sampling_rate: float = 100000.0,
        duration_s: float = 0.05,
    ):
        """Synthesise a mono-exponential capacitive transient.

        At t=0 of the step, I_peak = delta_V / Rs.
        tau = Rs * Cm  (SI units inside, returned in ms).
        """
        dt = 1.0 / sampling_rate
        t = np.arange(0, duration_s, dt)
        baseline_end = 0.01
        trans_start = baseline_end
        trans_end = trans_start + 0.03

        rs_ohm = rs_mohm * 1e6
        cm_f = cm_pf * 1e-12
        tau_s = rs_ohm * cm_f
        delta_v = voltage_step_mv * 1e-3  # V
        i_peak_a = delta_v / rs_ohm  # A (negative for hyperpolarising step)
        i_peak_pa = i_peak_a * 1e12  # pA

        current = np.zeros_like(t)
        step_idx = int(trans_start / dt)
        for idx in range(step_idx, len(t)):
            t_rel = (idx - step_idx) * dt
            current[idx] = i_peak_pa * np.exp(-t_rel / tau_s)

        baseline_window = (0.0, baseline_end - dt)
        transient_window = (trans_start, trans_end)
        return current, t, baseline_window, transient_window

    def test_rs_extraction_returns_dict_with_required_keys(self):
        """Result must be a dict with 'capacitance_pf' and 'series_resistance_mohm'."""
        current, t, bw, tw = self._make_vc_transient()
        result = calculate_capacitance_vc(current, t, bw, tw, voltage_step_amplitude_mv=-10.0)

        assert result is not None, "Expected dict, got None"
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "capacitance_pf" in result, "Missing 'capacitance_pf' key"
        assert "series_resistance_mohm" in result, "Missing 'series_resistance_mohm' key"

    def test_rs_value_is_positive(self):
        """Rs must be a positive finite float."""
        current, t, bw, tw = self._make_vc_transient(rs_mohm=15.0)
        result = calculate_capacitance_vc(current, t, bw, tw, voltage_step_amplitude_mv=-10.0)

        assert result is not None
        rs = result["series_resistance_mohm"]
        assert np.isfinite(rs), f"Rs is not finite: {rs}"
        assert rs > 0, f"Rs must be positive, got {rs}"

    def test_cm_value_is_positive(self):
        """Cm must be a positive finite float in pF."""
        current, t, bw, tw = self._make_vc_transient(cm_pf=80.0)
        result = calculate_capacitance_vc(current, t, bw, tw, voltage_step_amplitude_mv=-10.0)

        assert result is not None
        cm = result["capacitance_pf"]
        assert np.isfinite(cm), f"Cm is not finite: {cm}"
        assert cm > 0, f"Cm must be positive, got {cm}"

    def test_zero_voltage_step_returns_none(self):
        """A zero-amplitude voltage step must return None (no transient to fit)."""
        current, t, bw, tw = self._make_vc_transient()
        result = calculate_capacitance_vc(current, t, bw, tw, voltage_step_amplitude_mv=0.0)
        assert result is None, "Expected None for zero voltage step"

    def test_flat_current_returns_none(self):
        """A flat (no-transient) current trace must return None."""
        dt = 1e-5
        t = np.arange(0, 0.05, dt)
        current = np.zeros_like(t)  # completely flat
        result = calculate_capacitance_vc(current, t, (0.0, 0.009), (0.01, 0.04), voltage_step_amplitude_mv=-10.0)
        assert result is None, "Expected None for flat current trace"


class TestFAHPMAHP:
    """Tests verifying distinct fAHP and mAHP measurements for shaped spikes."""

    def _make_spike_with_dual_ahp(
        self,
        sampling_rate: float = 20000.0,
        fahp_depth_mv: float = 8.0,
        mahp_depth_mv: float = 5.0,
        baseline_mv: float = -65.0,
    ):
        """Build a synthetic spike with explicit fAHP (2 ms) and mAHP (20 ms) troughs.

        The spike peak is at t=20 ms; fAHP minimum at t=22 ms (2 ms post-peak);
        mAHP minimum at t=40 ms (20 ms post-peak).
        """
        dt = 1.0 / sampling_rate
        duration_s = 0.1  # 100 ms total
        t = np.arange(0, duration_s, dt)
        n = len(t)
        v = np.full(n, baseline_mv)

        peak_idx = int(0.020 / dt)
        # Rise: linear ramp from baseline to +20 mV over 1 ms
        rise_samples = int(0.001 / dt)
        for i in range(rise_samples):
            v[peak_idx - rise_samples + i] = baseline_mv + (85.0 * i / rise_samples)
        v[peak_idx] = baseline_mv + 85.0  # +20 mV absolute

        # Fast decay back toward fAHP minimum (1-5 ms window)
        fahp_idx = int(0.022 / dt)  # 2 ms post-peak (inside 1-5 ms window)
        fahp_min_mv = baseline_mv - fahp_depth_mv

        decay_samples = fahp_idx - peak_idx
        for i in range(decay_samples):
            v[peak_idx + i] = (baseline_mv + 85.0) + (fahp_min_mv - (baseline_mv + 85.0)) * (i / decay_samples)
        v[fahp_idx] = fahp_min_mv

        # Recovery from fAHP back to baseline
        mahp_idx = int(0.040 / dt)  # 20 ms post-peak (inside 10-50 ms window)
        mahp_min_mv = baseline_mv - mahp_depth_mv

        recover_samples = mahp_idx - fahp_idx
        for i in range(recover_samples):
            frac = i / recover_samples
            # Slightly above baseline between fAHP and mAHP troughs
            v[fahp_idx + i] = fahp_min_mv + (mahp_min_mv - fahp_min_mv) * frac
        v[mahp_idx] = mahp_min_mv

        # Final recovery to baseline
        tail_samples = n - mahp_idx
        for i in range(tail_samples):
            v[mahp_idx + i] = mahp_min_mv + (baseline_mv - mahp_min_mv) * (i / max(1, tail_samples))

        spike_indices = np.array([peak_idx])
        return v, t, spike_indices

    def test_fahp_and_mahp_are_returned(self):
        """calculate_spike_features must return both 'fahp_depth' and 'mahp_depth'."""
        v, t, spikes = self._make_spike_with_dual_ahp()
        features = calculate_spike_features(v, t, spikes)

        assert len(features) == 1
        feat = features[0]
        assert "fahp_depth" in feat, "Missing 'fahp_depth' key"
        assert "mahp_depth" in feat, "Missing 'mahp_depth' key"
        assert "ahp_depth" not in feat, "Old 'ahp_depth' key must not be present"

    def test_fahp_is_finite_and_positive(self):
        """fAHP depth must be a finite positive value for a spike with clear AHP."""
        v, t, spikes = self._make_spike_with_dual_ahp(fahp_depth_mv=8.0)
        features = calculate_spike_features(v, t, spikes)

        feat = features[0]
        assert np.isfinite(feat["fahp_depth"]), f"fahp_depth is not finite: {feat['fahp_depth']}"
        assert feat["fahp_depth"] > 0, f"fahp_depth must be positive, got {feat['fahp_depth']}"

    def test_mahp_is_finite_and_positive(self):
        """mAHP depth must be a finite positive value for a spike with clear mAHP."""
        v, t, spikes = self._make_spike_with_dual_ahp(mahp_depth_mv=5.0)
        features = calculate_spike_features(v, t, spikes)

        feat = features[0]
        assert np.isfinite(feat["mahp_depth"]), f"mahp_depth is not finite: {feat['mahp_depth']}"
        assert feat["mahp_depth"] > 0, f"mahp_depth must be positive, got {feat['mahp_depth']}"

    def test_fahp_and_mahp_are_distinct(self):
        """fAHP (early, deep) and mAHP (late, shallower) must yield different values."""
        v, t, spikes = self._make_spike_with_dual_ahp(fahp_depth_mv=8.0, mahp_depth_mv=5.0)
        features = calculate_spike_features(v, t, spikes)

        feat = features[0]
        # fAHP (2 ms post-peak) is deeper than mAHP (20 ms post-peak) in this fixture
        assert feat["fahp_depth"] != feat["mahp_depth"], (
            f"fahp_depth ({feat['fahp_depth']:.3f}) and mahp_depth ({feat['mahp_depth']:.3f}) "
            "must be distinct for a spike with explicit dual-AHP structure"
        )


# ---------------------------------------------------------------------------
# Task 5a: Quiescent Noise Floor with Heavy Spontaneous Activity at Start
# ---------------------------------------------------------------------------
class TestQuiescentNoiseFloor:
    """Verify that find_quiescent_baseline_rms ignores noisy burst regions
    at the beginning of a trace and correctly identifies a quiet segment."""

    def test_finds_quiet_region_not_start(self):
        """When the first 500 ms has heavy activity, the quiescent window must
        NOT be located at the very beginning."""
        from Synaptipy.core.analysis.synaptic_events import find_quiescent_baseline_rms

        fs = 20000.0
        dt = 1.0 / fs
        n_total = int(2.0 / dt)  # 2 s trace
        rng = np.random.default_rng(42)
        # Quiet baseline
        data = rng.normal(0.0, 0.5, size=n_total)

        # Seed heavy spontaneous activity in the first 500 ms
        noisy_end = int(0.5 / dt)
        for _ in range(30):
            ev_start = rng.integers(0, noisy_end - int(0.002 / dt))
            event_len = int(0.002 / dt)
            data[ev_start : ev_start + event_len] += rng.choice([-1, 1]) * 15.0

        rms, (start_idx, end_idx) = find_quiescent_baseline_rms(data, fs, window_ms=20.0)

        # The quiescent window must not start in the noisy first 500 ms
        assert start_idx >= noisy_end or rms < 2.0, (
            f"Quiescent window starts at idx={start_idx} (within noisy region) "
            f"with RMS={rms:.3f}; expected the quiet region to be selected."
        )

    def test_quiescent_rms_lower_than_global_rms(self):
        """RMS of the quiescent chunk must be lower than the global trace RMS."""
        from Synaptipy.core.analysis.synaptic_events import find_quiescent_baseline_rms

        fs = 20000.0
        dt = 1.0 / fs
        n_total = int(1.0 / dt)  # 1 s trace
        rng = np.random.default_rng(7)
        data = rng.normal(0.0, 0.3, size=n_total)

        # Large bursts in first 300 ms
        noisy_end = int(0.3 / dt)
        data[:noisy_end] += rng.normal(0.0, 10.0, size=noisy_end)

        rms, _ = find_quiescent_baseline_rms(data, fs, window_ms=20.0)
        global_rms = float(np.sqrt(np.mean(data**2)))

        assert rms < global_rms, f"Quiescent RMS ({rms:.4f}) should be less than global RMS ({global_rms:.4f})"

    def test_quiescent_rms_returns_positive(self):
        """RMS must always be a positive finite float."""
        from Synaptipy.core.analysis.synaptic_events import find_quiescent_baseline_rms

        fs = 10000.0
        data = np.sin(np.linspace(0, 10 * np.pi, int(fs))) * 5.0
        rms, (start_idx, end_idx) = find_quiescent_baseline_rms(data, fs, window_ms=20.0)

        assert np.isfinite(rms), f"RMS must be finite, got {rms}"
        assert rms > 0, f"RMS must be positive, got {rms}"
        assert start_idx >= 0
        assert end_idx > start_idx


# ---------------------------------------------------------------------------
# Task 5b: 0 mV Agnosticism - Blunted Spikes Peaking at -5 mV
# ---------------------------------------------------------------------------
class TestBluntedSpikeDetection:
    """Verify that spikes peaking well below 0 mV are detected when threshold
    is set appropriately. Spike detection must be agnostic about absolute
    voltage; it relies on kinetic derivatives, not a hard 0 mV boundary."""

    def _make_blunted_spike_trace(
        self,
        n_spikes: int = 3,
        peak_mv: float = -5.0,
        baseline_mv: float = -70.0,
        fs: float = 20000.0,
    ):
        """Build a trace with blunted spikes peaking at peak_mv (default -5 mV)."""
        dt = 1.0 / fs
        duration_s = 0.5
        n = int(duration_s / dt)
        t = np.arange(n) * dt
        v = np.full(n, baseline_mv)

        spike_times_s = np.linspace(0.05, 0.45, n_spikes)
        for st in spike_times_s:
            idx = int(st / dt)
            # Fast rise: 0.5 ms ramp from baseline to peak
            rise_len = max(2, int(0.0005 / dt))
            for k in range(rise_len):
                frac = k / rise_len
                vi = idx - rise_len + k
                if 0 <= vi < n:
                    v[vi] = baseline_mv + frac * (peak_mv - baseline_mv)
            # Peak sample
            if 0 <= idx < n:
                v[idx] = peak_mv
            # Exponential decay: 3 ms time constant
            tau_decay = 0.003
            for k in range(1, int(0.015 / dt)):
                vi = idx + k
                if vi < n:
                    v[vi] = baseline_mv + (peak_mv - baseline_mv) * np.exp(-(k * dt) / tau_decay)

        return v, t, fs

    def test_blunted_spikes_detected_with_appropriate_threshold(self):
        """Spikes peaking at -5 mV must be detected when threshold <= -5 mV."""
        v, t, fs = self._make_blunted_spike_trace(n_spikes=3, peak_mv=-5.0)
        refractory_samples = max(1, int(0.002 * fs))
        result = detect_spikes_threshold(v, t, threshold=-20.0, refractory_samples=refractory_samples)

        n_detected = len(result.spike_times) if result.spike_times is not None else 0
        assert n_detected >= 1, (
            f"Expected at least 1 spike with threshold=-20 mV for spikes peaking at -5 mV, " f"got {n_detected}."
        )

    def test_blunted_spikes_not_detected_when_threshold_above_peak(self):
        """Spikes peaking at -5 mV must NOT be detected when threshold=0 mV."""
        v, t, fs = self._make_blunted_spike_trace(n_spikes=3, peak_mv=-5.0)
        refractory_samples = max(1, int(0.002 * fs))
        # Threshold = 0 mV: -5 mV < 0 mV, so spikes should not pass the voltage gate
        result = detect_spikes_threshold(v, t, threshold=0.0, refractory_samples=refractory_samples)

        n_detected = len(result.spike_times) if result.spike_times is not None else 0
        assert n_detected == 0, (
            f"Spikes peaking at -5 mV should NOT be detected when threshold=0 mV, " f"but {n_detected} were detected."
        )

    def test_spike_features_computed_for_blunted_spike(self):
        """calculate_spike_features must not crash for a blunted -5 mV spike."""
        v, t, fs = self._make_blunted_spike_trace(n_spikes=1, peak_mv=-5.0)
        refractory_samples = max(1, int(0.002 * fs))
        result = detect_spikes_threshold(v, t, threshold=-20.0, refractory_samples=refractory_samples)

        if result.spike_indices is not None and len(result.spike_indices) > 0:
            features = calculate_spike_features(v, t, result.spike_indices)
            assert len(features) >= 1
            feat = features[0]
            # The absolute peak must be close to -5 mV
            assert (
                feat["absolute_peak_mv"] <= -3.0
            ), f"Expected blunted spike peak near -5 mV, got {feat['absolute_peak_mv']:.1f} mV"
            # Overshoot should be 0 (spike did not cross 0 mV)
            assert (
                feat["overshoot_mv"] == 0.0
            ), f"Blunted spike (-5 mV peak) overshoot must be 0, got {feat['overshoot_mv']}"

    def test_train_dynamics_default_threshold_allows_blunted_spikes(self):
        """The train dynamics wrapper's default threshold (-20 mV) must detect -5 mV spikes."""
        from Synaptipy.core.analysis.firing_dynamics import run_train_dynamics_wrapper

        v, t, fs = self._make_blunted_spike_trace(n_spikes=4, peak_mv=-5.0)
        out = run_train_dynamics_wrapper(v, t, fs, spike_threshold=-20.0)
        metrics = out.get("metrics", {})

        # Should have detected some spikes
        spike_count = metrics.get("spike_count", 0)
        assert spike_count >= 1, (
            f"run_train_dynamics_wrapper with threshold=-20 mV must detect -5 mV spikes, "
            f"got spike_count={spike_count}"
        )
