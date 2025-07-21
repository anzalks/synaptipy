#!/usr/bin/env python3
"""
Synaptipy UI Styling Module

This module defines theming and styling settings for the Synaptipy application using Qt's native theming system.
It provides a centralized way to control the application's visual appearance using Qt's built-in palette system.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

from PySide6 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import logging

log = logging.getLogger(__name__)

# ==============================================================================
# Theme Mode Management
# ==============================================================================

# Current theme mode (dark/light) - default to dark
CURRENT_THEME_MODE = "dark"

def get_current_theme_mode() -> str:
    """Returns the current theme mode ('dark' or 'light')."""
    return CURRENT_THEME_MODE

def set_theme_mode(mode: str) -> str:
    """
    Set the theme to a specific mode.
    
    Args:
        mode: String "light" or "dark"
        
    Returns:
        The current theme mode.
    """
    global CURRENT_THEME_MODE, THEME
    
    if mode not in ["light", "dark"]:
        log.warning(f"Invalid theme mode '{mode}'. Using 'dark' instead.")
        mode = "dark"
    
    CURRENT_THEME_MODE = mode
    # Update THEME dictionary with current colors
    THEME.update(_get_theme_dict())
    log.info(f"Theme mode set to: {mode}")
    return CURRENT_THEME_MODE

def toggle_theme_mode() -> str:
    """
    Toggle between light and dark theme modes.
    Returns the new theme mode name ("light" or "dark").
    """
    global CURRENT_THEME_MODE, THEME
    
    new_mode = "light" if CURRENT_THEME_MODE == "dark" else "dark"
    CURRENT_THEME_MODE = new_mode
    # Update THEME dictionary with current colors
    THEME.update(_get_theme_dict())
    log.info(f"Theme toggled to: {new_mode}")
    return new_mode

# ==============================================================================
# PyQtGraph Global Configuration (matching explorer tab)
# ==============================================================================

def configure_pyqtgraph_globally():
    """Apply global PyQtGraph configuration for consistent behavior across all plots."""
    import pyqtgraph as pg
    
    # Configure global PyQtGraph settings (matching explorer tab)
    pg.setConfigOption('imageAxisOrder', 'row-major')
    pg.setConfigOption('background', 'w')  # White background
    pg.setConfigOption('foreground', 'k')  # Black foreground (text, axes, grids)

# ==============================================================================
# Application Theme Functions
# ==============================================================================

def apply_stylesheet(app: QtWidgets.QApplication) -> QtWidgets.QApplication:
    """Apply the appropriate Qt native theme to the QApplication based on current theme mode."""
    try:
        if CURRENT_THEME_MODE == "dark":
            _apply_qt_dark_theme(app)
        else:
            _apply_qt_light_theme(app)
        log.info(f"Applied Qt native {CURRENT_THEME_MODE} theme")
    except Exception as e:
        log.warning(f"Could not apply Qt native theme: {e}")
    
    return app

def _apply_qt_dark_theme(app: QtWidgets.QApplication):
    """Apply Qt's native dark theme using palette and style."""
    # Use Fusion style for consistent cross-platform dark theme
    app.setStyle("Fusion")
    
    # Create dark palette using Qt's native color roles
    dark_palette = QtGui.QPalette()
    
    # Window colors
    dark_palette.setColor(QtGui.QPalette.Window, QtGui.QColor(53, 53, 53))
    dark_palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(255, 255, 255))
    
    # Base colors (for input fields, etc.)
    dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(25, 25, 25))
    dark_palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(53, 53, 53))
    
    # Text colors
    dark_palette.setColor(QtGui.QPalette.Text, QtGui.QColor(255, 255, 255))
    dark_palette.setColor(QtGui.QPalette.BrightText, QtGui.QColor(255, 0, 0))
    
    # Button colors
    dark_palette.setColor(QtGui.QPalette.Button, QtGui.QColor(53, 53, 53))
    dark_palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(255, 255, 255))
    
    # Highlight colors (selection)
    dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(42, 130, 218))
    dark_palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(0, 0, 0))
    
    # Disabled colors
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(127, 127, 127))
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(127, 127, 127))
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(127, 127, 127))
    
    # Tooltip colors
    dark_palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(0, 0, 0))
    dark_palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(255, 255, 255))
    
    # Links
    dark_palette.setColor(QtGui.QPalette.Link, QtGui.QColor(42, 130, 218))
    dark_palette.setColor(QtGui.QPalette.LinkVisited, QtGui.QColor(255, 0, 255))
    
    app.setPalette(dark_palette)

def _apply_qt_light_theme(app: QtWidgets.QApplication):
    """Apply Qt's native light theme using palette and style."""
    # Use the default system style for light theme
    try:
        # Try to use native system style first
        app.setStyle("windowsvista")  # Windows
    except:
        try:
            app.setStyle("macintosh")  # macOS
        except:
            app.setStyle("Fusion")  # Fallback
    
    # Reset to default light palette
    app.setPalette(app.style().standardPalette())

# ==============================================================================
# Plot Styling for PyQtGraph
# ==============================================================================

def get_plot_background_color() -> str:
    """Get consistent white background color for all plots."""
    return "#ffffff"  # Always white for consistency

def get_plot_foreground_color() -> str:
    """Get the appropriate foreground color for plots based on current theme."""
    if CURRENT_THEME_MODE == "dark":
        return "#ffffff"  # White
    else:
        return "#000000"  # Black

def configure_plot_widget(plot_widget):
    """Configure a PyQtGraph PlotWidget with consistent styling matching explorer tab approach."""
    # Always set background to white for consistency across all plots
    plot_widget.setBackground('white')
    
    # Configure axes with theme-appropriate colors
    axis_color = get_plot_foreground_color()
    plot_widget.getAxis('left').setPen(axis_color)
    plot_widget.getAxis('bottom').setPen(axis_color)
    plot_widget.getAxis('left').setTextPen(axis_color)
    plot_widget.getAxis('bottom').setTextPen(axis_color)
    
    # Enable grid with full opacity (like explorer tab)
    plot_widget.showGrid(x=True, y=True, alpha=1.0)
    
    # Ensure grids are properly behind data by setting correct z-values
    _configure_grid_z_order(plot_widget)
    
    return plot_widget

def _configure_grid_z_order(plot_widget):
    """Ensure grid lines are behind data by setting proper z-values (like explorer tab)."""
    try:
        plot_item = plot_widget.getPlotItem()
        if plot_item:
            # Set grid z-values to be behind data (negative values)
            for axis_name in ['bottom', 'left']:
                axis = plot_item.getAxis(axis_name)
                if axis and hasattr(axis, 'grid'):
                    if hasattr(axis.grid, 'setZValue'):
                        # Use negative z-value to ensure grids stay behind data
                        axis.grid.setZValue(-1000)
                    
                    # Set grid pen to black (consistent with explorer tab)
                    if hasattr(axis.grid, 'setPen'):
                        axis.grid.setPen(get_grid_pen())
                    
                    # Ensure grid opacity is set correctly
                    if hasattr(axis, 'setGrid'):
                        axis.setGrid(255)  # Full opacity
    except Exception as e:
        # Silently handle any grid configuration errors
        pass

def get_trial_pen():
    """Get pen for individual trial traces."""
    color = "#3498db" if CURRENT_THEME_MODE == "dark" else "#2980b9"  # Blue
    return pg.mkPen(color=color, width=1.0)

def get_average_pen():
    """Get pen for average traces."""
    color = "#e74c3c" if CURRENT_THEME_MODE == "dark" else "#c0392b"  # Red
    return pg.mkPen(color=color, width=2.0)

def get_baseline_pen():
    """Get pen for baseline indicators."""
    color = "#2ecc71" if CURRENT_THEME_MODE == "dark" else "#27ae60"  # Green
    return pg.mkPen(color=color, style=QtCore.Qt.PenStyle.DashLine, width=1.5)

def get_response_pen():
    """Get pen for response indicators."""
    color = "#f39c12" if CURRENT_THEME_MODE == "dark" else "#e67e22"  # Orange
    return pg.mkPen(color=color, style=QtCore.Qt.PenStyle.DashLine, width=1.5)

def get_grid_pen():
    """Get pen for grid lines - always black for consistency with explorer tab."""
    return pg.mkPen(color='#000000', width=1.0, style=QtCore.Qt.PenStyle.DotLine)

# ==============================================================================
# Simple Widget Styling Helpers
# ==============================================================================

def style_button(button, style='primary'):
    """Apply simple styling to a QPushButton using Qt's native theming."""
    # With native Qt theming, we rely on the palette for most styling
    # Only apply minimal custom styling if needed
    if style == 'primary':
        # Make primary buttons slightly more prominent
        button.setDefault(True)
    return button

def style_label(label, style='normal'):
    """Apply simple styling to a QLabel using Qt's native theming."""
    # With native Qt theming, labels inherit appropriate colors from palette
    if style == 'heading':
        font = label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        label.setFont(font)
    elif style == 'subheading':
        font = label.font()
        font.setBold(True)
        label.setFont(font)
    return label

def style_result_display(widget):
    """Apply styling to a widget displaying analysis results."""
    # Use system colors for results display
    return widget

def style_info_label(label):
    """Apply styling to an informational label."""
    # Use system colors for info labels
    font = label.font()
    font.setItalic(True)
    label.setFont(font)
    return label

def style_error_message(widget):
    """Apply styling to an error message."""
    # Use system colors for error messages
    palette = widget.palette()
    palette.setColor(widget.foregroundRole(), QtGui.QColor(220, 50, 50))  # Red text
    widget.setPalette(palette)
    return widget

# ==============================================================================
# Legacy compatibility - maintain basic color constants for existing code
# ==============================================================================

# Basic color constants for backward compatibility
def _get_theme_dict():
    """Get theme dictionary with current colors."""
    return {
        'primary': '#2980b9',
        'accent': '#e74c3c', 
        'background': get_plot_background_color(),
        'text_primary': get_plot_foreground_color(),
    }

# Initialize THEME as a basic dict, will be updated by functions as needed
THEME = {
    'primary': '#2980b9',
    'accent': '#e74c3c', 
    'background': '#ffffff',  # Default light background
    'text_primary': '#000000',  # Default dark text
}

# Plot colors for data visualization
PLOT_COLORS = [
    '#3498db',  # Blue
    '#e74c3c',  # Red
    '#2ecc71',  # Green
    '#f39c12',  # Orange
    '#9b59b6',  # Purple
    '#1abc9c',  # Turquoise
    '#34495e',  # Dark gray
    '#e67e22',  # Darker orange
]

# Expose main functions
__all__ = [
    'CURRENT_THEME_MODE', 'THEME', 'PLOT_COLORS',
    'get_current_theme_mode', 'set_theme_mode', 'toggle_theme_mode',
    'apply_stylesheet', 'configure_plot_widget', 'configure_pyqtgraph_globally',
    'get_trial_pen', 'get_average_pen', 'get_baseline_pen', 'get_response_pen', 'get_grid_pen',
    'style_button', 'style_label', 'style_result_display', 'style_info_label', 'style_error_message',
    'get_plot_background_color', 'get_plot_foreground_color'
] 