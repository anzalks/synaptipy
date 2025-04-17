# src/Synaptipy/application/gui/main_window.py
# -*- coding: utf-8 -*-
"""
Main Window for the Synaptipy GUI application using a tabbed interface.
Manages overall window structure, menu, status bar, tabs, and core adapters.
"""
import logging
import sys
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set
import uuid
from datetime import datetime, timezone

from PySide6 import QtCore, QtGui, QtWidgets

# --- Synaptipy Imports / Dummies ---
# Use RELATIVE import for dummy_classes within the same gui package
from .dummy_classes import (
    NeoAdapter, NWBExporter, Recording, SynaptipyError, ExportError,
    SYNAPTIPY_AVAILABLE
)
# --- Tab Imports ---
# Use RELATIVE imports for tabs and dialogs within the gui package
from .explorer_tab import ExplorerTab
from .analyser_tab import AnalyserTab
from .exporter_tab import ExporterTab
from .nwb_dialog import NwbMetadataDialog
try:
    import tzlocal # Optional, for local timezone handling
except ImportError:
    tzlocal = None


# Use a specific logger for this module
log = logging.getLogger('Synaptipy.application.gui.main_window')

class MainWindow(QtWidgets.QMainWindow):
    """Main application window managing different functional tabs."""

    def __init__(self):
        super().__init__()
        log.info("Initializing MainWindow...")
        self.setWindowTitle("Synaptipy Viewer")

        # --- Calculate initial size based on screen (75%) --- # Updated comment
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            available_geometry = screen.availableGeometry()
            initial_width = int(available_geometry.width() * 0.75) # <<< CHANGED to 0.75
            initial_height = int(available_geometry.height() * 0.75) # <<< CHANGED to 0.75
            self.resize(initial_width, initial_height) # Use resize instead of setGeometry
            log.info(f"Set initial size based on screen (75%): {initial_width}x{initial_height}")
        else:
            log.warning("Could not get screen geometry, using default size.")
            # Fallback default geometry (smaller than before)
            self.resize(1200, 800)
            # self.setGeometry(50, 50, 1700, 950) # <<< REMOVED

        # --- Instantiate Adapters/Exporters ---
        # These come from dummy_classes (which imports real ones if available)
        try:
             self.neo_adapter = NeoAdapter()
             self.nwb_exporter = NWBExporter()
             log.info("NeoAdapter and NWBExporter instantiated successfully.")
        except Exception as e:
             log.critical(f"Failed to instantiate NeoAdapter or NWBExporter: {e}", exc_info=True)
             print(f"CRITICAL ERROR: Failed to instantiate adapters: {e}")
             try: QtWidgets.QMessageBox.critical(None, "Initialization Error", f"Failed to initialize core components:\n{e}\nPlease check installation and dependencies.")
             except Exception as mb_error: print(f"Failed to show message box: {mb_error}")
             QtCore.QTimer.singleShot(100, lambda: sys.exit(1))
             return

        # --- Settings ---
        self.settings = QtCore.QSettings("Synaptipy", "Viewer") # Org name, App name

        # --- Initialize State Variables (Specific to MainWindow) ---
        self.saved_analysis_results: List[Dict[str, Any]] = []

        # --- Setup Core UI Components ---
        self._setup_menu_and_status_bar()
        self._setup_tabs()

        # --- Restore Window State ---
        self._restore_window_state() # Call after UI is created

        # --- Initial UI State ---
        self.status_bar.showMessage("Ready. Open a file using File > Open...", 5000)
        self._update_menu_state()
        log.info("MainWindow initialization complete.")


    def _setup_menu_and_status_bar(self):
        """Creates the main menu bar and status bar, and connects menu actions."""
        log.debug("Setting up menu bar and status bar...")
        # --- Status Bar ---
        self.status_bar = QtWidgets.QStatusBar()
        self.setStatusBar(self.status_bar)
        # --- Menu Bar ---
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        # Open Action
        self.open_file_action = file_menu.addAction("&Open...")
        self.open_file_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        self.open_file_action.setToolTip("Open a recording file (scans folder for siblings)")
        self.open_file_action.triggered.connect(self._open_file_dialog)
        # Export NWB Action
        self.export_nwb_action = file_menu.addAction("Export to &NWB...")
        self.export_nwb_action.setToolTip("Export the currently loaded data (in Explorer tab) to NWB format.")
        self.export_nwb_action.setEnabled(False) # Initially disabled
        self.export_nwb_action.triggered.connect(self._export_to_nwb)
        file_menu.addSeparator()
        # Quit Action
        self.quit_action = file_menu.addAction("&Quit")
        self.quit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)
        log.debug("Menu bar and status bar setup complete.")

    def _setup_tabs(self):
        """Creates the QTabWidget and adds the different functional tabs."""
        log.debug("Setting up tabs...")
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        self.tab_widget.setMovable(True)

        # --- Instantiate Tabs ---
        log.debug("Instantiating ExplorerTab...")
        self.explorer_tab = ExplorerTab(self.neo_adapter, self.nwb_exporter, self.status_bar, self)
        log.debug("Instantiating AnalyserTab...")
        # --- THIS IS THE LINE TO FIX ---
        # Pass the actual ExplorerTab instance, not self (MainWindow)
        self.analyser_tab = AnalyserTab(explorer_tab_ref=self.explorer_tab, parent=self)
        # --- END FIX ---
        log.debug("Instantiating ExporterTab...")
        self.exporter_tab = ExporterTab(
            explorer_tab_ref=self.explorer_tab, nwb_exporter_ref=self.nwb_exporter,
            settings_ref=self.settings, status_bar_ref=self.status_bar, parent=self
        )

        # --- Add Tabs ---
        self.tab_widget.addTab(self.explorer_tab, "Explorer")
        self.tab_widget.addTab(self.analyser_tab, "Analyser")
        self.tab_widget.addTab(self.exporter_tab, "Exporter")

        # --- Connect Signals FROM Tabs TO MainWindow ---
        self.explorer_tab.open_file_requested.connect(self._open_file_dialog)

        # --- Set Central Widget ---
        self.setCentralWidget(self.tab_widget)
        log.debug("Tabs setup complete.")

    def _update_menu_state(self):
        """Updates the enabled state of menu actions based on application state."""
        has_data_in_explorer = (hasattr(self, 'explorer_tab') and self.explorer_tab is not None and
                                self.explorer_tab.get_current_recording() is not None)
        self.export_nwb_action.setEnabled(has_data_in_explorer)
        log.debug(f"Updated menu state: Export enabled = {has_data_in_explorer}")

    # --- File Handling and Export Logic methods (_open_file_dialog, _load_in_explorer, _export_to_nwb) remain the same as previous answer ---
    # V V V (Keep methods from previous answer here) V V V
    def _open_file_dialog(self):
        """Shows the file open dialog (single file), scans for siblings, and initiates loading."""
        log.debug("Open file dialog requested.")
        try:
            file_filter = self.neo_adapter.get_supported_file_filter()
        except Exception as e:
            log.error(f"Failed to get file filter from NeoAdapter: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Adapter Error", f"Could not get file types from adapter:\n{e}")
            file_filter = "All Files (*)" # Fallback

        last_dir = self.settings.value("lastDirectory", "", type=str)

        # --- REVERTED: Use getOpenFileName --- 
        filepath_str, selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Recording File", dir=last_dir, filter=file_filter
        )
        # --- END REVERT ---

        # --- REVERTED: Check single filepath_str --- 
        if not filepath_str:
            log.info("File open dialog cancelled.")
            self.status_bar.showMessage("File open cancelled.", 3000)
            return
        # --- END REVERT ---

        # --- REVERTED: Process single selected file path --- 
        selected_filepath = Path(filepath_str)
        folder_path = selected_filepath.parent
        self.settings.setValue("lastDirectory", str(folder_path))

        selected_extension = selected_filepath.suffix.lower()
        log.info(f"File selected: {selected_filepath.name}. Scanning folder '{folder_path}' for files with extension '{selected_extension}'.")
        # --- END REVERT ---

        # --- REINSTATED: Sibling file scanning logic --- 
        try:
            sibling_files_all = list(folder_path.glob(f"*{selected_filepath.suffix}"))
            # Filter by lower case suffix after glob, ensure it's a file
            sibling_files = sorted([p for p in sibling_files_all if p.is_file() and p.suffix.lower() == selected_extension])
        except Exception as e:
            log.error(f"Error scanning folder {folder_path} for sibling files: {e}", exc_info=True)
            QtWidgets.QMessageBox.warning(self, "Folder Scan Error", f"Could not scan folder for similar files:\n{e}\nLoading selected file only.")
            # Fallback: Load only the selected file if scan fails
            file_list = [selected_filepath]
            current_index = 0
            self._load_in_explorer(selected_filepath, file_list, current_index)
            return
        # --- END REINSTATED SCAN ---

        # --- REINSTATED: Logic to handle found siblings --- 
        if not sibling_files:
            log.warning(f"No files with extension '{selected_extension}' found in the folder. Loading selected file only.")
            file_list = [selected_filepath]
            current_index = 0
        else:
            file_list = sibling_files
            try:
                # Find the index of the originally selected file within the sibling list
                current_index = file_list.index(selected_filepath)
                log.info(f"Found {len(file_list)} file(s) with extension '{selected_extension}'. Selected file is at index {current_index}.")
            except ValueError:
                log.error(f"Selected file '{selected_filepath.name}' not found in the scanned list? Defaulting to index 0.")
                current_index = 0 # Fallback
        # --- END REINSTATED SIBLING LOGIC ---

        # --- Load the file at the determined index from the sibling list --- 
        if file_list:
            if 0 <= current_index < len(file_list):
                 self._load_in_explorer(file_list[current_index], file_list, current_index)
            else:
                 log.error(f"Determined index {current_index} is out of bounds for file list (size {len(file_list)}). Cannot load.")
                 QtWidgets.QMessageBox.critical(self, "Loading Error", "Internal error: Could not determine correct file index.")
                 self._update_menu_state()
        else:
            log.error("File list is unexpectedly empty after selection and processing.")
            QtWidgets.QMessageBox.critical(self, "Loading Error", "Failed to identify the file to load.")
            self._update_menu_state()

    # CHANGE: Signature updated to reflect the arguments passed from the modified _open_file_dialog
    def _load_in_explorer(self, initial_filepath_to_load: Path, file_list: List[Path], current_index: int):
        """Instructs the Explorer tab to load the initial file and provide the full list."""
        # CHANGE: Log using the clearer argument name
        log.info(f"Requesting ExplorerTab to load initial file: {initial_filepath_to_load.name} (from list of {len(file_list)} siblings)")
        if not (hasattr(self, 'explorer_tab') and self.explorer_tab):
            log.error("Cannot load file: Explorer tab not found or not initialized yet.")
            QtWidgets.QMessageBox.critical(self, "Internal Error", "Explorer tab is missing. Cannot load file.")
            self._update_menu_state()
            if hasattr(self, 'exporter_tab') and self.exporter_tab: self.exporter_tab.update_state()
            if hasattr(self, 'analyser_tab') and self.analyser_tab: self.analyser_tab.update_state()
            return

        try:
            # CHANGE: Call the explorer tab's loading method with the initial file, full list, and index
            self.explorer_tab.load_recording_data(initial_filepath_to_load, file_list, current_index)
            self.tab_widget.setCurrentWidget(self.explorer_tab)
        except Exception as e:
            log.error(f"Error occurred trying to initiate load in ExplorerTab: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Load Error", f"An error occurred initiating the file load:\n{e}")
        finally:
            log.debug("Updating menu, exporter, and analyser states after load attempt.")
            self._update_menu_state()
            if hasattr(self, 'exporter_tab') and self.exporter_tab:
                try: self.exporter_tab.update_state()
                except Exception as e_export_update: log.error(f"Error updating exporter tab state: {e_export_update}", exc_info=True)
            else: log.warning("Cannot update exporter tab state: Exporter tab not found.")
            if hasattr(self, 'analyser_tab') and self.analyser_tab:
                try: self.analyser_tab.update_state(self.explorer_tab._analysis_items) # Pass analysis items explicitly
                except Exception as e_analyse_update: log.error(f"Error updating analyser tab state: {e_analyse_update}", exc_info=True)
            else: log.warning("Cannot update analyser tab state: Analyser tab not found.")


    def _export_to_nwb(self):
        """Handles exporting the current recording (from Explorer tab) to NWB."""
        log.debug("Export to NWB action triggered.")
        if not hasattr(self, 'explorer_tab') or not self.explorer_tab:
            log.error("Cannot export: Explorer tab not found.")
            QtWidgets.QMessageBox.critical(self, "Internal Error", "Explorer tab is missing. Cannot export.")
            return

        current_recording = self.explorer_tab.get_current_recording()
        if not current_recording:
            log.warning("Export requested but no recording loaded in Explorer tab.")
            QtWidgets.QMessageBox.warning(self, "Export Error", "No recording data loaded in Explorer tab to export.")
            return

        log.info(f"Preparing to export recording from: {current_recording.source_file.name}")

        # Suggest Filename & Get Save Location (using QSettings)
        default_filename = current_recording.source_file.with_suffix(".nwb").name
        last_export_dir = self.settings.value("lastExportDirectory", str(current_recording.source_file.parent), type=str)
        # Use os.path.join for robust cross-platform default path suggestion
        default_save_path = os.path.join(last_export_dir, default_filename)


        output_filepath_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save NWB File", dir=default_save_path, filter="NWB Files (*.nwb)"
        )

        if not output_filepath_str:
            log.info("NWB export cancelled by user."); self.status_bar.showMessage("NWB export cancelled.", 3000); return

        output_filepath = Path(output_filepath_str)
        # Save the chosen directory for next time
        self.settings.setValue("lastExportDirectory", str(output_filepath.parent))

        # Prepare Metadata for Dialog (same logic as original)
        default_identifier = str(uuid.uuid4())
        # Ensure session_start_time_dt attribute exists before accessing
        default_start_time_naive = getattr(current_recording, 'session_start_time_dt', datetime.now())

        aware_start_time = timezone.utc # Default fallback
        if default_start_time_naive.tzinfo is None:
            log.warning("Recording start time is timezone-naive. Attempting to use local timezone for NWB dialog.")
            if tzlocal:
                try:
                    local_tz = tzlocal.get_localzone()
                    aware_start_time = default_start_time_naive.replace(tzinfo=local_tz)
                    log.debug(f"Using local timezone from tzlocal: {local_tz}")
                except Exception as e:
                    log.warning(f"Failed to get local timezone using tzlocal: {e}. Defaulting to UTC.", exc_info=True)
                    aware_start_time = default_start_time_naive.replace(tzinfo=timezone.utc)
            else:
                 log.debug("tzlocal not found. Defaulting NWB start time to UTC.")
                 aware_start_time = default_start_time_naive.replace(tzinfo=timezone.utc)
        else:
             aware_start_time = default_start_time_naive # Time from recording is already aware

        # Show Metadata Dialog
        dialog = NwbMetadataDialog(default_identifier, aware_start_time, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            nwb_metadata = dialog.get_metadata()
            if nwb_metadata is None: # Validation failed in dialog
                log.error("Metadata dialog accepted but returned None (validation failed)."); self.status_bar.showMessage("Metadata validation failed.", 3000); return
            log.debug(f"NWB metadata collected: {nwb_metadata}")
        else:
            log.info("NWB export cancelled during metadata input."); self.status_bar.showMessage("NWB export cancelled.", 3000); return

        # Perform Export (using self.nwb_exporter)
        self.status_bar.showMessage(f"Exporting NWB to '{output_filepath.name}'...")
        QtWidgets.QApplication.processEvents() # Keep UI responsive during export if possible

        try:
            # nwb_exporter is already instantiated and available via self
            self.nwb_exporter.export(current_recording, output_filepath, nwb_metadata)
            log.info(f"Successfully exported NWB file: {output_filepath}")
            self.status_bar.showMessage(f"Export successful: {output_filepath.name}", 5000)
            QtWidgets.QMessageBox.information(self, "Export Successful", f"Data successfully saved to:\n{output_filepath}")
        except (ValueError, ExportError, SynaptipyError) as e:
            log.error(f"NWB Export failed: {e}", exc_info=False) # Log known errors concisely
            self.status_bar.showMessage(f"NWB Export failed: {e}", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export NWB file:\n{e}")
        except Exception as e:
            log.error(f"An unexpected error occurred during NWB Export: {e}", exc_info=True) # Log unexpected errors with traceback
            self.status_bar.showMessage("Unexpected NWB Export error occurred.", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"An unexpected error occurred during export:\n{e}")

    # ^ ^ ^ (Keep methods from previous answer here) ^ ^ ^


    # =========================================================================
    # Window State and Close Event
    # =========================================================================

    def _restore_window_state(self):
        """Restores window geometry and state from QSettings, checking validity."""
        log.debug("Restoring window state from settings...")
        screen = QtWidgets.QApplication.primaryScreen()
        available_geometry = screen.availableGeometry() if screen else None

        try:
            geom_value = self.settings.value("geometry") # Get value without type hint first
            if geom_value is not None:
                # Check if it's QByteArray or bytes and decode if necessary
                if isinstance(geom_value, QtCore.QByteArray):
                    geom_bytes = geom_value
                elif isinstance(geom_value, bytes):
                     geom_bytes = QtCore.QByteArray(geom_value)
                else:
                    log.warning(f"Saved geometry is not QByteArray or bytes: {type(geom_value)}. Skipping restore.")
                    geom_bytes = None

                if geom_bytes is not None:
                    # --- Check if saved geometry fits on screen --- 
                    temp_window = QtWidgets.QMainWindow() # Use a temporary object to parse geometry
                    if temp_window.restoreGeometry(geom_bytes):
                        restored_rect = temp_window.geometry()
                        fits_on_screen = True
                        if available_geometry:
                             # Check if width/height are smaller than available screen space
                             if restored_rect.width() > available_geometry.width() or \
                                restored_rect.height() > available_geometry.height():
                                 fits_on_screen = False
                                 log.warning(f"Saved geometry ({restored_rect.width()}x{restored_rect.height()}) exceeds available screen size ({available_geometry.width()}x{available_geometry.height()}). Ignoring saved geometry.")
                        # --- End Check ---
                        
                        if fits_on_screen:
                            if self.restoreGeometry(geom_bytes):
                                log.debug("Restored window geometry.")
                            else:
                                log.warning("Failed to restore geometry from saved value.")
                        # If !fits_on_screen, we do nothing, keeping the calculated default size
                    else:
                        log.warning("Could not parse saved geometry bytes.")
                    del temp_window # Clean up temporary window
            else:
                 log.debug("No saved geometry found.")

            # Restore state (like maximized) usually doesn't cause off-screen issues
            state_value = self.settings.value("windowState")
            if state_value is not None:
                if isinstance(state_value, QtCore.QByteArray):
                    state = state_value
                elif isinstance(state_value, bytes):
                    state = QtCore.QByteArray(state_value)
                else:
                    log.warning(f"Saved windowState is not QByteArray or bytes: {type(state_value)}. Skipping restore.")
                    state = None

                if state is not None and self.restoreState(state):
                     log.debug("Restored window state.")
                elif state is not None:
                     log.warning("Failed to restore state from saved value.")
            else:
                 log.debug("No saved window state found.")

        except Exception as e:
            log.warning(f"Could not restore window state: {e}", exc_info=True)


    def closeEvent(self, event: QtGui.QCloseEvent):
        """Handles the main window close event, saving state."""
        log.info("Close event received. Cleaning up and saving state...")
        # --- Call cleanup on tabs if they exist ---
        if hasattr(self, 'explorer_tab') and hasattr(self.explorer_tab, 'cleanup'): # Define cleanup() in ExplorerTab if needed
            try: log.debug("Calling cleanup for ExplorerTab..."); self.explorer_tab.cleanup()
            except Exception as e: log.warning(f"Error during ExplorerTab cleanup: {e}")
        # Clear graphics layout explicitly before closing
        if hasattr(self, 'explorer_tab') and hasattr(self.explorer_tab, 'graphics_layout_widget') and self.explorer_tab.graphics_layout_widget:
            try: self.explorer_tab.graphics_layout_widget.clear(); log.debug("Cleared explorer tab graphics.")
            except Exception as e: log.warning(f"Error clearing graphics layout during close: {e}")
        # --- Save Settings ---
        try:
             log.debug("Saving window geometry and state...")
             self.settings.setValue("geometry", self.saveGeometry())
             self.settings.setValue("windowState", self.saveState())
             # Ensure settings are written to disk (sync might be needed depending on OS/timing)
             self.settings.sync()
             log.debug("Saved window geometry and state.")
        except Exception as e:
            log.warning(f"Could not save settings on close: {e}")
        log.info("Accepting close event.")
        event.accept()

    # --- ADDED: Method to store analysis results ---
    def add_saved_result(self, result_data: Dict[str, Any]):
        """Appends a dictionary containing analysis results to the central list."""
        if not isinstance(result_data, dict):
            log.error(f"Attempted to add non-dict result: {type(result_data)}")
            return
        
        # Add a timestamp for when the result was saved
        result_data['timestamp_saved'] = datetime.now(timezone.utc).isoformat()
        
        self.saved_analysis_results.append(result_data)
        log.info(f"Saved analysis result ({result_data.get('analysis_type', '?')} from {result_data.get('source_file_name', '?')}). Total saved: {len(self.saved_analysis_results)}")
        # Optional: Update status bar or emit signal
        self.status_bar.showMessage(f"Result saved ({result_data.get('analysis_type', '?')}). Total: {len(self.saved_analysis_results)}", 3000)
        # Example signal (define in class header if needed):
        # self.analysis_results_updated.emit(self.saved_analysis_results)
    # --- END ADDED ---