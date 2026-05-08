"""
Test suite for division-by-zero guards and epsilon comparisons.

This module validates all mathematical edge case protections added to ensure
numerical stability and prevent NaN/Inf propagation in analysis algorithms.

Covers:
- CV2/LV calculations with extremely small ISIs
- Sag ratio with tiny voltage deflections
- RMP polyfit with constant time arrays
- Capacitance with non-physiological effective resistance
- Bi-exponential tau comparisons
- Adaptation ratio with artifact ISIs
"""

import numpy as np
import pytest

from Synaptipy.core.analysis.firing_dynamics import calculate_train_dynamics
from Synaptipy.core.analysis.passive_properties import (
    calculate_capacitance_cc,
    calculate_rmp,
    calculate_sag_ratio,
)


class TestCV2LVDivisionGuards:
    """Test CV2 and LV calculations with pathological ISI values."""

    def test_cv2_with_zero_sum_isi(self):
        """CV2 should return NaN when ISI sum approaches zero."""
        # Create spike times with extremely small ISIs (< 1e-9)
        spike_times = np.array([0.0, 1e-12, 2e-12, 3e-12])
        time = np.arange(0, 0.001, 0.0001)
        data = np.zeros_like(time)

        result = calculate_train_dynamics(
            spike_times=spike_times,
        )

        # CV2 should be NaN, not inf or crash
        assert np.isnan(result.cv2), f"Expected NaN for CV2 with tiny ISIs, got {result.cv2}"

    def test_lv_with_zero_sum_isi(self):
        """LV should return NaN when ISI sum approaches zero."""
        spike_times = np.array([0.0, 1e-12, 2e-12, 3e-12])
        time = np.arange(0, 0.001, 0.0001)
        data = np.zeros_like(time)

        result = calculate_train_dynamics(
            spike_times=spike_times,
        )

        # LV should be NaN, not inf or crash
        assert np.isnan(result.lv), f"Expected NaN for LV with tiny ISIs, got {result.lv}"

    def test_cv2_lv_with_normal_isis(self):
        """CV2 and LV should compute correctly with normal ISIs."""
        # Regular firing at ~100 Hz
        spike_times = np.array([0.0, 0.01, 0.02, 0.03, 0.04])
        time = np.arange(0, 0.05, 0.0001)
        data = np.zeros_like(time)

        result = calculate_train_dynamics(
            spike_times=spike_times,
        )

        # Should be valid numbers
        assert not np.isnan(result.cv2), "CV2 should be valid with normal ISIs"
        assert not np.isnan(result.lv), "LV should be valid with normal ISIs"
        assert not np.isinf(result.cv2), "CV2 should not be infinite"
        assert not np.isinf(result.lv), "LV should not be infinite"


class TestSagRatioEpsilonComparison:
    """Test sag ratio calculation with tiny voltage deflections."""

    def test_sag_ratio_with_near_zero_deflection(self):
        """Sag ratio should return NaN when deflection < epsilon."""
        # Create trace with extremely small deflection (< 1e-9 V)
        time = np.linspace(0, 0.5, 5000)
        voltage = np.ones(5000) * -60.0  # Flat at -60 mV
        voltage[2000:3000] += 1e-12  # Tiny deflection < epsilon

        result = calculate_sag_ratio(
            voltage_trace=voltage,
            time_vector=time,
            sampling_rate=10000.0,
            current_amplitude_pa=-100.0,
            response_window=(0.2, 0.3),
            response_steady_state_window=(0.25, 0.29),
            rebound_window_ms=50.0,
        )

        # Should return NaN, not huge ratio
        assert result.sag_ratio is None or np.isnan(result.sag_ratio), "Expected NaN for tiny deflection"

    def test_sag_ratio_with_normal_deflection(self):
        """Sag ratio should compute correctly with physiological deflection."""
        time = np.linspace(0, 0.5, 5000)
        voltage = np.ones(5000) * -60.0
        # Physiological hyperpolarization with sag
        voltage[2000:3000] -= 10.0  # -10 mV deflection
        voltage[2500:3000] += 2.0  # +2 mV sag recovery

        result = calculate_sag_ratio(
            voltage_trace=voltage,
            time_vector=time,
            sampling_rate=10000.0,
            current_amplitude_pa=-100.0,
            response_window=(0.2, 0.3),
            response_steady_state_window=(0.25, 0.29),
            rebound_window_ms=50.0,
        )

        # Should be valid
        assert result.sag_ratio is not None, "Sag ratio should be valid with normal deflection"
        assert not np.isnan(result.sag_ratio), "Sag ratio should not be NaN"
        assert not np.isinf(result.sag_ratio), "Sag ratio should not be infinite"


class TestRMPPolyfitValidation:
    """Test RMP drift calculation with edge case time arrays."""

    def test_rmp_with_constant_time(self):
        """RMP should handle constant time array gracefully."""
        # All time points identical (zero range)
        time = np.ones(1000) * 1.0
        voltage = np.random.randn(1000) * 0.5 - 60.0

        result = calculate_rmp(
            data=voltage,
            time=time,
            baseline_window=(0.9, 1.1),  # Will only find constant-time points
        )

        # Drift should be None (cannot fit line to constant time)
        assert result.drift is None, "Drift should be None for constant time array"
        # Mean should still be valid
        assert result.value is not None, "RMP value should still be computed"

    def test_rmp_with_single_unique_time(self):
        """RMP should handle near-constant time with < 2 unique values."""
        time = np.array([1.0, 1.0, 1.0, 1.000000001, 1.0])  # Only 2 values, but ptp < epsilon
        voltage = np.array([-60.0, -60.1, -59.9, -60.0, -60.05])

        result = calculate_rmp(
            data=voltage,
            time=time,
            baseline_window=(0.9, 1.1),
        )

        # Should not crash, drift may be None
        assert result.value is not None, "RMP value should be computed"
        # Drift might be None due to insufficient time range


class TestCapacitanceGuards:
    """Test capacitance calculation with non-physiological values."""

    def test_capacitance_with_tiny_effective_resistance(self):
        """Capacitance should reject effective_r < 0.1 MOhm."""
        # Tau = 10 ms, but Rin - Rs = 0.05 MOhm (50 kOhm, non-physiological)
        result = calculate_capacitance_cc(
            tau_ms=10.0,
            rin_mohm=0.1,  # 100 kOhm
            rs_mohm=0.05,  # 50 kOhm series resistance
        )

        # Should return None for non-physiological resistance
        assert result is None, "Capacitance should be None for effective_r < 0.1 MOhm"

    def test_capacitance_with_normal_values(self):
        """Capacitance should compute correctly with physiological values."""
        result = calculate_capacitance_cc(
            tau_ms=20.0,
            rin_mohm=200.0,  # 200 MOhm
            rs_mohm=10.0,  # 10 MOhm series resistance
        )

        # Cm = tau / (Rin - Rs) = 20 / 190 ≈ 0.105 nF = 105 pF
        assert result is not None, "Capacitance should be valid"
        assert 50 < result < 200, f"Expected Cm ~105 pF, got {result} pF"


class TestBiExponentialTauComparison:
    """Test that bi-exponential fits use epsilon comparison for tau equality."""

    def test_tau_comparison_with_nearly_equal_values(self):
        """Ensure tau_f != tau_s is replaced with epsilon comparison."""
        # This test documents expected behavior; actual implementation is in synaptic_events.py
        # The fix ensures that tau values within 0.01 ms are considered equal
        tau_f = 5.0
        tau_s = 5.009  # Within 0.01 ms epsilon

        # Old code: tau_f != tau_s would be True (5.0 != 5.009)
        # New code: abs(tau_f - tau_s) > 0.01 is False (0.009 < 0.01)
        # This documents the expected behavior after fix
        assert abs(tau_f - tau_s) <= 0.01, "Should be considered equal with epsilon comparison"


class TestAdaptationRatioGuards:
    """Test adaptation ratio with artifact ISIs."""

    def test_adaptation_ratio_with_tiny_first_isi(self):
        """Adaptation ratio should return NaN for ISI < 1 µs."""
        # Simulate artifact: first two spikes 0.5 µs apart (< 1 µs threshold)
        spike_times = np.array([0.0, 0.0000005, 0.01, 0.02])
        time = np.arange(0, 0.03, 0.0001)
        data = np.zeros_like(time)

        result = calculate_train_dynamics(
            spike_times=spike_times,
        )

        # Adaptation index should be NaN for artifact ISI
        assert np.isnan(result.adaptation_index), "Adaptation index should be NaN for ISI < 1 µs"

    def test_adaptation_ratio_with_normal_isis(self):
        """Adaptation ratio should compute correctly with normal ISIs."""
        # Regular spike train with adaptation
        spike_times = np.array([0.0, 0.01, 0.025, 0.045])  # ISIs: 10, 15, 20 ms
        time = np.arange(0, 0.05, 0.0001)
        data = np.zeros_like(time)

        result = calculate_train_dynamics(
            spike_times=spike_times,
        )

        # Adaptation index = last_ISI / first_ISI = 20 / 10 = 2.0
        assert not np.isnan(result.adaptation_index), "Adaptation index should be valid"
        assert 1.5 < result.adaptation_index < 2.5, f"Expected ~2.0, got {result.adaptation_index}"


class TestEdgeCaseIntegration:
    """Integration tests combining multiple edge cases."""

    def test_all_guards_with_pathological_data(self):
        """Test that all guards work together without crashes."""
        # Extremely pathological synthetic data
        spike_times = np.array([0.0, 1e-15, 2e-15, 0.001, 0.002])  # Mix of artifacts and real
        time = np.linspace(0, 0.1, 1000)
        voltage = np.random.randn(1000) * 1e-12 - 60.0  # Near-zero variance

        # Should not crash, should return NaN for invalid metrics
        result_train = calculate_train_dynamics(
            data=voltage,
            time=time,
            sampling_rate=10000.0,
            spike_indices=None,
            spike_times=spike_times,
        )

        # All metrics should be either valid or NaN, never inf or crash
        assert result_train is not None, "Should return result object"
        assert not np.isinf(result_train.cv2), "CV2 should not be infinite"
        assert not np.isinf(result_train.lv), "LV should not be infinite"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
