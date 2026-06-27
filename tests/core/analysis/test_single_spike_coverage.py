import numpy as np

from synaptipy.core.analysis.single_spike import (
    analyze_multi_sweep_spikes,
    calculate_dvdt,
    calculate_isi,
    calculate_spike_features,
    detect_threshold_kink,
    get_phase_plane_trajectory,
)


def test_calculate_isi():
    # Empty or single spike
    assert len(calculate_isi(np.array([]))) == 0
    assert len(calculate_isi(np.array([1.0]))) == 0
    # Multiple spikes
    np.testing.assert_array_equal(calculate_isi(np.array([1.0, 2.5, 4.0])), np.array([1.5, 1.5]))


def test_calculate_dvdt_coverage():
    voltage = np.array([1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0])
    sampling_rate = 1000.0  # 1kHz

    # No smoothing
    dvdt = calculate_dvdt(voltage, sampling_rate, sigma_ms=0.0)
    assert dvdt is not None
    assert len(dvdt) == len(voltage)

    # With smoothing, large enough window
    dvdt_smooth = calculate_dvdt(voltage, sampling_rate, sigma_ms=10.0)
    assert dvdt_smooth is not None


def test_get_phase_plane_trajectory():
    voltage = np.array([1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0])
    v, dvdt = get_phase_plane_trajectory(voltage, 1000.0)
    assert len(v) == len(dvdt)


def test_detect_threshold_kink_coverage():
    # Construct a trace that triggers crossings = np.where(dvdt_slice > dvdt_threshold)[0]
    # We need dvdt to exceed dvdt_threshold (default 20 V/s)
    # 20 V/s = 20,000 mV/s. At 10,000 Hz (dt=0.1ms), dv of 2mV per step = 20,000 mV/s
    voltage = np.ones(100) * -70.0
    voltage[50:60] = np.linspace(-70, 40, 10)  # steep rise
    voltage[60:70] = np.linspace(40, -80, 10)  # steep fall

    # Provide peak indices manually
    thresh = detect_threshold_kink(voltage, 10000.0, dvdt_threshold=20.0, peak_indices=np.array([59]))
    assert len(thresh) == 1

    # Peak index too close to start, or no crossing
    flat_voltage = np.ones(100) * -70.0
    thresh2 = detect_threshold_kink(flat_voltage, 10000.0, dvdt_threshold=20.0, peak_indices=np.array([10]))
    assert len(thresh2) == 1
    assert thresh2[0] == max(0, 10 - int(0.001 * 10000.0))

    # Auto detect peak indices
    thresh3 = detect_threshold_kink(voltage, 10000.0, dvdt_threshold=20.0)
    assert len(thresh3) > 0


def test_analyze_multi_sweep_spikes():
    voltage1 = np.ones(100) * -70.0
    voltage1[50] = 40.0
    voltage2 = np.ones(100) * -70.0

    time_vector = np.arange(100) / 10000.0

    # Valid analysis
    results = analyze_multi_sweep_spikes([voltage1, voltage2], time_vector, threshold=-20.0, refractory_samples=2)
    assert len(results) == 2
    assert results[0].value == 1
    assert results[1].value == 0

    # Exception handling (pass invalid time vector to trigger exception)
    results_err = analyze_multi_sweep_spikes([voltage1], np.array([]), threshold=-20.0, refractory_samples=2)
    assert len(results_err) == 1
    assert not results_err[0].is_valid
    assert "Time and data mismatch" in results_err[0].error_message


def test_calculate_spike_features_edge_cases():
    # Construct a spike that hits the edge of the array (no AHP/downstroke)
    voltage = np.ones(100) * -70.0
    voltage[90:100] = np.linspace(-70, 40, 10)  # Spike right at the end
    time_vector = np.arange(100) / 10000.0

    spike_indices = np.array([99])
    features = calculate_spike_features(voltage, time_vector, spike_indices, dvdt_threshold=5.0)

    # Because it hits the edge, half_width and AHP depths should safely return NaN or handle gracefully
    assert len(features) == 1
    assert hasattr(features[0], "half_width")
    assert hasattr(features[0], "fahp_depth")
    assert hasattr(features[0], "ap_delay")
    assert hasattr(features[0], "ahp_time")
    assert hasattr(features[0], "upstroke_downstroke_ratio")
    assert hasattr(features[0], "trough_v")
    assert hasattr(features[0], "phase_plane_area")

    # Noisy downstroke forcing None / NaN fallbacks
    voltage2 = np.ones(100) * -70.0
    voltage2[50] = 40.0
    voltage2[51:] = np.random.normal(0, 10, 49)  # random noise

    features2 = calculate_spike_features(voltage2, time_vector, np.array([50]), dvdt_threshold=5.0)
    assert len(features2) == 1
