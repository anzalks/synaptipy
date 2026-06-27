# src/synaptipy/application/gui/widgets/log_streamer.py
# -*- coding: utf-8 -*-
"""
Analysis Status Window for Synaptipy.

Provides two public components:

1. :class:`QtLoggingHandler` - a :class:`logging.Handler` that forwards log
   records to a Qt signal, permanently attached to the Synaptipy logger at
   DEBUG level so every log call in the hierarchy is captured.
2. :class:`AnalysisStatusWindow` - a tool window that streams live log output
   from the Synaptipy logger; hidden by default and shown only on user request
   via the View menu.

This file is part of Synaptipy, licensed under the GNU Affero General Public
License v3.0.  See the LICENSE file in the root of the repository for full
license details.
"""

import logging
from typing import Optional

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QCoreApplication, QEventLoop

log = logging.getLogger(__name__)

__all__ = ["QtLoggingHandler", "AnalysisStatusWindow"]


class _LogSignalBridge(QtCore.QObject):
    """Private QObject that owns the Qt signal for :class:`QtLoggingHandler`.

    Kept separate from :class:`QtLoggingHandler` so that PySide6 6.7.x does
    not intercept ``signal.emit(args)`` calls through the QObject's Python
    ``emit`` method when both live on the same object.
    """

    log_emitted = QtCore.Signal(str)


class QtLoggingHandler(logging.Handler):
    """A :class:`logging.Handler` that forwards log records via a Qt signal.

    The signal :attr:`log_emitted` is backed by a private
    :class:`_LogSignalBridge` QObject so that Qt can safely queue
    cross-thread signal deliveries without conflicting with the
    ``logging.Handler.emit`` protocol.

    The handler is set to DEBUG level so every call in the Synaptipy logger
    hierarchy (debug, info, warning, error) is captured.

    Attributes:
        log_emitted: ``SignalInstance(str)`` - connect slots to receive
            formatted log message strings.
    """

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__()
        self._bridge = _LogSignalBridge(parent=parent)
        # Expose the SignalInstance directly so callers can connect/disconnect
        # without needing to know about the internal bridge.
        self.log_emitted = self._bridge.log_emitted
        self.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="%(asctime)s  [%(levelname)-8s]  %(name)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """Format *record* and emit :attr:`log_emitted` via the bridge."""
        try:
            msg = self.format(record)
            # Call emit on the bridge QObject (which has no Python 'emit'
            # method) to avoid the PySide6 6.7.x dispatch conflict.
            self._bridge.log_emitted.emit(msg)
        except RuntimeError as e:
            if "deleted" in str(e):
                # The C++ object is gone. Remove ourselves from all loggers to stop the errors.
                for name in logging.root.manager.loggerDict:
                    logger = logging.getLogger(name)
                    if self in logger.handlers:
                        logger.removeHandler(self)
                if self in logging.root.handlers:
                    logging.root.removeHandler(self)
            else:
                self.handleError(record)
        except Exception:
            self.handleError(record)


class AnalysisStatusWindow(QtWidgets.QWidget):
    """Tool window that streams live log output from the Synaptipy logger.

    Hidden by default; shown only via :meth:`toggle_visible` called from
    the View menu.  Analysis always runs regardless of whether this window
    is open.

    Usage::

        handler = QtLoggingHandler(parent=analyser_tab)
        logging.getLogger("Synaptipy").addHandler(handler)
        window = AnalysisStatusWindow(parent=analyser_tab)
        window.connect_handler(handler)
        # user opens View -> Show Analysis Status:
        window.toggle_visible()
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.WindowType.Tool | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        # Never destroy on close - just hide
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # Opening does not steal keyboard focus from the main window
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle("Analysis Status")
        self.resize(640, 400)
        self.setMinimumSize(400, 200)
        self._entry_count: int = 0
        self._build_ui()
        self.hide()

    # Colour map keyed by level name prefix as it appears in the formatted message.
    # INFO uses None (default text colour - no override).
    _LEVEL_COLOURS = {
        "DEBUG": "#888888",
        "INFO": None,
        "WARNING": "#c8860a",
        "ERROR": "#cc2222",
        "CRITICAL": "#cc2222",
    }

    def _build_ui(self) -> None:
        """Construct the window layout."""
        layout = QtWidgets.QVBoxLayout(self)

        # --- Toolbar row ---
        toolbar = QtWidgets.QHBoxLayout()

        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(self._on_clear)
        toolbar.addWidget(clear_btn)

        self._pause_checkbox = QtWidgets.QCheckBox("Pause")
        toolbar.addWidget(self._pause_checkbox)

        toolbar.addStretch()

        self._entry_count_label = QtWidgets.QLabel("0 entries")
        self._entry_count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        toolbar.addWidget(self._entry_count_label)

        copy_btn = QtWidgets.QPushButton("Copy All")
        copy_btn.clicked.connect(self._on_copy_all)
        toolbar.addWidget(copy_btn)

        layout.addLayout(toolbar)

        # --- Log text area ---
        self._log_text = QtWidgets.QTextEdit()
        self._log_text.setReadOnly(True)
        font = self._log_text.font()
        font.setFamily("Courier New")
        font.setStyleHint(font.StyleHint.Monospace)
        font.setPointSize(9)
        self._log_text.setFont(font)
        self._log_text.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self._log_text, stretch=1)

        # --- Status bar ---
        self._status_bar_label = QtWidgets.QLabel("")
        self._status_bar_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._status_bar_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect_handler(self, handler: "QtLoggingHandler") -> None:
        """Connect *handler*.log_emitted to this window's append slot.

        Call once from ``AnalyserTab.__init__`` after attaching the handler
        to ``logging.getLogger("Synaptipy")``.

        Args:
            handler: The :class:`QtLoggingHandler` whose ``log_emitted``
                signal to connect.
        """
        handler.log_emitted.connect(self._append_message)

    def toggle_visible(self) -> None:
        """Show if hidden, hide if visible.

        This is the only method that shows the window; called by the View
        menu action in :class:`~Synaptipy.application.gui.main_window.MainWindow`.
        """
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def is_capturing(self) -> bool:
        """Return ``True`` - the handler is always attached.

        Exists for testability; the handler lifetime is managed by
        :class:`~Synaptipy.application.gui.analyser_tab.AnalyserTab`,
        not by this window.
        """
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @QtCore.Slot(str)
    def _append_message(self, msg: str) -> None:
        """Qt slot: append *msg* to the log text area.

        Does nothing if the Pause checkbox is checked.  Applies a colour
        based on the log level token in the formatted message.  Calls
        ``processEvents`` only when the window is visible to avoid
        wasting CPU when it is hidden.

        Args:
            msg: Formatted log message string.
        """
        if self._pause_checkbox.isChecked():
            return

        # Determine colour from the level token written by the formatter as
        # "[LEVELNAME " inside the formatted string.
        colour = None
        for level_name, hex_colour in self._LEVEL_COLOURS.items():
            if f"[{level_name}" in msg:
                colour = hex_colour
                break

        if colour:
            escaped = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self._log_text.append(f'<span style="color:{colour};">{escaped}</span>')
        else:
            self._log_text.append(msg)

        sb = self._log_text.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._entry_count += 1
        self._entry_count_label.setText(f"{self._entry_count} entries")
        self._status_bar_label.setText(msg.split("\n")[0])
        if self.isVisible():
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def _on_clear(self) -> None:
        """Clear the log text and reset entry count."""
        self._log_text.clear()
        self._entry_count = 0
        self._entry_count_label.setText("0 entries")

    def _on_copy_all(self) -> None:
        """Copy all log text to the clipboard."""
        QtWidgets.QApplication.clipboard().setText(self._log_text.toPlainText())
