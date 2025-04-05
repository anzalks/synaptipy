# src/Synaptipy/application/gui/analysis_tabs/spike_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting spikes using a simple threshold.
"""
import logging
from typing import Optional, List, Dict, Any
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets

from .base import BaseAnalysisTab
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.core.analysis import spike_analysis

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.spike_tab')

class SpikeAnalysisTab(BaseAnalysisTab):
    """QWidget for Threshold-based Spike Detection."""

    def __init__(self, explorer_tab_ref, parent=None):
        super().__init__(explorer_tab_ref, parent)

        # UI References specific to Spike
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.channel_scroll_area: Optional[QtWidgets.QScrollArea] = None
        self.channel_checkbox_layout: Optional[QtWidgets.QVBoxLayout] = None
        self.trial_mode_combo: Optional[QtWidgets.QComboBox] = None
        self.trial_single_spinbox: Optional[QtWidgets.QSpinBox] = None
        self.trial_range_start_spinbox: Optional[QtWidgets.QSpinBox] = None
        self.trial_range_end_spinbox: Optional[QtWidgets.QSpinBox] = None
        self.threshold_edit: Optional[QtWidgets.QLineEdit] = None
        self.refractory_edit: Optional[QtWidgets.QLineEdit] = None
        self.run_button: Optional[QtWidgets.QPushButton] = None
        self.results_textedit: Optional[QtWidgets.QTextEdit] = None

        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent

    def get_display_name(self) -> str:
        return "Spike Detection (Threshold)"

    def _setup_ui(self):
        """Create UI elements for the Spike analysis tab."""
        main_layout = QtWidgets.QHBoxLayout(self)
        controls_widget = QtWidgets.QWidget(); controls_layout = QtWidgets.QVBoxLayout(controls_widget)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        config_group = QtWidgets.QGroupBox("Spike Detection Configuration"); config_layout = QtWidgets.QVBoxLayout(config_group)
        chan_label = QtWidgets.QLabel("Channel(s) for Spikes:"); config_layout.addWidget(chan_label)
        self.channel_scroll_area = QtWidgets.QScrollArea(); self.channel_scroll_area.setWidgetResizable(True); self.channel_scroll_area.setFixedHeight(150)
        chan_widget = QtWidgets.QWidget(); self.channel_checkbox_layout = QtWidgets.QVBoxLayout(chan_widget); self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.channel_scroll_area.setWidget(chan_widget); config_layout.addWidget(self.channel_scroll_area)
        trial_layout = QtWidgets.QHBoxLayout(); trial_layout.addWidget(QtWidgets.QLabel("Data Source:"))
        self.trial_mode_combo = QtWidgets.QComboBox(); self.trial_mode_combo.addItems(self.TRIAL_MODES); trial_layout.addWidget(self.trial_mode_combo)
        self.trial_single_spinbox = QtWidgets.QSpinBox(); self.trial_single_spinbox.setMinimum(1); self.trial_single_spinbox.setPrefix("Trial: "); trial_layout.addWidget(self.trial_single_spinbox)
        self.trial_range_start_spinbox = QtWidgets.QSpinBox(); self.trial_range_start_spinbox.setMinimum(1); self.trial_range_start_spinbox.setPrefix("From: "); trial_layout.addWidget(self.trial_range_start_spinbox)
        self.trial_range_end_spinbox = QtWidgets.QSpinBox(); self.trial_range_end_spinbox.setMinimum(1); self.trial_range_end_spinbox.setPrefix("To: "); trial_layout.addWidget(self.trial_range_end_spinbox)
        config_layout.addLayout(trial_layout)
        param_layout = QtWidgets.QFormLayout(); param_layout.setContentsMargins(5, 5, 5, 5)
        self.threshold_edit = QtWidgets.QLineEdit("0.0"); self.threshold_edit.setValidator(QtGui.QDoubleValidator()); self.threshold_edit.setToolTip("Voltage threshold")
        param_layout.addRow("Threshold:", self.threshold_edit)
        self.refractory_edit = QtWidgets.QLineEdit("2.0"); self.refractory_edit.setValidator(QtGui.QDoubleValidator(0, 1000, 3)); self.refractory_edit.setToolTip("Refractory Period (ms)")
        param_layout.addRow("Refractory (ms):", self.refractory_edit)
        config_layout.addLayout(param_layout); config_layout.addStretch(1)
        self.run_button = QtWidgets.QPushButton("Detect Spikes"); self.run_button.setEnabled(False)
        config_layout.addWidget(self.run_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        controls_layout.addWidget(config_group); controls_widget.setFixedWidth(400)
        main_layout.addWidget(controls_widget)
        results_group = QtWidgets.QGroupBox("Spike Results"); results_layout = QtWidgets.QVBoxLayout(results_group)
        self.results_textedit = QtWidgets.QTextEdit(); self.results_textedit.setReadOnly(True); self.results_textedit.setPlaceholderText("Spike detection results...")
        results_layout.addWidget(self.results_textedit); main_layout.addWidget(results_group, stretch=1)
        self.setLayout(main_layout)
        self._update_trial_widget_visibility()

    def _connect_signals(self):
        self.trial_mode_combo.currentIndexChanged.connect(self._on_trial_mode_changed)
        self.trial_mode_combo.currentIndexChanged.connect(self.update_state)
        self.trial_single_spinbox.valueChanged.connect(self.update_state)
        self.trial_range_start_spinbox.valueChanged.connect(self.update_state)
        self.trial_range_end_spinbox.valueChanged.connect(self.update_state)
        self.threshold_edit.textChanged.connect(self.update_state)
        self.refractory_edit.textChanged.connect(self.update_state)
        self.run_button.clicked.connect(self._run_spike_analysis)
        # Channel checkboxes connected in update_state/_update_channel_list

    def update_state(self):
        """Update state specific to the Spike tab."""
        super().update_state() # Call base method
        has_data = self._current_recording is not None
        self._update_channel_list()
        self.channel_scroll_area.setEnabled(has_data)
        self.trial_mode_combo.setEnabled(has_data)
        self.threshold_edit.setEnabled(has_data)
        self.refractory_edit.setEnabled(has_data)
        self._update_trial_widget_visibility(has_data)
        self._update_run_button_state()

    def _update_channel_list(self):
        """Populate Spike channel list."""
        layout = self.channel_checkbox_layout
        checkboxes_dict = self.channel_checkboxes
        for checkbox in checkboxes_dict.values():
            try: checkbox.stateChanged.disconnect(self.update_state)
            except RuntimeError: pass
            checkbox.deleteLater()
        checkboxes_dict.clear()
        while layout.count(): item = layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        if self._current_recording and self._current_recording.channels:
            sorted_channels = sorted(self._current_recording.channels.items(), key=lambda item: item[0])
            for chan_id, channel in sorted_channels:
                units_lower = getattr(channel, 'units', '').lower()
                if 'v' in units_lower or units_lower == 'unknown': # Filter for voltage channels
                    checkbox = QtWidgets.QCheckBox(f"{channel.name} ({chan_id}) [{channel.units}]")
                    checkbox.stateChanged.connect(self.update_state)
                    layout.addWidget(checkbox)
                    checkboxes_dict[chan_id] = checkbox

    def _update_trial_widget_visibility(self, has_data: bool = True):
        """Shows/hides Spike trial widgets and sets limits."""
        if not has_data:
            self.trial_single_spinbox.setVisible(False); self.trial_range_start_spinbox.setVisible(False); self.trial_range_end_spinbox.setVisible(False)
            self.trial_single_spinbox.setEnabled(False); self.trial_range_start_spinbox.setEnabled(False); self.trial_range_end_spinbox.setEnabled(False)
            return
        selected_mode = self.trial_mode_combo.currentText()
        is_single = selected_mode == "Single Trial"; is_range = selected_mode == "Trial Range"
        self.trial_single_spinbox.setVisible(is_single); self.trial_range_start_spinbox.setVisible(is_range); self.trial_range_end_spinbox.setVisible(is_range)
        self.trial_single_spinbox.setEnabled(is_single); self.trial_range_start_spinbox.setEnabled(is_range); self.trial_range_end_spinbox.setEnabled(is_range)
        max_t = self._current_recording.max_trials if self._current_recording else 0
        max_spinbox_val = max(1, max_t)
        self.trial_single_spinbox.setMaximum(max_spinbox_val); self.trial_range_start_spinbox.setMaximum(max_spinbox_val); self.trial_range_end_spinbox.setMaximum(max_spinbox_val)
        if max_t <= 0: self.trial_single_spinbox.setEnabled(False); self.trial_range_start_spinbox.setEnabled(False); self.trial_range_end_spinbox.setEnabled(False)
        elif is_range and self.trial_range_end_spinbox.value() < self.trial_range_start_spinbox.value(): self.trial_range_end_spinbox.setValue(self.trial_range_start_spinbox.value())

    def _on_trial_mode_changed(self):
        self._update_trial_widget_visibility(self._current_recording is not None)

    def _validate_params(self) -> bool:
        """Validates parameters for Spike Detection."""
        try: float(self.threshold_edit.text()); r=float(self.refractory_edit.text()); return r>=0
        except (ValueError, TypeError): return False

    def _update_run_button_state(self):
        """Enables/disables the Spike Run button."""
        if not self.run_button: return
        have_data = self._current_recording is not None
        channels_selected = any(cb.isChecked() for cb in self.channel_checkboxes.values())
        params_valid = self._validate_params()
        trial_mode = self.trial_mode_combo.currentText(); trials_valid = False; max_trials = self._current_recording.max_trials if have_data else 0
        if max_trials > 0:
            if trial_mode == "Single Trial": trials_valid = True
            elif trial_mode == "Trial Range": trials_valid = self.trial_range_start_spinbox.value() <= self.trial_range_end_spinbox.value()
            elif trial_mode == "All Trials": trials_valid = True
            elif trial_mode == "Average Trace": trials_valid = True
        elif trial_mode == "Average Trace": trials_valid = True
        self.run_button.setEnabled(have_data and channels_selected and trials_valid and params_valid)

    def _get_analysis_data(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Retrieves data specifically for the selections in the Spike tab."""
        if not self._current_recording: return None
        selected_ids = [cid for cid, cb in self.channel_checkboxes.items() if cb.isChecked()] # Use Spike dict
        if not selected_ids: log.warning("No channels selected for Spikes."); return None
        mode = self.trial_mode_combo.currentText(); analysis_data = {} # Use Spike combo

        for cid in selected_ids:
            ch = self._current_recording.channels.get(cid);
            if not ch: continue
            data: Optional[np.ndarray] = None
            time: Optional[np.ndarray] = None
            units = ch.units
            rate = ch.sampling_rate

            try:
                if mode == "Single Trial":
                    idx = self.trial_single_spinbox.value() - 1 # Use Spike spinbox
                    if 0 <= idx < ch.num_trials:
                        data = ch.get_data(idx)
                        time = ch.get_relative_time_vector(idx)
                    else:
                        log.warning(f"Invalid single trial index {idx+1} for Ch {cid}"); continue

                elif mode == "Trial Range":
                    start_idx = self.trial_range_start_spinbox.value() - 1 # Use Spike spinboxes
                    end_idx = self.trial_range_end_spinbox.value() - 1
                    if 0 <= start_idx <= end_idx < ch.num_trials:
                        trials = [t for i in range(start_idx, end_idx + 1) if (t := ch.get_data(i)) is not None]
                        if not trials:
                            log.warning(f"No valid trials in range {start_idx+1}-{end_idx+1} for Ch {cid}"); continue

                        first_len = trials[0].shape[0]
                        if all(t.shape[0] == first_len for t in trials):
                            data = np.mean(np.stack(trials), axis=0)
                            time = ch.get_relative_time_vector(start_idx)
                            if time is not None and time.shape[0] != first_len and rate and rate > 0:
                                log.warning(f"Time vector length mismatch Ch {cid}. Regenerating."); time = np.linspace(0, first_len/rate, first_len, endpoint=False)
                            elif time is None and rate and rate > 0:
                                time = np.linspace(0, first_len/rate, first_len, endpoint=False)
                        else:
                            log.warning(f"Range length mismatch Ch {cid}. Cannot average."); continue
                    else:
                         log.warning(f"Invalid trial range {start_idx+1}-{end_idx+1} for Ch {cid}"); continue

                elif mode == "All Trials" or mode == "Average Trace":
                    data = ch.get_averaged_data()
                    time = ch.get_relative_averaged_time_vector()

                if data is not None and time is not None:
                    analysis_data[cid] = {'data': data, 'time': time, 'units': units, 'rate': rate}
                else:
                     log.warning(f"Could not get valid data/time for Ch {cid}, Mode: {mode}")
            except Exception as e:
                 log.error(f"Error getting data Ch {cid}: {e}", exc_info=True)
        return analysis_data if analysis_data else None


    def _run_spike_analysis(self):
        """Runs Spike Detection analysis and displays results."""
        log.debug("Run Spike Analysis clicked.")
        self.results_textedit.clear()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        results_str = f"--- Analysis Results: Spike Detection (Threshold) ---\n\n"
        try:
            selected_data = self._get_analysis_data()
            if not selected_data:
                self.results_textedit.setText("Error: Could not retrieve valid data."); QtWidgets.QMessageBox.warning(self, "Data Error", "Could not retrieve data."); return

            threshold = float(self.threshold_edit.text())
            refractory_ms = float(self.refractory_edit.text())

            for chan_id, data_dict in selected_data.items():
                channel = self._current_recording.channels[chan_id]; data = data_dict['data']; time = data_dict['time']; units = data_dict['units']; rate = data_dict['rate']
                results_str += f"Channel: {channel.name} ({chan_id})\n"
                refractory_samples = int(refractory_ms * rate / 1000.0) if rate and rate > 0 else 0
                spike_indices, spike_times = spike_analysis.detect_spikes_threshold(data, time, threshold, refractory_samples) # Call core function
                num_spikes = len(spike_indices)
                results_str += f"  Spike Count (Thr={threshold:.2f}{units}, Refr={refractory_ms:.1f}ms): {num_spikes}\n"
                if num_spikes > 0:
                    if num_spikes > 1: isis = np.diff(spike_times) * 1000; mean_isi=np.mean(isis); std_isi=np.std(isis); results_str += f"    Mean ISI: {mean_isi:.2f} ms, Std ISI: {std_isi:.2f} ms\n"
                    # Optionally list first few spike times
                    times_str = ", ".join([f"{t:.4f}" for t in spike_times[:min(5, num_spikes)]])
                    results_str += f"    First Spike Times (s): {times_str}{'...' if num_spikes > 5 else ''}\n"
                else: results_str += f"    No spikes detected.\n"
                results_str += "-"*20 + "\n"

            self.results_textedit.setText(results_str)
        except Exception as e:
             log.error(f"Error during Spike analysis: {e}", exc_info=True)
             self.results_textedit.setText(f"{results_str}\n\n*** ERROR: {e} ***"); QtWidgets.QMessageBox.critical(self, "Analysis Error", f"Error:\n{e}")
        finally: QtWidgets.QApplication.restoreOverrideCursor()