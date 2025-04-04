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
"""

# --- Standard Library Imports ---
import logging
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import uuid
from datetime import datetime, timezone
from functools import partial # ## MOD: Needed for connecting individual sliders

# --- Third-Party Imports ---
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets
try:
    import tzlocal # Optional, for local timezone handling
except ImportError:
    tzlocal = None

# --- Synaptipy Imports ---
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
# (NwbMetadataDialog class remains unchanged - assuming it's correct)
class NwbMetadataDialog(QtWidgets.QDialog):
    """Dialog to collect essential metadata for NWB export."""
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
    ## MOD: Constants for slider range and default zoom
    SLIDER_RANGE_MIN = 1
    SLIDER_RANGE_MAX = 100
    SLIDER_DEFAULT_VALUE = 100 # Represents 100% view (autoRange)

    def __init__(self):
        super().__init__(); self.setWindowTitle("Synaptipy"); self.setGeometry(100, 100, 1600, 900) # Increased width for sliders
        self.neo_adapter = NeoAdapter(); self.nwb_exporter = NWBExporter()
        self.current_recording: Optional[Recording] = None; self.file_list: List[Path] = []; self.current_file_index: int = -1
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}; self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG; self.current_trial_index: int = 0; self.max_trials_current_recording: int = 0

        ## MOD: State variables for zoom control
        self.y_axes_locked: bool = True
        # Store the full autorange view limits to calculate zoom from
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_y_ranges: Dict[str, Optional[Tuple[float, float]]] = {}
        # References to individual Y sliders (created dynamically)
        self.individual_y_sliders: Dict[str, QtWidgets.QSlider] = {}
        # Store references to labels associated with individual sliders
        self.individual_y_slider_labels: Dict[str, QtWidgets.QLabel] = {}


        self._setup_ui(); self._connect_signals(); self._update_ui_state()

    def _setup_ui(self):
        """Create and arrange widgets ONCE during initialization."""
        menu_bar = self.menuBar(); file_menu = menu_bar.addMenu("&File")
        self.open_file_action = file_menu.addAction("&Open..."); self.open_folder_action = None
        file_menu.addSeparator(); self.export_nwb_action = file_menu.addAction("Export to &NWB...")
        file_menu.addSeparator(); self.quit_action = file_menu.addAction("&Quit")

        main_widget = QtWidgets.QWidget(); self.setCentralWidget(main_widget)
        # ## MOD: Main layout now includes left panel, center (plots+xzoom), right (yzoom)
        main_layout = QtWidgets.QHBoxLayout(main_widget)

        # --- Left Panel (Controls) ---
        left_panel_widget = QtWidgets.QWidget()
        left_panel_layout = QtWidgets.QVBoxLayout(left_panel_widget)
        left_panel_layout.setSpacing(10)

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
        main_layout.addWidget(left_panel_widget) # Add left panel to main layout

        # --- Center Panel (Plots and X Zoom) ---
        center_panel_widget = QtWidgets.QWidget()
        center_panel_layout = QtWidgets.QVBoxLayout(center_panel_widget)

        # Top Navigation (File Prev/Next)
        nav_layout = QtWidgets.QHBoxLayout(); self.prev_file_button = QtWidgets.QPushButton("<< Prev File"); self.next_file_button = QtWidgets.QPushButton("Next File >>"); self.folder_file_index_label = QtWidgets.QLabel("")
        nav_layout.addWidget(self.prev_file_button); nav_layout.addStretch(); nav_layout.addWidget(self.folder_file_index_label); nav_layout.addStretch(); nav_layout.addWidget(self.next_file_button); center_panel_layout.addLayout(nav_layout)

        # Plot Area
        self.graphics_layout_widget = pg.GraphicsLayoutWidget(); center_panel_layout.addWidget(self.graphics_layout_widget, stretch=1) # Takes most space

        # Bottom Plot Controls (View, Trial Nav, X Zoom)
        plot_controls_layout = QtWidgets.QHBoxLayout()

        # View Controls (Original Buttons)
        view_group = QtWidgets.QGroupBox("View")
        view_layout = QtWidgets.QHBoxLayout(view_group)
        # self.zoom_in_button = QtWidgets.QPushButton("Zoom In"); ## MOD: Removed, replaced by sliders
        # self.zoom_out_button = QtWidgets.QPushButton("Zoom Out"); ## MOD: Removed, replaced by sliders
        self.reset_view_button = QtWidgets.QPushButton("Reset View")
        # view_layout.addWidget(self.zoom_in_button) # ## MOD: Removed
        # view_layout.addWidget(self.zoom_out_button) # ## MOD: Removed
        view_layout.addWidget(self.reset_view_button)
        plot_controls_layout.addWidget(view_group)

        # ## MOD: X Zoom Slider
        x_zoom_group = QtWidgets.QGroupBox("X Zoom")
        x_zoom_layout = QtWidgets.QHBoxLayout(x_zoom_group)
        self.x_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.x_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.x_zoom_slider.setToolTip("Adjust X-axis zoom (Shared)")
        x_zoom_layout.addWidget(self.x_zoom_slider)
        plot_controls_layout.addWidget(x_zoom_group, stretch=1) # Stretch to take available space

        # Trial Navigation
        trial_group = QtWidgets.QGroupBox("Trial")
        trial_layout = QtWidgets.QHBoxLayout(trial_group)
        self.prev_trial_button = QtWidgets.QPushButton("<"); self.next_trial_button = QtWidgets.QPushButton(">"); self.trial_index_label = QtWidgets.QLabel("N/A")
        trial_layout.addWidget(self.prev_trial_button); trial_layout.addWidget(self.trial_index_label); trial_layout.addWidget(self.next_trial_button)
        plot_controls_layout.addWidget(trial_group)

        center_panel_layout.addLayout(plot_controls_layout)
        main_layout.addWidget(center_panel_widget, stretch=1) # Add center panel, give it stretch

        # --- Right Panel (Y Zoom Controls) --- ## MOD: New panel
        y_zoom_panel_widget = QtWidgets.QWidget()
        y_zoom_panel_layout = QtWidgets.QVBoxLayout(y_zoom_panel_widget)
        y_zoom_panel_widget.setFixedWidth(100) # Adjust width as needed

        y_zoom_group = QtWidgets.QGroupBox("Y Zoom")
        y_zoom_group_layout = QtWidgets.QVBoxLayout(y_zoom_group)

        # Y Lock Checkbox
        self.y_lock_checkbox = QtWidgets.QCheckBox("Lock Axes")
        self.y_lock_checkbox.setChecked(self.y_axes_locked)
        self.y_lock_checkbox.setToolTip("Lock/Unlock Y-axis zoom across channels")
        y_zoom_group_layout.addWidget(self.y_lock_checkbox)

        # Global Y Slider (Visible when locked)
        self.global_y_slider_widget = QtWidgets.QWidget() # Container to easily show/hide
        global_y_slider_layout = QtWidgets.QVBoxLayout(self.global_y_slider_widget)
        global_y_slider_layout.setContentsMargins(0,0,0,0)
        global_y_slider_label = QtWidgets.QLabel("Global")
        global_y_slider_label.setAlignment(QtCore.Qt.AlignCenter)
        self.global_y_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self.global_y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.global_y_slider.setToolTip("Adjust Y-axis zoom for all visible channels")
        global_y_slider_layout.addWidget(global_y_slider_label)
        global_y_slider_layout.addWidget(self.global_y_slider, stretch=1) # Stretch vertically
        y_zoom_group_layout.addWidget(self.global_y_slider_widget)

        # Container for Individual Y Sliders (Visible when unlocked)
        self.individual_y_sliders_container = QtWidgets.QWidget()
        self.individual_y_sliders_layout = QtWidgets.QVBoxLayout(self.individual_y_sliders_container)
        self.individual_y_sliders_layout.setContentsMargins(0, 5, 0, 0)
        self.individual_y_sliders_layout.setSpacing(10)
        self.individual_y_sliders_layout.setAlignment(QtCore.Qt.AlignTop)
        y_zoom_group_layout.addWidget(self.individual_y_sliders_container, stretch=1) # Stretch

        y_zoom_panel_layout.addWidget(y_zoom_group)
        y_zoom_panel_layout.addStretch() # Push group to top
        main_layout.addWidget(y_zoom_panel_widget) # Add right panel

        # --- Status Bar ---
        self.statusBar = QtWidgets.QStatusBar(); self.setStatusBar(self.statusBar); self.statusBar.showMessage("Ready.")

        # Initial state for Y sliders visibility
        self._update_y_slider_visibility()


    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        self.open_file_action.triggered.connect(self._open_file_or_folder)
        self.export_nwb_action.triggered.connect(self._export_to_nwb); self.quit_action.triggered.connect(self.close)
        self.open_button_ui.clicked.connect(self._open_file_or_folder)
        self.downsample_checkbox.stateChanged.connect(self._trigger_plot_update); self.plot_mode_combobox.currentIndexChanged.connect(self._on_plot_mode_changed)
        # self.zoom_in_button.clicked.connect(self._zoom_in) # ## MOD: Removed
        # self.zoom_out_button.clicked.connect(self._zoom_out) # ## MOD: Removed
        self.reset_view_button.clicked.connect(self._reset_view)
        self.prev_trial_button.clicked.connect(self._prev_trial); self.next_trial_button.clicked.connect(self._next_trial)
        self.prev_file_button.clicked.connect(self._prev_file_folder); self.next_file_button.clicked.connect(self._next_file_folder)

        ## MOD: Connect zoom sliders and lock checkbox
        self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
        self.y_lock_checkbox.stateChanged.connect(self._on_y_lock_changed)
        self.global_y_slider.valueChanged.connect(self._on_global_y_zoom_changed)
        # Individual Y sliders are connected in _create_channel_ui

    # --- Reset UI and State ---
    def _reset_ui_and_state_for_new_file(self):
        """Fully resets UI elements and state related to channels and plots."""
        log.info("Resetting UI and state for new file...")
        # 1. Clear Checkboxes UI and state
        for checkbox in self.channel_checkboxes.values():
            try:
                if checkbox: checkbox.stateChanged.disconnect(self._trigger_plot_update)
            except (TypeError, RuntimeError): pass
        while self.channel_checkbox_layout.count():
            item = self.channel_checkbox_layout.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater()
        self.channel_checkboxes.clear()
        self.channel_select_group.setEnabled(False)

        # 2. Clear Plot Layout and state
        self.graphics_layout_widget.clear() # Remove all PlotItems from layout
        self.channel_plots.clear()          # Clear dictionary tracking PlotItems
        self.channel_plot_data_items.clear()# Clear dictionary tracking DataItems

        ## MOD: Clear individual Y sliders UI and state
        while self.individual_y_sliders_layout.count():
            item = self.individual_y_sliders_layout.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater() # Delete the container widget (holds label+slider)
        self.individual_y_sliders.clear()
        self.individual_y_slider_labels.clear()

        # 3. Reset Data State Variables
        self.current_recording = None
        self.max_trials_current_recording = 0
        self.current_trial_index = 0

        ## MOD: Reset zoom state
        self.base_x_range = None
        self.base_y_ranges.clear()
        self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.y_axes_locked = True # Reset to default locked state
        self.y_lock_checkbox.setChecked(self.y_axes_locked)
        self._update_y_slider_visibility() # Ensure correct initial visibility

        # 4. Reset Metadata Display
        self._clear_metadata_display()

        # 5. Reset Trial Label
        self._update_trial_label()


    # --- Create Channel UI (Checkboxes, Plot Panels, Y Sliders) ---
    def _create_channel_ui(self):
        """Creates checkboxes, PlotItems, AND individual Y-sliders. Called ONCE per file load."""
        if not self.current_recording or not self.current_recording.channels:
            log.warning("No data to create channel UI."); self.channel_select_group.setEnabled(False); return
        self.channel_select_group.setEnabled(True)
        sorted_channel_items = sorted(self.current_recording.channels.items(), key=lambda item: str(item[0]))
        log.info(f"Creating UI for {len(sorted_channel_items)} channels.")
        last_plot_item = None
        for i, (chan_id, channel) in enumerate(sorted_channel_items):
            if chan_id in self.channel_checkboxes or chan_id in self.channel_plots: log.error(f"State Error: UI element {chan_id} exists!"); continue

            # Checkbox
            checkbox = QtWidgets.QCheckBox(f"{channel.name or f'Ch {chan_id}'}") # Use name or ID
            checkbox.setChecked(True); checkbox.stateChanged.connect(self._trigger_plot_update)
            self.channel_checkbox_layout.addWidget(checkbox); self.channel_checkboxes[chan_id] = checkbox

            # Plot Item
            plot_item = self.graphics_layout_widget.addPlot(row=i, col=0); plot_item.setLabel('left', channel.name or f'Ch {chan_id}', units=channel.units or 'units'); plot_item.showGrid(x=True, y=True, alpha=0.3)
            self.channel_plots[chan_id] = plot_item
            if last_plot_item: plot_item.setXLink(last_plot_item); plot_item.hideAxis('bottom')
            last_plot_item = plot_item

            ## MOD: Create individual Y slider and label for this channel
            ind_y_slider_widget = QtWidgets.QWidget() # Container for label + slider
            ind_y_slider_layout = QtWidgets.QVBoxLayout(ind_y_slider_widget)
            ind_y_slider_layout.setContentsMargins(0,0,0,0)
            ind_y_slider_layout.setSpacing(2)

            # Short label for the slider
            slider_label = QtWidgets.QLabel(f"{channel.name or chan_id[:4]}") # Use name or first few chars of ID
            slider_label.setAlignment(QtCore.Qt.AlignCenter)
            slider_label.setToolTip(f"Y Zoom for {channel.name or chan_id}")
            self.individual_y_slider_labels[chan_id] = slider_label # Store label reference
            ind_y_slider_layout.addWidget(slider_label)

            y_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
            y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
            y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            y_slider.setToolTip(f"Adjust Y-axis zoom for {channel.name or chan_id}")
            # Use partial to pass chan_id to the handler
            y_slider.valueChanged.connect(partial(self._on_individual_y_zoom_changed, chan_id))
            ind_y_slider_layout.addWidget(y_slider, stretch=1)

            self.individual_y_sliders[chan_id] = y_slider # Store slider reference
            self.individual_y_sliders_layout.addWidget(ind_y_slider_widget) # Add container to layout
            ind_y_slider_widget.setVisible(False) # Initially hidden, visibility managed by _update_y_slider_visibility

        if last_plot_item: last_plot_item.setLabel('bottom', "Time", units='s'); last_plot_item.showAxis('bottom')


    # --- Action Handlers (Slots) --- START ---

    # --- Combined File/Folder Opening Logic --- (Unchanged)
    def _open_file_or_folder(self):
        """Handles the 'Open...' button/action. Selects one file, then finds siblings."""
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

    # --- Load and Display ---
    def _load_and_display_file(self, filepath: Path):
        """Loads data, resets UI, creates new UI elements, updates display."""
        self.statusBar.showMessage(f"Loading '{filepath.name}'..."); QtWidgets.QApplication.processEvents()
        self._reset_ui_and_state_for_new_file(); self.current_recording = None # Reset includes zoom state now
        try:
            self.current_recording = self.neo_adapter.read_recording(filepath); log.info(f"Loaded {filepath.name}")
            self.max_trials_current_recording = self.current_recording.max_trials if self.current_recording else 0
            self._create_channel_ui(); # Creates plots and individual sliders
            self._update_metadata_display();
            self._update_plot() # This will plot data
            self._reset_view() # ## MOD: Call reset view AFTER initial plot to set base ranges and reset sliders
            self.statusBar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000)
        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e: log.error(f"Load failed {filepath}: {e}", exc_info=False); QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load file:\n{filepath.name}\n\nError: {e}"); self._clear_metadata_display(); self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        except Exception as e: log.error(f"Unexpected error loading {filepath}: {e}", exc_info=True); QtWidgets.QMessageBox.critical(self, "Unexpected Error", f"Error loading:\n{filepath.name}\n\n{e}"); self._clear_metadata_display(); self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        finally: self._update_ui_state() # Updates button enables etc.

    # --- Display Option Changes ---
    def _on_plot_mode_changed(self, index):
        """Handles changes in the plot mode combobox."""
        self.current_plot_mode = index
        log.info(f"Plot mode changed to: {'Overlay+Avg' if index == self.PlotMode.OVERLAY_AVG else 'Cycle Single'}")
        self.current_trial_index = 0 # Reset trial index
        # ## MOD: No need to reset view here necessarily, just update plot and UI state
        # self._update_ui_state() # Update plot will call this
        self._trigger_plot_update() # Update plot immediately
        # self._reset_visible_plot_views() # Let user reset if they want

    def _trigger_plot_update(self):
        """Connected to checkboxes and downsample option. Updates plot and Y slider visibility."""
        if not self.current_recording: return

        # Determine if the sender was a checkbox being turned ON/OFF
        sender_checkbox = self.sender()
        is_checkbox_trigger = isinstance(sender_checkbox, QtWidgets.QCheckBox) and sender_checkbox != self.downsample_checkbox and sender_checkbox != self.y_lock_checkbox

        # Update the plot data first
        self._update_plot()

        ## MOD: Update visibility of individual Y sliders whenever a channel checkbox changes
        if is_checkbox_trigger:
            self._update_y_slider_visibility()

        # Reset view only if a checkbox was turned ON
        if is_checkbox_trigger and sender_checkbox.isChecked():
            channel_id_to_reset = None
            # Find the channel ID associated with this checkbox
            for ch_id, cb in self.channel_checkboxes.items():
                if cb == sender_checkbox: channel_id_to_reset = ch_id; break
            if channel_id_to_reset:
                plot_item = self.channel_plots.get(channel_id_to_reset)
                if plot_item and plot_item.isVisible(): # Check if it's actually visible after update
                    log.debug(f"Checkbox toggled ON for {channel_id_to_reset}, resetting its view.")
                    # ## MOD: Resetting view now also resets base ranges and sliders
                    self._reset_single_plot_view(channel_id_to_reset)


    # --- Plotting Core Logic ---
    def _clear_plot_data_only(self):
        """Clears only the plotted data lines/text from all existing PlotItems."""
        for chan_id, plot_item in self.channel_plots.items():
            if plot_item is None or plot_item.scene() is None: continue
            # Keep grid, labels etc.
            items_to_remove = [item for item in plot_item.items if isinstance(item, (pg.PlotDataItem, pg.TextItem))]
            for item in items_to_remove:
                plot_item.removeItem(item)
        self.channel_plot_data_items.clear() # Clear data item refs if you were using them

    def _update_plot(self):
        """Plots data onto the appropriate EXISTING PlotItems based on selections and mode."""
        self._clear_plot_data_only()
        if not self.current_recording or not self.channel_plots:
            log.warning("Update plot: No recording or plot items exist.")
            # Ensure the label is removed if plots exist but no data is loaded/visible
            items = self.graphics_layout_widget.items()
            if not any(isinstance(item, pg.PlotItem) for item in items):
                 self.graphics_layout_widget.clear() # Clear any stray labels
                 self.graphics_layout_widget.addLabel("Load data", row=0, col=0)
            self._update_ui_state() # Ensure controls are disabled if no data
            return

        is_cycle_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        log.debug(f"Updating plot data. Mode: {'Cycle Single' if is_cycle_mode else 'Overlay+Avg'}, Trial: {self.current_trial_index+1}/{self.max_trials_current_recording}")
        trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR + (VisConstants.TRIAL_ALPHA,), width=VisConstants.DEFAULT_PLOT_PEN_WIDTH)
        avg_pen = pg.mkPen(VisConstants.AVERAGE_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1)
        single_trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH)
        any_data_plotted = False
        visible_plots_this_update: List[pg.PlotItem] = [] # Track plots getting data

        # --- Store current view ranges BEFORE plotting new data ---
        # This is tricky because plotting itself might trigger autorange if view is unset
        # It's generally safer to update ranges AFTER plotting and AFTER calling autoRange (in _reset_view)

        for chan_id, plot_item in self.channel_plots.items():
            checkbox = self.channel_checkboxes.get(chan_id); channel = self.current_recording.channels.get(chan_id)
            if checkbox and checkbox.isChecked() and channel:
                plot_item.setVisible(True); plotted_something = False; visible_plots_this_update.append(plot_item)

                # --- Plotting logic (unchanged) ---
                if not is_cycle_mode: # Overlay+Avg Mode
                    # ... (rest of overlay plotting) ...
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
                    # ... (rest of cycle plotting) ...
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
            elif plot_item:
                plot_item.hide() # Hide plot panel if unchecked

        # --- Configure bottom axis on the last *currently visible* plot --- (Unchanged)
        last_visible_plot_this_update = visible_plots_this_update[-1] if visible_plots_this_update else None
        for item in self.channel_plots.values(): # Iterate all plots to configure axes
             if item in visible_plots_this_update:
                 is_last = (item == last_visible_plot_this_update)
                 item.showAxis('bottom', show=is_last)
                 if is_last: item.setLabel('bottom', "Time", units='s')
                 # Ensure X linking is correct among visible plots for this update
                 try:
                    current_vis_idx = visible_plots_this_update.index(item)
                    if current_vis_idx > 0: item.setXLink(visible_plots_this_update[current_vis_idx - 1])
                    else: item.setXLink(None) # First visible plot is unlinked
                 except ValueError: # Should not happen if item is in the list
                     item.setXLink(None)
             else:
                 item.hideAxis('bottom') # Hide axis if plot panel is hidden

        self._update_trial_label()
        if not any_data_plotted and self.current_recording and self.channel_plots: log.info("No channels selected or no data plotted.")

        # ## MOD: Update UI state after plot changes (enables/disables controls)
        self._update_ui_state()
        # ## MOD: Update Y slider visibility based on which plots are now visible
        # This is now called from _trigger_plot_update when needed

    # --- Metadata Display --- (Unchanged)
    def _update_metadata_display(self):
        if self.current_recording: rec = self.current_recording; self.filename_label.setText(rec.source_file.name); self.sampling_rate_label.setText(f"{rec.sampling_rate:.2f} Hz" if rec.sampling_rate else "N/A"); self.duration_label.setText(f"{rec.duration:.3f} s" if rec.duration else "N/A"); num_ch = rec.num_channels; max_tr = self.max_trials_current_recording; self.channels_label.setText(f"{num_ch} ch, {max_tr} trial(s)")
        else: self._clear_metadata_display()
    def _clear_metadata_display(self):
        self.filename_label.setText("N/A"); self.sampling_rate_label.setText("N/A"); self.channels_label.setText("N/A"); self.duration_label.setText("N/A")

    # --- UI State Update ---
    def _update_ui_state(self):
        has_data = self.current_recording is not None
        has_visible_plots = any(p.isVisible() for p in self.channel_plots.values())
        is_folder = len(self.file_list) > 1
        is_cycling_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        has_multiple_trials = self.max_trials_current_recording > 1

        enable_data_controls = has_data and has_visible_plots # ## MOD: Base enable on visible plots too
        enable_any_data_controls = has_data # For things like export, mode change

        # ## MOD: Enable/disable zoom controls based on visible data
        self.reset_view_button.setEnabled(enable_data_controls)
        self.x_zoom_slider.setEnabled(enable_data_controls)
        self.y_lock_checkbox.setEnabled(enable_data_controls)
        self.global_y_slider.setEnabled(enable_data_controls and self.y_axes_locked)
        # Individual sliders enabled/disabled based on visibility in _update_y_slider_visibility

        self.plot_mode_combobox.setEnabled(enable_any_data_controls)
        self.downsample_checkbox.setEnabled(enable_any_data_controls)
        self.export_nwb_action.setEnabled(enable_any_data_controls)
        self.channel_select_group.setEnabled(has_data) # Channel selection enabled if data exists

        enable_trial_cycle = enable_any_data_controls and is_cycling_mode and has_multiple_trials
        self.prev_trial_button.setEnabled(enable_trial_cycle and self.current_trial_index > 0)
        self.next_trial_button.setEnabled(enable_trial_cycle and self.current_trial_index < self.max_trials_current_recording - 1)
        self.trial_index_label.setVisible(enable_any_data_controls and is_cycling_mode)
        self._update_trial_label()

        self.prev_file_button.setVisible(is_folder); self.next_file_button.setVisible(is_folder); self.folder_file_index_label.setVisible(is_folder)
        if is_folder:
             self.prev_file_button.setEnabled(self.current_file_index > 0)
             self.next_file_button.setEnabled(self.current_file_index < len(self.file_list) - 1)
             current_filename = "N/A"
             if 0 <= self.current_file_index < len(self.file_list):
                 current_filename = self.file_list[self.current_file_index].name
             self.folder_file_index_label.setText(f"File {self.current_file_index + 1}/{len(self.file_list)}: {current_filename}")
        else: self.folder_file_index_label.setText("")


    # --- Trial Label Update --- (Unchanged)
    def _update_trial_label(self):
        if (self.current_recording and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0): self.trial_index_label.setText(f"{self.current_trial_index + 1} / {self.max_trials_current_recording}")
        else: self.trial_index_label.setText("N/A")

    # --- Plot Control Slots (Zoom/Pan/Reset) --- ## MOD: Reworked for sliders

    # --- Zoom Calculation Helper ---
    def _calculate_new_range(self, base_range: Tuple[float, float], slider_value: int) -> Optional[Tuple[float, float]]:
        """Calculates new view range based on base range and slider percentage."""
        if base_range is None or base_range[0] is None or base_range[1] is None:
            return None
        try:
            min_val, max_val = base_range
            center = (min_val + max_val) / 2.0
            full_span = max_val - min_val
            if full_span <= 0: full_span = 1.0 # Avoid zero span

            # Map slider 1-100 to zoom factor (100 = full span, 1 = 1% span)
            zoom_factor = slider_value / float(self.SLIDER_RANGE_MAX)
            new_span = full_span * zoom_factor

            new_min = center - new_span / 2.0
            new_max = center + new_span / 2.0
            return (new_min, new_max)
        except Exception as e:
            log.error(f"Error calculating new range: {e}", exc_info=True)
            return None

    # --- X Zoom ---
    def _on_x_zoom_changed(self, value):
        """Applies zoom based on the X slider value."""
        if self.base_x_range is None:
            # log.debug("X Zoom: Base X range not set.")
            return # Not ready yet

        new_x_range = self._calculate_new_range(self.base_x_range, value)
        if new_x_range is None:
            return

        # Apply to the first visible plot (others are linked)
        first_visible_plot = None
        for plot in self.channel_plots.values():
            if plot.isVisible():
                first_visible_plot = plot
                break

        if first_visible_plot:
            # Use setLimits to prevent panning outside base range if desired? No, allow panning.
            # Disable auto-ranging when manually setting range
            first_visible_plot.getViewBox().setXRange(new_x_range[0], new_x_range[1], padding=0)
            # log.debug(f"X Zoom set to: {new_x_range}")
        # else: log.debug("X Zoom: No visible plot to apply range.")


    # --- Y Zoom (Locking and Sliders) ---
    def _on_y_lock_changed(self, state):
        """Handles the Y-axis lock checkbox state change."""
        self.y_axes_locked = bool(state == QtCore.Qt.Checked.value) # PySide6 uses enum value
        log.info(f"Y-axes {'locked' if self.y_axes_locked else 'unlocked'}.")
        self._update_y_slider_visibility()
        # If locking, optionally synchronize all views to the global slider's current setting
        if self.y_axes_locked:
            self._apply_global_y_zoom(self.global_y_slider.value())
        self._update_ui_state() # Update global slider enable state


    def _update_y_slider_visibility(self):
        """Shows/hides global or individual Y sliders based on lock state and plot visibility."""
        locked = self.y_axes_locked
        self.global_y_slider_widget.setVisible(locked)
        self.individual_y_sliders_container.setVisible(not locked)

        if not locked:
            # Show/hide individual sliders based on corresponding plot's visibility
            visible_count = 0
            for chan_id, slider in self.individual_y_sliders.items():
                plot = self.channel_plots.get(chan_id)
                label = self.individual_y_slider_labels.get(chan_id)
                slider_widget = slider.parentWidget() # Get the container (QWidget holding label+slider)

                is_visible = plot is not None and plot.isVisible()
                if slider_widget: slider_widget.setVisible(is_visible)
                # if label: label.setVisible(is_visible) # Label is inside container
                # slider.setVisible(is_visible)
                slider.setEnabled(is_visible) # Also disable if not visible
                if is_visible: visible_count += 1
            log.debug(f"Updated individual Y slider visibility. {visible_count} visible.")


    def _on_global_y_zoom_changed(self, value):
        """Applies zoom to all visible plots based on the global Y slider."""
        if not self.y_axes_locked:
            return # Should only be active when locked
        self._apply_global_y_zoom(value)

    def _apply_global_y_zoom(self, value):
        """Helper function to apply a Y zoom value to all visible plots."""
        log.debug(f"Applying global Y zoom value: {value}")
        visible_count = 0
        for chan_id, plot in self.channel_plots.items():
            if plot.isVisible():
                base_y = self.base_y_ranges.get(chan_id)
                if base_y is None:
                    # log.warning(f"Global Y Zoom: Base Y range not set for visible channel {chan_id}.")
                    continue

                new_y_range = self._calculate_new_range(base_y, value)
                if new_y_range:
                    plot.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
                    visible_count += 1
                # else: log.warning(f"Global Y Zoom: Failed calculation for {chan_id}")
        # if visible_count > 0: log.debug(f"Applied global Y zoom to {visible_count} plots.")


    def _on_individual_y_zoom_changed(self, chan_id, value):
        """Applies zoom to a specific plot based on its individual Y slider."""
        if self.y_axes_locked:
            return # Should only be active when unlocked

        plot = self.channel_plots.get(chan_id)
        base_y = self.base_y_ranges.get(chan_id)

        if plot is None or not plot.isVisible():
            # log.debug(f"Individual Y Zoom: Plot {chan_id} not found or not visible.")
            return
        if base_y is None:
            # log.debug(f"Individual Y Zoom: Base Y range not set for {chan_id}.")
            return

        new_y_range = self._calculate_new_range(base_y, value)
        if new_y_range:
            plot.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
            # log.debug(f"Individual Y Zoom for {chan_id} set to: {new_y_range}")
        # else: log.warning(f"Individual Y Zoom: Failed calculation for {chan_id}")

    # --- Reset View ---
    def _reset_view(self):
        """Resets the view range on ALL currently visible plots and updates base ranges/sliders."""
        log.info("Reset View triggered.")
        visible_plots = []
        for chan_id, plot_item in self.channel_plots.items():
             if plot_item.isVisible():
                 plot_item.getViewBox().autoRange() # Let pyqtgraph calculate optimal view
                 visible_plots.append((chan_id, plot_item))

        if not visible_plots:
            log.debug("Reset View: No visible plots found.")
            self.base_x_range = None
            self.base_y_ranges.clear()
            # Reset sliders anyway
            self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            for slider in self.individual_y_sliders.values():
                slider.setValue(self.SLIDER_DEFAULT_VALUE)
            return

        # --- Capture the new base ranges AFTER autoRange ---
        # Use the first visible plot for X range (they are linked)
        first_chan_id, first_plot = visible_plots[0]
        try:
            self.base_x_range = first_plot.getViewBox().viewRange()[0]
            log.debug(f"Reset View: New base X range: {self.base_x_range}")
        except Exception as e:
            log.error(f"Reset View: Error getting base X range: {e}")
            self.base_x_range = None

        # Get Y ranges for all visible plots
        self.base_y_ranges.clear() # Clear old ranges first
        for chan_id, plot in visible_plots:
             try:
                 self.base_y_ranges[chan_id] = plot.getViewBox().viewRange()[1]
                 log.debug(f"Reset View: New base Y range for {chan_id}: {self.base_y_ranges[chan_id]}")
             except Exception as e:
                 log.error(f"Reset View: Error getting base Y range for {chan_id}: {e}")
                 # Leave it out of the dict if error occurs

        # --- Reset all sliders to 100% ---
        # Disconnect signals temporarily to avoid triggering zoom handlers during reset
        try: self.x_zoom_slider.valueChanged.disconnect(self._on_x_zoom_changed)
        except (TypeError, RuntimeError): pass
        try: self.global_y_slider.valueChanged.disconnect(self._on_global_y_zoom_changed)
        except (TypeError, RuntimeError): pass
        individual_connections = {}
        for chan_id, slider in self.individual_y_sliders.items():
            try:
                # Store the connection to reconnect later
                # Note: This assumes only one connection. If multiple exist, this needs refinement.
                # Finding the exact slot is tricky, partial makes it harder.
                # Simpler: just reconnect after setting value.
                slider.valueChanged.disconnect() # Disconnect all slots
                individual_connections[chan_id] = partial(self._on_individual_y_zoom_changed, chan_id)
            except (TypeError, RuntimeError): pass

        # Set values
        self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        for slider in self.individual_y_sliders.values():
            slider.setValue(self.SLIDER_DEFAULT_VALUE)

        # Reconnect signals
        self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
        self.global_y_slider.valueChanged.connect(self._on_global_y_zoom_changed)
        for chan_id, connection in individual_connections.items():
             if chan_id in self.individual_y_sliders:
                 self.individual_y_sliders[chan_id].valueChanged.connect(connection)

        log.debug("Reset View: Sliders reset to default.")
        self._update_ui_state() # Ensure sliders are enabled/disabled correctly


    def _reset_single_plot_view(self, chan_id: str):
        """Resets view for a single plot, updates its base Y range and slider."""
        plot_item = self.channel_plots.get(chan_id)
        if not plot_item or not plot_item.isVisible():
            log.debug(f"Reset Single View: Plot {chan_id} not visible or found.")
            return

        log.debug(f"Resetting single plot view for {chan_id}")
        plot_item.getViewBox().autoRange()

        # Update base Y range for this channel
        try:
            new_range = plot_item.getViewBox().viewRange()[1]
            self.base_y_ranges[chan_id] = new_range
            log.debug(f"Reset Single View: New base Y range for {chan_id}: {new_range}")
        except Exception as e:
            log.error(f"Reset Single View: Error getting base Y range for {chan_id}: {e}")
            if chan_id in self.base_y_ranges: del self.base_y_ranges[chan_id] # Remove potentially invalid entry


        # Reset the corresponding individual Y slider if it exists
        slider = self.individual_y_sliders.get(chan_id)
        if slider:
            try:
                slider.valueChanged.disconnect()
            except (TypeError, RuntimeError): pass
            slider.setValue(self.SLIDER_DEFAULT_VALUE)
            slider.valueChanged.connect(partial(self._on_individual_y_zoom_changed, chan_id))
            log.debug(f"Reset Single View: Slider for {chan_id} reset.")

        # Also reset global slider if axes are locked
        if self.y_axes_locked:
            try:
                self.global_y_slider.valueChanged.disconnect()
            except (TypeError, RuntimeError): pass
            self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            self.global_y_slider.valueChanged.connect(self._on_global_y_zoom_changed)
            # Re-apply global zoom to ensure consistency if other plots were already zoomed
            self._apply_global_y_zoom(self.SLIDER_DEFAULT_VALUE)

        # We don't reset X slider/range here as it's linked and controlled separately


    # --- Helper for resetting visible plot views --- (OBSOLETE - use _reset_view)
    # def _reset_visible_plot_views(self): ... # Removed


    # --- Trial Navigation Slots ---
    def _next_trial(self):
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0:
            if self.current_trial_index < self.max_trials_current_recording - 1:
                self.current_trial_index += 1; log.debug(f"Next trial: {self.current_trial_index + 1}")
                # ## MOD: Update plot, then reset view to get correct base ranges for the new trial data
                self._update_plot()
                self._reset_view() # Reset view resets base ranges and sliders for the new trial
                # self._update_ui_state() # Called by _update_plot and _reset_view
            else: log.debug("Already at last trial.")
    def _prev_trial(self):
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE:
            if self.current_trial_index > 0:
                self.current_trial_index -= 1; log.debug(f"Previous trial: {self.current_trial_index + 1}")
                # ## MOD: Update plot, then reset view
                self._update_plot()
                self._reset_view()
                # self._update_ui_state() # Called by _update_plot and _reset_view
            else: log.debug("Already at first trial.")

    # --- Folder Navigation Slots --- (Unchanged logic, relies on _load_and_display_file resetting state)
    def _next_file_folder(self):
        if self.file_list and self.current_file_index < len(self.file_list) - 1: self.current_file_index += 1; self._load_and_display_file(self.file_list[self.current_file_index])
    def _prev_file_folder(self):
        if self.file_list and self.current_file_index > 0: self.current_file_index -= 1; self._load_and_display_file(self.file_list[self.current_file_index])

    # --- NWB Export Slot --- (Unchanged)
    def _export_to_nwb(self):
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
    def closeEvent(self, event: QtGui.QCloseEvent):
        log.info("Close event triggered. Shutting down.")
        # Clean up resources if necessary
        self.graphics_layout_widget.clear()
        event.accept()
# --- MainWindow Class --- END ---

# --- Main Execution Block (Example) ---
if __name__ == '__main__':
    # Setup basic logging to console for testing
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create dummy Synaptipy classes/functions if running standalone for UI testing
    if 'Synaptipy' not in sys.modules:
        print("Warning: Synaptipy modules not found. Using dummy implementations for UI testing.")
        class DummyChannel:
            def __init__(self, id, name, units='mV', num_trials=5, duration=1.0, rate=1000.0):
                self.id = id; self.name = name; self.units = units; self.num_trials = num_trials
                self._duration = duration; self._rate = rate
                self.data = [np.random.randn(int(duration * rate)) * (i+1) * 0.1 for i in range(num_trials)]
                self.tvecs = [np.linspace(0, duration, int(duration*rate), endpoint=False) for _ in range(num_trials)]
            def get_data(self, trial_idx): return self.data[trial_idx] if 0 <= trial_idx < self.num_trials else None
            def get_relative_time_vector(self, trial_idx): return self.tvecs[trial_idx] if 0 <= trial_idx < self.num_trials else None
            def get_averaged_data(self): return np.mean(self.data, axis=0) if self.num_trials > 0 else None
            def get_relative_averaged_time_vector(self): return self.tvecs[0] if self.num_trials > 0 else None

        class DummyRecording:
            def __init__(self, filepath, num_channels=3):
                self.source_file = Path(filepath)
                self.sampling_rate = 1000.0
                self.duration = 1.0
                self.num_channels = num_channels
                self.max_trials = 5
                self.channels = {f'ch{i}': DummyChannel(f'ch{i}', f'Channel {i}', num_trials=self.max_trials, duration=self.duration, rate=self.sampling_rate) for i in range(num_channels)}
                self.session_start_time_dt = datetime.now()

        class DummyNeoAdapter:
            def get_supported_file_filter(self): return "Dummy Files (*.dummy);;All Files (*)"
            def read_recording(self, filepath):
                if not Path(filepath).exists():
                     # Create a dummy file for testing open dialog
                     try: Path(filepath).touch()
                     except: pass
                     # raise FileNotFoundError(f"Dummy file not found: {filepath}")
                print(f"DummyNeoAdapter: Reading {filepath}")
                # Simulate different numbers of channels based on filename?
                num_chan = 3 if '3ch' in filepath.name else 2
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
            TRIAL_COLOR = '#808080'; TRIAL_ALPHA = 100; AVERAGE_COLOR = '#FF0000'
            DEFAULT_PLOT_PEN_WIDTH = 1; DOWNSAMPLING_THRESHOLD = 500


    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())