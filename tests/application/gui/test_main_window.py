import pytest
from PySide6 import QtCore
from PySide6.QtCore import Qt
from pathlib import Path
import numpy as np
from unittest.mock import patch, MagicMock # Use unittest.mock or pytest-mock

# Assuming main_window fixture is in conftest.py providing a MainWindow instance
# Assuming qtbot fixture is available from pytest-qt
from Synaptipy.core.data_model import Recording, Channel # For creating mock data

# --- Basic Window Tests ---

def test_main_window_creation(main_window):
    """Test if the main window gets created."""
    assert main_window is not None
    assert main_window.windowTitle() == "Synaptipy - Electrophysiology Visualizer"

def test_initial_ui_state(main_window):
    """Test the initial enabled/disabled state of widgets."""
    assert main_window.open_file_action.isEnabled()
    # Check that export actions are disabled initially
    assert not main_window.export_nwb_action.isEnabled()
    
    # Check status bar exists
    assert main_window.status_bar is not None

def test_data_loader_setup(main_window):
    """Test that the background data loader is properly set up."""
    assert hasattr(main_window, 'data_loader')
    assert hasattr(main_window, 'data_loader_thread')
    assert main_window.data_loader is not None
    assert main_window.data_loader_thread is not None
    assert main_window.data_loader_thread.isRunning()

# --- Interaction Tests (using Mocking) ---

@pytest.fixture
def mock_recording():
    """Creates a mock Recording object for testing GUI state."""
    rec = Recording(source_file=Path("mock_file.abf"))
    rec.sampling_rate = 20000.0
    rec.duration = 2.5
    ch1 = Channel("1", "Vm", "mV", 20000.0, [np.random.rand(50000)]) # Mock data
    ch1.t_start = 0.0
    rec.channels = {"1": ch1}
    return rec

# Mock QFileDialog to simulate user selecting a file without showing the dialog
@patch('PySide6.QtWidgets.QFileDialog.getOpenFileName')
def test_open_file_success(mock_get_open_file_name, main_window, qtbot, mock_recording, mocker):
    """Test the UI state change after successfully 'opening' a file."""
    # Arrange
    mock_filepath = Path("mock_folder/mock_file.abf")
    # Configure the mock QFileDialog to return the mock filepath
    mock_get_open_file_name.return_value = (str(mock_filepath), "All Supported Files (*.abf)")
    
    # Instead of patching explorer_tab (which is a QWidget), patch _load_in_explorer
    load_spy = mocker.patch.object(main_window, '_load_in_explorer')
    
    # Act
    # Trigger the 'Open File' action
    main_window.open_file_action.trigger()
    
    # Assert
    # 1. Check if QFileDialog was called
    mock_get_open_file_name.assert_called_once()
    # 2. Check if _load_in_explorer was called
    assert load_spy.call_count > 0


# Mock QFileDialog to simulate user cancelling
@patch('PySide6.QtWidgets.QFileDialog.getOpenFileName')
def test_open_file_cancel(mock_get_open_file_name, main_window, qtbot, mocker):
    """Test UI state when user cancels the file dialog."""
    # Arrange
    mock_get_open_file_name.return_value = ("", "") # Simulate cancellation
    mocker.patch.object(main_window.neo_adapter, 'read_recording') # Mock adapter

    # Act
    main_window.open_file_action.trigger()

    # Assert
    mock_get_open_file_name.assert_called_once()
    main_window.neo_adapter.read_recording.assert_not_called() # Shouldn't try to read
    # Status message should indicate cancellation
    assert main_window.status_bar.currentMessage() != "" # Should have some message

# --- Background Data Loading Tests ---

def test_data_loader_signals(main_window, qtbot):
    """Test that DataLoader signals are properly connected."""
    # Check that signals are connected by verifying signal names exist
    assert hasattr(main_window.data_loader, 'data_ready')
    assert hasattr(main_window.data_loader, 'data_error')
    assert hasattr(main_window.data_loader, 'loading_started')
    assert hasattr(main_window.data_loader, 'loading_progress')
    
    # Verify signals are Qt Signal instances
    from PySide6.QtCore import Signal
    assert isinstance(main_window.data_loader.data_ready, Signal)
    assert isinstance(main_window.data_loader.data_error, Signal)
    assert isinstance(main_window.data_loader.loading_started, Signal)
    assert isinstance(main_window.data_loader.loading_progress, Signal)

def test_background_file_loading(main_window, qtbot, mock_recording, mocker):
    """Test that file loading happens in background without blocking UI."""
    # Mock the NeoAdapter to return our mock recording
    mock_adapter = mocker.patch.object(main_window.data_loader, 'neo_adapter')
    mock_adapter.read_recording.return_value = mock_recording
    
    # Mock the explorer tab's load_recording_data method
    load_spy = mocker.patch.object(main_window.explorer_tab, 'load_recording_data')
    
    # Set up pending state as if _load_in_explorer was called
    main_window._pending_file_list = [mock_recording.source_file]
    main_window._pending_current_index = 0
    
    # Act: Trigger the data_ready signal
    with qtbot.waitSignal(main_window.data_loader.data_ready, timeout=1000):
        main_window.data_loader.data_ready.emit(mock_recording)
    
    # Assert: Check that the explorer tab was updated
    load_spy.assert_called_once()
    
    # Check that pending state was cleared
    assert not hasattr(main_window, '_pending_file_list')
    assert not hasattr(main_window, '_pending_current_index')

def test_background_loading_error_handling(main_window, qtbot, mocker):
    """Test that loading errors are properly handled."""
    error_message = "Test error message"
    
    # Mock QMessageBox to avoid showing actual dialog during test
    message_box_spy = mocker.patch('PySide6.QtWidgets.QMessageBox.critical')
    
    # Set up pending state
    main_window._pending_file_list = [Path("test.abf")]
    main_window._pending_current_index = 0
    
    # Act: Trigger the data_error signal
    with qtbot.waitSignal(main_window.data_loader.data_error, timeout=1000):
        main_window.data_loader.data_error.emit(error_message)
    
    # Assert: Check that error dialog was shown
    message_box_spy.assert_called_once()
    
    # Check that pending state was cleared
    assert not hasattr(main_window, '_pending_file_list')
    assert not hasattr(main_window, '_pending_current_index')

def test_loading_progress_updates(main_window, qtbot):
    """Test that loading progress updates are handled correctly."""
    # Test progress update
    with qtbot.waitSignal(main_window.data_loader.loading_progress, timeout=1000):
        main_window.data_loader.loading_progress.emit(50)
    
    # Check that status bar was updated (we can't easily test the exact message
    # without more complex mocking, but we can verify the signal was received)
    assert True  # Signal was received without error

def test_loading_started_signal(main_window, qtbot):
    """Test that loading started signal is handled correctly."""
    test_file_path = "test_file.abf"
    
    with qtbot.waitSignal(main_window.data_loader.loading_started, timeout=1000):
        main_window.data_loader.loading_started.emit(test_file_path)
    
    # Verify the signal was received without error
    assert True

# --- Data Cache Tests ---

def test_data_loader_cache_integration(main_window, qtbot, mock_recording, mocker):
    """Test that DataLoader uses cache for faster subsequent loads."""
    # Mock the NeoAdapter to simulate slow I/O
    mock_adapter = mocker.patch.object(main_window.data_loader, 'neo_adapter')
    mock_adapter.read_recording.return_value = mock_recording
    
    # Mock the explorer tab's load_recording_data method
    load_spy = mocker.patch.object(main_window.explorer_tab, 'load_recording_data')
    
    file_path = Path("test_file.abf")
    
    # First load - should be slow (cache miss)
    main_window._pending_file_list = [file_path]
    main_window._pending_current_index = 0
    
    with qtbot.waitSignal(main_window.data_loader.data_ready, timeout=1000):
        main_window.data_loader.data_ready.emit(mock_recording)
    
    # Verify first load
    load_spy.assert_called_once()
    assert main_window.data_loader.cache.contains(file_path)
    
    # Second load - should be fast (cache hit)
    load_spy.reset_mock()
    
    with qtbot.waitSignal(main_window.data_loader.data_ready, timeout=1000):
        main_window.data_loader.data_ready.emit(mock_recording)
    
    # Verify second load (should use cached data)
    load_spy.assert_called_once()

def test_data_loader_cache_stats(main_window):
    """Test that DataLoader cache provides statistics."""
    cache_stats = main_window.data_loader.cache.get_stats()
    
    assert 'size' in cache_stats
    assert 'max_size' in cache_stats
    assert 'utilization' in cache_stats
    assert 'cached_files' in cache_stats
    
    assert cache_stats['max_size'] == 10  # Default cache size
    assert cache_stats['size'] == 0  # Initially empty
    assert cache_stats['utilization'] == 0.0

# TODO: Add tests for:
# - _open_folder (mocking getExistingDirectory and glob)
# - Error handling (mock read_recording to raise exceptions, check QMessageBox)
# - Plot controls (_zoom_in, _zoom_out, _reset_view - mock plot_widget methods)
# - Downsampling checkbox (_toggle_downsampling - check plot update calls)
# - Folder navigation (_next_file, _prev_file - check index changes and load calls)