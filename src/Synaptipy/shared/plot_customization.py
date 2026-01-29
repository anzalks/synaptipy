#!/usr/bin/env python3
"""
Centralized Plot Customization for Synaptipy

This module provides a unified system for managing plot styling preferences
including colors, line widths, and transparency for different plot types.

Author: Anzal
Email: anzal.ks@gmail.com
"""

import logging
import sys
from typing import Dict, Any, Optional, Tuple
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg

from Synaptipy.shared.constants import APP_NAME

log = logging.getLogger(__name__)

# --- Performance Mode Flag ---
_force_opaque_trials = False  # Global flag


def set_force_opaque_trials(force_opaque: bool):
    """Globally enable/disable forcing opaque trial plots for performance."""
    global _force_opaque_trials
    if _force_opaque_trials == force_opaque:
        return  # Avoid unnecessary updates
    _force_opaque_trials = force_opaque
    log.debug(f"Setting force_opaque_trials globally to: {_force_opaque_trials}")
    # Trigger a preference update signal so plots refresh immediately
    manager = get_plot_customization_manager()
    manager._pen_cache.clear()  # Clear cache to force pen regeneration
    # Direct emission for immediate response
    _plot_signals.preferences_updated.emit()


def get_force_opaque_trials() -> bool:
    """Check if trial plots should be forced opaque."""
    return _force_opaque_trials


# --- End Performance Mode Flag ---


# Global signal for plot customization updates
class PlotCustomizationSignals(QtCore.QObject):
    """Global signals for plot customization updates."""

    preferences_updated = QtCore.Signal()


# Global signal instance
_plot_signals = PlotCustomizationSignals()

# Debouncing mechanism
_update_timer = None


def _debounced_emit_preferences_updated():
    """Emit preferences updated signal with debouncing to prevent rapid successive emissions."""
    global _update_timer

    try:
        if _update_timer is None:
            _update_timer = QtCore.QTimer()
            _update_timer.setSingleShot(True)
            _update_timer.timeout.connect(_plot_signals.preferences_updated.emit)

        # Reset timer - will emit signal after 100ms of no updates
        _update_timer.start(100)
        log.debug("Timer started successfully")
    except Exception as e:
        # If timer fails, emit signal immediately as fallback
        log.debug(f"Timer failed: {e}")
        log.warning(f"Debouncing failed, emitting signal immediately: {e}")
        _plot_signals.preferences_updated.emit()
        log.debug("Fallback signal emitted")


class PlotCustomizationManager:
    """
    Centralized manager for plot customization settings.

    This class manages all plotting preferences and provides methods to
    retrieve styled pens and brushes for different plot types.
    """

    def __init__(self):
        """Initialize with default plotting preferences."""
        self._settings = QtCore.QSettings(APP_NAME, "PlotCustomization")
        self._load_defaults()
        self._load_user_preferences()

        # Cache for pens to avoid recreating them every time
        self._pen_cache = {}
        self._cache_dirty = False

    def _load_defaults(self):
        """Set default plotting preferences."""
        # Import original constants to maintain backward compatibility
        try:
            from .constants import TRIAL_COLOR, AVERAGE_COLOR, TRIAL_ALPHA

            # Convert RGB tuple to hex string
            if isinstance(TRIAL_COLOR, (tuple, list)) and len(TRIAL_COLOR) >= 3:
                trial_color = f"#{TRIAL_COLOR[0]:02x}{TRIAL_COLOR[1]:02x}{TRIAL_COLOR[2]:02x}"
            else:
                trial_color = "#377eb8"  # Fallback to matplotlib blue

            if isinstance(AVERAGE_COLOR, (tuple, list)) and len(AVERAGE_COLOR) >= 3:
                average_color = f"#{AVERAGE_COLOR[0]:02x}{AVERAGE_COLOR[1]:02x}{AVERAGE_COLOR[2]:02x}"
            else:
                average_color = "#000000"  # Fallback to black

            # Convert alpha from 0-255 to 0-100 percentage
            if isinstance(TRIAL_ALPHA, (int, float)):
                trial_transparency = max(0, min(100, int((TRIAL_ALPHA / 255.0) * 100)))
            else:
                trial_transparency = 100  # Default to fully opaque

            log.debug(
                f"Loaded constants: TRIAL_COLOR={TRIAL_COLOR} -> {trial_color}, AVERAGE_COLOR={AVERAGE_COLOR} -> {average_color}, TRIAL_ALPHA={TRIAL_ALPHA} -> {trial_transparency}%"
            )
        except ImportError:
            # Fallback to hardcoded values if constants not available
            trial_color = "#377eb8"  # Matplotlib blue
            average_color = "#000000"  # Black
            trial_transparency = 100
            log.debug("Using fallback colors (constants not available)")

        # Get default pen width from constants
        try:
            from .constants import DEFAULT_PLOT_PEN_WIDTH

            default_width = DEFAULT_PLOT_PEN_WIDTH
        except ImportError:
            default_width = 1

        self.defaults = {
            "average": {
                "color": average_color,
                "width": default_width,  # Use constant (1 pixel)
                "opacity": 100,  # 100% = fully opaque (alpha 1.0)
            },
            "single_trial": {
                "color": trial_color,
                "width": default_width,  # Use constant (1 pixel)
                "opacity": trial_transparency,
            },
            "grid": {
                "enabled": True,  # Whether grid is visible
                "color": "#808080",  # Gray
                "width": default_width,  # Use constant (1 pixel)
                "opacity": 70,  # 70% = 70% opaque (alpha 0.7)
            },
        }

    def _load_user_preferences(self):
        """Load user preferences from QSettings."""
        try:
            # Check if we have old preferences that need to be cleared
            needs_reset = False

            for plot_type in self.defaults.keys():
                for property_name in self.defaults[plot_type].keys():
                    key = f"{plot_type}/{property_name}"
                    default_value = self.defaults[plot_type][property_name]

                    if property_name in ["transparency", "opacity"]:
                        value = self._settings.value(key, default_value, type=int)
                    elif property_name == "width":
                         value = self._settings.value(key, default_value, type=float)
                    elif property_name == "enabled":
                         value = self._settings.value(key, default_value, type=bool)
                    else:
                        value = self._settings.value(key, default_value)

                    # Check if this is an old preference that needs to be reset
                    if plot_type == "average" and property_name == "color" and value == "orange":
                        log.debug("Detected old orange average color preference - will reset to defaults")
                        needs_reset = True
                    elif plot_type == "single_trial" and property_name == "color" and value == "orange":
                        log.debug("Detected old orange single trial color preference - will reset to defaults")
                        needs_reset = True
                    elif plot_type == "single_trial" and property_name == "width" and value == 3:
                        log.debug("Detected old width 3 preference - will reset to defaults")
                        needs_reset = True

                    self.defaults[plot_type][property_name] = value
                    log.debug(f"Loaded preference: {plot_type}/{property_name} = {value}")

            # If we detected old preferences, reset to defaults
            if needs_reset:
                log.debug("Old preferences detected - resetting to new defaults")
                self._load_defaults()  # Reload the defaults
                # Clear the old preferences from QSettings
                for plot_type in self.defaults.keys():
                    for property_name in self.defaults[plot_type].keys():
                        key = f"{plot_type}/{property_name}"
                        self._settings.remove(key)
                # Async sync to prevent blocking
                QtCore.QTimer.singleShot(0, self._settings.sync)
                log.debug("Old preferences cleared from QSettings")

            log.debug("User plot preferences loaded successfully")
            log.debug(f"Final defaults: {self.defaults}")
        except Exception as e:
            log.warning(f"Failed to load user plot preferences: {e}")

    def save_preferences(self):
        """Save current preferences to QSettings."""
        try:
            for plot_type in self.defaults.keys():
                for property_name in self.defaults[plot_type].keys():
                    key = f"{plot_type}/{property_name}"
                    value = self.defaults[plot_type][property_name]
                    self._settings.setValue(key, value)
                    log.debug(f"Saving preference: {key} = {value}")

            # Async sync
            QtCore.QTimer.singleShot(0, self._settings.sync)
            log.debug("Plot preferences saved successfully")

            # Clear pen cache since preferences changed
            self._pen_cache.clear()
            self._cache_dirty = False  # Reset cache state
            log.debug("Cleared pen cache after preference change")

            # Emit signal to notify about preference changes (queued to keep UI responsive)
            try:
                QtCore.QTimer.singleShot(0, _plot_signals.preferences_updated.emit)
            except Exception:
                _plot_signals.preferences_updated.emit()
            log.debug("Scheduled plot preferences update signal (queued)")

        except Exception as e:
            log.error(f"Failed to save plot preferences: {e}")

    def get_average_pen(self) -> pg.mkPen:
        """Get pen for average plots."""
        # Check cache first
        cached_pen = self._get_cached_pen("average")
        if cached_pen:
            return cached_pen

        # Create new pen with proper opacity handling
        color_str = self.defaults["average"]["color"]
        try:
            width = float(self.defaults["average"]["width"])
        except (ValueError, TypeError):
            width = 1.0
        opacity = self.defaults["average"]["opacity"]

        # Convert opacity to alpha: opacity 100% = fully opaque (alpha 1.0), opacity 0% = invisible (alpha 0.0)
        alpha = opacity / 100.0

        # Convert hex color to QColor with proper alpha
        from PySide6.QtGui import QColor

        if color_str.startswith("#"):
            # Parse hex color
            r = int(color_str[1:3], 16)
            g = int(color_str[3:5], 16)
            b = int(color_str[5:7], 16)
            alpha_value = int(alpha * 255)
            color = QColor(r, g, b, alpha_value)
        else:
            # Named color
            color = QColor(color_str)
            color.setAlpha(int(alpha * 255))

        pen = pg.mkPen(color=color, width=width)
        log.debug(
            f"Created average pen: color={color}, width={width}, alpha={color.alpha()} (opacity: {opacity}%, alpha: {alpha:.3f})"
        )
        self._cache_pen("average", pen)
        return pen

    def get_single_trial_pen(self) -> pg.mkPen:
        """Get pen for single trial plots."""
        # Check cache first
        cached_pen = self._get_cached_pen("single_trial")
        if cached_pen:
            return cached_pen

        # Create new pen with proper opacity handling
        color_str = self.defaults["single_trial"]["color"]
        try:
            width = float(self.defaults["single_trial"]["width"])
        except (ValueError, TypeError):
            width = 1.0
        opacity = self.defaults["single_trial"]["opacity"]

        # Convert opacity to alpha: opacity 100% = fully opaque (alpha 1.0), opacity 0% = invisible (alpha 0.0)
        alpha = opacity / 100.0

        # PERFORMANCE: Override alpha if force opaque mode is enabled
        # global _force_opaque_trials
        if _force_opaque_trials:
            log.debug("[get_single_trial_pen] Performance mode ON: Forcing alpha to 1.0")
            alpha = 1.0

        # Convert hex color to QColor with proper alpha
        from PySide6.QtGui import QColor

        if color_str.startswith("#"):
            # Parse hex color
            r = int(color_str[1:3], 16)
            g = int(color_str[3:5], 16)
            b = int(color_str[5:7], 16)
            alpha_value = int(alpha * 255)
            color = QColor(r, g, b, alpha_value)
        else:
            # Named color
            color = QColor(color_str)
            color.setAlpha(int(alpha * 255))

        pen = pg.mkPen(color=color, width=width)
        log.debug(
            f"Created single trial pen: color={color}, width={width}, alpha={color.alpha()} (opacity: {opacity}%, alpha: {alpha:.3f}, force_opaque: {_force_opaque_trials})"
        )
        self._cache_pen("single_trial", pen)
        return pen

    def get_grid_pen(self) -> Optional[pg.mkPen]:
        """Get pen for grid lines. Returns None if grid is disabled."""
        # Check if grid is enabled
        if not self.defaults["grid"]["enabled"]:
            return None

        # Check cache first
        cached_pen = self._get_cached_pen("grid")
        if cached_pen:
            return cached_pen

        # Create new pen with proper opacity handling
        try:
            width = float(self.defaults["grid"]["width"])
        except (ValueError, TypeError):
            width = 1.0
        opacity = self.defaults["grid"]["opacity"]

        # Convert opacity to alpha: opacity 100% = fully opaque (alpha 1.0), opacity 0% = invisible (alpha 0.0)
        alpha = opacity / 100.0

        # Create color with proper alpha - always black for grid
        from PySide6.QtGui import QColor

        alpha_value = int(alpha * 255)
        color = QColor(0, 0, 0, alpha_value)  # Black with custom alpha

        pen = pg.mkPen(color=color, width=width)
        log.debug(
            f"Created grid pen: color={color}, width={width}, alpha={color.alpha()} (opacity: {opacity}%, alpha: {alpha:.3f})"
        )
        self._cache_pen("grid", pen)
        return pen

    def is_grid_enabled(self) -> bool:
        """Check if grid is currently enabled."""
        return self.defaults["grid"]["enabled"]

    def has_preferences_changed(self, new_preferences: Dict[str, Dict[str, Any]]) -> bool:
        """Check if the given preferences differ from current ones."""
        try:
            for plot_type in new_preferences:
                if plot_type not in self.defaults:
                    return True
                for property_name in new_preferences[plot_type]:
                    if property_name not in self.defaults[plot_type]:
                        return True
                    if self.defaults[plot_type][property_name] != new_preferences[plot_type][property_name]:
                        return True
            return False
        except Exception as e:
            log.warning(f"Could not check preference changes: {e}")
            return True  # Assume changed if we can't check

    def update_preferences_batch(self, new_preferences: Dict[str, Dict[str, Any]], emit_signal: bool = True):
        """Update multiple preferences at once and optionally emit signal."""
        try:
            # Check if anything actually changed
            if not self.has_preferences_changed(new_preferences):
                log.debug("No preference changes detected - skipping update")
                return False

            # Update all preferences
            for plot_type in new_preferences:
                if plot_type in self.defaults:
                    for property_name in new_preferences[plot_type]:
                        if property_name in self.defaults[plot_type]:
                            self.defaults[plot_type][property_name] = new_preferences[plot_type][property_name]

            # Clear and reset pen cache so subsequent get_* calls create and reuse fresh pens once
            try:
                self._pen_cache.clear()
            except Exception:
                pass
            self._cache_dirty = False

            # Save to QSettings for persistence
            for plot_type in self.defaults.keys():
                for property_name in self.defaults[plot_type].keys():
                    key = f"{plot_type}/{property_name}"
                    value = self.defaults[plot_type][property_name]
                    self._settings.setValue(key, value)
            # Async sync
            QtCore.QTimer.singleShot(0, self._settings.sync)

            log.debug("Updated preferences in batch, saved to QSettings, and reset pen cache")

            # Emit signal if requested (queued to allow dialogs to close first)
            if emit_signal:
                try:
                    QtCore.QTimer.singleShot(0, _plot_signals.preferences_updated.emit)
                except Exception:
                    _plot_signals.preferences_updated.emit()
                log.debug("Scheduled preferences update signal after batch update (queued)")

            return True

        except Exception as e:
            log.error(f"Failed to update preferences in batch: {e}")
            return False

    def update_preference(self, plot_type: str, property_name: str, value: Any):
        """Update a specific preference."""
        if plot_type in self.defaults and property_name in self.defaults[plot_type]:
            self.defaults[plot_type][property_name] = value
            # Mark cache as dirty when preferences change
            self._cache_dirty = True
            log.debug(f"Updated {plot_type}/{property_name} to {value}")
        else:
            log.warning(f"Invalid preference: {plot_type}/{property_name}")

    def _get_cached_pen(self, plot_type: str) -> Optional[pg.mkPen]:
        """Get a cached pen if available and cache is not dirty."""
        if not self._cache_dirty and plot_type in self._pen_cache:
            log.debug(f"Cache HIT for {plot_type} pen")
            return self._pen_cache[plot_type]
        log.debug(
            f"Cache MISS for {plot_type} pen (dirty: {self._cache_dirty}, exists: {plot_type in self._pen_cache})"
        )
        return None

    def _cache_pen(self, plot_type: str, pen: pg.mkPen):
        """Cache a pen for future use."""
        self._pen_cache[plot_type] = pen

    def get_all_preferences(self) -> Dict[str, Dict[str, Any]]:
        """Get all current preferences."""
        return self.defaults.copy()

    def reset_to_defaults(self):
        """Reset all preferences to default values."""
        self._load_defaults()
        # Clear any saved preferences in QSettings
        try:
            for plot_type in self.defaults.keys():
                for property_name in self.defaults[plot_type].keys():
                    key = f"{plot_type}/{property_name}"
                    self._settings.remove(key)
            # Async sync
            QtCore.QTimer.singleShot(0, self._settings.sync)
            log.debug("Cleared saved preferences from QSettings")
        except Exception as e:
            log.warning(f"Failed to clear saved preferences: {e}")

        # Clear pen cache and mark as dirty
        self._pen_cache.clear()
        self._cache_dirty = True
        log.debug("Plot preferences reset to defaults")
        
        # Emit signal to notify about preference changes (queued to keep UI responsive)
        try:
            QtCore.QTimer.singleShot(0, _plot_signals.preferences_updated.emit)
        except Exception:
            _plot_signals.preferences_updated.emit()
        log.debug("Scheduled preferences update signal after reset (queued)")

    def update_grid_visibility(self, plot_widgets: list):
        """Update grid visibility for a list of plot widgets."""
        try:
            if not plot_widgets:
                return

            is_enabled = self.defaults["grid"]["enabled"]
            grid_pen = self.get_grid_pen() if is_enabled else None

            for plot_widget in plot_widgets:
                try:
                    if hasattr(plot_widget, "showGrid"):
                        if is_enabled and grid_pen:
                            # Get alpha value from pen color
                            alpha = 0.3  # Default alpha
                            if hasattr(grid_pen, "color") and hasattr(grid_pen.color(), "alpha"):
                                alpha = grid_pen.color().alpha() / 255.0
                                log.debug(f"Using grid pen alpha: {alpha} (opacity: {alpha * 100:.1f}%)")
                            else:
                                log.debug("Using default grid alpha: 0.3")

                            plot_widget.showGrid(x=True, y=True, alpha=alpha)
                        else:
                            plot_widget.showGrid(x=False, y=False)

                    # Also try to update PlotItem if available
                    if hasattr(plot_widget, "getPlotItem"):
                        plot_item = plot_widget.getPlotItem()
                        if plot_item and hasattr(plot_item, "showGrid"):
                            if is_enabled and grid_pen:
                                # Get alpha value from pen color
                                alpha = 0.3  # Default alpha
                                if hasattr(grid_pen, "color") and hasattr(grid_pen.color(), "alpha"):
                                    alpha = grid_pen.color().alpha() / 255.0
                                    log.debug(f"Using grid pen alpha: {alpha} (opacity: {alpha * 100:.1f}%)")
                                else:
                                    log.debug("Using default grid alpha: 0.3")

                                plot_item.showGrid(x=True, y=True, alpha=alpha)
                            else:
                                plot_item.showGrid(x=False, y=False)

                except Exception as e:
                    log.debug(f"Could not update grid for plot widget: {e}")
                    continue

            log.debug(f"Updated grid visibility for {len(plot_widgets)} plot widgets (enabled: {is_enabled})")

        except Exception as e:
            log.warning(f"Failed to update grid visibility: {e}")

    def update_plot_pens(self, plot_widgets: list):
        """Update plot pens for existing plots when preferences change."""
        try:
            if not plot_widgets:
                return

            # Get current pens
            average_pen = self.get_average_pen()
            single_trial_pen = self.get_single_trial_pen()

            for plot_widget in plot_widgets:
                try:
                    # Update plot items in the widget
                    if hasattr(plot_widget, "plotItem") and plot_widget.plotItem():
                        plot_item = plot_widget.plotItem()
                        self._update_plot_item_pens(plot_item, average_pen, single_trial_pen)

                    # Also try to update PlotItem if available
                    if hasattr(plot_widget, "getPlotItem"):
                        plot_item = plot_widget.getPlotItem()
                        if plot_item:
                            self._update_plot_item_pens(plot_item, average_pen, single_trial_pen)

                except Exception as e:
                    log.debug(f"Could not update pens for plot widget: {e}")
                    continue

            log.debug(f"Updated plot pens for {len(plot_widgets)} plot widgets")

        except Exception as e:
            log.warning(f"Failed to update plot pens: {e}")

    def _update_plot_item_pens(self, plot_item, average_pen, single_trial_pen):
        """Update pens for all items in a plot item."""
        try:
            if not plot_item or not hasattr(plot_item, "items"):
                return

            for item in plot_item.items:
                if hasattr(item, "setPen") and hasattr(item, "opts"):
                    # Try to determine item type from name or other properties
                    item_name = item.opts.get("name", "").lower()
                    if "average" in item_name or "avg" in item_name:
                        item.setPen(average_pen)
                        log.debug(f"Updated average pen for item: {item_name}")
                    else:
                        # Default to single trial pen
                        item.setPen(single_trial_pen)
                        log.debug(f"Updated single trial pen for item: {item_name}")

        except Exception as e:
            log.debug(f"Could not update plot item pens: {e}")


# Global instance for application-wide access
_plot_customization_manager = None


def get_plot_customization_manager() -> PlotCustomizationManager:
    """Get the global plot customization manager instance."""
    global _plot_customization_manager
    if _plot_customization_manager is None:
        _plot_customization_manager = PlotCustomizationManager()
    return _plot_customization_manager


# Convenience functions for easy access
def get_average_pen() -> pg.mkPen:
    """Get pen for average plots."""
    return get_plot_customization_manager().get_average_pen()


def get_single_trial_pen() -> pg.mkPen:
    """Get pen for single trial plots."""
    return get_plot_customization_manager().get_single_trial_pen()


def get_grid_pen() -> pg.mkPen:
    """Get pen for grid lines."""
    return get_plot_customization_manager().get_grid_pen()


def is_grid_enabled() -> bool:
    """Check if grid is currently enabled."""
    return get_plot_customization_manager().is_grid_enabled()


def update_grid_visibility(plot_widgets: list):
    """Update grid visibility for a list of plot widgets."""
    get_plot_customization_manager().update_grid_visibility(plot_widgets)


def update_plot_pens(plot_widgets: list):
    """Update plot pens for existing plots when preferences change."""
    get_plot_customization_manager().update_plot_pens(plot_widgets)


def update_plot_preference(plot_type: str, property_name: str, value: Any):
    """Update a plot preference."""
    get_plot_customization_manager().update_preference(plot_type, property_name, value)


def save_plot_preferences():
    """Save all plot preferences."""
    get_plot_customization_manager().save_preferences()


def get_plot_customization_signals():
    """Get the global plot customization signals."""
    return _plot_signals


def get_plot_pens(is_average: bool, trial_index: int = 0) -> pg.Qt.QtGui.QPen:
    """
    Creates a QPen object based on the current customization settings.

    Args:
        is_average: True if the pen is for an averaged trace, False otherwise.
        trial_index: The index of the trial (used for potential future color cycling).

    Returns:
        A configured QPen object.
    """
    from PySide6.QtGui import QColor

    manager = get_plot_customization_manager()
    prefs = manager.get_all_preferences()

    if is_average:
        config = prefs.get("average", {})
        color_str = config.get("color", "#FF0000")  # Default red
        width = config.get("width", 2)
        opacity = config.get("opacity", 100)
    else:
        config = prefs.get("single_trial", {})
        color_str = config.get("color", "#808080")  # Default gray
        width = config.get("width", 1)
        opacity = config.get("opacity", 50)

    color = QColor(color_str)
    color.setAlphaF(opacity / 100.0)

    pen = pg.mkPen(color=color, width=width)
    return pen
