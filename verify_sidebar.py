
import sys
import logging
from pathlib import Path
from PySide6 import QtWidgets, QtCore

# Setup logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

def verify_sidebar_fix():
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    try:
        from Synaptipy.application.gui.explorer.sidebar import ExplorerSidebar
        from Synaptipy.infrastructure.file_readers import NeoAdapter

        log.info("Successfully imported ExplorerSidebar")

        # Mock dependencies
        neo_adapter = NeoAdapter()
        
        # Instantiate
        sidebar = ExplorerSidebar(neo_adapter)
        log.info("Successfully instantiated ExplorerSidebar")
        
        # Test update_file_quality
        # We need a valid path that exists in the model typically, but QFileSystemModel is async...
        # However, index() might return an invalid index if not loaded, but code handles idx.isValid()
        
        dummy_path = Path("/tmp/test_file.nwb")
        metrics = {"is_good": True}
        
        # This should NOT CRASH even if index is invalid
        sidebar.update_file_quality(dummy_path, metrics)
        log.info("Successfully called update_file_quality without NameError")
        
        return True

    except Exception as e:
        log.error(f"Verification Failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = verify_sidebar_fix()
    sys.exit(0 if success else 1)
