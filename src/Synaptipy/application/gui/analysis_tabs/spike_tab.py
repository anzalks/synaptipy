# src/Synaptipy/application/gui/analysis_tabs/spike_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting spikes using a simple threshold.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# Import base class using relative path within analysis_tabs package
from .base import BaseAnalysisTab
# Import needed core components using absolute paths
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.core.analysis import spike_analysis # Import the analysis function
from Synaptipy.infrastructure.file_readers import NeoAdapter # <<< ADDED

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.spike_tab')

class SpikeAnalysisTab(BaseAnalysisTab):
    """QWidget for Threshold-based Spike Detection."""

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__(neo_adapter=neo_adapter, parent=parent)

        # --- UI References specific to Spike ---
        # REMOVED: self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        # REMOVED: self.channel_scroll_area: Optional[QtWidgets.QScrollArea] = None
        # REMOVED: self.channel_checkbox_layout: Optional[QtWidgets.QVBoxLayout] = None
        # ADDED: Standard selectors
        self.channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        # Spike parameters
        self.threshold_edit: Optional[QtWidgets.QLineEdit] = None
        self.refractory_edit: Optional[QtWidgets.QLineEdit] = None
        # Action button
        self.detect_button: Optional[QtWidgets.QPushButton] = None # Renamed from run_button
        # Results display
        self.results_textedit: Optional[QtWidgets.QTextEdit] = None
        # ADDED: Plotting related
        self.plot_widget: Optional[pg.PlotWidget] = None
        self.voltage_plot_item: Optional[pg.PlotDataItem] = None
        self.spike_markers_item: Optional[pg.ScatterPlotItem] = None
        self._current_plot_data: Optional[Dict[str, Any]] = None # To store time, voltage, spikes
        # Keep internal list of items to analyse (inherited from BaseAnalysisTab)
        # REMOVED: self._analysis_items_for_spike: List[Dict[str, Any]] = [] # Use inherited _analysis_items
        # REMOVED: self._current_recording_for_ui: Optional[Recording] = None # Use inherited _selected_item_recording


        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent AnalyserTab calling update_state()

    def get_display_name(self) -> str:
        return "Spike Detection (Threshold)"

    def _setup_ui(self):
        """Create UI elements for Spike analysis."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # --- Top Horizontal Section ---
        top_section_layout = QtWidgets.QHBoxLayout()
        top_section_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Left: Controls Group ---
        self.controls_group = QtWidgets.QGroupBox("Configuration")
        # Limit width and vertical expansion
        self.controls_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        controls_layout = QtWidgets.QVBoxLayout(self.controls_group)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Analysis Item Selector (inherited)
        item_selector_layout = QtWidgets.QFormLayout()
        self._setup_analysis_item_selector(item_selector_layout)
        controls_layout.addLayout(item_selector_layout)

        # Channel/Data Source
        channel_layout = QtWidgets.QFormLayout()
        self.channel_combobox = QtWidgets.QComboBox()
        self.channel_combobox.setToolTip("Select the voltage channel to analyze.")
        self.channel_combobox.setEnabled(False)
        channel_layout.addRow("Voltage Channel:", self.channel_combobox)

        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)
        channel_layout.addRow("Data Source:", self.data_source_combobox)
        controls_layout.addLayout(channel_layout)

        # Threshold Input
        threshold_layout = QtWidgets.QFormLayout()
        self.threshold_edit = QtWidgets.QLineEdit("0.0")
        self.threshold_edit.setValidator(QtGui.QDoubleValidator())
        self.threshold_edit.setToolTip("Voltage threshold for spike detection.")
        self.threshold_edit.setEnabled(False)
        threshold_layout.addRow("Threshold (mV):", self.threshold_edit)
        controls_layout.addLayout(threshold_layout)

        # Run Button
        self.detect_button = QtWidgets.QPushButton("Detect Spikes")
        self.detect_button.setEnabled(False)
        self.detect_button.setToolTip("Detect spikes on the currently plotted trace using specified parameters.")
        controls_layout.addWidget(self.detect_button)

        controls_layout.addStretch(1)
        top_section_layout.addWidget(self.controls_group) # Add controls to left

        # --- Right: Results Group ---
        self.results_group = QtWidgets.QGroupBox("Results")
        self.results_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Maximum)
        results_layout = QtWidgets.QVBoxLayout(self.results_group)
        self.results_textedit = QtWidgets.QTextEdit()
        self.results_textedit.setReadOnly(True)
        self.results_textedit.setFixedHeight(80) # Make it smaller
        self.results_textedit.setPlaceholderText("Spike counts and rates will appear here...")
        results_layout.addWidget(self.results_textedit)
        self._setup_save_button(results_layout) # Add save button here
        results_layout.addStretch(1)
        top_section_layout.addWidget(self.results_group) # Add results to right

        # Add top section to main layout
        main_layout.addLayout(top_section_layout)

        # --- Bottom: Plot Area ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self._setup_plot_area(plot_layout)
        main_layout.addWidget(plot_container, stretch=1)

        # --- Plot items specific to Spikes ---
        self.spike_markers_item = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 150)) # Red markers
        self.threshold_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
        self.plot_widget.addItem(self.spike_markers_item)
        self.plot_widget.addItem(self.threshold_line)
        self.spike_markers_item.setVisible(False) # Initially hidden
        self.threshold_line.setVisible(False)   # Initially hidden

        self.setLayout(main_layout)

    def _connect_signals(self):
        """Connect signals specific to Spike tab widgets."""
        # Connect signals specific to Spike tab widgets.
        # Item selection handled by base class (_on_analysis_item_selected)
        self.channel_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        # Connect param edits to update run button state? Or just read on click?
        # Let's update state on click for now. Requires _validate_params check.
        # self.threshold_edit.textChanged.connect(self._update_detect_button_state)
        # self.refractory_edit.textChanged.connect(self._update_detect_button_state)
        # Connect detect button
        self.detect_button.clicked.connect(self._run_spike_analysis)
        # Channel checkboxes removed

    # --- Overridden Methods from Base ---
    def _update_ui_for_selected_item(self):
        """Update Spike tab UI for new analysis item."""
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None # Clear previous plot data
        self.results_textedit.setText("") # Clear previous results
        if self.detect_button: self.detect_button.setEnabled(False)
        if self.save_button: self.save_button.setEnabled(False) # Base class save button

        # --- Populate Channel ComboBox --- (Similar to rmp_tab)
        self.channel_combobox.blockSignals(True)
        self.channel_combobox.clear()
        voltage_channels_found = False
        if self._selected_item_recording and self._selected_item_recording.channels:
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                 units_lower = getattr(channel, 'units', '').lower()
                 if 'v' in units_lower: # Look for voltage channels
                      display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{channel.units}]"
                      self.channel_combobox.addItem(display_name, userData=chan_id)
                      voltage_channels_found = True
            if voltage_channels_found:
                self.channel_combobox.setCurrentIndex(0)
            else:
                self.channel_combobox.addItem("No Voltage Channels")
        else:
            self.channel_combobox.addItem("Load Data Item")
        self.channel_combobox.setEnabled(voltage_channels_found)
        self.channel_combobox.blockSignals(False)

        # --- Populate Data Source ComboBox --- (Similar to rmp_tab)
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
        self.threshold_edit.setEnabled(can_analyze)
        self.detect_button.setEnabled(can_analyze)

        # --- Plot Initial Trace --- 
        if can_analyze:
            self._plot_selected_trace()
        else:
            if self.plot_widget: self.plot_widget.clear() # Ensure plot is clear
            self.threshold_edit.setEnabled(False)
            self.detect_button.setEnabled(False)

    # --- Plotting Method --- 
    def _plot_selected_trace(self):
        """Plots the selected voltage trace and clears previous spikes."""
        # Basic checks
        if not self.plot_widget or not self.channel_combobox or not self.data_source_combobox or not self._selected_item_recording:
            if self.plot_widget: self.plot_widget.clearPlots()
            self._current_plot_data = None
            self.detect_button.setEnabled(False)
            return

        chan_id = self.channel_combobox.currentData()
        source_data = self.data_source_combobox.currentData()
        if not chan_id or source_data is None:
             if self.plot_widget: self.plot_widget.clearPlots()
             self._current_plot_data = None
             self.detect_button.setEnabled(False)
             return

        channel = self._selected_item_recording.channels.get(chan_id)
        log.debug(f"Spike Plotting: Ch {chan_id}, Source: {source_data}")

        time_vec, voltage_vec = None, None
        data_label = "Trace Error"
        plot_succeeded = False

        # Clear previous plot items
        self.plot_widget.clearPlots()
        self._current_plot_data = None
        self.spike_markers_item.setData([]) # Clear spike markers
        self.spike_markers_item.setVisible(False)
        self.threshold_line.setVisible(False)

        try:
            if channel:
                # Fetch Data (similar to rmp_tab)
                if source_data == "average":
                    voltage_vec = channel.get_averaged_data()
                    time_vec = channel.get_relative_averaged_time_vector()
                    data_label = f"{channel.name or chan_id} (Average)"
                elif isinstance(source_data, int):
                    trial_index = source_data
                    if 0 <= trial_index < channel.num_trials:
                        voltage_vec = channel.get_data(trial_index)
                        time_vec = channel.get_relative_time_vector(trial_index)
                        data_label = f"{channel.name or chan_id} (Trial {trial_index + 1})"

            # Plotting
            if time_vec is not None and voltage_vec is not None:
                self.voltage_plot_item = self.plot_widget.plot(time_vec, voltage_vec, pen='k', name=data_label)
                self.plot_widget.setLabel('left', 'Voltage', units=channel.units or 'V')
                self.plot_widget.setLabel('bottom', 'Time', units='s')
                self.plot_widget.setTitle(data_label)
                # Store data needed for analysis
                self._current_plot_data = {
                    'time': time_vec,
                    'voltage': voltage_vec,
                    'rate': channel.sampling_rate,
                    'units': channel.units or 'V'
                }
                plot_succeeded = True
                log.debug("Spike Plotting: Success")
            else:
                log.warning(f"Spike Plotting: No valid data for Ch {chan_id}, Source: {source_data}")
                self.plot_widget.setTitle("Plot Error: No Data")

            # Re-add spike markers item (clearPlots removes it)
            self.plot_widget.addItem(self.spike_markers_item) 

        except Exception as e:
            log.error(f"Spike Plotting Error: Ch {chan_id}: {e}", exc_info=True)
            self.plot_widget.clear()
            self.plot_widget.addItem(self.spike_markers_item) # Ensure markers item is present even on error
            self.plot_widget.setTitle("Plot Error")
            self._current_plot_data = None
            plot_succeeded = False

        # Update button state based on plot success
        self.detect_button.setEnabled(plot_succeeded)
        # Clear results text whenever plot changes
        self.results_textedit.clear()
        if self.save_button: self.save_button.setEnabled(False) # Disable save if plot changed

    # --- Private Helper Methods specific to Spike Tab ---
    def _validate_params(self) -> bool:
        """Validates Spike Detection parameters."""
        try:
            float(self.threshold_edit.text()) # Check if threshold is a valid float
            r=float(self.refractory_edit.text())
            return r>=0 # Refractory must be non-negative
        except (ValueError, TypeError):
            return False

    @QtCore.Slot()
    def _run_spike_analysis(self):
        """Runs Spike Detection analysis on the currently plotted trace."""
        log.debug("Run Spike Analysis clicked.")
        
        # 1. Check if data is plotted
        if not self._current_plot_data:
            log.warning("Cannot run spike analysis: No data plotted.")
            self.results_textedit.setText("Plot data first.")
            return
            
        # 2. Validate parameters
        if not self._validate_params():
            log.warning("Invalid spike detection parameters.")
            QtWidgets.QMessageBox.warning(self, "Invalid Parameters", "Threshold and Refractory period must be valid numbers (Refractory >= 0).")
            return
            
        threshold = float(self.threshold_edit.text())
        refractory_ms = float(self.refractory_edit.text())
        refractory_s = refractory_ms / 1000.0
        
        voltage = self._current_plot_data.get('voltage')
        time = self._current_plot_data.get('time')
        rate = self._current_plot_data.get('rate')
        units = self._current_plot_data.get('units', 'V')
        
        if voltage is None or time is None or rate is None or rate <= 0:
            log.error("Cannot run spike analysis: Missing voltage, time, or valid rate in plotted data.")
            self.results_textedit.setText("Error: Invalid plotted data.")
            return
            
        # Add threshold line to plot? (Optional)
        # Could add/update a pg.InfiniteLineItem here
            
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        self.results_textedit.clear()
        self.spike_markers_item.setData([]) # Clear previous markers
        self.spike_markers_item.setVisible(False)
        self.threshold_line.setVisible(True)
        run_successful = False
        spike_indices = None
        spike_times = None
        results_str = f"--- Spike Detection Results ---\nThreshold: {threshold:.3f} {units}\nRefractory: {refractory_ms:.2f} ms\n\n"
        
        try:
            # 3. Call the detection function (adjust function name/args as needed)
            log.info(f"Running spike detection: Threshold={threshold:.3f}, Refractory={refractory_s:.4f}s")
            # CORRECTED: Pass arguments positionally according to function definition
            # detect_spikes_threshold(data, time, threshold, refractory_samples)
            refractory_period_samples = int(refractory_s * rate)
            spike_indices, spike_times_from_func = spike_analysis.detect_spikes_threshold(
                voltage,            # data
                time,               # time
                threshold,          # threshold
                refractory_period_samples # refractory_samples
            )
            
            if spike_indices is None: # Function might return None on error
                raise ValueError("Spike detection function returned None")
                
            num_spikes = len(spike_indices)
            log.info(f"Detected {num_spikes} spikes.")
            
            # 4. Process and Display Results
            if num_spikes > 0:
                spike_times = time[spike_indices] # Get actual times
                duration = time[-1] - time[0]
                avg_rate = num_spikes / duration if duration > 0 else 0
                results_str += f"Number of Spikes: {num_spikes}\n"
                results_str += f"Average Firing Rate: {avg_rate:.2f} Hz\n"
                # Store results for saving and plotting
                self._current_plot_data['spike_indices'] = spike_indices
                self._current_plot_data['spike_times'] = spike_times
                
                # 5. Update Plot Markers
                # Plot markers at the threshold crossing time, using threshold as Y
                # Or, if detection function returns peaks, plot at peaks.
                self.spike_markers_item.setData(x=spike_times, y=voltage[spike_indices]) # Plot at detected point Y value
                self.spike_markers_item.setVisible(True)
                
            else:
                results_str += "Number of Spikes: 0\n"
                self._current_plot_data['spike_indices'] = np.array([])
                self._current_plot_data['spike_times'] = np.array([])
            
            run_successful = True
            
        except AttributeError as ae:
             log.error(f"Spike detection function not found or attribute error: {ae}. Is 'spike_analysis.detect_spikes_threshold' correct?", exc_info=True)
             results_str += "Error: Spike detection function not found."
             self.results_textedit.setText(results_str)
        except Exception as e:
            log.error(f"Error during spike detection: {e}", exc_info=True)
            results_str += f"Error during analysis: {e}"
            self.results_textedit.setText(results_str)
            
        finally:
            self.results_textedit.setText(results_str)
            QtWidgets.QApplication.restoreOverrideCursor()
            # Enable save button only if spikes were detected successfully?
            if self.save_button: self.save_button.setEnabled(run_successful)

    # --- Base Class Method Implementation --- 
    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        # Gathers the specific Spike analysis details for saving.
        
        # 1. Check if analysis was run and results exist
        if not self._current_plot_data or 'spike_times' not in self._current_plot_data:
            log.debug("_get_specific_result_data (Spike): No spike analysis results available.")
            return None
            
        spike_times = self._current_plot_data.get('spike_times')
        spike_indices = self._current_plot_data.get('spike_indices')
        voltage = self._current_plot_data.get('voltage') # Needed for peak values
        
        # Check if spike_times is valid (e.g., a non-empty numpy array)
        if spike_times is None or not isinstance(spike_times, np.ndarray) or spike_times.size == 0:
             log.debug(f"_get_specific_result_data (Spike): spike_times is invalid or empty ({type(spike_times)}).")
             # Allow saving even if 0 spikes were detected, just need parameters
             # return None 
             pass # Continue to save parameters even if no spikes

        # 2. Get parameters used for the analysis
        try:
            threshold = float(self.threshold_edit.text())
            refractory_ms = float(self.refractory_edit.text())
        except (ValueError, TypeError):
            log.error("_get_specific_result_data (Spike): Could not read parameters from UI for saving.")
            return None # Cannot save without valid parameters

        # 3. Get data source information
        channel_id = self.channel_combobox.currentData()
        channel_name = self.channel_combobox.currentText().split(' (')[0] # Extract name before ID
        data_source = self.data_source_combobox.currentData() # "average" or trial index (int)
        data_source_text = self.data_source_combobox.currentText()

        if channel_id is None or data_source is None:
            log.warning("Cannot get specific Spike data: Missing channel or data source selection.")
            return None
            
        # 4. Gather results
        num_spikes = len(spike_times) if spike_times is not None else 0
        avg_rate = 0.0
        spike_peak_values = []
        if num_spikes > 0 and voltage is not None and spike_indices is not None:
             time_full = self._current_plot_data.get('time')
             if time_full is not None and time_full.size > 1:
                 duration = time_full[-1] - time_full[0]
                 avg_rate = num_spikes / duration if duration > 0 else 0
             # Get peak voltage values using the indices
             try:
                 spike_peak_values = voltage[spike_indices].tolist()
             except IndexError:
                  log.warning("Spike indices out of bounds for voltage array when getting peaks.")
                  spike_peak_values = [] # Set empty if indices are bad
        
        specific_data = {
            # Analysis Parameters
            'threshold': threshold,
            'threshold_units': self._current_plot_data.get('units', 'unknown'),
            'refractory_period_ms': refractory_ms,
            # Results
            'spike_count': num_spikes,
            'average_firing_rate_hz': avg_rate,
            'spike_times_s': spike_times.tolist() if spike_times is not None else [],
            'spike_peak_values': spike_peak_values, # Add peak values
            # Data Source Info (for base class)
            'channel_id': channel_id,
            'channel_name': channel_name,
            'data_source': data_source, 
            'data_source_label': data_source_text # Add readable label
            # Note: Base class adds file path etc.
        }
        log.debug(f"_get_specific_result_data (Spike) returning: {specific_data}")
        return specific_data

# --- END CLASS SpikeAnalysisTab ---

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = SpikeAnalysisTab