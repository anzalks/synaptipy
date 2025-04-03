"""
Main entry point for launching the Synaptipy GUI application.
"""

import sys
import logging
from PySide6 import QtWidgets

# Import the MainWindow class from its module
from Synaptipy.application.gui.main_window import MainWindow

def configure_logging():
    """Sets up basic logging for the application."""
    logging.basicConfig(
        level=logging.INFO, # Set to logging.DEBUG for more verbose output
        format='%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout) # Log to console
            # Optionally add logging to a file:
            # logging.FileHandler("synaptipy_gui.log")
        ]
    )
    # Quieten overly verbose libraries if needed
    logging.getLogger('pyqtgraph').setLevel(logging.WARNING)


def run_gui():
    """Initializes and runs the Qt application."""
    configure_logging()
    log = logging.getLogger(__name__)
    log.info("Starting Synaptipy GUI application...")

    # Qt Application Instance
    # Use QApplication.instance() to avoid creating multiple instances if run interactively
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # Set application details (optional)
    app.setApplicationName("Synaptipy")
    app.setOrganizationName("YourOrg") # Replace if applicable

    # Create and show the main window
    main_window = MainWindow()
    main_window.show()

    # Start the Qt event loop
    log.info("Entering Qt event loop.")
    sys.exit(app.exec())


if __name__ == "__main__":
    # This allows running the GUI by executing this script directly
    # (e.g., python src/Synaptipy/application/__main__.py)
    run_gui()