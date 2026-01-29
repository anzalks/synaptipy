import pytest
from unittest.mock import MagicMock
from pathlib import Path
from PySide6 import QtWidgets, QtCore
from Synaptipy.application.gui.explorer.explorer_tab import ExplorerTab
from Synaptipy.application.session_manager import SessionManager
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

@pytest.fixture
def session_manager():
    # Reset singleton? SessionManager is a singleton.
    # We might need to be careful.
    # But for now let's just get the instance.
    sm = SessionManager()
    return sm

@pytest.fixture
def explorer_tab(qtbot, session_manager):
    neo_adapter = MagicMock(spec=NeoAdapter)
    nwb_exporter = MagicMock(spec=NWBExporter)
    status_bar = QtWidgets.QStatusBar()
    
    # Create tab
    tab = ExplorerTab(neo_adapter, nwb_exporter, status_bar)
    qtbot.addWidget(tab)
    return tab

def test_explorer_syncs_with_session(explorer_tab, session_manager):
    """Verify that ExplorerTab updates its file list when SessionManager emits file_context_changed."""
    
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
    """Verify Sidebar.sync_to_file calls expand and selection."""
    
    # Mock the internal sidebar components
    sidebar = explorer_tab.sidebar
    sidebar.file_tree = MagicMock()
    sidebar.file_model = MagicMock()
    
    # Mock File Path and Index
    file_path = Path("/data/file1.wcp")
    mock_idx = MagicMock()
    mock_idx.isValid.return_value = True
    
    # Setup model behavior
    # We need index() to return mock_idx when called with file_path
    def side_effect_index(path_str):
        return mock_idx
        
    sidebar.file_model.index.side_effect = side_effect_index
    
    # Call sync
    sidebar.sync_to_file(file_path)
    
    # Verify expand was called on the parent index
    sidebar.file_tree.expand.assert_called_with(mock_idx.parent())
    
    # Verify selection
    sidebar.file_tree.selectionModel().select.assert_called()
