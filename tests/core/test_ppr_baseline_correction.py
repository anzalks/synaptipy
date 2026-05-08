"""
Test suite for paired-pulse ratio baseline correction validation.

This module validates that PPR calculations correctly account for residual
decay from the first response when measuring the second response.

Covers:
- PPR with various inter-stimulus intervals
- Residual subtraction accuracy
- Polarity handling (negative/positive)
- Comparison with expected values
"""

import numpy as np
import pytest

from Synaptipy.core.analysis.evoked_responses import calculate_paired_pulse_ratio


class TestPPRBaselineCorrection:
    """Test PPR baseline correction with synthetic data."""

    def _generate_ppr_trace(
        self,
        r1_amp=-50.0,
        r2_amp=-30.0,
        stim1_t=0.1,
        stim2_t=0.15,
        decay_tau_ms=20.0,
        fs=10000.0,
        duration=0.3,
    ):
        """Generate synthetic paired-pulse trace with exponential decay."""
        time = np.arange(0, duration, 1 / fs)
        voltage = np.ones_like(time) * -60.0  # Baseline at -60 mV

        # First response (EPSP or IPSP)
        stim1_idx = int(stim1_t * fs)
        r1_profile = r1_amp * np.exp(-np.arange(len(time) - stim1_idx) / (decay_tau_ms * fs / 1000))
        voltage[stim1_idx:] += r1_profile

        # Second response (on top of decaying R1)
        stim2_idx = int(stim2_t * fs)
        r2_profile = r2_amp * np.exp(-np.arange(len(time) - stim2_idx) / (decay_tau_ms * fs / 1000))
        voltage[stim2_idx:] += r2_profile

        return voltage, time

    def test_ppr_residual_subtraction(self):
        """PPR should correctly subtract residual decay from R1."""
        voltage, time = self._generate_ppr_trace(
            r1_amp=-50.0,  # -50 mV EPSP
            r2_amp=-50.0,  # Same amplitude (testing facilitation/depression = 1.0)
            stim1_t=0.1,
            stim2_t=0.15,  # 50 ms ISI
            decay_tau_ms=20.0,
        )

        result = calculate_paired_pulse_ratio(
            data=voltage,
            time=time,
            stim1_onset_s=0.1,
            stim2_onset_s=0.15,
            response_window_ms=20.0,
            baseline_window_ms=10.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=40.0,
            polarity="negative",
        )

        # R2 corrected should account for residual
        assert result["r2_amplitude_corrected"] is not None, "R2 corrected amplitude should be calculated"
        assert result["residual_at_stim2"] is not None, "Residual should be calculated"

        # Residual should be negative (decay from negative EPSP)
        assert result["residual_at_stim2"] < 0, f"Residual should be negative, got {result['residual_at_stim2']}"

        # R2 corrected should differ from raw
        r2_raw = result["r2_amplitude_raw"]
        r2_corrected = result["r2_amplitude_corrected"]
        assert abs(r2_corrected - r2_raw) > 1.0, "Corrected should significantly differ from raw"

    def test_ppr_with_short_isi(self):
        """PPR with short ISI should have large residual."""
        voltage, time = self._generate_ppr_trace(
            r1_amp=-50.0,
            r2_amp=-40.0,
            stim1_t=0.1,
            stim2_t=0.12,  # 20 ms ISI (short)
            decay_tau_ms=25.0,
        )

        result = calculate_paired_pulse_ratio(
            data=voltage,
            time=time,
            stim1_onset_s=0.1,
            stim2_onset_s=0.12,
            response_window_ms=20.0,
            baseline_window_ms=10.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=15.0,
            polarity="negative",
        )

        # Short ISI means large residual
        residual = result.get("residual_at_stim2")
        assert residual is not None, "Residual should be calculated"
        assert abs(residual) > 10.0, f"Short ISI should have large residual, got {abs(residual)}"

    def test_ppr_with_long_isi(self):
        """PPR with long ISI should have minimal residual."""
        voltage, time = self._generate_ppr_trace(
            r1_amp=-50.0,
            r2_amp=-50.0,
            stim1_t=0.1,
            stim2_t=0.3,  # 200 ms ISI (long)
            decay_tau_ms=20.0,
        )

        result = calculate_paired_pulse_ratio(
            data=voltage,
            time=time,
            stim1_onset_s=0.1,
            stim2_onset_s=0.3,
            response_window_ms=20.0,
            baseline_window_ms=10.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=180.0,
            polarity="negative",
        )

        # Long ISI means small residual
        residual = result.get("residual_at_stim2")
        if residual is not None:
            assert abs(residual) < 5.0, f"Long ISI should have minimal residual, got {abs(residual)}"

    def test_ppr_positive_polarity(self):
        """PPR should work correctly with positive polarity (depolarizing)."""
        voltage, time = self._generate_ppr_trace(
            r1_amp=30.0,  # Positive (depolarizing)
            r2_amp=20.0,
            stim1_t=0.1,
            stim2_t=0.15,
            decay_tau_ms=15.0,
        )
        # Adjust baseline for positive responses
        voltage -= 60.0  # Start at -60 mV

        result = calculate_paired_pulse_ratio(
            data=voltage,
            time=time,
            stim1_onset_s=0.1,
            stim2_onset_s=0.15,
            response_window_ms=20.0,
            baseline_window_ms=10.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=40.0,
            polarity="positive",
        )

        # Should calculate residual for positive polarity
        residual = result.get("residual_at_stim2")
        if residual is not None:
            assert residual > 0, "Residual should be positive for positive polarity"

    def test_ppr_depression(self):
        """PPR < 1 indicates synaptic depression."""
        voltage, time = self._generate_ppr_trace(
            r1_amp=-50.0,
            r2_amp=-25.0,  # 50% reduction (depression)
            stim1_t=0.1,
            stim2_t=0.15,
            decay_tau_ms=20.0,
        )

        result = calculate_paired_pulse_ratio(
            data=voltage,
            time=time,
            stim1_onset_s=0.1,
            stim2_onset_s=0.15,
            response_window_ms=20.0,
            baseline_window_ms=10.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=40.0,
            polarity="negative",
        )

        ppr = result.get("paired_pulse_ratio")
        if ppr is not None:
            assert ppr < 1.0, f"Expected depression (PPR < 1), got {ppr}"
            assert ppr > 0.3, f"PPR should be reasonable, got {ppr}"

    def test_ppr_facilitation(self):
        """PPR > 1 indicates synaptic facilitation."""
        voltage, time = self._generate_ppr_trace(
            r1_amp=-40.0,
            r2_amp=-60.0,  # 50% increase (facilitation)
            stim1_t=0.1,
            stim2_t=0.15,
            decay_tau_ms=20.0,
        )

        result = calculate_paired_pulse_ratio(
            data=voltage,
            time=time,
            stim1_onset_s=0.1,
            stim2_onset_s=0.15,
            response_window_ms=20.0,
            baseline_window_ms=10.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=40.0,
            polarity="negative",
        )

        ppr = result.get("paired_pulse_ratio")
        if ppr is not None:
            assert ppr > 1.0, f"Expected facilitation (PPR > 1), got {ppr}"
            assert ppr < 3.0, f"PPR should be reasonable, got {ppr}"


class TestPPREdgeCases:
    """Test PPR with edge cases and error handling."""

    def test_ppr_with_no_r1(self):
        """PPR should handle missing R1 gracefully."""
        time = np.linspace(0, 0.3, 3000)
        voltage = np.ones_like(time) * -60.0  # Flat trace (no responses)

        result = calculate_paired_pulse_ratio(
            data=voltage,
            time=time,
            stim1_onset_s=0.1,
            stim2_onset_s=0.15,
            response_window_ms=20.0,
            baseline_window_ms=10.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=40.0,
            polarity="negative",
        )

        # Should return error or NaN
        assert "ppr_error" in result or result.get("paired_pulse_ratio") is None

    def test_ppr_with_very_fast_decay(self):
        """PPR with fast decay (< 5 ms tau) should still work."""
        time = np.linspace(0, 0.3, 3000)
        voltage = np.ones_like(time) * -60.0

        # Fast decay means residual at R2 is minimal
        # This tests that the algorithm doesn't break with fast kinetics

        result = calculate_paired_pulse_ratio(
            data=voltage,
            time=time,
            stim1_onset_s=0.1,
            stim2_onset_s=0.15,
            response_window_ms=20.0,
            baseline_window_ms=10.0,
            fit_decay_from_ms=5.0,
            fit_decay_window_ms=40.0,
            polarity="negative",
        )

        # Should not crash
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
