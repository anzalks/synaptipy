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
IS_HEADLESS = os.environ.get('CI') or not os.environ.get('DISPLAY')

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
    get_trial_pen, get_average_pen, get_baseline_pen, get_response_pen, get_grid_pen,
    configure_plot_widget, apply_stylesheet,
    style_button, style_label, style_result_display, style_info_label,
    style_error_message, get_system_theme_mode
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
        """Test that style_button applies stylesheet (using mocks)."""
        # Use mock instead of real QPushButton to avoid crashes
        button = MagicMock()
        button.styleSheet = MagicMock(return_value="")
        button.setStyleSheet = MagicMock()
        
        # Call the function
        result = style_button(button, 'primary')
        
        # Check that setStyleSheet was called
        button.setStyleSheet.assert_called_once()
        self.assertEqual(result, button)  # Should return the same button
    
    def test_style_label_mock(self):
        """Test that style_label applies stylesheet (using mocks)."""
        # Use mock instead of real QLabel to avoid crashes
        label = MagicMock()
        label.styleSheet = MagicMock(return_value="")
        label.setStyleSheet = MagicMock()
        
        # Call the function
        result = style_label(label, 'heading')
        
        # Check that setStyleSheet was called
        label.setStyleSheet.assert_called_once()
        self.assertEqual(result, label)  # Should return the same label
    
    @patch('pyqtgraph.PlotWidget')
    def test_configure_plot_widget(self, mock_plot_widget):
        """Test that configure_plot_widget applies the correct styling."""
        mock_axis = MagicMock()
        mock_plot_widget.getAxis.return_value = mock_axis
        
        # Setup mock methods
        mock_plot_widget.setBackground = MagicMock()
        mock_plot_widget.getAxis = MagicMock(return_value=mock_axis)
        mock_plot_widget.showGrid = MagicMock()
        
        result = configure_plot_widget(mock_plot_widget)
        
        # Verify proper styling was applied
        mock_plot_widget.setBackground.assert_called_once()
        mock_plot_widget.showGrid.assert_called_once_with(x=True, y=True, alpha=0.3)
        self.assertEqual(mock_plot_widget, result)


if __name__ == '__main__':
    unittest.main() 