# src/Synaptipy/application/gui/analyser_tab.py
# (Keep imports: logging, pkgutil, importlib, Path, typing, PySide6, BaseAnalysisTab, ExplorerTab, Recording)
import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from PySide6 import QtCore, QtGui, QtWidgets

from Synaptipy.application.session_manager import SessionManager
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.shared.styling import style_button

from .analysis_tabs.base import BaseAnalysisTab

# from Synaptipy.application.gui.batch_dialog import BatchAnalysisDialog  # Imported locally to avoid circular imports?


log = logging.getLogger(__name__)


class AnalysisSourceListWidget(QtWidgets.QListWidget):
    """Custom ListWidget that accepts file drops for analysis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DropOnly)
        self.session_manager = SessionManager()  # Access singleton

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            new_items = []
            current_items = self.session_manager.selected_analysis_items

            for url in urls:
                file_path = Path(url.toLocalFile())
                if file_path.is_file():
                    # Create analysis item
                    item = {"path": file_path, "target_type": "Recording", "trial_index": None}

                    # Check for duplicates
                    is_duplicate = any(
                        existing.get("path") == file_path and existing.get("target_type") == "Recording"
                        for existing in current_items
                    )
                    if not is_duplicate:
                        new_items.append(item)
                        log.debug(f"Dropped file added to analysis: {file_path.name}")

            if new_items:
                # Update SessionManager (append new items)
                updated_list = current_items + new_items
                self.session_manager.selected_analysis_items = updated_list
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()


class AnalyserTab(QtWidgets.QWidget):
    """Main Analyser Widget containing dynamically loaded sub-tabs."""

    # Signal to request loading a file (e.g. from Batch Dialog result)
    load_file_requested = QtCore.Signal(str)

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        super().__init__(parent)
        log.debug("Initializing Main AnalyserTab (dynamic loading)")
        self.session_manager = SessionManager()
        self._neo_adapter = neo_adapter
        self._settings = settings_ref
        self._analysis_items: List[Dict[str, Any]] = []
        self._loaded_analysis_tabs: List[BaseAnalysisTab] = []

        # --- Global Preprocessing State ---
        self._global_preprocessing_settings: Optional[Dict[str, Any]] = None
        self._global_preprocessing_confirmed: bool = False  # Tracks if user confirmed for this session
        self._preprocessing_popup_active: bool = False  # Prevent double popups

        # --- UI References ---
        # self.source_file_label: Optional[QtWidgets.QLabel] = None  # Replaced by list
        self.source_list_widget: Optional[QtWidgets.QListWidget] = None
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None
        self.central_analysis_item_combo: Optional[QtWidgets.QComboBox] = None
        self.splitter: Optional[QtWidgets.QSplitter] = None

        self._setup_ui()
        self._load_analysis_tabs()
        # Connect the signal from SessionManager
        self.session_manager.selected_analysis_items_changed.connect(self.update_analysis_sources)
        self.session_manager.preprocessing_settings_changed.connect(self._on_session_preprocessing_changed)
        # Initialize with current session state
        self.update_analysis_sources(self.session_manager.selected_analysis_items)

        # Track last active tab for zoom syncing
        self._last_active_tab = None

    # --- Global Preprocessing Methods ---
    def get_global_preprocessing(self) -> Optional[Dict[str, Any]]:
        """Returns the currently active global preprocessing settings."""
        return self._global_preprocessing_settings

    def set_global_preprocessing(self, settings: Optional[Dict[str, Any]]):  # noqa: C901
        """
        Sets global preprocessing and propagates to all sub-tabs.
        Called by sub-tabs when user applies preprocessing.
        Supports multiple filters - same filter type replaces, different types accumulate.
        """
        if settings is None:
            # Clear all
            self._global_preprocessing_settings = None
            # Reset the confirmation flag so the popup can re-appear
            # if preprocessing is later re-applied from the Explorer tab
            self._global_preprocessing_confirmed = False
        elif "baseline" in settings or "filters" in settings:
            # Already in slot format
            self._global_preprocessing_settings = settings
        else:
            # Single step - accumulate by type
            step_type = settings.get("type")
            if self._global_preprocessing_settings is None:
                self._global_preprocessing_settings = {}

            if step_type == "baseline":
                self._global_preprocessing_settings["baseline"] = settings
            elif step_type == "filter":
                filter_method = settings.get("method", "unknown")
                if "filters" not in self._global_preprocessing_settings:
                    self._global_preprocessing_settings["filters"] = {}
                # Same filter method replaces old one
                self._global_preprocessing_settings["filters"][filter_method] = settings

        log.debug(f"Global preprocessing set: {self._global_preprocessing_settings is not None}")

        # Propagate full accumulated settings to all loaded sub-tabs
        for tab in self._loaded_analysis_tabs:
            if hasattr(tab, "apply_global_preprocessing"):
                try:
                    tab.apply_global_preprocessing(self._global_preprocessing_settings)
                except Exception as e:
                    log.error(f"Failed to apply global preprocessing to {tab.get_display_name()}: {e}")

    def _show_global_preprocessing_popup(self, settings: Dict[str, Any]) -> bool:
        """
        Shows popup asking user if they want to apply preprocessing globally.
        Returns True if user wants global application, False otherwise.
        """
        from PySide6.QtWidgets import QMessageBox

        # Build description of current preprocessing
        # Settings use 'type' and 'method' keys
        settings_type = settings.get("type", "unknown")
        method = settings.get("method", "unknown")

        if settings_type == "baseline":
            settings_desc = f"Baseline: {method}"
        elif settings_type == "filter":
            cutoff = settings.get("cutoff", "")
            settings_desc = f"Filter: {method} ({cutoff} Hz)"
        else:
            settings_desc = f"{settings_type}: {method}"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Apply Preprocessing Globally?")
        msg_box.setText(f"Preprocessing is active:\n{settings_desc}")
        msg_box.setInformativeText(
            "Do you want to apply this preprocessing to all files during analysis?\n\n"
            "This will be applied across all analysis sub-tabs."
        )

        apply_btn = msg_box.addButton("Apply Globally", QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton("This Tab Only", QMessageBox.ButtonRole.RejectRole)
        reset_btn = msg_box.addButton("Reset Preprocessing", QMessageBox.ButtonRole.DestructiveRole)

        msg_box.setDefaultButton(apply_btn)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == apply_btn:
            return True
        elif clicked == reset_btn:
            # Reset preprocessing
            self._global_preprocessing_settings = None
            self._global_preprocessing_confirmed = False
            for tab in self._loaded_analysis_tabs:
                if hasattr(tab, "apply_global_preprocessing"):
                    tab.apply_global_preprocessing(None)
            return False
        else:
            # This Tab Only - don't set global
            return False

    def showEvent(self, event):
        """Override to check for pending preprocessing confirmation."""
        super().showEvent(event)

        # Check SessionManager for preprocessing settings from Explorer
        session_preprocessing = self.session_manager.preprocessing_settings
        if session_preprocessing and not self._global_preprocessing_confirmed:
            # Store locally and trigger popup
            self._global_preprocessing_settings = session_preprocessing
            # Defer popup to after event processing
            QtCore.QTimer.singleShot(100, self._check_preprocessing_on_enter)

    def _check_preprocessing_on_enter(self):
        """Called when entering Analyser tab to check preprocessing state."""
        if getattr(self, "_preprocessing_popup_active", False):
            return

        session_preprocessing = self.session_manager.preprocessing_settings
        if session_preprocessing and not self._global_preprocessing_confirmed:
            self._preprocessing_popup_active = True
            try:
                self._global_preprocessing_settings = session_preprocessing
                apply_globally = self._show_global_preprocessing_popup(session_preprocessing)
                if apply_globally:
                    self._global_preprocessing_confirmed = True
                    # Propagate to all tabs
                    self.set_global_preprocessing(session_preprocessing)
                else:
                    # Don't show popup again for this session (until reset)
                    self._global_preprocessing_confirmed = True
            finally:
                self._preprocessing_popup_active = False

        # Process deferred initial selection if any
        if getattr(self, "_pending_initial_selection", False):
            log.debug("Processing deferred initial selection after preprocessing check.")
            self._pending_initial_selection = False
            if self.central_analysis_item_combo.count() > 0:
                self._on_central_item_selected(0)

    @QtCore.Slot(object)
    def _on_session_preprocessing_changed(self, settings: Optional[Dict[str, Any]]):
        """
        Handle updates to global preprocessing from SessionManager (e.g. from ExplorerTab).
        If global preprocessing is already confirmed/active, we update and propagate immediately.
        """
        # Always keep local reference in sync if we are in a 'confirmed' state or if it matches
        # logic where we want to track it.
        # If we haven't confirmed yet, _check_preprocessing_on_enter will handle it.
        # But if we HAVE confirmed, we must update active settings.

        if self._global_preprocessing_confirmed:
            log.debug("Session preprocessing changed. Updating active global settings.")
            self._global_preprocessing_settings = settings
            # Propagate to all tabs
            self.set_global_preprocessing(settings)
        else:
            # If not confirmed, just update local ref so next check might see it?
            # Actually _check_preprocessing_on_enter reads from SessionManager directly.
            # So we don't strictly need to do anything here unless we want to force a popup?
            # Let's just log.
            log.debug("Session preprocessing changed (not yet confirmed globally).")

    def _setup_ui(self):
        """Setup UI with sub-tabs only. Global controls are injected into each tab's left panel."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 30, 10, 10)  # Top margin prevents macOS traffic light clipping
        main_layout.setSpacing(5)

        # --- Top Toolbar with Batch Analysis Button ---
        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 5)

        # Batch Analysis Button
        self.batch_analysis_btn = QtWidgets.QPushButton("Run Batch Analysis...")
        self.batch_analysis_btn.setToolTip("Run analysis on multiple files.")
        self.batch_analysis_btn.clicked.connect(self._on_batch_analysis_clicked)
        style_button(self.batch_analysis_btn, style="primary")
        toolbar_layout.addWidget(self.batch_analysis_btn)

        # Copy Methods Button
        self.copy_methods_btn = QtWidgets.QPushButton("Copy Methods Text")
        self.copy_methods_btn.setToolTip("Copy a description of the current analysis methods to clipboard.")
        self.copy_methods_btn.clicked.connect(self._copy_methods_to_clipboard)
        style_button(self.copy_methods_btn, style="secondary")
        toolbar_layout.addWidget(self.copy_methods_btn)

        toolbar_layout.addStretch()

        toolbar_layout.addStretch()

        # Info label showing number of files
        self.files_info_label = QtWidgets.QLabel("No files loaded")
        self.files_info_label.setStyleSheet("color: gray;")
        toolbar_layout.addWidget(self.files_info_label)

        main_layout.addLayout(toolbar_layout)

        # Create Global Controls widgets (they will be injected into the active tab)
        self.source_list_widget = AnalysisSourceListWidget(self)
        self.source_list_widget.setToolTip("Items added from the Explorer tab for analysis.")
        self.source_list_widget.setMinimumHeight(60)
        self.source_list_widget.setMaximumHeight(120)

        self.central_analysis_item_combo = QtWidgets.QComboBox()
        self.central_analysis_item_combo.setToolTip("Select the specific file or data item to analyze.")
        self.central_analysis_item_combo.currentIndexChanged.connect(self._on_central_item_selected)

        # Connect Sidebar Selection Signal (Cross-Tab Navigation)
        self.source_list_widget.currentItemChanged.connect(self._on_sidebar_selection_changed)

        # --- Sub-Tab Widget (Analysis Tabs) - Takes full width ---
        self.sub_tab_widget = QtWidgets.QTabWidget()
        self.sub_tab_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self.sub_tab_widget.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        self.sub_tab_widget.setMovable(True)

        # Add sub_tab_widget directly to main layout
        main_layout.addWidget(self.sub_tab_widget)

        # Connect tab change signal
        self.sub_tab_widget.currentChanged.connect(self._on_tab_changed)

        self.setLayout(main_layout)
        log.debug("Main AnalyserTab UI setup complete (Global controls will be injected into tabs).")

    # _connect_explorer_signals removed as we use SessionManager now

    def _load_analysis_tabs(self):  # noqa: C901
        # ... (Dynamic loading logic remains exactly the same as the previous correct version) ...
        log.debug("Loading analysis sub-tabs...")
        # Block signals during tab loading to prevent premature currentChanged signals
        # before central_analysis_item_combo is populated
        self.sub_tab_widget.blockSignals(True)
        self._loaded_analysis_tabs = []
        analysis_pkg_path = ["Synaptipy", "application", "gui", "analysis_tabs"]
        analysis_module_prefix = ".".join(analysis_pkg_path) + "."
        # --- Get NeoAdapter instance ---
        neo_adapter_instance = self._neo_adapter
        if neo_adapter_instance is None:
            log.error("Cannot load analysis tabs: NeoAdapter not available from ExplorerTab.")
            # Show error in tab area
            placeholder = QtWidgets.QLabel("Error: Core NeoAdapter missing.")
            placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.sub_tab_widget.addTab(placeholder, "Error")
            self.sub_tab_widget.blockSignals(False)  # Re-enable signals before returning
            return
        # --- END Get NeoAdapter ---
        try:
            pkg = importlib.import_module(".".join(analysis_pkg_path))
            if not hasattr(pkg, "__path__") or not pkg.__path__:
                log.error(f"No path for analysis pkg: {'.'.join(analysis_pkg_path)}")
                return
            pkg_dir = Path(pkg.__path__[0])
            log.debug(f"Scanning analysis modules in: {pkg_dir}")
            modules_found = list(pkgutil.iter_modules([str(pkg_dir)]))  # Get list first
            log.debug(f"Modules found by pkgutil: {[m.name for m in modules_found]}")

            for finder, name, ispkg in modules_found:
                log.debug(f"Processing module: name='{name}', ispkg={ispkg}")  # Log each module attempt
                if not ispkg and name not in ("base", "metadata_driven"):
                    module_name = f"{analysis_module_prefix}{name}"
                    log.debug(f"Attempting to import module: {module_name}")  # Log before import
                    try:
                        module = importlib.import_module(module_name)
                        log.debug(f"Successfully imported module: {module_name}")  # Log after import
                        found_tab = False
                        # --- UPDATED: Look for ANALYSIS_TAB_CLASS ---
                        tab_class = getattr(module, "ANALYSIS_TAB_CLASS", None)
                        if tab_class and isinstance(tab_class, type) and issubclass(tab_class, BaseAnalysisTab):
                            log.debug(f"Found analysis tab class via ANALYSIS_TAB_CLASS: {tab_class.__name__}")
                            try:
                                # --- UPDATED: Pass neo_adapter directly ---
                                tab_instance = tab_class(
                                    neo_adapter=neo_adapter_instance, settings_ref=self._settings, parent=self
                                )
                                tab_name = tab_instance.get_display_name()
                                self.sub_tab_widget.addTab(tab_instance, tab_name)
                                self._loaded_analysis_tabs.append(tab_instance)
                                log.debug(f"Loaded analysis tab: '{tab_name}'")
                                found_tab = True
                            except NotImplementedError as nie:
                                log.error(f"{tab_class.__name__} missing method: {nie}")
                            except Exception as e_inst:
                                log.error(f"Failed instantiate/add tab {tab_class.__name__}: {e_inst}", exc_info=True)
                        # --- END UPDATE ---
                        if not found_tab:
                            log.warning(
                                f"No ANALYSIS_TAB_CLASS constant found or it's not a BaseAnalysisTab "
                                f"subclass in: {module_name}"
                            )
                    except ImportError as e_imp:
                        log.error(f"Failed import module '{module_name}': {e_imp}", exc_info=True)
                    except Exception as e_load:
                        log.error(f"Failed load/process module '{module_name}': {e_load}", exc_info=True)
        except ModuleNotFoundError:
            log.error(f"Could not find analysis pkg path: {'.'.join(analysis_pkg_path)}")
        except Exception as e_pkg:
            log.error(f"Failed discovery analysis tabs: {e_pkg}", exc_info=True)
        finally:
            # Re-enable signals after all tabs are loaded
            self.sub_tab_widget.blockSignals(False)
        # --- NEW: Load Metadata-Driven Tabs for remaining registered analyses ---
        # Import the full core.analysis package to trigger all @AnalysisRegistry.register
        # decorators.  Importing only the registry sub-module (registry.py) is NOT
        # enough — the individual analysis modules (basic_features, spike_analysis, …)
        # must be executed so their decorators run and populate the registry.
        # On Windows the import order never causes this package to be loaded earlier,
        # so without this explicit import the registry is always empty at this point.
        import Synaptipy.core.analysis  # noqa: F401 — side-effect: registers all built-in analyses
        from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
        from Synaptipy.core.analysis.registry import AnalysisRegistry

        registered_analyses = AnalysisRegistry.list_registered()

        # Collect all covered analysis names from loaded manual tabs
        loaded_registry_names = set()
        for tab in self._loaded_analysis_tabs:
            loaded_registry_names.add(tab.get_registry_name())
            if hasattr(tab, "get_covered_analysis_names"):
                loaded_registry_names.update(tab.get_covered_analysis_names())

        for analysis_name in registered_analyses:
            if analysis_name not in loaded_registry_names:
                log.debug(f"Loading metadata-driven tab for: {analysis_name}")
                try:
                    tab_instance = MetadataDrivenAnalysisTab(
                        analysis_name=analysis_name,
                        neo_adapter=self._neo_adapter,
                        settings_ref=self._settings,
                        parent=self,
                    )
                    self.sub_tab_widget.addTab(tab_instance, tab_instance.get_display_name())
                    self._loaded_analysis_tabs.append(tab_instance)

                except Exception as e:
                    log.error(f"Failed to load metadata-driven tab for {analysis_name}: {e}", exc_info=True)
        # ------------------------------------------------------------------------

        if not self._loaded_analysis_tabs:
            log.warning("No analysis sub-tabs loaded.")
            placeholder = QtWidgets.QLabel("No analysis modules found.")
            placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.sub_tab_widget.addTab(placeholder, "Info")
        else:
            # Inject global controls into the first tab initially
            first_tab = self._loaded_analysis_tabs[0]
            if hasattr(first_tab, "set_global_controls"):
                try:
                    first_tab.set_global_controls(self.source_list_widget, self.central_analysis_item_combo)
                    log.debug(f"Injected global controls into first tab: {first_tab.get_display_name()}")
                except Exception as e:
                    log.error(f"Failed to inject global controls into first tab: {e}", exc_info=True)

    # --- Batch Analysis Handler ---
    @QtCore.Slot()
    def _on_batch_analysis_clicked(self):  # noqa: C901
        """Open the Batch Analysis Dialog."""
        if not self._analysis_items:
            QtWidgets.QMessageBox.warning(self, "No Files", "Please load files in the Explorer tab first.")
            return

        # Filter for Recording items only
        recording_items = [item for item in self._analysis_items if item["target_type"] == "Recording"]
        if not recording_items:
            QtWidgets.QMessageBox.warning(
                self, "No Recordings", "No valid recording files selected for batch analysis."
            )
            return

        from Synaptipy.application.gui.batch_dialog import BatchAnalysisDialog

        # Extract files to process (Recording objects or Paths)
        # Prefer in-memory Recording objects to fix Split-Brain issues
        files_to_process = []
        for item in recording_items:
            if item.get("recording_ref"):
                files_to_process.append(item["recording_ref"])
            else:
                files_to_process.append(item["path"])

        # Ensure uniqueness (though ExplorerTab largely handles this)
        # We invoke set() but Recording objects are hashable by id, Paths by value.
        # Given ExplorerTab prevents duplicate Paths for same target type, this list should be unique per file.
        # But to be safe if multiple sources add items:
        # actually, simply passing the list is fine as BatchDialog handles list.
        # But let's keep the set() behavior for safety if logic changes elsewhere,
        # BUT set() might lose order. List is better for order.
        # Let's trust ExplorerTab uniqueness for now.

        # Gather current configuration from active tab if possible
        pipeline_config = None
        default_channels = None

        current_tab = self.sub_tab_widget.currentWidget()
        if current_tab and isinstance(current_tab, BaseAnalysisTab):
            try:
                # 1. Gather current parameters
                params = current_tab._gather_analysis_parameters()
                if params:
                    # 2. Get registry name
                    registry_name = getattr(current_tab, "get_registry_name", lambda: None)()

                    if not registry_name:
                        # Attempt to get from metadata if it's a metadata tab
                        if hasattr(current_tab, "analysis_name"):
                            registry_name = current_tab.analysis_name

                    # Handle special case for method-selector tabs which may return registry_key in params
                    if "registry_key" in params:
                        registry_name = params.pop("registry_key")

                    # Remove internal keys
                    params.pop("method_display", None)

                    if registry_name:
                        pipeline_config = [
                            {"analysis": registry_name, "scope": "all_trials", "params": params}  # Default scope
                        ]

                        # --- PREPEND Global Preprocessing ---
                        global_prep = self.get_global_preprocessing()
                        start_steps = []
                        if global_prep:
                            # Convert settings to steps
                            if "baseline" in global_prep:
                                # Baseline is a step
                                # Need to map 'method' to a registered function name

                                # Assuming the 'method' key holds the registry name or something usable.
                                start_steps.append(
                                    {
                                        "analysis": global_prep["baseline"].get("method_id", "baseline_subtraction"),
                                        "scope": "all_trials",  # Preprocessing works on raw data usually?
                                        "params": global_prep["baseline"],
                                    }
                                )

                            if "filters" in global_prep:
                                for method, settings in global_prep["filters"].items():
                                    # settings['method'] might be 'Lowpass'.
                                    # We need registered name 'lowpass_filter'.
                                    # This mapping is crucial.
                                    # For now, let's inject a "filter" task and hope Registry has it,
                                    # or we assume 'method_id' exists.

                                    # If PreprocessingWidget doesn't provide method_id, we might rely on 'method'.
                                    # Ideally, we should update PreprocessingWidget to include registry key.
                                    # But let's try to infer or use 'method_id' if present, else lowercase+underscore.

                                    analysis_name = settings.get(
                                        "method_id", settings.get("method", "").lower().replace(" ", "_")
                                    )
                                    if "filter" not in analysis_name:
                                        analysis_name += "_filter"  # basic heuristic

                                    start_steps.append(
                                        {"analysis": analysis_name, "scope": "all_trials", "params": settings}
                                    )

                        if start_steps:
                            log.debug(f"Prepending {len(start_steps)} preprocessing steps to batch pipeline.")
                            pipeline_config = start_steps + pipeline_config
                        # ------------------------------------

                        log.debug(f"Pre-filling batch pipeline with settings from {current_tab.get_display_name()}")

                # 3. Get channel selection
                if hasattr(current_tab, "signal_channel_combobox") and current_tab.signal_channel_combobox:
                    channel_id = current_tab.signal_channel_combobox.currentData()
                    if channel_id is not None:
                        default_channels = [str(channel_id)]

            except Exception as e:
                log.warning(f"Could not gather batch parameters from current tab: {e}")

        # Open dialog with pre-filled config
        # Note: The init signature of BatchAnalysisDialog is (files, pipeline_config, default_channels, parent)
        # We need to make sure we match it.
        # Checking previous files... BatchAnalysisDialog declaration was:
        # def __init__(self, files: List[Path], pipeline_config: Optional[List[Dict[str, Any]]] = None,
        # default_channels: Optional[List[str]] = None, parent=None):

        dialog = BatchAnalysisDialog(
            files=files_to_process, pipeline_config=pipeline_config, default_channels=default_channels, parent=self
        )
        dialog.load_file_request.connect(self._handle_batch_load_request)
        dialog.exec()

    def _handle_batch_load_request(self, file_path, params, channel, trial):
        """
        Handle request to load a file from batch results.
        Emits signal for MainWindow to handle.
        """
        log.debug(f"Batch Analysis requested load: {file_path}")
        self.load_file_requested.emit(file_path)

        # NOTE: Channel/trial auto-selection after batch load is not possible
        # because file loading is asynchronous. The file is loaded via signal emission
        # and processed by MainWindow, so we cannot select channels here.

    @QtCore.Slot()
    def _copy_methods_to_clipboard(self):
        """Generates methods text for the current analysis result and copies to clipboard."""
        from Synaptipy.application.controllers.analysis_formatter import generate_methods_text

        current_tab = self.sub_tab_widget.currentWidget()
        if not current_tab:
            return

        # Try to find a result object on the tab
        result = None
        if hasattr(current_tab, "last_result"):
            result = current_tab.last_result
        elif hasattr(current_tab, "current_result"):
            result = current_tab.current_result

        if result:
            methods_text = generate_methods_text(result)
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(methods_text)

            # Feedback
            self.window().statusBar().showMessage("Methods description copied to clipboard.", 3000)
            log.info("Copied methods text to clipboard.")
        else:
            QtWidgets.QMessageBox.information(self, "No Result", "Run an analysis first to generate methods text.")

    # --- Slot for Explorer Signal ---
    @QtCore.Slot(list)
    def update_analysis_sources(self, analysis_items: List[Dict[str, Any]]):  # noqa: C901
        """
        Called when the analysis set changes in the ExplorerTab.
        Updates the list widget, central combo box, and internal state.
        """
        log.debug(f"Received updated analysis set with {len(analysis_items)} items.")
        self._analysis_items = analysis_items  # Store the latest list

        # Update files info label
        unique_files: Set[Path] = set()
        for item in analysis_items:
            file_path = item.get("path")
            if file_path and isinstance(file_path, Path):
                unique_files.add(file_path)

        if unique_files:
            self.files_info_label.setText(f"{len(unique_files)} file(s) loaded")
            self.files_info_label.setStyleSheet("")  # Reset to default color
        else:
            self.files_info_label.setText("No files loaded")
            self.files_info_label.setStyleSheet("color: gray;")

        # Update the List Widget display
        self.source_list_widget.clear()
        if not analysis_items:
            self.source_list_widget.addItem("No items selected for analysis.")
            self.source_list_widget.setEnabled(False)
        else:
            self.source_list_widget.setEnabled(True)
            for item in analysis_items:
                path_name = item["path"].name
                target = item["target_type"]
                if target == "Recording":
                    display_text = f"File: {path_name}"
                elif target == "Current Trial":
                    trial_info = f" (Trial {item['trial_index'] + 1})" if item.get("trial_index") is not None else ""
                    display_text = f"{path_name} [{target}{trial_info}]"
                else:
                    display_text = f"{path_name} [{target}]"
                list_item = QtWidgets.QListWidgetItem(display_text)
                list_item.setToolTip(str(item["path"]))  # Show full path on hover
                self.source_list_widget.addItem(list_item)

        # Update the Central ComboBox
        self.central_analysis_item_combo.blockSignals(True)
        self.central_analysis_item_combo.clear()
        if not analysis_items:
            self.central_analysis_item_combo.addItem("No Analysis Items Available")
            self.central_analysis_item_combo.setEnabled(False)
        else:
            self.central_analysis_item_combo.setEnabled(True)
            for i, item in enumerate(analysis_items):
                path_name = item.get("path", Path("Unknown")).name
                target = item.get("target_type", "Unknown")
                display_text = f"Item {i+1}: "
                if target == "Recording":
                    display_text += f"File: {path_name}"
                elif target == "Current Trial":
                    trial_info = f" (Trial {item['trial_index'] + 1})" if item.get("trial_index") is not None else ""
                    display_text += f"{path_name} [{target}{trial_info}]"
                else:
                    display_text += f"{path_name} [{target}]"
                self.central_analysis_item_combo.addItem(display_text)
        self.central_analysis_item_combo.blockSignals(False)

        # Trigger state update for all sub-tabs
        self.update_state()

        # Check if we should defer selection due to pending global preprocessing check
        # This prevents loading raw data before the user has a chance to apply global preprocessing
        session_preprocessing = self.session_manager.preprocessing_settings
        if session_preprocessing and not self._global_preprocessing_confirmed and analysis_items:
            log.debug("Deferring initial selection until global preprocessing check matches.")
            self._pending_initial_selection = True
            # Trigger check immediately in case we are already visible and missed the event
            QtCore.QTimer.singleShot(50, self._check_preprocessing_on_enter)
        else:
            self._pending_initial_selection = False
            # Trigger initial selection if items exist
            if analysis_items:
                self._on_central_item_selected(0)

    # --- Central Item Selection Handler ---
    @QtCore.Slot(int)
    def _on_central_item_selected(self, index: int):
        """
        Called when user changes selection in the central analysis item combo box.
        Forwards the selection to the currently active analysis tab.
        """
        log.debug(f"Central combo item selected: index={index}")
        current_tab = self.sub_tab_widget.currentWidget()
        if current_tab and isinstance(current_tab, BaseAnalysisTab):
            try:
                current_tab._on_analysis_item_selected(index)
                log.debug(f"Forwarded selection to {current_tab.get_display_name()}")
            except Exception as e:
                log.error(f"Error forwarding selection to tab: {e}", exc_info=True)

    @QtCore.Slot(int)
    def _on_tab_changed(self, tab_index: int):  # noqa: C901
        """
        Called when user switches between analysis tabs.
        Updates the newly visible tab with the current combo selection.
        """
        log.debug(f"Analysis tab changed to index: {tab_index}")
        if tab_index < 0:
            return

        current_tab = self.sub_tab_widget.widget(tab_index)

        # --- Sync Zoom from Previous Tab ---
        if hasattr(self, "_last_active_tab") and self._last_active_tab and current_tab:
            try:
                if (
                    hasattr(self._last_active_tab, "plot_widget")
                    and self._last_active_tab.plot_widget
                    and hasattr(current_tab, "plot_widget")
                    and current_tab.plot_widget
                ):

                    # Sync X-Range (Time axis) only
                    # We assume X-axis is compatible (e.g. Time vs Time)
                    x_range = self._last_active_tab.plot_widget.viewRange()[0]
                    current_tab.plot_widget.setXRange(x_range[0], x_range[1], padding=0)
                    log.debug(f"Synced X-range from previous tab: {x_range}")
            except Exception as e:
                log.warning(f"Failed to sync zoom: {e}")

        self._last_active_tab = current_tab
        # -----------------------------------

        # Inject global controls into the current tab
        if current_tab and isinstance(current_tab, BaseAnalysisTab):
            try:
                current_tab.set_global_controls(self.source_list_widget, self.central_analysis_item_combo)
                log.debug(f"Injected global controls into {current_tab.get_display_name()}")
            except Exception as e:
                log.error(f"Error injecting global controls: {e}", exc_info=True)

            # Only forward selection if combo box is enabled (has valid items) and has items
            # This prevents forwarding invalid indices during initialization before
            # update_analysis_sources() populates the combo box
            if (
                self.central_analysis_item_combo.isEnabled()
                and self.central_analysis_item_combo.count() > 0
                and len(self._analysis_items) > 0
            ):
                selected_index = self.central_analysis_item_combo.currentIndex()
                if selected_index >= 0 and selected_index < len(self._analysis_items):
                    try:
                        current_tab._on_analysis_item_selected(selected_index)
                        log.debug(f"Updated {current_tab.get_display_name()} with selection index {selected_index}")
                    except Exception as e:
                        log.error(f"Error updating tab on switch: {e}", exc_info=True)
                else:
                    log.debug(
                        f"Skipping tab update: invalid combo index {selected_index} "
                        f"(items count: {len(self._analysis_items)})"
                    )
            else:
                is_enabled = self.central_analysis_item_combo.isEnabled()
                count = self.central_analysis_item_combo.count()
                items_len = len(self._analysis_items)
                log.debug(
                    f"Skipping tab update: combo box not ready (enabled={is_enabled}, "
                    f"count={count}, items={items_len})"
                )

    # --- Update State Method ---
    def update_state(self, _=None):  # Can ignore argument if called directly or by simple signals
        """Updates the state of all loaded sub-tabs based on the current analysis list."""
        # Update all loaded sub-tabs, passing only the list of analysis items
        log.debug(
            f"Updating state for {len(self._loaded_analysis_tabs)} sub-tabs with "
            f"{len(self._analysis_items)} analysis items."
        )
        for tab in self._loaded_analysis_tabs:
            try:
                # Pass only the analysis items list
                tab.update_state(self._analysis_items)
            except Exception as e_update:
                log.error(f"Error updating state for tab '{tab.get_display_name()}': {e_update}", exc_info=True)

    # --- Cross-Tab Navigation Handler ---
    @QtCore.Slot(QtWidgets.QListWidgetItem, QtWidgets.QListWidgetItem)
    def _on_sidebar_selection_changed(self, current: QtWidgets.QListWidgetItem, previous: QtWidgets.QListWidgetItem):
        """
        Handle selection changes in the sidebar (Analysis Source List).
        If a specific trial is selected, notify the current analysis tab to highlight it.
        """
        if not current:
            return

        # Determine index in the list
        row = self.source_list_widget.row(current)
        if row < 0 or row >= len(self._analysis_items):
            return

        selected_item = self._analysis_items[row]
        target_type = selected_item.get("target_type")

        # Check if it's a specific trial selection (from Explorer expansion)
        # Note: The item dictionary structure from ExplorerTab typically is:
        # {"path": Path(...), "target_type": "Current Trial", "trial_index": 5}

        trial_index = -1
        if target_type == "Current Trial":
            trial_index = selected_item.get("trial_index", -1)

        # Forward to current tab
        current_tab = self.sub_tab_widget.currentWidget()
        if current_tab and isinstance(current_tab, BaseAnalysisTab):
            if hasattr(current_tab, "highlight_trial"):
                try:
                    current_tab.highlight_trial(trial_index)
                    log.debug(f"Highlighted trial {trial_index} in {current_tab.get_display_name()}")
                except Exception as e:
                    log.error(f"Error highlighting trial in tab: {e}")

    # --- Cleanup ---

    def cleanup(self):
        log.debug("Cleaning up main AnalyserTab and sub-tabs.")
        for tab in self._loaded_analysis_tabs:
            try:
                tab.cleanup()
            except Exception as e_cleanup:
                log.error(f"Error during cleanup for tab '{tab.get_display_name()}': {e_cleanup}")
        self._loaded_analysis_tabs = []

    # --- State Persistence ---
    # Methods removed as splitter is no longer used in this version of AnalyserTab

    def reset_current_tab_parameters(self):
        """Resets the parameters of the currently active analysis sub-tab."""
        current_tab = self.sub_tab_widget.currentWidget()
        if current_tab:
            if hasattr(current_tab, "reset_parameters"):
                current_tab.reset_parameters()
                log.info(f"Reset parameters for {current_tab.get_display_name()}")
                # Status bar update via parent if available?
                # self.window().statusBar().showMessage("Parameters reset.", 3000)
            else:
                log.warning(f"Tab '{current_tab.get_display_name()}' does not support parameter reset.")
                QtWidgets.QMessageBox.information(
                    self, "Not Supported", f"Reset is not supported for {current_tab.get_display_name()}."
                )
