# src/Synaptipy/application/__main__.py
# -*- coding: utf-8 -*-
"""
Main entry point for the Synaptipy Viewer GUI application.

This module is responsible for:
1. Processing command line arguments
2. Setting up the logging system with dev mode support
3. Initializing the Qt application and UI styling
4. Creating and displaying the main application window
5. Running the event loop

The module defines the `run_gui` function called by the entry point script
defined in pyproject.toml.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""
import sys
import logging
import argparse
import os
from pathlib import Path
from PySide6 import QtWidgets, QtCore

# --- Import Core Components ---
from Synaptipy.application.gui.main_window import MainWindow
from Synaptipy.application.gui.dummy_classes import SYNAPTIPY_AVAILABLE
from Synaptipy.shared.logging_config import setup_logging
from Synaptipy.shared.styling import apply_stylesheet

# Log instance to be initialized after setting up logging
log = logging.getLogger('Synaptipy.application')

def parse_arguments():
    """
    Parse command line arguments for the application.
    
    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(description="Synaptipy - Electrophysiology Visualization Suite")
    parser.add_argument('--dev', action='store_true', help='Enable development mode with verbose logging')
    parser.add_argument('--log-dir', type=str, help='Custom directory for log files')
    parser.add_argument('--log-file', type=str, help='Custom log filename')
    return parser.parse_args()

def run_gui():
    """
    Set up and run the Synaptipy GUI application.
    
    This function:
    1. Parses command line arguments
    2. Configures the logging system
    3. Initializes the Qt application
    4. Creates and displays the main window
    5. Runs the Qt event loop
    
    Returns:
        int: The application exit code
    """
    # Parse command line arguments
    args = parse_arguments()
    
    # Check for dev mode environment variable
    env_dev_mode = os.environ.get('SYNAPTIPY_DEV_MODE')
    if env_dev_mode and env_dev_mode.lower() in ('1', 'true', 'yes'):
        dev_mode = True
    else:
        dev_mode = args.dev
    
    # Setup logging with the appropriate mode
    setup_logging(
        dev_mode=dev_mode,
        log_dir=args.log_dir,
        log_filename=args.log_file
    )
    
    log.info(f"Application starting via run_gui... Synaptipy Library Available: {SYNAPTIPY_AVAILABLE}")
    if dev_mode:
        log.info("Running in DEVELOPMENT mode with verbose logging")
    
    if not SYNAPTIPY_AVAILABLE:
        log.warning("*"*30 + "\n Running with DUMMY Synaptipy classes! \n" + "*"*30)

    # Create Qt Application
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # Apply application styling using our centralized styling module
    try:
        app = apply_stylesheet(app)
        log.info("Applied application styling from styling module.")
    except Exception as e:
        log.warning(f"Could not apply application styling: {e}")

    # Create and Show Main Window
    try:
        window = MainWindow()
        window.show()
        log.info("Main window created and shown.")
    except Exception as e:
        log.critical(f"Failed to initialize or show the MainWindow: {e}", exc_info=True)
        try: 
            QtWidgets.QMessageBox.critical(None, "Application Startup Error", 
                                         f"Failed to create main window:\n{e}\n\nSee logs.")
        except Exception:
            pass
        # Exit if window creation fails critically
        sys.exit(1)

    # Start Qt Event Loop
    log.info("Starting Qt event loop...")
    exit_code = app.exec()
    log.info(f"Qt event loop finished with exit code {exit_code}.")
    return exit_code

# Allow direct execution for development and testing
if __name__ == '__main__':
    run_gui()