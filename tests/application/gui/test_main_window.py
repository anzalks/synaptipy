import pytest
from PySide6 import QtCore
from PySide6.QtCore import Qt
from pathlib import Path
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
    assert main_window.open_file_button.isEnabled()
    assert main_window.open_folder_button.isEnabled()
    # Plot controls should be disabled initially
    assert not main_window.zoom_in_button.isEnabled()
    assert not main_window.zoom_out_button.isEnabled()
    assert not main_window.reset_view_button.isEnabled()
    # Folder navigation should be hidden initially
    assert not main_window.prev_file_button.isVisible()
    assert not main_window.next_file_button.isVisible()
    assert not main_window.file_index_label.isVisible()
    # Metadata should be 'N/A'
    assert main_window.filename_label.text() == "N/A"
    assert main_window.sampling_rate_label.text() == "N/A"

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

    # Configure the mock NeoAdapter to return the mock recording
    # Use mocker fixture from pytest-mock OR unittest.mock.patch
    mocker.patch.object(main_window.neo_adapter, 'read_recording', return_value=mock_recording)
    # Mock the plot update to avoid actual plotting
    mocker.patch.object(main_window, '_update_plot')
    mocker.patch.object(main_window, '_update_ui_state') # Can mock this too if needed

    # Act
    # Simulate clicking the 'Open File' button
    qtbot.mouseClick(main_window.open_file_button, Qt.LeftButton)

    # Assert
    # 1. Check if QFileDialog was called
    mock_get_open_file_name.assert_called_once()
    # 2. Check if adapter's read_recording was called with the correct path
    main_window.neo_adapter.read_recording.assert_called_once_with(mock_filepath)
    # 3. Check if plot update was called
    main_window._update_plot.assert_called_once()
    # 4. Check metadata labels (use call_args if _update_ui_state was mocked, or check directly)
    assert main_window.current_recording is mock_recording # Check internal state
    # Directly check labels AFTER the action (assuming _update_ui_state runs or checking its effect)
    # Need to ensure signal processing has finished if it's async later
    qtbot.waitSignal(main_window.statusBar.messageChanged, timeout=1000) # Wait for status bar update
    assert main_window.filename_label.text() == "mock_file.abf"
    assert "20000.00 Hz" in main_window.sampling_rate_label.text()
    assert main_window.channels_label.text().startswith("1:")
    assert main_window.statusBar.currentMessage().startswith("Loaded")

    # 5. Check button states (after _update_ui_state logic runs)
    # Manually call if it was mocked, otherwise assume it ran via signal/slot
    main_window._update_ui_state() # Call manually to ensure state update for assertion
    assert main_window.zoom_in_button.isEnabled()
    assert main_window.zoom_out_button.isEnabled()
    assert main_window.reset_view_button.isEnabled()
    assert not main_window.prev_file_button.isVisible() # Single file mode


# Mock QFileDialog to simulate user cancelling
@patch('PySide6.QtWidgets.QFileDialog.getOpenFileName')
def test_open_file_cancel(mock_get_open_file_name, main_window, qtbot, mocker):
    """Test UI state when user cancels the file dialog."""
    # Arrange
    mock_get_open_file_name.return_value = ("", "") # Simulate cancellation
    mocker.patch.object(main_window.neo_adapter, 'read_recording') # Mock adapter
    mocker.patch.object(main_window, '_update_plot')

    # Act
    qtbot.mouseClick(main_window.open_file_button, Qt.LeftButton)

    # Assert
    mock_get_open_file_name.assert_called_once()
    main_window.neo_adapter.read_recording.assert_not_called() # Shouldn't try to read
    main_window._update_plot.assert_not_called() # Shouldn't try to plot
    assert main_window.filename_label.text() == "N/A" # State shouldn't change


# TODO: Add tests for:
# - _open_folder (mocking getExistingDirectory and glob)
# - Error handling (mock read_recording to raise exceptions, check QMessageBox)
# - Plot controls (_zoom_in, _zoom_out, _reset_view - mock plot_widget methods)
# - Downsampling checkbox (_toggle_downsampling - check plot update calls)
# - Folder navigation (_next_file, _prev_file - check index changes and load calls)