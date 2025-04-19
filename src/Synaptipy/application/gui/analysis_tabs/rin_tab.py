# src/Synaptipy/application/gui/analysis_tabs/rin_tab.py
# -*- coding: utf-8 -*-
"""
Analysis tab for calculating Input Resistance (Rin) with interactive selection.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# Use relative imports within the same package
from .base import BaseAnalysisTab
# Use absolute paths for core components
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.infrastructure.file_readers import NeoAdapter
# from Synaptipy.core.analysis.intrinsic_properties import calculate_rin # Or define below

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rin_tab')

# --- Rin Calculation Function (REVERTED to use manual delta_i) ---
def calculate_rin(
    time_v: np.ndarray, voltage: np.ndarray,
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float],
    delta_i_pa: float # RE-ADDED manual delta I
) -> Optional[Tuple[float, float]]: # Return Rin, dV (dI is now input)
    """
    Calculates Input Resistance (Rin) based on voltage trace within defined windows
    and a provided current step amplitude (delta_i).

    Args:
        time_v: 1D numpy array of time values for voltage trace.
        voltage: 1D numpy array of voltage values.
        baseline_window: Tuple (start_time, end_time) for baseline measurement.
        response_window: Tuple (start_time, end_time) for response measurement.
        delta_i_pa: The change in current amplitude (I_response - I_baseline) in picoamps (pA).

    Returns:
        A tuple containing (rin_megaohms, delta_v_millivolts) 
        or None if calculation fails (e.g., invalid windows, no data, zero delta_i).
    """
    # Basic validations
    if time_v is None or voltage is None or \
       baseline_window is None or response_window is None or \
       baseline_window[0] >= baseline_window[1] or response_window[0] >= response_window[1]:
        log.error("Calculate Rin: Invalid input arrays or window times.")
        return None
    
    # Validate delta_i
    if np.isclose(delta_i_pa, 0.0):
        log.warning(f"Provided Delta I is zero or close to zero ({delta_i_pa:.4f} pA). Cannot calculate Rin.")
        return None

    try:
        # --- Calculate Mean Baseline Voltage ---
        bl_indices_v = np.where((time_v >= baseline_window[0]) & (time_v <= baseline_window[1]))[0]
        if len(bl_indices_v) == 0:
            log.warning(f"No voltage data points found in baseline window: {baseline_window}")
            return None
        mean_baseline_v = np.mean(voltage[bl_indices_v])

        # --- Calculate Mean Response Voltage ---
        resp_indices_v = np.where((time_v >= response_window[0]) & (time_v <= response_window[1]))[0]
        if len(resp_indices_v) == 0:
            log.warning(f"No voltage data points found in response window: {response_window}")
            return None
        mean_response_v = np.mean(voltage[resp_indices_v])

        # --- Calculate Delta V ---
        delta_v = mean_response_v - mean_baseline_v # mV (assuming input V is mV)

        log.debug(f"Rin Calc: Mean Baseline V={mean_baseline_v:.3f} mV, Mean Response V={mean_response_v:.3f} mV => dV={delta_v:.3f} mV")
        log.debug(f"Rin Calc: Using provided dI = {delta_i_pa:.3f} pA")

        # --- Calculate Rin using provided delta_i --- 
        # Rin (MΩ) = Delta V (mV) / Delta I (nA)
        # Convert delta_i from pA to nA by dividing by 1000
        rin_megaohms = delta_v / (delta_i_pa / 1000.0)

        log.info(f"Calculated Rin = {rin_megaohms:.2f} MΩ (dV={delta_v:.3f}mV, using provided dI={delta_i_pa:.3f}pA)")
        return rin_megaohms, delta_v # Return Rin and the calculated dV

    except Exception as e:
        log.error(f"Error calculating Rin: {e}", exc_info=True)
        return None

# --- Rin Analysis Tab Class ---
class RinAnalysisTab(BaseAnalysisTab):
    """Widget for Input Resistance calculation with interactive plotting."""

    MODE_INTERACTIVE = 0
    MODE_MANUAL = 1

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__(neo_adapter=neo_adapter, parent=parent)

        # --- UI References ---
        self.voltage_channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.current_channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        self.mode_combobox: Optional[QtWidgets.QComboBox] = None
        self.manual_time_group: Optional[QtWidgets.QGroupBox] = None
        self.manual_baseline_start_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.manual_baseline_end_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.manual_response_start_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.manual_response_end_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.manual_delta_i_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.run_button: Optional[QtWidgets.QPushButton] = None
        self.rin_result_label: Optional[QtWidgets.QLabel] = None
        self.delta_i_label: Optional[QtWidgets.QLabel] = None
        self.delta_v_label: Optional[QtWidgets.QLabel] = None
        self.status_label: Optional[QtWidgets.QLabel] = None
        self.baseline_region: Optional[pg.LinearRegionItem] = None
        self.response_region: Optional[pg.LinearRegionItem] = None
        self.baseline_line: Optional[pg.InfiniteLine] = None
        self.response_line: Optional[pg.InfiniteLine] = None
        self.voltage_plot_item: Optional[pg.PlotDataItem] = None
        self.current_plot_item: Optional[pg.PlotDataItem] = None
        self._current_plot_data: Optional[Dict[str, Any]] = None
        self._last_rin_result: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._connect_signals()

    def get_display_name(self) -> str:
        return "Input Resistance (Rin)"

    def _setup_ui(self):
        """Recreate UI elements for Rin analysis with a 3-column layout."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10) # Increased spacing for groups

        # --- Top Controls Area (3 Columns) ---
        top_controls_widget = QtWidgets.QWidget()
        top_controls_layout = QtWidgets.QHBoxLayout(top_controls_widget)
        top_controls_layout.setContentsMargins(0,0,0,0)
        top_controls_layout.setSpacing(8)
        top_controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Column 1: Data Selection --- 
        # Renamed group box and moved items here
        self.data_selection_group = QtWidgets.QGroupBox("Data Selection") # <<< RENAMED TITLE
        self.data_selection_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Preferred)
        data_selection_layout = QtWidgets.QVBoxLayout(self.data_selection_group)
        data_selection_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Analysis Item Selector (inherited)
        item_selector_layout = QtWidgets.QFormLayout()
        self._setup_analysis_item_selector(item_selector_layout)
        data_selection_layout.addLayout(item_selector_layout)

        # Channel/Data Source
        channel_layout = QtWidgets.QFormLayout()
        self.voltage_channel_combobox = QtWidgets.QComboBox()
        self.voltage_channel_combobox.setToolTip("Select the voltage channel to analyze.")
        self.voltage_channel_combobox.setEnabled(False)
        channel_layout.addRow("Voltage Channel:", self.voltage_channel_combobox)

        self.current_channel_combobox = QtWidgets.QComboBox()
        self.current_channel_combobox.setToolTip("Select the corresponding current channel (used for auto ΔI). Optional if Manual ΔI is provided.")
        self.current_channel_combobox.setEnabled(False)
        channel_layout.addRow("Current Channel:", self.current_channel_combobox)

        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)
        channel_layout.addRow("Data Source:", self.data_source_combobox)
        data_selection_layout.addLayout(channel_layout)

        # Manual Delta I (Always visible within this group)
        delta_i_layout = QtWidgets.QFormLayout()
        self.manual_delta_i_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_delta_i_spinbox.setDecimals(3)
        self.manual_delta_i_spinbox.setRange(-1e6, 1e6)
        self.manual_delta_i_spinbox.setSingleStep(10)
        self.manual_delta_i_spinbox.setSuffix(" pA")
        self.manual_delta_i_spinbox.setValue(0.0)
        self.manual_delta_i_spinbox.setToolTip("Manually enter the injected current step amplitude (ΔI, in pA). Overrides calculation from trace if non-zero.")
        delta_i_layout.addRow("Manual ΔI (pA):", self.manual_delta_i_spinbox)
        data_selection_layout.addLayout(delta_i_layout)

        data_selection_layout.addStretch(1) # Add stretch at the end of the column
        top_controls_layout.addWidget(self.data_selection_group) # Add Col 1 to top layout

        # --- Column 2: Analysis Mode & Parameters ---
        self.analysis_params_group = QtWidgets.QGroupBox("Analysis Mode & Parameters")
        self.analysis_params_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Preferred)
        analysis_params_layout = QtWidgets.QVBoxLayout(self.analysis_params_group)
        analysis_params_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Analysis Mode
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel("Window Mode:")) # Changed label for clarity
        self.mode_combobox = QtWidgets.QComboBox()
        self.mode_combobox.addItems(["Interactive", "Manual"])
        self.mode_combobox.setToolTip(
            "Interactive: Use region selectors on plot.\n"
            "Manual: Enter specific time windows below.")
        mode_layout.addWidget(self.mode_combobox)
        analysis_params_layout.addLayout(mode_layout)

        # Manual Time Window Group (Only visible in Manual Mode)
        self.manual_time_group = QtWidgets.QGroupBox("Manual Time Windows (s)")
        manual_layout = QtWidgets.QFormLayout(self.manual_time_group)
        self.manual_baseline_start_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_baseline_end_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_response_start_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_response_end_spinbox = QtWidgets.QDoubleSpinBox()
        for spinbox in [self.manual_baseline_start_spinbox, self.manual_baseline_end_spinbox,
                        self.manual_response_start_spinbox, self.manual_response_end_spinbox]:
            spinbox.setDecimals(4); spinbox.setRange(0.0, 1e6); spinbox.setSingleStep(0.01); spinbox.setSuffix(" s")
        manual_layout.addRow("Baseline Start:", self.manual_baseline_start_spinbox)
        manual_layout.addRow("Baseline End:", self.manual_baseline_end_spinbox)
        manual_layout.addRow("Response Start:", self.manual_response_start_spinbox)
        manual_layout.addRow("Response End:", self.manual_response_end_spinbox)
        self.manual_time_group.setVisible(False) # Initially hidden
        analysis_params_layout.addWidget(self.manual_time_group)

        # Run Button (Only visible & enabled in Manual mode)
        self.run_button = QtWidgets.QPushButton("Calculate Rin (Manual Times)") # Reverted text
        self.run_button.setToolTip("Calculate Rin using the manually entered time windows above.")
        self.run_button.setVisible(False) # <<< VISIBLE FALSE BY DEFAULT
        self.run_button.setEnabled(False) # Initially disabled
        analysis_params_layout.addWidget(self.run_button)

        analysis_params_layout.addStretch(1)
        top_controls_layout.addWidget(self.analysis_params_group) # Add Col 2 to top layout

        # --- Column 3: Results --- 
        self.results_group = QtWidgets.QGroupBox("Results")
        self.results_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred) # Expand horizontally
        results_layout = QtWidgets.QVBoxLayout(self.results_group)
        results_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.rin_result_label = QtWidgets.QLabel("Input Resistance (Rin): --")
        results_layout.addWidget(self.rin_result_label)
        self.delta_v_label = QtWidgets.QLabel("Voltage Change (ΔV): --")
        results_layout.addWidget(self.delta_v_label)
        self.delta_i_label = QtWidgets.QLabel("Current Step (ΔI): --") # Show the ΔI used
        results_layout.addWidget(self.delta_i_label)
        self.status_label = QtWidgets.QLabel("Status: Idle")
        self.status_label.setWordWrap(True)
        results_layout.addWidget(self.status_label)
        self._setup_save_button(results_layout)
        results_layout.addStretch(1)
        top_controls_layout.addWidget(self.results_group) # Add Col 3 to top layout

        # Add top controls area widget to main layout
        main_layout.addWidget(top_controls_widget)

        # --- Bottom: Plot Area --- 
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self._setup_plot_area(plot_layout)
        main_layout.addWidget(plot_container, stretch=1) # Plot takes remaining vertical space

        # --- Plot items specific to Rin --- 
        # Check if plot_widget exists before adding items
        if self.plot_widget:
            # Region Selectors (Interactive Mode)
            self.baseline_region = pg.LinearRegionItem(values=[0.0, 0.1], brush=(0, 0, 255, 30), movable=True, bounds=[0, 1])
            self.response_region = pg.LinearRegionItem(values=[0.2, 0.3], brush=(255, 0, 0, 30), movable=True, bounds=[0, 1])
            self.plot_widget.addItem(self.baseline_region)
            self.plot_widget.addItem(self.response_region)

            # Lines for visualization (added dynamically)
            self.baseline_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(color=(0, 0, 255), style=QtCore.Qt.PenStyle.DashLine))
            self.response_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(color=(255, 0, 0), style=QtCore.Qt.PenStyle.DashLine))
            self.plot_widget.addItem(self.baseline_line)
            self.plot_widget.addItem(self.response_line)
            self.baseline_line.setVisible(False)
            self.response_line.setVisible(False)
        else:
            log.error("Plot widget not initialized before adding Rin-specific items.")

        self.setLayout(main_layout)
        log.debug("Rin Analysis Tab UI setup complete (3-Column Layout).")
        self._on_mode_changed() # Set initial state based on mode

    def _connect_signals(self):
        # Item selection handled by base class
        if self.voltage_channel_combobox: self.voltage_channel_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        if self.current_channel_combobox: self.current_channel_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        if self.data_source_combobox: self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        # Use ComboBox signal for mode changes
        if self.mode_combobox: self.mode_combobox.currentIndexChanged.connect(self._on_mode_changed)
        
        # --- RE-ADDED Auto-triggers for Interactive Mode --- 
        # Manual Time Edits (trigger analysis only in manual mode)
        if self.manual_baseline_start_spinbox: self.manual_baseline_start_spinbox.editingFinished.connect(self._trigger_rin_analysis_if_manual)
        if self.manual_baseline_end_spinbox: self.manual_baseline_end_spinbox.editingFinished.connect(self._trigger_rin_analysis_if_manual)
        if self.manual_response_start_spinbox: self.manual_response_start_spinbox.editingFinished.connect(self._trigger_rin_analysis_if_manual)
        if self.manual_response_end_spinbox: self.manual_response_end_spinbox.editingFinished.connect(self._trigger_rin_analysis_if_manual)
        # Manual Delta I edit does NOT trigger analysis on its own
        # Region Edits (trigger analysis in interactive mode)
        if self.baseline_region: self.baseline_region.sigRegionChangeFinished.connect(self._trigger_rin_analysis_if_interactive)
        if self.response_region: self.response_region.sigRegionChangeFinished.connect(self._trigger_rin_analysis_if_interactive)
        # --- END RE-ADDED ---

        # Connect Run Button (ONLY for manual mode trigger via helper slot)
        if self.run_button: self.run_button.clicked.connect(self._trigger_rin_analysis_if_manual)
        # Save button handled by base class

    def _update_ui_for_selected_item(self):
        """Update Rin tab UI for new analysis item."""
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None
        self.rin_result_label.setText("Rin: --")
        self.delta_v_label.setText("ΔV: --")
        self.delta_i_label.setText("ΔI: --")
        if self.save_button: self.save_button.setEnabled(False)

        # --- ADDED: Log available channels --- 
        if self._selected_item_recording and self._selected_item_recording.channels:
            # Corrected: Get path from _analysis_items using the current index
            current_item_path = self._analysis_items[self._selected_item_index].get('Path', 'Unknown Path')
            log.debug(f"Available channels in recording ({current_item_path}):")
            for ch_id, ch in self._selected_item_recording.channels.items():
                log.debug(f"  - ID: {ch_id}, Name: {getattr(ch, 'name', 'N/A')}, Units: {getattr(ch, 'units', 'N/A')}")
        else:
            log.debug("No recording or channels found to list.")
        # --- END ADDED --- 

        # --- Populate Channel ComboBox ---
        self.voltage_channel_combobox.blockSignals(True)
        self.voltage_channel_combobox.clear()
        voltage_channels_found = False
        if self._selected_item_recording and self._selected_item_recording.channels:
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                 units_lower = getattr(channel, 'units', '').lower()
                 if 'v' in units_lower: # Look for voltage channels
                      display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{channel.units}]"
                      self.voltage_channel_combobox.addItem(display_name, userData=chan_id)
                      voltage_channels_found = True
            if voltage_channels_found:
                self.voltage_channel_combobox.setCurrentIndex(0)
            else:
                self.voltage_channel_combobox.addItem("No Voltage Channels")
        else:
            self.voltage_channel_combobox.addItem("Load Data Item")
        self.voltage_channel_combobox.setEnabled(voltage_channels_found)
        self.voltage_channel_combobox.blockSignals(False)

        # --- Populate Data Source ComboBox ---
        # (Identical logic to rmp_tab.py - could be moved to base class if desired)
        self.data_source_combobox.blockSignals(True)
        self.data_source_combobox.clear()
        self.data_source_combobox.setEnabled(False)
        can_analyze = False
        if voltage_channels_found and self._selected_item_recording:
            selected_item_details = self._analysis_items[self._selected_item_index]
            item_type = selected_item_details.get('target_type')
            item_trial_index = selected_item_details.get('trial_index')
            num_trials = 0
            has_average = False
            first_channel = next(iter(self._selected_item_recording.channels.values()), None)
            if first_channel:
                 num_trials = getattr(first_channel, 'num_trials', 0)
                 if hasattr(first_channel, 'get_averaged_data') and first_channel.get_averaged_data() is not None: has_average = True
                 elif hasattr(first_channel, 'has_average_data') and first_channel.has_average_data(): has_average = True

            if item_type == "Current Trial" and item_trial_index is not None and 0 <= item_trial_index < num_trials:
                self.data_source_combobox.addItem(f"Trial {item_trial_index + 1}", userData=item_trial_index); can_analyze = True
            elif item_type == "Average Trace" and has_average:
                self.data_source_combobox.addItem("Average Trace", userData="average"); can_analyze = True
            elif item_type == "Recording" or item_type == "All Trials":
                if has_average: self.data_source_combobox.addItem("Average Trace", userData="average")
                if num_trials > 0:
                    for i in range(num_trials): self.data_source_combobox.addItem(f"Trial {i + 1}", userData=i)
                if self.data_source_combobox.count() > 0: self.data_source_combobox.setEnabled(True); can_analyze = True
                else: self.data_source_combobox.addItem("No Trials/Average")
            else: self.data_source_combobox.addItem("Invalid Source Item")
        else: self.data_source_combobox.addItem("N/A")
        self.data_source_combobox.blockSignals(False)

        # --- Enable/Disable Controls --- 
        has_valid_selection = (self._selected_item_index >= 0 and self._selected_item_recording is not None)
        can_analyze = False # Determine if we can find data to plot
        if has_valid_selection: 
            # Check if channels/data sources were successfully populated
            volt_chans = self.voltage_channel_combobox.count() > 0 and self.voltage_channel_combobox.currentData() is not None
            data_sources = self.data_source_combobox.count() > 0 and self.data_source_combobox.currentData() is not None
            can_analyze = volt_chans and data_sources

        # Enable groups based on whether analysis is possible
        self.data_selection_group.setEnabled(can_analyze)
        self.analysis_params_group.setEnabled(can_analyze)
        self.results_group.setEnabled(can_analyze)

        self._on_mode_changed() # Update mode-specific controls

        # --- Plot Initial Trace --- 
        if can_analyze:
            self._plot_selected_trace()
        else:
            if self.plot_widget: self.plot_widget.clear()
            self._clear_rin_visualization_lines()
            # Ensure results are cleared if no data
            self.rin_result_label.setText("Rin: --")
            self.delta_v_label.setText("ΔV: --")
            self.delta_i_label.setText("ΔI: --")
            self.status_label.setText("Status: Select valid data.")
            if self.run_button: self.run_button.setEnabled(False) # <<< Disable button if no data

    def _plot_selected_trace(self):
        """Plots voltage and current for the selected channel/source."""
        # --- Reset UI State & Data --- 
        if self.plot_widget: self.plot_widget.clear()
        # Disable button initially during plot update
        if self.run_button: self.run_button.setEnabled(False) 
        self.rin_result_label.setText("Rin: --")
        self.delta_v_label.setText("ΔV: --")
        self.delta_i_label.setText("ΔI: --")
        if self.save_button: self.save_button.setEnabled(False)
        self._current_plot_data = None
        self._clear_rin_visualization_lines()
        
        # --- Check prerequisites --- 
        if not self.plot_widget or not self.voltage_channel_combobox or not self.data_source_combobox or not self._selected_item_recording:
            # Ensure button remains disabled if basic setup fails
            if self.run_button: self.run_button.setEnabled(False)
            return

        chan_id = self.voltage_channel_combobox.currentData()
        source_data = self.data_source_combobox.currentData()
        if not chan_id or source_data is None:
             self._current_plot_data = None; self.plot_widget.clear();
             self._clear_rin_visualization_lines()
             if self.run_button: self.run_button.setEnabled(False) # <<< Disable button
             return

        channel = self._selected_item_recording.channels.get(chan_id)
        log.debug(f"Plotting Rin trace for Ch {chan_id}, Data Source: {source_data}")
        if channel:
            log.debug(f"Channel ({chan_id}) attributes/methods: {dir(channel)}")
        else:
            log.warning(f"Channel ({chan_id}) not found in recording.")
            return # Cannot proceed without channel

        time_v, voltage, time_i, current = None, None, None, None
        v_label, i_label = "Voltage Error", "Current Error"

        try:
            if channel:
                # Fetch Voltage Data
                if source_data == "average":
                    voltage = channel.get_averaged_data()
                    time_v = channel.get_relative_averaged_time_vector()
                    v_label = f"{channel.name or chan_id} V (Avg)"
                elif isinstance(source_data, int):
                    trial_index = source_data
                    if 0 <= trial_index < channel.num_trials:
                        voltage = channel.get_data(trial_index)
                        time_v = channel.get_relative_time_vector(trial_index)
                        v_label = f"{channel.name or chan_id} V (Tr {trial_index + 1})"

                # Fetch Current Data using Channel methods
                current, time_i = None, None # Initialize
                if source_data == "average":
                    current = channel.get_averaged_current_data()
                    time_i = channel.get_relative_averaged_time_vector() # Assume same time base as voltage average
                    i_label = f"{channel.name or chan_id} I (Avg)"
                    log.debug(f"Fetched avg current using channel method: current is None = {current is None}, time_i is None = {time_i is None}")
                elif isinstance(source_data, int):
                    trial_index = source_data
                    current = channel.get_current_data(trial_index)
                    time_i = channel.get_relative_time_vector(trial_index) # Assume same time base as voltage trial
                    i_label = f"{channel.name or chan_id} I (Tr {trial_index + 1})"
                    log.debug(f"Fetched trial {trial_index} current using channel method: current is None = {current is None}, time_i is None = {time_i is None}")
                
                if current is None: # Check only current, assuming time_i will be valid if voltage time_v was
                    log.warning(f"Could not retrieve current trace for Ch {chan_id}, Source: {source_data} using channel methods.")
                    i_label = "Current N/A"
                    time_i = None # Ensure time_i is None if current is None

                # --- REVISED: Store data conditionally --- 
                plot_succeeded = False # Flag to track if voltage plotted
                if time_v is not None and voltage is not None:
                     self._current_plot_data = {'time_v': time_v, 'voltage': voltage}
                     log.debug(f"Stored voltage data. Keys: {list(self._current_plot_data.keys())}")
                     plot_succeeded = True # Mark voltage plot as successful
                else:
                     log.warning(f"Failed to fetch valid voltage data for Ch {chan_id}, Source: {source_data}. Plotting and analysis aborted.")
                     # Ensure plot is clear and controls disabled if voltage fetch fails
                     self.plot_widget.clear()
                     self._clear_rin_visualization_lines()
                     if self.run_button: self.run_button.setEnabled(False) # <<< Disable button
                     return # Cannot proceed without voltage
                
                # 2. Add current data if valid AND voltage was stored
                if self._current_plot_data and time_i is not None and current is not None:
                    self._current_plot_data['time_i'] = time_i
                    self._current_plot_data['current'] = current
                    log.debug(f"Added current data. Keys: {list(self._current_plot_data.keys())}")
                elif self._current_plot_data: # Voltage exists, but current failed/missing
                    log.warning(f"Valid voltage stored, but current trace is missing/invalid for Ch {chan_id}, Source: {source_data}. Will rely on manual ΔI.")
                    # Remove any potential old keys just in case, but keep the dict
                    self._current_plot_data.pop('time_i', None) 
                    self._current_plot_data.pop('current', None)
                    i_label = "Current N/A"
                else:
                    # This case should ideally not be reached due to the return above if voltage failed
                    log.error("Internal logic error: Attempted to handle current data when voltage data failed.")
                    i_label = "Current N/A"
                # --- END REVISED DATA STORAGE ---

                # --- Plotting --- 
                # Use clearPlots which keeps axes/regions, vs clear() which removes everything
                self.plot_widget.clearPlots() 
                # Detach regions FIRST before potential viewbox manipulation/clearing
                if self.baseline_region and self.baseline_region.getViewBox(): self.baseline_region.getViewBox().removeItem(self.baseline_region)
                if self.response_region and self.response_region.getViewBox(): self.response_region.getViewBox().removeItem(self.response_region)

                # Remove previous current plot item if it exists
                if self.current_plot_item and self.current_plot_item.scene():
                    self.plot_widget.removeItem(self.current_plot_item)
                    self.current_plot_item = None
                # Clear the secondary viewbox if it exists
                if hasattr(self.plot_widget.getPlotItem().layout, 'removeItem'): # Check layout exists
                    vb = self.plot_widget.getPlotItem().getViewBox()
                    if hasattr(vb, '_synaptipy_vb2'):
                        # Check if vb2 is still in the layout before removing
                        if self.plot_widget.getPlotItem().layout.itemAt(1,1) == vb._synaptipy_vb2: # Adjust indices if needed
                            self.plot_widget.getPlotItem().layout.removeItem(vb._synaptipy_vb2)
                        # Remove vb2 from scene and delete reference regardless
                        if vb._synaptipy_vb2.scene():
                            vb._synaptipy_vb2.scene().removeItem(vb._synaptipy_vb2)
                        del vb._synaptipy_vb2 # Clean up reference


                if time_v is not None and voltage is not None:
                    # Plot Voltage first
                    voltage_plot_item = self.plot_widget.plot(time_v, voltage, pen='k', name=v_label)
                    self.plot_widget.setLabel('left', 'Voltage', units=channel.units or 'V')
                    self.plot_widget.setLabel('bottom', 'Time', units='s')
                    # self._current_plot_data = {'time_v': time_v, 'voltage': voltage} # MOVED storage earlier

                    # Enable calculate button now that voltage is successfully plotted
                    if self.run_button: self.run_button.setEnabled(True) # <<< ENABLE BUTTON HERE

                    # Add current trace if available (check stored data)
                    if self._current_plot_data and 'current' in self._current_plot_data:
                        time_i_stored = self._current_plot_data['time_i']
                        current_stored = self._current_plot_data['current']
                        # Create secondary Y axis for current
                        p1 = self.plot_widget.getPlotItem()
                        p1.showAxis('right')
                        vb = p1.getViewBox()
                        # Check if we already added the second viewbox in a previous plot call
                        # Check if vb2 is already managed by the layout
                        if p1.layout.itemAt(1,1) is None: # Assuming current plot is at row 1, col 1
                            vb2 = pg.ViewBox()
                            vb._synaptipy_vb2 = vb2 # Store reference on primary viewbox
                            p1.scene().addItem(vb2) # Add to scene first
                            # Add vb2 to the grid layout AFTER voltage plot (e.g., row 1, col 1)
                            # This requires assuming the plot item layout is a QGraphicsGridLayout
                            # It might be safer to link views without placing vb2 in the layout explicitly
                            # p1.layout.addItem(vb2, 1, 1) # TRY TO AVOID THIS if linking works
                            
                            p1.getAxis('right').linkToView(vb2)
                            vb2.setXLink(vb)
                            
                            # Function to update views
                            def update_views():
                                try:
                                    vb2.setGeometry(vb.sceneBoundingRect())
                                    vb2.linkedViewChanged(vb.getViewBox(), vb2.XAxis)
                                except RuntimeError: pass # Ignore if viewbox is being deleted
                            
                            vb.sigStateChanged.connect(update_views) # Use sigStateChanged for better sync
                            update_views() # Initial sync
                        else:
                             vb2 = p1.layout.itemAt(1,1).getViewBox() # Try to get from layout
                             if not vb2: # Fallback if layout doesn't work as expected
                                 vb2 = getattr(vb, '_synaptipy_vb2', None)
                             if not vb2: 
                                 log.error("Failed to retrieve secondary ViewBox for current plot.")
                                 return # Cannot plot current without ViewBox
                             vb2.clear() # Clear previous items from the viewbox

                        # Ensure vb2 exists before adding item
                        if vb2:
                            self.current_plot_item = pg.PlotDataItem(time_i_stored, current_stored, pen='r', name=i_label)
                            vb2.addItem(self.current_plot_item)
                            current_units = channel.current_units if channel.current_units else 'A' # Use stored units or default
                            p1.getAxis('right').setLabel('Current', units=current_units)
                        else:
                            log.error("Secondary ViewBox (vb2) not found, cannot plot current trace.")

                    # Update region bounds and positions
                    min_t, max_t = time_v[0], time_v[-1]
                    for region in [self.baseline_region, self.response_region]:
                         region.setBounds([min_t, max_t])
                         rgn_start, rgn_end = region.getRegion()
                         if rgn_start < min_t or rgn_end > max_t or rgn_start >= rgn_end:
                              # Simple reset logic - needs refinement based on typical steps
                              bl_end = min(min_t + 0.1, min_t + (max_t - min_t) * 0.1, max_t)
                              resp_start = min(bl_end + 0.05, max_t)
                              resp_end = min(resp_start + 0.1, max_t)
                              if region == self.baseline_region: region.setRegion([min_t, bl_end])
                              else: region.setRegion([resp_start, resp_end])
                              log.debug(f"Resetting region {region.name} to default.")
                else: 
                    log.warning(f"No valid voltage data found to plot for channel {chan_id}")
                    self.plot_widget.clearPlots()
                    self._clear_rin_visualization_lines()
                    self._current_plot_data = None 
                    if self.run_button: self.run_button.setEnabled(False) # <<< Keep button disabled

                # Re-add regions after potential clearing and plotting
                # Check if they are already added (e.g., if voltage plotted but current failed)
                if self.baseline_region.scene() is None:
                     self.plot_widget.addItem(self.baseline_region)
                if self.response_region.scene() is None:
                     self.plot_widget.addItem(self.response_region)
                # Set title based on voltage plot success
                self.plot_widget.setTitle(v_label if voltage is not None else "Plot Error") 

        except Exception as e:
            log.error(f"Error plotting trace for channel {chan_id}: {e}", exc_info=True)
            self.plot_widget.clear()
            self._clear_rin_visualization_lines()
            # Attempt to re-add regions even on error
            try:
                if self.baseline_region.scene() is None: self.plot_widget.addItem(self.baseline_region)
                if self.response_region.scene() is None: self.plot_widget.addItem(self.response_region)
            except Exception as add_err:
                log.error(f"Error re-adding regions after plot error: {add_err}")
            self._current_plot_data = None
            if self.run_button: self.run_button.setEnabled(False) # <<< Disable button on error

        # INSTEAD: Enable calculate button if voltage plot succeeded
        # Manual dI also enabled based on voltage success
        if voltage is not None:
             self.run_button.setEnabled(True)
        else:
             self.run_button.setEnabled(False)
             self.rin_result_label.setText("Rin: --")
             self.delta_v_label.setText("ΔV: --")
             self.delta_i_label.setText("ΔI: --")
             if self.save_button: self.save_button.setEnabled(False)

    @QtCore.Slot()
    def _on_mode_changed(self):
        """Update UI elements based on the selected mode (ComboBox)."""
        if not self.mode_combobox: return
        
        current_mode_text = self.mode_combobox.currentText()
        is_manual = (current_mode_text == "Manual")
        is_interactive = (current_mode_text == "Interactive")

        # Show/hide manual time group and run button
        if self.manual_time_group: self.manual_time_group.setVisible(is_manual)
        if self.run_button: self.run_button.setVisible(is_manual) # <<< Visibility depends on mode
        
        # Enable run button only if manual mode is active AND data is plotted
        has_data = self._current_plot_data is not None
        if self.run_button: self.run_button.setEnabled(is_manual and has_data)

        # Show/hide interactive regions
        if self.baseline_region: self.baseline_region.setVisible(is_interactive)
        if self.response_region: self.response_region.setVisible(is_interactive)
        # Enable/disable moving regions
        if self.baseline_region: self.baseline_region.setMovable(is_interactive)
        if self.response_region: self.response_region.setMovable(is_interactive)

        log.debug(f"Rin analysis mode changed to: {current_mode_text}. Manual Time Group Visible: {is_manual}, Run Button Visible: {is_manual}, Interactive Regions Visible: {is_interactive}")
        
        # Trigger analysis immediately only if in interactive mode AND data exists
        if is_interactive and has_data:
            self._trigger_rin_analysis() # <<< Re-added trigger for interactive mode
        else:
            # Clear results or wait for explicit trigger in manual mode
            self.status_label.setText(f"Status: {current_mode_text} mode - Ready.")
            # Consider clearing results/visualization when switching TO manual?
            # self._clear_rin_visualization_lines() # Optional
            # self.rin_result_label.setText("Rin: --") # Optional

    # --- RE-ADDED: Helper slots to trigger analysis only in the correct mode ---
    @QtCore.Slot()
    def _trigger_rin_analysis_if_manual(self):
        """Trigger analysis only if the current mode is Manual."""
        if self.mode_combobox and self.mode_combobox.currentText() == "Manual":
            log.debug("Triggering Rin analysis from manual input (button/spinbox).")
            self._trigger_rin_analysis()
            
    @QtCore.Slot()
    def _trigger_rin_analysis_if_interactive(self):
        """Trigger analysis only if the current mode is Interactive."""
        if self.mode_combobox and self.mode_combobox.currentText() == "Interactive":
            log.debug("Triggering Rin analysis from interactive region change.")
            self._trigger_rin_analysis()
    # --- END RE-ADDED ---

    @QtCore.Slot()
    def _trigger_rin_analysis(self):
        """Central method to perform Rin calculation based on current mode and inputs."""
        log.debug(f"_trigger_rin_analysis called. self._current_plot_data keys: {list(self._current_plot_data.keys()) if self._current_plot_data else 'None'}")

        # --- Reset state ---
        self._last_rin_result = None
        self.rin_result_label.setText("Rin: Calculating...")
        self.delta_v_label.setText("ΔV: --")
        self.delta_i_label.setText("ΔI: --")
        if self.save_button: self.save_button.setEnabled(False)

        # --- 1. Check for Voltage Data ---
        if not self._current_plot_data or \
           'voltage' not in self._current_plot_data or \
           'time_v' not in self._current_plot_data:
            log.debug("Skipping Rin analysis: Voltage data missing.")
            self.rin_result_label.setText("Rin: Voltage Data Missing")
            return

        time_v = self._current_plot_data['time_v']
        voltage = self._current_plot_data['voltage']

        # --- Get Delta I (in pA) ---
        final_delta_i_pa = 0.0 # Initialize to zero, holds the final value in pA
        delta_i_source = "N/A" # N/A, Manual, Calculated

        # 1. Try Manual Delta I
        manual_delta_i_value_pa = 0.0 # Store the raw input just for logging/errors
        has_manual_spinbox = hasattr(self, 'manual_delta_i_spinbox') and self.manual_delta_i_spinbox is not None
        if has_manual_spinbox:
            manual_delta_i_value_pa = self.manual_delta_i_spinbox.value()
            # Use the manual value ONLY if it's significantly different from zero
            if not np.isclose(manual_delta_i_value_pa, 0.0):
                final_delta_i_pa = manual_delta_i_value_pa
                delta_i_source = "Manual"
                log.debug(f"Using Manual Delta I: {final_delta_i_pa:.3f} pA")
            else:
                log.debug("Manual Delta I is zero, will attempt calculation.")
        else:
            log.debug("Manual Delta I spinbox not found, attempting calculation.")

        # 2. Try Calculate Delta I (only if Manual was zero or unavailable)
        if np.isclose(final_delta_i_pa, 0.0):
            log.debug("Attempting to calculate Delta I from trace.")
            current_trace = self._current_plot_data.get('current')
            time_c = self._current_plot_data.get('time_i')
            calculation_attempted = False
            calculation_succeeded_non_zero = False

            if current_trace is not None and time_c is not None:
                log.debug("Current trace and time vector found.")
                baseline_window, response_window = self._get_analysis_windows()
                if baseline_window is not None and response_window is not None:
                    log.debug(f"Analysis windows obtained: BL={baseline_window}, Resp={response_window}")
                    calculation_attempted = True # We have data and windows
                    try:
                        if baseline_window[0] < baseline_window[1] and response_window[0] < response_window[1]:
                            mask_baseline_c = (time_c >= baseline_window[0]) & (time_c <= baseline_window[1])
                            mask_response_c = (time_c >= response_window[0]) & (time_c <= response_window[1])

                            if np.any(mask_baseline_c) and np.any(mask_response_c):
                                baseline_current = np.mean(current_trace[mask_baseline_c]) # Amps
                                response_current = np.mean(current_trace[mask_response_c]) # Amps
                                delta_i_calculated_a = response_current - baseline_current # Amps
                                delta_i_calculated_pa = delta_i_calculated_a * 1e12 # Convert to pA
                                log.debug(f"Calculated Delta I raw value: {delta_i_calculated_pa:.4f} pA")

                                # Assign ONLY if significantly non-zero
                                if not np.isclose(delta_i_calculated_pa, 0.0):
                                    final_delta_i_pa = delta_i_calculated_pa
                                    delta_i_source = "Calculated"
                                    calculation_succeeded_non_zero = True
                                    log.debug(f"Using Calculated Delta I: {final_delta_i_pa:.3f} pA")
                                else:
                                    log.warning("Calculated Delta I from trace is zero or close to zero.")
                            else:
                                 log.warning("Could not calculate Delta I: No data points found within window(s) in current trace.")
                        else:
                            log.warning("Could not calculate Delta I: Baseline or response windows are invalid.")
                    except Exception as e:
                        log.error(f"Error during Delta I calculation from current trace: {e}", exc_info=True)
                else: # Windows were None
                    log.warning("Could not calculate Delta I: Failed to get valid analysis windows.")
                    # Status message should be set by _get_analysis_windows
            else:
                log.warning("Cannot calculate Delta I: Current trace data ('current', 'time_i') not found.")

            # Update source if calculation failed after being attempted
            if calculation_attempted and not calculation_succeeded_non_zero and delta_i_source != "Manual":
                 delta_i_source = "Calculation Failed/Zero"

        # 3. Validate Final Delta I (must be non-zero)
        if delta_i_source == "N/A" or delta_i_source == "Calculation Failed/Zero":
            # Failure: Manual was zero/missing AND calculation failed/was zero
            error_msg = "Could not determine a non-zero ΔI. "
            if not has_manual_spinbox:
                 error_msg += "Manual input missing. "
            elif np.isclose(manual_delta_i_value_pa, 0.0):
                 error_msg += f"Manual input was zero. "
                 
            if 'current' not in self._current_plot_data:
                 error_msg += "Current trace missing for calculation. "
            elif delta_i_source == "Calculation Failed/Zero":
                 error_msg += "Calculation from trace failed or yielded zero. "
                 
            error_msg += "Check windows or provide non-zero Manual ΔI."
            log.error(error_msg)
            self.status_label.setText(f"Status: Error - {error_msg}")
            self._clear_rin_visualization_lines()
            self.delta_i_label.setText("ΔI: -- Error --")
            if self.save_button: self.save_button.setEnabled(False)
            return # Stop processing
        
        # --- If we reach here, final_delta_i_pa holds a valid non-zero value in pA ---
        self.delta_i_label.setText(f"ΔI: {final_delta_i_pa:.2f} pA ({delta_i_source})")

        # --- Calculate Rin ---
        # Get windows again just before calculation (might have changed in manual mode)
        baseline_win, response_win = self._get_analysis_windows()
        if baseline_win is None or response_win is None:
             log.error("Failed to get valid analysis windows just before Rin calculation.")
             # Status should be set by _get_analysis_windows
             return # Stop if windows invalid

        # Pass the non-zero pA value to the calculation function
        log.debug(f"Running calculate_rin with dI = {final_delta_i_pa:.3f} pA")
        calc_result = calculate_rin(time_v, voltage, baseline_win, response_win, final_delta_i_pa)

        # --- Display Result ---
        if calc_result is not None:
            rin_mohm, dV_mv = calc_result
            # Store the final pA value used and the determined source
            self._last_rin_result = (rin_mohm, dV_mv, final_delta_i_pa, delta_i_source)
            self.rin_result_label.setText(f"Rin: {rin_mohm:.2f} MΩ")
            self.delta_v_label.setText(f"ΔV: {dV_mv:.2f} mV")
            # delta_i_label already set above
            self.status_label.setText(f"Status: Calculation complete ({delta_i_source} ΔI). Mode: {self.mode_combobox.currentText()}")
            log.info(f"Rin = {rin_mohm:.2f} MΩ (dV={dV_mv:.2f}mV, ΔI={final_delta_i_pa:.2f}pA ({delta_i_source}))")
            if self.save_button: self.save_button.setEnabled(True)
            self._update_rin_visualization_lines(baseline_win, response_win, voltage)
        else:
            # calculate_rin returned None
            self.rin_result_label.setText("Rin: Calculation Error")
            self.delta_v_label.setText("ΔV: --")
            # Keep the delta_i label showing the value that was passed
            self.status_label.setText("Status: Error during Rin calculation (check windows/data validity).")
            log.warning(f"calculate_rin returned None. Input delta_i was {final_delta_i_pa:.3f} pA.")
            self._clear_rin_visualization_lines()

    def _get_analysis_windows(self) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        """Gets baseline and response windows based on current mode.
           Updates UI elements (regions or reflects spinbox values).
           Returns (None, None) if validation fails, setting status_label.
        """
        baseline_win, response_win = None, None
        current_mode_text = self.mode_combobox.currentText()

        if current_mode_text == "Interactive":
            if not self.baseline_region or not self.response_region:
                log.error("Interactive mode selected but region items are missing.")
                self.status_label.setText("Status: Error - Interactive regions missing.")
                return None, None
            baseline_win = self.baseline_region.getRegion()
            response_win = self.response_region.getRegion()
            log.debug(f"Using Interactive Windows. BL: {baseline_win}, Resp: {response_win}")
        
        elif current_mode_text == "Manual":
            if not self.manual_baseline_start_spinbox or not self.manual_baseline_end_spinbox or \
               not self.manual_response_start_spinbox or not self.manual_response_end_spinbox:
               log.error("Manual mode selected but spinboxes are missing.")
               self.status_label.setText("Status: Error - Manual time inputs missing.")
               return None, None
            try:
                bl_s = self.manual_baseline_start_spinbox.value()
                bl_e = self.manual_baseline_end_spinbox.value()
                r_s = self.manual_response_start_spinbox.value()
                r_e = self.manual_response_end_spinbox.value()
                if bl_s >= bl_e or r_s >= r_e:
                    raise ValueError("Start time must be less than end time for windows.")
                baseline_win = (bl_s, bl_e)
                response_win = (r_s, r_e)
                # Update regions from manual fields if they exist
                if self.baseline_region: self.baseline_region.setRegion(baseline_win)
                if self.response_region: self.response_region.setRegion(response_win)
                log.debug(f"Using Manual Windows. BL: {baseline_win}, Resp: {response_win}")
            except ValueError as e:
                log.warning(f"Manual time validation failed: {e}")
                self.status_label.setText(f"Status: Invalid Time ({e})")
                return None, None
        else:
             log.error(f"Unknown analysis mode selected: {current_mode_text}")
             self.status_label.setText(f"Status: Error - Unknown mode.")
             return None, None
             
        return baseline_win, response_win

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        # Gather the specific Rin result details for saving.
        # Uses the stored _last_rin_result from _trigger_rin_analysis.
        
        # Check if a valid result was calculated and stored
        if not self._last_rin_result:
            log.debug("_get_specific_result_data: No valid Rin calculation result available.")
            return None
            
        try:
            # Unpack all stored components
            rin_value, dv_val, di_val, di_source = self._last_rin_result
        except (TypeError, ValueError) as e:
             log.error(f"Could not unpack stored Rin result: {self._last_rin_result}. Error: {e}")
             return None

        channel_id = self.voltage_channel_combobox.currentData()
        # Robust way to get channel name without crashing if format changes
        current_text = self.voltage_channel_combobox.currentText()
        channel_name = current_text.split(' (')[0] if ' (' in current_text else current_text
        
        data_source = self.data_source_combobox.currentData()

        if channel_id is None or data_source is None:
            log.warning("_get_specific_result_data: Missing channel_id or data_source.") 
            return None

        # Get windows used for the calculation (read from current UI state)
        baseline_win, response_win = self._get_analysis_windows()
        if baseline_win is None or response_win is None:
             log.warning("_get_specific_result_data: Could not retrieve valid analysis windows.")
             # Should we still save without windows? Probably not.
             return None 

        # Get current mode from combobox
        analysis_mode = self.mode_combobox.currentText() if self.mode_combobox else "Unknown"

        specific_data = {
            'result_value': rin_value,
            'result_units': "MΩ",
            'delta_V_mV': dv_val,
            'delta_I_pA': di_val, # Use the delta I value that was actually used
            'delta_I_source': di_source, # Indicate source (manual or calculated)
            'channel_id': channel_id,
            'channel_name': channel_name,
            'data_source': data_source,
            'baseline_start_s': baseline_win[0],
            'baseline_end_s': baseline_win[1],
            'response_start_s': response_win[0],
            'response_end_s': response_win[1],
            'analysis_mode': analysis_mode, # Use text from combobox
            'manual_delta_i_pa': di_val if not np.isclose(di_val or 0.0, 0.0) else None, # Include manual value if set
        }
        log.debug(f"_get_specific_result_data (Rin) returning: {specific_data}")
        return specific_data

    def cleanup(self):
        if self.plot_widget: self.plot_widget.clear()
        super().cleanup()

    # --- ADDED: Helper to update visualization lines --- 
    def _update_rin_visualization_lines(self, baseline_win, response_win, voltage_trace):
        """Update the position and visibility of baseline/response lines."""
        if not self.baseline_line or not self.response_line or not self._current_plot_data:
            return
        time_v = self._current_plot_data['time_v']
        try:
            bl_indices = np.where((time_v >= baseline_win[0]) & (time_v <= baseline_win[1]))[0]
            resp_indices = np.where((time_v >= response_win[0]) & (time_v <= response_win[1]))[0]
            if len(bl_indices) > 0 and len(resp_indices) > 0:
                mean_baseline_v = np.mean(voltage_trace[bl_indices])
                mean_response_v = np.mean(voltage_trace[resp_indices])
                self.baseline_line.setPos(mean_baseline_v)
                self.response_line.setPos(mean_response_v)
                self.baseline_line.setVisible(True)
                self.response_line.setVisible(True)
            else:
                self._clear_rin_visualization_lines()
        except Exception as e:
            log.warning(f"Error updating Rin visualization lines: {e}")
            self._clear_rin_visualization_lines()

    # --- ADDED: Helper to clear visualization lines --- 
    def _clear_rin_visualization_lines(self):
        if self.baseline_line: self.baseline_line.setVisible(False)
        if self.response_line: self.response_line.setVisible(False)

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = RinAnalysisTab 