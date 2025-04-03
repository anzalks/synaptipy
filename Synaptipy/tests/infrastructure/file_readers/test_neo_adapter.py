import pytest
from pathlib import Path
import numpy as np

# Assuming neo_adapter_instance fixture is in conftest.py
# Assuming sample_abf_path fixture is in conftest.py providing a valid Path object
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.shared.error_handling import UnsupportedFormatError, FileNotFoundError, FileReadError


# --- Test _get_neo_io_class ---

def test_get_io_class_supported(neo_adapter_instance, sample_abf_path):
    """Test if it correctly identifies AxonIO for .abf files."""
    from neo.io import AxonIO # Import specific IO for assertion
    io_class = neo_adapter_instance._get_neo_io_class(sample_abf_path)
    assert io_class is AxonIO

def test_get_io_class_unsupported(neo_adapter_instance, tmp_path):
    """Test if it raises UnsupportedFormatError for an unknown extension."""
    unsupported_file = tmp_path / "test.unsupported_xyz"
    unsupported_file.touch() # Create empty file
    with pytest.raises(UnsupportedFormatError):
        neo_adapter_instance._get_neo_io_class(unsupported_file)

def test_get_io_class_not_found(neo_adapter_instance):
    """Test if it raises FileNotFoundError for a non-existent file."""
    non_existent_file = Path("./surely_this_does_not_exist.abf")
    with pytest.raises(FileNotFoundError):
        neo_adapter_instance._get_neo_io_class(non_existent_file)

# --- Test read_recording ---

def test_read_recording_abf_success(neo_adapter_instance, sample_abf_path):
    """Test successful reading of the sample ABF file."""
    recording = neo_adapter_instance.read_recording(sample_abf_path)

    assert isinstance(recording, Recording)
    assert recording.source_file == sample_abf_path
    assert recording.sampling_rate is not None
    assert recording.sampling_rate > 0
    assert recording.duration is not None
    assert recording.duration > 0
    assert recording.num_channels > 0 # Expect at least one channel

    # Check properties of the first channel (adapt based on your sample file)
    first_channel_id = list(recording.channels.keys())[0]
    ch = recording.channels[first_channel_id]
    assert isinstance(ch, Channel)
    assert ch.id is not None
    assert ch.name is not None
    assert ch.units is not None # e.g., 'mV' or 'pA'
    assert ch.sampling_rate == recording.sampling_rate
    assert ch.num_trials > 0
    assert ch.num_samples > 0
    assert isinstance(ch.get_data(0), np.ndarray)
    assert len(ch.get_data(0)) == ch.num_samples

    # Check specific metadata if known for the sample file
    # assert recording.protocol_name == "ExpectedProtocol" # If applicable
    # assert recording.metadata.get('neo_reader_class') == 'AxonIO'


def test_read_recording_not_found(neo_adapter_instance):
    """Test read_recording raises FileNotFoundError."""
    non_existent_file = Path("./surely_this_does_not_exist_either.abf")
    with pytest.raises(FileNotFoundError):
        neo_adapter_instance.read_recording(non_existent_file)

def test_read_recording_unsupported(neo_adapter_instance, tmp_path):
    """Test read_recording raises UnsupportedFormatError."""
    unsupported_file = tmp_path / "another.unsupported_xyz"
    unsupported_file.touch()
    with pytest.raises(UnsupportedFormatError):
        neo_adapter_instance.read_recording(unsupported_file)

# TODO: Add a test for a corrupted file if you have one, expecting FileReadError
# def test_read_recording_corrupted(neo_adapter_instance, corrupted_file_path):
#     with pytest.raises(FileReadError):
#         neo_adapter_instance.read_recording(corrupted_file_path)