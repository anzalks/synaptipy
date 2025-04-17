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
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger('Synaptipy.application.gui.analyser_tab')

class AnalyserTab(QtWidgets.QWidget):
    """Main Analyser Widget containing dynamically loaded sub-tabs."""

    def __init__(self, explorer_tab_ref: ExplorerTab, parent=None):
        super().__init__(parent)
        log.debug("Initializing Main AnalyserTab (dynamic loading)")
        self._explorer_tab = explorer_tab_ref
        self._analysis_items: List[Dict[str, Any]] = []
        self._loaded_analysis_tabs: List[BaseAnalysisTab] = []

        # --- UI References ---
        # self.source_file_label: Optional[QtWidgets.QLabel] = None # Replaced by list
        self.source_list_widget: Optional[QtWidgets.QListWidget] = None
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None

        self._setup_ui()
        self._load_analysis_tabs()
        # Connect the signal from ExplorerTab *after* UI is set up
        self._connect_explorer_signals()
        self.update_analysis_sources([]) # Initial empty state call

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Source Selection Display ---
        source_group = QtWidgets.QGroupBox("Analysis Input Set")
        source_layout = QtWidgets.QVBoxLayout(source_group)
        self.source_list_widget = QtWidgets.QListWidget()
        self.source_list_widget.setToolTip("Items added from the Explorer tab for analysis.")
        self.source_list_widget.setMaximumHeight(100) # Limit height
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
        # --- Get NeoAdapter instance --- 
        neo_adapter_instance = self._explorer_tab.neo_adapter
        if neo_adapter_instance is None:
             log.error("Cannot load analysis tabs: NeoAdapter not available from ExplorerTab.")
             # Show error in tab area
             placeholder = QtWidgets.QLabel("Error: Core NeoAdapter missing."); placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); self.sub_tab_widget.addTab(placeholder, "Error")
             return 
        # --- END Get NeoAdapter --- 
        try:
            pkg = importlib.import_module(".".join(analysis_pkg_path))
            if not hasattr(pkg, '__path__') or not pkg.__path__: log.error(f"No path for analysis pkg: {'.'.join(analysis_pkg_path)}"); return
            pkg_dir = Path(pkg.__path__[0]); log.debug(f"Scanning analysis modules in: {pkg_dir}")
            modules_found = list(pkgutil.iter_modules([str(pkg_dir)])) # Get list first
            log.debug(f"Modules found by pkgutil: {[m.name for m in modules_found]}")
            
            for finder, name, ispkg in modules_found:
                 log.debug(f"Processing module: name='{name}', ispkg={ispkg}") # Log each module attempt
                 if not ispkg and name != 'base':
                     module_name = f"{analysis_module_prefix}{name}"; 
                     log.debug(f"Attempting to import module: {module_name}") # Log before import
                     try:
                         module = importlib.import_module(module_name); 
                         log.debug(f"Successfully imported module: {module_name}") # Log after import
                         found_tab = False
                         # --- UPDATED: Look for ANALYSIS_TAB_CLASS --- 
                         tab_class = getattr(module, 'ANALYSIS_TAB_CLASS', None)
                         if tab_class and isinstance(tab_class, type) and issubclass(tab_class, BaseAnalysisTab):
                             log.debug(f"Found analysis tab class via ANALYSIS_TAB_CLASS: {tab_class.__name__}")
                             try:
                                 # --- UPDATED: Pass neo_adapter directly --- 
                                 tab_instance = tab_class(neo_adapter=neo_adapter_instance, parent=self)
                                 tab_name = tab_instance.get_display_name()
                                 self.sub_tab_widget.addTab(tab_instance, tab_name)
                                 self._loaded_analysis_tabs.append(tab_instance); log.info(f"Loaded analysis tab: '{tab_name}'"); found_tab = True
                             except NotImplementedError as nie: log.error(f"{tab_class.__name__} missing method: {nie}")
                             except Exception as e_inst: log.error(f"Failed instantiate/add tab {tab_class.__name__}: {e_inst}", exc_info=True)
                         # --- END UPDATE ---
                         if not found_tab: log.warning(f"No ANALYSIS_TAB_CLASS constant found or it's not a BaseAnalysisTab subclass in: {module_name}")
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
                if target == 'Recording': display_text = f"File: {path_name}"
                elif target == 'Current Trial': trial_info = f" (Trial {item['trial_index'] + 1})" if item.get('trial_index') is not None else ""; display_text = f"{path_name} [{target}{trial_info}]"
                else: display_text = f"{path_name} [{target}]"
                list_item = QtWidgets.QListWidgetItem(display_text)
                list_item.setToolTip(str(item['path'])) # Show full path on hover
                self.source_list_widget.addItem(list_item)

        # Trigger state update for all sub-tabs
        self.update_state()

    # --- Update State Method ---
    def update_state(self, _=None): # Can ignore argument if called directly or by simple signals
        """Updates the state of all loaded sub-tabs based on the current analysis list."""
        # Update all loaded sub-tabs, passing only the list of analysis items
        log.debug(f"Updating state for {len(self._loaded_analysis_tabs)} sub-tabs with {len(self._analysis_items)} analysis items.")
        for tab in self._loaded_analysis_tabs:
             try:
                 # Pass only the analysis items list
                 tab.update_state(self._analysis_items)
             except Exception as e_update:
                 log.error(f"Error updating state for tab '{tab.get_display_name()}': {e_update}", exc_info=True)

    # --- Cleanup ---
    def cleanup(self):
        log.debug("Cleaning up main AnalyserTab and sub-tabs.")
        for tab in self._loaded_analysis_tabs:
            try: tab.cleanup()
            except Exception as e_cleanup: log.error(f"Error during cleanup for tab '{tab.get_display_name()}': {e_cleanup}")
        self._loaded_analysis_tabs = []