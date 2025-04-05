# src/Synaptipy/application/gui/analysis_tabs/rmp_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for calculating Resting Membrane Potential (RMP).
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets

# Import base class using relative path within analysis_tabs package
from .base import BaseAnalysisTab
# Import needed core components using absolute paths
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.core.analysis import basic_features # Import the analysis function

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rmp_tab')

class RmpAnalysisTab(BaseAnalysisTab):
    """QWidget for RMP analysis."""

    def __init__(self, explorer_tab_ref, parent=None):
        super().__init__(explorer_tab_ref, parent)

        # --- UI References specific to RMP ---
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.channel_scroll_area: Optional[QtWidgets.QScrollArea] = None
        self.channel_checkbox_layout: Optional[QtWidgets.QVBoxLayout] = None
        # Trial selection UI is removed from this sub-tab directly
        self.start_time_edit: Optional[QtWidgets.QLineEdit] = None
        self.end_time_edit: Optional[QtWidgets.QLineEdit] = None
        self.run_button: Optional[QtWidgets.QPushButton] = None
        self.results_textedit: Optional[QtWidgets.QTextEdit] = None
        # Keep internal list of items to analyse, updated by parent
        self._analysis_items_for_rmp: List[Dict[str, Any]] = []
        # Store the representative recording used for UI population
        self._current_recording_for_ui: Optional[Recording] = None

        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent AnalyserTab calling update_state()

    def get_display_name(self) -> str:
        """Returns the name for the sub-tab."""
        return "Resting Potential (RMP)"

    def _setup_ui(self):
        """Create UI elements for the RMP analysis tab."""
        rmp_main_layout = QtWidgets.QHBoxLayout(self) # Controls | Results

        # --- Controls ---
        controls_widget = QtWidgets.QWidget()
        controls_layout = QtWidgets.QVBoxLayout(controls_widget)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        rmp_config_group = QtWidgets.QGroupBox("RMP Configuration")
        rmp_config_layout = QtWidgets.QVBoxLayout(rmp_config_group)

        # Channel Selection
        rmp_chan_label = QtWidgets.QLabel("Channel(s) for RMP:")
        rmp_config_layout.addWidget(rmp_chan_label)
        self.channel_scroll_area = QtWidgets.QScrollArea()
        self.channel_scroll_area.setWidgetResizable(True)
        self.channel_scroll_area.setFixedHeight(150) # Limit height
        rmp_chan_widget = QtWidgets.QWidget()
        self.channel_checkbox_layout = QtWidgets.QVBoxLayout(rmp_chan_widget)
        self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.channel_scroll_area.setWidget(rmp_chan_widget)
        rmp_config_layout.addWidget(self.channel_scroll_area)

        # RMP Parameters
        rmp_param_layout = QtWidgets.QFormLayout()
        rmp_param_layout.setContentsMargins(5, 5, 5, 5)
        self.start_time_edit = QtWidgets.QLineEdit("0.0")
        self.start_time_edit.setValidator(QtGui.QDoubleValidator())
        self.start_time_edit.setToolTip("Baseline Start (s)")
        rmp_param_layout.addRow("Baseline Start (s):", self.start_time_edit)
        self.end_time_edit = QtWidgets.QLineEdit("0.1")
        self.end_time_edit.setValidator(QtGui.QDoubleValidator())
        self.end_time_edit.setToolTip("Baseline End (s)")
        rmp_param_layout.addRow("Baseline End (s):", self.end_time_edit)
        rmp_config_layout.addLayout(rmp_param_layout)

        rmp_config_layout.addStretch(1)
        self.run_button = QtWidgets.QPushButton("Calculate RMP")
        self.run_button.setEnabled(False)
        rmp_config_layout.addWidget(self.run_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        controls_layout.addWidget(rmp_config_group)
        controls_widget.setFixedWidth(400) # Keep consistent width
        rmp_main_layout.addWidget(controls_widget)

        # --- Results ---
        rmp_results_group = QtWidgets.QGroupBox("RMP Results")
        rmp_results_layout = QtWidgets.QVBoxLayout(rmp_results_group)
        self.results_textedit = QtWidgets.QTextEdit()
        self.results_textedit.setReadOnly(True)
        self.results_textedit.setPlaceholderText("Select channels and run analysis...")
        rmp_results_layout.addWidget(self.results_textedit)
        rmp_main_layout.addWidget(rmp_results_group, stretch=1)

        self.setLayout(rmp_main_layout)

    def _connect_signals(self):
        """Connect signals specific to RMP tab widgets."""
        self.start_time_edit.textChanged.connect(self._update_run_button_state)
        self.end_time_edit.textChanged.connect(self._update_run_button_state)
        self.run_button.clicked.connect(self._run_rmp_analysis)
        # Channel checkboxes are connected in _update_channel_list

    # --- Overridden Methods from Base ---
    def update_state(self, current_recording_for_ui: Optional[Recording], analysis_items: List[Dict[str, Any]]):
        """Update state specific to the RMP tab."""
        # No need to call super().update_state() as it raises NotImplementedError
        self._current_recording_for_ui = current_recording_for_ui
        self._analysis_items_for_rmp = analysis_items
        has_items = bool(self._analysis_items_for_rmp)

        # Populate channel list based on the representative recording
        self._update_channel_list()

        # Enable/Disable controls
        # Channel list is enabled if we can display *any* channels
        self.channel_scroll_area.setEnabled(self._current_recording_for_ui is not None)
        # Params and run button enabled only if there are items to analyze
        self.start_time_edit.setEnabled(has_items)
        self.end_time_edit.setEnabled(has_items)
        self._update_run_button_state()

    # --- Private Helper Methods specific to RMP Tab ---
    def _update_channel_list(self):
        """Populate RMP channel list based on _current_recording_for_ui."""
        layout = self.channel_checkbox_layout
        checkboxes_dict = self.channel_checkboxes

        # Clear existing widgets and disconnect signals
        for checkbox in checkboxes_dict.values():
            try: checkbox.stateChanged.disconnect(self._update_run_button_state)
            except RuntimeError: pass
            checkbox.deleteLater()
        checkboxes_dict.clear()
        while layout.count():
            item = layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater()

        # Populate with new channels if a representative recording exists
        if self._current_recording_for_ui and self._current_recording_for_ui.channels:
            sorted_channels = sorted(self._current_recording_for_ui.channels.items(), key=lambda item: item[0])
            for chan_id, channel in sorted_channels:
                # Filter for voltage channels
                units_lower = getattr(channel, 'units', '').lower()
                if 'v' in units_lower or units_lower == 'unknown':
                    checkbox = QtWidgets.QCheckBox(f"{channel.name} ({chan_id}) [{channel.units}]")
                    checkbox.stateChanged.connect(self._update_run_button_state) # Connect run button update
                    layout.addWidget(checkbox)
                    checkboxes_dict[chan_id] = checkbox

    def _validate_params(self) -> bool:
        """Validates RMP parameters."""
        try:
            s = float(self.start_time_edit.text())
            e = float(self.end_time_edit.text())
            return e > s >= 0 # Basic check: end > start >= 0
        except (ValueError, TypeError):
            return False

    def _update_run_button_state(self):
        """Enables/disables the RMP Run button."""
        if not self.run_button: return
        have_items = bool(self._analysis_items_for_rmp)
        channels_selected = any(cb.isChecked() for cb in self.channel_checkboxes.values())
        params_valid = self._validate_params()
        self.run_button.setEnabled(have_items and channels_selected and params_valid)

    def _get_analysis_data_for_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Dict[str, Any]]]:
        """Reads a single file and extracts data for selected channels based on item info."""
        filepath = item['path']
        target_type = item['target_type']
        trial_index = item['trial_index'] # 0-based or None
        # Get channels selected *in this tab*
        selected_chan_ids = [cid for cid, cb in self.channel_checkboxes.items() if cb.isChecked()]
        item_results = {}
        if not selected_chan_ids: return None

        try:
            # Use the adapter stored in the explorer tab reference
            # Ensure adapter exists before calling
            if not hasattr(self._explorer_tab, 'neo_adapter') or not self._explorer_tab.neo_adapter:
                 log.error("NeoAdapter reference not found in ExplorerTab.")
                 return None
            recording = self._explorer_tab.neo_adapter.read_recording(filepath)
            if not recording or not recording.channels:
                 log.warning(f"Could not read or find channels in {filepath.name} for RMP analysis.")
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

                 # Select data based on the target type stored in the item
                 if target_type == "Current Trial":
                     if trial_index is not None and 0 <= trial_index < ch.num_trials:
                         data = ch.get_data(trial_index)
                         time = ch.get_relative_time_vector(trial_index)
                     else: log.warning(f"Invalid trial index {trial_index} for Ch {chan_id} in {filepath.name}")
                 elif target_type == "Average Trace":
                     data = ch.get_averaged_data()
                     time = ch.get_relative_averaged_time_vector()
                 elif target_type == "All Trials":
                     # For RMP, analyze average of all trials
                     data = ch.get_averaged_data()
                     time = ch.get_relative_averaged_time_vector()

                 if data is not None and time is not None:
                     item_results[chan_id] = {'data': data, 'time': time, 'units': units, 'rate': rate}
                 else:
                     log.warning(f"RMP: Could not get valid data/time for Ch {chan_id}, Item: {item}")

            return item_results if item_results else None

        except Exception as e:
            log.error(f"RMP: Error reading/processing file {filepath.name}: {e}", exc_info=True)
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
                self.results_textedit.setText("No analysis items selected from Explorer Tab."); return

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

                 item_channel_data = self._get_analysis_data_for_item(item)

                 if not item_channel_data:
                      results_str += "  (Could not retrieve data for this item)\n\n"
                      continue

                 item_processed = False
                 for chan_id, data_dict in item_channel_data.items():
                     # Get channel name from the representative recording loaded for UI, if possible
                     channel_name = chan_id # Default
                     if self._current_recording_for_ui and chan_id in self._current_recording_for_ui.channels:
                         channel_name = self._current_recording_for_ui.channels[chan_id].name

                     data = data_dict['data']; time = data_dict['time']; units = data_dict['units']
                     results_str += f"  Channel: {channel_name} ({chan_id})\n"
                     rmp = basic_features.calculate_rmp(data, time, baseline_window) # Call core function
                     if rmp is not None:
                         results_str += f"    RMP ({start_t:.3f}-{end_t:.3f}s): {rmp:.3f} {units}\n"
                         item_processed = True
                     else:
                         results_str += f"    RMP calculation failed.\n"
                 results_str += "\n" # Space between items
                 if item_processed: run_successful = True

            if not run_successful:
                 results_str += "\nNo channels successfully analyzed across all items."

            self.results_textedit.setText(results_str)
        except ValueError as ve: # Catch specific param errors
             log.warning(f"Invalid RMP parameters: {ve}")
             self.results_textedit.setText(f"*** Parameter Error: {ve} ***")
             QtWidgets.QMessageBox.warning(self, "Parameter Error", str(ve))
        except Exception as e:
             log.error(f"Error during RMP analysis: {e}", exc_info=True)
             self.results_textedit.setText(f"{results_str}\n\n*** ERROR: {e} ***")
             QtWidgets.QMessageBox.critical(self, "Analysis Error", f"Error:\n{e}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()