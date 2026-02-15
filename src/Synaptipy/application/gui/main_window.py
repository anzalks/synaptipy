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
from typing import List, Dict, Any
import uuid
from datetime import datetime, timezone

from PySide6 import QtCore, QtGui, QtWidgets

# --- Synaptipy Imports / Dummies ---
# --- Synaptipy Imports ---
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters import NWBExporter
from Synaptipy.shared.error_handling import SynaptipyError, ExportError

# Import the new DataLoader for background file loading
from ..data_loader import DataLoader
from Synaptipy.application.controllers.file_io_controller import FileIOController

# --- Tab Imports ---
# Use RELATIVE imports for tabs and dialogs within the gui package
from .explorer import ExplorerTab
from .analyser_tab import AnalyserTab
from .exporter_tab import ExporterTab
from .nwb_dialog import NwbMetadataDialog
from .plot_customization_dialog import PlotCustomizationDialog
from Synaptipy.application.session_manager import SessionManager

try:
    import tzlocal  # Optional, for local timezone handling
except ImportError:
    tzlocal = None

# Import styling module for basic styling
from Synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

# Use a specific logger for this module
log = logging.getLogger(__name__)


class MainWindow(QtWidgets.QMainWindow):
    """Main application window managing different functional tabs."""

    # Emitted when the window finished initializing all UI and state
    initialized = QtCore.Signal()

    # Signal for requesting file loading with lazy load flag
    load_request = QtCore.Signal(Path, bool)

    def __init__(self):
        super().__init__()
        log.debug("Initializing MainWindow...")
        self.session_manager = SessionManager()
        self.setWindowTitle("Synaptipy - Electrophysiology Visualizer")

        # Set Window Icon
        icon_path = Path(__file__).parent.parent.parent / "resources" / "icons" / "logo.png"
        if icon_path.exists():
            app_icon = QtGui.QIcon(str(icon_path))
            self.setWindowIcon(app_icon)
            QtWidgets.QApplication.setWindowIcon(app_icon)  # Set for taskbar/dock as well

        # --- Calculate initial size based on screen (70%) ---
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            available_geometry = screen.availableGeometry()
            # Reduce to 70% of available screen size
            initial_width = int(available_geometry.width() * 0.7)
            initial_height = int(available_geometry.height() * 0.7)

            # Set maximum dimensions to prevent too large windows on big monitors
            max_width = min(1600, available_geometry.width() - 100)
            max_height = min(1000, available_geometry.height() - 100)

            # Apply constraints
            initial_width = min(initial_width, max_width)
            initial_height = min(initial_height, max_height)

            self.resize(initial_width, initial_height)
            # Center the window on screen
            self.move(
                available_geometry.left() + (available_geometry.width() - initial_width) // 2,
                available_geometry.top() + (available_geometry.height() - initial_height) // 2,
            )
            log.debug(f"Set initial size based on screen (70%): {initial_width}x{initial_height}")
        else:
            log.warning("Could not get screen geometry, using default size.")
            # Fallback default geometry (smaller size)
            self.resize(1000, 700)

        # --- Instantiate Adapters/Exporters ---
        try:
            self.neo_adapter = NeoAdapter()
            self.nwb_exporter = NWBExporter()
            log.debug("NeoAdapter and NWBExporter instantiated successfully.")
        except Exception as e:
            log.critical(f"Failed to instantiate NeoAdapter or NWBExporter: {e}", exc_info=True)
            try:
                QtWidgets.QMessageBox.critical(
                    None,
                    "Initialization Error",
                    f"Failed to initialize core components:\n{e}\nPlease check installation and dependencies.",
                )
            except Exception as mb_error:
                log.error(f"Failed to show message box: {mb_error}")
            QtCore.QTimer.singleShot(100, lambda: sys.exit(1))
            return

        # --- Setup Background Data Loading ---
        self._setup_data_loader()

        # --- Settings ---
        self.settings = QtCore.QSettings(APP_NAME, SETTINGS_SECTION)

        # --- Controllers ---
        self.file_io_controller = FileIOController(self, self.settings, self.neo_adapter)

        # --- Initialize State Variables (Specific to MainWindow) ---
        self.saved_analysis_results: List[Dict[str, Any]] = []

        # --- Setup Core UI Components ---
        self._setup_menu_and_status_bar()
        self._setup_tabs()

        # --- Restore Window State ---
        self._restore_window_state()  # Call after UI is created

        # --- Initial UI State ---
        self.status_bar.showMessage("Ready. Open a file using File > Open...", 5000)
        self._update_menu_state()
        log.info("MainWindow initialization complete.")
        # Notify listeners that initialization is complete
        try:
            self.initialized.emit()
        except Exception:
            pass

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
        self.export_nwb_action.setEnabled(False)  # Initially disabled
        self.export_nwb_action.triggered.connect(self._export_to_nwb)
        file_menu.addSeparator()
        # Quit Action
        self.quit_action = file_menu.addAction("&Quit")
        self.quit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)

        # --- Edit Menu ---
        edit_menu = menu_bar.addMenu("&Edit")

        # Preferences Action
        self.preferences_action = edit_menu.addAction("&Preferences...")
        self.preferences_action.setShortcut(QtGui.QKeySequence.StandardKey.Preferences)
        self.preferences_action.setToolTip("Open application preferences")
        # Force it to appear in Edit menu on macOS (disable auto-move to App menu)
        self.preferences_action.setMenuRole(QtGui.QAction.MenuRole.NoRole)
        self.preferences_action.triggered.connect(self._show_preferences)

        edit_menu.addSeparator()

        # Configure Analysis Defaults Action
        self.configure_analysis_action = edit_menu.addAction("&Configure Analysis Defaults...")
        self.configure_analysis_action.setToolTip("Open the global analysis configuration dialog")
        # Also ensure this doesn't get moved strangely
        self.configure_analysis_action.setMenuRole(QtGui.QAction.MenuRole.NoRole)
        self.configure_analysis_action.triggered.connect(self._show_analysis_config)

        # --- View Menu ---
        view_menu = menu_bar.addMenu("&View")

        # Plot Customization Action
        self.plot_customization_action = view_menu.addAction("Plot &Customization...")
        self.plot_customization_action.setToolTip("Customize plot colors, widths, and transparency")
        self.plot_customization_action.triggered.connect(self._show_plot_customization)

        view_menu.addSeparator()

        # Show Popup Windows Action
        self.show_popup_windows_action = view_menu.addAction("Show Analysis &Popup Windows...")
        self.show_popup_windows_action.setToolTip("Show or restore any analysis popup windows (F-I curve, etc.)")
        self.show_popup_windows_action.triggered.connect(self._show_popup_windows)

        log.debug("Menu bar and status bar setup complete.")

        # Connect to plot customization signals
        self._connect_plot_customization_signals()

    def _setup_data_loader(self):
        """Setup the background data loader with worker thread."""
        log.debug("Setting up background data loader...")

        # Create worker thread
        self.data_loader_thread = QtCore.QThread()

        # Create data loader instance
        self.data_loader = DataLoader()

        # Move the loader to the worker thread
        self.data_loader.moveToThread(self.data_loader_thread)

        # Connect signals
        self.data_loader.data_ready.connect(self._on_data_ready)
        self.data_loader.data_error.connect(self._on_data_error)
        self.data_loader.loading_started.connect(self._on_loading_started)
        self.data_loader.loading_progress.connect(self._on_loading_progress)

        # Connect the load request signal to the data loader
        self.load_request.connect(self.data_loader.load_file)

        # Connect thread finished signal to cleanup
        self.data_loader_thread.finished.connect(self.data_loader.deleteLater)

        # Start the worker thread
        self.data_loader_thread.start()
        log.debug("Background data loader setup complete.")

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
        # Pass the neo_adapter instance
        self.analyser_tab = AnalyserTab(neo_adapter=self.neo_adapter, settings_ref=self.settings, parent=self)
        # --- END FIX ---
        log.debug("Instantiating ExporterTab...")
        self.exporter_tab = ExporterTab(
            nwb_exporter_ref=self.nwb_exporter, settings_ref=self.settings, status_bar_ref=self.status_bar, parent=self
        )

        # --- Add Tabs ---
        self.tab_widget.addTab(self.explorer_tab, "Explorer")
        self.tab_widget.addTab(self.analyser_tab, "Analyser")
        self.tab_widget.addTab(self.exporter_tab, "Exporter")

        # --- Connect Signals FROM Tabs TO MainWindow ---
        self.explorer_tab.open_file_requested.connect(self._open_file_dialog)
        
        # Connect AnalyserTab load request
        if hasattr(self.analyser_tab, "load_file_requested"):
            self.analyser_tab.load_file_requested.connect(self._on_analyser_load_file_request)

        # --- Set Central Widget ---
        self.setCentralWidget(self.tab_widget)
        log.debug("Tabs setup complete.")

    def _update_menu_state(self):
        """Updates the enabled state of menu actions based on application state."""
        has_data_in_explorer = (
            hasattr(self, "explorer_tab")
            and self.explorer_tab is not None
            and self.explorer_tab.get_current_recording() is not None
        )
        self.export_nwb_action.setEnabled(has_data_in_explorer)
        log.debug(f"Updated menu state: Export enabled = {has_data_in_explorer}")

    def _connect_plot_customization_signals(self):
        """Connect to plot customization signals for automatic plot updates."""
        try:
            from Synaptipy.shared.plot_customization import get_plot_customization_signals

            signals = get_plot_customization_signals()
            signals.preferences_updated.connect(self._on_plot_preferences_updated)
            log.debug("Connected to plot customization signals")
        except Exception as e:
            log.warning(f"Failed to connect plot customization signals: {e}")

    def _needs_plot_update(self) -> bool:
        """Check if plot update is actually needed."""
        try:
            # Always allow plot updates when preferences change, even if no plots are currently displayed
            # This ensures that when plots are created later, they use the new preferences

            # Check if we have any active plots that need immediate updating
            has_explorer_plots = (
                hasattr(self, "explorer_tab")
                and self.explorer_tab
                and hasattr(self.explorer_tab, "channel_plot_data_items")
                and self.explorer_tab.channel_plot_data_items
            )

            has_analysis_plots = (
                hasattr(self, "analyser_tab")
                and self.analyser_tab
                and (
                    (hasattr(self.analyser_tab, "count") and self.analyser_tab.count() > 0)
                    or (hasattr(self.analyser_tab, "plot_widget") and self.analyser_tab.plot_widget)
                )
            )

            # If we have active plots, update them immediately
            if has_explorer_plots or has_analysis_plots:
                log.debug("Active plots found - will update immediately")
                return True

            # If no active plots, still allow the update (for future plots)
            log.debug("No active plots found - allowing update for future plots")
            return True

        except Exception as e:
            log.warning(f"Could not check if plot update is needed: {e}")
            return True  # Assume update needed if we can't check

    def _on_plot_preferences_updated(self):
        """Handle plot preferences update signal by efficiently updating pens."""
        # Import the getter function (can be done at top of file too)
        from Synaptipy.shared.plot_customization import get_force_opaque_trials

        log.debug(f"[_on_plot_preferences_updated] Handling signal. Force opaque state: {get_force_opaque_trials()}")

        # CRITICAL FIX: Use the optimized _update_plot_pens_only() method instead of the slow update_plot_pens()
        # This updates pen properties in-place without removing/recreating plot items
        if hasattr(self, "explorer_tab") and self.explorer_tab:
            # Use the optimized update_plot_pens() method
            # This updates pen properties in-place immediately
            if hasattr(self.explorer_tab, "update_plot_pens"):
                self.explorer_tab.update_plot_pens()
                log.debug("Updated explorer tab plots using optimized update_plot_pens")
            else:
                log.warning("Explorer tab missing update_plot_pens method")
        if hasattr(self, "analyser_tab") and self.analyser_tab:
            # Add logic here to update analyser tab plots if they exist
            pass

    def _update_plot_pens_only(self):
        """Update only plot pens when user changes preferences in dialog."""
        try:
            log.debug("=== UPDATING PLOT PENS ONLY ===")

            # Update explorer tab plot pens
            if hasattr(self, "explorer_tab") and self.explorer_tab:
                try:
                    if hasattr(self.explorer_tab, "update_plot_pens"):
                        # Use explorer tab's own pen update method for better performance
                        self.explorer_tab.update_plot_pens()
                        log.debug("Updated plot pens for explorer tab plots (using tab's method)")
                    else:
                        # Fallback to generic method if tab doesn't have its own
                        from Synaptipy.shared.plot_customization import update_plot_pens

                        if hasattr(self.explorer_tab, "channel_plots"):
                            plot_widgets = list(self.explorer_tab.channel_plots.values())
                            if plot_widgets:
                                update_plot_pens(plot_widgets)
                                log.debug("Updated plot pens for explorer tab plots (using generic method)")
                except Exception as e:
                    log.debug(f"Could not update plot pens for explorer tab: {e}")

            # Update analysis tab plot pens
            if hasattr(self, "analyser_tab") and self.analyser_tab:
                try:
                    from Synaptipy.shared.plot_customization import update_plot_pens

                    # Check if analyser_tab has _loaded_analysis_tabs (AnalyserTab is QWidget)
                    if hasattr(self.analyser_tab, "_loaded_analysis_tabs"):
                        for analysis_widget in self.analyser_tab._loaded_analysis_tabs:
                            if hasattr(analysis_widget, "plot_widget"):
                                update_plot_pens([analysis_widget.plot_widget])
                                log.debug(f"Updated plot pens for analysis tab: {analysis_widget.get_display_name()}")
                    # Fallback for legacy QTabWidget structure
                    elif hasattr(self.analyser_tab, "count"):
                        for i in range(self.analyser_tab.count()):
                            analysis_widget = self.analyser_tab.widget(i)
                            if hasattr(analysis_widget, "plot_widget"):
                                update_plot_pens([analysis_widget.plot_widget])
                                log.debug(f"Updated plot pens for analysis tab {i}")
                    else:
                        # analyser_tab might be a single widget (unlikely now but safe fallback)
                        if hasattr(self.analyser_tab, "plot_widget"):
                            update_plot_pens([self.analyser_tab.plot_widget])
                            log.debug("Updated plot pens for single analysis tab")
                except Exception as e:
                    log.debug(f"Could not update plot pens for analysis tabs: {e}")

            log.debug("Plot pen update complete")
        except Exception as e:
            log.error(f"Failed to update plot pens: {e}")

    def _show_plot_customization(self):
        """Show the plot customization dialog."""
        try:
            dialog = PlotCustomizationDialog(self)
            dialog.exec()
            log.debug("Plot customization dialog closed")
        except Exception as e:
            log.error(f"Failed to show plot customization dialog: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open plot customization:\n{e}")

    def _show_preferences(self):
        """Show the preferences dialog."""
        try:
            from .preferences_dialog import PreferencesDialog

            dialog = PreferencesDialog(self)
            dialog.exec()
            log.debug("Preferences dialog closed")
        except Exception as e:
            log.error(f"Failed to show preferences dialog: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open preferences:\n{e}")

    def _show_analysis_config(self):
        """Show the global analysis configuration dialog."""
        try:
            from .analysis_config_dialog import AnalysisConfigDialog
            dialog = AnalysisConfigDialog(self)
            if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                # If accepted, we might want to notify active tabs to refresh if they are using defaults
                # But typically defaults apply to NEW actions or Reset.
                # Just log for now.
                log.info("Global analysis defaults updated.")
                self.status_bar.showMessage("Global analysis defaults updated.", 3000)
        except Exception as e:
            log.error(f"Failed to show analysis config dialog: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open configuration:\n{e}")

    def _show_popup_windows(self):
        """Show/restore all popup windows from analysis tabs."""
        log.debug("Show popup windows action triggered")

        popup_count = 0

        # Check if analyser_tab exists
        if hasattr(self, "analyser_tab") and self.analyser_tab:
            # Check for _loaded_analysis_tabs list (AnalyserTab is QWidget now)
            if hasattr(self.analyser_tab, "_loaded_analysis_tabs"):
                for analysis_tab in self.analyser_tab._loaded_analysis_tabs:
                    if hasattr(analysis_tab, "_popup_windows"):
                        for popup in analysis_tab._popup_windows:
                            if popup and not popup.isVisible():
                                popup.show()
                                popup_count += 1
                            elif popup and popup.isVisible():
                                # Bring to front if already visible
                                popup.raise_()
                                popup.activateWindow()
                                popup_count += 1
            # Fallback for legacy QTabWidget structure
            elif hasattr(self.analyser_tab, "count"):
                for i in range(self.analyser_tab.count()):
                    analysis_tab = self.analyser_tab.widget(i)
                    if hasattr(analysis_tab, "_popup_windows"):
                        for popup in analysis_tab._popup_windows:
                            if popup and not popup.isVisible():
                                popup.show()
                                popup_count += 1
                            elif popup and popup.isVisible():
                                # Bring to front if already visible
                                popup.raise_()
                                popup.activateWindow()
                                popup_count += 1

        if popup_count > 0:
            self.status_bar.showMessage(f"Restored {popup_count} popup window(s)", 3000)
            log.debug(f"Restored {popup_count} popup windows")
        else:
            QtWidgets.QMessageBox.information(
                self,
                "No Popup Windows",
                "No analysis popup windows are currently open.\n\n"
                "Popup windows are created when you run analyses that display\n"
                "additional visualizations (like F-I curves, phase planes, etc.).",
            )
            log.debug("No popup windows to restore")

    # --- Background Data Loading Signal Handlers ---

    def _on_loading_started(self, file_path: str):
        """Handle signal when file loading starts."""
        log.debug(f"Background loading started for: {file_path}")
        self.status_bar.showMessage(f"Loading {Path(file_path).name}...", 0)  # 0 = no timeout

    def _on_loading_progress(self, progress: int):
        """Handle loading progress updates."""
        # Update status bar with progress
        current_msg = self.status_bar.currentMessage()
        if "Loading" in current_msg:
            self.status_bar.showMessage(f"{current_msg} ({progress}%)", 0)

    def _on_data_ready(self, recording_data: Recording):
        """Handle successful data loading."""
        log.debug(f"Background loading completed successfully for: {recording_data.source_file.name}")

        try:
            # Get the file list and current index from the current state
            # These should have been set when _load_in_explorer was called
            if hasattr(self, "_pending_file_list") and hasattr(self, "_pending_current_index"):
                file_list = self._pending_file_list
                current_index = self._pending_current_index

                # Clear the pending state
                delattr(self, "_pending_file_list")
                delattr(self, "_pending_current_index")

                # CRITICAL FIX: Pass the pre-loaded Recording object directly to avoid double-loading
                log.debug(
                    f"Passing pre-loaded Recording object for '{recording_data.source_file.name}' "
                    f"to ExplorerTab via SessionManager."
                )

                # Update SessionManager
                self.session_manager.set_file_context(file_list, current_index)
                self.session_manager.current_recording = recording_data

                self.tab_widget.setCurrentWidget(self.explorer_tab)

                self.status_bar.showMessage(
                    f"Loaded {recording_data.source_file.name} ({len(recording_data.channels)} channels)", 5000
                )
            else:
                log.warning("Data loaded but no pending file list found. Using single file mode.")
                # Fallback: treat as single file
                file_list = [recording_data.source_file]
                current_index = 0
                # CRITICAL FIX: Pass the pre-loaded Recording object directly to avoid double-loading
                log.debug(
                    f"Passing pre-loaded Recording object for '{recording_data.source_file.name}' "
                    f"to ExplorerTab via SessionManager."
                )

                # Update SessionManager
                self.session_manager.set_file_context(file_list, current_index)
                self.session_manager.current_recording = recording_data

                self.tab_widget.setCurrentWidget(self.explorer_tab)
                self.status_bar.showMessage(f"Loaded {recording_data.source_file.name}", 5000)

        except Exception as e:
            log.error(f"Error handling loaded data: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Data Loading Error", f"Error processing loaded data:\n{e}")
            self.status_bar.showMessage("Error processing loaded data", 5000)
        finally:
            # Update UI state
            self._update_menu_state()
            if hasattr(self, "exporter_tab") and self.exporter_tab:
                try:
                    self.exporter_tab.update_state()
                except Exception as e_export_update:
                    log.error(f"Error updating exporter tab state: {e_export_update}", exc_info=True)
            # if hasattr(self, 'analyser_tab') and self.analyser_tab:
            #     try:
            #         self.analyser_tab.update_state(self.explorer_tab._analysis_items)
            #     except Exception as e_analyse_update:
            #         log.error(f"Error updating analyser tab state: {e_analyse_update}", exc_info=True)

    def _on_data_error(self, error_message: str):
        """Handle data loading errors."""
        log.error(f"Background loading failed: {error_message}")
        QtWidgets.QMessageBox.critical(self, "File Loading Error", f"Failed to load file:\n{error_message}")
        self.status_bar.showMessage("File loading failed", 5000)

        # Clear any pending state
        if hasattr(self, "_pending_file_list"):
            delattr(self, "_pending_file_list")
        if hasattr(self, "_pending_current_index"):
            delattr(self, "_pending_current_index")

        # Update UI state
        self._update_menu_state()
        if hasattr(self, "exporter_tab") and self.exporter_tab:
            try:
                self.exporter_tab.update_state()
            except Exception as e_export_update:
                log.error(f"Error updating exporter tab state: {e_export_update}", exc_info=True)
        # if hasattr(self, 'analyser_tab') and self.analyser_tab:
        #     try:
        #         self.analyser_tab.update_state(self.explorer_tab._analysis_items)
        #     except Exception as e_analyse_update:
        #         log.error(f"Error updating analyser tab state: {e_analyse_update}", exc_info=True)

    # --- File Handling and Export Logic methods (_open_file_dialog, _load_in_explorer, _export_to_nwb) remain the same
    # as previous answer ---
    # V V V (Keep methods from previous answer here) V V V
    def _open_file_dialog(self):
        """Shows the file open dialog (single file), scans for siblings, and initiates loading."""
        if not hasattr(self, "file_io_controller") or not self.file_io_controller:
            log.error("FileIOController not initialized.")
            return

        context = self.file_io_controller.prompt_and_get_file_context()

        if context:
            selected_filepath, file_list, current_index, lazy_load_enabled = context

            # Initiate loading
            self._load_in_explorer(selected_filepath, file_list, current_index, lazy_load_enabled)
        else:
            self.status_bar.showMessage("File open action cancelled or failed.", 3000)

    # CHANGE: Signature updated to reflect the arguments passed from the modified _open_file_dialog
    def _load_in_explorer(
        self, initial_filepath_to_load: Path, file_list: List[Path], current_index: int, lazy_load: bool
    ):
        """Initiates background loading of the initial file and stores context for completion."""
        # CHANGE: Log using the clearer argument name
        log.debug(
            f"Requesting background load of initial file: {initial_filepath_to_load.name} "
            f"(from list of {len(file_list)} siblings)"
        )
        if not (hasattr(self, "explorer_tab") and self.explorer_tab):
            log.error("Cannot load file: Explorer tab not found or not initialized yet.")
            QtWidgets.QMessageBox.critical(self, "Internal Error", "Explorer tab is missing. Cannot load file.")
            self._update_menu_state()
            if hasattr(self, "exporter_tab") and self.exporter_tab:
                self.exporter_tab.update_state()
            if hasattr(self, "analyser_tab") and self.analyser_tab:
                self.analyser_tab.update_state()
            return

        if not (hasattr(self, "data_loader") and self.data_loader):
            log.error("Cannot load file: Data loader not found or not initialized yet.")
            QtWidgets.QMessageBox.critical(self, "Internal Error", "Data loader is missing. Cannot load file.")
            return

        try:
            # Store the file list and current index for use when data is ready
            self._pending_file_list = file_list
            self._pending_current_index = current_index

            # Initiate background loading using signal
            log.debug(f"Initiating background load for: {initial_filepath_to_load} (lazy_load: {lazy_load})")
            self.load_request.emit(initial_filepath_to_load, lazy_load)

        except Exception as e:
            log.error(f"Error occurred trying to initiate background load: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Load Error", f"An error occurred initiating the file load:\n{e}")

            # Clear any pending state on error
            if hasattr(self, "_pending_file_list"):
                delattr(self, "_pending_file_list")
            if hasattr(self, "_pending_current_index"):
                delattr(self, "_pending_current_index")

            # Update UI state
            self._update_menu_state()
            if hasattr(self, "exporter_tab") and self.exporter_tab:
                try:
                    self.exporter_tab.update_state()
                except Exception as e_export_update:
                    log.error(f"Error updating exporter tab state: {e_export_update}", exc_info=True)
            else:
                log.warning("Cannot update exporter tab state: Exporter tab not found.")
            # else: log.warning("Cannot update analyser tab state: Analyser tab not found.")

    def _on_analyser_load_file_request(self, file_path_str: str):
        """Handle request from AnalyserTab to load a specific file."""
        try:
            file_path = Path(file_path_str)
            if not file_path.exists():
                QtWidgets.QMessageBox.warning(self, "File Not Found", f"The file could not be found:\n{file_path}")
                return
            
            log.debug(f"MainWindow received request to load: {file_path}")
            
            # Use _load_in_explorer to handle the loading
            # Treat as single file context if not already in list, or just load it.
            # _load_in_explorer expects: initial_filepath, file_list, index, lazy_load
            self._load_in_explorer(file_path, [file_path], 0, False)
            
        except Exception as e:
            log.error(f"Error handling analyser load request: {e}")

    def _export_to_nwb(self):
        """Handles exporting the current recording (from Explorer tab) to NWB."""
        log.debug("Export to NWB action triggered.")
        if not hasattr(self, "explorer_tab") or not self.explorer_tab:
            log.error("Cannot export: Explorer tab not found.")
            QtWidgets.QMessageBox.critical(self, "Internal Error", "Explorer tab is missing. Cannot export.")
            return

        current_recording = self.explorer_tab.get_current_recording()
        if not current_recording:
            log.warning("Export requested but no recording loaded in Explorer tab.")
            QtWidgets.QMessageBox.warning(self, "Export Error", "No recording data loaded in Explorer tab to export.")
            return

        log.debug(f"Preparing to export recording from: {current_recording.source_file.name}")

        # Suggest Filename & Get Save Location (using QSettings)
        default_filename = current_recording.source_file.with_suffix(".nwb").name
        last_export_dir = self.settings.value(
            "lastExportDirectory", str(current_recording.source_file.parent), type=str
        )
        # Use os.path.join for robust cross-platform default path suggestion
        default_save_path = os.path.join(last_export_dir, default_filename)

        output_filepath_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save NWB File", dir=default_save_path, filter="NWB Files (*.nwb)"
        )

        if not output_filepath_str:
            log.debug("NWB export cancelled by user.")
            self.status_bar.showMessage("NWB export cancelled.", 3000)
            return

        output_filepath = Path(output_filepath_str)
        # Save the chosen directory for next time
        self.settings.setValue("lastExportDirectory", str(output_filepath.parent))

        # Prepare Metadata for Dialog (same logic as original)
        default_identifier = str(uuid.uuid4())
        # Ensure session_start_time_dt attribute exists before accessing
        default_start_time_naive = getattr(current_recording, "session_start_time_dt", datetime.now())

        aware_start_time = timezone.utc  # Default fallback
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
            aware_start_time = default_start_time_naive  # Time from recording is already aware

        # Show Metadata Dialog
        dialog = NwbMetadataDialog(default_identifier, aware_start_time, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            nwb_metadata = dialog.get_metadata()
            if nwb_metadata is None:  # Validation failed in dialog
                log.error("Metadata dialog accepted but returned None (validation failed).")
                self.status_bar.showMessage("Metadata validation failed.", 3000)
                return
            log.debug(f"NWB metadata collected: {nwb_metadata}")
        else:
            log.debug("NWB export cancelled during metadata input.")
            self.status_bar.showMessage("NWB export cancelled.", 3000)
            return

        # Perform Export (using self.nwb_exporter)
        self.status_bar.showMessage(f"Exporting NWB to '{output_filepath.name}'...")
        QtWidgets.QApplication.processEvents()  # Keep UI responsive during export if possible

        try:
            # nwb_exporter is already instantiated and available via self
            self.nwb_exporter.export(current_recording, output_filepath, nwb_metadata)
            log.debug(f"Successfully exported NWB file: {output_filepath}")
            self.status_bar.showMessage(f"Export successful: {output_filepath.name}", 5000)
            QtWidgets.QMessageBox.information(
                self, "Export Successful", f"Data successfully saved to:\n{output_filepath}"
            )
        except (ValueError, ExportError, SynaptipyError) as e:
            log.error(f"NWB Export failed: {e}", exc_info=False)  # Log known errors concisely
            self.status_bar.showMessage(f"NWB Export failed: {e}", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export NWB file:\n{e}")
        except Exception as e:
            log.error(
                f"An unexpected error occurred during NWB Export: {e}", exc_info=True
            )  # Log unexpected errors with traceback
            self.status_bar.showMessage("Unexpected NWB Export error occurred.", 5000)
            QtWidgets.QMessageBox.critical(
                self, "NWB Export Error", f"An unexpected error occurred during export:\n{e}"
            )

    # ^ ^ ^ (Keep methods from previous answer here) ^ ^ ^

    # =========================================================================
    # Window State and Close Event
    # =========================================================================

    def _restore_window_state(self):
        """Restore window geometry, state, and user preferences."""
        log.debug("Restoring window state and preferences...")

        # Get current screen available geometry
        screen = QtWidgets.QApplication.primaryScreen()
        available_geometry = screen.availableGeometry() if screen else None

        # Restore window geometry if available
        if self.settings.contains("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
            log.debug("Restored window geometry.")

            # Validate restored geometry fits on current screen
            if available_geometry:
                current_geometry = self.geometry()
                # Check if window is mostly off-screen
                visible_width = min(current_geometry.right(), available_geometry.right()) - \
                               max(current_geometry.left(), available_geometry.left())
                visible_height = min(current_geometry.bottom(), available_geometry.bottom()) - \
                                max(current_geometry.top(), available_geometry.top())

                # If less than 50% visible, reset to fit screen
                if visible_width < current_geometry.width() * 0.5 or \
                   visible_height < current_geometry.height() * 0.5:
                    log.warning("Restored geometry doesn't fit current screen. Adjusting...")
                    # Resize to fit available screen (70% of screen)
                    new_width = min(current_geometry.width(), int(available_geometry.width() * 0.8))
                    new_height = min(current_geometry.height(), int(available_geometry.height() * 0.8))
                    self.resize(new_width, new_height)
                    # Move to visible area
                    self.move(
                        available_geometry.left() + (available_geometry.width() - new_width) // 2,
                        available_geometry.top() + (available_geometry.height() - new_height) // 2,
                    )
                    log.debug(f"Adjusted window size to {new_width}x{new_height}")

        # Restore window state if available
        if self.settings.contains("windowState"):
            self.restoreState(self.settings.value("windowState"))
            log.debug("Restored window state.")

        # Theme preference restoration removed - preserving original UI appearance

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Handles the main window close event, saving state."""
        log.debug("Close event received. Cleaning up and saving state...")

        # --- Cleanup Background Data Loader ---
        if hasattr(self, "data_loader_thread") and self.data_loader_thread:
            log.debug("Stopping background data loader thread...")
            try:
                # Disconnect signals to prevent any pending operations
                if hasattr(self, "data_loader") and self.data_loader:
                    self.data_loader.data_ready.disconnect()
                    self.data_loader.data_error.disconnect()
                    self.data_loader.loading_started.disconnect()
                    self.data_loader.loading_progress.disconnect()

                # Request thread to quit
                self.data_loader_thread.quit()

                # Wait for thread to finish (with timeout)
                if not self.data_loader_thread.wait(3000):  # 3 second timeout
                    log.warning("Data loader thread did not finish within timeout. Terminating...")
                    self.data_loader_thread.terminate()
                    self.data_loader_thread.wait(1000)  # Wait 1 more second after terminate

                log.debug("Background data loader thread cleanup complete.")
            except Exception as e:
                log.warning(f"Error during data loader thread cleanup: {e}")

        # --- Call cleanup on tabs if they exist ---
        if hasattr(self, "explorer_tab") and hasattr(
            self.explorer_tab, "cleanup"
        ):  # Define cleanup() in ExplorerTab if needed
            try:
                log.debug("Calling cleanup for ExplorerTab...")
                self.explorer_tab.cleanup()
            except Exception as e:
                log.warning(f"Error during ExplorerTab cleanup: {e}")

        if hasattr(self, "analyser_tab") and hasattr(self.analyser_tab, "cleanup"):
            try:
                log.debug("Calling cleanup for AnalyserTab...")
                self.analyser_tab.cleanup()
            except Exception as e:
                log.warning(f"Error during AnalyserTab cleanup: {e}")
        # Clear graphics layout explicitly before closing
        if (
            hasattr(self, "explorer_tab")
            and hasattr(self.explorer_tab, "graphics_layout_widget")
            and self.explorer_tab.graphics_layout_widget
        ):
            try:
                self.explorer_tab.graphics_layout_widget.clear()
                log.debug("Cleared explorer tab graphics.")
            except Exception as e:
                log.warning(f"Error clearing graphics layout during close: {e}")
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
        log.debug("Accepting close event.")
        event.accept()

    # --- ADDED: Method to store analysis results ---
    def add_saved_result(self, result_data: Dict[str, Any]):
        """Appends a dictionary containing analysis results to the central list."""
        if not isinstance(result_data, dict):
            log.error(f"Attempted to add non-dict result: {type(result_data)}")
            return

        # Add a timestamp for when the result was saved
        result_data["timestamp_saved"] = datetime.now(timezone.utc).isoformat()

        self.saved_analysis_results.append(result_data)
        log.debug(
            f"Saved analysis result ({result_data.get('analysis_type', '?')} from "
            f"{result_data.get('source_file_name', '?')}). Total saved: {len(self.saved_analysis_results)}"
        )
        # Optional: Update status bar or emit signal
        self.status_bar.showMessage(
            f"Result saved ({result_data.get('analysis_type', '?')}). Total: {len(self.saved_analysis_results)}", 3000
        )
        # Example signal (define in class header if needed):
        # self.analysis_results_updated.emit(self.saved_analysis_results)

    # --- END ADDED ---

    # Theme toggle methods removed - preserving original UI appearance

    # Plot refresh method removed - preserving original UI appearance
