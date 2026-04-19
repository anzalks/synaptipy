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


# ---------------------------------------------------------------------------
# UndoStack tests
# ---------------------------------------------------------------------------


def test_undo_stack_push_pop():
    from Synaptipy.core.data_model import UndoStack

    stack = UndoStack(max_depth=5)
    assert not stack.can_undo()
    assert stack.depth == 0
    stack.push("step1", {"data": [1, 2, 3]})
    assert stack.can_undo()
    assert stack.depth == 1
    label, state = stack.pop()
    assert label == "step1"
    assert not stack.can_undo()


def test_undo_stack_max_depth():
    from Synaptipy.core.data_model import UndoStack

    stack = UndoStack(max_depth=3)
    for i in range(6):
        stack.push(f"step{i}", {"v": i})
    assert stack.depth == 3
    label, _ = stack.pop()
    # Oldest entries evicted – should get step3, step4, step5
    assert label == "step5"


def test_undo_stack_pop_empty_returns_none():
    from Synaptipy.core.data_model import UndoStack

    stack = UndoStack()
    assert stack.pop() is None


def test_undo_stack_clear():
    from Synaptipy.core.data_model import UndoStack

    stack = UndoStack()
    stack.push("x", {})
    stack.clear()
    assert stack.depth == 0


def test_undo_stack_repr():
    from Synaptipy.core.data_model import UndoStack

    stack = UndoStack()
    stack.push("my_op", {})
    assert "my_op" in repr(stack)


# ---------------------------------------------------------------------------
# Channel undo support tests
# ---------------------------------------------------------------------------


def test_channel_push_undo_and_undo(sample_channel):
    original = sample_channel.data_trials[0].copy()
    sample_channel.push_undo("before filter")
    # Simulate destructive op
    sample_channel.data_trials[0] = np.zeros_like(original)
    assert np.all(sample_channel.data_trials[0] == 0)
    restored = sample_channel.undo()
    assert restored is True
    np.testing.assert_array_equal(sample_channel.data_trials[0], original)


def test_channel_undo_empty_returns_false(sample_channel):
    result = sample_channel.undo()
    assert result is False


def test_channel_can_undo_property(sample_channel):
    assert not sample_channel.can_undo
    sample_channel.push_undo("op")
    assert sample_channel.can_undo


# ---------------------------------------------------------------------------
# Channel lazy-loading tests
# ---------------------------------------------------------------------------


def test_channel_lazy_loading_via_callable():
    """Loader callable is invoked when data_trials is empty."""
    payload = np.array([1.0, 2.0, 3.0])

    def loader(idx):
        return payload if idx == 0 else None

    ch = Channel(id="lazy", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[], loader=loader)
    data = ch.get_data(0)
    np.testing.assert_array_equal(data, payload)
    # Second call should return cached value
    data2 = ch.get_data(0)
    np.testing.assert_array_equal(data2, payload)


def test_channel_lazy_loading_via_object():
    """Loader with load_trial method is invoked."""
    payload = np.arange(10.0)

    class FakeLoader:
        def load_trial(self, idx):
            return payload if idx == 0 else None

    ch = Channel(id="lazy2", name="Im", units="pA", sampling_rate=500.0, data_trials=[], loader=FakeLoader())
    data = ch.get_data(0)
    np.testing.assert_array_equal(data, payload)


def test_channel_lazy_out_of_range_returns_none():
    ch = Channel(id="x", name="X", units="V", sampling_rate=100.0, data_trials=[np.ones(10)])
    assert ch.get_data(5) is None


# ---------------------------------------------------------------------------
# Channel helper property tests
# ---------------------------------------------------------------------------


def test_channel_get_primary_data_label_voltage():
    ch = Channel(id="v", name="V", units="mV", sampling_rate=1000.0, data_trials=[])
    assert ch.get_primary_data_label() == "Voltage"


def test_channel_get_primary_data_label_current():
    ch = Channel(id="i", name="I", units="pA", sampling_rate=1000.0, data_trials=[])
    assert ch.get_primary_data_label() == "Current"


def test_channel_get_primary_data_label_unknown():
    ch = Channel(id="u", name="U", units="unknown", sampling_rate=1000.0, data_trials=[])
    label = ch.get_primary_data_label()
    assert label in ("Voltage", "Current", "Signal")


def test_channel_get_data_bounds():
    data = np.array([-5.0, 0.0, 10.0])
    ch = Channel(id="b", name="B", units="mV", sampling_rate=1000.0, data_trials=[data])
    lo, hi = ch.get_data_bounds()
    assert lo == pytest.approx(-5.0)
    assert hi == pytest.approx(10.0)


def test_channel_get_data_bounds_empty():
    ch = Channel(id="empty", name="E", units="mV", sampling_rate=1000.0, data_trials=[])
    assert ch.get_data_bounds() is None


def test_channel_get_finite_data_bounds():
    data = np.array([-1.0, 0.0, np.inf, 2.0, np.nan])
    ch = Channel(id="fin", name="F", units="mV", sampling_rate=1000.0, data_trials=[data])
    lo, hi = ch.get_finite_data_bounds()
    assert lo == pytest.approx(-1.0)
    assert hi == pytest.approx(2.0)


def test_channel_get_current_data():
    ch = Channel(id="c", name="C", units="pA", sampling_rate=1000.0, data_trials=[])
    ch.current_data_trials = [np.array([1.0, 2.0])]
    np.testing.assert_array_equal(ch.get_current_data(0), np.array([1.0, 2.0]))
    assert ch.get_current_data(5) is None


def test_channel_get_averaged_current_data():
    ch = Channel(id="ac", name="AC", units="pA", sampling_rate=1000.0, data_trials=[])
    ch.current_data_trials = [np.array([2.0, 4.0]), np.array([4.0, 6.0])]
    avg = ch.get_averaged_current_data()
    np.testing.assert_allclose(avg, [3.0, 5.0])


def test_channel_get_averaged_current_data_empty():
    ch = Channel(id="empty_c", name="C", units="pA", sampling_rate=1000.0, data_trials=[])
    assert ch.get_averaged_current_data() is None


def test_channel_num_samples_varying_lengths():
    ch = Channel(
        id="var",
        name="V",
        units="mV",
        sampling_rate=1000.0,
        data_trials=[np.ones(100), np.ones(200)],
    )
    # Should return first trial length with a warning
    assert ch.num_samples == 100


def test_channel_get_consistent_samples_inconsistent():
    ch = Channel(
        id="inconsist",
        name="V",
        units="mV",
        sampling_rate=1000.0,
        data_trials=[np.ones(100), np.ones(200)],
    )
    with pytest.raises(ValueError):
        ch.get_consistent_samples()


def test_channel_get_consistent_samples_zero():
    ch = Channel(id="z", name="Z", units="mV", sampling_rate=1000.0, data_trials=[])
    assert ch.get_consistent_samples() == 0


def test_channel_repr(sample_channel):
    r = repr(sample_channel)
    assert "ch1" in r


def test_channel_relative_averaged_time_vector(sample_channel):
    sample_channel.data_trials = [np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0])]
    sample_channel.sampling_rate = 100.0
    tv = sample_channel.get_relative_averaged_time_vector()
    assert tv is not None
    assert tv[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Recording additional tests
# ---------------------------------------------------------------------------


def test_recording_channel_names(sample_recording):
    names = sample_recording.channel_names
    assert "Vm" in names
    assert "Im" in names


def test_recording_get_channel(sample_recording):
    ch = sample_recording.channels.get("1")
    assert ch is not None
    assert ch.name == "Vm"


def test_recording_max_trials(sample_recording):
    assert sample_recording.max_trials == 2


def test_recording_num_channels(sample_recording):
    assert sample_recording.num_channels == 2
