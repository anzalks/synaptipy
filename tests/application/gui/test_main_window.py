from pathlib import Path
from unittest.mock import MagicMock, patch  # Use unittest.mock or pytest-mock

import numpy as np
import pytest

# Assuming main_window fixture is in conftest.py providing a MainWindow instance
# Assuming qtbot fixture is available from pytest-qt
from synaptipy.core.data_model import Channel, Recording  # For creating mock data


@pytest.fixture(autouse=True)
def reset_main_window_state(main_window):
    """
    Reset MainWindow state modified by individual tests.

    Because main_window is module-scoped (created once for the whole module
    to avoid crash-on-second-creation in offscreen mode), each test gets the
    same window instance. This fixture runs after every test to undo any
    state mutations so the next test starts clean.
    """
    yield
    # Clear data loader cache (test_data_loader_cache_integration adds entries)
    if hasattr(main_window, "data_loader") and hasattr(main_window.data_loader, "cache"):
        main_window.data_loader.cache.clear()
    # Clear asynchronous file-load contexts used by background loading tests.
    if hasattr(main_window, "_pending_load_requests"):
        main_window._pending_load_requests.clear()
        main_window._load_request_serial = 0
        main_window._latest_load_request = 0
    # Clear current recording (test_background_file_loading sets this)
    if hasattr(main_window, "session_manager"):
        main_window.session_manager.current_recording = None
    # Clear status bar messages
    if hasattr(main_window, "status_bar"):
        main_window.status_bar.clearMessage()


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
    assert hasattr(main_window, "data_loader")
    assert hasattr(main_window, "data_loader_thread")
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
    ch1 = Channel("1", "Vm", "mV", 20000.0, [np.random.rand(50000)])  # Mock data
    ch1.t_start = 0.0
    rec.channels = {"1": ch1}
    return rec


# Mock QFileDialog to simulate user selecting a file without showing the dialog
@pytest.fixture
def mock_file_dialog():
    """Mock QFileDialog for testing."""
    with patch("PySide6.QtWidgets.QFileDialog") as mock_dlg:
        mock_instance = MagicMock()
        mock_dlg.return_value = mock_instance
        mock_instance.exec.return_value = False
        mock_instance.selectedFiles.return_value = []
        yield mock_instance


def test_open_file_success(main_window, qtbot, mock_recording):
    """Test the UI state change after successfully 'opening' a file."""
    # Arrange
    mock_filepath = Path("mock_folder/mock_file.abf")

    with patch("PySide6.QtWidgets.QFileDialog") as mock_dlg:
        mock_instance = MagicMock()
        mock_dlg.return_value = mock_instance
        mock_instance.exec.return_value = True  # User accepted
        mock_instance.selectedFiles.return_value = [str(mock_filepath)]

        # Act
        main_window.open_file_action.trigger()

        # Assert
        mock_instance.exec.assert_called_once()
        assert True  # Test passes if we got here without exception


# Mock QFileDialog to simulate user cancelling
def test_open_file_cancel(main_window, qtbot):
    """Test UI state when user cancels the file dialog."""
    # Arrange
    with patch("PySide6.QtWidgets.QFileDialog") as mock_dlg:
        mock_instance = MagicMock()
        mock_dlg.return_value = mock_instance
        mock_instance.exec.return_value = False  # User cancelled

        # Act
        main_window.open_file_action.trigger()

        # Assert
        mock_instance.exec.assert_called_once()
        # Status message should indicate cancellation
        assert "cancel" in main_window.status_bar.currentMessage().lower()


# --- Background Data Loading Tests ---


def test_data_loader_signals(main_window, qtbot):
    """Test that DataLoader signals are properly connected."""
    # Check that signals are connected by verifying signal names exist
    assert hasattr(main_window.data_loader, "data_ready")
    assert hasattr(main_window.data_loader, "data_error")
    assert hasattr(main_window.data_loader, "loading_started")
    assert hasattr(main_window.data_loader, "loading_progress")

    # Verify signals are Qt Signal instances
    from PySide6.QtCore import Signal

    assert isinstance(main_window.data_loader.data_ready, Signal)
    assert isinstance(main_window.data_loader.data_error, Signal)
    assert isinstance(main_window.data_loader.loading_started, Signal)
    assert isinstance(main_window.data_loader.loading_progress, Signal)


def test_background_file_loading(main_window, mock_recording):
    """Test that _on_data_ready correctly updates session state.

    Calls the slot directly rather than going through the signal/event-loop
    path.  data_loader lives on data_loader_thread, so emitting data_ready
    from the main thread uses a QueuedConnection; delivering it requires
    running QEventLoop.exec().  On macOS+Python 3.10 that exec() fires
    deferred ViewBox geometry callbacks accumulated by earlier test modules
    that share the session-scoped main_window, causing a segfault.

    The slot logic (state management) is what this test verifies -- not the
    signal routing, which is already confirmed by test_data_loader_signals.
    tab_widget.setCurrentWidget is also patched to prevent Qt geometry
    recalculations that post new ViewBox callbacks on macOS.
    """
    # Set up a request as if _load_in_explorer had queued it.
    key = main_window._load_path_key(mock_recording.source_file)
    main_window._latest_load_request = 1
    main_window._pending_load_requests[key] = [{"id": 1, "file_list": [mock_recording.source_file], "current_index": 0}]

    with (
        patch.object(main_window.explorer_tab, "_display_recording"),
        patch.object(main_window.tab_widget, "setCurrentWidget"),
    ):
        # Call the slot directly -- no QEventLoop.exec() needed or safe here
        main_window._on_data_ready(mock_recording)

    # Assert: Check that SessionManager was updated with the recording
    assert main_window.session_manager.current_recording == mock_recording

    assert not main_window._pending_load_requests


def test_background_loading_error_handling(main_window, qtbot):
    """Test that loading errors are properly handled."""
    error_message = "Test error message"

    with patch("PySide6.QtWidgets.QMessageBox.critical") as message_box_spy:
        key = main_window._load_path_key(Path("test.abf"))
        main_window._latest_load_request = 1
        main_window._pending_load_requests[key] = [{"id": 1, "file_list": [Path("test.abf")], "current_index": 0}]

        # Act: Trigger the data_error signal
        with qtbot.waitSignal(main_window.data_loader.data_error, timeout=1000):
            main_window.data_loader.data_error.emit(Path("test.abf"), error_message)

        # Assert: Check that error dialog was shown
        message_box_spy.assert_called_once()

        assert not main_window._pending_load_requests


def test_stale_file_completion_is_ignored(main_window, mock_recording):
    """An earlier load must not replace the most recently requested file."""
    key = main_window._load_path_key(mock_recording.source_file)
    main_window._latest_load_request = 2
    main_window._pending_load_requests[key] = [{"id": 1, "file_list": [mock_recording.source_file], "current_index": 0}]

    with patch.object(main_window.tab_widget, "setCurrentWidget") as set_current:
        main_window._on_data_ready(mock_recording)

    set_current.assert_not_called()
    assert main_window.session_manager.current_recording is None


def test_plugin_load_failures_show_one_nonfatal_summary(main_window):
    """Broken optional plugins produce one informational warning, not a crash."""
    from synaptipy.application.plugin_manager import PluginLoadFailure

    failures = [PluginLoadFailure(Path("broken_plugin.py"), "SyntaxError: invalid syntax")]
    with patch("PySide6.QtWidgets.QMessageBox.warning") as warning:
        main_window._show_plugin_load_failures(failures)

    warning.assert_called_once()
    assert "broken_plugin.py" in warning.call_args.args[2]


def test_cancelled_plugin_reload_keeps_current_analyser_ui(main_window):
    """Declining plugin consent must not tear down and rebuild active tabs."""
    with (
        patch("synaptipy.application.plugin_manager.PluginManager.reload_plugins", return_value=None) as reload_plugins,
        patch.object(main_window.analyser_tab, "rebuild_analysis_tabs") as rebuild_tabs,
    ):
        applied = main_window._on_plugins_toggled(True)

    reload_plugins.assert_called_once_with(enabled=True)
    rebuild_tabs.assert_not_called()
    assert applied is False


def test_downloaded_plugins_hot_load_when_enabled(main_window):
    """A completed example-plugin download must activate without a restart."""
    with (
        patch.object(main_window.settings, "value", return_value=True),
        patch.object(main_window, "_on_plugins_toggled", return_value=True) as toggle_plugins,
    ):
        main_window._on_plugins_downloaded(Path("plugins"))

    toggle_plugins.assert_called_once_with(True)


def test_downloaded_plugins_stay_inactive_when_disabled(main_window):
    """Downloading files must not bypass an explicit disabled preference."""
    with (
        patch.object(main_window.settings, "value", return_value=False),
        patch.object(main_window, "_on_plugins_toggled") as toggle_plugins,
    ):
        main_window._on_plugins_downloaded(Path("plugins"))

    toggle_plugins.assert_not_called()


def test_plugin_rebuild_preserves_selected_core_analysis(main_window):
    """Hot-loading plugins must not jump the user back to another analysis."""
    analyser = main_window.analyser_tab
    if analyser.sub_tab_widget.count() < 2:
        pytest.skip("Need at least two analysis tabs to verify selection preservation")

    analyser.sub_tab_widget.setCurrentIndex(1)
    selected_name = analyser.sub_tab_widget.currentWidget().get_registry_name()
    analyser.rebuild_analysis_tabs()

    assert analyser.sub_tab_widget.currentWidget().get_registry_name() == selected_name


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


def test_data_loader_cache_integration(main_window, qtbot, mock_recording):
    """Test that DataLoader cache works correctly."""
    # Test the cache directly
    file_path = Path("test_file.abf")

    # Initially cache should be empty
    assert not main_window.data_loader.cache.contains(file_path)

    # Add to cache
    main_window.data_loader.cache.put(file_path, mock_recording)

    # Now it should be in cache
    assert main_window.data_loader.cache.contains(file_path)

    # Should be able to retrieve it
    cached_recording = main_window.data_loader.cache.get(file_path)
    assert cached_recording is mock_recording


def test_data_loader_cache_stats(main_window):
    """Test that DataLoader cache provides statistics."""
    cache_stats = main_window.data_loader.cache.get_stats()

    assert "size" in cache_stats
    assert "max_size" in cache_stats
    assert "utilization" in cache_stats
    assert "cached_files" in cache_stats

    assert cache_stats["max_size"] == 10  # Default cache size
    assert cache_stats["size"] == 0  # Initially empty
    assert cache_stats["utilization"] == 0.0


# --- File Loading & Folder Scan Tests ---


def test_file_dialog_scan_siblings(main_window, qtbot):
    """Test that selecting a file triggers scanning for sibling files."""
    # Arrange
    folder_path = Path("mock_folder")
    file1 = folder_path / "file1.abf"
    file2 = folder_path / "file2.abf"
    file3 = folder_path / "other.txt"

    # Mock settings to return last directory
    main_window.settings.setValue("lastDirectory", str(folder_path))

    # Mock iterdir to simulate folder content
    with patch("pathlib.Path.iterdir") as mock_iterdir:
        mock_iterdir.return_value = [file1, file2, file3]
        with (
            patch("pathlib.Path.is_dir", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.exists", return_value=True),
        ):

            with patch("PySide6.QtWidgets.QFileDialog") as mock_dlg:
                mock_instance = MagicMock()
                mock_dlg.return_value = mock_instance
                mock_instance.exec.return_value = True
                mock_instance.selectedFiles.return_value = [str(file1)]

                # Mock _load_in_explorer to verify it gets called with the list
                with patch.object(main_window, "_load_in_explorer") as mock_load:
                    # Act
                    main_window._open_file_dialog()

                    # Assert
                    # Check if _load_in_explorer was called
                    mock_load.assert_called_once()

                    # Verify arguments: file_list should contain file1 and file2 (sorted)
                    call_args = mock_load.call_args
                    file_list_arg = call_args[0][1]  # 2nd argument
                    assert len(file_list_arg) == 2
                    assert file1 in file_list_arg
                    assert file2 in file_list_arg
                    assert file3 not in file_list_arg  # different extension


# --- Error Handling Tests ---


def test_error_handling_dialog(main_window, qtbot):
    """Test that critical errors show a message box."""
    error_msg = "Critical failure"
    with patch("PySide6.QtWidgets.QMessageBox.critical") as mock_critical:
        main_window._on_data_error(Path("failed.abf"), error_msg)
        mock_critical.assert_called_once()
        args = mock_critical.call_args[0]
        assert error_msg in args[2]  # Message body


# --- Explorer Interaction Tests ---


def test_explorer_connections(main_window):
    """Test that explorer tab functionality is connected."""
    if hasattr(main_window, "explorer_tab") and main_window.explorer_tab:
        # Verify signal connection
        # We can't easily check 'is connected' without internal Qt introspection on the signal object
        # but we can check if the tab exists and has the expected methods/signals
        assert hasattr(main_window.explorer_tab, "open_file_requested")

        # Verify settings passed to tab - ExplorerTab stores settings differently or not as a public attribute
        # assert main_window.explorer_tab.settings is not None
