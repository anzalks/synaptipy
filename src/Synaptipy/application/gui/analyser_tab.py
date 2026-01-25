# src/Synaptipy/application/gui/analyser_tab.py
# (Keep imports: logging, pkgutil, importlib, Path, typing, PySide6, BaseAnalysisTab, ExplorerTab, Recording)
import logging
import pkgutil
import importlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

from PySide6 import QtCore, QtGui, QtWidgets

from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers import NeoAdapter
from .analysis_tabs.base import BaseAnalysisTab
from .analysis_tabs.rmp_tab import BaselineAnalysisTab
from .analysis_tabs.rin_tab import RinAnalysisTab
from .analysis_tabs.event_detection_tab import EventDetectionTab
from .analysis_tabs.spike_tab import SpikeAnalysisTab
from Synaptipy.application.session_manager import SessionManager
from Synaptipy.shared.styling import style_button

# from Synaptipy.application.gui.batch_dialog import BatchAnalysisDialog # Imported locally to avoid circular imports?


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

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        super().__init__(parent)
        log.debug("Initializing Main AnalyserTab (dynamic loading)")
        self.session_manager = SessionManager()
        self._neo_adapter = neo_adapter
        self._settings = settings_ref
        self._analysis_items: List[Dict[str, Any]] = []
        self._loaded_analysis_tabs: List[BaseAnalysisTab] = []

        # --- UI References ---
        # self.source_file_label: Optional[QtWidgets.QLabel] = None # Replaced by list
        self.source_list_widget: Optional[QtWidgets.QListWidget] = None
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None
        self.central_analysis_item_combo: Optional[QtWidgets.QComboBox] = None
        self.splitter: Optional[QtWidgets.QSplitter] = None

        self._setup_ui()
        self._restore_state()  # Restore splitter state
        self._load_analysis_tabs()
        # Connect the signal from SessionManager
        self.session_manager.selected_analysis_items_changed.connect(self.update_analysis_sources)
        # Initialize with current session state
        self.update_analysis_sources(self.session_manager.selected_analysis_items)

    def _setup_ui(self):
        """Setup UI with sub-tabs only. Global controls are injected into each tab's left panel."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
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

    def _load_analysis_tabs(self):
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
                if not ispkg and name != "base":
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
                                f"No ANALYSIS_TAB_CLASS constant found or it's not a BaseAnalysisTab subclass in: {module_name}"
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
        from Synaptipy.core.analysis.registry import AnalysisRegistry
        from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab

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
    def _on_batch_analysis_clicked(self):
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

                    # Handle special case for EventDetectionTab which returns registry_key in params
                    if "registry_key" in params:
                        registry_name = params.pop("registry_key")

                    # Remove internal keys
                    params.pop("method_display", None)

                    if registry_name:
                        pipeline_config = [
                            {"analysis": registry_name, "scope": "all_trials", "params": params}  # Default scope
                        ]
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
        # def __init__(self, files: List[Path], pipeline_config: Optional[List[Dict[str, Any]]] = None, default_channels: Optional[List[str]] = None, parent=None):

        dialog = BatchAnalysisDialog(
            files=files_to_process, pipeline_config=pipeline_config, default_channels=default_channels, parent=self
        )
        dialog.exec()

    # --- Slot for Explorer Signal ---
    @QtCore.Slot(list)
    def update_analysis_sources(self, analysis_items: List[Dict[str, Any]]):
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
    def _on_tab_changed(self, tab_index: int):
        """
        Called when user switches between analysis tabs.
        Updates the newly visible tab with the current combo selection.
        """
        log.debug(f"Analysis tab changed to index: {tab_index}")
        if tab_index < 0:
            return

        current_tab = self.sub_tab_widget.widget(tab_index)

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
                        f"Skipping tab update: invalid combo index {selected_index} (items count: {len(self._analysis_items)})"
                    )
            else:
                log.debug(
                    f"Skipping tab update: combo box not ready (enabled={self.central_analysis_item_combo.isEnabled()}, count={self.central_analysis_item_combo.count()}, items={len(self._analysis_items)})"
                )

    # --- Update State Method ---
    def update_state(self, _=None):  # Can ignore argument if called directly or by simple signals
        """Updates the state of all loaded sub-tabs based on the current analysis list."""
        # Update all loaded sub-tabs, passing only the list of analysis items
        log.debug(
            f"Updating state for {len(self._loaded_analysis_tabs)} sub-tabs with {len(self._analysis_items)} analysis items."
        )
        for tab in self._loaded_analysis_tabs:
            try:
                # Pass only the analysis items list
                tab.update_state(self._analysis_items)
            except Exception as e_update:
                log.error(f"Error updating state for tab '{tab.get_display_name()}': {e_update}", exc_info=True)

    # --- Cleanup ---
    def cleanup(self):
        log.debug("Cleaning up main AnalyserTab and sub-tabs.")
        self._save_state()  # Save splitter state
        for tab in self._loaded_analysis_tabs:
            try:
                tab.cleanup()
            except Exception as e_cleanup:
                log.error(f"Error during cleanup for tab '{tab.get_display_name()}': {e_cleanup}")
        self._loaded_analysis_tabs = []

    # --- State Persistence ---
    def _save_state(self):
        """Save UI state (splitter position) to settings."""
        if self._settings and self.splitter:
            try:
                self._settings.setValue("AnalyserTab/splitterState", self.splitter.saveState())
                log.debug("Saved AnalyserTab splitter state.")
            except Exception as e:
                log.error(f"Failed to save AnalyserTab state: {e}")

    def _restore_state(self):
        """Restore UI state (splitter position) from settings."""
        if self._settings and self.splitter:
            try:
                state = self._settings.value("AnalyserTab/splitterState")
                if state:
                    self.splitter.restoreState(state)
                    log.debug("Restored AnalyserTab splitter state.")
            except Exception as e:
                log.error(f"Failed to restore AnalyserTab state: {e}")
