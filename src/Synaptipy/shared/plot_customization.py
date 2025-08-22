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

log = logging.getLogger('Synaptipy.shared.plot_customization')

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
        print("DEBUG: Timer started successfully")
    except Exception as e:
        # If timer fails, emit signal immediately as fallback
        print(f"DEBUG: Timer failed: {e}")
        log.warning(f"Debouncing failed, emitting signal immediately: {e}")
        _plot_signals.preferences_updated.emit()
        print("DEBUG: Fallback signal emitted")

class PlotCustomizationManager:
    """
    Centralized manager for plot customization settings.

    This class manages all plotting preferences and provides methods to
    retrieve styled pens and brushes for different plot types.
    """

    def __init__(self):
        """Initialize with default plotting preferences."""
        self._settings = QtCore.QSettings("Synaptipy", "PlotCustomization")
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
                
            log.debug(f"Loaded constants: TRIAL_COLOR={TRIAL_COLOR} -> {trial_color}, AVERAGE_COLOR={AVERAGE_COLOR} -> {average_color}, TRIAL_ALPHA={TRIAL_ALPHA} -> {trial_transparency}%")
        except ImportError:
            # Fallback to hardcoded values if constants not available
            trial_color = "#377eb8"  # Matplotlib blue
            average_color = "#000000"  # Black
            trial_transparency = 100
            log.debug("Using fallback colors (constants not available)")
        
        self.defaults = {
            'average': {
                'color': average_color,
                'width': 2,
                'transparency': 100  # 100% = fully opaque
            },
            'single_trial': {
                'color': trial_color,
                'width': 1,
                'transparency': trial_transparency
            },
            'grid': {
                'color': '#808080',  # Gray
                'width': 1,
                'transparency': 30  # 30% = 70% transparent
            }
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
                    
                    if property_name == 'transparency':
                        value = self._settings.value(key, default_value, type=int)
                    else:
                        value = self._settings.value(key, default_value)
                    
                    # Check if this is an old preference that needs to be reset
                    if plot_type == 'average' and property_name == 'color' and value == 'orange':
                        log.info("Detected old orange average color preference - will reset to defaults")
                        needs_reset = True
                    elif plot_type == 'single_trial' and property_name == 'color' and value == 'orange':
                        log.info("Detected old orange single trial color preference - will reset to defaults")
                        needs_reset = True
                    elif plot_type == 'single_trial' and property_name == 'width' and value == 3:
                        log.info("Detected old width 3 preference - will reset to defaults")
                        needs_reset = True
                    
                    self.defaults[plot_type][property_name] = value
                    log.debug(f"Loaded preference: {plot_type}/{property_name} = {value}")
            
            # If we detected old preferences, reset to defaults
            if needs_reset:
                log.info("Old preferences detected - resetting to new defaults")
                self._load_defaults()  # Reload the defaults
                # Clear the old preferences from QSettings
                for plot_type in self.defaults.keys():
                    for property_name in self.defaults[plot_type].keys():
                        key = f"{plot_type}/{property_name}"
                        self._settings.remove(key)
                self._settings.sync()
                log.info("Old preferences cleared from QSettings")
                    
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
            
            self._settings.sync()
            log.debug("Plot preferences saved successfully")
            
            # Clear pen cache since preferences changed
            self._pen_cache.clear()
            self._cache_dirty = False  # Reset cache state
            log.debug("Cleared pen cache after preference change")
            
            # Emit signal to notify about preference changes
            _plot_signals.preferences_updated.emit()
            log.debug("Emitted plot preferences update signal")
            
        except Exception as e:
            log.error(f"Failed to save plot preferences: {e}")
    
    def get_average_pen(self) -> pg.mkPen:
        """Get pen for average plots."""
        # Check cache first
        cached_pen = self._get_cached_pen('average')
        if cached_pen:
            return cached_pen
        
        # Create new pen
        color = self.defaults['average']['color']
        width = self.defaults['average']['width']
        alpha = self.defaults['average']['transparency']

        pen = pg.mkPen(color=color, width=width, alpha=alpha/100.0)
        log.debug(f"Created average pen: color={color}, width={width}, alpha={alpha/100.0}")
        self._cache_pen('average', pen)
        return pen

    def get_single_trial_pen(self) -> pg.mkPen:
        """Get pen for single trial plots."""
        # Check cache first
        cached_pen = self._get_cached_pen('single_trial')
        if cached_pen:
            return cached_pen
        
        # Create new pen
        color = self.defaults['single_trial']['color']
        width = self.defaults['single_trial']['width']
        alpha = self.defaults['single_trial']['transparency']

        pen = pg.mkPen(color=color, width=width, alpha=alpha/100.0)
        log.debug(f"Created single trial pen: color={color}, width={width}, alpha={alpha/100.0}")
        self._cache_pen('single_trial', pen)
        return pen

    def get_grid_pen(self) -> pg.mkPen:
        """Get pen for grid lines."""
        # Check cache first
        cached_pen = self._get_cached_pen('grid')
        if cached_pen:
            return cached_pen
        
        # Create new pen
        color = self.defaults['grid']['color']
        width = self.defaults['grid']['width']
        alpha = self.defaults['grid']['transparency']

        pen = pg.mkPen(color=color, width=width, alpha=alpha/100.0)
        log.debug(f"Created grid pen: color={color}, width={width}, alpha={alpha/100.0}")
        self._cache_pen('grid', pen)
        return pen
    
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
            
            # Mark cache as dirty
            self._cache_dirty = True
            log.debug("Updated preferences in batch")
            
            # Emit signal if requested
            if emit_signal:
                _plot_signals.preferences_updated.emit()
                log.debug("Emitted preferences update signal after batch update")
            
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
        log.debug(f"Cache MISS for {plot_type} pen (dirty: {self._cache_dirty}, exists: {plot_type in self._pen_cache})")
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
            self._settings.sync()
            log.debug("Cleared saved preferences from QSettings")
        except Exception as e:
            log.warning(f"Failed to clear saved preferences: {e}")
        
        # Clear pen cache and mark as dirty
        self._pen_cache.clear()
        self._cache_dirty = True
        log.info("Plot preferences reset to defaults")

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

def update_plot_preference(plot_type: str, property_name: str, value: Any):
    """Update a plot preference."""
    get_plot_customization_manager().update_preference(plot_type, property_name, value)

def save_plot_preferences():
    """Save all plot preferences."""
    get_plot_customization_manager().save_preferences()

def get_plot_customization_signals():
    """Get the global plot customization signals."""
    return _plot_signals
