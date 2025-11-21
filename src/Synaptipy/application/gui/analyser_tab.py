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
from .analysis_tabs.rmp_tab import BaselineAnalysisTab
from .analysis_tabs.rin_tab import RinAnalysisTab
from .analysis_tabs.event_detection_tab import EventDetectionTab
from .analysis_tabs.spike_tab import SpikeAnalysisTab
from Synaptipy.application.session_manager import SessionManager


log = logging.getLogger('Synaptipy.application.gui.analyser_tab')

class AnalysisSourceListWidget(QtWidgets.QListWidget):
    """Custom ListWidget that accepts file drops for analysis."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DropOnly)
        self.session_manager = SessionManager() # Access singleton

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
                    item = {'path': file_path, 'target_type': 'Recording', 'trial_index': None}
                    
                    # Check for duplicates
                    is_duplicate = any(existing.get('path') == file_path and existing.get('target_type') == 'Recording' for existing in current_items)
                    if not is_duplicate:
                        new_items.append(item)
                        log.info(f"Dropped file added to analysis: {file_path.name}")
            
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

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__(parent)
        log.debug("Initializing Main AnalyserTab (dynamic loading)")
        self.session_manager = SessionManager()
        self._neo_adapter = neo_adapter
        self._analysis_items: List[Dict[str, Any]] = []
        self._loaded_analysis_tabs: List[BaseAnalysisTab] = []

        # --- UI References ---
        # self.source_file_label: Optional[QtWidgets.QLabel] = None # Replaced by list
        self.source_list_widget: Optional[QtWidgets.QListWidget] = None
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None
        self.central_analysis_item_combo: Optional[QtWidgets.QComboBox] = None

        self._setup_ui()
        self._load_analysis_tabs()
        # Connect the signal from SessionManager
        self.session_manager.selected_analysis_items_changed.connect(self.update_analysis_sources)
        # Initialize with current session state
        self.update_analysis_sources(self.session_manager.selected_analysis_items)

    def _setup_ui(self):
        """Setup UI with horizontal splitter: left=analysis tabs, right=sidebar."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # --- Create Horizontal Splitter ---
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # --- LEFT PANE: Sub-Tab Widget (Analysis Tabs) ---
        self.sub_tab_widget = QtWidgets.QTabWidget()
        self.sub_tab_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )
        self.sub_tab_widget.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        self.sub_tab_widget.setMovable(True)
        
        # Add to splitter
        splitter.addWidget(self.sub_tab_widget)
        
        # --- RIGHT PANE: Sidebar with controls ---
        sidebar_widget = QtWidgets.QWidget()
        sidebar_layout = QtWidgets.QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(5, 5, 5, 5)
        sidebar_layout.setSpacing(10)
        
        # Source Selection Display
        source_group = QtWidgets.QGroupBox("Analysis Input Set")
        source_layout = QtWidgets.QVBoxLayout(source_group)
        source_layout.setContentsMargins(5, 5, 5, 5)
        source_layout.setSpacing(5)
        
        self.source_list_widget = AnalysisSourceListWidget(self)
        self.source_list_widget.setToolTip("Items added from the Explorer tab for analysis.")
        self.source_list_widget.setMinimumHeight(80)
        self.source_list_widget.setMaximumHeight(150)
        source_layout.addWidget(self.source_list_widget)
        
        sidebar_layout.addWidget(source_group)
        
        # Centralized Analysis Item Selector
        selector_group = QtWidgets.QGroupBox("Analyze Item")
        selector_layout = QtWidgets.QVBoxLayout(selector_group)
        selector_layout.setContentsMargins(5, 5, 5, 5)
        selector_layout.setSpacing(5)
        
        selector_label = QtWidgets.QLabel("Select item to analyze:")
        selector_layout.addWidget(selector_label)
        
        self.central_analysis_item_combo = QtWidgets.QComboBox()
        self.central_analysis_item_combo.setToolTip("Select the specific file or data item to analyze.")
        self.central_analysis_item_combo.currentIndexChanged.connect(self._on_central_item_selected)
        selector_layout.addWidget(self.central_analysis_item_combo)
        
        sidebar_layout.addWidget(selector_group)
        
        # Add stretch to push controls to top
        sidebar_layout.addStretch()
        
        # Add sidebar to splitter
        splitter.addWidget(sidebar_widget)
        
        # Set initial splitter sizes (70% left, 30% right)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        
        # Add splitter to main layout
        main_layout.addWidget(splitter)
        
        # Connect tab change signal
        self.sub_tab_widget.currentChanged.connect(self._on_tab_changed)
        
        self.setLayout(main_layout)
        log.debug("Main AnalyserTab UI setup complete with sidebar layout.")

    # _connect_explorer_signals removed as we use SessionManager now

    def _load_analysis_tabs(self):
        # ... (Dynamic loading logic remains exactly the same as the previous correct version) ...
        log.info("Loading analysis sub-tabs...")
        self._loaded_analysis_tabs = []
        analysis_pkg_path = ["Synaptipy", "application", "gui", "analysis_tabs"]
        analysis_module_prefix = ".".join(analysis_pkg_path) + "."
        # --- Get NeoAdapter instance --- 
        neo_adapter_instance = self._neo_adapter
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
        Updates the list widget, central combo box, and internal state.
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

        # Update the Central ComboBox
        self.central_analysis_item_combo.blockSignals(True)
        self.central_analysis_item_combo.clear()
        if not analysis_items:
            self.central_analysis_item_combo.addItem("No Analysis Items Available")
            self.central_analysis_item_combo.setEnabled(False)
        else:
            self.central_analysis_item_combo.setEnabled(True)
            for i, item in enumerate(analysis_items):
                path_name = item.get('path', Path("Unknown")).name
                target = item.get('target_type', 'Unknown')
                display_text = f"Item {i+1}: "
                if target == 'Recording': 
                    display_text += f"File: {path_name}"
                elif target == 'Current Trial': 
                    trial_info = f" (Trial {item['trial_index'] + 1})" if item.get('trial_index') is not None else ""
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
        if current_tab and isinstance(current_tab, BaseAnalysisTab):
            # Get current selection from central combo
            selected_index = self.central_analysis_item_combo.currentIndex()
            if selected_index >= 0:
                try:
                    current_tab._on_analysis_item_selected(selected_index)
                    log.debug(f"Updated {current_tab.get_display_name()} with selection index {selected_index}")
                except Exception as e:
                    log.error(f"Error updating tab on switch: {e}", exc_info=True)

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