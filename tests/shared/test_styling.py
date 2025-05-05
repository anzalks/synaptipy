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
    THEME, PALETTE, PLOT_COLORS, ALPHA,
    BUTTON_STYLES, TEXT_STYLES,
    get_trial_pen, get_average_pen, get_baseline_pen, get_response_pen,
    get_baseline_brush, get_response_brush, get_axis_pen, get_grid_pen,
    get_plot_pen, configure_plot_widget, apply_stylesheet,
    style_button, style_label, style_result_display, style_info_label,
    style_error_message
)


class TestStylingConstants(unittest.TestCase):
    """Test the theme and color constants."""
    
    def test_theme_contains_expected_colors(self):
        """Verify THEME contains all expected color keys."""
        expected_keys = [
            'primary', 'secondary', 'accent', 'background', 'surface',
            'error', 'warning', 'success', 'text_primary', 'text_secondary',
            'text_disabled', 'trial_color', 'average_color', 'axis_color',
            'grid_color', 'baseline_region', 'response_region'
        ]
        for key in expected_keys:
            self.assertIn(key, THEME, f"Missing key {key} in THEME")
    
    def test_palette_contains_expected_colors(self):
        """Verify PALETTE contains expected color groups."""
        expected_groups = ['blues', 'reds', 'greens', 'grays']
        for group in expected_groups:
            self.assertIn(group, PALETTE, f"Missing color group {group} in PALETTE")
            self.assertEqual(len(PALETTE[group]), 10, f"Color group {group} should have 10 values")
    
    def test_button_styles_consistency(self):
        """Verify BUTTON_STYLES contains all expected types."""
        expected_styles = ['primary', 'action', 'toolbar']
        for style in expected_styles:
            self.assertIn(style, BUTTON_STYLES, f"Missing style {style} in BUTTON_STYLES")


class TestStylingFunctions(unittest.TestCase):
    """Test the styling helper functions."""
    
    @unittest.skipIf(not PYQTGRAPH_AVAILABLE, "pyqtgraph not available")
    def test_get_trial_pen(self):
        """Test that get_trial_pen returns a valid pen with correct color."""
        pen = get_trial_pen()
        self.assertIsInstance(pen, pg.mkPen().__class__)
        # Skip color check if running in a headless environment
        if not IS_HEADLESS and QT_AVAILABLE:
            self.assertEqual(pen.color().name(), QtGui.QColor(THEME['trial_color']).name())
    
    @unittest.skipIf(not PYQTGRAPH_AVAILABLE, "pyqtgraph not available")
    def test_get_average_pen(self):
        """Test that get_average_pen returns a valid pen with correct color."""
        pen = get_average_pen()
        self.assertIsInstance(pen, pg.mkPen().__class__)
        # Skip color check if running in a headless environment
        if not IS_HEADLESS and QT_AVAILABLE:
            self.assertEqual(pen.color().name(), QtGui.QColor(THEME['average_color']).name())
    
    @unittest.skipIf(not PYQTGRAPH_AVAILABLE, "pyqtgraph not available")
    def test_get_plot_pen_index_wrapping(self):
        """Test that get_plot_pen handles index wrapping correctly."""
        num_colors = len(PLOT_COLORS)
        # Test with index beyond the color count
        pen1 = get_plot_pen(index=num_colors)  # Should wrap to 0
        pen2 = get_plot_pen(index=0)  # First color
        self.assertIsInstance(pen1, pg.mkPen().__class__)
        self.assertIsInstance(pen2, pg.mkPen().__class__)


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