"""Tests for AnalysisStatusWindow and QtLoggingHandler."""

import logging

from PySide6 import QtWidgets
from PySide6.QtCore import QCoreApplication, QEventLoop

from Synaptipy.application.gui.widgets.log_streamer import AnalysisStatusWindow, QtLoggingHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _process():
    """Flush the Qt event queue (excluding user input events)."""
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_handler_captures_log_record(qapp):
    """QtLoggingHandler.emit() should fire log_emitted with the formatted text."""
    handler = QtLoggingHandler()
    captured = []
    handler.log_emitted.connect(lambda msg: captured.append(msg))

    record = logging.makeLogRecord(
        {
            "msg": "ping",
            "levelno": logging.DEBUG,
            "levelname": "DEBUG",
            "name": "some.third.party.lib",
        }
    )
    handler.emit(record)
    _process()

    assert len(captured) == 1
    assert "ping" in captured[0]


def test_window_hidden_by_default(qapp):
    """AnalysisStatusWindow must be hidden immediately after construction."""
    window = AnalysisStatusWindow()
    assert window.isVisible() is False
    window.close()


def test_toggle_visible(qapp):
    """toggle_visible() should show a hidden window, then hide a visible one."""
    window = AnalysisStatusWindow()
    assert window.isVisible() is False

    window.toggle_visible()
    assert window.isVisible() is True

    window.toggle_visible()
    assert window.isVisible() is False

    window.close()


def test_window_receives_log_via_handler(qapp):
    """Messages emitted by the handler should appear in _log_text."""
    handler = QtLoggingHandler()
    window = AnalysisStatusWindow()
    window.connect_handler(handler)

    record = logging.makeLogRecord(
        {
            "msg": "hello_world",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "name": "Synaptipy.test",
        }
    )
    handler.emit(record)
    _process()

    assert "hello_world" in window._log_text.toPlainText()
    window.close()


def test_pause_suppresses_output(qapp):
    """When Pause is checked, emitted messages must not appear in _log_text."""
    handler = QtLoggingHandler()
    window = AnalysisStatusWindow()
    window.connect_handler(handler)

    window._pause_checkbox.setChecked(True)

    record = logging.makeLogRecord(
        {
            "msg": "should_not_appear",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "name": "Synaptipy.test",
        }
    )
    handler.emit(record)
    _process()

    assert "should_not_appear" not in window._log_text.toPlainText()
    window.close()


def test_handler_ownership_by_parent():
    """Handler cleanup is handled automatically via Qt parent-child ownership.

    QtLoggingHandler is created with parent=analyser_tab so Qt destroys it
    when the parent widget is deleted.  No explicit detach step is needed
    because the handler is permanently attached for the application lifetime.
    This test exists as documentation; no runtime assertion is required.
    """
    pass


def test_warning_message_appears_in_colour(qapp):
    """WARNING records must be rendered in the warning colour (#c8860a)."""
    handler = QtLoggingHandler()
    window = AnalysisStatusWindow()
    window.connect_handler(handler)

    handler.emit(
        logging.makeLogRecord(
            {
                "msg": "something went wrong",
                "levelno": logging.WARNING,
                "levelname": "WARNING",
                "name": "neo.io",
            }
        )
    )
    QtWidgets.QApplication.processEvents()

    html = window._log_text.toHtml()
    assert "something went wrong" in html
    assert "#c8860a" in html  # warning colour applied

    window.close()
