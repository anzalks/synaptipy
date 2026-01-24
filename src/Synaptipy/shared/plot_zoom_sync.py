#!/usr/bin/env python3
"""
Centralized plot zoom and scrollbar synchronization for Synaptipy.

This module provides a consistent way to synchronize zoom controls, scrollbars,
and manual limit inputs across all plot widgets in the application.
"""

import logging
from typing import Optional, Tuple, Dict, Any, Callable
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg

log = logging.getLogger(__name__)


class PlotZoomSyncManager(QtCore.QObject):
    """
    Manages synchronization between plot view changes, scrollbars, zoom sliders,
    and manual limit inputs. Provides a centralized solution for both explorer
    and analysis tabs.
    """
    
    # Constants from explorer tab
    SCROLLBAR_MAX_RANGE = 10000
    SLIDER_RANGE_MIN = 1
    SLIDER_RANGE_MAX = 100
    MIN_ZOOM_FACTOR = 0.01
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Control references
        self.x_scrollbar: Optional[QtWidgets.QScrollBar] = None
        self.y_scrollbar: Optional[QtWidgets.QScrollBar] = None
        self.x_zoom_slider: Optional[QtWidgets.QSlider] = None
        self.y_zoom_slider: Optional[QtWidgets.QSlider] = None
        self.x_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.x_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.y_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.y_max_edit: Optional[QtWidgets.QLineEdit] = None
        
        # Plot references
        self.plot_widget: Optional[pg.PlotWidget] = None
        self.view_box: Optional[pg.ViewBox] = None
        
        # State variables
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_y_range: Optional[Tuple[float, float]] = None
        self.manual_limits_enabled: bool = False
        self.manual_x_range: Optional[Tuple[float, float]] = None
        self.manual_y_range: Optional[Tuple[float, float]] = None
        
        # Update flags to prevent recursion
        self._updating_scrollbars: bool = False
        self._updating_viewranges: bool = False
        self._updating_limit_fields: bool = False
        
        # Optional callbacks for custom behavior
        self.on_range_changed: Optional[Callable] = None
        
    def setup_plot_widget(self, plot_widget: pg.PlotWidget):
        """Setup plot widget with zoom synchronization."""
        self.plot_widget = plot_widget
        self.view_box = plot_widget.getViewBox()
        
        if self.view_box:
            # Connect viewbox signals to our handlers
            self.view_box.sigXRangeChanged.connect(self._on_x_range_changed)
            self.view_box.sigYRangeChanged.connect(self._on_y_range_changed)
            
            # Enable rectangle zoom mode
            self.view_box.setMouseMode(pg.ViewBox.RectMode)
            
    def setup_controls(self, 
                      x_scrollbar: QtWidgets.QScrollBar = None,
                      y_scrollbar: QtWidgets.QScrollBar = None,
                      x_zoom_slider: QtWidgets.QSlider = None,
                      y_zoom_slider: QtWidgets.QSlider = None,
                      x_min_edit: QtWidgets.QLineEdit = None,
                      x_max_edit: QtWidgets.QLineEdit = None,
                      y_min_edit: QtWidgets.QLineEdit = None,
                      y_max_edit: QtWidgets.QLineEdit = None):
        """Setup control widgets and connect their signals."""
        
        # Store references
        self.x_scrollbar = x_scrollbar
        self.y_scrollbar = y_scrollbar
        self.x_zoom_slider = x_zoom_slider
        self.y_zoom_slider = y_zoom_slider
        self.x_min_edit = x_min_edit
        self.x_max_edit = x_max_edit
        self.y_min_edit = y_min_edit
        self.y_max_edit = y_max_edit
        
        # Connect scrollbar signals
        if self.x_scrollbar:
            self.x_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
            self.x_scrollbar.valueChanged.connect(self._on_x_scrollbar_changed)
            
        if self.y_scrollbar:
            self.y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
            self.y_scrollbar.valueChanged.connect(self._on_y_scrollbar_changed)
            
        # Connect zoom slider signals
        if self.x_zoom_slider:
            self.x_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
            self.x_zoom_slider.setValue(self.SLIDER_RANGE_MIN)
            self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
            
        if self.y_zoom_slider:
            self.y_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
            self.y_zoom_slider.setValue(self.SLIDER_RANGE_MIN)
            self.y_zoom_slider.valueChanged.connect(self._on_y_zoom_changed)
            
        # Connect manual input signals
        if self.x_min_edit:
            self.x_min_edit.editingFinished.connect(self._on_manual_limits_changed)
        if self.x_max_edit:
            self.x_max_edit.editingFinished.connect(self._on_manual_limits_changed)
        if self.y_min_edit:
            self.y_min_edit.editingFinished.connect(self._on_manual_limits_changed)
        if self.y_max_edit:
            self.y_max_edit.editingFinished.connect(self._on_manual_limits_changed)
    
    def set_base_ranges(self, x_range: Tuple[float, float], y_range: Tuple[float, float]):
        """Set the base data ranges for zoom/scroll calculations."""
        self.base_x_range = x_range
        self.base_y_range = y_range
        
        # Reset zoom sliders to minimum (full view)
        if self.x_zoom_slider:
            self.x_zoom_slider.setValue(self.SLIDER_RANGE_MIN)
        if self.y_zoom_slider:
            self.y_zoom_slider.setValue(self.SLIDER_RANGE_MIN)
            
        # Reset scrollbars to center
        if self.x_scrollbar:
            self._reset_scrollbar(self.x_scrollbar)
        if self.y_scrollbar:
            self._reset_scrollbar(self.y_scrollbar)
            
        # Update limit fields
        self._update_limit_fields()
    
    def enable_manual_limits(self, enabled: bool):
        """Enable or disable manual limit mode."""
        self.manual_limits_enabled = enabled
        
        # Enable/disable controls
        controls = [self.x_zoom_slider, self.y_zoom_slider]
        for control in controls:
            if control:
                control.setEnabled(not enabled)
                
        # Reset scrollbars if manual limits enabled
        if enabled:
            if self.x_scrollbar:
                self._reset_scrollbar(self.x_scrollbar)
            if self.y_scrollbar:
                self._reset_scrollbar(self.y_scrollbar)
                
        # Disable mouse interaction if manual limits enabled
        if self.view_box:
            self.view_box.setMouseEnabled(x=not enabled, y=not enabled)
    
    def apply_manual_limits(self):
        """Apply manual limits from input fields to the plot."""
        if not self.manual_limits_enabled or not self.view_box:
            return
            
        try:
            # Parse X limits
            x_min = None
            x_max = None
            if self.x_min_edit and self.x_min_edit.text().strip():
                x_min = float(self.x_min_edit.text())
            if self.x_max_edit and self.x_max_edit.text().strip():
                x_max = float(self.x_max_edit.text())
                
            if x_min is not None and x_max is not None:
                self.manual_x_range = (x_min, x_max)
                self.view_box.setXRange(x_min, x_max, padding=0)
                
            # Parse Y limits
            y_min = None
            y_max = None
            if self.y_min_edit and self.y_min_edit.text().strip():
                y_min = float(self.y_min_edit.text())
            if self.y_max_edit and self.y_max_edit.text().strip():
                y_max = float(self.y_max_edit.text())
                
            if y_min is not None and y_max is not None:
                self.manual_y_range = (y_min, y_max)
                self.view_box.setYRange(y_min, y_max, padding=0)
                
        except ValueError as e:
            log.warning(f"Invalid manual limit values: {e}")
    
    def auto_range(self):
        """Auto-range the plot to fit all data."""
        if self.view_box:
            self.view_box.autoRange()
            log.debug("Plot auto-ranged")
    
    def is_zoom_available(self) -> bool:
        """Check if zoom controls are available and functional."""
        return (self.plot_widget is not None and 
                self.view_box is not None and 
                self.base_x_range is not None)
    
    def is_scroll_available(self) -> bool:
        """Check if scroll controls are available and functional."""
        return (self.is_zoom_available() and
                (self.x_scrollbar is not None or self.y_scrollbar is not None))
    
    def get_current_zoom_levels(self) -> Dict[str, float]:
        """Get current zoom levels as a percentage of base range."""
        if not self.is_zoom_available():
            return {"x": 100.0, "y": 100.0}
            
        try:
            current_ranges = self.view_box.viewRange()
            x_range, y_range = current_ranges
            
            x_zoom = 100.0
            if self.base_x_range:
                base_x_span = abs(self.base_x_range[1] - self.base_x_range[0])
                current_x_span = abs(x_range[1] - x_range[0])
                if base_x_span > 0:
                    x_zoom = (current_x_span / base_x_span) * 100.0
            
            y_zoom = 100.0
            if self.base_y_range:
                base_y_span = abs(self.base_y_range[1] - self.base_y_range[0])
                current_y_span = abs(y_range[1] - y_range[0])
                if base_y_span > 0:
                    y_zoom = (current_y_span / base_y_span) * 100.0
                    
            return {"x": x_zoom, "y": y_zoom}
            
        except Exception as e:
            log.error(f"Error getting zoom levels: {e}")
            return {"x": 100.0, "y": 100.0}
    
    def set_zoom_level(self, axis: str, zoom_percent: float):
        """Set zoom level for specific axis (for future programmatic control)."""
        if not self.is_zoom_available():
            return
            
        try:
            if axis.lower() == 'x' and self.base_x_range:
                base_span = abs(self.base_x_range[1] - self.base_x_range[0])
                center = (self.base_x_range[0] + self.base_x_range[1]) / 2.0
                new_span = base_span * (zoom_percent / 100.0)
                new_range = (center - new_span/2.0, center + new_span/2.0)
                
                self._updating_viewranges = True
                self.view_box.setXRange(new_range[0], new_range[1], padding=0)
                self._updating_viewranges = False
                
            elif axis.lower() == 'y' and self.base_y_range:
                base_span = abs(self.base_y_range[1] - self.base_y_range[0])
                center = (self.base_y_range[0] + self.base_y_range[1]) / 2.0
                new_span = base_span * (zoom_percent / 100.0)
                new_range = (center - new_span/2.0, center + new_span/2.0)
                
                self._updating_viewranges = True
                self.view_box.setYRange(new_range[0], new_range[1], padding=0)
                self._updating_viewranges = False
                
        except Exception as e:
            log.error(f"Error setting zoom level: {e}")
    
    # ===========================================================================
    # Signal Handlers
    # ===========================================================================
    
    def _on_x_range_changed(self, view_box, x_range):
        """Handle X range changes from plot interactions (rectangle zoom, etc.)"""
        if self._updating_viewranges:
            return
            
        log.debug(f"X range changed to: {x_range}")
        
        # Update scrollbar to reflect new range - this should work even during view updates
        if not self.manual_limits_enabled and self.base_x_range and self.x_scrollbar:
            self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, x_range)
            
        # Update limit fields
        self._update_limit_fields()
        
        # Trigger callback if provided
        if self.on_range_changed:
            self.on_range_changed('x', x_range)
    
    def _on_y_range_changed(self, view_box, y_range):
        """Handle Y range changes from plot interactions (rectangle zoom, etc.)"""
        if self._updating_viewranges:
            return
            
        log.debug(f"Y range changed to: {y_range}")
        
        # Update scrollbar to reflect new range - this should work even during view updates
        if not self.manual_limits_enabled and self.base_y_range and self.y_scrollbar:
            self._update_scrollbar_from_view(self.y_scrollbar, self.base_y_range, y_range)
            
        # Update limit fields
        self._update_limit_fields()
        
        # Trigger callback if provided
        if self.on_range_changed:
            self.on_range_changed('y', y_range)
    
    def _on_x_scrollbar_changed(self, value: int):
        """Handle X scrollbar changes."""
        if self.manual_limits_enabled or not self.view_box or not self.base_x_range or self._updating_scrollbars:
            return
            
        self._updating_viewranges = True
        try:
            # Get current view range
            current_x_range = self.view_box.viewRange()[0]
            current_span = max(abs(current_x_range[1] - current_x_range[0]), 1e-12)
            base_span = max(abs(self.base_x_range[1] - self.base_x_range[0]), 1e-12)
            
            # Calculate scrollable range
            scrollable_range = max(0, base_span - current_span)
            scroll_fraction = float(value) / max(1, self.x_scrollbar.maximum())
            
            # Calculate new range
            new_min_x = self.base_x_range[0] + scroll_fraction * scrollable_range
            new_max_x = new_min_x + current_span
            
            self.view_box.setXRange(new_min_x, new_max_x, padding=0)
            
        except Exception as e:
            log.error(f"Error in X scrollbar handler: {e}")
        finally:
            self._updating_viewranges = False
    
    def _on_y_scrollbar_changed(self, value: int):
        """Handle Y scrollbar changes."""
        if self.manual_limits_enabled or not self.view_box or not self.base_y_range or self._updating_scrollbars:
            return
            
        self._updating_viewranges = True
        try:
            # Get current view range
            current_y_range = self.view_box.viewRange()[1]
            current_span = max(abs(current_y_range[1] - current_y_range[0]), 1e-12)
            base_span = max(abs(self.base_y_range[1] - self.base_y_range[0]), 1e-12)
            
            # Calculate scrollable range
            scrollable_range = max(0, base_span - current_span)
            scroll_fraction = float(value) / max(1, self.y_scrollbar.maximum())
            
            # Calculate new range
            new_min_y = self.base_y_range[0] + scroll_fraction * scrollable_range
            new_max_y = new_min_y + current_span
            
            self.view_box.setYRange(new_min_y, new_max_y, padding=0)
            
        except Exception as e:
            log.error(f"Error in Y scrollbar handler: {e}")
        finally:
            self._updating_viewranges = False
    
    def _on_x_zoom_changed(self, value: int):
        """Handle X zoom slider changes."""
        if self.manual_limits_enabled or not self.view_box or not self.base_x_range:
            return
            
        log.debug(f"X zoom slider changed to: {value}")
        
        new_x_range = self._calculate_new_range(self.base_x_range, value)
        if new_x_range:
            self._updating_viewranges = True
            try:
                self.view_box.setXRange(new_x_range[0], new_x_range[1], padding=0)
                # Update scrollbar position to match new zoom level
                if self.x_scrollbar:
                    self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_x_range)
            finally:
                self._updating_viewranges = False
    
    def _on_y_zoom_changed(self, value: int):
        """Handle Y zoom slider changes."""
        if self.manual_limits_enabled or not self.view_box or not self.base_y_range:
            return
            
        log.debug(f"Y zoom slider changed to: {value}")
        
        new_y_range = self._calculate_new_range(self.base_y_range, value)
        if new_y_range:
            self._updating_viewranges = True
            try:
                self.view_box.setYRange(new_y_range[0], new_y_range[1], padding=0)
                # Update scrollbar position to match new zoom level
                if self.y_scrollbar:
                    self._update_scrollbar_from_view(self.y_scrollbar, self.base_y_range, new_y_range)
            finally:
                self._updating_viewranges = False
    
    def _on_manual_limits_changed(self):
        """Handle manual limit input changes."""
        if self.manual_limits_enabled:
            self.apply_manual_limits()
    
    # ===========================================================================
    # Helper Methods
    # ===========================================================================
    
    def _calculate_new_range(self, base_range: Tuple[float, float], slider_value: int) -> Optional[Tuple[float, float]]:
        """Calculate new range based on zoom slider value."""
        try:
            m, M = base_range
            center = (m + M) / 2.0
            span = max(abs(M - m), 1e-12)
            
            # Normalize slider value to 0.0-1.0
            normalized_zoom = (float(slider_value) - self.SLIDER_RANGE_MIN) / (self.SLIDER_RANGE_MAX - self.SLIDER_RANGE_MIN)
            
            # Calculate zoom factor (1.0 = full view, MIN_ZOOM_FACTOR = most zoomed in)
            zoom_factor = max(self.MIN_ZOOM_FACTOR, 1.0 - normalized_zoom * (1.0 - self.MIN_ZOOM_FACTOR))
            
            # Calculate new range
            new_span = span * zoom_factor
            new_min = center - new_span / 2.0
            new_max = center + new_span / 2.0
            
            return (new_min, new_max)
            
        except Exception as e:
            log.error(f"Error calculating new range: {e}")
            return None
    
    def _update_scrollbar_from_view(self, scrollbar: QtWidgets.QScrollBar, base_range: Tuple[float, float], view_range: Tuple[float, float]):
        """Update scrollbar position and range based on current view."""
        if not scrollbar or self._updating_scrollbars or self.manual_limits_enabled:
            return
            
        self._updating_scrollbars = True
        try:
            base_min, base_max = base_range
            view_min, view_max = view_range
            
            base_span = max(abs(base_max - base_min), 1e-12)
            view_span = min(max(abs(view_max - view_min), 1e-12), base_span)
            
            # Calculate page step (proportional to view span)
            page_step = max(1, min(int((view_span / base_span) * self.SCROLLBAR_MAX_RANGE), self.SCROLLBAR_MAX_RANGE))
            
            # Calculate scrollbar range
            scrollbar_range = max(0, self.SCROLLBAR_MAX_RANGE - page_step)
            
            # Calculate current position
            range_pos = view_min - base_min
            scrollable_distance = max(abs(base_span - view_span), 1e-12)
            value = 0
            if scrollable_distance > 1e-10:
                value = max(0, min(int((range_pos / scrollable_distance) * scrollbar_range), scrollbar_range))
            
            # Update scrollbar
            scrollbar.blockSignals(True)
            scrollbar.setRange(0, scrollbar_range)
            scrollbar.setPageStep(page_step)
            scrollbar.setValue(value)
            scrollbar.setEnabled(scrollbar_range > 0)
            scrollbar.blockSignals(False)
            
        except Exception as e:
            log.error(f"Error updating scrollbar: {e}")
            self._reset_scrollbar(scrollbar)
        finally:
            self._updating_scrollbars = False
    
    def _reset_scrollbar(self, scrollbar: QtWidgets.QScrollBar):
        """Reset scrollbar to default state."""
        if not scrollbar:
            return
            
        scrollbar.blockSignals(True)
        try:
            scrollbar.setRange(0, 0)
            scrollbar.setPageStep(self.SCROLLBAR_MAX_RANGE)
            scrollbar.setValue(0)
            scrollbar.setEnabled(False)
        finally:
            scrollbar.blockSignals(False)
    
    def _update_limit_fields(self):
        """Update manual limit input fields to show current view ranges."""
        if self._updating_limit_fields or not self.view_box:
            return
            
        self._updating_limit_fields = True
        try:
            # Get current ranges
            x_range, y_range = self.view_box.viewRange()
            
            # Update X limit fields
            if self.x_min_edit and not self.manual_limits_enabled:
                self.x_min_edit.setText(f"{x_range[0]:.4g}")
            if self.x_max_edit and not self.manual_limits_enabled:
                self.x_max_edit.setText(f"{x_range[1]:.4g}")
                
            # Update Y limit fields
            if self.y_min_edit and not self.manual_limits_enabled:
                self.y_min_edit.setText(f"{y_range[0]:.4g}")
            if self.y_max_edit and not self.manual_limits_enabled:
                self.y_max_edit.setText(f"{y_range[1]:.4g}")
                
        except Exception as e:
            log.error(f"Error updating limit fields: {e}")
        finally:
            self._updating_limit_fields = False 