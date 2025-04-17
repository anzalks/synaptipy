# src/Synaptipy/application/gui/analysis_tabs/rin_tab.py
# -*- coding: utf-8 -*-
"""Analysis tab for calculating Input Resistance (Rin)."""

import logging
import numpy as np
from PySide6 import QtWidgets, QtCore
from typing import Optional, Dict, Any, List

# Use relative imports within the same package
from .base import BaseAnalysisTab
from ....core.data_model import Recording, Channel
from ....infrastructure.file_readers import NeoAdapter
from ....core.analysis.intrinsic_properties import calculate_rin

log = logging.getLogger(__name__)

class RinAnalysisTab(BaseAnalysisTab):
    """Widget for Input Resistance calculation."""
    display_name = "Input Resistance (Rin)"

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__(neo_adapter=neo_adapter, parent=parent)
        self.rin_channel_combo: Optional[QtWidgets.QComboBox] = None
        self.rin_trial_combo: Optional[QtWidgets.QComboBox] = None
        self.baseline_start_spin: Optional[QtWidgets.QDoubleSpinBox] = None
        self.baseline_end_spin: Optional[QtWidgets.QDoubleSpinBox] = None
        self.response_start_spin: Optional[QtWidgets.QDoubleSpinBox] = None
        self.response_end_spin: Optional[QtWidgets.QDoubleSpinBox] = None
        self.current_amp_spin: Optional[QtWidgets.QDoubleSpinBox] = None
        self.calculate_button: Optional[QtWidgets.QPushButton] = None
        self.result_label: Optional[QtWidgets.QLabel] = None
        self._setup_ui()

    def get_display_name(self) -> str:
        return self.display_name

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QFormLayout()

        self._setup_analysis_item_selector(form_layout)

        self.rin_channel_combo = QtWidgets.QComboBox()
        self.rin_trial_combo = QtWidgets.QComboBox()

        self.baseline_start_spin = QtWidgets.QDoubleSpinBox()
        self.baseline_end_spin = QtWidgets.QDoubleSpinBox()
        self.response_start_spin = QtWidgets.QDoubleSpinBox()
        self.response_end_spin = QtWidgets.QDoubleSpinBox()
        self.current_amp_spin = QtWidgets.QDoubleSpinBox()
        self.calculate_button = QtWidgets.QPushButton("Calculate Rin")
        self.result_label = QtWidgets.QLabel("Rin: ---")

        for spin in [self.baseline_start_spin, self.baseline_end_spin, self.response_start_spin, self.response_end_spin]:
            spin.setDecimals(3); spin.setRange(0, 1e6); spin.setSuffix(" s")
        self.current_amp_spin.setDecimals(3); self.current_amp_spin.setRange(-1e6, 1e6); self.current_amp_spin.setSuffix(" pA")

        form_layout.addRow("Target Channel (for Rin):", self.rin_channel_combo)
        form_layout.addRow("Target Trial (for Rin):", self.rin_trial_combo)
        form_layout.addRow("Current Step Amp (delta I):", self.current_amp_spin)
        form_layout.addRow("Baseline Window (t):", self._create_hbox(self.baseline_start_spin, self.baseline_end_spin))
        form_layout.addRow("Response Window (t):", self._create_hbox(self.response_start_spin, self.response_end_spin))

        layout.addLayout(form_layout)
        layout.addWidget(self.calculate_button)
        layout.addWidget(self.result_label)
        layout.addStretch()

        self.calculate_button.clicked.connect(self._perform_calculation)

    def _create_hbox(self, w1, w2):
        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(w1); hbox.addWidget(QtWidgets.QLabel("to")); hbox.addWidget(w2)
        widget = QtWidgets.QWidget(); widget.setLayout(hbox); hbox.setContentsMargins(0,0,0,0)
        return widget

    def _update_ui_for_selected_item(self):
        log.debug(f"{self.display_name}: Updating UI for selected item.")
        self.rin_channel_combo.blockSignals(True)
        self.rin_trial_combo.blockSignals(True)
        try:
            self.rin_channel_combo.clear()
            self.rin_trial_combo.clear()
            self.result_label.setText("Rin: ---")

            can_calculate = False
            recording = self._selected_item_recording
            if recording and recording.channels:
                voltage_channels = []
                for chan_id, channel in recording.channels.items():
                    if channel.units and ('V' in channel.units or 'v' in channel.units):
                        voltage_channels.append((f"{channel.name} ({chan_id})", chan_id))
                
                if voltage_channels:
                    for name, chan_id in voltage_channels:
                        self.rin_channel_combo.addItem(name, userData=chan_id)
                    
                    try: self.rin_channel_combo.currentIndexChanged.disconnect()
                    except RuntimeError: pass
                    self.rin_channel_combo.currentIndexChanged.connect(self._update_rin_trial_combo)
                    
                    self.rin_channel_combo.setCurrentIndex(0)
                    self._update_rin_trial_combo()
                    can_calculate = self.rin_trial_combo.count() > 0
                else:
                    self.rin_channel_combo.addItem("No Voltage Channels Found")
                    self.rin_trial_combo.addItem("N/A")
            else:
                self.rin_channel_combo.addItem("Load Data Item First")
                self.rin_trial_combo.addItem("N/A")

            self.rin_channel_combo.setEnabled(can_calculate)
            self.rin_trial_combo.setEnabled(can_calculate)
            self.calculate_button.setEnabled(can_calculate)
            for w in [self.baseline_start_spin, self.baseline_end_spin,
                      self.response_start_spin, self.response_end_spin, self.current_amp_spin]:
                w.setEnabled(can_calculate)
        finally:
            self.rin_channel_combo.blockSignals(False)
            self.rin_trial_combo.blockSignals(False)

    def _update_rin_trial_combo(self):
        self.rin_trial_combo.blockSignals(True)
        try:
            self.rin_trial_combo.clear()
            recording = self._selected_item_recording
            if not recording: 
                self.rin_trial_combo.addItem("N/A"); self.rin_trial_combo.setEnabled(False); return
            
            chan_id = self.rin_channel_combo.currentData()
            if not chan_id: 
                self.rin_trial_combo.addItem("N/A"); self.rin_trial_combo.setEnabled(False); return

            channel = recording.channels.get(chan_id)
            if channel and channel.num_trials > 0:
                self.rin_trial_combo.addItems([f"Trial {i}" for i in range(channel.num_trials)])
                self.rin_trial_combo.setEnabled(True)
                self.calculate_button.setEnabled(True)
                for w in [self.baseline_start_spin, self.baseline_end_spin,
                          self.response_start_spin, self.response_end_spin, self.current_amp_spin]:
                    w.setEnabled(True)
            else:
                self.rin_trial_combo.addItem("No Trials")
                self.rin_trial_combo.setEnabled(False)
                self.calculate_button.setEnabled(False)
                for w in [self.baseline_start_spin, self.baseline_end_spin,
                          self.response_start_spin, self.response_end_spin, self.current_amp_spin]:
                    w.setEnabled(False)
        finally:
            self.rin_trial_combo.blockSignals(False)

    def _perform_calculation(self):
        recording = self._selected_item_recording
        if not recording: 
            self.result_label.setText("Rin: Load Data Item First")
            return

        chan_id = self.rin_channel_combo.currentData()
        trial_index = self.rin_trial_combo.currentIndex()

        if not chan_id or trial_index < 0: 
            self.result_label.setText("Rin: Select Channel/Trial")
            return

        channel = recording.channels.get(chan_id)
        if not channel:
            self.result_label.setText("Rin: Channel not found in loaded data")
            return

        voltage_trace = channel.get_data(trial_index)
        time_vector = channel.get_relative_time_vector(trial_index)

        if voltage_trace is None or time_vector is None:
            self.result_label.setText("Rin: Invalid data for selected trial")
            return

        baseline_win = (self.baseline_start_spin.value(), self.baseline_end_spin.value())
        response_win = (self.response_start_spin.value(), self.response_end_spin.value())
        current_amp = self.current_amp_spin.value()

        if baseline_win[0] >= baseline_win[1] or response_win[0] >= response_win[1]:
            self.result_label.setText("Rin: Invalid time windows")
            return
        if current_amp == 0:
            self.result_label.setText("Rin: Current Amp cannot be 0")
            return

        log.debug(f"Calculating Rin for Selected Item {self._selected_item_index}, Ch: {chan_id}, Trial: {trial_index}, dI: {current_amp}")
        try:
            rin_value = calculate_rin(voltage_trace, time_vector, current_amp, baseline_win, response_win)
            if rin_value is not None:
                self.result_label.setText(f"Rin: {rin_value:.2f} MΩ")
            else:
                self.result_label.setText("Rin: Calculation failed (check logs)")
        except Exception as e:
            log.exception("Error during Rin calculation UI call.")
            self.result_label.setText(f"Rin: Error - {e}")

ANALYSIS_TAB_CLASS = RinAnalysisTab 