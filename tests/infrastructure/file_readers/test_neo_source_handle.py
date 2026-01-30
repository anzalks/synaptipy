# tests/infrastructure/file_readers/test_neo_source_handle.py
"""
Tests for the NeoSourceHandle class.
"""
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np

from Synaptipy.infrastructure.file_readers.neo_source_handle import NeoSourceHandle


class TestNeoSourceHandle:
    """Tests for NeoSourceHandle."""

    def test_source_identifier(self):
        """Test source_identifier returns path string."""
        path = Path("/test/file.abf")
        handle = NeoSourceHandle(path)
        assert handle.source_identifier == str(path)

    def test_load_channel_data_no_block(self):
        """Test load_channel_data returns None when no block is set."""
        handle = NeoSourceHandle(Path("/test/file.abf"))
        result = handle.load_channel_data("0", 0)
        assert result is None

    def test_load_channel_data_invalid_trial_index(self):
        """Test load_channel_data returns None for invalid trial index."""
        mock_block = MagicMock()
        mock_block.segments = []  # Empty segments list

        handle = NeoSourceHandle(Path("/test/file.abf"), block=mock_block)
        result = handle.load_channel_data("0", 0)
        assert result is None

        result = handle.load_channel_data("0", -1)
        assert result is None

    def test_load_channel_data_no_mapping(self):
        """Test load_channel_data returns None when channel not in map."""
        mock_segment = MagicMock()
        mock_block = MagicMock()
        mock_block.segments = [mock_segment]

        handle = NeoSourceHandle(Path("/test/file.abf"), block=mock_block)
        handle.set_channel_map({})  # Empty map
        result = handle.load_channel_data("unknown_channel", 0)
        assert result is None

    def test_load_channel_data_success(self):
        """Test load_channel_data returns data when properly configured."""
        # Create mock analog signal with magnitude attribute
        mock_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        mock_quantity = MagicMock()
        mock_quantity.magnitude = mock_data
        mock_quantity.shape = (5, 1)

        mock_analog_signal = MagicMock()
        mock_analog_signal.shape = (5, 1)
        mock_analog_signal.__getitem__ = MagicMock(return_value=mock_quantity)

        mock_segment = MagicMock()
        mock_segment.analogsignals = [mock_analog_signal]

        mock_block = MagicMock()
        mock_block.segments = [mock_segment]

        handle = NeoSourceHandle(Path("/test/file.abf"), block=mock_block)
        handle.set_channel_map({"0": {"signal_index": 0, "channel_offset": 0}})

        result = handle.load_channel_data("0", 0)
        assert result is not None
        np.testing.assert_array_equal(result, mock_data)

    def test_set_channel_map(self):
        """Test set_channel_map stores the mapping."""
        handle = NeoSourceHandle(Path("/test/file.abf"))
        mapping = {"ch1": {"signal_index": 0, "channel_offset": 0}}
        handle.set_channel_map(mapping)
        assert handle._channel_map == mapping

    def test_get_metadata_empty(self):
        """Test get_metadata returns empty dict when no block."""
        handle = NeoSourceHandle(Path("/test/file.abf"))
        assert handle.get_metadata() == {}

    def test_get_metadata_with_annotations(self):
        """Test get_metadata returns block annotations."""
        mock_block = MagicMock()
        mock_block.annotations = {"key": "value", "protocol": "test"}

        handle = NeoSourceHandle(Path("/test/file.abf"), block=mock_block)
        meta = handle.get_metadata()
        assert meta == {"key": "value", "protocol": "test"}

    def test_close_calls_reader_close(self):
        """Test close calls reader.close if available."""
        mock_reader = MagicMock()
        handle = NeoSourceHandle(Path("/test/file.abf"), reader=mock_reader)
        handle.close()
        mock_reader.close.assert_called_once()

    def test_close_handles_no_reader(self):
        """Test close handles case when no reader is set."""
        handle = NeoSourceHandle(Path("/test/file.abf"))
        handle.close()  # Should not raise
