# src/Synaptipy/application/gui/explorer/config_panel.py
# -*- coding: utf-8 -*-
"""
Explorer Config Panel.
Contains the Left Panel widgets: Display Options, Manual Limits, Channel List, File Info.
"""
import logging
from typing import Dict, Any, Optional, Tuple

from PySide6 import QtCore, QtWidgets
from Synaptipy.core.data_model import Recording
from Synaptipy.shared.constants import APP_NAME

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
    
    # Manual Limits signals
    manual_limits_toggled = QtCore.Signal(bool)
    set_manual_limits_clicked = QtCore.Signal(dict) # Returns limits dict
    
    # Channel signals
    channel_visibility_changed = QtCore.Signal(str, bool)
    
    class PlotMode:
        OVERLAY_AVG = 0
        CYCLE_SINGLE = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.manual_limit_edits: Dict[str, Dict[str, QtWidgets.QLineEdit]] = {}
        self.manual_x_edits: Dict[str, QtWidgets.QLineEdit] = {}
        
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)
        # layout.setContentsMargins(0, 0, 0, 0)

        # 1. Display Options
        self._setup_display_options(layout)
        
        # 2. Manual Limits
        self._setup_manual_limits(layout)
        
        # 3. Channels
        self._setup_channel_list(layout)
        
        # 4. File Info
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

    def _setup_manual_limits(self, parent_layout):
        self.manual_limits_group = QtWidgets.QGroupBox("Manual Plot Limits")
        layout = QtWidgets.QVBoxLayout(self.manual_limits_group)
        
        self.enable_limits_cb = QtWidgets.QCheckBox("Enable Manual Limits")
        self.enable_limits_cb.toggled.connect(self._on_limits_toggled)
        layout.addWidget(self.enable_limits_cb)
        
        # Shared X
        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("X Min:"), 0, 0)
        self.xmin_edit = QtWidgets.QLineEdit()
        self.xmin_edit.setPlaceholderText("Auto")
        self.xmin_edit.setEnabled(False)
        grid.addWidget(self.xmin_edit, 0, 1)
        
        grid.addWidget(QtWidgets.QLabel("X Max:"), 1, 0)
        self.xmax_edit = QtWidgets.QLineEdit()
        self.xmax_edit.setPlaceholderText("Auto")
        self.xmax_edit.setEnabled(False)
        grid.addWidget(self.xmax_edit, 1, 1)
        
        self.manual_x_edits = {'min': self.xmin_edit, 'max': self.xmax_edit}
        
        layout.addLayout(grid)
        layout.addWidget(QtWidgets.QLabel("Y Limits:"))
        
        # Scroll Area for Channels
        self.y_limits_scroll = QtWidgets.QScrollArea()
        self.y_limits_scroll.setWidgetResizable(True)
        self.y_limits_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.y_limits_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.y_limits_widget = QtWidgets.QWidget()
        self.y_limits_layout = QtWidgets.QVBoxLayout(self.y_limits_widget)
        self.y_limits_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        
        self.y_limits_scroll.setWidget(self.y_limits_widget)
        layout.addWidget(self.y_limits_scroll)
        
        # Set Button
        self.set_limits_btn = QtWidgets.QPushButton("Set Manual Limits from Fields")
        self.set_limits_btn.clicked.connect(self._collect_and_emit_limits)
        layout.addWidget(self.set_limits_btn)
        
        parent_layout.addWidget(self.manual_limits_group)

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
        self._rebuild_manual_limits(recording)
        self._rebuild_channel_list(recording)
        
        if recording:
            self.lbl_filename.setText(recording.source_file.name)
            rate = recording.sampling_rate
            self.lbl_rate.setText(f"{rate:.2f} Hz" if rate else "N/A")
            dur = recording.duration
            self.lbl_duration.setText(f"{dur:.2f} s" if dur else "N/A")
            n_ch = len(recording.channels)
            n_tr = getattr(recording, 'max_trials', 0)
            self.lbl_channels.setText(f"{n_ch} / {n_tr}")
        else:
            self.lbl_filename.setText("N/A")
            self.lbl_rate.setText("N/A")
            self.lbl_duration.setText("N/A")
            self.lbl_channels.setText("N/A")

    def _rebuild_manual_limits(self, recording):
        # Clear
        while self.y_limits_layout.count():
            item = self.y_limits_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.manual_limit_edits.clear()
        
        if not recording:
             self.y_limits_layout.addWidget(QtWidgets.QLabel("Load data..."))
             return
             
        # Rebuild
        sorted_chans = sorted(recording.channels.items(), key=lambda x: str(x[0]))
        first = True
        
        for cid, chan in sorted_chans:
            if not first:
                 sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.Shape.HLine); self.y_limits_layout.addWidget(sep)
            first = False
            
            self.y_limits_layout.addWidget(QtWidgets.QLabel(f"{chan.name or cid}:"))
            grid_w = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(grid_w)
            grid.setContentsMargins(0,0,0,0)
            
            grid.addWidget(QtWidgets.QLabel("Y Min:"), 0, 0)
            grid.addWidget(QtWidgets.QLabel("Y Max:"), 0, 1)
            
            ymin = QtWidgets.QLineEdit(); ymin.setPlaceholderText("Auto")
            ymax = QtWidgets.QLineEdit(); ymax.setPlaceholderText("Auto")
            
            # Use current enabled state
            enabled = self.enable_limits_cb.isChecked()
            ymin.setEnabled(enabled); ymax.setEnabled(enabled)
            
            grid.addWidget(ymin, 1, 0)
            grid.addWidget(ymax, 1, 1)
            
            self.manual_limit_edits[cid] = {'ymin': ymin, 'ymax': ymax}
            self.y_limits_layout.addWidget(grid_w)

    def _rebuild_channel_list(self, recording):
        # Clear
        while self.channel_list_layout.count():
             item = self.channel_list_layout.takeAt(0)
             if item.widget(): item.widget().deleteLater()
        self.channel_checkboxes.clear()
        
        if not recording: return
        
        sorted_chans = sorted(recording.channels.items(), key=lambda x: str(x[0]))
        for cid, chan in sorted_chans:
            name = f"{chan.name}" if chan.name else f"Ch {cid}"
            cb = QtWidgets.QCheckBox(name)
            cb.setChecked(True)
            cb.toggled.connect(lambda checked, c=cid: self.channel_visibility_changed.emit(c, checked))
            self.channel_list_layout.addWidget(cb)
            self.channel_checkboxes[cid] = cb

    def _on_limits_toggled(self, checked):
        state = checked
        self.xmin_edit.setEnabled(state)
        self.xmax_edit.setEnabled(state)
        for d in self.manual_limit_edits.values():
            d['ymin'].setEnabled(state)
            d['ymax'].setEnabled(state)
        self.manual_limits_toggled.emit(state)

    def _collect_and_emit_limits(self):
        # Collect values
        limits = {
            'x_min': self.xmin_edit.text(),
            'x_max': self.xmax_edit.text(),
            'channels': {}
        }
        for cid, edits in self.manual_limit_edits.items():
            limits['channels'][cid] = {
                'y_min': edits['ymin'].text(),
                'y_max': edits['ymax'].text()
            }
        self.set_manual_limits_clicked.emit(limits)

    def _update_visibility(self):
        # Toggle buttons based on mode if needed
        # e.g. Select Trial button is only for Cycle mode
        pass # Implemented in Controller if needed, but UI can do it too
        is_cycle = (self.plot_mode_combo.currentIndex() == self.PlotMode.CYCLE_SINGLE)
        self.select_trial_btn.setEnabled(is_cycle)
        self.show_avg_btn.setEnabled(is_cycle)
        self.clear_sel_btn.setEnabled(is_cycle)

    def update_selection_label(self, selected_indices):
        if not selected_indices:
            self.selected_label.setText("Selected: None")
        else:
            txt = ", ".join(map(str, sorted(list(selected_indices))))
            self.selected_label.setText(f"Selected: {txt}")

