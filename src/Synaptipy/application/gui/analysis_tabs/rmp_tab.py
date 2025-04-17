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
        self.analysis_mode_group: Optional[QtWidgets.QGroupBox] = None
        self.mode_button_group: Optional[QtWidgets.QButtonGroup] = None
        self.interactive_radio: Optional[QtWidgets.QRadioButton] = None
        self.manual_radio: Optional[QtWidgets.QRadioButton] = None
        # Manual Inputs
        self.manual_time_group: Optional[QtWidgets.QGroupBox] = None
        self.start_time_edit: Optional[QtWidgets.QLineEdit] = None
        self.end_time_edit: Optional[QtWidgets.QLineEdit] = None
        # Results Display
        self.results_label: Optional[QtWidgets.QLabel] = None # To display the calculated RMP
        # Plotting Interaction
        self.baseline_region_item: Optional[pg.LinearRegionItem] = None
        # ADDED: Calculate Button
        self.calculate_button: Optional[QtWidgets.QPushButton] = None
        # Store currently plotted data for analysis
        self._current_plot_data: Optional[Dict[str, np.ndarray]] = None # {'time':..., 'voltage':...}


        self._setup_ui()
        self._connect_signals()
        self._on_mode_changed() # Set initial UI state based on default mode

    def get_display_name(self) -> str:
        # Returns the name for the sub-tab.
        return "Resting Potential (RMP)"

    def _setup_ui(self):
        # Create UI elements for the RMP analysis tab.
        main_layout = QtWidgets.QVBoxLayout(self) # Use Vertical layout

        # --- Top Controls Area ---
        controls_group = QtWidgets.QGroupBox("Configuration")
        controls_layout = QtWidgets.QVBoxLayout(controls_group)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # 1. Analysis Item Selector (Inherited)
        item_selector_layout = QtWidgets.QFormLayout() # Use Form layout for this part
        self._setup_analysis_item_selector(item_selector_layout) # Add combo box
        controls_layout.addLayout(item_selector_layout)

        # 2. Channel Selector (Single Channel for Plotting)
        channel_select_layout = QtWidgets.QHBoxLayout()
        channel_select_layout.addWidget(QtWidgets.QLabel("Plot Channel:"))
        self.channel_combobox = QtWidgets.QComboBox()
        self.channel_combobox.setToolTip("Select the channel to plot and interact with.")
        self.channel_combobox.setEnabled(False)
        channel_select_layout.addWidget(self.channel_combobox, stretch=1)
        controls_layout.addLayout(channel_select_layout)

        # --- ADDED: Data Source Selector ---
        data_source_layout = QtWidgets.QHBoxLayout()
        data_source_layout.addWidget(QtWidgets.QLabel("Data Source:"))
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace to analyze.")
        self.data_source_combobox.setEnabled(False)
        data_source_layout.addWidget(self.data_source_combobox, stretch=1)
        controls_layout.addLayout(data_source_layout)
        # --- END ADDED ---

        # 3. Analysis Mode Selection
        self.analysis_mode_group = QtWidgets.QGroupBox("Analysis Mode")
        mode_layout = QtWidgets.QHBoxLayout(self.analysis_mode_group)
        self.interactive_radio = QtWidgets.QRadioButton("Interactive Baseline")
        self.manual_radio = QtWidgets.QRadioButton("Manual Time Entry")
        self.mode_button_group = QtWidgets.QButtonGroup(self)
        self.mode_button_group.addButton(self.interactive_radio, self.MODE_INTERACTIVE)
        self.mode_button_group.addButton(self.manual_radio, self.MODE_MANUAL)
        mode_layout.addWidget(self.interactive_radio)
        mode_layout.addWidget(self.manual_radio)
        self.interactive_radio.setChecked(True) # Default to interactive
        self.analysis_mode_group.setEnabled(False)
        controls_layout.addWidget(self.analysis_mode_group)

        # 4. Manual Time Inputs (Initially grouped and potentially disabled)
        self.manual_time_group = QtWidgets.QGroupBox("Manual Time Window")
        manual_layout = QtWidgets.QFormLayout(self.manual_time_group)
        self.start_time_edit = QtWidgets.QLineEdit("0.0")
        self.start_time_edit.setValidator(QtGui.QDoubleValidator(0, 1e6, 4, self)) # Min 0, high max, 4 decimals
        self.start_time_edit.setToolTip("Start time (s) for baseline calculation.")
        manual_layout.addRow("Start Time (s):", self.start_time_edit)
        self.end_time_edit = QtWidgets.QLineEdit("0.1")
        self.end_time_edit.setValidator(QtGui.QDoubleValidator(0, 1e6, 4, self))
        self.end_time_edit.setToolTip("End time (s) for baseline calculation.")
        manual_layout.addRow("End Time (s):", self.end_time_edit)
        self.manual_time_group.setEnabled(False) # Disabled initially
        controls_layout.addWidget(self.manual_time_group)

        # 5. Results Display
        results_layout = QtWidgets.QHBoxLayout()
        results_layout.addWidget(QtWidgets.QLabel("Calculated RMP:"))
        self.results_label = QtWidgets.QLabel("N/A")
        font = self.results_label.font(); font.setBold(True); self.results_label.setFont(font)
        results_layout.addWidget(self.results_label, stretch=1)
        controls_layout.addLayout(results_layout)

        # --- ADDED: Calculate Button --- 
        self.calculate_button = QtWidgets.QPushButton("Calculate RMP")
        self.calculate_button.setEnabled(False) # Initially disabled
        self.calculate_button.setToolTip("Click to calculate RMP using the current settings and plot.")
        # Add button centered below results
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.calculate_button)
        button_layout.addStretch()
        controls_layout.addLayout(button_layout)
        # --- END ADDED ---

        # --- UPDATED: Use base class method for Save Button --- 
        # self.save_button = QtWidgets.QPushButton("Save RMP Result")
        # ... (manual button creation removed) ...
        # controls_layout.addWidget(self.save_button, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        self._setup_save_button(controls_layout) # Call base class helper
        # --- END UPDATE ---

        controls_layout.addStretch()
        main_layout.addWidget(controls_group)

        # --- Bottom Plot Area (Inherited) ---
        # Use stretch factor > 0 to allow plot to expand vertically
        self._setup_plot_area(main_layout, stretch_factor=1)

        # Add the interactive region item (initially hidden/disabled)
        self.baseline_region_item = pg.LinearRegionItem(values=[0.0, 0.1], orientation='vertical', brush=(0, 255, 0, 50), movable=True, bounds=None)
        self.baseline_region_item.setZValue(-10) # Ensure it's behind plot lines
        self.plot_widget.addItem(self.baseline_region_item)
        self.baseline_region_item.setVisible(True) # Visible but might be disabled by mode

        self.setLayout(main_layout)
        log.debug("RMP Analysis Tab UI setup complete.")

    def _connect_signals(self):
        # Connect signals specific to RMP tab widgets.
        # Inherited combo box signal handled by BaseAnalysisTab (_on_analysis_item_selected)

        # Connect channel selector
        self.channel_combobox.currentIndexChanged.connect(self._plot_selected_channel_trace)

        # --- ADDED: Connect Data Source Selector ---
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_channel_trace)
        # --- END ADDED ---

        # Connect analysis mode change
        self.mode_button_group.buttonClicked.connect(self._on_mode_changed)

        # Connect manual time edits
        # REMOVED: self.start_time_edit.editingFinished.connect(self._trigger_rmp_analysis_from_manual)
        # REMOVED: self.end_time_edit.editingFinished.connect(self._trigger_rmp_analysis_from_manual)

        # Connect interactive region change
        # REMOVED: self.baseline_region_item.sigRegionChangeFinished.connect(self._trigger_rmp_analysis_from_region)

        # ADDED: Connect Calculate Button
        self.calculate_button.clicked.connect(self._trigger_rmp_analysis)

        # --- REMOVED: Save button connection (handled by base) ---
        # self.save_button.clicked.connect(self._on_save_result_clicked)
        # --- END REMOVED ---

    # --- Overridden Methods from Base ---
    def _update_ui_for_selected_item(self):
        # Update the RMP tab UI when a new analysis item is selected.
        # Populates channel list, plots data, and enables/disables controls.
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None # Clear previous plot data
        self.results_label.setText("N/A") # Clear previous results
        if self.save_button: self.save_button.setEnabled(False) # Disable save on selection change

        # --- Populate Channel ComboBox ---
        self.channel_combobox.blockSignals(True)
        self.channel_combobox.clear()
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
                    self.channel_combobox.addItem(display_name, userData=chan_id)
                    valid_channels.append(chan_id)

            if valid_channels:
                self.channel_combobox.setCurrentIndex(0) # Select first valid channel
                voltage_channels_found = True # Mark that we found channels
                # can_enable_ui = True # Enable UI is determined later
            else:
                self.channel_combobox.addItem("No Voltage Channels Found")
        else:
            self.channel_combobox.addItem("Load Data Item...")

        self.channel_combobox.setEnabled(voltage_channels_found) # Enable only if voltage channels exist
        self.channel_combobox.blockSignals(False)

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
        self.analysis_mode_group.setEnabled(can_analyze)
        self._on_mode_changed() # Update manual/interactive state based on loaded data availability

        # --- Plot Initial Trace --- 
        if can_analyze:
            self._plot_selected_channel_trace() # Plot the trace for the initially selected channel
        else:
            self.plot_widget.clear() # Ensure plot is clear if no data/channels

    # --- Plotting and Interaction ---
    def _plot_selected_channel_trace(self):
        """Plots the voltage trace for the currently selected channel and data source.""" # Updated docstring
        if not self.plot_widget or not self.channel_combobox or not self.data_source_combobox or not self._selected_item_recording:
            self._current_plot_data = None
            if self.plot_widget:
                self.plot_widget.clear()
                # Re-add region if cleared
                if self.baseline_region_item not in self.plot_widget.items:
                    self.plot_widget.addItem(self.baseline_region_item)
            return

        chan_id = self.channel_combobox.currentData()
        source_data = self.data_source_combobox.currentData() # Trial index (int) or "average" (str)

        if not chan_id or source_data is None:
            self._current_plot_data = None
            self.plot_widget.clear()
            if self.baseline_region_item not in self.plot_widget.items:
                 self.plot_widget.addItem(self.baseline_region_item)
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
                self.plot_widget.plot(time_vec, voltage_vec, pen='k', name=data_label)
                self.plot_widget.setLabel('left', 'Voltage', units=channel.units or 'V')
                self.plot_widget.setLabel('bottom', 'Time', units='s')
                self._current_plot_data = {'time': time_vec, 'voltage': voltage_vec}
                # Set initial region/bounds based on plotted data
                min_t, max_t = time_vec[0], time_vec[-1]
                self.baseline_region_item.setBounds([min_t, max_t])
                # Keep current region if valid, otherwise reset
                rgn_start, rgn_end = self.baseline_region_item.getRegion()
                if rgn_start < min_t or rgn_end > max_t or rgn_start >= rgn_end:
                     # Set default region (e.g., first 100ms or 10% of trace)
                     default_end = min(min_t + 0.1, min_t + (max_t - min_t) * 0.1, max_t)
                     self.baseline_region_item.setRegion([min_t, default_end])
                     log.debug(f"Resetting region to default: [{min_t}, {default_end}]")
                # This else corresponds to the region check
                else:
                    log.debug("Region is within bounds and valid.")
            # This else corresponds to `if time_vec is not None and voltage_vec is not None:`
            else: 
                self._current_plot_data = None
                log.warning(f"No valid data found to plot for channel {chan_id}")

            # Always re-add region item as clear() removes it
            self.plot_widget.addItem(self.baseline_region_item)
            self.plot_widget.setTitle(data_label) # Set title for clarity

        except Exception as e:
            log.error(f"Error plotting trace for channel {chan_id}: {e}", exc_info=True)
            self.plot_widget.clear()
            self.plot_widget.addItem(self.baseline_region_item) # Re-add region on error
            self._current_plot_data = None

        # Trigger analysis after plotting new trace
        # REMOVED: self._trigger_rmp_analysis() 
        # INSTEAD: Enable calculate button if plot succeeded
        if self._current_plot_data:
             self.calculate_button.setEnabled(True)
        else:
             self.calculate_button.setEnabled(False)
             # Ensure result is cleared if plot failed
             self.results_label.setText("N/A")
             if self.save_button: self.save_button.setEnabled(False)

    # --- Analysis Logic ---
    @QtCore.Slot()
    def _on_mode_changed(self):
        """Handles switching between interactive and manual modes."""
        is_manual = self.mode_button_group.checkedId() == self.MODE_MANUAL
        self.manual_time_group.setEnabled(is_manual)
        self.baseline_region_item.setVisible(not is_manual)
        self.baseline_region_item.setMovable(not is_manual)

        log.debug(f"Analysis mode changed. Manual Mode: {is_manual}")
        # Trigger analysis immediately when mode changes
        self._trigger_rmp_analysis()


    @QtCore.Slot()
    def _trigger_rmp_analysis_from_manual(self):
        """Slot specifically for manual time edit changes."""
        if self.mode_button_group.checkedId() == self.MODE_MANUAL:
            log.debug("Manual time edit finished, triggering analysis.")
            self._trigger_rmp_analysis()

    @QtCore.Slot()
    def _trigger_rmp_analysis_from_region(self):
        """Slot specifically for region changes."""
        if self.mode_button_group.checkedId() == self.MODE_INTERACTIVE:
            log.debug("Interactive region change finished, triggering analysis.")
            self._trigger_rmp_analysis()

    def _trigger_rmp_analysis(self):
        """Central method to get parameters and run RMP calculation."""
        if not self._current_plot_data:
             log.debug("Skipping RMP analysis: No data plotted.")
             self.results_label.setText("N/A")
             if self.save_button: self.save_button.setEnabled(False)
             return

        time_vec = self._current_plot_data['time']
        voltage_vec = self._current_plot_data['voltage']
        start_t, end_t = None, None

        if self.mode_button_group.checkedId() == self.MODE_INTERACTIVE:
            start_t, end_t = self.baseline_region_item.getRegion()
            # Update manual fields to reflect region (optional, for user feedback)
            self.start_time_edit.setText(f"{start_t:.4f}")
            self.end_time_edit.setText(f"{end_t:.4f}")
            log.debug(f"Running RMP in Interactive mode. Region: [{start_t:.4f}, {end_t:.4f}]")
        else: # Manual mode
            try:
                start_t = float(self.start_time_edit.text())
                end_t = float(self.end_time_edit.text())
                if start_t >= end_t:
                    log.warning("Manual time validation failed: Start >= End")
                    self.results_label.setText("Invalid Time")
                    if self.save_button: self.save_button.setEnabled(False)
                    return
                # Optionally update region to match manual input
                self.baseline_region_item.setRegion([start_t, end_t])
                log.debug(f"Running RMP in Manual mode. Times: [{start_t:.4f}, {end_t:.4f}]")
            except (ValueError, TypeError):
                log.warning("Manual time validation failed: Invalid number")
                self.results_label.setText("Invalid Time")
                if self.save_button: self.save_button.setEnabled(False)
                return

        # --- Perform Calculation ---
        rmp_value, rmp_sd = calculate_rmp(time_vec, voltage_vec, start_t, end_t)

        # --- Display Result ---
        if rmp_value is not None:
            units = self._selected_item_recording.channels.get(self.channel_combobox.currentData()).units or "V"
            self.results_label.setText(f"{rmp_value:.3f} {units} ± {rmp_sd:.3f} {units}")
            log.info(f"Calculated RMP = {rmp_value:.3f} {units} ± {rmp_sd:.3f} {units}")
            if self.save_button: self.save_button.setEnabled(True) # Enable save button
        else:
            self.results_label.setText("Error")
            log.warning("RMP calculation returned None.")
            if self.save_button: self.save_button.setEnabled(False) # Disable save button

    # --- Implementation of BaseAnalysisTab method --- 
    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Gathers the specific RMP result details for saving."""
        if not self.results_label or self.results_label.text() in ["N/A", "Error", "Invalid Time"]:
            log.debug("_get_specific_result_data: No valid RMP result available.")
            return None

        value, sd, units = None, None, None # Initialize
        # Parse result from label
        result_text = self.results_label.text()
        try:
            parts = result_text.split() # e.g., "-65.123 V ± 0.567 V"
            if len(parts) < 4 or parts[2] != '±': # Basic check for expected format
                 raise ValueError("Result string format unexpected.")
            value = float(parts[0])
            sd = float(parts[3]) # SD is at index 3
            units = parts[1]     # Units are at index 1 (or 4)
        except (ValueError, IndexError) as e:
            log.error(f"Could not parse result from label '{result_text}' for saving: {e}")
            return None # Cannot save if result can't be parsed
        
        # If parsing succeeded, proceed to get other details
        channel_id = self.channel_combobox.currentData()
        channel_name = self.channel_combobox.currentText().split(' (')[0] # Extract name before ID
        data_source = self.data_source_combobox.currentData() # "average" or trial index (int)

        if channel_id is None or data_source is None:
            log.warning("Cannot get specific RMP data: Missing channel or data source selection.")
            return None

        specific_data = {
            'result_value': value,
            'result_sd': sd,
            'result_units': units,
            'channel_id': channel_id,
            'channel_name': channel_name,
            'data_source': data_source, # Crucial for base class to interpret
            # Add analysis-specific parameters used
            'baseline_start_s': self.baseline_region_item.getRegion()[0],
            'baseline_end_s': self.baseline_region_item.getRegion()[1],
            'analysis_mode': "Interactive" if self.mode_button_group.checkedId() == self.MODE_INTERACTIVE else "Manual"
        }
        log.debug(f"_get_specific_result_data returning: {specific_data}")
        return specific_data
    # --- END Implementation ---

    def cleanup(self):
        # Clean up plot items if necessary
        if self.plot_widget:
             self.plot_widget.clear() # Ensure plot is cleared
        # Call superclass cleanup if it does anything useful
        super().cleanup()

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = RmpAnalysisTab