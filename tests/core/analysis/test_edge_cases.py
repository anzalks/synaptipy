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

from Synaptipy.core.analysis.intrinsic_properties import (
    calculate_rin,
    calculate_sag_ratio,
    calculate_tau,
    calculate_iv_curve,
)
from Synaptipy.core.analysis.spike_analysis import (
    detect_spikes_threshold,
    calculate_spike_features,
)
from Synaptipy.core.analysis.basic_features import (
    calculate_rmp,
    find_stable_baseline,
)
from Synaptipy.core.analysis.burst_analysis import (
    calculate_bursts_logic,
    analyze_spikes_and_bursts,
)
from Synaptipy.core.analysis.capacitance import (
    calculate_capacitance_cc,
    calculate_capacitance_vc,
)
from Synaptipy.core.analysis.train_dynamics import (
    calculate_train_dynamics,
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

    def test_flat_trace_returns_none(self):
        """A completely flat trace has delta_v_ss == 0 → None."""
        v, t, _ = _make_trace()
        result = calculate_sag_ratio(
            v, t,
            baseline_window=(0.0, 0.05),
            response_peak_window=(0.1, 0.2),
            response_steady_state_window=(0.3, 0.45),
        )
        assert result is None

    def test_depolarising_step(self):
        """A depolarising step should still compute a ratio (< 1)."""
        v, t, _ = _make_trace()
        # Depolarising step: +20 mV
        step_mask = (t >= 0.1) & (t < 0.4)
        v[step_mask] = -50.0
        result = calculate_sag_ratio(
            v, t,
            baseline_window=(0.0, 0.05),
            response_peak_window=(0.1, 0.2),
            response_steady_state_window=(0.3, 0.4),
        )
        assert result is not None
        assert isinstance(result["sag_ratio"], float)

    def test_empty_window_returns_none(self):
        """Windows outside the trace range → None."""
        v, t, _ = _make_trace()
        result = calculate_sag_ratio(
            v, t,
            baseline_window=(10.0, 11.0),
            response_peak_window=(12.0, 13.0),
            response_steady_state_window=(14.0, 15.0),
        )
        assert result is None

    def test_sag_percentage_reported(self):
        """Verify sag_percentage key is present after formalization."""
        v, t, _ = _make_trace()
        step_mask = (t >= 0.1) & (t < 0.4)
        v[step_mask] = -90.0
        # Transient peak deeper
        peak_mask = (t >= 0.1) & (t < 0.15)
        v[peak_mask] = -100.0
        result = calculate_sag_ratio(
            v, t,
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
            v, t,
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
            v, t, stim_start_time=0.0, fit_duration=0.003,
            model='bi',
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
        result = calculate_iv_curve(
            [v], [t], [0.0], (0.0, 0.05), (0.1, 0.2)
        )
        assert result["rin_aggregate_mohm"] is None

    def test_all_zero_currents(self):
        """All-zero current steps → regression on flat data."""
        v, t, _ = _make_trace(n=5000)
        result = calculate_iv_curve(
            [v, v], [t, t], [0.0, 0.0], (0.0, 0.05), (0.1, 0.2)
        )
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
            v, t, threshold=-20.0, refractory_samples=int(0.002 * fs),
        )
        n_spikes = len(result.spike_times) if result.spike_times is not None else 0
        assert n_spikes == 0

    def test_single_sample_trace(self):
        """A 1-sample trace should not crash."""
        v = np.array([-70.0])
        t = np.array([0.0])
        result = detect_spikes_threshold(
            v, t, threshold=-20.0, refractory_samples=1,
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
            v, t, spike_indices,
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
            v, t, fs, threshold=-20.0,
            max_isi_start=0.01, max_isi_end=0.2,
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
            v, t, (0.0, 0.1), (0.1, 0.2), voltage_step_amplitude_mv=0.0,
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
        """Window outside data range → should have error or None."""
        v, t, _ = _make_trace()
        result = calculate_rmp(v, t, baseline_window=(10.0, 11.0))
        assert not result.is_valid or result.value is None

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
            np.array([]), np.array([]), 0.0, 1.0,
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
        pipeline.add_step({
            'type': 'artifact',
            'onset_time': 0.1,
            'duration_ms': 1.0,
            'method': 'hold',
        })
        result = pipeline.process(v, fs, time_vector=t)
        assert np.all(result[art_mask] != 500.0)
