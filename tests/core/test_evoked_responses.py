# tests/core/test_evoked_responses.py
# -*- coding: utf-8 -*-
"""Tests for evoked_responses analysis functions."""

import numpy as np

from Synaptipy.core.analysis.evoked_responses import (
    calculate_stimulus_train_stp,
    extract_ttl_epochs,
    run_ppr_wrapper,
    run_stimulus_train_stp_wrapper,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sine_trace(fs: float = 10_000.0, duration: float = 1.0) -> tuple:
    """Return (time, flat-zero data) suitable for testing."""
    t = np.arange(0, duration, 1.0 / fs)
    d = np.zeros_like(t)
    return t, d


def _add_negative_peak(data: np.ndarray, time: np.ndarray, onset: float, amplitude: float, width_s: float = 0.005):
    """Insert a downward peak at *onset* with the given amplitude and width."""
    fs = 1.0 / float(time[1] - time[0])
    i0 = int(np.searchsorted(time, onset + 0.001))  # skip 1 ms artifact blanking
    i1 = min(i0 + int(width_s * fs), len(data))
    data[i0:i1] = -abs(amplitude)
    return data


def _ttl_signal(time: np.ndarray, onsets: list, offsets: list, high: float = 5.0) -> np.ndarray:
    """Build a square-wave TTL signal from onset/offset pairs."""
    ttl = np.zeros_like(time)
    for on, off in zip(onsets, offsets):
        ttl[(time >= on) & (time < off)] = high
    return ttl


# ---------------------------------------------------------------------------
# calculate_stimulus_train_stp
# ---------------------------------------------------------------------------


class TestCalculateStimulusTrainStp:
    """Unit tests for calculate_stimulus_train_stp."""

    def test_basic_negative_polarity(self):
        """Four evenly-spaced negative peaks should return correct amplitudes."""
        fs = 10_000.0
        t, d = _sine_trace(fs, 1.0)
        onsets = np.array([0.1, 0.2, 0.3, 0.4])
        amplitudes_expected = [10.0, 8.0, 6.0, 5.0]  # depression pattern
        for on, amp in zip(onsets, amplitudes_expected):
            _add_negative_peak(d, t, on, amp)

        result = calculate_stimulus_train_stp(
            data=d,
            time=t,
            stim_onsets=onsets,
            polarity="negative",
            response_window_ms=15.0,
            baseline_window_ms=5.0,
            artifact_blanking_ms=1.0,
        )

        assert result.get("stp_error") is None, f"Unexpected error: {result.get('stp_error')}"
        assert result["pulse_count"] == 4
        assert result["stp_type"] == "depression"
        amps = result["amplitudes"]
        assert len(amps) == 4
        # R1 should be close to 10 pA
        assert abs(amps[0] - 10.0) < 2.0, f"R1 amplitude off: {amps[0]}"
        # Normalised R1 must be 1.0
        assert abs(result["amplitudes_norm"][0] - 1.0) < 1e-6
        # R2/R1 key must be present and < 1 (depression)
        assert "R2/R1" in result
        assert result["R2/R1"] < 1.0

    def test_facilitation_detected(self):
        """Increasing amplitude pattern should be labelled as facilitation."""
        fs = 10_000.0
        t, d = _sine_trace(fs, 1.0)
        onsets = np.array([0.1, 0.2, 0.3])
        for on, amp in zip(onsets, [5.0, 8.0, 12.0]):
            _add_negative_peak(d, t, on, amp)

        result = calculate_stimulus_train_stp(
            data=d,
            time=t,
            stim_onsets=onsets,
            polarity="negative",
        )

        assert result["stp_type"] == "facilitation"

    def test_invalid_data_returns_error(self):
        """Empty data should return an error key."""
        result = calculate_stimulus_train_stp(
            data=np.array([]),
            time=np.array([]),
            stim_onsets=np.array([0.1]),
        )
        assert "stp_error" in result

    def test_positive_polarity(self):
        """Positive-polarity peaks should yield positive amplitudes."""
        fs = 10_000.0
        t, d = _sine_trace(fs, 0.5)
        onsets = np.array([0.1, 0.2])
        for on in onsets:
            i = int(np.searchsorted(t, on + 0.002))
            d[i : i + 20] = 15.0

        result = calculate_stimulus_train_stp(
            data=d,
            time=t,
            stim_onsets=onsets,
            polarity="positive",
            response_window_ms=10.0,
        )
        assert result.get("stp_error") is None
        assert result["amplitudes"][0] > 0


# ---------------------------------------------------------------------------
# extract_ttl_epochs (sanity check for PPR and STP TTL path)
# ---------------------------------------------------------------------------


class TestExtractTtlEpochs:
    """Sanity tests for TTL edge detection used by PPR and STP wrappers."""

    def test_detects_two_onsets(self):
        """Two TTL pulses should yield exactly two onset times."""
        fs = 10_000.0
        t = np.arange(0, 1.0, 1.0 / fs)
        ttl = _ttl_signal(t, [0.1, 0.3], [0.15, 0.35])
        onsets, offsets = extract_ttl_epochs(ttl, t, threshold=2.5)
        assert onsets is not None
        assert len(onsets) == 2
        assert abs(onsets[0] - 0.1) < 0.001
        assert abs(onsets[1] - 0.3) < 0.001

    def test_no_ttl_returns_empty(self):
        """A flat zero signal should return empty onset/offset arrays."""
        fs = 10_000.0
        t = np.arange(0, 0.5, 1.0 / fs)
        ttl = np.zeros_like(t)
        onsets, offsets = extract_ttl_epochs(ttl, t)
        assert onsets is not None
        assert len(onsets) == 0


# ---------------------------------------------------------------------------
# run_ppr_wrapper TTL path
# ---------------------------------------------------------------------------


class TestRunPprWrapperTtl:
    """Test that use_ttl=True extracts stim onsets from the TTL channel."""

    def test_ttl_onsets_override_manual(self):
        """When use_ttl=True, detected TTL onsets should override manual values."""
        fs = 10_000.0
        t, d = _sine_trace(fs, 0.5)
        _add_negative_peak(d, t, 0.1, 10.0)
        _add_negative_peak(d, t, 0.25, 8.0)

        ttl = _ttl_signal(t, [0.1, 0.25], [0.11, 0.26])

        result = run_ppr_wrapper(
            data=d,
            time=t,
            sampling_rate=fs,
            use_ttl=True,
            ttl_threshold=2.5,
            ttl_data=ttl,
            # Wrong manual values - should be ignored
            stim1_onset_s=0.0,
            stim2_onset_s=0.5,
            polarity="negative",
        )

        metrics = result["metrics"]
        assert metrics.get("ppr_error") is None or "window" in str(metrics.get("ppr_error", ""))
        assert abs(metrics["stim1_onset_used_s"] - 0.1) < 0.001
        assert abs(metrics["stim2_onset_used_s"] - 0.25) < 0.001

    def test_no_ttl_data_falls_back_to_manual(self):
        """When use_ttl=True but ttl_data is None, manual values should be used."""
        fs = 10_000.0
        t, d = _sine_trace(fs, 0.5)
        _add_negative_peak(d, t, 0.1, 10.0)
        _add_negative_peak(d, t, 0.25, 8.0)

        result = run_ppr_wrapper(
            data=d,
            time=t,
            sampling_rate=fs,
            use_ttl=True,
            ttl_data=None,
            stim1_onset_s=0.1,
            stim2_onset_s=0.25,
            polarity="negative",
        )

        metrics = result["metrics"]
        assert abs(metrics["stim1_onset_used_s"] - 0.1) < 1e-6
        assert abs(metrics["stim2_onset_used_s"] - 0.25) < 1e-6


# ---------------------------------------------------------------------------
# run_stimulus_train_stp_wrapper
# ---------------------------------------------------------------------------


class TestRunStimulusTrainStpWrapper:
    """Integration tests for the registered STP train wrapper."""

    def test_manual_frequency(self):
        """Manual frequency path should generate n_pulses evenly spaced onsets."""
        fs = 10_000.0
        t, d = _sine_trace(fs, 1.0)
        onsets_expected = [0.1, 0.2, 0.3, 0.4]
        for on in onsets_expected:
            _add_negative_peak(d, t, on, 10.0)

        result = run_stimulus_train_stp_wrapper(
            data=d,
            time=t,
            sampling_rate=fs,
            use_ttl=False,
            stim_start_s=0.1,
            stim_frequency_hz=10.0,
            n_pulses=4,
            polarity="negative",
        )

        metrics = result["metrics"]
        assert metrics.get("stp_error") is None
        assert metrics["pulse_count"] == 4
        assert len(metrics["amplitudes"]) == 4

    def test_ttl_path(self):
        """TTL-based detection path should find pulses and return STP profile."""
        fs = 10_000.0
        t, d = _sine_trace(fs, 1.0)
        onsets = [0.1, 0.2, 0.3]
        for on in onsets:
            _add_negative_peak(d, t, on, 10.0)
        ttl = _ttl_signal(t, onsets, [o + 0.01 for o in onsets])

        result = run_stimulus_train_stp_wrapper(
            data=d,
            time=t,
            sampling_rate=fs,
            use_ttl=True,
            ttl_threshold=2.5,
            ttl_data=ttl,
            n_pulses=3,
            polarity="negative",
        )

        metrics = result["metrics"]
        assert metrics.get("stp_error") is None
        assert metrics["pulse_count"] == 3

    def test_zero_frequency_returns_error(self):
        """A zero-Hz frequency with TTL disabled should return an error."""
        fs = 10_000.0
        t, d = _sine_trace(fs, 0.5)

        result = run_stimulus_train_stp_wrapper(
            data=d,
            time=t,
            sampling_rate=fs,
            use_ttl=False,
            stim_frequency_hz=0.0,
            n_pulses=3,
        )

        assert "stp_error" in result["metrics"]
