# src/Synaptipy/application/gui/explorer/config_panel.py
# -*- coding: utf-8 -*-
"""
Explorer Config Panel.
Contains the Left Panel widgets: Display Options, Manual Limits, Channel List, File Info.
"""
import logging
from typing import Dict, Optional

from PySide6 import QtCore, QtWidgets, QtGui
from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)


class ExplorerConfigPanel(QtWidgets.QWidget):
    """
    Panel for configuration and status display.
    """

    plot_mode_changed = QtCore.Signal(int)
    downsample_toggled = QtCore.Signal(bool)

    # Average selection signals
    select_current_trial_clicked = QtCore.Signal()
    clear_avg_selection_clicked = QtCore.Signal()
    show_selected_avg_toggled = QtCore.Signal(bool)

    # Trial Selection signals
    trial_selection_requested = QtCore.Signal(int, int)  # gap, start_index
    trial_selection_reset_requested = QtCore.Signal()

    # Channel signals
    channel_visibility_changed = QtCore.Signal(str, bool)

    # Live Analysis Signals
    threshold_changed = QtCore.Signal(float)
    refractory_changed = QtCore.Signal(float)

    class PlotMode:
        OVERLAY_AVG = 0
        CYCLE_SINGLE = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}

        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)
        # layout.setContentsMargins(0, 0, 0, 0)

        # 1. Display Options
        self._setup_display_options(layout)

        # 2. Trial Selection (Replaces Manual Limits)
        self._setup_trial_selection(layout)

        # 3. Channels
        self._setup_channel_list(layout)

        # 4. Analysis Controls (New)
        self._setup_analysis_controls(layout)

        # 5. File Info
        self._setup_file_info(layout)

        layout.addStretch()

    def _setup_display_options(self, parent_layout):
        group = QtWidgets.QGroupBox("Display Options")
        layout = QtWidgets.QVBoxLayout(group)

        # Plot Mode
        pm_layout = QtWidgets.QHBoxLayout()
        pm_layout.addWidget(QtWidgets.QLabel("Plot Mode:"))
        self.plot_mode_combo = QtWidgets.QComboBox()
        self.plot_mode_combo.addItems(["Overlay All + Avg", "Cycle Single Trial"])
        self.plot_mode_combo.currentIndexChanged.connect(self.plot_mode_changed.emit)
        self.plot_mode_combo.currentIndexChanged.connect(self._update_visibility)
        pm_layout.addWidget(self.plot_mode_combo)
        layout.addLayout(pm_layout)

        # Downsample
        self.downsample_cb = QtWidgets.QCheckBox("Auto Downsample Plot")
        self.downsample_cb.setChecked(True)
        self.downsample_cb.toggled.connect(self.downsample_toggled.emit)
        layout.addWidget(self.downsample_cb)

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Average Controls
        layout.addWidget(QtWidgets.QLabel("Manual Trial Averaging (Cycle Mode):"))
        self.select_trial_btn = QtWidgets.QPushButton("Add Current Trial to Avg Set")
        self.select_trial_btn.clicked.connect(self.select_current_trial_clicked.emit)
        layout.addWidget(self.select_trial_btn)

        self.selected_label = QtWidgets.QLabel("Selected: None")
        self.selected_label.setWordWrap(True)
        layout.addWidget(self.selected_label)

        h_layout = QtWidgets.QHBoxLayout()
        self.clear_sel_btn = QtWidgets.QPushButton("Clear Avg Set")
        self.clear_sel_btn.clicked.connect(self.clear_avg_selection_clicked.emit)
        h_layout.addWidget(self.clear_sel_btn)

        self.show_avg_btn = QtWidgets.QPushButton("Plot Selected Avg")
        self.show_avg_btn.setCheckable(True)
        self.show_avg_btn.toggled.connect(self.show_selected_avg_toggled.emit)
        h_layout.addWidget(self.show_avg_btn)
        layout.addLayout(h_layout)

        parent_layout.addWidget(group)

    def _setup_trial_selection(self, parent_layout):
        group = QtWidgets.QGroupBox("Plot Selected Trials")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(10)

        # Input Row
        in_layout = QtWidgets.QHBoxLayout()
        in_layout.addWidget(QtWidgets.QLabel("Trial Gap (Skip N):"))
        self.nth_trial_input = QtWidgets.QLineEdit()
        self.nth_trial_input.setPlaceholderText("e.g. 0=All, 1=Every 2nd")
        self.nth_trial_input.setValidator(QtGui.QIntValidator(0, 9999))
        in_layout.addWidget(self.nth_trial_input)

        in_layout.addWidget(QtWidgets.QLabel("Start Trial:"))
        self.start_trial_input = QtWidgets.QLineEdit()
        self.start_trial_input.setPlaceholderText("0")
        self.start_trial_input.setValidator(QtGui.QIntValidator(0, 9999))
        self.start_trial_input.setText("0")
        in_layout.addWidget(self.start_trial_input)

        layout.addLayout(in_layout)

        # Buttons
        self.plot_selected_btn = QtWidgets.QPushButton("Plot Selected")
        self.plot_selected_btn.clicked.connect(self._on_plot_selected_clicked)
        self.plot_selected_btn.setToolTip("Filter trials to show only every Nth trial.")
        layout.addWidget(self.plot_selected_btn)

        self.reset_selection_btn = QtWidgets.QPushButton("Reset Trial Selection")
        self.reset_selection_btn.clicked.connect(self.trial_selection_reset_requested.emit)
        self.reset_selection_btn.setToolTip("Reset to show all trials (raw data).")
        layout.addWidget(self.reset_selection_btn)

        parent_layout.addWidget(group)

    def _setup_channel_list(self, parent_layout):
        self.channel_group = QtWidgets.QGroupBox("Channels")
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)

        self.channel_list_widget = QtWidgets.QWidget()
        self.channel_list_layout = QtWidgets.QVBoxLayout(self.channel_list_widget)
        self.channel_list_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self.channel_list_widget)
        layout = QtWidgets.QVBoxLayout(self.channel_group)
        layout.addWidget(scroll)

        parent_layout.addWidget(self.channel_group)

    def _setup_analysis_controls(self, parent_layout):
        group = QtWidgets.QGroupBox("Live Analysis")
        layout = QtWidgets.QFormLayout(group)
        
        # Threshold
        self.threshold_spin = QtWidgets.QDoubleSpinBox()
        self.threshold_spin.setRange(-1000.0, 1000.0)
        self.threshold_spin.setValue(-20.0)
        self.threshold_spin.setSuffix(" mV")
        self.threshold_spin.valueChanged.connect(self.threshold_changed.emit)
        layout.addRow("Threshold:", self.threshold_spin)
        
        # Refractory
        self.refractory_spin = QtWidgets.QDoubleSpinBox()
        self.refractory_spin.setRange(0.0, 100.0)
        self.refractory_spin.setValue(2.0)
        self.refractory_spin.setSuffix(" ms")
        self.refractory_spin.setSingleStep(0.1)
        self.refractory_spin.valueChanged.connect(self.refractory_changed.emit)
        layout.addRow("Refractory:", self.refractory_spin)
        
        parent_layout.addWidget(group)

    def _setup_file_info(self, parent_layout):
        group = QtWidgets.QGroupBox("File Information")
        layout = QtWidgets.QFormLayout(group)

        self.lbl_filename = QtWidgets.QLabel("N/A")
        self.lbl_rate = QtWidgets.QLabel("N/A")
        self.lbl_duration = QtWidgets.QLabel("N/A")
        self.lbl_channels = QtWidgets.QLabel("N/A")

        layout.addRow("File:", self.lbl_filename)
        layout.addRow("Sampling Rate:", self.lbl_rate)
        layout.addRow("Duration:", self.lbl_duration)
        layout.addRow("Channels / Trials:", self.lbl_channels)

        parent_layout.addWidget(group)

    def rebuild(self, recording: Optional[Recording]):
        self._rebuild_channel_list(recording)

        if recording:
            self.lbl_filename.setText(recording.source_file.name)
            rate = recording.sampling_rate
            self.lbl_rate.setText(f"{rate:.2f} Hz" if rate else "N/A")
            dur = recording.duration
            self.lbl_duration.setText(f"{dur:.2f} s" if dur else "N/A")
            n_ch = len(recording.channels)
            n_tr = getattr(recording, "max_trials", 0)
            self.lbl_channels.setText(f"{n_ch} / {n_tr}")
        else:
            self.lbl_filename.setText("N/A")
            self.lbl_rate.setText("N/A")
            self.lbl_duration.setText("N/A")
            self.lbl_channels.setText("N/A")

    def _rebuild_channel_list(self, recording):
        # Clear
        while self.channel_list_layout.count():
            item = self.channel_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.channel_checkboxes.clear()

        if not recording:
            return

        sorted_chans = sorted(recording.channels.items(), key=lambda x: str(x[0]))
        for cid, chan in sorted_chans:
            name = f"{chan.name}" if chan.name else f"Ch {cid}"
            cb = QtWidgets.QCheckBox(name)
            cb.setChecked(True)
            cb.toggled.connect(lambda checked, c=cid: self.channel_visibility_changed.emit(c, checked))
            self.channel_list_layout.addWidget(cb)
            self.channel_checkboxes[cid] = cb

    def _on_plot_selected_clicked(self):
        text = self.nth_trial_input.text().strip()
        if not text:
            return

        text_start = self.start_trial_input.text().strip()

        try:
            n = int(text)
            start_idx = int(text_start) if text_start else 0

            if n >= 0 and start_idx >= 0:
                self.trial_selection_requested.emit(n, start_idx)
        except ValueError:
            pass

    def _update_visibility(self):
        # Toggle buttons based on mode if needed
        # e.g. Select Trial button is only for Cycle mode
        pass  # Implemented in Controller if needed, but UI can do it too
        is_cycle = self.plot_mode_combo.currentIndex() == self.PlotMode.CYCLE_SINGLE
        self.select_trial_btn.setEnabled(is_cycle)
        self.show_avg_btn.setEnabled(is_cycle)
        self.clear_sel_btn.setEnabled(is_cycle)

    def update_selection_label(self, selected_indices):
        if not selected_indices:
            self.selected_label.setText("Selected: None")
        else:
            txt = ", ".join(map(str, sorted(list(selected_indices))))
            self.selected_label.setText(f"Selected: {txt}")
