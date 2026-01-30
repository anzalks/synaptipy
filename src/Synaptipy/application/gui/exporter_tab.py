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
from datetime import datetime
import pandas as pd  # Added missing import

from PySide6 import QtCore, QtGui, QtWidgets

# Assuming these are correctly structured now
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.exporters import NWBExporter
from Synaptipy.shared.error_handling import SynaptipyError, ExportError
from .nwb_dialog import NwbMetadataDialog  # Need the metadata dialog
from Synaptipy.infrastructure.exporters.csv_exporter import CSVExporter
from Synaptipy.application.session_manager import SessionManager
from Synaptipy.application.controllers.analysis_formatter import AnalysisResultFormatter

try:
    import tzlocal
except ImportError:
    tzlocal = None

log = logging.getLogger(__name__)


class ExporterTab(QtWidgets.QWidget):
    """
    Main Exporter QWidget containing a QTabWidget for different export formats.
    """

    def __init__(
        self,
        nwb_exporter_ref: NWBExporter,
        settings_ref: QtCore.QSettings,
        status_bar_ref: QtWidgets.QStatusBar,
        parent=None,
    ):
        super().__init__(parent)
        log.debug("Initializing ExporterTab")

        # Store references from MainWindow
        self._nwb_exporter = nwb_exporter_ref
        self._settings = settings_ref
        self._status_bar = status_bar_ref

        # --- Exporters ---
        self._csv_exporter = CSVExporter()

        # --- UI Widget References ---
        self.source_file_label: Optional[QtWidgets.QLabel] = None
        # NWB Sub-tab elements
        self.nwb_output_path_edit: Optional[QtWidgets.QLineEdit] = None
        self.nwb_browse_button: Optional[QtWidgets.QPushButton] = None
        self.nwb_export_button: Optional[QtWidgets.QPushButton] = None

        # Main sub-tab widget
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None

        self._setup_ui()
        self._connect_signals()

        # Connect to SessionManager
        self._session_manager = SessionManager()
        self._session_manager.current_recording_changed.connect(self._on_recording_changed)

        self.update_state()  # Set initial state

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

        analysis_results_tab_widget = self._create_analysis_results_sub_tab()  # Create Analysis Results export tab
        self.sub_tab_widget.addTab(analysis_results_tab_widget, "Export Analysis Results")  # Add Analysis Results tab

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

    def _create_analysis_results_sub_tab(self) -> QtWidgets.QWidget:
        """Creates the QWidget containing the UI for exporting analysis results to CSV."""
        tab_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab_widget)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Group for output file selection
        file_group = QtWidgets.QGroupBox("Output File")
        file_layout = QtWidgets.QHBoxLayout(file_group)

        self.analysis_results_path_edit = QtWidgets.QLineEdit()
        self.analysis_results_path_edit.setPlaceholderText("Select file path for analysis results (CSV or JSON)...")
        self.analysis_results_path_edit.setClearButtonEnabled(True)
        file_layout.addWidget(self.analysis_results_path_edit, stretch=1)

        self.analysis_results_browse_button = QtWidgets.QPushButton("Browse...")
        self.analysis_results_browse_button.setToolTip("Choose where to save the analysis results file")
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
        self.analysis_results_table.setHorizontalHeaderLabels(
            ["Analysis Type", "Source File", "Data Source", "Value", "Timestamp", "Details"]
        )
        self.analysis_results_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.analysis_results_table.horizontalHeader().setStretchLastSection(True)
        self.analysis_results_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.analysis_results_table)

        layout.addWidget(results_group, stretch=1)

        # Export button
        export_layout = QtWidgets.QHBoxLayout()
        export_layout.addStretch(1)

        self.analysis_results_export_button = QtWidgets.QPushButton("Export Selected Results")
        self.analysis_results_export_button.setIcon(QtGui.QIcon.fromTheme("document-save"))
        self.analysis_results_export_button.setToolTip("Export the selected analysis results to a file")
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
        if self.nwb_browse_button:
            self.nwb_browse_button.clicked.connect(self._browse_nwb_output_path)
        if self.nwb_export_button:
            self.nwb_export_button.clicked.connect(self._do_export_nwb)
        if self.nwb_output_path_edit:
            self.nwb_output_path_edit.textChanged.connect(self.update_state)

        # Analysis Results export signals
        if self.analysis_results_browse_button:
            self.analysis_results_browse_button.clicked.connect(self._browse_analysis_results_output_path)
        if self.analysis_results_export_button:
            self.analysis_results_export_button.clicked.connect(self._do_export_analysis_results)
        if self.analysis_results_path_edit:
            self.analysis_results_path_edit.textChanged.connect(self.update_state)
        if self.analysis_results_refresh_button:
            self.analysis_results_refresh_button.clicked.connect(self._refresh_analysis_results)
        if self.analysis_results_select_all_button:
            self.analysis_results_select_all_button.clicked.connect(self._select_all_results)
        if self.analysis_results_deselect_all_button:
            self.analysis_results_deselect_all_button.clicked.connect(self._deselect_all_results)
        if self.analysis_results_table:
            self.analysis_results_table.itemSelectionChanged.connect(self.update_state)

    def _on_recording_changed(self, recording: Optional[Recording]):
        """Slot for when the session recording changes."""
        self.update_state()

    # --- Public Method for MainWindow to Call ---
    def update_state(self):
        """
        Updates the enabled state of UI elements based on data availability
        and path/directory selection. Also updates source label.
        """
        current_recording = self._session_manager.current_recording
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

        # Update Analysis Results Export Button
        # Enable if we have selected results, even if path is not set yet (we'll prompt)
        has_selected_results = (
            hasattr(self, "analysis_results_table")
            and self.analysis_results_table
            and len(self._get_selected_results_indices()) > 0
        )
        if self.analysis_results_export_button:
            self.analysis_results_export_button.setEnabled(has_selected_results)

    # --- Handlers ---

    # NWB Handlers
    def _browse_nwb_output_path(self):
        current_recording = self._session_manager.current_recording
        default_dir = self._settings.value("lastExportDirectory", "", type=str)
        default_filename = "exported_data.nwb"
        if current_recording:
            default_filename = current_recording.source_file.with_suffix(".nwb").name
            if not default_dir:
                default_dir = str(current_recording.source_file.parent)
        default_save_path = os.path.join(default_dir, default_filename)
        output_filepath_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save NWB File", dir=default_save_path, filter="NWB Files (*.nwb)"
        )
        if output_filepath_str:
            output_filepath = Path(output_filepath_str)
            self.nwb_output_path_edit.setText(str(output_filepath))
            self._settings.setValue("lastExportDirectory", str(output_filepath.parent))
            log.debug(f"Output NWB path selected: {output_filepath}")
            self.update_state()

    def _do_export_nwb(self):
        # --- NWB Export logic remains the same as previous correct version ---
        log.debug("NWB Export button clicked.")
        current_recording = self._session_manager.current_recording
        output_path_str = self.nwb_output_path_edit.text().strip()
        if not current_recording:
            log.warning("Export NWB ignored: No data.")
            QtWidgets.QMessageBox.warning(self, "Export Error", "No data loaded.")
            self.update_state()
            return
        if not output_path_str:
            log.warning("Export NWB ignored: No output path.")
            QtWidgets.QMessageBox.warning(self, "Export Error", "Select output file path.")
            self.update_state()
            return
        output_filepath = Path(output_path_str)
        try:
            output_filepath.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error(f"Failed create output dir {output_filepath.parent}: {e}")
            QtWidgets.QMessageBox.critical(
                self, "Directory Error", f"Could not create dir:\n{output_filepath.parent}\n\nError: {e}"
            )
            return

        log.debug(f"Preparing NWB metadata for: {current_recording.source_file.name}")

        # New Dialog accepts recording for pre-fill
        dialog = NwbMetadataDialog(recording=current_recording, parent=self)

        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            nwb_metadata = dialog.get_metadata()
            if nwb_metadata is None:  # Should be handled by dialog validation but safety check
                log.error("Metadata validation failed (returned None).")
                self._status_bar.showMessage("Metadata validation failed.", 4000)
                return
        else:
            log.debug("NWB export cancelled by user.")
            self._status_bar.showMessage("NWB export cancelled.", 3000)
            return

        self.nwb_export_button.setEnabled(False)
        self._status_bar.showMessage(f"Exporting NWB to '{output_filepath.name}'...", 0)
        QtWidgets.QApplication.processEvents()
        try:
            self._nwb_exporter.export(current_recording, output_filepath, nwb_metadata)
            log.debug(f"Success export NWB: {output_filepath}")
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

    # Add methods for the analysis results export functionality
    def _browse_analysis_results_output_path(self):
        """Shows file dialog to select CSV output path for analysis results."""
        default_dir = self._settings.value("lastExportDirectory", "", type=str)
        default_filename = "analysis_results.csv"
        default_path = os.path.join(default_dir, default_filename)

        filepath_str, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Analysis Results", dir=default_path, filter="CSV Files (*.csv);;JSON Files (*.json)"
        )

        if filepath_str:
            # Ensure the file has correct extension based on filter or user input
            if selected_filter.startswith("JSON") and not filepath_str.lower().endswith(".json"):
                filepath_str += ".json"
            elif selected_filter.startswith("CSV") and not filepath_str.lower().endswith(".csv"):
                filepath_str += ".csv"

            self.analysis_results_path_edit.setText(filepath_str)
            self._settings.setValue("lastExportDirectory", str(Path(filepath_str).parent))
            log.debug(f"Selected analysis results output path: {filepath_str}")
            self.update_state()

    def _refresh_analysis_results(self):
        """Refreshes the table of available analysis results."""
        # Access the main window to get the saved analysis results
        main_window = self.window()

        if not hasattr(main_window, "saved_analysis_results"):
            log.warning("MainWindow does not have saved_analysis_results attribute")
            return

        results = main_window.saved_analysis_results
        log.debug(f"Refreshing analysis results table with {len(results)} results")

        # Clear and setup the table
        self.analysis_results_table.setRowCount(0)
        self.analysis_results_table.setRowCount(len(results))

        for i, result in enumerate(results):
            # Extract key information for columns
            analysis_type = result.get("analysis_type", "Unknown")
            source_file = result.get("source_file_name", "Unknown")

            # Determine data source string
            data_source_type = result.get("data_source_used", "Unknown")
            trial_index = result.get("trial_index_used")
            if data_source_type == "Trial" and trial_index is not None:
                data_source = f"Trial {trial_index + 1}"
            else:
                data_source = data_source_type

            # Use Formatter
            value_str, details = AnalysisResultFormatter.format_result(result)

            # Format timestamp
            timestamp = "Unknown"
            if "timestamp_saved" in result:
                try:
                    dt = datetime.fromisoformat(result["timestamp_saved"])
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    timestamp = str(result["timestamp_saved"])

            details_str = "; ".join(details)

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

        return [
            index.row() for index in self.analysis_results_table.selectedIndexes() if index.column() == 0
        ]  # Only count one selection per row

    def _do_export_analysis_results(self):
        """Exports the selected analysis results to a CSV file."""
        # Get the output file path
        output_path = self.analysis_results_path_edit.text().strip()

        # If no path set, prompt for one
        if not output_path:
            self._browse_analysis_results_output_path()
            output_path = self.analysis_results_path_edit.text().strip()

        # If still no path (user cancelled), return
        if not output_path:
            return

        # Get selected indices
        selected_indices = set(self._get_selected_results_indices())
        if not selected_indices:
            QtWidgets.QMessageBox.warning(self, "Export Error", "Please select at least one result to export.")
            return

        # Access the main window to get the saved analysis results
        main_window = self.window()
        if not hasattr(main_window, "saved_analysis_results"):
            QtWidgets.QMessageBox.critical(self, "Export Error", "Cannot access analysis results.")
            return

        all_results = main_window.saved_analysis_results

        # Filter for selected results
        results_to_export = [all_results[i] for i in sorted(selected_indices) if i < len(all_results)]

        if not results_to_export:
            QtWidgets.QMessageBox.warning(self, "Export Error", "No valid results selected for export.")
            return

        try:
            # Create DataFrame
            df = pd.DataFrame(results_to_export)

            if output_path.lower().endswith(".json"):
                # JSON Export
                df.to_json(output_path, orient="records", indent=2, default_handler=str)
                log.debug(f"Exported analysis results to JSON: {output_path}")
            else:
                # CSV Export (Default)
                # Flatten or stringify complex columns for CSV if needed, but pandas usually handles basic types.
                # For complex types like arrays, we might want to stringify them explicitly if pandas doesn't.
                # But for now, let's rely on pandas default behavior or string conversion.
                df.to_csv(output_path, index=False)
                log.debug(f"Exported analysis results to CSV: {output_path}")

            QtWidgets.QMessageBox.information(self, "Export Successful", f"Results exported to:\n{output_path}")

        except Exception as e:
            log.error(f"Failed to export analysis results: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Export Error", f"Failed to export results:\n{e}")
            success = self._csv_exporter.export_analysis_results(results_to_export, Path(output_path))

            if success:
                # Show success message
                QtWidgets.QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Successfully exported {len(results_to_export)} analysis results to:\n{output_path}",
                )

                self._status_bar.showMessage(
                    f"Exported {len(results_to_export)} analysis results to {Path(output_path).name}", 5000
                )
            else:
                QtWidgets.QMessageBox.critical(
                    self, "Export Error", "Failed to export analysis results to CSV. Check logs for details."
                )
