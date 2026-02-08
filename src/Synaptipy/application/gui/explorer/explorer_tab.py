# src/Synaptipy/application/gui/explorer/explorer_tab.py
# -*- coding: utf-8 -*-
"""
Explorer Tab widget for the Synaptipy GUI.
Refactored modular version.
"""
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set

import numpy as np
from PySide6 import QtCore, QtWidgets

# --- Synaptipy Imports ---
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from Synaptipy.application.session_manager import SessionManager
from Synaptipy.application.gui.analysis_worker import AnalysisWorker

# --- Components ---
from .sidebar import ExplorerSidebar
from .config_panel import ExplorerConfigPanel
from .plot_canvas import ExplorerPlotCanvas
from .y_controls import ExplorerYControls
from .toolbar import ExplorerToolbar
from Synaptipy.application.gui.widgets.preprocessing import PreprocessingWidget
from Synaptipy.core import signal_processor
from Synaptipy.core.processing_pipeline import SignalProcessingPipeline

# Configure Logger
log = logging.getLogger(__name__)


class ExplorerTab(QtWidgets.QWidget):
    """
    Main controller for the Data Explorer tab.
    Coordinatse sub-components: Sidebar, PlotCanvas, Controls, Toolbar, ConfigPanel.
    """

    open_file_requested = QtCore.Signal()  # Check if still needed

    # Constants
    class PlotMode:
        OVERLAY_AVG = 0
        CYCLE_SINGLE = 1

    def __init__(
        self, neo_adapter: NeoAdapter, nwb_exporter: NWBExporter, status_bar: QtWidgets.QStatusBar, parent=None
    ):
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
        self.session_manager.file_context_changed.connect(self._on_file_context_changed)

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
        self._processed_cache: Dict[str, Dict[int, Tuple[np.ndarray, np.ndarray]]] = {}  # NEW: Cache for processed data
        # Pipeline for processing
        self.pipeline = SignalProcessingPipeline()
        # Active settings for on-the-fly processing
        self._active_preprocessing_settings: Optional[Dict[str, Any]] = None
        self._cache_dirty: bool = False
        self._is_loading: bool = False

        # Limits State
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_y_ranges: Dict[str, Optional[Tuple[float, float]]] = {}
        # self.manual_limits_enabled: bool = False  # Removed

        self._updating_viewranges: bool = False  # Lock to prevent feedback loops

        # Components
        self._init_components()
        self._setup_layout()
        self._connect_signals()

        # Initial State
        self._update_all_ui_state()

        # State Preservation for Cycling
        self._current_trial_selection_params: Optional[Tuple[int, int]] = None  # (n, start_index)
        self._pending_view_state: Optional[Dict[str, Tuple[Tuple[float, float], Tuple[float, float]]]] = None
        self._pending_trial_params: Optional[Tuple[int, int]] = None

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

        # Preprocessing Widget
        self.preprocessing_widget = PreprocessingWidget()
        self.preprocessing_widget.preprocessing_requested.connect(self._handle_preprocessing_request)
        self.preprocessing_widget.preprocessing_reset_requested.connect(self._handle_preprocessing_reset)

    def _setup_layout(self):
        layout = QtWidgets.QHBoxLayout(self)

        # LEFT PANEL
        layout.addWidget(self.config_panel, 0)

        # CENTER PANEL
        center_widget = QtWidgets.QWidget()
        center_layout = QtWidgets.QGridLayout(center_widget)
        # (Row, Col, RowSpan, ColSpan)

        # 1. Plot Area (0, 0)
        center_layout.addWidget(self.plot_canvas.widget, 0, 0)

        # 2. Y Scrollbar (Right of Plot) (0, 1)
        center_layout.addWidget(self.y_controls.y_scroll_widget, 0, 1)

        # 3. X Scrollbar (Below Plot) (1, 0)
        center_layout.addWidget(self.x_scrollbar, 1, 0)

        # 4. Navigation Row (Row 2: Prev File | Trial Cycle | Next File)
        # We need to construct this row by "stealing" widgets from the toolbar
        nav_row_widget = QtWidgets.QWidget()
        nav_row_layout = QtWidgets.QHBoxLayout(nav_row_widget)
        nav_row_layout.setContentsMargins(0, 0, 0, 0)

        # Reparent widgets
        nav_row_layout.addWidget(self.toolbar.prev_file_btn)
        nav_row_layout.addStretch()
        nav_row_layout.addWidget(self.toolbar.trial_group)
        nav_row_layout.addStretch()
        nav_row_layout.addWidget(self.toolbar.next_file_btn)

        # Also include the file index label somewhere? The user's request:
        # "the seco row acomodates the next previous as it isand put trial cycle int he centre of that region"
        # The original toolbar had the file label in the middle.
        # I'll put the file index label with the file buttons to keep context?
        # Or maybe putting trial cycle in center implicitly displaces the index label.
        # I'll add the index label next to the buttons for clarity.
        # [Prev] [Index] ... [Trial] ... [Next] - actually User said "put trial cycle in the centre".
        # So I will do: [Prev] [Index] [Stretch] [Trial] [Stretch] [Next]

        # Wait, I can't easily insert into the middle of the "nav_row" if I just steal buttons.
        # Let's clean up the toolbar layout first? No, reparenting removes from old layout automatically.
        # I will grab the file_index_lbl too.

        nav_row_layout.insertWidget(1, self.toolbar.file_index_lbl)  # Place index next to Prev?
        # Or maybe better: [Prev] [Stretch] [Trial] [Stretch] [Index] [Next]?
        # Let's stick to the user request: "trial cycle in the centre... between the two buttons".
        # I'll put index label next to Next or Prev. Let's put it next to Next.

        # Re-doing nav row layout:
        # [Prev File] [Stretch] [Trial Group] [Stretch] [Index Label] [Next File]

        # 5. Zoom/View Row (Row 3: X Zoom | Y Zoom | View)
        zoom_row_widget = QtWidgets.QWidget()
        zoom_row_layout = QtWidgets.QHBoxLayout(zoom_row_widget)
        zoom_row_layout.setContentsMargins(0, 0, 0, 0)

        zoom_row_layout.addWidget(self.toolbar.x_zoom_group, 1)  # Time Zoom
        zoom_row_layout.addWidget(self.y_controls.y_zoom_widget, 1)  # Amplitude Zoom
        zoom_row_layout.addWidget(self.toolbar.view_group)  # View Controls

        center_layout.addWidget(nav_row_widget, 2, 0)
        center_layout.addWidget(zoom_row_widget, 3, 0)

        # Adjust column stretch
        center_layout.setColumnStretch(0, 1)  # Plot takes max width
        center_layout.setColumnStretch(1, 0)  # Scrollbar fixes width

        # Adjust row stretch
        center_layout.setRowStretch(0, 1)  # Plot takes max height
        center_layout.setRowStretch(1, 0)
        center_layout.setRowStretch(2, 0)
        center_layout.setRowStretch(3, 0)

        layout.addWidget(center_widget, 1)

        # RIGHT PANEL
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)

        right_layout.addWidget(self.open_file_btn)
        right_layout.addWidget(self.sidebar)
        right_layout.addWidget(self.analysis_group)
        right_layout.addWidget(self.preprocessing_widget)  # Added below analysis selection
        # right_layout.addWidget(self.y_controls)  # Removed, integrated into center grid

        layout.addWidget(right_widget, 0)

    def _connect_signals(self):
        # Open File
        self.open_file_btn.clicked.connect(self.open_file_requested.emit)

        # Sidebar
        # Sidebar
        # We preserve state when selecting from sidebar too, to allow seamless browsing of siblings
        self.sidebar.file_selected.connect(
            lambda f, files, i: self.load_recording_data(f, files, i, preserve_state=True)
        )

        # Config Panel
        self.config_panel.plot_mode_changed.connect(self._on_plot_mode_changed)
        self.config_panel.downsample_toggled.connect(self._trigger_plot_update)  # Just trigger redraw
        self.config_panel.select_current_trial_clicked.connect(self._toggle_select_current_trial)
        self.config_panel.clear_avg_selection_clicked.connect(self._clear_avg_selection)
        self.config_panel.show_selected_avg_toggled.connect(self._toggle_plot_selected_average)
        self.config_panel.select_current_trial_clicked.connect(self._toggle_select_current_trial)
        self.config_panel.clear_avg_selection_clicked.connect(self._clear_avg_selection)
        self.config_panel.show_selected_avg_toggled.connect(self._toggle_plot_selected_average)
        self.config_panel.trial_selection_requested.connect(self._on_trial_selection_requested)
        self.config_panel.trial_selection_reset_requested.connect(self._on_trial_selection_reset_requested)
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

    def load_recording_data(
        self,
        filepath: Path,
        file_list: List[Path] = None,
        selected_index: int = -1,
        preserve_state: bool = False,
    ):
        if self._is_loading:
            return
        self._is_loading = True

        if file_list is None:
            file_list = [filepath]
        if selected_index == -1:
            selected_index = 0

        self.file_list = file_list
        self.current_file_index = selected_index

        # --- Capture State if Requested ---
        if preserve_state:
            # 1. Capture View State (Zoom/Pan)
            self._pending_view_state = {}
            for cid, plot in self.plot_canvas.channel_plots.items():
                if plot.isVisible():
                    # capture ((xmin, xmax), (ymin, ymax))
                    self._pending_view_state[cid] = (plot.viewRange()[0], plot.viewRange()[1])

            # 2. Capture Trial Selection Params
            self._pending_trial_params = self._current_trial_selection_params
            log.debug(
                f"State captured for restoration: View for {len(self._pending_view_state)} plots, "
                f"Trial Params: {self._pending_trial_params}"
            )
        else:
            # Clear pending state if not preserving
            self._pending_view_state = None
            self._pending_trial_params = None

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
        
        # Auto-add to analysis set so AnalyserTab sees it immediately
        self._add_current_to_analysis_set()

    def _display_recording(self, recording: Recording):
        if not recording:
            return
        self.current_recording = recording
        self.max_trials_current_recording = getattr(recording, "max_trials", 0)

        # Reset Logic
        self._data_cache.clear()
        self._average_cache.clear()
        self._processed_cache.clear()
        self._cache_dirty: bool = False
        self.current_trial_index = 0
        self.selected_trial_indices.clear()
        self._current_trial_selection_params = None  # Reset params

        # Default: Select ALL trials implicitly (empty set means all in some logic, but here we want explicit control?)
        # Let's say empty set in selected_trial_indices means "User hasn't filtered".
        # But for "Plot Selected" feature, we want explicit subset.
        # Actually my plan said "self.selected_trial_indices: Set[int] = set()".
        # If I use this set for BOTH manual selection (cycle mode) and Nth selection (overlay mode),
        # I need to be careful. User wants "Plot Selected Trials" to replace "Manual Limits".
        # So this selection affects Overlay mode primarily?
        # Yes: "this will plot only those trials which i select... plot, preprocess, and average only every nth trial"

        # So, if selected_trial_indices is Empty, we assume ALL trials are valid for Overlay mode.
        # If it is populated, we use only those.
        self.selected_trial_indices = set()

        # Rebuild Components
        self.plot_canvas.rebuild_plots(recording)
        self.config_panel.rebuild(recording)
        self.y_controls.rebuild(recording)

        # Calculate Base Ranges
        self._calculate_base_ranges()

        # Initial Plot
        self._update_plot()
        self._reset_view()

        # --- Restore State if Pending ---
        restored_view = False
        if self._pending_view_state:
            log.debug("Restoring view state...")
            try:
                for cid, ranges in self._pending_view_state.items():
                    # Only restore if channel exists in new recording
                    if cid in self.plot_canvas.channel_plots:
                        plot = self.plot_canvas.channel_plots[cid]
                        if plot and plot.isVisible():
                            # ranges = ((xmin, xmax), (ymin, ymax))
                            plot.setXRange(ranges[0][0], ranges[0][1], padding=0)
                            plot.setYRange(ranges[1][0], ranges[1][1], padding=0)
                restored_view = True
                # Clear after use
                self._pending_view_state = None
            except Exception as e:
                log.warning(f"Failed to restore view state: {e}")

        if not restored_view:
            pass  # _reset_view already called above

        # Restore Trial Selection
        if self._pending_trial_params:
            log.debug(f"Restoring trial selection params: {self._pending_trial_params}")
            try:
                n_gap, start_idx = self._pending_trial_params
                # Re-apply selection logic (this will update selected_trial_indices and trigger plot update)
                self._on_trial_selection_requested(n_gap, start_index=start_idx)
                # Note: _on_trial_selection_requested calls _update_plot, so we might redraw twice, but safe.
            except Exception as e:
                log.warning(f"Failed to restore trial selection: {e}")
                self._auto_select_trials()  # Fallback
            finally:
                self._pending_trial_params = None
        else:
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
                    if diff == 0:
                        diff = 1.0
                    self.base_y_ranges[cid] = (mn - diff * 0.1, mx + diff * 0.1)
                else:
                    self.base_y_ranges[cid] = (-1, 1)
            except Exception:
                self.base_y_ranges[cid] = (-1, 1)

    def get_current_recording(self) -> Optional[Recording]:
        return self.current_recording

    def _recalculate_base_y_ranges_from_view(self):
        """
        Recalculate base Y ranges from the current view ranges.

        This fixes scroll range issues after preprocessing (e.g., baseline subtraction)
        by updating the base ranges to match the currently displayed data range.
        """
        if not self.current_recording:
            return

        for cid, plot in self.plot_canvas.channel_plots.items():
            if not plot or not plot.isVisible():
                continue

            try:
                # Get the current view range from the plot's ViewBox
                vb = plot.getViewBox()
                if vb:
                    y_range = vb.viewRange()[1]  # [1] is Y range
                    if y_range and len(y_range) == 2:
                        ymin, ymax = y_range
                        diff = ymax - ymin
                        if diff > 0:
                            # Expand slightly to allow full scroll range
                            self.base_y_ranges[cid] = (ymin - diff * 0.1, ymax + diff * 0.1)
                            log.debug(f"Updated base Y range for {cid}: {self.base_y_ranges[cid]}")
            except Exception as e:
                log.debug(f"Could not recalculate Y range for {cid}: {e}")

    def _trigger_plot_update(self):
        """Updates all plot items based on current selection/data state."""
        if not self.current_recording:
            return
        # Handle styling updates if needed (omitted for brevity)
        self._update_plot()
        if self.plot_canvas.widget:
            self.plot_canvas.widget.update()

    def _update_plot(self):
        """Standard plot update."""
        if not self.current_recording or not self.plot_canvas.channel_plots:
            return

        # Disable updates
        if self.plot_canvas.widget:
            self.plot_canvas.widget.setUpdatesEnabled(False)
        try:
            # Clear existing items
            # Clear existing items robustly
            for cid in self.plot_canvas.channel_plots.keys():
                self.plot_canvas.clear_plot_items(cid)

            # Reset tracking lists
            self.plot_canvas.channel_plot_data_items.clear()
            self.plot_canvas.selected_average_plot_items.clear()

            # Re-init dict keys
            for cid in self.plot_canvas.channel_plots.keys():
                self.plot_canvas.channel_plot_data_items[cid] = []

            # 0. Preserve View State if possible
            view_state = {}
            for cid, plot in self.plot_canvas.channel_plots.items():
                if plot.isVisible():
                    view_state[cid] = plot.viewRange()

            # --- PLOT SETTINGS ---
            ds_enabled = self.config_panel.downsample_cb.isChecked()
            # Force aggressive threshold if enabled (e.g. 3000 points) to prevent freezes
            ds_avg_threshold = 3000
            ds_method = "peak"
            clip_view = True

            # Function to apply common item settings
            def _apply_item_opts(item, is_ds):
                if hasattr(item, "setDownsampling"):
                    item.setDownsampling(auto=is_ds, method=ds_method)
                if hasattr(item, "opts"):
                    item.opts["autoDownsample"] = is_ds
                    if is_ds:
                        item.opts["autoDownsampleThreshold"] = ds_avg_threshold
                if hasattr(item, "setClipToView"):
                    item.setClipToView(clip_view)

            # Get Pens
            from Synaptipy.shared.plot_customization import get_average_pen, get_single_trial_pen

            avg_pen = get_average_pen()
            current_trial_pen = get_single_trial_pen()

            # Iterate and plot
            for cid, channel in self.current_recording.channels.items():
                plot_item = self.plot_canvas.channel_plots.get(cid)
                if not plot_item or not plot_item.isVisible():
                    continue

                self.plot_canvas.channel_plot_data_items[cid] = []

                if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE:
                    # Plot Single Trial
                    if 0 <= self.current_trial_index < self.max_trials_current_recording:
                        try:
                            data = channel.get_data(self.current_trial_index)
                            t = channel.get_relative_time_vector(self.current_trial_index)

                            # APPLY PREPROCESSING (via Pipeline)
                            if data is not None:
                                try:
                                    fs = channel.sampling_rate
                                    # Pipeline handles empty steps gracefully
                                    data = self.pipeline.process(data, fs, time_vector=t)
                                except Exception as e:
                                    log.error(f"Error processing trial {self.current_trial_index}: {e}")

                            if data is not None and t is not None:
                                item = plot_item.plot(
                                    t, data, pen=current_trial_pen, name=f"Trial {self.current_trial_index+1}"
                                )
                                _apply_item_opts(item, ds_enabled)
                                self.plot_canvas.channel_plot_data_items[cid].append(item)
                        except Exception as e:
                            log.error(f"Error plotting trial {self.current_trial_index} for {cid}: {e}")

                else:  # OVERLAY_AVG
                    # 1. Overlay ALL trials (Background) or SELECTED trials

                    # Determine trials to plot
                    if self.selected_trial_indices:
                        trials_to_plot = sorted(list(self.selected_trial_indices))
                    else:
                        trials_to_plot = list(range(channel.num_trials))

                    for trial_idx in trials_to_plot:
                        try:
                            # Skip extensive background plotting if too many trials?
                            # For now, plot all but use subsample for speed if DS enabled
                            bg_ds_method = "subsample" if ds_enabled else "peak"

                            data = channel.get_data(trial_idx)
                            t = channel.get_relative_time_vector(trial_idx)

                            # APPLY PREPROCESSING (via Pipeline - same as CYCLE_SINGLE)
                            if data is not None:
                                try:
                                    fs = channel.sampling_rate
                                    # Pipeline handles empty steps gracefully
                                    data = self.pipeline.process(data, fs, time_vector=t)
                                except Exception as e:
                                    log.error(f"Error processing trial {trial_idx}: {e}")

                            if data is not None and t is not None:
                                item = plot_item.plot(t, data, pen=current_trial_pen)

                                # Apply background optimizations
                                item.setDownsampling(auto=ds_enabled, method=bg_ds_method)
                                item.opts["autoDownsample"] = ds_enabled
                                if ds_enabled:
                                    item.opts["autoDownsampleThreshold"] = ds_avg_threshold
                                item.setClipToView(clip_view)

                                self.plot_canvas.channel_plot_data_items[cid].append(item)
                        except Exception:
                            pass

                    # 2. Plot Average on Top
                    # 2. Plot Average on Top
                    try:
                        avg_data = channel.get_averaged_data(
                            trial_indices=list(self.selected_trial_indices) if self.selected_trial_indices else None
                        )
                        avg_t = channel.get_relative_time_vector(0)  # Use trial 0 time as Ref

                        # APPLY PREPROCESSING (via Pipeline - same as trials)
                        if avg_data is not None:
                            try:
                                fs = channel.sampling_rate
                                # Pipeline handles empty steps gracefully
                                avg_data = self.pipeline.process(avg_data, fs, time_vector=avg_t)
                            except Exception as e:
                                log.error(f"Error processing average for {cid}: {e}")

                        if avg_data is not None and avg_t is not None:
                            item = plot_item.plot(avg_t, avg_data, pen=avg_pen, name="Average")
                            _apply_item_opts(item, ds_enabled)
                            item.setZValue(10)
                            self.plot_canvas.channel_plot_data_items[cid].append(item)
                    except Exception as e:
                        log.error(f"Error plotting avg for {cid}: {e}")

            # Restore View State
            if view_state:
                for cid, state in view_state.items():
                    plot = self.plot_canvas.get_plot(cid)
                    if plot and plot.isVisible():
                        # We restore the view range to preserve zoom
                        plot.setXRange(state[0][0], state[0][1], padding=0)
                        plot.setYRange(state[1][0], state[1][1], padding=0)
        finally:
            if self.plot_canvas.widget:
                self.plot_canvas.widget.setUpdatesEnabled(True)

    def _clear_data_cache(self):
        self._data_cache.clear()
        self._average_cache.clear()
        self._processed_cache.clear()
        self._cache_dirty = False

    def _mark_cache_dirty(self):
        self._cache_dirty = True

    def _remove_selected_average_plots(self):
        for cid, item in self.plot_canvas.selected_average_plot_items.items():
            try:
                self.plot_canvas.channel_plots[cid].removeItem(item)
            except Exception:
                pass
        self.plot_canvas.selected_average_plot_items.clear()

    def update_plot_pens(self):
        """Update plot pens when customization preferences change."""
        # Prevent re-entrant calls
        if getattr(self, "_is_updating_pens", False):
            return

        if not self.current_recording or not self.plot_canvas.channel_plots:
            return

        self._is_updating_pens = True
        try:
            from Synaptipy.shared.plot_customization import get_average_pen, get_single_trial_pen

            # Get pens once (cached in customization manager)
            avg_pen = get_average_pen()
            trial_pen = get_single_trial_pen()

            # Disable updates during batch operation
            if self.plot_canvas.widget:
                self.plot_canvas.widget.setUpdatesEnabled(False)

            try:
                # Update existing plot item pens
                for cid, items in self.plot_canvas.channel_plot_data_items.items():
                    if not items:
                        continue

                    # Optimization: Skip hidden plots
                    # The expensive setPen operation is avoided for all items in hidden plots
                    plot_widget = self.plot_canvas.channel_plots.get(cid)
                    if not plot_widget or not plot_widget.isVisible():
                        continue

                    for item in items:
                        try:
                            # Check if this is an average plot
                            if hasattr(item, "name") and item.name() == "Average":
                                item.setPen(avg_pen)
                            else:
                                item.setPen(trial_pen)
                        except Exception:
                            pass
            finally:
                # Re-enable updates and force single repaint
                if self.plot_canvas.widget:
                    self.plot_canvas.widget.setUpdatesEnabled(True)
                    self.plot_canvas.widget.update()

        except Exception as e:
            log.warning(f"Failed to update plot pens: {e}")
        finally:
            self._is_updating_pens = False

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

    def _on_file_context_changed(self, file_list: List[Path], current_index: int):
        """Handle file context updates from SessionManager (e.g. from Open File dialog)."""
        log.debug(f"ExplorerTab received file context update: {len(file_list)} files, index {current_index}")
        self.file_list = file_list
        self.current_file_index = current_index
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
        self.toolbar.set_trial_nav_enabled(
            self.current_recording is not None and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        )

        # Analysis Buttons
        self.add_analysis_btn.setEnabled(self.current_recording is not None)
        self.clear_analysis_btn.setEnabled(bool(self._analysis_items))

        # Preprocessing state
        # Can enable/disable based on recording presence
        self.preprocessing_widget.setEnabled(self.current_recording is not None)

    # --- Placeholders for remaining logic ---
    def _add_current_to_analysis_set(self):
        if not self.current_recording or not self.current_recording.source_file:
            log.warning("Cannot add recording to analysis set: No recording loaded.")
            return

        file_path = self.current_recording.source_file
        target_type = "Recording"
        trial_index = None

        analysis_item = {
            "path": file_path,
            "target_type": target_type,
            "trial_index": trial_index,
            "recording_ref": self.current_recording,
        }

        is_duplicate = any(
            item.get("path") == file_path and item.get("target_type") == target_type for item in self._analysis_items
        )
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
        if not self._analysis_items:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Confirm Clear",
            f"Clear all {len(self._analysis_items)} items from the analysis set?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
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
                if i >= items_to_show:
                    tooltip_text += f"... ({count - items_to_show} more)"
                    break
                path_name = item["path"].name
                target = item["target_type"]
                tooltip_text += f"- {path_name} [{target}]\n"
            self.analysis_set_label.setToolTip(tooltip_text.strip())
        else:
            self.analysis_set_label.setToolTip("Analysis set is empty.")

    def _prev_file_folder(self):
        if self.current_file_index > 0:
            self.load_recording_data(
                self.file_list[self.current_file_index - 1],
                self.file_list,
                self.current_file_index - 1,
                preserve_state=True,  # Preserve Zoom/Selection
            )

    def _next_file_folder(self):
        if self.current_file_index < len(self.file_list) - 1:
            self.load_recording_data(
                self.file_list[self.current_file_index + 1],
                self.file_list,
                self.current_file_index + 1,
                preserve_state=True,  # Preserve Zoom/Selection
            )

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
        self.y_controls.set_global_scrollbar(5000)  # Center?
        # Reset individual scrollbars too

    # ... Implement Zoom/Scroll applying ...
    # --- Interaction Logic (Zoom/Scroll) ---

    def _calculate_visible_range(
        self, total_min, total_max, zoom_val, scroll_val, zoom_min=0, zoom_max=1000, scroll_max=10000
    ):
        """
        Calculates the new min/max range based on zoom slider and scrollbar values.
        Zoom: 0 (Wide) -> 1000 (Narrow). Exponential scale (Apple-like feel).
        Scroll: 0 -> 10000 (Relative position of center)
        """
        total_span = total_max - total_min
        if total_span <= 0:
            return total_min, total_max

        # 1. Calculate Visible Span using Exponential Scaling
        # We want to map slider [0, 1000] to ratio [1.0, 1e-6]
        # ratio = (min_ratio) ** normalized_slider

        # Normalize slider to 0..1
        if zoom_max == zoom_min:
            norm_slider = 0
        else:
            norm_slider = (zoom_val - zoom_min) / (zoom_max - zoom_min)

        # Target minimum ratio (1e-6 = 1ppm, allows zooming to ~10 samples in 10s @ 100kHz)
        min_ratio = 1e-6

        # Exponential mapping: ratio = min_ratio ^ norm_slider
        # However, to be "Apple-like", high numbers of slider should be SMALL ratio.
        # At slider=0, norm=0, ratio=1 (Full view)
        # At slider=1000, norm=1, ratio=1e-6 (Micro view)
        ratio = min_ratio**norm_slider

        visible_span = total_span * ratio

        # 2. Calculate Center based on Scroll
        # Scroll 0 => center at start + half_view
        # Scroll max => center at end - half_view

        # Allowable center range:
        min_center = total_min + visible_span / 2
        max_center = total_max - visible_span / 2

        if min_center > max_center:  # Zoomed out fully or more (should happen at ratio=1)
            center = (total_min + total_max) / 2
        else:
            scroll_ratio = scroll_val / scroll_max
            # Apply scroll direction inversion based on user preference
            try:
                from Synaptipy.shared.scroll_settings import is_scroll_inverted
                if is_scroll_inverted():
                    scroll_ratio = 1.0 - scroll_ratio
            except ImportError:
                pass
            center = min_center + (max_center - min_center) * scroll_ratio

        new_min = center - visible_span / 2
        new_max = center + visible_span / 2

        # Clamp to bounds to prevent floating point drift outside valid range
        if new_min < total_min:
            diff = total_min - new_min
            new_min += diff
            new_max += diff
        if new_max > total_max:
            diff = new_max - total_max
            new_min -= diff
            new_max -= diff

        return new_min, new_max

    def _calculate_controls_from_range(
        self, current_min, current_max, total_min, total_max, zoom_min=0, zoom_max=1000, scroll_max=10000
    ):
        """
        Reverse calculation: Range -> Zoom/Scroll values.
        Syncs sliders when user uses Mouse Zoom/Pan (Rectangle).
        """
        total_span = total_max - total_min
        current_span = current_max - current_min

        if total_span <= 0:
            return zoom_min, scroll_max // 2

        # 1. Zoom
        ratio = current_span / total_span
        # Clamp ratio
        min_ratio = 1e-6
        ratio = max(min_ratio, min(1.0, ratio))

        # Inverse of ratio = min_ratio ** norm_slider
        # log(ratio) = norm_slider * log(min_ratio)
        # norm_slider = log(ratio) / log(min_ratio)
        import math

        try:
            norm_slider = math.log(ratio) / math.log(min_ratio)
        except ValueError:
            norm_slider = 0

        zoom_val = zoom_min + norm_slider * (zoom_max - zoom_min)
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

    # --- Preprocessing Logic ---
    def _handle_preprocessing_request(self, settings: Dict[str, Any]):
        """
        Handle signal from PreprocessingWidget.
        Updates the SignalProcessingPipeline and triggers re-draw.
        Supports multiple filters - same filter type replaces, different types accumulate.
        """
        if not self.current_recording:
            QtWidgets.QMessageBox.warning(self, "No Data", "No recording loaded.")
            return

        # Store settings for UI state tracking - merge with existing
        step_type = settings.get('type')
        if self._active_preprocessing_settings is None:
            self._active_preprocessing_settings = {}
        
        # Store in slot format (baseline slot + filters dict keyed by method)
        if step_type == 'baseline':
            self._active_preprocessing_settings['baseline'] = settings
            # Pipeline: remove old baseline, add new
            self.pipeline.remove_step_by_type('baseline')
            self.pipeline.add_step(settings)
        elif step_type == 'filter':
            filter_method = settings.get('method', 'unknown')
            if 'filters' not in self._active_preprocessing_settings:
                self._active_preprocessing_settings['filters'] = {}
            # Same filter method replaces old one
            self._active_preprocessing_settings['filters'][filter_method] = settings
            # Pipeline: rebuild from all filters to ensure correct order
            self._rebuild_pipeline_from_settings()

        # Notify SessionManager for global preprocessing state
        self.session_manager.preprocessing_settings = settings

        # Trigger update
        self.preprocessing_widget.set_processing_state(True)
        try:
            self._update_plot()
            # Recalculate base Y ranges from current view to fix scroll range
            self._recalculate_base_y_ranges_from_view()
        finally:
            self.preprocessing_widget.set_processing_state(False)
            self.status_bar.showMessage("Applied preprocessing settings via Pipeline.", 3000)

    def _rebuild_pipeline_from_settings(self):
        """Rebuild pipeline from current slot-based settings."""
        self.pipeline.clear()
        if self._active_preprocessing_settings:
            # Baseline first
            if 'baseline' in self._active_preprocessing_settings:
                self.pipeline.add_step(self._active_preprocessing_settings['baseline'])
            # Then all filters in sorted order
            if 'filters' in self._active_preprocessing_settings:
                for method in sorted(self._active_preprocessing_settings['filters'].keys()):
                    self.pipeline.add_step(self._active_preprocessing_settings['filters'][method])

    def _on_preprocessing_complete_legacy(self, result_data):
        pass  # Removed legacy worker method

    def _handle_preprocessing_reset(self):
        """Reset all preprocessing and revert to raw data."""
        self._processed_cache.clear()
        self._cache_dirty = True
        self._active_preprocessing_settings = None  # Clear slot-based settings
        self.pipeline.clear()  # Clear pipeline
        
        # Notify SessionManager
        self.session_manager.preprocessing_settings = None
        
        self._update_plot()

        # Auto-range to fit raw data
        for plot in self.plot_canvas.channel_plots.values():
            plot.autoRange()

        self.status_bar.showMessage("Preprocessing reset to raw data.", 3000)

    # --- X-Axis Logic ---

    def _apply_x_zoom(self, value):
        if self._updating_viewranges or not self.base_x_range:
            return
        self._updating_viewranges = True
        try:
            scroll_val = self.x_scrollbar.value()
            new_min, new_max = self._calculate_visible_range(
                self.base_x_range[0], self.base_x_range[1], value, scroll_val
            )

            # Apply to all plots (X-Linked anyway, but be explicit)
            for plot in self.plot_canvas.channel_plots.values():
                plot.setXRange(new_min, new_max, padding=0)
        finally:
            self._updating_viewranges = False

    def _on_x_scrollbar_changed(self, value):
        if self._updating_viewranges or not self.base_x_range:
            return
        self._updating_viewranges = True
        try:
            zoom_val = self.toolbar.x_zoom_slider.value()
            new_min, new_max = self._calculate_visible_range(
                self.base_x_range[0], self.base_x_range[1], zoom_val, value
            )

            for plot in self.plot_canvas.channel_plots.values():
                plot.setXRange(new_min, new_max, padding=0)
        finally:
            self._updating_viewranges = False

    def _on_vb_x_range_changed(self, chan_id, new_range):
        if self._updating_viewranges or not self.base_x_range:
            return

        # Avoid rapid updates
        self._updating_viewranges = True
        try:
            # Derived from ViewBox
            cmin, cmax = new_range
            tmin, tmax = self.base_x_range

            # Avoid division by zero
            total_span = tmax - tmin
            if total_span <= 0:
                total_span = 1

            # 1. Update Sliders/Scrollbars values
            z, s = self._calculate_controls_from_range(cmin, cmax, tmin, tmax)

            # Block signals to prevent loop
            self.toolbar.x_zoom_slider.blockSignals(True)
            self.toolbar.x_zoom_slider.setValue(z)
            self.toolbar.x_zoom_slider.blockSignals(False)

            self.x_scrollbar.blockSignals(True)
            self.x_scrollbar.setValue(s)

            # 2. Update Page Step (Handle Size)
            current_span = cmax - cmin
            ratio = max(0.0, min(1.0, current_span / total_span))
            page_step = int(ratio * 10000)
            if page_step < 1:
                page_step = 1
            self.x_scrollbar.setPageStep(page_step)

            self.x_scrollbar.blockSignals(False)

        except Exception as e:
            log.error(f"Error updating X controls: {e}")
        finally:
            self._updating_viewranges = False

    # --- Y-Axis Logic ---

    def _apply_global_y_zoom(self, value):
        if self._updating_viewranges:
            return
        self._updating_viewranges = True
        try:
            scroll_val = self.y_controls.global_y_scrollbar.value()

            # Apply to ALL visible channels
            for cid, base_range in self.base_y_ranges.items():
                if not base_range:
                    continue

                plot = self.plot_canvas.get_plot(cid)
                if not plot or not plot.isVisible():
                    continue

                new_min, new_max = self._calculate_visible_range(base_range[0], base_range[1], value, scroll_val)
                plot.setYRange(new_min, new_max, padding=0)

                # ALSO Update individual controls to match global
                self.y_controls.set_individual_scrollbar(cid, scroll_val)

        finally:
            self._updating_viewranges = False

    def _apply_global_y_scroll(self, value):
        if self._updating_viewranges:
            return
        self._updating_viewranges = True
        try:
            zoom_val = self.y_controls.global_y_slider.value()
            log.debug(f"Applying Global Y Scroll: val={value}, zoom={zoom_val}")

            for cid, base_range in self.base_y_ranges.items():
                if not base_range:
                    continue
                plot = self.plot_canvas.get_plot(cid)
                if not plot or not plot.isVisible():
                    continue

                new_min, new_max = self._calculate_visible_range(base_range[0], base_range[1], zoom_val, value)
                plot.setYRange(new_min, new_max, padding=0)
                self.y_controls.set_individual_scrollbar(cid, value)

        finally:
            self._updating_viewranges = False

    def _apply_channel_y_zoom(self, cid, val):
        if self._updating_viewranges:
            return

        # If locked, this shouldn't happen usually, but if it does, maybe redirect to global?
        if self.y_controls.y_lock_checkbox.isChecked():
            # If logic allows changing individual while locked, we should probably update global
            self.y_controls.global_y_slider.setValue(val)
            return

        self._updating_viewranges = True
        try:
            base_range = self.base_y_ranges.get(cid)
            if not base_range:
                return

            # We need the current scroll for this channel
            # Accessing via y_controls private dict is slightly dirty, but we can assume we track it?
            # Or read from current view?
            # Better: read from the individual scrollbar
            sb = self.y_controls.individual_y_scrollbars.get(cid)
            scroll_val = sb.value() if sb else 5000

            new_min, new_max = self._calculate_visible_range(base_range[0], base_range[1], val, scroll_val)
            plot = self.plot_canvas.get_plot(cid)
            if plot:
                plot.setYRange(new_min, new_max, padding=0)

        finally:
            self._updating_viewranges = False

    def _apply_channel_y_scroll(self, cid, val):
        if self._updating_viewranges:
            return

        if self.y_controls.y_lock_checkbox.isChecked():
            self.y_controls.set_global_scrollbar(val)  # Trigger global
            return

        self._updating_viewranges = True
        try:
            base_range = self.base_y_ranges.get(cid)
            if not base_range:
                return

            # Get Zoom
            sl = self.y_controls.individual_y_sliders.get(cid)
            zoom_val = sl.value() if sl else 1

            new_min, new_max = self._calculate_visible_range(base_range[0], base_range[1], zoom_val, val)
            plot = self.plot_canvas.get_plot(cid)
            if plot:
                plot.setYRange(new_min, new_max, padding=0)

        finally:
            self._updating_viewranges = False

    def _on_vb_y_range_changed(self, chan_id, new_range):
        if self._updating_viewranges:
            return
        self._updating_viewranges = True
        try:
            base_range = self.base_y_ranges.get(chan_id)
            if not base_range:
                return

            tmin, tmax = base_range
            cmin, cmax = new_range

            # --- Dynamic Range Expansion ---
            # If the user pans outside the initial "Base Range" (calculated from Trial 0),
            # we must expand the base range to encompass the new view.
            # Otherwise, scroll ratio calculations clamp to 0 or 1, locking the view.
            expanded = False
            if cmin < tmin:
                tmin = cmin
                expanded = True
            if cmax > tmax:
                tmax = cmax
                expanded = True

            if expanded:
                self.base_y_ranges[chan_id] = (tmin, tmax)
                # Note: We don't trigger a full re-calc of everything, just update the reference.
            # -------------------------------

            # Avoid division by zero
            total_span = tmax - tmin
            if total_span <= 0:
                total_span = 1

            z, s = self._calculate_controls_from_range(cmin, cmax, tmin, tmax)

            # Update Individual Controls
            # We need to access YControls methods to set these without triggering signals if possible
            # But here we want to update the UI
            self.y_controls.set_individual_scrollbar(chan_id, s)

            # Update Page Step (Handle Size) for individual scrollbar?
            current_span = cmax - cmin
            ratio = max(0.0, min(1.0, current_span / total_span))
            page_step = int(ratio * 10000)
            if page_step < 1:
                page_step = 1

            sb = self.y_controls.individual_y_scrollbars.get(chan_id)
            if sb:
                sb.setPageStep(page_step)

            # If Locked, update Global too?
            if self.y_controls.y_lock_checkbox.isChecked():
                self.y_controls.set_global_scrollbar(s)
                self.y_controls.global_y_scrollbar.setPageStep(page_step)

                self.y_controls.global_y_slider.blockSignals(True)
                self.y_controls.global_y_slider.setValue(z)
                self.y_controls.global_y_slider.blockSignals(False)

                # And update other plots?
                # Yes, if locked, changing one view should update others.
                # However, calling set_global_scrollbar/slider might not trigger the update
                # because we blocked signals or because we are in _updating_viewranges
                # We need to explicitly sync others if we want "Pan on Plot A moves Plot B"

                for other_cid, other_base in self.base_y_ranges.items():
                    if other_cid == chan_id:
                        continue
                    other_plot = self.plot_canvas.get_plot(other_cid)
                    if other_plot and other_plot.isVisible():
                        nm, nM = self._calculate_visible_range(other_base[0], other_base[1], z, s)
                        other_plot.setYRange(nm, nM, padding=0)
                        # Also update their individual scrollbars
                        self.y_controls.set_individual_scrollbar(other_cid, s)

                        # And page steps
                        other_sb = self.y_controls.individual_y_scrollbars.get(other_cid)
                        if other_sb:
                            other_sb.setPageStep(page_step)

        except Exception as e:
            log.warning(f"Error syncing Y range: {e}")

        finally:
            self._updating_viewranges = False

    def _on_y_lock_changed(self, locked):
        # When locking, force alignment to global settings?
        if locked:
            self._apply_global_y_zoom(self.y_controls.global_y_slider.value())

    def _save_plot(self):
        """Save the current plot to an image file with custom dialog."""
        if not self.current_recording:
            return

        from Synaptipy.application.gui.dialogs.plot_export_dialog import PlotExportDialog

        dialog = PlotExportDialog(self)
        if dialog.exec():
            settings = dialog.get_settings()
            fmt = settings["format"]
            dpi = settings["dpi"]

            # Default filename
            default_name = f"plot_{self.current_recording.source_file.stem}.{fmt}"
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save Plot", str(Path.home() / default_name), f"Images (*.{fmt})"
            )

            if filename:
                from Synaptipy.shared.plot_exporter import PlotExporter

                # Provide context for export
                export_config = {
                    "plot_mode": self.current_plot_mode,
                    "current_trial_index": self.current_trial_index,
                    "selected_trial_indices": self.selected_trial_indices,
                    "show_average": self.config_panel.show_avg_btn.isChecked()
                }

                exporter = PlotExporter(
                    recording=self.current_recording,
                    plot_canvas_widget=self.plot_canvas.widget,
                    plot_canvas_wrapper=self.plot_canvas,
                    config=export_config
                )

                try:
                    exporter.export(filename, fmt, dpi)
                    self.status_bar.showMessage(f"Plot saved to {filename}", 3000)
                except Exception as e:
                    self.status_bar.showMessage(f"Error saving plot: {e}", 3000)

        # Helper methods removed in favor of shared.plot_exporter.PlotExporter
        pass

    def _on_trial_selection_requested(self, n, start_index=0):
        """Filter trials to every Nth trial, starting from start_index."""
        if not self.current_recording:
            return

        self.max_trials_current_recording = getattr(self.current_recording, "max_trials", 0)
        all_indices = range(self.max_trials_current_recording)

        # Select every Nth (Gap Logic: Step = N + 1)
        # 0 -> Step 1 (All)
        # 1 -> Step 2 (Every 2nd)
        step = n + 1

        # Validate Start Index
        if start_index < 0:
            start_index = 0

        # Slicing: [start:stop:step]
        self.selected_trial_indices = set(all_indices[start_index::step])

        log.info(
            f"Filtering trials: Start={start_index}, Gap={n} (Step={step}) -> "
            f"{len(self.selected_trial_indices)} trials selected."
        )

        # Store params for preservation
        self._current_trial_selection_params = (n, start_index)

        self.config_panel.update_selection_label(self.selected_trial_indices)
        self._update_plot()

    def _on_trial_selection_reset_requested(self):
        """Reset trial selection to show all (raw data)."""
        self.selected_trial_indices.clear()  # Empty means all
        self._current_trial_selection_params = None  # Clear params
        log.info("Reset trial filtering: All trials selected.")
        self.config_panel.update_selection_label(self.selected_trial_indices)
        self._update_plot()

    def _apply_manual_limits_from_dict(self, limits):
        pass  # Deprecated

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
                pass
            else:
                plot.hide()
        self._update_plot()

    def _auto_select_trials(self):
        # Removed auto-selection logic to avoid interfering with default view (Show All)
        # self.selected_trial_indices = set(range(min(5, self.max_trials_current_recording)))
        pass
