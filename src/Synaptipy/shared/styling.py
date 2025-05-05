#!/usr/bin/env python3
"""
Synaptipy UI Styling Module

This module defines all styling, theming, and appearance settings for the Synaptipy application.
It provides a centralized way to control all visual aspects of the UI.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

from PySide6 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import logging

log = logging.getLogger(__name__)

# ==============================================================================
# Color Constants
# ==============================================================================

# Current theme mode (dark/light)
CURRENT_THEME_MODE = "dark"  # Default to dark mode initially

# Application Dark Theme Colors
DARK_THEME = {
    # Main application colors
    'primary': '#3D7AB3',         # Blue primary color
    'secondary': '#2A5F8E',       # Darker blue
    'accent': '#EE4B2B',          # Red accent
    'background': '#303030',      # Dark background
    'surface': '#424242',         # Surface color
    'error': '#CF6679',           # Error color
    'warning': '#FFCC00',         # Warning color
    'success': '#4CAF50',         # Success color
    
    # Text colors
    'text_primary': '#FFFFFF',    # Primary text on dark background
    'text_secondary': '#B0B0B0',  # Secondary text
    'text_disabled': '#757575',   # Disabled text
    
    # Graph plotting colors - UPDATED to match original colors
    'trial_color': '#377EB8',     # Original blue trace color (RGB: 55, 126, 184)
    'average_color': '#000000',   # Black color for average traces
    'axis_color': '#000000',      # Axis color (CHANGED TO SOLID BLACK)
    'grid_color': '#000000',      # Grid lines color (CHANGED TO SOLID BLACK)
    'baseline_region': '#22AA22AA', # Baseline region with alpha
    'response_region': '#AA2222AA', # Response region with alpha
}

# Application Light Theme Colors
LIGHT_THEME = {
    # Main application colors
    'primary': '#3D7AB3',         # Blue primary color
    'secondary': '#2A5F8E',       # Darker blue
    'accent': '#EE4B2B',          # Red accent
    'background': '#F5F5F5',      # Light background
    'surface': '#FFFFFF',         # Surface color
    'error': '#B00020',           # Error color
    'warning': '#FF9800',         # Warning color
    'success': '#4CAF50',         # Success color
    
    # Text colors
    'text_primary': '#000000',    # Primary text on light background
    'text_secondary': '#555555',  # Secondary text
    'text_disabled': '#9E9E9E',   # Disabled text
    
    # Graph plotting colors
    'trial_color': '#377EB8',     # Original blue trace color (RGB: 55, 126, 184)
    'average_color': '#000000',   # Black color for average traces
    'axis_color': '#000000',      # Axis color (CHANGED TO SOLID BLACK)
    'grid_color': '#000000',      # Grid lines color (CHANGED TO SOLID BLACK)
    'baseline_region': '#22AA2277', # Baseline region with alpha
    'response_region': '#AA222277', # Response region with alpha
}

# Use dark theme as the active theme by default
THEME = DARK_THEME.copy()

# Application Color Palette
PALETTE = {
    'blues': ['#E3F2FD', '#BBDEFB', '#90CAF9', '#64B5F6', '#42A5F5', '#2196F3', '#1E88E5', '#1976D2', '#1565C0', '#0D47A1'],
    'reds': ['#FFEBEE', '#FFCDD2', '#EF9A9A', '#E57373', '#EF5350', '#F44336', '#E53935', '#D32F2F', '#C62828', '#B71C1C'],
    'greens': ['#E8F5E9', '#C8E6C9', '#A5D6A7', '#81C784', '#66BB6A', '#4CAF50', '#43A047', '#388E3C', '#2E7D32', '#1B5E20'],
    'grays': ['#FAFAFA', '#F5F5F5', '#EEEEEE', '#E0E0E0', '#BDBDBD', '#9E9E9E', '#757575', '#616161', '#424242', '#212121'],
}

# Plot colors for different data channels - UPDATED to match original colors
PLOT_COLORS = [
    '#377EB8',                       # Original blue (55, 126, 184)
    '#E41A1C',                       # Red
    '#4DAF4A',                       # Green
    '#984EA3',                       # Purple
    '#FF7F00',                       # Orange
    '#FFFF33',                       # Yellow
    '#A65628',                       # Brown
    '#F781BF',                       # Pink
]

# Alpha values for various UI elements
ALPHA = {
    'trial_traces': 100,             # Alpha for overlaid trial traces (0-255)
    'regions': 50,                   # Alpha for interactive regions
    'inactive': 30,                  # Alpha for inactive elements
    'highlighted': 150,              # Alpha for highlighted elements
}

# Z-order values for rendering priority
Z_ORDER = {
    'grid': -1000,                   # Grid lines (very back)
    'axes': -500,                    # Axes (behind data, in front of grid)
    'background_data': 100,          # Background data (e.g., individual trials)
    'primary_data': 1000,            # Primary data (e.g., single trial or main trace)
    'average_data': 1500,            # Average data (typical highlight)
    'selected_data': 2000,           # Selected/highlighted data
    'text_overlay': 3000,            # Text overlay (annotations, errors)
}

# ==============================================================================
# Element Styling
# ==============================================================================

# Button styles for different contexts
BUTTON_STYLES = {
    'primary': f"""
        QPushButton {{
            background-color: {THEME['primary']};
            color: {THEME['text_primary']};
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: bold;
            min-height: 30px;
        }}
        QPushButton:hover {{
            background-color: {THEME['secondary']};
        }}
        QPushButton:pressed {{
            background-color: #1E5086;
        }}
        QPushButton:disabled {{
            background-color: #555555;
            color: {THEME['text_disabled']};
        }}
    """,
    
    'action': f"""
        QPushButton {{
            background-color: {THEME['accent']};
            color: {THEME['text_primary']};
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: bold;
            min-height: 30px;
        }}
        QPushButton:hover {{
            background-color: #D32F2F;
        }}
        QPushButton:pressed {{
            background-color: #B71C1C;
        }}
        QPushButton:disabled {{
            background-color: #555555;
            color: {THEME['text_disabled']};
        }}
    """,
    
    'toolbar': f"""
        QPushButton {{
            background-color: transparent;
            color: {THEME['text_primary']};
            border: none;
            padding: 4px 8px;
        }}
        QPushButton:hover {{
            background-color: rgba(127, 127, 127, 30);
        }}
        QPushButton:pressed {{
            background-color: rgba(127, 127, 127, 50);
        }}
        QPushButton:disabled {{
            color: {THEME['text_disabled']};
        }}
    """,
}

# Text and label styles
TEXT_STYLES = {
    'heading': f"""
        font-weight: bold;
        font-size: 16px;
        color: {THEME['text_primary']};
    """,
    
    'subheading': f"""
        font-weight: bold;
        font-size: 14px;
        color: {THEME['text_primary']};
    """,
    
    'info': f"""
        font-style: italic;
        color: {THEME['text_secondary']};
    """,
    
    'result': f"""
        font-weight: bold;
        color: {THEME['accent']};
    """,
    
    'error': f"""
        font-weight: bold;
        color: {THEME['error']};
    """,
}

# ==============================================================================
# Theme Switching Function
# ==============================================================================

def toggle_theme_mode():
    """
    Toggle between light and dark theme modes.
    Returns the new theme mode name ("light" or "dark").
    """
    global CURRENT_THEME_MODE, THEME, BUTTON_STYLES, TEXT_STYLES
    
    # Toggle the theme mode
    if CURRENT_THEME_MODE == "dark":
        CURRENT_THEME_MODE = "light"
        THEME = LIGHT_THEME.copy()
    else:
        CURRENT_THEME_MODE = "dark"
        THEME = DARK_THEME.copy()
    
    # Update dependent styles
    _update_dependent_styles()
    
    return CURRENT_THEME_MODE

def set_theme_mode(mode):
    """
    Set the theme to a specific mode.
    
    Args:
        mode: String "light" or "dark"
        
    Returns:
        The current theme mode.
    """
    global CURRENT_THEME_MODE, THEME, BUTTON_STYLES, TEXT_STYLES
    
    if mode not in ["light", "dark"]:
        log.warning(f"Invalid theme mode '{mode}'. Using 'dark' instead.")
        mode = "dark"
    
    if mode != CURRENT_THEME_MODE:
        CURRENT_THEME_MODE = mode
        THEME = LIGHT_THEME.copy() if mode == "light" else DARK_THEME.copy()
        _update_dependent_styles()
    
    return CURRENT_THEME_MODE

def get_current_theme_mode():
    """Returns the current theme mode ("light" or "dark")."""
    return CURRENT_THEME_MODE

def _update_dependent_styles():
    """Update all style definitions that depend on the THEME colors."""
    global BUTTON_STYLES, TEXT_STYLES
    
    # Update button styles
    BUTTON_STYLES = {
        'primary': f"""
            QPushButton {{
                background-color: {THEME['primary']};
                color: {THEME['text_primary']};
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: {THEME['secondary']};
            }}
            QPushButton:pressed {{
                background-color: #1E5086;
            }}
            QPushButton:disabled {{
                background-color: #555555;
                color: {THEME['text_disabled']};
            }}
        """,
        
        'action': f"""
            QPushButton {{
                background-color: {THEME['accent']};
                color: {THEME['text_primary']};
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: #D32F2F;
            }}
            QPushButton:pressed {{
                background-color: #B71C1C;
            }}
            QPushButton:disabled {{
                background-color: #555555;
                color: {THEME['text_disabled']};
            }}
        """,
        
        'toolbar': f"""
            QPushButton {{
                background-color: transparent;
                color: {THEME['text_primary']};
                border: none;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: rgba(127, 127, 127, 30);
            }}
            QPushButton:pressed {{
                background-color: rgba(127, 127, 127, 50);
            }}
            QPushButton:disabled {{
                color: {THEME['text_disabled']};
            }}
        """,
    }

    # Update text styles
    TEXT_STYLES = {
        'heading': f"""
            font-weight: bold;
            font-size: 16px;
            color: {THEME['text_primary']};
        """,
        
        'subheading': f"""
            font-weight: bold;
            font-size: 14px;
            color: {THEME['text_primary']};
        """,
        
        'info': f"""
            font-style: italic;
            color: {THEME['text_secondary']};
        """,
        
        'result': f"""
            font-weight: bold;
            color: {THEME['accent']};
        """,
        
        'error': f"""
            font-weight: bold;
            color: {THEME['error']};
        """,
    }

# ==============================================================================
# PyQtGraph styling helpers
# ==============================================================================

def get_trial_pen(width=1):
    """Get a pen for plotting individual trials."""
    color = THEME['trial_color']
    return pg.mkPen(color=color, width=width)

def get_average_pen(width=2):
    """Get a pen for plotting averaged traces."""
    color = THEME['average_color']
    return pg.mkPen(color=color, width=width)

def get_baseline_pen():
    """Get a pen for plotting baseline indicators."""
    return pg.mkPen(color=(0, 150, 0), style=QtCore.Qt.PenStyle.DashLine, width=1.5)

def get_response_pen():
    """Get a pen for plotting response indicators."""
    return pg.mkPen(color=(200, 0, 0), style=QtCore.Qt.PenStyle.DashLine, width=1.5)

def get_baseline_brush():
    """Get a brush for baseline regions."""
    return QtGui.QBrush(QtGui.QColor.fromString(THEME['baseline_region']))

def get_response_brush():
    """Get a brush for response regions."""
    return QtGui.QBrush(QtGui.QColor.fromString(THEME['response_region']))

def get_axis_pen():
    """Get a pen for graph axes."""
    # Always use solid black for axes with explicit alpha=255
    axis_color = QtGui.QColor('#000000')  # Force black color regardless of theme
    axis_color.setAlpha(255)  # Ensure full opacity
    
    # Create a thicker pen for better visibility
    axis_pen = pg.mkPen(color=axis_color, width=1.5)
    axis_pen.setCosmetic(True)  # Ensure consistent width regardless of zoom
    
    return axis_pen

def get_grid_pen():
    """Get a pen for graph grid lines."""
    # Always use solid black for grid lines with explicit alpha=255
    grid_color = QtGui.QColor('#000000')  # Force black color regardless of theme
    grid_color.setAlpha(255)  # Force full opacity
    
    # Create a pen with increased contrast for better visibility
    grid_pen = pg.mkPen(color=grid_color, width=1.2, style=QtCore.Qt.PenStyle.DotLine)
    grid_pen.setCosmetic(True)  # Ensure consistent width regardless of zoom
    
    return grid_pen

def get_plot_pen(index=0, width=1):
    """Get a pen for plotted data based on index."""
    color_idx = index % len(PLOT_COLORS)
    return pg.mkPen(color=PLOT_COLORS[color_idx], width=width)

def configure_plot_widget(plot_widget):
    """Apply consistent styling to a PyQtGraph plot widget."""
    # Always use white background for plot area, regardless of theme mode
    plot_widget.setBackground('white')
    
    # Properly style axes with solid, non-transparent pens
    axis_pen = get_axis_pen()
    axis_pen.setCosmetic(True)  # Ensure consistent width
    axis_pen.setWidth(1.5)      # Slightly thicker for better visibility
    
    for axis in ('left', 'bottom', 'right', 'top'):
        try:
            axis_item = plot_widget.getAxis(axis)
            if axis_item:
                axis_item.setPen(axis_pen)
                # Set text color based on theme
                axis_item.setTextPen(axis_pen)
                # Make sure grid is initialized properly for this axis
                if hasattr(axis_item, 'grid') and axis_item.grid is None:
                    axis_item.grid = 255  # Initialize with integer value
        except Exception:
            pass
    
    # Get the plot item and view box
    plot_item = plot_widget.getPlotItem()
    view_box = plot_widget.getViewBox() if plot_item else None
    
    # Create fully opaque grid pens
    x_grid_pen = get_grid_pen()
    y_grid_pen = get_grid_pen()
    
    # *** CRITICAL FIX: Set z-value ordering first ***
    if plot_item:
        # Set z-values AFTER creating grid but BEFORE adding data
        # Set plot item z-value high to ensure data is on top
        plot_item.setZValue(Z_ORDER['primary_data'])  # Higher z-value appears on top
        
        # Configure grid visibility
        plot_item.showGrid(x=True, y=True, alpha=1.0)
        
        # Manually set grid z-values very low
        try:
            # Apply settings to grid items
            bottom_axis = plot_item.getAxis('bottom')
            left_axis = plot_item.getAxis('left')
            
            # Set bottom axis grid
            if hasattr(bottom_axis, 'grid'):
                # If grid is an actual object (not an int)
                if hasattr(bottom_axis.grid, 'setZValue'):
                    bottom_axis.grid.setZValue(Z_ORDER['grid'])  # Very low z-value
                    if hasattr(bottom_axis.grid, 'setPen'):
                        bottom_axis.grid.setPen(x_grid_pen)
                # If grid is just an integer
                elif bottom_axis.grid is None or isinstance(bottom_axis.grid, int):
                    bottom_axis.grid = 255  # Use high value for opacity
            
            # Set left axis grid
            if hasattr(left_axis, 'grid'):
                # If grid is an actual object (not an int)
                if hasattr(left_axis.grid, 'setZValue'):
                    left_axis.grid.setZValue(Z_ORDER['grid'])  # Very low z-value
                    if hasattr(left_axis.grid, 'setPen'):
                        left_axis.grid.setPen(y_grid_pen)
                # If grid is just an integer
                elif left_axis.grid is None or isinstance(left_axis.grid, int):
                    left_axis.grid = 255  # Use high value for opacity
        except Exception:
            pass
            
    # Configure the view box
    if view_box:
        view_box.setMouseMode(pg.ViewBox.RectMode)
        view_box.mouseEnabled = True
    
    return plot_widget

def configure_plot_item(plot_item):
    """Apply consistent styling to a PyQtGraph PlotItem (for GraphicsLayoutWidget plots)."""
    # Style axes with solid, non-transparent pens
    axis_pen = get_axis_pen()
    axis_pen.setCosmetic(True)  # Ensure consistent width
    axis_pen.setWidth(1.5)      # Slightly thicker for better visibility
    
    for ax_name in ('left', 'bottom', 'right', 'top'):
        try:
            axis = plot_item.getAxis(ax_name)
            if axis:
                axis.setPen(axis_pen)
                axis.setTextPen(axis_pen)
                # Make sure grid is initialized properly for this axis
                if hasattr(axis, 'grid') and axis.grid is None:
                    axis.grid = 255  # Initialize with integer value
        except Exception:
            pass
    
    # Create fully opaque grid pens
    x_grid_pen = get_grid_pen()
    y_grid_pen = get_grid_pen()
    
    # Set very high z-value for the plot item (containing data items)
    plot_item.setZValue(Z_ORDER['primary_data'])  # Higher z-value appears on top
    
    # EXPLICITLY FORCE GRID VISIBILITY
    plot_item.showGrid(x=True, y=True, alpha=1.0)
    
    # Force the grid lines behind data with extremely low z-values
    try:
        bottom_axis = plot_item.getAxis('bottom')
        left_axis = plot_item.getAxis('left')
        
        if bottom_axis and hasattr(bottom_axis, 'grid'):
            # If grid is an actual object (not an int)
            if hasattr(bottom_axis.grid, 'setZValue'):
                # Set z-value to ensure grid is behind data
                bottom_axis.grid.setZValue(Z_ORDER['grid'])  # Very low z-value
                if hasattr(bottom_axis.grid, 'setPen'):
                    bottom_axis.grid.setPen(x_grid_pen)
            # If grid is just an integer or None
            elif bottom_axis.grid is None or isinstance(bottom_axis.grid, int):
                bottom_axis.grid = 255  # Use high value for opacity
        
        if left_axis and hasattr(left_axis, 'grid'):
            # If grid is an actual object (not an int)
            if hasattr(left_axis.grid, 'setZValue'):
                # Set z-value to ensure grid is behind data
                left_axis.grid.setZValue(Z_ORDER['grid'])  # Very low z-value 
                if hasattr(left_axis.grid, 'setPen'):
                    left_axis.grid.setPen(y_grid_pen)
            # If grid is just an integer or None
            elif left_axis.grid is None or isinstance(left_axis.grid, int):
                left_axis.grid = 255  # Use high value for opacity
    except Exception:
        pass
    
    # Configure ViewBox for rectangle selection zoom
    try:
        viewbox = plot_item.getViewBox()
        if viewbox:
            viewbox.setMouseMode(pg.ViewBox.RectMode)
            viewbox.mouseEnabled = True
    except Exception:
        pass
    
    return plot_item

# New function to set plot data item z-ordering consistently
def set_data_item_z_order(data_item, item_type='primary_data'):
    """
    Set the z-value for a plot data item to ensure consistent rendering order.
    
    Args:
        data_item: The PlotDataItem or similar object to set z-order on
        item_type: String indicating the type of data being plotted. Valid values:
                  'background_data' - Individual trials or background traces
                  'primary_data' - Main data series 
                  'average_data' - Average trace
                  'selected_data' - Manually selected data
                  'text_overlay' - Text annotations
    Returns:
        The data_item with updated z-order
    """
    if hasattr(data_item, 'setZValue'):
        z_value = Z_ORDER.get(item_type, Z_ORDER['primary_data'])
        data_item.setZValue(z_value)
    return data_item

# ==============================================================================
# Application Theme Functions
# ==============================================================================

def apply_stylesheet(app):
    """Apply the appropriate stylesheet to the QApplication based on current theme."""
    try:
        if CURRENT_THEME_MODE == "dark":
            _apply_dark_style(app)
        else:
            _apply_light_style(app)
    except Exception as e:
        log.warning(f"Could not apply application theme: {e}")
    
    return app

def _apply_dark_style(app):
    """Apply dark styling to the application."""
    try:
        # Try to use qdarkstyle first (if available)
        try:
            import qdarkstyle
            if hasattr(qdarkstyle, 'load_stylesheet'):
                style = qdarkstyle.load_stylesheet(qt_api='pyside6')
            elif hasattr(qdarkstyle, 'load_stylesheet_pyside6'):
                style = qdarkstyle.load_stylesheet_pyside6()
            
            if style:
                # Apply base style from qdarkstyle
                app.setStyleSheet(style)
                log.info("Applied qdarkstyle as base theme.")
            else:
                log.warning("qdarkstyle found but no suitable load_stylesheet function.")
                _apply_fallback_dark_style(app)
        except ImportError:
            log.info("qdarkstyle not found, using fallback dark style.")
            _apply_fallback_dark_style(app)
    except Exception as e:
        log.warning(f"Could not apply dark theme: {e}")

def _apply_light_style(app):
    """Apply light styling to the application."""
    # Base application palette for light theme
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(LIGHT_THEME['background']))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(LIGHT_THEME['text_primary']))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(LIGHT_THEME['surface']))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor('#E0E0E0'))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(LIGHT_THEME['text_primary']))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(LIGHT_THEME['text_primary']))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(LIGHT_THEME['text_primary']))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(LIGHT_THEME['surface']))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(LIGHT_THEME['text_primary']))
    palette.setColor(QtGui.QPalette.Link, QtGui.QColor(LIGHT_THEME['primary']))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(LIGHT_THEME['primary']))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor('#FFFFFF')) # White text for highlights
    
    # Additional styling for disabled elements
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(LIGHT_THEME['text_disabled']))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(LIGHT_THEME['text_disabled']))
    
    app.setPalette(palette)
    
    # Try to use the system's native style (windowsvista as shown in the image)
    try:
        app.setStyle("windowsvista")
    except Exception:
        app.setStyle("Fusion")  # Fallback to Fusion if windowsvista not available
    
    # Additional stylesheet for controls (light theme)
    app.setStyleSheet("""
        QToolTip { 
            color: #000000; 
            background-color: #F5F5F5;
            border: 1px solid #BDBDBD;
            padding: 2px;
        }
        
        QTableView, QTreeView, QListView {
            background-color: #FFFFFF;
            alternate-background-color: #F5F5F5;
            selection-background-color: #BBDEFB;
            selection-color: #000000;
        }
        
        QTabBar::tab {
            background-color: #F5F5F5;
            color: #555555;
            padding: 6px 12px;
            border: 1px solid #BDBDBD;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        
        QTabBar::tab:selected {
            background-color: #FFFFFF;
            color: #000000;
            border-bottom: none;
        }
        
        QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
            background-color: #FFFFFF;
            color: #000000;
            border: 1px solid #BDBDBD;
            padding: 4px;
        }
        
        QProgressBar {
            border: 1px solid #BDBDBD;
            border-radius: 3px;
            background-color: #F5F5F5;
            text-align: center;
            color: #000000;
        }
        
        QProgressBar::chunk {
            background-color: #3D7AB3;
            width: 10px;
        }
        
        QScrollBar:vertical {
            border: none;
            background-color: #F5F5F5;
            width: 12px;
            margin: 12px 0 12px 0;
        }
        
        QScrollBar::handle:vertical {
            background-color: #BDBDBD;
            min-height: 20px;
        }
        
        QScrollBar::handle:vertical:hover {
            background-color: #9E9E9E;
        }
        
        QScrollBar:horizontal {
            border: none;
            background-color: #F5F5F5;
            height: 12px;
            margin: 0 12px 0 12px;
        }
        
        QScrollBar::handle:horizontal {
            background-color: #BDBDBD;
            min-width: 20px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background-color: #9E9E9E;
        }
    """)
    
    log.info("Applied light theme style.")
    return app

def _apply_fallback_dark_style(app):
    """Apply a fallback dark style when qdarkstyle is not available."""
    # Base application palette
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(THEME['background']))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(THEME['text_primary']))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(THEME['surface']))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor('#3A3A3A'))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(THEME['text_primary']))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(THEME['text_primary']))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(THEME['text_primary']))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(THEME['surface']))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(THEME['text_primary']))
    palette.setColor(QtGui.QPalette.Link, QtGui.QColor(THEME['primary']))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(THEME['primary']))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(THEME['text_primary']))
    
    # Additional styling for disabled elements
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(THEME['text_disabled']))
    palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(THEME['text_disabled']))
    
    app.setPalette(palette)
    
    # Set the application style to Fusion for dark mode
    app.setStyle("Fusion")
    
    # Additional stylesheet for controls
    app.setStyleSheet("""
        QToolTip { 
            color: #FFFFFF; 
            background-color: #2A5F8E;
            border: 1px solid #3D7AB3;
            padding: 2px;
        }
        
        QTableView, QTreeView, QListView {
            background-color: #303030;
            alternate-background-color: #3A3A3A;
            selection-background-color: #2A5F8E;
        }
        
        QTabBar::tab {
            background-color: #424242;
            color: #B0B0B0;
            padding: 6px 12px;
        }
        
        QTabBar::tab:selected {
            background-color: #3D7AB3;
            color: #FFFFFF;
        }
        
        QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
            background-color: #424242;
            color: #FFFFFF;
            border: 1px solid #555555;
            padding: 4px;
        }
        
        QProgressBar {
            border: 1px solid #555555;
            border-radius: 3px;
            background-color: #424242;
            text-align: center;
            color: #FFFFFF;
        }
        
        QProgressBar::chunk {
            background-color: #3D7AB3;
            width: 10px;
        }
        
        QScrollBar:vertical {
            border: none;
            background-color: #424242;
            width: 12px;
            margin: 12px 0 12px 0;
        }
        
        QScrollBar::handle:vertical {
            background-color: #555555;
            min-height: 20px;
        }
        
        QScrollBar::handle:vertical:hover {
            background-color: #666666;
        }
        
        QScrollBar:horizontal {
            border: none;
            background-color: #424242;
            height: 12px;
            margin: 0 12px 0 12px;
        }
        
        QScrollBar::handle:horizontal {
            background-color: #555555;
            min-width: 20px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background-color: #666666;
        }
    """)
    
    log.info("Applied fallback dark style.")
    return app

# ==============================================================================
# Helper functions for widgets
# ==============================================================================

def style_button(button, style='primary'):
    """Apply consistent styling to a QPushButton."""
    if style in BUTTON_STYLES:
        button.setStyleSheet(BUTTON_STYLES[style])
    return button

def style_label(label, style='subheading'):
    """Apply consistent styling to a QLabel."""
    if style in TEXT_STYLES:
        label.setStyleSheet(TEXT_STYLES[style])
    return label

def style_result_display(widget):
    """Apply styling to a widget displaying analysis results."""
    widget.setStyleSheet(TEXT_STYLES['result'])
    return widget

def style_info_label(label):
    """Apply styling to an informational label."""
    label.setStyleSheet(TEXT_STYLES['info'])
    return label

def style_error_message(widget):
    """Apply styling to an error message."""
    widget.setStyleSheet(TEXT_STYLES['error'])
    return widget

# Make constants available at the module level
__all__ = [
    'THEME', 'PALETTE', 'PLOT_COLORS', 'ALPHA',
    'BUTTON_STYLES', 'TEXT_STYLES',
    'get_trial_pen', 'get_average_pen', 'get_baseline_pen', 'get_response_pen',
    'get_baseline_brush', 'get_response_brush', 'get_axis_pen', 'get_grid_pen',
    'get_plot_pen', 'configure_plot_widget', 'apply_stylesheet',
    'style_button', 'style_label', 'style_result_display', 'style_info_label',
    'style_error_message', 'toggle_theme_mode', 'set_theme_mode', 'get_current_theme_mode',
    'Z_ORDER', 'set_data_item_z_order'
] 