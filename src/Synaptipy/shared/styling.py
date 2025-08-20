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
# Theme Management - Disabled to preserve original UI appearance
# ==============================================================================

# Theme mode management removed - preserving original system styling

# ==============================================================================
# PyQtGraph Global Configuration (matching explorer tab)
# ==============================================================================

def configure_pyqtgraph_globally():
    """Apply global PyQtGraph configuration for consistent behavior across all plots."""
    # Configure global PyQtGraph settings (matching explorer tab)
    pg.setConfigOption('imageAxisOrder', 'row-major')
    # Don't override background/foreground - let the original styling remain

# ==============================================================================
# Application Theme Functions
# ==============================================================================

def apply_stylesheet(app: QtWidgets.QApplication) -> QtWidgets.QApplication:
    """Apply clean, consistent styling that respects system theme without conflicts."""
    try:
        import platform
        
        # Don't override the system style - let it handle theme automatically
        # This prevents the style from resetting to default light theme
        log.info("Keeping system default style to preserve theme")
        
        # Let the system handle its own theme (light/dark) automatically
        # Don't override with custom palettes or styles - this prevents conflicts
        log.info("System theme handling enabled - no style or palette overrides")
        
    except Exception as e:
        log.warning(f"Could not apply styling: {e}")
        log.info("Keeping system default styling")
        
    return app

def _detect_linux_desktop() -> str:
    """Detect the Linux desktop environment."""
    try:
        import os
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        
        if "gnome" in desktop:
            return "gnome"
        elif "kde" in desktop or "plasma" in desktop:
            return "kde"
        elif "xfce" in desktop:
            return "xfce"
        elif "mate" in desktop:
            return "mate"
        elif "cinnamon" in desktop:
            return "cinnamon"
        else:
            # Try to detect from process list
            try:
                import subprocess
                result = subprocess.run(["ps", "-e"], capture_output=True, text=True)
                if "gnome" in result.stdout.lower():
                    return "gnome"
                elif "kde" in result.stdout.lower() or "plasma" in result.stdout.lower():
                    return "kde"
            except:
                pass
            
        return "unknown"
        
    except Exception as e:
        log.debug(f"Could not detect Linux desktop: {e}")
        return "unknown"

def get_system_theme_mode() -> str:
    """Detect the current system theme mode (light/dark) across platforms."""
    try:
        import platform
        
        if platform.system() == "Darwin":  # macOS
            # macOS: Check for dark mode
            try:
                import subprocess
                result = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], 
                                     capture_output=True, text=True)
                if "Dark" in result.stdout:
                    return "dark"
                else:
                    return "light"
            except:
                return "light"  # Default to light if detection fails
                
        elif platform.system() == "Linux":
            # Linux: Check for dark mode in common desktop environments
            try:
                import os
                desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
                
                if "gnome" in desktop:
                    # GNOME: Check gsettings for dark mode
                    try:
                        import subprocess
                        result = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"], 
                                             capture_output=True, text=True)
                        if "dark" in result.stdout.lower():
                            return "dark"
                        else:
                            return "light"
                    except:
                        pass
                        
                elif "kde" in desktop:
                    # KDE: Check for dark mode
                    try:
                        import subprocess
                        result = subprocess.run(["kreadconfig5", "--group", "General", "--key", "ColorScheme"], 
                                             capture_output=True, text=True)
                        if "breeze" in result.stdout.lower():
                            return "light"  # Breeze is typically light
                        else:
                            return "dark"
                    except:
                        pass
                        
            except:
                pass
                
            return "light"  # Default to light for Linux
            
        elif platform.system() == "Windows":
            # Windows: Check registry for dark mode
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                   r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                return "light" if value == 1 else "dark"
            except:
                return "light"  # Default to light if detection fails
                
        return "light"  # Default fallback
        
    except Exception as e:
        log.debug(f"Could not detect system theme: {e}")
        return "light"



# Removed custom theme functions - preserving original system styling

# ==============================================================================
# Plot Styling for PyQtGraph
# ==============================================================================

# Plot color functions removed - preserving original plot appearance


def configure_plot_widget(plot_widget):
    """Configure a PyQtGraph PlotWidget with minimal styling to preserve original appearance."""
    # Don't override plot styling - let the original appearance remain
    # Only enable grid if not already configured
    if not plot_widget.gridAlpha:
        plot_widget.showGrid(x=True, y=True, alpha=0.3)

def _configure_grid_z_order_safe(plot_widget):
    """Safely configure grid z-order with better error handling for Windows compatibility."""
    try:
        plot_item = plot_widget.getPlotItem()
        if not plot_item:
            return
            
        # Import Z_ORDER from constants
        try:
            from Synaptipy.shared.constants import Z_ORDER
            grid_z_value = Z_ORDER['grid']
        except (ImportError, KeyError):
            # Fallback to hardcoded value if constants not available
            grid_z_value = -1000
            
        # Set grid z-values to be behind data (negative values)
        for axis_name in ['bottom', 'left']:
            try:
                axis = plot_item.getAxis(axis_name)
                if not axis:
                    continue
                    
                # Check if grid exists and is properly initialized
                if not hasattr(axis, 'grid') or axis.grid is None:
                    continue
                    
                # Only set z-value if the grid item has a valid scene
                if hasattr(axis.grid, 'setZValue') and hasattr(axis.grid, 'scene'):
                    if axis.grid.scene() is not None:  # Ensure it's added to a scene
                        axis.grid.setZValue(grid_z_value)
                    
                # Set grid pen only if grid is properly initialized
                if hasattr(axis.grid, 'setPen'):
                    axis.grid.setPen(get_grid_pen())
                    
                # Ensure grid opacity is set correctly
                if hasattr(axis, 'setGrid'):
                    axis.setGrid(255)  # Full opacity
                    
            except Exception as e:
                # Log individual axis errors for debugging but continue
                log.debug(f"Could not configure grid for axis '{axis_name}': {e}")
                continue
                
    except Exception as e:
        # Silently handle any major grid configuration errors
        log.debug(f"Grid configuration failed: {e}")

def get_trial_pen():
    """Get pen for individual trial traces."""
    return pg.mkPen(color="#377eb8", width=1.0)  # Original blue color

def get_average_pen():
    """Get pen for average traces."""
    return pg.mkPen(color="#000000", width=2.0)  # Black as requested

def get_baseline_pen():
    """Get pen for baseline indicator lines."""
    return pg.mkPen(color="#7f8c8d", width=1.5, style=QtCore.Qt.DashLine)  # Gray

def get_response_pen():
    """Get pen for response indicator lines."""
    return pg.mkPen(color="#f39c12", width=1.5, style=QtCore.Qt.DashLine)  # Orange

def get_grid_pen():
    """Get pen for grid lines."""
    color = "#000000"  # Always black for grid lines
    return pg.mkPen(color=color, width=0.5, style=QtCore.Qt.SolidLine)

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
# Legacy compatibility - simplified for original UI appearance
# ==============================================================================

# Basic color constants for backward compatibility
PLOT_COLORS = [
    '#377eb8',  # Blue (original trial color)
    '#000000',  # Black (average color)
    '#2ecc71',  # Green
    '#f39c12',  # Orange
    '#9b59b6',  # Purple
    '#1abc9c',  # Turquoise
    '#34495e',  # Dark gray
    '#e67e22',  # Darker orange
]

# Expose main functions
__all__ = [
    'apply_stylesheet', 'configure_plot_widget', 'configure_pyqtgraph_globally',
    'get_trial_pen', 'get_average_pen', 'get_baseline_pen', 'get_response_pen', 'get_grid_pen',
    'style_button', 'style_label', 'style_result_display', 'style_info_label', 'style_error_message',
    'get_system_theme_mode', 'PLOT_COLORS'
] 