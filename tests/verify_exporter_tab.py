import sys
import logging
from PySide6 import QtWidgets
from Synaptipy.application.gui.exporter_tab import ExporterTab
from unittest.mock import MagicMock

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("verify_exporter")


def verify_exporter_tab():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Mock dependencies
    mock_explorer = MagicMock()
    mock_nwb = MagicMock()
    mock_settings = MagicMock()
    mock_status = MagicMock()

    try:
        log.info("Initializing ExporterTab...")
        tab = ExporterTab(mock_explorer, mock_nwb, mock_settings, mock_status)

        # Verify sub-tabs
        count = tab.sub_tab_widget.count()
        log.info(f"Sub-tab count: {count}")

        expected_tabs = ["Export to NWB", "Export Analysis Results"]
        actual_tabs = [tab.sub_tab_widget.tabText(i) for i in range(count)]

        if count != 2:
            log.error(f"Expected 2 sub-tabs, got {count}: {actual_tabs}")
            sys.exit(1)

        if actual_tabs != expected_tabs:
            log.error(f"Tab names mismatch. Expected {expected_tabs}, got {actual_tabs}")
            sys.exit(1)

        log.info("Sub-tab structure verified.")

        # Verify JSON export logic existence (static check)
        import inspect

        source = inspect.getsource(tab._do_export_analysis_results)
        if "to_json" in source and "orient='records'" in source:
            log.info("JSON export logic found in _do_export_analysis_results.")
        else:
            log.error("JSON export logic NOT found in _do_export_analysis_results.")
            sys.exit(1)

        log.info("ExporterTab Verification PASSED")

    except Exception as e:
        log.error(f"Verification FAILED: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    verify_exporter_tab()
