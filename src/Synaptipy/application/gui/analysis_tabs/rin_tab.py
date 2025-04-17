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

# --- Rin Calculation Function (Example - Adapt if imported) ---
def calculate_rin(
    time_v: np.ndarray, voltage: np.ndarray,
    time_i: np.ndarray, current: np.ndarray,
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float]
) -> Optional[Tuple[float, float, float]]: # Return Rin, dV, dI
    """
    Calculates Input Resistance (Rin) from voltage and current traces using defined windows.

    Args:
        time_v: Time vector for voltage trace.
        voltage: Voltage trace.
        time_i: Time vector for current trace.
        current: Current trace.
        baseline_window: (start_time, end_time) for baseline measurement.
        response_window: (start_time, end_time) for steady-state response measurement.

    Returns:
        Tuple of (Rin in MOhms, delta_V in mV, delta_I in pA) or None on error.
    """
    if time_v is None or voltage is None or time_i is None or current is None:
        log.warning("Rin calc: Missing voltage or current data.")
        return None
    if not baseline_window or baseline_window[0] >= baseline_window[1]:
        log.warning("Rin calc: Invalid baseline window.")
        return None
    if not response_window or response_window[0] >= response_window[1]:
        log.warning("Rin calc: Invalid response window.")
        return None

    try:
        # Find indices for baseline window (use voltage time vector)
        bl_indices = np.where((time_v >= baseline_window[0]) & (time_v <= baseline_window[1]))[0]
        if len(bl_indices) == 0:
            log.warning(f"Rin calc: No baseline data points found in window {baseline_window}")
            return None
        # Find indices for response window (use voltage time vector)
        resp_indices = np.where((time_v >= response_window[0]) & (time_v <= response_window[1]))[0]
        if len(resp_indices) == 0:
            log.warning(f"Rin calc: No response data points found in window {response_window}")
            return None

        # Find corresponding indices for current trace (assuming same time base or interpolate if needed)
        # Simple approach: assume same time base for now
        # A robust solution might need interpolation if time_v != time_i
        bl_indices_i = np.where((time_i >= baseline_window[0]) & (time_i <= baseline_window[1]))[0]
        resp_indices_i = np.where((time_i >= response_window[0]) & (time_i <= response_window[1]))[0]
        if len(bl_indices_i) == 0 or len(resp_indices_i) == 0:
             log.warning("Rin calc: Could not find corresponding current data points for windows.")
             # Fallback: Use the known delta_I if provided? For now, return None.
             return None

        # Calculate means
        baseline_v_mean = np.mean(voltage[bl_indices])
        response_v_mean = np.mean(voltage[resp_indices])
        baseline_i_mean = np.mean(current[bl_indices_i])
        response_i_mean = np.mean(current[resp_indices_i])

        delta_v = response_v_mean - baseline_v_mean
        delta_i = response_i_mean - baseline_i_mean

        # Convert delta_v to mV (assuming V input) and delta_i to pA (assuming A input) for Rin calculation
        # Adjust these factors based on actual units!
        delta_v_mv = delta_v * 1000.0
        delta_i_pa = delta_i * 1e12

        if abs(delta_i_pa) < 1e-3: # Avoid division by zero or near-zero
            log.warning("Rin calc: Delta current is too small.")
            return None

        # Rin = dV (mV) / dI (nA) = (dV * 1000) / (dI * 1e9) = dV / dI * 1e-6 -> MOhm
        # Rin = dV (mV) / dI (pA) = (dV * 1000) / (dI * 1e12) = dV / dI * 1e-9 -> GOhm
        # Let's calculate in GOhms first, then convert to MOhms
        rin_gohm = delta_v_mv / (delta_i_pa * 1e-3) # dV(mV) / dI(nA)
        rin_mohm = rin_gohm * 1000.0

        return rin_mohm, delta_v_mv, delta_i_pa

    except Exception as e:
        log.error(f"Error during Rin calculation: {e}", exc_info=True)
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
        # Results
        self.result_label: Optional[QtWidgets.QLabel] = None # Shows Rin value
        # Plotting
        self.baseline_region: Optional[pg.LinearRegionItem] = None
        self.response_region: Optional[pg.LinearRegionItem] = None
        self.current_plot_item: Optional[pg.PlotDataItem] = None # To store ref to current plot
        self._current_plot_data: Optional[Dict[str, np.ndarray]] = None # Store all traces


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
        # Manual Edits
        self.baseline_start_edit.editingFinished.connect(self._trigger_rin_analysis_from_manual)
        self.baseline_end_edit.editingFinished.connect(self._trigger_rin_analysis_from_manual)
        self.response_start_edit.editingFinished.connect(self._trigger_rin_analysis_from_manual)
        self.response_end_edit.editingFinished.connect(self._trigger_rin_analysis_from_manual)
        # Region Edits
        self.baseline_region.sigRegionChangeFinished.connect(self._trigger_rin_analysis_from_region)
        self.response_region.sigRegionChangeFinished.connect(self._trigger_rin_analysis_from_region)
        # Save button handled by base class

    def _update_ui_for_selected_item(self):
        """Update Rin tab UI for new analysis item."""
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None
        self.result_label.setText("N/A")
        if self.save_button: self.save_button.setEnabled(False)

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
        if not self.plot_widget or not self.rin_channel_combo or not self.data_source_combobox or not self._selected_item_recording:
            self._current_plot_data = None
            if self.plot_widget: self.plot_widget.clear()
            return

        chan_id = self.rin_channel_combo.currentData()
        source_data = self.data_source_combobox.currentData()
        if not chan_id or source_data is None:
             self._current_plot_data = None; self.plot_widget.clear(); return

        channel = self._selected_item_recording.channels.get(chan_id)
        log.debug(f"Plotting Rin trace for Ch {chan_id}, Data Source: {source_data}")

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

                # Fetch Current Data (NEEDS ADAPTATION based on actual Channel methods)
                # Placeholder - assuming a similar method exists for current
                # --- CURRENT FETCHING DISABLED - NEEDS IMPLEMENTATION --- 
                # log.warning("Current trace fetching is currently disabled.")
                current = None
                time_i = None
                i_label = "Current N/A"
                # --- END DISABLED BLOCK ---


                # --- Plotting ---
                self.plot_widget.clearPlots() # Use clearPlots to keep axes, regions etc.
                # Detach regions before clearing viewboxes in case they are linked internally
                if self.baseline_region.getViewBox(): self.baseline_region.getViewBox().removeItem(self.baseline_region)
                if self.response_region.getViewBox(): self.response_region.getViewBox().removeItem(self.response_region)

                self._current_plot_data = None # Reset stored data

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
                    self._current_plot_data = {'time_v': time_v, 'voltage': voltage}

                    # Add current trace if available
                    if time_i is not None and current is not None:
                        self._current_plot_data['time_i'] = time_i
                        self._current_plot_data['current'] = current

                        # Create secondary Y axis for current
                        # --- CURRENT PLOTTING DISABLED --- 
                        # p1 = self.plot_widget.getPlotItem()
                        # p1.showAxis('right')
                        # vb = p1.getViewBox()
                        # # ... (rest of viewbox/plotting code removed) ...
                        # self.current_plot_item = pg.PlotDataItem(time_i, current, pen='r', name=i_label)
                        # vb2.addItem(self.current_plot_item)
                        # p1.getAxis('right').setLabel('Current', units='A') # Placeholder units
                        pass # Keep structure

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

        self._trigger_rin_analysis()

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

    @QtCore.Slot()
    def _trigger_rin_analysis_from_manual(self):
        if self.mode_button_group.checkedId() == self.MODE_MANUAL:
            log.debug("Rin manual time edit finished, triggering analysis.")
            self._trigger_rin_analysis()

    @QtCore.Slot()
    def _trigger_rin_analysis_from_region(self):
        if self.mode_button_group.checkedId() == self.MODE_INTERACTIVE:
            log.debug("Rin interactive region change finished, triggering analysis.")
            self._trigger_rin_analysis()

    def _trigger_rin_analysis(self):
        """Get parameters and run Rin calculation."""
        # Check if basic voltage data is available
        if not self._current_plot_data or 'voltage' not in self._current_plot_data:
             log.debug("Skipping Rin analysis: No voltage data plotted.")
             self.result_label.setText("N/A")
             if self.save_button: self.save_button.setEnabled(False)
             return

        # Check if current data is available (it won't be if fetching is disabled)
        if 'time_i' not in self._current_plot_data or 'current' not in self._current_plot_data:
            log.warning("Skipping Rin calculation: Current data is missing.")
            self.result_label.setText("N/A (Current Missing)")
            if self.save_button: self.save_button.setEnabled(False)
            return # Don't proceed with calculation

        # If we reach here, both voltage and current data *should* be present
        time_v = self._current_plot_data['time_v']
        voltage = self._current_plot_data['voltage']
        time_i = self._current_plot_data['time_i'] # Now safe to access
        current = self._current_plot_data['current'] # Now safe to access
        baseline_win, response_win = None, None

        if self.mode_button_group.checkedId() == self.MODE_INTERACTIVE:
            baseline_win = self.baseline_region.getRegion()
            response_win = self.response_region.getRegion()
            # Update manual fields
            self.baseline_start_edit.setText(f"{baseline_win[0]:.4f}")
            self.baseline_end_edit.setText(f"{baseline_win[1]:.4f}")
            self.response_start_edit.setText(f"{response_win[0]:.4f}")
            self.response_end_edit.setText(f"{response_win[1]:.4f}")
            log.debug(f"Running Rin (Interactive). BL: {baseline_win}, Resp: {response_win}")
        else: # Manual mode
            try:
                bl_s = float(self.baseline_start_edit.text())
                bl_e = float(self.baseline_end_edit.text())
                r_s = float(self.response_start_edit.text())
                r_e = float(self.response_end_edit.text())
                if bl_s >= bl_e or r_s >= r_e: raise ValueError("Start time must be less than end time.")
                baseline_win = (bl_s, bl_e)
                response_win = (r_s, r_e)
                # Update regions
                self.baseline_region.setRegion(baseline_win)
                self.response_region.setRegion(response_win)
                log.debug(f"Running Rin (Manual). BL: {baseline_win}, Resp: {response_win}")
            except (ValueError, TypeError) as e:
                log.warning(f"Manual time validation failed: {e}")
                self.result_label.setText("Invalid Time")
                if self.save_button: self.save_button.setEnabled(False)
                return

        # --- Perform Calculation --- 
        # This part only runs if current data was found earlier
        calc_result = calculate_rin(time_v, voltage, time_i, current, baseline_win, response_win)

        # --- Display Result ---
        if calc_result is not None:
            rin_mohm, dV_mv, dI_pa = calc_result
            self.result_label.setText(f"{rin_mohm:.2f} MΩ (ΔV={dV_mv:.2f}mV, ΔI={dI_pa:.1f}pA)")
            log.info(f"Calculated Rin = {rin_mohm:.2f} MΩ")
            if self.save_button: self.save_button.setEnabled(True)
        else:
            self.result_label.setText("Error")
            log.warning("Rin calculation returned None.")
            if self.save_button: self.save_button.setEnabled(False)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Gathers the specific Rin result details for saving."""
        if not self.result_label or self.result_label.text() in ["N/A", "Error", "Invalid Time"]:
            log.debug("_get_specific_result_data: No valid Rin result.")
            return None

        result_text = self.result_label.text()
        try: # Example: "123.45 MΩ (ΔV=10.50mV, ΔI=-100.0pA)"
            rin_part = result_text.split(" MΩ")[0]
            rin_value = float(rin_part)
            # Optional: Parse dV and dI if needed for saving, requires robust parsing
            dv_val, di_val = None, None
            if "(ΔV=" in result_text and "mV," in result_text:
                 dv_str = result_text.split("(ΔV=")[1].split("mV,")[0]
                 dv_val = float(dv_str)
            if "ΔI=" in result_text and "pA)" in result_text:
                 di_str = result_text.split("ΔI=")[1].split("pA)")[0]
                 di_val = float(di_str)

        except Exception as e:
            log.error(f"Could not parse Rin result from label '{result_text}': {e}")
            return None

        channel_id = self.rin_channel_combo.currentData()
        channel_name = self.rin_channel_combo.currentText().split(' (')[0]
        data_source = self.data_source_combobox.currentData()

        if channel_id is None or data_source is None: return None

        baseline_win = self.baseline_region.getRegion()
        response_win = self.response_region.getRegion()

        specific_data = {
            'result_value': rin_value,
            'result_units': "MΩ",
            'delta_V_mV': dv_val,
            'delta_I_pA': di_val,
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