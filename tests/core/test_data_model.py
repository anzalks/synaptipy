from pathlib import Path

import numpy as np
import pytest

from Synaptipy.core.data_model import Channel, Recording

# Sample data for testing
SAMPLE_RATE = 10000.0  # Hz
T_START = 0.1  # seconds
DATA_TRIAL_1 = np.linspace(0, 1, int(SAMPLE_RATE * 1.0))  # 1 second long
DATA_TRIAL_2 = np.linspace(1, 0, int(SAMPLE_RATE * 0.5))  # 0.5 seconds long


@pytest.fixture
def sample_channel():
    """Fixture for a basic Channel object."""
    return Channel(
        id="ch1",
        name="Voltage",
        units="mV",
        sampling_rate=SAMPLE_RATE,
        data_trials=[DATA_TRIAL_1, DATA_TRIAL_2],  # Two trials
    )


@pytest.fixture
def sample_recording():
    """Fixture for a basic Recording object."""
    rec = Recording(source_file=Path("dummy_file.rec"))
    rec.sampling_rate = SAMPLE_RATE
    rec.t_start = T_START
    rec.duration = 1.0  # Based on longest trial
    ch1 = Channel("1", "Vm", "mV", SAMPLE_RATE, [DATA_TRIAL_1])
    ch1.t_start = T_START
    ch2 = Channel("2", "Im", "pA", SAMPLE_RATE, [DATA_TRIAL_1, DATA_TRIAL_2])
    ch2.t_start = T_START
    rec.channels = {"1": ch1, "2": ch2}
    return rec


# --- Channel Tests ---
def test_channel_creation(sample_channel):
    assert sample_channel.id == "ch1"
    assert sample_channel.name == "Voltage"
    assert sample_channel.units == "mV"
    assert sample_channel.sampling_rate == SAMPLE_RATE
    assert sample_channel.num_trials == 2
    assert sample_channel.num_samples == len(DATA_TRIAL_1)  # Based on first trial
    assert len(sample_channel.data_trials[1]) == len(DATA_TRIAL_2)


def test_channel_get_data(sample_channel):
    assert np.array_equal(sample_channel.get_data(trial_index=0), DATA_TRIAL_1)
    assert np.array_equal(sample_channel.get_data(trial_index=1), DATA_TRIAL_2)
    assert sample_channel.get_data(trial_index=2) is None  # Out of bounds


def test_channel_get_time_vector(sample_channel):
    time_vec_0 = sample_channel.get_time_vector(trial_index=0)
    assert time_vec_0 is not None
    assert len(time_vec_0) == len(DATA_TRIAL_1)
    assert np.isclose(time_vec_0[0], sample_channel.t_start)
    assert np.isclose(time_vec_0[-1], sample_channel.t_start + (len(DATA_TRIAL_1) - 1) / SAMPLE_RATE)

    time_vec_1 = sample_channel.get_time_vector(trial_index=1)
    assert time_vec_1 is not None
    assert len(time_vec_1) == len(DATA_TRIAL_2)

    assert sample_channel.get_time_vector(trial_index=2) is None


# --- Recording Tests ---
def test_recording_creation(sample_recording):
    assert sample_recording.source_file == Path("dummy_file.rec")
    assert sample_recording.sampling_rate == SAMPLE_RATE
    assert sample_recording.num_channels == 2
    assert "Vm" in sample_recording.channel_names
    assert "Im" in sample_recording.channel_names
    assert sample_recording.max_trials == 2  # Max trials across channels


# --- Averaging Tests ---
def test_channel_get_averaged_data_success(sample_channel):
    # Modify fixture to have equal length trials if needed for this test
    sample_channel.data_trials = [np.array([1.0, 2.0, 3.0]), np.array([3.0, 4.0, 5.0])]
    avg_data = sample_channel.get_averaged_data()
    assert avg_data is not None
    assert isinstance(avg_data, np.ndarray)
    assert avg_data.ndim == 1
    assert len(avg_data) == 3
    assert np.allclose(avg_data, np.array([2.0, 3.0, 4.0]))  # (1+3)/2, (2+4)/2, (3+5)/2


def test_channel_get_averaged_data_unequal_length(sample_channel):
    # Use original fixture with unequal lengths
    sample_channel.data_trials = [DATA_TRIAL_1, DATA_TRIAL_2]
    avg_data = sample_channel.get_averaged_data()
    assert avg_data is None  # Should fail or return None


def test_channel_get_averaged_data_no_trials(sample_channel):
    sample_channel.data_trials = []
    avg_data = sample_channel.get_averaged_data()
    assert avg_data is None


def test_channel_get_averaged_time_vector(sample_channel):
    sample_channel.data_trials = [np.array([1.0, 2.0, 3.0]), np.array([3.0, 4.0, 5.0])]
    sample_channel.sampling_rate = 100.0  # Example rate
    sample_channel.t_start = 0.1
    avg_time = sample_channel.get_averaged_time_vector()
    assert avg_time is not None
    assert len(avg_time) == 3
    assert np.allclose(avg_time, np.array([0.1, 0.11, 0.12]))  # t_start, t_start + 1/rate, ...


def test_channel_get_averaged_time_vector_fail(sample_channel):
    sample_channel.data_trials = [DATA_TRIAL_1, DATA_TRIAL_2]  # Unequal lengths
    avg_time = sample_channel.get_averaged_time_vector()
    assert avg_time is None
