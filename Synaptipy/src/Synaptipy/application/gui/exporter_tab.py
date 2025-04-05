# src/Synaptipy/application/gui/exporter_tab.py
# -*- coding: utf-8 -*-
"""
Exporter Tab widget for the Synaptipy GUI. Provides UI for exporting data,
using sub-tabs for different formats (e.g., NWB, CSV).
"""
import logging
import os
from pathlib import Path
from typing import Optional
import uuid
from datetime import datetime, timezone

import numpy as np # Needed for CSV export
from PySide6 import QtCore, QtGui, QtWidgets

# Assuming these are correctly structured now
from .dummy_classes import Recording, NWBExporter, SynaptipyError, ExportError, Channel # Import Channel
from .explorer_tab import ExplorerTab # Need reference to get recording
from .nwb_dialog import NwbMetadataDialog # Need the metadata dialog

try:
    import tzlocal
except ImportError:
    tzlocal = None

log = logging.getLogger('Synaptipy.application.gui.exporter_tab')

class ExporterTab(QtWidgets.QWidget):
    """
    Main Exporter QWidget containing a QTabWidget for different export formats.
    """

    def __init__(self,
                 explorer_tab_ref: ExplorerTab,
                 nwb_exporter_ref: NWBExporter,
                 settings_ref: QtCore.QSettings,
                 status_bar_ref: QtWidgets.QStatusBar,
                 parent=None):
        super().__init__(parent)
        log.debug("Initializing ExporterTab")

        # Store references from MainWindow
        self._explorer_tab = explorer_tab_ref
        self._nwb_exporter = nwb_exporter_ref
        self._settings = settings_ref
        self._status_bar = status_bar_ref

        # --- UI Widget References ---
        self.source_file_label: Optional[QtWidgets.QLabel] = None
        # NWB Sub-tab elements
        self.nwb_output_path_edit: Optional[QtWidgets.QLineEdit] = None
        self.nwb_browse_button: Optional[QtWidgets.QPushButton] = None
        self.nwb_export_button: Optional[QtWidgets.QPushButton] = None
        # CSV Sub-tab elements
        self.csv_output_dir_edit: Optional[QtWidgets.QLineEdit] = None
        self.csv_browse_dir_button: Optional[QtWidgets.QPushButton] = None
        self.csv_export_button: Optional[QtWidgets.QPushButton] = None
        # Main sub-tab widget
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None

        self._setup_ui()
        self._connect_signals()
        self.update_state() # Set initial state

    def _setup_ui(self):
        """Create the main layout and the sub-tab structure."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Source Data Group ---
        source_group = QtWidgets.QGroupBox("Data Source (from Explorer Tab)")
        source_layout = QtWidgets.QFormLayout(source_group)
        self.source_file_label = QtWidgets.QLabel("<i>None loaded</i>")
        self.source_file_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_file_label.setWordWrap(True)
        source_layout.addRow("Current File:", self.source_file_label)
        main_layout.addWidget(source_group)

        # --- Sub-Tab Widget ---
        self.sub_tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.sub_tab_widget)

        # --- Create and Add Sub-Tabs ---
        nwb_sub_tab_widget = self._create_nwb_sub_tab()
        self.sub_tab_widget.addTab(nwb_sub_tab_widget, "Export to NWB")

        csv_sub_tab_widget = self._create_csv_sub_tab() # Create CSV tab
        self.sub_tab_widget.addTab(csv_sub_tab_widget, "Export to CSV") # Add CSV tab

        main_layout.addStretch()
        self.setLayout(main_layout)
        log.debug("ExporterTab UI setup complete with NWB and CSV sub-tabs.")

    def _create_nwb_sub_tab(self) -> QtWidgets.QWidget:
        """Creates the QWidget containing the UI for the NWB export sub-tab."""
        nwb_widget = QtWidgets.QWidget()
        nwb_layout = QtWidgets.QVBoxLayout(nwb_widget)
        nwb_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        nwb_group = QtWidgets.QGroupBox("NWB Export Options")
        nwb_group_layout = QtWidgets.QVBoxLayout(nwb_group)
        output_layout = QtWidgets.QHBoxLayout()
        output_layout.addWidget(QtWidgets.QLabel("Output File:"))
        self.nwb_output_path_edit = QtWidgets.QLineEdit()
        self.nwb_output_path_edit.setPlaceholderText("Select NWB output file path...")
        self.nwb_output_path_edit.setClearButtonEnabled(True)
        output_layout.addWidget(self.nwb_output_path_edit, stretch=1)
        self.nwb_browse_button = QtWidgets.QPushButton("Browse...")
        self.nwb_browse_button.setToolTip("Choose where to save the NWB file")
        output_layout.addWidget(self.nwb_browse_button)
        nwb_group_layout.addLayout(output_layout)
        self.nwb_export_button = QtWidgets.QPushButton("Export to NWB...")
        self.nwb_export_button.setIcon(QtGui.QIcon.fromTheme("document-save"))
        self.nwb_export_button.setToolTip("Start the NWB export process")
        self.nwb_export_button.setEnabled(False)
        nwb_group_layout.addWidget(self.nwb_export_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        nwb_layout.addWidget(nwb_group)
        nwb_layout.addStretch()
        nwb_widget.setLayout(nwb_layout)
        return nwb_widget

    def _create_csv_sub_tab(self) -> QtWidgets.QWidget:
        """Creates the QWidget containing the UI for the CSV export sub-tab."""
        csv_widget = QtWidgets.QWidget()
        csv_layout = QtWidgets.QVBoxLayout(csv_widget)
        csv_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        csv_group = QtWidgets.QGroupBox("CSV Export Options")
        csv_group_layout = QtWidgets.QVBoxLayout(csv_group)

        # Output Directory Selection
        dir_layout = QtWidgets.QHBoxLayout()
        dir_layout.addWidget(QtWidgets.QLabel("Output Directory:"))
        self.csv_output_dir_edit = QtWidgets.QLineEdit()
        self.csv_output_dir_edit.setPlaceholderText("Select directory to save CSV files...")
        self.csv_output_dir_edit.setClearButtonEnabled(True)
        dir_layout.addWidget(self.csv_output_dir_edit, stretch=1)
        self.csv_browse_dir_button = QtWidgets.QPushButton("Browse...")
        self.csv_browse_dir_button.setToolTip("Choose directory for CSV output")
        dir_layout.addWidget(self.csv_browse_dir_button)
        csv_group_layout.addLayout(dir_layout)

        # --- Placeholder for future CSV options ---
        # options_layout = QtWidgets.QFormLayout()
        # self.csv_format_combo = QtWidgets.QComboBox()
        # self.csv_format_combo.addItems(["One file per Channel/Trial", "One file per Channel (Trials as columns)"])
        # options_layout.addRow("File Structure:", self.csv_format_combo)
        # self.csv_delimiter_edit = QtWidgets.QLineEdit(",")
        # options_layout.addRow("Delimiter:", self.csv_delimiter_edit)
        # csv_group_layout.addLayout(options_layout)
        # --- End Placeholder ---

        # Export Action Button
        self.csv_export_button = QtWidgets.QPushButton("Export to CSV(s)")
        self.csv_export_button.setIcon(QtGui.QIcon.fromTheme("document-save")) # Optional icon
        self.csv_export_button.setToolTip("Export data as CSV files (one per channel/trial)")
        self.csv_export_button.setEnabled(False) # Disabled initially
        csv_group_layout.addWidget(self.csv_export_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        csv_layout.addWidget(csv_group)
        csv_layout.addStretch()
        csv_widget.setLayout(csv_layout)
        return csv_widget

    def _connect_signals(self):
        """Connect signals for widgets within the Exporter Tab and its sub-tabs."""
        # NWB signals
        if self.nwb_browse_button: self.nwb_browse_button.clicked.connect(self._browse_nwb_output_path)
        if self.nwb_export_button: self.nwb_export_button.clicked.connect(self._do_export_nwb)
        if self.nwb_output_path_edit: self.nwb_output_path_edit.textChanged.connect(self.update_state)

        # CSV signals
        if self.csv_browse_dir_button: self.csv_browse_dir_button.clicked.connect(self._browse_csv_output_dir)
        if self.csv_export_button: self.csv_export_button.clicked.connect(self._do_export_csv)
        if self.csv_output_dir_edit: self.csv_output_dir_edit.textChanged.connect(self.update_state)

    # --- Public Method for MainWindow to Call ---
    def update_state(self):
        """
        Updates the enabled state of UI elements based on data availability
        and path/directory selection. Also updates source label.
        """
        current_recording = self._explorer_tab.get_current_recording()
        has_data = current_recording is not None

        # Update Source Label
        if self.source_file_label:
            if has_data:
                self.source_file_label.setText(f"<i>{current_recording.source_file.name}</i>")
                self.source_file_label.setToolTip(str(current_recording.source_file))
            else:
                self.source_file_label.setText("<i>None loaded</i>")
                self.source_file_label.setToolTip("")

        # Update NWB Export Button
        nwb_output_path_ok = bool(self.nwb_output_path_edit.text().strip()) if self.nwb_output_path_edit else False
        if self.nwb_export_button:
            self.nwb_export_button.setEnabled(has_data and nwb_output_path_ok)

        # Update CSV Export Button
        csv_output_dir_ok = bool(self.csv_output_dir_edit.text().strip()) if self.csv_output_dir_edit else False
        if self.csv_export_button:
            self.csv_export_button.setEnabled(has_data and csv_output_dir_ok)

    # --- Handlers ---

    # NWB Handlers
    def _browse_nwb_output_path(self):
        current_recording = self._explorer_tab.get_current_recording()
        default_dir = self._settings.value("lastExportDirectory", "", type=str)
        default_filename = "exported_data.nwb"
        if current_recording:
            default_filename = current_recording.source_file.with_suffix(".nwb").name
            if not default_dir: default_dir = str(current_recording.source_file.parent)
        default_save_path = os.path.join(default_dir, default_filename)
        output_filepath_str, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save NWB File", dir=default_save_path, filter="NWB Files (*.nwb)")
        if output_filepath_str:
            output_filepath = Path(output_filepath_str)
            self.nwb_output_path_edit.setText(str(output_filepath))
            self._settings.setValue("lastExportDirectory", str(output_filepath.parent))
            log.info(f"Output NWB path selected: {output_filepath}")
            self.update_state()

    def _do_export_nwb(self):
        # --- NWB Export logic remains the same as previous correct version ---
        log.debug("NWB Export button clicked.")
        current_recording = self._explorer_tab.get_current_recording()
        output_path_str = self.nwb_output_path_edit.text().strip()
        if not current_recording: log.warning("Export NWB ignored: No data."); QtWidgets.QMessageBox.warning(self, "Export Error", "No data loaded."); self.update_state(); return
        if not output_path_str: log.warning("Export NWB ignored: No output path."); QtWidgets.QMessageBox.warning(self, "Export Error", "Select output file path."); self.update_state(); return
        output_filepath = Path(output_path_str)
        try: output_filepath.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e: log.error(f"Failed create output dir {output_filepath.parent}: {e}"); QtWidgets.QMessageBox.critical(self, "Directory Error", f"Could not create dir:\n{output_filepath.parent}\n\nError: {e}"); return

        log.info(f"Preparing NWB metadata for: {current_recording.source_file.name}")
        default_identifier = str(uuid.uuid4())
        default_start_time_naive = getattr(current_recording, 'session_start_time_dt', datetime.now())
        aware_start_time = timezone.utc
        if default_start_time_naive.tzinfo is None:
            log.warning("Rec time naive. Assuming local/UTC.");
            if tzlocal:
                try: aware_start_time = default_start_time_naive.replace(tzinfo=tzlocal.get_localzone())
                except Exception as e: log.warning(f"tzlocal failed: {e}. Using UTC."); aware_start_time = default_start_time_naive.replace(tzinfo=timezone.utc)
            else: aware_start_time = default_start_time_naive.replace(tzinfo=timezone.utc)
        else: aware_start_time = default_start_time_naive

        dialog = NwbMetadataDialog(default_identifier, aware_start_time, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            nwb_metadata = dialog.get_metadata()
            if nwb_metadata is None: log.error("Metadata dialog None."); self._status_bar.showMessage("Metadata validation failed.", 4000); return
        else: log.info("NWB export cancelled."); self._status_bar.showMessage("NWB export cancelled.", 3000); return

        self.nwb_export_button.setEnabled(False)
        self._status_bar.showMessage(f"Exporting NWB to '{output_filepath.name}'...", 0)
        QtWidgets.QApplication.processEvents()
        try:
            self._nwb_exporter.export(current_recording, output_filepath, nwb_metadata)
            log.info(f"Success export NWB: {output_filepath}")
            self._status_bar.showMessage(f"Export successful: {output_filepath.name}", 5000)
            QtWidgets.QMessageBox.information(self, "Export Successful", f"Data saved to:\n{output_filepath}")
        except (ValueError, ExportError, SynaptipyError) as e:
            log.error(f"NWB Export failed: {e}", exc_info=False)
            self._status_bar.showMessage(f"NWB Export failed: {e}", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export NWB:\n{e}")
        except Exception as e:
            log.error(f"Unexpected NWB Export error: {e}", exc_info=True)
            self._status_bar.showMessage("Unexpected NWB Export error.", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Unexpected error during export:\n{e}")
        finally:
            self.update_state()

    # --- NEW CSV Handlers ---
    def _browse_csv_output_dir(self):
        """Opens a directory dialog to select the CSV output folder."""
        # Use lastExportDirectory setting, or source file dir, or home dir
        current_recording = self._explorer_tab.get_current_recording()
        last_dir = self._settings.value("lastExportDirectory", "", type=str)
        if not last_dir and current_recording:
            last_dir = str(current_recording.source_file.parent)
        if not last_dir:
            last_dir = str(Path.home()) # Fallback to home

        dir_path_str = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory for CSV Files", dir=last_dir
        )

        if dir_path_str:
            dir_path = Path(dir_path_str)
            self.csv_output_dir_edit.setText(str(dir_path))
            # Optionally save this directory setting separately if needed
            # self._settings.setValue("lastCsvExportDirectory", str(dir_path))
            log.info(f"Output CSV directory selected: {dir_path}")
            self.update_state()

    def _do_export_csv(self):
        """Exports loaded data to CSV files (one per channel/trial)."""
        log.debug("CSV Export button clicked.")
        current_recording = self._explorer_tab.get_current_recording()
        output_dir_str = self.csv_output_dir_edit.text().strip()

        # --- Validation ---
        if not current_recording:
            log.warning("Export CSV ignored: No data."); QtWidgets.QMessageBox.warning(self, "Export Error", "No data loaded."); self.update_state(); return
        if not output_dir_str:
            log.warning("Export CSV ignored: No output directory."); QtWidgets.QMessageBox.warning(self, "Export Error", "Select output directory."); self.update_state(); return

        output_dir = Path(output_dir_str)
        try:
            output_dir.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        except OSError as e:
            log.error(f"Failed create output dir {output_dir}: {e}"); QtWidgets.QMessageBox.critical(self, "Directory Error", f"Could not create directory:\n{output_dir}\n\nError: {e}"); return

        # --- Perform Export ---
        self.csv_export_button.setEnabled(False)
        self._status_bar.showMessage(f"Exporting CSV files to '{output_dir.name}'...", 0)
        QtWidgets.QApplication.processEvents()

        export_counter = 0
        export_errors = 0
        source_stem = current_recording.source_file.stem # Base name without extension

        try:
            for chan_id, channel in current_recording.channels.items():
                if not isinstance(channel, Channel) or not channel.data_trials:
                    log.warning(f"Skipping CSV export for invalid channel: {chan_id}")
                    continue

                chan_name_safe = channel.name.replace(" ", "_").replace("/", "-") # Sanitize name for filename

                for trial_idx, trial_data in enumerate(channel.data_trials):
                    if not isinstance(trial_data, np.ndarray) or trial_data.ndim != 1 or trial_data.size == 0:
                        log.warning(f"Skipping invalid trial data for CSV: Ch='{channel_name_safe}', Trial={trial_idx}")
                        continue

                    # Get relative time vector for this trial
                    time_vec = channel.get_relative_time_vector(trial_idx)
                    if time_vec is None:
                        log.error(f"Could not get time vector for CSV: Ch='{channel_name_safe}', Trial={trial_idx}. Skipping trial.")
                        export_errors += 1
                        continue

                    # Prepare data for saving (time, data columns)
                    if time_vec.shape != trial_data.shape:
                         log.error(f"Time ({time_vec.shape}) and data ({trial_data.shape}) shape mismatch for CSV: Ch='{channel_name_safe}', Trial={trial_idx}. Skipping.")
                         export_errors += 1
                         continue
                    data_to_save = np.column_stack((time_vec, trial_data))

                    # Construct filename
                    csv_filename = f"{source_stem}_chan_{chan_id}_trial_{trial_idx:03d}.csv"
                    csv_filepath = output_dir / csv_filename

                    # Define header
                    header = f"Time (s),Data ({channel.units if channel.units else 'unknown'})"

                    # Save using numpy.savetxt
                    try:
                        log.debug(f"Saving CSV: {csv_filepath}")
                        np.savetxt(csv_filepath, data_to_save, delimiter=",", header=header, comments='') # comments='' prevents '#' before header
                        export_counter += 1
                    except Exception as e_save:
                        log.error(f"Failed to save CSV file '{csv_filepath}': {e_save}", exc_info=True)
                        export_errors += 1

                    QtWidgets.QApplication.processEvents() # Keep UI responsive during loop

            # --- Report Outcome ---
            if export_errors > 0:
                msg = f"CSV export completed with {export_errors} errors. {export_counter} files saved to '{output_dir.name}'."
                log.warning(msg)
                self._status_bar.showMessage(msg, 8000)
                QtWidgets.QMessageBox.warning(self, "CSV Export Warning", f"{msg}\n\nCheck logs for details.")
            elif export_counter > 0:
                msg = f"Successfully exported {export_counter} CSV files to '{output_dir.name}'."
                log.info(msg)
                self._status_bar.showMessage(msg, 5000)
                QtWidgets.QMessageBox.information(self, "CSV Export Successful", msg)
            else:
                msg = "No valid data found to export to CSV."
                log.warning(msg)
                self._status_bar.showMessage(msg, 5000)
                QtWidgets.QMessageBox.information(self, "CSV Export Info", msg)

        except Exception as e:
            # Catch unexpected errors during the main loop
            log.error(f"Unexpected error during CSV export: {e}", exc_info=True)
            self._status_bar.showMessage("Unexpected CSV Export error occurred.", 5000)
            QtWidgets.QMessageBox.critical(self, "CSV Export Error", f"An unexpected error occurred:\n{e}")
            export_errors +=1 # Indicate failure
        finally:
            self.update_state() # Re-enable buttons etc.