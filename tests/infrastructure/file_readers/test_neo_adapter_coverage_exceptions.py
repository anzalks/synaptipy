import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter
from synaptipy.shared.error_handling import FileReadError


class MockBlock:
    def __init__(self, segments=None):
        self.segments = segments or []
        self.rec_datetime = None


@pytest.fixture
def neo_adapter():
    return NeoAdapter()


def test_read_recording_type_error_signal_group_mode(neo_adapter, tmp_path):
    # Mock IO class
    class MockIO:
        def __init__(self, filename):
            self.filename = filename

        def read_block(self, lazy=False, signal_group_mode=None):
            if signal_group_mode is not None:
                raise TypeError("unexpected keyword argument 'signal_group_mode'")
            # If retry succeeds, return empty block
            return MockBlock()

    with patch.object(neo_adapter, "_get_neo_io_class", return_value=MockIO):
        rec = neo_adapter.read_recording(tmp_path / "test.test", lazy=False)
        assert rec is not None


def test_read_recording_type_error_lazy_fallback(neo_adapter, tmp_path):
    class MockIO:
        def __init__(self, filename):
            pass

        def read_block(self, lazy=False, signal_group_mode=None):
            if not lazy:
                raise Exception("First non-lazy attempt fails")
            if signal_group_mode is not None:
                raise TypeError("unexpected keyword argument 'signal_group_mode'")
            return MockBlock()

    with patch.object(neo_adapter, "_get_neo_io_class", return_value=MockIO):
        rec = neo_adapter.read_recording(tmp_path / "test.test", lazy=False)
        assert rec is not None


def test_lazy_fallback_fails(neo_adapter, tmp_path):
    class MockIO:
        def __init__(self, filename):
            pass

        def read_block(self, lazy=False, signal_group_mode=None):
            raise Exception("Always fails")

    with patch.object(neo_adapter, "_get_neo_io_class", return_value=MockIO):
        with pytest.raises(FileReadError, match="Could not read file"):
            neo_adapter.read_recording(tmp_path / "test.test", lazy=False)


def test_pyabf_rescue_fails_import(neo_adapter, tmp_path):
    class MockIO:
        def __init__(self, filename):
            pass

        def read_block(self, **kwargs):
            raise Exception("Neo fails")

    with patch.object(neo_adapter, "_get_neo_io_class", return_value=MockIO):
        with patch.dict(sys.modules, {"pyabf": None}):
            with pytest.raises(FileReadError, match="ABF rescue failed"):
                neo_adapter.read_recording(tmp_path / "test.abf", lazy=False)


def test_unexpected_error_during_extraction(neo_adapter):
    class MockReader:
        def read_raw_protocol(self):
            return "not a list"

    # Should not crash, just returns None, None
    proto, curr = neo_adapter._extract_axon_metadata(MockReader())
    assert proto is None
    assert curr is None


def test_populate_command_signals_errors(neo_adapter):
    class MockReader:
        def read_raw_protocol(self):
            raise Exception("Protocol extraction error")

    mock_channel = MagicMock()
    mock_channel.units = "mV"
    mock_recording = MagicMock()

    neo_adapter._populate_command_signals(MockReader(), [mock_channel], mock_recording, lazy=False)
    # Should just catch the exception and log, no crash


def test_unit_error_re_raise(neo_adapter):
    mock_seg = MagicMock()
    mock_anasig = MagicMock()
    mock_anasig.sampling_rate = 50.0
    mock_anasig.units = MagicMock(dimensionality="Hz")
    mock_anasig.t_start = 0.0
    mock_anasig.magnitude = np.array([1.0])
    mock_seg.analogsignals = [mock_anasig]

    with patch(
        "synaptipy.infrastructure.file_readers.neo_adapter.validate_sampling_rate",
        side_effect=Exception("Mock Generic Exception"),
    ):
        # Should not raise, should just log and continue
        neo_adapter._process_segment_signals(mock_seg, 0, {}, False, None, {})
