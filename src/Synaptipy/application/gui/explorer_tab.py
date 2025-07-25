# src/Synaptipy/application/gui/explorer_tab.py
# -*- coding: utf-8 -*-
"""
Explorer Tab widget for the Synaptipy GUI.
Contains all UI and logic for browsing, plotting, and interacting with recording data.
Includes functionality to select data targets for analysis.
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

# Import Z_ORDER constant with fallback
try:
    from Synaptipy.shared.constants import Z_ORDER
except ImportError:
    # Fallback Z_ORDER in case constants are not available
    Z_ORDER = {
        'grid': -1000,
        'baseline': -500,
        'data': 0,
        'selection': 500,
        'annotation': 1000,
    }

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
    SELECTED_AVG_PEN = pg.mkPen('g', width=_selected_avg_pen_width, name="Selected Avg")  # Original green color

    # --- Signals ---
    open_file_requested = QtCore.Signal()
    analysis_set_changed = QtCore.Signal(list)

    # --- Initialization ---
    def __init__(self, neo_adapter: NeoAdapter, nwb_exporter: NWBExporter, status_bar: QtWidgets.QStatusBar, parent=None):
        super().__init__(parent)
        log.debug("Initializing ExplorerTab...")
        
        # --- External References ---
        self.neo_adapter = neo_adapter
        self.nwb_exporter = nwb_exporter
        self.status_bar = status_bar

        # --- Data State ---
        self.current_recording: Optional[Recording] = None
        self.file_list: List[Path] = []
        self.current_file_index: int = -1
        self.current_trial_index: int = 0
        self.max_trials_current_recording: int = 0
        self.y_lock_enabled: bool = True  # Use this as the primary attribute
        self.y_axes_locked: bool = True   # Keep this for backward compatibility
        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG
        self.global_y_range_base: Optional[Tuple[float, float]] = None
        self.global_x_range_base: Optional[Tuple[float, float]] = None
        self.selected_trial_indices: Set[int] = set()
        self.manual_limits_enabled: bool = False
        
        # --- Analysis Set (for Analyser Tab) ---
        self._analysis_items: List[Dict[str, Any]] = []
        
        # --- Display State Collections --- 
        self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.selected_average_plot_items: Dict[str, pg.PlotDataItem] = {}
        
        # NEW: Added missing attributes
        self.channel_y_range_bases: Dict[str, Tuple[float, float]] = {}
        self.channel_view_boxes: Dict[str, pg.ViewBox] = {}
        
        # Y Control References
        self.global_y_slider_value: int = self.SLIDER_DEFAULT_VALUE
        self.global_y_scrollbar_value: int = self.SCROLLBAR_MAX_RANGE // 2
        self.individual_y_sliders: Dict[str, QtWidgets.QSlider] = {}
        self.individual_y_slider_labels: Dict[str, QtWidgets.QLabel] = {}
        self.individual_y_scrollbars: Dict[str, QtWidgets.QScrollBar] = {}
        self.individual_y_slider_values: Dict[str, int] = {}
        self.individual_y_scrollbar_values: Dict[str, int] = {}
        
        # Manual limits storage
        self.manual_x_range: Optional[Tuple[float, float]] = None
        self.manual_y_ranges: Dict[str, Tuple[float, float]] = {}

        # --- State Variables ---
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
        # --- UPDATED: Limit storage ---
        self.manual_x_limits: Optional[Tuple[float, float]] = None # Shared X limits
        self.manual_limit_edits: Dict[str, Dict[str, QtWidgets.QLineEdit]] = {} # {chan_id: {'ymin': QLineEdit, 'ymax': QLineEdit}}
        self.manual_channel_limits: Dict[str, Dict[str, Optional[Tuple[float, float]]]] = {} # {chan_id: {'y': (min, max)}}
        # --- END UPDATE ---

        # --- UI References ---
        # (Initialize all UI references to None as before)
        self.open_button_ui: Optional[QtWidgets.QPushButton] = None
        self.plot_mode_combobox: Optional[QtWidgets.QComboBox] = None
        self.downsample_checkbox: Optional[QtWidgets.QCheckBox] = None
        self.select_trial_button: Optional[QtWidgets.QPushButton] = None
        self.selected_trials_display: Optional[QtWidgets.QLabel] = None
        self.clear_selection_button: Optional[QtWidgets.QPushButton] = None
        self.show_selected_average_button: Optional[QtWidgets.QPushButton] = None
        self.enable_manual_limits_checkbox: Optional[QtWidgets.QCheckBox] = None
        self.manual_limit_x_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_x_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_y_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_y_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.set_manual_limits_button: Optional[QtWidgets.QPushButton] = None
        self.channel_select_group: Optional[QtWidgets.QGroupBox] = None
        self.channel_scroll_area: Optional[QtWidgets.QScrollArea] = None
        self.channel_select_widget: Optional[QtWidgets.QWidget] = None
        self.channel_checkbox_layout: Optional[QtWidgets.QVBoxLayout] = None
        self.filename_label: Optional[QtWidgets.QLabel] = None
        self.sampling_rate_label: Optional[QtWidgets.QLabel] = None
        self.channels_label: Optional[QtWidgets.QLabel] = None
        self.duration_label: Optional[QtWidgets.QLabel] = None
        self.prev_file_button: Optional[QtWidgets.QPushButton] = None
        self.next_file_button: Optional[QtWidgets.QPushButton] = None
        self.folder_file_index_label: Optional[QtWidgets.QLabel] = None
        self.graphics_layout_widget: Optional[pg.GraphicsLayoutWidget] = None
        self.x_scrollbar: Optional[QtWidgets.QScrollBar] = None
        self.reset_view_button: Optional[QtWidgets.QPushButton] = None
        self.x_zoom_slider: Optional[QtWidgets.QSlider] = None
        self.prev_trial_button: Optional[QtWidgets.QPushButton] = None
        self.next_trial_button: Optional[QtWidgets.QPushButton] = None
        self.trial_index_label: Optional[QtWidgets.QLabel] = None
        self.global_y_scrollbar_widget: Optional[QtWidgets.QWidget] = None
        self.global_y_scrollbar: Optional[QtWidgets.QScrollBar] = None
        self.individual_y_scrollbars_container: Optional[QtWidgets.QWidget] = None
        self.individual_y_scrollbars_layout: Optional[QtWidgets.QVBoxLayout] = None
        self.y_lock_checkbox: Optional[QtWidgets.QCheckBox] = None
        self.global_y_slider_widget: Optional[QtWidgets.QWidget] = None
        self.global_y_slider: Optional[QtWidgets.QSlider] = None
        self.individual_y_sliders_container: Optional[QtWidgets.QWidget] = None
        self.individual_y_sliders_layout: Optional[QtWidgets.QVBoxLayout] = None
        self.analysis_target_combo: Optional[QtWidgets.QComboBox] = None
        self.add_analysis_button: Optional[QtWidgets.QPushButton] = None
        self.analysis_set_label: Optional[QtWidgets.QLabel] = None
        self.clear_analysis_button: Optional[QtWidgets.QPushButton] = None
        # References for the limit group itself and the grid layout
        self.manual_limits_group: Optional[QtWidgets.QGroupBox] = None
        self.limits_grid_layout: Optional[QtWidgets.QGridLayout] = None
        # References for the fixed labels in the grid
        self.xmin_label_widget: Optional[QtWidgets.QLabel] = None
        self.xmax_label_widget: Optional[QtWidgets.QLabel] = None
        self.ymin_label_widget: Optional[QtWidgets.QLabel] = None
        self.ymax_label_widget: Optional[QtWidgets.QLabel] = None
        # References for shared X limit widgets
        self.xmin_edit: Optional[QtWidgets.QLineEdit] = None # Changed name
        self.xmax_edit: Optional[QtWidgets.QLineEdit] = None # Changed name
        # References for Y limit scroll area
        self.y_limits_scroll_area: Optional[QtWidgets.QScrollArea] = None
        self.y_limits_widget: Optional[QtWidgets.QWidget] = None
        # --- UPDATED: HBox changed to VBox --- 
        self.y_limits_vbox: Optional[QtWidgets.QVBoxLayout] = None # Holds HBoxes (rows) for each channel
        # --- END UPDATE ---
        # Keep references for the global enable checkbox and set button
        self.enable_manual_limits_checkbox: Optional[QtWidgets.QCheckBox] = None
        self.set_manual_limits_button: Optional[QtWidgets.QPushButton] = None
        # --- End UI References ---

        # --- Setup ---
        self._setup_ui()
        self._connect_signals()
        self._update_ui_state()
        self._update_limit_fields() # Initial update
        self._update_analysis_set_display()
        
        # Import styling to initialize plots properly at startup
        from Synaptipy.shared.styling import configure_plot_widget
        
        # Ensure the GraphicsLayoutWidget has proper styling from the beginning
        if hasattr(self, 'graphics_layout_widget') and self.graphics_layout_widget:
            self.graphics_layout_widget.setBackground('white')

    # =========================================================================
    # UI Setup (_setup_ui) - Verified Structure
    # =========================================================================
    def _setup_ui(self):
        log.debug("Setting up ExplorerTab UI...")
        main_layout = QtWidgets.QHBoxLayout(self)
        self.setLayout(main_layout)

        # --- Left Panel ---
        left_panel_widget = QtWidgets.QWidget()
        left_panel_layout = QtWidgets.QVBoxLayout(left_panel_widget)
        left_panel_layout.setSpacing(10)
        left_panel_widget.setMinimumWidth(200) # <<< ADDED

        # File Op Group
        file_op_group = QtWidgets.QGroupBox("Load Data")
        file_op_layout = QtWidgets.QHBoxLayout(file_op_group)
        self.open_button_ui = QtWidgets.QPushButton("Open File...")
        file_op_layout.addWidget(self.open_button_ui)
        left_panel_layout.addWidget(file_op_group)

        # Display Options Group
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
        self.select_trial_button.setToolTip("Add/Remove trial from overlay avg set")
        display_layout.addWidget(self.select_trial_button)
        self.selected_trials_display = QtWidgets.QLabel("Selected: None")
        self.selected_trials_display.setWordWrap(True)
        display_layout.addWidget(self.selected_trials_display)
        clear_avg_layout = QtWidgets.QHBoxLayout()
        self.clear_selection_button = QtWidgets.QPushButton("Clear Avg Set")
        self.clear_selection_button.setToolTip("Clear overlay avg selection")
        clear_avg_layout.addWidget(self.clear_selection_button)
        self.show_selected_average_button = QtWidgets.QPushButton("Plot Selected Avg")
        self.show_selected_average_button.setToolTip("Toggle overlay avg plot")
        self.show_selected_average_button.setCheckable(True)
        clear_avg_layout.addWidget(self.show_selected_average_button)
        display_layout.addLayout(clear_avg_layout)
        left_panel_layout.addWidget(display_group)

        # Manual Plot Limits Group - Setup Shell
        self.manual_limits_group = QtWidgets.QGroupBox("Manual Plot Limits")
        manual_limits_layout = QtWidgets.QVBoxLayout(self.manual_limits_group)
        manual_limits_layout.setSpacing(5)
        self.enable_manual_limits_checkbox = QtWidgets.QCheckBox("Enable Manual Limits")
        self.enable_manual_limits_checkbox.setToolTip("Apply manually set limits to plots. Disables zoom/pan.")
        manual_limits_layout.addWidget(self.enable_manual_limits_checkbox)

        # --- UPDATED: Grid for Shared X Limits Only ---
        self.limits_grid_layout = QtWidgets.QGridLayout()
        self.limits_grid_layout.setSpacing(3)
        # Change label text
        self.xmin_label_widget = QtWidgets.QLabel("X Min:") # Renamed
        self.xmax_label_widget = QtWidgets.QLabel("X Max:") # Renamed
        self.limits_grid_layout.addWidget(self.xmin_label_widget, 0, 0)
        self.limits_grid_layout.addWidget(self.xmax_label_widget, 1, 0)
        # Add shared X limit edits (tooltips updated)
        self.xmin_edit = QtWidgets.QLineEdit()
        self.xmax_edit = QtWidgets.QLineEdit()
        self.xmin_edit.setPlaceholderText("Auto")
        self.xmax_edit.setPlaceholderText("Auto")
        self.xmin_edit.setToolTip("Minimum X limit for all channels") # Tooltip ok
        self.xmax_edit.setToolTip("Maximum X limit for all channels") # Tooltip ok
        self.limits_grid_layout.addWidget(self.xmin_edit, 0, 1)
        self.limits_grid_layout.addWidget(self.xmax_edit, 1, 1)
        self.limits_grid_layout.setColumnStretch(1, 1)
        manual_limits_layout.addLayout(self.limits_grid_layout)
        # --- END X LIMITS UPDATE ---

        # --- UPDATED: Label for Y Limits ---
        y_limits_label = QtWidgets.QLabel("Y Limits:") # Renamed
        manual_limits_layout.addWidget(y_limits_label)
        # --- END Y LABEL UPDATE ---

        self.y_limits_scroll_area = QtWidgets.QScrollArea()
        self.y_limits_scroll_area.setWidgetResizable(True)
        self.y_limits_scroll_area.setMaximumHeight(150) # <<< ADDED
        # --- UPDATED: Scroll bar policies --- 
        self.y_limits_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # No horizontal scroll
        self.y_limits_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded) # Vertical scroll as needed
        # --- END UPDATE ---

        self.y_limits_widget = QtWidgets.QWidget()
        # --- UPDATED: Changed layout to QVBoxLayout --- 
        self.y_limits_vbox = QtWidgets.QVBoxLayout(self.y_limits_widget)
        self.y_limits_vbox.setContentsMargins(2, 2, 2, 2)
        self.y_limits_vbox.setSpacing(5) # Adjust spacing between rows
        self.y_limits_vbox.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop) # Align channel rows to the top
        # --- END UPDATE ---

        self.y_limits_scroll_area.setWidget(self.y_limits_widget)
        manual_limits_layout.addWidget(self.y_limits_scroll_area)
        # --- END Y LIMITS SCROLL AREA ---

        self.set_manual_limits_button = QtWidgets.QPushButton("Set Manual Limits from Fields")
        self.set_manual_limits_button.setToolTip("Store the shared X and per-channel Y limit values entered above.") # Updated tooltip
        manual_limits_layout.addWidget(self.set_manual_limits_button)
        left_panel_layout.addWidget(self.manual_limits_group)

        # Channel Selection Group
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

        # File Info Group
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

        # Analysis Selection Group
        analysis_group = QtWidgets.QGroupBox("Analysis Selection")
        analysis_layout = QtWidgets.QVBoxLayout(analysis_group)
        analysis_layout.setSpacing(5)
        # --- REMOVE Target Selection Layout ---
        # target_layout = QtWidgets.QHBoxLayout()
        # target_layout.addWidget(QtWidgets.QLabel("Add:"))
        # self.analysis_target_combo = QtWidgets.QComboBox()
        # self.analysis_target_combo.addItems(["Current Trial", "Average Trace", "All Trials"])
        # self.analysis_target_combo.setToolTip("Select data from current file for analysis set.")
        # target_layout.addWidget(self.analysis_target_combo, stretch=1)
        # analysis_layout.addLayout(target_layout)
        # --- END REMOVE ---

        # Buttons
        analysis_buttons_layout = QtWidgets.QHBoxLayout()
        # Rename button to reflect fixed action
        self.add_analysis_button = QtWidgets.QPushButton("Add Recording to Set")
        self.add_analysis_button.setToolTip("Add the entire currently loaded recording to the analysis set.")
        self.add_analysis_button.setEnabled(False)
        analysis_buttons_layout.addWidget(self.add_analysis_button)

        # --- ADD: Add Clear button to this layout ---
        self.clear_analysis_button = QtWidgets.QPushButton("Clear Analysis Set")
        self.clear_analysis_button.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
        self.clear_analysis_button.setToolTip("Remove all items from analysis set.")
        analysis_buttons_layout.addWidget(self.clear_analysis_button) # Add it here
        # --- END ADD ---

        self.analysis_set_label = QtWidgets.QLabel("Analysis Set: 0 items")
        self.analysis_set_label.setWordWrap(True)
        analysis_layout.addWidget(self.analysis_set_label)
        analysis_layout.addLayout(analysis_buttons_layout)
        left_panel_layout.addWidget(analysis_group)

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
        
        # Create and properly initialize the GraphicsLayoutWidget with white background
        self.graphics_layout_widget = pg.GraphicsLayoutWidget()
        self.graphics_layout_widget.setBackground('white')  # Ensure this is set during creation
        
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
        y_controls_panel_widget.setMinimumWidth(180) # <<< ADDED
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
        self.y_lock_checkbox = QtWidgets.QCheckBox("Lock Y Views")
        self.y_lock_checkbox.setToolTip("Link Y axes across channels")
        self.y_lock_checkbox.setChecked(self.y_lock_enabled)  # Use y_lock_enabled instead of y_axes_locked
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
    # Signal Connections (_connect_signals) - Corrected
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
        if self.add_analysis_button: self.add_analysis_button.clicked.connect(self._add_current_to_analysis_set)
        if self.clear_analysis_button: self.clear_analysis_button.clicked.connect(self._clear_analysis_set)
        self.plot_mode_combobox.currentIndexChanged.connect(self._update_ui_state)
        # --- REMOVE Combo Box Connection --- 
        # if self.analysis_target_combo: self.analysis_target_combo.currentIndexChanged.connect(self._update_ui_state)
        # --- END REMOVE --- 
        # --- REMOVE Connection for removed button --- 
        # if hasattr(self, 'add_all_loaded_button') and self.add_all_loaded_button:
        #     self.add_all_loaded_button.clicked.connect(self._add_current_file_to_set) # Renamed method
        # --- END REMOVE ---
        log.debug("ExplorerTab signal connections complete.")


    # =========================================================================
    # Public Methods for Interaction
    # =========================================================================
    def load_recording_data(self, initial_filepath_to_load: Path, file_list: List[Path], current_index: int):
        """
        Stores the list of files selected by the user and loads the initial one.
        Navigation between files is handled by _next_file_folder / _prev_file_folder.
        """
        # CHANGE: Log using the clearer argument name
        log.info(f"ExplorerTab received file list (count: {len(file_list)}). Initial file to display: {initial_filepath_to_load.name} (Index {current_index})")
        # Store the full list and the starting index provided by MainWindow
        self.file_list = file_list
        self.current_file_index = current_index
        # Load and display the specific file requested initially
        self._load_and_display_file(initial_filepath_to_load)

    def get_current_recording(self) -> Optional[Recording]:
        return self.current_recording

    def get_current_file_info(self) -> Tuple[Optional[Path], List[Path], int]:
        current_file = self.file_list[self.current_file_index] if 0 <= self.current_file_index < len(self.file_list) else None
        return current_file, self.file_list, self.current_file_index

    def get_analysis_items(self) -> List[Dict[str, Any]]:
        return self._analysis_items.copy()

    # =========================================================================
    # Reset & UI Creation (_reset_ui_and_state_for_new_file, _create_channel_ui)
    # =========================================================================
    def _reset_ui_and_state_for_new_file(self):
        log.info("Resetting ExplorerTab UI and state for new file...")
        # --- Keep existing resets for plot items, selections, checkboxes, plots, sliders, scrollbars --- 
        self._remove_selected_average_plots()
        self.selected_trial_indices.clear()
        self._update_selected_trials_display()
        if self.show_selected_average_button:
            self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)

        for checkbox in self.channel_checkboxes.values():
            try: checkbox.stateChanged.disconnect(self._trigger_plot_update)
            except RuntimeError: pass

        if hasattr(self, 'channel_checkbox_layout') and self.channel_checkbox_layout:
            while self.channel_checkbox_layout.count():
                item = self.channel_checkbox_layout.takeAt(0); widget = item.widget()
                if widget: widget.deleteLater()
        self.channel_checkboxes.clear()
        if self.channel_select_group: self.channel_select_group.setEnabled(False)

        for plot in self.channel_plots.values():
            if plot and plot.getViewBox():
                vb = plot.getViewBox()
                try: vb.sigXRangeChanged.disconnect()
                except RuntimeError: pass
                try: vb.sigYRangeChanged.disconnect()
                except RuntimeError: pass
        if hasattr(self, 'graphics_layout_widget') and self.graphics_layout_widget:
             self.graphics_layout_widget.clear()
        self.channel_plots.clear(); self.channel_plot_data_items.clear()

        for slider in self.individual_y_sliders.values():
             try: slider.valueChanged.disconnect()
             except RuntimeError: pass
        if hasattr(self, 'individual_y_sliders_layout') and self.individual_y_sliders_layout:
            while self.individual_y_sliders_layout.count():
                 item = self.individual_y_sliders_layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        self.individual_y_sliders.clear(); self.individual_y_slider_labels.clear()

        for scrollbar in self.individual_y_scrollbars.values():
            try: scrollbar.valueChanged.disconnect()
            except RuntimeError: pass
        if hasattr(self, 'individual_y_scrollbars_layout') and self.individual_y_scrollbars_layout:
            while self.individual_y_scrollbars_layout.count():
                 item = self.individual_y_scrollbars_layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        self.individual_y_scrollbars.clear()
        # --- END standard resets --- 

        # --- Reset view/state variables --- 
        self.current_recording = None; self.max_trials_current_recording = 0; self.current_trial_index = 0
        self.base_x_range = None; self.base_y_ranges.clear()
        if self.x_zoom_slider: self.x_zoom_slider.blockSignals(True); self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.x_zoom_slider.blockSignals(False)
        if self.global_y_slider: self.global_y_slider.blockSignals(True); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.blockSignals(False)
        self.y_axes_locked = True
        if self.y_lock_checkbox: self.y_lock_checkbox.blockSignals(True); self.y_lock_checkbox.setChecked(self.y_axes_locked); self.y_lock_checkbox.blockSignals(False)
        self._reset_scrollbar(self.x_scrollbar); self._reset_scrollbar(self.global_y_scrollbar)

        # --- UPDATED: Clear dynamic manual limits UI and state ---
        # Clear Y limits layout
        if self.y_limits_vbox:
            while self.y_limits_vbox.count():
                item = self.y_limits_vbox.takeAt(0)
                if item and item.widget(): 
                    item.widget().deleteLater()
        # Clear X limits edits
        if self.xmin_edit: self.xmin_edit.clear()
        if self.xmax_edit: self.xmax_edit.clear()
        # Clear state variables
        self.manual_limit_edits.clear() # Holds Y edits per channel
        self.manual_channel_limits.clear() # Holds Y limits per channel
        self.manual_x_limits = None # Holds shared X limits
        # Reset the global enable checkbox
        self.manual_limits_enabled = False
        if self.enable_manual_limits_checkbox:
             self.enable_manual_limits_checkbox.blockSignals(True)
             self.enable_manual_limits_checkbox.setChecked(False)
             self.enable_manual_limits_checkbox.blockSignals(False)
        # Ensure X edits are enabled if limits are off (will be disabled if ON later)
        if self.xmin_edit: self.xmin_edit.setEnabled(True) 
        if self.xmax_edit: self.xmax_edit.setEnabled(True)
        # --- END UPDATE ---

        # --- Reset remaining UI elements --- 
        self._update_y_controls_visibility(); self._clear_metadata_display(); self._update_trial_label()
        self._update_limit_fields(); self._update_zoom_scroll_enable_state(); self._update_ui_state()
        log.info("ExplorerTab UI and state reset complete.")

    def _reset_scrollbar(self, scrollbar: Optional[QtWidgets.QScrollBar]):
        if not scrollbar: return
        scrollbar.blockSignals(True)
        try: scrollbar.setRange(0, 0); scrollbar.setPageStep(self.SCROLLBAR_MAX_RANGE); scrollbar.setValue(0); scrollbar.setEnabled(False)
        finally: scrollbar.blockSignals(False)

    def _create_channel_ui(self):
        """Creates UI for channels in the current recording."""
        log.debug(f"Creating channel UI elements for {self.current_recording.source_file if self.current_recording else None}")
        # Need to scan the recording for channels
        if not self.current_recording or not self.current_recording.channels:
            log.warning("No channels in recording to create UI for.")
            return

        self.channel_checkboxes.clear()
        self.channel_plots.clear()
        self.channel_plot_data_items.clear()
        self.selected_average_plot_items.clear()
        self.global_y_range_base = None
        self.channel_y_range_bases.clear()

        # Import critical styling functions
        from Synaptipy.shared.styling import configure_plot_widget, get_grid_pen
        
        # Set white background on the GraphicsLayoutWidget (parent of all plot items)
        if hasattr(self, 'graphics_layout_widget') and self.graphics_layout_widget:
            self.graphics_layout_widget.setBackground('white')

        # Get current channel keys from recording (as strings)
        channel_keys = list(self.current_recording.channels.keys())

        # Loop through channels and create UI elements
        checkbox_group = QtWidgets.QButtonGroup()
        checkbox_group.setExclusive(False)
        
        for i, chan_key in enumerate(channel_keys):
            channel = self.current_recording.channels[chan_key]
            # Prefer channel's name attribute, fall back to its key
            display_name = f"{channel.name}" if hasattr(channel, 'name') and channel.name else f"Ch {chan_key}"
            
            # Create checkbox and add to layout
            checkbox = QtWidgets.QCheckBox(display_name)
            checkbox.setChecked(True)  # Default to checked
            checkbox.setToolTip(f"Show/hide {display_name}")
            self.channel_checkbox_layout.addWidget(checkbox)
            self.channel_checkboxes[chan_key] = checkbox
            checkbox_group.addButton(checkbox)
            
            # Create plot item for this channel
            plot_item = self.graphics_layout_widget.addPlot(row=i, col=0)
            
            # Apply basic plot styling
            try:
                # Set background via the view box for PlotItem
                vb = plot_item.getViewBox()
                if vb:
                    vb.setBackgroundColor('white')
                    # Add Windows-safe ViewBox configuration
                    vb.enableAutoRange(enable=False)
                    vb.setAutoVisible(x=False, y=False)
            except:
                pass  # Fallback if background setting fails
            
            # Skip all grid configuration to prevent Windows scaling issues
            # Grid can be manually enabled by users if needed
            
            # Explicitly set grid pens to ensure visibility and proper z-ordering
            try:
                # Set the grid explicitly with non-transparent grid lines
                for axis_name in ['bottom', 'left']:
                    axis = plot_item.getAxis(axis_name)
                    if axis and hasattr(axis, 'grid'):
                        # Set grid in the axis to force opacity
                        if hasattr(axis, 'setGrid'):
                            axis.setGrid(255)  # Full opacity
                        
                        # If grid is an object, set its z-value and pen
                        if hasattr(axis.grid, 'setZValue'):
                            axis.grid.setZValue(Z_ORDER['grid'])
                        
                        if hasattr(axis.grid, 'setPen'):
                            axis.grid.setPen(get_grid_pen())
            except Exception as e:
                log.warning(f"Could not set grid opacity for channel {chan_key}: {e}")
            
            # Store this association
            plot_item.getViewBox()._synaptipy_chan_id = chan_key  # Attach ID to viewbox
            self.channel_plots[chan_key] = plot_item
            
            # Y-axis label with units if available
            plot_item.setLabel('left', text=channel.get_primary_data_label(), units=channel.units)
            
            # Don't label every plot with the same X-axis label, only the bottom one
            if i == len(channel_keys) - 1:
                plot_item.setLabel('bottom', 'Time', units='s')
            # Make all but last bottom axis invisible by hiding its labels
            if i < len(channel_keys) - 1:
                plot_item.getAxis('bottom').showLabel(False)
            
            # Set up selection rectangle tool for zooming plots
            plot_item.getViewBox().setMouseMode(pg.ViewBox.RectMode)
            
            # Add a placeholder for the data - don't add plot items here, they're added in _update_plot
            self.channel_plot_data_items[chan_key] = []  # Initialize empty list to store plot items
        
        # Hook up checkbox signals at the end
        for chan_key, checkbox in self.channel_checkboxes.items():
            checkbox.toggled.connect(self._trigger_plot_update)
            checkbox.toggled.connect(lambda checked, k=chan_key: self._update_channel_visibility(k, checked))
        
        # Create Y control sliders and scrollbars for each channel
        self._create_y_controls_for_channels()
        
        # Ensure all plots are properly sized and laid out
        self.graphics_layout_widget.ci.setSpacing(10)  # Add spacing between plots
        
        # Update manual limits UI
        self._update_manual_limits_ui()
        
        log.debug(f"Created {len(channel_keys)} channel UI elements with white backgrounds and grid lines behind data.")
        
        # Complete initial UI update
        self._update_ui_state()

    def _create_y_controls_for_channels(self):
        """Creates and connects individual Y sliders and scrollbars for each channel."""
        log.debug("Creating individual Y controls for channels")
        
        # Clear existing individual Y controls
        for slider in self.individual_y_sliders.values():
            try:
                slider.valueChanged.disconnect()
            except RuntimeError:
                pass
                
        for scrollbar in self.individual_y_scrollbars.values():
            try:
                scrollbar.valueChanged.disconnect()
            except RuntimeError:
                pass
                
        # Clear the layouts
        if hasattr(self, 'individual_y_sliders_layout') and self.individual_y_sliders_layout:
            while self.individual_y_sliders_layout.count():
                item = self.individual_y_sliders_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
                    
        if hasattr(self, 'individual_y_scrollbars_layout') and self.individual_y_scrollbars_layout:
            while self.individual_y_scrollbars_layout.count():
                item = self.individual_y_scrollbars_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
                    
        # Clear the dictionaries
        self.individual_y_sliders.clear()
        self.individual_y_scrollbars.clear()
        self.individual_y_slider_labels.clear()
        self.individual_y_slider_values.clear()
        self.individual_y_scrollbar_values.clear()
        
        # Create new controls for each channel
        for chan_id, channel in self.current_recording.channels.items():
            # Prefer channel's name attribute, fall back to its key
            display_name = f"{channel.name}" if hasattr(channel, 'name') and channel.name else f"Ch {chan_id}"
            
            # Create Y slider container
            slider_container = QtWidgets.QWidget()
            slider_layout = QtWidgets.QVBoxLayout(slider_container)
            slider_layout.setContentsMargins(0, 0, 0, 0)
            slider_layout.setSpacing(2)
            
            # Create slider label
            slider_label = QtWidgets.QLabel(display_name)
            slider_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            slider_layout.addWidget(slider_label)
            
            # Create Y slider
            y_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
            y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
            y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            y_slider.setToolTip(f"Y zoom for {display_name}")
            slider_layout.addWidget(y_slider, 1)
            
            # Add to container
            self.individual_y_sliders_layout.addWidget(slider_container)
            
            # Store references
            self.individual_y_sliders[chan_id] = y_slider
            self.individual_y_slider_labels[chan_id] = slider_label
            self.individual_y_slider_values[chan_id] = self.SLIDER_DEFAULT_VALUE
            
            # Connect signals
            y_slider.valueChanged.connect(lambda value, cid=chan_id: self._on_individual_y_zoom_changed(cid, value))
            
            # Create Y scrollbar container
            scrollbar_container = QtWidgets.QWidget()
            scrollbar_layout = QtWidgets.QVBoxLayout(scrollbar_container)
            scrollbar_layout.setContentsMargins(0, 0, 0, 0)
            scrollbar_layout.setSpacing(2)
            
            # Create scrollbar label (reuse same text)
            scrollbar_label = QtWidgets.QLabel(display_name)
            scrollbar_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            scrollbar_layout.addWidget(scrollbar_label)
            
            # Create Y scrollbar
            y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Vertical)
            y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
            y_scrollbar.setValue(self.SCROLLBAR_MAX_RANGE // 2)
            y_scrollbar.setToolTip(f"Y pan for {display_name}")
            scrollbar_layout.addWidget(y_scrollbar, 1)
            
            # Add to container
            self.individual_y_scrollbars_layout.addWidget(scrollbar_container)
            
            # Store references
            self.individual_y_scrollbars[chan_id] = y_scrollbar
            self.individual_y_scrollbar_values[chan_id] = self.SCROLLBAR_MAX_RANGE // 2
            
            # Connect signals
            y_scrollbar.valueChanged.connect(lambda value, cid=chan_id: self._on_individual_y_scrollbar_changed(cid, value))
            
        # Update visibility based on current lock state
        self._update_y_controls_visibility()

    # --- REVISED Method: Channel labels above rows, larger edits --- 
    def _update_manual_limits_ui(self):
        """Dynamically populates the per-channel Y limits scroll area.""" # Updated docstring
        if not self.y_limits_vbox or not self.manual_limits_group or not self.y_limits_widget:
             log.error("Manual Y limits layout/widget not initialized.")
             return

        log.debug("Updating manual Y limits UI layout (grid per channel).") # Updated log
        # Clear existing Y limit channel rows first
        while self.y_limits_vbox.count():
            item = self.y_limits_vbox.takeAt(0)
            if item and item.widget():
                widget = item.widget()
                widget.deleteLater()
            # Also handle potential leftover layouts (less likely but safer)
            elif item and item.layout():
                 layout_to_clear = item.layout()
                 while layout_to_clear.count():
                     sub_item = layout_to_clear.takeAt(0)
                     if sub_item and sub_item.widget(): sub_item.widget().deleteLater()

        self.manual_limit_edits.clear() # Clear Y edits references

        if not self.current_recording or not self.current_recording.channels:
            self.manual_limits_group.setEnabled(False)
            placeholder = QtWidgets.QLabel("Load data...")
            placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.y_limits_vbox.addWidget(placeholder)
            # Need stretch even for placeholder to keep it centered/top
            self.y_limits_vbox.addStretch()
            return

        self.manual_limits_group.setEnabled(True)

        sorted_channel_items = sorted(self.current_recording.channels.items(), key=lambda item: str(item[0]))

        self.manual_limit_edits = {} # Reinitialize Y edit dict
        first_channel = True
        for chan_id, channel in sorted_channel_items:
            # Add separator between channels (optional)
            if not first_channel:
                sep = QtWidgets.QFrame()
                sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
                sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
                self.y_limits_vbox.addWidget(sep)
            first_channel = False

            # Add Channel Name Label directly to VBox
            chan_header_label = QtWidgets.QLabel(f"{channel.name or chan_id}:")
            chan_header_label.setToolTip(f"Channel ID: {chan_id}")
            # font = chan_header_label.font(); font.setBold(True); chan_header_label.setFont(font)
            self.y_limits_vbox.addWidget(chan_header_label)

            # Create a widget and grid layout for labels and inputs
            grid_widget = QtWidgets.QWidget()
            channel_grid = QtWidgets.QGridLayout(grid_widget)
            channel_grid.setContentsMargins(5, 2, 5, 2) # Add some margin
            channel_grid.setSpacing(5)

            # Create and add Y limit QLineEdit widgets and labels to the Grid
            edit_map = {}
            ymin_label = QtWidgets.QLabel("Y Min:")
            channel_grid.addWidget(ymin_label, 0, 0) # Row 0, Col 0
            
            ymax_label = QtWidgets.QLabel("Y Max:")
            channel_grid.addWidget(ymax_label, 0, 1) # Row 0, Col 1

            ymin_edit = QtWidgets.QLineEdit()
            ymin_edit.setPlaceholderText("Auto")
            ymin_edit.setToolTip(f"Y Min for {channel.name or chan_id}")
            ymin_edit.setMinimumWidth(70) # Keep minimum width
            channel_grid.addWidget(ymin_edit, 1, 0) # Row 1, Col 0
            edit_map['ymin'] = ymin_edit

            ymax_edit = QtWidgets.QLineEdit()
            ymax_edit.setPlaceholderText("Auto")
            ymax_edit.setToolTip(f"Y Max for {channel.name or chan_id}")
            ymax_edit.setMinimumWidth(70) # Keep minimum width
            channel_grid.addWidget(ymax_edit, 1, 1) # Row 1, Col 1
            edit_map['ymax'] = ymax_edit
            
            # Optional: Align columns if needed (e.g., make inputs expand)
            # channel_grid.setColumnStretch(0, 1)
            # channel_grid.setColumnStretch(1, 1)
            
            self.manual_limit_edits[chan_id] = edit_map
            # Add the grid widget (containing the grid layout) to the main VBox
            self.y_limits_vbox.addWidget(grid_widget)
        
        # Add stretch at the end of the VBox to keep rows packed top
        self.y_limits_vbox.addStretch()

        self._update_limit_fields()
        self._set_limit_edits_enabled(self.manual_limits_enabled)

    # --- UPDATED Helper --- 
    def _set_limit_edits_enabled(self, enabled: bool):
        """Enable/disable limit QLineEdit widgets based on manual mode state."""
        # Enable/disable shared X edits
        if self.xmin_edit: self.xmin_edit.setEnabled(enabled)
        if self.xmax_edit: self.xmax_edit.setEnabled(enabled)
        # Enable/disable per-channel Y edits
        if hasattr(self, 'manual_limit_edits'):
            for chan_map in self.manual_limit_edits.values():
                if 'ymin' in chan_map: chan_map['ymin'].setEnabled(enabled)
                if 'ymax' in chan_map: chan_map['ymax'].setEnabled(enabled)

    # =========================================================================
    # File Loading & Display Options
    # =========================================================================
    def _load_and_display_file(self, filepath: Path):
        if not filepath or not filepath.exists():
             log.error(f"Invalid file: {filepath}")
             QtWidgets.QMessageBox.critical(self, "File Error", f"File not found: {filepath}")
             self._reset_ui_and_state_for_new_file(); self._update_ui_state(); return
        self.status_bar.showMessage(f"Loading '{filepath.name}'..."); QtWidgets.QApplication.processEvents()
        self._reset_ui_and_state_for_new_file(); self.current_recording = None
        try:
            log.info(f"Reading: {filepath}"); self.current_recording = self.neo_adapter.read_recording(filepath)
            log.info(f"Loaded: {filepath.name}"); self.max_trials_current_recording = getattr(self.current_recording, 'max_trials', 0)
            self._create_channel_ui(); self._update_metadata_display(); self._update_plot(); self._reset_view()
            self.status_bar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000)
        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e:
             log.error(f"Load fail '{filepath.name}': {e}", exc_info=False)
             QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load:\n{filepath.name}\n\nError: {e}")
             self._clear_metadata_display(); self.status_bar.showMessage(f"Error loading {filepath.name}.", 5000)
        except Exception as e:
             log.error(f"Unexpected load error '{filepath.name}': {e}", exc_info=True)
             QtWidgets.QMessageBox.critical(self, "Unexpected Error", f"Error loading:\n{filepath.name}\n\n{e}")
             self._clear_metadata_display(); self.status_bar.showMessage(f"Unexpected error loading {filepath.name}.", 5000)
        finally:
             self._update_zoom_scroll_enable_state(); self._update_ui_state()
             if self.manual_limits_enabled: self._apply_manual_limits()

    def _on_plot_mode_changed(self, index: int):
        new_mode = index
        if new_mode == self.current_plot_mode: return
        log.info(f"Plot mode changed to index {index}")
        if self.selected_average_plot_items: self._remove_selected_average_plots()
        if self.show_selected_average_button:
             self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self.current_plot_mode = new_mode; self.current_trial_index = 0
        self._update_plot(); self._reset_view(); self._update_ui_state()

    # Corrected _trigger_plot_update
    def _trigger_plot_update(self):
        """Updates all plot items based on current selection/data state."""
        if not self.current_recording: return
        
        sender = self.sender()
        is_channel_checkbox = isinstance(sender, QtWidgets.QCheckBox) and sender in self.channel_checkboxes.values()

        # Import the styling module
        from Synaptipy.shared.styling import get_grid_pen

        # Apply consistent styling to all plots
        for chan_id, plot_item in self.channel_plots.items():
            if plot_item and plot_item.scene() is not None:
                # Apply basic styling
                try:
                    # Set background via the view box for PlotItem
                    vb = plot_item.getViewBox()
                    if vb:
                        vb.setBackgroundColor('white')
                        # Add Windows-safe ViewBox configuration
                        vb.enableAutoRange(enable=False)
                        vb.setAutoVisible(x=False, y=False)
                except:
                    pass  # Fallback if background setting fails
                
                # Skip showGrid to prevent Windows infinite scroll issues
                
                # Explicitly set grid pens for both axes
                try:
                    for axis_name in ['bottom', 'left']:
                        axis = plot_item.getAxis(axis_name)
                        if axis and hasattr(axis, 'grid'):
                            axis.grid.setPen(get_grid_pen())
                            # Set grid opacity to 100%
                            axis.setGrid(255)
                except Exception as e:
                    log.warning(f"Could not set grid opacity for channel {chan_id}: {e}")

        # Special case for checkbox senders - update selected average plots
        if is_channel_checkbox and self.selected_average_plot_items:
            self._remove_selected_average_plots()
            if self.show_selected_average_button:
                self.show_selected_average_button.setChecked(False)

        # Update current plot data based on current settings
        self._update_plot_data()
        
        # DISABLED: Force update can cause Windows scaling issues
        # self.graphics_layout_widget.update()
        
        log.debug("Plot update triggered and styling refreshed.")

    # =========================================================================
    # Plotting Core & Metadata - Corrected _update_plot
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
        if not self.current_recording or not self.channel_plots:
             log.warning("Update plot: No data/plots."); self._update_ui_state(); return
        is_cycle_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        log.debug(f"Updating plots. Mode: {'Cycle' if is_cycle_mode else 'Overlay'}. Trial: {self.current_trial_index}")
        
        # Import styling functions to ensure consistent appearance
        from Synaptipy.shared.styling import get_grid_pen
        
        vis_const_available = VisConstants is not None
        _trial_color_def = getattr(VisConstants, 'TRIAL_COLOR', '#888888') if vis_const_available else '#888888'
        _trial_alpha_val = getattr(VisConstants, 'TRIAL_ALPHA', 70) if vis_const_available else 70
        _avg_color_str = getattr(VisConstants, 'AVERAGE_COLOR', '#EE4B2B') if vis_const_available else '#EE4B2B'
        _pen_width_val = getattr(VisConstants, 'DEFAULT_PLOT_PEN_WIDTH', 1) if vis_const_available else 1
        _ds_thresh_val = getattr(VisConstants, 'DOWNSAMPLING_THRESHOLD', 5000) if vis_const_available else 5000
        
        try:
            if isinstance(_trial_color_def, (tuple, list)) and len(_trial_color_def) >= 3: rgb_tuple = tuple(int(c) for c in _trial_color_def[:3])
            elif isinstance(_trial_color_def, str): color_hex = _trial_color_def.lstrip('#'); rgb_tuple = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
            else: raise ValueError(f"Unsupported color format: {_trial_color_def}")
            alpha_int = max(0, min(255, int(_trial_alpha_val * 2.55)))
            rgba_tuple = rgb_tuple + (alpha_int,)
            trial_pen = pg.mkPen(rgba_tuple, width=_pen_width_val, name="Trial")  # Original trial pen
            log.debug(f"Trial pen RGBA: {rgba_tuple}")
        except Exception as e:
            log.error(f"Error creating trial_pen: {e}. Fallback."); trial_pen = pg.mkPen((128, 128, 128, 80), width=1, name="Trial_Fallback")
        average_pen = pg.mkPen(_avg_color_str, width=_pen_width_val + 1, name="Average")  # Original average pen
        single_trial_pen = pg.mkPen(_trial_color_def, width=_pen_width_val, name="Single Trial")  # Original single trial pen
        enable_downsampling = self.downsample_checkbox.isChecked() if self.downsample_checkbox else False
        ds_threshold = _ds_thresh_val
        any_data_plotted = False; visible_plots: List[pg.PlotItem] = []

        for chan_id, plot_item in self.channel_plots.items():
            checkbox = self.channel_checkboxes.get(chan_id)
            channel = self.current_recording.channels.get(chan_id)
            if checkbox and checkbox.isChecked() and channel and plot_item:
                plot_item.setVisible(True); visible_plots.append(plot_item); channel_plotted = False
                
                # Step 1: Apply basic styling BEFORE plotting
                try:
                    # Set background via the view box for PlotItem
                    vb = plot_item.getViewBox()
                    if vb:
                        vb.setBackgroundColor('white')
                        # Add Windows-safe ViewBox configuration
                        vb.enableAutoRange(enable=False)
                        vb.setAutoVisible(x=False, y=False)
                except:
                    pass  # Fallback if background setting fails
                
                # Skip showGrid to prevent Windows infinite scroll issues
                
                # Step 3: Force grid lines to have proper z-values and pens
                try:
                    for axis_name in ['bottom', 'left']:
                        axis = plot_item.getAxis(axis_name)
                        if axis and hasattr(axis, 'grid'):
                            # Set grid opacity
                            if hasattr(axis, 'setGrid'):
                                axis.setGrid(255)  # Full opacity
                                
                            # Set grid z-order
                            if hasattr(axis.grid, 'setZValue'):
                                axis.grid.setZValue(Z_ORDER['grid'])
                                
                            # Apply proper grid pen
                            if hasattr(axis.grid, 'setPen'):
                                grid_pen = get_grid_pen()
                                axis.grid.setPen(grid_pen)
                except Exception as e:
                    log.warning(f"Could not configure grid for channel {chan_id}: {e}")
                
                # Now plot the data with proper z-ordering
                if not is_cycle_mode:
                    # --- Overlay All + Avg Mode ---
                    for trial_idx in range(channel.num_trials):
                        data = channel.get_data(trial_idx)
                        time_vec = channel.get_relative_time_vector(trial_idx)
                        if data is not None and time_vec is not None:
                            item = plot_item.plot(time_vec, data, pen=trial_pen)
                            # Set z-order for proper layering
                            if hasattr(item, 'setZValue'):
                                item.setZValue(1)
                            item.opts['autoDownsample'] = enable_downsampling
                            item.opts['autoDownsampleThreshold'] = ds_threshold
                            self.channel_plot_data_items.setdefault(chan_id, []).append(item)
                            channel_plotted = True
                        else:
                            log.warning(f"Missing data or time for trial {trial_idx+1}, Ch {chan_id}")
                    
                    # Plot average trace
                    avg_data = channel.get_averaged_data()
                    avg_time_vec = channel.get_relative_averaged_time_vector()
                    if avg_data is not None and avg_time_vec is not None:
                        item = plot_item.plot(avg_time_vec, avg_data, pen=average_pen)
                        # Set average data z-order
                        if hasattr(item, 'setZValue'):
                            item.setZValue(2)
                        item.opts['autoDownsample'] = enable_downsampling
                        item.opts['autoDownsampleThreshold'] = ds_threshold
                        self.channel_plot_data_items.setdefault(chan_id, []).append(item)
                        channel_plotted = True

                else:
                    # --- Cycle Single Trial Mode ---
                    idx = min(self.current_trial_index, channel.num_trials - 1) if channel.num_trials > 0 else -1
                    if idx >= 0:
                        data = channel.get_data(idx)
                        time_vec = channel.get_relative_time_vector(idx)
                        if data is not None and time_vec is not None:
                            item = plot_item.plot(time_vec, data, pen=single_trial_pen)
                            # Set primary data z-order
                            if hasattr(item, 'setZValue'):
                                item.setZValue(3)
                            item.opts['autoDownsample'] = enable_downsampling
                            item.opts['autoDownsampleThreshold'] = ds_threshold
                            self.channel_plot_data_items.setdefault(chan_id, []).append(item)
                            channel_plotted = True
                        else: 
                            text_item = pg.TextItem(f"Data Err\nTrial {idx+1}", color='r', anchor=(0.5, 0.5))
                            # Set text overlay z-order
                            if hasattr(text_item, 'setZValue'):
                                text_item.setZValue(10)
                            plot_item.addItem(text_item)
                    else: 
                        text_item = pg.TextItem("No Trials", color='orange', anchor=(0.5, 0.5))
                        # Set text overlay z-order
                        if hasattr(text_item, 'setZValue'):
                            text_item.setZValue(10)
                        plot_item.addItem(text_item)

                if not channel_plotted: 
                    text_item = pg.TextItem("No Trials" if channel.num_trials==0 else "Plot Err", color='orange' if channel.num_trials==0 else 'red', anchor=(0.5,0.5))
                    # Set text overlay z-order
                    if hasattr(text_item, 'setZValue'):
                        text_item.setZValue(10)
                    plot_item.addItem(text_item)
                
                # Skip showGrid to prevent Windows infinite scroll issues
                
                if channel_plotted: any_data_plotted = True
            elif plot_item: plot_item.hide()

        # --- Axis linking logic (Corrected) ---
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
                    idx = visible_plots.index(plot_item)
                    target = visible_plots[idx - 1].getViewBox() if idx > 0 else None
                    vb = plot_item.getViewBox()
                    # DISABLED: setXLink operations cause Windows scaling issues
                    # if vb and hasattr(vb, 'linkedView') and vb.linkedView(0) != target:
                    #     plot_item.setXLink(target)
                    # elif vb and not hasattr(vb, 'linkedView'): # Safety
                    #     plot_item.setXLink(target)
                except Exception as link_e:
                     chan_id = getattr(plot_item.getViewBox(), '_synaptipy_chan_id', f'plot_{i}')
                     log.warning(f"XLink Err {chan_id}: {link_e}")
                     # DISABLED: setXLink operations cause Windows scaling issues
                     # plot_item.setXLink(None)
            else: # Unlink hidden plots
                vb = plot_item.getViewBox()
                # DISABLED: setXLink operations cause Windows scaling issues
                # if vb and hasattr(vb, 'linkedView') and vb.linkedView(0) is not None:
                #     plot_item.setXLink(None)
        # --- End Axis linking ---

        self._update_trial_label(); self._update_ui_state(); log.debug(f"Plot update done. Plotted: {any_data_plotted}")

    def _update_metadata_display(self):
        if self.current_recording and all(hasattr(self, w) and getattr(self, w) for w in ['filename_label','sampling_rate_label','duration_label','channels_label']):
            rec = self.current_recording; self.filename_label.setText(rec.source_file.name); self.filename_label.setToolTip(str(rec.source_file))
            sr, dur, nc = getattr(rec,'sampling_rate',None), getattr(rec,'duration',None), getattr(rec,'num_channels','N/A')
            self.sampling_rate_label.setText(f"{sr:.2f} Hz" if sr else "N/A"); self.duration_label.setText(f"{dur:.3f} s" if dur else "N/A"); self.channels_label.setText(f"{nc} ch / {self.max_trials_current_recording} trial(s)")
        else:
            self._clear_metadata_display()

    def _clear_metadata_display(self):
        if hasattr(self, 'filename_label') and self.filename_label: self.filename_label.setText("N/A"); self.filename_label.setToolTip("")
        if hasattr(self, 'sampling_rate_label') and self.sampling_rate_label: self.sampling_rate_label.setText("N/A")
        if hasattr(self, 'duration_label') and self.duration_label: self.duration_label.setText("N/A")
        if hasattr(self, 'channels_label') and self.channels_label: self.channels_label.setText("N/A")

    # =========================================================================
    # UI State Update (_update_ui_state) - Corrected
    # =========================================================================
    def _update_ui_state(self):
        if not hasattr(self, 'plot_mode_combobox'): return
        has_data=self.current_recording is not None; has_vis=any(p.isVisible() for p in self.channel_plots.values()); is_folder=len(self.file_list)>1; is_cycle=has_data and self.current_plot_mode==self.PlotMode.CYCLE_SINGLE; has_trials=has_data and self.max_trials_current_recording>0; has_avg_selection=bool(self.selected_trial_indices); is_avg_overlay_plotted=bool(self.selected_average_plot_items)
        has_file_list = bool(self.file_list) # Check if any files were loaded via File > Open

        self.plot_mode_combobox.setEnabled(has_data)
        if self.downsample_checkbox: self.downsample_checkbox.setEnabled(has_data)
        can_select_manual_avg = is_cycle and has_trials
        if self.select_trial_button:
            self.select_trial_button.setEnabled(can_select_manual_avg)
            if can_select_manual_avg: is_curr_sel=self.current_trial_index in self.selected_trial_indices; self.select_trial_button.setText("Deselect Trial" if is_curr_sel else "Add Trial")
            else: self.select_trial_button.setText("Add Current Trial")
        if self.clear_selection_button: self.clear_selection_button.setEnabled(has_avg_selection)
        if self.show_selected_average_button: self.show_selected_average_button.setEnabled(has_avg_selection); self.show_selected_average_button.setText("Hide Avg" if is_avg_overlay_plotted else "Plot Avg")
        man_lim_en=has_data
        if self.enable_manual_limits_checkbox: pg = self.enable_manual_limits_checkbox.parentWidget(); pg.setEnabled(man_lim_en) if isinstance(pg,QtWidgets.QGroupBox) else self.enable_manual_limits_checkbox.setEnabled(man_lim_en)
        if self.set_manual_limits_button: self.set_manual_limits_button.setEnabled(man_lim_en)
        lim_ed_en = man_lim_en;
        if self.manual_limit_x_min_edit: self.manual_limit_x_min_edit.setEnabled(lim_ed_en)
        if self.manual_limit_x_max_edit: self.manual_limit_x_max_edit.setEnabled(lim_ed_en)
        if self.manual_limit_y_min_edit: self.manual_limit_y_min_edit.setEnabled(lim_ed_en)
        if self.manual_limit_y_max_edit: self.manual_limit_y_max_edit.setEnabled(lim_ed_en)
        if self.channel_select_group: self.channel_select_group.setEnabled(has_data)
        if self.prev_file_button: self.prev_file_button.setVisible(is_folder); self.prev_file_button.setEnabled(is_folder and self.current_file_index > 0)
        if self.next_file_button: self.next_file_button.setVisible(is_folder); self.next_file_button.setEnabled(is_folder and self.current_file_index < len(self.file_list) - 1)
        if self.folder_file_index_label:
            self.folder_file_index_label.setVisible(is_folder)
            if is_folder: fname = self.file_list[self.current_file_index].name if 0 <= self.current_file_index < len(self.file_list) else "N/A"; self.folder_file_index_label.setText(f"{self.current_file_index+1}/{len(self.file_list)}: {fname}")
            else: self.folder_file_index_label.setText("")
        if self.reset_view_button: self.reset_view_button.setEnabled(has_vis and not self.manual_limits_enabled)
        trial_nav_en=is_cycle and has_trials and self.max_trials_current_recording > 1
        if self.prev_trial_button: self.prev_trial_button.setEnabled(trial_nav_en and self.current_trial_index > 0)
        if self.next_trial_button: self.next_trial_button.setEnabled(trial_nav_en and self.current_trial_index < self.max_trials_current_recording - 1)
        if self.trial_index_label: self.trial_index_label.setVisible(is_cycle and has_trials)

        if self.add_analysis_button:
            # --- UPDATE: Enable button based only on whether data is loaded --- 
            # target_type = self.analysis_target_combo.currentText() if self.analysis_target_combo else ""; 
            add_enabled = has_data
            # if target_type == "Current Trial": add_enabled = add_enabled and is_cycle and has_trials
            # elif target_type == "Average Trace": add_enabled = add_enabled and has_trials
            # elif target_type == "All Trials": add_enabled = add_enabled and has_trials
            self.add_analysis_button.setEnabled(add_enabled)
            # --- END UPDATE --- 
        if self.clear_analysis_button: self.clear_analysis_button.setEnabled(bool(self._analysis_items))

        # --- UPDATE: Enable/disable RENAMED button --- 
        if hasattr(self, 'add_all_loaded_button') and self.add_all_loaded_button:
             # Enable only if a recording is currently loaded
             self.add_all_loaded_button.setEnabled(has_data) 
        # --- END UPDATE ---

    def _update_trial_label(self):
        if not hasattr(self, 'trial_index_label') or not self.trial_index_label: return
        if (self.current_recording and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0):
             self.trial_index_label.setText(f"{self.current_trial_index + 1}/{self.max_trials_current_recording}")
        else:
             self.trial_index_label.setText("N/A")

    # =========================================================================
    # Analysis Set Management - Corrected
    # =========================================================================
    def _update_analysis_set_display(self):
        if not self.analysis_set_label: return
        count = len(self._analysis_items);
        self.analysis_set_label.setText(f"Analysis Set: {count} item{'s' if count != 1 else ''}")
        if count > 0:
            tooltip_text = "Analysis Set Items:\n"; items_to_show = 15
            for i, item in enumerate(self._analysis_items):
                if i >= items_to_show: tooltip_text += f"... ({count - items_to_show} more)"; break
                path_name = item['path'].name
                target = item['target_type']
                if target == 'Recording':
                    tooltip_text += f"- File: {path_name}\n"
                elif target == 'Current Trial':
                    trial_info = f" (Trial {item['trial_index'] + 1})" if item.get('trial_index') is not None else ""
                    tooltip_text += f"- {path_name} [{target}{trial_info}]\n"
                else:
                    tooltip_text += f"- {path_name} [{target}]\n"
            self.analysis_set_label.setToolTip(tooltip_text.strip())
        else: self.analysis_set_label.setToolTip("Analysis set is empty.")

    def _add_current_to_analysis_set(self):
        # --- UPDATE: Always add the current recording --- 
        if not self.current_recording or not self.current_recording.source_file:
            log.warning("Cannot add recording to analysis set: No recording loaded.")
            return False
            
        file_path = self.current_recording.source_file
        target_type = 'Recording' # Fixed target type
        trial_index = None
        
        # --- ADD: Define analysis_item here ---
        analysis_item = {'path': file_path, 'target_type': target_type, 'trial_index': trial_index}
        # --- END ADD ---
        
        # Prevent adding exact duplicate (same path and type)
        is_duplicate = any(item.get('path') == file_path and item.get('target_type') == target_type for item in self._analysis_items)
        if is_duplicate:
             log.debug(f"Recording already in analysis set: {file_path.name}")
             self.status_bar.showMessage(f"Recording '{file_path.name}' is already in the analysis set.", 3000)
             return False
             
        self._analysis_items.append(analysis_item); log.info(f"Added to analysis set: {analysis_item}")
        self.status_bar.showMessage(f"Added Recording '{file_path.name}' to the analysis set.", 3000)
        # --- END UPDATE --- 
        self._update_analysis_set_display(); self.analysis_set_changed.emit(self._analysis_items); self._update_ui_state()

    def _clear_analysis_set(self):
        """Clears the analysis set."""
        if not self._analysis_items: return
        confirm = QtWidgets.QMessageBox.question(self, "Confirm Clear", f"Clear all {len(self._analysis_items)} items from the analysis set?", QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No, QtWidgets.QMessageBox.StandardButton.No)
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            self._analysis_items = []; log.info("Analysis set cleared."); self._update_analysis_set_display(); self.analysis_set_changed.emit(self._analysis_items); self._update_ui_state()


    # =========================================================================
    # Zoom & Scroll / View Reset / Navigation / Manual Avg / Manual Limits
    # --- Corrected implementations ---
    # =========================================================================
    def _calculate_new_range(self, base_range: Optional[Tuple[float, float]], slider_value: int) -> Optional[Tuple[float, float]]:
        if base_range is None or base_range[0] is None or base_range[1] is None: return None
        try: m, M = base_range; c = (m+M)/2.0; s = max(abs(M-m), 1e-12); sl_m, sl_M = float(self.SLIDER_RANGE_MIN), float(self.SLIDER_RANGE_MAX); nz = (float(slider_value)-sl_m)/(sl_M-sl_m) if sl_M > sl_m else 0.0; zf = max(self.MIN_ZOOM_FACTOR, min(1.0, 1.0 - nz * (1.0 - self.MIN_ZOOM_FACTOR))); ns = s*zf; nm = c-ns/2.0; nM = c+ns/2.0; return (nm, nM)
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
            cx = vb.viewRange()[0]; cs=max(abs(cx[1]-cx[0]), 1e-12)
            bs=max(abs(self.base_x_range[1]-self.base_x_range[0]), 1e-12)
            sr=max(0, bs-cs); f=float(value)/max(1, self.x_scrollbar.maximum())
            nm=self.base_x_range[0]+f*sr; nM=nm+cs # Corrected var
            vb.setXRange(nm, nM, padding=0)
        except Exception as e: log.error(f"Error in _on_x_scrollbar_changed: {e}")
        finally: self._updating_viewranges=False

    def _handle_vb_xrange_changed(self, vb: pg.ViewBox, new_range: Tuple[float, float]):
        # --- UPDATED: Check shared X limits --- 
        is_manual_enabled = self.manual_limits_enabled
        manual_x = self.manual_x_limits if is_manual_enabled else None
        # --- END UPDATE ---
        if is_manual_enabled and manual_x and not self._updating_viewranges:
            self._updating_viewranges=True; vb.setXRange(manual_x[0], manual_x[1], padding=0); self._updating_viewranges=False; return
        if self._updating_viewranges or self.base_x_range is None: return
        self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_range)
        if not is_manual_enabled: self._trigger_limit_field_update()

    @QtCore.Slot(int)
    def _on_y_lock_changed(self, state: int):
        """Handle Y lock checkbox state change."""
        is_checked = state == QtCore.Qt.CheckState.Checked.value
        # Keep both attributes in sync for backward compatibility
        self.y_lock_enabled = is_checked
        self.y_axes_locked = is_checked
        log.debug(f"Y lock changed to: {is_checked}")
        self._update_y_controls_visibility()
        self._update_ui_state()
        self._update_zoom_scroll_enable_state()

    def _update_y_controls_visibility(self):
        """Update Y control widgets visibility based on current state."""
        if not all(hasattr(self, w) for w in ['global_y_slider_widget','global_y_scrollbar_widget','individual_y_sliders_container','individual_y_scrollbars_container']):
            return
        
        # Get current lock state
        lock = self.y_lock_enabled  # Use primary attribute
        
        # Check if any plots are visible
        any_vis = any(p.isVisible() for p in self.channel_plots.values())
        
        # Log current state for debugging
        log.debug(f"Updating Y controls visibility. Y lock: {lock}, Any visible plots: {any_vis}")
        
        # Set visibility of main containers based on lock state
        self.global_y_slider_widget.setVisible(lock and any_vis)
        self.global_y_scrollbar_widget.setVisible(lock and any_vis)
        self.individual_y_sliders_container.setVisible(not lock and any_vis)
        self.individual_y_scrollbars_container.setVisible(not lock and any_vis)
        
        if not any_vis:
            return
        
        # Get visible channel IDs
        vis_cids = {getattr(p.getViewBox(), '_synaptipy_chan_id', None) for p in self.channel_plots.values() 
                    if p.isVisible() and p.getViewBox() and hasattr(p.getViewBox(), '_synaptipy_chan_id')}
        vis_cids.discard(None)
        
        # Check if manual limits are enabled to determine control enabled state
        controls_enabled = not self.manual_limits_enabled
        
        # Update visibility status message
        status_msg = f"Y Controls: {'Individual' if not lock else 'Global'}, Manual Limits: {'ON' if self.manual_limits_enabled else 'OFF'}"
        log.debug(status_msg)
        
        if not lock:
            # Individual controls mode - show controls only for visible channels
            for cid, slider in self.individual_y_sliders.items():
                # Get the parent container widget
                container = slider.parent()
                while container and not isinstance(container, QtWidgets.QWidget):
                    container = container.parent()
                
                # Check if channel is visible and has base range defined
                is_visible = cid in vis_cids
                has_base_range = self.base_y_ranges.get(cid) is not None
                
                # Update container visibility
                if container:
                    container.setVisible(is_visible)
                
                # Update slider enabled state
                slider.setEnabled(is_visible and has_base_range and controls_enabled)
                
                if is_visible:
                    log.debug(f"Channel {cid}: visible={is_visible}, has_range={has_base_range}, enabled={is_visible and has_base_range and controls_enabled}")
            
            # Handle scrollbars similarly
            for cid, scrollbar in self.individual_y_scrollbars.items():
                # Get the parent container
                container = scrollbar.parent()
                while container and not isinstance(container, QtWidgets.QWidget):
                    container = container.parent()
                
                # Check visibility and range
                is_visible = cid in vis_cids
                has_base_range = self.base_y_ranges.get(cid) is not None
                has_scrollable_range = scrollbar.maximum() > scrollbar.minimum()
                
                # Update container visibility
                if container:
                    container.setVisible(is_visible)
                
                # Update scrollbar enabled state (enable only if there's a scrollable range)
                scrollbar.setEnabled(is_visible and has_base_range and controls_enabled and has_scrollable_range)
        else:
            # Global controls mode
            can_enable = any(self.base_y_ranges.get(cid) is not None for cid in vis_cids)
            
            # Global slider
            if self.global_y_slider:
                self.global_y_slider.setEnabled(can_enable and controls_enabled)
            
            # Global scrollbar - enable only if there's a scrollable range
            if self.global_y_scrollbar:
                has_scrollable_range = self.global_y_scrollbar.maximum() > self.global_y_scrollbar.minimum()
                self.global_y_scrollbar.setEnabled(can_enable and controls_enabled and has_scrollable_range)

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
                    if new_y:
                        p.getViewBox().setYRange(new_y[0], new_y[1], padding=0)
                        if b_ref is None and new_y is not None: b_ref, n_ref = base, new_y
        except Exception as e: log.error(f"Error applying global Y zoom: {e}")
        finally:
             self._updating_viewranges=False
             if b_ref and n_ref: self._update_scrollbar_from_view(self.global_y_scrollbar, b_ref, n_ref)
             else: self._reset_scrollbar(self.global_y_scrollbar)

    def _on_global_y_scrollbar_changed(self, value: int):
        if self.manual_limits_enabled or not self.y_axes_locked or self._updating_scrollbars: return
        self._apply_global_y_scroll(value)

    def _apply_global_y_scroll(self, value: int):
        if self.manual_limits_enabled or not self.y_axes_locked: return # Added lock check here too

        # Find the first visible plot to act as a reference for calculating the offset
        ref_plot = next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
        if not ref_plot: return

        ref_vb = ref_plot.getViewBox()
        ref_cid = getattr(ref_vb, '_synaptipy_chan_id', None)
        ref_base_range = self.base_y_ranges.get(ref_cid)

        # Ensure we have a valid base range for the reference plot
        if ref_base_range is None or ref_base_range[0] is None or ref_base_range[1] is None:
            log.warning(f"Cannot apply global scroll: Missing base Y range for reference channel {ref_cid}")
            return

        self._updating_viewranges = True
        try:
            current_ref_y_range = ref_vb.viewRange()[1]
            current_ref_span = max(abs(current_ref_y_range[1] - current_ref_y_range[0]), 1e-12)
            base_ref_span = max(abs(ref_base_range[1] - ref_base_range[0]), 1e-12)
            
            # Calculate the total scrollable distance in plot coordinates
            scrollable_range = max(0, base_ref_span - current_ref_span)
            
            # Calculate the scroll fraction (0.0 to 1.0)
            scroll_fraction = float(value) / max(1, self.global_y_scrollbar.maximum())
            
            # Calculate the desired new minimum Y value for the reference plot
            target_ref_min_y = ref_base_range[0] + scroll_fraction * scrollable_range
            
            # Calculate the offset needed to reach that target minimum from the current minimum
            y_offset = target_ref_min_y - current_ref_y_range[0]
            
            log.debug(f"Global Y scroll: value={value}, fraction={scroll_fraction:.3f}, target_ref_min={target_ref_min_y:.4g}, offset={y_offset:.4g}")

            # Apply the calculated offset to ALL visible plots
            for cid, plot_item in self.channel_plots.items():
                if plot_item.isVisible() and plot_item.getViewBox():
                    vb = plot_item.getViewBox()
                    current_plot_y_range = vb.viewRange()[1]
                    new_min_y = current_plot_y_range[0] + y_offset
                    new_max_y = current_plot_y_range[1] + y_offset
                    # Apply the new range by shifting the current range
                    vb.setYRange(new_min_y, new_max_y, padding=0)
                    log.debug(f"  Applied offset to {cid}: new range=({new_min_y:.4g}, {new_max_y:.4g})")

        except Exception as e:
            log.error(f"Error applying global Y scroll: {e}", exc_info=True)
        finally:
            self._updating_viewranges = False
            # We don't need to update the scrollbar here, as it triggered this action

    def _on_individual_y_zoom_changed(self, chan_id: str, value: int):
        if self.manual_limits_enabled or self.y_axes_locked or self._updating_viewranges: return
        p=self.channel_plots.get(chan_id)
        b=self.base_y_ranges.get(chan_id)
        s=self.individual_y_scrollbars.get(chan_id)
        if not p or not p.isVisible() or not p.getViewBox() or b is None or s is None: return
        
        # Calculate new Y range based on slider value
        new_y = self._calculate_new_range(b, value)
        if new_y:
            # Store the slider value
            self.individual_y_slider_values[chan_id] = value
            log.debug(f"Individual Y zoom for channel {chan_id}: value={value}, new range={new_y}")
            
            # Apply the zoom
            self._updating_viewranges=True
            try: 
                p.getViewBox().setYRange(new_y[0], new_y[1], padding=0)
            except Exception as e: 
                log.error(f"Error setting individual Y zoom {chan_id}: {e}")
            finally: 
                self._updating_viewranges=False
                # Update the scrollbar position
                self._update_scrollbar_from_view(s, b, new_y)

    def _on_individual_y_scrollbar_changed(self, chan_id: str, value: int):
        if self.manual_limits_enabled or self.y_axes_locked or self._updating_scrollbars: return
        p=self.channel_plots.get(chan_id)
        b=self.base_y_ranges.get(chan_id)
        s=self.individual_y_scrollbars.get(chan_id)
        if not p or not p.isVisible() or not p.getViewBox() or b is None or s is None: return
        
        # Store the scrollbar value
        self.individual_y_scrollbar_values[chan_id] = value
        
        # Apply the pan
        vb=p.getViewBox()
        self._updating_viewranges=True
        try:
            # Calculate new range based on scrollbar position
            current_y_range = vb.viewRange()[1]
            current_span = max(abs(current_y_range[1] - current_y_range[0]), 1e-12)
            base_span = max(abs(b[1] - b[0]), 1e-12)
            scrollable_range = max(0, base_span - current_span)
            scroll_fraction = float(value) / max(1, s.maximum())
            
            # Calculate new min/max Y values
            new_min_y = b[0] + scroll_fraction * scrollable_range
            new_max_y = new_min_y + current_span
            
            log.debug(f"Individual Y scroll for channel {chan_id}: value={value}, fraction={scroll_fraction:.3f}, new range=({new_min_y:.4g}, {new_max_y:.4g})")
            
            # Set the new range
            vb.setYRange(new_min_y, new_max_y, padding=0)
        except Exception as e: 
            log.error(f"Error handling individual Y scroll {chan_id}: {e}")
        finally: 
            self._updating_viewranges=False

    def _handle_vb_yrange_changed(self, vb: pg.ViewBox, new_range: Tuple[float, float]):
        cid = getattr(vb,'_synaptipy_chan_id',None)
        if cid is None: return
        # --- UPDATED: Check per-channel Y limits --- 
        is_manual_enabled = self.manual_limits_enabled
        channel_limits = self.manual_channel_limits.get(cid, {})
        manual_y = channel_limits.get('y') if is_manual_enabled else None
        # --- END UPDATE --- 
        if is_manual_enabled and manual_y and not self._updating_viewranges:
            self._updating_viewranges=True; vb.setYRange(manual_y[0], manual_y[1], padding=0); self._updating_viewranges=False; return
        b=self.base_y_ranges.get(cid)
        if self._updating_viewranges or b is None: return
        if self.y_axes_locked:
            fvb = next((p.getViewBox() for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
            if vb == fvb: self._update_scrollbar_from_view(self.global_y_scrollbar, b, new_range)
        else:
             s=self.individual_y_scrollbars.get(cid)
             if s: self._update_scrollbar_from_view(s, b, new_range)
        if not is_manual_enabled: self._trigger_limit_field_update()

    def _update_scrollbar_from_view(self, scrollbar: QtWidgets.QScrollBar, base_range: Optional[Tuple[float,float]], view_range: Optional[Tuple[float, float]]):
        if self._updating_scrollbars or scrollbar is None: return
        if self.manual_limits_enabled or base_range is None or view_range is None:
            self._reset_scrollbar(scrollbar); return
        self._updating_scrollbars = True
        try:
            bm, bM=base_range; vm, vM=view_range
            bs=max(abs(bM-bm),1e-12); vs=min(max(abs(vM-vm),1e-12),bs)
            ps=max(1, min(int((vs/bs)*self.SCROLLBAR_MAX_RANGE), self.SCROLLBAR_MAX_RANGE))
            rm=max(0, self.SCROLLBAR_MAX_RANGE-ps)
            rp=vm-bm; srd=max(abs(bs-vs),1e-12); v=0
            if srd>1e-10: v=max(0, min(int((rp/srd)*rm),rm))
            scrollbar.blockSignals(True); scrollbar.setRange(0, rm); scrollbar.setPageStep(ps); scrollbar.setValue(v); scrollbar.setEnabled(rm > 0); scrollbar.blockSignals(False)
        except Exception as e: log.error(f"Error updating scrollbar: {e}"); self._reset_scrollbar(scrollbar)
        finally: self._updating_scrollbars=False

    def _reset_view(self):
        if not self.current_recording: self._reset_ui_and_state_for_new_file(); self._update_ui_state(); return
        if self.manual_limits_enabled: self._apply_manual_limits(); self._update_ui_state(); return
        log.debug("Auto-ranging plots.")
        vis_map={ getattr(p.getViewBox(),'_synaptipy_chan_id',None):p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox() and hasattr(p.getViewBox(),'_synaptipy_chan_id')}
        vis_map={k:v for k,v in vis_map.items() if k is not None}
        if not vis_map: self._reset_all_sliders(); self._update_limit_fields(); self._update_ui_state(); return
        first_cid, first_plot = next(iter(vis_map.items()))
        # DISABLED: enableAutoRange calls cause Windows scaling issues
        # first_plot.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis)
        # for plot in vis_map.values(): plot.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)
        # DISABLED: Range capture can also cause Windows scaling issues
        # QtCore.QTimer.singleShot(50, self._capture_base_ranges_after_reset)
        self._reset_all_sliders(); self._update_limit_fields(); self._update_y_controls_visibility(); self._update_zoom_scroll_enable_state(); self._update_ui_state()

    def _capture_base_ranges_after_reset(self):
        log.debug("Capturing base ranges...")
        vis_map={ getattr(p.getViewBox(),'_synaptipy_chan_id',None):p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox() and hasattr(p.getViewBox(),'_synaptipy_chan_id')}
        vis_map={k:v for k,v in vis_map.items() if k is not None}
        if not vis_map: return
        first_cid, first_plot = next(iter(vis_map.items()))
        try:
             self.base_x_range=first_plot.getViewBox().viewRange()[0]
             if self.base_x_range: self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, self.base_x_range)
             else: self._reset_scrollbar(self.x_scrollbar)
        except Exception as e: log.error(f"Error capture base X: {e}"); self.base_x_range=None; self._reset_scrollbar(self.x_scrollbar)
        self.base_y_ranges.clear()
        for cid, p in vis_map.items():
            try:
                 by=p.getViewBox().viewRange()[1]; self.base_y_ranges[cid]=by
                 if not self.y_axes_locked:
                     s=self.individual_y_scrollbars.get(cid)
                     if s: self._update_scrollbar_from_view(s, by, by)
            except Exception as e:
                 log.error(f"Error capture base Y {cid}: {e}")
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
        plot = self.channel_plots.get(chan_id)
        if not plot or not plot.isVisible() or not plot.getViewBox(): return
        # DISABLED: enableAutoRange call causes Windows scaling issues
        # plot.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)
        # DISABLED: Range capture can also cause Windows scaling issues
        # QtCore.QTimer.singleShot(50, lambda: self._capture_single_base_range_after_reset(chan_id))

    def _capture_single_base_range_after_reset(self, chan_id: str):
        plot=self.channel_plots.get(chan_id)
        if not plot or not plot.getViewBox() or not plot.isVisible(): return
        vb=plot.getViewBox(); ny=None
        try:
            ny=vb.viewRange()[1]; self.base_y_ranges[chan_id]=ny
        except Exception as e:
            log.error(f"Error capture single Y {chan_id}: {e}")
            if chan_id in self.base_y_ranges: del self.base_y_ranges[chan_id]
            ny=None
        slider=self.individual_y_sliders.get(chan_id)
        if slider: slider.blockSignals(True); slider.setValue(self.SLIDER_DEFAULT_VALUE); slider.blockSignals(False)
        scroll=self.individual_y_scrollbars.get(chan_id)
        if scroll:
            if ny: self._update_scrollbar_from_view(scroll, ny, ny)
            else: self._reset_scrollbar(scroll)
        if self.y_axes_locked:
            f_plot=next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
            if f_plot and plot == f_plot:
                f_cid=getattr(f_plot.getViewBox(),'_synaptipy_chan_id',None)
                b_ref=self.base_y_ranges.get(f_cid)
                if b_ref: self._update_scrollbar_from_view(self.global_y_scrollbar, b_ref, b_ref)
                else: self._reset_scrollbar(self.global_y_scrollbar)
            if self.global_y_slider:
                self.global_y_slider.blockSignals(True); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.blockSignals(False)
        self._update_limit_fields(); self._update_y_controls_visibility()

    def _next_trial(self):
        if not self.current_recording or self.max_trials_current_recording <= 1: return
        self.current_trial_index = (self.current_trial_index + 1) % self.max_trials_current_recording
        self._update_plot() # Update plot only
        self._update_trial_label()

    def _prev_trial(self):
        if not self.current_recording or self.max_trials_current_recording <= 1: return
        self.current_trial_index = (self.current_trial_index - 1 + self.max_trials_current_recording) % self.max_trials_current_recording
        self._update_plot() # Update plot only
        self._update_trial_label()

    def _next_file_folder(self):
        if len(self.file_list) <= 1: return
        self.current_file_index = (self.current_file_index + 1) % len(self.file_list)
        filepath_to_load = self.file_list[self.current_file_index]
        log.info(f"Navigating to next file: {filepath_to_load.name} (Index {self.current_file_index})")
        # CHANGE: Call _load_and_display_file to load the new file from the list
        self._load_and_display_file(filepath_to_load)

    def _prev_file_folder(self):
        if len(self.file_list) <= 1: return
        self.current_file_index = (self.current_file_index - 1 + len(self.file_list)) % len(self.file_list)
        filepath_to_load = self.file_list[self.current_file_index]
        log.info(f"Navigating to previous file: {filepath_to_load.name} (Index {self.current_file_index})")
        # CHANGE: Call _load_and_display_file to load the new file from the list
        self._load_and_display_file(filepath_to_load)

    def _update_selected_trials_display(self): # Manual Avg Overlay
        if self.selected_trials_display:
            count = len(self.selected_trial_indices)
            self.selected_trials_display.setText(f"Selected Trials: {count}")
            indices_str = ", ".join(map(str, sorted(self.selected_trial_indices)))
            self.selected_trials_display.setToolTip(f"Indices: {indices_str}" if indices_str else "No trials selected")

    def _toggle_select_current_trial(self): # Manual Avg Overlay
        if not self.current_recording or self.current_plot_mode!=self.PlotMode.CYCLE_SINGLE or not (0<=self.current_trial_index<self.max_trials_current_recording): return
        idx=self.current_trial_index; msg=""
        if idx in self.selected_trial_indices: self.selected_trial_indices.remove(idx); msg=f"Trial {idx+1} removed."
        else: self.selected_trial_indices.add(idx); msg=f"Trial {idx+1} added."
        self.status_bar.showMessage(msg, 2000)
        if self.selected_average_plot_items: self._remove_selected_average_plots()
        if self.show_selected_average_button: self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self._update_selected_trials_display(); self._update_ui_state()

    def _clear_avg_selection(self): # Manual Avg Overlay
        if not self.selected_trial_indices: return
        if self.selected_average_plot_items: self._remove_selected_average_plots()
        if self.show_selected_average_button: self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self.selected_trial_indices.clear(); self.status_bar.showMessage("Selection cleared.", 2000); self._update_selected_trials_display(); self._update_ui_state()

    def _toggle_plot_selected_average(self, checked: bool): # Manual Avg Overlay
        if checked: self._plot_selected_average()
        else: self._remove_selected_average_plots()
        self._update_ui_state()

    def _plot_selected_average(self): # Manual Avg Overlay
        if not self.selected_trial_indices or not self.current_recording:
            if self.show_selected_average_button: 
                self.show_selected_average_button.blockSignals(True)
                self.show_selected_average_button.setChecked(False)
                self.show_selected_average_button.blockSignals(False)
            self._update_ui_state()
            return
            
        if self.selected_average_plot_items:
            return
            
        # Plot selected trial averages
        
        idxs=sorted(list(self.selected_trial_indices))
        log.info(f"Plotting avg: {idxs}")
        plotted=False
        ref_t=None
        first_idx=idxs[0]
        
        for cid, p in self.channel_plots.items():
            if p.isVisible():
                ch=self.current_recording.channels.get(cid)
                if ch and 0<=first_idx<ch.num_trials:
                    try:
                        t=ch.get_relative_time_vector(first_idx)
                        if t is not None and len(t)>0:
                            ref_t=t
                            break
                    except Exception:
                        pass
                        
        if ref_t is None:
            QtWidgets.QMessageBox.warning(self, "Averaging Error", "No valid time vector.")
            if self.show_selected_average_button:
                self.show_selected_average_button.blockSignals(True)
                self.show_selected_average_button.setChecked(False)
                self.show_selected_average_button.blockSignals(False)
            self._update_ui_state()
            return
            
        ds_thresh_val = getattr(VisConstants, 'DOWNSAMPLING_THRESHOLD', 5000) if VisConstants else 5000
        en_ds = self.downsample_checkbox.isChecked() if self.downsample_checkbox else False
        ref_l=len(ref_t)
        
        for cid, p in self.channel_plots.items():
            if p.isVisible():
                ch=self.current_recording.channels.get(cid)
                if not ch:
                    continue
                    
                valid_d=[]
                for idx in idxs:
                    if 0<=idx<ch.num_trials:
                        try:
                            d=ch.get_data(idx)
                            if d is not None and len(d)==ref_l:
                                valid_d.append(d)
                        except Exception:
                            pass
                            
                if valid_d:
                    try:
                        avg_d=np.mean(np.array(valid_d), axis=0)
                        item=p.plot(ref_t, avg_d, pen=self.SELECTED_AVG_PEN)
                        # Set selected data z-order
                        if hasattr(item, 'setZValue'):
                            item.setZValue(5)
                        item.opts['autoDownsample']=en_ds
                        item.opts['autoDownsampleThreshold']=ds_thresh_val
                        self.selected_average_plot_items[cid]=item
                        plotted=True
                    except Exception as e:
                        log.error(f"Error plot avg {cid}: {e}")
                        
        if not plotted:
            QtWidgets.QMessageBox.warning(self, "Averaging Warning", "Could not plot average.")
            if self.show_selected_average_button:
                self.show_selected_average_button.blockSignals(True)
                self.show_selected_average_button.setChecked(False)
                self.show_selected_average_button.blockSignals(False)
        else:
            self.status_bar.showMessage(f"Plotted avg of {len(self.selected_trial_indices)} trials.", 2500)
            
        self._update_ui_state()

    def _remove_selected_average_plots(self): # Manual Avg Overlay
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

    def _parse_limit_value(self, text: str) -> Optional[float]:
        if not text or text.strip().lower()=="auto": return None
        try: return float(text.strip())
        except ValueError: return None

    def _on_set_limits_clicked(self):
        """Stores the manually entered shared X and per-channel Y limits.""" # Docstring update
        # --- UPDATED: Get shared X edits ---
        if not hasattr(self, 'xmin_edit') or not self.xmin_edit or \
           not hasattr(self, 'xmax_edit') or not self.xmax_edit:
            log.error("Shared X limit edits not initialized.")
            return
        # --- END UPDATE ---
        if not hasattr(self, 'manual_limit_edits'): # Check Y edits dict
            log.warning("Y Limit edits dictionary not initialized.")
            # Allow setting only X if Y edits aren't ready?
            # return 
            pass # Continue to try setting X

        log.debug("Storing manual limits from fields.")
        # --- UPDATED: Parse and store shared X --- 
        self.manual_x_limits = None # Reset shared X
        xm_str = self.xmin_edit.text(); xM_str = self.xmax_edit.text()
        xm = self._parse_limit_value(xm_str); xM = self._parse_limit_value(xM_str)
        x_limits_set = False
        x_limit_valid = False
        if xm is not None and xM is not None:
            x_limits_set = True
            if xm < xM: self.manual_x_limits = (xm, xM); x_limit_valid = True
            else: QtWidgets.QMessageBox.warning(self, "Input Error", f"Shared X Min must be less than Shared X Max.")
        elif xm is not None or xM is not None: 
             x_limits_set = True
             QtWidgets.QMessageBox.warning(self, "Input Error", f"Both Shared X Min and X Max must be numbers or 'Auto'.")
        # else: Both are Auto, self.manual_x_limits remains None
        # --- END X UPDATE ---

        # --- UPDATED: Iterate through per-channel Y edits --- 
        self.manual_channel_limits.clear() # Clear previous stored Y limits
        y_limits_set = False # Track if any Y limits were attempted
        valid_y_limits_stored = False # Track if any valid Y limits were stored
        all_y_auto = True
        
        if hasattr(self, 'manual_limit_edits'): # Only process Y if dict exists
            for chan_id, edit_map in self.manual_limit_edits.items():
                chan_y_limits = None # Store only Y limit tuple for this channel
                
                ym_str = edit_map.get('ymin', QtWidgets.QLineEdit()).text() # Safe access
                yM_str = edit_map.get('ymax', QtWidgets.QLineEdit()).text() # Safe access
                ym = self._parse_limit_value(ym_str); yM = self._parse_limit_value(yM_str)
                
                if ym is not None and yM is not None:
                    y_limits_set = True
                    all_y_auto = False
                    if ym < yM: chan_y_limits = (ym, yM); valid_y_limits_stored = True
                    else: QtWidgets.QMessageBox.warning(self, "Input Error", f"Channel {chan_id}: Y Min must be less than Y Max.")
                elif ym is not None or yM is not None: 
                    y_limits_set = True
                    all_y_auto = False
                    QtWidgets.QMessageBox.warning(self, "Input Error", f"Channel {chan_id}: Both Y Min and Y Max must be numbers or 'Auto'.")
                # else: Both are Auto, chan_y_limits remains None

                if chan_y_limits is not None:
                    self.manual_channel_limits[chan_id] = {'y': chan_y_limits}
            # --- END Y UPDATE ---
        
        limits_were_validly_set = x_limit_valid or valid_y_limits_stored
        all_limits_are_auto = (self.manual_x_limits is None) and all_y_auto

        if limits_were_validly_set:
            self.status_bar.showMessage("Manual limits stored.", 3000)
            if self.manual_limits_enabled: self._apply_manual_limits()
        elif all_limits_are_auto:
            self.status_bar.showMessage("All limits set to Auto.", 3000)
            if self.manual_limits_enabled and self.enable_manual_limits_checkbox: self.enable_manual_limits_checkbox.setChecked(False)
        else:
             self.status_bar.showMessage("No valid limits stored. Check inputs.", 3000)

    # --- Need to update _on_manual_limits_toggled to call the new helper --- 
    def _on_manual_limits_toggled(self, checked: bool):
        self.manual_limits_enabled=checked; log.info(f"Manual limits {'ON' if checked else 'OFF'}"); self.status_bar.showMessage(f"Manual limits {'ON' if checked else 'OFF'}.", 2000)
        # --- UPDATED: Call helper to enable/disable *all* edits --- 
        self._set_limit_edits_enabled(checked) 
        # --- END UPDATE ---
        if checked:
            # If enabling, ensure some limits are actually stored. If not, try storing from fields.
            # --- UPDATED: Check combined X and Y limits --- 
            valid_x_limit_exists = self.manual_x_limits is not None
            valid_y_limit_exists = any(lim is not None for chan_lims in self.manual_channel_limits.values() for lim_key, lim in chan_lims.items() if lim_key == 'y' and lim is not None)
            if not (valid_x_limit_exists or valid_y_limit_exists):
            # --- END UPDATE ---
                self._on_set_limits_clicked() # Try to store current field values
                # Re-check if storing succeeded
                valid_x_limit_exists = self.manual_x_limits is not None
                valid_y_limit_exists = any(lim is not None for chan_lims in self.manual_channel_limits.values() for lim_key, lim in chan_lims.items() if lim_key == 'y' and lim is not None)
                if not (valid_x_limit_exists or valid_y_limit_exists):
                    QtWidgets.QMessageBox.warning(self, "Enable Failed", "No valid manual limits stored. Set values first.");
                    if self.enable_manual_limits_checkbox: self.enable_manual_limits_checkbox.blockSignals(True); self.enable_manual_limits_checkbox.setChecked(False); self.enable_manual_limits_checkbox.blockSignals(False)
                    self.manual_limits_enabled=False;
                    self._set_limit_edits_enabled(False) # Ensure edits are disabled again
                    return
            self._apply_manual_limits()
        else:
            # If disabling, re-enable zoom/scroll and auto-range
            self._update_zoom_scroll_enable_state(); self._reset_view()
        self._update_ui_state() # Update other UI elements if needed

    def _apply_manual_limits(self):
        # --- UPDATED: Check shared X and per-channel Y limits --- 
        if not self.manual_limits_enabled or (self.manual_x_limits is None and not self.manual_channel_limits):
             log.debug("Apply manual limits skipped: Not enabled or no X/Y limits stored.")
             return
        # --- END UPDATE ---

        log.debug(f"Applying stored manual limits to visible channels.");
        applied_any = False
        self._updating_viewranges=True
        try:
            # --- UPDATED: Apply shared X first, then per-channel Y --- 
            manual_x = self.manual_x_limits # Get shared X limit
            for chan_id, plot in self.channel_plots.items(): # Iterate plots
                if plot and plot.isVisible() and plot.getViewBox():
                    vb=plot.getViewBox(); vb.disableAutoRange()
                    # Apply shared X limit
                    if manual_x: 
                        vb.setXRange(manual_x[0], manual_x[1], padding=0); applied_any=True
                        # Log only once if applied
                        if chan_id == next(iter(self.channel_plots.keys())): 
                             log.debug(f"Applied shared X limits {manual_x}")
                    else:
                         # DISABLED: enableAutoRange call causes Windows scaling issues
                         # vb.enableAutoRange(axis=pg.ViewBox.XAxis) # Auto-range X if no manual X
                         pass
                    
                    # Apply per-channel Y limit
                    channel_y_limits = self.manual_channel_limits.get(chan_id, {}).get('y')
                    if channel_y_limits:
                        vb.setYRange(channel_y_limits[0], channel_y_limits[1], padding=0); applied_any=True
                        log.debug(f"Applied Y limits {channel_y_limits} to {chan_id}")
                    else:
                        # DISABLED: enableAutoRange call causes Windows scaling issues
                        # vb.enableAutoRange(axis=pg.ViewBox.YAxis) # Auto-range Y if no manual Y for this channel
                        pass
            # --- END UPDATE ---
        finally:
             self._updating_viewranges=False

        if applied_any:
            self._update_limit_fields() # Update fields to show applied limits
            # --- UPDATED: Reset scrolls/sliders --- 
            self._update_zoom_scroll_enable_state()
            self._reset_all_sliders()
            # Reset X scrollbar based on whether X limits were actually applied
            if manual_x: self._update_scrollbar_from_view(self.x_scrollbar, manual_x, manual_x)
            else: self._reset_scrollbar(self.x_scrollbar)
            # Reset Y scrollbars - always reset global, reset individual based on applied Y
            self._reset_scrollbar(self.global_y_scrollbar)
            for cid, sb in self.individual_y_scrollbars.items():
                 chan_y_lim = self.manual_channel_limits.get(cid, {}).get('y')
                 if chan_y_lim: self._update_scrollbar_from_view(sb, chan_y_lim, chan_y_lim)
                 else: self._reset_scrollbar(sb)
            # --- END UPDATE ---

    def _update_zoom_scroll_enable_state(self):
        """Updates the enabled state of zoom and scroll controls based on manual limits."""
        if not all(hasattr(self, w) for w in ['x_zoom_slider', 'global_y_slider', 'reset_view_button']):
            return
        
        en = not self.manual_limits_enabled
        
        # Update zoom sliders
        self.x_zoom_slider.setEnabled(en)
        self.global_y_slider.setEnabled(en and self.y_lock_enabled)
        for s in self.individual_y_sliders.values():
            s.setEnabled(en and not self.y_lock_enabled)
        
        # Reset scrollbars if manual limits are enabled
        if not en:
            self._reset_scrollbar(self.x_scrollbar)
            self._reset_scrollbar(self.global_y_scrollbar)
            for sb in self.individual_y_scrollbars.values():
                self._reset_scrollbar(sb)
        
        # Disable mouse interaction with plots if manual limits are enabled
        for p in self.channel_plots.values():
            if p and p.getViewBox():
                p.getViewBox().setMouseEnabled(x=en, y=en)
        
        # Enable/disable reset view button based on visibility and manual limits
        has_vis = any(p.isVisible() for p in self.channel_plots.values())
        self.reset_view_button.setEnabled(has_vis and en)

    def _update_limit_fields(self):
        if self._updating_limit_fields: return 
        # --- Check required widgets exist --- 
        if not hasattr(self, 'xmin_edit') or not self.xmin_edit or \
           not hasattr(self, 'xmax_edit') or not self.xmax_edit or \
           not hasattr(self, 'manual_limit_edits'): 
            return
        # --- End Check --- 
            
        self._updating_limit_fields=True
        try:
            # --- UPDATED: Handle shared X fields --- 
            xmin_text, xmax_text = "Auto", "Auto"
            first_visible_plot = next((p for p in self.channel_plots.values() if p and p.isVisible() and p.getViewBox()), None)
            if self.manual_limits_enabled and self.manual_x_limits:
                # Show stored shared X limits
                xmin_text, xmax_text = f"{self.manual_x_limits[0]:.4g}", f"{self.manual_x_limits[1]:.4g}"
            elif first_visible_plot and not self.manual_limits_enabled:
                # Show current X view range from first visible plot
                 try:
                     vb = first_visible_plot.getViewBox()
                     xr, _ = vb.viewRange()
                     xmin_text, xmax_text = f"{xr[0]:.4g}", f"{xr[1]:.4g}"
                 except Exception: xmin_text, xmax_text = "Err", "Err"
            elif not first_visible_plot:
                 xmin_text, xmax_text = "N/A", "N/A"
                 
            self.xmin_edit.setText(xmin_text)
            self.xmax_edit.setText(xmax_text)
            # --- END X UPDATE ---

            # --- UPDATED: Iterate through channel Y edits --- 
            for chan_id, edit_map in self.manual_limit_edits.items():
                plot = self.channel_plots.get(chan_id)
                ymin_text, ymax_text = "Auto", "Auto"
                ymin_edit = edit_map.get('ymin')
                ymax_edit = edit_map.get('ymax')
                
                if not ymin_edit or not ymax_edit: continue # Skip if edits don't exist

                if self.manual_limits_enabled:
                    # Show stored per-channel Y limits
                    channel_limits = self.manual_channel_limits.get(chan_id, {})
                    manual_y = channel_limits.get('y')
                    if manual_y: ymin_text, ymax_text = f"{manual_y[0]:.4g}", f"{manual_y[1]:.4g}"
                elif plot and plot.isVisible() and plot.getViewBox():
                    # Show current Y view range for this channel
                    try:
                        vb=plot.getViewBox(); _,yr=vb.viewRange()
                        ymin_text, ymax_text = f"{yr[0]:.4g}",f"{yr[1]:.4g}"
                    except Exception: ymin_text, ymax_text="Err","Err"
                else:
                    # Plot not visible or available
                    ymin_text, ymax_text="N/A","N/A"

                # Update the QLineEdit widgets for this channel's Y limits
                ymin_edit.setText(ymin_text)
                ymax_edit.setText(ymax_text)
            # --- END Y UPDATE --- 
        finally:
             self._updating_limit_fields=False

    def _trigger_limit_field_update(self):
        if not self.manual_limits_enabled and not self._updating_limit_fields:
            QtCore.QTimer.singleShot(50, self._update_limit_fields)

    def _apply_safe_grid_to_plot(self, plot_item):
        """Safely apply grid configuration to a specific plot item."""
        try:
            if plot_item and hasattr(plot_item, 'ctrl') and plot_item.ctrl:
                # Use the control panel's grid toggle if available (safer than direct showGrid)
                if hasattr(plot_item.ctrl, 'xGridCheck') and hasattr(plot_item.ctrl, 'yGridCheck'):
                    plot_item.ctrl.xGridCheck.setChecked(True)
                    plot_item.ctrl.yGridCheck.setChecked(True)
                else:
                    # Fallback: try showGrid but catch any errors
                    try:
                        plot_item.showGrid(x=True, y=True, alpha=0.3)
                    except:
                        pass  # Ignore grid errors on Windows
        except:
            pass  # Ignore all errors to prevent crashes

    # --- End of Methods ---