#!/usr/bin/env python3
"""
Zoom Selection Theme Customization for Synaptipy

This module provides system theme-aware colors for the zoom selection rectangle
that appears when users drag to zoom in on plots.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


def get_system_accent_color() -> str:
    """Get the system accent color or fallback to a neutral color."""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPalette
        
        app = QApplication.instance()
        if app:
            palette = app.palette()
            # Try to get accent color from various sources
            accent_color = palette.color(QPalette.ColorRole.Accent)
            if accent_color.isValid() and accent_color.alpha() > 0:
                log.debug(f"Using system accent color: {accent_color.name()}")
                return accent_color.name()
            
            # Fallback to highlight color
            highlight_color = palette.color(QPalette.ColorRole.Highlight)
            if highlight_color.isValid() and highlight_color.alpha() > 0:
                log.debug(f"Using system highlight color: {highlight_color.name()}")
                return highlight_color.name()
            
            # Fallback to link color
            link_color = palette.color(QPalette.ColorRole.Link)
            if link_color.isValid() and link_color.alpha() > 0:
                log.debug(f"Using system link color: {link_color.name()}")
                return link_color.name()
        
        # Final fallback to a neutral blue-grey
        log.debug("Using fallback neutral color: #6B7280")
        return "#6B7280"
        
    except Exception as e:
        log.warning(f"Failed to get system accent color: {e}")
        return "#6B7280"


def apply_theme_to_viewbox(viewbox) -> None:
    """Apply system theme colors to a ViewBox's zoom selection rectangle."""
    try:
        if not viewbox:
            return
            
        # Get system-accented color
        accent_color = get_system_accent_color()
        
        # Create new pen and brush with system colors
        from PySide6.QtGui import QPen, QBrush, QColor
        
        # Parse the hex color
        if accent_color.startswith('#'):
            color = QColor(accent_color)
        else:
            color = QColor(accent_color)
            
        if not color.isValid():
            color = QColor("#6B7280")  # Fallback grey
            
        # Create pen with solid color
        new_pen = QPen(color)
        new_pen.setWidth(1)
        
        # Create brush with semi-transparent color
        brush_color = QColor(color)
        brush_color.setAlpha(100)  # 40% opacity
        new_brush = QBrush(brush_color)
        
        # Store the colors on the viewbox for later use
        viewbox._synaptipy_theme_pen = new_pen
        viewbox._synaptipy_theme_brush = new_brush
        
        # Apply the colors immediately if rbScaleBox exists
        if hasattr(viewbox, 'rbScaleBox') and viewbox.rbScaleBox is not None:
            viewbox.rbScaleBox.setPen(new_pen)
            viewbox.rbScaleBox.setBrush(new_brush)
            
        log.debug(f"Applied theme to ViewBox: pen={color.name()}, brush={brush_color.name()}")
        
    except Exception as e:
        log.warning(f"Failed to apply theme to ViewBox: {e}")


def apply_theme_to_plot_widget(plot_widget) -> None:
    """Apply system theme colors to a plot widget's zoom selection rectangle."""
    try:
        if not plot_widget:
            return
            
        # Get the ViewBox and customize its selection colors
        viewbox = plot_widget.getViewBox()
        if viewbox:
            apply_theme_to_viewbox(viewbox)
            
    except Exception as e:
        log.warning(f"Failed to apply theme to plot widget: {e}")


def ensure_theme_colors(viewbox) -> None:
    """Ensure theme colors are applied to a ViewBox."""
    try:
        if not viewbox:
            return
            
        # Check if we have stored theme colors
        if hasattr(viewbox, '_synaptipy_theme_pen') and hasattr(viewbox, '_synaptipy_theme_brush'):
            # Apply stored theme colors
            if hasattr(viewbox, 'rbScaleBox') and viewbox.rbScaleBox is not None:
                viewbox.rbScaleBox.setPen(viewbox._synaptipy_theme_pen)
                viewbox.rbScaleBox.setBrush(viewbox._synaptipy_theme_brush)
        else:
            # Apply theme colors for the first time
            apply_theme_to_viewbox(viewbox)
            
    except Exception as e:
        log.warning(f"Failed to ensure theme colors: {e}")


def apply_theme_with_patching(viewbox) -> None:
    """Apply theme colors to a ViewBox (alias for apply_theme_to_viewbox)."""
    apply_theme_to_viewbox(viewbox)


def refresh_theme_colors(viewbox) -> None:
    """Refresh theme colors on a ViewBox - call this whenever you want to ensure theme is applied."""
    try:
        if not viewbox:
            return
            
        # Check if we have stored theme colors
        if hasattr(viewbox, '_synaptipy_theme_pen') and hasattr(viewbox, '_synaptipy_theme_brush'):
            # Apply stored theme colors
            if hasattr(viewbox, 'rbScaleBox') and viewbox.rbScaleBox is not None:
                viewbox.rbScaleBox.setPen(viewbox._synaptipy_theme_pen)
                viewbox.rbScaleBox.setBrush(viewbox._synaptipy_theme_brush)
                log.debug("Refreshed theme colors on ViewBox")
        else:
            # Apply theme colors for the first time
            apply_theme_to_viewbox(viewbox)
            
    except Exception as e:
        log.warning(f"Failed to refresh theme colors: {e}")


def setup_theme_for_plot(plot_widget) -> None:
    """Set up theme for a plot widget - this will apply theme colors."""
    try:
        if not plot_widget:
            return
            
        # Get the ViewBox and apply theme
        viewbox = plot_widget.getViewBox()
        if viewbox:
            apply_theme_to_viewbox(viewbox)
            log.debug("Set up theme for plot widget")
            
    except Exception as e:
        log.warning(f"Failed to set up theme for plot widget: {e}")


def setup_theme_for_viewbox(viewbox) -> None:
    """Set up theme for a ViewBox - this will apply theme colors."""
    try:
        if viewbox:
            apply_theme_to_viewbox(viewbox)
            log.debug("Set up theme for ViewBox")
    except Exception as e:
        log.warning(f"Failed to set up theme for ViewBox: {e}")

