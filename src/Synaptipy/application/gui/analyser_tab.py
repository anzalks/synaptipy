# src/Synaptipy/application/gui/analyser_tab.py
# (Keep imports: logging, pkgutil, importlib, Path, typing, PySide6, BaseAnalysisTab, ExplorerTab, Recording)
import logging
import pkgutil
import importlib
from pathlib import Path
from typing import Optional, List, Dict, Any # Add Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets

from .analysis_tabs.base import BaseAnalysisTab
from .explorer_tab import ExplorerTab
from Synaptipy.core.data_model import Recording

log = logging.getLogger('Synaptipy.application.gui.analyser_tab')

class AnalyserTab(QtWidgets.QWidget):
    """Main Analyser Widget containing dynamically loaded sub-tabs."""

    def __init__(self, explorer_tab_ref: ExplorerTab, parent=None):
        super().__init__(parent)
        log.debug("Initializing Main AnalyserTab (dynamic loading)")
        self._explorer_tab = explorer_tab_ref
        self._current_recording_for_ui: Optional[Recording] = None # Recording used to populate UI (e.g., channels)
        self._analysis_items: List[Dict[str, Any]] = [] # The list of selected items from ExplorerTab
        self._loaded_analysis_tabs: List[BaseAnalysisTab] = []

        # --- UI References ---
        # self.source_file_label: Optional[QtWidgets.QLabel] = None # Replaced by list
        self.source_list_widget: Optional[QtWidgets.QListWidget] = None
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None

        self._setup_ui()
        self._load_analysis_tabs()
        # Connect the signal from ExplorerTab *after* UI is set up
        self._connect_explorer_signals()
        self.update_state([]) # Initial empty state

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Source Selection Display ---
        source_group = QtWidgets.QGroupBox("Analysis Input Set")
        source_layout = QtWidgets.QVBoxLayout(source_group)
        self.source_list_widget = QtWidgets.QListWidget()
        self.source_list_widget.setToolTip("Items added from the Explorer tab for analysis.")
        self.source_list_widget.setFixedHeight(100) # Limit height
        source_layout.addWidget(self.source_list_widget)
        main_layout.addWidget(source_group)

        # --- Sub-Tab Widget ---
        self.sub_tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.sub_tab_widget, stretch=1)

        self.setLayout(main_layout)
        log.debug("Main AnalyserTab UI setup complete.")

    def _connect_explorer_signals(self):
        """Connect to signals from the Explorer tab."""
        log.debug("Connecting AnalyserTab to ExplorerTab signals...")
        self._explorer_tab.analysis_set_changed.connect(self.update_analysis_sources)

    def _load_analysis_tabs(self):
        # ... (Dynamic loading logic remains exactly the same as the previous correct version) ...
        log.info("Loading analysis sub-tabs...")
        self._loaded_analysis_tabs = []
        analysis_pkg_path = ["Synaptipy", "application", "gui", "analysis_tabs"]
        analysis_module_prefix = ".".join(analysis_pkg_path) + "."
        try:
            pkg = importlib.import_module(".".join(analysis_pkg_path))
            if not hasattr(pkg, '__path__') or not pkg.__path__: log.error(f"No path for analysis pkg: {'.'.join(analysis_pkg_path)}"); return
            pkg_dir = Path(pkg.__path__[0]); log.debug(f"Scanning analysis modules in: {pkg_dir}")
            for finder, name, ispkg in pkgutil.iter_modules([str(pkg_dir)]):
                 if not ispkg and name != 'base':
                     module_name = f"{analysis_module_prefix}{name}"; log.debug(f"Loading module: {module_name}")
                     try:
                         module = importlib.import_module(module_name); found_tab = False
                         for item_name in dir(module):
                             item = getattr(module, item_name)
                             if isinstance(item, type) and item.__module__ == module_name and issubclass(item, BaseAnalysisTab):
                                 log.debug(f"Found analysis tab class: {item.__name__}")
                                 try:
                                     tab_instance = item(explorer_tab_ref=self._explorer_tab, parent=self) # Pass explorer ref
                                     tab_name = tab_instance.get_display_name()
                                     self.sub_tab_widget.addTab(tab_instance, tab_name)
                                     self._loaded_analysis_tabs.append(tab_instance); log.info(f"Loaded analysis tab: '{tab_name}'"); found_tab = True; break
                                 except NotImplementedError as nie: log.error(f"{item.__name__} missing method: {nie}")
                                 except Exception as e_inst: log.error(f"Failed instantiate/add tab {item.__name__}: {e_inst}", exc_info=True)
                         if not found_tab: log.warning(f"No BaseAnalysisTab subclass found in: {module_name}")
                     except ImportError as e_imp: log.error(f"Failed import module '{module_name}': {e_imp}", exc_info=True)
                     except Exception as e_load: log.error(f"Failed load/process module '{module_name}': {e_load}", exc_info=True)
        except ModuleNotFoundError: log.error(f"Could not find analysis pkg path: {'.'.join(analysis_pkg_path)}")
        except Exception as e_pkg: log.error(f"Failed discovery analysis tabs: {e_pkg}", exc_info=True)
        if not self._loaded_analysis_tabs:
             log.warning("No analysis sub-tabs loaded."); placeholder = QtWidgets.QLabel("No analysis modules found."); placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); self.sub_tab_widget.addTab(placeholder, "Info")


    # --- Slot for Explorer Signal ---
    @QtCore.Slot(list)
    def update_analysis_sources(self, analysis_items: List[Dict[str, Any]]):
        """
        Called when the analysis set changes in the ExplorerTab.
        Updates the list widget and internal state.
        """
        log.info(f"Received updated analysis set with {len(analysis_items)} items.")
        self._analysis_items = analysis_items # Store the latest list

        # Update the List Widget display
        self.source_list_widget.clear()
        if not analysis_items:
            self.source_list_widget.addItem("No items selected for analysis.")
            self.source_list_widget.setEnabled(False)
        else:
            self.source_list_widget.setEnabled(True)
            for item in analysis_items:
                path_name = item['path'].name
                target = item['target_type']
                trial_info = f" (Trial {item['trial_index'] + 1})" if item['target_type'] == "Current Trial" else ""
                display_text = f"{path_name} [{target}{trial_info}]"
                list_item = QtWidgets.QListWidgetItem(display_text)
                list_item.setToolTip(str(item['path'])) # Show full path on hover
                self.source_list_widget.addItem(list_item)

        # Trigger state update for all sub-tabs
        self.update_state()

    # --- Update State Method ---
    def update_state(self, _=None): # Can ignore argument if called directly or by simple signals
        """Updates the state of all loaded sub-tabs based on the current analysis list."""
        # Determine the 'representative' recording for UI population (e.g., channel lists)
        # Use the first item in the list if available, otherwise None
        self._current_recording_for_ui = None
        if self._analysis_items:
            try:
                # Attempt to read the first file to get channel info etc.
                # This re-reads, which might be slow. Alternative: get from explorer if guaranteed sync.
                first_item_path = self._analysis_items[0]['path']
                # Need access to the adapter - assuming _explorer_tab has it
                self._current_recording_for_ui = self._explorer_tab.neo_adapter.read_recording(first_item_path)
                log.debug(f"Using recording from {first_item_path.name} to populate Analyser UI.")
            except Exception as e:
                log.error(f"Failed to read first file for Analyser UI setup: {e}")
                self._current_recording_for_ui = None # Ensure it's None on error

        # Update all loaded sub-tabs, passing the representative recording (if any)
        # and the list of items they actually need to analyze
        log.debug(f"Updating state for {len(self._loaded_analysis_tabs)} sub-tabs.")
        for tab in self._loaded_analysis_tabs:
             try:
                 # Pass both the potentially loaded recording (for UI setup)
                 # and the list of analysis items
                 tab.update_state(self._current_recording_for_ui, self._analysis_items)
             except Exception as e_update:
                 log.error(f"Error updating state for tab '{tab.get_display_name()}': {e_update}", exc_info=True)

    # --- Cleanup ---
    def cleanup(self):
        log.debug("Cleaning up main AnalyserTab and sub-tabs.")
        for tab in self._loaded_analysis_tabs:
            try: tab.cleanup()
            except Exception as e_cleanup: log.error(f"Error during cleanup for tab '{tab.get_display_name()}': {e_cleanup}")
        self._loaded_analysis_tabs = []