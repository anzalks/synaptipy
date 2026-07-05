"""Targeted coverage tests for core.analysis.cross_file_utils missed lines."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

# ---------------------------------------------------------------------------
# _resolve_effective_trials — line 27 (Current Trial branch)
# ---------------------------------------------------------------------------


def test_resolve_effective_trials_current_trial_branch():
    from synaptipy.core.analysis.cross_file_utils import _resolve_effective_trials

    item = {"target_type": "Current Trial", "trial_index": 3}
    channel = MagicMock(num_trials=10)
    result = _resolve_effective_trials(item, channel, [0, 1, 2])
    assert result == [3]


def test_resolve_effective_trials_recording_branch():
    from synaptipy.core.analysis.cross_file_utils import _resolve_effective_trials

    item = {"target_type": "Recording"}
    channel = MagicMock(num_trials=5)
    result = _resolve_effective_trials(item, channel, [0])
    assert result == [0, 1, 2, 3, 4]


def test_resolve_effective_trials_fallback_branch():
    from synaptipy.core.analysis.cross_file_utils import _resolve_effective_trials

    item = {}
    channel = MagicMock(num_trials=10)
    result = _resolve_effective_trials(item, channel, [2, 4])
    assert result == [2, 4]


# ---------------------------------------------------------------------------
# average_padded_trials — lines 361, 371-375
# ---------------------------------------------------------------------------


def test_average_padded_trials_empty_returns_none():
    from synaptipy.core.analysis.cross_file_utils import average_padded_trials

    result = average_padded_trials([])
    assert result is None


def test_average_padded_trials_equal_lengths():
    from synaptipy.core.analysis.cross_file_utils import average_padded_trials

    a = np.array([1.0, 2.0, 3.0])
    b = np.array([3.0, 4.0, 5.0])
    result = average_padded_trials([a, b])
    np.testing.assert_allclose(result, [2.0, 3.0, 4.0])


def test_average_padded_trials_unequal_lengths_nan_pad():
    """Lines 371-375: NaN-padding path for unequal-length arrays."""
    from synaptipy.core.analysis.cross_file_utils import average_padded_trials

    short = np.array([1.0, 2.0])
    long_ = np.array([3.0, 4.0, 6.0])
    result = average_padded_trials([short, long_])
    assert result is not None
    assert len(result) == 3
    # First two points: average of both; third point: only long contributes
    np.testing.assert_allclose(result[:2], [2.0, 3.0])
    np.testing.assert_allclose(result[2], 6.0)


# ---------------------------------------------------------------------------
# build_averaged_recording — lines 252-253, 267-271, 286-287
# ---------------------------------------------------------------------------


def test_build_averaged_recording_no_loadable_file():
    """Lines 255-257: all paths fail to load → returns None."""
    from synaptipy.core.analysis.cross_file_utils import build_averaged_recording

    adapter = MagicMock()
    adapter.read_recording.return_value = None
    items = [{"path": "/nonexistent/a.wcp"}, {"path": "/nonexistent/b.wcp"}]
    result = build_averaged_recording(items, [0], adapter)
    assert result is None


def test_build_averaged_recording_all_channels_empty():
    """Lines 285-287: reference recording loads but all channels average to None → None."""
    from pathlib import Path

    from synaptipy.core.analysis.cross_file_utils import build_averaged_recording

    # Build a reference recording with one channel
    from synaptipy.core.data_model import Channel, Recording

    rec = Recording(source_file=Path("dummy.wcp"))
    ch = Channel(id="ch0", name="V", units="mV", sampling_rate=10000.0, data_trials=[np.zeros(100)])
    rec.channels = {"ch0": ch}
    rec.sampling_rate = 10000.0
    rec.duration = 0.01

    adapter = MagicMock()
    adapter.read_recording.side_effect = [rec, None, None]

    # All items will fail to produce a valid average (second call returns None)
    items = [{"path": "a.wcp"}, {"path": "b.wcp"}]

    # Patch get_cross_file_average to return (None, None, 0, None) for every channel
    from unittest.mock import patch

    with patch("synaptipy.core.analysis.cross_file_utils.get_cross_file_average") as mock_avg:
        mock_avg.return_value = (None, None, 0, None)
        result = build_averaged_recording(items, [0], adapter)
    assert result is None


def test_build_averaged_recording_success():
    """Successful path: produces a synthetic Recording."""
    from pathlib import Path

    from synaptipy.core.analysis.cross_file_utils import build_averaged_recording
    from synaptipy.core.data_model import Channel, Recording

    rec = Recording(source_file=Path("dummy.wcp"))
    time_arr = np.linspace(0, 0.01, 100)
    data_arr = np.zeros(100)
    ch = Channel(id="ch0", name="V", units="mV", sampling_rate=10000.0, data_trials=[data_arr])
    rec.channels = {"ch0": ch}
    rec.sampling_rate = 10000.0
    rec.duration = 0.01

    adapter = MagicMock()
    adapter.read_recording.return_value = rec

    from unittest.mock import patch

    with patch("synaptipy.core.analysis.cross_file_utils.get_cross_file_average") as mock_avg:
        mock_avg.return_value = (time_arr, data_arr, 2, None)
        result = build_averaged_recording([{"path": "a.wcp"}, {"path": "b.wcp"}], [0], adapter)
    assert result is not None
    assert "ch0" in result.channels
