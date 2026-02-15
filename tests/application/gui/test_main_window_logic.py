
import pytest
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from Synaptipy.application.gui.main_window import MainWindow


@pytest.fixture
def app():
    if not QtWidgets.QApplication.instance():
        return QtWidgets.QApplication([])
    return QtWidgets.QApplication.instance()


def test_show_popup_windows_logic(app):
    """Verify _show_popup_windows iterates _loaded_analysis_tabs correctly."""
    # Mock MainWindow and dependencies
    window = MainWindow()

    # Mock AnalyserTab (it's a QWidget now)
    window.analyser_tab = MagicMock(spec=QtWidgets.QWidget)

    # Mock Analysis Tabs with popups
    tab1 = MagicMock()
    popup1 = MagicMock()
    popup1.isVisible.return_value = False
    tab1._popup_windows = [popup1]

    tab2 = MagicMock()
    popup2 = MagicMock()
    popup2.isVisible.return_value = True
    tab2._popup_windows = [popup2]

    # Set _loaded_analysis_tabs
    window.analyser_tab._loaded_analysis_tabs = [tab1, tab2]

    # Run method
    window._show_popup_windows()

    # Verify behavior
    popup1.show.assert_called_once()
    popup2.raise_.assert_called_once()
    popup2.activateWindow.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
