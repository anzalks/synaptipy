# tests/core/test_spike_kinetics.py
import pytest
import numpy as np
from Synaptipy.core.analysis.spike_analysis import calculate_spike_features


def test_spike_kinetics_ideal():
    fs = 10000.0  # 10 kHz, dt = 0.1 ms
    dt = 1.0 / fs
    t = np.arange(1000) * dt

    # Construct an ideal spike
    # Baseline -70
    # Threshold -40
    # Peak +30
    # Amplitude = 70 mV

    # 10% amp = -40 + 7 = -33 mV
    # 90% amp = -40 + 63 = +23 mV

    v = np.full_like(t, -70.0)

    # Linear rise from -40 (at 10ms) to +30 (at 11ms)
    # Duration 1ms.
    # Rise time 10-90% should be 0.8 ms

    start_idx = 100  # 10 ms
    peak_idx = 110  # 11 ms

    # Pre-threshold rise (Make it flat to avoid premature threshold detection)
    v[90:100] = -70.0

    # AP Rise
    v[100:111] = np.linspace(-40, 30, 11)

    # AP Decay (Linear for simplicity)
    # Fall from +30 to -70 in 2ms (20 samples)
    # Decay 90-10% should be 0.8 * 2 = 1.6 ms
    end_idx = 130
    v[110:131] = np.linspace(30, -70, 21)

    spike_indices = np.array([peak_idx])

    features = calculate_spike_features(v, t, spike_indices)

    assert len(features) == 1
    f = features[0]

    # Check Rise Time
    # Expected: 0.8 ms
    # Allow small error due to discrete sampling
    assert abs(f["rise_time_10_90"] - 0.8) < 0.15

    # Check Decay Time
    # Expected: 1.6 ms
    assert abs(f["decay_time_90_10"] - 1.6) < 0.15


def test_adp_detection():
    fs = 10000.0
    dt = 1.0 / fs
    t = np.arange(2000) * dt

    v = np.full_like(t, -70.0)

    # Spike at 10ms
    peak_idx = 100
    v[90:100] = np.linspace(-70, 30, 10)
    v[100:110] = np.linspace(30, -80, 10)  # Fast AHP/repolarization to -80 (below threshold -70)

    # ADP: Bump after spike
    # Center at 15ms (idx 150)
    # Amplitude 5mV above baseline (-80mV) -> -75mV
    # Width 10ms
    adp_center = 150
    v[110:200] = -80.0 + 5.0 * np.exp(-0.5 * ((np.arange(110, 200) - adp_center) / 10) ** 2)

    spike_indices = np.array([peak_idx])
    features = calculate_spike_features(v, t, spike_indices)

    f = features[0]

    # ADP amplitude should be around 5 mV
    # Note: calculate_spike_features calculates ADP relative to 'ap_end_idx' voltage.
    # If ap_end_idx is at -70, then ADP amp is ~5.

    assert f["adp_amplitude"] is not None
    assert f["adp_amplitude"] > 2.0  # At least detected
    assert abs(f["adp_amplitude"] - 5.0) < 2.0
