from unittest.mock import MagicMock

import pytest
from PySide6 import QtWidgets


def test_show_popup_windows_logic(main_window):
    """Verify _show_popup_windows iterates _loaded_analysis_tabs correctly."""
    window = main_window

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
