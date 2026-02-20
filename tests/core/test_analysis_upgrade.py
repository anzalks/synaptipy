# tests/core/test_analysis_upgrade.py
import numpy as np
from unittest.mock import MagicMock
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.analysis.excitability import calculate_fi_curve
from Synaptipy.core.analysis.spike_analysis import run_spike_detection_wrapper
from Synaptipy.core.analysis.burst_analysis import calculate_bursts_logic
from Synaptipy.core.analysis.intrinsic_properties import run_rin_analysis_wrapper


# --- 1. Batch Engine Update Tests ---
def test_batch_engine_channel_set_scope():
    """Test that BatchAnalysisEngine correctly aggregates trials for scope='channel_set'."""
    # Mock NeoAdapter and Channel
    mock_channel = MagicMock()
    mock_channel.num_trials = 3
    mock_channel.get_data.side_effect = [np.array([1, 2]), np.array([3, 4]), np.array([5, 6])]
    mock_channel.get_relative_time_vector.side_effect = [np.array([0, 1]), np.array([0, 1]), np.array([0, 1])]

    mock_recording = MagicMock()
    mock_recording.channels = {"Ch1": mock_channel}

    mock_adapter = MagicMock()
    mock_adapter.read_recording.return_value = mock_recording

    engine = BatchAnalysisEngine(neo_adapter=mock_adapter)

    # Define a dummy analysis function
    mock_analysis = MagicMock(return_value={"result": "ok"})
    from Synaptipy.core.analysis.registry import AnalysisRegistry

    # Register dummy analysis
    AnalysisRegistry.register("dummy_set_analysis")(mock_analysis)

    pipeline = [{"analysis": "dummy_set_analysis", "scope": "channel_set", "params": {"p": 1}}]

    # Run batch
    from pathlib import Path

    results = engine.run_batch([Path("test.abf")], pipeline)

    # Verify aggregation
    assert not results.empty
    assert len(results) == 1
    assert results.iloc[0]["trial_count"] == 3

    # Verify analysis function was called with lists
    mock_analysis.assert_called_once()
    args, _ = mock_analysis.call_args
    data_list, time_list, _ = args
    assert len(data_list) == 3
    assert len(time_list) == 3
    assert np.array_equal(data_list[0], np.array([1, 2]))


# --- 2. Excitability Analysis Tests ---
def test_calculate_fi_curve():
    """Test F-I curve calculation."""
    # Create synthetic sweeps: 0 spikes, 2 spikes, 5 spikes
    # We need to simulate spikes. Simple way: threshold crossing.
    t = np.linspace(0, 1, 1000)

    # Sweep 1: 0 spikes (flat line)
    s1 = np.zeros_like(t)

    # Sweep 2: 2 spikes (sine wave peaks)
    s2 = np.zeros_like(t)
    s2[200] = 20  # Spike 1
    s2[600] = 20  # Spike 2

    # Sweep 3: 5 spikes
    s3 = np.zeros_like(t)
    indices = [100, 300, 500, 700, 900]
    s3[indices] = 20

    sweeps = [s1, s2, s3]
    times = [t, t, t]
    currents = [0, 10, 20]  # pA

    result = calculate_fi_curve(sweeps, times, current_steps=currents, threshold=10.0)

    assert result["rheobase_pa"] == 10
    assert result["spike_counts"] == [0, 2, 5]
    # Mean frequency now uses (N-1)/spike_span formula:
    # Sweep 2: 2 spikes, freq = 1/(t[600]-t[200]) ~ 2.5 Hz
    # Sweep 3: 5 spikes, freq = 4/(t[900]-t[100]) ~ 5.0 Hz
    # fi_slope via linregress on 3 points (0Hz@0pA, ~2.5Hz@10pA, ~5Hz@20pA)
    assert result["fi_slope"] is not None
    assert np.isclose(result["fi_slope"], 0.25, atol=0.02)


# --- 3. Spike Shape Statistics Tests ---
def test_spike_shape_stats():
    """Test that spike detection wrapper returns aggregated stats."""
    t = np.linspace(0, 1, 10000)  # 10kHz
    _dt = t[1] - t[0]  # noqa: F841
    data = np.zeros_like(t)

    # Create a spike
    # Simple triangle spike
    peak_idx = 5000
    data[peak_idx - 10 : peak_idx] = np.linspace(-60, 20, 10)  # Rise
    data[peak_idx : peak_idx + 10] = np.linspace(20, -60, 10)  # Fall

    result = run_spike_detection_wrapper(data, t, 10000.0, threshold=0.0)

    assert result["spike_count"] == 1
    # Check for stats keys
    assert "amplitude_mean" in result
    assert "half_width_mean" in result
    # Since only 1 spike, std should be 0
    assert result["amplitude_std"] == 0.0


# --- 4. Burst Analysis Tests ---
def test_burst_detection():
    """Test burst detection logic."""
    # Create spike times: Burst 1 (0.1, 0.11, 0.12), Isolated (0.5), Burst 2 (0.8, 0.81)
    spikes = np.array([0.1, 0.11, 0.12, 0.5, 0.8, 0.81])

    stats = calculate_bursts_logic(spikes, max_isi_start=0.02, max_isi_end=0.05, min_spikes=2)

    assert stats.burst_count == 2
    # Burst 1: 3 spikes. Burst 2: 2 spikes. Avg = 2.5
    assert stats.spikes_per_burst_avg == 2.5


# --- 5. Auto-Windowing Tests ---
def test_auto_windowing_rin():
    """Test auto-detection of pulse windows."""
    t = np.linspace(0, 1, 1000)
    data = np.zeros_like(t)

    # Create a hyperpolarizing pulse from 0.3 to 0.7
    # Baseline 0
    # Pulse -10
    start_idx = 300
    end_idx = 700
    data[start_idx:end_idx] = -10

    # Add some noise
    # data += np.random.normal(0, 0.1, size=len(t))

    # Run wrapper with auto-detect
    result = run_rin_analysis_wrapper(data, t, 1000.0, current_amplitude=-50.0, auto_detect_pulse=True)

    assert result["rin_mohm"] is not None
    assert result["auto_detected"] is True
    # Check if calculated Rin is reasonable
    # V = -10 mV, I = -50 pA. R = V/I = -10 / -0.05 nA = 200 MOhm
    assert np.isclose(result["rin_mohm"], 200.0, atol=1.0)
