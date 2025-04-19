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
        self.rin_channel_combo: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        # Mode
        self.analysis_mode_group: Optional[QtWidgets.QGroupBox] = None
        self.mode_button_group: Optional[QtWidgets.QButtonGroup] = None
        self.interactive_radio: Optional[QtWidgets.QRadioButton] = None
        self.manual_radio: Optional[QtWidgets.QRadioButton] = None
        # Manual Inputs
        self.manual_time_group: Optional[QtWidgets.QGroupBox] = None
        self.baseline_start_edit: Optional[QtWidgets.QLineEdit] = None
        self.baseline_end_edit: Optional[QtWidgets.QLineEdit] = None
        self.response_start_edit: Optional[QtWidgets.QLineEdit] = None
        self.response_end_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_delta_i_edit: Optional[QtWidgets.QLineEdit] = None # RE-ADDED
        # ADDED: Calculate Button
        self.calculate_button: Optional[QtWidgets.QPushButton] = None
        # Results
        self.result_label: Optional[QtWidgets.QLabel] = None # Shows Rin value
        # Plotting
        self.baseline_region: Optional[pg.LinearRegionItem] = None
        self.response_region: Optional[pg.LinearRegionItem] = None
        self.current_plot_item: Optional[pg.PlotDataItem] = None # To store ref to current plot
        self._current_plot_data: Optional[Dict[str, np.ndarray]] = None # Store all traces
        # REVISED: Store result as (rin, dV, dI, source) tuple
        self._last_rin_result: Optional[Tuple[float, float, float, str]] = None 


        self._setup_ui()
        self._connect_signals()
        self._on_mode_changed() # Set initial state

    def get_display_name(self) -> str:
        return "Input Resistance (Rin)"

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # --- Controls ---
        controls_group = QtWidgets.QGroupBox("Configuration")
        controls_layout = QtWidgets.QVBoxLayout(controls_group)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Item Selector (from base)
        item_selector_layout = QtWidgets.QFormLayout()
        self._setup_analysis_item_selector(item_selector_layout)
        controls_layout.addLayout(item_selector_layout)

        # Channel Selector
        channel_select_layout = QtWidgets.QHBoxLayout()
        channel_select_layout.addWidget(QtWidgets.QLabel("Target Channel:"))
        self.rin_channel_combo = QtWidgets.QComboBox()
        self.rin_channel_combo.setToolTip("Select the voltage channel containing the response.")
        self.rin_channel_combo.setEnabled(False)
        channel_select_layout.addWidget(self.rin_channel_combo, stretch=1)
        controls_layout.addLayout(channel_select_layout)

        # Data Source Selector
        data_source_layout = QtWidgets.QHBoxLayout()
        data_source_layout.addWidget(QtWidgets.QLabel("Data Source:"))
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)
        data_source_layout.addWidget(self.data_source_combobox, stretch=1)
        controls_layout.addLayout(data_source_layout)

        # Analysis Mode
        self.analysis_mode_group = QtWidgets.QGroupBox("Analysis Mode")
        mode_layout = QtWidgets.QHBoxLayout(self.analysis_mode_group)
        self.interactive_radio = QtWidgets.QRadioButton("Interactive Windows")
        self.manual_radio = QtWidgets.QRadioButton("Manual Time Entry")
        self.mode_button_group = QtWidgets.QButtonGroup(self)
        self.mode_button_group.addButton(self.interactive_radio, self.MODE_INTERACTIVE)
        self.mode_button_group.addButton(self.manual_radio, self.MODE_MANUAL)
        mode_layout.addWidget(self.interactive_radio)
        mode_layout.addWidget(self.manual_radio)
        self.interactive_radio.setChecked(True)
        self.analysis_mode_group.setEnabled(False)
        controls_layout.addWidget(self.analysis_mode_group)

        # Manual Time Inputs
        self.manual_time_group = QtWidgets.QGroupBox("Manual Time Windows")
        manual_layout = QtWidgets.QFormLayout(self.manual_time_group)
        # Use QLineEdit for flexibility, add validators later if needed
        self.baseline_start_edit = QtWidgets.QLineEdit("0.0")
        self.baseline_end_edit = QtWidgets.QLineEdit("0.1")
        self.response_start_edit = QtWidgets.QLineEdit("0.2")
        self.response_end_edit = QtWidgets.QLineEdit("0.3")
        manual_layout.addRow("Baseline Start (s):", self.baseline_start_edit)
        manual_layout.addRow("Baseline End (s):", self.baseline_end_edit)
        manual_layout.addRow("Response Start (s):", self.response_start_edit)
        manual_layout.addRow("Response End (s):", self.response_end_edit)
        self.manual_time_group.setEnabled(False)
        controls_layout.addWidget(self.manual_time_group)

        # --- RE-ADDED: Manual Delta I Input --- 
        manual_current_layout = QtWidgets.QFormLayout()
        self.manual_delta_i_edit = QtWidgets.QLineEdit()
        self.manual_delta_i_edit.setPlaceholderText("e.g., -100.0 (optional)")
        self.manual_delta_i_edit.setToolTip("Optionally enter current step ΔI (pA). If blank, ΔI will be calculated from current trace.")
        # Add validator for floating point numbers
        double_validator = QtGui.QDoubleValidator(-np.inf, np.inf, 4, self) # Allow negative/positive, 4 decimals
        double_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.manual_delta_i_edit.setValidator(double_validator)
        self.manual_delta_i_edit.setEnabled(False) # Initialize as disabled
        manual_current_layout.addRow("Manual ΔI (pA):", self.manual_delta_i_edit)
        controls_layout.addLayout(manual_current_layout) # Add below time group
        # --- END RE-ADDED ---

        # --- Calculate Button --- 
        self.calculate_button = QtWidgets.QPushButton("Calculate Rin")
        self.calculate_button.setEnabled(False) # Initially disabled
        # UPDATED tooltip to reflect new logic
        self.calculate_button.setToolTip("Calculate Rin using Manual ΔI (if provided) or Current trace.")

        # Add button centered below Manual Delta I group
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.calculate_button)
        button_layout.addStretch()
        controls_layout.addLayout(button_layout)

        # Results Display
        results_layout = QtWidgets.QHBoxLayout()
        results_layout.addWidget(QtWidgets.QLabel("Input Resistance (Rin):"))
        self.result_label = QtWidgets.QLabel("N/A")
        font = self.result_label.font(); font.setBold(True); self.result_label.setFont(font)
        results_layout.addWidget(self.result_label, stretch=1)
        controls_layout.addLayout(results_layout)

        # Save Button (from base)
        self._setup_save_button(controls_layout)

        controls_layout.addStretch()
        main_layout.addWidget(controls_group)

        # --- Plot Area ---
        self._setup_plot_area(main_layout, stretch_factor=1)
        # Setup second plot axis for current (will be done in plotting method)

        # Add region items
        self.baseline_region = pg.LinearRegionItem(values=[0.0, 0.1], orientation='vertical', brush=(0, 255, 0, 40), movable=True, bounds=None)
        self.response_region = pg.LinearRegionItem(values=[0.2, 0.3], orientation='vertical', brush=(0, 0, 255, 40), movable=True, bounds=None)
        self.baseline_region.setZValue(-10)
        self.response_region.setZValue(-10)
        self.plot_widget.addItem(self.baseline_region)
        self.plot_widget.addItem(self.response_region)

        self.setLayout(main_layout)
        log.debug("Rin Analysis Tab UI setup complete.")

    def _connect_signals(self):
        # Item selection handled by base class
        self.rin_channel_combo.currentIndexChanged.connect(self._plot_selected_trace)
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        self.mode_button_group.buttonClicked.connect(self._on_mode_changed)
        # Manual Time Edits (trigger only in manual mode)
        self.baseline_start_edit.editingFinished.connect(self._trigger_rin_analysis_if_manual)
        self.baseline_end_edit.editingFinished.connect(self._trigger_rin_analysis_if_manual)
        self.response_start_edit.editingFinished.connect(self._trigger_rin_analysis_if_manual)
        self.response_end_edit.editingFinished.connect(self._trigger_rin_analysis_if_manual)
        # Manual Delta I Edit (trigger always)
        self.manual_delta_i_edit.editingFinished.connect(self._trigger_rin_analysis)
        # Region Edits (trigger only in interactive mode)
        self.baseline_region.sigRegionChangeFinished.connect(self._trigger_rin_analysis_if_interactive)
        self.response_region.sigRegionChangeFinished.connect(self._trigger_rin_analysis_if_interactive)
        
        # Connect Calculate Button
        self.calculate_button.clicked.connect(self._trigger_rin_analysis)
        
        # Save button handled by base class

    def _update_ui_for_selected_item(self):
        """Update Rin tab UI for new analysis item."""
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None
        self.result_label.setText("N/A")
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
        self.rin_channel_combo.blockSignals(True)
        self.rin_channel_combo.clear()
        voltage_channels_found = False
        if self._selected_item_recording and self._selected_item_recording.channels:
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                 units_lower = getattr(channel, 'units', '').lower()
                 if 'v' in units_lower: # Look for voltage channels
                      display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{channel.units}]"
                      self.rin_channel_combo.addItem(display_name, userData=chan_id)
                      voltage_channels_found = True
            if voltage_channels_found:
                self.rin_channel_combo.setCurrentIndex(0)
            else:
                self.rin_channel_combo.addItem("No Voltage Channels")
        else:
            self.rin_channel_combo.addItem("Load Data Item")
        self.rin_channel_combo.setEnabled(voltage_channels_found)
        self.rin_channel_combo.blockSignals(False)

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

        # --- Enable/Disable Remaining Controls ---
        self.analysis_mode_group.setEnabled(can_analyze)
        self._on_mode_changed() # Update manual/interactive state

        # --- Plot Initial Trace ---
        if can_analyze:
            self._plot_selected_trace()
        else:
            if self.plot_widget: self.plot_widget.clear()

    def _plot_selected_trace(self):
        """Plots voltage and current for the selected channel/source."""
        # --- Reset UI State & Data --- 
        if self.plot_widget: self.plot_widget.clear()
        self.manual_delta_i_edit.setEnabled(False)
        self.calculate_button.setEnabled(False)
        self.result_label.setText("N/A")
        if self.save_button: self.save_button.setEnabled(False)
        self._current_plot_data = None # *** Start with None ***
        
        # --- Check prerequisites --- 
        if not self.plot_widget or not self.rin_channel_combo or not self.data_source_combobox or not self._selected_item_recording:
            return

        chan_id = self.rin_channel_combo.currentData()
        source_data = self.data_source_combobox.currentData()
        if not chan_id or source_data is None:
             self._current_plot_data = None; self.plot_widget.clear(); return

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
                # 1. Store voltage data if valid
                if time_v is not None and voltage is not None:
                     self._current_plot_data = {'time_v': time_v, 'voltage': voltage}
                     log.debug(f"Stored voltage data. Keys: {list(self._current_plot_data.keys())}")
                else:
                     log.warning(f"Failed to fetch valid voltage data for Ch {chan_id}, Source: {source_data}. Plotting and analysis aborted.")
                     # Ensure plot is clear and controls disabled if voltage fetch fails
                     self.plot_widget.clear()
                     self.manual_delta_i_edit.setEnabled(False)
                     self.calculate_button.setEnabled(False)
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

                    # Enable manual input now that voltage is plotted
                    self.manual_delta_i_edit.setEnabled(True)

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
                    # Ensure plot is empty if voltage failed
                    self.plot_widget.clearPlots()
                    self._current_plot_data = None 

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
            # Attempt to re-add regions even on error
            try:
                if self.baseline_region.scene() is None: self.plot_widget.addItem(self.baseline_region)
                if self.response_region.scene() is None: self.plot_widget.addItem(self.response_region)
            except Exception as add_err:
                log.error(f"Error re-adding regions after plot error: {add_err}")
            self._current_plot_data = None

        # INSTEAD: Enable calculate button if voltage plot succeeded
        # Manual dI also enabled based on voltage success
        if voltage is not None:
             self.calculate_button.setEnabled(True)
             # self.manual_delta_i_edit.setEnabled(True) # Moved earlier, enable right after voltage plots
        else:
             self.calculate_button.setEnabled(False)
             self.manual_delta_i_edit.setEnabled(False) # Ensure disabled if voltage fails
             # Ensure result is cleared if plot failed
             self.result_label.setText("N/A")
             if self.save_button: self.save_button.setEnabled(False)

    # --- Analysis Logic ---
    @QtCore.Slot()
    def _on_mode_changed(self):
        is_manual = self.mode_button_group.checkedId() == self.MODE_MANUAL
        self.manual_time_group.setEnabled(is_manual)
        self.baseline_region.setVisible(not is_manual)
        self.baseline_region.setMovable(not is_manual)
        self.response_region.setVisible(not is_manual)
        self.response_region.setMovable(not is_manual)
        log.debug(f"Rin analysis mode changed. Manual Mode: {is_manual}")
        self._trigger_rin_analysis()

    # Helper slots to trigger analysis only in the correct mode
    @QtCore.Slot()
    def _trigger_rin_analysis_if_manual(self):
        if self.mode_button_group.checkedId() == self.MODE_MANUAL:
            self._trigger_rin_analysis()
            
    @QtCore.Slot()
    def _trigger_rin_analysis_if_interactive(self):
         if self.mode_button_group.checkedId() == self.MODE_INTERACTIVE:
            self._trigger_rin_analysis()

    @QtCore.Slot()
    def _trigger_rin_analysis(self):
        # --- Log entry state ---
        log.debug(f"_trigger_rin_analysis called. self._current_plot_data keys: {list(self._current_plot_data.keys()) if self._current_plot_data else 'None'}")
        has_v_data = self._current_plot_data and 'voltage' in self._current_plot_data
        has_t_data = self._current_plot_data and 'time_v' in self._current_plot_data
        log.debug(f"  >> Has voltage key: {has_v_data}, Has time_v key: {has_t_data}")
        
        # --- Reset state ---
        self._last_rin_result = None 
        self.result_label.setText("Calculating...")
        if self.save_button: self.save_button.setEnabled(False)

        # --- 1. Check for Voltage Data --- 
        if not self._current_plot_data or \
           'voltage' not in self._current_plot_data or \
           'time_v' not in self._current_plot_data:
            log.debug("Skipping Rin analysis: Voltage data missing.")
            self.result_label.setText("Voltage Data Missing")
            return
            
        time_v = self._current_plot_data['time_v']
        voltage = self._current_plot_data['voltage']

        # --- 2. Determine Delta I --- 
        delta_i_to_use: Optional[float] = None
        delta_i_source: Optional[str] = None

        # 2a. Try Manual Delta I
        manual_delta_i_text = self.manual_delta_i_edit.text().strip()
        if manual_delta_i_text:
            try:
                manual_delta_i_pa = float(manual_delta_i_text)
                if not np.isclose(manual_delta_i_pa, 0.0):
                    delta_i_to_use = manual_delta_i_pa
                    delta_i_source = 'manual'
                    log.debug(f"Using Manual ΔI = {delta_i_to_use:.3f} pA")
                else:
                    log.warning("Manual ΔI is zero or close to zero, ignoring.")
            except ValueError:
                log.warning(f"Invalid Manual ΔI value: '{manual_delta_i_text}'. Ignoring.")
                # Optionally display a temporary warning in result_label?
                # self.result_label.setText("Invalid Manual ΔI") 
                # return # Or just ignore and try calculated?

        # 2b. Try Calculated Delta I (if manual wasn't used)
        if delta_i_to_use is None:
            log.debug("Manual ΔI not provided or invalid, attempting to calculate from current trace.")
            if 'current' in self._current_plot_data and 'time_i' in self._current_plot_data:
                time_i = self._current_plot_data['time_i']
                current = self._current_plot_data['current']
                
                # Need to get windows *before* calculating dI
                temp_baseline_win, temp_response_win = self._get_analysis_windows()
                if temp_baseline_win is None or temp_response_win is None: 
                     # Error getting windows, already handled in _get_analysis_windows
                     return # Stop calculation
                
                try:
                    # Calculate Mean Baseline Current
                    bl_indices_i = np.where((time_i >= temp_baseline_win[0]) & (time_i <= temp_baseline_win[1]))[0]
                    if len(bl_indices_i) == 0: raise ValueError("No current data in baseline window")
                    mean_baseline_i = np.mean(current[bl_indices_i])

                    # Calculate Mean Response Current
                    resp_indices_i = np.where((time_i >= temp_response_win[0]) & (time_i <= temp_response_win[1]))[0]
                    if len(resp_indices_i) == 0: raise ValueError("No current data in response window")
                    mean_response_i = np.mean(current[resp_indices_i])
                    
                    calculated_delta_i = mean_response_i - mean_baseline_i
                    log.debug(f"Calculated ΔI: Mean Baseline I={mean_baseline_i:.3f} pA, Mean Response I={mean_response_i:.3f} pA => ΔI={calculated_delta_i:.3f} pA")

                    if not np.isclose(calculated_delta_i, 0.0):
                        delta_i_to_use = calculated_delta_i
                        delta_i_source = 'calculated'
                        log.debug(f"Using Calculated ΔI = {delta_i_to_use:.3f} pA")
                    else:
                         log.warning("Calculated ΔI is zero or close to zero. Cannot use for Rin.")
                         # Keep delta_i_to_use as None
                except ValueError as e:
                    log.warning(f"Could not calculate ΔI from current trace: {e}")
                    # Keep delta_i_to_use as None
                except Exception as e:
                     log.error(f"Unexpected error calculating ΔI: {e}", exc_info=True)
                     # Keep delta_i_to_use as None
            else:
                log.debug("Current trace data not available for calculating ΔI.")

        # --- 3. Check if ΔI was determined --- 
        if delta_i_to_use is None:
            log.warning("Failed to determine a valid ΔI from manual input or current trace.")
            self.result_label.setText("Valid ΔI Required")
            # self.save_button remains disabled
            return

        # --- 4. Get Analysis Windows --- 
        baseline_win, response_win = self._get_analysis_windows()
        if baseline_win is None or response_win is None:
            # Error should have been displayed by _get_analysis_windows
            return

        # --- 5. Perform Calculation --- 
        log.debug(f"Running calculate_rin with dI={delta_i_to_use:.3f} pA (Source: {delta_i_source})")
        calc_result = calculate_rin(time_v, voltage, baseline_win, response_win, delta_i_to_use)

        # --- 6. Display Result --- 
        if calc_result is not None:
            rin_mohm, dV_mv = calc_result
            # Store the full result including the dI used and its source
            self._last_rin_result = (rin_mohm, dV_mv, delta_i_to_use, delta_i_source)
            # Update label to show source of ΔI
            source_tag = "Man." if delta_i_source == 'manual' else "Calc."
            self.result_label.setText(f"{rin_mohm:.2f} MΩ (ΔV={dV_mv:.2f}mV, {source_tag} ΔI={delta_i_to_use:.1f}pA)")
            log.info(f"Rin = {rin_mohm:.2f} MΩ (dV={dV_mv:.2f}mV, Source: {delta_i_source}, dI={delta_i_to_use:.1f}pA)")
            if self.save_button: self.save_button.setEnabled(True)
        else:
            # calculate_rin logs specific errors
            self.result_label.setText("Calculation Error") 
            log.warning("calculate_rin returned None.")
            # self.save_button remains disabled

    def _get_analysis_windows(self) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        """Gets baseline and response windows based on current mode.
           Updates UI elements (manual fields or regions) accordingly.
           Returns (None, None) if validation fails, setting result_label.
        """
        baseline_win, response_win = None, None
        if self.mode_button_group.checkedId() == self.MODE_INTERACTIVE:
            baseline_win = self.baseline_region.getRegion()
            response_win = self.response_region.getRegion()
            # Update manual fields from regions
            self.baseline_start_edit.setText(f"{baseline_win[0]:.4f}")
            self.baseline_end_edit.setText(f"{baseline_win[1]:.4f}")
            self.response_start_edit.setText(f"{response_win[0]:.4f}")
            self.response_end_edit.setText(f"{response_win[1]:.4f}")
            log.debug(f"Using Interactive Windows. BL: {baseline_win}, Resp: {response_win}")
        else: # Manual mode
            try:
                bl_s = float(self.baseline_start_edit.text())
                bl_e = float(self.baseline_end_edit.text())
                r_s = float(self.response_start_edit.text())
                r_e = float(self.response_end_edit.text())
                if bl_s >= bl_e or r_s >= r_e: raise ValueError("Start time must be less than end time.")
                baseline_win = (bl_s, bl_e)
                response_win = (r_s, r_e)
                # Update regions from manual fields
                self.baseline_region.setRegion(baseline_win)
                self.response_region.setRegion(response_win)
                log.debug(f"Using Manual Windows. BL: {baseline_win}, Resp: {response_win}")
            except (ValueError, TypeError) as e:
                log.warning(f"Manual time validation failed: {e}")
                self.result_label.setText("Invalid Time")
                if self.save_button: self.save_button.setEnabled(False)
                return None, None # Indicate failure
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

        channel_id = self.rin_channel_combo.currentData()
        # Robust way to get channel name without crashing if format changes
        current_text = self.rin_channel_combo.currentText()
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
            'analysis_mode': "Interactive" if self.mode_button_group.checkedId() == self.MODE_INTERACTIVE else "Manual"
        }
        log.debug(f"_get_specific_result_data (Rin) returning: {specific_data}")
        return specific_data

    def cleanup(self):
        if self.plot_widget: self.plot_widget.clear()
        super().cleanup()

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = RinAnalysisTab 