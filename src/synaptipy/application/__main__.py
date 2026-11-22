# src/synaptipy/application/__main__.py
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
import multiprocessing
import os
import sys
import traceback
import warnings
from pathlib import Path
from typing import Optional, Sequence

from synaptipy.shared.logging_config import ensure_stdio_streams_support_fileno, get_logger, setup_logging

# PyInstaller ``console=False`` / ``--noconsole``: streams may be None or lack
# ``fileno()`` (e.g. *None* patched to :class:`io.StringIO` elsewhere).
# :func:`faulthandler.enable` requires ``sys.stderr.fileno()`` - bootstrap before Qt.
ensure_stdio_streams_support_fileno()

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyqtgraph")

# Enable low-level C traceback on SIGBUS/SIGSEGV so fatal crashes include a
# Python stack trace in the log (zero overhead in normal operation).
try:
    faulthandler.enable()
except (OSError, RuntimeError, ValueError):
    pass

# Log instance namespaced under "synaptipy" even when __name__ == "__main__" in PyInstaller
log = get_logger(__name__)


def _strip_macos_launch_args(argv: Sequence[str]) -> list[str]:
    """Strip macOS LaunchServices process serial number flags (``-psn_*``)."""
    return [arg for arg in argv if not arg.startswith("-psn_")]


_KNOWN_BOOL_FLAGS = frozenset({"--dev", "--verbose", "-v", "--smoke-test", "--version", "-h", "--help"})


def _extract_positional_file(cleaned_argv: Sequence[str]) -> Optional[str]:
    """Return an OS-supplied file path from ``cleaned_argv``, ignoring ``-flag value`` pairs."""
    skip_next = False
    for token in cleaned_argv:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            if "=" in token or token in _KNOWN_BOOL_FLAGS:
                continue
            # Both known value flags (--file X) and unknown OS/Qt flags
            # (-ApplePersistenceIgnoreState YES, -platform offscreen) may
            # consume the next non-option token as their value.
            skip_next = True
            continue
        if Path(token).is_file():
            return token
    return None


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments for the application.

    Uses ``parse_known_args`` so macOS LaunchServices / Cocoa flags
    (e.g. ``-psn_0_...``, ``-ApplePersistenceIgnoreState YES``,
    ``-NSDocumentRevisionsDebugMode YES``) and Qt platform flags never cause an
    unhandled ``SystemExit(2)`` in packaged desktop bundles.

    Parameters
    ----------
    argv : Sequence[str], optional
        Explicit argument vector (excluding program name). Defaults to
        ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
        Parsed command line arguments.
    """
    try:
        from synaptipy import __version__ as _version
    except ImportError:
        _version = "unknown"

    raw_argv = list(sys.argv[1:] if argv is None else argv)
    cleaned_argv = _strip_macos_launch_args(raw_argv)

    parser = argparse.ArgumentParser(description="Synaptipy - Electrophysiology Visualization Suite")
    # --version is handled by argparse before any Qt code runs, so it exits 0
    # cleanly in headless / no-console builds - used by installer smoke tests.
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_version}",
    )
    parser.add_argument("--dev", action="store_true", help="Enable development mode with verbose logging")
    parser.add_argument("--verbose", "-v", action="store_true", help="Increase output verbosity")
    parser.add_argument("--log-dir", type=str, help="Custom directory for log files")
    parser.add_argument("--log-file", type=str, help="Custom log filename")
    parser.add_argument("--file", type=str, default=None, help="Open a specific file on startup")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)

    args, unknown = parser.parse_known_args(cleaned_argv)
    args.unknown_args = unknown
    if args.file is None:
        args.file = _extract_positional_file(cleaned_argv)
    return args


# ---------------------------------------------------------------------------
# Graceful crash reporter
# ---------------------------------------------------------------------------


class CrashReportDialog(QtWidgets.QDialog):
    """Non-modal dialog shown when an unhandled Python exception escapes to the
    top level.  Displays a GitHub-ready Markdown crash report in a read-only
    text area and provides one-click "Copy to Clipboard" so the user can paste
    directly into a GitHub Issue.
    """

    _GITHUB_ISSUES_URL = "https://github.com/anzalks/synaptipy/issues/new"

    def __init__(self, traceback_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Synaptipy - Unexpected Error")
        self.setMinimumSize(720, 460)
        self._traceback_text = traceback_text
        self._markdown_report = self._build_markdown_report(traceback_text)
        self._build_ui()

    # ------------------------------------------------------------------
    # Markdown report builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_markdown_report(traceback_text: str) -> str:
        """Build a GitHub-ready Markdown crash report.

        The report embeds:
        - Synaptipy version
        - Python version and platform
        - OS description
        - Full stack trace inside a fenced code block

        Returns
        -------
        str
            Markdown-formatted string suitable for pasting into a GitHub Issue.
        """
        import platform
        import sys

        try:
            from synaptipy import __version__ as synaptipy_version
        except Exception:
            synaptipy_version = "unknown"

        os_info = platform.platform(aliased=True, terse=False)
        python_info = f"{sys.version} " f"[{platform.python_implementation()} {platform.python_version()}]"
        try:
            import PySide6

            pyside_version = PySide6.__version__
        except Exception:
            pyside_version = "unknown"

        report_lines = [
            "# Synaptipy Crash Report",
            "",
            "## Environment",
            "",
            "| Property | Value |",
            "|---|---|",
            f"| **Synaptipy** | `{synaptipy_version}` |",
            f"| **Python** | `{python_info}` |",
            f"| **PySide6** | `{pyside_version}` |",
            f"| **OS** | `{os_info}` |",
            "",
            "## Stack Trace",
            "",
            "```python-traceback",
            traceback_text.rstrip(),
            "```",
            "",
            "*Please paste this report into a new "
            "[GitHub Issue](https://github.com/anzalks/synaptipy/issues/new) "
            "so we can fix this. Thank you!*",
        ]
        return "\n".join(report_lines)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        # ---- Header ----
        header = QtWidgets.QLabel(
            "<b>An unexpected error occurred.</b><br>"
            "The crash report below is formatted for GitHub Issues. "
            "Click <i>Copy to Clipboard</i> and paste it into a "
            "<a href='{url}'>GitHub Issue</a> so we can fix this.".format(url=self._GITHUB_ISSUES_URL)
        )
        header.setWordWrap(True)
        header.setOpenExternalLinks(True)
        layout.addWidget(header)

        # ---- Markdown report (read-only) ----
        self._text_area = QtWidgets.QPlainTextEdit()
        self._text_area.setReadOnly(True)
        self._text_area.setPlainText(self._markdown_report)
        font = QtGui.QFont()
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        font.setFamily("monospace")
        font.setPointSize(9)
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
        QtWidgets.QApplication.clipboard().setText(self._markdown_report)


def _install_excepthook(headless: bool = False) -> None:
    """Replace ``sys.excepthook`` with a GUI-aware crash reporter.

    When an unhandled exception propagates to the top of the event loop,
    the default hook prints to stderr and silently exits.  Our replacement
    logs the traceback, then pops up a ``CrashReportDialog`` containing a
    GitHub-ready Markdown report so the user can paste it into an issue.

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
        if headless:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            if app is not None:
                app.exit(1)
            return
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


def _create_qapplication() -> QtWidgets.QApplication:
    """Return existing QApplication or instantiate one with High-DPI PassThrough."""
    app = QtWidgets.QApplication.instance()
    if app is not None:
        return app

    if hasattr(QtCore.Qt, "HighDpiScaleFactorRoundingPolicy"):
        try:
            QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
                QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
            log.debug("High DPI PassThrough policy set successfully")
        except (AttributeError, RuntimeError) as exc:
            log.warning("Could not set High DPI policy: %s", exc)

    qt_argv = [sys.argv[0], *_strip_macos_launch_args(sys.argv[1:])]
    return QtWidgets.QApplication(qt_argv)


def _schedule_initial_file_open(startup_manager, initial_file: Path) -> None:
    """Poll until MainWindow is visible, then open ``initial_file``."""
    timer = QtCore.QTimer(startup_manager)
    timer.setInterval(200)

    def _try_open_initial_file() -> None:
        mw = startup_manager.get_main_window()
        if mw is None or not mw.isVisible():
            return
        timer.stop()
        fio = getattr(mw, "file_io_controller", None)
        if fio is None:
            return
        siblings = fio._scan_siblings(initial_file)
        idx = siblings.index(initial_file) if initial_file in siblings else 0
        mw._load_in_explorer(initial_file, siblings, idx, False)

    timer.timeout.connect(_try_open_initial_file)
    startup_manager._initial_file_timer = timer
    startup_manager._initial_file_cb = _try_open_initial_file
    timer.start()


def _schedule_smoke_test_exit(app: QtWidgets.QApplication, startup_manager) -> None:
    """Verify full packaged GUI bootstrap through MainWindow, then exit cleanly."""
    attempts = [0]
    timer = QtCore.QTimer(startup_manager)
    timer.setInterval(100)

    def _probe() -> None:
        attempts[0] += 1
        mw = startup_manager.get_main_window()
        if mw is not None and mw.isVisible():
            timer.stop()
            from synaptipy.core.analysis.registry import AnalysisRegistry

            if not AnalysisRegistry.list_registered():
                log.critical("Smoke test failed: AnalysisRegistry is empty.")
                app.exit(1)
                return
            sentinel = os.environ.get("SYNAPTIPY_SMOKE_SENTINEL")
            if sentinel:
                Path(sentinel).write_text("OK\n", encoding="utf-8")
            log.info("Smoke test passed: MainWindow initialized and visible.")
            mw.close()
            app.exit(0)
            return
        if attempts[0] >= 200:
            timer.stop()
            log.critical("Smoke test timed out waiting for MainWindow visibility.")
            app.exit(1)

    timer.timeout.connect(_probe)
    startup_manager._smoke_test_timer = timer
    startup_manager._smoke_test_cb = _probe
    timer.start()


def _start_welcome_flow(app: QtWidgets.QApplication, smoke_test: bool = False):
    """Import StartupManager after logging/excepthook setup and display WelcomeScreen."""
    from synaptipy.application.startup_manager import StartupManager

    startup_manager = StartupManager(app, headless_smoke_test=smoke_test)
    welcome_screen = startup_manager.start_loading()
    welcome_screen.show()
    welcome_screen.raise_()
    welcome_screen.activateWindow()
    app.processEvents()
    welcome_screen.force_display()
    log.debug("Welcome screen displayed, beginning startup process")
    return startup_manager


def run_gui():
    """
    Set up and run the Synaptipy GUI application with welcome screen.

    Returns:
        int: The application exit code
    """
    multiprocessing.freeze_support()
    args = parse_arguments()

    env_dev_mode = os.environ.get("SYNAPTIPY_DEV_MODE", "")
    dev_mode = (env_dev_mode.lower() in ("1", "true", "yes")) or args.dev or args.verbose

    setup_logging(dev_mode=dev_mode, log_dir=args.log_dir, log_filename=args.log_file)
    log.info("Application starting...")
    if dev_mode:
        log.info("Running in DEVELOPMENT mode with verbose logging")

    app = _create_qapplication()
    QtCore.QLocale.setDefault(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))
    log.debug("Forced application locale to English/US (dot decimal separator)")

    smoke_test = bool(getattr(args, "smoke_test", False))
    _install_excepthook(headless=smoke_test)
    log.debug("Crash-report excepthook installed.")

    try:
        startup_manager = _start_welcome_flow(app, smoke_test=smoke_test)
    except Exception as exc:  # noqa: BLE001 - top-level GUI bootstrap guard
        log.critical("Failed to create startup manager: %s", exc, exc_info=True)
        try:
            QtWidgets.QMessageBox.critical(
                None, "Application Startup Error", f"Failed to create startup manager:\n{exc}\n\nSee logs."
            )
        except RuntimeError:
            pass
        sys.exit(1)

    if args.file:
        initial_file = Path(args.file).resolve()
        if not initial_file.exists():
            log.error("File not found: %s", initial_file)
            sys.stderr.write(f"Error: File not found: {initial_file}\n")
            sys.exit(1)
        _schedule_initial_file_open(startup_manager, initial_file)

    if getattr(args, "smoke_test", False):
        _schedule_smoke_test_exit(app, startup_manager)

    log.debug("Starting Qt event loop...")
    exit_code = app.exec()
    log.debug("Qt event loop finished with exit code %s.", exit_code)
    return exit_code


# Allow direct execution for development and frozen PyInstaller bundles
if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(run_gui())
