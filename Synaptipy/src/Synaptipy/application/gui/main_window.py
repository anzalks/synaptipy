"""
Main Window for the Synaptipy GUI application.
Uses PySide6 for the GUI framework and pyqtgraph for plotting.
"""
# ... (keep existing imports: logging, sys, Path, Optional, np, pg, QtWidgets, QtCore, QtGui) ...
import uuid # Import uuid for default identifier
from datetime import datetime, timezone # Import datetime for NWB

# Import from our package structure
from Synaptipy.core.data_model import Recording, Channel # Channel needed for type hints
from Synaptipy.infrastructure.file_readers import NeoAdapter
# --- Import NWB Exporter ---
from Synaptipy.infrastructure.exporters import NWBExporter
# ---
from Synaptipy.shared import constants
from Synaptipy.shared.error_handling import (FileReadError,
                                             UnsupportedFormatError,
                                             ExportError, # Added ExportError
                                             SynaptipyError) # Base error

log = logging.getLogger(__name__)
# ... (keep pg config options) ...

# --- Simple NWB Metadata Dialog ---
class NwbMetadataDialog(QtWidgets.QDialog):
    """Dialog to collect essential metadata for NWB export."""
    def __init__(self, default_identifier, default_start_time, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NWB Session Metadata")
        self.setModal(True) # Block main window until closed

        self.layout = QtWidgets.QFormLayout(self)

        self.session_description = QtWidgets.QLineEdit("Session description (e.g., experiment type, condition)")
        self.identifier = QtWidgets.QLineEdit(default_identifier)
        self.session_start_time_edit = QtWidgets.QDateTimeEdit(default_start_time)
        self.session_start_time_edit.setCalendarPopup(True)
        self.session_start_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.experimenter = QtWidgets.QLineEdit("")
        self.lab = QtWidgets.QLineEdit("")
        self.institution = QtWidgets.QLineEdit("")
        self.session_id = QtWidgets.QLineEdit("") # Optional

        self.layout.addRow("Description*:", self.session_description)
        self.layout.addRow("Identifier*:", self.identifier)
        self.layout.addRow("Start Time*:", self.session_start_time_edit)
        self.layout.addRow("Experimenter:", self.experimenter)
        self.layout.addRow("Lab:", self.lab)
        self.layout.addRow("Institution:", self.institution)
        self.layout.addRow("Session ID:", self.session_id)
        self.layout.addRow(QtWidgets.QLabel("* Required fields"))

        # Dialog buttons
        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addRow(self.button_box)

    def get_metadata(self) -> Optional[Dict]:
        """Returns the entered metadata as a dictionary if input is valid."""
        desc = self.session_description.text().strip()
        ident = self.identifier.text().strip()
        start_time = self.session_start_time_edit.dateTime().toPython() # Get as Python datetime

        if not desc or not ident:
            QtWidgets.QMessageBox.warning(self, "Input Error", "Session Description and Identifier are required.")
            return None

        return {
            "session_description": desc,
            "identifier": ident,
            "session_start_time": start_time,
            "experimenter": self.experimenter.text().strip() or None, # Use None if empty
            "lab": self.lab.text().strip() or None,
            "institution": self.institution.text().strip() or None,
            "session_id": self.session_id.text().strip() or None,
        }

class MainWindow(QtWidgets.QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        # ... (keep existing __init__ content: title, geometry, data state) ...
        self.nwb_exporter = NWBExporter() # Add exporter instance

        # --- UI Setup ---
        self._setup_ui()
        self._connect_signals()

        # --- Initial State ---
        self._update_ui_state()

    def _setup_ui(self):
        """Create and arrange widgets."""
        # --- Menu Bar ---
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        self.open_file_action = file_menu.addAction("&Open File...")
        self.open_folder_action = file_menu.addAction("Open &Folder...")
        file_menu.addSeparator()
        # --- Add NWB Export Action ---
        self.export_nwb_action = file_menu.addAction("Export to &NWB...")
        self.export_nwb_action.setEnabled(False) # Disabled initially
        # ---
        file_menu.addSeparator()
        self.quit_action = file_menu.addAction("&Quit")


        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QtWidgets.QVBoxLayout(main_widget)

        # --- Top Control Panel ---
        top_panel = QtWidgets.QHBoxLayout()

        # File Group (Use menu actions now, keep buttons maybe?)
        file_group = QtWidgets.QGroupBox("File Operations")
        file_layout = QtWidgets.QHBoxLayout(file_group)
        # self.open_file_button = QtWidgets.QPushButton("Open File") # Replaced by menu
        # self.open_folder_button = QtWidgets.QPushButton("Open Folder") # Replaced by menu
        # file_layout.addWidget(self.open_file_button)
        # file_layout.addWidget(self.open_folder_button)
        # top_panel.addWidget(file_group) # Remove button group if only using menu

        display_group = QtWidgets.QGroupBox("Display Options")
        display_layout = QtWidgets.QVBoxLayout(display_group) # Changed to QVBoxLayout
        self.downsample_checkbox = QtWidgets.QCheckBox("Auto Downsample Plot")
        self.downsample_checkbox.setChecked(True)
        # --- Add Averaging Checkbox ---
        self.plot_average_checkbox = QtWidgets.QCheckBox("Plot Average Only")
        self.plot_average_checkbox.setChecked(False)
        # ---
        display_layout.addWidget(self.downsample_checkbox)
        display_layout.addWidget(self.plot_average_checkbox) # Add average checkbox
        top_panel.addWidget(display_group)

        # --- Metadata Display (Keep as before) ---
        meta_group = QtWidgets.QGroupBox("File Information")
        # ... (metadata labels setup remains the same) ...
        meta_layout = QtWidgets.QFormLayout(meta_group)
        self.filename_label = QtWidgets.QLabel("N/A")
        self.sampling_rate_label = QtWidgets.QLabel("N/A")
        self.channels_label = QtWidgets.QLabel("N/A")
        self.duration_label = QtWidgets.QLabel("N/A")
        self.nwb_start_time_label = QtWidgets.QLabel("N/A") # Add label for NWB start time
        meta_layout.addRow("File:", self.filename_label)
        meta_layout.addRow("Sampling Rate:", self.sampling_rate_label)
        meta_layout.addRow("Duration:", self.duration_label)
        meta_layout.addRow("NWB Start Time:", self.nwb_start_time_label) # Add NWB time
        meta_layout.addRow("Channels:", self.channels_label)

        top_panel.addWidget(meta_group)

        main_layout.addLayout(top_panel)

        # --- Main Plot Area (Keep as before) ---
        plot_layout = QtWidgets.QHBoxLayout()
        self.plot_widget = pg.PlotWidget(name="EphysPlot")
        # ... (plot widget setup remains the same) ...
        self.plot_widget.setLabel('bottom', "Time", units='s')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.enableAutoRange(axis='y', enable=True)
        self.plot_widget.setAutoVisible(y=True)
        self.plot_legend = self.plot_widget.addLegend(offset=(10, 10))

        plot_controls_layout = QtWidgets.QVBoxLayout()
        self.zoom_in_button = QtWidgets.QPushButton("Zoom In")
        self.zoom_out_button = QtWidgets.QPushButton("Zoom Out")
        self.reset_view_button = QtWidgets.QPushButton("Reset View")
        # ... (plot controls setup remains the same) ...
        plot_controls_layout.addWidget(self.zoom_in_button)
        plot_controls_layout.addWidget(self.zoom_out_button)
        plot_controls_layout.addWidget(self.reset_view_button)
        plot_controls_layout.addStretch()

        plot_layout.addWidget(self.plot_widget, stretch=1)
        plot_layout.addLayout(plot_controls_layout)
        main_layout.addLayout(plot_layout, stretch=1)

        # --- Folder Navigation (Keep as before) ---
        nav_layout = QtWidgets.QHBoxLayout()
        # ... (navigation buttons setup remains the same) ...
        self.prev_file_button = QtWidgets.QPushButton("<< Previous File")
        self.next_file_button = QtWidgets.QPushButton("Next File >>")
        self.file_index_label = QtWidgets.QLabel("")
        nav_layout.addWidget(self.prev_file_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.file_index_label)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_file_button)
        main_layout.addLayout(nav_layout)


        # --- Status Bar (Keep as before) ---
        self.statusBar = QtWidgets.QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready. Open a file or folder.")


    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        # File Menu Actions
        self.open_file_action.triggered.connect(self._open_file)
        self.open_folder_action.triggered.connect(self._open_folder)
        self.export_nwb_action.triggered.connect(self._export_to_nwb) # Connect export
        self.quit_action.triggered.connect(self.close) # Connect quit action

        # Display Options
        self.downsample_checkbox.stateChanged.connect(self._trigger_plot_update)
        self.plot_average_checkbox.stateChanged.connect(self._trigger_plot_update) # Connect average checkbox

        # Plot Controls
        self.zoom_in_button.clicked.connect(self._zoom_in)
        self.zoom_out_button.clicked.connect(self._zoom_out)
        self.reset_view_button.clicked.connect(self._reset_view)

        # Navigation
        self.prev_file_button.clicked.connect(self._prev_file)
        self.next_file_button.clicked.connect(self._next_file)


    # --- Action Handlers (Slots) ---

    def _open_file(self):
        """Handle the 'Open File' menu action."""
        # ... (logic remains the same) ...
        filepath_str, selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Electrophysiology File", "", constants.NEO_FILE_FILTER
        )
        if filepath_str:
            filepath = Path(filepath_str)
            self.file_list = [filepath]
            self.current_file_index = 0
            self._load_and_display_file(filepath)
            self._update_ui_state()


    def _open_folder(self):
        """Handle the 'Open Folder' menu action."""
        # ... (logic remains the same) ...
        folder_path_str = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Open Folder Containing Recordings", ""
        )
        if folder_path_str:
            folder_path = Path(folder_path_str)
            # ... (file finding logic remains the same) ...
            supported_files = []
            all_extensions = set()
            for exts in constants.NEO_READER_EXTENSIONS.values():
                all_extensions.update(ext.lstrip('*') for ext in exts)
            for ext in all_extensions:
                if not ext: continue
                supported_files.extend(list(folder_path.glob(f"*{ext}")))
            supported_files = sorted(list(set(supported_files)))

            if not supported_files:
                QtWidgets.QMessageBox.information(self, "No Files Found", f"No supported recording files found in '{folder_path}'.")
                self.file_list = []
                self.current_file_index = -1
            else:
                self.file_list = supported_files
                self.current_file_index = 0
                self._load_and_display_file(self.file_list[0])
            self._update_ui_state()


    def _load_and_display_file(self, filepath: Path):
        """Load data using NeoAdapter and update the plot and metadata."""
        # ... (loading logic remains mostly the same) ...
        self.statusBar.showMessage(f"Loading '{filepath.name}'...")
        try:
            self.current_recording = self.neo_adapter.read_recording(filepath)
            log.info(f"Successfully loaded {filepath.name}")
            self._update_metadata_display()
            self._update_plot() # Plot immediately after load
            self.statusBar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000)
        # ... (error handling remains the same) ...
        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e:
            log.error(f"Failed to load file {filepath}: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load file:\n{filepath.name}\n\nError: {e}")
            self.current_recording = None
            self._clear_plot()
            self._clear_metadata_display()
            self.statusBar.showMessage(f"Error loading {filepath.name}. Ready.", 5000)
        except Exception as e:
             log.error(f"An unexpected error occurred loading {filepath}: {e}", exc_info=True)
             QtWidgets.QMessageBox.critical(self, "Unexpected Error", f"An unexpected error occurred while loading:\n{filepath.name}\n\nError: {e}")
             self.current_recording = None
             self._clear_plot()
             self._clear_metadata_display()
             self.statusBar.showMessage(f"Unexpected error loading {filepath.name}. Ready.", 5000)
        finally:
             self._update_ui_state() # Ensure UI state is correct after load attempt


    def _trigger_plot_update(self):
        """Slot to explicitly update plot when display options change."""
        if self.current_recording:
             self._update_plot()


    def _update_plot(self):
        """Clear and redraw the plot based on current data and options."""
        self._clear_plot()
        if not self.current_recording or not self.current_recording.channels:
            log.warning("Update plot called with no recording data.")
            self.plot_widget.setTitle("No data loaded")
            return

        self.plot_widget.setTitle("") # Clear title
        log.debug(f"Plotting {self.current_recording.num_channels} channels.")

        first_channel_units = "Units"
        has_plotted = False
        plot_average = self.plot_average_checkbox.isChecked() # Check state

        if plot_average:
             log.debug("Plotting averaged traces.")

        for i, channel in enumerate(self.current_recording.channels.values()):
            data = None
            time_vector = None

            # --- Get data based on checkbox state ---
            if plot_average:
                data = channel.get_averaged_data()
                if data is not None:
                     time_vector = channel.get_averaged_time_vector()
                else:
                     log.warning(f"Could not get averaged data for channel '{channel.name}'. Skipping.")
                     continue # Skip plotting this channel if averaging failed
            else:
                # Plot first trial (or implement trial selection later)
                if channel.num_trials > 0:
                    data = channel.get_data(trial_index=0)
                    time_vector = channel.get_time_vector(trial_index=0)
                else:
                    log.warning(f"Channel '{channel.name}' has no trials to plot.")
                    continue
            # -----------------------------------------

            if data is None or time_vector is None:
                log.error(f"Failed to retrieve data or time for channel '{channel.name}'. Skipping.")
                continue

            if not has_plotted: # Set Y label based on first successfully plotted channel
                first_channel_units = channel.units if channel.units else "Unknown Units"
                self.plot_widget.setLabel('left', "Amplitude", units=first_channel_units)

            color = constants.PLOT_COLORS[i % len(constants.PLOT_COLORS)]
            pen = pg.mkPen(color=color, width=constants.DEFAULT_PLOT_PEN_WIDTH)

            # Add legend entry name
            legend_name = f"{channel.name} (Avg)" if plot_average else f"{channel.name} (Tr 0)"

            plot_item = self.plot_widget.plot(time_vector, data, pen=pen, name=legend_name)
            log.debug(f"Added plot for Channel: {channel.name}, Mode: {'Average' if plot_average else 'Trial 0'}, Samples: {len(data)}")
            has_plotted = True

            # Apply downsampling options (same as before)
            enable_ds = self.downsample_checkbox.isChecked()
            plot_item.opts['autoDownsample'] = enable_ds
            if enable_ds:
                 plot_item.opts['autoDownsampleThreshold'] = constants.DOWNSAMPLING_THRESHOLD

        if not has_plotted:
             self.plot_widget.setTitle("No plottable data found for current settings")
        # Optionally reset view after plot update?
        # self._reset_view()


    def _clear_plot(self):
        """Remove all items from the plot and legend."""
        # ... (logic remains the same) ...
        log.debug("Clearing plot widget.")
        for item in self.plot_widget.listDataItems():
            self.plot_widget.removeItem(item)
        if self.plot_legend:
             self.plot_widget.removeItem(self.plot_legend)
             self.plot_legend = self.plot_widget.addLegend(offset=(10, 10))
        self.plot_widget.setTitle("")
        self.plot_widget.setLabel('left', "Amplitude")


    def _update_metadata_display(self):
        """Update labels with info from self.current_recording."""
        if self.current_recording:
            rec = self.current_recording
            self.filename_label.setText(rec.source_file.name)
            self.sampling_rate_label.setText(f"{rec.sampling_rate:.2f} Hz" if rec.sampling_rate else "N/A")
            self.duration_label.setText(f"{rec.duration:.3f} s" if rec.duration else "N/A")
            # Display NWB start time if available
            if rec.session_start_time_dt:
                 self.nwb_start_time_label.setText(rec.session_start_time_dt.strftime("%Y-%m-%d %H:%M:%S %Z"))
            else:
                 self.nwb_start_time_label.setText("Not extracted")

            ch_names = ", ".join(rec.channel_names)
            num_ch = rec.num_channels
            max_tr = rec.max_trials
            self.channels_label.setText(f"{num_ch} ch, {max_tr} trial(s): ({ch_names})")
        else:
            self._clear_metadata_display()


    def _clear_metadata_display(self):
        """Reset metadata labels to 'N/A'."""
        # ... (reset logic remains the same) ...
        self.filename_label.setText("N/A")
        self.sampling_rate_label.setText("N/A")
        self.channels_label.setText("N/A")
        self.duration_label.setText("N/A")
        self.nwb_start_time_label.setText("N/A") # Reset NWB time label


    def _update_ui_state(self):
        """Enable/disable widgets based on the current state."""
        has_data = self.current_recording is not None
        is_folder = len(self.file_list) > 1

        # Plot controls
        self.zoom_in_button.setEnabled(has_data)
        self.zoom_out_button.setEnabled(has_data)
        self.reset_view_button.setEnabled(has_data)
        self.plot_average_checkbox.setEnabled(has_data) # Enable avg checkbox if data loaded
        self.downsample_checkbox.setEnabled(has_data)

        # Export action
        self.export_nwb_action.setEnabled(has_data) # Enable export if data loaded

        # Navigation controls (visibility and enabled state)
        self.prev_file_button.setVisible(is_folder)
        self.next_file_button.setVisible(is_folder)
        self.file_index_label.setVisible(is_folder)
        if is_folder:
             self.prev_file_button.setEnabled(self.current_file_index > 0)
             self.next_file_button.setEnabled(self.current_file_index < len(self.file_list) - 1)
             current_filename = self.file_list[self.current_file_index].name
             self.file_index_label.setText(f"File {self.current_file_index + 1} / {len(self.file_list)}: {current_filename}")
        else:
            self.file_index_label.setText("")


    # --- Plot Control Slots (Keep _zoom_in, _zoom_out, _reset_view as before) ---
    def _zoom_in(self):
        if not self.current_recording: return
        self.plot_widget.getViewBox().scaleBy((0.8, 0.8))

    def _zoom_out(self):
        if not self.current_recording: return
        self.plot_widget.getViewBox().scaleBy((1.25, 1.25))

    def _reset_view(self):
        if not self.current_recording: return
        self.plot_widget.getViewBox().autoRange()

    # --- Folder Navigation Slots (Keep _next_file, _prev_file as before) ---
    def _next_file(self):
        if self.file_list and self.current_file_index < len(self.file_list) - 1:
            self.current_file_index += 1
            filepath = self.file_list[self.current_file_index]
            self._load_and_display_file(filepath)
            # self._update_ui_state() # Called within _load_and_display_file's finally block

    def _prev_file(self):
        if self.file_list and self.current_file_index > 0:
            self.current_file_index -= 1
            filepath = self.file_list[self.current_file_index]
            self._load_and_display_file(filepath)
            # self._update_ui_state() # Called within _load_and_display_file's finally block


    # --- NWB Export Slot ---
    def _export_to_nwb(self):
        """Handles the 'Export to NWB' action."""
        if not self.current_recording:
            QtWidgets.QMessageBox.warning(self, "Export Error", "No recording data loaded to export.")
            return

        # 1. Get Output Filename
        default_filename = self.current_recording.source_file.with_suffix(".nwb").name
        output_path_str, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Recording as NWB File",
            default_filename, # Suggest filename based on source
            "NWB Files (*.nwb)"
        )

        if not output_path_str:
            self.statusBar.showMessage("NWB export cancelled.", 3000)
            return # User cancelled

        output_path = Path(output_path_str)

        # 2. Get Metadata via Dialog
        # Prepare defaults for dialog
        default_id = str(uuid.uuid4())
        default_time = self.current_recording.session_start_time_dt or datetime.now()
        if default_time.tzinfo is None: # Ensure default time is timezone-aware for dialog
             try:
                 import tzlocal
                 default_time = default_time.replace(tzinfo=tzlocal.get_localzone())
             except ImportError:
                  default_time = default_time.replace(tzinfo=timezone.utc) # Fallback to UTC

        dialog = NwbMetadataDialog(default_id, default_time, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            session_metadata = dialog.get_metadata()
            if session_metadata is None: # Invalid input in dialog
                return # Error message already shown by dialog
        else:
            self.statusBar.showMessage("NWB export cancelled (metadata input).", 3000)
            return # User cancelled dialog

        # 3. Perform Export (Consider Threading for large files later)
        self.statusBar.showMessage(f"Exporting to {output_path.name}...")
        QtWidgets.QApplication.processEvents() # Update GUI briefly

        try:
            self.nwb_exporter.export(self.current_recording, output_path, session_metadata)
            log.info(f"Successfully exported recording to {output_path}")
            self.statusBar.showMessage(f"Export successful: {output_path.name}", 5000)
            QtWidgets.QMessageBox.information(self, "Export Successful", f"Recording saved to:\n{output_path}")

        except (ValueError, ExportError, SynaptipyError) as e:
            log.error(f"NWB Export failed: {e}", exc_info=True)
            self.statusBar.showMessage(f"NWB Export failed: {e}", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export file:\n{e}")
        except Exception as e: # Catch unexpected errors
             log.error(f"Unexpected error during NWB Export: {e}", exc_info=True)
             self.statusBar.showMessage(f"Unexpected NWB Export error.", 5000)
             QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"An unexpected error occurred during export:\n{e}")


    def closeEvent(self, event: QtGui.QCloseEvent):
        """Handle the window closing event."""
        # ... (logic remains the same) ...
        log.info("Close event triggered. Shutting down.")
        event.accept()