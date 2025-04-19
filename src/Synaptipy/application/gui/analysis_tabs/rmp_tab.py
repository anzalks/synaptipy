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

        # --- Calculate and Auto Calculate Buttons Side-by-Side ---
        self.calculate_button = QtWidgets.QPushButton("Calculate RMP (Window)") # Clarify name
        self.calculate_button.setEnabled(False)
        self.calculate_button.setToolTip("Calculate RMP using the interactive region or manual time window.")
        
        # Update text and tooltip for 0.5 SD
        self.auto_calculate_button = QtWidgets.QPushButton("Auto Calculate RMP (±0.5SD)")
        self.auto_calculate_button.setEnabled(False)
        self.auto_calculate_button.setToolTip("Calculate RMP using mean ± 0.5SD of the entire trace.")
        
        # Add both buttons to the same horizontal layout
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.calculate_button)
        buttons_layout.addWidget(self.auto_calculate_button)
        buttons_layout.addStretch()
        controls_layout.addLayout(buttons_layout)
        # --- END MODIFIED ---

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

        # ADDED: Connect Auto Calculate Button
        self.auto_calculate_button.clicked.connect(self._run_auto_rmp_analysis)

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
        
        # Move this call AFTER plotting to ensure _current_plot_data is set
        self._on_mode_changed() # Update manual/interactive state

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

        # Clear previous data
        self.plot_widget.clear()
        self._current_plot_data = None
        self._clear_rmp_visualization_lines() # <<< ADDED: Clear RMP/SD lines

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
            self.plot_widget.addItem(self.baseline_region_item) # Re-add region on error
            self._current_plot_data = None

        # Trigger analysis after plotting new trace
        # REMOVED: self._trigger_rmp_analysis() 
        # INSTEAD: Enable calculate button if plot succeeded
        if self._current_plot_data:
             self.calculate_button.setEnabled(True)
             self.auto_calculate_button.setEnabled(True) # Also enable auto button
        else:
             self.calculate_button.setEnabled(False)
             self.auto_calculate_button.setEnabled(False) # Also disable auto button
             # Ensure result is cleared if plot failed
             self.results_label.setText("N/A")
             if self.save_button: self.save_button.setEnabled(False)

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
        self._last_rmp_result = None # Clear previous result before storing new one

        # --- Store Result and Update UI ---
        if rmp_value is not None:
            units = "V" # Default
            chan_id = self.channel_combobox.currentData()
            if self._selected_item_recording and chan_id:
                channel = self._selected_item_recording.channels.get(chan_id)
                if channel: units = channel.units or "V"

            self.results_label.setText(f"{rmp_value:.3f} {units} ± {rmp_sd:.3f} {units}")
            log.info(f"Calculated RMP = {rmp_value:.3f} {units} ± {rmp_sd:.3f} {units}")

            # --- Store result for saving ---
            self._last_rmp_result = {
                'result_value': rmp_value,
                'result_sd': rmp_sd,
                'result_units': units,
                'calculation_method': 'window' # Indicate the method used
            }

            # --- REMOVED: Manual plot line handling and save button enable ---
            # (Code related to manually adding/removing items and setting button state removed)

        else: # Calculation failed
            self.results_label.setText("Error")
            log.warning("RMP calculation returned None.")
            # --- REMOVED: Manual save button disable and SD line removal ---
            # (Code related to manually disabling button and removing items removed)

        # --- ADDED: Centralized UI Update --- 
        self._clear_rmp_visualization_lines()
        self._plot_rmp_visualization_lines() # Update plot lines based on _last_rmp_result
        self._update_save_button_state() # Update save button based on _last_rmp_result
        # --- END ADDED ---

    # --- ADDED: Auto RMP Calculation Logic --- 
    @QtCore.Slot()
    def _run_auto_rmp_analysis(self):
        """Calculates RMP using mean ± 0.5SD of the entire trace."""
        if not self._current_plot_data:
            log.warning("Skipping Auto RMP analysis: No data plotted.")
            self.results_label.setText("N/A")
            self._last_rmp_result = None # Ensure result is cleared
            self._clear_rmp_visualization_lines() # Clear any lines
            self._update_save_button_state() # Update button state
            return

        voltage_vec = self._current_plot_data.get('voltage')
        time_vec = self._current_plot_data.get('time')
        if voltage_vec is None or len(voltage_vec) == 0 or time_vec is None or len(time_vec) == 0:
            log.warning("Skipping Auto RMP analysis: Voltage or time data is empty/missing.")
            self.results_label.setText("N/A")
            self._last_rmp_result = None
            self._clear_rmp_visualization_lines()
            self._update_save_button_state()
            return

        log.debug("Running Auto RMP Calculation (Mean ± 0.5SD method)")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        self._last_rmp_result = None # Clear previous result
        calculation_succeeded = False # Flag to track success
        # --- REMOVED: Variables for temporary visualization lines ---
        # temp_sd_upper_line = None
        # temp_sd_lower_line = None
        # --- END REMOVED ---

        try:
            full_mean = np.mean(voltage_vec)
            full_sd = np.std(voltage_vec)
            threshold_sd = 0.5 # Use 0.5 SD
            upper_bound = full_mean + threshold_sd * full_sd
            lower_bound = full_mean - threshold_sd * full_sd

            # Find indices within ±0.5 SD
            indices = np.where((voltage_vec >= lower_bound) & (voltage_vec <= upper_bound))[0]
            num_indices = len(indices)
            # --- REMOVED: Percentage calculation and related logging ---
            # percentage_in_range = (num_indices / len(voltage_vec)) * 100
            # log.debug(f"Auto RMP: {percentage_in_range:.1f}% of data points are within {threshold_sd} SD.")

            # --- REMOVED: Plotting of temporary ±0.5 SD lines ---
            # sd_pen = pg.mkPen(color=(100, 100, 100), style=QtCore.Qt.PenStyle.DashLine)
            # temp_sd_upper_line = pg.InfiniteLine(pos=upper_bound, angle=0, pen=sd_pen, movable=False)
            # self.plot_widget.addItem(temp_sd_upper_line)
            # log.debug(f"  Added temporary upper SD line at {upper_bound:.3f}")
            # temp_sd_lower_line = pg.InfiniteLine(pos=lower_bound, angle=0, pen=sd_pen, movable=False)
            # self.plot_widget.addItem(temp_sd_lower_line)
            # log.debug(f"  Added temporary lower SD line at {lower_bound:.3f}")

            # --- REVISED: Condition is now simply num_indices > 0 ---
            # is_close_or_greater = np.isclose(percentage_in_range, 80.0, atol=0.02) or percentage_in_range > 80.0
            log.debug(f"Condition Check: num_indices={num_indices}")

            if num_indices > 0:
                log.debug("  Proceeding with calculation (num_indices > 0).")
                # Proceed with calculation
                selected_voltage = voltage_vec[indices]
                auto_rmp_mean = np.mean(selected_voltage)
                auto_rmp_sd = np.std(selected_voltage)

                # Get units
                units = "V"
                chan_id = self.channel_combobox.currentData()
                if self._selected_item_recording and chan_id:
                    channel = self._selected_item_recording.channels.get(chan_id)
                    if channel: units = channel.units or "V"

                self.results_label.setText(f"{auto_rmp_mean:.3f} {units} ± {auto_rmp_sd:.3f} {units}")
                log.info(f"Auto Calculated RMP = {auto_rmp_mean:.3f} {units} ± {auto_rmp_sd:.3f} {units}")

                # --- Store result for saving ---
                self._last_rmp_result = {
                    'result_value': auto_rmp_mean,
                    'result_sd': auto_rmp_sd,
                    'result_units': units,
                    'calculation_method': f'auto_{threshold_sd}sd' # Indicate method used
                }
                calculation_succeeded = True # Mark calculation as successful

            else: # num_indices == 0
                 # --- UPDATED: Log/UI message for num_indices == 0 --- 
                 log.warning(f"Auto RMP failed: No data points found within ±{threshold_sd} SD range.")
                 self.results_label.setText(f"Error: No data in ±{threshold_sd}SD")
                 # --- END UPDATED --- 
                 # calculation_succeeded remains False
                 # _last_rmp_result remains None
            # --- END REVISED ---

        except Exception as e:
            log.error(f"Error during auto RMP calculation: {e}", exc_info=True)
            self.results_label.setText("Error")
            calculation_succeeded = False # Ensure failure on exception
            self._last_rmp_result = None

        finally:
            # --- MODIFIED: Simplified final block --- 
            # 1. Always clear persistent lines from previous calculations
            self._clear_rmp_visualization_lines()

            # 2. Plot final result ONLY if calculation succeeded (num_indices > 0)
            if calculation_succeeded:
                log.debug("  Auto RMP succeeded (num_indices > 0). Plotting final results.")
                # Plot the final, persistent result lines (red)
                self._plot_rmp_visualization_lines()
            # else: # Calculation failed (num_indices == 0 or exception)
            #     log.debug("  Auto RMP failed (num_indices == 0 or exception). No final lines plotted.")
            #     # No lines to leave visible, as temporary lines were removed

            # 3. Update save button state based on whether _last_rmp_result was set
            self._update_save_button_state()
            # 4. Restore cursor
            QtWidgets.QApplication.restoreOverrideCursor()
            # 5. Explicitly update plot range
            self.plot_widget.autoRange()
            log.debug("  Called plot_widget.autoRange()")
            # --- END MODIFIED ---

    def cleanup(self):
        # Clean up plot items if necessary
        if self.plot_widget:
             # Remove RMP line if it exists
             if self.rmp_line_item is not None and self.rmp_line_item.scene():
                 self.plot_widget.removeItem(self.rmp_line_item)
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
        self.channel_combobox.setEnabled(has_valid_selection)
        self.data_source_combobox.setEnabled(has_valid_selection and self.data_source_combobox.count() > 0 and self.data_source_combobox.currentData() is not None)

        # Enable the rest only if data is actually plotted (implies valid selection AND successful plot)
        self.analysis_mode_group.setEnabled(has_data)
        
        current_mode = self.mode_button_group.checkedId()
        is_interactive = (current_mode == self.MODE_INTERACTIVE)
        self.manual_time_group.setEnabled(has_data and not is_interactive)
        self.baseline_region_item.setVisible(has_data and is_interactive)
        self.baseline_region_item.setMovable(has_data and is_interactive)

        # Enable Calculate buttons only if data is present
        self.calculate_button.setEnabled(has_data)
        self.auto_calculate_button.setEnabled(has_data)

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
        channel_id = self.channel_combobox.currentData()
        channel_name = self.channel_combobox.currentText().split(' (')[0] # Extract name before ID
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
            'calculation_method': method # Store 'auto_Xsd' or 'window'
        }

        # Add window parameters only if window method was used
        if method == 'window':
            start_s, end_s = self.baseline_region_item.getRegion()
            specific_data['baseline_start_s'] = start_s
            specific_data['baseline_end_s'] = end_s
            # Determine if mode was Interactive or Manual when window was used
            mode_id = self.mode_button_group.checkedId()
            if mode_id == self.MODE_INTERACTIVE:
                specific_data['analysis_mode'] = "Interactive"
            elif mode_id == self.MODE_MANUAL:
                specific_data['analysis_mode'] = "Manual"
            else:
                specific_data['analysis_mode'] = "Unknown" # Should not happen

        log.debug(f"_get_specific_result_data returning: {specific_data}")
        return specific_data
    # --- END Implementation ---


# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = RmpAnalysisTab