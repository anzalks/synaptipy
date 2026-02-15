# src/Synaptipy/application/gui/analysis_tabs/base.py
# -*- coding: utf-8 -*-
"""
Base class for individual analysis tab widgets. Defines the expected interface
and provides common functionality like selecting the analysis target item.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from abc import ABC, abstractmethod

from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import numpy as np

# Use absolute path to import NeoAdapter and Recording
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.application.controllers.analysis_plot_manager import AnalysisPlotManager
from Synaptipy.shared.styling import (
    style_button,
)
from Synaptipy.shared.plot_zoom_sync import PlotZoomSyncManager
from Synaptipy.application.gui.widgets.preprocessing import PreprocessingWidget

# NEW: Unified Plotting & Pipeline
from Synaptipy.application.gui.widgets.plot_canvas import SynaptipyPlotCanvas
from Synaptipy.core.processing_pipeline import SignalProcessingPipeline
from Synaptipy.application.gui.analysis_worker import AnalysisWorker
from Synaptipy.shared.plot_customization import (
    get_average_pen,
    get_single_trial_pen,
    get_plot_customization_signals
)
from Synaptipy.shared.plot_exporter import PlotExporter
from Synaptipy.application.gui.dialogs.plot_export_dialog import PlotExportDialog

log = logging.getLogger(__name__)


# Custom metaclass to resolve Qt/ABC metaclass conflict
class QABCMeta(type(QtWidgets.QWidget), type(ABC)):
    """Metaclass that combines Qt's metaclass with ABC's metaclass."""

    pass


class BaseAnalysisTab(QtWidgets.QWidget, ABC, metaclass=QABCMeta):
    """Base Class for all analysis sub-tabs."""

    # Removed TRIAL_MODES as it's less relevant now

    def __init__(
        self,
        neo_adapter: NeoAdapter,
        settings_ref: Optional[QtCore.QSettings] = None,
        parent: Optional[QtWidgets.QWidget] = None
    ):
        """
        Initialize the base analysis tab.

        Args:
            neo_adapter: Instance of the NeoAdapter for loading data.
            settings_ref: Reference to QSettings for state persistence.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.neo_adapter = neo_adapter
        self._settings = settings_ref
        self._analysis_items: List[Dict[str, Any]] = []  # Store the full list from AnalyserTab
        self._selected_item_index: int = -1

        # Popup Management
        self._popup_windows: List[QtWidgets.QWidget] = []
        self._analysis_thread: Optional[QtCore.QThread] = None

        # Data placeholders
        # Store the currently loaded recording corresponding to the selected item (if it's a 'Recording' type)
        self._selected_item_recording: Optional[Recording] = None
        # UI element for selecting the analysis item - REMOVED: Now centralized in parent AnalyserTab
        # self.analysis_item_combo: Optional[QtWidgets.QComboBox] = None
        # --- ADDED: Plot Canvas (replaces plot_widget wrapper) ---
        self.plot_canvas: Optional[SynaptipyPlotCanvas] = None
        # self.plot_widget will now reference the main PlotItem for compatibility
        self.plot_widget: Optional[pg.PlotItem] = None
        # --- END ADDED ---
        # --- ADDED: Save Button ---
        self.save_button: Optional[QtWidgets.QPushButton] = None
        # --- END ADDED ---
        # --- ADDED: Zoom Sync Manager ---
        self.zoom_sync: Optional[PlotZoomSyncManager] = None
        # --- END ADDED ---
        # --- ADDED: Reset View Button ---
        self.reset_view_button: Optional[QtWidgets.QPushButton] = None
        # --- END ADDED ---

        # --- ADDED: Preprocessing State ---
        # self.preprocessing_widget initialized below
        self._preprocessed_data: Optional[Dict[str, Any]] = None  # Cached preprocessed data
        self._is_preprocessing: bool = False
        self._active_preprocessing_settings: Optional[Dict[str, Any]] = None  # Persist settings
        # Pipeline
        self.pipeline = SignalProcessingPipeline()
        
        # --- ADDED: Global Analysis Window ---
        self.analysis_region: Optional[pg.LinearRegionItem] = None
        self.restrict_analysis_checkbox: Optional[QtWidgets.QCheckBox] = None
        # --- END ADDED ---

        # --- ADDED: Trial Filtering State ---
        self._filtered_indices: Optional[List[int]] = None
        # --- END ADDED ---

        # --- ADDED: Preprocessing Widget Init ---
        # Initialize early so it's available for layout placement by subclasses
        self.preprocessing_widget = PreprocessingWidget()
        self.preprocessing_widget.preprocessing_requested.connect(self._handle_preprocessing_request)
        # --- END ADDED ---
        
        # --- PHASE 1: Data Selection and Plotting ---
        self.signal_channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        self._current_plot_data: Optional[Dict[str, Any]] = None

        # --- PHASE 2: Analysis Results ---
        self._last_analysis_result: Optional[Dict[str, Any]] = None

        # --- PHASE 3: Debounce Timer for Parameter Changes ---
        self._analysis_debounce_timer: Optional[QtCore.QTimer] = None
        self._debounce_delay_ms: int = 500  # 500ms delay for debouncing

        # Initialize debounce timer
        self._analysis_debounce_timer = QtCore.QTimer(self)
        self._analysis_debounce_timer.setSingleShot(True)
        self._analysis_debounce_timer.timeout.connect(self._trigger_analysis)

        # --- PHASE 2: Threading ---
        self.thread_pool = QtCore.QThreadPool()
        log.debug(f"BaseAnalysisTab initialized with ThreadPool max count: {self.thread_pool.maxThreadCount()}")

        # --- PHASE 4: Session Accumulation ---
        self._accumulated_results: List[Dict[str, Any]] = []
        self.add_to_session_button: Optional[QtWidgets.QPushButton] = None
        self.view_session_button: Optional[QtWidgets.QPushButton] = None

        # --- PHASE 5: Popup Windows and Thread Management ---
        self._popup_windows: List[QtWidgets.QWidget] = []  # Track popup windows for cleanup
        self._analysis_thread: Optional[QtCore.QThread] = None  # Track analysis thread for cleanup

        log.debug(f"Initializing BaseAnalysisTab: {self.__class__.__name__}")

        # Connect Customization Signals
        get_plot_customization_signals().preferences_updated.connect(self._on_plot_preferences_updated)

    def _on_plot_preferences_updated(self):
        """Handle global plot preference changes efficiently."""
        # Only update pens if we have cached data, otherwise do a full re-plot
        if self._current_plot_data and self.plot_widget:
            self._update_plot_pens_only()
        else:
            self._plot_selected_data()

    # --- ADDED: Method to set global controls (Removed duplicate) ---
    # The actual implementation is further down in the file.

    def _setup_toolbar(self, parent_layout: QtWidgets.QLayout) -> None:
        """
        Setup the toolbar with common actions (Reset View, Save Plot).

        Args:
            parent_layout: The layout to add the toolbar to.
        """
        toolbar_layout = QtWidgets.QHBoxLayout()

        # Reset View Button
        self.reset_view_button = QtWidgets.QPushButton("Reset View")
        style_button(self.reset_view_button)
        self.reset_view_button.clicked.connect(self._reset_plot_view)
        toolbar_layout.addWidget(self.reset_view_button)

        # Save Plot Button
        self.save_plot_button = QtWidgets.QPushButton("Save Plot")
        style_button(self.save_plot_button)
        self.save_plot_button.clicked.connect(self._save_plot)
        toolbar_layout.addWidget(self.save_plot_button)

        # Restrict Analysis Checkbox
        self.restrict_analysis_checkbox = QtWidgets.QCheckBox("Restrict Analysis Window")
        self.restrict_analysis_checkbox.setToolTip("Only analyze data within the green region")
        self.restrict_analysis_checkbox.stateChanged.connect(self._toggle_analysis_region)
        toolbar_layout.addWidget(self.restrict_analysis_checkbox)

        toolbar_layout.addStretch()

        parent_layout.addLayout(toolbar_layout)

    def _reset_plot_view(self) -> None:
        """Reset the plot view to default range."""
        if self.plot_widget:
            self.plot_widget.autoRange()

    def _save_plot(self):
        """Save the current plot using the shared PlotExportDialog."""
        if not self.plot_widget:
            QtWidgets.QMessageBox.warning(self, "Export Error", "No plot widget available.")
            return
        if not self._selected_item_recording:
            QtWidgets.QMessageBox.warning(self, "Export Error", "No recording loaded. Please load data first.")
            return

        dialog = PlotExportDialog(self)
        if dialog.exec():
            settings = dialog.get_settings()
            fmt = settings["format"]
            dpi = settings["dpi"]

            # Default filename
            default_name = f"plot_{self._selected_item_recording.source_file.stem}_analysis.{fmt}"
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save Plot", str(Path.home() / default_name), f"Images (*.{fmt})"
            )

            if filename:
                # Provide context for export (Analysis tabs specific)
                export_config = {
                    "plot_mode": "Analysis",  # Custom mode string
                    "selected_trial_indices": self._filtered_indices or "All",
                    "channel": self.signal_channel_combobox.currentText() if self.signal_channel_combobox else "",
                    "data_source": self.data_source_combobox.currentText() if self.data_source_combobox else ""
                }

                exporter = PlotExporter(
                    recording=self._selected_item_recording,
                    plot_canvas_widget=self.plot_widget,
                    plot_canvas_wrapper=None,  # Analysis tabs don't use PlotCanvas wrapper same way
                    config=export_config
                )

                try:
                    exporter.export(filename, fmt, dpi)
                    if hasattr(self, "status_label") and self.status_label:
                        self.status_label.setText(f"Status: Plot saved to {filename}")
                except Exception as e:
                    log.error(f"Error saving plot: {e}")
                    QtWidgets.QMessageBox.critical(self, "Export Error", f"Failed to save plot:\n{e}")

    # --- END ADDED ---

    # --- Methods for UI setup to be called by subclasses ---
    # REMOVED: _setup_analysis_item_selector - now centralized in parent AnalyserTab
    # Subclasses no longer need to call this method

    # --- ADDED: Method to set global controls ---
    def set_global_controls(self, source_list_widget: QtWidgets.QListWidget, item_combo: QtWidgets.QComboBox):
        """
        Receives global control widgets from AnalyserTab and places them at the top
        of the tab's left panel. Subclasses must have 'global_controls_layout' attribute.
        """
        if not hasattr(self, "global_controls_layout") or self.global_controls_layout is None:
            log.warning(f"{self.__class__.__name__}: 'global_controls_layout' not found. Global controls not added.")
            return

        layout = self.global_controls_layout

        # Initialize references to containers if they don't exist
        if not hasattr(self, "_global_source_group"):
            self._global_source_group = None
        if not hasattr(self, "_global_combo_group"):
            self._global_combo_group = None

        # 1. Handle Source List Widget
        if self._global_source_group is None:
            # Create container
            self._global_source_group = QtWidgets.QGroupBox("Analysis Input Set")
            layout_inner = QtWidgets.QVBoxLayout(self._global_source_group)
            layout_inner.setContentsMargins(5, 5, 5, 5)
            # Insert at top
            layout.insertWidget(0, self._global_source_group)

        # Reparent source list to our container
        # Note: addWidget automatically reparents
        self._global_source_group.layout().addWidget(source_list_widget)
        source_list_widget.setVisible(True)

        # 2. Handle Combo Widget
        if self._global_combo_group is None:
            # Create container
            # RENAME: "Analyze Item" -> "Selected File"
            self._global_combo_group = QtWidgets.QGroupBox("Selected File")
            layout_inner = QtWidgets.QVBoxLayout(self._global_combo_group)
            layout_inner.setContentsMargins(5, 5, 5, 5)
            # Insert after source group
            layout.insertWidget(1, self._global_combo_group)

        # Reparent combo to our container
        self._global_combo_group.layout().addWidget(item_combo)
        item_combo.setVisible(True)

        # REMOVED: Preprocessing Widget Injection
        # We now rely on subclasses to place self.preprocessing_widget explicitly
        # where they want it (between Data Source and Params usually).
        
        log.debug(f"{self.__class__.__name__}: Global controls injected/reparented.")

    # --- Preprocessing Logic (Pipeline Integrated) ---
    def _handle_preprocessing_request(self, settings: Dict[str, Any]):
        """
        Handle signal from PreprocessingWidget.
        Updates the pipeline and triggers re-plotting.
        Also notifies parent AnalyserTab to enable global preprocessing.
        Supports multiple filters - same filter type replaces, different types accumulate.
        """
        if self._selected_item_recording is None:
            QtWidgets.QMessageBox.warning(self, "No Data", "No recording loaded to preprocess.")
            return

        self._is_preprocessing = True
        
        # Store settings in slot format - merge with existing
        step_type = settings.get('type')
        if self._active_preprocessing_settings is None:
            self._active_preprocessing_settings = {}
        
        if step_type == 'baseline':
            self._active_preprocessing_settings['baseline'] = settings
        elif step_type == 'filter':
            filter_method = settings.get('method', 'unknown')
            if 'filters' not in self._active_preprocessing_settings:
                self._active_preprocessing_settings['filters'] = {}
            # Same filter method replaces old one
            self._active_preprocessing_settings['filters'][filter_method] = settings

        # Rebuild pipeline from all settings
        self._rebuild_pipeline_from_settings()

        # --- Notify Parent AnalyserTab about preprocessing ---
        # This enables global preprocessing across all sub-tabs
        parent_analyser = self.parent()
        while parent_analyser is not None:
            if hasattr(parent_analyser, "set_global_preprocessing"):
                parent_analyser.set_global_preprocessing(settings if settings else None)
                log.debug("Notified parent AnalyserTab about preprocessing change.")
                break
            parent_analyser = parent_analyser.parent()

        if self.preprocessing_widget:
            self.preprocessing_widget.set_processing_state(True)

        try:
            # Use cached data if available for faster processing
            if self._current_plot_data and "raw_data" in self._current_plot_data:
                self._apply_preprocessing_to_cached_data()
            else:
                # Fallback to full re-plot
                self._plot_selected_data()

            # Processing is synchronous, so just finish up
            self._is_preprocessing = False
            if self.preprocessing_widget:
                self.preprocessing_widget.set_processing_state(False)

        except Exception as e:
            log.error(f"Failed to start preprocessing: {e}", exc_info=True)
            self._on_preprocessing_error(e)

    def apply_global_preprocessing(self, settings):
        """
        Called by parent AnalyserTab to apply global preprocessing.
        Updates local state and re-plots if data is loaded.
        
        Args:
            settings: Can be None (clear), a single step dict, or slot-based dict
        """
        log.debug(f"{self.__class__.__name__}: Applying global preprocessing: {settings is not None}")
        
        if settings is None:
            # Reset all preprocessing
            self._active_preprocessing_settings = None
            self.pipeline.clear()
        elif 'baseline' in settings or 'filters' in settings:
            # Slot-based format - apply all steps
            self._active_preprocessing_settings = settings
            self._rebuild_pipeline_from_settings()
        else:
            # Single step format - accumulate by type
            step_type = settings.get('type')
            if self._active_preprocessing_settings is None:
                self._active_preprocessing_settings = {}
            
            if step_type == 'baseline':
                self._active_preprocessing_settings['baseline'] = settings
            elif step_type == 'filter':
                filter_method = settings.get('method', 'unknown')
                if 'filters' not in self._active_preprocessing_settings:
                    self._active_preprocessing_settings['filters'] = {}
                self._active_preprocessing_settings['filters'][filter_method] = settings
            
            self._rebuild_pipeline_from_settings()
        
        # Re-plot if we have data loaded
        if self._selected_item_recording is not None and self._current_plot_data:
            try:
                if "raw_data" in self._current_plot_data:
                    self._apply_preprocessing_to_cached_data()
                else:
                    self._plot_selected_data()
            except Exception as e:
                log.error(f"Failed to re-plot after global preprocessing: {e}")

    def _rebuild_pipeline_from_settings(self):
        """Rebuild pipeline from current slot-based settings."""
        self.pipeline.clear()
        if self._active_preprocessing_settings:
            # Baseline first
            if 'baseline' in self._active_preprocessing_settings:
                self.pipeline.add_step(self._active_preprocessing_settings['baseline'])
            # Then all filters in sorted order for consistency
            if 'filters' in self._active_preprocessing_settings:
                for method in sorted(self._active_preprocessing_settings['filters'].keys()):
                    self.pipeline.add_step(self._active_preprocessing_settings['filters'][method])

    def _on_preprocessing_complete(self, result_data):
        """
        Legacy callback.
        If result_data is provided, it updates plot.
        If None (from synchronous flow), it does nothing (handled in caller).
        """
        self._is_preprocessing = False
        if self.preprocessing_widget:
            self.preprocessing_widget.set_processing_state(False)

        if result_data is None:
            return

        log.debug("Preprocessing complete (async).")
        # Legacy Handling for async if needed:
        if self._preprocessed_data is None:
            self._preprocessed_data = self._current_plot_data.copy() if self._current_plot_data else {}
        self._preprocessed_data['data'] = result_data

        if self._current_plot_data:
            self._current_plot_data['data'] = result_data

        if self.plot_widget:
            self.plot_widget.clear()
            time = self._current_plot_data.get('time')
            if time is not None:
                self.plot_widget.plot(time, result_data, pen='k')
                self._update_plot_pens_only()
                self._on_data_plotted()

    def _on_preprocessing_error(self, error):
        """Preprocessing failed."""
        self._is_preprocessing = False
        if self.preprocessing_widget:
            self.preprocessing_widget.set_processing_state(False)

        log.error(f"Preprocessing error: {error}")
        QtWidgets.QMessageBox.critical(self, "Processing Error", f"An error occurred:\n{error}")

    def _apply_preprocessing_to_cached_data(self):
        """Apply current pipeline to cached raw data and re-plot efficiently."""
        if not self._current_plot_data or "raw_data" not in self._current_plot_data:
            # Fallback to full re-plot if no cached data
            log.debug("No cached data, falling back to full re-plot")
            self._plot_selected_data()
            return

        raw_data = self._current_plot_data["raw_data"]
        raw_time = self._current_plot_data["raw_time"]
        fs = self._current_plot_data.get("sampling_rate", 1.0)
        chan_id = self._current_plot_data.get("channel_id")

        processed_data = raw_data.copy()
        if self._active_preprocessing_settings and self.pipeline:
            result = self.pipeline.process(raw_data, fs, raw_time)
            if result is not None:
                processed_data = result

        # Update cache with processed data
        self._current_plot_data["data"] = processed_data

        # Clear and re-plot
        self.plot_widget.clear()
        data_source = self._current_plot_data.get("data_source", "")
        trial_pen = get_single_trial_pen()
        avg_pen = get_average_pen()

        # For average, plot individual trials first (background)
        if data_source == "average" and self._selected_item_recording and chan_id:
            channel = self._selected_item_recording.channels.get(chan_id)
            if channel:
                # Get indices to plot
                indices_to_plot = []
                if hasattr(self, "_filtered_indices") and self._filtered_indices:
                    indices_to_plot = sorted(list(self._filtered_indices))
                else:
                    num_trials = getattr(channel, "num_trials", 0)
                    indices_to_plot = list(range(num_trials))

                # Plot each trial with preprocessing
                for trial_idx in indices_to_plot:
                    try:
                        trial_data = channel.get_data(trial_idx)
                        trial_time = channel.get_relative_time_vector(trial_idx)

                        if trial_data is not None and trial_time is not None:
                            if self._active_preprocessing_settings and self.pipeline:
                                processed_trial = self.pipeline.process(trial_data, fs, trial_time)
                                if processed_trial is not None:
                                    trial_data = processed_trial
                            self.plot_widget.plot(trial_time, trial_data, pen=trial_pen)
                    except (ValueError, IndexError) as e:
                        log.debug(f"Could not plot trial {trial_idx}: {e}")

            # Plot average on top
            self.plot_widget.plot(raw_time, processed_data, pen=avg_pen)
        else:
            # Single trial - just plot it
            self.plot_widget.plot(raw_time, processed_data, pen=trial_pen)

        # Restore labels
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", self._current_plot_data.get("channel_name", ""),
                                  units=self._current_plot_data.get("units", ""))

        # Auto-range to fit new data
        self.auto_range_plot()

        self._on_data_plotted()
        log.debug("Preprocessing applied to cached data")

    def _pipeline_process_adapter(
        self, data_in: np.ndarray, fs: float, params: Dict[str, Any], time_vector: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Adapter to make SignalProcessingPipeline compatible with AnalysisPlotManager's callback signature.
        Ignores 'params' as the pipeline is already configured.
        """
        return self.pipeline.process(data_in, fs, time_vector)

    # --- END ADDED ---
    # --- END ADDED ---

    def create_double_input(
        self,
        default_value: str,
        min_val: float = -float("inf"),
        max_val: float = float("inf"),
        decimals: int = 2,
        tooltip: str = "",
    ) -> QtWidgets.QLineEdit:
        """Helper to create a QLineEdit with QDoubleValidator."""
        line_edit = QtWidgets.QLineEdit(default_value)
        validator = QtGui.QDoubleValidator(min_val, max_val, decimals)
        validator.setNotation(QtGui.QDoubleValidator.Notation.StandardNotation)
        line_edit.setValidator(validator)
        if tooltip:
            line_edit.setToolTip(tooltip)
        return line_edit

    def _update_plot_pens_only(self):
        """Efficiently update only the pen properties of existing plot items without recreating data."""
        if not self.plot_widget:
            return

        try:
            # Get current pens from customization manager
            from Synaptipy.shared.plot_customization import get_single_trial_pen, get_average_pen, get_grid_pen

            single_trial_pen = get_single_trial_pen()
            average_pen = get_average_pen()
            grid_pen = get_grid_pen()

            # Update pens for existing plot data items
            # Accessing items on PlotItem directly
            items = self.plot_widget.items if hasattr(self.plot_widget, 'items') else []
            for item in items:
                if isinstance(item, pg.PlotDataItem):
                    # Determine which pen to apply based on item properties or name
                    if hasattr(item, "opts") and "name" in item.opts:
                        item_name = item.opts["name"]
                        if "average" in item_name.lower() or "avg" in item_name.lower():
                            item.setPen(average_pen)
                        else:
                            item.setPen(single_trial_pen)
                    else:
                        # Default to single trial pen if we can't determine the type
                        item.setPen(single_trial_pen)

            # Update grid
            try:
                alpha = grid_pen.alpha() if hasattr(grid_pen, "alpha") else 0.3
                self.plot_widget.showGrid(x=True, y=True, alpha=alpha)
            except Exception as e:
                log.warning(f"Could not update grid: {e}")

            log.debug(f"[ANALYSIS-BASE] Pen update complete for {self.__class__.__name__}")

        except ImportError:
            log.warning(f"Could not import plot customization - skipping pen update for {self.__class__.__name__}")
        except Exception as e:
            log.error(f"Error updating plot pens for {self.__class__.__name__}: {e}")

    # --- ADDED: Method to setup plot area ---
    def _setup_plot_area(self, layout: QtWidgets.QLayout, stretch_factor: int = 1):
        """Adds a SynaptipyPlotCanvas to the provided layout."""
        log.debug(f"[ANALYSIS-BASE] Setting up plot area for {self.__class__.__name__}")

        # Usage of SynaptipyPlotCanvas
        self.plot_canvas = SynaptipyPlotCanvas(parent=self)

        # Add the main analysis plot item
        self.plot_widget = self.plot_canvas.add_plot("main_analysis_plot", row=0, col=0)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel("left", "Amplitude")
        self.plot_widget.setLabel("bottom", "Time", units="s")

        # Standard interaction mode
        vb = self.plot_widget.getViewBox()
        if vb:
            vb.setMouseMode(pg.ViewBox.RectMode)

        # Add windows signal protection? handled by new canvas?
        # Base canvas handles signal protection if needed, but we can verify.
        # For now, rely on canvas.

        self.analysis_region = pg.LinearRegionItem(
            values=[0, 0], orientation=pg.LinearRegionItem.Vertical, 
            brush=pg.mkBrush(0, 255, 0, 50), movable=True
        )
        self.analysis_region.setVisible(False)
        self.analysis_region.setZValue(-10)  # Behind data traces
        self.plot_widget.addItem(self.analysis_region)
        self.analysis_region.sigRegionChanged.connect(self._on_region_changed)
        
        # Add the plot widget (GraphicsLayoutWidget) to layout
        layout.addWidget(self.plot_canvas.widget, stretch=stretch_factor)
        log.debug(f"[ANALYSIS-BASE] Added plot widget to layout for {self.__class__.__name__}")

        # Add Toolbar below the plot
        self._setup_toolbar(layout)

        # Initialize zoom synchronization manager (with the new canvas setup)
        # ZoomSyncManager expects a PlotWidget or we adapt it?
        # It calls widget.getViewBox(). If we pass SynaptipyPlotCanvas.widget, it might fail?
        # PlotZoomSyncManager takes 'plot_widget' usually.
        # If we pass the PlotItem (self.plot_widget), it might work if it uses getViewBox().
        # Let's check `_setup_zoom_sync` implementation below.

        self._setup_zoom_sync()

        log.debug(f"[ANALYSIS-BASE] Plot area setup complete for {self.__class__.__name__}")

    # --- END ADDED ---

    # --- ADDED: Method to setup save button ---
    def _setup_save_button(self, layout: QtWidgets.QLayout, alignment=QtCore.Qt.AlignmentFlag.AlignCenter):
        """Adds a standard 'Save Result' button to the layout and connects it."""
        self.save_button = QtWidgets.QPushButton(f"Save {self.get_display_name()} Result")
        self.save_button.setIcon(QtGui.QIcon.fromTheme("document-save"))  # Optional icon
        self.save_button.setToolTip(
            f"Save the currently calculated {self.get_display_name()} result to the main results list."
        )

        # Use our styling module for consistent appearance
        style_button(self.save_button, "primary")

        self.save_button.setEnabled(False)  # Disabled until a valid result is calculated
        self.save_button.clicked.connect(self._on_save_button_clicked_base)
        # Add button to layout
        if alignment:
            layout.addWidget(self.save_button, 0, alignment)
        else:
            layout.addWidget(self.save_button)
        log.debug(f"{self.__class__.__name__}: Save button setup.")

    # --- END ADDED ---

    # --- ADDED: Helper method to enable/disable save button ---
    def _set_save_button_enabled(self, enabled: bool):
        """Helper method to enable or disable the save button."""
        if hasattr(self, "save_button") and self.save_button:
            was_enabled = self.save_button.isEnabled()
            self.save_button.setEnabled(enabled)
            log.debug(f"{self.__class__.__name__}: Save button set to enabled={enabled} (was={was_enabled})")
        else:
            log.warning(
                f"{self.__class__.__name__}: Cannot set save button enabled={enabled} - save_button not found or None"
            )

    # --- END ADDED ---

    # --- END ADDED ---

    def _setup_reset_view_button(self, layout: QtWidgets.QLayout):
        """Setup reset view button for the plot area."""
        # Create horizontal layout for reset button
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()  # Push button to center

        # Create reset view button with consistent styling
        self.reset_view_button = QtWidgets.QPushButton("Reset View")
        self.reset_view_button.setToolTip("Reset plot zoom and pan to fit all data")

        # Apply consistent button styling
        style_button(self.reset_view_button)

        # Connect to auto-range functionality
        self.reset_view_button.clicked.connect(self._on_reset_view_clicked)

        button_layout.addWidget(self.reset_view_button)

        # Create save plot button
        self.save_plot_button = QtWidgets.QPushButton("Save Plot")
        self.save_plot_button.setToolTip("Save plot as PNG or PDF")

        # Apply consistent button styling
        style_button(self.save_plot_button)

        # Connect to save functionality
        self.save_plot_button.clicked.connect(self._on_save_plot_clicked)

        button_layout.addWidget(self.save_plot_button)
        button_layout.addStretch()  # Push button to center

        # Add button layout to main layout
        layout.addLayout(button_layout)

        log.debug(f"Reset view button setup for {self.__class__.__name__}")

    def _on_reset_view_clicked(self):
        """Handle reset view button click."""
        log.debug(f"[ANALYSIS-BASE] Reset view clicked for {self.__class__.__name__}")
        self.auto_range_plot()
        log.debug(f"[ANALYSIS-BASE] Reset view triggered for {self.__class__.__name__}")

    def _on_save_plot_clicked(self):
        """Handle save plot button click."""
        log.debug(f"[ANALYSIS-BASE] Save plot clicked for {self.__class__.__name__}")

        if not self.plot_widget:
            log.warning("[ANALYSIS-BASE] No plot widget available for saving")
            return

        try:
            from Synaptipy.application.gui.dialogs.plot_export_dialog import PlotExportDialog
            from Synaptipy.shared.plot_exporter import PlotExporter
            from PySide6.QtWidgets import QFileDialog

            # Generate default filename based on tab name
            default_filename = f"{self.__class__.__name__.lower().replace('tab', '')}_plot"

            # 1. Config Dialog
            dialog = PlotExportDialog(self)
            if dialog.exec():
                settings = dialog.get_settings()
                fmt = settings["format"]
                dpi = settings["dpi"]

                # 2. File Dialog
                filename, _ = QFileDialog.getSaveFileName(
                    self, "Save Plot", str(Path.home() / f"{default_filename}.{fmt}"), f"Images (*.{fmt})"
                )

                if filename:
                    # 3. Export
                    exporter = PlotExporter(
                        recording=self._selected_item_recording,  # Can be None as wrapper is None
                        plot_canvas_widget=self.plot_widget
                    )

                    success = exporter.export(filename, fmt, dpi)

                    if success:
                        log.debug(f"[ANALYSIS-BASE] Plot saved successfully for {self.__class__.__name__}")
                        if hasattr(self, "status_label") and self.status_label:
                            self.status_label.setText(f"Status: Plot saved to {Path(filename).name}")
                    else:
                        log.warning(f"[ANALYSIS-BASE] Plot save failed for {self.__class__.__name__}")
            else:
                log.debug("[ANALYSIS-BASE] Plot save cancelled")

        except Exception as e:
            log.error(f"[ANALYSIS-BASE] Failed to save plot for {self.__class__.__name__}: {e}")
            # Show error message to user
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Save Error", f"Failed to save plot:\n{str(e)}")

    def _setup_zoom_sync(self):
        """Initialize the zoom synchronization manager for reset functionality only."""
        if not self.plot_widget:
            return

        self.zoom_sync = PlotZoomSyncManager(self)
        self.zoom_sync.setup_plot_widget(self.plot_widget)

        # Set callback for range changes
        self.zoom_sync.on_range_changed = self._on_plot_range_changed

        # Apply system theme colors to the selection rectangle
        try:
            from Synaptipy.shared.zoom_theme import apply_theme_with_custom_selection

            # Apply custom selection rectangle with theme
            apply_theme_with_custom_selection(self.plot_widget.getViewBox())
        except Exception as e:
            log.debug(f"Failed to apply theme to plot widget: {e}")

        log.debug(f"Zoom sync manager initialized for {self.__class__.__name__} (reset functionality only)")

    def setup_zoom_controls(self, **kwargs):
        """Deprecated method - analysis tabs no longer use zoom controls, only reset view."""
        log.warning(f"setup_zoom_controls called on {self.__class__.__name__} - analysis tabs only use reset view")
        pass

    def set_data_ranges(self, x_range: Tuple[float, float], y_range: Tuple[float, float]):
        """Set the base data ranges for zoom/scroll calculations. Call this when plotting new data."""
        if self.zoom_sync:
            self.zoom_sync.set_base_ranges(x_range, y_range)
            log.debug(f"Data ranges set: X={x_range}, Y={y_range}")

    def auto_range_plot(self):
        """Auto-range the plot to fit all data."""
        log.debug(f"[ANALYSIS-BASE] Auto-ranging plot for {self.__class__.__name__}")
        if self.zoom_sync:
            log.debug("[ANALYSIS-BASE] Using zoom sync auto-range")
            self.zoom_sync.auto_range()
        elif self.plot_widget:
            log.debug("[ANALYSIS-BASE] Using direct plot widget auto-range")
            self.plot_widget.autoRange()
        else:
            log.warning("[ANALYSIS-BASE] No plot widget available for auto-range")

    def _setup_windows_signal_protection(self, viewbox):
        """Setup signal protection for Windows to prevent rapid range changes."""
        try:
            # Simple debouncing by limiting rapid range changes
            def debounced_range_handler(signal_name):
                def handler(vb, range_data):
                    # Simple debouncing - prevent excessive calls
                    attr_name = f"_last_{signal_name}_change"
                    if not hasattr(self, attr_name):
                        setattr(self, attr_name, 0)
                    import time

                    now = time.time()
                    last_change = getattr(self, attr_name)
                    if now - last_change < 0.1:  # 100ms debounce for Windows
                        return
                    setattr(self, attr_name, now)
                    log.debug(f"[ANALYSIS-BASE] {signal_name} range change allowed for {self.__class__.__name__}")

                return handler

            # Connect simple debouncing handlers to prevent rapid range changes
            viewbox.sigXRangeChanged.connect(debounced_range_handler("x"))
            viewbox.sigYRangeChanged.connect(debounced_range_handler("y"))

            log.debug(f"[ANALYSIS-BASE] Windows signal protection setup complete for {self.__class__.__name__}")
        except Exception as e:
            log.warning(f"[ANALYSIS-BASE] Failed to setup Windows signal protection: {e}")

    def _on_plot_range_changed(self, axis: str, new_range: Tuple[float, float]):
        """Called when plot range changes from any source (zoom, scroll, manual)."""
        # Subclasses can override this to handle range changes
        # For example, to update analysis regions or recalculate results
        pass

    # ViewBox state change handler
    def _on_viewbox_changed(self):
        """Handles view box state changes (like zoom/pan) - now handled by zoom sync manager."""
        # The zoom sync manager now handles all range synchronization
        # This method is kept for backward compatibility
        pass

    # Add stub method for mouse click handling
    def _handle_mouse_click(self, ev):
        """Default handler for mouse clicks on the plot."""
        # By default, just pass the event to the original handler
        if hasattr(self, "plot_widget") and self.plot_widget and self.plot_widget.getViewBox():
            # Auto-range on double-click
            if ev.double():
                self.plot_widget.getViewBox().autoRange()
                # Prevent further processing
                ev.accept()
            else:
                # Ensure original mouse behavior is preserved
                pg.ViewBox.mouseClickEvent(self.plot_widget.getViewBox(), ev)

    # --- Method called by AnalyserTab when the analysis set changes ---
    def update_state(self, analysis_items: List[Dict[str, Any]]):
        """
        Update the state based on the list of analysis items provided by AnalyserTab.
        Now simplified - only updates internal data without managing combo box.
        """
        log.debug(f"{self.__class__.__name__}: Updating state with {len(analysis_items)} items.")
        self._analysis_items = analysis_items
        # Clear currently loaded data when the list changes
        self._selected_item_recording = None
        self._selected_item_index = -1
        # Clear preprocessing cache
        self._preprocessed_data = None
        self._active_preprocessing_settings = None
        self._current_plot_data = None  # Clear plot context
        self.pipeline.clear()

        # Clear plot when items change
        if self.plot_widget:
            self.plot_widget.clear()

        log.debug(f"{self.__class__.__name__}: State updated, ready for item selection from parent.")

    # --- Internal Slot for Item Selection Change ---
    @QtCore.Slot(int)
    def _on_analysis_item_selected(self, index: int):
        """Handles the selection change in the analysis item combo box."""
        self._selected_item_index = index
        self._selected_item_recording = None  # Clear previous loaded recording
        self._preprocessed_data = None  # Clear preprocessing cache on new item
        self._active_preprocessing_settings = None  # Clear settings on new item
        self._current_plot_data = None  # Reset plot data context immediately
        self.pipeline.clear()

        if index < 0 or index >= len(self._analysis_items):
            log.debug(f"{self.__class__.__name__}: No valid analysis item selected (index {index}).")
            # Still need to update UI to reflect empty state
            try:
                self._update_ui_for_selected_item()
            except Exception as e:
                log.error(f"Error calling _update_ui_for_selected_item on empty selection: {e}", exc_info=True)
            return

        selected_item = self._analysis_items[index]
        item_path = selected_item.get("path")
        item_type = selected_item.get("target_type")

        log.debug(f"{self.__class__.__name__}: Selected analysis item {index}: Type={item_type}, Path={item_path}")

        # Show Loading State if we have a status label or similar
        # For now, we can maybe set the cursor?
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        self.setEnabled(False)  # Disable interaction while loading

        # Clear plot immediately
        if self.plot_widget:
            self.plot_widget.clear()

        # Define the loading task
        def load_task(path):
            if not path:
                return None
            return self.neo_adapter.read_recording(path)

        # Launch Worker
        worker = AnalysisWorker(load_task, item_path)
        worker.signals.result.connect(self._on_item_load_success)
        worker.signals.error.connect(self._on_item_load_error)
        # We can also connect finished to restore cursor
        worker.signals.finished.connect(self._on_item_load_finished)

        log.debug(f"{self.__class__.__name__}: Starting async load for {item_path}")
        self.thread_pool.start(worker)

    def _on_item_load_success(self, recording: Optional[Recording]):
        """Callback when async loading completes successfully."""
        self._selected_item_recording = recording
        self._current_plot_data = None  # Force reset of view state for new recording

        # Re-enable widget immediately so UI updates (which check isEnabled) can succeed
        self.setEnabled(True)
        QtWidgets.QApplication.restoreOverrideCursor()

        if recording:
            log.debug(f"{self.__class__.__name__}: Async load success. Channels: {len(recording.channels)}")
        else:
            log.warning(f"{self.__class__.__name__}: Async load returned None/Empty.")

        # --- Check for global preprocessing from parent AnalyserTab ---
        self._apply_global_preprocessing_from_parent()

        # Trigger UI update
        try:
            # PHASE 1: Populate channel and data source comboboxes if they exist
            if self.signal_channel_combobox and self.data_source_combobox:
                self._populate_channel_and_source_comboboxes()

            self._update_ui_for_selected_item()
        except Exception as e:
            log.error(f"Error updating UI after load: {e}", exc_info=True)

    def _apply_global_preprocessing_from_parent(self):
        """Check parent AnalyserTab for global preprocessing and apply if active.
        
        Falls back to checking SessionManager directly if parent doesn't have
        global preprocessing set yet (e.g., before popup confirmation).
        """
        global_settings = None
        
        # First try parent AnalyserTab's global preprocessing
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "get_global_preprocessing"):
                global_settings = parent.get_global_preprocessing()
                break
            parent = parent.parent()
        
        # Fallback: check SessionManager directly (for preprocessing set in Explorer
        # but not yet confirmed via popup in AnalyserTab)
        if not global_settings:
            try:
                from Synaptipy.application.session_manager import SessionManager
                session_settings = SessionManager.instance().preprocessing_settings
                if session_settings:
                    global_settings = session_settings
                    log.debug(f"{self.__class__.__name__}: Using preprocessing from SessionManager")
            except Exception as e:
                log.debug(f"Could not check SessionManager for preprocessing: {e}")
        
        if global_settings:
            log.debug(f"{self.__class__.__name__}: Applying global preprocessing from parent")
            self._active_preprocessing_settings = global_settings
            self._rebuild_pipeline_from_settings()

    def _on_item_load_error(self, err_tuple):
        """Callback when async loading fails."""
        exctype, value, tb_str = err_tuple
        log.error(f"{self.__class__.__name__}: Async load failed: {value}")
        log.debug(f"Traceback: {tb_str}")

        # Re-enable widget
        self.setEnabled(True)
        QtWidgets.QApplication.restoreOverrideCursor()

        QtWidgets.QMessageBox.critical(self, "Load Error", f"Failed to load data:\n{value}")
        self._selected_item_recording = None

        # Still update UI to reflect potential empty state or error state
        # Still update UI to reflect potential empty state or error state
        try:
            self._update_ui_for_selected_item()
        except Exception:
            pass

    def _on_item_load_finished(self):
        """Cleanup after loading (success or error)."""
        # Redundant safety measure
        if not self.isEnabled():
            self.setEnabled(True)
            QtWidgets.QApplication.restoreOverrideCursor()
        log.debug(f"{self.__class__.__name__}: Async load finished.")

    # --- ADDED: Base slot for save button click ---
    @QtCore.Slot()
    def _on_save_button_clicked_base(self):
        """Handles the save button click, gets specific data, and requests save."""
        log.debug(f"{self.get_display_name()}: Save button clicked (base slot).")
        try:
            specific_data = self._get_specific_result_data()
            if specific_data is not None:
                self._request_save_result(specific_data)
                # Provide visual feedback to the user
                if hasattr(self, "status_label") and self.status_label:
                    self.status_label.setText("Status: Results saved successfully")
            else:
                log.warning("Save requested, but _get_specific_result_data returned None.")
                QtWidgets.QMessageBox.warning(self, "Save Error", "No valid result available to save.")

                # Disable the save button as a precaution
                self._set_save_button_enabled(False)
        except NotImplementedError:
            log.error(
                f"Subclass {self.__class__.__name__} must implement _get_specific_result_data() to enable saving."
            )
            QtWidgets.QMessageBox.critical(self, "Save Error", "Save functionality not implemented for this tab.")
        except Exception as e:
            log.error(f"Error getting specific result data in {self.__class__.__name__}: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Error preparing result for saving:\n{e}")

    # --- END ADDED ---

    # --- Abstract Methods / Methods Subclasses MUST Implement ---
    @abstractmethod
    def get_registry_name(self) -> str:
        """
        Return the unique name used to register the analysis function in AnalysisRegistry.
        Must be implemented by subclasses if they correspond to a specific analysis.
        """
        return "unknown_analysis"

    def get_covered_analysis_names(self) -> List[str]:
        """
        Return a list of all registry names covered by this tab.
        Used by AnalyserTab to prevent loading duplicate generic tabs.
        """
        return [self.get_registry_name()]

    @abstractmethod
    def get_display_name(self) -> str:
        """Return the display name for this analysis tab."""
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement get_display_name()")

    @abstractmethod
    def _setup_ui(self):
        """
        Set up the UI for this analysis tab.
        Subclass implementation SHOULD call self._setup_plot_area(layout) somewhere appropriate.
        Subclass implementation CAN call self._setup_save_button(layout) to add the save button.
        NOTE: Item selector is now centralized in parent AnalyserTab, no need to add it here.
        """
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement _setup_ui()")

    @abstractmethod
    def _update_ui_for_selected_item(self):
        """
        Subclasses MUST implement this method.
        Called AFTER an item is selected in the `analysis_item_combo` and
        `self._selected_item_recording` has been potentially loaded.
        Subclass should update its specific UI elements (e.g., channel/trial
        selectors, input fields) based on the data in `self._selected_item_recording`
        or the details in `self._analysis_items[self._selected_item_index]`.
        Should also handle the case where `self._selected_item_recording` is None (load failed).
        Typically, this method should also trigger plotting the relevant data.
        """
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement _update_ui_for_selected_item()")

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """
        Subclasses MUST implement this method if they use the save button.
        It should gather the specific results (value, units, parameters, etc.)
        from the tab's UI elements and return them as a dictionary.
        Return None if no valid result is currently available.
        The dictionary should NOT include common metadata like filename, analysis_type,
        timestamp, etc., as those are added by _request_save_result.
        It MUST include the 'data_source' key if applicable (value is 'average' or trial index).
        """
        # Default implementation returns None, indicating save is not supported or no result
        # or raise NotImplementedError explicitly if button setup *requires* implementation
        log.warning(f"{self.__class__.__name__}._get_specific_result_data() is not implemented.")
        return None

    # --- PHASE 2: Analysis Result Handling ---

    @QtCore.Slot(object)
    def _on_analysis_result(self, results):
        """Handle successful analysis results from worker."""
        if results is None:
            log.warning("Analysis returned None.")
            if hasattr(self, "status_label") and self.status_label:
                self.status_label.setText("Status: Analysis failed (no result).")
            self._set_save_button_enabled(False)
            return

        log.debug(f"{self.__class__.__name__}: Analysis finished successfully.")

        # CRITICAL FIX: Store the results so save button can access them
        self._last_analysis_result = results

        # 4. Update UI (UI Thread)
        self._display_analysis_results(results)
        self._plot_analysis_visualizations(results)

        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setText("Status: Analysis complete.")

        # Enable save button if we have results
        self._set_save_button_enabled(True)

        # Update Accumulation UI state
        self._update_accumulation_ui_state()

    @QtCore.Slot(tuple)
    def _on_analysis_error(self, error_info):
        """Handle analysis errors."""
        exctype, value, traceback_str = error_info
        log.error(f"{self.__class__.__name__}: Analysis error: {value}\n{traceback_str}")
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setText(f"Status: Error: {value}")

        QtWidgets.QMessageBox.critical(self, "Analysis Error", f"An error occurred during analysis:\n{value}")

    def _toggle_analysis_region(self, state):
        """Toggle visibility of the analysis region."""
        visible = (state == QtCore.Qt.CheckState.Checked.value)
        if self.analysis_region and self.plot_widget:
            if visible:
                # Add if not already added (check items list or just try add)
                if self.analysis_region not in self.plot_widget.items:
                    self.plot_widget.addItem(self.analysis_region)
                self.analysis_region.setVisible(True)
            else:
                self.analysis_region.setVisible(False)
                # Remove to prevent auto-ranging issues
                if self.analysis_region in self.plot_widget.items:
                    self.plot_widget.removeItem(self.analysis_region)

        # Trigger re-analysis
        self._trigger_analysis()

    def _on_region_changed(self):
        """Handle region drag."""
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

    # --- PHASE 2: Abstract Methods for Template Method Pattern ---
    # BUG 2 FIX: These are the ONLY declarations of these methods - no duplicates

    @abstractmethod
    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """
        Gather analysis parameters from UI widgets.

        Returns:
            Dictionary containing all parameters needed for analysis.
            Return empty dict if parameters are invalid.
        """
        pass

    @abstractmethod
    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Execute the core analysis logic.

        Args:
            params: Parameters gathered from _gather_analysis_parameters
            data: Current plot data dictionary

        Returns:
            Dictionary containing analysis results, or None if analysis fails.
            NOTE: Return type is Optional to allow returning None on failure.
        """
        pass

    @abstractmethod
    def _display_analysis_results(self, results: Dict[str, Any]):
        """
        Display analysis results in UI widgets.

        Args:
            results: Analysis results dictionary from _execute_core_analysis
        """
        pass

    @abstractmethod
    def _plot_analysis_visualizations(self, results: Dict[str, Any]):
        """
        Update plot with analysis-specific visualizations (markers, lines, etc.).

        Args:
            results: Analysis results dictionary from _execute_core_analysis
        """
        pass

    # --- PHASE 1: Data Selection and Plotting Infrastructure ---
    def _setup_data_selection_ui(self, layout: QtWidgets.QLayout):
        """
        Adds channel and data source selection combo boxes to the provided layout.
        Called by subclasses in their _setup_ui method.
        """
        # --- Group 1: Data Source ---
        data_group = QtWidgets.QGroupBox("Data Source")
        dg_layout = QtWidgets.QVBoxLayout(data_group)

        # Signal Channel Selection
        self.signal_channel_combobox = QtWidgets.QComboBox()
        self.signal_channel_combobox.setToolTip("Select the signal channel to plot and analyze.")
        self.signal_channel_combobox.setEnabled(False)

        hbox1 = QtWidgets.QHBoxLayout()
        hbox1.addWidget(QtWidgets.QLabel("Signal Channel:"))
        hbox1.addWidget(self.signal_channel_combobox, stretch=1)
        dg_layout.addLayout(hbox1)

        # Data Source Selection (Trial vs Average)
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)

        hbox2 = QtWidgets.QHBoxLayout()
        hbox2.addWidget(QtWidgets.QLabel("Data Source:"))
        hbox2.addWidget(self.data_source_combobox, stretch=1)
        dg_layout.addLayout(hbox2)

        # Add Data Group to parent (handles FormLayout check if needed, but usually VBox)
        if isinstance(layout, QtWidgets.QFormLayout):
            layout.addRow(data_group)
        else:
            layout.addWidget(data_group)

        # --- Group 2: Plot Selected Trials ---
        # User requested consistency with Explorer Tab filtering
        pst_group = QtWidgets.QGroupBox("Plot Selected Trials")
        pst_layout = QtWidgets.QVBoxLayout(pst_group)
        pst_layout.setSpacing(10)

        # Input Row
        in_layout = QtWidgets.QHBoxLayout()
        in_layout.addWidget(QtWidgets.QLabel("Trial Gap (Skip N):"))
        self.nth_trial_input = QtWidgets.QLineEdit()
        self.nth_trial_input.setPlaceholderText("e.g. 0=All, 1=Every 2nd")
        self.nth_trial_input.setValidator(QtGui.QIntValidator(0, 9999))
        self.nth_trial_input.returnPressed.connect(self._on_plot_filtered_trials)
        in_layout.addWidget(self.nth_trial_input)

        in_layout.addWidget(QtWidgets.QLabel("Start Trial:"))
        self.start_trial_input = QtWidgets.QLineEdit()
        self.start_trial_input.setPlaceholderText("0")
        self.start_trial_input.setValidator(QtGui.QIntValidator(0, 9999))
        self.start_trial_input.setText("0")
        self.start_trial_input.returnPressed.connect(self._on_plot_filtered_trials)
        in_layout.addWidget(self.start_trial_input)

        pst_layout.addLayout(in_layout)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.select_trials_button = QtWidgets.QPushButton("Plot Selected")
        self.select_trials_button.clicked.connect(self._on_plot_filtered_trials)
        self.select_trials_button.setToolTip("Filter trials to show only every Nth trial.")
        btn_layout.addWidget(self.select_trials_button)

        self.reset_selection_btn = QtWidgets.QPushButton("Reset")
        self.reset_selection_btn.clicked.connect(self._reset_trial_filtering)
        btn_layout.addWidget(self.reset_selection_btn)

        pst_layout.addLayout(btn_layout)

        if isinstance(layout, QtWidgets.QFormLayout):
            layout.addRow(pst_group)
        else:
            layout.addWidget(pst_group)

        # Connect signals to trigger plotting when selection changes
        self.signal_channel_combobox.currentIndexChanged.connect(self._plot_selected_data)
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_data)

        log.debug(f"{self.__class__.__name__}: Data selection UI setup complete")

    def _reset_trial_filtering(self):
        """Reset trial filter inputs and plot filtered trials default (all?). No, maybe just clears overlay."""
        self.nth_trial_input.clear()
        self.start_trial_input.setText("0")

        # Clear filter state
        self._filtered_indices = None

        self._plot_selected_data()  # Reverts to single trial view

    def _on_plot_filtered_trials(self):
        """
        Parse inputs and plot filtered trials.
        Replica of ExplorerTab logic.
        """
        text_gap = self.nth_trial_input.text().strip()
        text_start = self.start_trial_input.text().strip()

        if not self._selected_item_recording:
            return

        # Get number of trials from first channel
        first_channel = next(iter(self._selected_item_recording.channels.values()), None)
        num_trials = getattr(first_channel, "num_trials", 0) if first_channel else 0

        if num_trials == 0:
            return

        start_idx = 0

        try:
            if text_gap:
                gap = int(text_gap)
            else:
                gap = 0  # Default to All (Gap 0)
            start_idx = int(text_start) if text_start else 0
        except ValueError:
            log.warning("Invalid input for trial selection.")
            return

        selected_indices = []
        # Gap Logic: Step = Gap + 1
        # Gap 0 -> Step 1 (All)
        # Gap 1 -> Step 2 (Every 2nd)
        step = gap + 1

        # Guard against zero step (shouldn't happen with gap >= 0)
        if step < 1:
            step = 1

        for i in range(start_idx, num_trials, step):
            selected_indices.append(i)

        log.info(
            f"Trial Selection: Gap={gap} (Step={step}), Start={start_idx} -> Found {len(selected_indices)} trials."
        )

        if selected_indices:
            # Store state and redraw using main loop
            self._filtered_indices = set(selected_indices)
            self._plot_selected_data()
        else:
            log.warning("No trials matched selection criteria (Indices empty).")
            # FIX: Clear previous filter so we don't show old data
            self._filtered_indices = None
            QtWidgets.QMessageBox.information(self, "Trial Selection", "No trials matched your criteria.")
            # Refresh plot (revert to default/all?)
            self._plot_selected_data()

    # Removed _open_trial_selection_dialog as we use filtering now

    def _plot_multi_trials(self, trial_indices):
        """Plot multiple trials overlaid."""
        if not self.plot_widget or not self._selected_item_recording:
            return

        chan_id = self.signal_channel_combobox.currentData()
        if chan_id is None:
            return

        channel = self._selected_item_recording.channels.get(chan_id)
        if not channel:
            return

        self.plot_widget.clear()
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", channel.name or f"Ch {chan_id}", units=channel.units)
        self.plot_widget.setTitle(f"{channel.name} - Selected Trials ({len(trial_indices)})")

        # Color cycle
        colors = ['r', 'g', 'b', 'c', 'm', 'y']

        for i, trial_idx in enumerate(sorted(list(trial_indices))):
            data = channel.get_data(trial_idx)
            time = channel.get_relative_time_vector(trial_idx)

            if data is not None and time is not None:
                color = colors[i % len(colors)]
                self.plot_widget.plot(time, data, pen=pg.mkPen(color, width=1), name=f"Trial {trial_idx + 1}")

        # Update current plot data to match what analysis might expect?
        # CAUTION: Analysis functions usually expect ONE trial or Average.
        # If we plot multiple, does analysis run on all?
        # Typically analysis runs on what is selected in the combobox.
        # Plotting multiple is usually just for visualization.
        # So we might NOT update _current_plot_data, or update it to None to prevent analysis on mixed data?
        # Or just leave specific selection as "Data Source" active.

        # Let's verify: user wants "plot selected trials" option.
        # They probably just want to see them.
        # If they run analysis, it should probably run on the "Data Source" selection?
        # Or should we disable analysis?
        # For now, let's keep it simple: Visualization only.
        pass

    def _populate_channel_and_source_comboboxes(self):
        """
        Populate channel and data source comboboxes based on the currently loaded recording.
        Called automatically by the base class when an analysis item is selected.
        """
        log.debug(f"{self.__class__.__name__}: Populating channel and source comboboxes")

        # Clear previous selections
        self.signal_channel_combobox.blockSignals(True)
        self.data_source_combobox.blockSignals(True)
        self.signal_channel_combobox.clear()
        self.data_source_combobox.clear()

        has_channels = False

        # Populate Channel ComboBox
        if self._selected_item_recording and self._selected_item_recording.channels:
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                units = getattr(channel, "units", "")
                display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{units}]"
                self.signal_channel_combobox.addItem(display_name, userData=chan_id)
                has_channels = True

        if not has_channels:
            log.warning(f"{self.__class__.__name__}: No channels found in loaded recording!")
            self.signal_channel_combobox.addItem("No Channels Found")
            self.signal_channel_combobox.setEnabled(False)
            self.data_source_combobox.addItem("N/A")
            self.data_source_combobox.setEnabled(False)
            self.signal_channel_combobox.blockSignals(False)
            self.data_source_combobox.blockSignals(False)
            return

        self.signal_channel_combobox.setEnabled(True)
        self.signal_channel_combobox.setCurrentIndex(0)

        # Populate Data Source ComboBox
        selected_item_details = (
            self._analysis_items[self._selected_item_index] if self._selected_item_index >= 0 else {}
        )
        item_type = selected_item_details.get("target_type")
        item_trial_index = selected_item_details.get("trial_index")

        # Get trial info from first channel
        first_channel = next(iter(self._selected_item_recording.channels.values()), None)
        num_trials = 0

        if first_channel:
            num_trials = getattr(first_channel, "num_trials", 0)

        # Populate based on item type
        if item_type == "Current Trial" and item_trial_index is not None and 0 <= item_trial_index < num_trials:
            self.data_source_combobox.addItem(f"Trial {item_trial_index + 1}", userData=item_trial_index)
        elif item_type == "Average Trace":
            self.data_source_combobox.addItem("Average Trace", userData="average")
        else:  # "Recording" or "All Trials"
            # Always add "Average Trace" (Overlay) option so users can see all trials even if no average exists
            self.data_source_combobox.addItem("Average Trace", userData="average")
            for i in range(num_trials):
                self.data_source_combobox.addItem(f"Trial {i + 1}", userData=i)

        if self.data_source_combobox.count() > 0:
            self.data_source_combobox.setEnabled(True)
        else:
            log.warning(f"{self.__class__.__name__}: No trials or average data found.")
            self.data_source_combobox.addItem("No Data Available")
            self.data_source_combobox.setEnabled(False)

        # Enable/Disable Select Trials Button
        if hasattr(self, "select_trials_button") and self.select_trials_button:
            self.select_trials_button.setEnabled(num_trials > 0)

        self.signal_channel_combobox.blockSignals(False)
        self.data_source_combobox.blockSignals(False)

        log.debug(f"{self.__class__.__name__}: Comboboxes populated - triggering plot")
        self._plot_selected_data()

    @QtCore.Slot()
    def _plot_selected_data(self):
        """
        Centralized plotting method that fetches data based on selected channel and source,
        plots it, and calls the _on_data_plotted hook for subclass-specific additions.
        """
        log.debug(f"{self.__class__.__name__}: Plotting selected data")
        

        if not self.plot_widget:
            log.error(f"{self.__class__.__name__}: Plot widget is None!")
            return

        if not self.signal_channel_combobox.isEnabled() or not self.data_source_combobox.isEnabled():
            log.debug(f"{self.__class__.__name__}: Comboboxes disabled, skipping plot")
            self.plot_widget.clear()
            return

        chan_id = self.signal_channel_combobox.currentData()
        data_source = self.data_source_combobox.currentData()

        if chan_id is None or data_source is None:
            log.debug(f"{self.__class__.__name__}: Invalid selection (chan={chan_id}, source={data_source})")
            self.plot_widget.clear()
            return

        if not self._selected_item_recording or chan_id not in self._selected_item_recording.channels:
            log.error(f"{self.__class__.__name__}: Channel {chan_id} not found in recording")
            self.plot_widget.clear()
            return

        # channel = self._selected_item_recording.channels[chan_id] # Unused now as Manager handles it

        try:
            # 0. Preserve View State (Sticky Zoom Logic)
            view_state = None
            should_preserve_view = False

            if self.plot_widget:
                view_state = self.plot_widget.viewRange()

                # Logic: Preserve view if preprocessing active OR if user is zoomed in
                # Logic: Preserve view if preprocessing active AND we have existing data
                # (Prevents locking to default 0-1 view on first load with global preprocessing)
                # (Prevents locking to default 0-1 view on first load with global preprocessing)
                if self._active_preprocessing_settings and self._current_plot_data:
                    should_preserve_view = True
                elif self._current_plot_data and "time" in self._current_plot_data:
                    # Check if zoomed in (> 5% reduction from full range)
                    try:
                        data_time = self._current_plot_data["time"]
                        if len(data_time) > 1:
                            # Use finite min/max in case of NaNs, or just first/last if sorted
                            # Time is usually sorted
                            data_span = float(data_time[-1] - data_time[0])

                            current_x_view = view_state[0]
                            view_span = float(current_x_view[1] - current_x_view[0])

                            # If view covers less than 95% of data, consider it zoomed
                            # Also check if we are significantly panned away (center shift)
                            # But span check is usually sufficient for "zoomed in"
                            if data_span > 0 and (view_span / data_span) < 0.95:
                                should_preserve_view = True
                    except Exception as e:
                        log.debug(f"Error checking zoom state: {e}")

            # 1. Clear plot
            self.plot_widget.clear()

            # 2. Get Plot Data via Manager
            plot_package = AnalysisPlotManager.prepare_plot_data(
                recording=self._selected_item_recording,
                channel_id=chan_id,
                data_source=data_source,
                preprocessing_settings=self._active_preprocessing_settings,
                filtered_indices=self._filtered_indices if hasattr(self, "_filtered_indices") else None,
                process_callback=self._pipeline_process_adapter
            )

            if not plot_package:
                log.warning(f"{self.__class__.__name__}: Plot Manager returned no data.")
                return

            # 3. Plot Context Traces
            # Use customized single trial pen for context
            trial_pen = get_single_trial_pen()
            avg_pen = get_average_pen()

            for ctx_trace in plot_package.context_traces:
                self.plot_widget.plot(ctx_trace.time, ctx_trace.data, pen=trial_pen)

            # 4. Plot Main Trace
            # When average is selected, plot all trials underneath with transparency
            if plot_package.data_source == "average":
                log.debug(f"[TRIAL-OVERLAY] data_source is 'average', plotting background trials")
                # Get indices used for this average
                indices_to_plot = []
                if hasattr(self, "_filtered_indices") and self._filtered_indices:
                    indices_to_plot = sorted(list(self._filtered_indices))
                    log.debug(f"[TRIAL-OVERLAY] Using filtered indices: {len(indices_to_plot)} trials")
                else:
                    # If no specific filter is set, plot ALL trials
                    # (This is the standard behavior: show population behind average)
                    channel = self._selected_item_recording.channels.get(chan_id)
                    if channel:
                        # Try multiple ways to get trial count
                        num_trials = getattr(channel, "num_trials", 0)
                        if num_trials == 0:
                            # Fallback: check data_trials length
                            num_trials = len(getattr(channel, "data_trials", []))
                        if num_trials == 0:
                            # Fallback: check trial_count
                            num_trials = getattr(channel, "trial_count", 0)
                        indices_to_plot = list(range(num_trials))
                        log.debug(f"[TRIAL-OVERLAY] No filter, using all {num_trials} trials")
                    else:
                        log.warning(f"[TRIAL-OVERLAY] Channel {chan_id} not found in recording")

                # If valid indices found, plot them
                if indices_to_plot:
                    channel = self._selected_item_recording.channels.get(chan_id)
                    if channel:
                        for trial_idx in indices_to_plot:
                            try:
                                trial_data = channel.get_data(trial_idx)
                                trial_time = channel.get_relative_time_vector(trial_idx)

                                if trial_data is not None and trial_time is not None:
                                    # Apply any preprocessing if active
                                    if self._active_preprocessing_settings:
                                        processed = self.pipeline.process(
                                            trial_data,
                                            plot_package.sampling_rate,
                                            trial_time
                                        )
                                        if processed is not None:
                                            trial_data = processed

                                    self.plot_widget.plot(trial_time, trial_data, pen=trial_pen)
                            except Exception as e:
                                log.debug(f"Could not plot trial {trial_idx}: {e}")

                # Plot the average on top
                self.plot_widget.plot(
                    plot_package.main_time, plot_package.main_data,
                    pen=avg_pen, name=plot_package.label
                )
            else:
                # Single trial selected - just plot it
                self.plot_widget.plot(
                    plot_package.main_time, plot_package.main_data,
                    pen=trial_pen, name=plot_package.label
                )

            self.plot_widget.setLabel("bottom", "Time", units="s")
            self.plot_widget.setLabel("left", plot_package.channel_name, units=plot_package.units)
            self.plot_widget.setTitle(f"{plot_package.channel_name} - {plot_package.label}")

            if len(plot_package.main_time) > 0 and len(plot_package.main_data) > 0:
                x_range = (float(np.min(plot_package.main_time)), float(np.max(plot_package.main_time)))
                y_range = (float(np.min(plot_package.main_data)), float(np.max(plot_package.main_data)))
                self.set_data_ranges(x_range, y_range)

            # 6. Store State (including raw data for efficient preprocessing)
            self._current_plot_data = {
                "data": plot_package.main_data,
                "time": plot_package.main_time,
                "raw_data": plot_package.main_data.copy(),  # Cache raw for preprocessing
                "raw_time": plot_package.main_time.copy(),  # Cache raw time
                "channel_id": plot_package.channel_id,
                "data_source": plot_package.data_source,
                "units": plot_package.units,
                "sampling_rate": plot_package.sampling_rate,
                "channel_name": plot_package.channel_name,
            }

            # 7. Auto-range or Restore View
            # Apply Sticky Zoom Logic
            if should_preserve_view and view_state:
                # User was zoomed or processing active -> Keep the view
                self.plot_widget.setRange(xRange=view_state[0], yRange=view_state[1], padding=0)
            else:
                # User was in full view (or first plot) -> Auto-range to new data
                self.auto_range_plot()

            # 8. Update analysis_region defaults (25-75% of time range)
            if getattr(self, "analysis_region", None) and len(plot_package.main_time) > 1:
                t_min = float(plot_package.main_time[0])
                t_max = float(plot_package.main_time[-1])
                t_span = t_max - t_min
                self.analysis_region.setRegion([t_min + 0.25 * t_span, t_min + 0.75 * t_span])

            self._on_data_plotted()

        except Exception as e:
            log.error(f"{self.__class__.__name__}: Error plotting data: {e}", exc_info=True)
            self.plot_widget.clear()
            self._current_plot_data = None

    def _on_data_plotted(self):
        """
        Hook method called after data has been successfully plotted by the base class.
        Subclasses should override this to add their specific plot items (e.g., regions, markers).
        """
        # Base implementation handles analysis_region re-addition
        if self.analysis_region and self.restrict_analysis_checkbox.isChecked():
            if self.plot_widget and self.analysis_region not in self.plot_widget.items():
                self.plot_widget.addItem(self.analysis_region)
            self.analysis_region.setVisible(True)
        pass  # Default implementation does nothing

    # --- PHASE 2: Template Method Pattern ---
    @QtCore.Slot()
    def _trigger_analysis(self):
        """
        Template method that orchestrates the analysis workflow.
        This method should NOT be overridden by subclasses.

        Workflow:
        1. Validate data availability
        2. Set wait cursor
        3. Gather parameters from UI (via abstract method)
        4. Execute core analysis (via abstract method)
        5. Display results (via abstract method)
        6. Update plot visualizations (via abstract method)
        7. Enable save button
        8. Handle errors and restore cursor
        """
        log.debug(f"{self.__class__.__name__}: Triggering analysis")

        # Validate data
        # Validate data
        if not self._current_plot_data:
            log.warning(f"{self.__class__.__name__}: No data available for analysis")

            # Check if triggered automatically (by timer) vs manually (button)
            # We don't want to annoy the user with popups during initialization or reactive updates
            sender = self.sender()
            is_auto_triggered = (sender == self._analysis_debounce_timer) or isinstance(sender, QtCore.QTimer)

            if not is_auto_triggered:
                QtWidgets.QMessageBox.warning(self, "No Data", "Please load and plot data before running analysis.")
            return

        # Set wait cursor
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        self._last_analysis_result = None

        try:
            # Step 1: Gather parameters from subclass UI
            params = self._gather_analysis_parameters()
            if not params:
                self._set_save_button_enabled(False)
                return

            # --- INJECT GLOBAL ANALYSIS WINDOW ---
            if getattr(self, "restrict_analysis_checkbox", None) and \
               self.restrict_analysis_checkbox.isChecked() and \
               getattr(self, "analysis_region", None):
                min_t, max_t = self.analysis_region.getRegion()
                params["t_start"] = min_t
                params["t_end"] = max_t
                log.debug(f"Applied restricted analysis window: {min_t:.4f} to {max_t:.4f} s")
            # -------------------------------------

            # Step 2: Execute core analysis
            results = self._execute_core_analysis(params, self._current_plot_data)

            # BUG 1 FIX: Check if results is None before proceeding
            if results is None:
                log.warning(f"{self.__class__.__name__}: Analysis returned None")
                QtWidgets.QMessageBox.warning(
                    self, "Analysis Failed", "Analysis could not be completed. Please check your parameters and data."
                )
                self._set_save_button_enabled(False)
                return

            # CRITICAL FIX: Call _on_analysis_result to allow subclasses to properly
            # store results in their own variables (e.g., _last_spike_result, _last_event_result)
            # This delegates to subclass implementations that know how to handle results
            self._on_analysis_result(results)

            log.debug(f"{self.__class__.__name__}: Analysis completed successfully")

        except Exception as e:
            log.error(f"{self.__class__.__name__}: Analysis failed: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Analysis Error", f"An error occurred during analysis:\n{str(e)}")
            self._set_save_button_enabled(False)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    # --- PHASE 3: Debounced Parameter Change Handler ---
    @QtCore.Slot()
    def _on_parameter_changed(self):
        """
        Called when a parameter widget changes.
        Starts/restarts the debounce timer to trigger analysis after a delay.
        """
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)
            log.debug(f"{self.__class__.__name__}: Parameter changed, debounce timer started")

    # --- Optional Methods Subclasses Might Implement ---
    def _connect_signals(self) -> None:
        pass  # Optional

    def cleanup(self) -> None:
        """Cleanup resources, stop threads, close popups."""
        log.debug(f"Cleaning up {self.__class__.__name__}")

        # Close all popup windows
        for win in self._popup_windows:
            try:
                win.close()
            except Exception as e:
                log.warning(f"Error closing popup window: {e}")
        self._popup_windows.clear()

        # Stop worker thread if running
        if self._analysis_thread and self._analysis_thread.isRunning():
            self._analysis_thread.quit()
            self._analysis_thread.wait()

    def create_popup_plot(self, title: str, x_label: str = None, y_label: str = None) -> pg.PlotWidget:
        """
        Create a separate popup window with a PlotWidget.
        The window is tracked and will be closed when the tab is cleaned up.

        Args:
            title: Window title.
            x_label: Label for X axis.
            y_label: Label for Y axis.

        Returns:
            pg.PlotWidget: The plot widget in the new window.
        """
        # Create a new window (QMainWindow or QWidget)
        popup = QtWidgets.QMainWindow(self)  # Parented to self so it closes with app, but we track it too
        popup.setWindowTitle(title)
        popup.resize(600, 400)

        # Prevent window from being destroyed when closed - it will just hide
        # User can restore it via View > Show Analysis Popup Windows
        popup.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)

        # Create central widget and layout
        central_widget = QtWidgets.QWidget()
        popup.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        # Create PlotWidget using Factory (§II.3 Visualization Safety)
        from Synaptipy.shared.plot_factory import SynaptipyPlotFactory

        plot_widget = SynaptipyPlotFactory.create_plot_widget(parent=central_widget)
        if x_label:
            plot_widget.setLabel("bottom", x_label)
        if y_label:
            plot_widget.setLabel("left", y_label)

        layout.addWidget(plot_widget)

        # Show and track
        popup.show()
        self._popup_windows.append(popup)

        return plot_widget

    # --- ADDED: Helper for Saving Results ---
    def _request_save_result(self, specific_result_data: Dict[str, Any]):
        """
        Collects common metadata and calls MainWindow's method to save the result.

        Args:
            specific_result_data: Dictionary containing results specific to this
                                      analysis tab (e.g., value, units, channel,
                                      data source selection).
        """
        log.debug(f"{self.get_display_name()}: Requesting to save result.")
        main_window = self.window()  # Get reference to the top-level MainWindow
        if not hasattr(main_window, "add_saved_result"):
            log.error("Cannot save result: MainWindow does not have 'add_saved_result' method.")
            QtWidgets.QMessageBox.critical(self, "Save Error", "Internal error: Cannot access result saving mechanism.")
            return

        if self._selected_item_index < 0 or self._selected_item_index >= len(self._analysis_items):
            log.warning("Cannot save result: No valid analysis item selected.")
            QtWidgets.QMessageBox.warning(self, "Save Error", "No analysis item selected.")
            return

        # --- Get Common Metadata ---
        selected_item = self._analysis_items[self._selected_item_index]
        source_file_path = selected_item.get("path")
        source_file_name = source_file_path.name if source_file_path else "Unknown"
        item_target_type = selected_item.get("target_type")  # Type selected in Explorer list
        item_trial_index = selected_item.get("trial_index")  # Trial defined in Explorer list (if any)

        # --- Determine Actual Data Source Used ---
        # This comes from the UI elements *within* this specific analysis tab
        data_source = specific_result_data.get("data_source", None)  # e.g., "average" or trial index
        actual_trial_index = None
        data_source_type = "Unknown"
        if data_source == "average":
            data_source_type = "Average"
        elif isinstance(data_source, int):
            data_source_type = "Trial"
            actual_trial_index = data_source  # 0-based
        else:  # Handle cases where data source might be fixed by the item_type
            if item_target_type == "Current Trial":
                data_source_type = "Trial"
                actual_trial_index = item_trial_index
            elif item_target_type == "Average Trace":
                data_source_type = "Average"

        # --- Get Analysis Type ---
        analysis_type = self.get_display_name()

        # --- Combine Data ---
        # Prioritize specific results passed in, then add common metadata
        final_result = {
            "analysis_type": analysis_type,
            "source_file_name": source_file_name,
            "source_file_path": str(source_file_path) if source_file_path else None,
            "item_target_type": item_target_type,  # How the source was added
            "data_source_used": data_source_type,  # Average or Trial
            "trial_index_used": actual_trial_index,  # 0-based index if applicable
            **specific_result_data,  # Add the specific results from the subclass
        }

        # Remove the internal 'data_source' key if it exists in specific_result_data
        final_result.pop("data_source", None)

        log.debug(f"Final result data to save: {final_result}")

        # --- Check for Existing Result ---
        existing_index = -1
        if hasattr(main_window, "saved_results"):
            for i, res in enumerate(main_window.saved_results):
                # Define what "same result" means.
                # Usually: Same file, same analysis type, same data source (trial/avg)
                if (
                    res.get("source_file_path") == final_result.get("source_file_path")
                    and res.get("analysis_type") == final_result.get("analysis_type")
                    and res.get("data_source_used") == final_result.get("data_source_used")
                    and res.get("trial_index_used") == final_result.get("trial_index_used")
                ):
                    existing_index = i
                    break

        if existing_index >= 0:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Overwrite Result?",
                f"A result for '{analysis_type}' on this data already exists.\nDo you want to overwrite it?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                log.debug("Save cancelled by user (overwrite denied).")
                return

        # --- Call MainWindow Method ---
        try:
            # If overwriting, we might need a way to tell MainWindow to replace.
            # If add_saved_result just appends, we might have duplicates.
            # Let's assume we can replace if we have the index, OR we just append and let the user manage (but user
            # asked to "rewrite").
            # If MainWindow has 'update_saved_result', use it. Else, maybe 'saved_results[i] = ...' ?
            # Safest is to check if we can replace.

            if existing_index >= 0 and hasattr(main_window, "saved_results"):
                main_window.saved_results[existing_index] = final_result
                # We also need to refresh the results view in MainWindow if it exists
                if hasattr(main_window, "results_tab") and hasattr(main_window.results_tab, "refresh_results"):
                    main_window.results_tab.refresh_results()
                elif hasattr(main_window, "refresh_results_display"):
                    main_window.refresh_results_display()
                log.debug(f"Overwrote existing result at index {existing_index}")
                if hasattr(self, "status_label") and self.status_label:
                    self.status_label.setText("Status: Result overwritten successfully")
            else:
                main_window.add_saved_result(final_result)
                if hasattr(self, "status_label") and self.status_label:
                    self.status_label.setText("Status: Result saved successfully")

        except Exception as e:
            log.error(f"Error saving result: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Failed to save result:\n{e}")

    # --- PHASE 4: Session Accumulation Methods ---

    def _setup_accumulation_ui(self, layout: QtWidgets.QLayout):
        """
        Adds 'Add to Session' and 'View Session' buttons to the layout.
        """
        group = QtWidgets.QGroupBox("Session Accumulation")
        group_layout = QtWidgets.QHBoxLayout(group)
        group_layout.setContentsMargins(5, 5, 5, 5)

        self.add_to_session_button = QtWidgets.QPushButton("Add to Session")
        self.add_to_session_button.setToolTip("Add current result to session statistics.")
        self.add_to_session_button.clicked.connect(self._on_add_to_session_clicked)
        self.add_to_session_button.setEnabled(False)  # Enabled only when result exists
        style_button(self.add_to_session_button)

        self.view_session_button = QtWidgets.QPushButton("View Session")
        self.view_session_button.setToolTip("View accumulated results and statistics.")
        self.view_session_button.clicked.connect(self._on_view_session_clicked)
        self.view_session_button.setEnabled(False)  # Enabled when list not empty
        style_button(self.view_session_button)

        group_layout.addWidget(self.add_to_session_button)
        group_layout.addWidget(self.view_session_button)

        layout.addWidget(group)

    def _on_add_to_session_clicked(self):
        """Add the current result to the accumulated list."""
        if not self._last_analysis_result:
            return

        # Get specific data (value, units, etc.)
        specific_data = self._get_specific_result_data()
        if not specific_data:
            return

        # Add metadata about source
        entry = specific_data.copy()

        # Add trial info
        if self.data_source_combobox and self.data_source_combobox.isEnabled():
            entry["source_label"] = self.data_source_combobox.currentText()
        else:
            entry["source_label"] = "Current"

        self._accumulated_results.append(entry)

        # Update UI
        self.view_session_button.setEnabled(True)
        self.view_session_button.setText(f"View Session ({len(self._accumulated_results)})")

        # Feedback
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setText(f"Status: Added to session ({len(self._accumulated_results)} items)")

    def _on_view_session_clicked(self):
        """Show the session summary dialog."""
        if not self._accumulated_results:
            return

        from Synaptipy.application.gui.session_summary_dialog import SessionSummaryDialog

        dialog = SessionSummaryDialog(self._accumulated_results, parent=self)
        dialog.exec()

    def _update_accumulation_ui_state(self):
        """Enable/Disable Add button based on result availability."""
        if self.add_to_session_button:
            self.add_to_session_button.setEnabled(self._last_analysis_result is not None)

    # --- END ADDED ---
