"""
PySide6 testing fixtures for shared module tests.

These fixtures help with testing GUI components by providing
mock objects and setup for headless UI testing.
"""

import pytest
from unittest.mock import MagicMock

# Try to import PySide6, but provide mocks if it's not available
# This allows tests to run in environments without a display
try:
    from PySide6 import QtWidgets, QtGui, QtCore

    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False
    # Create mock modules if PySide6 is not available
    QtWidgets = MagicMock()
    QtGui = MagicMock()
    QtCore = MagicMock()

    # Setup basic mocks for common classes
    QtWidgets.QApplication = MagicMock()
    QtWidgets.QPushButton = MagicMock()
    QtWidgets.QLabel = MagicMock()

    # Setup color mocks
    QtGui.QColor = MagicMock()
    QtGui.QColor.fromString = MagicMock(return_value=QtGui.QColor())

    # Setup palette mocks
    QtGui.QPalette = MagicMock()

try:
    import pyqtgraph as pg

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    # Create mock module for pyqtgraph
    pg = MagicMock()
    pg.mkPen = MagicMock(return_value=MagicMock())
    pg.PlotWidget = MagicMock()
    pg.LinearRegionItem = MagicMock()
    pg.InfiniteLine = MagicMock()


@pytest.fixture
def qapp():
    """Create a Qt application instance for the tests."""
    if not PYSIDE_AVAILABLE:
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
    if not PYQTGRAPH_AVAILABLE:
        return pg.PlotWidget()

    # Create a real PlotWidget if available
    plot_widget = pg.PlotWidget()

    yield plot_widget

    # Clean up after test
    plot_widget.close()
