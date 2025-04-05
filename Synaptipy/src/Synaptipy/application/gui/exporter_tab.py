# src/Synaptipy/application/gui/exporter_tab.py
# -*- coding: utf-8 -*-
"""
Exporter Tab widget for the Synaptipy GUI. Provides UI for exporting data,
using sub-tabs for different formats (e.g., NWB).
"""
import logging
import os
from pathlib import Path
from typing import Optional
import uuid
from datetime import datetime, timezone

from PySide6 import QtCore, QtGui, QtWidgets

# Assuming these are correctly structured now
from .dummy_classes import Recording, NWBExporter, SynaptipyError, ExportError
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

        # --- UI Widget References (Specific to contained elements) ---
        # Source Info (Outside sub-tabs)
        self.source_file_label: Optional[QtWidgets.QLabel] = None
        # NWB Sub-tab elements
        self.nwb_output_path_edit: Optional[QtWidgets.QLineEdit] = None
        self.nwb_browse_button: Optional[QtWidgets.QPushButton] = None
        self.nwb_export_button: Optional[QtWidgets.QPushButton] = None
        # Main sub-tab widget
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None

        self._setup_ui()
        self._connect_signals()
        self.update_state() # Set initial state

    def _setup_ui(self):
        """Create the main layout and the sub-tab structure."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Source Data Group (Remains outside sub-tabs) ---
        source_group = QtWidgets.QGroupBox("Data Source (from Explorer Tab)")
        source_layout = QtWidgets.QFormLayout(source_group)
        self.source_file_label = QtWidgets.QLabel("<i>None loaded</i>")
        self.source_file_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_file_label.setWordWrap(True)
        source_layout.addRow("Current File:", self.source_file_label)
        main_layout.addWidget(source_group)

        # --- Sub-Tab Widget ---
        self.sub_tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.sub_tab_widget) # Add sub-tabs below source info

        # --- Create and Add NWB Sub-Tab ---
        nwb_sub_tab_widget = self._create_nwb_sub_tab()
        self.sub_tab_widget.addTab(nwb_sub_tab_widget, "Export to NWB")

        # --- Placeholder for adding other export format sub-tabs ---
        # csv_sub_tab_widget = self._create_csv_sub_tab()
        # self.sub_tab_widget.addTab(csv_sub_tab_widget, "Export to CSV")

        # --- Stretch ---
        main_layout.addStretch() # Push content to the top
        self.setLayout(main_layout)
        log.debug("ExporterTab UI setup complete with sub-tabs.")

    def _create_nwb_sub_tab(self) -> QtWidgets.QWidget:
        """Creates the QWidget containing the UI for the NWB export sub-tab."""
        nwb_widget = QtWidgets.QWidget()
        nwb_layout = QtWidgets.QVBoxLayout(nwb_widget)
        nwb_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- NWB Export Group ---
        nwb_group = QtWidgets.QGroupBox("NWB Export Options") # Title optional here
        nwb_group_layout = QtWidgets.QVBoxLayout(nwb_group)

        # Output Path Selection
        output_layout = QtWidgets.QHBoxLayout()
        output_layout.addWidget(QtWidgets.QLabel("Output File:"))
        self.nwb_output_path_edit = QtWidgets.QLineEdit() # Use specific name
        self.nwb_output_path_edit.setPlaceholderText("Select NWB output file path...")
        self.nwb_output_path_edit.setClearButtonEnabled(True)
        output_layout.addWidget(self.nwb_output_path_edit, stretch=1)
        self.nwb_browse_button = QtWidgets.QPushButton("Browse...") # Use specific name
        self.nwb_browse_button.setToolTip("Choose where to save the NWB file")
        output_layout.addWidget(self.nwb_browse_button)
        nwb_group_layout.addLayout(output_layout)

        # Export Action Button
        self.nwb_export_button = QtWidgets.QPushButton("Export to NWB...") # Use specific name
        self.nwb_export_button.setIcon(QtGui.QIcon.fromTheme("document-save")) # Optional icon
        self.nwb_export_button.setToolTip("Start the NWB export process")
        self.nwb_export_button.setEnabled(False) # Disabled initially
        nwb_group_layout.addWidget(self.nwb_export_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        nwb_layout.addWidget(nwb_group)
        nwb_layout.addStretch() # Push group to top within the sub-tab
        nwb_widget.setLayout(nwb_layout)
        return nwb_widget

    def _connect_signals(self):
        """Connect signals for widgets within the Exporter Tab and its sub-tabs."""
        # Connect signals for NWB sub-tab widgets
        if self.nwb_browse_button:
            self.nwb_browse_button.clicked.connect(self._browse_nwb_output_path)
        if self.nwb_export_button:
            self.nwb_export_button.clicked.connect(self._do_export_nwb)
        if self.nwb_output_path_edit:
            self.nwb_output_path_edit.textChanged.connect(self.update_state)

    # --- Public Method for MainWindow to Call ---
    def update_state(self):
        """
        Updates the enabled state of UI elements (like export buttons) based
        on data availability and path selection. Also updates source label.
        """
        current_recording = self._explorer_tab.get_current_recording()
        has_data = current_recording is not None

        # Update Source Label (outside sub-tabs)
        if self.source_file_label:
            if has_data:
                self.source_file_label.setText(f"<i>{current_recording.source_file.name}</i>")
                self.source_file_label.setToolTip(str(current_recording.source_file))
            else:
                self.source_file_label.setText("<i>None loaded</i>")
                self.source_file_label.setToolTip("")

        # Update NWB Export Button Enabled State (inside sub-tab)
        nwb_output_path_ok = bool(self.nwb_output_path_edit.text().strip()) if self.nwb_output_path_edit else False
        if self.nwb_export_button:
            self.nwb_export_button.setEnabled(has_data and nwb_output_path_ok)

        # Update state for other potential export buttons here...

    # --- Handlers (specific to NWB export) ---
    def _browse_nwb_output_path(self):
        """Opens a file dialog to select the NWB output file path."""
        current_recording = self._explorer_tab.get_current_recording()
        default_dir = self._settings.value("lastExportDirectory", "", type=str)
        default_filename = "exported_data.nwb"

        if current_recording:
            default_filename = current_recording.source_file.with_suffix(".nwb").name
            if not default_dir: default_dir = str(current_recording.source_file.parent)

        default_save_path = os.path.join(default_dir, default_filename)

        output_filepath_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save NWB File", dir=default_save_path, filter="NWB Files (*.nwb)"
        )

        if output_filepath_str:
            output_filepath = Path(output_filepath_str)
            self.nwb_output_path_edit.setText(str(output_filepath)) # Update NWB path edit
            self._settings.setValue("lastExportDirectory", str(output_filepath.parent))
            log.info(f"Output NWB path selected: {output_filepath}")
            self.update_state() # Re-check button state

    def _do_export_nwb(self):
        """Handles the logic for exporting to NWB."""
        log.debug("NWB Export button clicked.")
        current_recording = self._explorer_tab.get_current_recording()
        output_path_str = self.nwb_output_path_edit.text().strip() # Get path from NWB edit

        # --- Validation ---
        if not current_recording:
            log.warning("Export ignored: No recording loaded."); QtWidgets.QMessageBox.warning(self, "Export Error", "No data loaded."); self.update_state(); return
        if not output_path_str:
            log.warning("Export ignored: No output file path."); QtWidgets.QMessageBox.warning(self, "Export Error", "Select output file path."); self.update_state(); return

        output_filepath = Path(output_path_str)
        try: output_filepath.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error(f"Failed to create output dir {output_filepath.parent}: {e}"); QtWidgets.QMessageBox.critical(self, "Directory Error", f"Could not create dir:\n{output_filepath.parent}\n\nError: {e}"); return

        # --- Prepare and Show Metadata Dialog ---
        log.info(f"Preparing NWB metadata for: {current_recording.source_file.name}")
        default_identifier = str(uuid.uuid4())
        default_start_time_naive = getattr(current_recording, 'session_start_time_dt', datetime.now())
        aware_start_time = timezone.utc
        if default_start_time_naive.tzinfo is None:
            log.warning("Recording start time naive. Using local/UTC.");
            if tzlocal:
                try: aware_start_time = default_start_time_naive.replace(tzinfo=tzlocal.get_localzone())
                except Exception as e: log.warning(f"tzlocal failed: {e}. Using UTC."); aware_start_time = default_start_time_naive.replace(tzinfo=timezone.utc)
            else: aware_start_time = default_start_time_naive.replace(tzinfo=timezone.utc)
        else: aware_start_time = default_start_time_naive

        dialog = NwbMetadataDialog(default_identifier, aware_start_time, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            nwb_metadata = dialog.get_metadata()
            if nwb_metadata is None: log.error("Metadata dialog returned None."); self._status_bar.showMessage("Metadata validation failed.", 4000); return
        else: log.info("NWB export cancelled."); self._status_bar.showMessage("NWB export cancelled.", 3000); return

        # --- Perform Export ---
        self.nwb_export_button.setEnabled(False) # Disable NWB button
        self._status_bar.showMessage(f"Exporting NWB to '{output_filepath.name}'...", 0)
        QtWidgets.QApplication.processEvents()

        try:
            self._nwb_exporter.export(current_recording, output_filepath, nwb_metadata)
            log.info(f"Successfully exported NWB: {output_filepath}")
            self._status_bar.showMessage(f"Export successful: {output_filepath.name}", 5000)
            QtWidgets.QMessageBox.information(self, "Export Successful", f"Data saved to:\n{output_filepath}")
        except (ValueError, ExportError, SynaptipyError) as e:
            log.error(f"NWB Export failed: {e}", exc_info=False)
            self._status_bar.showMessage(f"NWB Export failed: {e}", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export NWB:\n{e}")
        except Exception as e:
            log.error(f"Unexpected error during NWB Export: {e}", exc_info=True)
            self._status_bar.showMessage("Unexpected NWB Export error.", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Unexpected error during export:\n{e}")
        finally:
            self.update_state() # Re-enable button if conditions met