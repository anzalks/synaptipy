# src/Synaptipy/application/__main__.py
# -*- coding: utf-8 -*-
"""
Main entry point for the Synaptipy Viewer GUI application.
Initializes logging, QApplication, styles, MainWindow, and starts the event loop.
This file defines the `run_gui` function called by the entry point script.
"""
import sys
import logging
from PySide6 import QtWidgets, QtCore

# --- Import Core Components ---
# Use absolute imports from the Synaptipy package root
from Synaptipy.application.gui.main_window import MainWindow
from Synaptipy.application.gui.dummy_classes import SYNAPTIPY_AVAILABLE

# --- Configure Logging ---
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
log = logging.getLogger('Synaptipy.application') # Use a specific logger name
log.setLevel(logging.DEBUG) # Set desired level
# Avoid adding handlers if root logger already has them
if not log.hasHandlers() and not logging.getLogger().hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(log_format)
    handler.setFormatter(formatter)
    log.addHandler(handler)

# This function will be called by the entry point script (e.g., synaptipy-gui)
def run_gui():
    """Sets up and runs the Synaptipy GUI application."""
    log.info(f"Application starting via run_gui... Synaptipy Library Available: {SYNAPTIPY_AVAILABLE}")
    if not SYNAPTIPY_AVAILABLE:
        log.warning("*"*30 + "\n Running with DUMMY Synaptipy classes! \n" + "*"*30)

    # Create Qt Application
    # High DPI scaling attributes
    # QtWidgets.QApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    # QtWidgets.QApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    # Use QApplication.instance() to avoid creating multiple QApplications if already exists
    # Or handle potential existing instance in a more robust way if necessary
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # Apply Dark Theme (Optional) - using qdarkstyle
    style = None
    try:
        import qdarkstyle
        if hasattr(qdarkstyle, 'load_stylesheet'): # Generic loader
            style = qdarkstyle.load_stylesheet(qt_api='pyside6')
        elif hasattr(qdarkstyle, 'load_stylesheet_pyside6'): # Specific loader
             style = qdarkstyle.load_stylesheet_pyside6()

        if style:
            app.setStyleSheet(style)
            log.info("Applied qdarkstyle theme.")
        else:
             log.warning("qdarkstyle found but no suitable load_stylesheet function.")
    except ImportError:
        log.info("qdarkstyle not found, using default system style.")
    except Exception as e:
        log.warning(f"Could not apply qdarkstyle theme: {e}")


    # Create and Show Main Window
    try:
        window = MainWindow() # MainWindow handles its own QSettings
        window.show()
        log.info("Main window created and shown.")
    except Exception as e:
        log.critical(f"Failed to initialize or show the MainWindow: {e}", exc_info=True)
        try: QtWidgets.QMessageBox.critical(None, "Application Startup Error", f"Failed to create main window:\n{e}\n\nSee logs.")
        except Exception: pass
        # Exit if window creation fails critically
        sys.exit(1) # Consider exiting here or letting exec return non-zero

    # Start Qt Event Loop
    log.info("Starting Qt event loop...")
    # sys.exit(app.exec()) # sys.exit might be too aggressive if called from library code
    exit_code = app.exec()
    log.info(f"Qt event loop finished with exit code {exit_code}.")
    return exit_code # Return the exit code

# The if __name__ == '__main__': block is typically NOT needed
# when the functionality is meant to be called via an entry point function.
# Keeping it allows running this script directly for testing, but it's
# redundant if only using the entry point.
# If you want to allow direct execution:
# if __name__ == '__main__':
#     run_gui()