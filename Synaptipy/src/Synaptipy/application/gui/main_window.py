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
## MOD: Rearranged Right Panel: Y Scrollbars are now immediately right of plots, Y Zoom sliders are further right.
## MOD: Ensured individual Y controls stretch vertically.
## MOD: Ensured global Y controls AND group boxes stretch vertically.
## MOD: Added feature to select multiple trials during cycle mode and plot their average as an overlay.
"""

# --- Standard Library Imports ---
import logging
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set
import uuid
from datetime import datetime, timezone
from functools import partial # Needed for connecting individual sliders/scrollbars

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
# Placeholder imports for standalone testing, replace with actual ones
try:
    from Synaptipy.core.data_model import Recording, Channel
    from Synaptipy.infrastructure.file_readers import NeoAdapter
    from Synaptipy.infrastructure.exporters import NWBExporter
    from Synaptipy.shared import constants as VisConstants # Use alias
    from Synaptipy.shared.error_handling import (
        FileReadError, UnsupportedFormatError, ExportError, SynaptipyError)
except ImportError:
    print("Warning: Synaptipy modules not found. Using dummy implementations.")
    # Define dummy classes inline if needed for testing (see __main__ block)
    pass


# --- Configure Logging ---
log = logging.getLogger(__name__)

# --- PyQtGraph Configuration ---
pg.setConfigOption('imageAxisOrder', 'row-major')
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# --- NWB Metadata Dialog ---
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
    SLIDER_DEFAULT_VALUE = SLIDER_RANGE_MIN # Default is zoomed OUT
    MIN_ZOOM_FACTOR = 0.01 # e.g., 1% zoom at max slider value
    SCROLLBAR_MAX_RANGE = 10000 # Arbitrary large range for scrollbar mapping
    # MOD: Pen for selected average plot
    SELECTED_AVG_PEN = pg.mkPen('#00FF00', width=VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1) if 'VisConstants' in globals() else pg.mkPen('g', width=2)

    def __init__(self):
        super().__init__(); self.setWindowTitle("Synaptipy"); self.setGeometry(50, 50, 1700, 950) # Keep width for Y controls
        # Use dummy classes if real ones failed to import
        global NeoAdapter, NWBExporter, Recording, Channel, VisConstants, SynaptipyError, FileReadError, UnsupportedFormatError, ExportError
        if 'NeoAdapter' not in globals(): NeoAdapter = DummyNeoAdapter
        if 'NWBExporter' not in globals(): NWBExporter = DummyNWBExporter
        if 'Recording' not in globals(): Recording = DummyRecording
        if 'Channel' not in globals(): Channel = DummyChannel
        if 'VisConstants' not in globals(): VisConstants = DummyVisConstants
        if 'SynaptipyError' not in globals(): SynaptipyError, FileReadError, UnsupportedFormatError, ExportError = DummyErrors()

        self.neo_adapter = NeoAdapter(); self.nwb_exporter = NWBExporter()
        self.current_recording: Optional[Recording] = None; self.file_list: List[Path] = []; self.current_file_index: int = -1
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}; self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG; self.current_trial_index: int = 0; self.max_trials_current_recording: int = 0

        ## State variables for zoom control
        self.y_axes_locked: bool = True
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_y_ranges: Dict[str, Optional[Tuple[float, float]]] = {}
        self.individual_y_sliders: Dict[str, QtWidgets.QSlider] = {}
        self.individual_y_slider_labels: Dict[str, QtWidgets.QLabel] = {}

        ## State variables for scrollbars
        self.individual_y_scrollbars: Dict[str, QtWidgets.QScrollBar] = {}
        self._updating_scrollbars: bool = False # Flag to prevent signal loops
        self._updating_viewranges: bool = False # Flag to prevent signal loops

        ## MOD: State variables for multi-trial selection
        self.selected_trial_indices: Set[int] = set()
        self.selected_average_plot_items: Dict[str, pg.PlotDataItem] = {} # Stores the temporary average plot item per channel

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

        file_op_group = QtWidgets.QGroupBox("Load Data"); file_op_layout = QtWidgets.QHBoxLayout(file_op_group)
        self.open_button_ui = QtWidgets.QPushButton("Open..."); file_op_layout.addWidget(self.open_button_ui); left_panel_layout.addWidget(file_op_group)

        # --- Display Options Group (MODIFIED) ---
        display_group = QtWidgets.QGroupBox("Display Options")
        display_layout = QtWidgets.QVBoxLayout(display_group) # Use QVBoxLayout for vertical arrangement

        # Plot Mode ComboBox
        plot_mode_layout = QtWidgets.QHBoxLayout()
        plot_mode_layout.addWidget(QtWidgets.QLabel("Plot Mode:"))
        self.plot_mode_combobox = QtWidgets.QComboBox()
        self.plot_mode_combobox.addItems(["Overlay All + Avg", "Cycle Single Trial"])
        self.plot_mode_combobox.setCurrentIndex(self.current_plot_mode)
        plot_mode_layout.addWidget(self.plot_mode_combobox)
        display_layout.addLayout(plot_mode_layout) # Add the HBox to the VBox

        # Downsample Checkbox
        self.downsample_checkbox = QtWidgets.QCheckBox("Auto Downsample Plot")
        self.downsample_checkbox.setChecked(True)
        display_layout.addWidget(self.downsample_checkbox)

        # Separator
        sep1 = QtWidgets.QFrame(); sep1.setFrameShape(QtWidgets.QFrame.Shape.HLine); sep1.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        display_layout.addWidget(sep1)

        # Multi-Trial Selection Widgets
        display_layout.addWidget(QtWidgets.QLabel("Manual Trial Averaging:"))
        self.select_trial_button = QtWidgets.QPushButton("Add Current Trial to Avg Set")
        self.select_trial_button.setToolTip("Add/Remove the currently viewed trial (in Cycle Mode) to the set for averaging.")
        display_layout.addWidget(self.select_trial_button)

        self.selected_trials_display = QtWidgets.QLabel("Selected: None")
        self.selected_trials_display.setWordWrap(True) # Allow text wrapping
        display_layout.addWidget(self.selected_trials_display)

        clear_avg_layout = QtWidgets.QHBoxLayout() # Layout for clear/plot buttons
        self.clear_selection_button = QtWidgets.QPushButton("Clear Avg Set")
        self.clear_selection_button.setToolTip("Clear the set of selected trials.")
        clear_avg_layout.addWidget(self.clear_selection_button)

        self.show_selected_average_button = QtWidgets.QPushButton("Plot Selected Avg")
        self.show_selected_average_button.setToolTip("Toggle the display of the average of selected trials as an overlay.")
        self.show_selected_average_button.setCheckable(True) # Make it a toggle button
        clear_avg_layout.addWidget(self.show_selected_average_button)
        display_layout.addLayout(clear_avg_layout) # Add HBox for buttons

        left_panel_layout.addWidget(display_group) # Add the completed group to the main left layout
        # --- End Display Options Group Modification ---

        self.channel_select_group = QtWidgets.QGroupBox("Channels"); self.channel_scroll_area = QtWidgets.QScrollArea(); self.channel_scroll_area.setWidgetResizable(True)
        self.channel_select_widget = QtWidgets.QWidget(); self.channel_checkbox_layout = QtWidgets.QVBoxLayout(self.channel_select_widget); self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignTop)
        self.channel_scroll_area.setWidget(self.channel_select_widget); channel_group_layout = QtWidgets.QVBoxLayout(self.channel_select_group); channel_group_layout.addWidget(self.channel_scroll_area); left_panel_layout.addWidget(self.channel_select_group)

        meta_group = QtWidgets.QGroupBox("File Information"); meta_layout = QtWidgets.QFormLayout(meta_group)
        self.filename_label = QtWidgets.QLabel("N/A"); self.sampling_rate_label = QtWidgets.QLabel("N/A"); self.channels_label = QtWidgets.QLabel("N/A"); self.duration_label = QtWidgets.QLabel("N/A")
        meta_layout.addRow("File:", self.filename_label); meta_layout.addRow("Sampling Rate:", self.sampling_rate_label); meta_layout.addRow("Duration:", self.duration_label); meta_layout.addRow("Channels:", self.channels_label)
        left_panel_layout.addWidget(meta_group); left_panel_layout.addStretch();
        main_layout.addWidget(left_panel_widget, stretch=0) # Give left panel fixed size

        # --- Center Panel (Plots, X Controls) ---
        center_panel_widget = QtWidgets.QWidget()
        center_panel_layout = QtWidgets.QVBoxLayout(center_panel_widget)
        nav_layout = QtWidgets.QHBoxLayout(); self.prev_file_button = QtWidgets.QPushButton("<< Prev File"); self.next_file_button = QtWidgets.QPushButton("Next File >>"); self.folder_file_index_label = QtWidgets.QLabel("")
        nav_layout.addWidget(self.prev_file_button); nav_layout.addStretch(); nav_layout.addWidget(self.folder_file_index_label); nav_layout.addStretch(); nav_layout.addWidget(self.next_file_button); center_panel_layout.addLayout(nav_layout)
        self.graphics_layout_widget = pg.GraphicsLayoutWidget(); center_panel_layout.addWidget(self.graphics_layout_widget, stretch=1)
        self.x_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Horizontal); self.x_scrollbar.setFixedHeight(20); self.x_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE); center_panel_layout.addWidget(self.x_scrollbar)
        plot_controls_layout = QtWidgets.QHBoxLayout()
        view_group = QtWidgets.QGroupBox("View"); view_layout = QtWidgets.QHBoxLayout(view_group); self.reset_view_button = QtWidgets.QPushButton("Reset View"); view_layout.addWidget(self.reset_view_button); plot_controls_layout.addWidget(view_group)
        x_zoom_group = QtWidgets.QGroupBox("X Zoom (Min=Out, Max=In)"); x_zoom_layout = QtWidgets.QHBoxLayout(x_zoom_group); self.x_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.x_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX); self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.x_zoom_slider.setToolTip("Adjust X-axis zoom (Shared)"); x_zoom_layout.addWidget(self.x_zoom_slider); plot_controls_layout.addWidget(x_zoom_group, stretch=1)
        trial_group = QtWidgets.QGroupBox("Trial"); trial_layout = QtWidgets.QHBoxLayout(trial_group); self.prev_trial_button = QtWidgets.QPushButton("<"); self.next_trial_button = QtWidgets.QPushButton(">"); self.trial_index_label = QtWidgets.QLabel("N/A"); trial_layout.addWidget(self.prev_trial_button); trial_layout.addWidget(self.trial_index_label); trial_layout.addWidget(self.next_trial_button); plot_controls_layout.addWidget(trial_group)
        center_panel_layout.addLayout(plot_controls_layout)
        main_layout.addWidget(center_panel_widget, stretch=1)

        # --- Right Panel (Y Controls: Scroll then Zoom) ---
        y_controls_panel_widget = QtWidgets.QWidget()
        y_controls_panel_layout = QtWidgets.QHBoxLayout(y_controls_panel_widget)
        y_controls_panel_widget.setFixedWidth(220); y_controls_panel_layout.setContentsMargins(0, 0, 0, 0); y_controls_panel_layout.setSpacing(5)
        # --- Y Scroll Column (FIRST) ---
        y_scroll_widget = QtWidgets.QWidget(); y_scroll_layout = QtWidgets.QVBoxLayout(y_scroll_widget); y_scroll_layout.setContentsMargins(0,0,0,0); y_scroll_layout.setSpacing(5)
        y_scroll_group = QtWidgets.QGroupBox("Y Scroll"); y_scroll_group_layout = QtWidgets.QVBoxLayout(y_scroll_group); y_scroll_layout.addWidget(y_scroll_group, stretch=1) # Group stretches
        self.global_y_scrollbar_widget = QtWidgets.QWidget(); global_y_scrollbar_layout = QtWidgets.QVBoxLayout(self.global_y_scrollbar_widget); global_y_scrollbar_layout.setContentsMargins(0,0,0,0); global_y_scrollbar_layout.setSpacing(2)
        global_y_scrollbar_label = QtWidgets.QLabel("Global Scroll"); global_y_scrollbar_label.setAlignment(QtCore.Qt.AlignCenter)
        self.global_y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Vertical); self.global_y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE); self.global_y_scrollbar.setToolTip("Scroll Y-axis (All visible)")
        global_y_scrollbar_layout.addWidget(global_y_scrollbar_label); global_y_scrollbar_layout.addWidget(self.global_y_scrollbar, stretch=1) # Scrollbar stretches
        y_scroll_group_layout.addWidget(self.global_y_scrollbar_widget, stretch=1) # Widget containing global stretches
        self.individual_y_scrollbars_container = QtWidgets.QWidget(); self.individual_y_scrollbars_layout = QtWidgets.QVBoxLayout(self.individual_y_scrollbars_container); self.individual_y_scrollbars_layout.setContentsMargins(0, 5, 0, 0); self.individual_y_scrollbars_layout.setSpacing(10); self.individual_y_scrollbars_layout.setAlignment(QtCore.Qt.AlignTop)
        y_scroll_group_layout.addWidget(self.individual_y_scrollbars_container, stretch=1) # Container for individual stretches
        y_controls_panel_layout.addWidget(y_scroll_widget, stretch=1) # Column stretches
        # --- Y Zoom Column (SECOND) ---
        y_zoom_widget = QtWidgets.QWidget(); y_zoom_layout = QtWidgets.QVBoxLayout(y_zoom_widget); y_zoom_layout.setContentsMargins(0,0,0,0); y_zoom_layout.setSpacing(5)
        y_zoom_group = QtWidgets.QGroupBox("Y Zoom"); y_zoom_group_layout = QtWidgets.QVBoxLayout(y_zoom_group); y_zoom_layout.addWidget(y_zoom_group, stretch=1) # Group stretches
        self.y_lock_checkbox = QtWidgets.QCheckBox("Lock Axes"); self.y_lock_checkbox.setChecked(self.y_axes_locked); self.y_lock_checkbox.setToolTip("Lock/Unlock Y-axis zoom & scroll"); y_zoom_group_layout.addWidget(self.y_lock_checkbox)
        self.global_y_slider_widget = QtWidgets.QWidget(); global_y_slider_layout = QtWidgets.QVBoxLayout(self.global_y_slider_widget); global_y_slider_layout.setContentsMargins(0,0,0,0); global_y_slider_layout.setSpacing(2)
        global_y_slider_label = QtWidgets.QLabel("Global Zoom"); global_y_slider_label.setAlignment(QtCore.Qt.AlignCenter)
        self.global_y_slider = QtWidgets.QSlider(QtCore.Qt.Vertical); self.global_y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.setToolTip("Adjust Y-axis zoom (All visible)")
        global_y_slider_layout.addWidget(global_y_slider_label); global_y_slider_layout.addWidget(self.global_y_slider, stretch=1) # Slider stretches
        y_zoom_group_layout.addWidget(self.global_y_slider_widget, stretch=1) # Widget containing global stretches
        self.individual_y_sliders_container = QtWidgets.QWidget(); self.individual_y_sliders_layout = QtWidgets.QVBoxLayout(self.individual_y_sliders_container); self.individual_y_sliders_layout.setContentsMargins(0, 5, 0, 0); self.individual_y_sliders_layout.setSpacing(10); self.individual_y_sliders_layout.setAlignment(QtCore.Qt.AlignTop)
        y_zoom_group_layout.addWidget(self.individual_y_sliders_container, stretch=1) # Container for individual stretches
        y_controls_panel_layout.addWidget(y_zoom_widget, stretch=1) # Column stretches
        main_layout.addWidget(y_controls_panel_widget, stretch=0) # Right panel fixed size

        # --- Status Bar ---
        self.statusBar = QtWidgets.QStatusBar(); self.setStatusBar(self.statusBar); self.statusBar.showMessage("Ready.")

        # Initial state for Y controls visibility and trial selection display
        self._update_y_controls_visibility()
        self._update_selected_trials_display()

    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        self.open_file_action.triggered.connect(self._open_file_or_folder)
        self.export_nwb_action.triggered.connect(self._export_to_nwb); self.quit_action.triggered.connect(self.close)
        self.open_button_ui.clicked.connect(self._open_file_or_folder)
        self.downsample_checkbox.stateChanged.connect(self._trigger_plot_update); self.plot_mode_combobox.currentIndexChanged.connect(self._on_plot_mode_changed)
        self.reset_view_button.clicked.connect(self._reset_view)
        self.prev_trial_button.clicked.connect(self._prev_trial); self.next_trial_button.clicked.connect(self._next_trial)
        self.prev_file_button.clicked.connect(self._prev_file_folder); self.next_file_button.clicked.connect(self._next_file_folder)

        ## Connect zoom sliders and lock checkbox
        self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
        self.y_lock_checkbox.stateChanged.connect(self._on_y_lock_changed)
        self.global_y_slider.valueChanged.connect(self._on_global_y_zoom_changed)

        ## Connect scrollbars
        self.x_scrollbar.valueChanged.connect(self._on_x_scrollbar_changed)
        self.global_y_scrollbar.valueChanged.connect(self._on_global_y_scrollbar_changed)
        # Individual Y sliders/scrollbars & ViewBox signals are connected in _create_channel_ui

        ## MOD: Connect multi-trial selection buttons
        self.select_trial_button.clicked.connect(self._toggle_select_current_trial)
        self.clear_selection_button.clicked.connect(self._clear_avg_selection)
        self.show_selected_average_button.toggled.connect(self._toggle_plot_selected_average) # Use toggled signal

    # --- Reset UI and State ---
    def _reset_ui_and_state_for_new_file(self):
        """Fully resets UI elements and state related to channels and plots."""
        log.info("Resetting UI and state for new file...")
        self._remove_selected_average_plots() # Remove any lingering average plots first
        self.selected_trial_indices.clear() # Clear selection set
        self._update_selected_trials_display() # Update display label
        # Reset toggle button state without triggering its signal
        self.show_selected_average_button.blockSignals(True)
        self.show_selected_average_button.setChecked(False)
        self.show_selected_average_button.blockSignals(False)

        # Clear Checkboxes UI and state
        for checkbox in self.channel_checkboxes.values():
            try:
                if checkbox: checkbox.stateChanged.disconnect(self._trigger_plot_update)
            except (TypeError, RuntimeError): # Catch potential errors if already disconnected
                pass # Ignore disconnection error, goal is to remove
        while self.channel_checkbox_layout.count():
            item = self.channel_checkbox_layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater() # Safely delete widget
        self.channel_checkboxes.clear(); self.channel_select_group.setEnabled(False)

        # Clear Plot Layout and state
        # Safely disconnect signals from ViewBoxes before clearing
        for plot in self.channel_plots.values():
            if plot:
                vb = plot.getViewBox()
                if vb:
                    try: vb.sigXRangeChanged.disconnect(self._handle_vb_xrange_changed)
                    except (TypeError, RuntimeError): pass
                    try: vb.sigYRangeChanged.disconnect(self._handle_vb_yrange_changed)
                    except (TypeError, RuntimeError): pass
        self.graphics_layout_widget.clear(); self.channel_plots.clear(); self.channel_plot_data_items.clear()

        # Clear individual Y sliders UI and state
        # Safely disconnect signals before removing
        for chan_id, slider in self.individual_y_sliders.items():
            try: slider.valueChanged.disconnect() # Disconnect all slots connected by valueChanged
            except (TypeError, RuntimeError): pass
        while self.individual_y_sliders_layout.count():
            item = self.individual_y_sliders_layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater()
        self.individual_y_sliders.clear(); self.individual_y_slider_labels.clear()

        # Clear individual Y scrollbars UI and state
        # Safely disconnect signals before removing
        for chan_id, scrollbar in self.individual_y_scrollbars.items():
            try: scrollbar.valueChanged.disconnect() # Disconnect all slots connected by valueChanged
            except (TypeError, RuntimeError): pass
        while self.individual_y_scrollbars_layout.count():
            item = self.individual_y_scrollbars_layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater() # Deletes the scrollbar itself
        self.individual_y_scrollbars.clear()

        # Reset Data State Variables
        self.current_recording = None; self.max_trials_current_recording = 0; self.current_trial_index = 0

        # Reset zoom state
        self.base_x_range = None; self.base_y_ranges.clear()
        self.x_zoom_slider.blockSignals(True); self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.x_zoom_slider.blockSignals(False)
        self.global_y_slider.blockSignals(True); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.blockSignals(False)
        self.y_axes_locked = True; self.y_lock_checkbox.blockSignals(True); self.y_lock_checkbox.setChecked(self.y_axes_locked); self.y_lock_checkbox.blockSignals(False)

        # Reset scrollbar state
        self._reset_scrollbar(self.x_scrollbar)
        self._reset_scrollbar(self.global_y_scrollbar)

        self._update_y_controls_visibility() # Ensure correct initial visibility

        # Reset Metadata Display
        self._clear_metadata_display()
        # Reset Trial Label
        self._update_trial_label()
        # Update UI state including new buttons
        self._update_ui_state()


    def _reset_scrollbar(self, scrollbar: QtWidgets.QScrollBar):
        """Helper to reset a scrollbar to its default state (full range visible, disabled)."""
        scrollbar.blockSignals(True)
        try:
            scrollbar.setRange(0, 0) # Effectively disable scrolling range
            scrollbar.setPageStep(self.SCROLLBAR_MAX_RANGE) # Make the 'page' cover the max possible range
            scrollbar.setValue(0) # Set value to the beginning
        finally:
            scrollbar.blockSignals(False)
        scrollbar.setEnabled(False) # Disable until data is loaded and view range determined

    # --- Create Channel UI (Checkboxes, Plots, Y Sliders, Y Scrollbars) ---
    def _create_channel_ui(self):
        """Creates checkboxes, PlotItems, Y-sliders, AND Y-scrollbars. Called ONCE per file load."""
        if not self.current_recording or not self.current_recording.channels:
            log.warning("No data to create channel UI."); self.channel_select_group.setEnabled(False); return
        self.channel_select_group.setEnabled(True)
        # Sort by channel ID (or name if available and desired)
        sorted_channel_items = sorted(self.current_recording.channels.items(), key=lambda item: str(item[0]))
        log.info(f"Creating UI for {len(sorted_channel_items)} channels.")
        last_plot_item = None # To link X axes

        for i, (chan_id, channel) in enumerate(sorted_channel_items):
            # Safety check: Skip if UI elements somehow already exist for this ID
            if chan_id in self.channel_checkboxes or chan_id in self.channel_plots:
                log.error(f"State Error: UI element {chan_id} exists before creation!"); continue

            # --- Checkbox ---
            checkbox = QtWidgets.QCheckBox(f"{channel.name or f'Ch {chan_id}'}")
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._trigger_plot_update)
            self.channel_checkbox_layout.addWidget(checkbox)
            self.channel_checkboxes[chan_id] = checkbox

            # --- PlotItem ---
            plot_item = self.graphics_layout_widget.addPlot(row=i, col=0)
            plot_item.setLabel('left', channel.name or f'Ch {chan_id}', units=channel.units or 'units')
            plot_item.showGrid(x=True, y=True, alpha=0.3)
            self.channel_plots[chan_id] = plot_item

            # --- ViewBox Setup ---
            vb = plot_item.getViewBox()
            vb.setMouseMode(pg.ViewBox.RectMode) # Enable rubber-band zoom
            # Store channel ID on the ViewBox for easy retrieval in signal handlers
            vb._synaptipy_chan_id = chan_id # Custom attribute
            vb.sigXRangeChanged.connect(self._handle_vb_xrange_changed)
            vb.sigYRangeChanged.connect(self._handle_vb_yrange_changed)

            # --- Link Axes ---
            if last_plot_item:
                plot_item.setXLink(last_plot_item) # Link X axis to the plot above
                plot_item.hideAxis('bottom') # Hide redundant bottom axis
            last_plot_item = plot_item

            # --- Individual Y Zoom Slider ---
            # Use a container widget to group label and slider for layout/visibility control
            ind_y_slider_widget = QtWidgets.QWidget()
            ind_y_slider_layout = QtWidgets.QVBoxLayout(ind_y_slider_widget)
            ind_y_slider_layout.setContentsMargins(0,0,0,0)
            ind_y_slider_layout.setSpacing(2)
            # Label
            slider_label_text = f"{channel.name or chan_id[:4]} Zoom" # Short label
            slider_label = QtWidgets.QLabel(slider_label_text)
            slider_label.setAlignment(QtCore.Qt.AlignCenter)
            slider_label.setToolTip(f"Y Zoom for {channel.name or chan_id}")
            self.individual_y_slider_labels[chan_id] = slider_label
            ind_y_slider_layout.addWidget(slider_label)
            # Slider
            y_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
            y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
            y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            y_slider.setToolTip(f"Adjust Y zoom for {channel.name or chan_id} (Min=Out, Max=In)")
            # Use partial to pass chan_id to the handler
            y_slider.valueChanged.connect(partial(self._on_individual_y_zoom_changed, chan_id))
            ind_y_slider_layout.addWidget(y_slider, stretch=1) # Slider stretches vertically
            self.individual_y_sliders[chan_id] = y_slider
            # Add container widget to main layout, ensure it stretches
            self.individual_y_sliders_layout.addWidget(ind_y_slider_widget, stretch=1)
            ind_y_slider_widget.setVisible(False) # Initially hidden (visible if axes unlocked)

            # --- Individual Y Scrollbar ---
            y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Vertical)
            y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
            y_scrollbar.setToolTip(f"Scroll Y-axis for {channel.name or chan_id}")
            # Use partial to pass chan_id to the handler
            y_scrollbar.valueChanged.connect(partial(self._on_individual_y_scrollbar_changed, chan_id))
            self.individual_y_scrollbars[chan_id] = y_scrollbar
            # Add directly to its layout, ensure it stretches
            self.individual_y_scrollbars_layout.addWidget(y_scrollbar, stretch=1)
            y_scrollbar.setVisible(False) # Initially hidden (visible if axes unlocked)
            self._reset_scrollbar(y_scrollbar) # Set initial state (disabled, range 0-0)

        # --- Final Plot Setup ---
        # Set bottom label for the very last plot created
        if last_plot_item:
            last_plot_item.setLabel('bottom', "Time", units='s')
            last_plot_item.showAxis('bottom') # Ensure the last one shows its axis


    # --- File Loading ---
    def _open_file_or_folder(self):
        """Opens a file dialog, finds sibling files, and loads the selected one."""
        file_filter = self.neo_adapter.get_supported_file_filter()
        log.debug(f"Using dynamic file filter: {file_filter}")

        # Use QFileDialog to get the filename
        filepath_str, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Recording File", "", file_filter
        )

        if not filepath_str:
            log.info("File open cancelled.")
            return # User cancelled

        selected_filepath = Path(filepath_str)
        folder_path = selected_filepath.parent
        selected_extension = selected_filepath.suffix.lower() # Use lower for case-insensitive match

        log.info(f"User selected: {selected_filepath.name}. Scanning folder '{folder_path}' for '{selected_extension}'.")

        # Find all files with the same extension in the folder
        try:
            # Use glob to find matching files and sort them (natural sort might be better if filenames have numbers)
            sibling_files = sorted(list(folder_path.glob(f"*{selected_extension}")))
        except Exception as e:
             # Handle potential errors during folder scanning (e.g., permissions)
             log.error(f"Error scanning folder {folder_path}: {e}")
             QtWidgets.QMessageBox.warning(self, "Folder Scan Error", f"Could not scan folder:\n{e}")
             # Fallback: just load the single selected file
             self.file_list = [selected_filepath]; self.current_file_index = 0
             self._load_and_display_file(selected_filepath)
             return

        if not sibling_files:
            log.warning(f"No other files with extension '{selected_extension}' found in {folder_path}. Loading selected file only.")
            self.file_list = [selected_filepath]
            self.current_file_index = 0
        else:
            self.file_list = sibling_files
            try:
                # Find the index of the user-selected file within the sorted list
                self.current_file_index = self.file_list.index(selected_filepath)
                log.info(f"Found {len(self.file_list)} file(s) with extension '{selected_extension}'. Selected index: {self.current_file_index}.")
            except ValueError:
                # Should not happen if selected_filepath came from the glob, but handle defensively
                log.error(f"Selected file {selected_filepath} not found in the scanned list? Loading first file instead.")
                self.current_file_index = 0

        # Load the file at the determined index
        if self.file_list:
            self._load_and_display_file(self.file_list[self.current_file_index])
        else:
            # If somehow file_list is empty after all checks
            self._reset_ui_and_state_for_new_file()
            self._update_ui_state()

    def _load_and_display_file(self, filepath: Path):
        """Loads data, resets UI, creates plots, updates metadata."""
        self.statusBar.showMessage(f"Loading '{filepath.name}'..."); QtWidgets.QApplication.processEvents() # Provide feedback

        # 1. Reset everything related to the previous file
        self._reset_ui_and_state_for_new_file()
        self.current_recording = None # Ensure no stale recording data

        # 2. Load data using the adapter
        try:
            self.current_recording = self.neo_adapter.read_recording(filepath)
            log.info(f"Successfully loaded recording from {filepath.name}")
            self.max_trials_current_recording = self.current_recording.max_trials if self.current_recording else 0

            # 3. Rebuild UI elements based on the new data
            self._create_channel_ui() # Create checkboxes, plots, sliders, scrollbars
            self._update_metadata_display() # Show file info

            # 4. Plot initial data
            self._update_plot() # Calls _update_ui_state internally

            # 5. Reset view to fit the loaded data and initialize zoom/scroll state
            self._reset_view() # Sets base ranges, resets sliders/scrollbars

            self.statusBar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000) # Clear status after success

        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e:
            log.error(f"Load failed for {filepath}: {e}", exc_info=False) # Log specific error
            QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load file:\n{filepath.name}\n\nError: {e}")
            self._clear_metadata_display()
            self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        except Exception as e: # Catch unexpected errors during loading/UI creation
            log.error(f"Unexpected error loading {filepath}: {e}", exc_info=True) # Log with traceback
            QtWidgets.QMessageBox.critical(self, "Unexpected Error", f"An unexpected error occurred while loading:\n{filepath.name}\n\n{e}")
            self._clear_metadata_display()
            self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        finally:
            # Ensure UI state (button enables etc.) is correct regardless of success/failure
            self._update_ui_state()


    # --- Display Option Changes ---
    def _on_plot_mode_changed(self, index):
        """Handles change in plot mode (Overlay vs Cycle)."""
        new_mode_name = 'Overlay+Avg' if index == self.PlotMode.OVERLAY_AVG else 'Cycle Single'
        log.info(f"Plot mode changed to: {new_mode_name} (Index: {index})")

        if self.current_plot_mode != index:
            # If mode changes, the selected average plot is no longer relevant/visible
            self._remove_selected_average_plots()
            # Ensure the toggle button reflects that the plot is removed
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)

        self.current_plot_mode = index
        self.current_trial_index = 0 # Always reset to the first trial when changing mode

        self._update_plot() # Re-plot data according to the new mode
        self._reset_view() # Reset view limits after changing mode/data
        # Update UI state (e.g., enable/disable trial cycle buttons, avg selection buttons)
        self._update_ui_state()

    def _trigger_plot_update(self):
        """Connected to channel checkboxes and downsample option. Updates plot and related UI."""
        if not self.current_recording: return # No data loaded

        sender_widget = self.sender()
        is_channel_checkbox = isinstance(sender_widget, QtWidgets.QCheckBox) and sender_widget != self.downsample_checkbox and sender_widget != self.y_lock_checkbox

        # If a channel's visibility changes AND a selected average plot is currently shown,
        # remove the average plot because the set of visible channels has changed, potentially
        # making the average confusing or invalid (e.g., if the channel used for the t-vector is hidden).
        if is_channel_checkbox and self.selected_average_plot_items:
            log.debug("Channel visibility changed while selected average was plotted, removing average plot.")
            self._remove_selected_average_plots()
            # Update the button state to match
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)
            # Note: _update_ui_state will be called by _update_plot later, which will fix button text

        # 1. Update the plot data itself
        self._update_plot() # This also calls _update_ui_state at the end

        # 2. Update visibility of individual Y controls if a channel checkbox triggered this
        if is_channel_checkbox:
            self._update_y_controls_visibility()

        # 3. Reset view *only* for a channel that was just turned ON
        # Avoid resetting view when turning channels OFF or changing downsample.
        # Resetting ensures the newly visible channel's data range is properly considered.
        if is_channel_checkbox and sender_widget.isChecked():
            channel_id_to_reset = None
            # Find which channel ID corresponds to the checkbox that was just checked
            for ch_id, cb in self.channel_checkboxes.items():
                if cb == sender_widget:
                    channel_id_to_reset = ch_id
                    break
            if channel_id_to_reset:
                 # Reset only the Y-axis view for this specific channel
                 # We don't reset X because it's linked and should remain consistent
                 self._reset_single_plot_view(channel_id_to_reset)


    # --- Plotting Core Logic ---
    def _clear_plot_data_only(self):
        """Clears data items from plots, *excluding* the selected average overlays."""
        log.debug("Clearing plot data items (excluding selected averages).")
        for chan_id, plot_item in self.channel_plots.items():
            # Basic check if plot_item is valid
            if plot_item is None or plot_item.scene() is None: continue

            # Identify the PlotDataItem corresponding to the selected average for this channel (if it exists)
            selected_avg_item = self.selected_average_plot_items.get(chan_id)

            # Build a list of items to remove from this plot
            items_to_remove = []
            for item in plot_item.items:
                # Remove regular data plots (PlotDataItem) and any text error messages (TextItem)
                # Crucially, DO NOT remove the item if it IS the selected_avg_item for this channel
                if isinstance(item, (pg.PlotDataItem, pg.TextItem)) and item != selected_avg_item:
                    items_to_remove.append(item)

            # Remove the identified items
            for item in items_to_remove:
                # Safety check: ensure item still exists before removal attempt
                if item in plot_item.items:
                    plot_item.removeItem(item)
                else:
                    log.warning(f"Attempted to remove item {item} from plot {chan_id}, but it was not found.")

        # Clear the dictionary that tracks the *regular* plot data items
        self.channel_plot_data_items.clear()

    def _update_plot(self):
        """Core function to draw data onto the visible plot items based on current mode."""
        # 1. Clear previous *regular* data (leaves selected avg plots if they exist)
        self._clear_plot_data_only()

        # 2. Check if data and plots exist
        if not self.current_recording or not self.channel_plots:
            log.warning("Update plot called but no recording or plot items exist.")
            # Clear the layout widget entirely if there are no PlotItems left
            items = self.graphics_layout_widget.items()
            if not any(isinstance(item, pg.PlotItem) for item in items):
                 self.graphics_layout_widget.clear()
                 self.graphics_layout_widget.addLabel("Load data to begin", row=0, col=0)
            self._update_ui_state(); return

        # 3. Determine plot mode and logging
        is_cycle_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        log.debug(f"Updating plot data. Mode: {'Cycle Single' if is_cycle_mode else 'Overlay+Avg'}, Trial: {self.current_trial_index+1}/{self.max_trials_current_recording}")

        # 4. Define pens (could be cached)
        # Use VisConstants if available, otherwise use defaults
        vis_constants_available = 'VisConstants' in globals()
        trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR + (VisConstants.TRIAL_ALPHA,), width=VisConstants.DEFAULT_PLOT_PEN_WIDTH) if vis_constants_available else pg.mkPen(color=(128, 128, 128, 80), width=1)
        avg_pen = pg.mkPen(VisConstants.AVERAGE_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1) if vis_constants_available else pg.mkPen('r', width=2)
        single_trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH) if vis_constants_available else pg.mkPen(color=(128, 128, 128), width=1) # Cycle mode pen (opaque)
        ds_threshold = VisConstants.DOWNSAMPLING_THRESHOLD if vis_constants_available else 1000

        # 5. Iterate through channels and plot data for visible ones
        any_data_plotted_overall = False
        visible_plots_this_update: List[pg.PlotItem] = [] # Track which plots are actually shown

        for chan_id, plot_item in self.channel_plots.items():
            checkbox = self.channel_checkboxes.get(chan_id)
            channel = self.current_recording.channels.get(chan_id)

            # Check if channel exists, is selected via checkbox, and has a corresponding plot item
            if checkbox and checkbox.isChecked() and channel and plot_item:
                plot_item.setVisible(True) # Ensure plot is visible
                visible_plots_this_update.append(plot_item)
                plotted_something_for_channel = False
                enable_ds = self.downsample_checkbox.isChecked() # Check downsample setting once per channel

                # --- Plotting based on mode ---
                if not is_cycle_mode: # == PlotMode.OVERLAY_AVG
                    # Plot all individual trials
                    for trial_idx in range(channel.num_trials):
                        data = channel.get_data(trial_idx)
                        tvec = channel.get_relative_time_vector(trial_idx)
                        if data is not None and tvec is not None:
                             # Plot trial with semi-transparent pen
                             di = plot_item.plot(tvec, data, pen=trial_pen)
                             # Apply downsampling settings AFTER plotting
                             di.opts['autoDownsample'] = enable_ds
                             if enable_ds: di.opts['autoDownsampleThreshold'] = ds_threshold
                             # Store reference to the data item
                             self.channel_plot_data_items.setdefault(chan_id, []).append(di)
                             plotted_something_for_channel = True
                        else:
                             log.warning(f"Missing data/tvec for trial {trial_idx+1}, channel {chan_id}")

                    # Plot overall average (if it exists)
                    avg_data = channel.get_averaged_data()
                    avg_tvec = channel.get_relative_averaged_time_vector()
                    if avg_data is not None and avg_tvec is not None:
                        # Plot average with distinct pen
                        di_avg = plot_item.plot(avg_tvec, avg_data, pen=avg_pen)
                        # Apply downsampling settings AFTER plotting
                        di_avg.opts['autoDownsample'] = enable_ds
                        if enable_ds: di_avg.opts['autoDownsampleThreshold'] = ds_threshold
                        self.channel_plot_data_items.setdefault(chan_id, []).append(di_avg)
                        plotted_something_for_channel = True
                    elif channel.num_trials > 0:
                        # Only warn if trials exist but avg failed
                        log.warning(f"Could not get averaged data for channel {chan_id}")

                else: # == PlotMode.CYCLE_SINGLE
                    # Determine the correct trial index to display (handle edge case of no trials)
                    idx_to_plot = -1
                    if channel.num_trials > 0:
                       idx_to_plot = min(self.current_trial_index, channel.num_trials - 1) # Ensure index is valid

                    if idx_to_plot >= 0:
                        data = channel.get_data(idx_to_plot)
                        tvec = channel.get_relative_time_vector(idx_to_plot)
                        if data is not None and tvec is not None:
                            # Plot the single trial with opaque pen
                            di = plot_item.plot(tvec, data, pen=single_trial_pen)
                            # Apply downsampling settings AFTER plotting
                            di.opts['autoDownsample'] = enable_ds
                            if enable_ds: di.opts['autoDownsampleThreshold'] = ds_threshold
                            self.channel_plot_data_items.setdefault(chan_id, []).append(di)
                            plotted_something_for_channel = True
                        else:
                            # Show error if data for this specific trial is missing
                            plot_item.addItem(pg.TextItem(f"Trial {idx_to_plot+1} data error", color='r'))
                            log.warning(f"Missing data/tvec for trial {idx_to_plot+1}, channel {chan_id}")

                # --- End Plotting based on mode ---

                # Add a message if no data could be plotted for a visible channel
                if not plotted_something_for_channel and channel.num_trials == 0:
                     plot_item.addItem(pg.TextItem(f"No trials in file", color='orange'))
                elif not plotted_something_for_channel:
                     # Generic message if something went wrong but trials exist
                     plot_item.addItem(pg.TextItem(f"No data to display", color='orange'))

                if plotted_something_for_channel:
                    any_data_plotted_overall = True

            elif plot_item: # Channel exists but is not checked
                plot_item.hide() # Hide the plot item if checkbox is unchecked

        # 6. Configure X axis linking and bottom label visibility
        # Find the *last* plot that is currently visible
        last_visible_plot_this_update = visible_plots_this_update[-1] if visible_plots_this_update else None

        for i, item in enumerate(self.channel_plots.values()):
             if item in visible_plots_this_update:
                 # Check if this plot is the last visible one
                 is_last = (item == last_visible_plot_this_update)
                 # Show bottom axis only for the last visible plot
                 item.showAxis('bottom', show=is_last)
                 if is_last:
                     item.setLabel('bottom', "Time", units='s') # Set label only for the last one
                 else:
                      item.setLabel('bottom', None) # Clear label for others

                 # Link X axes: Link plot i to plot i-1 if both are visible
                 # Find the index of the current item within the *visible* list
                 try:
                    current_vis_idx = visible_plots_this_update.index(item)
                    if current_vis_idx > 0:
                        # Link to the previous plot *in the visible list*
                        item.setXLink(visible_plots_this_update[current_vis_idx - 1])
                    else:
                        item.setXLink(None) # Ensure first visible plot has no link above it
                 except ValueError: # Should not happen if item is in visible_plots_this_update
                    item.setXLink(None)
                    log.error(f"PlotItem {item} was marked visible but not found in visible_plots_this_update list.")
             else:
                 # Ensure hidden plots don't show the axis label
                 item.hideAxis('bottom')
                 item.setLabel('bottom', None)
                 # Unlink hidden plots to avoid potential issues
                 item.setXLink(None)


        # 7. Update trial label and UI state
        self._update_trial_label()
        if not any_data_plotted_overall and self.current_recording and self.channel_plots:
            log.info("Update plot finished: No channels selected or no data successfully plotted.")

        self._update_ui_state() # Refresh button enables etc.


    # --- Metadata Display ---
    def _update_metadata_display(self):
        """Updates labels in the 'File Information' group box."""
        if self.current_recording:
            rec = self.current_recording
            self.filename_label.setText(rec.source_file.name)
            # Format sampling rate if available
            sr_text = f"{rec.sampling_rate:.2f} Hz" if rec.sampling_rate else "N/A"
            self.sampling_rate_label.setText(sr_text)
            # Format duration if available
            dur_text = f"{rec.duration:.3f} s" if rec.duration else "N/A"
            self.duration_label.setText(dur_text)
            # Display channel count and max trials
            num_ch = rec.num_channels
            max_tr = self.max_trials_current_recording # Use cached value
            self.channels_label.setText(f"{num_ch} channel(s), {max_tr} trial(s)")
        else:
            self._clear_metadata_display()

    def _clear_metadata_display(self):
        """Resets metadata labels to 'N/A'."""
        self.filename_label.setText("N/A")
        self.sampling_rate_label.setText("N/A")
        self.duration_label.setText("N/A")
        self.channels_label.setText("N/A")

    # --- UI State Update ---
    def _update_ui_state(self):
        """Updates enable/disable state and text of various UI elements based on current application state."""
        has_data = self.current_recording is not None
        # Check if there are *any* plot items that are currently set to be visible
        visible_plots = [p for p in self.channel_plots.values() if p.isVisible()]
        has_visible_plots = bool(visible_plots)
        is_folder = len(self.file_list) > 1 # True if multiple files were found in the folder
        is_cycling_mode = has_data and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        # Use max_trials_current_recording which is updated when loading a file
        has_multiple_trials = has_data and self.max_trials_current_recording > 0
        has_selection = bool(self.selected_trial_indices) # True if the selection set is not empty
        # Check if the dictionary storing average plot items is not empty
        is_selected_average_plotted = bool(self.selected_average_plot_items)

        # Determine enable state for controls requiring plotted data
        enable_data_controls = has_data and has_visible_plots # Need data AND something showing
        # Determine enable state for controls requiring only loaded data (even if no channels selected)
        enable_any_data_controls = has_data

        # --- Update Enable States ---

        # Zoom/Scroll/Reset View controls: Require visible plots
        self.reset_view_button.setEnabled(enable_data_controls)
        self.x_zoom_slider.setEnabled(enable_data_controls)
        self.y_lock_checkbox.setEnabled(enable_data_controls)
        # Note: Individual/Global Y zoom/scroll enables are handled dynamically by _update_y_controls_visibility and _update_scrollbar_from_view

        # General display options: Require data to be loaded
        self.plot_mode_combobox.setEnabled(enable_any_data_controls)
        self.downsample_checkbox.setEnabled(enable_any_data_controls)
        self.export_nwb_action.setEnabled(enable_any_data_controls)
        self.channel_select_group.setEnabled(has_data) # Enable channel box if data loaded

        # Trial Navigation (Cycle Mode): Require cycle mode and more than one trial
        enable_trial_cycle_nav = enable_any_data_controls and is_cycling_mode and self.max_trials_current_recording > 1
        self.prev_trial_button.setEnabled(enable_trial_cycle_nav and self.current_trial_index > 0) # Can go back if not first trial
        self.next_trial_button.setEnabled(enable_trial_cycle_nav and self.current_trial_index < self.max_trials_current_recording - 1) # Can go forward if not last
        # Show trial label only in cycle mode with data
        self.trial_index_label.setVisible(enable_any_data_controls and is_cycling_mode)
        self._update_trial_label() # Update text if visible

        # File Navigation: Require multiple files loaded
        self.prev_file_button.setVisible(is_folder)
        self.next_file_button.setVisible(is_folder)
        self.folder_file_index_label.setVisible(is_folder)
        if is_folder:
             # Enable Prev/Next based on current index in the file list
             self.prev_file_button.setEnabled(self.current_file_index > 0)
             self.next_file_button.setEnabled(self.current_file_index < len(self.file_list) - 1)
             # Update file index label
             current_filename = "N/A"
             if 0 <= self.current_file_index < len(self.file_list):
                 current_filename = self.file_list[self.current_file_index].name
             self.folder_file_index_label.setText(f"File {self.current_file_index + 1}/{len(self.file_list)}: {current_filename}")
        else:
             self.folder_file_index_label.setText("") # Clear label if not in folder mode

        # Multi-Trial Selection Button States:
        # Can select/deselect the current trial only if in cycling mode and trials exist
        can_select_current = is_cycling_mode and has_multiple_trials
        self.select_trial_button.setEnabled(can_select_current)
        # Change button text/tooltip based on whether the *current* trial is selected
        if can_select_current and self.current_trial_index in self.selected_trial_indices:
            self.select_trial_button.setText("Deselect Current Trial")
            self.select_trial_button.setToolTip("Remove the currently viewed trial from the set for averaging.")
        else:
            self.select_trial_button.setText("Add Current Trial to Avg Set")
            self.select_trial_button.setToolTip("Add the currently viewed trial (in Cycle Mode) to the set for averaging.")

        # Can clear selection only if a selection exists
        self.clear_selection_button.setEnabled(has_selection)
        # Can show/hide the average plot only if a selection exists
        self.show_selected_average_button.setEnabled(has_selection)

        # --- Update Button Text (Toggle Button) ---
        # Update the "Plot/Hide Selected Avg" button text based on whether the average plot is *currently* displayed
        # Do this without changing the button's checked state here.
        if is_selected_average_plotted:
             self.show_selected_average_button.setText("Hide Selected Avg")
             self.show_selected_average_button.setToolTip("Hide the average overlay plot.")
        else:
             self.show_selected_average_button.setText("Plot Selected Avg")
             self.show_selected_average_button.setToolTip("Show the average of selected trials as an overlay.")


    # --- Trial Label Update ---
    def _update_trial_label(self):
        """Updates the text of the trial index label."""
        # Only show meaningful label in Cycle Single mode with trials
        if (self.current_recording and
            self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and
            self.max_trials_current_recording > 0):
            # Display 1-based index
            self.trial_index_label.setText(f"{self.current_trial_index + 1} / {self.max_trials_current_recording}")
        else:
            # Hide or show N/A when not applicable
            self.trial_index_label.setText("N/A") # Or setVisible(False) in _update_ui_state


    # --- Zoom & Scroll Controls ---

    def _calculate_new_range(self, base_range: Optional[Tuple[float, float]], slider_value: int) -> Optional[Tuple[float, float]]:
        """Calculates a new zoomed range based on a base range and slider value."""
        if base_range is None or base_range[0] is None or base_range[1] is None:
            log.warning("_calculate_new_range: Invalid base_range provided.")
            return None
        try:
            min_val, max_val = base_range
            center = (min_val + max_val) / 2.0
            full_span = max_val - min_val

            # Avoid division by zero if range is effectively zero
            if full_span <= 1e-12: # Use a small epsilon
                full_span = 1.0 # Assign a nominal span if zero

            # Normalize slider value (0.0 at min slider, 1.0 at max slider)
            min_slider = float(self.SLIDER_RANGE_MIN)
            max_slider = float(self.SLIDER_RANGE_MAX)
            slider_pos_norm = 0.0
            if max_slider > min_slider:
                 slider_pos_norm = (float(slider_value) - min_slider) / (max_slider - min_slider)

            # Calculate zoom factor: 1.0 (full view) at min slider, MIN_ZOOM_FACTOR at max slider (inverted)
            # Linear interpolation between 1.0 and MIN_ZOOM_FACTOR
            zoom_factor = 1.0 - slider_pos_norm * (1.0 - self.MIN_ZOOM_FACTOR)

            # Clamp zoom factor to prevent issues
            zoom_factor = max(self.MIN_ZOOM_FACTOR, min(1.0, zoom_factor))

            # Calculate new span and range limits
            new_span = full_span * zoom_factor
            new_min = center - new_span / 2.0
            new_max = center + new_span / 2.0

            return (new_min, new_max)

        except Exception as e:
            log.error(f"Error calculating new range: base={base_range}, slider={slider_value}. Error: {e}", exc_info=True)
            return None

    # --- X Zoom/Scroll ---
    def _on_x_zoom_changed(self, value):
        """Handles changes from the shared X-axis zoom slider."""
        # Prevent updates if no base range is set or if triggered programmatically
        if self.base_x_range is None or self._updating_viewranges: return

        new_x_range = self._calculate_new_range(self.base_x_range, value)
        if new_x_range is None: return # Calculation failed

        # Apply the new range to the *first visible* plot's ViewBox
        # Since X axes are linked, this will propagate to others.
        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if first_visible_plot:
            vb = first_visible_plot.getViewBox()
            try:
                self._updating_viewranges = True # Prevent ViewBox signal loop
                vb.setXRange(new_x_range[0], new_x_range[1], padding=0) # Apply range, no padding
            finally:
                self._updating_viewranges = False # Release flag
            # Update the scrollbar to reflect the new view range relative to the base range
            self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_x_range)
        else:
            log.warning("X zoom changed, but no visible plot found to apply range.")

    def _on_x_scrollbar_changed(self, value):
        """Handles changes from the shared X-axis scrollbar."""
        # Prevent updates if no base range or if triggered programmatically
        if self.base_x_range is None or self._updating_scrollbars: return

        # Find the first visible plot to get the current view span
        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if not first_visible_plot: return

        try:
            vb = first_visible_plot.getViewBox()
            current_x_range = vb.viewRange()[0]
            current_span = current_x_range[1] - current_x_range[0]

            if current_span <= 1e-12: return # Avoid issues with zero span

            base_span = self.base_x_range[1] - self.base_x_range[0]
            if base_span <= 1e-12: return # Base range is invalid

            # Calculate how much of the base range is *not* visible (the scrollable amount)
            scrollable_data_range = max(0, base_span - current_span)

            # Calculate the new minimum based on scrollbar position
            scroll_fraction = float(value) / max(1, self.x_scrollbar.maximum()) # Avoid division by zero
            new_min = self.base_x_range[0] + scroll_fraction * scrollable_data_range
            new_max = new_min + current_span # Keep the same span, just shift

            # Apply the new range by setting the ViewBox range
            self._updating_viewranges = True # Prevent ViewBox signal loop
            vb.setXRange(new_min, new_max, padding=0)
        except Exception as e:
            log.error(f"Error handling X scrollbar change: {e}", exc_info=True)
        finally:
            self._updating_viewranges = False # Release flag

    def _handle_vb_xrange_changed(self, vb, new_range):
        """Handles X range changes originating from the ViewBox (e.g., mouse zoom/pan)."""
        # Ignore if change was triggered by our code or if base range isn't set
        if self._updating_viewranges or self.base_x_range is None: return

        # Update the X scrollbar position based on the new ViewBox range
        # No need to update sliders here, as mouse zoom doesn't map directly to slider value
        self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_range)

    # --- Y Lock & Control Visibility ---
    def _on_y_lock_changed(self, state):
        """Handles the 'Lock Axes' checkbox state change."""
        self.y_axes_locked = bool(state == QtCore.Qt.Checked.value) # state is integer
        log.info(f"Y-axes {'locked' if self.y_axes_locked else 'unlocked'}.")
        # Update which set of Y controls (global or individual) are visible
        self._update_y_controls_visibility()
        # Update enable states (e.g., global slider might become enabled/disabled)
        self._update_ui_state()
        # When locking/unlocking, it might be desirable to reset the view,
        # or at least synchronize the individual/global controls. For now, just toggle visibility.

    def _update_y_controls_visibility(self):
        """Shows/hides Global vs Individual Y zoom/scroll controls based on lock state and plot visibility."""
        locked = self.y_axes_locked
        has_visible_plots = any(p.isVisible() for p in self.channel_plots.values())

        # Toggle visibility of the main containers for global/individual controls
        self.global_y_slider_widget.setVisible(locked and has_visible_plots)
        self.individual_y_sliders_container.setVisible(not locked and has_visible_plots)
        self.global_y_scrollbar_widget.setVisible(locked and has_visible_plots)
        self.individual_y_scrollbars_container.setVisible(not locked and has_visible_plots)

        if not has_visible_plots: return  # Skip individual updates if nothing is showing

        # Get IDs of currently visible channels that have the necessary attribute set
        # --- FIX IS HERE ---
        visible_chan_ids = {p.getViewBox()._synaptipy_chan_id
                            for p in self.channel_plots.values()
                            if p.isVisible() and hasattr(p.getViewBox(), '_synaptipy_chan_id')}
        # --- END FIX ---

        if not locked:
            # Show/hide *individual* controls based on plot visibility
            for chan_id, slider in self.individual_y_sliders.items():
                is_visible = chan_id in visible_chan_ids
                # The slider's parent widget controls visibility (includes the label)
                slider.parentWidget().setVisible(is_visible)
                # Enable slider only if visible AND its base Y range has been set
                has_base = self.base_y_ranges.get(chan_id) is not None
                slider.setEnabled(is_visible and has_base)

            for chan_id, scrollbar in self.individual_y_scrollbars.items():
                is_visible = chan_id in visible_chan_ids
                scrollbar.setVisible(is_visible)
                # Enable scrollbar only if visible, has base range, AND it's currently scrollable
                # (is scrollable state checked by _update_scrollbar_from_view)
                has_base = self.base_y_ranges.get(chan_id) is not None
                current_enabled_state = scrollbar.isEnabled()  # Preserve scrollable state
                # Re-enable only if it meets criteria AND was already enabled (scrollable)
                # Also add the has_base check here for robustness
                scrollbar.setEnabled(is_visible and has_base and current_enabled_state)
        else:
            # Enable *global* controls if axes are locked and *any* visible plot has a base Y range
            can_enable_global = any(self.base_y_ranges.get(ch_id) is not None for ch_id in visible_chan_ids)
            self.global_y_slider.setEnabled(can_enable_global)
            # Preserve scrollable state for global scrollbar
            current_enabled_state = self.global_y_scrollbar.isEnabled()
            self.global_y_scrollbar.setEnabled(can_enable_global and current_enabled_state)

    # --- Y Zoom/Scroll (Global) ---
    def _on_global_y_zoom_changed(self, value):
        """Handles changes from the global Y-axis zoom slider."""
        # Only act if axes are locked and not updating programmatically
        if not self.y_axes_locked or self._updating_viewranges: return
        self._apply_global_y_zoom(value)

    def _apply_global_y_zoom(self, value):
        """Applies the zoom level to all visible plots."""
        log.debug(f"Applying global Y zoom value: {value}")
        first_visible_base_y = None # To update scrollbar later
        first_visible_new_y = None

        try:
            self._updating_viewranges = True # Prevent ViewBox signal loops
            for chan_id, plot in self.channel_plots.items():
                if plot.isVisible():
                    base_y = self.base_y_ranges.get(chan_id)
                    if base_y is None:
                        log.warning(f"Global Y Zoom: No base Y range for visible channel {chan_id}")
                        continue # Skip if no base range stored

                    new_y_range = self._calculate_new_range(base_y, value)
                    if new_y_range:
                        plot.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
                        # Store the first valid ranges encountered to update the scrollbar
                        if first_visible_base_y is None:
                            first_visible_base_y = base_y
                            first_visible_new_y = new_y_range
                    else:
                         log.warning(f"Global Y Zoom: Failed to calculate new range for {chan_id}")
        finally:
            self._updating_viewranges = False # Release flag

        # Update the global scrollbar based on the zoom applied to the first plot
        if first_visible_base_y and first_visible_new_y:
            self._update_scrollbar_from_view(self.global_y_scrollbar, first_visible_base_y, first_visible_new_y)
        else:
             # If no valid ranges found, reset the scrollbar
             self._reset_scrollbar(self.global_y_scrollbar)


    def _on_global_y_scrollbar_changed(self, value):
         """Handles changes from the global Y-axis scrollbar."""
         # Only act if axes are locked and not updating programmatically
         if not self.y_axes_locked or self._updating_scrollbars: return
         self._apply_global_y_scroll(value)

    def _apply_global_y_scroll(self, value):
         """Applies the scroll position to all visible plots."""
         # Find the first visible plot to use as a reference for current span
         first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
         if not first_visible_plot: return

         try:
             vb_ref = first_visible_plot.getViewBox()
             ref_chan_id = getattr(vb_ref, '_synaptipy_chan_id', None)
             ref_base_y = self.base_y_ranges.get(ref_chan_id)

             if ref_base_y is None or ref_base_y[0] is None or ref_base_y[1] is None:
                  log.warning("Global Y Scroll: Reference plot has no valid base Y range.")
                  return

             current_y_range_ref = vb_ref.viewRange()[1]
             current_span = current_y_range_ref[1] - current_y_range_ref[0]
             if current_span <= 1e-12: return # Avoid issues with zero span

             ref_base_span = ref_base_y[1] - ref_base_y[0]
             if ref_base_span <= 1e-12: return # Base range is invalid

             # Calculate scroll fraction
             scroll_fraction = float(value) / max(1, self.global_y_scrollbar.maximum())

             self._updating_viewranges = True # Prevent ViewBox signal loops
             # Apply scroll to all visible plots based on their *own* base range
             for chan_id, plot in self.channel_plots.items():
                 if plot.isVisible():
                     base_y = self.base_y_ranges.get(chan_id)
                     if base_y is None or base_y[0] is None or base_y[1] is None: continue # Skip if no base range

                     base_span = base_y[1] - base_y[0]
                     if base_span <= 1e-12: continue # Skip if base range invalid

                     # Calculate scrollable range *for this channel*
                     scrollable_data_range = max(0, base_span - current_span) # Span is same for all locked axes
                     # Calculate new position based on this channel's base min
                     new_min = base_y[0] + scroll_fraction * scrollable_data_range
                     new_max = new_min + current_span # Keep span consistent

                     plot.getViewBox().setYRange(new_min, new_max, padding=0)

         except Exception as e:
             log.error(f"Error handling global Y scrollbar change: {e}", exc_info=True)
         finally:
             self._updating_viewranges = False # Release flag


    # --- Y Zoom/Scroll (Individual) ---
    def _on_individual_y_zoom_changed(self, chan_id, value):
        """Handles changes from an individual channel's Y-axis zoom slider."""
        # Only act if axes are unlocked and not updating programmatically
        if self.y_axes_locked or self._updating_viewranges: return

        plot = self.channel_plots.get(chan_id)
        base_y = self.base_y_ranges.get(chan_id)
        scrollbar = self.individual_y_scrollbars.get(chan_id)

        # Ensure all necessary components exist and plot is visible
        if plot is None or not plot.isVisible() or base_y is None or scrollbar is None:
            log.warning(f"Individual Y Zoom: Missing plot, base range, or scrollbar for {chan_id}.")
            return

        new_y_range = self._calculate_new_range(base_y, value)
        if new_y_range:
            try:
                self._updating_viewranges = True # Prevent ViewBox signal loop
                plot.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
            finally:
                self._updating_viewranges = False # Release flag
            # Update the corresponding scrollbar
            self._update_scrollbar_from_view(scrollbar, base_y, new_y_range)
        else:
             log.warning(f"Individual Y Zoom: Failed to calculate new range for {chan_id}")

    def _on_individual_y_scrollbar_changed(self, chan_id, value):
        """Handles changes from an individual channel's Y-axis scrollbar."""
        # Only act if axes are unlocked and not updating programmatically
        if self.y_axes_locked or self._updating_scrollbars: return

        plot = self.channel_plots.get(chan_id)
        base_y = self.base_y_ranges.get(chan_id)
        scrollbar = self.individual_y_scrollbars.get(chan_id)

        # Ensure all components exist, plot is visible, and base range is valid
        if (plot is None or not plot.isVisible() or
            base_y is None or base_y[0] is None or base_y[1] is None or
            scrollbar is None):
            return

        try:
            vb = plot.getViewBox()
            current_y_range = vb.viewRange()[1]
            current_span = current_y_range[1] - current_y_range[0]
            if current_span <= 1e-12: return # Avoid zero span issues

            base_span = base_y[1] - base_y[0]
            if base_span <= 1e-12: return # Invalid base range

            # Calculate scrollable range and new position
            scrollable_data_range = max(0, base_span - current_span)
            scroll_fraction = float(value) / max(1, scrollbar.maximum())
            new_min = base_y[0] + scroll_fraction * scrollable_data_range
            new_max = new_min + current_span

            # Apply new range
            self._updating_viewranges = True # Prevent ViewBox signal loop
            vb.setYRange(new_min, new_max, padding=0)
        except Exception as e:
            log.error(f"Error handling individual Y scrollbar change for {chan_id}: {e}", exc_info=True)
        finally:
            self._updating_viewranges = False # Release flag


    # --- Y ViewBox Change Handler ---
    def _handle_vb_yrange_changed(self, vb, new_range):
        """Handles Y range changes originating from ViewBox (mouse zoom/pan)."""
        # Ignore if change was triggered by our code
        if self._updating_viewranges: return

        # Get the channel ID associated with this ViewBox
        chan_id = getattr(vb, '_synaptipy_chan_id', None)
        if chan_id is None: return # Should not happen if setup is correct

        base_y = self.base_y_ranges.get(chan_id)
        if base_y is None: return # Cannot update scrollbar without base range

        # Update the appropriate scrollbar (global or individual)
        if self.y_axes_locked:
            # In locked mode, only update the global scrollbar if the change
            # came from the *first visible* plot's ViewBox (acts as the reference)
             first_visible_vb = next((p.getViewBox() for p in self.channel_plots.values() if p.isVisible()), None)
             if vb == first_visible_vb:
                  self._update_scrollbar_from_view(self.global_y_scrollbar, base_y, new_range)
        else:
            # In unlocked mode, update the specific scrollbar for this channel
            scrollbar = self.individual_y_scrollbars.get(chan_id)
            if scrollbar:
                self._update_scrollbar_from_view(scrollbar, base_y, new_range)


    # --- Scrollbar Update Helper ---
    def _update_scrollbar_from_view(self, scrollbar: QtWidgets.QScrollBar, base_range: Optional[Tuple[float,float]], view_range: Optional[Tuple[float, float]]):
        """Updates a scrollbar's range, page step, and value based on base and current view ranges."""
        # Prevent loop if update was triggered by scrollbar itself
        if self._updating_scrollbars: return

        # Validate inputs
        if (base_range is None or base_range[0] is None or base_range[1] is None or
            view_range is None or view_range[0] is None or view_range[1] is None):
            self._reset_scrollbar(scrollbar) # Disable scrollbar if ranges are invalid
            return

        try:
            base_min, base_max = base_range
            view_min, view_max = view_range
            base_span = base_max - base_min
            view_span = view_max - view_min

            # If base range has no span, disable scrollbar
            if base_span <= 1e-12:
                self._reset_scrollbar(scrollbar)
                return

            # Ensure view span is positive and not larger than base span
            view_span = max(1e-12, min(view_span, base_span))

            # Calculate Page Step: Proportion of the view range relative to the base range
            # Mapped onto the scrollbar's maximum range (SCROLLBAR_MAX_RANGE)
            page_step_float = (view_span / base_span) * self.SCROLLBAR_MAX_RANGE
            # Ensure page step is at least 1 and not more than the max range
            page_step = max(1, min(int(page_step_float), self.SCROLLBAR_MAX_RANGE))

            # Calculate Scrollbar Maximum Value: The total range minus the page size
            # Represents the maximum value the scrollbar's handle top edge can reach
            scroll_range_max = max(0, self.SCROLLBAR_MAX_RANGE - page_step)

            # Calculate Scrollbar Value: Position of the current view_min relative to base_min
            # Mapped onto the scrollbar's actual scrolling range (scroll_range_max)
            relative_pos = view_min - base_min # How far view_min is from base_min
            # Total data range that can be scrolled through
            scrollable_data_range = max(1e-12, base_span - view_span) # Avoid division by zero
            # Proportion of the way through the scrollable range
            value_float = (relative_pos / scrollable_data_range) * scroll_range_max
            # Clamp value to the valid scrollbar range [0, scroll_range_max]
            value = max(0, min(int(value_float), scroll_range_max))

            # Apply calculated values to the scrollbar
            self._updating_scrollbars = True # Set flag to prevent signal loops
            scrollbar.blockSignals(True) # Block signals during update

            scrollbar.setRange(0, scroll_range_max)
            scrollbar.setPageStep(page_step)
            scrollbar.setValue(value)
            scrollbar.setEnabled(scroll_range_max > 0) # Enable only if there's something to scroll

            scrollbar.blockSignals(False) # Re-enable signals

        except Exception as e:
            log.error(f"Error updating scrollbar: base={base_range}, view={view_range}. Error: {e}", exc_info=True)
            self._reset_scrollbar(scrollbar) # Reset on error
        finally:
            self._updating_scrollbars = False # Release flag


    # --- View Reset ---
    def _reset_view(self):
        """Resets zoom/pan to show full data range for all visible plots."""
        log.info("Reset View triggered.")

        # 1. Identify currently visible plots and their channel IDs
        visible_plots_dict = {}
        for chan_id, p in self.channel_plots.items():
             if p.isVisible():
                 visible_plots_dict[chan_id] = p

        # 2. Handle case where no plots are visible
        if not visible_plots_dict:
            log.debug("Reset View: No visible plots found.")
            self.base_x_range = None; self.base_y_ranges.clear()
            self._reset_scrollbar(self.x_scrollbar)
            self._reset_scrollbar(self.global_y_scrollbar)
            for sb in self.individual_y_scrollbars.values(): self._reset_scrollbar(sb)
            self._reset_all_sliders()
            self._update_y_controls_visibility() # Hide controls if no plots
            self._update_ui_state()
            return

        # 3. Auto-range all visible plots first (pyqtgraph determines full range)
        # Important: Auto-range X *before* Y if axes are linked.
        # Auto-ranging the first visible plot's X-axis should propagate due to linking.
        first_chan_id, first_plot = next(iter(visible_plots_dict.items()))
        first_plot.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis) # Auto-range X on first visible
        for plot in visible_plots_dict.values():
            plot.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis) # Auto-range Y on all visible

        # 4. Store the new full ranges as the base ranges
        try:
            # Get X range from the first visible plot (axes are linked)
            self.base_x_range = first_plot.getViewBox().viewRange()[0]
            log.debug(f"Reset View: New base X range: {self.base_x_range}")
        except Exception as e:
            log.error(f"Reset View: Error getting base X range from plot {first_chan_id}: {e}")
            self.base_x_range = None # Invalidate if error occurs

        # Get Y ranges for *each* visible plot
        self.base_y_ranges.clear()
        for chan_id, plot in visible_plots_dict.items():
             try:
                 # Store Y range using the channel ID as the key
                 self.base_y_ranges[chan_id] = plot.getViewBox().viewRange()[1]
                 log.debug(f"Reset View: New base Y range for {chan_id}: {self.base_y_ranges[chan_id]}")
             except Exception as e:
                 log.error(f"Reset View: Error getting base Y range for {chan_id}: {e}")
                 # Don't add to dict if error occurs

        # 5. Reset all zoom sliders to their default (zoomed out) value
        self._reset_all_sliders()

        # 6. Update scrollbars to reflect the new full view (they should be disabled or show full range)
        # Update X scrollbar
        if self.base_x_range:
             # View range is same as base range after reset
             self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, self.base_x_range)
        else:
             self._reset_scrollbar(self.x_scrollbar)

        # Update Y scrollbars based on lock state
        if self.y_axes_locked:
             # Update global scrollbar based on the *first visible plot's* base Y range
             first_visible_base_y = self.base_y_ranges.get(first_chan_id)
             if first_visible_base_y:
                 self._update_scrollbar_from_view(self.global_y_scrollbar, first_visible_base_y, first_visible_base_y)
             else:
                 self._reset_scrollbar(self.global_y_scrollbar)
             # Reset all individual scrollbars (they are hidden but reset state)
             for scrollbar in self.individual_y_scrollbars.values():
                 self._reset_scrollbar(scrollbar)
        else: # Y axes unlocked
             # Update each individual scrollbar based on its own base Y range
             for chan_id, scrollbar in self.individual_y_scrollbars.items():
                 base_y = self.base_y_ranges.get(chan_id)
                 # Update only if it's visible and has a valid base range
                 if chan_id in visible_plots_dict and base_y:
                     self._update_scrollbar_from_view(scrollbar, base_y, base_y)
                 else:
                     # Reset if not visible or no valid base range found
                     self._reset_scrollbar(scrollbar)
             # Reset the global scrollbar (it's hidden but reset state)
             self._reset_scrollbar(self.global_y_scrollbar)

        log.debug("Reset View: Sliders reset, scrollbars updated.")

        # 7. Update UI element visibility and enable states
        self._update_y_controls_visibility()
        self._update_ui_state()

    def _reset_all_sliders(self):
        """Resets X, Global Y, and all Individual Y sliders to the default value."""
        sliders = [self.x_zoom_slider, self.global_y_slider] + list(self.individual_y_sliders.values())
        for slider in sliders:
             slider.blockSignals(True) # Prevent triggering zoom updates
             slider.setValue(self.SLIDER_DEFAULT_VALUE)
             slider.blockSignals(False)

    def _reset_single_plot_view(self, chan_id: str):
        """Resets Y-axis zoom/pan for only one specific channel plot."""
        plot_item = self.channel_plots.get(chan_id)
        # Only proceed if the plot exists and is currently visible
        if not plot_item or not plot_item.isVisible(): return

        log.debug(f"Resetting single plot view (Y-axis) for {chan_id}")
        vb = plot_item.getViewBox()

        # 1. Auto-range the Y-axis of this specific plot
        vb.enableAutoRange(axis=pg.ViewBox.YAxis)
        new_y_range = None
        try:
             # Immediately get the new range determined by auto-ranging
             new_y_range = vb.viewRange()[1]
             # Update the base range for this channel
             self.base_y_ranges[chan_id] = new_y_range
             log.debug(f"Reset Single View: New base Y range for {chan_id}: {new_y_range}")
        except Exception as e:
             log.error(f"Reset Single View: Error getting new base Y range for {chan_id}: {e}")
             # If error, remove potentially invalid old base range
             if chan_id in self.base_y_ranges: del self.base_y_ranges[chan_id]

        # 2. Reset the corresponding individual Y slider (if exists)
        slider = self.individual_y_sliders.get(chan_id)
        if slider:
             slider.blockSignals(True)
             slider.setValue(self.SLIDER_DEFAULT_VALUE)
             slider.blockSignals(False)
             log.debug(f"Reset Single View: Slider for {chan_id} reset.")
             # Ensure slider is enabled now that base range is set (if axes unlocked)
             if not self.y_axes_locked: slider.setEnabled(True)


        # 3. Reset/Update the corresponding individual Y scrollbar (if exists)
        scrollbar = self.individual_y_scrollbars.get(chan_id)
        if scrollbar:
             if new_y_range:
                 # Update scrollbar to show full range (view == base)
                 self._update_scrollbar_from_view(scrollbar, new_y_range, new_y_range)
                 log.debug(f"Reset Single View: Scrollbar for {chan_id} updated.")
             else:
                 # Reset scrollbar if base range couldn't be determined
                 self._reset_scrollbar(scrollbar)
             # Ensure scrollbar visibility matches lock state (handled by _update_y_controls_visibility)

        # 4. If Y axes are locked, also reset the global controls
        if self.y_axes_locked:
             # Reset global slider
             self.global_y_slider.blockSignals(True)
             self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
             self.global_y_slider.blockSignals(False)
             # Update global scrollbar based on the *newly reset* range of this plot
             if new_y_range:
                  self._update_scrollbar_from_view(self.global_y_scrollbar, new_y_range, new_y_range)
             else:
                  self._reset_scrollbar(self.global_y_scrollbar)
             log.debug("Reset Single View: Global Y controls reset/updated due to lock.")

        # Ensure control visibility/enable state is correct
        self._update_y_controls_visibility()


    # --- Trial Navigation Slots ---
    def _next_trial(self):
        """Cycles to the next trial in 'Cycle Single Trial' mode."""
        if (self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and
            self.max_trials_current_recording > 0):

            if self.current_trial_index < self.max_trials_current_recording - 1:
                self.current_trial_index += 1
                log.debug(f"Next trial: {self.current_trial_index + 1}/{self.max_trials_current_recording}")
                # 1. Update the plot to show the new trial's data
                self._update_plot() # This calls _update_ui_state internally
                # 2. Reset View? (Currently commented out - see previous discussion)
                # If you uncomment the line below, the view will fully reset on every trial change.
                # self._reset_view()
                # 3. Ensure UI state (button enables, trial selection text) is updated
                # Note: _update_plot already calls _update_ui_state, so calling it again
                # here might be redundant unless _reset_view is uncommented and doesn't call it.
                # For clarity, explicitly call it if _reset_view is commented.
                if '# self._reset_view()' in self._next_trial.__doc__: # Check if reset is commented
                    self._update_ui_state() # Ensure UI state is correct after plot update

            else:
                log.debug("Already at last trial.")
                self.statusBar.showMessage("Already at last trial.", 1500)


    def _prev_trial(self):
        """Cycles to the previous trial in 'Cycle Single Trial' mode."""
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE:
            if self.current_trial_index > 0:
                self.current_trial_index -= 1
                log.debug(f"Previous trial: {self.current_trial_index + 1}/{self.max_trials_current_recording}")
                # 1. Update the plot to show the new trial's data
                self._update_plot() # This calls _update_ui_state internally
                # 2. Reset View? (Currently commented out)
                # If you uncomment the line below, the view will fully reset on every trial change.
                # self._reset_view()
                # 3. Ensure UI state is updated
                # See comment in _next_trial about redundant call
                if '# self._reset_view()' in self._prev_trial.__doc__: # Check if reset is commented
                     self._update_ui_state()
            else:
                log.debug("Already at first trial.")
                self.statusBar.showMessage("Already at first trial.", 1500)


    # --- Folder Navigation Slots ---
    def _next_file_folder(self):
        """Loads the next file in the folder list."""
        if self.file_list and self.current_file_index < len(self.file_list) - 1:
            self.current_file_index += 1
            log.info(f"Navigating to next file: index {self.current_file_index}, path {self.file_list[self.current_file_index]}")
            self._load_and_display_file(self.file_list[self.current_file_index])
        else:
            log.debug("Next file: Already at the last file or no folder list.")
            self.statusBar.showMessage("Already at last file.", 1500)


    def _prev_file_folder(self):
        """Loads the previous file in the folder list."""
        if self.file_list and self.current_file_index > 0:
            self.current_file_index -= 1
            log.info(f"Navigating to previous file: index {self.current_file_index}, path {self.file_list[self.current_file_index]}")
            self._load_and_display_file(self.file_list[self.current_file_index])
        else:
            log.debug("Previous file: Already at the first file or no folder list.")
            self.statusBar.showMessage("Already at first file.", 1500)


    # --- NWB Export Slot ---
    def _export_to_nwb(self):
        """Handles the NWB export process including metadata dialog."""
        if not self.current_recording:
             QtWidgets.QMessageBox.warning(self, "Export Error", "No recording data loaded to export.")
             return

        # Suggest default filename based on current file
        default_filename = self.current_recording.source_file.with_suffix(".nwb").name
        output_path_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save NWB File", default_filename, "NWB Files (*.nwb)"
        )

        if not output_path_str:
            self.statusBar.showMessage("NWB export cancelled.", 3000)
            log.info("NWB export cancelled by user.")
            return

        output_path = Path(output_path_str)

        # Prepare default metadata for the dialog
        default_id = str(uuid.uuid4()) # Generate a new unique ID
        # Use recording start time if available, otherwise use current time
        default_time = self.current_recording.session_start_time_dt or datetime.now()
        # Ensure timezone awareness (use local timezone if available, else UTC)
        if default_time.tzinfo is None:
            local_tz = None
            if tzlocal:
                try: local_tz = tzlocal.get_localzone()
                except Exception as e: log.warning(f"Could not get local timezone using tzlocal: {e}")
            # Use local or fallback to UTC
            default_time = default_time.replace(tzinfo=local_tz if local_tz else timezone.utc)

        # Show metadata dialog
        dialog = NwbMetadataDialog(default_id, default_time, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            session_metadata = dialog.get_metadata()
            # get_metadata handles basic validation (required fields)
            if session_metadata is None: # Should not happen if Accepted, but check
                 self.statusBar.showMessage("NWB metadata input error.", 3000)
                 return # Abort if metadata is invalid
        else:
            self.statusBar.showMessage("NWB export cancelled (metadata dialog).", 3000)
            log.info("NWB export cancelled at metadata dialog.")
            return

        # Perform the export
        self.statusBar.showMessage(f"Exporting NWB to '{output_path.name}'..."); QtWidgets.QApplication.processEvents()
        try:
            self.nwb_exporter.export(self.current_recording, output_path, session_metadata)
            log.info(f"Successfully exported NWB to {output_path}")
            self.statusBar.showMessage(f"Export successful: {output_path.name}", 5000)
            QtWidgets.QMessageBox.information(self, "Export Successful", f"Recording successfully exported to:\n{output_path}")
        except (ValueError, ExportError, SynaptipyError) as e: # Catch specific known export errors
            log.error(f"NWB Export failed: {e}", exc_info=False)
            self.statusBar.showMessage(f"NWB Export failed: {e}", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export NWB file:\n\n{e}")
        except Exception as e: # Catch unexpected errors during export
            log.error(f"Unexpected NWB Export error: {e}", exc_info=True)
            self.statusBar.showMessage("Unexpected NWB Export error.", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"An unexpected error occurred during export:\n\n{e}")

    # --- Multi-Trial Selection Slots --- ## NEW SECTION ##
    def _update_selected_trials_display(self):
        """Updates the QLabel showing the selected trial indices."""
        if not self.selected_trial_indices:
            self.selected_trials_display.setText("Selected: None")
        else:
            # Display sorted indices (add 1 for user-friendly 1-based display)
            sorted_indices = sorted(list(self.selected_trial_indices))
            display_text = "Selected: " + ", ".join(str(i + 1) for i in sorted_indices)
            # Limit displayed length if too many trials selected? Maybe not needed with word wrap.
            # max_display_len = 100
            # if len(display_text) > max_display_len:
            #     display_text = display_text[:max_display_len-3] + "..."
            self.selected_trials_display.setText(display_text)

    def _toggle_select_current_trial(self):
        """Adds or removes the current trial index from the selection set."""
        # Ensure we are in the correct mode and have data
        if not self.current_recording or self.current_plot_mode != self.PlotMode.CYCLE_SINGLE:
            log.warning("Cannot select trial: Not in cycle mode or no data loaded.")
            return

        # Ensure current trial index is valid for the data
        if not (0 <= self.current_trial_index < self.max_trials_current_recording):
             log.error(f"Invalid current trial index ({self.current_trial_index}) for selection.")
             return

        idx = self.current_trial_index # Use 0-based index internally
        if idx in self.selected_trial_indices:
            self.selected_trial_indices.remove(idx)
            log.debug(f"Removed trial {idx+1} from selection set.")
            self.statusBar.showMessage(f"Trial {idx+1} removed from average set.", 2000)
        else:
            self.selected_trial_indices.add(idx)
            log.debug(f"Added trial {idx+1} to selection set.")
            self.statusBar.showMessage(f"Trial {idx+1} added to average set.", 2000)


        # IMPORTANT: If the average plot overlay is currently shown, we must remove it
        # because the underlying selection has changed, making the current overlay invalid.
        if self.selected_average_plot_items:
            log.debug("Selection changed while average was plotted. Removing the old average plot.")
            self._remove_selected_average_plots()
            # Also, ensure the "Show/Hide Avg" button becomes unchecked, as the plot is gone.
            # Block signals to prevent _toggle_plot_selected_average from firing unnecessarily.
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)
            # _update_ui_state will fix the button text later.

        # Update the label showing selected trials
        self._update_selected_trials_display()
        # Update button enable states and the text of the "Add/Deselect" button
        self._update_ui_state()

    def _clear_avg_selection(self):
        """Clears the selected trial set and removes the average plot if shown."""
        log.debug("Clearing trial selection set.")
        if not self.selected_trial_indices:
             log.debug("Selection already empty.")
             return # Nothing to do

        # If the average plot is currently shown, remove it first.
        if self.selected_average_plot_items:
            self._remove_selected_average_plots()
            # Ensure the toggle button becomes unchecked.
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)

        self.selected_trial_indices.clear()
        self.statusBar.showMessage("Trial selection cleared.", 2000)
        # Update the display label ("Selected: None")
        self._update_selected_trials_display()
        # Update button enable states (Clear/Plot Avg should become disabled)
        self._update_ui_state()

    def _toggle_plot_selected_average(self, checked):
        """Slot connected to the 'Plot/Hide Selected Avg' toggle button."""
        log.debug(f"Toggle plot selected average requested. Button state: {'Checked' if checked else 'Unchecked'}")
        if checked:
            # If button is checked, try to plot the average
            self._plot_selected_average()
            # _plot_selected_average might uncheck the button itself if plotting fails
        else:
            # If button is unchecked, remove the average plot
            self._remove_selected_average_plots()

        # Update UI state needed to change button text ("Plot Avg" <-> "Hide Avg") via _update_ui_state
        # This needs to happen *after* the plot/remove action has finished and potentially
        # modified self.selected_average_plot_items
        self._update_ui_state()

    def _plot_selected_average(self):
        """Calculates and plots the average of selected trials for visible channels."""
        # --- Pre-conditions ---
        if not self.selected_trial_indices:
            log.warning("Cannot plot selected average: No trials selected.")
            self.statusBar.showMessage("Select trials first to plot average.", 3000)
            # Ensure button gets unchecked if state somehow becomes invalid
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)
            return
        if not self.current_recording:
             log.error("Cannot plot selected average: No recording loaded.")
             self.show_selected_average_button.blockSignals(True)
             self.show_selected_average_button.setChecked(False)
             self.show_selected_average_button.blockSignals(False)
             return
        if self.selected_average_plot_items:
             log.debug("Selected average already plotted. Ignoring redundant request.")
             # Ensure button remains checked
             self.show_selected_average_button.blockSignals(True)
             self.show_selected_average_button.setChecked(True)
             self.show_selected_average_button.blockSignals(False)
             return # Already plotted

        log.info(f"Plotting average of selected trials (0-based): {sorted(list(self.selected_trial_indices))}")
        plotted_any_avg = False

        # --- Determine Reference Time Vector ---
        # Need a time vector consistent across selected trials. Assume all trials within a channel
        # share the same time vector length and sampling. Use the first selected trial from the
        # *first visible channel* that has data for that trial.
        first_selected_idx = next(iter(sorted(self.selected_trial_indices))) # Get the smallest selected index
        ref_tvec = None
        ref_chan_id_for_tvec = None

        # Find a visible channel that has data for the reference trial
        for chan_id, plot_item in self.channel_plots.items():
             if plot_item.isVisible():
                  channel = self.current_recording.channels.get(chan_id)
                  if channel and 0 <= first_selected_idx < channel.num_trials:
                      try:
                          tvec_candidate = channel.get_relative_time_vector(first_selected_idx)
                          if tvec_candidate is not None:
                              ref_tvec = tvec_candidate
                              ref_chan_id_for_tvec = chan_id
                              log.debug(f"Using time vector from channel '{ref_chan_id_for_tvec}', trial {first_selected_idx+1}.")
                              break # Found a valid time vector
                      except Exception as e:
                           log.warning(f"Error getting tvec from ch {chan_id}, trial {first_selected_idx+1}: {e}")

        if ref_tvec is None:
             log.error("Could not determine a reference time vector for the selected average. Cannot plot.")
             QtWidgets.QMessageBox.warning(self, "Plot Error", "Could not find a valid time vector for the selected trials among visible channels.")
             # Uncheck the button as plotting failed
             self.show_selected_average_button.blockSignals(True)
             self.show_selected_average_button.setChecked(False)
             self.show_selected_average_button.blockSignals(False)
             return

        # --- Calculate and Plot Average for Each Visible Channel ---
        ds_threshold = VisConstants.DOWNSAMPLING_THRESHOLD if 'VisConstants' in globals() else 1000
        enable_ds = self.downsample_checkbox.isChecked()

        for chan_id, plot_item in self.channel_plots.items():
            if plot_item.isVisible():
                channel = self.current_recording.channels.get(chan_id)
                if not channel: continue # Skip if channel data not found

                valid_trial_data = [] # Store data arrays for averaging
                # Collect data from selected trials for this channel
                for trial_idx in self.selected_trial_indices:
                    # Check if trial index is valid for this channel
                    if 0 <= trial_idx < channel.num_trials:
                        try:
                            data = channel.get_data(trial_idx)
                            # Crucial Check: Ensure data length matches the reference time vector
                            if data is not None and len(data) == len(ref_tvec):
                                valid_trial_data.append(data)
                            elif data is not None:
                                 log.warning(f"Trial {trial_idx+1} data length ({len(data)}) mismatch for channel {chan_id} (expected {len(ref_tvec)}). Skipping this trial for average.")
                            else:
                                 log.warning(f"No data found for trial {trial_idx+1} in channel {chan_id}. Skipping for average.")
                        except Exception as e:
                             log.error(f"Error getting data for trial {trial_idx+1}, ch {chan_id}: {e}")
                    else:
                         log.warning(f"Selected trial index {trial_idx+1} is out of bounds for channel {chan_id} (max: {channel.num_trials}). Skipping.")


                # Proceed only if we collected some valid data for this channel
                if not valid_trial_data:
                    log.warning(f"No valid data found for averaging among selected trials in channel {chan_id}.")
                    continue # Skip to the next channel

                # Calculate the average
                try:
                    # Convert list of arrays to a 2D NumPy array for efficient averaging
                    selected_avg_data = np.mean(np.array(valid_trial_data), axis=0)

                    # Add the average data item to the plot
                    # Use a distinct pen (defined in __init__)
                    avg_di = plot_item.plot(ref_tvec, selected_avg_data, pen=self.SELECTED_AVG_PEN)

                    # Apply downsampling settings to the average plot item
                    avg_di.opts['autoDownsample'] = enable_ds
                    if enable_ds: avg_di.opts['autoDownsampleThreshold'] = ds_threshold

                    # Store reference to this average PlotDataItem for later removal
                    self.selected_average_plot_items[chan_id] = avg_di
                    plotted_any_avg = True
                    log.debug(f"Plotted selected average overlay for channel {chan_id}")

                except Exception as e:
                    log.error(f"Error calculating or plotting selected average for channel {chan_id}: {e}", exc_info=True)
                    # Optionally add a text item indicating error on the plot?
                    # plot_item.addItem(pg.TextItem(f"Avg Error", color='magenta'))

        # --- Post-plotting ---
        if not plotted_any_avg:
             log.warning("Failed to plot selected average for *any* visible channel.")
             QtWidgets.QMessageBox.warning(self, "Plot Warning", "Could not plot the selected average for any visible channel. Check logs for details.")
             # Uncheck the button as plotting effectively failed
             self.show_selected_average_button.blockSignals(True)
             self.show_selected_average_button.setChecked(False)
             self.show_selected_average_button.blockSignals(False)
        else:
             self.statusBar.showMessage("Selected average plotted.", 2500)


    def _remove_selected_average_plots(self):
        """Removes any currently displayed selected average plots from all channels."""
        if not self.selected_average_plot_items:
            #log.debug("Remove selected average plots requested, but none are currently plotted.")
            return # Nothing to remove

        log.debug(f"Removing {len(self.selected_average_plot_items)} selected average plot overlay(s).")
        removed_count = 0
        for chan_id, avg_di in self.selected_average_plot_items.items():
            plot_item = self.channel_plots.get(chan_id)
            # Check if the plot item still exists and the avg data item is part of it
            if plot_item and avg_di in plot_item.items:
                try:
                    plot_item.removeItem(avg_di)
                    removed_count += 1
                except Exception as e:
                    # Log error but continue trying to remove others
                    log.warning(f"Could not remove selected average item for channel {chan_id}: {e}")
            elif plot_item:
                 log.warning(f"Selected average item for channel {chan_id} not found in its plot items during removal.")
            # else: plot item for chan_id doesn't exist anymore

        if removed_count > 0:
            log.debug(f"Successfully removed {removed_count} average plot items.")
            self.statusBar.showMessage("Selected average hidden.", 2000)

        # Clear the dictionary tracking the average plot items
        self.selected_average_plot_items.clear()
        # Note: Do not call _update_ui_state here. The calling function
        # (_clear_avg_selection, _toggle_plot_selected_average, _on_plot_mode_changed, etc.)
        # is responsible for updating the UI state afterwards.


    # --- Close Event ---
    def closeEvent(self, event: QtGui.QCloseEvent):
        """Clean up resources before closing the application."""
        log.info("Close event triggered. Shutting down GUI.")
        # Optional: Add any specific cleanup here (e.g., close hardware connections if applicable)

        # Clear the graphics layout widget to release plot items
        try:
             if self.graphics_layout_widget:
                  self.graphics_layout_widget.clear()
                  # Optionally force deletion?
                  # self.graphics_layout_widget.deleteLater()
        except Exception as e:
             log.warning(f"Error clearing graphics layout widget on close: {e}")

        # Allow pyqtgraph to clean up its resources if needed
        # pg.exit() # Generally not needed unless specific cleanup required

        log.info("Accepting close event.")
        event.accept() # Allow the window to close
# --- MainWindow Class --- END ---

# --- Dummy Classes for Standalone Testing (if Synaptipy not installed) ---
class DummyChannel:
    def __init__(self, id, name, units='mV', num_trials=5, duration=1.0, rate=10000.0):
        self.id = id
        self.name = name
        self.units = units
        self.num_trials = num_trials
        self._duration = duration
        self._rate = rate
        self._num_samples = int(duration * rate)
        self.tvecs = [np.linspace(0, duration, self._num_samples, endpoint=False) for _ in range(num_trials)]
        # Generate slightly more interesting dummy data
        self.data = []
        for i in range(num_trials):
             noise = np.random.randn(self._num_samples) * 0.1 * (i + 1)
             sine_wave = np.sin(self.tvecs[i] * (i + 1) * 2 * np.pi / duration) * 0.5 * (i + 1)
             baseline_shift = i * 0.2
             self.data.append(noise + sine_wave + baseline_shift)

    def get_data(self, trial_idx):
        return self.data[trial_idx] if 0 <= trial_idx < self.num_trials else None

    def get_relative_time_vector(self, trial_idx):
        return self.tvecs[trial_idx] if 0 <= trial_idx < self.num_trials else None

    def get_averaged_data(self):
        if self.num_trials > 0 and self.data:
            try:
                # Ensure all data arrays have the same length before averaging
                min_len = min(len(d) for d in self.data)
                data_to_avg = [d[:min_len] for d in self.data]
                return np.mean(np.array(data_to_avg), axis=0)
            except Exception as e:
                log.error(f"Error averaging dummy data for channel {self.id}: {e}")
                return None
        else:
            return None

    def get_relative_averaged_time_vector(self):
        # Return the time vector corresponding to the potentially truncated averaged data
        if self.num_trials > 0 and self.tvecs:
             min_len = min(len(d) for d in self.data) if self.data else self._num_samples
             return self.tvecs[0][:min_len]
        else:
             return None

class DummyRecording:
    def __init__(self, filepath, num_channels=3):
        self.source_file = Path(filepath)
        self.sampling_rate = 10000.0
        self.duration = 2.0
        self.num_channels = num_channels
        self.max_trials = 10 # Use a decent number for testing selection
        # Create channel IDs and Channel objects
        ch_ids = [f'Ch{i+1:02d}' for i in range(num_channels)]
        self.channels = {
            ch_ids[i]: DummyChannel(
                id=ch_ids[i],
                name=f'Channel {i+1}',
                units='pA' if i % 2 == 0 else 'mV', # Alternate units
                num_trials=self.max_trials,
                duration=self.duration,
                rate=self.sampling_rate
            ) for i in range(num_channels)
        }
        # Simulate a session start time
        self.session_start_time_dt = datetime.now() # Use local time directly

class DummyNeoAdapter:
    def get_supported_file_filter(self):
        # Provides a filter string for QFileDialog
        return "Dummy Files (*.dummy);;Text Files (*.txt);;All Files (*)"

    def read_recording(self, filepath):
        # Simulate reading a file
        log.info(f"DummyNeoAdapter: Simulating read for {filepath}")
        # Create a dummy file if it doesn't exist for testing _open_file_or_folder
        if not Path(filepath).exists():
            try: Path(filepath).touch()
            except Exception as e: log.warning(f"Could not create dummy file {filepath}: {e}")

        # Vary number of channels based on filename for simple testing variation
        if '5ch' in filepath.name.lower(): num_chan = 5
        elif '1ch' in filepath.name.lower(): num_chan = 1
        else: num_chan = 3
        log.debug(f"DummyNeoAdapter: Creating recording with {num_chan} channels.")
        return DummyRecording(filepath, num_channels=num_chan)

class DummyNWBExporter:
    def export(self, recording, output_path, metadata):
        log.info(f"DummyNWBExporter: Simulating export of recording from '{recording.source_file.name}'")
        log.info(f"DummyNWBExporter: Output path: {output_path}")
        log.info(f"DummyNWBExporter: Metadata received: {metadata}")
        # Simulate success
        print(f"--- Dummy NWB Export ---")
        print(f"   Source: {recording.source_file.name}")
        print(f"   Target: {output_path}")
        print(f"   Metadata: {metadata['session_description']}, ID: {metadata['identifier']}")
        print(f"--- End Dummy Export ---")

class DummyVisConstants:
    TRIAL_COLOR = '#888888' # Slightly darker grey
    TRIAL_ALPHA = 70       # Slightly less transparent
    AVERAGE_COLOR = '#EE4B2B' # Red-Orange
    DEFAULT_PLOT_PEN_WIDTH = 1
    DOWNSAMPLING_THRESHOLD = 5000 # Higher threshold for dummy data

# Helper to define dummy error classes if Synaptipy not installed
def DummyErrors():
    class SynaptipyError(Exception): pass
    class FileReadError(SynaptipyError): pass
    class UnsupportedFormatError(SynaptipyError): pass
    class ExportError(SynaptipyError): pass
    return SynaptipyError, FileReadError, UnsupportedFormatError, ExportError
# --- End Dummy Classes ---

# --- Main Execution Block ---
if __name__ == '__main__':
    # --- Setup Logging ---
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format) # Use DEBUG for development
    log.info("Application starting...")

    # --- Check for Dummy Mode ---
    # This check happens *before* MainWindow is instantiated
    if 'Synaptipy' not in sys.modules:
        log.warning("*"*30)
        log.warning(" Running with DUMMY Synaptipy classes! ")
        log.warning(" Functionality will be simulated. ")
        log.warning("*"*30)
        # Ensure dummy error classes are globally available if needed early
        SynaptipyError, FileReadError, UnsupportedFormatError, ExportError = DummyErrors()
        # Ensure VisConstants exists
        if 'VisConstants' not in globals(): VisConstants = DummyVisConstants

    # --- Create Application and Window ---
    app = QtWidgets.QApplication(sys.argv)

    # --- Apply Dark Style (Optional) ---
    try:
        import qdarkstyle
        # Use the appropriate function based on qdarkstyle version and Qt binding
        if hasattr(qdarkstyle, 'load_stylesheet'): # Older versions
             stylesheet = qdarkstyle.load_stylesheet(qt_api='pyside6')
        elif hasattr(qdarkstyle, 'load_stylesheet_pyside6'): # Newer versions
             stylesheet = qdarkstyle.load_stylesheet_pyside6()
        else: # Fallback if structure changed again
             stylesheet = qdarkstyle.load_stylesheet() # Try generic
        app.setStyleSheet(stylesheet)
        log.info("Applied qdarkstyle theme.")
    except ImportError:
        log.info("qdarkstyle not found, using default application style.")
    except Exception as e:
        log.warning(f"Could not apply qdarkstyle: {e}")

    # --- Instantiate and Show Main Window ---
    try:
        window = MainWindow()
        window.show()
        log.info("Main window created and shown.")
    except Exception as e:
         log.critical(f"Failed to initialize or show MainWindow: {e}", exc_info=True)
         sys.exit(1) # Exit if main window fails

    # --- Start Event Loop ---
    log.info("Starting Qt event loop...")
    sys.exit(app.exec())