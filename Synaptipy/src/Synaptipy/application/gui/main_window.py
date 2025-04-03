# -*- coding: utf-8 -*-
"""
Main Window for the Synaptipy GUI application.
Uses PySide6 for the GUI framework and pyqtgraph for plotting.
Features multi-panel plots per channel, channel selection,
and different trial plotting modes (overlay+avg, single trial cycling) via ComboBox.
Includes a single UI button for opening files (scans folder for same extension).
Uses NeoAdapter to dynamically generate file filters.
Plot view resets strategically when channel visibility or plot options change.
"""

# --- Standard Library Imports ---
import logging
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import uuid
from datetime import datetime, timezone

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
            return None # Corrected return
        return {"session_description": desc, "identifier": ident, "session_start_time": start_time, "experimenter": self.experimenter.text().strip() or None, "lab": self.lab.text().strip() or None, "institution": self.institution.text().strip() or None, "session_id": self.session_id.text().strip() or None}
# --- NwbMetadataDialog End ---


# --- MainWindow Class ---
class MainWindow(QtWidgets.QMainWindow):
    """Main application window with multi-panel plotting and trial modes."""
    class PlotMode: OVERLAY_AVG = 0; CYCLE_SINGLE = 1

    def __init__(self):
        super().__init__(); self.setWindowTitle("Synaptipy"); self.setGeometry(100, 100, 1400, 850)
        self.neo_adapter = NeoAdapter(); self.nwb_exporter = NWBExporter()
        self.current_recording: Optional[Recording] = None; self.file_list: List[Path] = []; self.current_file_index: int = -1
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}; self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG; self.current_trial_index: int = 0; self.max_trials_current_recording: int = 0
        self._setup_ui(); self._connect_signals(); self._update_ui_state()

    def _setup_ui(self):
        """Create and arrange widgets ONCE during initialization."""
        menu_bar = self.menuBar(); file_menu = menu_bar.addMenu("&File")
        self.open_file_action = file_menu.addAction("&Open..."); self.open_folder_action = None
        file_menu.addSeparator(); self.export_nwb_action = file_menu.addAction("Export to &NWB...")
        file_menu.addSeparator(); self.quit_action = file_menu.addAction("&Quit")
        main_widget = QtWidgets.QWidget(); self.setCentralWidget(main_widget); main_layout = QtWidgets.QHBoxLayout(main_widget)
        left_panel = QtWidgets.QVBoxLayout(); left_panel.setSpacing(10)
        file_op_group = QtWidgets.QGroupBox("Load Data"); file_op_layout = QtWidgets.QHBoxLayout(file_op_group)
        self.open_button_ui = QtWidgets.QPushButton("Open..."); file_op_layout.addWidget(self.open_button_ui); left_panel.addWidget(file_op_group)
        display_group = QtWidgets.QGroupBox("Display Options"); display_layout = QtWidgets.QVBoxLayout(display_group)
        self.downsample_checkbox = QtWidgets.QCheckBox("Auto Downsample Plot"); self.downsample_checkbox.setChecked(True)
        plot_mode_layout = QtWidgets.QHBoxLayout(); plot_mode_layout.addWidget(QtWidgets.QLabel("Plot Mode:"))
        self.plot_mode_combobox = QtWidgets.QComboBox(); self.plot_mode_combobox.addItems(["Overlay All + Avg", "Cycle Single Trial"]); self.plot_mode_combobox.setCurrentIndex(self.current_plot_mode)
        plot_mode_layout.addWidget(self.plot_mode_combobox); display_layout.addLayout(plot_mode_layout); display_layout.addWidget(self.downsample_checkbox); left_panel.addWidget(display_group)
        self.channel_select_group = QtWidgets.QGroupBox("Channels"); self.channel_scroll_area = QtWidgets.QScrollArea(); self.channel_scroll_area.setWidgetResizable(True)
        self.channel_select_widget = QtWidgets.QWidget(); self.channel_checkbox_layout = QtWidgets.QVBoxLayout(self.channel_select_widget); self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignTop)
        self.channel_scroll_area.setWidget(self.channel_select_widget); channel_group_layout = QtWidgets.QVBoxLayout(self.channel_select_group); channel_group_layout.addWidget(self.channel_scroll_area); left_panel.addWidget(self.channel_select_group)
        meta_group = QtWidgets.QGroupBox("File Information"); meta_layout = QtWidgets.QFormLayout(meta_group)
        self.filename_label = QtWidgets.QLabel("N/A"); self.sampling_rate_label = QtWidgets.QLabel("N/A"); self.channels_label = QtWidgets.QLabel("N/A"); self.duration_label = QtWidgets.QLabel("N/A")
        meta_layout.addRow("File:", self.filename_label); meta_layout.addRow("Sampling Rate:", self.sampling_rate_label); meta_layout.addRow("Duration:", self.duration_label); meta_layout.addRow("Channels:", self.channels_label)
        left_panel.addWidget(meta_group); left_panel.addStretch(); main_layout.addLayout(left_panel)
        right_panel = QtWidgets.QVBoxLayout()
        nav_layout = QtWidgets.QHBoxLayout(); self.prev_file_button = QtWidgets.QPushButton("<< Prev File"); self.next_file_button = QtWidgets.QPushButton("Next File >>"); self.folder_file_index_label = QtWidgets.QLabel("")
        nav_layout.addWidget(self.prev_file_button); nav_layout.addStretch(); nav_layout.addWidget(self.folder_file_index_label); nav_layout.addStretch(); nav_layout.addWidget(self.next_file_button); right_panel.addLayout(nav_layout)
        self.graphics_layout_widget = pg.GraphicsLayoutWidget(); right_panel.addWidget(self.graphics_layout_widget, stretch=1)
        plot_controls_layout = QtWidgets.QHBoxLayout(); plot_controls_layout.addWidget(QtWidgets.QLabel("View:"))
        self.zoom_in_button = QtWidgets.QPushButton("Zoom In"); self.zoom_out_button = QtWidgets.QPushButton("Zoom Out"); self.reset_view_button = QtWidgets.QPushButton("Reset View")
        plot_controls_layout.addWidget(self.zoom_in_button); plot_controls_layout.addWidget(self.zoom_out_button); plot_controls_layout.addWidget(self.reset_view_button)
        plot_controls_layout.addStretch(1); plot_controls_layout.addWidget(QtWidgets.QLabel("Trial:"))
        self.prev_trial_button = QtWidgets.QPushButton("<"); self.next_trial_button = QtWidgets.QPushButton(">"); self.trial_index_label = QtWidgets.QLabel("N/A")
        plot_controls_layout.addWidget(self.prev_trial_button); plot_controls_layout.addWidget(self.trial_index_label); plot_controls_layout.addWidget(self.next_trial_button)
        right_panel.addLayout(plot_controls_layout)
        main_layout.addLayout(right_panel, stretch=1)
        self.statusBar = QtWidgets.QStatusBar(); self.setStatusBar(self.statusBar); self.statusBar.showMessage("Ready.")

    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        self.open_file_action.triggered.connect(self._open_file_or_folder)
        self.export_nwb_action.triggered.connect(self._export_to_nwb); self.quit_action.triggered.connect(self.close)
        self.open_button_ui.clicked.connect(self._open_file_or_folder)
        self.downsample_checkbox.stateChanged.connect(self._trigger_plot_update); self.plot_mode_combobox.currentIndexChanged.connect(self._on_plot_mode_changed)
        self.zoom_in_button.clicked.connect(self._zoom_in); self.zoom_out_button.clicked.connect(self._zoom_out); self.reset_view_button.clicked.connect(self._reset_view)
        self.prev_trial_button.clicked.connect(self._prev_trial); self.next_trial_button.clicked.connect(self._next_trial)
        self.prev_file_button.clicked.connect(self._prev_file_folder); self.next_file_button.clicked.connect(self._next_file_folder)

    # --- Reset UI and State (Corrected Syntax) --- START ---
    def _reset_ui_and_state_for_new_file(self):
        """Fully resets UI elements and state related to channels and plots."""
        log.info("Resetting UI and state for new file...")
        # 1. Clear Checkboxes UI and state
        for checkbox in self.channel_checkboxes.values():
            try:
                if checkbox: checkbox.stateChanged.disconnect(self._trigger_plot_update)
            except (TypeError, RuntimeError):
                pass # Ignore errors if already disconnected/deleted
        while self.channel_checkbox_layout.count():
            item = self.channel_checkbox_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.channel_checkboxes.clear()
        self.channel_select_group.setEnabled(False) # Disable groupbox

        # 2. Clear Plot Layout and state
        self.graphics_layout_widget.clear() # Remove all PlotItems from layout
        self.channel_plots.clear()          # Clear dictionary tracking PlotItems
        self.channel_plot_data_items.clear()# Clear dictionary tracking DataItems

        # 3. Reset Data State Variables
        self.current_recording = None
        self.max_trials_current_recording = 0
        self.current_trial_index = 0 # Reset trial index

        # 4. Reset Metadata Display
        self._clear_metadata_display()

        # 5. Reset Trial Label
        self._update_trial_label()
    # --- Reset UI and State (Corrected Syntax) --- END ---


    # --- Create Channel UI (Checkboxes & Plot Panels) ---
    def _create_channel_ui(self):
        """Creates checkboxes AND PlotItems in the layout. Called ONCE per file load."""
        if not self.current_recording or not self.current_recording.channels:
            log.warning("No data to create channel UI."); self.channel_select_group.setEnabled(False); return
        self.channel_select_group.setEnabled(True)
        sorted_channel_items = sorted(self.current_recording.channels.items(), key=lambda item: str(item[0]))
        log.info(f"Creating UI for {len(sorted_channel_items)} channels.")
        last_plot_item = None
        for i, (chan_id, channel) in enumerate(sorted_channel_items):
            if chan_id in self.channel_checkboxes or chan_id in self.channel_plots: log.error(f"State Error: UI element {chan_id} exists!"); continue
            checkbox = QtWidgets.QCheckBox(f"{channel.name} (ID: {chan_id})"); checkbox.setChecked(True); checkbox.stateChanged.connect(self._trigger_plot_update)
            self.channel_checkbox_layout.addWidget(checkbox); self.channel_checkboxes[chan_id] = checkbox
            plot_item = self.graphics_layout_widget.addPlot(row=i, col=0); plot_item.setLabel('left', channel.name, units=channel.units or 'units'); plot_item.showGrid(x=True, y=True, alpha=0.3)
            self.channel_plots[chan_id] = plot_item
            if last_plot_item: plot_item.setXLink(last_plot_item); plot_item.hideAxis('bottom')
            last_plot_item = plot_item
        if last_plot_item: last_plot_item.setLabel('bottom', "Time", units='s'); last_plot_item.showAxis('bottom')

    # --- Action Handlers (Slots) --- START ---

    # --- Combined File/Folder Opening Logic ---
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
        self._reset_ui_and_state_for_new_file(); self.current_recording = None
        try:
            self.current_recording = self.neo_adapter.read_recording(filepath); log.info(f"Loaded {filepath.name}")
            self.max_trials_current_recording = self.current_recording.max_trials if self.current_recording else 0
            self._create_channel_ui(); self._update_metadata_display(); self._update_plot()
            self.statusBar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000)
        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e: log.error(f"Load failed {filepath}: {e}", exc_info=False); QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load file:\n{filepath.name}\n\nError: {e}"); self._clear_metadata_display(); self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        except Exception as e: log.error(f"Unexpected error loading {filepath}: {e}", exc_info=True); QtWidgets.QMessageBox.critical(self, "Unexpected Error", f"Error loading:\n{filepath.name}\n\n{e}"); self._clear_metadata_display(); self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        finally: self._update_ui_state()

    # --- Display Option Changes ---
    def _on_plot_mode_changed(self, index):
        """Handles changes in the plot mode combobox."""
        self.current_plot_mode = index
        log.info(f"Plot mode changed to: {'Overlay+Avg' if index == self.PlotMode.OVERLAY_AVG else 'Cycle Single'}")
        self.current_trial_index = 0 # Reset trial index
        self._update_ui_state()
        self._trigger_plot_update() # Update plot immediately
        self._reset_visible_plot_views() # Also reset view when mode changes

    def _trigger_plot_update(self):
        """Connected to checkboxes and downsample option."""
        if not self.current_recording: return

        # Determine if the sender was a checkbox being turned ON
        sender_checkbox = self.sender()
        channel_id_to_reset = None
        is_checkbox_on_trigger = False
        if isinstance(sender_checkbox, QtWidgets.QCheckBox) and sender_checkbox != self.downsample_checkbox:
             if sender_checkbox.isChecked():
                 is_checkbox_on_trigger = True
                 # Find the channel ID associated with this checkbox
                 for ch_id, cb in self.channel_checkboxes.items():
                     if cb == sender_checkbox: channel_id_to_reset = ch_id; break

        # Update the plot data first
        self._update_plot()

        # Reset view strategically
        if is_checkbox_on_trigger and channel_id_to_reset:
            # Only reset the specific plot if a checkbox was turned ON
             plot_item = self.channel_plots.get(channel_id_to_reset)
             if plot_item and plot_item.isVisible(): # Check if it's actually visible after update
                  log.debug(f"Checkbox toggled ON for {channel_id_to_reset}, resetting its view.")
                  plot_item.getViewBox().autoRange()
        # No automatic reset for downsample change or checkbox OFF, use Reset button.

    # --- Plotting Core Logic ---
    def _clear_plot_data_only(self):
        """Clears only the plotted data lines/text from all existing PlotItems."""
        for chan_id, plot_item in self.channel_plots.items():
            if plot_item is None or plot_item.scene() is None: continue
            plot_item.clear(); plot_item.showGrid(x=True, y=True, alpha=0.3)
        # self.channel_plot_data_items.clear() # Not strictly needed

    def _update_plot(self):
        """Plots data onto the appropriate EXISTING PlotItems based on selections and mode."""
        self._clear_plot_data_only()
        if not self.current_recording or not self.channel_plots:
            log.warning("Update plot: No recording or plot items exist.")
            if not self.graphics_layout_widget.items(): self.graphics_layout_widget.addLabel("Load data", row=0, col=0)
            return
        is_cycle_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        log.debug(f"Updating plot data. Mode: {'Cycle Single' if is_cycle_mode else 'Overlay+Avg'}, Trial: {self.current_trial_index+1}/{self.max_trials_current_recording}")
        trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR + (VisConstants.TRIAL_ALPHA,), width=VisConstants.DEFAULT_PLOT_PEN_WIDTH)
        avg_pen = pg.mkPen(VisConstants.AVERAGE_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1)
        single_trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH)
        any_data_plotted = False
        visible_plots_this_update: List[pg.PlotItem] = [] # Track plots getting data

        for chan_id, plot_item in self.channel_plots.items():
            checkbox = self.channel_checkboxes.get(chan_id); channel = self.current_recording.channels.get(chan_id)
            if checkbox and checkbox.isChecked() and channel:
                plot_item.setVisible(True); plotted_something = False; visible_plots_this_update.append(plot_item)
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
                if plotted_something: any_data_plotted = True
            elif plot_item: plot_item.hide() # Hide plot panel if unchecked

        # Configure bottom axis on the last *currently visible* plot
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

    # --- Metadata Display ---
    def _update_metadata_display(self):
        if self.current_recording: rec = self.current_recording; self.filename_label.setText(rec.source_file.name); self.sampling_rate_label.setText(f"{rec.sampling_rate:.2f} Hz" if rec.sampling_rate else "N/A"); self.duration_label.setText(f"{rec.duration:.3f} s" if rec.duration else "N/A"); num_ch = rec.num_channels; max_tr = self.max_trials_current_recording; self.channels_label.setText(f"{num_ch} ch, {max_tr} trial(s)")
        else: self._clear_metadata_display()
    def _clear_metadata_display(self):
        self.filename_label.setText("N/A"); self.sampling_rate_label.setText("N/A"); self.channels_label.setText("N/A"); self.duration_label.setText("N/A")

    # --- UI State Update ---
    def _update_ui_state(self):
        has_data = self.current_recording is not None; is_folder = len(self.file_list) > 1
        is_cycling_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE; has_multiple_trials = self.max_trials_current_recording > 1
        enable_data_controls = has_data
        self.zoom_in_button.setEnabled(enable_data_controls); self.zoom_out_button.setEnabled(enable_data_controls); self.reset_view_button.setEnabled(enable_data_controls)
        self.plot_mode_combobox.setEnabled(enable_data_controls)
        self.downsample_checkbox.setEnabled(enable_data_controls); self.export_nwb_action.setEnabled(enable_data_controls)
        self.channel_select_group.setEnabled(enable_data_controls)
        enable_trial_cycle = has_data and is_cycling_mode and has_multiple_trials
        self.prev_trial_button.setEnabled(enable_trial_cycle and self.current_trial_index > 0)
        self.next_trial_button.setEnabled(enable_trial_cycle and self.current_trial_index < self.max_trials_current_recording - 1)
        self.trial_index_label.setVisible(has_data and is_cycling_mode)
        self._update_trial_label()
        self.prev_file_button.setVisible(is_folder); self.next_file_button.setVisible(is_folder); self.folder_file_index_label.setVisible(is_folder)
        if is_folder: self.prev_file_button.setEnabled(self.current_file_index > 0); self.next_file_button.setEnabled(self.current_file_index < len(self.file_list) - 1); current_filename = self.file_list[self.current_file_index].name; self.folder_file_index_label.setText(f"File {self.current_file_index + 1}/{len(self.file_list)}: {current_filename}")
        else: self.folder_file_index_label.setText("")

    # --- Trial Label Update ---
    def _update_trial_label(self):
        if (self.current_recording and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0): self.trial_index_label.setText(f"{self.current_trial_index + 1} / {self.max_trials_current_recording}")
        else: self.trial_index_label.setText("N/A")

    # --- Plot Control Slots (Corrected) ---
    def _zoom_in(self):
        visible_plots = [p for p in self.channel_plots.values() if p.isVisible()]
        if visible_plots: visible_plots[0].getViewBox().scaleBy((0.8, 0.8)); log.debug("Zoomed In")
        else: log.debug("Zoom In: No visible plots.")
    def _zoom_out(self):
        visible_plots = [p for p in self.channel_plots.values() if p.isVisible()]
        if visible_plots: visible_plots[0].getViewBox().scaleBy((1.25, 1.25)); log.debug("Zoomed Out")
        else: log.debug("Zoom Out: No visible plots.")
    def _reset_view(self):
        """Resets the view range on all currently visible plots."""
        self._reset_visible_plot_views() # Call helper

    # --- Helper for resetting visible plot views ---
    def _reset_visible_plot_views(self):
        """Helper function to call autoRange on visible plots."""
        log.debug("Resetting view range for visible plots.")
        visible_found = False
        for plot_item in self.channel_plots.values():
             if plot_item.isVisible(): plot_item.getViewBox().autoRange(); visible_found = True
        if visible_found: log.debug("View reset triggered.")
        else: log.debug("No visible plots found to reset view.")

    # --- Trial Navigation Slots (Modified to reset view) ---
    def _next_trial(self):
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0:
            if self.current_trial_index < self.max_trials_current_recording - 1:
                self.current_trial_index += 1; log.debug(f"Next trial: {self.current_trial_index + 1}")
                self._update_plot(); self._reset_visible_plot_views(); self._update_ui_state()
            else: log.debug("Already at last trial.")
    def _prev_trial(self):
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE:
            if self.current_trial_index > 0:
                self.current_trial_index -= 1; log.debug(f"Previous trial: {self.current_trial_index + 1}")
                self._update_plot(); self._reset_visible_plot_views(); self._update_ui_state()
            else: log.debug("Already at first trial.")

    # --- Folder Navigation Slots ---
    def _next_file_folder(self):
        if self.file_list and self.current_file_index < len(self.file_list) - 1: self.current_file_index += 1; self._load_and_display_file(self.file_list[self.current_file_index])
    def _prev_file_folder(self):
        if self.file_list and self.current_file_index > 0: self.current_file_index -= 1; self._load_and_display_file(self.file_list[self.current_file_index])

    # --- NWB Export Slot ---
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

    # --- Close Event ---
    def closeEvent(self, event: QtGui.QCloseEvent):
        log.info("Close event triggered. Shutting down.")
        event.accept()
# --- MainWindow Class --- END ---