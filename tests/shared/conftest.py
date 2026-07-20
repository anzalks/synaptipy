"""
PySide6 testing fixtures for shared module tests.

These fixtures help with testing GUI components by providing
mock objects and setup for headless UI testing.
"""

from unittest.mock import MagicMock

import pytest


def _qt_widgets():
    """Import Qt only for fixtures that actually create a widget.

    Importing PySide at collection time makes pure data/cache tests depend on
    the platform's Qt binary, which is unnecessary and prevents those tests
    from running in a headless or architecture-mismatched environment.
    """
    try:
        from PySide6 import QtWidgets

        return QtWidgets
    except ImportError:
        return None


@pytest.fixture
def qapp():
    """Create a Qt application instance for the tests."""
    QtWidgets = _qt_widgets()
    if QtWidgets is None:
        return MagicMock()

    # Check if application already exists
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    yield app

    # No cleanup needed - app will be closed when Python exits


@pytest.fixture
def qtbot(qapp):
    """
    Fixture to provide QtBot for UI testing if available.
    Falls back to MagicMock if pytest-qt is not installed.
    """
    try:
        from pytestqt.qtbot import QtBot

        return QtBot(qapp)
    except ImportError:
        return MagicMock()


@pytest.fixture
def mock_plot_widget():
    """
    Create a mock PlotWidget for testing pyqtgraph-related functions.
    """
    try:
        import pyqtgraph as pg
    except ImportError:
        return MagicMock()

    # Create a real PlotWidget if available
    plot_widget = pg.PlotWidget()

    yield plot_widget

    # Clean up after test
    plot_widget.close()
