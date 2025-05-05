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


# TODO: Add tests for:
# - _open_folder (mocking getExistingDirectory and glob)
# - Error handling (mock read_recording to raise exceptions, check QMessageBox)
# - Plot controls (_zoom_in, _zoom_out, _reset_view - mock plot_widget methods)
# - Downsampling checkbox (_toggle_downsampling - check plot update calls)
# - Folder navigation (_next_file, _prev_file - check index changes and load calls)