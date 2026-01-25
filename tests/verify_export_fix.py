import sys
import logging
import pandas as pd
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from Synaptipy.application.gui.exporter_tab import ExporterTab

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("verify_export_fix")


def verify_export_fix():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Mock dependencies
    mock_explorer = MagicMock()
    mock_nwb = MagicMock()
    mock_settings = MagicMock()
    mock_status = MagicMock()
    mock_main_window = QtWidgets.QMainWindow()
    mock_main_window.saved_analysis_results = [
        {"source_file_name": "test.abf", "analysis_type": "Test", "value": 123, "timestamp_saved": "2023-01-01"}
    ]

    try:
        log.info("Initializing ExporterTab...")
        tab = ExporterTab(mock_explorer, mock_nwb, mock_settings, mock_status, parent=mock_main_window)

        # Mock UI elements
        tab.analysis_results_path_edit = MagicMock()
        tab.analysis_results_path_edit.text.return_value = "test_output.json"

        # Select results
        tab.analysis_results_table = MagicMock()
        tab.analysis_results_table.selectedIndexes.return_value = [MagicMock(row=lambda: 0, column=lambda: 0)]

        log.info("Testing JSON export...")
        # This calls pd.DataFrame.to_json, which previously failed due to missing import
        tab._do_export_analysis_results()

        log.info("Export Fix Verification PASSED")

    except Exception as e:
        log.error(f"Verification FAILED: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    verify_export_fix()
