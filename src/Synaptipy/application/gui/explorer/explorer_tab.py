# src/Synaptipy/application/gui/explorer/explorer_tab.py
# -*- coding: utf-8 -*-
"""
Explorer Tab widget for the Synaptipy GUI.
Refactored modular version.
"""
import logging
import os
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set, Union
from functools import partial

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

# --- Synaptipy Imports ---
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from Synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION, Z_ORDER
from Synaptipy.application.session_manager import SessionManager
from Synaptipy.application.gui.analysis_worker import AnalysisWorker
from Synaptipy.application.gui.nwb_dialog import NwbMetadataDialog

# --- Components ---
from .sidebar import ExplorerSidebar
from .config_panel import ExplorerConfigPanel
from .plot_canvas import ExplorerPlotCanvas
from .y_controls import ExplorerYControls
from .toolbar import ExplorerToolbar

# Configure Logger
log = logging.getLogger(__name__)

class ExplorerTab(QtWidgets.QWidget):
    """
    Main controller for the Data Explorer tab.
    Coordinatse sub-components: Sidebar, PlotCanvas, Controls, Toolbar, ConfigPanel.
    """
    open_file_requested = QtCore.Signal() # Check if still needed

    # Constants
    class PlotMode:
        OVERLAY_AVG = 0
        CYCLE_SINGLE = 1

    def __init__(self, neo_adapter: NeoAdapter, nwb_exporter: NWBExporter, status_bar: QtWidgets.QStatusBar, parent=None):
        super().__init__(parent)
        
        # Dependencies
        self.neo_adapter = neo_adapter
        self.nwb_exporter = nwb_exporter
        self.status_bar = status_bar
        
        # Thread Pool
        self.thread_pool = QtCore.QThreadPool()
        
        # Session Manager
        self.session_manager = SessionManager()
        self.session_manager.current_recording_changed.connect(self._on_recording_changed_from_session)
        self.session_manager.selected_analysis_items_changed.connect(self._on_analysis_items_changed_from_session)
        
        # Data State
        self.current_recording: Optional[Recording] = None
        self.file_list: List[Path] = []
        self.current_file_index: int = -1
        self.current_trial_index: int = 0
        self.max_trials_current_recording: int = 0
        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG
        self.selected_trial_indices: Set[int] = set()
        
        self._analysis_items: List[Dict[str, Any]] = []
        
        # Caching
        self._data_cache: Dict[str, Dict[int, Tuple[np.ndarray, np.ndarray]]] = {}
        self._average_cache: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        self._cache_dirty: bool = False
        self._is_loading: bool = False
        
        # Limits State
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_y_ranges: Dict[str, Optional[Tuple[float, float]]] = {}
        self.manual_limits_enabled: bool = False
        
        self._updating_viewranges: bool = False # Lock to prevent feedback loops
        
        # Components
        self._init_components()
        self._setup_layout()
        self._connect_signals()
        
        # Initial State
        self._update_all_ui_state()

    def _init_components(self):
        self.config_panel = ExplorerConfigPanel()
        self.plot_canvas = ExplorerPlotCanvas()
        self.toolbar = ExplorerToolbar()
        self.sidebar = ExplorerSidebar(self.neo_adapter)
        self.y_controls = ExplorerYControls()
        
        # X Scrollbar (managed here as it bridges canvas and toolbar)
        self.x_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Horizontal)
        self.x_scrollbar.setRange(0, 10000)
        self.x_scrollbar.setFixedHeight(20)
        
        # Analysis Selection Widget (Simple implementation here)
        self.analysis_group = QtWidgets.QGroupBox("Analysis Selection")
        agl = QtWidgets.QVBoxLayout(self.analysis_group)
        self.analysis_set_label = QtWidgets.QLabel("Analysis Set: 0 items")
        self.analysis_set_label.setWordWrap(True)
        agl.addWidget(self.analysis_set_label)
        
        abtn_layout = QtWidgets.QHBoxLayout()
        self.add_analysis_btn = QtWidgets.QPushButton("Add Recording to Set")
        self.add_analysis_btn.setEnabled(False)
        self.add_analysis_btn.clicked.connect(self._add_current_to_analysis_set)
        abtn_layout.addWidget(self.add_analysis_btn)
        
        self.clear_analysis_btn = QtWidgets.QPushButton("Clear Analysis Set")
        self.clear_analysis_btn.clicked.connect(self._clear_analysis_set)
        abtn_layout.addWidget(self.clear_analysis_btn)
        agl.addLayout(abtn_layout)
        
        # Open File Button
        self.open_file_btn = QtWidgets.QPushButton("Open File...")
    
    def _setup_layout(self):
        layout = QtWidgets.QHBoxLayout(self)
        
        # LEFT PANEL
        layout.addWidget(self.config_panel, 0)
        
        # CENTER PANEL
        center_widget = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center_widget)
        center_layout.addWidget(self.plot_canvas.widget, 1)
        center_layout.addWidget(self.x_scrollbar)
        center_layout.addWidget(self.toolbar)
        layout.addWidget(center_widget, 1)
        
        # RIGHT PANEL
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        
        right_layout.addWidget(self.open_file_btn)
        right_layout.addWidget(self.sidebar)
        right_layout.addWidget(self.analysis_group)
        right_layout.addWidget(self.y_controls)
        
        layout.addWidget(right_widget, 0)

    def _connect_signals(self):
        # Open File
        self.open_file_btn.clicked.connect(self.open_file_requested.emit)
        
        # Sidebar
        self.sidebar.file_selected.connect(self.load_recording_data)
        
        # Config Panel
        self.config_panel.plot_mode_changed.connect(self._on_plot_mode_changed)
        self.config_panel.downsample_toggled.connect(self._trigger_plot_update) # Just trigger redraw
        self.config_panel.select_current_trial_clicked.connect(self._toggle_select_current_trial)
        self.config_panel.clear_avg_selection_clicked.connect(self._clear_avg_selection)
        self.config_panel.show_selected_avg_toggled.connect(self._toggle_plot_selected_average)
        self.config_panel.manual_limits_toggled.connect(self._on_manual_limits_toggled)
        self.config_panel.set_manual_limits_clicked.connect(self._apply_manual_limits_from_dict)
        self.config_panel.channel_visibility_changed.connect(self._on_channel_visibility_changed)

        # Toolbar
        self.toolbar.prev_file_clicked.connect(self._prev_file_folder)
        self.toolbar.next_file_clicked.connect(self._next_file_folder)
        self.toolbar.prev_trial_clicked.connect(self._prev_trial)
        self.toolbar.next_trial_clicked.connect(self._next_trial)
        self.toolbar.reset_view_clicked.connect(self._reset_view)
        self.toolbar.save_plot_clicked.connect(self._save_plot)
        self.toolbar.x_zoom_changed.connect(self._apply_x_zoom)
        
        # X Scrollbar
        self.x_scrollbar.valueChanged.connect(self._on_x_scrollbar_changed)
        
        # Y Controls
        self.y_controls.global_zoom_changed.connect(self._apply_global_y_zoom)
        self.y_controls.global_scroll_changed.connect(self._apply_global_y_scroll)
        self.y_controls.channel_zoom_changed.connect(self._apply_channel_y_zoom)
        self.y_controls.channel_scroll_changed.connect(self._apply_channel_y_scroll)
        self.y_controls.lock_toggled.connect(self._on_y_lock_changed)
        
        # Plot Canvas
        self.plot_canvas.x_range_changed.connect(self._on_vb_x_range_changed)
        self.plot_canvas.y_range_changed.connect(self._on_vb_y_range_changed)
        
        # Analysis Buttons
        self.add_analysis_btn.clicked.connect(self._add_current_to_analysis_set)
        self.clear_analysis_btn.clicked.connect(self._clear_analysis_set)

    # --- Loading Logic ---
    
    def load_recording_data(self, filepath: Path, file_list: List[Path] = None, selected_index: int = -1):
        if self._is_loading: return
        self._is_loading = True
        
        if file_list is None: file_list = [filepath]
        if selected_index == -1: selected_index = 0
        
        self.file_list = file_list
        self.current_file_index = selected_index
        
        # Update SessionManager
        self.session_manager.set_file_context(file_list, selected_index)
        
        # Start Worker
        worker = AnalysisWorker(self.neo_adapter.read_recording, filepath)
        worker.signals.result.connect(self._on_file_load_success)
        worker.signals.error.connect(self._on_file_load_error)
        worker.signals.finished.connect(self._finalize_loading_state)
        
        self.status_bar.showMessage(f"Loading '{filepath.name}'...")
        self.thread_pool.start(worker)

    def _on_file_load_success(self, recording, filepath=None):
        self._display_recording(recording)
        # Session Manager update handled by signal? existing code suggests so.
        # But we update session manager with recording:
        self.session_manager.current_recording = recording

    def _display_recording(self, recording: Recording):
        if not recording: return
        self.current_recording = recording
        self.max_trials_current_recording = getattr(recording, 'max_trials', 0)
        
        # Reset Logic
        self._data_cache.clear(); self._average_cache.clear()
        self._cache_dirty = False
        self.current_trial_index = 0
        self.selected_trial_indices.clear()
        
        # Rebuild Components
        self.plot_canvas.rebuild_plots(recording)
        self.config_panel.rebuild(recording)
        self.y_controls.rebuild(recording)
        
        # Calculate Base Ranges
        self._calculate_base_ranges()
        
        # Initial Plot
        self._update_plot()
        self._reset_view()
        self._auto_select_trials()
        
        # Update State
        self._update_all_ui_state()
        self.sidebar.sync_to_file(recording.source_file)
        self.status_bar.showMessage(f"Displayed '{recording.source_file.name}'", 5000)

    def _calculate_base_ranges(self):
        self.base_y_ranges = {}
        self.base_x_range = (0, self.current_recording.duration) if self.current_recording.duration else (0, 1)
        
        for cid, channel in self.current_recording.channels.items():
            # Estimate Y range from random trial or global min/max
            # Simple approach: get data from trial 0
             try:
                d = channel.get_data(0)
                if d is not None:
                    mn, mx = np.min(d), np.max(d)
                    diff = mx - mn
                    if diff == 0: diff = 1.0
                    self.base_y_ranges[cid] = (mn - diff*0.1, mx + diff*0.1)
                else:
                    self.base_y_ranges[cid] = (-1, 1)
             except:
                 self.base_y_ranges[cid] = (-1, 1)

    def get_current_recording(self) -> Optional[Recording]:
        return self.current_recording

    def _trigger_plot_update(self):
        """Updates all plot items based on current selection/data state."""
        if not self.current_recording: return
        # Handle styling updates if needed (omitted for brevity)
        self._update_plot()
        if self.plot_canvas.widget:
            self.plot_canvas.widget.update()

    def _update_plot(self):
        """Standard plot update."""
        if not self.current_recording or not self.plot_canvas.channel_plots:
            return

        # Disable updates
        if self.plot_canvas.widget: self.plot_canvas.widget.setUpdatesEnabled(False)
        try:
            # Clear existing items
            for cid, items in self.plot_canvas.channel_plot_data_items.items():
                p = self.plot_canvas.channel_plots.get(cid)
                if p:
                    for item in items:
                        try: p.removeItem(item)
                        except: pass
            self.plot_canvas.channel_plot_data_items.clear()
            self.plot_canvas.selected_average_plot_items.clear()
            
            # --- PLOT SETTINGS ---
            ds_enabled = self.config_panel.downsample_cb.isChecked()
            # Force aggressive threshold if enabled (e.g. 3000 points) to prevent freezes
            ds_avg_threshold = 3000 
            ds_method = 'peak' 
            clip_view = True
            
            # Function to apply common item settings
            def _apply_item_opts(item, is_ds):
                if hasattr(item, 'setDownsampling'):
                    item.setDownsampling(auto=is_ds, method=ds_method)
                if hasattr(item, 'opts'):
                    item.opts['autoDownsample'] = is_ds
                    if is_ds: item.opts['autoDownsampleThreshold'] = ds_avg_threshold
                if hasattr(item, 'setClipToView'):
                    item.setClipToView(clip_view)

            # Get Pens
            from Synaptipy.shared.plot_customization import get_average_pen, get_single_trial_pen
            avg_pen = get_average_pen()
            current_trial_pen = get_single_trial_pen()
            
            # Iterate and plot
            for cid, channel in self.current_recording.channels.items():
                 plot_item = self.plot_canvas.channel_plots.get(cid)
                 if not plot_item or not plot_item.isVisible(): continue
                 
                 self.plot_canvas.channel_plot_data_items[cid] = []
                 
                 if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE:
                     # Plot Single Trial
                     if 0 <= self.current_trial_index < self.max_trials_current_recording:
                         try:
                             data = channel.get_data(self.current_trial_index)
                             t = channel.get_relative_time_vector(self.current_trial_index)
                             if data is not None and t is not None:
                                 item = plot_item.plot(t, data, pen=current_trial_pen, name=f"Trial {self.current_trial_index+1}")
                                 _apply_item_opts(item, ds_enabled)
                                 self.plot_canvas.channel_plot_data_items[cid].append(item)
                         except Exception as e:
                             log.error(f"Error plotting trial {self.current_trial_index} for {cid}: {e}")
                             
                 else: # OVERLAY_AVG
                     # 1. Overlay ALL trials (Background)
                     for trial_idx in range(channel.num_trials):
                          try:
                             # Skip extensive background plotting if too many trials? 
                             # For now, plot all but use subsample for speed if DS enabled
                             bg_ds_method = 'subsample' if ds_enabled else 'peak'
                             
                             data = channel.get_data(trial_idx)
                             t = channel.get_relative_time_vector(trial_idx)
                             if data is not None and t is not None:
                                 item = plot_item.plot(t, data, pen=current_trial_pen)
                                 
                                 # Apply background optimizations
                                 item.setDownsampling(auto=ds_enabled, method=bg_ds_method)
                                 item.opts['autoDownsample'] = ds_enabled
                                 if ds_enabled: item.opts['autoDownsampleThreshold'] = ds_avg_threshold
                                 item.setClipToView(clip_view)
                                 
                                 self.plot_canvas.channel_plot_data_items[cid].append(item)
                          except Exception: pass
                     
                     # 2. Plot Average on Top
                     try:
                         avg_data = channel.get_averaged_data()
                         avg_t = channel.get_relative_time_vector(0) # Use trial 0 time as Ref
                         if avg_data is not None and avg_t is not None:
                              item = plot_item.plot(avg_t, avg_data, pen=avg_pen, name="Average")
                              _apply_item_opts(item, ds_enabled)
                              item.setZValue(10) # Top
                              self.plot_canvas.channel_plot_data_items[cid].append(item)
                     except Exception as e:
                         log.error(f"Error plotting avg for {cid}: {e}")

        finally:
             if self.plot_canvas.widget: self.plot_canvas.widget.setUpdatesEnabled(True)

    def _clear_data_cache(self):
        self._data_cache.clear()
        self._average_cache.clear()
        self._cache_dirty = False
        
    def _mark_cache_dirty(self):
        self._cache_dirty = True
        
    def _remove_selected_average_plots(self):
        for cid, item in self.plot_canvas.selected_average_plot_items.items():
            try:
                self.plot_canvas.channel_plots[cid].removeItem(item)
            except: pass
        self.plot_canvas.selected_average_plot_items.clear()

    def update_plot_pens(self):
        """Update plot pens when customization preferences change."""
        if not self.current_recording or not self.plot_canvas.channel_plots:
            return
            
        try:
            from Synaptipy.shared.plot_customization import get_average_pen, get_single_trial_pen
            
            avg_pen = get_average_pen()
            trial_pen = get_single_trial_pen()
            
            # Update existing plot item pens
            for cid, items in self.plot_canvas.channel_plot_data_items.items():
                for item in items:
                    try:
                        # Check if this is an average plot (usually last item, higher Z value)
                        if hasattr(item, 'name') and item.name() == "Average":
                            item.setPen(avg_pen)
                        else:
                            item.setPen(trial_pen)
                    except Exception:
                        pass
                        
            # Force repaint
            if self.plot_canvas.widget:
                self.plot_canvas.widget.update()
                
            log.debug("Updated plot pens from customization preferences")
        except Exception as e:
            log.warning(f"Failed to update plot pens: {e}")

    # --- Interaction Logic (Zoom/Scroll) ---
    # Need to reimplement _calculate_new_range, _apply_x_zoom, etc.
    # Basically copying the logic from the snippets I read.
    
    # ...

    # --- Event Handlers ---
    def _on_recording_changed_from_session(self, recording):
        if recording and recording != self.current_recording:
             self._display_recording(recording)
             
    def _on_analysis_items_changed_from_session(self, items):
        self._analysis_items = items
        self.analysis_set_label.setText(f"Analysis Set: {len(items)} items")
        self._update_all_ui_state()

    def _on_file_load_error(self, error_info, filepath=None):
        self.status_bar.showMessage(f"Error loading file: {error_info}", 5000)
        self._is_loading = False

    def _finalize_loading_state(self):
        self._is_loading = False
    
    def _update_all_ui_state(self):
        # Delegate to subcomponents or handle locally?
        # Update Config Panel
        self.config_panel.update_selection_label(self.selected_trial_indices)
        
        # Update Toolbar
        self.toolbar.update_file_nav(self.current_file_index, len(self.file_list))
        self.toolbar.update_trial_nav(self.current_trial_index, self.max_trials_current_recording)
        self.toolbar.set_trial_nav_enabled(self.current_recording is not None and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE)
        
        # Analysis Buttons
        self.add_analysis_btn.setEnabled(self.current_recording is not None)
        self.clear_analysis_btn.setEnabled(bool(self._analysis_items))

    # --- Placeholders for remaining logic ---
    def _add_current_to_analysis_set(self):
        if not self.current_recording or not self.current_recording.source_file:
            log.warning("Cannot add recording to analysis set: No recording loaded.")
            return

        file_path = self.current_recording.source_file
        target_type = 'Recording'
        trial_index = None
        
        analysis_item = {
            'path': file_path, 
            'target_type': target_type, 
            'trial_index': trial_index,
            'recording_ref': self.current_recording
        }
        
        is_duplicate = any(item.get('path') == file_path and item.get('target_type') == target_type for item in self._analysis_items)
        if is_duplicate:
             log.debug(f"Recording already in analysis set: {file_path.name}")
             self.status_bar.showMessage(f"Recording '{file_path.name}' is already in the analysis set.", 3000)
             return
             
        self._analysis_items.append(analysis_item)
        log.debug(f"Added to analysis set: {analysis_item}")
        self.status_bar.showMessage(f"Added Recording '{file_path.name}' to the analysis set.", 3000)
        
        self._update_analysis_set_display()
        
        if self.session_manager:
             self.session_manager.selected_analysis_items = self._analysis_items[:]
             
        self._update_all_ui_state()
         
    def _clear_analysis_set(self):
        if not self._analysis_items: return
        confirm = QtWidgets.QMessageBox.question(self, "Confirm Clear", f"Clear all {len(self._analysis_items)} items from the analysis set?", QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No, QtWidgets.QMessageBox.StandardButton.No)
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            self._analysis_items = []
            log.debug("Analysis set cleared.")
            self._update_analysis_set_display()
            
            if self.session_manager:
                 self.session_manager.selected_analysis_items = []
                 
            self._update_all_ui_state()

    def _update_analysis_set_display(self):
        count = len(self._analysis_items)
        self.analysis_set_label.setText(f"Analysis Set: {count} item{'s' if count != 1 else ''}")
        if count > 0:
            tooltip_text = "Analysis Set Items:\n"
            items_to_show = 15
            for i, item in enumerate(self._analysis_items):
                if i >= items_to_show: tooltip_text += f"... ({count - items_to_show} more)"; break
                path_name = item['path'].name
                target = item['target_type']
                tooltip_text += f"- {path_name} [{target}]\n"
            self.analysis_set_label.setToolTip(tooltip_text.strip())
        else:
            self.analysis_set_label.setToolTip("Analysis set is empty.")
        
    def _prev_file_folder(self):
        if self.current_file_index > 0:
            self.load_recording_data(self.file_list[self.current_file_index - 1], self.file_list, self.current_file_index - 1)
            
    def _next_file_folder(self):
        if self.current_file_index < len(self.file_list) - 1:
            self.load_recording_data(self.file_list[self.current_file_index + 1], self.file_list, self.current_file_index + 1)

    def _prev_trial(self):
        if self.current_trial_index > 0:
            self.current_trial_index -= 1
            self._update_plot()
            self._update_all_ui_state()
            
    def _next_trial(self):
        if self.current_trial_index < self.max_trials_current_recording - 1:
            self.current_trial_index += 1
            self._update_plot()
            self._update_all_ui_state()

    def _reset_view(self):
        for cid, plot in self.plot_canvas.channel_plots.items():
            base_x = self.base_x_range
            base_y = self.base_y_ranges.get(cid)
            if base_x and base_y and plot.isVisible():
                plot.setXRange(*base_x, padding=0)
                plot.setYRange(*base_y, padding=0)
        self.x_scrollbar.setValue(0)
        self.y_controls.set_global_scrollbar(5000) # Center?
        # Reset individual scrollbars too

    # ... Implement Zoom/Scroll applying ...
    # --- Interaction Logic (Zoom/Scroll) ---

    def _calculate_visible_range(self, total_min, total_max, zoom_val, scroll_val, zoom_min=1, zoom_max=100, scroll_max=10000):
        """
        Calculates the new min/max range based on zoom slider and scrollbar values.
        Zoom: 1 (Wide) -> 100 (Narrow)
        Scroll: 0 -> 10000 (Relative position of center)
        """
        total_span = total_max - total_min
        if total_span <= 0: return total_min, total_max

        # 1. Calculate Visible Span based on Zoom
        # Map 1..100 to 1.0..0.01 (inv log scale or linear?)
        # Linear approach: 
        # zoom 1 => 100% visible
        # zoom 100 => 1% visible
        
        # Using a power scale for better feel
        # factor = 1 means 100% visible
        # factor = 0.01 means 1% visible
        # Let's map slider 1..100 -> ratio 1.0 .. 0.01
        
        # Linear mapping: ratio = 1.0 - (zoom_val - 1) / (zoom_max - 1) * 0.99
        # This gives 1->1.0, 100->0.01
        ratio = 1.0 - ((zoom_val - zoom_min) / (zoom_max - zoom_min)) * 0.99
        
        visible_span = total_span * ratio
        
        # 2. Calculate Center based on Scroll
        # scroll 0 => center at total_min + visible_span/2 (or just total_min for left-aligned?)
        # Let's say scroll controls the CENTER of the view within the allowable range.
        
        # Allowable center range:
        min_center = total_min + visible_span / 2
        max_center = total_max - visible_span / 2
        
        if min_center > max_center: # Zoomed out fully or more
             center = (total_min + total_max) / 2
        else:
             scroll_ratio = scroll_val / scroll_max
             center = min_center + (max_center - min_center) * scroll_ratio
             
        new_min = center - visible_span / 2
        new_max = center + visible_span / 2
        
        # Clamp (optional, but good for stability)
        if new_min < total_min: 
            diff = total_min - new_min
            new_min += diff; new_max += diff
        if new_max > total_max:
            diff = new_max - total_max
            new_min -= diff; new_max -= diff
            
        return new_min, new_max

    def _calculate_controls_from_range(self, current_min, current_max, total_min, total_max, zoom_min=1, zoom_max=100, scroll_max=10000):
        """
        Reverse calculation: Range -> Zoom/Scroll values.
        """
        total_span = total_max - total_min
        current_span = current_max - current_min
        
        if total_span <= 0: return zoom_min, scroll_max // 2
        
        # 1. Zoom
        ratio = current_span / total_span
        ratio = max(0.01, min(1.0, ratio))
        
        # ratio = 1.0 - (zoom - 1)/99 * 0.99
        # (zoom - 1)/99 = (1.0 - ratio) / 0.99
        if ratio >= 1.0:
            zoom_val = zoom_min
        else:
            zoom_val = 1 + ((1.0 - ratio) / 0.99) * (zoom_max - zoom_min)
        
        zoom_val = int(round(zoom_val))
        zoom_val = max(zoom_min, min(zoom_max, zoom_val))
        
        # 2. Scroll
        center = (current_min + current_max) / 2
        visible_span = current_span
        
        min_center = total_min + visible_span / 2
        max_center = total_max - visible_span / 2
        
        if max_center <= min_center:
            scroll_val = scroll_max // 2
        else:
            scroll_ratio = (center - min_center) / (max_center - min_center)
            scroll_val = int(scroll_ratio * scroll_max)
            scroll_val = max(0, min(scroll_max, scroll_val))
            
        return zoom_val, scroll_val

    # --- X-Axis Logic ---

    def _apply_x_zoom(self, value):
        if self._updating_viewranges or not self.base_x_range: return
        self._updating_viewranges = True
        try:
            scroll_val = self.x_scrollbar.value()
            new_min, new_max = self._calculate_visible_range(
                self.base_x_range[0], self.base_x_range[1], 
                value, scroll_val
            )
            
            # Apply to all plots (X-Linked anyway, but be explicit)
            for plot in self.plot_canvas.channel_plots.values():
                plot.setXRange(new_min, new_max, padding=0)
        finally:
            self._updating_viewranges = False
    
    def _on_x_scrollbar_changed(self, value):
        if self._updating_viewranges or not self.base_x_range: return
        self._updating_viewranges = True
        try:
            zoom_val = self.toolbar.x_zoom_slider.value()
            new_min, new_max = self._calculate_visible_range(
                self.base_x_range[0], self.base_x_range[1], 
                zoom_val, value
            )
            
            for plot in self.plot_canvas.channel_plots.values():
                plot.setXRange(new_min, new_max, padding=0)
        finally:
            self._updating_viewranges = False
            
    def _on_vb_x_range_changed(self, chan_id, new_range):
        if self._updating_viewranges or not self.base_x_range: return
        
        # Avoid rapid updates
        self._updating_viewranges = True
        try:
            # Derived from ViewBox
            cmin, cmax = new_range
            tmin, tmax = self.base_x_range
            
            z, s = self._calculate_controls_from_range(cmin, cmax, tmin, tmax)
            
            # Block signals to prevent loop
            self.toolbar.x_zoom_slider.blockSignals(True)
            self.toolbar.x_zoom_slider.setValue(z)
            self.toolbar.x_zoom_slider.blockSignals(False)
            
            self.x_scrollbar.blockSignals(True)
            self.x_scrollbar.setValue(s)
            self.x_scrollbar.blockSignals(False)
            
        except Exception: pass
        finally:
            self._updating_viewranges = False

    # --- Y-Axis Logic ---
    
    def _apply_global_y_zoom(self, value):
        if self._updating_viewranges: return
        self._updating_viewranges = True
        try:
            scroll_val = self.y_controls.global_y_scrollbar.value()
            
            # Apply to ALL visible channels
            for cid, base_range in self.base_y_ranges.items():
                if not base_range: continue
                
                plot = self.plot_canvas.get_plot(cid)
                if not plot or not plot.isVisible(): continue
                
                new_min, new_max = self._calculate_visible_range(
                    base_range[0], base_range[1], value, scroll_val
                )
                plot.setYRange(new_min, new_max, padding=0)
                
                # ALSO Update individual controls to match global
                self.y_controls.set_individual_scrollbar(cid, scroll_val)
                # Note: Assuming individual sliders should also sync?
                # y_controls.set_individual_slider... (not impl accessing private widget, let's skip for now or add method)
                
        finally:
            self._updating_viewranges = False
            
    def _apply_global_y_scroll(self, value):
        if self._updating_viewranges: return
        self._updating_viewranges = True
        try:
            zoom_val = self.y_controls.global_y_slider.value()
            
            for cid, base_range in self.base_y_ranges.items():
                if not base_range: continue
                plot = self.plot_canvas.get_plot(cid)
                if not plot or not plot.isVisible(): continue
                
                new_min, new_max = self._calculate_visible_range(
                    base_range[0], base_range[1], zoom_val, value
                )
                plot.setYRange(new_min, new_max, padding=0)
                self.y_controls.set_individual_scrollbar(cid, value)

        finally:
            self._updating_viewranges = False

    def _apply_channel_y_zoom(self, cid, val):
        if self._updating_viewranges: return
        
        # If locked, this shouldn't happen usually, but if it does, maybe redirect to global?
        if self.y_controls.y_lock_checkbox.isChecked():
            # If logic allows changing individual while locked, we should probably update global
            self.y_controls.global_y_slider.setValue(val)
            return

        self._updating_viewranges = True
        try:
            base_range = self.base_y_ranges.get(cid)
            if not base_range: return
            
            # We need the current scroll for this channel
            # Accessing via y_controls private dict is slightly dirty, but we can assume we track it?
            # Or read from current view? 
            # Better: read from the individual scrollbar
            sb = self.y_controls.individual_y_scrollbars.get(cid)
            scroll_val = sb.value() if sb else 5000
            
            new_min, new_max = self._calculate_visible_range(
                base_range[0], base_range[1], val, scroll_val
            )
            plot = self.plot_canvas.get_plot(cid)
            if plot: plot.setYRange(new_min, new_max, padding=0)
            
        finally:
            self._updating_viewranges = False

    def _apply_channel_y_scroll(self, cid, val):
        if self._updating_viewranges: return
        
        if self.y_controls.y_lock_checkbox.isChecked():
            self.y_controls.set_global_scrollbar(val) # Trigger global
            return

        self._updating_viewranges = True
        try:
            base_range = self.base_y_ranges.get(cid)
            if not base_range: return
            
            # Get Zoom
            sl = self.y_controls.individual_y_sliders.get(cid)
            zoom_val = sl.value() if sl else 1
            
            new_min, new_max = self._calculate_visible_range(
                base_range[0], base_range[1], zoom_val, val
            )
            plot = self.plot_canvas.get_plot(cid)
            if plot: plot.setYRange(new_min, new_max, padding=0)
            
        finally:
             self._updating_viewranges = False

    def _on_vb_y_range_changed(self, chan_id, new_range):
        if self._updating_viewranges: return
        self._updating_viewranges = True
        try:
            base_range = self.base_y_ranges.get(chan_id)
            if not base_range: return
            
            tmin, tmax = base_range
            cmin, cmax = new_range
            
            z, s = self._calculate_controls_from_range(cmin, cmax, tmin, tmax)
            
            # Update Individual Controls
            # We need to access YControls methods to set these without triggering signals if possible
            # But here we want to update the UI
            self.y_controls.set_individual_scrollbar(chan_id, s)
            
            # If Locked, update Global too?
            # Logic: If I pan ONE plot, and they are locked... strictly speaking I should pan ALL plots?
            # Or does locking just mean the sliders control all?
            # Usually locking means "force all to same". So if I interact with Plot A, Plot B should move.
            
            if self.y_controls.y_lock_checkbox.isChecked():
                self.y_controls.set_global_scrollbar(s)
                self.y_controls.global_y_slider.blockSignals(True)
                self.y_controls.global_y_slider.setValue(z)
                self.y_controls.global_y_slider.blockSignals(False)
                
                # And update other plots?
                # Yes, if locked, changing one view should update others.
                # However, calling set_global_scrollbar/slider might not trigger the update 
                # because we blocked signals or because we are in _updating_viewranges
                # We need to explicitly sync others if we want "Pan on Plot A moves Plot B"
                
                for other_cid, other_base in self.base_y_ranges.items():
                    if other_cid == chan_id: continue
                    other_plot = self.plot_canvas.get_plot(other_cid)
                    if other_plot and other_plot.isVisible():
                         nm, nM = self._calculate_visible_range(other_base[0], other_base[1], z, s)
                         other_plot.setYRange(nm, nM, padding=0)
                         # Also update their individual scrollbars
                         self.y_controls.set_individual_scrollbar(other_cid, s)

        except Exception as e:
            log.warning(f"Error syncing Y range: {e}")
            
        finally:
            self._updating_viewranges = False

    def _on_y_lock_changed(self, locked):
        # When locking, force alignment to global settings?
        if locked:
           self._apply_global_y_zoom(self.y_controls.global_y_slider.value())

    def _save_plot(self):
        """Save the current plot to an image file."""
        if not self.current_recording: return
        
        # Simple save dialog
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Plot", str(Path.home() / "plot.png"), "Images (*.png *.jpg *.svg)"
        )
        
        if filename:
            try:
                # Use pyqtgraph exporter on the layout widget
                import pyqtgraph.exporters
                exporter = None
                if filename.endswith(".svg"):
                    exporter = pyqtgraph.exporters.SVGExporter(self.plot_canvas.widget.scene())
                else:
                    exporter = pyqtgraph.exporters.ImageExporter(self.plot_canvas.widget.scene())
                exporter.export(filename)
                self.status_bar.showMessage(f"Plot saved to {filename}", 3000)
            except Exception as e:
                log.error(f"Error saving plot: {e}")
                self.status_bar.showMessage(f"Error saving plot: {e}", 3000)

    def _on_manual_limits_toggled(self, enabled):
        self.manual_limits_enabled = enabled
        self.y_controls.y_lock_checkbox.setEnabled(not enabled) # Maybe?
        # Update plots if needed

    def _apply_manual_limits_from_dict(self, limits):
        # Apply limits
        pass

    def _toggle_select_current_trial(self):
        if self.current_trial_index in self.selected_trial_indices:
            self.selected_trial_indices.discard(self.current_trial_index)
        else:
            self.selected_trial_indices.add(self.current_trial_index)
        self._update_all_ui_state()

    def _clear_avg_selection(self):
        self.selected_trial_indices.clear()
        self._update_all_ui_state()
        self._toggle_plot_selected_average(False)

    def _toggle_plot_selected_average(self, show):
        # Logic to show/hide overlay
        self._update_plot()

    def _on_plot_mode_changed(self, mode):
        self.current_plot_mode = mode
        self._update_plot()
        self._update_all_ui_state()

    def _on_channel_visibility_changed(self, chan_id, visible):
        plot = self.plot_canvas.get_plot(chan_id)
        if plot:
            if visible:
                plot.show()
                # Restore row
                # This is tricky with GraphicsLayoutWidget. 
                # Ideally config panel should just toggle row height or something.
                # But GraphicsLayoutWidget doesn't support hiding easily without removing.
                # Just keeping plot items logic simpler: always there, maybe just hide content?
                pass
            else:
                plot.hide() 
        self._update_plot()



    def _auto_select_trials(self):
        # Auto select 5 trials
        self.selected_trial_indices = set(range(min(5, self.max_trials_current_recording)))
