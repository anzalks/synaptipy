#!/usr/bin/env python3
"""
Zoom Selection Theme Customization for Synaptipy

This module provides system theme-aware colors for the zoom selection rectangle
that appears when users drag to zoom in on plots.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
# from typing import Optional
import shiboken6

log = logging.getLogger(__name__)

# Cached styling objects and class-patch state
_CACHED_PEN = None
_CACHED_BRUSH = None
_PATCHED_CLASSES = set()


def _build_cached_pen_brush():
    """Create and cache the pen/brush from current system accent color."""
    from PySide6.QtGui import QPen, QBrush, QColor
    from PySide6.QtCore import Qt

    accent_color = get_system_accent_color()
    color = QColor(accent_color)
    if not color.isValid():
        color = QColor("#6B7280")

    pen = QPen(color)
    pen.setWidth(1)
    pen.setStyle(Qt.SolidLine)
    pen.setCapStyle(Qt.SquareCap)
    pen.setJoinStyle(Qt.MiterJoin)
    pen.setCosmetic(True)

    brush_color = QColor(color)
    brush_color.setAlpha(77)  # ~30% opacity (70% transparency)
    brush = QBrush(brush_color, Qt.SolidPattern)

    global _CACHED_PEN, _CACHED_BRUSH
    _CACHED_PEN, _CACHED_BRUSH = pen, brush


def get_cached_pen_brush():
    """Return cached pen/brush, building them if needed."""
    # global _CACHED_PEN, _CACHED_BRUSH
    if _CACHED_PEN is None or _CACHED_BRUSH is None:
        _build_cached_pen_brush()
    return _CACHED_PEN, _CACHED_BRUSH


def refresh_cached_pen_brush():
    """Rebuild cached pen/brush (call on theme change)."""
    _build_cached_pen_brush()


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
        log.debug("Using fallback neutral color:  #6B7280")
        return "#6B7280"

    except Exception as e:
        log.warning(f"Failed to get system accent color: {e}")
        return "#6B7280"


def apply_theme_to_viewbox(viewbox) -> None:
    """Apply system theme colors to a ViewBox's zoom selection rectangle."""
    try:
        if not viewbox or not shiboken6.isValid(viewbox):
            return
        # Use cached pen/brush to avoid per-ViewBox construction and palette fetch
        pen, brush = get_cached_pen_brush()

        # Store references in case other code wants to reuse them
        viewbox._synaptipy_theme_pen = pen
        viewbox._synaptipy_theme_brush = brush

        # Apply immediately if rbScaleBox exists and is valid
        rb = getattr(viewbox, "rbScaleBox", None)
        if rb is not None and shiboken6.isValid(rb):
            rb.setPen(pen)
            rb.setBrush(brush)

        log.debug("Applied cached theme to ViewBox")

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
        if not viewbox or not shiboken6.isValid(viewbox):
            return

        # Check if we have stored theme colors
        if hasattr(viewbox, "_synaptipy_theme_pen") and hasattr(viewbox, "_synaptipy_theme_brush"):
            # Apply stored theme colors
            rb = getattr(viewbox, "rbScaleBox", None)
            if rb is not None and shiboken6.isValid(rb):
                rb.setPen(viewbox._synaptipy_theme_pen)
                rb.setBrush(viewbox._synaptipy_theme_brush)
        else:
            # Apply theme colors for the first time
            apply_theme_to_viewbox(viewbox)

    except Exception as e:
        log.warning(f"Failed to ensure theme colors: {e}")


def refresh_theme_colors(viewbox) -> None:
    """Refresh theme colors on a ViewBox - call this whenever you want to ensure theme is applied."""
    try:
        if not viewbox or not shiboken6.isValid(viewbox):
            return

        # Check if we have stored theme colors
        if hasattr(viewbox, "_synaptipy_theme_pen") and hasattr(viewbox, "_synaptipy_theme_brush"):
            # Apply stored theme colors
            rb = getattr(viewbox, "rbScaleBox", None)
            if rb is not None and shiboken6.isValid(rb):
                rb.setPen(viewbox._synaptipy_theme_pen)
                rb.setBrush(viewbox._synaptipy_theme_brush)
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


def apply_theme_with_monitoring(viewbox) -> None:
    """Apply theme and monitor for rbScaleBox changes to reapply theme."""
    try:
        if not viewbox:
            return

        log.debug("Applying theme with monitoring...")

        # Apply initial theme
        apply_theme_to_viewbox(viewbox)

        # Set up aggressive monitoring to reapply theme when rbScaleBox changes
        def monitor_and_reapply():
            try:
                if hasattr(viewbox, "rbScaleBox") and viewbox.rbScaleBox is not None:
                    # Force reapply theme to ensure it sticks
                    apply_theme_to_viewbox(viewbox)

                    # Also try to force the rectangle shape
                    rb = viewbox.rbScaleBox
                    if rb is not None:
                        # Force rectangular shape
                        rb.resetTransform()
                        rb.setRotation(0)
                        rb.setScale(1.0)

                        # Force sharp corners
                        from PySide6.QtCore import Qt
                        from PySide6.QtGui import QPen

                        if hasattr(viewbox, "_synaptipy_theme_pen"):
                            sharp_pen = QPen(viewbox._synaptipy_theme_pen.color())
                            sharp_pen.setWidth(1)
                            sharp_pen.setCapStyle(Qt.SquareCap)
                            sharp_pen.setJoinStyle(Qt.MiterJoin)
                            rb.setPen(sharp_pen)

                        # Force transparency
                        if hasattr(viewbox, "_synaptipy_theme_brush"):
                            rb.setBrush(viewbox._synaptipy_theme_brush)

                    # Set up a timer to keep monitoring
                    from PySide6.QtCore import QTimer

                    timer = QTimer()
                    timer.timeout.connect(lambda: monitor_and_reapply())
                    timer.start(50)  # Check every 50ms for more aggressive monitoring

            except Exception as e:
                log.debug(f"Monitor reapply failed: {e}")

        # Start monitoring immediately
        from PySide6.QtCore import QTimer

        QTimer.singleShot(10, monitor_and_reapply)

        log.debug("Theme with monitoring applied successfully!")

    except Exception as e:
        log.error(f"Failed to apply theme with monitoring: {e}")
        import traceback

        log.error(f"Traceback: {traceback.format_exc()}")


def apply_theme_with_patching(viewbox) -> None:
    """Apply theme with patching - alias for monitoring approach."""
    apply_theme_with_monitoring(viewbox)


def customize_pyqtgraph_selection(viewbox) -> None:
    """Customize PyQtGraph's existing rbScaleBox with system colors and transparency."""
    try:
        if not viewbox or not shiboken6.isValid(viewbox):
            return
        # Ensure cached objects exist
        pen, brush = get_cached_pen_brush()

        # Install a single class-level patch on ViewBox.updateScaleBox so the rectangle
        # always receives our pen/brush the moment it's created/updated. This avoids
        # per-instance timers and per-instance monkey-patching.
        cls = viewbox.__class__
        if cls not in _PATCHED_CLASSES:
            try:
                if not hasattr(cls, "_synaptipy_original_updateScaleBox"):
                    cls._synaptipy_original_updateScaleBox = cls.updateScaleBox

                def _patched_updateScaleBox(self, *args, **kwargs):
                    result = self._synaptipy_original_updateScaleBox(*args, **kwargs)
                    try:
                        rb = getattr(self, "rbScaleBox", None)
                        if rb is not None and shiboken6.isValid(self) and shiboken6.isValid(rb):
                            p, b = get_cached_pen_brush()
                            rb.setPen(p)
                            rb.setBrush(b)
                    except Exception:
                        pass
                    return result

                cls.updateScaleBox = _patched_updateScaleBox
                _PATCHED_CLASSES.add(cls)
                log.debug("Installed global ViewBox.updateScaleBox patch for selection styling")
            except Exception:
                pass

        # Apply immediately if already present for this instance
        try:
            rb = getattr(viewbox, "rbScaleBox", None)
            if rb is not None and shiboken6.isValid(viewbox) and shiboken6.isValid(rb):
                rb.setPen(pen)
                rb.setBrush(brush)
        except Exception:
            pass

        log.debug("Selection customization active (class patch)")

    except Exception as e:
        log.error(f"Failed to customize PyQtGraph selection: {e}")
        import traceback

        log.error(f"Traceback: {traceback.format_exc()}")


def apply_theme_with_custom_selection(viewbox) -> None:
    """Apply theme and customize PyQtGraph's selection rectangle."""
    try:
        if not viewbox:
            return

        log.debug("Applying theme with PyQtGraph customization...")

        # Apply basic theme colors to ViewBox
        apply_theme_to_viewbox(viewbox)

        # Customize PyQtGraph's existing selection rectangle
        customize_pyqtgraph_selection(viewbox)

        log.debug("Theme with PyQtGraph customization applied successfully!")

    except Exception as e:
        log.error(f"Failed to apply theme with PyQtGraph customization: {e}")
        import traceback

        log.error(f"Traceback: {traceback.format_exc()}")
