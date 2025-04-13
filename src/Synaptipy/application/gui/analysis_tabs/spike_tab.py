# src/Synaptipy/application/gui/analysis_tabs/spike_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting spikes using a simple threshold.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets

# Import base class using relative path within analysis_tabs package
from .base import BaseAnalysisTab
# Import needed core components using absolute paths
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.core.analysis import spike_analysis # Import the analysis function

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.spike_tab')

class SpikeAnalysisTab(BaseAnalysisTab):
    """QWidget for Threshold-based Spike Detection."""

    def __init__(self, explorer_tab_ref, parent=None):
        super().__init__(explorer_tab_ref, parent)

        # --- UI References specific to Spike ---
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.channel_scroll_area: Optional[QtWidgets.QScrollArea] = None
        self.channel_checkbox_layout: Optional[QtWidgets.QVBoxLayout] = None
        # Trial selection UI is removed
        self.threshold_edit: Optional[QtWidgets.QLineEdit] = None
        self.refractory_edit: Optional[QtWidgets.QLineEdit] = None
        self.run_button: Optional[QtWidgets.QPushButton] = None
        self.results_textedit: Optional[QtWidgets.QTextEdit] = None
        # Keep internal list of items to analyse
        self._analysis_items_for_spike: List[Dict[str, Any]] = []
        # Store the representative recording used for UI population
        self._current_recording_for_ui: Optional[Recording] = None


        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent AnalyserTab calling update_state()

    def get_display_name(self) -> str:
        return "Spike Detection (Threshold)"

    def _setup_ui(self):
        """Create UI elements for the Spike analysis tab."""
        main_layout = QtWidgets.QHBoxLayout(self)
        controls_widget = QtWidgets.QWidget()
        controls_layout = QtWidgets.QVBoxLayout(controls_widget)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        config_group = QtWidgets.QGroupBox("Spike Detection Configuration")
        config_layout = QtWidgets.QVBoxLayout(config_group)

        # Channel Selection
        chan_label = QtWidgets.QLabel("Channel(s) for Spikes:")
        config_layout.addWidget(chan_label)
        self.channel_scroll_area = QtWidgets.QScrollArea()
        self.channel_scroll_area.setWidgetResizable(True)
        self.channel_scroll_area.setFixedHeight(150)
        chan_widget = QtWidgets.QWidget()
        self.channel_checkbox_layout = QtWidgets.QVBoxLayout(chan_widget)
        self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.channel_scroll_area.setWidget(chan_widget)
        config_layout.addWidget(self.channel_scroll_area)

        # Spike Parameters
        param_layout = QtWidgets.QFormLayout()
        param_layout.setContentsMargins(5, 5, 5, 5)
        self.threshold_edit = QtWidgets.QLineEdit("0.0")
        self.threshold_edit.setValidator(QtGui.QDoubleValidator())
        self.threshold_edit.setToolTip("Voltage threshold")
        param_layout.addRow("Threshold:", self.threshold_edit)
        self.refractory_edit = QtWidgets.QLineEdit("2.0")
        self.refractory_edit.setValidator(QtGui.QDoubleValidator(0, 1000, 3))
        self.refractory_edit.setToolTip("Refractory Period (ms)")
        param_layout.addRow("Refractory (ms):", self.refractory_edit)
        config_layout.addLayout(param_layout)

        config_layout.addStretch(1)
        self.run_button = QtWidgets.QPushButton("Detect Spikes")
        self.run_button.setEnabled(False)
        config_layout.addWidget(self.run_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        controls_layout.addWidget(config_group)
        controls_widget.setFixedWidth(400)
        main_layout.addWidget(controls_widget)

        # Results
        results_group = QtWidgets.QGroupBox("Spike Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        self.results_textedit = QtWidgets.QTextEdit()
        self.results_textedit.setReadOnly(True)
        self.results_textedit.setPlaceholderText("Select channels and run analysis...")
        results_layout.addWidget(self.results_textedit)
        main_layout.addWidget(results_group, stretch=1)

        self.setLayout(main_layout)


    def _connect_signals(self):
        """Connect signals specific to Spike tab widgets."""
        # Connect param edits to update run button state
        self.threshold_edit.textChanged.connect(self._update_run_button_state)
        self.refractory_edit.textChanged.connect(self._update_run_button_state)
        # Connect run button
        self.run_button.clicked.connect(self._run_spike_analysis)
        # Channel checkboxes are connected in _update_channel_list

    # --- Overridden Methods from Base ---
    def update_state(self, current_recording_for_ui: Optional[Recording], analysis_items: List[Dict[str, Any]]):
        """Update state specific to the Spike tab."""
        self._current_recording_for_ui = current_recording_for_ui
        self._analysis_items_for_spike = analysis_items
        has_items = bool(self._analysis_items_for_spike)
        has_data_for_ui = self._current_recording_for_ui is not None

        self._update_channel_list() # Use representative recording
        self.channel_scroll_area.setEnabled(has_data_for_ui)
        self.threshold_edit.setEnabled(has_items) # Enable params if items exist
        self.refractory_edit.setEnabled(has_items)
        self._update_run_button_state() # Update run button

    # --- Private Helper Methods specific to Spike Tab ---
    def _update_channel_list(self):
        """Populate Spike channel list based on _current_recording_for_ui."""
        layout = self.channel_checkbox_layout
        checkboxes_dict = self.channel_checkboxes
        for checkbox in checkboxes_dict.values():
            try: checkbox.stateChanged.disconnect(self._update_run_button_state)
            except RuntimeError: pass
            checkbox.deleteLater()
        checkboxes_dict.clear()
        while layout.count(): item = layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None

        if self._current_recording_for_ui and self._current_recording_for_ui.channels:
            sorted_channels = sorted(self._current_recording_for_ui.channels.items(), key=lambda item: item[0])
            for chan_id, channel in sorted_channels:
                units_lower = getattr(channel, 'units', '').lower()
                # Filter for voltage channels
                if 'v' in units_lower or units_lower == 'unknown':
                    checkbox = QtWidgets.QCheckBox(f"{channel.name} ({chan_id}) [{channel.units}]")
                    checkbox.stateChanged.connect(self._update_run_button_state) # Connect run button update
                    layout.addWidget(checkbox)
                    checkboxes_dict[chan_id] = checkbox

    def _validate_params(self) -> bool:
        """Validates Spike Detection parameters."""
        try:
            float(self.threshold_edit.text()) # Check if threshold is a valid float
            r=float(self.refractory_edit.text())
            return r>=0 # Refractory must be non-negative
        except (ValueError, TypeError):
            return False

    def _update_run_button_state(self):
        """Enables/disables the Spike Run button."""
        if not self.run_button: return
        have_items = bool(self._analysis_items_for_spike)
        channels_selected = any(cb.isChecked() for cb in self.channel_checkboxes.values())
        params_valid = self._validate_params()
        self.run_button.setEnabled(have_items and channels_selected and params_valid)

    def _get_analysis_data_for_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Dict[str, Any]]]:
        """Reads file and extracts data for selected channels based on item info for spike analysis."""
        filepath = item['path']; target_type = item['target_type']; trial_index = item['trial_index']
        selected_chan_ids = [cid for cid, cb in self.channel_checkboxes.items() if cb.isChecked()]
        item_results = {}
        if not selected_chan_ids: return None

        try:
            if not hasattr(self._explorer_tab, 'neo_adapter') or not self._explorer_tab.neo_adapter: return None
            recording = self._explorer_tab.neo_adapter.read_recording(filepath)
            if not recording or not recording.channels: return None

            for chan_id in selected_chan_ids:
                 ch = recording.channels.get(chan_id)
                 if not ch: continue
                 data: Optional[np.ndarray] = None; time: Optional[np.ndarray] = None
                 units = ch.units; rate = ch.sampling_rate
                 is_multi = False; data_list = []; time_list = []

                 if target_type == "Current Trial":
                     if trial_index is not None and 0 <= trial_index < ch.num_trials: data = ch.get_data(trial_index); time = ch.get_relative_time_vector(trial_index)
                 elif target_type == "Average Trace":
                     data = ch.get_averaged_data(); time = ch.get_relative_averaged_time_vector()
                 elif target_type == "All Trials":
                     is_multi = True
                     for idx in range(ch.num_trials):
                         t_data = ch.get_data(idx); t_time = ch.get_relative_time_vector(idx)
                         if t_data is not None and t_time is not None: data_list.append(t_data); time_list.append(t_time)
                     if not data_list: continue # Skip channel if no valid trials found for 'All'

                 # Store results
                 if is_multi:
                      item_results[chan_id] = {'data': data_list, 'time': time_list, 'units': units, 'rate': rate, 'is_multi_trial': True}
                 elif data is not None and time is not None:
                      item_results[chan_id] = {'data': data, 'time': time, 'units': units, 'rate': rate, 'is_multi_trial': False}
                 else: log.warning(f"Spike: Could not get valid data/time Ch {chan_id}, Item: {item}")

            return item_results if item_results else None
        except Exception as e: log.error(f"Spike: Error reading/processing {filepath.name}: {e}", exc_info=True); return None


    def _run_spike_analysis(self):
        """Runs Spike Detection analysis and displays results."""
        log.debug("Run Spike Analysis clicked.")
        self.results_textedit.clear()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        results_str = f"--- Analysis Results: Spike Detection (Threshold) ---\n\n"
        run_successful = False
        try:
            if not self._analysis_items_for_spike: self.results_textedit.setText("No analysis items selected."); return

            threshold = float(self.threshold_edit.text())
            refractory_ms = float(self.refractory_edit.text())

            for item_idx, item in enumerate(self._analysis_items_for_spike):
                 path_name = item['path'].name; target = item['target_type']; trial_info_item = f" (Trial {item['trial_index'] + 1})" if target == "Current Trial" else ""
                 item_label = f"{path_name} [{target}{trial_info_item}]"
                 results_str += f"===== Item {item_idx+1}: {item_label} =====\n"
                 item_channel_data = self._get_analysis_data_for_item(item)
                 if not item_channel_data: results_str += "  (Could not retrieve data)\n\n"; continue

                 item_processed = False
                 for chan_id, data_dict in item_channel_data.items():
                     channel_name = chan_id # Default if representative recording is None
                     if self._current_recording_for_ui and chan_id in self._current_recording_for_ui.channels:
                         channel_name = self._current_recording_for_ui.channels[chan_id].name

                     units = data_dict['units']; rate = data_dict['rate']
                     results_str += f"  Channel: {channel_name} ({chan_id})\n"
                     if not rate or rate <= 0:
                          results_str += "    Skipped: Invalid sampling rate.\n"; continue

                     refractory_samples = int(refractory_ms * rate / 1000.0)
                     is_multi = data_dict.get('is_multi_trial', False)
                     data_list = data_dict['data'] if is_multi else [data_dict['data']]
                     time_list = data_dict['time'] if is_multi else [data_dict['time']]
                     total_spikes_item_chan = 0
                     all_isis_item_chan = []

                     for t_idx, (data, time) in enumerate(zip(data_list, time_list)):
                         if is_multi: results_str += f"    Trial {t_idx+1}:\n"; indent = "      "
                         else: indent = "    "

                         spike_indices, spike_times = spike_analysis.detect_spikes_threshold(data, time, threshold, refractory_samples)
                         num_spikes = len(spike_indices); total_spikes_item_chan += num_spikes
                         results_str += f"{indent}Spike Count (Thr={threshold:.2f}{units}, Refr={refractory_ms:.1f}ms): {num_spikes}\n"
                         if num_spikes > 1: isis = np.diff(spike_times) * 1000; all_isis_item_chan.extend(isis); mean_isi=np.mean(isis); std_isi=np.std(isis); results_str += f"{indent}  Mean ISI: {mean_isi:.2f} ms, Std ISI: {std_isi:.2f} ms\n"
                         elif num_spikes == 1: results_str += f"{indent}  Spike Time (s): {spike_times[0]:.4f}\n"
                         # Add newline between trials if processing all
                         # if is_multi and t_idx < len(data_list) - 1: results_str += "\n" # Maybe too much space

                     # Overall stats for this channel if multi-trial
                     if is_multi and total_spikes_item_chan > 0:
                          results_str += f"    Overall (Channel):\n"
                          results_str += f"      Total Spikes: {total_spikes_item_chan}\n"
                          if len(all_isis_item_chan) > 0: mean_isi_all=np.mean(all_isis_item_chan); std_isi_all=np.std(all_isis_item_chan); results_str += f"      Mean ISI (all trials): {mean_isi_all:.2f} ms, Std ISI: {std_isi_all:.2f} ms\n"
                     item_processed = True # Mark item as processed if at least one channel was attempted

                 results_str += "\n" # Space between channels for the same item
                 if item_processed: run_successful = True

            if not run_successful: results_str += "\nNo channels successfully analyzed across all items."
            self.results_textedit.setText(results_str)
        except ValueError as ve: log.warning(f"Invalid Spike params: {ve}"); self.results_textedit.setText(f"*** Param Error: {ve} ***"); QtWidgets.QMessageBox.warning(self, "Param Error", str(ve))
        except Exception as e: log.error(f"Error during Spike analysis: {e}", exc_info=True); self.results_textedit.setText(f"{results_str}\n\n*** ERROR: {e} ***"); QtWidgets.QMessageBox.critical(self, "Analysis Error", f"Error:\n{e}")
        finally: QtWidgets.QApplication.restoreOverrideCursor()