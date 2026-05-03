# src/Synaptipy/core/error_handler.py
# -*- coding: utf-8 -*-
"""
Offline, privacy-respecting crash reporter for Synaptipy.

This module intercepts fatal unhandled Python exceptions **before** they
silently terminate the process.  It assembles a GitHub-ready Markdown
report containing:

- Synaptipy version
- Python version and platform string
- PySide6 version
- OS description (``platform.platform()``)
- Full formatted stack trace

The report is displayed in a safe emergency ``QDialog`` with two buttons:

- **Copy to Clipboard** -- copies the Markdown string so the user can
  paste it directly into a GitHub Issue.
- **Exit** -- closes the dialog and terminates the process.

Usage
-----
Call :func:`install_excepthook` once, **before** ``QApplication`` is
instantiated, at the very top of the application entry point::

    from Synaptipy.core.error_handler import install_excepthook
    install_excepthook()

The hook is safe to call even in headless / test environments: when no
``QApplication`` is running the error falls back to ``sys.__excepthook__``
(stderr output).

Note
----
``SystemExit`` and ``KeyboardInterrupt`` are intentionally *not* intercepted
so that normal shutdown (``sys.exit()``) and Ctrl-C still work as expected.
"""

from __future__ import annotations

import logging
import platform
import sys
import traceback
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

GITHUB_ISSUES_URL: str = "https://github.com/anzalks/synaptipy/issues/new"


# ---------------------------------------------------------------------------
# Markdown report builder (pure Python, no Qt required)
# ---------------------------------------------------------------------------


def build_crash_markdown(traceback_text: str) -> str:
    """Assemble a GitHub-ready Markdown crash report.

    Parameters
    ----------
    traceback_text : str
        The formatted traceback string from
        ``"".join(traceback.format_exception(...))``.

    Returns
    -------
    str
        Multi-line Markdown string ready for a GitHub Issue body.
    """
    try:
        from Synaptipy import __version__ as synaptipy_version
    except Exception:
        synaptipy_version = "unknown"

    os_info = platform.platform(aliased=True, terse=False)
    python_info = f"{sys.version} " f"[{platform.python_implementation()} {platform.python_version()}]"

    try:
        import PySide6

        pyside_version = PySide6.__version__
    except Exception:
        pyside_version = "unknown"

    lines = [
        "# \U0001f41b Synaptipy Crash Report",
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
        f"[GitHub Issue]({GITHUB_ISSUES_URL}) "
        "so we can fix this. Thank you!*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Emergency QDialog (safe, minimal Qt widgets only)
# ---------------------------------------------------------------------------


def _show_crash_dialog(markdown_report: str) -> None:
    """Display *markdown_report* in an emergency PySide6 QDialog.

    The dialog is intentionally minimal — it avoids any Synaptipy-specific
    styling or widgets that might themselves crash.

    Parameters
    ----------
    markdown_report : str
        The pre-built Markdown crash report string.
    """
    try:
        from PySide6 import QtGui, QtWidgets

        # Ensure a QApplication exists (required for any widget)
        app: Optional[QtWidgets.QApplication] = QtWidgets.QApplication.instance()  # type: ignore[assignment]
        if app is None:
            app = QtWidgets.QApplication(sys.argv)

        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Synaptipy \u2014 Unexpected Error")
        dialog.setMinimumSize(720, 460)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Header
        header = QtWidgets.QLabel(
            "<b>An unexpected error occurred.</b><br>"
            "The crash report below is formatted for GitHub Issues. "
            "Click <i>Copy to Clipboard</i> and paste it into a "
            f'<a href="{GITHUB_ISSUES_URL}">GitHub Issue</a> so we can fix this.'
        )
        header.setWordWrap(True)
        header.setOpenExternalLinks(True)
        layout.addWidget(header)

        # Crash report text area
        text_area = QtWidgets.QPlainTextEdit()
        text_area.setReadOnly(True)
        text_area.setPlainText(markdown_report)
        font = QtGui.QFont("Courier New", 9)
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        text_area.setFont(font)
        layout.addWidget(text_area)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox()
        copy_btn = btn_box.addButton(
            "Copy to Clipboard",
            QtWidgets.QDialogButtonBox.ButtonRole.ActionRole,
        )
        exit_btn = btn_box.addButton(
            "Exit",
            QtWidgets.QDialogButtonBox.ButtonRole.RejectRole,
        )
        copy_btn.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(markdown_report))
        exit_btn.clicked.connect(dialog.reject)
        layout.addWidget(btn_box)

        dialog.exec()
    except Exception as dlg_err:
        # If even the emergency dialog fails, write to stderr and give up.
        print(f"[Synaptipy] Emergency dialog failed: {dlg_err}", file=sys.stderr)
        print(markdown_report, file=sys.stderr)


# ---------------------------------------------------------------------------
# sys.excepthook installer
# ---------------------------------------------------------------------------


def install_excepthook() -> None:
    """Install the Synaptipy crash reporter as ``sys.excepthook``.

    Call this **once** at application startup, before ``QApplication`` is
    instantiated.  Subsequent calls are idempotent (the hook checks whether
    it has already been installed).

    The installed hook:

    1. Passes ``SystemExit`` and ``KeyboardInterrupt`` through unchanged so
       normal shutdown and Ctrl-C are unaffected.
    2. Formats the traceback with ``traceback.format_exception``.
    3. Logs the traceback at CRITICAL level.
    4. Builds a GitHub-ready Markdown report via :func:`build_crash_markdown`.
    5. Shows the emergency :func:`_show_crash_dialog` when a ``QApplication``
       is available; otherwise writes to ``sys.__excepthook__``.
    """
    # Guard against double-installation
    if getattr(sys.excepthook, "_synaptipy_crash_reporter", False):
        log.debug("error_handler: excepthook already installed, skipping.")
        return

    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, (SystemExit, KeyboardInterrupt)):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.critical("Unhandled exception:\n%s", tb_str)

        markdown = build_crash_markdown(tb_str)

        try:
            from PySide6.QtWidgets import QApplication

            if QApplication.instance() is not None:
                _show_crash_dialog(markdown)
                return
        except Exception:
            pass

        # Fallback: no Qt available
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        print("\n--- Synaptipy Crash Report (Markdown) ---", file=sys.stderr)
        print(markdown, file=sys.stderr)

    _excepthook._synaptipy_crash_reporter = True  # type: ignore[attr-defined]
    sys.excepthook = _excepthook
    log.debug("error_handler: crash-reporter excepthook installed.")
