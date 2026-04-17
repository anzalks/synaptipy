from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6 import QtWidgets

from Synaptipy.application.gui.explorer.explorer_tab import ExplorerTab
from Synaptipy.application.session_manager import SessionManager
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from Synaptipy.infrastructure.file_readers import NeoAdapter


@pytest.fixture
def session_manager():
    # Reset singleton? SessionManager is a singleton.
    # We might need to be careful.
    # But for now let's just get the instance.
    sm = SessionManager()
    return sm


@pytest.fixture(scope="session")
def explorer_tab(qapp):
    neo_adapter = MagicMock(spec=NeoAdapter)
    nwb_exporter = MagicMock(spec=NWBExporter)
    status_bar = QtWidgets.QStatusBar()

    tab = ExplorerTab(neo_adapter, nwb_exporter, status_bar)
    return tab


def test_explorer_syncs_with_session(explorer_tab, session_manager):
    """Verify ExplorerTab updates its file list when SessionManager emits."""

    # Mock data
    file_list = [Path("/data/file1.wcp"), Path("/data/file2.wcp")]
    current_index = 1

    # ExplorerTab should be connected to session_manager signals
    # Emit signal
    session_manager.file_context_changed.emit(file_list, current_index)

    # Check if ExplorerTab updated its internal state
    assert explorer_tab.file_list == file_list
    assert explorer_tab.current_file_index == current_index


def test_sidebar_sync_calls_expand(explorer_tab):
    """Verify Sidebar.sync_to_file calls scrollTo and selection on file_tree."""

    # Mock the internal sidebar components
    sidebar = explorer_tab.sidebar
    sidebar.file_tree = MagicMock()
    sidebar.file_model = MagicMock()

    # Mock File Path and Index
    file_path = Path("/data/file1.wcp")
    mock_file_idx = MagicMock()
    mock_file_idx.isValid.return_value = True
    mock_parent_idx = MagicMock()
    mock_parent_idx.isValid.return_value = True

    # Setup model behavior - index() returns different values based on path
    def side_effect_index(path_str):
        if path_str == str(file_path):
            return mock_file_idx
        elif path_str == str(file_path.parent):
            return mock_parent_idx
        return MagicMock()

    sidebar.file_model.index.side_effect = side_effect_index

    # Call sync
    sidebar.sync_to_file(file_path)

    # Verify setRootIndex was called with parent index
    sidebar.file_tree.setRootIndex.assert_called_with(mock_parent_idx)

    # Verify scrollTo was called on file index
    sidebar.file_tree.scrollTo.assert_called()

    # Verify setCurrentIndex was called
    sidebar.file_tree.setCurrentIndex.assert_called_with(mock_file_idx)

    # Verify selection was called
    sidebar.file_tree.selectionModel().select.assert_called()
