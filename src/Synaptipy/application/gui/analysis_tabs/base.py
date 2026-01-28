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
from Synaptipy.shared.error_handling import SynaptipyError, FileReadError
from Synaptipy.shared.styling import (
    style_button,
)
from Synaptipy.shared.plot_zoom_sync import PlotZoomSyncManager
from Synaptipy.application.gui.analysis_worker import AnalysisWorker  # Import Worker
from Synaptipy.shared.plot_factory import SynaptipyPlotFactory
from Synaptipy.application.gui.widgets.preprocessing import PreprocessingWidget
from Synaptipy.core import signal_processor

log = logging.getLogger(__name__)


# Custom metaclass to resolve Qt/ABC metaclass conflict
class QABCMeta(type(QtWidgets.QWidget), type(ABC)):
    """Metaclass that combines Qt's metaclass with ABC's metaclass."""

    pass


class BaseAnalysisTab(QtWidgets.QWidget, ABC, metaclass=QABCMeta):
    """Base Class for all analysis sub-tabs."""

    # Removed TRIAL_MODES as it's less relevant now

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent: Optional[QtWidgets.QWidget] = None):
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
        # --- ADDED: Plot Widget ---
        self.plot_widget: Optional[pg.PlotWidget] = None
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
        self.preprocessing_widget: Optional[PreprocessingWidget] = None
        self._preprocessed_data: Optional[Dict[str, Any]] = None # Cached preprocessed data
        self._is_preprocessing: bool = False
        self._active_preprocessing_settings: Optional[Dict[str, Any]] = None  # Persist settings
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

        toolbar_layout.addStretch()

        parent_layout.addLayout(toolbar_layout)

    def _reset_plot_view(self) -> None:
        """Reset the plot view to default range."""
        if self.plot_widget:
            self.plot_widget.autoRange()

    def _save_plot(self):
        """Save the current plot as an image."""
        if not self.plot_widget:
            return

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Plot", "", "Images (*.png *.jpg *.svg)")

        if file_path:
            # Use pyqtgraph exporter
            import pyqtgraph.exporters

            exporter = pyqtgraph.exporters.ImageExporter(self.plot_widget.plotItem)
            exporter.export(file_path)

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
            self._global_combo_group = QtWidgets.QGroupBox("Analyze Item")
            layout_inner = QtWidgets.QVBoxLayout(self._global_combo_group)
            layout_inner.setContentsMargins(5, 5, 5, 5)
            # Insert after source group
            layout.insertWidget(1, self._global_combo_group)

        # Reparent combo to our container
        self._global_combo_group.layout().addWidget(item_combo)
        item_combo.setVisible(True)
        
        # 3. Handle Preprocessing Widget (Inject below Analyze Item)
        if not hasattr(self, "preprocessing_widget") or self.preprocessing_widget is None:
            self.preprocessing_widget = PreprocessingWidget()
            self.preprocessing_widget.preprocessing_requested.connect(self._handle_preprocessing_request)
            layout.insertWidget(2, self.preprocessing_widget)
            log.debug(f"{self.__class__.__name__}: Created and injected PreprocessingWidget.")
        else:
            # Ensure it's visible if it was hidden or reused
            self.preprocessing_widget.setVisible(True)
            # Ensure it's in the layout at the right spot? 
            # If we created it, it stays in the layout unless removed.
            # But if we switch tabs, we want to make sure it's valid.

        log.debug(f"{self.__class__.__name__}: Global controls injected/reparented.")

    def _handle_preprocessing_request(self, settings: Dict[str, Any]):
        """
        Handle signal from PreprocessingWidget.
        Runs the requested operation in a background thread.
        """
        if self._selected_item_recording is None:
            QtWidgets.QMessageBox.warning(self, "No Data", "No recording loaded to preprocess.")
            return

        # Disable UI
        self._is_preprocessing = True
        self._active_preprocessing_settings = settings  # Store settings for future plots
        if self.preprocessing_widget:
            self.preprocessing_widget.set_processing_state(True)
        
        # Determine data to process (Raw Data from the recording)
        # We process the entire channel data generally, or just the current trial?
        # Typically we preprocess the RAW signal for the display/analysis.
        # But we need to know WHICH channel is selected.
        
        # Simplification: We process the CURRENTLY SELECTED data if possible,
        # or we might need to process the whole recording?
        # Let's say we process the data that is currently being PLOTTED.
        # But wait, if we change channels, we want that new channel to be processed too?
        # Ideally, preprocessing parameters are applied dynamically on load.
        # But here the user explicitly clicked "Apply".
        
        # Strategy: We will apply the operation to the CURRENTLY DISPLAYED trace data.
        # And cache it in `_preprocessed_data`.
        # If we change channels, `_preprocessed_data` is cleared (in _on_analysis_item_selected/channel changed),
        # so the user has to re-apply. This is consistent with "Basic Analysis" flow.
        
        # Get raw data from currently loaded recording (and selected channel)
        try:
            # FIX: Directly trigger re-plotting.
            # This ensures we use the centralized `_plot_selected_data` logic, which:
            # 1. Preserves Zoom (via our recent fix).
            # 2. Applies settings to ALL traces (Context + Main) on-the-fly.
            # 3. Respects trial selection.
            self._plot_selected_data()
            # Note: We return early or just let the method finish

        except Exception as e:
            log.error(f"Failed to start preprocessing: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Error", f"Could not start processing: {e}")
            self._is_preprocessing = False
            if self.preprocessing_widget:
                self.preprocessing_widget.set_processing_state(False)

    def _on_preprocessing_complete(self, result_data):
        """Preprocessing finished successfully."""
        self._is_preprocessing = False
        if self.preprocessing_widget:
            self.preprocessing_widget.set_processing_state(False)
            
        log.debug("Preprocessing complete.")
        
        # Update cache
        if self._preprocessed_data is None:
             # Initialize from current plot data structure if first time
             self._preprocessed_data = self._current_plot_data.copy() if self._current_plot_data else {}
             
        self._preprocessed_data['data'] = result_data
        
        # Trigger Re-plot with new data
        # We need to manually update the plot because `_plot_selected_data` usually fetches raw data.
        # But we modified `_plot_selected_data` (in our plan, not yet done in code?)
        # Wait, I need to modify `_plot_selected_data` to checking `self._preprocessed_data`.
        # For now, let's manually invoke the plotting logic with the new data.
        
        # Update `_current_plot_data` to point to the new data
        if self._current_plot_data:
            self._current_plot_data['data'] = result_data
            
        # Re-plot traces
        if self.plot_widget:
            self.plot_widget.clear()
            # Re-draw the trace
            # We can't easily call `_plot_selected_data` because it re-reads from file (usually).
            # So we manually plot here or refactor.
            # Refactoring `_plot_selected_data` might be risky if subclasses override it aggressively.
            
            # Safest: Use the standard plotting way if available, or just plot directly here.
            time = self._current_plot_data.get('time')
            if time is not None:
                self.plot_widget.plot(time, result_data, pen='k') # Use default pen?
                self._update_plot_pens_only() # Apply correct styling
                
                # IMPORTANT: Trigger any analysis that depends on the data (like Spike Detection)
                # Subclasses hook into `_on_data_plotted`
                self._on_data_plotted()
            else:
                 log.warning("Time array missing, cannot re-plot.")

    def _on_preprocessing_error(self, error):
        """Preprocessing failed."""
        self._is_preprocessing = False
        if self.preprocessing_widget:
            self.preprocessing_widget.set_processing_state(False)
        
        log.error(f"Preprocessing error: {error}")
        QtWidgets.QMessageBox.critical(self, "Processing Error", f"An error occurred:\n{error}")

    @staticmethod
    def _process_signal_data(data_in: np.ndarray, fs: float, params: Dict[str, Any]) -> np.ndarray:
        """
        Static helper method to process signal data.
        Can be used by worker threads or main thread.
        """
        import numpy as np
        # Check for NaNs/Inf just in case
        if not np.all(np.isfinite(data_in)):
                log.warning("Data contains NaNs or Infs before processing.")
                
        result_data = data_in.copy()
        op_type = params.get('type')
        
        if op_type == 'baseline':
            decimals = params.get('decimals', 1)
            result_data = signal_processor.subtract_baseline_mode(result_data, decimals=decimals)
            
        elif op_type == 'filter':
            method = params.get('method')
            if method == 'lowpass':
                cutoff = params.get('cutoff')
                order = int(params.get('order', 5))
                result_data = signal_processor.lowpass_filter(result_data, cutoff, fs, order)
            elif method == 'highpass':
                cutoff = params.get('cutoff')
                order = int(params.get('order', 5))
                result_data = signal_processor.highpass_filter(result_data, cutoff, fs, order)
            elif method == 'bandpass':
                low = params.get('low_cut')
                high = params.get('high_cut')
                order = int(params.get('order', 5))
                result_data = signal_processor.bandpass_filter(result_data, low, high, fs, order)
            elif method == 'notch':
                freq = params.get('freq')
                q = params.get('q_factor')
                result_data = signal_processor.notch_filter(result_data, freq, q, fs)
                
        return result_data

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
            for item in self.plot_widget.plotItem.items:
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
        """Adds a PlotWidget to the provided layout with normal configuration."""
        log.debug(f"[ANALYSIS-BASE] Setting up plot area for {self.__class__.__name__}")

        # Add the plot widget using the factory pattern for compliance
        self.plot_widget = SynaptipyPlotFactory.create_plot_widget(
            parent=None, background="white", enable_grid=True, mouse_mode="rect"  # Parent handled by addWidget
        )
        log.debug(f"[ANALYSIS-BASE] Created plot widget for {self.__class__.__name__}")

        # Add Windows signal protection to prevent rapid range changes
        # This is already partly handled by factory but added here for extra safety if needed
        viewbox = self.plot_widget.getViewBox()
        if viewbox:
            import sys

            if sys.platform.startswith("win"):
                log.debug(f"[ANALYSIS-BASE] Adding Windows signal protection for {self.__class__.__name__}")
                self._setup_windows_signal_protection(viewbox)

        # Add the plot widget to the layout
        layout.addWidget(self.plot_widget, stretch=stretch_factor)
        log.debug(f"[ANALYSIS-BASE] Added plot widget to layout for {self.__class__.__name__}")

        # Add Toolbar below the plot
        self._setup_toolbar(layout)

        # Normal grid configuration with customization support
        try:
            # Try to use customized grid settings
            try:
                from Synaptipy.shared.plot_customization import get_grid_pen, is_grid_enabled

                if is_grid_enabled():
                    grid_pen = get_grid_pen()
                    if grid_pen:
                        # Get alpha value from pen color
                        alpha = 0.3  # Default alpha
                        if hasattr(grid_pen, "color") and hasattr(grid_pen.color(), "alpha"):
                            alpha = grid_pen.color().alpha() / 255.0
                            log.debug(f"Using grid pen alpha: {alpha} (opacity: {alpha * 100:.1f}%)")
                        else:
                            log.debug("Using default grid alpha: 0.3")

                        self.plot_widget.showGrid(x=True, y=True, alpha=alpha)
                        log.debug(
                            f"[ANALYSIS-BASE] Customized grid configuration successful for {self.__class__.__name__} with alpha: {alpha}"
                        )
                    else:
                        self.plot_widget.showGrid(x=False, y=False)
                        log.debug(f"[ANALYSIS-BASE] Grid disabled for {self.__class__.__name__}")
                else:
                    self.plot_widget.showGrid(x=False, y=False)
                    log.debug(f"[ANALYSIS-BASE] Grid disabled for {self.__class__.__name__}")
            except ImportError:
                self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
                log.debug(f"[ANALYSIS-BASE] Default grid configuration successful for {self.__class__.__name__}")
        except Exception as e:
            log.warning(f"[ANALYSIS-BASE] Grid configuration warning for {self.__class__.__name__}: {e}")

        # Initialize zoom synchronization manager (for reset functionality only)
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
            log.warning(f"[ANALYSIS-BASE] No plot widget available for saving")
            return

        try:
            from Synaptipy.application.gui.dialogs.plot_export_dialog import PlotExportDialog
            from Synaptipy.shared.plot_exporter import PlotExporter
            from PySide6.QtWidgets import QFileDialog
            from pathlib import Path

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
                log.debug(f"[ANALYSIS-BASE] Plot save cancelled")

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
            log.debug(f"[ANALYSIS-BASE] Using zoom sync auto-range")
            self.zoom_sync.auto_range()
        elif self.plot_widget:
            log.debug(f"[ANALYSIS-BASE] Using direct plot widget auto-range")
            self.plot_widget.autoRange()
        else:
            log.warning(f"[ANALYSIS-BASE] No plot widget available for auto-range")

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
        self._preprocessed_data = None # Clear preprocessing cache on new item
        self._active_preprocessing_settings = None  # Clear settings on new item


        if index < 0 or index >= len(self._analysis_items):
            log.debug(f"{self.__class__.__name__}: No valid analysis item selected (index {index}).")
            # Still need to update UI to reflect empty state
            try:
                self._update_ui_for_selected_item()
            except Exception as e:
                log.error(f"Error calling _update_ui_for_selected_item on empty selection: {e}", exc_info=True)
            return

        selected_item = self._analysis_items[index]
        item_type = selected_item.get("target_type")
        item_path = selected_item.get("path")

        log.debug(f"{self.__class__.__name__}: Selected analysis item {index}: Type={item_type}, Path={item_path}")

        # If the selected item is a whole recording, we need to load it
        if item_type == "Recording" and item_path:
            try:
                log.debug(f"{self.__class__.__name__}: Loading recording for analysis item: {item_path.name}")
                # Force process events to flush logs and update UI before blocking read
                QtWidgets.QApplication.processEvents()

                # Use the NeoAdapter passed during init
                self._selected_item_recording = self.neo_adapter.read_recording(item_path)

                if self._selected_item_recording:
                    log.debug(
                        f"{self.__class__.__name__}: Successfully loaded {item_path.name} with {len(self._selected_item_recording.channels)} channels."
                    )
                else:
                    log.error(f"{self.__class__.__name__}: read_recording returned None for {item_path.name}")

            except (FileNotFoundError, FileReadError, SynaptipyError) as e:
                log.error(f"{self.__class__.__name__}: Failed to load recording {item_path.name}: {e}")
                QtWidgets.QMessageBox.warning(
                    self, "Load Error", f"Could not load data for selected item:\n{item_path.name}\n\nError: {e}"
                )
                self._selected_item_recording = None
            except Exception as e:
                log.exception(f"{self.__class__.__name__}: Unexpected error loading recording {item_path.name}")
                QtWidgets.QMessageBox.critical(
                    self, "Load Error", f"Unexpected error loading:\n{item_path.name}\n\n{e}"
                )
                self._selected_item_recording = None
        elif item_type in ["Current Trial", "Average Trace", "All Trials"]:
            if item_path:
                try:
                    log.debug(f"{self.__class__.__name__}: Loading source recording for item: {item_path.name}")
                    QtWidgets.QApplication.processEvents()
                    self._selected_item_recording = self.neo_adapter.read_recording(item_path)
                    if not self._selected_item_recording:
                        log.error(
                            f"{self.__class__.__name__}: read_recording returned None for source {item_path.name}"
                        )
                except Exception as e:
                    log.error(
                        f"{self.__class__.__name__}: Failed to load source recording {item_path.name} for item type {item_type}: {e}"
                    )
                    self._selected_item_recording = None
            else:
                log.warning(f"{self.__class__.__name__}: Item type {item_type} selected but path is missing.")
                self._selected_item_recording = None
        else:
            log.warning(f"{self.__class__.__name__}: Unknown or unhandled analysis item type: {item_type}")
            self._selected_item_recording = None

        # --- Call Subclass UI Update ---
        # This should be called regardless of whether loading succeeded,
        # so the subclass can update its UI (e.g., disable widgets if loading failed)
        try:
            # Clear plot before updating UI for new selection
            if self.plot_widget:
                self.plot_widget.clear()

            # PHASE 1: Populate channel and data source comboboxes if they exist
            if self.signal_channel_combobox and self.data_source_combobox:
                self._populate_channel_and_source_comboboxes()

            self._update_ui_for_selected_item()
        except NotImplementedError:  # Catch if subclass forgot to implement
            log.error(f"Subclass {self.__class__.__name__} must implement _update_ui_for_selected_item()")
        except Exception as e:
            log.error(f"Error calling _update_ui_for_selected_item in {self.__class__.__name__}: {e}", exc_info=True)

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

    # --- PHASE 2: Threaded Analysis Execution ---
    @QtCore.Slot()
    def _trigger_analysis(self):
        """
        Triggers the analysis process.
        Gathers parameters and starts the worker thread.
        """
        log.debug(f"{self.__class__.__name__}: Triggering analysis...")

        # 1. Gather Parameters (UI Thread)
        params = self._gather_analysis_parameters()
        if not params:
            log.debug("Analysis aborted: Invalid parameters.")
            return

        # 2. Get Data (UI Thread)
        # We need to pass a copy of data to the worker to avoid thread safety issues
        # Assuming _current_plot_data is a dict of numpy arrays/primitives which is fine to read
        if not self._current_plot_data:
            log.debug("Analysis aborted: No data available.")
            return

        data_copy = self._current_plot_data.copy()

        # 3. Start Worker (Background Thread)
        worker = AnalysisWorker(self._execute_core_analysis, params, data_copy)
        worker.signals.result.connect(self._on_analysis_result)
        worker.signals.error.connect(self._on_analysis_error)

        # Show busy state
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setText("Status: Analyzing...")

        self.thread_pool.start(worker)

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
        in_layout.addWidget(QtWidgets.QLabel("Every Nth Trial (Period):"))
        self.nth_trial_input = QtWidgets.QLineEdit()
        self.nth_trial_input.setPlaceholderText("e.g. 1=All, 10=Every 10th")
        self.nth_trial_input.setValidator(QtGui.QIntValidator(1, 9999))
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
        
        self._plot_selected_data() # Reverts to single trial view

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

        gap = 0
        start_idx = 0

        try:
            if text_gap:
                period = int(text_gap)
            else:
                period = 1 # Default to All
            start_idx = int(text_start) if text_start else 0
        except ValueError:
            log.warning("Invalid input for trial selection.")
            return

        selected_indices = []
        # Period = Step
        step = period
        
        # Guard against zero step
        if step < 1:
            step = 1

        for i in range(start_idx, num_trials, step):
            selected_indices.append(i)
            
        log.info(f"Trial Selection: Period={step}, Start={start_idx} -> Found {len(selected_indices)} trials.")

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
        has_average = False

        if first_channel:
            num_trials = getattr(first_channel, "num_trials", 0)
            # Check for average data
            if hasattr(first_channel, "get_averaged_data") and first_channel.get_averaged_data() is not None:
                has_average = True
            elif hasattr(first_channel, "has_average_data") and first_channel.has_average_data():
                has_average = True
            elif getattr(first_channel, "_averaged_data", None) is not None:
                has_average = True

        # Populate based on item type
        if item_type == "Current Trial" and item_trial_index is not None and 0 <= item_trial_index < num_trials:
            self.data_source_combobox.addItem(f"Trial {item_trial_index + 1}", userData=item_trial_index)
        elif item_type == "Average Trace" and has_average:
            self.data_source_combobox.addItem("Average Trace", userData="average")
        else:  # "Recording" or "All Trials"
            if has_average:
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
        self._current_plot_data = None

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

        channel = self._selected_item_recording.channels[chan_id]

        try:
            # --- New Logic: Handle Filtered Trials Overlay & Dynamic Averaging ---
            # If filtered trials are active (set by _on_plot_filtered_trials), we use them.
            
            # 0. Preserve View State if possible
            view_state = None
            if self.plot_widget.plotItem:
                # Check if we should preserve (e.g., if we are looking at the same channel/recording)
                # For now, let's assume if we are actively viewing, we want to preserve.
                # Only preserve if we have valid items previously? 
                # Simplest check: just get range.
                view_state = self.plot_widget.viewRange()


            # 1. Clear plot to prevent ghost traces (FIX)
            self.plot_widget.clear()

            # 1. Overlay Background (Context)
            if hasattr(self, "_filtered_indices") and self._filtered_indices:
                # Plot context traces in subtle gray
                gray_pen = pg.mkPen((200, 200, 200), width=1)
                # Sort indices for deterministic drawing order
                for idx in sorted(list(self._filtered_indices)): 
                    # Skip if this is the "main" trial being highlighted later (to avoid drawing twice)
                    if isinstance(data_source, int) and idx == data_source:
                        continue
                        
                    ctx_data = channel.get_data(idx)
                    ctx_time = channel.get_relative_time_vector(idx)
                    
                    # Apply processing to context traces if active
                    if ctx_data is not None:
                        if self._active_preprocessing_settings:
                             ctx_data = self._process_signal_data(
                                 ctx_data, 
                                 channel.sampling_rate, 
                                 self._active_preprocessing_settings
                             )
                        
                        self.plot_widget.plot(ctx_time, ctx_data, pen=gray_pen)
            
            # 2. Handle Dynamic Averaging
            # If "Average" is selected AND we have a filter, compute average across filtered indices.
            # Otherwise use pre-calculated average.
            if data_source == "average":
                if hasattr(self, "_filtered_indices") and self._filtered_indices:
                     # Dynamic Average
                     indices = sorted(list(self._filtered_indices))
                     if not indices:
                         log.warning("Filtered indices empty during dynamic average calculation.")
                         return

                     # Fetch all data to compute mean
                     first_trace = channel.get_data(indices[0])
                     if first_trace is not None:
                         sum_data = np.zeros_like(first_trace, dtype=float)
                         count = 0
                         skipped = 0
                         for idx in indices:
                             d = channel.get_data(idx)
                             if d is not None and d.shape == sum_data.shape:
                                 sum_data += d
                                 count += 1
                             else:
                                 skipped += 1
                         
                         log.info(f"Dynamic Average: Averaged {count} trials, Skipped {skipped} (Shape mismatch or None)")
                         
                         if count > 0:
                             data_vec = sum_data / count
                             data_label = f"Average (Selected {count})"
                             # Time vec is safe to take from first
                             time_vec = channel.get_relative_time_vector(indices[0])
                else:
                    # Standard Average
                    data_vec = channel.get_averaged_data()
                    time_vec = channel.get_relative_averaged_time_vector()
                    data_label = "Average (All)"
            
            elif isinstance(data_source, int):
                data_vec = channel.get_data(data_source)
                time_vec = channel.get_relative_time_vector(data_source)
                data_label = f"Trial {data_source + 1}"
            else:
                log.error(f"{self.__class__.__name__}: Invalid data source value: {data_source}")
                # Plot/Cache cleared by default init
                return

            if data_vec is None or time_vec is None:
                log.warning(f"{self.__class__.__name__}: No data vectors returned for {data_label}")
                # Don't clear if we plotted background? No, clear because main analysis data is missing.
                # Actually, standard behavior is strict.
                return

            # --- PROCESS DATA IF SETTINGS EXIST --- (FIX)
            if self._active_preprocessing_settings:
                try:
                    data_vec = self._process_signal_data(
                        data_vec, 
                        channel.sampling_rate, 
                        self._active_preprocessing_settings
                    )
                    # Note: We do NOT update the cache `_preprocessed_data` here because 
                    # `_preprocessed_data` is strictly for "what was last computed by the widget".
                    # Actually, `_preprocessed_data` is used in `_on_preprocessing_complete` to cache result.
                    # But here we are applying it on-the-fly.
                    # Consistent behavior: 
                    # If we just switched trials, `self._preprocessed_data` is None (cleared in selection change).
                    # We have `self._active_preprocessing_settings`.
                    # We compute fresh.
                except Exception as proc_err:
                    log.error(f"Failed to apply active preprocessing: {proc_err}")
                    # Fallback to raw? Or fail? Fallback with warning is safer for UI.
            
            # Store current plot data (which analysis functions use)
            # FIX: Apply active preprocessing to the main trace if settings exist
            if self._active_preprocessing_settings and data_vec is not None:
                 try:
                     # For Average, we process the averaged result (valid for linear filters)
                     data_vec = self._process_signal_data(
                         data_vec, 
                         channel.sampling_rate, 
                         self._active_preprocessing_settings
                     )
                 except Exception as proc_err:
                     log.error(f"Failed to apply active preprocessing to main trace: {proc_err}")

            self._current_plot_data = {
                "data": data_vec,
                "time": time_vec,
                "channel_id": chan_id,
                "data_source": data_source,
                "units": channel.units or "?",
                "sampling_rate": channel.sampling_rate,
                "channel_name": channel.name or f"Ch {chan_id}",
            }
            
            # Setup Pen for Main Trace
            try:
                from Synaptipy.shared.plot_customization import get_single_trial_pen, get_average_pen
                pen = get_average_pen() if data_source == "average" else get_single_trial_pen()
            except ImportError:
                pen = pg.mkPen(color=(0, 0, 0), width=2) # Make main trace slightly thicker/definitive

            self.plot_widget.plot(time_vec, data_vec, pen=pen, name=data_label)

            self.plot_widget.setLabel("bottom", "Time", units="s")
            self.plot_widget.setLabel("left", channel.name or f"Ch {chan_id}", units=channel.units)
            self.plot_widget.setTitle(f"{channel.name or f'Channel {chan_id}'} - {data_label}")

            if len(time_vec) > 0 and len(data_vec) > 0:
                x_range = (float(np.min(time_vec)), float(np.max(time_vec)))
                y_range = (float(np.min(data_vec)), float(np.max(data_vec)))
                self.set_data_ranges(x_range, y_range)

            log.debug(f"{self.__class__.__name__}: Successfully plotted {data_label} from channel {chan_id}")
            
            # Restore View State
            if view_state:
                # We restore the view range to preserve zoom
                # Use padding=0 to respect exact previous bounds
                self.plot_widget.setRange(xRange=view_state[0], yRange=view_state[1], padding=0)

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
                log.warning(f"{self.__class__.__name__}: No parameters gathered")
                self._set_save_button_enabled(False)
                return

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
            # Let's assume we can replace if we have the index, OR we just append and let the user manage (but user asked to "rewrite").
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
