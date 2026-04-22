# tests/core/analysis/test_cross_file_utils.py
# -*- coding: utf-8 -*-
"""
Unit tests for Synaptipy.core.analysis.cross_file_utils.

These tests exercise the pure-math functions directly without any Qt or GUI
infrastructure, so no ``qtbot`` fixture is required.  All Recording / channel
objects are replaced with lightweight mocks.
"""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from Synaptipy.core.analysis.cross_file_utils import (
    extract_per_file_trace,
    get_cross_file_average,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel(data_map, time_map):
    """Return a mock channel backed by dict look-ups."""
    ch = MagicMock()
    ch.get_data.side_effect = lambda idx: data_map.get(idx)
    ch.get_relative_time_vector.side_effect = lambda idx: time_map.get(idx)
    ch.num_trials = max(data_map.keys()) + 1 if data_map else 0
    ch.name = "Ch0"
    ch.units = "mV"
    return ch


def _make_recording(channels_dict):
    """Return a mock Recording with the supplied channel dict."""
    rec = MagicMock()
    rec.channels = channels_dict
    return rec


def _make_adapter(*recordings):
    """Return a mock NeoAdapter whose read_recording returns each recording in sequence."""
    adapter = MagicMock()
    if len(recordings) == 1:
        adapter.read_recording.return_value = recordings[0]
    else:
        adapter.read_recording.side_effect = list(recordings)
    return adapter


# ---------------------------------------------------------------------------
# Tests for extract_per_file_trace
# ---------------------------------------------------------------------------


class TestExtractPerFileTrace:
    def test_single_trial_single_file(self):
        """Returns time and averaged data for a single trial."""
        t = np.linspace(0, 1, 50)
        d = np.ones(50) * 3.0
        ch = _make_channel({0: d}, {0: t})
        adapter = _make_adapter(_make_recording({0: ch}))

        item = {"path": Path("file.abf")}
        time_out, avg_out = extract_per_file_trace(item, [0], 0, adapter)

        np.testing.assert_allclose(time_out, t)
        np.testing.assert_allclose(avg_out, 3.0)

    def test_multi_trial_averages_within_file(self):
        """Multiple parsed_trials from one file are averaged together."""
        t = np.linspace(0, 1, 100)
        ch = _make_channel(
            {0: np.ones(100) * 1.0, 1: np.ones(100) * 3.0},
            {0: t.copy(), 1: t.copy()},
        )
        adapter = _make_adapter(_make_recording({0: ch}))

        item = {"path": Path("multi.abf")}
        _, avg_out = extract_per_file_trace(item, [0, 1], 0, adapter)

        np.testing.assert_allclose(avg_out, 2.0)

    def test_mismatched_trial_lengths_truncated(self):
        """Trials of different lengths are truncated to the shortest."""
        t_long = np.linspace(0, 1, 100)
        t_short = np.linspace(0, 1, 60)
        ch = _make_channel(
            {0: np.ones(100) * 2.0, 1: np.ones(60) * 4.0},
            {0: t_long, 1: t_short},
        )
        adapter = _make_adapter(_make_recording({0: ch}))

        item = {"path": Path("mismatch.abf")}
        time_out, avg_out = extract_per_file_trace(item, [0, 1], 0, adapter)

        assert len(avg_out) == 60
        np.testing.assert_allclose(avg_out, 3.0)  # mean(2, 4)

    def test_no_path_returns_none(self):
        """Item with no path returns None without calling the adapter."""
        adapter = MagicMock()
        result = extract_per_file_trace({}, [0], 0, adapter)
        assert result is None
        adapter.read_recording.assert_not_called()

    def test_adapter_returns_none_recording(self):
        """If read_recording returns None, the function returns None."""
        adapter = _make_adapter(None)
        result = extract_per_file_trace({"path": Path("missing.abf")}, [0], 0, adapter)
        assert result is None

    def test_channel_idx_out_of_range(self):
        """Channel index beyond available channels returns None."""
        ch = _make_channel({0: np.ones(10)}, {0: np.linspace(0, 1, 10)})
        adapter = _make_adapter(_make_recording({0: ch}))
        result = extract_per_file_trace({"path": Path("f.abf")}, [0], channel_idx=5, neo_adapter=adapter)
        assert result is None

    def test_trial_returns_none_data(self):
        """Trial whose get_data returns None causes the item to be skipped."""
        ch = _make_channel({}, {})  # all look-ups return None
        adapter = _make_adapter(_make_recording({0: ch}))
        result = extract_per_file_trace({"path": Path("f.abf")}, [0], 0, adapter)
        assert result is None

    def test_index_error_from_get_data_skipped(self):
        """IndexError from get_data is caught; function returns None."""
        ch = MagicMock()
        ch.get_data.side_effect = IndexError("no trial")
        ch.get_relative_time_vector.side_effect = IndexError("no trial")
        adapter = _make_adapter(_make_recording({0: ch}))
        result = extract_per_file_trace({"path": Path("f.abf")}, [0], 0, adapter)
        assert result is None

    def test_second_channel_selected(self):
        """channel_idx=1 selects the second channel sorted by key."""
        t = np.linspace(0, 1, 20)
        ch0 = _make_channel({0: np.zeros(20)}, {0: t.copy()})
        ch1 = _make_channel({0: np.ones(20) * 7.0}, {0: t.copy()})
        adapter = _make_adapter(_make_recording({0: ch0, 1: ch1}))
        _, avg_out = extract_per_file_trace({"path": Path("two_ch.abf")}, [0], 1, adapter)
        np.testing.assert_allclose(avg_out, 7.0)


# ---------------------------------------------------------------------------
# Tests for get_cross_file_average
# ---------------------------------------------------------------------------


class TestGetCrossFileAverage:
    def test_two_files_same_length(self):
        """Grand average of two identical-length per-file averages is correct."""
        t = np.linspace(0, 1, 100)
        d_a = np.ones(100) * 2.0
        d_b = np.ones(100) * 4.0
        ch_a = _make_channel({0: d_a}, {0: t.copy()})
        ch_b = _make_channel({0: d_b}, {0: t.copy()})
        adapter = _make_adapter(
            _make_recording({0: ch_a}),
            _make_recording({0: ch_b}),
        )
        items = [{"path": Path("a.abf")}, {"path": Path("b.abf")}]

        time_out, grand_avg, n = get_cross_file_average(items, [0], 0, adapter)

        assert n == 2
        assert len(grand_avg) == 100
        np.testing.assert_allclose(grand_avg, 3.0)  # mean(2, 4)

    def test_two_files_different_lengths_truncated(self):
        """Grand average is truncated to shortest per-file series."""
        t_long = np.linspace(0, 1, 100)
        t_short = np.linspace(0, 1, 80)
        ch_a = _make_channel({0: np.ones(100)}, {0: t_long})
        ch_b = _make_channel({0: np.ones(80) * 3.0}, {0: t_short})
        adapter = _make_adapter(
            _make_recording({0: ch_a}),
            _make_recording({0: ch_b}),
        )
        items = [{"path": Path("long.abf")}, {"path": Path("short.abf")}]

        _, grand_avg, n = get_cross_file_average(items, [0], 0, adapter)

        assert n == 2
        assert len(grand_avg) == 80
        np.testing.assert_allclose(grand_avg, 2.0)  # mean(1, 3)

    def test_missing_trial_skipped(self):
        """File missing the requested trial is silently excluded."""
        t = np.linspace(0, 1, 50)
        d_good = np.ones(50) * 5.0
        ch_good = _make_channel({20: d_good}, {20: t.copy()})
        ch_bad = MagicMock()
        ch_bad.get_data.side_effect = IndexError("no such trial")
        ch_bad.get_relative_time_vector.side_effect = IndexError("no such trial")

        adapter = _make_adapter(
            _make_recording({0: ch_good}),
            _make_recording({0: ch_bad}),
        )
        items = [{"path": Path("good.abf")}, {"path": Path("bad.abf")}]

        _, avg_out, n = get_cross_file_average(items, [20], 0, adapter)

        assert n == 1
        np.testing.assert_allclose(avg_out, 5.0)

    def test_all_files_missing_returns_none(self):
        """Returns (None, None, 0) when no file can supply the trial."""
        ch = _make_channel({}, {})  # all look-ups return None
        adapter = _make_adapter(
            _make_recording({0: ch}),
            _make_recording({0: ch}),
        )
        items = [{"path": Path("a.abf")}, {"path": Path("b.abf")}]

        time_out, avg_out, n = get_cross_file_average(items, [0], 0, adapter)

        assert n == 0
        assert time_out is None
        assert avg_out is None

    def test_channel_idx_out_of_range_skipped(self):
        """Files with fewer channels than requested are silently skipped."""
        rec = MagicMock()
        rec.channels = {}
        adapter = _make_adapter(rec)
        items = [{"path": Path("narrow.abf")}]

        _, _, n = get_cross_file_average(items, [0], channel_idx=5, neo_adapter=adapter)

        assert n == 0

    def test_empty_items_list(self):
        """Empty items list returns (None, None, 0) immediately."""
        adapter = MagicMock()
        time_out, avg_out, n = get_cross_file_average([], [0], 0, adapter)
        assert n == 0
        assert time_out is None
        assert avg_out is None
        adapter.read_recording.assert_not_called()

    def test_multi_trial_within_file(self):
        """Multiple parsed_trials per file are averaged before grand-averaging."""
        t = np.linspace(0, 1, 100)
        ch = _make_channel(
            {0: np.ones(100) * 1.0, 1: np.ones(100) * 3.0},
            {0: t.copy(), 1: t.copy()},
        )
        adapter = _make_adapter(_make_recording({0: ch}))
        items = [{"path": Path("multi.abf")}]

        _, avg_out, n = get_cross_file_average(items, [0, 1], 0, adapter)

        assert n == 1
        np.testing.assert_allclose(avg_out, 2.0)

    def test_time_array_corresponds_to_first_valid_file(self):
        """The returned time array originates from the first valid file."""
        t_a = np.linspace(0, 0.5, 50)
        t_b = np.linspace(0, 0.5, 50)
        ch_a = _make_channel({0: np.ones(50)}, {0: t_a})
        ch_b = _make_channel({0: np.ones(50) * 2.0}, {0: t_b})
        adapter = _make_adapter(
            _make_recording({0: ch_a}),
            _make_recording({0: ch_b}),
        )
        items = [{"path": Path("a.abf")}, {"path": Path("b.abf")}]

        time_out, _, _ = get_cross_file_average(items, [0], 0, adapter)

        np.testing.assert_allclose(time_out, t_a)
