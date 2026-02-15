# tests/application/gui/test_analysis_config_dialog.py
import pytest
from PySide6 import QtWidgets
from Synaptipy.application.gui.analysis_config_dialog import AnalysisConfigDialog
from Synaptipy.core.analysis.registry import AnalysisRegistry

@pytest.fixture
def mock_registry(monkeypatch):
    """Mock the AnalysisRegistry to return known metadata."""
    
    # Store original first
    original_meta = AnalysisRegistry._metadata.copy()
    original_orig_meta = AnalysisRegistry._original_metadata.copy()
    
    # Setup test data
    test_meta = {
        "test_analysis": {
            "ui_params": [
                {"name": "param1", "type": "float", "default": 1.0},
                {"name": "param2", "type": "int", "default": 10}
            ],
            "type": "analysis"
        }
    }
    
    import copy
    AnalysisRegistry._metadata = copy.deepcopy(test_meta)
    AnalysisRegistry._original_metadata = copy.deepcopy(test_meta)
    
    yield
    
    # Teardown
    AnalysisRegistry._metadata = original_meta
    AnalysisRegistry._original_metadata = original_orig_meta

def test_dialog_init(qtbot, mock_registry):
    """Test that the dialog initializes and populates tabs."""
    dialog = AnalysisConfigDialog()
    qtbot.addWidget(dialog)
    
    assert dialog.tab_widget.count() == 1
    assert dialog.tab_widget.tabText(0) == "Test Analysis"
    
def test_gather_params(qtbot, mock_registry):
    """Test gathering parameters from the dialog."""
    dialog = AnalysisConfigDialog()
    qtbot.addWidget(dialog)
    
    config = dialog._gather_all_params()
    assert "test_analysis" in config
    assert config["test_analysis"]["param1"] == 1.0
    assert config["test_analysis"]["param2"] == 10

def test_apply_configuration(qtbot, mock_registry):
    """Test searching configuration updates registry."""
    dialog = AnalysisConfigDialog()
    qtbot.addWidget(dialog)
    
    # Simulate changing a value
    # Access generator directly
    generator = dialog._generators["test_analysis"]
    # We can use set_params to simulate UI change
    generator.set_params({"param1": 5.5})
    
    # Apply
    config = dialog._gather_all_params()
    dialog._apply_configuration(config)
    
    # Verify Registry Updated
    meta = AnalysisRegistry.get_metadata("test_analysis")
    # Find param1
    param1 = next(p for p in meta["ui_params"] if p["name"] == "param1")
    assert param1["default"] == 5.5
    
def test_restore_defaults(qtbot, mock_registry):
    """Test restoring factory defaults."""
    dialog = AnalysisConfigDialog()
    qtbot.addWidget(dialog)
    
    # 1. Modify registry first
    AnalysisRegistry.update_default_params("test_analysis", {"param1": 999.0})
    
    # 2. Re-populate (dialog usually does this on open, but here we do it manually to sync)
    dialog._populate_tabs()
    config = dialog._gather_all_params()
    assert config["test_analysis"]["param1"] == 999.0
    
    # 3. Restore Defaults (mocking message box if needed, but we call methods directly)
    # We bypass the confirmation dialog and call logic directly
    AnalysisRegistry.reset_to_factory()
    dialog._populate_tabs()
    
    config = dialog._gather_all_params()
    assert config["test_analysis"]["param1"] == 1.0
