# src/Synaptipy/application/gui/explorer_tab.py
# -*- coding: utf-8 -*-
"""
Explorer Tab widget for the Synaptipy GUI.
Contains all UI and logic for browsing, plotting, and interacting with recording data.
"""
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set
import uuid
from datetime import datetime, timezone
from functools import partial

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

# --- Synaptipy Imports / Dummies ---
from .dummy_classes import (
    Recording, Channel, NeoAdapter, NWBExporter, VisConstants,
    SynaptipyError, FileReadError, UnsupportedFormatError, ExportError,
    SYNAPTIPY_AVAILABLE
)
# --- Other Imports ---
from .nwb_dialog import NwbMetadataDialog
try:
    import tzlocal
except ImportError:
    tzlocal = None

log = logging.getLogger('Synaptipy.application.gui.explorer_tab')

# --- PyQtGraph Configuration ---
pg.setConfigOption('imageAxisOrder', 'row-major')
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# --- ExplorerTab Class ---
class ExplorerTab(QtWidgets.QWidget):
    """QWidget containing the data exploration UI and logic."""
    # --- Constants ---
    class PlotMode: OVERLAY_AVG = 0; CYCLE_SINGLE = 1
    SLIDER_RANGE_MIN = 1; SLIDER_RANGE_MAX = 100
    SLIDER_DEFAULT_VALUE = SLIDER_RANGE_MIN
    MIN_ZOOM_FACTOR = 0.01; SCROLLBAR_MAX_RANGE = 10000

    _selected_avg_pen_width = (VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1) if (VisConstants and hasattr(VisConstants, 'DEFAULT_PLOT_PEN_WIDTH')) else 2
    SELECTED_AVG_PEN = pg.mkPen('g', width=_selected_avg_pen_width, name="Selected Avg")

    # --- Signals ---
    open_file_requested = QtCore.Signal()

    # --- Initialization ---
    def __init__(self, neo_adapter: NeoAdapter, nwb_exporter: NWBExporter, status_bar: QtWidgets.QStatusBar, parent=None):
        super().__init__(parent)
        log.debug("Initializing ExplorerTab")
        self.neo_adapter = neo_adapter
        self.nwb_exporter = nwb_exporter
        self.status_bar = status_bar

        # --- Initialize State Variables ---
        self.current_recording: Optional[Recording] = None
        self.file_list: List[Path] = []
        self.current_file_index: int = -1
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.selected_average_plot_items: Dict[str, pg.PlotDataItem] = {}
        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG
        self.current_trial_index: int = 0
        self.max_trials_current_recording: int = 0
        self.y_axes_locked: bool = True
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_y_ranges: Dict[str, Optional[Tuple[float, float]]] = {}
        self.individual_y_sliders: Dict[str, QtWidgets.QSlider] = {}
        self.individual_y_slider_labels: Dict[str, QtWidgets.QLabel] = {}
        self.individual_y_scrollbars: Dict[str, QtWidgets.QScrollBar] = {}
        self._updating_scrollbars: bool = False
        self._updating_viewranges: bool = False
        self._updating_limit_fields: bool = False
        self.selected_trial_indices: Set[int] = set()
        self.manual_limits_enabled: bool = False
        self.manual_x_limits: Optional[Tuple[float, float]] = None
        self.manual_y_limits: Optional[Tuple[float, float]] = None
        self.manual_limit_x_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_x_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_y_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_y_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.set_manual_limits_button: Optional[QtWidgets.QPushButton] = None
        self.enable_manual_limits_checkbox: Optional[QtWidgets.QCheckBox] = None

        self._setup_ui()
        self._connect_signals()
        self._update_ui_state()
        self._update_limit_fields()

    # =========================================================================
    # UI Setup (_setup_ui)
    # =========================================================================
    def _setup_ui(self):
        log.debug("Setting up ExplorerTab UI...")
        main_layout = QtWidgets.QHBoxLayout(self)
        self.setLayout(main_layout)

        # --- Left Panel ---
        left_panel_widget = QtWidgets.QWidget()
        left_panel_layout = QtWidgets.QVBoxLayout(left_panel_widget)
        left_panel_layout.setSpacing(10)
        left_panel_widget.setFixedWidth(250)

        file_op_group = QtWidgets.QGroupBox("Load Data")
        file_op_layout = QtWidgets.QHBoxLayout(file_op_group)
        self.open_button_ui = QtWidgets.QPushButton("Open File...")
        file_op_layout.addWidget(self.open_button_ui)
        left_panel_layout.addWidget(file_op_group)

        display_group = QtWidgets.QGroupBox("Display Options")
        display_layout = QtWidgets.QVBoxLayout(display_group)
        plot_mode_layout = QtWidgets.QHBoxLayout()
        plot_mode_layout.addWidget(QtWidgets.QLabel("Plot Mode:"))
        self.plot_mode_combobox = QtWidgets.QComboBox()
        self.plot_mode_combobox.addItems(["Overlay All + Avg", "Cycle Single Trial"])
        self.plot_mode_combobox.setCurrentIndex(self.current_plot_mode)
        plot_mode_layout.addWidget(self.plot_mode_combobox)
        display_layout.addLayout(plot_mode_layout)
        self.downsample_checkbox = QtWidgets.QCheckBox("Auto Downsample Plot")
        self.downsample_checkbox.setChecked(True)
        self.downsample_checkbox.setToolTip("Enable automatic downsampling for performance.")
        display_layout.addWidget(self.downsample_checkbox)
        sep1 = QtWidgets.QFrame()
        sep1.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep1.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        display_layout.addWidget(sep1)
        display_layout.addWidget(QtWidgets.QLabel("Manual Trial Averaging (Cycle Mode):"))
        self.select_trial_button = QtWidgets.QPushButton("Add Current Trial to Avg Set")
        self.select_trial_button.setToolTip("Add/Remove trial")
        display_layout.addWidget(self.select_trial_button)
        self.selected_trials_display = QtWidgets.QLabel("Selected: None")
        self.selected_trials_display.setWordWrap(True)
        display_layout.addWidget(self.selected_trials_display)
        clear_avg_layout = QtWidgets.QHBoxLayout()
        self.clear_selection_button = QtWidgets.QPushButton("Clear Avg Set")
        self.clear_selection_button.setToolTip("Clear selection")
        clear_avg_layout.addWidget(self.clear_selection_button)
        self.show_selected_average_button = QtWidgets.QPushButton("Plot Selected Avg")
        self.show_selected_average_button.setToolTip("Toggle selected avg plot")
        self.show_selected_average_button.setCheckable(True)
        clear_avg_layout.addWidget(self.show_selected_average_button)
        display_layout.addLayout(clear_avg_layout)
        left_panel_layout.addWidget(display_group)

        manual_limits_group = QtWidgets.QGroupBox("Manual Plot Limits")
        manual_limits_layout = QtWidgets.QVBoxLayout(manual_limits_group)
        manual_limits_layout.setSpacing(5)
        self.enable_manual_limits_checkbox = QtWidgets.QCheckBox("Enable Manual Limits")
        self.enable_manual_limits_checkbox.setToolTip("Lock axes")
        manual_limits_layout.addWidget(self.enable_manual_limits_checkbox)
        limits_grid_layout = QtWidgets.QGridLayout()
        limits_grid_layout.setSpacing(3)
        self.manual_limit_x_min_edit = QtWidgets.QLineEdit()
        self.manual_limit_x_max_edit = QtWidgets.QLineEdit()
        self.manual_limit_y_min_edit = QtWidgets.QLineEdit()
        self.manual_limit_y_max_edit = QtWidgets.QLineEdit()
        self.manual_limit_x_min_edit.setPlaceholderText("Auto")
        self.manual_limit_x_max_edit.setPlaceholderText("Auto")
        self.manual_limit_y_min_edit.setPlaceholderText("Auto")
        self.manual_limit_y_max_edit.setPlaceholderText("Auto")
        self.manual_limit_x_min_edit.setToolTip("X Min")
        self.manual_limit_x_max_edit.setToolTip("X Max")
        self.manual_limit_y_min_edit.setToolTip("Y Min")
        self.manual_limit_y_max_edit.setToolTip("Y Max")
        limits_grid_layout.addWidget(QtWidgets.QLabel("X Min:"), 0, 0)
        limits_grid_layout.addWidget(self.manual_limit_x_min_edit, 0, 1)
        limits_grid_layout.addWidget(QtWidgets.QLabel("X Max:"), 1, 0)
        limits_grid_layout.addWidget(self.manual_limit_x_max_edit, 1, 1)
        limits_grid_layout.addWidget(QtWidgets.QLabel("Y Min:"), 2, 0)
        limits_grid_layout.addWidget(self.manual_limit_y_min_edit, 2, 1)
        limits_grid_layout.addWidget(QtWidgets.QLabel("Y Max:"), 3, 0)
        limits_grid_layout.addWidget(self.manual_limit_y_max_edit, 3, 1)
        manual_limits_layout.addLayout(limits_grid_layout)
        self.set_manual_limits_button = QtWidgets.QPushButton("Set Manual Limits from Fields")
        self.set_manual_limits_button.setToolTip("Store values")
        manual_limits_layout.addWidget(self.set_manual_limits_button)
        left_panel_layout.addWidget(manual_limits_group)

        self.channel_select_group = QtWidgets.QGroupBox("Channels")
        self.channel_scroll_area = QtWidgets.QScrollArea()
        self.channel_scroll_area.setWidgetResizable(True)
        self.channel_select_widget = QtWidgets.QWidget()
        self.channel_checkbox_layout = QtWidgets.QVBoxLayout(self.channel_select_widget)
        self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.channel_scroll_area.setWidget(self.channel_select_widget)
        channel_group_layout = QtWidgets.QVBoxLayout(self.channel_select_group)
        channel_group_layout.addWidget(self.channel_scroll_area)
        left_panel_layout.addWidget(self.channel_select_group)

        meta_group = QtWidgets.QGroupBox("File Information")
        meta_layout = QtWidgets.QFormLayout(meta_group)
        self.filename_label = QtWidgets.QLabel("N/A")
        self.sampling_rate_label = QtWidgets.QLabel("N/A")
        self.channels_label = QtWidgets.QLabel("N/A")
        self.duration_label = QtWidgets.QLabel("N/A")
        meta_layout.addRow("File:", self.filename_label)
        meta_layout.addRow("Sampling Rate:", self.sampling_rate_label)
        meta_layout.addRow("Duration:", self.duration_label)
        meta_layout.addRow("Channels / Trials:", self.channels_label)
        left_panel_layout.addWidget(meta_group)
        left_panel_layout.addStretch()
        main_layout.addWidget(left_panel_widget, stretch=0)

        # --- Center Panel ---
        center_panel_widget = QtWidgets.QWidget()
        center_panel_layout = QtWidgets.QVBoxLayout(center_panel_widget)
        nav_layout = QtWidgets.QHBoxLayout()
        self.prev_file_button = QtWidgets.QPushButton("<< Prev File")
        self.next_file_button = QtWidgets.QPushButton("Next File >>")
        self.folder_file_index_label = QtWidgets.QLabel("")
        self.folder_file_index_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.prev_file_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.folder_file_index_label)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_file_button)
        center_panel_layout.addLayout(nav_layout)
        self.graphics_layout_widget = pg.GraphicsLayoutWidget()
        center_panel_layout.addWidget(self.graphics_layout_widget, stretch=1)
        self.x_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Horizontal)
        self.x_scrollbar.setFixedHeight(20)
        self.x_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
        center_panel_layout.addWidget(self.x_scrollbar)
        plot_controls_layout = QtWidgets.QHBoxLayout()
        view_group = QtWidgets.QGroupBox("View")
        view_layout = QtWidgets.QHBoxLayout(view_group)
        self.reset_view_button = QtWidgets.QPushButton("Reset View")
        self.reset_view_button.setToolTip("Reset zoom/pan")
        view_layout.addWidget(self.reset_view_button)
        plot_controls_layout.addWidget(view_group)
        x_zoom_group = QtWidgets.QGroupBox("X Zoom")
        x_zoom_layout = QtWidgets.QHBoxLayout(x_zoom_group)
        self.x_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.x_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.x_zoom_slider.setToolTip("X zoom")
        x_zoom_layout.addWidget(self.x_zoom_slider)
        plot_controls_layout.addWidget(x_zoom_group, stretch=1)
        trial_group = QtWidgets.QGroupBox("Trial (Cycle)")
        trial_layout = QtWidgets.QHBoxLayout(trial_group)
        self.prev_trial_button = QtWidgets.QPushButton("< Prev")
        self.next_trial_button = QtWidgets.QPushButton("Next >")
        self.trial_index_label = QtWidgets.QLabel("N/A")
        self.trial_index_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        trial_layout.addWidget(self.prev_trial_button)
        trial_layout.addWidget(self.trial_index_label)
        trial_layout.addWidget(self.next_trial_button)
        plot_controls_layout.addWidget(trial_group)
        center_panel_layout.addLayout(plot_controls_layout)
        main_layout.addWidget(center_panel_widget, stretch=1)

        # --- Right Panel ---
        y_controls_panel_widget = QtWidgets.QWidget()
        y_controls_panel_layout = QtWidgets.QHBoxLayout(y_controls_panel_widget)
        y_controls_panel_widget.setFixedWidth(220)
        y_controls_panel_layout.setContentsMargins(0, 0, 0, 0)
        y_controls_panel_layout.setSpacing(5)
        y_scroll_widget = QtWidgets.QWidget()
        y_scroll_layout = QtWidgets.QVBoxLayout(y_scroll_widget)
        y_scroll_layout.setContentsMargins(0,0,0,0)
        y_scroll_layout.setSpacing(5)
        y_scroll_group = QtWidgets.QGroupBox("Y Scroll")
        y_scroll_group_layout = QtWidgets.QVBoxLayout(y_scroll_group)
        y_scroll_layout.addWidget(y_scroll_group, stretch=1)
        self.global_y_scrollbar_widget = QtWidgets.QWidget()
        global_y_scrollbar_layout = QtWidgets.QVBoxLayout(self.global_y_scrollbar_widget)
        global_y_scrollbar_layout.setContentsMargins(0,0,0,0)
        global_y_scrollbar_layout.setSpacing(2)
        global_y_scrollbar_label = QtWidgets.QLabel("Global")
        global_y_scrollbar_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.global_y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Vertical)
        self.global_y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
        self.global_y_scrollbar.setToolTip("Y scroll (All)")
        global_y_scrollbar_layout.addWidget(global_y_scrollbar_label)
        global_y_scrollbar_layout.addWidget(self.global_y_scrollbar, stretch=1)
        y_scroll_group_layout.addWidget(self.global_y_scrollbar_widget, stretch=1)
        self.individual_y_scrollbars_container = QtWidgets.QWidget()
        self.individual_y_scrollbars_layout = QtWidgets.QVBoxLayout(self.individual_y_scrollbars_container)
        self.individual_y_scrollbars_layout.setContentsMargins(0, 5, 0, 0)
        self.individual_y_scrollbars_layout.setSpacing(10)
        self.individual_y_scrollbars_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        y_scroll_group_layout.addWidget(self.individual_y_scrollbars_container, stretch=1)
        y_controls_panel_layout.addWidget(y_scroll_widget, stretch=1)
        y_zoom_widget = QtWidgets.QWidget()
        y_zoom_layout = QtWidgets.QVBoxLayout(y_zoom_widget)
        y_zoom_layout.setContentsMargins(0,0,0,0)
        y_zoom_layout.setSpacing(5)
        y_zoom_group = QtWidgets.QGroupBox("Y Zoom")
        y_zoom_group_layout = QtWidgets.QVBoxLayout(y_zoom_group)
        y_zoom_layout.addWidget(y_zoom_group, stretch=1)
        self.y_lock_checkbox = QtWidgets.QCheckBox("Lock Y Axes")
        self.y_lock_checkbox.setChecked(self.y_axes_locked)
        self.y_lock_checkbox.setToolTip("Lock Y controls")
        y_zoom_group_layout.addWidget(self.y_lock_checkbox)
        self.global_y_slider_widget = QtWidgets.QWidget()
        global_y_slider_layout = QtWidgets.QVBoxLayout(self.global_y_slider_widget)
        global_y_slider_layout.setContentsMargins(0,0,0,0)
        global_y_slider_layout.setSpacing(2)
        global_y_slider_label = QtWidgets.QLabel("Global")
        global_y_slider_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.global_y_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        self.global_y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.global_y_slider.setToolTip("Y zoom (All)")
        global_y_slider_layout.addWidget(global_y_slider_label)
        global_y_slider_layout.addWidget(self.global_y_slider, stretch=1)
        y_zoom_group_layout.addWidget(self.global_y_slider_widget, stretch=1)
        self.individual_y_sliders_container = QtWidgets.QWidget()
        self.individual_y_sliders_layout = QtWidgets.QVBoxLayout(self.individual_y_sliders_container)
        self.individual_y_sliders_layout.setContentsMargins(0, 5, 0, 0)
        self.individual_y_sliders_layout.setSpacing(10)
        self.individual_y_sliders_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        y_zoom_group_layout.addWidget(self.individual_y_sliders_container, stretch=1)
        y_controls_panel_layout.addWidget(y_zoom_widget, stretch=1)
        main_layout.addWidget(y_controls_panel_widget, stretch=0)

        self._update_y_controls_visibility()
        self._update_selected_trials_display()
        self._update_zoom_scroll_enable_state()
        log.debug("ExplorerTab UI Setup complete.")

    # =========================================================================
    # Signal Connections (_connect_signals)
    # =========================================================================
    def _connect_signals(self):
        log.debug("Connecting ExplorerTab signals...")
        self.open_button_ui.clicked.connect(self.open_file_requested)
        self.downsample_checkbox.stateChanged.connect(self._trigger_plot_update)
        self.plot_mode_combobox.currentIndexChanged.connect(self._on_plot_mode_changed)
        self.reset_view_button.clicked.connect(self._reset_view)
        self.prev_trial_button.clicked.connect(self._prev_trial)
        self.next_trial_button.clicked.connect(self._next_trial)
        self.prev_file_button.clicked.connect(self._prev_file_folder)
        self.next_file_button.clicked.connect(self._next_file_folder)
        self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
        self.y_lock_checkbox.stateChanged.connect(self._on_y_lock_changed)
        self.global_y_slider.valueChanged.connect(self._on_global_y_zoom_changed)
        self.x_scrollbar.valueChanged.connect(self._on_x_scrollbar_changed)
        self.global_y_scrollbar.valueChanged.connect(self._on_global_y_scrollbar_changed)
        self.select_trial_button.clicked.connect(self._toggle_select_current_trial)
        self.clear_selection_button.clicked.connect(self._clear_avg_selection)
        self.show_selected_average_button.toggled.connect(self._toggle_plot_selected_average)
        if self.enable_manual_limits_checkbox: self.enable_manual_limits_checkbox.toggled.connect(self._on_manual_limits_toggled)
        if self.set_manual_limits_button: self.set_manual_limits_button.clicked.connect(self._on_set_limits_clicked)
        log.debug("ExplorerTab signal connections complete.")

    # =========================================================================
    # Public Methods for Interaction
    # =========================================================================
    def load_recording_data(self, filepath: Path, file_list: List[Path], current_index: int):
        log.info(f"ExplorerTab received request to load: {filepath.name} (Index: {current_index}/{len(file_list)})")
        self.file_list = file_list
        self.current_file_index = current_index
        self._load_and_display_file(filepath)

    def get_current_recording(self) -> Optional[Recording]:
        return self.current_recording

    def get_current_file_info(self) -> Tuple[Optional[Path], List[Path], int]:
        current_file = self.file_list[self.current_file_index] if 0 <= self.current_file_index < len(self.file_list) else None
        return current_file, self.file_list, self.current_file_index

    # =========================================================================
    # Reset & UI Creation
    # =========================================================================
    def _reset_ui_and_state_for_new_file(self):
        log.info("Resetting ExplorerTab UI and state for new file...")
        self._remove_selected_average_plots()
        self.selected_trial_indices.clear()
        self._update_selected_trials_display()
        if self.show_selected_average_button: self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        for checkbox in self.channel_checkboxes.values():
            try: checkbox.stateChanged.disconnect(self._trigger_plot_update)
            except (TypeError, RuntimeError): pass
        if hasattr(self, 'channel_checkbox_layout') and self.channel_checkbox_layout:
            while self.channel_checkbox_layout.count(): item = self.channel_checkbox_layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        self.channel_checkboxes.clear()
        if self.channel_select_group: self.channel_select_group.setEnabled(False)
        for plot in self.channel_plots.values():
            if plot and plot.getViewBox(): vb = plot.getViewBox();
            try: vb.sigXRangeChanged.disconnect()
            except (TypeError, RuntimeError): pass
            try: vb.sigYRangeChanged.disconnect()
            except (TypeError, RuntimeError): pass
        if hasattr(self, 'graphics_layout_widget') and self.graphics_layout_widget: self.graphics_layout_widget.clear()
        self.channel_plots.clear(); self.channel_plot_data_items.clear()
        for slider in self.individual_y_sliders.values():
             try: slider.valueChanged.disconnect()
             except (TypeError, RuntimeError): pass
        if hasattr(self, 'individual_y_sliders_layout') and self.individual_y_sliders_layout:
            while self.individual_y_sliders_layout.count(): item = self.individual_y_sliders_layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        self.individual_y_sliders.clear(); self.individual_y_slider_labels.clear()
        for scrollbar in self.individual_y_scrollbars.values():
            try: scrollbar.valueChanged.disconnect()
            except (TypeError, RuntimeError): pass
        if hasattr(self, 'individual_y_scrollbars_layout') and self.individual_y_scrollbars_layout:
            while self.individual_y_scrollbars_layout.count(): item = self.individual_y_scrollbars_layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        self.individual_y_scrollbars.clear()
        self.current_recording = None; self.max_trials_current_recording = 0; self.current_trial_index = 0
        self.base_x_range = None; self.base_y_ranges.clear()
        if self.x_zoom_slider: self.x_zoom_slider.blockSignals(True); self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.x_zoom_slider.blockSignals(False)
        if self.global_y_slider: self.global_y_slider.blockSignals(True); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.blockSignals(False)
        self.y_axes_locked = True
        if self.y_lock_checkbox: self.y_lock_checkbox.blockSignals(True); self.y_lock_checkbox.setChecked(self.y_axes_locked); self.y_lock_checkbox.blockSignals(False)
        self._reset_scrollbar(self.x_scrollbar); self._reset_scrollbar(self.global_y_scrollbar)
        self._update_y_controls_visibility(); self._clear_metadata_display(); self._update_trial_label()
        self._update_limit_fields(); self._update_zoom_scroll_enable_state(); self._update_ui_state()
        log.info("ExplorerTab UI and state reset complete.")

    def _reset_scrollbar(self, scrollbar: Optional[QtWidgets.QScrollBar]):
        if not scrollbar: return
        scrollbar.blockSignals(True)
        try: scrollbar.setRange(0, 0); scrollbar.setPageStep(self.SCROLLBAR_MAX_RANGE); scrollbar.setValue(0); scrollbar.setEnabled(False)
        finally: scrollbar.blockSignals(False)

    def _create_channel_ui(self):
        if not self.current_recording or not self.current_recording.channels: log.warning("Create channel UI: No data."); return
        if not all(hasattr(self, w) for w in ['channel_select_group', 'channel_checkbox_layout', 'graphics_layout_widget', 'individual_y_sliders_layout', 'individual_y_scrollbars_layout']): log.error("Create channel UI: Layouts missing."); return
        self.channel_select_group.setEnabled(True)
        sorted_items = sorted(self.current_recording.channels.items(), key=lambda item: str(item[0]))
        log.info(f"Creating UI for {len(sorted_items)} channels.")
        last_plot_item: Optional[pg.PlotItem] = None
        for i, (chan_id, channel) in enumerate(sorted_items):
            if chan_id in self.channel_checkboxes or chan_id in self.channel_plots: log.error(f"UI exists for {chan_id}, skipping."); continue
            checkbox = QtWidgets.QCheckBox(f"{channel.name or f'Ch {chan_id}'}"); checkbox.setChecked(True); checkbox.stateChanged.connect(self._trigger_plot_update)
            self.channel_checkbox_layout.addWidget(checkbox); self.channel_checkboxes[chan_id] = checkbox
            plot_item = self.graphics_layout_widget.addPlot(row=i, col=0); plot_item.setLabel('left', channel.name or f'Ch {chan_id}', units=channel.units or 'units')
            plot_item.showGrid(x=True, y=True, alpha=0.3); self.channel_plots[chan_id] = plot_item
            vb = plot_item.getViewBox(); vb.setMouseMode(pg.ViewBox.RectMode); vb._synaptipy_chan_id = chan_id
            vb.sigXRangeChanged.connect(self._handle_vb_xrange_changed); vb.sigYRangeChanged.connect(self._handle_vb_yrange_changed)
            vb.sigXRangeChanged.connect(lambda *a: self._trigger_limit_field_update()); vb.sigYRangeChanged.connect(lambda *a: self._trigger_limit_field_update())
            if last_plot_item: plot_item.setXLink(last_plot_item.getViewBox()); plot_item.hideAxis('bottom') # Link ViewBoxes
            last_plot_item = plot_item
            slider_widget = QtWidgets.QWidget(); slider_layout = QtWidgets.QVBoxLayout(slider_widget); slider_layout.setContentsMargins(0,0,0,0); slider_layout.setSpacing(2)
            lbl = QtWidgets.QLabel(f"{channel.name or chan_id[:4]}"); lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); lbl.setToolTip(f"Y Zoom {channel.name or chan_id}")
            self.individual_y_slider_labels[chan_id] = lbl; slider_layout.addWidget(lbl)
            slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical); slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX); slider.setValue(self.SLIDER_DEFAULT_VALUE)
            slider.setToolTip(f"Y Zoom {channel.name or chan_id}"); slider.valueChanged.connect(partial(self._on_individual_y_zoom_changed, chan_id))
            slider_layout.addWidget(slider, stretch=1); self.individual_y_sliders[chan_id] = slider; self.individual_y_sliders_layout.addWidget(slider_widget, stretch=1); slider_widget.setVisible(False)
            scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Vertical); scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE); scrollbar.setToolTip(f"Y Scroll {channel.name or chan_id}")
            scrollbar.valueChanged.connect(partial(self._on_individual_y_scrollbar_changed, chan_id)); self._reset_scrollbar(scrollbar); self.individual_y_scrollbars[chan_id] = scrollbar
            self.individual_y_scrollbars_layout.addWidget(scrollbar, stretch=1); scrollbar.setVisible(False)
        if last_plot_item: last_plot_item.setLabel('bottom', "Time", units='s'); last_plot_item.showAxis('bottom')
        log.info("Channel UI creation complete.")

    # =========================================================================
    # File Loading & Display Options
    # =========================================================================
    def _load_and_display_file(self, filepath: Path):
        if not filepath or not filepath.exists():
            log.error(f"Invalid file path: {filepath}")
            QtWidgets.QMessageBox.critical(self, "File Error", f"File not found or invalid:\n{filepath}") # Use self
            self._reset_ui_and_state_for_new_file(); self._update_ui_state(); return
        self.status_bar.showMessage(f"Loading '{filepath.name}'..."); QtWidgets.QApplication.processEvents()
        self._reset_ui_and_state_for_new_file(); self.current_recording = None
        try:
            log.info(f"Reading recording: {filepath}"); self.current_recording = self.neo_adapter.read_recording(filepath)
            log.info(f"Loaded: {filepath.name}"); self.max_trials_current_recording = getattr(self.current_recording, 'max_trials', 0)
            self._create_channel_ui(); self._update_metadata_display(); self._update_plot(); self._reset_view()
            self.status_bar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000)
        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e:
            log.error(f"Load failed '{filepath.name}': {e}", exc_info=False); QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load:\n{filepath.name}\n\nError: {e}") # Use self
            self._clear_metadata_display(); self.status_bar.showMessage(f"Error loading {filepath.name}.", 5000)
        except Exception as e:
            log.error(f"Unexpected load error '{filepath.name}': {e}", exc_info=True); QtWidgets.QMessageBox.critical(self, "Unexpected Error", f"Error loading:\n{filepath.name}\n\n{e}") # Use self
            self._clear_metadata_display(); self.status_bar.showMessage(f"Unexpected error loading {filepath.name}.", 5000)
        finally: self._update_zoom_scroll_enable_state(); self._update_ui_state();
        if self.manual_limits_enabled: self._apply_manual_limits()

    def _on_plot_mode_changed(self, index: int):
        new_mode = index;
        if new_mode == self.current_plot_mode: return
        log.info(f"Plot mode changed to index {index}")
        if self.selected_average_plot_items: self._remove_selected_average_plots()
        if self.show_selected_average_button: self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self.current_plot_mode = new_mode; self.current_trial_index = 0
        self._update_plot(); self._reset_view(); self._update_ui_state()

    def _trigger_plot_update(self):
        if not self.current_recording: return
        sender = self.sender(); is_channel_checkbox = isinstance(sender, QtWidgets.QCheckBox) and sender in self.channel_checkboxes.values()
        if is_channel_checkbox and self.selected_average_plot_items: self._remove_selected_average_plots()
        if is_channel_checkbox and self.show_selected_average_button: self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self._update_plot()
        if is_channel_checkbox: self._update_y_controls_visibility()
        # Check sender state *after* updating plot and controls
        if is_channel_checkbox and sender.isChecked():
            chan_id = next((k for k, v in self.channel_checkboxes.items() if v == sender), None)
            if chan_id: self._reset_single_plot_view(chan_id)

    # =========================================================================
    # Plotting Core & Metadata
    # =========================================================================
    def _clear_plot_data_only(self):
        cleared_count = 0
        for chan_id, plot_item in self.channel_plots.items():
            if not plot_item or plot_item.scene() is None: continue
            selected_avg = self.selected_average_plot_items.get(chan_id)
            items_to_remove = [item for item in plot_item.items if isinstance(item, (pg.PlotDataItem, pg.TextItem)) and item != selected_avg]
            for item in items_to_remove:
                try: plot_item.removeItem(item); cleared_count += 1
                except Exception: pass
        self.channel_plot_data_items.clear()

    def _update_plot(self):
        self._clear_plot_data_only()
        if not self.current_recording or not self.channel_plots: log.warning("Update plot: No data/plots."); self._update_ui_state(); return
        is_cycle_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        log.debug(f"Updating plots. Mode: {'Cycle' if is_cycle_mode else 'Overlay'}. Trial: {self.current_trial_index}")
        vis_const_available = VisConstants is not None
        _trial_color_str = getattr(VisConstants, 'TRIAL_COLOR', '#888888') if vis_const_available else '#888888'
        _trial_alpha_val = getattr(VisConstants, 'TRIAL_ALPHA', 70) if vis_const_available else 70
        _avg_color_str = getattr(VisConstants, 'AVERAGE_COLOR', '#EE4B2B') if vis_const_available else '#EE4B2B'
        _pen_width_val = getattr(VisConstants, 'DEFAULT_PLOT_PEN_WIDTH', 1) if vis_const_available else 1
        _ds_thresh_val = getattr(VisConstants, 'DOWNSAMPLING_THRESHOLD', 5000) if vis_const_available else 5000
        try:
            trial_qcolor = QtGui.QColor(_trial_color_str); alpha_int = max(0, min(255, int(_trial_alpha_val * 2.55)))
            trial_qcolor.setAlpha(alpha_int); trial_pen = pg.mkPen(trial_qcolor, width=_pen_width_val, name="Trial")
            log.debug(f"Trial pen: {trial_qcolor.name(QtGui.QColor.NameFormat.HexArgb)}")
        except Exception as e:
            log.error(f"Error creating trial_pen: {e}. Using fallback."); trial_pen = pg.mkPen((128, 128, 128, 80), width=1, name="Trial_Fallback")
        average_pen = pg.mkPen(_avg_color_str, width=_pen_width_val + 1, name="Average")
        single_trial_pen = pg.mkPen(_trial_color_str, width=_pen_width_val, name="Single Trial")
        enable_downsampling = self.downsample_checkbox.isChecked() if self.downsample_checkbox else False
        ds_threshold = _ds_thresh_val
        any_data_plotted = False; visible_plots: List[pg.PlotItem] = []
        for chan_id, plot_item in self.channel_plots.items():
            checkbox = self.channel_checkboxes.get(chan_id); channel = self.current_recording.channels.get(chan_id)
            if checkbox and checkbox.isChecked() and channel and plot_item:
                plot_item.setVisible(True); visible_plots.append(plot_item); channel_plotted = False
                if not is_cycle_mode:
                    for trial_idx in range(channel.num_trials):
                        data, time_vec = channel.get_data(trial_idx), channel.get_relative_time_vector(trial_idx)
                        if data is not None and time_vec is not None:
                            item = plot_item.plot(time_vec, data, pen=trial_pen); item.opts['autoDownsample'] = enable_downsampling; item.opts['autoDownsampleThreshold'] = ds_threshold
                            self.channel_plot_data_items.setdefault(chan_id, []).append(item); channel_plotted = True
                        else: log.warning(f"Missing data/time: trial {trial_idx+1}, Ch {chan_id}")
                    avg_data, avg_time_vec = channel.get_averaged_data(), channel.get_relative_averaged_time_vector()
                    if avg_data is not None and avg_time_vec is not None:
                        item = plot_item.plot(avg_time_vec, avg_data, pen=average_pen); item.opts['autoDownsample'] = enable_downsampling; item.opts['autoDownsampleThreshold'] = ds_threshold
                        self.channel_plot_data_items.setdefault(chan_id, []).append(item); channel_plotted = True
                else:
                    idx = min(self.current_trial_index, channel.num_trials - 1) if channel.num_trials > 0 else -1
                    if idx >= 0:
                        data, time_vec = channel.get_data(idx), channel.get_relative_time_vector(idx)
                        if data is not None and time_vec is not None:
                            item = plot_item.plot(time_vec, data, pen=single_trial_pen); item.opts['autoDownsample'] = enable_downsampling; item.opts['autoDownsampleThreshold'] = ds_threshold
                            self.channel_plot_data_items.setdefault(chan_id, []).append(item); channel_plotted = True
                        else: plot_item.addItem(pg.TextItem(f"Data Err\nTrial {idx+1}", color='r', anchor=(0.5, 0.5)))
                    else: plot_item.addItem(pg.TextItem("No Trials", color='orange', anchor=(0.5, 0.5)))
                if not channel_plotted: plot_item.addItem(pg.TextItem("No Trials" if channel.num_trials==0 else "Plot Err", color='orange' if channel.num_trials==0 else 'red', anchor=(0.5,0.5)))
                if channel_plotted: any_data_plotted = True
            elif plot_item: plot_item.hide()

        # --- Axis linking logic ---
        last_visible_plot = visible_plots[-1] if visible_plots else None
        for i, plot_item in enumerate(self.channel_plots.values()):
            is_visible = plot_item in visible_plots; is_last = plot_item == last_visible_plot
            plot_item.showAxis('bottom', show=is_last)
            bottom_axis = plot_item.getAxis('bottom')
            if is_last:
                 if bottom_axis: bottom_axis.setLabel("Time", units='s')
            elif bottom_axis and bottom_axis.labelText:
                 bottom_axis.setLabel(None)

            if is_visible:
                try:
                    visible_index = visible_plots.index(plot_item)
                    link_target = visible_plots[visible_index - 1].getViewBox() if visible_index > 0 else None
                    current_vb = plot_item.getViewBox()
                    if current_vb and hasattr(current_vb, 'linkedView') and current_vb.linkedView(0) != link_target:
                         plot_item.setXLink(link_target)
                    elif current_vb and not hasattr(current_vb, 'linkedView'):
                         plot_item.setXLink(link_target)
                except Exception as link_e:
                     current_chan_id = getattr(plot_item.getViewBox(), '_synaptipy_chan_id', f'plot_{i}')
                     log.warning(f"XLink Error for {current_chan_id}: {link_e}")
                     plot_item.setXLink(None)
            else:
                current_vb = plot_item.getViewBox()
                if current_vb and hasattr(current_vb, 'linkedView') and current_vb.linkedView(0) is not None:
                    plot_item.setXLink(None)

        self._update_trial_label(); self._update_ui_state(); log.debug(f"Plot update done. Plotted: {any_data_plotted}")

    def _update_metadata_display(self):
        if self.current_recording and all(hasattr(self, w) and getattr(self, w) for w in ['filename_label','sampling_rate_label','duration_label','channels_label']):
            rec = self.current_recording; self.filename_label.setText(rec.source_file.name); self.filename_label.setToolTip(str(rec.source_file))
            sr, dur, nc = getattr(rec,'sampling_rate',None), getattr(rec,'duration',None), getattr(rec,'num_channels','N/A')
            self.sampling_rate_label.setText(f"{sr:.2f} Hz" if sr else "N/A"); self.duration_label.setText(f"{dur:.3f} s" if dur else "N/A")
            self.channels_label.setText(f"{nc} ch / {self.max_trials_current_recording} trial(s)")
        else: self._clear_metadata_display()

    def _clear_metadata_display(self):
        if hasattr(self, 'filename_label') and self.filename_label: self.filename_label.setText("N/A"); self.filename_label.setToolTip("")
        if hasattr(self, 'sampling_rate_label') and self.sampling_rate_label: self.sampling_rate_label.setText("N/A")
        if hasattr(self, 'duration_label') and self.duration_label: self.duration_label.setText("N/A")
        if hasattr(self, 'channels_label') and self.channels_label: self.channels_label.setText("N/A")

    # =========================================================================
    # UI State Update
    # =========================================================================
    def _update_ui_state(self):
        if not hasattr(self, 'plot_mode_combobox'): return
        has_data=self.current_recording is not None; has_vis=any(p.isVisible() for p in self.channel_plots.values())
        is_folder=len(self.file_list)>1; is_cycle=has_data and self.current_plot_mode==self.PlotMode.CYCLE_SINGLE
        has_trials=has_data and self.max_trials_current_recording>0; has_sel=bool(self.selected_trial_indices); is_avg_plotted=bool(self.selected_average_plot_items)
        self.plot_mode_combobox.setEnabled(has_data)
        if self.downsample_checkbox: self.downsample_checkbox.setEnabled(has_data)
        can_sel=is_cycle and has_trials
        if self.select_trial_button: self.select_trial_button.setEnabled(can_sel); is_curr=self.current_trial_index in self.selected_trial_indices; self.select_trial_button.setText("Deselect Trial" if is_curr else "Add Trial")
        if self.clear_selection_button: self.clear_selection_button.setEnabled(has_sel)
        if self.show_selected_average_button: self.show_selected_average_button.setEnabled(has_sel); self.show_selected_average_button.setText("Hide Avg" if is_avg_plotted else "Plot Avg")
        man_lim_en=has_data
        if self.enable_manual_limits_checkbox:
            pg = self.enable_manual_limits_checkbox.parentWidget(); pg.setEnabled(man_lim_en) if isinstance(pg,QtWidgets.QGroupBox) else self.enable_manual_limits_checkbox.setEnabled(man_lim_en)
        if self.set_manual_limits_button: self.set_manual_limits_button.setEnabled(man_lim_en)
        lim_ed_en = man_lim_en
        if self.manual_limit_x_min_edit: self.manual_limit_x_min_edit.setEnabled(lim_ed_en)
        if self.manual_limit_x_max_edit: self.manual_limit_x_max_edit.setEnabled(lim_ed_en)
        if self.manual_limit_y_min_edit: self.manual_limit_y_min_edit.setEnabled(lim_ed_en)
        if self.manual_limit_y_max_edit: self.manual_limit_y_max_edit.setEnabled(lim_ed_en)
        if self.channel_select_group: self.channel_select_group.setEnabled(has_data)
        if self.prev_file_button: self.prev_file_button.setVisible(is_folder); self.prev_file_button.setEnabled(is_folder and self.current_file_index > 0)
        if self.next_file_button: self.next_file_button.setVisible(is_folder); self.next_file_button.setEnabled(is_folder and self.current_file_index < len(self.file_list) - 1)
        if self.folder_file_index_label: self.folder_file_index_label.setVisible(is_folder)
        if is_folder and self.folder_file_index_label: fname = self.file_list[self.current_file_index].name if 0 <= self.current_file_index < len(self.file_list) else "N/A"; self.folder_file_index_label.setText(f"{self.current_file_index+1}/{len(self.file_list)}: {fname}")
        elif self.folder_file_index_label: self.folder_file_index_label.setText("")
        if self.reset_view_button: self.reset_view_button.setEnabled(has_vis and not self.manual_limits_enabled)
        trial_nav_en=is_cycle and self.max_trials_current_recording>1
        if self.prev_trial_button: self.prev_trial_button.setEnabled(trial_nav_en and self.current_trial_index > 0)
        if self.next_trial_button: self.next_trial_button.setEnabled(trial_nav_en and self.current_trial_index < self.max_trials_current_recording - 1)
        if self.trial_index_label: self.trial_index_label.setVisible(is_cycle and has_trials)

    def _update_trial_label(self):
        if not hasattr(self, 'trial_index_label') or not self.trial_index_label: return
        if (self.current_recording and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0): self.trial_index_label.setText(f"{self.current_trial_index + 1}/{self.max_trials_current_recording}")
        else: self.trial_index_label.setText("N/A")

    # =========================================================================
    # Zoom & Scroll Controls
    # =========================================================================
    def _calculate_new_range(self, base_range: Optional[Tuple[float, float]], slider_value: int) -> Optional[Tuple[float, float]]:
        if base_range is None or base_range[0] is None or base_range[1] is None: return None
        try:
            m, M = base_range; c = (m+M)/2.0; s = max(abs(M-m), 1e-12)
            sl_m, sl_M = float(self.SLIDER_RANGE_MIN), float(self.SLIDER_RANGE_MAX)
            nz = (float(slider_value)-sl_m)/(sl_M-sl_m) if sl_M > sl_m else 0.0
            zf = max(self.MIN_ZOOM_FACTOR, min(1.0, 1.0 - nz * (1.0 - self.MIN_ZOOM_FACTOR)))
            ns = s*zf; nm = c-ns/2.0; nM = c+ns/2.0; return (nm, nM)
        except Exception as e: log.error(f"Error in _calculate_new_range: {e}"); return None

    def _on_x_zoom_changed(self, value: int):
        if self.manual_limits_enabled or self.base_x_range is None or self._updating_viewranges: return
        new_x = self._calculate_new_range(self.base_x_range, value)
        if new_x is None: return
        plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if plot and plot.getViewBox():
            vb=plot.getViewBox(); self._updating_viewranges=True
            try: vb.setXRange(new_x[0], new_x[1], padding=0)
            finally: self._updating_viewranges=False; self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_x)

    def _on_x_scrollbar_changed(self, value: int):
        if self.manual_limits_enabled or self.base_x_range is None or self._updating_scrollbars: return
        plot = next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
        if not plot: return
        vb=plot.getViewBox(); self._updating_viewranges=True
        try:
            cx = vb.viewRange()[0]; cs=max(abs(cx[1]-cx[0]), 1e-12); bs=max(abs(self.base_x_range[1]-self.base_x_range[0]), 1e-12)
            sr=max(0, bs-cs); f=float(value)/max(1, self.x_scrollbar.maximum()); nm=self.base_x_range[0]+f*sr
            nM=nm+cs # Fixed syntax error here
            vb.setXRange(nm, nM, padding=0)
        except Exception as e: log.error(f"Error in _on_x_scrollbar_changed: {e}")
        finally: self._updating_viewranges=False

    def _handle_vb_xrange_changed(self, vb: pg.ViewBox, new_range: Tuple[float, float]):
        if self.manual_limits_enabled and self.manual_x_limits and not self._updating_viewranges:
            self._updating_viewranges=True; vb.setXRange(self.manual_x_limits[0], self.manual_x_limits[1], padding=0); self._updating_viewranges=False; return
        if self._updating_viewranges or self.base_x_range is None: return
        self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_range)

    def _on_y_lock_changed(self, state: int):
        self.y_axes_locked = bool(state == QtCore.Qt.CheckState.Checked.value); log.info(f"Y-lock {'ON' if self.y_axes_locked else 'OFF'}.")
        self._update_y_controls_visibility(); self._update_ui_state(); self._update_zoom_scroll_enable_state()

    def _update_y_controls_visibility(self):
        if not all(hasattr(self, w) for w in ['global_y_slider_widget','global_y_scrollbar_widget','individual_y_sliders_container','individual_y_scrollbars_container']): return
        lock=self.y_axes_locked; any_vis=any(p.isVisible() for p in self.channel_plots.values())
        self.global_y_slider_widget.setVisible(lock and any_vis); self.global_y_scrollbar_widget.setVisible(lock and any_vis)
        self.individual_y_sliders_container.setVisible(not lock and any_vis); self.individual_y_scrollbars_container.setVisible(not lock and any_vis)
        if not any_vis: return
        vis_cids={ getattr(p.getViewBox(),'_synaptipy_chan_id',None) for p in self.channel_plots.values() if p.isVisible() and p.getViewBox() and hasattr(p.getViewBox(),'_synaptipy_chan_id')}; vis_cids.discard(None)
        en = not self.manual_limits_enabled
        if not lock:
            for cid, slider in self.individual_y_sliders.items(): cont=slider.parentWidget(); vis=cid in vis_cids; base=self.base_y_ranges.get(cid) is not None; cont.setVisible(vis); slider.setEnabled(vis and base and en)
            for cid, scroll in self.individual_y_scrollbars.items(): vis=cid in vis_cids; base=self.base_y_ranges.get(cid) is not None; scroll.setVisible(vis); can=scroll.maximum()>scroll.minimum(); scroll.setEnabled(vis and base and en and can)
        else:
            can_en=any(self.base_y_ranges.get(cid) is not None for cid in vis_cids)
            if self.global_y_slider: self.global_y_slider.setEnabled(can_en and en)
            if self.global_y_scrollbar: can=self.global_y_scrollbar.maximum()>self.global_y_scrollbar.minimum(); self.global_y_scrollbar.setEnabled(can_en and en and can)

    def _on_global_y_zoom_changed(self, value: int):
        if self.manual_limits_enabled or not self.y_axes_locked or self._updating_viewranges: return
        self._apply_global_y_zoom(value)

    def _apply_global_y_zoom(self, value: int):
        if self.manual_limits_enabled: return
        b_ref, n_ref = None, None; self._updating_viewranges=True
        try:
            for cid, p in self.channel_plots.items():
                if p.isVisible() and p.getViewBox():
                    base=self.base_y_ranges.get(cid)
                    if base is None: continue
                    new_y=self._calculate_new_range(base, value)
                    if new_y: p.getViewBox().setYRange(new_y[0], new_y[1], padding=0)
                    if b_ref is None and new_y is not None: b_ref, n_ref = base, new_y # Capture first valid
        except Exception as e: log.error(f"Error applying global Y zoom: {e}")
        finally: self._updating_viewranges=False
        if b_ref and n_ref: self._update_scrollbar_from_view(self.global_y_scrollbar, b_ref, n_ref)
        else: self._reset_scrollbar(self.global_y_scrollbar)

    def _on_global_y_scrollbar_changed(self, value: int):
        if self.manual_limits_enabled or not self.y_axes_locked or self._updating_scrollbars: return
        self._apply_global_y_scroll(value)

    def _apply_global_y_scroll(self, value: int):
        if self.manual_limits_enabled: return
        plot = next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
        if not plot: return
        self._updating_viewranges=True
        try:
            vb_ref=plot.getViewBox(); ref_cid=getattr(vb_ref,'_synaptipy_chan_id',None); ref_b=self.base_y_ranges.get(ref_cid)
            if ref_b is None or ref_b[0] is None or ref_b[1] is None: return
            curr_y=vb_ref.viewRange()[1]; curr_s=max(abs(curr_y[1]-curr_y[0]), 1e-12); ref_bs=max(abs(ref_b[1]-ref_b[0]), 1e-12)
            f=float(value)/max(1, self.global_y_scrollbar.maximum())
            for cid, p in self.channel_plots.items():
                if p.isVisible() and p.getViewBox():
                    b=self.base_y_ranges.get(cid)
                    if b is None or b[0] is None or b[1] is None: continue
                    bs=max(abs(b[1]-b[0]), 1e-12); sr=max(0, bs-curr_s); nm=b[0]+f*sr; nM=nm+curr_s
                    p.getViewBox().setYRange(nm, nM, padding=0)
        except Exception as e: log.error(f"Error applying global Y scroll: {e}")
        finally: self._updating_viewranges=False

    def _on_individual_y_zoom_changed(self, chan_id: str, value: int):
        if self.manual_limits_enabled or self.y_axes_locked or self._updating_viewranges: return
        p=self.channel_plots.get(chan_id); b=self.base_y_ranges.get(chan_id); s=self.individual_y_scrollbars.get(chan_id)
        if not p or not p.isVisible() or not p.getViewBox() or b is None or s is None: return
        new_y = self._calculate_new_range(b, value)
        if new_y:
             self._updating_viewranges=True
             try: p.getViewBox().setYRange(new_y[0], new_y[1], padding=0)
             except Exception as e: log.error(f"Error setting individual Y zoom {chan_id}: {e}")
             finally: self._updating_viewranges=False; self._update_scrollbar_from_view(s, b, new_y)

    def _on_individual_y_scrollbar_changed(self, chan_id: str, value: int):
        if self.manual_limits_enabled or self.y_axes_locked or self._updating_scrollbars: return
        p=self.channel_plots.get(chan_id); b=self.base_y_ranges.get(chan_id); s=self.individual_y_scrollbars.get(chan_id)
        if not p or not p.isVisible() or not p.getViewBox() or b is None or s is None: return
        vb=p.getViewBox(); self._updating_viewranges=True
        try:
            cy=vb.viewRange()[1]; cs=max(abs(cy[1]-cy[0]), 1e-12); bs=max(abs(b[1]-b[0]), 1e-12)
            sr=max(0, bs-cs); f=float(value)/max(1, s.maximum()); nm=b[0]+f*sr; nM=nm+cs
            vb.setYRange(nm, nM, padding=0)
        except Exception as e: log.error(f"Error handling individual Y scroll {chan_id}: {e}")
        finally: self._updating_viewranges=False

    def _handle_vb_yrange_changed(self, vb: pg.ViewBox, new_range: Tuple[float, float]):
        cid = getattr(vb,'_synaptipy_chan_id',None)
        if cid is None: return
        if self.manual_limits_enabled and self.manual_y_limits and not self._updating_viewranges:
            self._updating_viewranges=True; vb.setYRange(self.manual_y_limits[0], self.manual_y_limits[1], padding=0); self._updating_viewranges=False; return
        b=self.base_y_ranges.get(cid)
        if self._updating_viewranges or b is None: return
        if self.y_axes_locked:
            fvb = next((p.getViewBox() for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
            if vb == fvb: self._update_scrollbar_from_view(self.global_y_scrollbar, b, new_range)
        else:
             s=self.individual_y_scrollbars.get(cid)
             if s: self._update_scrollbar_from_view(s, b, new_range)

    def _update_scrollbar_from_view(self, scrollbar: QtWidgets.QScrollBar, base_range: Optional[Tuple[float,float]], view_range: Optional[Tuple[float, float]]):
        if self._updating_scrollbars or scrollbar is None: return
        if self.manual_limits_enabled or base_range is None or view_range is None: self._reset_scrollbar(scrollbar); return
        self._updating_scrollbars = True
        try:
            bm, bM=base_range; vm, vM=view_range; bs=max(abs(bM-bm),1e-12); vs=min(max(abs(vM-vm),1e-12),bs)
            ps=max(1, min(int((vs/bs)*self.SCROLLBAR_MAX_RANGE), self.SCROLLBAR_MAX_RANGE)); rm=max(0, self.SCROLLBAR_MAX_RANGE-ps)
            rp=vm-bm; srd=max(abs(bs-vs),1e-12); v=0
            if srd>1e-10: v=max(0, min(int((rp/srd)*rm),rm))
            scrollbar.blockSignals(True); scrollbar.setRange(0, rm); scrollbar.setPageStep(ps); scrollbar.setValue(v); scrollbar.setEnabled(rm > 0); scrollbar.blockSignals(False)
        except Exception as e: log.error(f"Error updating scrollbar: {e}"); self._reset_scrollbar(scrollbar)
        finally: self._updating_scrollbars=False

    # =========================================================================
    # View Reset
    # =========================================================================
    def _reset_view(self):
        if not self.current_recording: self._reset_ui_and_state_for_new_file(); self._update_ui_state(); return
        if self.manual_limits_enabled: self._apply_manual_limits(); self._update_ui_state(); return
        log.debug("Auto-ranging plots.")
        vis_map={ getattr(p.getViewBox(),'_synaptipy_chan_id',None):p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox() and hasattr(p.getViewBox(),'_synaptipy_chan_id')}; vis_map={k:v for k,v in vis_map.items() if k is not None}
        if not vis_map: self._reset_all_sliders(); self._update_limit_fields(); self._update_ui_state(); return
        first_cid, first_plot = next(iter(vis_map.items())); first_plot.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis)
        for plot in vis_map.values(): plot.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)
        QtCore.QTimer.singleShot(50, self._capture_base_ranges_after_reset)
        self._reset_all_sliders(); self._update_limit_fields(); self._update_y_controls_visibility(); self._update_zoom_scroll_enable_state(); self._update_ui_state()

    def _capture_base_ranges_after_reset(self):
        log.debug("Capturing base ranges...")
        vis_map={ getattr(p.getViewBox(),'_synaptipy_chan_id',None):p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox() and hasattr(p.getViewBox(),'_synaptipy_chan_id')}; vis_map={k:v for k,v in vis_map.items() if k is not None}
        if not vis_map: return
        first_cid, first_plot = next(iter(vis_map.items()))
        try:
             self.base_x_range=first_plot.getViewBox().viewRange()[0]
             if self.base_x_range: self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, self.base_x_range)
             else: self._reset_scrollbar(self.x_scrollbar)
        except Exception as e: log.error(f"Error capturing base X range: {e}"); self.base_x_range=None; self._reset_scrollbar(self.x_scrollbar)
        self.base_y_ranges.clear()
        for cid, p in vis_map.items():
            try:
                 by=p.getViewBox().viewRange()[1]; self.base_y_ranges[cid]=by
                 if not self.y_axes_locked:
                     s=self.individual_y_scrollbars.get(cid)
                     if s: self._update_scrollbar_from_view(s, by, by)
            except Exception as e:
                 log.error(f"Error capturing base Y range for {cid}: {e}")
                 if cid in self.base_y_ranges: del self.base_y_ranges[cid]
                 s=self.individual_y_scrollbars.get(cid);
                 if s: self._reset_scrollbar(s)
        if self.y_axes_locked:
            b_ref=self.base_y_ranges.get(first_cid)
            if b_ref: self._update_scrollbar_from_view(self.global_y_scrollbar, b_ref, b_ref)
            else: self._reset_scrollbar(self.global_y_scrollbar)
            for s in self.individual_y_scrollbars.values(): self._reset_scrollbar(s)
        else: self._reset_scrollbar(self.global_y_scrollbar)
        self._update_limit_fields(); self._update_y_controls_visibility()

    def _reset_all_sliders(self):
        sliders = [self.x_zoom_slider, self.global_y_slider] + list(self.individual_y_sliders.values())
        for s in sliders:
            if s: s.blockSignals(True); s.setValue(self.SLIDER_DEFAULT_VALUE); s.blockSignals(False)

    def _reset_single_plot_view(self, chan_id: str):
        if self.manual_limits_enabled: return
        plot = self.channel_plots.get(chan_id);
        if not plot or not plot.isVisible() or not plot.getViewBox(): return
        plot.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis); QtCore.QTimer.singleShot(50, lambda: self._capture_single_base_range_after_reset(chan_id))

    def _capture_single_base_range_after_reset(self, chan_id: str):
        plot=self.channel_plots.get(chan_id);
        if not plot or not plot.getViewBox() or not plot.isVisible(): return
        vb=plot.getViewBox(); ny=None
        try: ny=vb.viewRange()[1]; self.base_y_ranges[chan_id]=ny
        except Exception as e:
            log.error(f"Error capturing single base Y {chan_id}: {e}")
            if chan_id in self.base_y_ranges: del self.base_y_ranges[chan_id]; ny=None
        slider=self.individual_y_sliders.get(chan_id);
        if slider: slider.blockSignals(True); slider.setValue(self.SLIDER_DEFAULT_VALUE); slider.blockSignals(False)
        scroll=self.individual_y_scrollbars.get(chan_id)
        if scroll:
            if ny: self._update_scrollbar_from_view(scroll, ny, ny)
            else: self._reset_scrollbar(scroll)
        if self.y_axes_locked:
            f_plot=next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
            if f_plot and plot == f_plot:
                f_cid=getattr(f_plot.getViewBox(),'_synaptipy_chan_id',None); b_ref=self.base_y_ranges.get(f_cid)
                if b_ref: self._update_scrollbar_from_view(self.global_y_scrollbar, b_ref, b_ref)
                else: self._reset_scrollbar(self.global_y_scrollbar)
            if self.global_y_slider: self.global_y_slider.blockSignals(True); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.blockSignals(False)
        self._update_limit_fields(); self._update_y_controls_visibility()

    # =========================================================================
    # Navigation
    # =========================================================================
    def _next_trial(self):
        if self.current_plot_mode==self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording>0:
            if self.current_trial_index < self.max_trials_current_recording - 1:
                 self.current_trial_index+=1; self._update_plot();
                 if self.manual_limits_enabled: self._apply_manual_limits()
                 self._update_ui_state()
            else: self.status_bar.showMessage("Last trial.", 2000)

    def _prev_trial(self):
        if self.current_plot_mode==self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording>0:
            if self.current_trial_index > 0:
                 self.current_trial_index-=1; self._update_plot();
                 if self.manual_limits_enabled: self._apply_manual_limits()
                 self._update_ui_state()
            else: self.status_bar.showMessage("First trial.", 2000)

    def _next_file_folder(self):
        if self.file_list and self.current_file_index < len(self.file_list) - 1: self.current_file_index+=1; self._load_and_display_file(self.file_list[self.current_file_index])
        else: self.status_bar.showMessage("Last file.", 2000)

    def _prev_file_folder(self):
        if self.file_list and self.current_file_index > 0: self.current_file_index-=1; self._load_and_display_file(self.file_list[self.current_file_index])
        else: self.status_bar.showMessage("First file.", 2000)

    # =========================================================================
    # Multi-Trial Selection & Averaging
    # =========================================================================
    def _update_selected_trials_display(self):
        if not hasattr(self,'selected_trials_display') or not self.selected_trials_display: return
        if not self.selected_trial_indices: self.selected_trials_display.setText("Selected: None")
        else: idxs=sorted([i+1 for i in self.selected_trial_indices]); txt="Selected: "+", ".join(map(str,idxs)); self.selected_trials_display.setText(txt); self.selected_trials_display.setToolTip(txt)

    def _toggle_select_current_trial(self):
        if not self.current_recording or self.current_plot_mode!=self.PlotMode.CYCLE_SINGLE or not (0<=self.current_trial_index<self.max_trials_current_recording): return
        idx=self.current_trial_index; msg=""
        if idx in self.selected_trial_indices: self.selected_trial_indices.remove(idx); msg=f"Trial {idx+1} removed."
        else: self.selected_trial_indices.add(idx); msg=f"Trial {idx+1} added."
        self.status_bar.showMessage(msg, 2000)
        if self.selected_average_plot_items: self._remove_selected_average_plots()
        if self.show_selected_average_button: self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self._update_selected_trials_display(); self._update_ui_state()

    def _clear_avg_selection(self):
        if not self.selected_trial_indices: return
        if self.selected_average_plot_items: self._remove_selected_average_plots()
        if self.show_selected_average_button: self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self.selected_trial_indices.clear(); self.status_bar.showMessage("Selection cleared.", 2000); self._update_selected_trials_display(); self._update_ui_state()

    def _toggle_plot_selected_average(self, checked: bool):
        if checked: self._plot_selected_average()
        else: self._remove_selected_average_plots()
        self._update_ui_state()

    def _plot_selected_average(self):
        if not self.selected_trial_indices or not self.current_recording:
            if self.show_selected_average_button:
                self.show_selected_average_button.blockSignals(True)
                self.show_selected_average_button.setChecked(False)
                self.show_selected_average_button.blockSignals(False)
            self._update_ui_state(); return
        if self.selected_average_plot_items: return
        idxs=sorted(list(self.selected_trial_indices)); log.info(f"Plotting avg: {idxs}"); plotted=False; ref_t=None; first_idx=idxs[0]
        for cid, p in self.channel_plots.items(): # Find ref time vector
            if p.isVisible():
                 ch=self.current_recording.channels.get(cid);
                 if ch and 0<=first_idx<ch.num_trials:
                     try:
                         t=ch.get_relative_time_vector(first_idx)
                         if t is not None and len(t)>0: ref_t=t; break
                     except Exception: pass
        if ref_t is None:
             QtWidgets.QMessageBox.warning(self, "Averaging Error", "No valid time vector.") # Use self
             if self.show_selected_average_button:
                 self.show_selected_average_button.blockSignals(True)
                 self.show_selected_average_button.setChecked(False)
                 self.show_selected_average_button.blockSignals(False)
             self._update_ui_state(); return
        ds_thresh_val = getattr(VisConstants, 'DOWNSAMPLING_THRESHOLD', 5000) if VisConstants else 5000
        en_ds = self.downsample_checkbox.isChecked() if self.downsample_checkbox else False
        ref_l=len(ref_t)
        for cid, p in self.channel_plots.items(): # Calc and plot avg
            if p.isVisible():
                 ch=self.current_recording.channels.get(cid)
                 if not ch: continue
                 valid_d=[]
                 for idx in idxs:
                     if 0<=idx<ch.num_trials:
                         try:
                             d=ch.get_data(idx)
                             if d is not None and len(d)==ref_l: valid_d.append(d)
                         except Exception: pass
                 if valid_d:
                     try:
                         avg_d=np.mean(np.array(valid_d), axis=0)
                         item=p.plot(ref_t, avg_d, pen=self.SELECTED_AVG_PEN)
                         item.opts['autoDownsample']=en_ds
                         item.opts['autoDownsampleThreshold']=ds_thresh_val
                         self.selected_average_plot_items[cid]=item; plotted=True
                     except Exception as e: log.error(f"Error plot avg {cid}: {e}")
        if not plotted:
             QtWidgets.QMessageBox.warning(self, "Averaging Warning", "Could not plot average.") # Use self
             if self.show_selected_average_button:
                 self.show_selected_average_button.blockSignals(True)
                 self.show_selected_average_button.setChecked(False)
                 self.show_selected_average_button.blockSignals(False)
        else:
            self.status_bar.showMessage(f"Plotted avg of {len(self.selected_trial_indices)} trials.", 2500)
        self._update_ui_state()

    def _remove_selected_average_plots(self):
        if not self.selected_average_plot_items: return
        rem=0
        for cid, item in list(self.selected_average_plot_items.items()):
            p=self.channel_plots.get(cid)
            if p and item in p.items:
                try: p.removeItem(item); rem+=1
                except Exception: pass
            del self.selected_average_plot_items[cid]
        if rem>0: self.status_bar.showMessage("Avg overlay hidden.", 2000)
        self._update_ui_state()

    # =========================================================================
    # Manual Limits
    # =========================================================================
    def _parse_limit_value(self, text: str) -> Optional[float]:
        if not text or text.strip().lower()=="auto": return None
        try: return float(text.strip())
        except ValueError: return None

    def _on_set_limits_clicked(self):
        if not all(hasattr(self,w) and getattr(self,w) for w in ['manual_limit_x_min_edit','manual_limit_x_max_edit','manual_limit_y_min_edit','manual_limit_y_max_edit']): return
        xm=self._parse_limit_value(self.manual_limit_x_min_edit.text()); xM=self._parse_limit_value(self.manual_limit_x_max_edit.text())
        ym=self._parse_limit_value(self.manual_limit_y_min_edit.text()); yM=self._parse_limit_value(self.manual_limit_y_max_edit.text())
        vx,vy=False,False
        if xm is not None and xM is not None:
            if xm<xM: self.manual_x_limits=(xm,xM); vx=True
            else: QtWidgets.QMessageBox.warning(self, "Input Error", "X Min must be less than X Max."); self.manual_x_limits=None # Use self
        elif xm is not None or xM is not None: QtWidgets.QMessageBox.warning(self, "Input Error", "Both X Min and X Max must be provided."); self.manual_x_limits=None # Use self
        else: self.manual_x_limits=None
        if ym is not None and yM is not None:
            if ym<yM: self.manual_y_limits=(ym,yM); vy=True
            else: QtWidgets.QMessageBox.warning(self, "Input Error", "Y Min must be less than Y Max."); self.manual_y_limits=None # Use self
        elif ym is not None or yM is not None: QtWidgets.QMessageBox.warning(self, "Input Error", "Both Y Min and Y Max must be provided."); self.manual_y_limits=None # Use self
        else: self.manual_y_limits=None

        if vx or vy:
            self.status_bar.showMessage("Manual limits stored.", 3000)
            if self.manual_limits_enabled: self._apply_manual_limits()
        # Only show Auto message if *all* fields were cleared/invalidated to None intentionally
        elif self.manual_x_limits is None and self.manual_y_limits is None and all(v is None for v in [xm,xM,ym,yM]):
            self.status_bar.showMessage("Manual limits set to Auto.", 3000)
            if self.manual_limits_enabled and self.enable_manual_limits_checkbox:
                # If enabled but set to auto, disable it
                self.enable_manual_limits_checkbox.setChecked(False)
        else:
            # This covers cases where validation failed (min > max, or only one field filled)
            self.status_bar.showMessage("Invalid or incomplete limits entered.", 3000)


    def _on_manual_limits_toggled(self, checked: bool):
        self.manual_limits_enabled=checked; log.info(f"Manual limits {'ON' if checked else 'OFF'}"); self.status_bar.showMessage(f"Manual limits {'ON' if checked else 'OFF'}.", 2000)
        if checked:
            if self.manual_x_limits is None and self.manual_y_limits is None: self._on_set_limits_clicked() # Try setting from fields first
            if self.manual_x_limits is None and self.manual_y_limits is None: # Check again
                QtWidgets.QMessageBox.warning(self, "Enable Failed", "No valid limits set.") # Use self
                if self.enable_manual_limits_checkbox:
                    self.enable_manual_limits_checkbox.blockSignals(True)
                    self.enable_manual_limits_checkbox.setChecked(False)
                    self.enable_manual_limits_checkbox.blockSignals(False)
                self.manual_limits_enabled=False # Ensure state is false
                return # Abort enabling
            self._apply_manual_limits()
        else:
             self._update_zoom_scroll_enable_state() # Enable controls first
             self._reset_view() # Then reset view to auto-range
        self._update_ui_state() # Update other UI elements

    def _apply_manual_limits(self):
        if not self.manual_limits_enabled or (self.manual_x_limits is None and self.manual_y_limits is None): return
        log.debug(f"Applying limits - X:{self.manual_x_limits}, Y:{self.manual_y_limits}"); ax,ay=False,False; self._updating_viewranges=True
        try:
            for p in self.channel_plots.values():
                if p.isVisible() and p.getViewBox():
                     vb=p.getViewBox(); vb.disableAutoRange()
                     if self.manual_x_limits: vb.setXRange(self.manual_x_limits[0], self.manual_x_limits[1], padding=0); ax=True
                     if self.manual_y_limits: vb.setYRange(self.manual_y_limits[0], self.manual_y_limits[1], padding=0); ay=True
        finally: self._updating_viewranges=False
        if ax or ay:
             self._update_limit_fields()
             if ax and self.manual_x_limits: self._update_scrollbar_from_view(self.x_scrollbar, self.manual_x_limits, self.manual_x_limits)
             if ay and self.manual_y_limits:
                 self._update_scrollbar_from_view(self.global_y_scrollbar, self.manual_y_limits, self.manual_y_limits)
                 for s in self.individual_y_scrollbars.values(): self._update_scrollbar_from_view(s, self.manual_y_limits, self.manual_y_limits)
        self._update_zoom_scroll_enable_state() # Disable controls after applying

    def _update_zoom_scroll_enable_state(self):
        if not all(hasattr(self,w) for w in ['x_zoom_slider','global_y_slider','reset_view_button']): return
        en = not self.manual_limits_enabled; self.x_zoom_slider.setEnabled(en); self.global_y_slider.setEnabled(en and self.y_axes_locked)
        for s in self.individual_y_sliders.values(): s.setEnabled(en and not self.y_axes_locked)
        if not en: # If manual limits ON, disable scrollbars
            self._reset_scrollbar(self.x_scrollbar); self._reset_scrollbar(self.global_y_scrollbar)
            for sb in self.individual_y_scrollbars.values(): self._reset_scrollbar(sb)
        # If manual limits OFF, scrollbar state is handled by _update_scrollbar_from_view called during reset/zoom/pan
        for p in self.channel_plots.values():
            if p and p.getViewBox(): p.getViewBox().setMouseEnabled(x=en, y=en)
        has_vis=any(p.isVisible() for p in self.channel_plots.values()); self.reset_view_button.setEnabled(has_vis and en) # Reset enabled only if auto-ranging possible

    def _update_limit_fields(self):
        if self._updating_limit_fields or not all(hasattr(self,w) and getattr(self,w) for w in ['manual_limit_x_min_edit','manual_limit_x_max_edit','manual_limit_y_min_edit','manual_limit_y_max_edit']): return
        xm,xM,ym,yM="Auto","Auto","Auto","Auto"
        if self.manual_limits_enabled:
            if self.manual_x_limits: xm,xM=f"{self.manual_x_limits[0]:.4g}", f"{self.manual_x_limits[1]:.4g}"
            if self.manual_y_limits: ym,yM=f"{self.manual_y_limits[0]:.4g}", f"{self.manual_y_limits[1]:.4g}"
        else:
            plot=next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
            if plot:
                try: vb=plot.getViewBox(); xr,yr=vb.viewRange(); xm,xM=f"{xr[0]:.4g}",f"{xr[1]:.4g}"; ym,yM=f"{yr[0]:.4g}",f"{yr[1]:.4g}"
                except Exception: xm,xM,ym,yM="Err","Err","Err","Err"
        self._updating_limit_fields=True
        try: self.manual_limit_x_min_edit.setText(xm); self.manual_limit_x_max_edit.setText(xM); self.manual_limit_y_min_edit.setText(ym); self.manual_limit_y_max_edit.setText(yM)
        finally: self._updating_limit_fields=False

    def _trigger_limit_field_update(self):
        if not self.manual_limits_enabled and not self._updating_limit_fields: QtCore.QTimer.singleShot(50, self._update_limit_fields)