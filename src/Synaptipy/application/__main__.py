# src/Synaptipy/application/__main__.py
# -*- coding: utf-8 -*-
"""
Main entry point for the Synaptipy Viewer GUI application.

This module is responsible for:
1. Processing command line arguments
2. Setting up the logging system with dev mode support
3. Initializing the Qt application and UI styling
4. Creating and displaying the welcome screen with startup manager
5. Running the event loop

The module defines the `run_gui` function called by the entry point script
defined in pyproject.toml.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import argparse
import faulthandler
import logging
import os
import sys
import traceback

# Suppress annoying pyqtgraph RuntimeWarnings (overflow in cast)
import warnings

from PySide6 import QtCore, QtGui, QtWidgets

# --- Import Core Components ---
from Synaptipy.application.startup_manager import StartupManager
from Synaptipy.shared.logging_config import setup_logging

warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyqtgraph")

# Enable low-level C traceback on SIGBUS/SIGSEGV so fatal crashes include a
# Python stack trace in the log (zero overhead in normal operation).
faulthandler.enable()

# Log instance to be initialized after setting up logging
log = logging.getLogger(__name__)


def parse_arguments():
    """
    Parse command line arguments for the application.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(description="Synaptipy - Electrophysiology Visualization Suite")
    parser.add_argument("--dev", action="store_true", help="Enable development mode with verbose logging")
    parser.add_argument("--log-dir", type=str, help="Custom directory for log files")
    parser.add_argument("--log-file", type=str, help="Custom log filename")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Graceful crash reporter
# ---------------------------------------------------------------------------


class CrashReportDialog(QtWidgets.QDialog):
    """Non-modal dialog shown when an unhandled Python exception escapes to the
    top level.  Displays the full traceback in a read-only text area and
    provides a one-click "Copy to Clipboard" button so the user can paste the
    report directly into a GitHub Issue.
    """

    _GITHUB_ISSUES_URL = "https://github.com/anzalks/synaptipy/issues/new"

    def __init__(self, traceback_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Synaptipy — Unexpected Error")
        self.setMinimumSize(680, 420)
        self._traceback_text = traceback_text
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        # ---- Header ----
        header = QtWidgets.QLabel(
            "<b>An unexpected error occurred.</b><br>"
            "The error details are shown below. "
            "Please click <i>Copy to Clipboard</i> and paste them into a "
            "<a href='{url}'>GitHub Issue</a> so we can fix this.".format(url=self._GITHUB_ISSUES_URL)
        )
        header.setWordWrap(True)
        header.setOpenExternalLinks(True)
        layout.addWidget(header)

        # ---- Traceback ----
        self._text_area = QtWidgets.QPlainTextEdit()
        self._text_area.setReadOnly(True)
        self._text_area.setPlainText(self._traceback_text)
        font = QtGui.QFont("Courier New", 9)
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        self._text_area.setFont(font)
        layout.addWidget(self._text_area)

        # ---- Buttons ----
        btn_box = QtWidgets.QDialogButtonBox()
        copy_btn = btn_box.addButton("Copy to Clipboard", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        close_btn = btn_box.addButton(QtWidgets.QDialogButtonBox.StandardButton.Close)
        copy_btn.clicked.connect(self._copy_to_clipboard)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(btn_box)

    def _copy_to_clipboard(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self._traceback_text)


def _install_excepthook() -> None:
    """Replace ``sys.excepthook`` with a GUI-aware crash reporter.

    When an unhandled exception propagates to the top of the event loop,
    the default hook prints to stderr and silently exits.  Our replacement
    logs the traceback, then pops up a ``CrashReportDialog`` so the user
    can copy the error into a GitHub Issue.

    The hook is intentionally *not* installed for ``SystemExit`` and
    ``KeyboardInterrupt`` so normal shutdown and Ctrl-C still work.
    """

    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, (SystemExit, KeyboardInterrupt)):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.critical("Unhandled exception:\n%s", tb_str)

        app = QtWidgets.QApplication.instance()
        if app is not None:
            try:
                dlg = CrashReportDialog(tb_str)
                dlg.exec()
            except Exception:
                # If the dialog itself fails, fall back to stderr
                sys.__excepthook__(exc_type, exc_value, exc_tb)
        else:
            sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook


def run_gui():  # noqa: C901
    """
    Set up and run the Synaptipy GUI application with welcome screen.

    This function:
    1. Parses command line arguments
    2. Configures the logging system
    3. Initializes the Qt application
    4. Creates and displays the welcome screen
    5. Manages startup process with progress tracking
    6. Runs the Qt event loop

    Returns:
        int: The application exit code
    """
    # Parse command line arguments
    args = parse_arguments()

    # Check for dev mode environment variable
    env_dev_mode = os.environ.get("SYNAPTIPY_DEV_MODE")
    if env_dev_mode and env_dev_mode.lower() in ("1", "true", "yes"):
        dev_mode = True
    else:
        dev_mode = args.dev

    # Setup logging with the appropriate mode
    setup_logging(dev_mode=dev_mode, log_dir=args.log_dir, log_filename=args.log_file)

    log.info("Application starting...")
    if dev_mode:
        log.info("Running in DEVELOPMENT mode with verbose logging")

    # Create Qt Application with High DPI support
    app = QtWidgets.QApplication.instance()
    if app is None:
        # Enable High DPI scaling before creating QApplication
        # Check if HighDpiScaleFactorRoundingPolicy is available (Qt 6.0+)
        if hasattr(QtCore.Qt, "HighDpiScaleFactorRoundingPolicy"):
            try:
                QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
                    QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
                )
                log.debug("High DPI PassThrough policy set successfully")
            except Exception as e:
                log.warning(f"Could not set High DPI policy: {e}")

        app = QtWidgets.QApplication(sys.argv)

        # Enable High DPI pixmaps (for better icon rendering)
        try:
            app.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
        except Exception as e:
            log.warning(f"Could not enable High DPI pixmaps: {e}")

    # Force locale to English/US to ensure dot decimal separators
    # This fixes issues where European locales force comma separators in spinboxes
    QtCore.QLocale.setDefault(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))
    log.debug("Forced application locale to English/US (dot decimal separator)")

    # Install the GUI-aware crash reporter so unhandled exceptions show a
    # dialog with a "Copy to Clipboard" button instead of silently exiting.
    _install_excepthook()
    log.debug("Crash-report excepthook installed.")

    # Create startup manager and begin loading process
    try:
        startup_manager = StartupManager(app)
        welcome_screen = startup_manager.start_loading()

        # Show welcome screen immediately and force display
        welcome_screen.show()
        welcome_screen.raise_()  # Bring to front
        welcome_screen.activateWindow()  # Activate the window

        # Force Qt to process events and display the window immediately
        app.processEvents()

        # Use the optimized display method
        welcome_screen.force_display()

        log.debug("Welcome screen displayed, beginning startup process")

    except Exception as e:
        log.critical(f"Failed to create startup manager: {e}", exc_info=True)
        try:
            QtWidgets.QMessageBox.critical(
                None, "Application Startup Error", f"Failed to create startup manager:\n{e}\n\nSee logs."
            )
        except Exception:
            pass
        sys.exit(1)

    # Start Qt Event Loop
    log.debug("Starting Qt event loop...")
    exit_code = app.exec()
    log.debug(f"Qt event loop finished with exit code {exit_code}.")
    return exit_code


# Allow direct execution for development and testing
if __name__ == "__main__":
    run_gui()
