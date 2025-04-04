# -*- coding: utf-8 -*-
"""
Main Window for the Synaptipy GUI application.
Uses PySide6 for the GUI framework and pyqtgraph for plotting.
Features multi-panel plots per channel, channel selection,
and different trial plotting modes (overlay+avg, single trial cycling) via ComboBox.
Includes a single UI button for opening files (scans folder for same extension).
Uses NeoAdapter to dynamically generate file filters.
Plot view resets strategically when channel visibility or plot options change.

## MOD: Added X/Y zoom sliders with Y-axis lock functionality.
## MOD: Inverted zoom slider behavior (min=out, max=in).
## MOD: Added X/Y scrollbars for panning.
"""

# --- Standard Library Imports ---
import logging
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import uuid
from datetime import datetime, timezone
from functools import partial # ## MOD: Needed for connecting individual sliders/scrollbars

# --- Third-Party Imports ---
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets
try:
    import tzlocal # Optional, for local timezone handling
except ImportError:
    tzlocal = None

# --- Synaptipy Imports ---
# (Assume these imports are correct and classes exist)
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters import NWBExporter
from Synaptipy.shared import constants as VisConstants # Use alias
from Synaptipy.shared.error_handling import (
    FileReadError, UnsupportedFormatError, ExportError, SynaptipyError)

# --- Configure Logging ---
log = logging.getLogger(__name__)

# --- PyQtGraph Configuration ---
pg.setConfigOption('imageAxisOrder', 'row-major')
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# --- NWB Metadata Dialog ---
# (NwbMetadataDialog class remains unchanged)
class NwbMetadataDialog(QtWidgets.QDialog):
    def __init__(self, default_identifier, default_start_time, parent=None):
        super().__init__(parent); self.setWindowTitle("NWB Session Metadata"); self.setModal(True)
        self.layout = QtWidgets.QFormLayout(self)
        self.session_description = QtWidgets.QLineEdit("Session description..."); self.identifier = QtWidgets.QLineEdit(default_identifier)
        self.session_start_time_edit = QtWidgets.QDateTimeEdit(default_start_time); self.session_start_time_edit.setCalendarPopup(True); self.session_start_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.experimenter = QtWidgets.QLineEdit(""); self.lab = QtWidgets.QLineEdit(""); self.institution = QtWidgets.QLineEdit(""); self.session_id = QtWidgets.QLineEdit("")
        self.layout.addRow("Description*:", self.session_description); self.layout.addRow("Identifier*:", self.identifier); self.layout.addRow("Start Time*:", self.session_start_time_edit)
        self.layout.addRow("Experimenter:", self.experimenter); self.layout.addRow("Lab:", self.lab); self.layout.addRow("Institution:", self.institution); self.layout.addRow("Session ID:", self.session_id)
        self.layout.addRow(QtWidgets.QLabel("* Required fields"))
        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel); self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject)
        self.layout.addRow(self.button_box)
    def get_metadata(self) -> Optional[Dict]:
        desc = self.session_description.text().strip(); ident = self.identifier.text().strip(); start_time = self.session_start_time_edit.dateTime().toPython();
        if not desc or not ident:
            QtWidgets.QMessageBox.warning(self, "Input Error", "Session Description and Identifier are required.")
            return None
        return {"session_description": desc, "identifier": ident, "session_start_time": start_time, "experimenter": self.experimenter.text().strip() or None, "lab": self.lab.text().strip() or None, "institution": self.institution.text().strip() or None, "session_id": self.session_id.text().strip() or None}
# --- NwbMetadataDialog End ---


# --- MainWindow Class ---
class MainWindow(QtWidgets.QMainWindow):
    """Main application window with multi-panel plotting and trial modes."""
    class PlotMode: OVERLAY_AVG = 0; CYCLE_SINGLE = 1
    ## MOD: Constants for slider/scrollbar range and zoom
    SLIDER_RANGE_MIN = 1
    SLIDER_RANGE_MAX = 100
    SLIDER_DEFAULT_VALUE = SLIDER_RANGE_MIN # ## MOD: Default is zoomed OUT
    MIN_ZOOM_FACTOR = 0.01 # e.g., 1% zoom at max slider value
    SCROLLBAR_MAX_RANGE = 10000 # Arbitrary large range for scrollbar mapping

    def __init__(self):
        super().__init__(); self.setWindowTitle("Synaptipy"); self.setGeometry(50, 50, 1700, 950) # Wider for Y controls
        self.neo_adapter = NeoAdapter(); self.nwb_exporter = NWBExporter()
        self.current_recording: Optional[Recording] = None; self.file_list: List[Path] = []; self.current_file_index: int = -1
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}; self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG; self.current_trial_index: int = 0; self.max_trials_current_recording: int = 0

        ## MOD: State variables for zoom control
        self.y_axes_locked: bool = True
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_y_ranges: Dict[str, Optional[Tuple[float, float]]] = {}
        self.individual_y_sliders: Dict[str, QtWidgets.QSlider] = {}
        self.individual_y_slider_labels: Dict[str, QtWidgets.QLabel] = {}

        ## MOD: State variables for scrollbars
        self.individual_y_scrollbars: Dict[str, QtWidgets.QScrollBar] = {}
        self._updating_scrollbars: bool = False # Flag to prevent signal loops
        self._updating_viewranges: bool = False # Flag to prevent signal loops

        self._setup_ui(); self._connect_signals(); self._update_ui_state()

    def _setup_ui(self):
        """Create and arrange widgets ONCE during initialization."""
        menu_bar = self.menuBar(); file_menu = menu_bar.addMenu("&File")
        self.open_file_action = file_menu.addAction("&Open..."); self.open_folder_action = None
        file_menu.addSeparator(); self.export_nwb_action = file_menu.addAction("Export to &NWB...")
        file_menu.addSeparator(); self.quit_action = file_menu.addAction("&Quit")

        main_widget = QtWidgets.QWidget(); self.setCentralWidget(main_widget)
        main_layout = QtWidgets.QHBoxLayout(main_widget)

        # --- Left Panel (Controls) ---
        left_panel_widget = QtWidgets.QWidget()
        left_panel_layout = QtWidgets.QVBoxLayout(left_panel_widget)
        left_panel_layout.setSpacing(10)
        # (File Op, Display Options, Channels, Metadata groups - same as before)
        file_op_group = QtWidgets.QGroupBox("Load Data"); file_op_layout = QtWidgets.QHBoxLayout(file_op_group)
        self.open_button_ui = QtWidgets.QPushButton("Open..."); file_op_layout.addWidget(self.open_button_ui); left_panel_layout.addWidget(file_op_group)
        display_group = QtWidgets.QGroupBox("Display Options"); display_layout = QtWidgets.QVBoxLayout(display_group)
        self.downsample_checkbox = QtWidgets.QCheckBox("Auto Downsample Plot"); self.downsample_checkbox.setChecked(True)
        plot_mode_layout = QtWidgets.QHBoxLayout(); plot_mode_layout.addWidget(QtWidgets.QLabel("Plot Mode:"))
        self.plot_mode_combobox = QtWidgets.QComboBox(); self.plot_mode_combobox.addItems(["Overlay All + Avg", "Cycle Single Trial"]); self.plot_mode_combobox.setCurrentIndex(self.current_plot_mode)
        plot_mode_layout.addWidget(self.plot_mode_combobox); display_layout.addLayout(plot_mode_layout); display_layout.addWidget(self.downsample_checkbox); left_panel_layout.addWidget(display_group)
        self.channel_select_group = QtWidgets.QGroupBox("Channels"); self.channel_scroll_area = QtWidgets.QScrollArea(); self.channel_scroll_area.setWidgetResizable(True)
        self.channel_select_widget = QtWidgets.QWidget(); self.channel_checkbox_layout = QtWidgets.QVBoxLayout(self.channel_select_widget); self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignTop)
        self.channel_scroll_area.setWidget(self.channel_select_widget); channel_group_layout = QtWidgets.QVBoxLayout(self.channel_select_group); channel_group_layout.addWidget(self.channel_scroll_area); left_panel_layout.addWidget(self.channel_select_group)
        meta_group = QtWidgets.QGroupBox("File Information"); meta_layout = QtWidgets.QFormLayout(meta_group)
        self.filename_label = QtWidgets.QLabel("N/A"); self.sampling_rate_label = QtWidgets.QLabel("N/A"); self.channels_label = QtWidgets.QLabel("N/A"); self.duration_label = QtWidgets.QLabel("N/A")
        meta_layout.addRow("File:", self.filename_label); meta_layout.addRow("Sampling Rate:", self.sampling_rate_label); meta_layout.addRow("Duration:", self.duration_label); meta_layout.addRow("Channels:", self.channels_label)
        left_panel_layout.addWidget(meta_group); left_panel_layout.addStretch();
        main_layout.addWidget(left_panel_widget)

        # --- Center Panel (Plots, X Controls) ---
        center_panel_widget = QtWidgets.QWidget()
        center_panel_layout = QtWidgets.QVBoxLayout(center_panel_widget)

        # Top Navigation (File Prev/Next) - same as before
        nav_layout = QtWidgets.QHBoxLayout(); self.prev_file_button = QtWidgets.QPushButton("<< Prev File"); self.next_file_button = QtWidgets.QPushButton("Next File >>"); self.folder_file_index_label = QtWidgets.QLabel("")
        nav_layout.addWidget(self.prev_file_button); nav_layout.addStretch(); nav_layout.addWidget(self.folder_file_index_label); nav_layout.addStretch(); nav_layout.addWidget(self.next_file_button); center_panel_layout.addLayout(nav_layout)

        # Plot Area
        self.graphics_layout_widget = pg.GraphicsLayoutWidget(); center_panel_layout.addWidget(self.graphics_layout_widget, stretch=1)

        ## MOD: X Scrollbar below plot area
        self.x_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Horizontal)
        self.x_scrollbar.setFixedHeight(20)
        self.x_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE) # Initial dummy range
        center_panel_layout.addWidget(self.x_scrollbar)

        # Bottom Plot Controls (View, X Zoom, Trial Nav)
        plot_controls_layout = QtWidgets.QHBoxLayout()

        view_group = QtWidgets.QGroupBox("View")
        view_layout = QtWidgets.QHBoxLayout(view_group)
        self.reset_view_button = QtWidgets.QPushButton("Reset View")
        view_layout.addWidget(self.reset_view_button)
        plot_controls_layout.addWidget(view_group)

        x_zoom_group = QtWidgets.QGroupBox("X Zoom (Min=Out, Max=In)") # ## MOD: Clarify behavior in title
        x_zoom_layout = QtWidgets.QHBoxLayout(x_zoom_group)
        self.x_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.x_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.x_zoom_slider.setToolTip("Adjust X-axis zoom (Shared)")
        x_zoom_layout.addWidget(self.x_zoom_slider)
        plot_controls_layout.addWidget(x_zoom_group, stretch=1)

        trial_group = QtWidgets.QGroupBox("Trial")
        trial_layout = QtWidgets.QHBoxLayout(trial_group)
        self.prev_trial_button = QtWidgets.QPushButton("<"); self.next_trial_button = QtWidgets.QPushButton(">"); self.trial_index_label = QtWidgets.QLabel("N/A")
        trial_layout.addWidget(self.prev_trial_button); trial_layout.addWidget(self.trial_index_label); trial_layout.addWidget(self.next_trial_button)
        plot_controls_layout.addWidget(trial_group)

        center_panel_layout.addLayout(plot_controls_layout)
        main_layout.addWidget(center_panel_widget, stretch=1)

        # --- Right Panel (Y Controls: Zoom and Scroll) --- ## MOD: Added scrollbars
        y_controls_panel_widget = QtWidgets.QWidget()
        y_controls_panel_layout = QtWidgets.QHBoxLayout(y_controls_panel_widget) # ## MOD: HBox for Side-by-side Zoom/Scroll
        y_controls_panel_widget.setFixedWidth(220) # ## MOD: Increased width

        # --- Y Zoom Column ---
        y_zoom_widget = QtWidgets.QWidget()
        y_zoom_layout = QtWidgets.QVBoxLayout(y_zoom_widget)
        y_zoom_group = QtWidgets.QGroupBox("Y Zoom")
        y_zoom_group_layout = QtWidgets.QVBoxLayout(y_zoom_group)
        y_zoom_layout.addWidget(y_zoom_group)
        y_zoom_layout.addStretch() # Push group to top

        self.y_lock_checkbox = QtWidgets.QCheckBox("Lock Axes")
        self.y_lock_checkbox.setChecked(self.y_axes_locked)
        self.y_lock_checkbox.setToolTip("Lock/Unlock Y-axis zoom & scroll")
        y_zoom_group_layout.addWidget(self.y_lock_checkbox)

        # Global Y Slider (Visible when locked)
        self.global_y_slider_widget = QtWidgets.QWidget()
        global_y_slider_layout = QtWidgets.QVBoxLayout(self.global_y_slider_widget)
        global_y_slider_layout.setContentsMargins(0,0,0,0)
        global_y_slider_label = QtWidgets.QLabel("Global Zoom") # ## MOD: More specific label
        global_y_slider_label.setAlignment(QtCore.Qt.AlignCenter)
        self.global_y_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self.global_y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.global_y_slider.setToolTip("Adjust Y-axis zoom (All visible)")
        global_y_slider_layout.addWidget(global_y_slider_label)
        global_y_slider_layout.addWidget(self.global_y_slider, stretch=1)
        y_zoom_group_layout.addWidget(self.global_y_slider_widget)

        # Container for Individual Y Sliders (Visible when unlocked)
        self.individual_y_sliders_container = QtWidgets.QWidget()
        self.individual_y_sliders_layout = QtWidgets.QVBoxLayout(self.individual_y_sliders_container)
        self.individual_y_sliders_layout.setContentsMargins(0, 5, 0, 0); self.individual_y_sliders_layout.setSpacing(10); self.individual_y_sliders_layout.setAlignment(QtCore.Qt.AlignTop)
        y_zoom_group_layout.addWidget(self.individual_y_sliders_container, stretch=1)

        y_controls_panel_layout.addWidget(y_zoom_widget) # Add Zoom column


        # --- Y Scroll Column --- ## MOD: New column
        y_scroll_widget = QtWidgets.QWidget()
        y_scroll_layout = QtWidgets.QVBoxLayout(y_scroll_widget)
        y_scroll_group = QtWidgets.QGroupBox("Y Scroll")
        y_scroll_group_layout = QtWidgets.QVBoxLayout(y_scroll_group)
        y_scroll_layout.addWidget(y_scroll_group)
        y_scroll_layout.addStretch() # Push group to top

        # Global Y Scrollbar (Visible when locked)
        self.global_y_scrollbar_widget = QtWidgets.QWidget()
        global_y_scrollbar_layout = QtWidgets.QVBoxLayout(self.global_y_scrollbar_widget)
        global_y_scrollbar_layout.setContentsMargins(0,0,0,0)
        global_y_scrollbar_label = QtWidgets.QLabel("Global Scroll")
        global_y_scrollbar_label.setAlignment(QtCore.Qt.AlignCenter)
        self.global_y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Vertical)
        self.global_y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE) # Initial dummy range
        self.global_y_scrollbar.setToolTip("Scroll Y-axis (All visible)")
        global_y_scrollbar_layout.addWidget(global_y_scrollbar_label)
        global_y_scrollbar_layout.addWidget(self.global_y_scrollbar, stretch=1)
        y_scroll_group_layout.addWidget(self.global_y_scrollbar_widget)

        # Container for Individual Y Scrollbars (Visible when unlocked)
        self.individual_y_scrollbars_container = QtWidgets.QWidget()
        self.individual_y_scrollbars_layout = QtWidgets.QVBoxLayout(self.individual_y_scrollbars_container)
        self.individual_y_scrollbars_layout.setContentsMargins(0, 5, 0, 0); self.individual_y_scrollbars_layout.setSpacing(10); self.individual_y_scrollbars_layout.setAlignment(QtCore.Qt.AlignTop)
        y_scroll_group_layout.addWidget(self.individual_y_scrollbars_container, stretch=1)

        y_controls_panel_layout.addWidget(y_scroll_widget) # Add Scroll column


        main_layout.addWidget(y_controls_panel_widget) # Add combined Y controls panel

        # --- Status Bar ---
        self.statusBar = QtWidgets.QStatusBar(); self.setStatusBar(self.statusBar); self.statusBar.showMessage("Ready.")

        # Initial state for Y controls visibility
        self._update_y_controls_visibility()

    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        self.open_file_action.triggered.connect(self._open_file_or_folder)
        self.export_nwb_action.triggered.connect(self._export_to_nwb); self.quit_action.triggered.connect(self.close)
        self.open_button_ui.clicked.connect(self._open_file_or_folder)
        self.downsample_checkbox.stateChanged.connect(self._trigger_plot_update); self.plot_mode_combobox.currentIndexChanged.connect(self._on_plot_mode_changed)
        self.reset_view_button.clicked.connect(self._reset_view)
        self.prev_trial_button.clicked.connect(self._prev_trial); self.next_trial_button.clicked.connect(self._next_trial)
        self.prev_file_button.clicked.connect(self._prev_file_folder); self.next_file_button.clicked.connect(self._next_file_folder)

        ## MOD: Connect zoom sliders and lock checkbox
        self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
        self.y_lock_checkbox.stateChanged.connect(self._on_y_lock_changed)
        self.global_y_slider.valueChanged.connect(self._on_global_y_zoom_changed)

        ## MOD: Connect scrollbars
        self.x_scrollbar.valueChanged.connect(self._on_x_scrollbar_changed)
        self.global_y_scrollbar.valueChanged.connect(self._on_global_y_scrollbar_changed)
        # Individual Y sliders/scrollbars & ViewBox signals are connected in _create_channel_ui

    # --- Reset UI and State ---
    def _reset_ui_and_state_for_new_file(self):
        """Fully resets UI elements and state related to channels and plots."""
        log.info("Resetting UI and state for new file...")
        # 1. Clear Checkboxes UI and state (same as before)
        for checkbox in self.channel_checkboxes.values():
            try:
                if checkbox: checkbox.stateChanged.disconnect(self._trigger_plot_update)
            except (TypeError, RuntimeError): pass
        while self.channel_checkbox_layout.count():
            item = self.channel_checkbox_layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater()
        self.channel_checkboxes.clear(); self.channel_select_group.setEnabled(False)

        # 2. Clear Plot Layout and state
        # ## MOD: Disconnect ViewBox signals first
        for plot in self.channel_plots.values():
            try: plot.getViewBox().sigXRangeChanged.disconnect(self._handle_vb_xrange_changed)
            except (TypeError, RuntimeError): pass
            try: plot.getViewBox().sigYRangeChanged.disconnect(self._handle_vb_yrange_changed)
            except (TypeError, RuntimeError): pass
        self.graphics_layout_widget.clear(); self.channel_plots.clear(); self.channel_plot_data_items.clear()

        ## MOD: Clear individual Y sliders UI and state
        while self.individual_y_sliders_layout.count():
            item = self.individual_y_sliders_layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater()
        self.individual_y_sliders.clear(); self.individual_y_slider_labels.clear()

        ## MOD: Clear individual Y scrollbars UI and state
        while self.individual_y_scrollbars_layout.count():
            item = self.individual_y_scrollbars_layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater() # Deletes the scrollbar itself
        self.individual_y_scrollbars.clear()

        # 3. Reset Data State Variables (same as before)
        self.current_recording = None; self.max_trials_current_recording = 0; self.current_trial_index = 0

        ## MOD: Reset zoom state
        self.base_x_range = None; self.base_y_ranges.clear()
        self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.y_axes_locked = True; self.y_lock_checkbox.setChecked(self.y_axes_locked)

        ## MOD: Reset scrollbar state
        self._reset_scrollbar(self.x_scrollbar)
        self._reset_scrollbar(self.global_y_scrollbar)
        # Individual ones cleared above

        self._update_y_controls_visibility() # Ensure correct initial visibility

        # 4. Reset Metadata Display (same)
        self._clear_metadata_display()
        # 5. Reset Trial Label (same)
        self._update_trial_label()


    def _reset_scrollbar(self, scrollbar: QtWidgets.QScrollBar):
        """Helper to reset a scrollbar to its default state."""
        scrollbar.blockSignals(True)
        scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
        scrollbar.setValue(0)
        scrollbar.setPageStep(self.SCROLLBAR_MAX_RANGE) # Full range initially visible
        scrollbar.blockSignals(False)
        scrollbar.setEnabled(False) # Disabled until data is loaded/view set

    # --- Create Channel UI (Checkboxes, Plots, Y Sliders, Y Scrollbars) ---
    def _create_channel_ui(self):
        """Creates checkboxes, PlotItems, Y-sliders, AND Y-scrollbars. Called ONCE per file load."""
        if not self.current_recording or not self.current_recording.channels:
            log.warning("No data to create channel UI."); self.channel_select_group.setEnabled(False); return
        self.channel_select_group.setEnabled(True)
        sorted_channel_items = sorted(self.current_recording.channels.items(), key=lambda item: str(item[0]))
        log.info(f"Creating UI for {len(sorted_channel_items)} channels.")
        last_plot_item = None
        for i, (chan_id, channel) in enumerate(sorted_channel_items):
            if chan_id in self.channel_checkboxes or chan_id in self.channel_plots: log.error(f"State Error: UI element {chan_id} exists!"); continue

            # Checkbox (same as before)
            checkbox = QtWidgets.QCheckBox(f"{channel.name or f'Ch {chan_id}'}"); checkbox.setChecked(True); checkbox.stateChanged.connect(self._trigger_plot_update)
            self.channel_checkbox_layout.addWidget(checkbox); self.channel_checkboxes[chan_id] = checkbox

            # Plot Item
            plot_item = self.graphics_layout_widget.addPlot(row=i, col=0); plot_item.setLabel('left', channel.name or f'Ch {chan_id}', units=channel.units or 'units'); plot_item.showGrid(x=True, y=True, alpha=0.3)
            self.channel_plots[chan_id] = plot_item
            vb = plot_item.getViewBox()
            vb.setMouseMode(pg.ViewBox.RectMode) # Ensure default mouse mode allows panning
            # Store chan_id in the ViewBox for easy retrieval in handlers
            vb._synaptipy_chan_id = chan_id

            ## MOD: Connect ViewBox range change signals
            vb.sigXRangeChanged.connect(self._handle_vb_xrange_changed)
            vb.sigYRangeChanged.connect(self._handle_vb_yrange_changed)

            if last_plot_item: plot_item.setXLink(last_plot_item); plot_item.hideAxis('bottom')
            last_plot_item = plot_item

            ## MOD: Create individual Y slider (same container logic as before)
            ind_y_slider_widget = QtWidgets.QWidget()
            ind_y_slider_layout = QtWidgets.QVBoxLayout(ind_y_slider_widget)
            ind_y_slider_layout.setContentsMargins(0,0,0,0); ind_y_slider_layout.setSpacing(2)
            slider_label = QtWidgets.QLabel(f"{channel.name or chan_id[:4]} Zoom"); slider_label.setAlignment(QtCore.Qt.AlignCenter); slider_label.setToolTip(f"Y Zoom for {channel.name or chan_id}")
            self.individual_y_slider_labels[chan_id] = slider_label
            ind_y_slider_layout.addWidget(slider_label)
            y_slider = QtWidgets.QSlider(QtCore.Qt.Vertical); y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX); y_slider.setValue(self.SLIDER_DEFAULT_VALUE); y_slider.setToolTip(f"Adjust Y zoom for {channel.name or chan_id}")
            y_slider.valueChanged.connect(partial(self._on_individual_y_zoom_changed, chan_id))
            ind_y_slider_layout.addWidget(y_slider, stretch=1)
            self.individual_y_sliders[chan_id] = y_slider
            self.individual_y_sliders_layout.addWidget(ind_y_slider_widget)
            ind_y_slider_widget.setVisible(False) # Initially hidden

            ## MOD: Create individual Y scrollbar
            y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Vertical)
            y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
            y_scrollbar.setToolTip(f"Scroll Y-axis for {channel.name or chan_id}")
            y_scrollbar.valueChanged.connect(partial(self._on_individual_y_scrollbar_changed, chan_id))
            self.individual_y_scrollbars[chan_id] = y_scrollbar
            self.individual_y_scrollbars_layout.addWidget(y_scrollbar) # Add directly
            y_scrollbar.setVisible(False) # Initially hidden
            self._reset_scrollbar(y_scrollbar) # Set initial state

        if last_plot_item: last_plot_item.setLabel('bottom', "Time", units='s'); last_plot_item.showAxis('bottom')


    # --- File Loading --- (Unchanged logic, relies on reset)
    def _open_file_or_folder(self): # ... (same as before) ...
        file_filter = self.neo_adapter.get_supported_file_filter(); log.debug(f"Using dynamic file filter: {file_filter}")
        filepath_str, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Recording File", "", file_filter)
        if not filepath_str: log.info("File open cancelled."); return
        selected_filepath = Path(filepath_str); folder_path = selected_filepath.parent; selected_extension = selected_filepath.suffix.lower()
        log.info(f"User selected: {selected_filepath.name}. Scanning folder '{folder_path}' for '{selected_extension}'.")
        try: sibling_files = sorted(list(folder_path.glob(f"*{selected_extension}")))
        except Exception as e:
             log.error(f"Error scanning folder {folder_path}: {e}"); QtWidgets.QMessageBox.warning(self, "Folder Scan Error", f"Could not scan folder:\n{e}")
             self.file_list = [selected_filepath]; self.current_file_index = 0; self._load_and_display_file(selected_filepath); return
        if not sibling_files: log.warning(f"No files with {selected_extension} found. Loading selected only."); self.file_list = [selected_filepath]; self.current_file_index = 0
        else:
            self.file_list = sibling_files
            try: self.current_file_index = self.file_list.index(selected_filepath); log.info(f"Found {len(self.file_list)} file(s). Selected index {self.current_file_index}.")
            except ValueError: log.error(f"Selected file {selected_filepath} not in scanned list? Loading first."); self.current_file_index = 0
        if self.file_list: self._load_and_display_file(self.file_list[self.current_file_index])
        else: self._reset_ui_and_state_for_new_file(); self._update_ui_state()

    def _load_and_display_file(self, filepath: Path): # ... (same as before until end) ...
        self.statusBar.showMessage(f"Loading '{filepath.name}'..."); QtWidgets.QApplication.processEvents()
        self._reset_ui_and_state_for_new_file(); self.current_recording = None
        try:
            self.current_recording = self.neo_adapter.read_recording(filepath); log.info(f"Loaded {filepath.name}")
            self.max_trials_current_recording = self.current_recording.max_trials if self.current_recording else 0
            self._create_channel_ui(); # Creates plots, sliders, scrollbars, connects VB signals
            self._update_metadata_display();
            self._update_plot() # Plots data
            self._reset_view() # Sets base ranges, resets sliders, updates scrollbars
            self.statusBar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000)
        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e: log.error(f"Load failed {filepath}: {e}", exc_info=False); QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load file:\n{filepath.name}\n\nError: {e}"); self._clear_metadata_display(); self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        except Exception as e: log.error(f"Unexpected error loading {filepath}: {e}", exc_info=True); QtWidgets.QMessageBox.critical(self, "Unexpected Error", f"Error loading:\n{filepath.name}\n\n{e}"); self._clear_metadata_display(); self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        finally: self._update_ui_state() # Updates enables etc.


    # --- Display Option Changes ---
    def _on_plot_mode_changed(self, index): # (Same as before)
        self.current_plot_mode = index
        log.info(f"Plot mode changed to: {'Overlay+Avg' if index == self.PlotMode.OVERLAY_AVG else 'Cycle Single'}")
        self.current_trial_index = 0
        self._trigger_plot_update()


    def _trigger_plot_update(self):
        """Connected to checkboxes and downsample option. Updates plot and Y controls visibility."""
        if not self.current_recording: return

        sender_checkbox = self.sender()
        is_checkbox_trigger = isinstance(sender_checkbox, QtWidgets.QCheckBox) and sender_checkbox != self.downsample_checkbox and sender_checkbox != self.y_lock_checkbox

        # Update the plot data first
        self._update_plot() # This also calls _update_ui_state at the end

        ## MOD: Update visibility of individual Y sliders & scrollbars if a channel checkbox changed
        if is_checkbox_trigger:
            self._update_y_controls_visibility()

        # Reset view only if a checkbox was turned ON
        if is_checkbox_trigger and sender_checkbox.isChecked():
            channel_id_to_reset = None
            for ch_id, cb in self.channel_checkboxes.items():
                if cb == sender_checkbox: channel_id_to_reset = ch_id; break
            if channel_id_to_reset:
                 self._reset_single_plot_view(channel_id_to_reset) # This resets base range, slider, and updates scrollbar for that plot


    # --- Plotting Core Logic ---
    def _clear_plot_data_only(self): # (Same as before)
        for chan_id, plot_item in self.channel_plots.items():
            if plot_item is None or plot_item.scene() is None: continue
            items_to_remove = [item for item in plot_item.items if isinstance(item, (pg.PlotDataItem, pg.TextItem))]
            for item in items_to_remove: plot_item.removeItem(item)
        self.channel_plot_data_items.clear()

    def _update_plot(self): # (Plotting logic itself is same, UI update at end)
        self._clear_plot_data_only()
        if not self.current_recording or not self.channel_plots:
            log.warning("Update plot: No recording or plot items exist.")
            items = self.graphics_layout_widget.items()
            if not any(isinstance(item, pg.PlotItem) for item in items):
                 self.graphics_layout_widget.clear(); self.graphics_layout_widget.addLabel("Load data", row=0, col=0)
            self._update_ui_state(); return

        is_cycle_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        log.debug(f"Updating plot data. Mode: {'Cycle Single' if is_cycle_mode else 'Overlay+Avg'}, Trial: {self.current_trial_index+1}/{self.max_trials_current_recording}")
        trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR + (VisConstants.TRIAL_ALPHA,), width=VisConstants.DEFAULT_PLOT_PEN_WIDTH)
        avg_pen = pg.mkPen(VisConstants.AVERAGE_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1)
        single_trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH)
        any_data_plotted = False
        visible_plots_this_update: List[pg.PlotItem] = []

        for chan_id, plot_item in self.channel_plots.items():
            checkbox = self.channel_checkboxes.get(chan_id); channel = self.current_recording.channels.get(chan_id)
            if checkbox and checkbox.isChecked() and channel:
                plot_item.setVisible(True); plotted_something = False; visible_plots_this_update.append(plot_item)
                # --- Plotting logic (unchanged) ---
                if not is_cycle_mode: # Overlay+Avg Mode
                    for trial_idx in range(channel.num_trials):
                        data = channel.get_data(trial_idx); tvec = channel.get_relative_time_vector(trial_idx)
                        if data is not None and tvec is not None: plot_item.plot(tvec, data, pen=trial_pen); plotted_something = True
                    avg_data = channel.get_averaged_data(); avg_tvec = channel.get_relative_averaged_time_vector()
                    if avg_data is not None and avg_tvec is not None:
                        di_avg = plot_item.plot(avg_tvec, avg_data, pen=avg_pen)
                        enable_ds = self.downsample_checkbox.isChecked(); di_avg.opts['autoDownsample'] = enable_ds;
                        if enable_ds: di_avg.opts['autoDownsampleThreshold'] = VisConstants.DOWNSAMPLING_THRESHOLD
                        plotted_something = True
                    elif channel.num_trials > 0: log.warning(f"Avg failed ch {chan_id}")
                    if not plotted_something and channel.num_trials > 0: plot_item.addItem(pg.TextItem(f"Plot error", color='r'))
                    elif channel.num_trials == 0: plot_item.addItem(pg.TextItem(f"No trials", color='orange'))
                else: # Cycle Single Mode
                    idx = min(self.current_trial_index, channel.num_trials - 1) if channel.num_trials > 0 else -1
                    if idx >= 0:
                        data = channel.get_data(idx); tvec = channel.get_relative_time_vector(idx)
                        if data is not None and tvec is not None:
                            di = plot_item.plot(tvec, data, pen=single_trial_pen)
                            enable_ds = self.downsample_checkbox.isChecked(); di.opts['autoDownsample'] = enable_ds
                            if enable_ds: di.opts['autoDownsampleThreshold'] = VisConstants.DOWNSAMPLING_THRESHOLD
                            plotted_something = True
                        else: plot_item.addItem(pg.TextItem(f"Trial {idx+1} data error", color='r'))
                    else: plot_item.addItem(pg.TextItem(f"No trials", color='orange'))
                # --- End Plotting logic ---
                if plotted_something: any_data_plotted = True
            elif plot_item: plot_item.hide()

        # --- Configure bottom axis --- (Unchanged)
        last_visible_plot_this_update = visible_plots_this_update[-1] if visible_plots_this_update else None
        for item in self.channel_plots.values():
             if item in visible_plots_this_update:
                 is_last = (item == last_visible_plot_this_update)
                 item.showAxis('bottom', show=is_last)
                 if is_last: item.setLabel('bottom', "Time", units='s')
                 try:
                    current_vis_idx = visible_plots_this_update.index(item)
                    if current_vis_idx > 0: item.setXLink(visible_plots_this_update[current_vis_idx - 1])
                    else: item.setXLink(None)
                 except ValueError: item.setXLink(None)
             else: item.hideAxis('bottom')

        self._update_trial_label()
        if not any_data_plotted and self.current_recording and self.channel_plots: log.info("No channels selected or no data plotted.")

        self._update_ui_state() # Update enables/disables


    # --- Metadata Display --- (Unchanged)
    def _update_metadata_display(self): # ... (same) ...
        if self.current_recording: rec = self.current_recording; self.filename_label.setText(rec.source_file.name); self.sampling_rate_label.setText(f"{rec.sampling_rate:.2f} Hz" if rec.sampling_rate else "N/A"); self.duration_label.setText(f"{rec.duration:.3f} s" if rec.duration else "N/A"); num_ch = rec.num_channels; max_tr = self.max_trials_current_recording; self.channels_label.setText(f"{num_ch} ch, {max_tr} trial(s)")
        else: self._clear_metadata_display()
    def _clear_metadata_display(self): # ... (same) ...
        self.filename_label.setText("N/A"); self.sampling_rate_label.setText("N/A"); self.channels_label.setText("N/A"); self.duration_label.setText("N/A")

    # --- UI State Update ---
    def _update_ui_state(self):
        has_data = self.current_recording is not None
        visible_plots = [p for p in self.channel_plots.values() if p.isVisible()]
        has_visible_plots = bool(visible_plots)
        is_folder = len(self.file_list) > 1
        is_cycling_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        has_multiple_trials = self.max_trials_current_recording > 1

        enable_data_controls = has_data and has_visible_plots
        enable_any_data_controls = has_data

        ## MOD: Enable/disable zoom/scroll controls
        self.reset_view_button.setEnabled(enable_data_controls)
        self.x_zoom_slider.setEnabled(enable_data_controls)
        self.x_scrollbar.setEnabled(enable_data_controls and self.base_x_range is not None) # Only enable if range known

        self.y_lock_checkbox.setEnabled(enable_data_controls)
        can_enable_global_y = enable_data_controls and self.y_axes_locked and any(self.base_y_ranges.get(p.getViewBox()._synaptipy_chan_id) is not None for p in visible_plots)
        self.global_y_slider.setEnabled(can_enable_global_y)
        self.global_y_scrollbar.setEnabled(can_enable_global_y)

        # Individual controls enabled state managed in _update_y_controls_visibility

        self.plot_mode_combobox.setEnabled(enable_any_data_controls)
        self.downsample_checkbox.setEnabled(enable_any_data_controls)
        self.export_nwb_action.setEnabled(enable_any_data_controls)
        self.channel_select_group.setEnabled(has_data)

        # Trial Nav (same)
        enable_trial_cycle = enable_any_data_controls and is_cycling_mode and has_multiple_trials
        self.prev_trial_button.setEnabled(enable_trial_cycle and self.current_trial_index > 0)
        self.next_trial_button.setEnabled(enable_trial_cycle and self.current_trial_index < self.max_trials_current_recording - 1)
        self.trial_index_label.setVisible(enable_any_data_controls and is_cycling_mode)
        self._update_trial_label()

        # File Nav (same)
        self.prev_file_button.setVisible(is_folder); self.next_file_button.setVisible(is_folder); self.folder_file_index_label.setVisible(is_folder)
        if is_folder:
             self.prev_file_button.setEnabled(self.current_file_index > 0)
             self.next_file_button.setEnabled(self.current_file_index < len(self.file_list) - 1)
             current_filename = "N/A"
             if 0 <= self.current_file_index < len(self.file_list): current_filename = self.file_list[self.current_file_index].name
             self.folder_file_index_label.setText(f"File {self.current_file_index + 1}/{len(self.file_list)}: {current_filename}")
        else: self.folder_file_index_label.setText("")

    # --- Trial Label Update --- (Unchanged)
    def _update_trial_label(self): # ... (same) ...
        if (self.current_recording and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0): self.trial_index_label.setText(f"{self.current_trial_index + 1} / {self.max_trials_current_recording}")
        else: self.trial_index_label.setText("N/A")

    # --- Zoom & Scroll Controls --- ## MOD: MAJOR REWORK

    # --- Zoom Calculation Helper (Inverted) ---
    def _calculate_new_range(self, base_range: Tuple[float, float], slider_value: int) -> Optional[Tuple[float, float]]:
        """Calculates new view range based on base range and INVERTED slider percentage."""
        if base_range is None or base_range[0] is None or base_range[1] is None: return None
        try:
            min_val, max_val = base_range
            center = (min_val + max_val) / 2.0
            full_span = max_val - min_val
            if full_span <= 0: full_span = 1.0 # Avoid zero span

            # ## MOD: Inverted Zoom Factor Calculation
            # Map slider MIN->MAX to zoom factor 1.0 -> MIN_ZOOM_FACTOR
            min_slider = float(self.SLIDER_RANGE_MIN)
            max_slider = float(self.SLIDER_RANGE_MAX)
            slider_pos_norm = (float(slider_value) - min_slider) / (max_slider - min_slider) if max_slider > min_slider else 0
            zoom_factor = 1.0 - slider_pos_norm * (1.0 - self.MIN_ZOOM_FACTOR)
            # Clamp zoom factor just in case
            zoom_factor = max(self.MIN_ZOOM_FACTOR, min(1.0, zoom_factor))

            new_span = full_span * zoom_factor
            new_min = center - new_span / 2.0
            new_max = center + new_span / 2.0
            return (new_min, new_max)
        except Exception as e:
            log.error(f"Error calculating new range: {e}", exc_info=True)
            return None

    # --- X Zoom/Scroll ---
    def _on_x_zoom_changed(self, value):
        """Applies zoom based on the X slider value."""
        if self.base_x_range is None or self._updating_viewranges: return
        new_x_range = self._calculate_new_range(self.base_x_range, value)
        if new_x_range is None: return

        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if first_visible_plot:
            self._updating_viewranges = True # Prevent feedback from sigXRangeChanged
            first_visible_plot.getViewBox().setXRange(new_x_range[0], new_x_range[1], padding=0)
            self._updating_viewranges = False
            # Update scrollbar page step after zoom
            self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_x_range)

    def _on_x_scrollbar_changed(self, value):
        """Applies pan based on the X scrollbar value."""
        if self.base_x_range is None or self._updating_scrollbars: return

        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if not first_visible_plot: return

        try:
            vb = first_visible_plot.getViewBox()
            current_x_range = vb.viewRange()[0]
            current_span = current_x_range[1] - current_x_range[0]
            if current_span <= 0: return

            # Map scrollbar value (0 to SCROLLBAR_MAX_RANGE) to data coordinates
            base_span = self.base_x_range[1] - self.base_x_range[0]
            if base_span <=0 : return
            # Effective scrollable range in data coords
            scrollable_data_range = base_span - current_span
            if scrollable_data_range < 0: scrollable_data_range = 0 # Don't allow negative

            # Calculate new minimum position
            new_min = self.base_x_range[0] + (float(value) / self.SCROLLBAR_MAX_RANGE) * scrollable_data_range
            new_max = new_min + current_span

            self._updating_viewranges = True # Prevent feedback
            vb.setXRange(new_min, new_max, padding=0)
            self._updating_viewranges = False
        except Exception as e:
            log.error(f"Error handling X scrollbar change: {e}", exc_info=True)
            self._updating_viewranges = False # Ensure flag is reset

    def _handle_vb_xrange_changed(self, vb, new_range):
        """Updates X scrollbar when ViewBox X range changes (e.g., mouse pan)."""
        if self._updating_viewranges or self.base_x_range is None: return
        # Update the scrollbar position based on the new view range
        self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_range)

    # --- Y Zoom/Scroll (Locking and Controls) ---
    def _on_y_lock_changed(self, state):
        """Handles the Y-axis lock checkbox state change."""
        self.y_axes_locked = bool(state == QtCore.Qt.Checked.value)
        log.info(f"Y-axes {'locked' if self.y_axes_locked else 'unlocked'}.")
        self._update_y_controls_visibility()
        # If locking, optionally sync views/scrollbars to global state? Or just apply future changes globally.
        # Let's just control future behavior.
        self._update_ui_state() # Update global control enable state

    def _update_y_controls_visibility(self):
        """Shows/hides global or individual Y sliders and scrollbars."""
        locked = self.y_axes_locked
        # Sliders
        self.global_y_slider_widget.setVisible(locked)
        self.individual_y_sliders_container.setVisible(not locked)
        # Scrollbars
        self.global_y_scrollbar_widget.setVisible(locked)
        self.individual_y_scrollbars_container.setVisible(not locked)

        visible_plots = {p.getViewBox()._synaptipy_chan_id: p for p in self.channel_plots.values() if p.isVisible()}

        if not locked:
            # Show/hide individual controls based on corresponding plot's visibility
            for chan_id, slider in self.individual_y_sliders.items():
                is_visible = chan_id in visible_plots
                slider.parentWidget().setVisible(is_visible) # Container widget
                has_base = self.base_y_ranges.get(chan_id) is not None
                slider.setEnabled(is_visible and has_base)

            for chan_id, scrollbar in self.individual_y_scrollbars.items():
                is_visible = chan_id in visible_plots
                scrollbar.setVisible(is_visible)
                has_base = self.base_y_ranges.get(chan_id) is not None
                scrollbar.setEnabled(is_visible and has_base)
        else:
             # Enable global controls only if there are visible plots with base ranges
             can_enable_global = bool(visible_plots) and any(self.base_y_ranges.get(ch_id) is not None for ch_id in visible_plots)
             self.global_y_slider.setEnabled(can_enable_global)
             self.global_y_scrollbar.setEnabled(can_enable_global)

    def _on_global_y_zoom_changed(self, value):
        """Applies zoom to all visible plots based on the global Y slider."""
        if not self.y_axes_locked or self._updating_viewranges: return
        self._apply_global_y_zoom(value)

    def _apply_global_y_zoom(self, value):
        """Helper function to apply a Y zoom value to all visible plots."""
        log.debug(f"Applying global Y zoom value: {value}")
        self._updating_viewranges = True # Prevent feedback loop
        updated_any = False
        for chan_id, plot in self.channel_plots.items():
            if plot.isVisible():
                base_y = self.base_y_ranges.get(chan_id)
                if base_y is None: continue
                new_y_range = self._calculate_new_range(base_y, value)
                if new_y_range:
                    plot.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
                    updated_any = True
                    # Update global scrollbar page step after zoom (use first plot's range)
                    if updated_any and plot == next(iter(self.channel_plots.values())): # Hacky way to do once
                        self._update_scrollbar_from_view(self.global_y_scrollbar, base_y, new_y_range)
        self._updating_viewranges = False

    def _on_individual_y_zoom_changed(self, chan_id, value):
        """Applies zoom to a specific plot based on its individual Y slider."""
        if self.y_axes_locked or self._updating_viewranges: return

        plot = self.channel_plots.get(chan_id)
        base_y = self.base_y_ranges.get(chan_id)
        scrollbar = self.individual_y_scrollbars.get(chan_id)

        if plot is None or not plot.isVisible() or base_y is None or scrollbar is None: return

        new_y_range = self._calculate_new_range(base_y, value)
        if new_y_range:
            self._updating_viewranges = True # Prevent feedback
            plot.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
            self._updating_viewranges = False
            # Update corresponding scrollbar page step
            self._update_scrollbar_from_view(scrollbar, base_y, new_y_range)

    def _on_global_y_scrollbar_changed(self, value):
        """Applies pan to all visible plots based on the global Y scrollbar."""
        if not self.y_axes_locked or self._updating_scrollbars: return
        self._apply_global_y_scroll(value)

    def _apply_global_y_scroll(self, value):
        """Helper to apply scroll value to all visible Y axes."""
        self._updating_viewranges = True # Prevent feedback loop
        try:
            first_processed = False
            current_span = None # Determine from first plot with valid range
            base_y_for_span = None

            # Find span first
            for chan_id, plot in self.channel_plots.items():
                 if plot.isVisible():
                    base_y = self.base_y_ranges.get(chan_id)
                    if base_y and base_y[0] is not None and base_y[1] is not None:
                         current_y_range = plot.getViewBox().viewRange()[1]
                         current_span = current_y_range[1] - current_y_range[0]
                         base_y_for_span = base_y
                         if current_span > 0: break # Found a valid span

            if current_span is None or current_span <= 0 or base_y_for_span is None:
                 self._updating_viewranges = False
                 return # Cannot determine span

            # Now apply scroll based on this span
            for chan_id, plot in self.channel_plots.items():
                if plot.isVisible():
                    base_y = self.base_y_ranges.get(chan_id)
                    if base_y is None or base_y[0] is None or base_y[1] is None: continue

                    base_span = base_y[1] - base_y[0]
                    if base_span <= 0: continue
                    scrollable_data_range = max(0, base_span - current_span)

                    new_min = base_y[0] + (float(value) / self.SCROLLBAR_MAX_RANGE) * scrollable_data_range
                    new_max = new_min + current_span
                    plot.getViewBox().setYRange(new_min, new_max, padding=0)

        except Exception as e:
            log.error(f"Error handling global Y scrollbar change: {e}", exc_info=True)
        finally:
             self._updating_viewranges = False # Ensure flag is reset

    def _on_individual_y_scrollbar_changed(self, chan_id, value):
        """Applies pan to a specific plot based on its individual Y scrollbar."""
        if self.y_axes_locked or self._updating_scrollbars: return

        plot = self.channel_plots.get(chan_id)
        base_y = self.base_y_ranges.get(chan_id)
        if plot is None or not plot.isVisible() or base_y is None or base_y[0] is None or base_y[1] is None: return

        try:
            vb = plot.getViewBox()
            current_y_range = vb.viewRange()[1]
            current_span = current_y_range[1] - current_y_range[0]
            if current_span <= 0: return

            base_span = base_y[1] - base_y[0]
            if base_span <= 0: return
            scrollable_data_range = max(0, base_span - current_span)

            new_min = base_y[0] + (float(value) / self.SCROLLBAR_MAX_RANGE) * scrollable_data_range
            new_max = new_min + current_span

            self._updating_viewranges = True # Prevent feedback
            vb.setYRange(new_min, new_max, padding=0)
            self._updating_viewranges = False
        except Exception as e:
            log.error(f"Error handling individual Y scrollbar change for {chan_id}: {e}", exc_info=True)
            self._updating_viewranges = False # Ensure flag is reset


    def _handle_vb_yrange_changed(self, vb, new_range):
        """Updates Y scrollbar(s) when ViewBox Y range changes."""
        if self._updating_viewranges: return # Caused by scrollbar/slider already

        chan_id = getattr(vb, '_synaptipy_chan_id', None)
        if chan_id is None: return # Should not happen
        base_y = self.base_y_ranges.get(chan_id)
        if base_y is None: return

        if self.y_axes_locked:
            # Update the global scrollbar (only needs to happen once per event)
            # Check if this VB is the first visible one to avoid multiple updates
            first_visible_vb = next((p.getViewBox() for p in self.channel_plots.values() if p.isVisible()), None)
            if vb == first_visible_vb:
                 self._update_scrollbar_from_view(self.global_y_scrollbar, base_y, new_range)
        else:
            # Update the specific individual scrollbar
            scrollbar = self.individual_y_scrollbars.get(chan_id)
            if scrollbar:
                 self._update_scrollbar_from_view(scrollbar, base_y, new_range)

    # --- Scrollbar Update Helper ---
    def _update_scrollbar_from_view(self, scrollbar: QtWidgets.QScrollBar, base_range: Optional[Tuple[float,float]], view_range: Tuple[float, float]):
        """Updates a scrollbar's value and pageStep based on view and base ranges."""
        if self._updating_scrollbars or base_range is None or base_range[0] is None or base_range[1] is None or view_range[0] is None or view_range[1] is None:
            # Disable scrollbar if ranges are invalid
            scrollbar.setEnabled(False)
            return

        base_min, base_max = base_range
        view_min, view_max = view_range
        base_span = base_max - base_min
        view_span = view_max - view_min

        if base_span <= 0 or view_span <= 0:
            # If base span is zero, disable. If view span is zero, maybe set pageStep small?
             scrollbar.setEnabled(False)
             return

        # Calculate page step (thumb size) as fraction of total range
        # Map view_span relative to base_span onto SCROLLBAR_MAX_RANGE
        page_step = int((view_span / base_span) * self.SCROLLBAR_MAX_RANGE)
        page_step = max(1, min(page_step, self.SCROLLBAR_MAX_RANGE)) # Clamp

        # Calculate value (scrollbar position) based on view_min relative to base_min
        # Map view_min position within the scrollable part of base_range onto SCROLLBAR_MAX_RANGE
        scrollable_data_range = base_span - view_span
        relative_pos = (view_min - base_min)
        if scrollable_data_range > 1e-9: # Avoid division by zero if view == base
             value = int((relative_pos / scrollable_data_range) * (self.SCROLLBAR_MAX_RANGE - page_step)) # Scale to available scroll range
             # Alternative simpler mapping: map relative pos in base range
             # value = int( (relative_pos / base_span) * self.SCROLLBAR_MAX_RANGE)

        else: # View covers the whole base range or more
             value = 0
        value = max(0, min(value, self.SCROLLBAR_MAX_RANGE - page_step)) # Clamp within scrollable range


        # Prevent signal emission while setting programmatically
        self._updating_scrollbars = True
        scrollbar.blockSignals(True)
        scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE - page_step if self.SCROLLBAR_MAX_RANGE > page_step else 0) # Adjust range based on pageStep
        scrollbar.setPageStep(page_step)
        scrollbar.setValue(value)
        scrollbar.setEnabled(True) # Enable if calculation was valid
        scrollbar.blockSignals(False)
        self._updating_scrollbars = False


    # --- Reset View ---
    def _reset_view(self):
        """Resets view, captures base ranges, resets sliders, updates scrollbars."""
        log.info("Reset View triggered.")
        visible_plots_dict = {p.getViewBox()._synaptipy_chan_id: p for p in self.channel_plots.values() if p.isVisible()}
        if not visible_plots_dict:
            log.debug("Reset View: No visible plots found.")
            self.base_x_range = None; self.base_y_ranges.clear()
            self._reset_scrollbar(self.x_scrollbar); self._reset_scrollbar(self.global_y_scrollbar)
            # Reset sliders anyway
            self._reset_all_sliders()
            self._update_ui_state()
            return

        # --- Autorange all visible plots ---
        for plot in visible_plots_dict.values():
            plot.getViewBox().autoRange()

        # --- Capture base ranges AFTER autoRange ---
        first_chan_id, first_plot = next(iter(visible_plots_dict.items()))
        try:
            self.base_x_range = first_plot.getViewBox().viewRange()[0]
            log.debug(f"Reset View: New base X range: {self.base_x_range}")
        except Exception as e: log.error(f"Reset View: Error getting base X range: {e}"); self.base_x_range = None

        self.base_y_ranges.clear()
        for chan_id, plot in visible_plots_dict.items():
             try:
                 self.base_y_ranges[chan_id] = plot.getViewBox().viewRange()[1]
                 log.debug(f"Reset View: New base Y range for {chan_id}: {self.base_y_ranges[chan_id]}")
             except Exception as e: log.error(f"Reset View: Error getting base Y range for {chan_id}: {e}")

        # --- Reset all sliders to default (zoomed out) ---
        self._reset_all_sliders()

        # --- Update scrollbars based on the new (full) view ranges ---
        if self.base_x_range:
             self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, self.base_x_range)

        if self.y_axes_locked:
             first_visible_base_y = next((self.base_y_ranges.get(ch_id) for ch_id in visible_plots_dict if self.base_y_ranges.get(ch_id)), None)
             if first_visible_base_y:
                 self._update_scrollbar_from_view(self.global_y_scrollbar, first_visible_base_y, first_visible_base_y)
             else: self._reset_scrollbar(self.global_y_scrollbar)
        else:
             for chan_id, scrollbar in self.individual_y_scrollbars.items():
                 base_y = self.base_y_ranges.get(chan_id)
                 if chan_id in visible_plots_dict and base_y:
                     self._update_scrollbar_from_view(scrollbar, base_y, base_y)
                 else: self._reset_scrollbar(scrollbar) # Reset/disable if not visible or no base range

        log.debug("Reset View: Sliders reset, scrollbars updated.")
        self._update_ui_state() # Ensure controls are enabled/disabled correctly

    def _reset_all_sliders(self):
        """Helper to reset all zoom sliders to their default value."""
        sliders = [self.x_zoom_slider, self.global_y_slider] + list(self.individual_y_sliders.values())
        for slider in sliders:
            slider.blockSignals(True)
            slider.setValue(self.SLIDER_DEFAULT_VALUE)
            slider.blockSignals(False)

    def _reset_single_plot_view(self, chan_id: str):
        """Resets view for a single plot, updates its base Y range, slider, and scrollbar."""
        plot_item = self.channel_plots.get(chan_id)
        if not plot_item or not plot_item.isVisible(): return

        log.debug(f"Resetting single plot view for {chan_id}")
        plot_item.getViewBox().autoRange()

        # Update base Y range
        try:
            new_range = plot_item.getViewBox().viewRange()[1]
            self.base_y_ranges[chan_id] = new_range
            log.debug(f"Reset Single View: New base Y range for {chan_id}: {new_range}")
        except Exception as e:
            log.error(f"Reset Single View: Error getting base Y range for {chan_id}: {e}")
            if chan_id in self.base_y_ranges: del self.base_y_ranges[chan_id]

        # Reset the corresponding individual Y slider
        slider = self.individual_y_sliders.get(chan_id)
        if slider:
            slider.blockSignals(True)
            slider.setValue(self.SLIDER_DEFAULT_VALUE)
            slider.blockSignals(False)
            log.debug(f"Reset Single View: Slider for {chan_id} reset.")

        # Reset the corresponding individual Y scrollbar
        scrollbar = self.individual_y_scrollbars.get(chan_id)
        if scrollbar and new_range:
            self._update_scrollbar_from_view(scrollbar, new_range, new_range) # Update based on new autorange
            log.debug(f"Reset Single View: Scrollbar for {chan_id} updated.")

        # If Y axes are locked, resetting one plot should ideally reset all to maintain consistency?
        # Or at least reset the global controls based on this one if it's the 'reference'?
        # For now, let's also reset the global controls if locked.
        if self.y_axes_locked:
            self.global_y_slider.blockSignals(True)
            self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            self.global_y_slider.blockSignals(False)
            if new_range: # Use this plot's new base range to update global scrollbar
                 self._update_scrollbar_from_view(self.global_y_scrollbar, new_range, new_range)
            # Re-apply global zoom/scroll? No, reset should put everything to full view.

        # We don't reset X controls here as they are linked.


    # --- Trial Navigation Slots ---
    def _next_trial(self): # (Same as before - calls _reset_view)
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0:
            if self.current_trial_index < self.max_trials_current_recording - 1:
                self.current_trial_index += 1; log.debug(f"Next trial: {self.current_trial_index + 1}")
                self._update_plot() # Plot data first
                self._reset_view() # Reset view, base ranges, sliders, scrollbars
            else: log.debug("Already at last trial.")
    def _prev_trial(self): # (Same as before - calls _reset_view)
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE:
            if self.current_trial_index > 0:
                self.current_trial_index -= 1; log.debug(f"Previous trial: {self.current_trial_index + 1}")
                self._update_plot() # Plot data first
                self._reset_view() # Reset view, base ranges, sliders, scrollbars
            else: log.debug("Already at first trial.")

    # --- Folder Navigation Slots --- (Unchanged logic)
    def _next_file_folder(self): # ... (same) ...
        if self.file_list and self.current_file_index < len(self.file_list) - 1: self.current_file_index += 1; self._load_and_display_file(self.file_list[self.current_file_index])
    def _prev_file_folder(self): # ... (same) ...
        if self.file_list and self.current_file_index > 0: self.current_file_index -= 1; self._load_and_display_file(self.file_list[self.current_file_index])

    # --- NWB Export Slot --- (Unchanged)
    def _export_to_nwb(self): # ... (same) ...
        if not self.current_recording: return
        default_filename = self.current_recording.source_file.with_suffix(".nwb").name; output_path_str, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save NWB", default_filename, "NWB Files (*.nwb)")
        if not output_path_str: self.statusBar.showMessage("NWB export cancelled.", 3000); return
        output_path = Path(output_path_str); default_id = str(uuid.uuid4()); default_time = self.current_recording.session_start_time_dt or datetime.now()
        if default_time.tzinfo is None:
            try: default_time = default_time.replace(tzinfo=tzlocal.get_localzone() if tzlocal else timezone.utc)
            except Exception: default_time = default_time.replace(tzinfo=timezone.utc)
        dialog = NwbMetadataDialog(default_id, default_time, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted: session_metadata = dialog.get_metadata();
        else: self.statusBar.showMessage("NWB export cancelled.", 3000); return
        if session_metadata is None: return
        self.statusBar.showMessage(f"Exporting NWB..."); QtWidgets.QApplication.processEvents()
        try: self.nwb_exporter.export(self.current_recording, output_path, session_metadata); log.info(f"Exported NWB to {output_path}"); self.statusBar.showMessage(f"Export successful: {output_path.name}", 5000); QtWidgets.QMessageBox.information(self, "Export Successful", f"Saved to:\n{output_path}")
        except (ValueError, ExportError, SynaptipyError) as e: log.error(f"NWB Export failed: {e}", exc_info=False); self.statusBar.showMessage(f"NWB Export failed: {e}", 5000); QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export:\n{e}")
        except Exception as e: log.error(f"Unexpected NWB Export error: {e}", exc_info=True); self.statusBar.showMessage("Unexpected NWB Export error.", 5000); QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Unexpected error:\n{e}")

    # --- Close Event --- (Unchanged)
    def closeEvent(self, event: QtGui.QCloseEvent): # ... (same) ...
        log.info("Close event triggered. Shutting down.")
        self.graphics_layout_widget.clear()
        event.accept()
# --- MainWindow Class --- END ---

# --- Main Execution Block (Example - Updated Dummy Classes) ---
if __name__ == '__main__':
    # Setup basic logging to console for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s') # Use INFO for less noise

    # Create dummy Synaptipy classes/functions if running standalone for UI testing
    if 'Synaptipy' not in sys.modules:
        print("Warning: Synaptipy modules not found. Using dummy implementations for UI testing.")
        # (Use updated dummy classes from previous response if needed)
        class DummyChannel:
            def __init__(self, id, name, units='mV', num_trials=5, duration=1.0, rate=1000.0):
                self.id = id; self.name = name; self.units = units; self.num_trials = num_trials
                self._duration = duration; self._rate = rate
                self.data = [np.random.randn(int(duration * rate)) * (i+1) * 0.1 + (np.sin(np.linspace(0, (i+1)*np.pi, int(duration*rate)))* (i+1)) for i in range(num_trials)] # Add sine wave
                self.tvecs = [np.linspace(0, duration, int(duration*rate), endpoint=False) for _ in range(num_trials)]
            def get_data(self, trial_idx): return self.data[trial_idx] if 0 <= trial_idx < self.num_trials else None
            def get_relative_time_vector(self, trial_idx): return self.tvecs[trial_idx] if 0 <= trial_idx < self.num_trials else None
            def get_averaged_data(self): return np.mean(self.data, axis=0) if self.num_trials > 0 else None
            def get_relative_averaged_time_vector(self): return self.tvecs[0] if self.num_trials > 0 else None

        class DummyRecording:
            def __init__(self, filepath, num_channels=3):
                self.source_file = Path(filepath)
                self.sampling_rate = 10000.0 # Higher rate
                self.duration = 2.0 # Longer duration
                self.num_channels = num_channels
                self.max_trials = 10 # More trials
                self.channels = {f'ch{i}': DummyChannel(f'ch{i}', f'Channel {i}', units='pA' if i%2==0 else 'mV', num_trials=self.max_trials, duration=self.duration, rate=self.sampling_rate) for i in range(num_channels)}
                self.session_start_time_dt = datetime.now()

        class DummyNeoAdapter:
            def get_supported_file_filter(self): return "Dummy Files (*.dummy);;All Files (*)"
            def read_recording(self, filepath):
                if not Path(filepath).exists(): Path(filepath).touch()
                print(f"DummyNeoAdapter: Reading {filepath}")
                num_chan = 3 if '3ch' in filepath.name else ( 5 if '5ch' in filepath.name else 2)
                return DummyRecording(filepath, num_channels=num_chan)

        class DummyNWBExporter:
            def export(self, recording, output_path, metadata): print(f"DummyNWBExporter: Exporting to {output_path} with metadata {metadata}")

        # Replace real classes with dummies
        NeoAdapter = DummyNeoAdapter
        NWBExporter = DummyNWBExporter
        Recording = DummyRecording
        Channel = DummyChannel
        # Make constants available if Synaptipy not installed
        class VisConstants:
            TRIAL_COLOR = '#808080'; TRIAL_ALPHA = 80; AVERAGE_COLOR = '#FF0000' # Reduced alpha slightly
            DEFAULT_PLOT_PEN_WIDTH = 1; DOWNSAMPLING_THRESHOLD = 1000 # Increased threshold

        # Define error classes if needed
        class SynaptipyError(Exception): pass
        class FileReadError(SynaptipyError): pass
        class UnsupportedFormatError(SynaptipyError): pass
        class ExportError(SynaptipyError): pass

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())