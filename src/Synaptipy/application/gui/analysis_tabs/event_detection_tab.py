# src/Synaptipy/application/gui/analysis_tabs/event_detection_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting synaptic events (Miniature and Evoked).
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

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.event_detection_tab')

class EventDetectionTab(BaseAnalysisTab):
    """QWidget for Synaptic Event Detection (Miniature and Evoked)."""

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__(neo_adapter=neo_adapter, parent=parent)

        # --- UI References specific to Event Detection ---
        # Top Level Controls (apply to both sub-tabs)
        self.channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None

        # Sub-Tab Widget
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None

        # Miniature Event Controls
        self.mini_threshold_edit: Optional[QtWidgets.QLineEdit] = None
        self.mini_detect_button: Optional[QtWidgets.QPushButton] = None
        self.mini_results_textedit: Optional[QtWidgets.QTextEdit] = None
        self.mini_method_combobox: Optional[QtWidgets.QComboBox] = None
        self.mini_threshold_widget: Optional[QtWidgets.QWidget] = None
        self.mini_threshold_label: Optional[QtWidgets.QLabel] = None

        # Evoked Event Controls (Placeholder for now)
        # ... (add references if needed later)

        # Plotting related (Shared)
        self.plot_widget: Optional[pg.PlotWidget] = None
        self.data_plot_item: Optional[pg.PlotDataItem] = None
        self.event_markers_item: Optional[pg.ScatterPlotItem] = None
        self._current_plot_data: Optional[Dict[str, Any]] = None

        # Analysis results (potentially store type: mini/evoked)
        self._last_analysis_result: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent AnalyserTab calling update_state()

    def get_display_name(self) -> str:
        return "Event Detection"

    def _setup_ui(self):
        """Create UI elements for the Event Detection tab."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # --- Top Controls Area (Shared) ---
        shared_controls_group = QtWidgets.QGroupBox("Data Selection")
        shared_controls_layout = QtWidgets.QVBoxLayout(shared_controls_group)
        shared_controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # 1. Analysis Item Selector (Inherited)
        item_selector_layout = QtWidgets.QFormLayout()
        self._setup_analysis_item_selector(item_selector_layout)
        shared_controls_layout.addLayout(item_selector_layout)

        # 2. Channel Selector (Current Channels)
        channel_select_layout = QtWidgets.QHBoxLayout()
        channel_select_layout.addWidget(QtWidgets.QLabel("Plot Channel:"))
        self.channel_combobox = QtWidgets.QComboBox()
        self.channel_combobox.setToolTip("Select the current channel to analyze.")
        self.channel_combobox.setEnabled(False)
        channel_select_layout.addWidget(self.channel_combobox, stretch=1)
        shared_controls_layout.addLayout(channel_select_layout)

        # 3. Data Source Selector
        data_source_layout = QtWidgets.QHBoxLayout()
        data_source_layout.addWidget(QtWidgets.QLabel("Data Source:"))
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)
        data_source_layout.addWidget(self.data_source_combobox, stretch=1)
        shared_controls_layout.addLayout(data_source_layout)

        main_layout.addWidget(shared_controls_group) # Add shared controls first

        # --- Sub-Tab Widget ---
        self.sub_tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.sub_tab_widget) # Add sub-tabs below shared controls

        # --- Miniature Event Sub-Tab ---
        miniature_widget = QtWidgets.QWidget()
        miniature_layout = QtWidgets.QVBoxLayout(miniature_widget)
        miniature_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # 4. Miniature Detection Parameters
        mini_param_group = QtWidgets.QGroupBox("Detection Parameters")
        mini_param_layout = QtWidgets.QFormLayout(mini_param_group)
        
        # Method Selection
        self.mini_method_combobox = QtWidgets.QComboBox()
        self.mini_method_combobox.addItems(["Threshold Based", "Automatic (MAD)"])
        self.mini_method_combobox.setToolTip("Choose detection method.")
        mini_param_layout.addRow("Method:", self.mini_method_combobox)
        
        # Threshold Input (Now conditionally visible)
        self.mini_threshold_label = QtWidgets.QLabel("Threshold:")
        self.mini_threshold_edit = QtWidgets.QLineEdit("5.0")
        self.mini_threshold_edit.setToolTip(
            "Detection threshold (sign indicates direction, e.g., -5 for negative deflections, +5 for positive)."
        )
        mini_param_layout.addRow(self.mini_threshold_label, self.mini_threshold_edit)
        
        # Add more params later (e.g., min duration, rise time filter)
        miniature_layout.addWidget(mini_param_group)

        # 5. Miniature Action Button
        self.mini_detect_button = QtWidgets.QPushButton("Detect Miniature Events") # Updated text
        self.mini_detect_button.setEnabled(False)
        self.mini_detect_button.setToolTip("Detect miniature events on the currently plotted trace.")
        mini_button_layout = QtWidgets.QHBoxLayout()
        mini_button_layout.addStretch()
        mini_button_layout.addWidget(self.mini_detect_button)
        mini_button_layout.addStretch()
        miniature_layout.addLayout(mini_button_layout)

        # 6. Miniature Results Display Area
        mini_results_group = QtWidgets.QGroupBox("Results")
        mini_results_layout = QtWidgets.QVBoxLayout(mini_results_group)
        self.mini_results_textedit = QtWidgets.QTextEdit()
        self.mini_results_textedit.setReadOnly(True)
        self.mini_results_textedit.setFixedHeight(100)
        self.mini_results_textedit.setPlaceholderText("Event frequency and amplitude will appear here...")
        mini_results_layout.addWidget(self.mini_results_textedit)
        miniature_layout.addWidget(mini_results_group)

        # 7. Miniature Save Button (Add to this specific sub-tab layout)
        # We need a separate save button instance or logic to handle context
        # For now, let's use the base one but it might need adjustment later.
        self._setup_save_button(miniature_layout)

        miniature_layout.addStretch(1) # Push controls up
        self.sub_tab_widget.addTab(miniature_widget, "Miniature")

        # --- Evoked Event Sub-Tab (Placeholder) ---
        evoked_widget = QtWidgets.QWidget()
        evoked_layout = QtWidgets.QVBoxLayout(evoked_widget)
        evoked_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        placeholder_label = QtWidgets.QLabel("Evoked Event Analysis (Not Yet Implemented)")
        placeholder_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        evoked_layout.addWidget(placeholder_label)
        evoked_layout.addStretch(1)
        self.sub_tab_widget.addTab(evoked_widget, "Evoked")

        # --- Plot Area (Remains at the bottom, shared) ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout) # Base method adds self.plot_widget
        # Add scatter plot item for event markers
        self.event_markers_item = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(0, 0, 255, 150)) # Blue markers
        self.plot_widget.addItem(self.event_markers_item)
        self.event_markers_item.setVisible(False)

        # Add plot container to main layout
        main_layout.addWidget(plot_container, stretch=1) # Make plot expand

        self.setLayout(main_layout)

    def _connect_signals(self):
        """Connect signals specific to Event Detection tab widgets."""
        # Item selection handled by base class (_on_analysis_item_selected)
        self.channel_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        # Connect detect button
        self.mini_detect_button.clicked.connect(self._run_event_detection) # Changed method name
        # Parameters don't need explicit connection if read on click
        
        # ADDED: Connect method combobox
        self.mini_method_combobox.currentIndexChanged.connect(self._on_mini_method_changed)

    # --- Overridden Methods from Base ---
    def _update_ui_for_selected_item(self):
        """Update Event Detection tab UI for new analysis item."""
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None
        if self.mini_results_textedit: self.mini_results_textedit.setText("") # Clear mini results
        if self.mini_detect_button: self.mini_detect_button.setEnabled(False)
        if self.save_button: self.save_button.setEnabled(False)

        # --- Populate Channel ComboBox (Look for Current OR Voltage) ---
        self.channel_combobox.blockSignals(True)
        self.channel_combobox.clear()
        voltage_channels = {}
        current_channels = {}
        if self._selected_item_recording and self._selected_item_recording.channels:
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                 units = getattr(channel, 'units', '')
                 units_lower = units.lower()
                 log.debug(f"  Checking Ch {chan_id} ({channel.name}): Units='{units}'") 
                 display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{units}]"
                 
                 # Check for Current
                 if 'a' in units_lower or 'amp' in units_lower:
                      current_channels[chan_id] = display_name
                      log.debug(f"    >> Found current channel.") 
                 # Check for Voltage (only if not already current)
                 elif 'v' in units_lower:
                      voltage_channels[chan_id] = display_name
                      log.debug(f"    >> Found voltage channel.")

        suitable_channels_found = False
        # Prioritize Current Channels
        if current_channels:
            log.debug(f"Populating combobox with {len(current_channels)} current channels.")
            for chan_id, display_name in current_channels.items():
                self.channel_combobox.addItem(display_name, userData=chan_id)
            suitable_channels_found = True
        # Fallback to Voltage Channels
        elif voltage_channels:
            log.debug(f"No current channels found. Populating combobox with {len(voltage_channels)} voltage channels.")
            for chan_id, display_name in voltage_channels.items():
                self.channel_combobox.addItem(display_name, userData=chan_id)
            suitable_channels_found = True
        # No suitable channels
        else:
            self.channel_combobox.addItem("No Current/Voltage Channels")
            log.debug("No suitable current or voltage channels found.")

        self.channel_combobox.setEnabled(suitable_channels_found) # Enable channel selector if suitable channels exist
        self.channel_combobox.blockSignals(False)

        # --- Populate Data Source ComboBox --- 
        self.data_source_combobox.blockSignals(True)
        self.data_source_combobox.clear()
        self.data_source_combobox.setEnabled(False)
        can_analyze = False
        # Enable data source ONLY if suitable channels were found
        if suitable_channels_found and self._selected_item_recording:
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

        # --- Enable/Disable Miniature Controls --- 
        # Enable only if a valid source can be analyzed (implies suitable channel found)
        mini_controls_enabled = can_analyze 
        if self.mini_method_combobox: self.mini_method_combobox.setEnabled(mini_controls_enabled)
        
        # Update threshold visibility based on current method selection
        self._on_mini_method_changed()

        # --- Plot Initial Trace ---
        if mini_controls_enabled: # If we can potentially analyze
            self._plot_selected_trace()
        else:
            if self.plot_widget: self.plot_widget.clear()
            # Ensure all controls are disabled if no suitable data/channel
            if self.channel_combobox: self.channel_combobox.setEnabled(False)
            if self.data_source_combobox: self.data_source_combobox.setEnabled(False)
            if self.mini_detect_button: self.mini_detect_button.setEnabled(False)
            if self.save_button: self.save_button.setEnabled(False)

    # --- Plotting Method ---
    def _plot_selected_trace(self):
        """Plots the selected current trace and clears previous events."""
        # Basic checks
        plot_succeeded = False # Track plot success
        self._current_plot_data = None # Clear previous data/results
        if self.mini_results_textedit: self.mini_results_textedit.clear()
        if self.event_markers_item: self.event_markers_item.setData([]) # Clear markers
        if self.save_button: self.save_button.setEnabled(False)

        if not self.plot_widget or not self.channel_combobox or not self.data_source_combobox or not self._selected_item_recording:
            if self.plot_widget: self.plot_widget.clearPlots()
            if self.mini_detect_button: self.mini_detect_button.setEnabled(False)
            return

        chan_id = self.channel_combobox.currentData()
        source_data = self.data_source_combobox.currentData()
        if not chan_id or source_data is None:
             if self.plot_widget: self.plot_widget.clearPlots()
             if self.mini_detect_button: self.mini_detect_button.setEnabled(False)
             return

        channel = self._selected_item_recording.channels.get(chan_id)
        log.debug(f"Event Detection Plotting: Ch {chan_id}, Source: {source_data}")

        time_vec, data_vec = None, None
        data_label = "Trace Error"
        units = "A" # Default current units

        # Clear previous plot items
        if self.plot_widget: self.plot_widget.clearPlots()
        # Re-add markers item after clearing plots
        if self.plot_widget and self.event_markers_item not in self.plot_widget.items():
             self.plot_widget.addItem(self.event_markers_item)
             self.event_markers_item.setVisible(False) # Keep hidden initially

        try:
            if channel:
                units = channel.units or "A"
                # Select data based on DATA SOURCE COMBOBOX
                if source_data == "average":
                    data_vec = channel.get_averaged_data()
                    time_vec = channel.get_relative_averaged_time_vector()
                    log.debug(f"Retrieved average data: Data is None = {data_vec is None}, Time is None = {time_vec is None}")
                    data_label = f"{channel.name or chan_id} (Average)"
                elif isinstance(source_data, int):
                    trial_index = source_data
                    if 0 <= trial_index < channel.num_trials:
                        data_vec = channel.get_data(trial_index)
                        time_vec = channel.get_relative_time_vector(trial_index)
                        log.debug(f"Retrieved trial {trial_index} data: Data is None = {data_vec is None}, Time is None = {time_vec is None}")
                        data_label = f"{channel.name or chan_id} (Trial {trial_index + 1})"
                    else:
                        log.warning(f"Invalid trial index {trial_index} requested for Ch {chan_id}")
                else:
                     log.warning(f"Unknown data source selected: {source_data}")

            # Plotting
            if time_vec is not None and data_vec is not None:
                self.data_plot_item = self.plot_widget.plot(time_vec, data_vec, pen='k', name=data_label)
                self.plot_widget.setLabel('left', 'Current', units=units)
                self.plot_widget.setLabel('bottom', 'Time', units='s')
                self.plot_widget.setTitle(data_label)
                self._current_plot_data = {
                    'time': time_vec,
                    'data': data_vec,
                    'units': units,
                    'sampling_rate': channel.sampling_rate if channel else None
                }
                # ADDED: Log keys to verify data storage
                log.debug(f"Stored keys in _current_plot_data: {list(self._current_plot_data.keys())}")
                plot_succeeded = True
                log.debug("Event Detection Plotting: Success")
                self.plot_widget.autoRange() # Auto-range after successful plot
            else:
                log.warning(f"Event Detection Plotting: No valid data for Ch {chan_id}, Source: {source_data}")
                if self.plot_widget: self.plot_widget.setTitle("Plot Error: No Data")
                self._current_plot_data = None
                plot_succeeded = False

        except Exception as e:
            log.error(f"Event Detection Plotting Error: Ch {chan_id}: {e}", exc_info=True)
            if self.plot_widget:
                self.plot_widget.clear()
                # Re-add markers item if needed after clear
                if self.event_markers_item not in self.plot_widget.items():
                    self.plot_widget.addItem(self.event_markers_item)
                    self.event_markers_item.setVisible(False)
                self.plot_widget.setTitle("Plot Error")
            self._current_plot_data = None
            plot_succeeded = False

        # --- Final UI State Update --- 
        # Enable miniature detection button and parameters ONLY if plot succeeded
        if self.mini_detect_button: self.mini_detect_button.setEnabled(plot_succeeded)
        if self.mini_method_combobox: self.mini_method_combobox.setEnabled(plot_succeeded)
        # Clear results and disable save button regardless, as analysis needs to be re-run
        if self.mini_results_textedit: self.mini_results_textedit.clear()
        if self.save_button: self.save_button.setEnabled(False)

    # --- Placeholder Analysis Method ---
    @QtCore.Slot()
    def _run_event_detection(self):
        """Runs Event Detection analysis based on selected method."""
        log.debug("Run Event Detection clicked.")
        
        # Determine selected method
        method = self.mini_method_combobox.currentText()
        log.debug(f"Detection method selected: {method}")

        # 1. Check if data is plotted
        if not self._current_plot_data:
            log.warning("Cannot run event detection: No data plotted.")
            if self.mini_results_textedit: self.mini_results_textedit.setText("Plot data first.")
            return

        # 2. Validate parameters
        try:
            threshold = float(self.mini_threshold_edit.text())
            if threshold == 0: raise ValueError("Threshold cannot be zero")
        except (ValueError, TypeError):
            log.warning("Invalid event detection parameters.")
            # More specific error based on method?
            err_msg = "Threshold must be a non-zero number." if "Threshold" in method else "Invalid parameters."
            QtWidgets.QMessageBox.warning(self, "Invalid Parameters", err_msg)
            return

        data = self._current_plot_data.get('data')
        time = self._current_plot_data.get('time')
        rate = self._current_plot_data.get('sampling_rate')
        units = self._current_plot_data.get('units', '?') # Default to '?'

        if data is None or time is None or rate is None or rate <= 0:
            log.error("Cannot run event detection: Missing data, time, or valid rate.")
            if self.mini_results_textedit: self.mini_results_textedit.setText("Error: Invalid plotted data.")
            return

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        if self.mini_results_textedit: self.mini_results_textedit.clear()
        if self.event_markers_item:
            self.event_markers_item.setData([])
            self.event_markers_item.setVisible(False)
        run_successful = False
        event_indices = None
        event_times = None
        event_amplitudes = np.array([]) # Store amplitudes
        results_str = f"""--- Event Detection Results ---
Threshold: {threshold:.3f} {units}

"""

        try:
            # --- PLACEHOLDER DETECTION LOGIC ---
            # This is a very basic threshold crossing detector.
            # A real implementation would need filtering, baseline subtraction,
            # event shape analysis (rise/decay), etc.
            log.info(f"Running placeholder event detection: Threshold={threshold:.3f}")

            crossings = None
            if threshold < 0:
                log.info(f"Running placeholder event detection: Threshold={threshold:.3f} (Negative)")
                crossings = np.where(data < threshold)[0]
            else: # threshold > 0
                log.info(f"Running placeholder event detection: Threshold={threshold:.3f} (Positive)")
                crossings = np.where(data > threshold)[0]

            # Very simple: mark the first point of each crossing sequence
            if crossings is not None and len(crossings) > 0:
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
            if self.mini_results_textedit: self.mini_results_textedit.setText(results_str)

        finally:
            if self.mini_results_textedit: self.mini_results_textedit.setText(results_str)
            QtWidgets.QApplication.restoreOverrideCursor()
            if self.save_button: self.save_button.setEnabled(run_successful)

    # --- Helper Slot --- 
    @QtCore.Slot()
    def _on_mini_method_changed(self):
        """Handles changes in the miniature detection method combobox."""
        # Check if analysis is possible overall (reflected by method combobox enabled state)
        overall_enabled = self.mini_method_combobox.isEnabled() if self.mini_method_combobox else False
        
        is_threshold_method = self.mini_method_combobox.currentText() == "Threshold Based"
        
        # Enable threshold field only if overall analysis is possible AND threshold method is selected
        threshold_field_enabled = overall_enabled and is_threshold_method
        
        if self.mini_threshold_edit:
            self.mini_threshold_edit.setEnabled(threshold_field_enabled)
        if self.mini_threshold_label:
             self.mini_threshold_label.setEnabled(threshold_field_enabled)
             
        log.debug(f"Mini detection method changed. Overall enabled: {overall_enabled}, Is Threshold Method: {is_threshold_method} => Threshold input enabled: {threshold_field_enabled}")

    # --- Base Class Method Implementation ---
    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Gathers the specific Event Detection analysis details for saving."""

        # 1. Check if analysis was run and results exist
        if not self._current_plot_data or 'event_times' not in self._current_plot_data:
            log.debug("_get_specific_result_data (EventDetection): No analysis results available.")
            return None

        event_times = self._current_plot_data.get('event_times')
        event_amplitudes = self._current_plot_data.get('event_amplitudes')

        # Allow saving even if 0 events detected
        if event_times is None or event_amplitudes is None:
             log.debug("_get_specific_result_data (EventDetection): event_times or event_amplitudes missing.")
             # Pass # Allow saving params even if no events found

        # 2. Get parameters used
        try:
            threshold = float(self.mini_threshold_edit.text())
        except (ValueError, TypeError):
            log.error("_get_specific_result_data (EventDetection): Could not read parameters from UI.")
            return None

        # 3. Get data source information
        channel_id = self.channel_combobox.currentData()
        channel_name = self.channel_combobox.currentText().split(' (')[0]
        data_source = self.data_source_combobox.currentData()
        data_source_text = self.data_source_combobox.currentText()

        if channel_id is None or data_source is None:
            log.warning("Cannot get specific Event Detection data: Missing channel or data source.")
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
        log.debug(f"_get_specific_result_data (EventDetection) returning: {specific_data}")
        return specific_data

# --- END CLASS EventDetectionTab ---

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = EventDetectionTab 