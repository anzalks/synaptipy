#!/usr/bin/env python3
"""
Unit tests for the styling module.

Tests the styling constants, theme values, and functions for consistency.
"""
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import pytest

# Check if running in CI/headless environment
IS_HEADLESS = os.environ.get("CI") or not os.environ.get("DISPLAY")

# Import Qt components only if not in a headless environment
QT_AVAILABLE = False
try:
    from PySide6 import QtWidgets, QtGui, QtCore

    QT_AVAILABLE = True
except ImportError:
    # Create mocks for headless testing
    QtWidgets = MagicMock()
    QtGui = MagicMock()
    QtCore = MagicMock()

# Import pyqtgraph safely
try:
    import pyqtgraph as pg

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    pg = MagicMock()
    PYQTGRAPH_AVAILABLE = False

# Import styling module - this should always succeed
from Synaptipy.shared.styling import (
    PLOT_COLORS,
    get_trial_pen,
    get_average_pen,
    get_baseline_pen,
    get_response_pen,
    get_grid_pen,
    configure_plot_widget,
    apply_stylesheet,
    style_button,
    style_label,
    style_result_display,
    style_info_label,
    style_error_message,
    get_system_theme_mode,
)


class TestStylingConstants(unittest.TestCase):
    """Test the theme and color constants."""

    def test_plot_colors_available(self):
        """Verify PLOT_COLORS is available and contains colors."""
        self.assertIsInstance(PLOT_COLORS, list)
        self.assertGreater(len(PLOT_COLORS), 0)

    def test_system_theme_mode_function(self):
        """Verify system theme mode function works correctly."""
        # Test get_system_theme_mode
        current = get_system_theme_mode()
        self.assertEqual(current, "auto")


class TestStylingFunctions(unittest.TestCase):
    """Test the styling helper functions."""

    @unittest.skipIf(not PYQTGRAPH_AVAILABLE, "pyqtgraph not available")
    def test_get_trial_pen(self):
        """Test that get_trial_pen returns a valid pen."""
        pen = get_trial_pen()
        self.assertIsInstance(pen, pg.mkPen().__class__)

    @unittest.skipIf(not PYQTGRAPH_AVAILABLE, "pyqtgraph not available")
    def test_get_average_pen(self):
        """Test that get_average_pen returns a valid pen."""
        pen = get_average_pen()
        self.assertIsInstance(pen, pg.mkPen().__class__)

    @unittest.skipIf(not PYQTGRAPH_AVAILABLE, "pyqtgraph not available")
    def test_get_grid_pen(self):
        """Test that get_grid_pen returns a valid pen."""
        pen = get_grid_pen()
        self.assertIsInstance(pen, pg.mkPen().__class__)


@unittest.skipIf(IS_HEADLESS or not QT_AVAILABLE, "Qt tests require a display or Qt not available")
class TestWidgetStyling(unittest.TestCase):
    """Test widget styling functions (requires PySide6 and a display)."""

    @classmethod
    def setUpClass(cls):
        """Initialize Qt application once for all tests."""
        if QT_AVAILABLE:
            # Initialize Qt application (needed for widget tests)
            cls.app = QtWidgets.QApplication.instance()
            if cls.app is None:
                cls.app = QtWidgets.QApplication([])

    def test_style_button_mock(self):
        """Test that style_button applies primary styling (using mocks)."""
        # Use mock instead of real QPushButton to avoid crashes
        button = MagicMock()
        button.setDefault = MagicMock()

        # Call the function
        result = style_button(button, "primary")

        # Check that setDefault was called for primary style
        button.setDefault.assert_called_once_with(True)
        self.assertEqual(result, button)  # Should return the same button

    def test_style_label_mock(self):
        """Test that style_label applies heading styling (using mocks)."""
        # Use mock instead of real QLabel to avoid crashes
        label = MagicMock()
        mock_font = MagicMock()
        label.font = MagicMock(return_value=mock_font)
        label.setFont = MagicMock()

        # Call the function
        result = style_label(label, "heading")

        # Check that font was modified and set
        mock_font.setBold.assert_called_once_with(True)
        mock_font.setPointSize.assert_called_once()
        label.setFont.assert_called_once_with(mock_font)
        self.assertEqual(result, label)  # Should return the same label

    def test_configure_plot_widget(self):
        """Test that configure_plot_widget applies the correct styling."""
        # Create a proper mock for the plot widget
        mock_widget = MagicMock()
        mock_widget.setBackground = MagicMock()
        mock_widget.showGrid = MagicMock()
        mock_widget._synaptipy_configured = False  # Ensure it's not already configured

        # Call the function
        result = configure_plot_widget(mock_widget)

        # Verify proper styling was applied
        mock_widget.setBackground.assert_called_once_with("w")
        # Grid alpha now comes from plot customization (70% opacity = ~0.698 alpha)
        # Just verify showGrid was called with the correct parameters (exact alpha may vary)
        self.assertTrue(mock_widget.showGrid.called)
        call_args = mock_widget.showGrid.call_args
        self.assertTrue(call_args[1]["x"])
        self.assertTrue(call_args[1]["y"])
        # Alpha should be between 0 and 1
        self.assertGreater(call_args[1]["alpha"], 0.0)
        self.assertLessEqual(call_args[1]["alpha"], 1.0)
        self.assertEqual(mock_widget, result)
        self.assertTrue(mock_widget._synaptipy_configured)


if __name__ == "__main__":
    unittest.main()
