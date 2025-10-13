import pytest
from pathlib import Path
import numpy as np

# Assuming neo_adapter_instance fixture is in conftest.py
# Assuming sample_abf_path fixture is in conftest.py providing a valid Path object
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.shared.error_handling import UnsupportedFormatError, SynaptipyFileNotFoundError, FileReadError


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
    """Test if it raises SynaptipyFileNotFoundError for a non-existent file."""
    non_existent_file = Path("./surely_this_does_not_exist.abf")
    with pytest.raises(SynaptipyFileNotFoundError):
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
    """Test read_recording raises SynaptipyFileNotFoundError."""
    non_existent_file = Path("./surely_this_does_not_exist_either.abf")
    with pytest.raises(SynaptipyFileNotFoundError):
        neo_adapter_instance.read_recording(non_existent_file)

def test_read_recording_unsupported(neo_adapter_instance, tmp_path):
    """Test read_recording raises UnsupportedFormatError."""
    unsupported_file = tmp_path / "another.unsupported_xyz"
    unsupported_file.touch()
    with pytest.raises(UnsupportedFormatError):
        neo_adapter_instance.read_recording(unsupported_file)

# --- Lazy Loading Tests ---

def test_read_recording_lazy_loading(neo_adapter_instance, sample_abf_path):
    """Test that lazy loading works correctly - data_trials should be empty initially."""
    recording = neo_adapter_instance.read_recording(sample_abf_path)

    assert isinstance(recording, Recording)
    assert recording.source_file == sample_abf_path
    
    # Check that neo_block and neo_reader are stored
    assert hasattr(recording, 'neo_block')
    assert hasattr(recording, 'neo_reader')
    assert recording.neo_block is not None
    assert recording.neo_reader is not None
    
    # Check that channels have lazy loading info
    assert recording.num_channels > 0
    first_channel_id = list(recording.channels.keys())[0]
    channel = recording.channels[first_channel_id]
    
    # Check lazy loading attributes
    assert hasattr(channel, 'lazy_info')
    assert hasattr(channel, 'metadata')
    assert hasattr(channel, '_recording_ref')
    assert channel._recording_ref is recording
    
    # For lazy loading, data_trials should be empty initially
    assert len(channel.data_trials) == 0
    
    # But num_trials should still work via metadata
    assert channel.num_trials > 0
    assert 'num_trials' in channel.metadata
    assert 'data_shape' in channel.metadata

def test_lazy_data_loading(neo_adapter_instance, sample_abf_path):
    """Test that data is loaded on-demand when get_data is called."""
    recording = neo_adapter_instance.read_recording(sample_abf_path)
    
    first_channel_id = list(recording.channels.keys())[0]
    channel = recording.channels[first_channel_id]
    
    # Initially, data_trials should be empty
    assert len(channel.data_trials) == 0
    
    # Call get_data to trigger lazy loading
    data = channel.get_data(0)
    
    # After calling get_data, data should be loaded
    assert data is not None
    assert isinstance(data, np.ndarray)
    assert len(data) > 0
    
    # data_trials should now contain the loaded data
    assert len(channel.data_trials) > 0
    assert channel.data_trials[0] is not None
    assert np.array_equal(channel.data_trials[0], data)
    
    # Calling get_data again should return the cached data
    data2 = channel.get_data(0)
    assert np.array_equal(data, data2)

def test_lazy_loading_error_handling(neo_adapter_instance, sample_abf_path):
    """Test that lazy loading handles errors gracefully."""
    recording = neo_adapter_instance.read_recording(sample_abf_path)
    
    first_channel_id = list(recording.channels.keys())[0]
    channel = recording.channels[first_channel_id]
    
    # Test accessing out-of-range trial
    data = channel.get_data(999)  # Should be out of range
    assert data is None
    
    # Test accessing valid trial
    data = channel.get_data(0)
    assert data is not None

# TODO: Add a test for a corrupted file if you have one, expecting FileReadError
# def test_read_recording_corrupted(neo_adapter_instance, corrupted_file_path):
#     with pytest.raises(FileReadError):
#         neo_adapter_instance.read_recording(corrupted_file_path)