# src/Synaptipy/application/gui/analysis_tabs/rmp_tab.py
# -*- coding: utf-8 -*-
# Analysis sub-tab for calculating Baseline signal properties (Mean/SD).
# Allows interactive or manual selection of the baseline period.
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg # <<< Make sure this is imported

# Import base class using relative path within analysis_tabs package
from .base import BaseAnalysisTab
# Import needed core components using absolute paths
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.infrastructure.file_readers import NeoAdapter
# from Synaptipy.core.analysis import basic_features # We might create our own here

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.baseline_tab')

# --- Baseline Calculation Function ---
def calculate_baseline_stats(time: np.ndarray, voltage: np.ndarray, start_time: float, end_time: float) -> Optional[Tuple[float, float]]:
    # Calculates the Mean and Standard Deviation of a signal
    # over a specified time window.
    # Args:
    #     time: 1D numpy array of time values.
    #     voltage: 1D numpy array of signal values.
    #     start_time: Start time for the baseline window.
    #     end_time: End time for the baseline window.
    # Returns:
    #     A tuple containing (mean_value, std_dev_value) or None if the window
    #     is invalid or no data points are found.
    if time is None or voltage is None or start_time >= end_time:
        return None
    try:
        # Find indices corresponding to the time window
        indices = np.where((time >= start_time) & (time <= end_time))[0]
        if len(indices) == 0:
            log.warning(f"No data points found between {start_time}s and {end_time}s.")
            return None
        # Calculate the mean and standard deviation voltage within the window
        baseline_values = voltage[indices]
        baseline_mean = np.mean(baseline_values)
        baseline_sd = np.std(baseline_values)
        return baseline_mean, baseline_sd
    except Exception as e:
        log.error(f"Error calculating Baseline Mean/SD between {start_time}s and {end_time}s: {e}", exc_info=True)
        return None

# --- Baseline Analysis Tab Class ---
class BaselineAnalysisTab(BaseAnalysisTab):
    # QWidget for Baseline analysis with interactive plotting.

    # Define constants for analysis modes
    MODE_INTERACTIVE = 0
    MODE_MANUAL = 1

    def __init__(self, neo_adapter: NeoAdapter, parent=None): # Corrected signature
        # Pass neo_adapter to superclass constructor
        super().__init__(neo_adapter=neo_adapter, parent=parent)

        # --- UI References specific to Baseline ---
        # NOTE: signal_channel_combobox and data_source_combobox are now inherited from BaseAnalysisTab
        # Mode Selection
        self.analysis_params_group: Optional[QtWidgets.QGroupBox] = None
        self.mode_button_group: Optional[QtWidgets.QButtonGroup] = None
        self.interactive_radio: Optional[QtWidgets.QRadioButton] = None
        self.manual_radio: Optional[QtWidgets.QRadioButton] = None
        # Manual Inputs
        self.manual_time_group: Optional[QtWidgets.QGroupBox] = None
        self.start_time_edit: Optional[QtWidgets.QLineEdit] = None
        self.end_time_edit: Optional[QtWidgets.QLineEdit] = None
        # Results Display
        self.mean_sd_result_label: Optional[QtWidgets.QLabel] = None # To display the calculated Baseline
        # Plotting Interaction
        self.interactive_region: Optional[pg.LinearRegionItem] = None
        # ADDED: Calculate Button
        self.calculate_button: Optional[QtWidgets.QPushButton] = None
        # ADDED: Auto Calculate Button
        self.auto_calculate_button: Optional[QtWidgets.QPushButton] = None
        # ADDED: Plot items for Baseline lines
        self.baseline_mean_line: Optional[pg.InfiniteLine] = None
        # NOTE: _current_plot_data is now inherited from BaseAnalysisTab
        # ADDED: Store last calculated Baseline result
        self._last_baseline_result: Optional[Dict[str, Any]] = None # {value, sd, method}
        # ADDED: Plot items for SD lines
        self.baseline_plus_sd_line: Optional[pg.InfiniteLine] = None
        self.baseline_minus_sd_line: Optional[pg.InfiniteLine] = None

        self._setup_ui()
        self._connect_signals()
        self._on_mode_changed() # Set initial UI state based on default mode

    def get_display_name(self) -> str:
        # Returns the name for the sub-tab.
        return "Baseline Analysis"

    def _setup_ui(self):
        """Recreate Baseline analysis UI with a 3-column top layout."""
        main_layout = QtWidgets.QVBoxLayout(self) # Main layout is Vertical
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # --- Top Controls Area (3 Columns) ---
        top_controls_widget = QtWidgets.QWidget()
        top_controls_layout = QtWidgets.QHBoxLayout(top_controls_widget)
        top_controls_layout.setContentsMargins(0,0,0,0)
        top_controls_layout.setSpacing(8)
        top_controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Column 1: Data Selection ---
        data_selection_group = QtWidgets.QGroupBox("Data Selection")
        data_selection_layout = QtWidgets.QFormLayout(data_selection_group)
        data_selection_layout.setContentsMargins(5, 10, 5, 5)
        data_selection_layout.setSpacing(5)
        data_selection_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # 1a. Analysis Item Selector (inherited)
        self._setup_analysis_item_selector(data_selection_layout)
        # 1b. Signal Channel & Data Source (now handled by base class)
        self._setup_data_selection_ui(data_selection_layout)
        # Set size policy for Col 1
        data_selection_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Preferred)
        top_controls_layout.addWidget(data_selection_group)

        # --- Column 2: Analysis Mode & Parameters ---
        analysis_params_group = QtWidgets.QGroupBox("Analysis Mode & Parameters")
        analysis_params_layout = QtWidgets.QVBoxLayout(analysis_params_group)
        analysis_params_layout.setContentsMargins(5, 10, 5, 5)
        analysis_params_layout.setSpacing(5)
        analysis_params_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        # 2a. Analysis Mode
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel("Mode:"))
        self.mode_combobox = QtWidgets.QComboBox()
        self.mode_combobox.addItems(["Interactive", "Automatic", "Manual"])
        self.mode_combobox.setToolTip(
            "Interactive: Use region selector on plot.\n"
            "Automatic: Attempt calculation based on criteria.\n"
            "Manual: Enter specific time window.")
        mode_layout.addWidget(self.mode_combobox, stretch=1)
        analysis_params_layout.addLayout(mode_layout)
        # 2b. Manual Time Window Group (nested)
        self.manual_time_group = QtWidgets.QGroupBox("Manual Time Window (s)")
        manual_layout = QtWidgets.QHBoxLayout(self.manual_time_group)
        self.manual_start_time_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_end_time_spinbox = QtWidgets.QDoubleSpinBox()
        for spinbox in [self.manual_start_time_spinbox, self.manual_end_time_spinbox]:
            spinbox.setDecimals(4); spinbox.setRange(0.0, 1e6); spinbox.setSingleStep(0.01); spinbox.setSuffix(" s")
        manual_layout.addWidget(QtWidgets.QLabel("Start:"))
        manual_layout.addWidget(self.manual_start_time_spinbox)
        manual_layout.addWidget(QtWidgets.QLabel("End:"))
        manual_layout.addWidget(self.manual_end_time_spinbox)
        self.manual_time_group.setVisible(False)
        analysis_params_layout.addWidget(self.manual_time_group)
        # 2c. Automatic Threshold Group (nested)
        self.auto_threshold_group = QtWidgets.QGroupBox("Auto - Baseline SD Threshold")
        auto_thresh_layout = QtWidgets.QHBoxLayout(self.auto_threshold_group)
        self.auto_sd_threshold_spinbox = QtWidgets.QDoubleSpinBox()
        self.auto_sd_threshold_spinbox.setDecimals(2); self.auto_sd_threshold_spinbox.setRange(0.1, 5.0); self.auto_sd_threshold_spinbox.setValue(0.5); self.auto_sd_threshold_spinbox.setSingleStep(0.1); self.auto_sd_threshold_spinbox.setSuffix(" x Initial SD")
        self.auto_sd_threshold_spinbox.setToolTip("Max allowed standard deviation within the baseline window for auto-calculation (relative to initial trace noise estimate).")
        auto_thresh_layout.addWidget(self.auto_sd_threshold_spinbox)
        self.auto_threshold_group.setVisible(False)
        analysis_params_layout.addWidget(self.auto_threshold_group)
        # 2d. Run Button
        self.run_button = QtWidgets.QPushButton("Run Manual/Auto Analysis")
        self.run_button.setVisible(False)
        self.run_button.setEnabled(False)
        self.run_button.setMinimumHeight(30)
        analysis_params_layout.addWidget(self.run_button)
        analysis_params_layout.addStretch(1)
        # Set size policy for Col 2
        self.analysis_params_group = analysis_params_group # Assign to self
        analysis_params_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Preferred)
        top_controls_layout.addWidget(analysis_params_group)

        # --- Column 3: Results ---
        self.results_group = QtWidgets.QGroupBox("Results")
        results_layout = QtWidgets.QVBoxLayout(self.results_group)
        results_layout.setContentsMargins(5, 10, 5, 5)
        results_layout.setSpacing(5)
        results_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.mean_sd_result_label = QtWidgets.QLabel("Mean ± SD: --")
        self.mean_sd_result_label.setToolTip("Calculated Baseline Mean ± Standard Deviation")
        results_layout.addWidget(self.mean_sd_result_label)
        self.status_label = QtWidgets.QLabel("Status: Idle")
        self.status_label.setWordWrap(True)
        results_layout.addWidget(self.status_label)
        self._setup_save_button(results_layout)
        results_layout.addStretch(1)
        # Set size policy for Col 3
        self.results_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        top_controls_layout.addWidget(self.results_group)

        # Add top controls area to main layout
        main_layout.addWidget(top_controls_widget)

        # --- Bottom Plot Area --- 
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout)
        
        main_layout.addWidget(plot_container, stretch=1) # Plot stretches vertically

        # Create baseline-specific plot items but don't add to plot yet
        # They will be added when data is loaded to prevent Qt graphics errors
        if self.plot_widget:
            self.interactive_region = pg.LinearRegionItem(values=[0, 0.1], bounds=[0, 1], movable=True)
            self.interactive_region.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 0, 30)))

            # Create InfiniteLine objects for showing baseline statistics
            self.baseline_mean_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', width=2))
            self.baseline_plus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
            self.baseline_minus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
            
            # Automatic and manual mode lines (gray dashed)
            self.auto_plus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(color=(128, 128, 128), style=QtCore.Qt.PenStyle.DashLine))
            self.auto_minus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(color=(128, 128, 128), style=QtCore.Qt.PenStyle.DashLine))
            
            # Plot items will be added when data is loaded

        log.debug("Baseline Analysis Tab UI setup complete (3-Column Top Layout).")
        self._on_mode_changed(initial_call=True)

    # --- ADDED: Method to clear auto-calculation visualization lines ---
    def _clear_auto_baseline_visualization_lines(self):
        """Removes the temporary grey dashed lines used for auto-baseline visualization."""
        # Check and remove items safely
        if self.auto_plus_sd_line is not None and self.auto_plus_sd_line.scene() is not None:
            try:
                self.plot_widget.removeItem(self.auto_plus_sd_line)
                self.auto_plus_sd_line = None # Clear reference after removal
            except Exception as e:
                log.warning(f"Could not remove auto-baseline visualization line (+SD): {e}")
        if self.auto_minus_sd_line is not None and self.auto_minus_sd_line.scene() is not None:
            try:
                self.plot_widget.removeItem(self.auto_minus_sd_line)
                self.auto_minus_sd_line = None # Clear reference after removal
            except Exception as e:
                log.warning(f"Could not remove auto-baseline visualization line (-SD): {e}")
        # log.debug("Cleared auto-baseline visualization lines.")
    # --- END ADDED ---

    def _connect_signals(self):
        # Connect signals specific to Baseline tab widgets.
        # Inherited combo box signal handled by BaseAnalysisTab (_on_analysis_item_selected)
        # NOTE: Channel and Data Source signals are now connected by BaseAnalysisTab._setup_data_selection_ui

        # Connect analysis mode change
        # self.mode_button_group.buttonClicked.connect(self._on_mode_changed) <-- Old
        self.mode_combobox.currentIndexChanged.connect(self._on_mode_changed) # Use combobox

        # Connect manual time edits (trigger analysis only in manual mode)
        self.manual_start_time_spinbox.editingFinished.connect(self._trigger_baseline_analysis_if_manual)
        self.manual_end_time_spinbox.editingFinished.connect(self._trigger_baseline_analysis_if_manual)

        # Connect interactive region change (trigger analysis only in interactive mode)
        self.interactive_region.sigRegionChangeFinished.connect(self._trigger_baseline_analysis_if_interactive)

        # Connect Run Button (for Auto/Manual modes)
        self.run_button.clicked.connect(self._trigger_analysis_from_button)

        # --- REMOVED: Connections for non-existent calculate buttons ---
        # self.calculate_button.clicked.connect(self._trigger_rmp_analysis)
        # self.auto_calculate_button.clicked.connect(self._run_auto_rmp_analysis)
        # --- END REMOVED ---

    # --- Overridden Methods from Base ---
    def _update_ui_for_selected_item(self):
        """
        Update the Baseline tab UI when a new analysis item is selected.
        NOTE: Channel/data source population and plotting are now handled by BaseAnalysisTab.
        This method only handles mode-specific UI updates.
        """
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        
        # Clear previous analysis results
        self._current_plot_data = None
        if self.mean_sd_result_label: 
            self.mean_sd_result_label.setText("Mean ± SD: --")
        if self.save_button:
            self.save_button.setEnabled(False)
        
        # Determine if analysis can be performed based on data availability
        # BaseAnalysisTab has already loaded the recording and will populate comboboxes
        can_analyze = (self._selected_item_recording is not None and 
                      bool(self._selected_item_recording.channels))
        
        # Enable/disable analysis parameter controls
        self.analysis_params_group.setEnabled(can_analyze)
        
        # Update mode-specific controls
        self._on_mode_changed()

    # --- PHASE 1 REFACTORING: Hook for RMP-Specific Plot Items ---
    def _on_data_plotted(self):
        """
        Hook called by BaseAnalysisTab after plotting main data trace.
        Adds RMP-specific plot items: interactive region, baseline visualization lines.
        """
        log.debug(f"{self.get_display_name()}: _on_data_plotted hook called")
        
        # Clear any previous baseline visualization lines
        self._clear_baseline_visualization_lines()
        
        # Validate that base class plotted data successfully
        if not self._current_plot_data or 'time' not in self._current_plot_data:
            log.debug("No plot data available, skipping RMP-specific items")
            return

        time_vec = self._current_plot_data['time']
        
        # Set interactive region bounds based on plotted data
        min_t, max_t = time_vec[0], time_vec[-1]
        self.interactive_region.setBounds([min_t, max_t])
        
        # Keep current region if valid, otherwise reset to default
        rgn_start, rgn_end = self.interactive_region.getRegion()
        if rgn_start < min_t or rgn_end > max_t or rgn_start >= rgn_end:
            # Set default region (first 100ms or 10% of trace, whichever is smaller)
            default_end = min(min_t + 0.1, min_t + (max_t - min_t) * 0.1, max_t)
            self.interactive_region.setRegion([min_t, default_end])
            log.debug(f"Reset interactive region to default: [{min_t:.4f}, {default_end:.4f}]")
        else:
            log.debug(f"Interactive region is valid: [{rgn_start:.4f}, {rgn_end:.4f}]")

        # Add interactive region to plot (removed by base class clear())
        self.plot_widget.addItem(self.interactive_region)

        # Plot baseline visualization lines if previous results exist
        self._plot_baseline_visualization_lines()

        # Update UI control states
        self._update_analysis_controls_state()
        
        log.debug(f"{self.get_display_name()}: RMP-specific plot items added successfully")
    # --- END PHASE 1 REFACTORING ---

    # --- ADDED: Helper to clear Baseline/SD lines ---
    def _clear_baseline_visualization_lines(self):
        """Removes Baseline mean and SD lines from the plot."""
        items_to_remove = []
        if hasattr(self, 'baseline_mean_line') and self.baseline_mean_line is not None:
            items_to_remove.append(self.baseline_mean_line)
            self.baseline_mean_line = None # Prevent dangling reference
        if hasattr(self, 'baseline_plus_sd_line') and self.baseline_plus_sd_line is not None:
            items_to_remove.append(self.baseline_plus_sd_line)
            self.baseline_plus_sd_line = None
        if hasattr(self, 'baseline_minus_sd_line') and self.baseline_minus_sd_line is not None:
            items_to_remove.append(self.baseline_minus_sd_line)
            self.baseline_minus_sd_line = None

        for item in items_to_remove:
            if item.scene() is not None: # Check if item is actually in the plot
                try:
                    self.plot_widget.removeItem(item)
                    # log.debug(f"Removed item: {type(item)}")
                except Exception as e:
                    log.warning(f"Could not remove item {item}: {e}")

    # --- ADDED: Helper to plot Baseline/SD lines ---
    def _plot_baseline_visualization_lines(self):
        """Plots the Baseline mean line and optionally SD lines based on _last_baseline_result."""
        log.debug("_plot_baseline_visualization_lines called.")

        # --- Start: Always clear previous lines first ---
        self._clear_baseline_visualization_lines()
        # --- End: Always clear previous lines first ---

        if not hasattr(self, '_last_baseline_result') or self._last_baseline_result is None:
            log.debug("  Skipping Baseline line plotting: No last result.")
            return

        baseline_value = self._last_baseline_result.get('baseline_mean')
        baseline_sd = self._last_baseline_result.get('baseline_sd')
        units = self._last_baseline_result.get('baseline_units', '?')

        if baseline_value is not None and np.isfinite(baseline_value):
            log.debug("Preparing to plot Baseline visualization lines.")
            # Plot Mean Baseline Line
            mean_pen = pg.mkPen('r', width=2)
            # Use InfLineLabel for hover effect
            mean_label_opts = {'position': 0.5, 'color': 'r', 'movable': False, 'anchor': (0.5, 1)} # Removed offset
            self.baseline_mean_line = pg.InfiniteLine(
                pos=baseline_value, angle=0, pen=mean_pen, movable=False,
                label=f"Mean = {baseline_value:.3f} {units}", labelOpts=mean_label_opts
            )
            self.baseline_mean_line.label.setPos(0, 5) # Offset label 5 pixels down
            self.plot_widget.addItem(self.baseline_mean_line)
            log.debug(f"  Added Baseline mean line at {baseline_value:.3f} {units}")

            # Plot SD Lines (if SD is valid)
            if baseline_sd is not None and np.isfinite(baseline_sd) and baseline_sd > 0:
                sd_pen = pg.mkPen('r', width=1, style=QtCore.Qt.PenStyle.DashLine)
                upper_sd_val = baseline_value + baseline_sd
                lower_sd_val = baseline_value - baseline_sd

                # Upper SD Line
                upper_label_opts = {'position': 0.8, 'color': 'k', 'movable': False, 'anchor': (0.5, 0)} # Removed offset
                self.baseline_plus_sd_line = pg.InfiniteLine(
                    pos=upper_sd_val, angle=0, pen=sd_pen, movable=False,
                    label=f"+SD = {upper_sd_val:.3f}", labelOpts=upper_label_opts
                )
                self.baseline_plus_sd_line.label.setPos(0, -5) # Offset label 5 pixels up
                self.plot_widget.addItem(self.baseline_plus_sd_line)
                log.debug(f"  Added Baseline +SD line at {upper_sd_val:.3f}")

                # Lower SD Line
                lower_label_opts = {'position': 0.2, 'color': 'k', 'movable': False, 'anchor': (0.5, 1)} # Removed offset
                self.baseline_minus_sd_line = pg.InfiniteLine(
                    pos=lower_sd_val, angle=0, pen=sd_pen, movable=False,
                    label=f"-SD = {lower_sd_val:.3f}", labelOpts=lower_label_opts
                )
                self.baseline_minus_sd_line.label.setPos(0, 5) # Offset label 5 pixels down
                self.plot_widget.addItem(self.baseline_minus_sd_line)
                log.debug(f"  Added Baseline -SD line at {lower_sd_val:.3f}")
            else:
                log.debug(f"  Skipping SD lines: SD is None, zero, or non-finite ({baseline_sd}).")
        else:
            log.debug(f"  Skipping Baseline line plotting: Mean value is None or non-finite ({baseline_value}).")

    # --- Analysis Logic ---
    @QtCore.Slot()
    def _on_mode_changed(self, initial_call=False): # Add initial_call flag
        """Handles switching between interactive, automatic, and manual modes based on ComboBox."""
        # --- ADDED: Guard clause ---
        if not self.mode_combobox:
            log.warning("_on_mode_changed called before mode_combobox was initialized.")
            return
        # --- END ADDED ---

        current_mode_text = self.mode_combobox.currentText()
        is_interactive = (current_mode_text == "Interactive")
        is_automatic = (current_mode_text == "Automatic")
        is_manual = (current_mode_text == "Manual")

        # --- UI Element Visibility/State ---
        # Interactive Region
        if self.interactive_region:
            self.interactive_region.setVisible(is_interactive)
            self.interactive_region.setMovable(is_interactive)
        
        # Manual Time Group
        if self.manual_time_group:
            self.manual_time_group.setVisible(is_manual)
            # Enable spinboxes only in manual mode (and if data exists)
            has_data = self._current_plot_data is not None
            self.manual_time_group.setEnabled(is_manual and has_data)
        
        # Auto Threshold Group
        if self.auto_threshold_group:
            self.auto_threshold_group.setVisible(is_automatic)
            # Enable threshold spinbox only in auto mode (and if data exists)
            has_data = self._current_plot_data is not None
            self.auto_threshold_group.setEnabled(is_automatic and has_data)

        # Run Button (Visible for Auto and Manual)
        if self.run_button:
            self.run_button.setVisible(is_automatic or is_manual)
            # Enable button only if data is plotted in Auto/Manual mode
            has_data = self._current_plot_data is not None
            self.run_button.setEnabled(has_data and (is_automatic or is_manual))

        log.debug(f"Baseline analysis mode changed to: {current_mode_text}. Interactive={is_interactive}, Auto={is_automatic}, Manual={is_manual}")

        # --- Trigger Analysis ---
        # MODIFIED: Trigger analysis immediately only if interactive, data loaded, AND NOT the initial call
        if is_interactive and self._current_plot_data and not initial_call:
            # PHASE 2: Use template method
            self._trigger_analysis()
        else:
            # In Auto/Manual, analysis waits for the Run button or specific input edits
            # Optionally clear results or set status message
            self.status_label.setText(f"Status: {current_mode_text} mode - Ready.")
            # Don't automatically clear the result/lines when switching to Auto/Manual
            # Keep the previous result visible until Run is clicked.
            if initial_call:
                log.debug("_on_mode_changed: Initial call from setup, skipping analysis trigger.")

    @QtCore.Slot()
    def _trigger_baseline_analysis_if_manual(self):
        """Slot specifically for manual time edit changes."""
        if self.mode_combobox and self.mode_combobox.currentText() == "Manual":
            log.debug("Manual time edit finished, triggering baseline analysis.")
            # PHASE 2 & 3: Use template method (supports debouncing)
            self._on_parameter_changed()

    @QtCore.Slot()
    def _trigger_baseline_analysis_if_interactive(self):
        """Slot specifically for region changes."""
        if self.mode_combobox and self.mode_combobox.currentText() == "Interactive":
            log.debug("Interactive region change finished, triggering baseline analysis.")
            # PHASE 2 & 3: Use template method (supports debouncing)
            self._on_parameter_changed()

    # --- ADDED: Slot for Run button (Auto/Manual modes) ---
    @QtCore.Slot()
    def _trigger_analysis_from_button(self):
        """Triggers the appropriate analysis when the Run button is clicked."""
        if not self.mode_combobox: return
        
        current_mode_text = self.mode_combobox.currentText()
        log.debug(f"Run button clicked in {current_mode_text} mode.")
        # PHASE 2: Use template method directly (no debouncing for button clicks)
        self._trigger_analysis()
    # --- END ADDED ---

    def _trigger_baseline_analysis(self):
        """Central method to get parameters and run Baseline calculation (Window-based: Interactive/Manual)."""
        # --- ADDED: Check for plot data FIRST --- 
        if not self._current_plot_data or \
           'time' not in self._current_plot_data or \
           'voltage' not in self._current_plot_data:
            log.warning("_trigger_baseline_analysis: Skipping - Plot data missing.")
            self.mean_sd_result_label.setText("Mean ± SD: No Data")
            self._last_baseline_result = None
            self._clear_baseline_visualization_lines()
            self._update_save_button_state()
            self.status_label.setText("Status: Error - No data plotted.")
            return
        # Retrieve data from stored dict
        # NOTE: Base class now stores data as 'data', not 'voltage'
        time_vec = self._current_plot_data['time']
        voltage_vec = self._current_plot_data.get('data') or self._current_plot_data.get('voltage')
        # --- END ADDED ---

        # --- NEW: Get windows based on current mode (Interactive or Manual) ---
        start_t, end_t = None, None
        current_mode_text = self.mode_combobox.currentText()

        if current_mode_text == "Interactive":
            if not self.interactive_region:
                log.error("Interactive mode selected but region item is missing.")
                self.status_label.setText("Status: Error - Interactive region missing.")
                return
            start_t, end_t = self.interactive_region.getRegion()
            # Update manual spinboxes to reflect region for user feedback
            if self.manual_start_time_spinbox: self.manual_start_time_spinbox.setValue(start_t)
            if self.manual_end_time_spinbox: self.manual_end_time_spinbox.setValue(end_t)
            log.debug(f"Running Baseline (Window-based) in Interactive mode. Region: [{start_t:.4f}, {end_t:.4f}]")
        elif current_mode_text == "Manual":
            if not self.manual_start_time_spinbox or not self.manual_end_time_spinbox:
                log.error("Manual mode selected but spinboxes are missing.")
                self.status_label.setText("Status: Error - Manual time inputs missing.")
                return
            try:
                start_t = self.manual_start_time_spinbox.value()
                end_t = self.manual_end_time_spinbox.value()
                if start_t >= end_t:
                    raise ValueError("Start time must be less than end time.")
                # Update interactive region to match manual input (visual feedback)
                if self.interactive_region: self.interactive_region.setRegion([start_t, end_t])
                log.debug(f"Running Baseline (Window-based) in Manual mode. Times: [{start_t:.4f}, {end_t:.4f}]")
            except ValueError as e:
                log.warning(f"Manual time validation failed: {e}")
                self.status_label.setText(f"Status: Invalid Time ({e})")
                if self.save_button: self.save_button.setEnabled(False)
                self._last_baseline_result = None # Ensure result is cleared on error
                self._clear_baseline_visualization_lines() # Clear lines on error
                return
        else:
            log.warning(f"_trigger_baseline_analysis called in unexpected mode: {current_mode_text}")
            return # Should only be called for Interactive or Manual via respective triggers
        # --- END NEW ---

        # --- Perform Calculation ---
        baseline_result = calculate_baseline_stats(time_vec, voltage_vec, start_t, end_t)
        self._last_baseline_result = None # Clear previous result before storing new one

        # --- Store Result and Update UI ---
        if baseline_result is not None:
            baseline_value, baseline_sd = baseline_result
            units = "V" # Default
            chan_id = self.signal_channel_combobox.currentData() # Use the correct combobox
            if self._selected_item_recording and chan_id:
                channel = self._selected_item_recording.channels.get(chan_id)
                if channel: units = channel.units or "V"

            self.mean_sd_result_label.setText(f"Mean: {baseline_value:.3f} {units} ± SD: {baseline_sd:.3f} {units}") # Use correct label
            log.info(f"Calculated Baseline (Window) = {baseline_value:.3f} {units} ± {baseline_sd:.3f} {units}")

            # --- Store result for saving ---
            self._last_baseline_result = {
                'baseline_mean': baseline_value,
                'baseline_sd': baseline_sd,
                'baseline_units': units,
                # Use the actual mode text from the combobox
                'calculation_method': f'window_{current_mode_text.lower()}'
            }

            # --- REMOVED: Manual plot line handling and save button enable ---

        else: # Calculation failed
            self.mean_sd_result_label.setText("Calculation Error") # Use correct label
            log.warning("Baseline (Window) calculation returned None.")
            # --- REMOVED: Manual save button disable and SD line removal ---

        # --- ADDED: Centralized UI Update --- 
        self._clear_baseline_visualization_lines()
        self._plot_baseline_visualization_lines() # Update plot lines based on _last_baseline_result
        self._update_save_button_state() # Update save button based on _last_baseline_result
        self.status_label.setText(f"Status: Calculation complete ({current_mode_text}).") # Update status
        # --- END ADDED ---

    # --- ADDED: Auto Baseline Calculation Logic --- 
    @QtCore.Slot()
    def _run_auto_baseline_analysis(self):
        """Calculates Baseline Mean/SD using a stable window identification method (replaces mean ± SD)."""
        if not self._current_plot_data:
            log.warning("Skipping Auto Baseline analysis: No data plotted.")
            self.mean_sd_result_label.setText("N/A") # Use correct label
            self._last_baseline_result = None
            self._clear_baseline_visualization_lines()
            self._update_save_button_state()
            self.status_label.setText("Status: Auto - No data.")
            return

        voltage_vec = self._current_plot_data.get('voltage')
        time_vec = self._current_plot_data.get('time')
        if voltage_vec is None or len(voltage_vec) < 2 or time_vec is None or len(time_vec) < 2:
            log.warning("Skipping Auto Baseline analysis: Signal or time data is empty/missing or too short.")
            self.mean_sd_result_label.setText("N/A") # Use correct label
            self._last_baseline_result = None
            self._clear_baseline_visualization_lines()
            self._update_save_button_state()
            self.status_label.setText("Status: Auto - Data invalid.")
            return
            
        sd_threshold = self.auto_sd_threshold_spinbox.value() if self.auto_sd_threshold_spinbox else 0.5
        log.debug(f"Running Auto Baseline Calculation (Mode Based, Tolerance: {sd_threshold:.1f})")
        self.status_label.setText("Status: Auto - Running...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        self._last_baseline_result = None # Clear previous result
        calculation_succeeded = False

        # --- Visualization lines for auto method ---
        self._clear_auto_baseline_visualization_lines() # Clear any previous grey lines
        auto_sd_upper_line = None
        auto_sd_lower_line = None

        try:
            # --- Mode-based Baseline Calculation ---
            # 1. Estimate initial noise (optional, can be used for tolerance)
            end_idx_noise = min(int(0.1 * len(time_vec)), len(time_vec)) # Use up to 10% for noise estimate
            if end_idx_noise > 1 and time_vec[end_idx_noise] - time_vec[0] > 0.1: # Or up to 100ms
                 end_idx_noise = np.searchsorted(time_vec, time_vec[0] + 0.1)
            if end_idx_noise < 2: end_idx_noise = min(10, len(voltage_vec)) # Fallback
            initial_sd = np.std(voltage_vec[:end_idx_noise]) if end_idx_noise > 0 else np.std(voltage_vec)
            log.debug(f"  Initial SD estimate (first {end_idx_noise} points): {initial_sd:.4f} mV (assuming mV)")

            # 2. Round voltage data and find the mode
            rounded_voltage = np.round(voltage_vec, 1) # Round to 1 decimal place
            values, counts = np.unique(rounded_voltage, return_counts=True)
            if len(values) == 0:
                raise ValueError("No unique voltage values found after rounding.")
            mode_voltage_rounded = values[np.argmax(counts)]
            log.debug(f"  Mode of rounded voltage (1 decimal): {mode_voltage_rounded:.1f} mV")

            # 3. Define tolerance band around the mode
            #    Let's use a fixed tolerance for now, e.g., +/- 1 mV
            #    Alternatively, could use +/- N * initial_sd
            tolerance_mv = 1.0 
            lower_bound = mode_voltage_rounded - tolerance_mv
            upper_bound = mode_voltage_rounded + tolerance_mv
            log.debug(f"  Using tolerance band: {lower_bound:.2f} mV to {upper_bound:.2f} mV")

            # 4. Find indices where ORIGINAL voltage falls within the band
            mode_indices = np.where((voltage_vec >= lower_bound) & (voltage_vec <= upper_bound))[0]
            
            if len(mode_indices) < 10: # Require a minimum number of points
                 log.warning(f"Auto Baseline failed: Found only {len(mode_indices)} points within the value band [{lower_bound:.2f}, {upper_bound:.2f}]. Not enough data.")
                 self.mean_sd_result_label.setText("Error: Insufficient data near mode")
                 calculation_succeeded = False
            else:
                log.debug(f"  Found {len(mode_indices)} points within the tolerance band.")
                # 5. Calculate Mean and SD of ORIGINAL voltage at these indices
                values_at_mode = voltage_vec[mode_indices]
                auto_baseline_mean = np.mean(values_at_mode)
                auto_baseline_sd = np.std(values_at_mode)

                # 6. Determine the time window for visualization (using min/max time of found indices)
                start_idx = mode_indices[0]
                end_idx = mode_indices[-1]
                start_time = time_vec[start_idx]
                end_time = time_vec[end_idx]
                log.debug(f"  Calculated Baseline based on mode: Mean={auto_baseline_mean:.3f}, SD={auto_baseline_sd:.3f}")
                log.debug(f"  Corresponding time window (min/max index): [{start_time:.4f}s, {end_time:.4f}s]")

                # --- Visualization ---
                # Grey lines are optional for mode method, maybe remove? Let's keep for now.
                vis_pen = pg.mkPen(color=(128, 128, 128), style=QtCore.Qt.PenStyle.DashLine)
                auto_sd_upper_line = pg.InfiniteLine(pos=auto_baseline_mean + auto_baseline_sd, angle=0, pen=vis_pen)
                auto_sd_lower_line = pg.InfiniteLine(pos=auto_baseline_mean - auto_baseline_sd, angle=0, pen=vis_pen)
                self.plot_widget.addItem(auto_sd_upper_line)
                self.plot_widget.addItem(auto_sd_lower_line)
                
                # Highlight the region used for auto-calc
                if self.interactive_region:
                    # Adjust end time slightly if end_idx points to last element to avoid issues
                    safe_end_time = time_vec[min(end_idx, len(time_vec) - 1)]
                    self.interactive_region.setRegion([start_time, safe_end_time])
                    self.interactive_region.setBrush(QtGui.QBrush(QtGui.QColor(128, 128, 128, 50))) # Grey brush
                
                # --- Store Result ---
                units = "?" # Default
                chan_id = self.signal_channel_combobox.currentData()
                if self._selected_item_recording and chan_id:
                    channel = self._selected_item_recording.channels.get(chan_id)
                    if channel and hasattr(channel, 'units') and channel.units:
                        units = channel.units 
                    else:
                         log.warning(f"Could not determine units for channel {chan_id}, assuming unknown.")
                         units = "?"

                self.mean_sd_result_label.setText(f"Mean: {auto_baseline_mean:.3f} {units} ± SD: {auto_baseline_sd:.3f} {units}")
                log.info(f"Auto Calculated Baseline (Mode Based) = {auto_baseline_mean:.3f} {units} ± {auto_baseline_sd:.3f} {units}")

                self._last_baseline_result = {
                    'baseline_mean': auto_baseline_mean,
                    'baseline_sd': auto_baseline_sd,
                    'baseline_units': units,
                    'calculation_method': f'auto_mode_tolerance={tolerance_mv:.1f}mV'
                }
                calculation_succeeded = True

        except Exception as e:
            log.error(f"Error during auto Baseline calculation (mode-based): {e}", exc_info=True)

        finally:
            # 1. Clear the main (red) Baseline lines from any previous calculation
            self._clear_baseline_visualization_lines()
            
            # 2. Plot the final (red) lines ONLY if this auto-calculation succeeded
            if calculation_succeeded:
                log.debug("  Auto Baseline succeeded. Plotting final (red) result lines.")
                self._plot_baseline_visualization_lines() # Plot based on _last_baseline_result
                self.status_label.setText("Status: Auto - Calculation complete.")
            else:
                log.debug("  Auto Baseline failed. No final lines plotted.")
                self.status_label.setText("Status: Auto - Calculation failed.")
                # Reset region brush if it was changed
                if self.interactive_region:
                     self.interactive_region.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 0, 30))) # Reset to green

            # 3. Remove the temporary grey visualization lines *after* potential plotting of red lines
            #    Need to store references outside the try block if needed here.
            #    Let's modify _clear_auto_rmp_visualization_lines to handle this.
            self._clear_auto_baseline_visualization_lines() # Call the dedicated clearer

            # 4. Update save button state
            self._update_save_button_state()
            # 5. Restore cursor
            QtWidgets.QApplication.restoreOverrideCursor()
            # 6. Auto-range
            self.plot_widget.autoRange()
            log.debug("  Auto Baseline final block finished.")

    def cleanup(self):
        # Clean up plot items if necessary
        if self.plot_widget:
            self._clear_baseline_visualization_lines() # Clear final Baseline lines
            self._clear_auto_baseline_visualization_lines() # Clear auto-calc temp lines
            # Remove interactive region
            if self.interactive_region and self.interactive_region.scene():
                self.plot_widget.removeItem(self.interactive_region)
            self.plot_widget.clear() # Ensure plot is cleared
        # Call superclass cleanup if it does anything useful
        super().cleanup()

    # --- ADDED BACK: Method to update control enabled states ---
    def _update_analysis_controls_state(self):
        # Enable/disable analysis controls based on whether data is plotted.
        has_data = (self._current_plot_data is not None)
        # Check if a valid analysis item is actually selected
        has_valid_selection = (self._selected_item_index >= 0 and self._selected_item_recording is not None)
        
        # Enable channel and data source selection only if an item is selected
        self.signal_channel_combobox.setEnabled(has_valid_selection) # Use correct combobox
        self.data_source_combobox.setEnabled(has_valid_selection and self.data_source_combobox.count() > 0 and self.data_source_combobox.currentData() is not None)

        # Enable the rest only if data is actually plotted (implies valid selection AND successful plot)
        if self.mode_combobox: self.mode_combobox.setEnabled(has_data) # Use correct mode control
        
        # Delegate mode-specific enables/visibility to _on_mode_changed
        if has_data:
             self._on_mode_changed() # Let this handle visibility/enabled state of regions, groups, run button
        else:
            # Explicitly disable mode-specific groups if no data
            if self.manual_time_group: self.manual_time_group.setEnabled(False)
            if self.auto_threshold_group: self.auto_threshold_group.setEnabled(False)
            if self.run_button: self.run_button.setEnabled(False)
            if self.interactive_region: self.interactive_region.setVisible(False)

        # Base class handles save button state based on self._last_result
        self._update_save_button_state() # Call the specific save button updater
    # --- END ADDED BACK ---

    def _update_save_button_state(self):
        # Override if Baseline requires specific conditions
        # Enable save button only if a valid Baseline result is stored.
        can_save = hasattr(self, '_last_baseline_result') and self._last_baseline_result is not None
        # Directly enable/disable the save button
        if self.save_button:
            self.save_button.setEnabled(can_save)

    # --- Implementation of BaseAnalysisTab method --- 
    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Gathers the specific Baseline result details for saving."""
        # UPDATED: Use stored result instead of parsing label
        if not hasattr(self, '_last_baseline_result') or self._last_baseline_result is None:
             log.debug("_get_specific_result_data: No calculated Baseline result stored.")
             return None

        mean_val = self._last_baseline_result.get('baseline_mean')
        sd_val = self._last_baseline_result.get('baseline_sd')
        units = self._last_baseline_result.get('baseline_units', '?')
        method = self._last_baseline_result.get('calculation_method')

        if mean_val is None or sd_val is None or method is None:
             log.error(f"_get_specific_result_data: Stored Baseline result is incomplete: {self._last_baseline_result}")
             return None

        # Get source info
        channel_id = self.signal_channel_combobox.currentData()
        channel_name = self.signal_channel_combobox.currentText().split(' (')[0]
        data_source = self.data_source_combobox.currentData()
        data_source_text = self.data_source_combobox.currentText()

        if channel_id is None or data_source is None:
            log.warning("Cannot get specific Baseline data: Missing channel or data source selection.")
            return None

        specific_data = {
            'baseline_mean': mean_val,
            'baseline_sd': sd_val,
            'baseline_units': units,
            'channel_id': channel_id,
            'channel_name': channel_name,
            'data_source': data_source,
            'data_source_label': data_source_text,
            'calculation_method': method
        }

        # Add window parameters only if a window method was used
        if 'window' in method:
             current_mode_text = self.mode_combobox.currentText()
             if self.interactive_region:
                 start_s, end_s = self.interactive_region.getRegion()
                 specific_data['baseline_start_s'] = start_s
                 specific_data['baseline_end_s'] = end_s
             specific_data['analysis_mode'] = current_mode_text
        
        # Add threshold parameter only if auto method was used
        if 'auto_stable_window' in method:
            threshold_val = self.auto_sd_threshold_spinbox.value() if self.auto_sd_threshold_spinbox else None
            specific_data['auto_sd_threshold'] = threshold_val
            specific_data['analysis_mode'] = "Automatic"

        log.debug(f"_get_specific_result_data returning: {specific_data}")
        return specific_data
    # --- END Implementation ---

    # --- PHASE 2: Template Method Pattern Implementation ---
    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """
        Gather analysis parameters based on current mode.
        
        Returns:
            Dictionary with mode and mode-specific parameters.
        """
        if not self.mode_combobox:
            log.warning("_gather_analysis_parameters: mode_combobox not initialized")
            return {'mode': 'unknown'}
        
        current_mode_text = self.mode_combobox.currentText()
        params = {'mode': current_mode_text.lower()}
        
        if current_mode_text == "Interactive":
            if self.interactive_region:
                start_t, end_t = self.interactive_region.getRegion()
                params['start_time'] = start_t
                params['end_time'] = end_t
        
        elif current_mode_text == "Manual":
            if self.manual_start_time_spinbox and self.manual_end_time_spinbox:
                params['start_time'] = self.manual_start_time_spinbox.value()
                params['end_time'] = self.manual_end_time_spinbox.value()
        
        elif current_mode_text == "Automatic":
            if self.auto_sd_threshold_spinbox:
                params['sd_threshold'] = self.auto_sd_threshold_spinbox.value()
            else:
                params['sd_threshold'] = 0.5  # Default
        
        log.debug(f"Gathered parameters: {params}")
        return params
    
    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Execute baseline analysis based on mode.
        
        Args:
            params: Analysis parameters from _gather_analysis_parameters
            data: Current plot data
        
        Returns:
            Dictionary with analysis results or None on failure.
        """
        # Validate data
        if not data or 'time' not in data:
            log.warning("_execute_core_analysis: Missing plot data")
            return None
        
        time_vec = data['time']
        voltage_vec = data.get('data') if data.get('data') is not None else data.get('voltage')
        
        if voltage_vec is None or len(voltage_vec) < 2:
            log.warning("_execute_core_analysis: Invalid voltage data")
            return None
        
        # Get units
        units = "V"  # Default
        chan_id = self.signal_channel_combobox.currentData() if self.signal_channel_combobox else None
        if self._selected_item_recording and chan_id:
            channel = self._selected_item_recording.channels.get(chan_id)
            if channel:
                units = channel.units or "V"
        
        mode = params.get('mode', 'unknown')
        
        # Branch based on mode
        if mode in ['interactive', 'manual']:
            # Window-based analysis
            start_t = params.get('start_time')
            end_t = params.get('end_time')
            
            if start_t is None or end_t is None:
                log.warning(f"_execute_core_analysis: Missing time parameters for {mode} mode")
                return None
            
            if start_t >= end_t:
                log.warning(f"_execute_core_analysis: Invalid time range [{start_t}, {end_t}]")
                return None
            
            # Use existing calculate_baseline_stats function
            baseline_result = calculate_baseline_stats(time_vec, voltage_vec, start_t, end_t)
            
            if baseline_result is None:
                return None
            
            baseline_value, baseline_sd = baseline_result
            
            return {
                'baseline_mean': baseline_value,
                'baseline_sd': baseline_sd,
                'baseline_units': units,
                'calculation_method': f'window_{mode}',
                'start_time': start_t,
                'end_time': end_t
            }
        
        elif mode == 'automatic':
            # Mode-based analysis
            sd_threshold = params.get('sd_threshold', 0.5)
            
            try:
                # Mode-based calculation (similar to _run_auto_baseline_analysis)
                # 1. Estimate initial noise
                end_idx_noise = min(int(0.1 * len(time_vec)), len(time_vec))
                if end_idx_noise > 1 and time_vec[end_idx_noise] - time_vec[0] > 0.1:
                    end_idx_noise = np.searchsorted(time_vec, time_vec[0] + 0.1)
                if end_idx_noise < 2:
                    end_idx_noise = min(10, len(voltage_vec))
                
                # 2. Round voltage and find mode
                rounded_voltage = np.round(voltage_vec, 1)
                values, counts = np.unique(rounded_voltage, return_counts=True)
                
                if len(values) == 0:
                    log.warning("_execute_core_analysis: No unique voltage values found")
                    return None
                
                mode_voltage_rounded = values[np.argmax(counts)]
                
                # 3. Define tolerance band
                tolerance_mv = 1.0
                lower_bound = mode_voltage_rounded - tolerance_mv
                upper_bound = mode_voltage_rounded + tolerance_mv
                
                # 4. Find indices within band
                mode_indices = np.where((voltage_vec >= lower_bound) & (voltage_vec <= upper_bound))[0]
                
                if len(mode_indices) < 10:
                    log.warning(f"_execute_core_analysis: Only {len(mode_indices)} points within band")
                    return None
                
                # 5. Calculate mean and SD
                values_at_mode = voltage_vec[mode_indices]
                auto_baseline_mean = np.mean(values_at_mode)
                auto_baseline_sd = np.std(values_at_mode)
                
                # 6. Get time window
                start_time = time_vec[mode_indices[0]]
                end_time = time_vec[mode_indices[-1]]
                
                return {
                    'baseline_mean': auto_baseline_mean,
                    'baseline_sd': auto_baseline_sd,
                    'baseline_units': units,
                    'calculation_method': f'auto_mode_tolerance={tolerance_mv:.1f}mV',
                    'start_time': start_time,
                    'end_time': end_time,
                    'mode_voltage': mode_voltage_rounded,
                    'tolerance': tolerance_mv
                }
            
            except Exception as e:
                log.error(f"_execute_core_analysis: Auto mode failed: {e}", exc_info=True)
                return None
        
        else:
            log.warning(f"_execute_core_analysis: Unknown mode '{mode}'")
            return None
    
    def _display_analysis_results(self, results: Dict[str, Any]):
        """
        Display analysis results in the UI.
        
        Args:
            results: Analysis results dictionary
        """
        baseline_mean = results.get('baseline_mean')
        baseline_sd = results.get('baseline_sd')
        units = results.get('baseline_units', 'V')
        
        if baseline_mean is not None and baseline_sd is not None:
            self.mean_sd_result_label.setText(
                f"Mean: {baseline_mean:.3f} {units} ± SD: {baseline_sd:.3f} {units}"
            )
            log.info(f"Baseline result displayed: {baseline_mean:.3f} {units} ± {baseline_sd:.3f} {units}")
            
            # Store result for saving
            self._last_baseline_result = {
                'baseline_mean': baseline_mean,
                'baseline_sd': baseline_sd,
                'baseline_units': units,
                'calculation_method': results.get('calculation_method', 'unknown')
            }
            
            # Update status
            mode = results.get('calculation_method', 'unknown')
            self.status_label.setText(f"Status: Calculation complete ({mode})")
        else:
            self.mean_sd_result_label.setText("Calculation Error")
            self.status_label.setText("Status: Error")
            self._last_baseline_result = None
    
    def _plot_analysis_visualizations(self, results: Dict[str, Any]):
        """
        Update plot visualizations based on analysis results.
        
        Args:
            results: Analysis results dictionary
        """
        # Clear existing visualization lines
        self._clear_baseline_visualization_lines()
        
        # Get baseline values
        baseline_mean = results.get('baseline_mean')
        baseline_sd = results.get('baseline_sd')
        
        if baseline_mean is None or not np.isfinite(baseline_mean):
            return
        
        # For automatic mode, update interactive region to show detected window
        mode = results.get('calculation_method', '')
        if 'auto' in mode and self.interactive_region:
            start_time = results.get('start_time')
            end_time = results.get('end_time')
            if start_time is not None and end_time is not None:
                self.interactive_region.setRegion([start_time, end_time])
                self.interactive_region.setBrush(QtGui.QBrush(QtGui.QColor(128, 128, 128, 50)))
        
        # Plot baseline lines (same as _plot_baseline_visualization_lines)
        baseline_pen = pg.mkPen(color='green', width=2, style=QtCore.Qt.PenStyle.DashLine)
        label_opts = {
            'position': 0.1, 'color': 'k', 'movable': False, 'anchor': (0.5, 0.5)
        }
        
        self.baseline_mean_line = pg.InfiniteLine(
            pos=baseline_mean, angle=0, pen=baseline_pen, movable=False,
            label=f"Baseline = {baseline_mean:.3f}", labelOpts=label_opts
        )
        self.plot_widget.addItem(self.baseline_mean_line)
        
        # Plot SD lines if valid
        if baseline_sd is not None and np.isfinite(baseline_sd) and baseline_sd > 0:
            upper_sd_val = baseline_mean + baseline_sd
            lower_sd_val = baseline_mean - baseline_sd
            
            sd_pen = pg.mkPen(color='orange', width=1, style=QtCore.Qt.PenStyle.DashLine)
            
            upper_label_opts = {'position': 0.2, 'color': 'k', 'movable': False, 'anchor': (0.5, 0)}
            self.baseline_plus_sd_line = pg.InfiniteLine(
                pos=upper_sd_val, angle=0, pen=sd_pen, movable=False,
                label=f"+SD = {upper_sd_val:.3f}", labelOpts=upper_label_opts
            )
            self.baseline_plus_sd_line.label.setPos(0, -5)
            self.plot_widget.addItem(self.baseline_plus_sd_line)
            
            lower_label_opts = {'position': 0.2, 'color': 'k', 'movable': False, 'anchor': (0.5, 1)}
            self.baseline_minus_sd_line = pg.InfiniteLine(
                pos=lower_sd_val, angle=0, pen=sd_pen, movable=False,
                label=f"-SD = {lower_sd_val:.3f}", labelOpts=lower_label_opts
            )
            self.baseline_minus_sd_line.label.setPos(0, 5)
            self.plot_widget.addItem(self.baseline_minus_sd_line)
        
        log.debug("Baseline visualization updated via template method")
    # --- END PHASE 2 ---


# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = BaselineAnalysisTab