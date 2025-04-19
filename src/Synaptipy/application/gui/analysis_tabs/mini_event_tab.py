# src/Synaptipy/application/gui/analysis_tabs/mini_event_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting miniature synaptic events (e.g., mEPSCs, mIPSCs).
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .base import BaseAnalysisTab
from Synaptipy.core.data_model import Recording, Channel
# from Synaptipy.core.analysis import event_detection # Will be needed later
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.mini_event_tab')

class MiniEventAnalysisTab(BaseAnalysisTab):
    """QWidget for Miniature Synaptic Event Detection."""

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__(neo_adapter=neo_adapter, parent=parent)

        # --- UI References specific to Mini Event Detection ---
        self.channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        # Detection parameters
        self.threshold_edit: Optional[QtWidgets.QLineEdit] = None
        self.direction_combobox: Optional[QtWidgets.QComboBox] = None # Negative/Positive
        # Action button
        self.detect_button: Optional[QtWidgets.QPushButton] = None
        # Results display
        self.results_textedit: Optional[QtWidgets.QTextEdit] = None
        # Plotting related
        self.plot_widget: Optional[pg.PlotWidget] = None
        self.data_plot_item: Optional[pg.PlotDataItem] = None # Renamed from voltage_plot_item
        self.event_markers_item: Optional[pg.ScatterPlotItem] = None # Renamed from spike_markers_item
        self._current_plot_data: Optional[Dict[str, Any]] = None # Store time, data, events

        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent AnalyserTab calling update_state()

    def get_display_name(self) -> str:
        return "Miniature Event Detection"

    def _setup_ui(self):
        """Create UI elements for the Mini Event analysis tab."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # --- Top Controls Area ---
        controls_group = QtWidgets.QGroupBox("Configuration")
        controls_layout = QtWidgets.QVBoxLayout(controls_group)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # 1. Analysis Item Selector (Inherited)
        item_selector_layout = QtWidgets.QFormLayout()
        self._setup_analysis_item_selector(item_selector_layout)
        controls_layout.addLayout(item_selector_layout)

        # 2. Channel Selector (Current Channels)
        channel_select_layout = QtWidgets.QHBoxLayout()
        channel_select_layout.addWidget(QtWidgets.QLabel("Plot Channel:"))
        self.channel_combobox = QtWidgets.QComboBox()
        self.channel_combobox.setToolTip("Select the current channel to analyze.")
        self.channel_combobox.setEnabled(False)
        channel_select_layout.addWidget(self.channel_combobox, stretch=1)
        controls_layout.addLayout(channel_select_layout)

        # 3. Data Source Selector
        data_source_layout = QtWidgets.QHBoxLayout()
        data_source_layout.addWidget(QtWidgets.QLabel("Data Source:"))
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)
        data_source_layout.addWidget(self.data_source_combobox, stretch=1)
        controls_layout.addLayout(data_source_layout)

        # 4. Detection Parameters
        param_group = QtWidgets.QGroupBox("Detection Parameters")
        param_layout = QtWidgets.QFormLayout(param_group)
        # Threshold Input
        self.threshold_edit = QtWidgets.QLineEdit("5.0") # Default threshold (e.g., pA)
        self.threshold_edit.setValidator(QtGui.QDoubleValidator(0, 10000, 3)) # Only positive thresholds
        self.threshold_edit.setToolTip("Detection threshold (absolute value, in trace units like pA)")
        param_layout.addRow("Threshold:", self.threshold_edit)
        # Direction Input
        self.direction_combobox = QtWidgets.QComboBox()
        self.direction_combobox.addItems(["Negative (IPSCs/EPSPs)", "Positive (EPSCs/IPSPs)"])
        self.direction_combobox.setToolTip("Direction of events relative to baseline")
        param_layout.addRow("Direction:", self.direction_combobox)
        # Add more params later (e.g., min duration, rise time filter)
        controls_layout.addWidget(param_group)

        # 5. Action Button
        self.detect_button = QtWidgets.QPushButton("Detect Events")
        self.detect_button.setEnabled(False)
        self.detect_button.setToolTip("Detect events on the currently plotted trace.")
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.detect_button)
        button_layout.addStretch()
        controls_layout.addLayout(button_layout)

        # 6. Save Button (Using base class setup)
        self._setup_save_button(controls_layout) # Add the save button

        # 7. Results Display Area
        results_group = QtWidgets.QGroupBox("Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        self.results_textedit = QtWidgets.QTextEdit()
        self.results_textedit.setReadOnly(True)
        self.results_textedit.setFixedHeight(100) # Slightly taller
        self.results_textedit.setPlaceholderText("Event frequency and amplitude will appear here...")
        results_layout.addWidget(self.results_textedit)
        controls_layout.addWidget(results_group)

        controls_layout.addStretch(1) # Push controls up
        main_layout.addWidget(controls_group) # Add controls group to main layout

        # --- Plot Area ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout) # Base method adds self.plot_widget
        # Add scatter plot item for event markers
        self.event_markers_item = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(0, 0, 255, 150)) # Blue markers
        self.plot_widget.addItem(self.event_markers_item)
        self.event_markers_item.setVisible(False)

        # Add plot container to main layout
        main_layout.addWidget(plot_container, stretch=1)

        self.setLayout(main_layout)

    def _connect_signals(self):
        """Connect signals specific to Mini Event tab widgets."""
        # Item selection handled by base class (_on_analysis_item_selected)
        self.channel_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        # Connect detect button
        self.detect_button.clicked.connect(self._run_event_detection) # Changed method name
        # Parameters don't need explicit connection if read on click

    # --- Overridden Methods from Base ---
    def _update_ui_for_selected_item(self):
        """Update Mini Event tab UI for new analysis item."""
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None
        self.results_textedit.setText("")
        if self.detect_button: self.detect_button.setEnabled(False)
        if self.save_button: self.save_button.setEnabled(False)

        # --- Populate Channel ComboBox (Focus on Current Channels) ---
        self.channel_combobox.blockSignals(True)
        self.channel_combobox.clear()
        current_channels_found = False
        if self._selected_item_recording and self._selected_item_recording.channels:
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                 units_lower = getattr(channel, 'units', '').lower()
                 # Look for current channels (units contain 'a' or 'amp')
                 if 'a' in units_lower or 'amp' in units_lower:
                      display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{channel.units}]"
                      self.channel_combobox.addItem(display_name, userData=chan_id)
                      current_channels_found = True
            if current_channels_found:
                self.channel_combobox.setCurrentIndex(0)
            else:
                self.channel_combobox.addItem("No Current Channels")
        else:
            self.channel_combobox.addItem("Load Data Item")
        self.channel_combobox.setEnabled(current_channels_found)
        self.channel_combobox.blockSignals(False)

        # --- Populate Data Source ComboBox --- (Identical logic to Spike Tab)
        self.data_source_combobox.blockSignals(True)
        self.data_source_combobox.clear()
        self.data_source_combobox.setEnabled(False)
        can_analyze = False
        if current_channels_found and self._selected_item_recording:
            selected_item_details = self._analysis_items[self._selected_item_index]
            item_type = selected_item_details.get('target_type')
            item_trial_index = selected_item_details.get('trial_index')
            num_trials = 0
            has_average = False
            first_channel = next(iter(self._selected_item_recording.channels.values()), None) # Any channel works here
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
        params_enabled = can_analyze and current_channels_found
        self.threshold_edit.setEnabled(params_enabled)
        self.direction_combobox.setEnabled(params_enabled)
        # Detect button enabled by plotting

        # --- Plot Initial Trace ---
        if can_analyze and current_channels_found:
            self._plot_selected_trace()
        else:
            if self.plot_widget: self.plot_widget.clear()
            self.detect_button.setEnabled(False)
            self.threshold_edit.setEnabled(False)
            self.direction_combobox.setEnabled(False)


    # --- Plotting Method ---
    def _plot_selected_trace(self):
        """Plots the selected current trace and clears previous events."""
        # Basic checks (Similar to Spike Tab)
        if not self.plot_widget or not self.channel_combobox or not self.data_source_combobox or not self._selected_item_recording:
            if self.plot_widget: self.plot_widget.clearPlots()
            self._current_plot_data = None
            if self.detect_button: self.detect_button.setEnabled(False)
            return

        chan_id = self.channel_combobox.currentData()
        source_data = self.data_source_combobox.currentData()
        if not chan_id or source_data is None:
             if self.plot_widget: self.plot_widget.clearPlots()
             self._current_plot_data = None
             if self.detect_button: self.detect_button.setEnabled(False)
             return

        channel = self._selected_item_recording.channels.get(chan_id)
        log.debug(f"Mini Event Plotting: Ch {chan_id}, Source: {source_data}")

        time_vec, data_vec = None, None
        data_label = "Trace Error"
        plot_succeeded = False

        # Clear previous plot items
        self.plot_widget.clearPlots()
        self._current_plot_data = None
        if self.event_markers_item:
            self.event_markers_item.setData([])
            self.event_markers_item.setVisible(False)

        try:
            if channel:
                units = channel.units or 'pA' # Assume pA if units missing
                # Fetch Data (similar to Spike Tab)
                if source_data == "average":
                    data_vec = channel.get_averaged_data()
                    time_vec = channel.get_relative_averaged_time_vector()
                    data_label = f"{channel.name or chan_id} (Average)"
                elif isinstance(source_data, int):
                    trial_index = source_data
                    if 0 <= trial_index < channel.num_trials:
                        data_vec = channel.get_data(trial_index)
                        time_vec = channel.get_relative_time_vector(trial_index)
                        data_label = f"{channel.name or chan_id} (Trial {trial_index + 1})"

            # Plotting
            if time_vec is not None and data_vec is not None:
                self.data_plot_item = self.plot_widget.plot(time_vec, data_vec, pen='k', name=data_label)
                self.plot_widget.setLabel('left', 'Current', units=units)
                self.plot_widget.setLabel('bottom', 'Time', units='s')
                self.plot_widget.setTitle(data_label)
                # Store data needed for analysis
                self._current_plot_data = {
                    'time': time_vec,
                    'data': data_vec, # Changed key from 'voltage'
                    'rate': channel.sampling_rate,
                    'units': units
                }
                plot_succeeded = True
                log.debug("Mini Event Plotting: Success")
            else:
                log.warning(f"Mini Event Plotting: No valid data for Ch {chan_id}, Source: {source_data}")
                self.plot_widget.setTitle("Plot Error: No Data")

            # Re-add event markers item (clearPlots removes it)
            if self.event_markers_item: self.plot_widget.addItem(self.event_markers_item)

        except Exception as e:
            log.error(f"Mini Event Plotting Error: Ch {chan_id}: {e}", exc_info=True)
            if self.plot_widget:
                self.plot_widget.clear()
                if self.event_markers_item: self.plot_widget.addItem(self.event_markers_item)
                self.plot_widget.setTitle("Plot Error")
            self._current_plot_data = None
            plot_succeeded = False

        # Update button state based on plot success
        if self.detect_button: self.detect_button.setEnabled(plot_succeeded)
        # Clear results text whenever plot changes
        if self.results_textedit: self.results_textedit.clear()
        if self.save_button: self.save_button.setEnabled(False) # Disable save if plot changed

    # --- Placeholder Analysis Method ---
    @QtCore.Slot()
    def _run_event_detection(self):
        """(Placeholder) Runs Mini Event Detection analysis."""
        log.debug("Run Mini Event Detection clicked.")

        # 1. Check if data is plotted
        if not self._current_plot_data:
            log.warning("Cannot run event detection: No data plotted.")
            if self.results_textedit: self.results_textedit.setText("Plot data first.")
            return

        # 2. Validate parameters
        try:
            threshold = float(self.threshold_edit.text())
            direction_text = self.direction_combobox.currentText()
            is_negative_going = "Negative" in direction_text
            if threshold <= 0: raise ValueError("Threshold must be positive")
        except (ValueError, TypeError):
            log.warning("Invalid event detection parameters.")
            QtWidgets.QMessageBox.warning(self, "Invalid Parameters", "Threshold must be a positive number.")
            return

        data = self._current_plot_data.get('data')
        time = self._current_plot_data.get('time')
        rate = self._current_plot_data.get('rate')
        units = self._current_plot_data.get('units', 'pA')

        if data is None or time is None or rate is None or rate <= 0:
            log.error("Cannot run event detection: Missing data, time, or valid rate.")
            if self.results_textedit: self.results_textedit.setText("Error: Invalid plotted data.")
            return

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        if self.results_textedit: self.results_textedit.clear()
        if self.event_markers_item:
            self.event_markers_item.setData([])
            self.event_markers_item.setVisible(False)
        run_successful = False
        event_indices = None
        event_times = None
        event_amplitudes = np.array([]) # Store amplitudes
        results_str = f"""--- Mini Event Detection Results ---
Threshold: {threshold:.3f} {units}
Direction: {'Negative' if is_negative_going else 'Positive'}

"""

        try:
            # --- PLACEHOLDER DETECTION LOGIC ---
            # This is a very basic threshold crossing detector.
            # A real implementation would need filtering, baseline subtraction,
            # event shape analysis (rise/decay), etc.
            log.info(f"Running placeholder event detection: Threshold={threshold:.3f}, Negative={is_negative_going}")

            if is_negative_going:
                crossings = np.where(data < -threshold)[0]
            else:
                crossings = np.where(data > threshold)[0]

            # Very simple: mark the first point of each crossing sequence
            if len(crossings) > 0:
                diffs = np.diff(crossings)
                event_start_indices = crossings[np.concatenate(([True], diffs > 1))] # Find where diff > 1 sample
                event_indices = event_start_indices # Use start index for now
                event_times = time[event_indices]
                # Placeholder amplitude: just the value at the detected index
                event_amplitudes = data[event_indices]
                log.info(f"Placeholder detected {len(event_indices)} events.")
            else:
                event_indices = np.array([])
                event_times = np.array([])
                event_amplitudes = np.array([])
                log.info("Placeholder detected 0 events.")
            # --- END PLACEHOLDER ---

            num_events = len(event_indices)

            # 4. Process and Display Results
            if num_events > 0:
                duration = time[-1] - time[0]
                frequency = num_events / duration if duration > 0 else 0
                mean_amplitude = np.mean(event_amplitudes)
                std_amplitude = np.std(event_amplitudes)

                # Append results to the string
                results_str += f"Number of Events: {num_events}\\n"
                results_str += f"Frequency: {frequency:.3f} Hz\\n"
                results_str += f"Mean Amplitude: {mean_amplitude:.3f} {units}\\n"
                results_str += f"Amplitude SD: {std_amplitude:.3f} {units}\\n"

                # Store results
                self._current_plot_data['event_indices'] = event_indices
                self._current_plot_data['event_times'] = event_times
                self._current_plot_data['event_amplitudes'] = event_amplitudes

                # 5. Update Plot Markers
                if self.event_markers_item:
                    self.event_markers_item.setData(x=event_times, y=data[event_indices]) # Plot at detected point
                    self.event_markers_item.setVisible(True)

            else:
                # Append results to the string
                results_str += "Number of Events: 0\\n"
                self._current_plot_data['event_indices'] = np.array([])
                self._current_plot_data['event_times'] = np.array([])
                self._current_plot_data['event_amplitudes'] = np.array([])

            run_successful = True

        except Exception as e:
            log.error(f"Error during placeholder event detection: {e}", exc_info=True)
            results_str += f"Error during analysis: {e}"
            if self.results_textedit: self.results_textedit.setText(results_str)

        finally:
            if self.results_textedit: self.results_textedit.setText(results_str)
            QtWidgets.QApplication.restoreOverrideCursor()
            if self.save_button: self.save_button.setEnabled(run_successful)

    # --- Base Class Method Implementation ---
    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Gathers the specific Mini Event analysis details for saving."""

        # 1. Check if analysis was run and results exist
        if not self._current_plot_data or 'event_times' not in self._current_plot_data:
            log.debug("_get_specific_result_data (MiniEvent): No analysis results available.")
            return None

        event_times = self._current_plot_data.get('event_times')
        event_amplitudes = self._current_plot_data.get('event_amplitudes')

        # Allow saving even if 0 events detected
        if event_times is None or event_amplitudes is None:
             log.debug("_get_specific_result_data (MiniEvent): event_times or event_amplitudes missing.")
             # Pass # Allow saving params even if no events found

        # 2. Get parameters used
        try:
            threshold = float(self.threshold_edit.text())
            direction_text = self.direction_combobox.currentText()
            is_negative_going = "Negative" in direction_text
        except (ValueError, TypeError):
            log.error("_get_specific_result_data (MiniEvent): Could not read parameters from UI.")
            return None

        # 3. Get data source information
        channel_id = self.channel_combobox.currentData()
        channel_name = self.channel_combobox.currentText().split(' (')[0]
        data_source = self.data_source_combobox.currentData()
        data_source_text = self.data_source_combobox.currentText()

        if channel_id is None or data_source is None:
            log.warning("Cannot get specific Mini Event data: Missing channel or data source.")
            return None

        # 4. Gather results
        num_events = len(event_times) if event_times is not None else 0
        frequency = 0.0
        mean_amplitude = 0.0
        std_amplitude = 0.0

        if num_events > 0:
            time_full = self._current_plot_data.get('time')
            if time_full is not None and time_full.size > 1:
                duration = time_full[-1] - time_full[0]
                frequency = num_events / duration if duration > 0 else 0
            if event_amplitudes is not None and event_amplitudes.size > 0:
                mean_amplitude = np.mean(event_amplitudes)
                std_amplitude = np.std(event_amplitudes)

        specific_data = {
            # Analysis Parameters
            'threshold': threshold,
            'threshold_units': self._current_plot_data.get('units', 'unknown'),
            'detection_direction': 'negative' if is_negative_going else 'positive',
            # Results
            'event_count': num_events,
            'frequency_hz': frequency,
            'mean_amplitude': mean_amplitude,
            'amplitude_sd': std_amplitude,
            'event_times_s': event_times.tolist() if event_times is not None else [],
            'event_amplitudes': event_amplitudes.tolist() if event_amplitudes is not None else [],
             # Data Source Info (for base class)
            'channel_id': channel_id,
            'channel_name': channel_name,
            'data_source': data_source,
            'data_source_label': data_source_text
        }
        log.debug(f"_get_specific_result_data (MiniEvent) returning: {specific_data}")
        return specific_data

# --- END CLASS MiniEventAnalysisTab ---

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = MiniEventAnalysisTab 