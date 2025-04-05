# src/Synaptipy/application/gui/analysis_tabs/rmp_tab.py
# (Imports remain mostly the same, ensure typing is correct)
import logging
from typing import Optional, List, Dict, Any, Tuple # Add Tuple
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from .base import BaseAnalysisTab
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.core.analysis import basic_features

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rmp_tab')

class RmpAnalysisTab(BaseAnalysisTab):
    # ... (Existing __init__ and UI references) ...
    def __init__(self, explorer_tab_ref, parent=None):
        super().__init__(explorer_tab_ref, parent)
        # --- UI References specific to RMP ---
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.channel_scroll_area: Optional[QtWidgets.QScrollArea] = None
        self.channel_checkbox_layout: Optional[QtWidgets.QVBoxLayout] = None
        # Trial selection is now implicit based on items from Explorer
        # Remove trial selection widgets if they were still here
        self.start_time_edit: Optional[QtWidgets.QLineEdit] = None
        self.end_time_edit: Optional[QtWidgets.QLineEdit] = None
        self.run_button: Optional[QtWidgets.QPushButton] = None
        self.results_textedit: Optional[QtWidgets.QTextEdit] = None
        # Keep internal list of items to analyse
        self._analysis_items_for_rmp: List[Dict[str, Any]] = []

        self._setup_ui()
        self._connect_signals()

    def get_display_name(self) -> str: return "Resting Potential (RMP)"

    def _setup_ui(self):
        rmp_main_layout = QtWidgets.QHBoxLayout(self)
        controls_widget = QtWidgets.QWidget(); controls_layout = QtWidgets.QVBoxLayout(controls_widget)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        rmp_config_group = QtWidgets.QGroupBox("RMP Configuration"); rmp_config_layout = QtWidgets.QVBoxLayout(rmp_config_group)
        rmp_chan_label = QtWidgets.QLabel("Channel(s) for RMP:"); rmp_config_layout.addWidget(rmp_chan_label)
        self.channel_scroll_area = QtWidgets.QScrollArea(); self.channel_scroll_area.setWidgetResizable(True); self.channel_scroll_area.setFixedHeight(150)
        rmp_chan_widget = QtWidgets.QWidget(); self.channel_checkbox_layout = QtWidgets.QVBoxLayout(rmp_chan_widget); self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.channel_scroll_area.setWidget(rmp_chan_widget); rmp_config_layout.addWidget(self.channel_scroll_area)
        # --- Remove Trial Selection UI ---
        rmp_param_layout = QtWidgets.QFormLayout(); rmp_param_layout.setContentsMargins(5, 5, 5, 5)
        self.start_time_edit = QtWidgets.QLineEdit("0.0"); self.start_time_edit.setValidator(QtGui.QDoubleValidator()); self.start_time_edit.setToolTip("Baseline Start (s)")
        rmp_param_layout.addRow("Baseline Start (s):", self.start_time_edit)
        self.end_time_edit = QtWidgets.QLineEdit("0.1"); self.end_time_edit.setValidator(QtGui.QDoubleValidator()); self.end_time_edit.setToolTip("Baseline End (s)")
        rmp_param_layout.addRow("Baseline End (s):", self.end_time_edit)
        rmp_config_layout.addLayout(rmp_param_layout); rmp_config_layout.addStretch(1)
        self.run_button = QtWidgets.QPushButton("Calculate RMP"); self.run_button.setEnabled(False)
        rmp_config_layout.addWidget(self.run_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        controls_layout.addWidget(rmp_config_group); controls_widget.setFixedWidth(400)
        rmp_main_layout.addWidget(controls_widget)
        rmp_results_group = QtWidgets.QGroupBox("RMP Results"); rmp_results_layout = QtWidgets.QVBoxLayout(rmp_results_group)
        self.results_textedit = QtWidgets.QTextEdit(); self.results_textedit.setReadOnly(True); self.results_textedit.setPlaceholderText("RMP results...")
        rmp_results_layout.addWidget(self.results_textedit)
        rmp_main_layout.addWidget(rmp_results_group, stretch=1)
        self.setLayout(rmp_main_layout)

    def _connect_signals(self):
        # Connect only param edits and run button
        self.start_time_edit.textChanged.connect(self._update_run_button_state) # Update button when params change
        self.end_time_edit.textChanged.connect(self._update_run_button_state)
        self.run_button.clicked.connect(self._run_rmp_analysis)
        # Channel checkboxes connected in _update_channel_list

    def update_state(self, current_recording_for_ui: Optional[Recording], analysis_items: List[Dict[str, Any]]):
        """Update state specific to the RMP tab, using the provided item list."""
        # Call base first is not needed if we re-implement fully
        # super().update_state() # Don't call base if it raises NotImplementedError
        self._current_recording_for_ui = current_recording_for_ui # Store representative recording for UI
        self._analysis_items_for_rmp = analysis_items # Store the list of items to analyze
        has_items = bool(self._analysis_items_for_rmp)

        # Populate channel list based on the representative recording
        self._update_channel_list()

        # Enable/Disable based on whether there are items to analyze
        self.channel_scroll_area.setEnabled(has_items)
        self.start_time_edit.setEnabled(has_items)
        self.end_time_edit.setEnabled(has_items)
        self._update_run_button_state() # Update run button specifically

    def _update_channel_list(self):
        """Populate RMP channel list based on _current_recording_for_ui."""
        layout = self.channel_checkbox_layout
        checkboxes_dict = self.channel_checkboxes
        for checkbox in checkboxes_dict.values():
            try: checkbox.stateChanged.disconnect(self._update_run_button_state) # Disconnect run button update
            except RuntimeError: pass
            checkbox.deleteLater()
        checkboxes_dict.clear()
        while layout.count(): item = layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None

        if self._current_recording_for_ui and self._current_recording_for_ui.channels:
            sorted_channels = sorted(self._current_recording_for_ui.channels.items(), key=lambda item: item[0])
            for chan_id, channel in sorted_channels:
                units_lower = getattr(channel, 'units', '').lower()
                if 'v' in units_lower or units_lower == 'unknown':
                    checkbox = QtWidgets.QCheckBox(f"{channel.name} ({chan_id}) [{channel.units}]")
                    checkbox.stateChanged.connect(self._update_run_button_state) # Connect run button update
                    layout.addWidget(checkbox)
                    checkboxes_dict[chan_id] = checkbox

    def _validate_params(self) -> bool:
        """Validates RMP parameters."""
        try: s=float(self.start_time_edit.text()); e=float(self.end_time_edit.text()); return e>s>=0
        except (ValueError, TypeError): return False

    def _update_run_button_state(self):
        """Enables/disables the RMP Run button."""
        if not self.run_button: return
        have_items = bool(self._analysis_items_for_rmp)
        channels_selected = any(cb.isChecked() for cb in self.channel_checkboxes.values())
        params_valid = self._validate_params()
        self.run_button.setEnabled(have_items and channels_selected and params_valid)

    def _get_analysis_data_for_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Reads a single file and extracts data for selected channels based on item info.
        Returns {chan_id: {'data':..., 'time':..., 'units':..., 'rate':...}, ...} for THIS item.
        """
        filepath = item['path']
        target_type = item['target_type']
        trial_index = item['trial_index'] # 0-based or None
        selected_chan_ids = [cid for cid, cb in self.channel_checkboxes.items() if cb.isChecked()]
        item_results = {}

        if not selected_chan_ids: return None # No channels selected in this tab

        try:
            # Read the recording for this specific item
            # Use the adapter from the explorer tab reference
            recording = self._explorer_tab.neo_adapter.read_recording(filepath)
            if not recording or not recording.channels:
                 log.warning(f"Could not read or find channels in {filepath.name} for analysis.")
                 return None

            for chan_id in selected_chan_ids:
                 ch = recording.channels.get(chan_id)
                 if not ch:
                     log.warning(f"Channel {chan_id} not found in {filepath.name}")
                     continue

                 data: Optional[np.ndarray] = None
                 time: Optional[np.ndarray] = None
                 units = ch.units
                 rate = ch.sampling_rate

                 if target_type == "Current Trial":
                     if trial_index is not None and 0 <= trial_index < ch.num_trials:
                         data = ch.get_data(trial_index)
                         time = ch.get_relative_time_vector(trial_index)
                     else: log.warning(f"Invalid trial index {trial_index} for Ch {chan_id} in {filepath.name}")
                 elif target_type == "Average Trace":
                     data = ch.get_averaged_data()
                     time = ch.get_relative_averaged_time_vector()
                 elif target_type == "All Trials":
                     # For RMP, averaging all trials makes sense.
                     # For other analyses, might need to return List[Tuple[data, time]]
                     data = ch.get_averaged_data() # Average for RMP context
                     time = ch.get_relative_averaged_time_vector()
                 # Add other target_type handling if needed

                 if data is not None and time is not None:
                     item_results[chan_id] = {'data': data, 'time': time, 'units': units, 'rate': rate}
                 else:
                     log.warning(f"Could not get valid data/time for Ch {chan_id}, Item: {item}")

            return item_results if item_results else None

        except Exception as e:
            log.error(f"Error reading/processing file {filepath.name} for analysis item {item}: {e}", exc_info=True)
            return None


    def _run_rmp_analysis(self):
        """Runs RMP analysis on all selected items/channels and displays results."""
        log.debug("Run RMP Analysis clicked.")
        self.results_textedit.clear()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        results_str = f"--- Analysis Results: Resting Potential (RMP) ---\n\n"
        run_successful = False
        try:
            if not self._analysis_items_for_rmp:
                 self.results_textedit.setText("No analysis items selected.")
                 return

            start_t = float(self.start_time_edit.text())
            end_t = float(self.end_time_edit.text())
            baseline_window = (start_t, end_t)
            if start_t >= end_t: raise ValueError("Baseline start time must be less than end time.")

            for item_idx, item in enumerate(self._analysis_items_for_rmp):
                 path_name = item['path'].name
                 target = item['target_type']
                 trial_info = f" (Trial {item['trial_index'] + 1})" if target == "Current Trial" else ""
                 item_label = f"{path_name} [{target}{trial_info}]"
                 results_str += f"===== Item {item_idx+1}: {item_label} =====\n"

                 # Get data for the channels selected in *this tab* for *this item*
                 item_channel_data = self._get_analysis_data_for_item(item)

                 if not item_channel_data:
                      results_str += "  (Could not retrieve data for this item)\n"
                      continue

                 for chan_id, data_dict in item_channel_data.items():
                     # Use the channel name from the originally read data for this item
                     # We need to re-read the recording inside _get_analysis_data_for_item anyway
                     # Alternatively, store channel name in the item dict if needed frequently
                     channel_name = self._current_recording_for_ui.channels[chan_id].name if self._current_recording_for_ui and chan_id in self._current_recording_for_ui.channels else chan_id
                     data = data_dict['data']; time = data_dict['time']; units = data_dict['units']
                     results_str += f"  Channel: {channel_name} ({chan_id})\n"
                     rmp = basic_features.calculate_rmp(data, time, baseline_window)
                     if rmp is not None: results_str += f"    RMP ({start_t:.3f}-{end_t:.3f}s): {rmp:.3f} {units}\n"
                     else: results_str += f"    RMP calculation failed.\n"
                 results_str += "\n" # Space between items
                 run_successful = True # Mark success if at least one item processed

            if not run_successful:
                 results_str += "\nNo channels successfully analyzed."

            self.results_textedit.setText(results_str)
        except ValueError as ve: # Catch specific param errors
             log.warning(f"Invalid RMP parameters: {ve}")
             self.results_textedit.setText(f"*** Parameter Error: {ve} ***"); QtWidgets.QMessageBox.warning(self, "Parameter Error", str(ve))
        except Exception as e:
             log.error(f"Error during RMP analysis: {e}", exc_info=True)
             self.results_textedit.setText(f"{results_str}\n\n*** ERROR: {e} ***"); QtWidgets.QMessageBox.critical(self, "Analysis Error", f"Error:\n{e}")
        finally: QtWidgets.QApplication.restoreOverrideCursor()