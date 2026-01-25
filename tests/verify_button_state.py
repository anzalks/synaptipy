import sys
import logging
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from Synaptipy.application.gui.exporter_tab import ExporterTab

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("verify_button_state")


def verify_button_state():
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
        # Ensure path is empty
        tab.analysis_results_path_edit.setText("")

        # Mock table with selection
        tab.analysis_results_table = MagicMock()
        # Simulate selection exists
        tab.analysis_results_table.selectedIndexes.return_value = [MagicMock(row=lambda: 0, column=lambda: 0)]

        # Trigger update
        tab.update_state()

        # Verify button is enabled even with empty path
        if not tab.analysis_results_export_button.isEnabled():
            log.error("Export button should be enabled when selection exists, even if path is empty")
            sys.exit(1)

        log.info("Button State Verification PASSED")

    except Exception as e:
        log.error(f"Verification FAILED: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    verify_button_state()
