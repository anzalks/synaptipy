from pathlib import Path
from unittest.mock import MagicMock

from PySide6 import QtCore

from Synaptipy.application.gui.explorer.sidebar import ExplorerSidebar
from Synaptipy.infrastructure.file_readers import NeoAdapter


class MockFileSystemModel(QtCore.QObject):
    directoryLoaded = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.root_path = "/"
        self.indices = {}  # path -> index mock
        self.loaded_paths = set()

    def setRootPath(self, path):
        self.root_path = path
        # Simulate async loading
        # We can't actually thread in QT test easily without event loop.
        # But we can simulate "latched" loading or manual trigger.
        pass

    def index(self, path):
        # In real life, returns invalid if not loaded
        # Here we simulate: valid only if "loaded" or if it is root?
        # Actually simplest is: valid if we added it to mocking dict.
        return self.indices.get(path, QtCore.QModelIndex())

    def filePath(self, index):
        # Reverse lookup for completeness if needed
        return ""


def test_sidebar_async_sync(qtbot):
    """Verify Sidebar handles deferred loading via directoryLoaded."""

    neo_adapter = MagicMock(spec=NeoAdapter)
    neo_adapter.get_supported_extensions.return_value = ["wcp"]

    # We construct Sidebar directly as it's easier to mock internal model
    sidebar = ExplorerSidebar(neo_adapter)

    # Replace the real model with our mocked signals/methods
    # But QFileSystemModel is a C++ class, difficult to fully mock inheritance.
    # Instead, we just mock the instance.

    mock_model = MagicMock()
    # Add signal manually
    mock_model.directoryLoaded = QtCore.Signal(str)
    # Just use a real signal object attached to mock?
    # Or rely on the fact that sidebar.file_model replaced by mock

    # Let's use a real object for signal emission
    class SignalHolder(QtCore.QObject):
        directoryLoaded = QtCore.Signal(str)

    signal_holder = SignalHolder()

    mock_model.directoryLoaded = signal_holder.directoryLoaded

    # Setup sidebar with mock
    _old_model = sidebar.file_model  # noqa: F841
    sidebar.file_model = mock_model
    # Re-connect signals because we replaced the object
    mock_model.directoryLoaded.connect(sidebar._on_directory_loaded)

    # Mock indices
    mock_parent_idx = MagicMock()
    mock_parent_idx.isValid.return_value = True

    mock_file_idx = MagicMock()
    mock_file_idx.isValid.return_value = True

    # Scenario:
    # 1. sync_to_file called.
    # 2. index(parent) returns INVALID initially (simulating not loaded)
    # 3. directoryLoaded emitted later
    # 4. index(parent) returns VALID then

    file_path = Path("/data/folder/file.wcp")
    parent_path = str(file_path.parent)

    # STEP 1: Initial State - Model is empty/not loaded
    # When sidebar calls index(), return Invalid
    mock_model.index.return_value = QtCore.QModelIndex()

    # Call sync
    sidebar.sync_to_file(file_path)

    # Verify setRootPath was called to start loading
    mock_model.setRootPath.assert_called_with(parent_path)

    # Verify _pending_sync_path is set
    assert sidebar._pending_sync_path == file_path

    # Verify setRootIndex was NOT called yet (because index was invalid)
    sidebar.file_tree = MagicMock()  # Mock tree to check calls
    sidebar.file_tree.setRootIndex.assert_not_called()

    # STEP 2: Directory Loads
    # Now configure model to return valid indices
    def side_effect_index(path):
        if path == parent_path:
            return mock_parent_idx
        if path == str(file_path):
            return mock_file_idx
        return QtCore.QModelIndex()

    mock_model.index.side_effect = side_effect_index

    # Emit signal
    signal_holder.directoryLoaded.emit(parent_path)

    # STEP 3: Verification
    # Now setRootIndex should have been called
    sidebar.file_tree.setRootIndex.assert_called_with(mock_parent_idx)

    # And file should be selected
    sidebar.file_tree.setCurrentIndex.assert_called_with(mock_file_idx)

    # And pending path cleared
    assert sidebar._pending_sync_path is None
