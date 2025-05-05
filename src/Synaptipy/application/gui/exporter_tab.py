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
import csv

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
        
        analysis_results_tab_widget = self._create_analysis_results_sub_tab() # Create Analysis Results export tab
        self.sub_tab_widget.addTab(analysis_results_tab_widget, "Export Analysis Results") # Add Analysis Results tab

        main_layout.addStretch()
        self.setLayout(main_layout)
        log.debug("ExporterTab UI setup complete with NWB, CSV, and Analysis Results sub-tabs.")

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

    def _create_analysis_results_sub_tab(self) -> QtWidgets.QWidget:
        """Creates the QWidget containing the UI for exporting analysis results to CSV."""
        tab_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab_widget)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        
        # Group for output file selection
        file_group = QtWidgets.QGroupBox("Output CSV File")
        file_layout = QtWidgets.QHBoxLayout(file_group)
        
        self.analysis_results_path_edit = QtWidgets.QLineEdit()
        self.analysis_results_path_edit.setPlaceholderText("Select CSV file path for analysis results...")
        self.analysis_results_path_edit.setClearButtonEnabled(True)
        file_layout.addWidget(self.analysis_results_path_edit, stretch=1)
        
        self.analysis_results_browse_button = QtWidgets.QPushButton("Browse...")
        self.analysis_results_browse_button.setToolTip("Choose where to save the analysis results CSV file")
        file_layout.addWidget(self.analysis_results_browse_button)
        
        layout.addWidget(file_group)
        
        # Group for results table and selection
        results_group = QtWidgets.QGroupBox("Available Analysis Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        
        # Button row for refresh and select/deselect all
        button_layout = QtWidgets.QHBoxLayout()
        
        self.analysis_results_refresh_button = QtWidgets.QPushButton("Refresh Results")
        self.analysis_results_refresh_button.setToolTip("Refresh the list of available analysis results")
        button_layout.addWidget(self.analysis_results_refresh_button)
        
        button_layout.addStretch(1)
        
        self.analysis_results_select_all_button = QtWidgets.QPushButton("Select All")
        self.analysis_results_select_all_button.setToolTip("Select all analysis results")
        button_layout.addWidget(self.analysis_results_select_all_button)
        
        self.analysis_results_deselect_all_button = QtWidgets.QPushButton("Deselect All")
        self.analysis_results_deselect_all_button.setToolTip("Deselect all analysis results")
        button_layout.addWidget(self.analysis_results_deselect_all_button)
        
        results_layout.addLayout(button_layout)
        
        # Table for showing results
        self.analysis_results_table = QtWidgets.QTableWidget()
        self.analysis_results_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.analysis_results_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.analysis_results_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.analysis_results_table.setColumnCount(6)
        self.analysis_results_table.setHorizontalHeaderLabels([
            "Analysis Type", "Source File", "Data Source", "Value", "Timestamp", "Details"
        ])
        self.analysis_results_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.analysis_results_table.horizontalHeader().setStretchLastSection(True)
        self.analysis_results_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.analysis_results_table)
        
        layout.addWidget(results_group, stretch=1)
        
        # Export button
        export_layout = QtWidgets.QHBoxLayout()
        export_layout.addStretch(1)
        
        self.analysis_results_export_button = QtWidgets.QPushButton("Export Selected Results to CSV")
        self.analysis_results_export_button.setIcon(QtGui.QIcon.fromTheme("document-save"))
        self.analysis_results_export_button.setToolTip("Export the selected analysis results to a CSV file")
        self.analysis_results_export_button.setEnabled(False)  # Disabled initially
        export_layout.addWidget(self.analysis_results_export_button)
        
        export_layout.addStretch(1)
        layout.addLayout(export_layout)
        
        # Call refresh to populate the table initially
        QtCore.QTimer.singleShot(100, self._refresh_analysis_results)
        
        return tab_widget

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
        
        # Analysis Results export signals
        if self.analysis_results_browse_button: self.analysis_results_browse_button.clicked.connect(self._browse_analysis_results_output_path)
        if self.analysis_results_export_button: self.analysis_results_export_button.clicked.connect(self._do_export_analysis_results)
        if self.analysis_results_path_edit: self.analysis_results_path_edit.textChanged.connect(self.update_state)
        if self.analysis_results_refresh_button: self.analysis_results_refresh_button.clicked.connect(self._refresh_analysis_results)
        if self.analysis_results_select_all_button: self.analysis_results_select_all_button.clicked.connect(self._select_all_results)
        if self.analysis_results_deselect_all_button: self.analysis_results_deselect_all_button.clicked.connect(self._deselect_all_results)

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
            
        # Update Analysis Results Export Button
        analysis_results_path_ok = bool(self.analysis_results_path_edit.text().strip()) if self.analysis_results_path_edit else False
        has_selected_results = (hasattr(self, 'analysis_results_table') and 
                               self.analysis_results_table and 
                               len(self._get_selected_results_indices()) > 0)
        if self.analysis_results_export_button:
            self.analysis_results_export_button.setEnabled(analysis_results_path_ok and has_selected_results)

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

    # Add methods for the analysis results export functionality
    def _browse_analysis_results_output_path(self):
        """Shows file dialog to select CSV output path for analysis results."""
        default_dir = self._settings.value("lastExportDirectory", "", type=str)
        default_filename = "analysis_results.csv"
        default_path = os.path.join(default_dir, default_filename)
        
        filepath_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Analysis Results CSV File", 
            dir=default_path, 
            filter="CSV Files (*.csv)"
        )
        
        if filepath_str:
            # Ensure the file has .csv extension
            if not filepath_str.lower().endswith('.csv'):
                filepath_str += '.csv'
                
            self.analysis_results_path_edit.setText(filepath_str)
            self._settings.setValue("lastExportDirectory", str(Path(filepath_str).parent))
            log.info(f"Selected analysis results output path: {filepath_str}")
            self.update_state()
    
    def _refresh_analysis_results(self):
        """Refreshes the table of available analysis results."""
        # Access the main window to get the saved analysis results
        main_window = self.window()
        
        if not hasattr(main_window, 'saved_analysis_results'):
            log.warning("MainWindow does not have saved_analysis_results attribute")
            return
            
        results = main_window.saved_analysis_results
        log.debug(f"Refreshing analysis results table with {len(results)} results")
        
        # Clear and setup the table
        self.analysis_results_table.setRowCount(0)
        self.analysis_results_table.setRowCount(len(results))
        
        for i, result in enumerate(results):
            # Extract key information for columns
            analysis_type = result.get('analysis_type', 'Unknown')
            source_file = result.get('source_file_name', 'Unknown')
            
            # Determine data source string
            data_source_type = result.get('data_source_used', 'Unknown')
            trial_index = result.get('trial_index_used')
            if data_source_type == "Trial" and trial_index is not None:
                data_source = f"Trial {trial_index + 1}"
            else:
                data_source = data_source_type
                
            # Determine value string based on analysis type
            value_str = "N/A"
            
            try:
                if analysis_type == "Input Resistance" or analysis_type == "Input Resistance/Conductance":
                    # Try different possible keys for the resistance value
                    for key in ['Input Resistance (kOhm)', 'Rin (MΩ)']:
                        value = result.get(key)
                        if value is not None:
                            if isinstance(value, (int, float)) or hasattr(value, 'item'):
                                try:
                                    value_float = float(value if isinstance(value, (int, float)) else value.item())
                                    if key == 'Input Resistance (kOhm)':
                                        value_str = f"{value_float:.2f} kOhm"
                                    else:
                                        value_str = f"{value_float:.2f} MΩ"
                                    break
                                except (ValueError, TypeError, AttributeError):
                                    continue
                    
                elif analysis_type == "Baseline Analysis":
                    # Extract baseline mean and SD
                    mean = result.get('baseline_mean')
                    sd = result.get('baseline_sd')
                    units = result.get('baseline_units', '')
                    
                    # Extract the calculation method for display in the value string
                    method = result.get('calculation_method', '')
                    method_display = ""
                    if method:
                        if method.startswith("auto_"):
                            method_display = " (Auto)"
                        elif method.startswith("manual_"):
                            method_display = " (Manual)"
                        elif method.startswith("interactive_"):
                            method_display = " (Interactive)"
                    
                    if mean is not None and sd is not None:
                        try:
                            mean_float = float(mean if isinstance(mean, (int, float)) else mean.item() if hasattr(mean, 'item') else mean)
                            sd_float = float(sd if isinstance(sd, (int, float)) else sd.item() if hasattr(sd, 'item') else sd)
                            value_str = f"{mean_float:.3f} ± {sd_float:.3f} {units}{method_display}"
                        except (ValueError, TypeError, AttributeError):
                            value_str = f"Mean: {mean}, SD: {sd} {units}{method_display}"
                    
                elif analysis_type == "Spike Detection (Threshold)":
                    # Extract spike count
                    spike_count = result.get('spike_count')
                    if spike_count is not None:
                        try:
                            count = int(spike_count if isinstance(spike_count, (int, float)) else 
                                      spike_count.item() if hasattr(spike_count, 'item') else spike_count)
                            value_str = f"{count} spikes"
                            
                            # Add frequency if available
                            rate = result.get('average_firing_rate_hz')
                            if rate is not None:
                                try:
                                    rate_float = float(rate if isinstance(rate, (int, float)) else 
                                                    rate.item() if hasattr(rate, 'item') else rate)
                                    value_str += f" ({rate_float:.2f} Hz)"
                                except (ValueError, TypeError, AttributeError):
                                    pass
                        except (ValueError, TypeError, AttributeError):
                            value_str = f"{spike_count} spikes"
                    
                elif analysis_type == "Event Detection":
                    # Access summary_stats if it exists
                    summary_stats = result.get('summary_stats', {})
                    if not isinstance(summary_stats, dict):
                        summary_stats = {}
                    
                    event_count = summary_stats.get('count')
                    if event_count is not None:
                        try:
                            count = int(event_count if isinstance(event_count, (int, float)) else 
                                       event_count.item() if hasattr(event_count, 'item') else event_count)
                            value_str = f"{count} events"
                            
                            # Add frequency if available
                            freq = summary_stats.get('frequency_hz')
                            if freq is not None:
                                try:
                                    freq_float = float(freq if isinstance(freq, (int, float)) else 
                                                    freq.item() if hasattr(freq, 'item') else freq)
                                    value_str += f" ({freq_float:.2f} Hz)"
                                except (ValueError, TypeError, AttributeError):
                                    pass
                        except (ValueError, TypeError, AttributeError):
                            value_str = f"{event_count} events"
                    
            except Exception as e:
                log.warning(f"Error formatting value for {analysis_type}: {e}")
                # Keep default "N/A" value string
                    
            # Format timestamp
            timestamp = "Unknown"
            if 'timestamp_saved' in result:
                try:
                    dt = datetime.fromisoformat(result['timestamp_saved'])
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    timestamp = str(result['timestamp_saved'])
                    
            # Create a summary of details for the last column
            details = []
            
            try:
                if analysis_type == "Input Resistance" or analysis_type == "Input Resistance/Conductance":
                    # Add mode if available
                    mode = result.get('mode', '')
                    if mode:
                        details.append(f"Mode: {mode}")
                    
                    # Add delta values if available
                    delta_v = result.get('delta_mV') if 'delta_mV' in result else result.get('ΔV (mV)')
                    delta_i = result.get('delta_pA') if 'delta_pA' in result else result.get('ΔI (pA)')
                    
                    if delta_v is not None:
                        try:
                            dv_float = float(delta_v if isinstance(delta_v, (int, float)) else 
                                           delta_v.item() if hasattr(delta_v, 'item') else delta_v)
                            details.append(f"ΔV: {dv_float:.2f} mV")
                        except (ValueError, TypeError, AttributeError):
                            details.append(f"ΔV: {delta_v} mV")
                    
                    if delta_i is not None:
                        try:
                            di_float = float(delta_i if isinstance(delta_i, (int, float)) else 
                                           delta_i.item() if hasattr(delta_i, 'item') else delta_i)
                            details.append(f"ΔI: {di_float:.2f} pA")
                        except (ValueError, TypeError, AttributeError):
                            details.append(f"ΔI: {delta_i} pA")
                
                elif analysis_type == "Baseline Analysis":
                    # Format calculation method in user-friendly format
                    method = result.get('calculation_method', '')
                    if method:
                        # Parse the calculation method to make it more human-readable
                        if method.startswith('auto_mode_tolerance='):
                            # Extract tolerance value from string
                            try:
                                tolerance = method.split('=')[1].rstrip('mV')
                                details.append(f"Method: Auto (Mode-based, Tolerance: {tolerance} mV)")
                            except (IndexError, ValueError):
                                details.append(f"Method: Auto (Mode-based)")
                        elif method.startswith('auto_'):
                            details.append(f"Method: Automatic")
                        elif method.startswith('manual_'):
                            details.append(f"Method: Manual Time Window")
                        elif method.startswith('interactive_'):
                            details.append(f"Method: Interactive Region")
                        else:
                            details.append(f"Method: {method}")
                    
                    # Add channel info if available    
                    channel = result.get('channel_name', '')
                    if channel:
                        details.append(f"Channel: {channel}")
                
                elif analysis_type == "Spike Detection (Threshold)":
                    # Add threshold and refractory period
                    threshold = result.get('threshold')
                    units = result.get('threshold_units', '')
                    
                    if threshold is not None:
                        try:
                            threshold_float = float(threshold if isinstance(threshold, (int, float)) else 
                                                  threshold.item() if hasattr(threshold, 'item') else threshold)
                            details.append(f"Threshold: {threshold_float} {units}")
                        except (ValueError, TypeError, AttributeError):
                            details.append(f"Threshold: {threshold} {units}")
                    
                    refractory = result.get('refractory_period_ms')
                    if refractory is not None:
                        try:
                            refractory_float = float(refractory if isinstance(refractory, (int, float)) else 
                                                   refractory.item() if hasattr(refractory, 'item') else refractory)
                            details.append(f"Refractory: {refractory_float} ms")
                        except (ValueError, TypeError, AttributeError):
                            details.append(f"Refractory: {refractory} ms")
                    
                    # Add channel info if available
                    channel = result.get('channel_name', '')
                    if channel:
                        details.append(f"Channel: {channel}")
                
                elif analysis_type == "Event Detection":
                    # Add method
                    method = result.get('method', '')
                    if method:
                        details.append(f"Method: {method}")
                    
                    # Add parameters from the parameters dict if it exists
                    params = result.get('parameters', {})
                    if isinstance(params, dict):
                        direction = params.get('direction')
                        if direction:
                            details.append(f"Direction: {direction}")
                        
                        filter_val = params.get('filter')
                        if filter_val is not None:
                            try:
                                filter_float = float(filter_val if isinstance(filter_val, (int, float)) else 
                                                   filter_val.item() if hasattr(filter_val, 'item') else filter_val)
                                details.append(f"Filter: {filter_float} Hz")
                            except (ValueError, TypeError, AttributeError):
                                details.append(f"Filter: {filter_val} Hz")
                    
                    # Add key metrics from summary_stats if they exist
                    summary_stats = result.get('summary_stats', {})
                    if isinstance(summary_stats, dict):
                        # Mean amplitude if available
                        mean_amp = summary_stats.get('mean_amplitude')
                        amp_units = result.get('units', '')
                        
                        if mean_amp is not None:
                            try:
                                amp_float = float(mean_amp if isinstance(mean_amp, (int, float)) else 
                                                mean_amp.item() if hasattr(mean_amp, 'item') else mean_amp)
                                details.append(f"Mean Amplitude: {amp_float:.2f} {amp_units}")
                            except (ValueError, TypeError, AttributeError):
                                details.append(f"Mean Amplitude: {mean_amp} {amp_units}")
                    
                    # Add channel info if available
                    channel = result.get('channel_name', '')
                    if channel:
                        details.append(f"Channel: {channel}")
            
            except Exception as e:
                log.warning(f"Error formatting details for {analysis_type}: {e}")
                    
            details_str = ", ".join(details) if details else "No additional details"
            
            # Add items to the table
            self.analysis_results_table.setItem(i, 0, QtWidgets.QTableWidgetItem(analysis_type))
            self.analysis_results_table.setItem(i, 1, QtWidgets.QTableWidgetItem(source_file))
            self.analysis_results_table.setItem(i, 2, QtWidgets.QTableWidgetItem(data_source))
            self.analysis_results_table.setItem(i, 3, QtWidgets.QTableWidgetItem(value_str))
            self.analysis_results_table.setItem(i, 4, QtWidgets.QTableWidgetItem(timestamp))
            self.analysis_results_table.setItem(i, 5, QtWidgets.QTableWidgetItem(details_str))
            
        # Update export button state
        self.update_state()
        
    def _select_all_results(self):
        """Selects all rows in the analysis results table."""
        if not self.analysis_results_table:
            return
            
        self.analysis_results_table.selectAll()
        self.update_state()
        
    def _deselect_all_results(self):
        """Deselects all rows in the analysis results table."""
        if not self.analysis_results_table:
            return
            
        self.analysis_results_table.clearSelection()
        self.update_state()
        
    def _get_selected_results_indices(self):
        """Returns a list of indices for the selected results."""
        if not self.analysis_results_table:
            return []
            
        return [index.row() for index in self.analysis_results_table.selectedIndexes() 
                if index.column() == 0]  # Only count one selection per row
        
    def _do_export_analysis_results(self):
        """Exports the selected analysis results to a CSV file."""
        # Get the output file path
        output_path = self.analysis_results_path_edit.text().strip()
        if not output_path:
            QtWidgets.QMessageBox.warning(self, "Export Error", "Please select an output file path.")
            return
            
        # Get selected indices
        selected_indices = set(self._get_selected_results_indices())
        if not selected_indices:
            QtWidgets.QMessageBox.warning(self, "Export Error", "Please select at least one result to export.")
            return
            
        # Access the main window to get the saved analysis results
        main_window = self.window()
        if not hasattr(main_window, 'saved_analysis_results'):
            QtWidgets.QMessageBox.critical(self, "Export Error", "Cannot access analysis results.")
            return
            
        all_results = main_window.saved_analysis_results
        
        # Filter for selected results
        results_to_export = [all_results[i] for i in sorted(selected_indices) if i < len(all_results)]
        
        if not results_to_export:
            QtWidgets.QMessageBox.warning(self, "Export Error", "No valid results selected for export.")
            return
            
        try:
            # Write to CSV
            self._write_results_to_csv(results_to_export, output_path)
            
            # Show success message
            QtWidgets.QMessageBox.information(
                self, 
                "Export Successful", 
                f"Successfully exported {len(results_to_export)} analysis results to:\n{output_path}"
            )
            
            self._status_bar.showMessage(f"Exported {len(results_to_export)} analysis results to {Path(output_path).name}", 5000)
            
        except Exception as e:
            log.error(f"Error exporting analysis results to CSV: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self, 
                "Export Error", 
                f"Failed to export analysis results to CSV:\n{e}"
            )
            
    def _write_results_to_csv(self, results, output_path):
        """Writes the list of result dictionaries to a CSV file."""
        log.info(f"Writing {len(results)} analysis results to CSV: {output_path}")
        
        # Determine all possible fields across all results
        all_fields = set()
        
        # First pass to identify all fields, including nested ones
        for result in results:
            for key, value in result.items():
                if isinstance(value, dict):
                    # For nested dictionaries, add flattened keys
                    for nested_key in value.keys():
                        flat_key = f"{key}.{nested_key}"
                        all_fields.add(flat_key)
                else:
                    all_fields.add(key)
            
        # Sort fields in a logical order
        # First, specify key fields that should appear first
        priority_fields = [
            'analysis_type', 
            'source_file_name', 
            'source_file_path',
            'data_source_used', 
            'trial_index_used', 
            'channel_id',
            'channel_name',
            'timestamp_saved'
        ]
        
        # Then add analysis-specific fields by type
        rin_fields = [
            'Input Resistance (kOhm)', 
            'Rin (MΩ)',
            'Input Conductance (nS)', 
            'delta_mV', 
            'ΔV (mV)',
            'delta_pA', 
            'ΔI (pA)',
            'baseline_mean', 
            'response_mean', 
            'mode'
        ]
        
        baseline_fields = [
            'baseline_mean', 
            'baseline_sd', 
            'baseline_units', 
            'calculation_method'
        ]
        
        spike_fields = [
            'spike_count', 
            'average_firing_rate_hz', 
            'threshold', 
            'threshold_units',
            'refractory_period_ms',
            'spike_times',
            'spike_amplitudes'
        ]
        
        event_fields = [
            'method', 
            'parameters.direction',
            'parameters.filter',
            'parameters.prominence',
            'parameters.sampling_rate_hz',
            'summary_stats.count', 
            'summary_stats.frequency_hz',
            'summary_stats.baseline_mean',
            'summary_stats.baseline_sd',
            'summary_stats.threshold',
            'summary_stats.mean_amplitude',
            'summary_stats.amplitude_sd',
            'summary_stats.mean_rise_time_ms',
            'summary_stats.rise_time_sd_ms',
            'summary_stats.mean_decay_half_time_ms',
            'summary_stats.decay_half_time_sd_ms'
        ]
        
        # Create ordered list of fields
        ordered_fields = priority_fields.copy()
        
        # Add analysis-specific fields from each type
        for field_list in [rin_fields, baseline_fields, spike_fields, event_fields]:
            for field in field_list:
                if field in all_fields and field not in ordered_fields:
                    ordered_fields.append(field)
        
        # Add any remaining fields not already included
        for field in sorted(all_fields):
            if field not in ordered_fields:
                ordered_fields.append(field)
        
        # Helper function to convert numpy values to Python native types
        def convert_value(val):
            """Convert numpy types to Python native types for CSV compatibility."""
            if val is None:
                return ""
            
            # Convert numpy arrays to lists
            if hasattr(val, 'tolist') and callable(getattr(val, 'tolist')):
                try:
                    return str(val.tolist())
                except (ValueError, AttributeError):
                    return str(val)
                    
            # Convert numpy scalar types to native Python types
            if hasattr(val, 'item') and callable(getattr(val, 'item')):
                try:
                    return val.item()
                except (ValueError, AttributeError):
                    return str(val)
            
            # Handle other types
            if isinstance(val, (list, tuple)):
                return str(val)
            
            return val
                
        # Create the CSV file
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=ordered_fields)
            writer.writeheader()
            
            # Process each result to handle nested dictionaries
            for result in results:
                # Create a flattened copy of the result
                flat_result = {}
                
                # Process each key-value pair in the result dictionary
                for key, value in result.items():
                    if isinstance(value, dict):
                        # For nested dictionaries (like summary_stats or parameters)
                        for nested_key, nested_value in value.items():
                            flat_key = f"{key}.{nested_key}"
                            if flat_key in ordered_fields:
                                flat_result[flat_key] = convert_value(nested_value)
                    else:
                        if key in ordered_fields:
                            flat_result[key] = convert_value(value)
                
                # Fill in missing fields with empty strings
                for field in ordered_fields:
                    if field not in flat_result:
                        flat_result[field] = ""
                            
                # Write the flattened result
                writer.writerow(flat_result)
                
        log.info(f"Successfully wrote analysis results to CSV: {output_path}")