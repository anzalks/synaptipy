# tests/core/test_optogenetics.py
# -*- coding: utf-8 -*-
"""
Tests for optogenetic synchronisation analysis, including the new
multi-mode event-detection support (Spikes / Events (Threshold) /
Events (Template)).
"""
import numpy as np
import pytest

from Synaptipy.core.analysis.optogenetics import (
    extract_ttl_epochs,
    run_opto_sync_wrapper,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ttl(sampling_rate: float, duration: float, onsets: list, pulse_duration: float = 0.01):
    """Create a synthetic TTL square-wave signal (0 / 5 V)."""
    t = np.arange(0, duration, 1.0 / sampling_rate)
    ttl = np.zeros_like(t)
    for onset in onsets:
        start = int(onset * sampling_rate)
        end = int((onset + pulse_duration) * sampling_rate)
        ttl[start:end] = 5.0
    return t, ttl


def _make_spikes_at(sampling_rate: float, duration: float, spike_times: list, amplitude: float = 60.0):
    """Create a voltage trace with brief spike-like transients at given times."""
    t = np.arange(0, duration, 1.0 / sampling_rate)
    data = np.full_like(t, -65.0)  # resting potential
    for st in spike_times:
        idx = int(st * sampling_rate)
        if 0 <= idx < len(data):
            data[idx] = -65.0 + amplitude  # simple threshold crossing
    return t, data


# ---------------------------------------------------------------------------
# extract_ttl_epochs
# ---------------------------------------------------------------------------

class TestExtractTTLEpochs:
    def test_basic_onsets_offsets(self):
        """Detected onsets / offsets match the constructed TTL pulses."""
        sr = 10_000.0
        t, ttl = _make_ttl(sr, 1.0, onsets=[0.1, 0.3, 0.7], pulse_duration=0.02)
        onsets, offsets = extract_ttl_epochs(ttl, t, threshold=2.5)

        assert len(onsets) == 3
        assert len(offsets) == 3
        # Allow 1 sample tolerance
        for i, expected_onset in enumerate([0.1, 0.3, 0.7]):
            assert abs(onsets[i] - expected_onset) < 1.0 / sr + 1e-6

    def test_empty_signal(self):
        onsets, offsets = extract_ttl_epochs(np.array([]), np.array([]))
        assert len(onsets) == 0
        assert len(offsets) == 0

    def test_auto_threshold_unit_mismatch(self):
        """Auto-threshold handles mV-scaled TTL (e.g. 0–5000 mV range)."""
        sr = 10_000.0
        t, ttl_v = _make_ttl(sr, 0.5, onsets=[0.1, 0.3], pulse_duration=0.02)
        ttl_mv = ttl_v * 1000.0  # scale to mV; default threshold (2.5) won't work
        onsets, offsets = extract_ttl_epochs(ttl_mv, t, threshold=2.5, auto_threshold=True)
        assert len(onsets) == 2


# ---------------------------------------------------------------------------
# run_opto_sync_wrapper – Spikes mode (default)
# ---------------------------------------------------------------------------

class TestOptoSyncWrapperSpikes:
    def test_returns_keys(self):
        sr = 10_000.0
        t, ttl = _make_ttl(sr, 1.0, onsets=[0.2, 0.5, 0.8], pulse_duration=0.02)
        _, data = _make_spikes_at(sr, 1.0, spike_times=[0.205, 0.505, 0.805])

        result = run_opto_sync_wrapper(data, t, sr, ttl_data=ttl, event_detection_type="Spikes",
                                       spike_threshold=-10.0)

        assert "optical_latency_ms" in result
        assert "response_probability" in result
        assert "stimulus_count" in result
        assert result["stimulus_count"] == 3

    def test_response_probability_full(self):
        """All three stimuli get a response → probability == 1.0."""
        sr = 10_000.0
        t, ttl = _make_ttl(sr, 1.0, onsets=[0.2, 0.5, 0.8], pulse_duration=0.02)
        # Spike 5 ms after each onset (within default 20 ms window)
        _, data = _make_spikes_at(sr, 1.0, spike_times=[0.205, 0.505, 0.805])

        result = run_opto_sync_wrapper(data, t, sr, ttl_data=ttl, event_detection_type="Spikes",
                                       spike_threshold=-10.0, response_window_ms=20.0)

        assert result.get("response_probability") == pytest.approx(1.0, abs=0.01)

    def test_no_spikes(self):
        """No spikes → probability 0."""
        sr = 10_000.0
        t, ttl = _make_ttl(sr, 1.0, onsets=[0.2, 0.5], pulse_duration=0.02)
        data = np.full_like(t, -65.0)  # flat – no spikes

        result = run_opto_sync_wrapper(data, t, sr, ttl_data=ttl, event_detection_type="Spikes",
                                       spike_threshold=0.0)

        # Response probability should be 0
        assert result.get("response_probability") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# run_opto_sync_wrapper – Events (Threshold) mode
# ---------------------------------------------------------------------------

class TestOptoSyncWrapperEventsThreshold:
    def test_returns_keys(self):
        sr = 10_000.0
        t, ttl = _make_ttl(sr, 1.0, onsets=[0.2, 0.5, 0.8], pulse_duration=0.02)
        # Create synaptic-event-like deflections (negative, 10 pA) after each stimulus
        data = np.zeros_like(t)
        for onset in [0.205, 0.505, 0.805]:
            idx = int(onset * sr)
            width = int(0.010 * sr)   # 10 ms event
            data[idx: idx + width] = np.linspace(0, -10, width)

        result = run_opto_sync_wrapper(
            data, t, sr,
            ttl_data=ttl,
            event_detection_type="Events (Threshold)",
            event_threshold=5.0,
            event_direction="negative",
            event_refractory_s=0.05,
            response_window_ms=40.0,
        )

        assert "optical_latency_ms" in result
        assert "stimulus_count" in result
        assert result["stimulus_count"] == 3

    def test_event_count_key_present(self):
        sr = 10_000.0
        t, ttl = _make_ttl(sr, 0.5, onsets=[0.1, 0.3], pulse_duration=0.01)
        data = np.zeros_like(t)

        result = run_opto_sync_wrapper(
            data, t, sr,
            ttl_data=ttl,
            event_detection_type="Events (Threshold)",
            event_threshold=5.0,
        )

        assert "event_count" in result


# ---------------------------------------------------------------------------
# run_opto_sync_wrapper – Events (Template) mode
# ---------------------------------------------------------------------------

class TestOptoSyncWrapperEventsTemplate:
    def test_returns_keys(self):
        sr = 10_000.0
        t, ttl = _make_ttl(sr, 1.0, onsets=[0.3, 0.7], pulse_duration=0.02)
        data = np.zeros_like(t)

        result = run_opto_sync_wrapper(
            data, t, sr,
            ttl_data=ttl,
            event_detection_type="Events (Template)",
            template_tau_rise_ms=0.5,
            template_tau_decay_ms=5.0,
            template_threshold_sd=4.0,
            response_window_ms=30.0,
        )

        assert "stimulus_count" in result
        assert "event_count" in result

    def test_unknown_type_falls_back_gracefully(self):
        """Unrecognised event_detection_type should not raise, just return no events."""
        sr = 10_000.0
        t, ttl = _make_ttl(sr, 0.5, onsets=[0.1], pulse_duration=0.01)
        data = np.zeros_like(t)

        result = run_opto_sync_wrapper(
            data, t, sr,
            ttl_data=ttl,
            event_detection_type="Nonexistent Type",
        )

        # The analysis should complete (possibly with 0 events),
        # not raise an exception.
        assert isinstance(result, dict)
