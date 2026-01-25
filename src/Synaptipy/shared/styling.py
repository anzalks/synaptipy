#!/usr/bin/env python3
"""
Optimized Synaptipy UI Styling Module

This module provides streamlined styling with minimal startup overhead.
It preserves system theming without complex detection during startup.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

from PySide6 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import logging

from .zoom_theme import (
    apply_theme_to_plot_widget,
    apply_theme_with_custom_selection as customize_viewbox_selection_colors,
    get_system_accent_color,
)

log = logging.getLogger(__name__)

# ==============================================================================
# Optimized PyQtGraph Global Configuration
# ==============================================================================


def configure_pyqtgraph_globally():
    """Apply minimal PyQtGraph configuration for fast startup."""
    try:
        # Only essential configuration - minimal overhead
        pg.setConfigOption("imageAxisOrder", "row-major")

        # Disable expensive features during startup
        pg.setConfigOption("useOpenGL", False)  # Avoid OpenGL initialization delays
        pg.setConfigOption("foreground", "k")  # Simple black foreground

        log.debug("PyQtGraph configured with minimal overhead")

    except Exception as e:
        log.warning(f"PyQtGraph configuration failed: {e}")


# ==============================================================================
# Streamlined Application Styling
# ==============================================================================


def apply_stylesheet(app: QtWidgets.QApplication) -> QtWidgets.QApplication:
    """Apply minimal styling that preserves system theme without startup overhead."""
    try:
        # Minimal styling - let system handle theme automatically
        # No complex detection or palette manipulation during startup
        log.debug("Applied minimal styling - system theme preserved")

    except Exception as e:
        log.warning(f"Could not apply styling: {e}")
        log.debug("Keeping system default styling")

    return app


# ==============================================================================
# Optimized Plot Styling (Lazy-loaded)
# ==============================================================================


def get_trial_pen():
    """Get pen for trial data."""
    try:
        from .plot_customization import get_single_trial_pen

        return get_single_trial_pen()
    except ImportError:
        return pg.mkPen(color="b", width=1)


def get_average_pen():
    """Get pen for average data."""
    try:
        from .plot_customization import get_average_pen

        return get_average_pen()
    except ImportError:
        return pg.mkPen(color="k", width=2)


def get_baseline_pen():
    """Get pen for baseline data."""
    return pg.mkPen(color="g", width=1)


def get_response_pen():
    """Get pen for response data."""
    return pg.mkPen(color="r", width=1)


def configure_plot_widget(plot_widget):
    """Configure plot widget with minimal styling."""
    try:
        # Only configure if not already configured
        if not getattr(plot_widget, "_synaptipy_configured", False):
            # Try to use customized grid settings
            try:
                from .plot_customization import get_grid_pen, is_grid_enabled

                if is_grid_enabled():
                    grid_pen = get_grid_pen()
                    if grid_pen:
                        # Get alpha value from pen color
                        alpha = grid_pen.color().alpha() / 255.0
                        log.debug(f"Using grid pen alpha: {alpha} (opacity: {alpha * 100:.1f}%)")

                        plot_widget.showGrid(x=True, y=True, alpha=alpha)
                        log.debug(f"Grid enabled with alpha: {alpha}")
                    else:
                        plot_widget.showGrid(x=False, y=False)
                        log.debug("Grid disabled - no grid pen")
                else:
                    plot_widget.showGrid(x=False, y=False)
                    log.debug("Grid disabled by preference")
            except ImportError:
                plot_widget.showGrid(x=True, y=True, alpha=0.3)

            plot_widget.setBackground("w")  # White background for plots
            plot_widget._synaptipy_configured = True

    except Exception as e:
        log.debug(f"Plot widget configuration failed: {e}")

    return plot_widget


# ==============================================================================
# Lazy Theme Detection (Only when needed)
# ==============================================================================


def get_system_theme_mode():
    """Get system theme mode - lazy-loaded only when needed."""
    # This is now lazy-loaded to avoid startup overhead
    # Return default and let the system handle it automatically
    return "auto"


def _detect_linux_desktop():
    """Detect Linux desktop - lazy-loaded only when needed."""
    # This is now lazy-loaded to avoid startup overhead
    return "auto"


# Removed custom theme functions - preserving original system styling

# ==============================================================================
# Plot Styling for PyQtGraph
# ==============================================================================

# Plot color functions removed - preserving original plot appearance


def _configure_grid_z_order_safe(plot_widget):
    """Safely configure grid z-order with better error handling for Windows compatibility."""
    try:
        plot_item = plot_widget.getPlotItem()
        if not plot_item:
            return

        # Import Z_ORDER from constants
        try:
            from Synaptipy.shared.constants import Z_ORDER

            grid_z_value = Z_ORDER["grid"]
        except (ImportError, KeyError):
            # Fallback to hardcoded value if constants not available
            grid_z_value = -1000

        # Set grid z-values to be behind data (negative values)
        for axis_name in ["bottom", "left"]:
            try:
                axis = plot_item.getAxis(axis_name)
                if not axis:
                    continue

                # Check if grid exists and is properly initialized
                if not hasattr(axis, "grid") or axis.grid is None:
                    continue

                # Only set z-value if the grid item has a valid scene
                if hasattr(axis.grid, "setZValue") and hasattr(axis.grid, "scene"):
                    if axis.grid.scene() is not None:  # Ensure it's added to a scene
                        axis.grid.setZValue(grid_z_value)

                # Set grid pen only if grid is properly initialized
                if hasattr(axis.grid, "setPen"):
                    grid_pen = get_grid_pen()
                    if grid_pen:
                        axis.grid.setPen(grid_pen)
                        log.debug(f"Applied grid pen to axis {axis_name}")
                    else:
                        log.debug(f"Grid pen is None for axis {axis_name}")

                # Ensure grid opacity is set correctly
                if hasattr(axis, "setGrid"):
                    axis.setGrid(255)  # Full opacity

            except Exception as e:
                # Log individual axis errors for debugging but continue
                log.debug(f"Could not configure grid for axis '{axis_name}': {e}")
                continue

    except Exception as e:
        # Silently handle any major grid configuration errors
        log.debug(f"Grid configuration failed: {e}")


def get_grid_pen():
    """Get pen for grid lines."""
    try:
        from .plot_customization import get_grid_pen as get_customized_grid_pen, is_grid_enabled

        if is_grid_enabled():
            return get_customized_grid_pen()
        else:
            return None  # Grid is disabled
    except ImportError:
        # Fallback to default grid pen
        color = "#000000"  # Always black for grid lines
        return pg.mkPen(color=color, width=0.5, alpha=0.3, style=QtCore.Qt.SolidLine)


# ==============================================================================
# Simple Widget Styling Helpers
# ==============================================================================


def style_button(button, style="primary"):
    """Apply simple styling to a QPushButton using Qt's native theming."""
    # With native Qt theming, we rely on the palette for most styling
    # Only apply minimal custom styling if needed
    if style == "primary":
        # Make primary buttons slightly more prominent
        button.setDefault(True)
    return button


def style_label(label, style="normal"):
    """Apply simple styling to a QLabel using Qt's native theming."""
    # With native Qt theming, labels inherit appropriate colors from palette
    if style == "heading":
        font = label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        label.setFont(font)
    elif style == "subheading":
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
    "#377eb8",  # Blue (original trial color)
    "#000000",  # Black (average color)
    "#2ecc71",  # Green
    "#f39c12",  # Orange
    "#9b59b6",  # Purple
    "#1abc9c",  # Turquoise
    "#34495e",  # Dark gray
    "#e67e22",  # Darker orange
]

# Expose main functions
__all__ = [
    "apply_stylesheet",
    "configure_plot_widget",
    "configure_pyqtgraph_globally",
    "get_trial_pen",
    "get_average_pen",
    "get_baseline_pen",
    "get_response_pen",
    "get_grid_pen",
    "style_button",
    "style_label",
    "style_result_display",
    "style_info_label",
    "style_error_message",
    "get_system_theme_mode",
    "PLOT_COLORS",
    "get_system_accent_color",
    "customize_viewbox_selection_colors",
    "apply_theme_to_plot_widget",
]
