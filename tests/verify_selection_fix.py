
import sys
import logging
from unittest.mock import MagicMock
from PySide6 import QtWidgets, QtCore
from Synaptipy.application.gui.exporter_tab import ExporterTab

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("verify_selection_fix")

def verify_selection_fix():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    
    # Mock dependencies
    mock_explorer = MagicMock()
    mock_nwb = MagicMock()
    mock_settings = MagicMock()
    mock_status = MagicMock()
    mock_main_window = QtWidgets.QMainWindow()
    
    try:
        log.info("Initializing ExporterTab...")
        tab = ExporterTab(mock_explorer, mock_nwb, mock_settings, mock_status, parent=mock_main_window)
        
        # Mock UI elements
        tab.analysis_results_path_edit = MagicMock()
        tab.analysis_results_path_edit.text.return_value = "test.csv"
        
        # Mock table behavior
        tab.analysis_results_table = QtWidgets.QTableWidget()
        tab.analysis_results_table.setRowCount(1)
        tab.analysis_results_table.setColumnCount(1)
        
        # Re-connect signals manually since we replaced the table (or ensure _connect_signals used the real table)
        # In the real class, _connect_signals is called in __init__, so it connected to the real table.
        # But wait, I replaced the table above? No, I should use the one created by __init__.
        # Let's re-instantiate to be safe and use the real table.
        
        tab = ExporterTab(mock_explorer, mock_nwb, mock_settings, mock_status, parent=mock_main_window)
        tab.analysis_results_path_edit.setText("test.csv") # Use real widget if possible, or mock text()
        
        # Add a row
        tab.analysis_results_table.setRowCount(1)
        tab.analysis_results_table.setColumnCount(1)
        tab.analysis_results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Test"))
        
        # Verify initial state (disabled)
        if tab.analysis_results_export_button.isEnabled():
            log.error("Export button should be disabled initially")
            sys.exit(1)
            
        log.info("Simulating manual selection...")
        # Select the row
        tab.analysis_results_table.selectRow(0)
        
        # Process events to let signal propagate
        app.processEvents()
        
        # Verify state (enabled)
        if not tab.analysis_results_export_button.isEnabled():
            log.error("Export button should be enabled after selection")
            sys.exit(1)
            
        log.info("Selection Fix Verification PASSED")
        
    except Exception as e:
        log.error(f"Verification FAILED: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    verify_selection_fix()
