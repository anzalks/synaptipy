# src/Synaptipy/application/gui/analysis_tabs/rmp_tab.py
# -*- coding: utf-8 -*-
# Analysis sub-tab for calculating Resting Membrane Potential (RMP).
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

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rmp_tab')

# --- RMP Calculation Function ---
def calculate_rmp(time: np.ndarray, voltage: np.ndarray, start_time: float, end_time: float) -> Optional[Tuple[float, float]]:
    # Calculates the Resting Membrane Potential (RMP) and its standard deviation
    # over a specified time window.
    # Args:
    #     time: 1D numpy array of time values.
    #     voltage: 1D numpy array of voltage values.
    #     start_time: Start time for the baseline window.
    #     end_time: End time for the baseline window.
    # Returns:
    #     A tuple containing (mean_voltage, std_dev_voltage) or None if the window
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
        baseline_voltage = voltage[indices]
        rmp_mean = np.mean(baseline_voltage)
        rmp_sd = np.std(baseline_voltage)
        return rmp_mean, rmp_sd # Return both values
    except Exception as e:
        log.error(f"Error calculating RMP/SD between {start_time}s and {end_time}s: {e}", exc_info=True)
        return None

# --- RMP Analysis Tab Class ---
class RmpAnalysisTab(BaseAnalysisTab):
    # QWidget for RMP analysis with interactive plotting.

    # Define constants for analysis modes
    MODE_INTERACTIVE = 0
    MODE_MANUAL = 1

    def __init__(self, neo_adapter: NeoAdapter, parent=None): # Corrected signature
        # Pass neo_adapter to superclass constructor
        super().__init__(neo_adapter=neo_adapter, parent=parent)

        # --- UI References specific to RMP ---
        self.channel_combobox: Optional[QtWidgets.QComboBox] = None # Single channel selection for plot interaction
        # --- ADDED: Data Source Selection ---
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        # --- END ADDED ---
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
        self.rmp_result_label: Optional[QtWidgets.QLabel] = None # To display the calculated RMP
        # Plotting Interaction
        self.interactive_region: Optional[pg.LinearRegionItem] = None
        # ADDED: Calculate Button
        self.calculate_button: Optional[QtWidgets.QPushButton] = None
        # ADDED: Auto Calculate Button
        self.auto_calculate_button: Optional[QtWidgets.QPushButton] = None
        # ADDED: Plot item for RMP line
        self.rmp_line_item: Optional[pg.InfiniteLine] = None
        # Store currently plotted data for analysis
        self._current_plot_data: Optional[Dict[str, np.ndarray]] = None # {'time':..., 'voltage':...}
        # ADDED: Store last calculated RMP result
        self._last_rmp_result: Optional[Dict[str, Any]] = None # {value, sd, method}
        # ADDED: Plot items for SD lines
        self.rmp_sd_upper_line_item: Optional[pg.InfiniteLine] = None
        self.rmp_sd_lower_line_item: Optional[pg.InfiniteLine] = None

        self._setup_ui()
        self._connect_signals()
        self._on_mode_changed() # Set initial UI state based on default mode

    def get_display_name(self) -> str:
        # Returns the name for the sub-tab.
        return "Resting Potential (RMP)"

    def _setup_ui(self):
        """Recreate RMP analysis UI with a 3-column top layout."""
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
        # 1b. Voltage Channel
        self.voltage_channel_combobox = QtWidgets.QComboBox()
        self.voltage_channel_combobox.setToolTip("Select the voltage channel to analyze.")
        self.voltage_channel_combobox.setEnabled(False)
        data_selection_layout.addRow("Voltage Channel:", self.voltage_channel_combobox)
        # 1c. Data Source
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)
        data_selection_layout.addRow("Data Source:", self.data_source_combobox)
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
        self.rmp_result_label = QtWidgets.QLabel("RMP: --")
        self.rmp_result_label.setToolTip("Calculated Resting Membrane Potential (Mean ± SD)")
        results_layout.addWidget(self.rmp_result_label)
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

        # --- Plot items specific to RMP ---
        if self.plot_widget:
            self.interactive_region = pg.LinearRegionItem(values=[0, 0.1], bounds=[0, 1], movable=True)
            self.interactive_region.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 0, 30)))
            self.plot_widget.addItem(self.interactive_region)
            self.interactive_region.setVisible(True) # Default visibility handled by _on_mode_changed

            self.rmp_mean_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', width=2))
            self.rmp_plus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
            self.rmp_minus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
            self.plot_widget.addItem(self.rmp_mean_line); self.plot_widget.addItem(self.rmp_plus_sd_line); self.plot_widget.addItem(self.rmp_minus_sd_line)
            self._clear_rmp_visualization_lines() # Hide initially

            self.auto_plus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(color=(128, 128, 128), style=QtCore.Qt.PenStyle.DashLine))
            self.auto_minus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(color=(128, 128, 128), style=QtCore.Qt.PenStyle.DashLine))
            self.plot_widget.addItem(self.auto_plus_sd_line); self.plot_widget.addItem(self.auto_minus_sd_line)
            self._clear_auto_rmp_visualization_lines() # Hide initially
        else:
             log.error("Plot widget not created by base class setup.")

        log.debug("RMP Analysis Tab UI setup complete (3-Column Top Layout).")
        self._on_mode_changed(initial_call=True)

    # --- ADDED: Method to clear auto-calculation visualization lines ---
    def _clear_auto_rmp_visualization_lines(self):
        """Removes the temporary grey dashed lines used for auto-RMP visualization."""
        # Check and remove items safely
        if self.auto_plus_sd_line is not None and self.auto_plus_sd_line.scene() is not None:
            try:
                self.plot_widget.removeItem(self.auto_plus_sd_line)
                self.auto_plus_sd_line = None # Clear reference after removal
            except Exception as e:
                log.warning(f"Could not remove auto-RMP visualization line (+SD): {e}")
        if self.auto_minus_sd_line is not None and self.auto_minus_sd_line.scene() is not None:
            try:
                self.plot_widget.removeItem(self.auto_minus_sd_line)
                self.auto_minus_sd_line = None # Clear reference after removal
            except Exception as e:
                log.warning(f"Could not remove auto-RMP visualization line (-SD): {e}")
        # log.debug("Cleared auto-RMP visualization lines.")
    # --- END ADDED ---

    def _connect_signals(self):
        # Connect signals specific to RMP tab widgets.
        # Inherited combo box signal handled by BaseAnalysisTab (_on_analysis_item_selected)

        # Connect channel selector
        self.voltage_channel_combobox.currentIndexChanged.connect(self._plot_selected_channel_trace)

        # --- ADDED: Connect Data Source Selector ---
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_channel_trace)
        # --- END ADDED ---

        # Connect analysis mode change
        # self.mode_button_group.buttonClicked.connect(self._on_mode_changed) <-- Old
        self.mode_combobox.currentIndexChanged.connect(self._on_mode_changed) # Use combobox

        # Connect manual time edits (trigger analysis only in manual mode)
        self.manual_start_time_spinbox.editingFinished.connect(self._trigger_rmp_analysis_if_manual)
        self.manual_end_time_spinbox.editingFinished.connect(self._trigger_rmp_analysis_if_manual)

        # Connect interactive region change (trigger analysis only in interactive mode)
        self.interactive_region.sigRegionChangeFinished.connect(self._trigger_rmp_analysis_if_interactive)

        # Connect Run Button (for Auto/Manual modes)
        self.run_button.clicked.connect(self._trigger_analysis_from_button)

        # --- REMOVED: Connections for non-existent calculate buttons ---
        # self.calculate_button.clicked.connect(self._trigger_rmp_analysis)
        # self.auto_calculate_button.clicked.connect(self._run_auto_rmp_analysis)
        # --- END REMOVED ---

    # --- Overridden Methods from Base ---
    def _update_ui_for_selected_item(self):
        # Update the RMP tab UI when a new analysis item is selected.
        # Populates channel list, plots data, and enables/disables controls.
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None # Clear previous plot data
        if self.rmp_result_label: 
             self.rmp_result_label.setText("RMP: --") # Reset to default text
        else:
             # This case should ideally not happen if setup is correct
             log.warning("rmp_result_label is None during _update_ui_for_selected_item")
        if self.save_button: self.save_button.setEnabled(False) # Disable save on selection change

        # --- Populate Channel ComboBox ---
        self.voltage_channel_combobox.blockSignals(True)
        self.voltage_channel_combobox.clear()
        can_enable_ui = False
        voltage_channels_found = False # Track if any suitable channels exist
        if self._selected_item_recording and self._selected_item_recording.channels:
            valid_channels = []
            # Populate with voltage channels
            for chan_id, channel in sorted(self._selected_item_recording.channels.items(), key=lambda item: item[0]):
                units_lower = getattr(channel, 'units', '').lower()
                # RMP needs voltage traces
                if 'v' in units_lower:
                    display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{channel.units}]"
                    self.voltage_channel_combobox.addItem(display_name, userData=chan_id)
                    valid_channels.append(chan_id)

            if valid_channels:
                self.voltage_channel_combobox.setCurrentIndex(0) # Select first valid channel
                voltage_channels_found = True # Mark that we found channels
                # can_enable_ui = True # Enable UI is determined later
            else:
                self.voltage_channel_combobox.addItem("No Voltage Channels Found")
        else:
            self.voltage_channel_combobox.addItem("Load Data Item...")

        self.voltage_channel_combobox.setEnabled(voltage_channels_found) # Enable only if voltage channels exist
        self.voltage_channel_combobox.blockSignals(False)

        # --- Populate Data Source ComboBox --- 
        self.data_source_combobox.blockSignals(True)
        self.data_source_combobox.clear()
        self.data_source_combobox.setEnabled(False) # Default to disabled
        can_analyze = False # Can we actually run analysis?

        if voltage_channels_found and self._selected_item_recording: # Need channels and loaded recording
            selected_item_details = self._analysis_items[self._selected_item_index]
            item_type = selected_item_details.get('target_type')
            item_trial_index = selected_item_details.get('trial_index') # 0-based

            # --- Get num_trials and has_average from the first available channel --- 
            num_trials = 0
            has_average = False
            first_channel = next(iter(self._selected_item_recording.channels.values()), None)
            if first_channel:
                 num_trials = getattr(first_channel, 'num_trials', 0)
                 # Check for average data availability (adjust if method name is different)
                 if hasattr(first_channel, 'get_averaged_data') and first_channel.get_averaged_data() is not None:
                     has_average = True 
                 elif hasattr(first_channel, 'has_average_data') and first_channel.has_average_data(): # Alternative check
                     has_average = True
            log.debug(f"Determined from first channel: num_trials={num_trials}, has_average={has_average}")
            # --- End checks --- 

            if item_type == "Current Trial" and item_trial_index is not None and 0 <= item_trial_index < num_trials:
                self.data_source_combobox.addItem(f"Trial {item_trial_index + 1}", userData=item_trial_index)
            elif item_type == "Average Trace" and has_average:
                self.data_source_combobox.addItem("Average Trace", userData="average")
            elif item_type == "Recording" or item_type == "All Trials":
                if has_average:
                    self.data_source_combobox.addItem("Average Trace", userData="average")
                if num_trials > 0:
                    for i in range(num_trials):
                        self.data_source_combobox.addItem(f"Trial {i + 1}", userData=i)
                # Enable only if there are options to choose from
                if self.data_source_combobox.count() > 0:
                    self.data_source_combobox.setEnabled(True)
                    can_analyze = True # Can analyze if there's at least one source
                else:
                    self.data_source_combobox.addItem("No Trials/Average")
            else: # Unknown item type or missing info
                self.data_source_combobox.addItem("Invalid Source Item")

        else: # No recording loaded or no voltage channels
             self.data_source_combobox.addItem("N/A")

        self.data_source_combobox.blockSignals(False)

        # --- Enable/Disable Remaining Controls --- 
        self.analysis_params_group.setEnabled(can_analyze)
        self._on_mode_changed() # Update manual/interactive state based on loaded data availability

        # --- Plot Initial Trace --- 
        if can_analyze:
            self._plot_selected_channel_trace() # Plot the trace for the initially selected channel
        else:
            self.plot_widget.clear() # Ensure plot is clear if no data/channels
        
        # Move this call AFTER plotting to ensure _current_plot_data is set
        self._on_mode_changed() # Update manual/interactive state

    # --- Plotting and Interaction ---
    def _plot_selected_channel_trace(self):
        """Plots the voltage trace for the currently selected channel and data source.""" # Updated docstring
        if not self.plot_widget or not self.voltage_channel_combobox or not self.data_source_combobox or not self._selected_item_recording:
            self._current_plot_data = None
            if self.plot_widget:
                self.plot_widget.clear()
                # Re-add region if cleared
                if self.interactive_region and self.interactive_region not in self.plot_widget.items:
                    self.plot_widget.addItem(self.interactive_region)
            return

        # Clear previous data
        self.plot_widget.clear()
        self._current_plot_data = None
        self._clear_rmp_visualization_lines() # <<< ADDED: Clear RMP/SD lines

        chan_id = self.voltage_channel_combobox.currentData()
        source_data = self.data_source_combobox.currentData() # Trial index (int) or "average" (str)

        if not chan_id or source_data is None:
            self._current_plot_data = None
            self.plot_widget.clear()
            if self.interactive_region and self.interactive_region not in self.plot_widget.items:
                 self.plot_widget.addItem(self.interactive_region)
            return

        channel = self._selected_item_recording.channels.get(chan_id)
        # selected_item_details = self._analysis_items[self._selected_item_index] # Don't need item type here
        # target_type = selected_item_details.get('target_type')
        # trial_index = selected_item_details.get('trial_index') # 0-based or None

        log.debug(f"Plotting RMP trace for Ch {chan_id}, Data Source: {source_data}")

        time_vec, voltage_vec = None, None
        data_label = "Trace Error"

        try:
            if channel:
                # --- Select data based on DATA SOURCE COMBOBOX --- 
                if source_data == "average":
                    voltage_vec = channel.get_averaged_data()
                    time_vec = channel.get_relative_averaged_time_vector()
                    # ADDED: Log values immediately after retrieval
                    log.debug(f"Retrieved average data: voltage_vec is None = {voltage_vec is None}, time_vec is None = {time_vec is None}")
                    data_label = f"{channel.name or chan_id} (Average)"
                elif isinstance(source_data, int):
                    trial_index = source_data # 0-based index from userData
                    if 0 <= trial_index < channel.num_trials:
                        voltage_vec = channel.get_data(trial_index)
                        time_vec = channel.get_relative_time_vector(trial_index)
                        # ADDED: Log values immediately after retrieval
                        log.debug(f"Retrieved trial {trial_index} data: voltage_vec is None = {voltage_vec is None}, time_vec is None = {time_vec is None}")
                        data_label = f"{channel.name or chan_id} (Trial {trial_index + 1})"
                    else:
                        log.warning(f"Invalid trial index {trial_index} requested for Ch {chan_id}")
                else:
                     log.warning(f"Unknown data source selected: {source_data}")
                # --- END data selection --- 

            # --- Plotting --- 
            self.plot_widget.clear() # Clear previous plots
            if time_vec is not None and voltage_vec is not None:
                self.data_plot_item = self.plot_widget.plot(time_vec, voltage_vec, pen='k', name=data_label)

                # --- Get Label from Data Model --- 
                units = channel.units or '?' # Use '?' if units are None/empty
                base_label = channel.get_primary_data_label()
                self.plot_widget.setLabel('left', base_label, units=units)
                # --- End Get Label from Data Model --- 

                self.plot_widget.setLabel('bottom', 'Time', units='s')
                self.plot_widget.setTitle(data_label)
                self._current_plot_data = { # Store data for analysis
                    'time': time_vec,
                    'voltage': voltage_vec
                }
                # Set initial region/bounds based on plotted data
                min_t, max_t = time_vec[0], time_vec[-1]
                self.interactive_region.setBounds([min_t, max_t])
                # Keep current region if valid, otherwise reset
                rgn_start, rgn_end = self.interactive_region.getRegion()
                if rgn_start < min_t or rgn_end > max_t or rgn_start >= rgn_end:
                     # Set default region (e.g., first 100ms or 10% of trace)
                     default_end = min(min_t + 0.1, min_t + (max_t - min_t) * 0.1, max_t)
                     self.interactive_region.setRegion([min_t, default_end])
                     log.debug(f"Resetting region to default: [{min_t}, {default_end}]")
                else:
                    log.debug("Region is within bounds and valid.")
            else:
                self._current_plot_data = None
                log.warning(f"No valid data found to plot for channel {chan_id}")

            # Always re-add region item as clear() removes it
            self.plot_widget.addItem(self.interactive_region)
            self.plot_widget.setTitle(data_label) # Set title for clarity

            # Auto-range the plot initially
            self.plot_widget.autoRange()

            # --- REMOVED: Errant vertical RMP line creation ---
            # if self._current_plot_data:
            #     self.rmp_line_item = pg.InfiniteLine(pos=self._current_plot_data['time'][len(self._current_plot_data['time']) // 2],
            #                                           pen=pg.mkPen(color=(255, 0, 0), width=2),
            #                                           movable=False)
            #     self.plot_widget.addItem(self.rmp_line_item)
            # --- END REMOVED ---

            # --- ADDED: Plot RMP and SD lines if available ---
            self._plot_rmp_visualization_lines()
            # --- END ADDED ---

            # Update UI state (enable/disable buttons etc.)
            self._update_analysis_controls_state()
            # Trigger analysis automatically if in interactive mode initially?
            # self._trigger_rmp_analysis() # Maybe do this explicitly

        except Exception as e:
            log.error(f"Error plotting trace for channel {chan_id}: {e}", exc_info=True)
            self.plot_widget.clear()
            self.plot_widget.addItem(self.interactive_region) # Re-add region on error
            self._current_plot_data = None

        # Trigger analysis after plotting new trace
        # REMOVED: self._trigger_rmp_analysis() 
        # INSTEAD: Let _update_analysis_controls_state handle button states
        self._update_analysis_controls_state() # Update controls based on plot success/failure

    # --- ADDED: Helper to clear RMP/SD lines ---
    def _clear_rmp_visualization_lines(self):
        """Removes RMP mean and SD lines from the plot."""
        items_to_remove = []
        if hasattr(self, 'rmp_line_item') and self.rmp_line_item is not None:
            items_to_remove.append(self.rmp_line_item)
            self.rmp_line_item = None # Prevent dangling reference
        if hasattr(self, 'rmp_sd_upper_line_item') and self.rmp_sd_upper_line_item is not None:
            items_to_remove.append(self.rmp_sd_upper_line_item)
            self.rmp_sd_upper_line_item = None
        if hasattr(self, 'rmp_sd_lower_line_item') and self.rmp_sd_lower_line_item is not None:
            items_to_remove.append(self.rmp_sd_lower_line_item)
            self.rmp_sd_lower_line_item = None

        for item in items_to_remove:
            if item.scene() is not None: # Check if item is actually in the plot
                try:
                    self.plot_widget.removeItem(item)
                    # log.debug(f"Removed item: {type(item)}")
                except Exception as e:
                    log.warning(f"Could not remove item {item}: {e}")

    # --- ADDED: Helper to plot RMP/SD lines ---
    def _plot_rmp_visualization_lines(self):
        """Plots the RMP mean line and optionally SD lines based on _last_rmp_result."""
        log.debug("_plot_rmp_visualization_lines called.")

        # --- Start: Always clear previous lines first ---
        self._clear_rmp_visualization_lines()
        # --- End: Always clear previous lines first ---

        if not hasattr(self, '_last_rmp_result') or self._last_rmp_result is None:
            log.debug("  Skipping RMP line plotting: No last result.")
            return

        rmp_value = self._last_rmp_result.get('result_value')
        rmp_sd = self._last_rmp_result.get('result_sd')
        units = self._last_rmp_result.get('result_units', 'mV')

        if rmp_value is not None and np.isfinite(rmp_value):
            log.debug("Preparing to plot RMP visualization lines.")
            # Plot Mean RMP Line
            mean_pen = pg.mkPen('r', width=2)
            # Use InfLineLabel for hover effect
            mean_label_opts = {'position': 0.5, 'color': 'r', 'movable': False, 'anchor': (0.5, 1)} # Removed offset
            self.rmp_line_item = pg.InfiniteLine(
                pos=rmp_value, angle=0, pen=mean_pen, movable=False,
                label=f"RMP = {rmp_value:.2f} {units}", labelOpts=mean_label_opts
            )
            self.rmp_line_item.label.setPos(0, 5) # Offset label 5 pixels down
            self.plot_widget.addItem(self.rmp_line_item)
            log.debug(f"  Added RMP mean line at {rmp_value:.2f} {units}")

            # Plot SD Lines (if SD is valid)
            if rmp_sd is not None and np.isfinite(rmp_sd) and rmp_sd > 0:
                sd_pen = pg.mkPen('r', width=1, style=QtCore.Qt.PenStyle.DashLine)
                upper_sd_val = rmp_value + rmp_sd
                lower_sd_val = rmp_value - rmp_sd

                # Upper SD Line
                upper_label_opts = {'position': 0.8, 'color': 'k', 'movable': False, 'anchor': (0.5, 0)} # Removed offset
                self.rmp_sd_upper_line_item = pg.InfiniteLine(
                    pos=upper_sd_val, angle=0, pen=sd_pen, movable=False,
                    label=f"+SD = {upper_sd_val:.2f}", labelOpts=upper_label_opts
                )
                self.rmp_sd_upper_line_item.label.setPos(0, -5) # Offset label 5 pixels up
                self.plot_widget.addItem(self.rmp_sd_upper_line_item)
                log.debug(f"  Added RMP +SD line at {upper_sd_val:.2f}")

                # Lower SD Line
                lower_label_opts = {'position': 0.2, 'color': 'k', 'movable': False, 'anchor': (0.5, 1)} # Removed offset
                self.rmp_sd_lower_line_item = pg.InfiniteLine(
                    pos=lower_sd_val, angle=0, pen=sd_pen, movable=False,
                    label=f"-SD = {lower_sd_val:.2f}", labelOpts=lower_label_opts
                )
                self.rmp_sd_lower_line_item.label.setPos(0, 5) # Offset label 5 pixels down
                self.plot_widget.addItem(self.rmp_sd_lower_line_item)
                log.debug(f"  Added RMP -SD line at {lower_sd_val:.2f}")
            else:
                log.debug(f"  Skipping SD lines: SD is None, zero, or non-finite ({rmp_sd}).")
        else:
            log.debug(f"  Skipping RMP line plotting: RMP value is None or non-finite ({rmp_value}).")

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

        log.debug(f"RMP analysis mode changed to: {current_mode_text}. Interactive={is_interactive}, Auto={is_automatic}, Manual={is_manual}")

        # --- Trigger Analysis ---
        # MODIFIED: Trigger analysis immediately only if interactive, data loaded, AND NOT the initial call
        if is_interactive and self._current_plot_data and not initial_call:
            self._trigger_rmp_analysis()
        else:
            # In Auto/Manual, analysis waits for the Run button or specific input edits
            # Optionally clear results or set status message
            self.status_label.setText(f"Status: {current_mode_text} mode - Ready.")
            # Don't automatically clear the result/lines when switching to Auto/Manual
            # Keep the previous result visible until Run is clicked.
            if initial_call:
                log.debug("_on_mode_changed: Initial call from setup, skipping analysis trigger.")

    @QtCore.Slot()
    def _trigger_rmp_analysis_if_manual(self):
        """Slot specifically for manual time edit changes."""
        if self.mode_combobox and self.mode_combobox.currentText() == "Manual":
            log.debug("Manual time edit finished, triggering analysis.")
            self._trigger_rmp_analysis() # Trigger standard window-based analysis

    @QtCore.Slot()
    def _trigger_rmp_analysis_if_interactive(self):
        """Slot specifically for region changes."""
        if self.mode_combobox and self.mode_combobox.currentText() == "Interactive":
            log.debug("Interactive region change finished, triggering analysis.")
            self._trigger_rmp_analysis() # Trigger standard window-based analysis

    # --- ADDED: Slot for Run button (Auto/Manual modes) ---
    @QtCore.Slot()
    def _trigger_analysis_from_button(self):
        """Triggers the appropriate analysis when the Run button is clicked."""
        if not self.mode_combobox: return
        
        current_mode_text = self.mode_combobox.currentText()
        if current_mode_text == "Automatic":
            log.debug("Run button clicked in Automatic mode.")
            self._run_auto_rmp_analysis() # Run the specific auto-analysis method
        elif current_mode_text == "Manual":
            log.debug("Run button clicked in Manual mode.")
            self._trigger_rmp_analysis() # Run the standard window-based analysis
        else:
             log.warning(f"Run button clicked in unexpected mode: {current_mode_text}")
    # --- END ADDED ---

    def _trigger_rmp_analysis(self):
        """Central method to get parameters and run RMP calculation (Window-based: Interactive/Manual)."""
        # --- ADDED: Check for plot data FIRST --- 
        if not self._current_plot_data or \
           'time' not in self._current_plot_data or \
           'voltage' not in self._current_plot_data:
            log.warning("_trigger_rmp_analysis: Skipping - Plot data missing.")
            self.rmp_result_label.setText("RMP: No Data")
            self._last_rmp_result = None
            self._clear_rmp_visualization_lines()
            self._update_save_button_state()
            self.status_label.setText("Status: Error - No data plotted.")
            return
        # Retrieve data from stored dict
        time_vec = self._current_plot_data['time']
        voltage_vec = self._current_plot_data['voltage']
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
            log.debug(f"Running RMP (Window-based) in Interactive mode. Region: [{start_t:.4f}, {end_t:.4f}]")
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
                log.debug(f"Running RMP (Window-based) in Manual mode. Times: [{start_t:.4f}, {end_t:.4f}]")
            except ValueError as e:
                log.warning(f"Manual time validation failed: {e}")
                self.status_label.setText(f"Status: Invalid Time ({e})")
                if self.save_button: self.save_button.setEnabled(False)
                self._last_rmp_result = None # Ensure result is cleared on error
                self._clear_rmp_visualization_lines() # Clear lines on error
                return
        else:
            log.warning(f"_trigger_rmp_analysis called in unexpected mode: {current_mode_text}")
            return # Should only be called for Interactive or Manual via respective triggers
        # --- END NEW ---

        # --- Perform Calculation ---
        rmp_result = calculate_rmp(time_vec, voltage_vec, start_t, end_t)
        self._last_rmp_result = None # Clear previous result before storing new one

        # --- Store Result and Update UI ---
        if rmp_result is not None:
            rmp_value, rmp_sd = rmp_result
            units = "V" # Default
            chan_id = self.voltage_channel_combobox.currentData() # Use the correct combobox
            if self._selected_item_recording and chan_id:
                channel = self._selected_item_recording.channels.get(chan_id)
                if channel: units = channel.units or "V"

            self.rmp_result_label.setText(f"{rmp_value:.3f} {units} ± {rmp_sd:.3f} {units}") # Use correct label
            log.info(f"Calculated RMP (Window) = {rmp_value:.3f} {units} ± {rmp_sd:.3f} {units}")

            # --- Store result for saving ---
            self._last_rmp_result = {
                'result_value': rmp_value,
                'result_sd': rmp_sd,
                'result_units': units,
                # Use the actual mode text from the combobox
                'calculation_method': f'window_{current_mode_text.lower()}'
            }

            # --- REMOVED: Manual plot line handling and save button enable ---

        else: # Calculation failed
            self.rmp_result_label.setText("Calculation Error") # Use correct label
            log.warning("RMP (Window) calculation returned None.")
            # --- REMOVED: Manual save button disable and SD line removal ---

        # --- ADDED: Centralized UI Update --- 
        self._clear_rmp_visualization_lines()
        self._plot_rmp_visualization_lines() # Update plot lines based on _last_rmp_result
        self._update_save_button_state() # Update save button based on _last_rmp_result
        self.status_label.setText(f"Status: Calculation complete ({current_mode_text}).") # Update status
        # --- END ADDED ---

    # --- ADDED: Auto RMP Calculation Logic --- 
    @QtCore.Slot()
    def _run_auto_rmp_analysis(self):
        """Calculates RMP using a stable window identification method (replaces mean ± SD)."""
        if not self._current_plot_data:
            log.warning("Skipping Auto RMP analysis: No data plotted.")
            self.rmp_result_label.setText("N/A") # Use correct label
            self._last_rmp_result = None
            self._clear_rmp_visualization_lines()
            self._update_save_button_state()
            self.status_label.setText("Status: Auto - No data.")
            return

        voltage_vec = self._current_plot_data.get('voltage')
        time_vec = self._current_plot_data.get('time')
        if voltage_vec is None or len(voltage_vec) < 2 or time_vec is None or len(time_vec) < 2:
            log.warning("Skipping Auto RMP analysis: Voltage or time data is empty/missing or too short.")
            self.rmp_result_label.setText("N/A") # Use correct label
            self._last_rmp_result = None
            self._clear_rmp_visualization_lines()
            self._update_save_button_state()
            self.status_label.setText("Status: Auto - Data invalid.")
            return
            
        sd_threshold = self.auto_sd_threshold_spinbox.value() if self.auto_sd_threshold_spinbox else 0.5
        log.debug(f"Running Auto RMP Calculation (Stable Window Method, SD Threshold: {sd_threshold})")
        self.status_label.setText("Status: Auto - Running...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        self._last_rmp_result = None # Clear previous result
        calculation_succeeded = False

        # --- Visualization lines for auto method ---
        self._clear_auto_rmp_visualization_lines() # Clear any previous grey lines
        auto_sd_upper_line = None
        auto_sd_lower_line = None

        try:
            # --- Mode-based RMP Calculation ---
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
                 log.warning(f"Auto RMP failed: Found only {len(mode_indices)} points within the voltage band [{lower_bound:.2f}, {upper_bound:.2f}] mV around the mode. Not enough data.")
                 self.rmp_result_label.setText("Error: Insufficient data near mode")
                 calculation_succeeded = False
            else:
                log.debug(f"  Found {len(mode_indices)} points within the tolerance band.")
                # 5. Calculate Mean and SD of ORIGINAL voltage at these indices
                voltage_at_mode = voltage_vec[mode_indices]
                auto_rmp_mean = np.mean(voltage_at_mode)
                auto_rmp_sd = np.std(voltage_at_mode)

                # 6. Determine the time window for visualization (using min/max time of found indices)
                start_idx = mode_indices[0]
                end_idx = mode_indices[-1]
                start_time = time_vec[start_idx]
                end_time = time_vec[end_idx]
                log.debug(f"  Calculated RMP based on mode: Mean={auto_rmp_mean:.3f}, SD={auto_rmp_sd:.3f} mV")
                log.debug(f"  Corresponding time window (min/max index): [{start_time:.4f}s, {end_time:.4f}s]")

                # --- Visualization ---
                # Grey lines are optional for mode method, maybe remove? Let's keep for now.
                vis_pen = pg.mkPen(color=(128, 128, 128), style=QtCore.Qt.PenStyle.DashLine)
                auto_sd_upper_line = pg.InfiniteLine(pos=auto_rmp_mean + auto_rmp_sd, angle=0, pen=vis_pen)
                auto_sd_lower_line = pg.InfiniteLine(pos=auto_rmp_mean - auto_rmp_sd, angle=0, pen=vis_pen)
                self.plot_widget.addItem(auto_sd_upper_line)
                self.plot_widget.addItem(auto_sd_lower_line)
                
                # Highlight the region used for auto-calc
                if self.interactive_region:
                    # Adjust end time slightly if end_idx points to last element to avoid issues
                    safe_end_time = time_vec[min(end_idx, len(time_vec) - 1)]
                    self.interactive_region.setRegion([start_time, safe_end_time])
                    self.interactive_region.setBrush(QtGui.QBrush(QtGui.QColor(128, 128, 128, 50))) # Grey brush
                
                # --- Store Result ---
                units = "mV" # Assume mV for now, get from channel later if possible
                chan_id = self.voltage_channel_combobox.currentData()
                if self._selected_item_recording and chan_id:
                    channel = self._selected_item_recording.channels.get(chan_id)
                    # Attempt to get units, default to mV if not found or not voltage-like
                    if channel and hasattr(channel, 'units') and channel.units and 'V' in channel.units.upper():
                        # Convert mean/sd if units are V instead of mV? Assume input is mV for now.
                        units = channel.units 
                    else:
                         log.warning(f"Could not determine units for channel {chan_id}, assuming mV.")
                         units = "mV"

                self.rmp_result_label.setText(f"{auto_rmp_mean:.3f} {units} ± {auto_rmp_sd:.3f} {units}")
                log.info(f"Auto Calculated RMP (Mode Based) = {auto_rmp_mean:.3f} {units} ± {auto_rmp_sd:.3f} {units}")

                self._last_rmp_result = {
                    'result_value': auto_rmp_mean,
                    'result_sd': auto_rmp_sd,
                    'result_units': units,
                    'calculation_method': f'auto_mode_tolerance={tolerance_mv:.1f}mV'
                }
                calculation_succeeded = True

        except Exception as e:
            log.error(f"Error during auto RMP calculation (mode-based): {e}", exc_info=True)

        finally:
            # 1. Clear the main (red) RMP lines from any previous calculation
            self._clear_rmp_visualization_lines()
            
            # 2. Plot the final (red) lines ONLY if this auto-calculation succeeded
            if calculation_succeeded:
                log.debug("  Auto RMP succeeded. Plotting final (red) result lines.")
                self._plot_rmp_visualization_lines() # Plot based on _last_rmp_result
                self.status_label.setText("Status: Auto - Calculation complete.")
            else:
                log.debug("  Auto RMP failed. No final lines plotted.")
                self.status_label.setText("Status: Auto - Calculation failed.")
                # Reset region brush if it was changed
                if self.interactive_region:
                     self.interactive_region.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 0, 30))) # Reset to green

            # 3. Remove the temporary grey visualization lines *after* potential plotting of red lines
            #    Need to store references outside the try block if needed here.
            #    Let's modify _clear_auto_rmp_visualization_lines to handle this.
            self._clear_auto_rmp_visualization_lines() # Call the dedicated clearer

            # 4. Update save button state
            self._update_save_button_state()
            # 5. Restore cursor
            QtWidgets.QApplication.restoreOverrideCursor()
            # 6. Auto-range
            self.plot_widget.autoRange()
            log.debug("  Auto RMP final block finished.")

    def cleanup(self):
        # Clean up plot items if necessary
        if self.plot_widget:
            self._clear_rmp_visualization_lines() # Clear final RMP lines
            self._clear_auto_rmp_visualization_lines() # Clear auto-calc temp lines
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
        self.voltage_channel_combobox.setEnabled(has_valid_selection) # Use correct combobox
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
        # Override if RMP requires specific conditions
        # Enable save button only if a valid RMP result is stored.
        can_save = hasattr(self, '_last_rmp_result') and self._last_rmp_result is not None
        # Directly enable/disable the save button
        if self.save_button:
            self.save_button.setEnabled(can_save)

    # --- Implementation of BaseAnalysisTab method --- 
    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Gathers the specific RMP result details for saving."""
        # UPDATED: Use stored result instead of parsing label
        if not hasattr(self, '_last_rmp_result') or self._last_rmp_result is None:
             log.debug("_get_specific_result_data: No calculated RMP result stored.")
             return None

        value = self._last_rmp_result.get('result_value')
        sd = self._last_rmp_result.get('result_sd')
        units = self._last_rmp_result.get('result_units', 'V') # Default units
        method = self._last_rmp_result.get('calculation_method')

        if value is None or sd is None or method is None:
             log.error(f"_get_specific_result_data: Stored RMP result is incomplete: {self._last_rmp_result}")
             return None

        # Get source info
        channel_id = self.voltage_channel_combobox.currentData() # Use correct combobox
        channel_name = self.voltage_channel_combobox.currentText().split(' (')[0] # Extract name before ID
        data_source = self.data_source_combobox.currentData() # "average" or trial index (int)
        data_source_text = self.data_source_combobox.currentText()

        if channel_id is None or data_source is None:
            log.warning("Cannot get specific RMP data: Missing channel or data source selection.")
            return None

        specific_data = {
            'result_value': value,
            'result_sd': sd,
            'result_units': units,
            'channel_id': channel_id,
            'channel_name': channel_name,
            'data_source': data_source,
            'data_source_label': data_source_text, # Add readable label
            # Add analysis-specific parameters used
            'calculation_method': method # Store 'auto_...' or 'window_...'
        }

        # Add window parameters only if a window method was used
        if 'window' in method:
             current_mode_text = self.mode_combobox.currentText() # Get mode from combobox
             # Get window from the region item (updated by both modes)
             if self.interactive_region:
                 start_s, end_s = self.interactive_region.getRegion()
                 specific_data['baseline_start_s'] = start_s
                 specific_data['baseline_end_s'] = end_s
             specific_data['analysis_mode'] = current_mode_text # Save the mode text
        
        # Add threshold parameter only if auto method was used
        if 'auto_stable_window' in method:
            threshold_val = self.auto_sd_threshold_spinbox.value() if self.auto_sd_threshold_spinbox else None
            specific_data['auto_sd_threshold'] = threshold_val
            specific_data['analysis_mode'] = "Automatic" # Explicitly set mode

        log.debug(f"_get_specific_result_data returning: {specific_data}")
        return specific_data
    # --- END Implementation ---


# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = RmpAnalysisTab