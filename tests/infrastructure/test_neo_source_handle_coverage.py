# tests/infrastructure/test_neo_source_handle_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage-boosting tests for infrastructure/file_readers/neo_source_handle.py.

Targets previously uncovered lines:
  61-62  : log.debug + return None when sig_idx is invalid
  71-73  : return np.array(data) path and return None when ch_offset out of range
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from Synaptipy.infrastructure.file_readers.neo_source_handle import NeoSourceHandle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle_with_mock_block(n_segments: int = 1, n_signals: int = 1, n_samples: int = 50, n_channels: int = 2):
    """Return a NeoSourceHandle backed by a MagicMock neo.Block."""
    block = MagicMock()

    # Build fake analog signals: shape (n_samples, n_channels)
    raw_data = np.random.default_rng(0).normal(size=(n_samples, n_channels))

    analog_signal = MagicMock()
    analog_signal.shape = (n_samples, n_channels)
    # [:, 0] returns a slice mock that has .magnitude
    slice_mock = MagicMock()
    slice_mock.magnitude = raw_data[:, 0]
    analog_signal.__getitem__ = MagicMock(return_value=slice_mock)

    segment = MagicMock()
    segment.analogsignals = [analog_signal] * n_signals

    block.segments = [segment] * n_segments

    handle = NeoSourceHandle(source_path=Path("/fake/test.abf"), block=block)
    handle.set_channel_map(
        {
            "Ch0": {"signal_index": 0, "channel_offset": 0},
        }
    )
    return handle, raw_data


# ---------------------------------------------------------------------------
# Tests for lines 61-62: invalid sig_idx paths
# ---------------------------------------------------------------------------


class TestLoadChannelDataInvalidSigIdx:
    def test_sig_idx_none_returns_none(self):
        """Lines 61-62: mapping has no 'signal_index' → sig_idx is None → return None."""
        handle, _ = _make_handle_with_mock_block()
        handle.set_channel_map({"Ch0": {"channel_offset": 0}})  # No signal_index key
        result = handle.load_channel_data("Ch0", 0)
        assert result is None

    def test_sig_idx_out_of_range_returns_none(self):
        """Lines 61-62: sig_idx >= len(analogsignals) → return None."""
        handle, _ = _make_handle_with_mock_block(n_signals=1)
        handle.set_channel_map({"Ch0": {"signal_index": 99, "channel_offset": 0}})  # 99 > 0 signals
        result = handle.load_channel_data("Ch0", 0)
        assert result is None


# ---------------------------------------------------------------------------
# Tests for lines 71-73: data extraction paths
# ---------------------------------------------------------------------------


class TestLoadChannelDataExtraction:
    def test_valid_signal_returns_magnitude(self):
        """Existing path: analog_signal has .magnitude → returns it."""
        handle, raw_data = _make_handle_with_mock_block(n_samples=50, n_channels=2)
        result = handle.load_channel_data("Ch0", 0)
        assert result is not None
        np.testing.assert_array_equal(result, raw_data[:, 0])

    def test_signal_without_magnitude_returns_array(self):
        """Lines 71-73: slice has no 'magnitude' attr → return np.array(data)."""
        block = MagicMock()

        raw_col = np.arange(50, dtype=float)
        analog_signal = MagicMock()
        analog_signal.shape = (50, 1)
        # Return a plain numpy array (no .magnitude attribute)
        analog_signal.__getitem__ = MagicMock(return_value=raw_col)

        segment = MagicMock()
        segment.analogsignals = [analog_signal]
        block.segments = [segment]

        handle = NeoSourceHandle(source_path=Path("/fake/plain.abf"), block=block)
        handle.set_channel_map({"Ch0": {"signal_index": 0, "channel_offset": 0}})
        result = handle.load_channel_data("Ch0", 0)
        assert result is not None
        assert isinstance(result, np.ndarray)

    def test_ch_offset_out_of_shape_returns_none(self):
        """Line 73 (final return None): ch_offset >= shape[1] → None."""
        block = MagicMock()

        raw_data = np.zeros((50, 1))  # noqa: F841 – kept for clarity
        analog_signal = MagicMock()
        analog_signal.shape = (50, 1)  # Only 1 channel column

        segment = MagicMock()
        segment.analogsignals = [analog_signal]
        block.segments = [segment]

        handle = NeoSourceHandle(source_path=Path("/fake/small.abf"), block=block)
        handle.set_channel_map({"Ch0": {"signal_index": 0, "channel_offset": 5}})  # 5 >= 1
        result = handle.load_channel_data("Ch0", 0)
        assert result is None


# ---------------------------------------------------------------------------
# Existing short-circuit paths (for completeness)
# ---------------------------------------------------------------------------


class TestLoadChannelDataShortCircuits:
    def test_no_block_returns_none(self):
        handle = NeoSourceHandle(source_path=Path("/fake/x.abf"), block=None)
        assert handle.load_channel_data("Ch0", 0) is None

    def test_trial_index_out_of_range_returns_none(self):
        handle, _ = _make_handle_with_mock_block(n_segments=1)
        assert handle.load_channel_data("Ch0", 99) is None

    def test_missing_mapping_returns_none(self):
        handle, _ = _make_handle_with_mock_block()
        handle.set_channel_map({})  # No mapping for "Ch0"
        assert handle.load_channel_data("Ch0", 0) is None
