# src/Synaptipy/application/gui/analysis_tabs/base.py
# -*- coding: utf-8 -*-
"""
Base class for individual analysis tab widgets. Defines the expected interface
and provides common functionality like selecting the analysis target item.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

# Use absolute path to import NeoAdapter and Recording
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.shared.error_handling import SynaptipyError, FileReadError
from Synaptipy.shared.styling import (
    style_button,
)
from Synaptipy.shared.plot_zoom_sync import PlotZoomSyncManager

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.base')

class BaseAnalysisTab(QtWidgets.QWidget):
    """Base Class for all analysis sub-tabs."""

    # Removed TRIAL_MODES as it's less relevant now

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        """
        Initialize the base analysis tab.

        Args:
            neo_adapter: Instance of the NeoAdapter for loading data.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.neo_adapter = neo_adapter
        self._analysis_items: List[Dict[str, Any]] = [] # Store the full list from AnalyserTab
        self._selected_item_index: int = -1
        # Store the currently loaded recording corresponding to the selected item (if it's a 'Recording' type)
        self._selected_item_recording: Optional[Recording] = None 
        # UI element for selecting the analysis item
        self.analysis_item_combo: Optional[QtWidgets.QComboBox] = None
        # --- ADDED: Plot Widget --- 
        self.plot_widget: Optional[pg.PlotWidget] = None
        # --- END ADDED --- 
        # --- ADDED: Save Button --- 
        self.save_button: Optional[QtWidgets.QPushButton] = None
        # --- END ADDED ---
        # --- ADDED: Zoom Sync Manager ---
        self.zoom_sync: Optional[PlotZoomSyncManager] = None
        # --- END ADDED ---
        # --- ADDED: Reset View Button ---
        self.reset_view_button: Optional[QtWidgets.QPushButton] = None
        # --- END ADDED ---
        log.debug(f"Initializing BaseAnalysisTab: {self.__class__.__name__}")

    # --- Methods for UI setup to be called by subclasses ---
    def _setup_analysis_item_selector(self, layout: QtWidgets.QLayout):
        """Adds the analysis item selection combo box to the provided layout."""
        self.analysis_item_combo = QtWidgets.QComboBox()
        self.analysis_item_combo.setToolTip("Select the specific file or data item to analyze from the set defined in Explorer.")
        # Add to layout - assumes QFormLayout is common, but works with others
        if isinstance(layout, QtWidgets.QFormLayout):
            layout.insertRow(0, "Analyze Item:", self.analysis_item_combo)
        else:
            # Fallback for other layouts (e.g., QVBoxLayout)
            hbox = QtWidgets.QHBoxLayout()
            hbox.addWidget(QtWidgets.QLabel("Analyze Item:"))
            hbox.addWidget(self.analysis_item_combo, stretch=1)
            # Try inserting at the top if possible
            if hasattr(layout, 'insertLayout'):
                layout.insertLayout(0, hbox)
            else:
                layout.addLayout(hbox)

        self.analysis_item_combo.currentIndexChanged.connect(self._on_analysis_item_selected)

    # --- ADDED: Method to setup plot area --- 
    def _setup_plot_area(self, layout: QtWidgets.QLayout, stretch_factor: int = 1):
        """Adds a PlotWidget to the provided layout with normal configuration."""
        log.info(f"[ANALYSIS-BASE] Setting up plot area for {self.__class__.__name__}")
        
        self.plot_widget = pg.PlotWidget()
        log.debug(f"[ANALYSIS-BASE] Created plot widget for {self.__class__.__name__}")

        # Set white background
        self.plot_widget.setBackground('white')
        log.debug(f"[ANALYSIS-BASE] Set white background for {self.__class__.__name__}")

        # Configure mouse mode normally
        viewbox = self.plot_widget.getViewBox()
        if viewbox:
            viewbox.setMouseMode(pg.ViewBox.RectMode)
            viewbox.mouseEnabled = True
            log.debug(f"[ANALYSIS-BASE] Configured mouse mode for {self.__class__.__name__}")
            
            # Add Windows signal protection to prevent rapid range changes
            import sys
            if sys.platform.startswith('win'):
                log.debug(f"[ANALYSIS-BASE] Adding Windows signal protection for {self.__class__.__name__}")
                self._setup_windows_signal_protection(viewbox)

        # Add the plot widget to the layout
        layout.addWidget(self.plot_widget, stretch=stretch_factor)
        log.debug(f"[ANALYSIS-BASE] Added plot widget to layout for {self.__class__.__name__}")

        # Normal grid configuration
        try:
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            log.debug(f"[ANALYSIS-BASE] Grid configuration successful for {self.__class__.__name__}")
        except Exception as e:
            log.warning(f"[ANALYSIS-BASE] Grid configuration warning for {self.__class__.__name__}: {e}")

        # Add reset view button below plot
        self._setup_reset_view_button(layout)

        # Initialize zoom synchronization manager (for reset functionality only)
        self._setup_zoom_sync()

        log.info(f"[ANALYSIS-BASE] Plot area setup complete for {self.__class__.__name__}")

    # --- END ADDED ---

    # --- ADDED: Method to setup save button --- 
    def _setup_save_button(self, layout: QtWidgets.QLayout, alignment=QtCore.Qt.AlignmentFlag.AlignCenter):
        """Adds a standard 'Save Result' button to the layout and connects it."""
        self.save_button = QtWidgets.QPushButton(f"Save {self.get_display_name()} Result")
        self.save_button.setIcon(QtGui.QIcon.fromTheme("document-save")) # Optional icon
        self.save_button.setToolTip(f"Save the currently calculated {self.get_display_name()} result to the main results list.")
        
        # Use our styling module for consistent appearance
        style_button(self.save_button, 'primary')
        
        self.save_button.setEnabled(False) # Disabled until a valid result is calculated
        self.save_button.clicked.connect(self._on_save_button_clicked_base)
        # Add button to layout
        if alignment:
            layout.addWidget(self.save_button, 0, alignment)
        else:
            layout.addWidget(self.save_button)
        log.debug(f"{self.__class__.__name__}: Save button setup.")
    # --- END ADDED ---

    # --- ADDED: Helper method to enable/disable save button ---
    def _set_save_button_enabled(self, enabled: bool):
        """Helper method to enable or disable the save button."""
        if hasattr(self, 'save_button') and self.save_button:
            was_enabled = self.save_button.isEnabled()
            self.save_button.setEnabled(enabled)
            if was_enabled != enabled:
                log.debug(f"{self.__class__.__name__}: Save button enabled changed from {was_enabled} to {enabled}")
    # --- END ADDED ---

    def _setup_reset_view_button(self, layout: QtWidgets.QLayout):
        """Setup reset view button for the plot area."""
        # Create horizontal layout for reset button
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()  # Push button to center
        
        # Create reset view button with consistent styling
        self.reset_view_button = QtWidgets.QPushButton("Reset View")
        self.reset_view_button.setToolTip("Reset plot zoom and pan to fit all data")
        
        # Apply consistent button styling
        style_button(self.reset_view_button)
        
        # Connect to auto-range functionality
        self.reset_view_button.clicked.connect(self._on_reset_view_clicked)
        
        button_layout.addWidget(self.reset_view_button)
        button_layout.addStretch()  # Push button to center
        
        # Add button layout to main layout
        layout.addLayout(button_layout)
        
        log.debug(f"Reset view button setup for {self.__class__.__name__}")

    def _on_reset_view_clicked(self):
        """Handle reset view button click."""
        log.info(f"[ANALYSIS-BASE] Reset view clicked for {self.__class__.__name__}")
        self.auto_range_plot()
        log.debug(f"[ANALYSIS-BASE] Reset view triggered for {self.__class__.__name__}")

    def _setup_zoom_sync(self):
        """Initialize the zoom synchronization manager for reset functionality only."""
        if not self.plot_widget:
            return
            
        self.zoom_sync = PlotZoomSyncManager(self)
        self.zoom_sync.setup_plot_widget(self.plot_widget)
        
        # Set callback for range changes
        self.zoom_sync.on_range_changed = self._on_plot_range_changed
        
        log.debug(f"Zoom sync manager initialized for {self.__class__.__name__} (reset functionality only)")
        
    def setup_zoom_controls(self, **kwargs):
        """Deprecated method - analysis tabs no longer use zoom controls, only reset view."""
        log.warning(f"setup_zoom_controls called on {self.__class__.__name__} - analysis tabs only use reset view")
        pass
    
    def set_data_ranges(self, x_range: Tuple[float, float], y_range: Tuple[float, float]):
        """Set the base data ranges for zoom/scroll calculations. Call this when plotting new data."""
        if self.zoom_sync:
            self.zoom_sync.set_base_ranges(x_range, y_range)
            log.debug(f"Data ranges set: X={x_range}, Y={y_range}")
    
    def auto_range_plot(self):
        """Auto-range the plot to fit all data."""
        log.info(f"[ANALYSIS-BASE] Auto-ranging plot for {self.__class__.__name__}")
        if self.zoom_sync:
            log.debug(f"[ANALYSIS-BASE] Using zoom sync auto-range")
            self.zoom_sync.auto_range()
        elif self.plot_widget:
            log.debug(f"[ANALYSIS-BASE] Using direct plot widget auto-range")
            self.plot_widget.autoRange()
        else:
            log.warning(f"[ANALYSIS-BASE] No plot widget available for auto-range")

    def _setup_windows_signal_protection(self, viewbox):
        """Setup signal protection for Windows to prevent rapid range changes."""
        try:
            # Simple debouncing by limiting rapid range changes
            def debounced_range_handler(signal_name):
                def handler(vb, range_data):
                    # Simple debouncing - prevent excessive calls
                    attr_name = f'_last_{signal_name}_change'
                    if not hasattr(self, attr_name):
                        setattr(self, attr_name, 0)
                    import time
                    now = time.time()
                    last_change = getattr(self, attr_name)
                    if now - last_change < 0.1:  # 100ms debounce for Windows
                        return
                    setattr(self, attr_name, now)
                    log.debug(f"[ANALYSIS-BASE] {signal_name} range change allowed for {self.__class__.__name__}")
                return handler
            
            # Connect simple debouncing handlers to prevent rapid range changes
            viewbox.sigXRangeChanged.connect(debounced_range_handler('x'))
            viewbox.sigYRangeChanged.connect(debounced_range_handler('y'))
                
            log.debug(f"[ANALYSIS-BASE] Windows signal protection setup complete for {self.__class__.__name__}")
        except Exception as e:
            log.warning(f"[ANALYSIS-BASE] Failed to setup Windows signal protection: {e}")

    def _on_plot_range_changed(self, axis: str, new_range: Tuple[float, float]):
        """Called when plot range changes from any source (zoom, scroll, manual)."""
        # Subclasses can override this to handle range changes
        # For example, to update analysis regions or recalculate results
        pass

    # ViewBox state change handler
    def _on_viewbox_changed(self):
        """Handles view box state changes (like zoom/pan) - now handled by zoom sync manager."""
        # The zoom sync manager now handles all range synchronization
        # This method is kept for backward compatibility
        pass

    # Add stub method for mouse click handling
    def _handle_mouse_click(self, ev):
        """Default handler for mouse clicks on the plot."""
        # By default, just pass the event to the original handler
        if hasattr(self, 'plot_widget') and self.plot_widget and self.plot_widget.getViewBox():
            # Auto-range on double-click
            if ev.double():
                self.plot_widget.getViewBox().autoRange()
                # Prevent further processing
                ev.accept()
            else:
                # Ensure original mouse behavior is preserved
                pg.ViewBox.mouseClickEvent(self.plot_widget.getViewBox(), ev)

    # --- Method called by AnalyserTab when the analysis set changes ---
    def update_state(self, analysis_items: List[Dict[str, Any]]):
        """
        Update the state based on the list of analysis items provided by AnalyserTab.
        Populates the item selection combo box.
        """
        log.debug(f"{self.__class__.__name__}: Updating state with {len(analysis_items)} items.")
        self._analysis_items = analysis_items
        # Clear currently loaded data when the list changes
        self._selected_item_recording = None 
        self._selected_item_index = -1

        if not self.analysis_item_combo:
            log.warning(f"{self.__class__.__name__}: analysis_item_combo not setup. Call _setup_analysis_item_selector in _setup_ui.")
            return

        self.analysis_item_combo.blockSignals(True)
        try:
            self.analysis_item_combo.clear()
            if not analysis_items:
                self.analysis_item_combo.addItem("No Analysis Items Available")
                self.analysis_item_combo.setEnabled(False)
            else:
                self.analysis_item_combo.setEnabled(True)
                for i, item in enumerate(analysis_items):
                    # Create descriptive text for combo box
                    path_name = item.get('path', Path("Unknown")).name
                    target = item.get('target_type', 'Unknown')
                    display_text = f"Item {i+1}: "
                    if target == 'Recording': display_text += f"File: {path_name}"
                    elif target == 'Current Trial': trial_info = f" (Trial {item['trial_index'] + 1})" if item.get('trial_index') is not None else ""; display_text += f"{path_name} [{target}{trial_info}]"
                    else: display_text += f"{path_name} [{target}]"
                    self.analysis_item_combo.addItem(display_text)
        finally:
            self.analysis_item_combo.blockSignals(False)
        
        # Trigger update based on the potentially new first item (or lack thereof)
        # Clear plot when items change before selecting new one
        if self.plot_widget:
            self.plot_widget.clear()
        self._on_analysis_item_selected(0 if analysis_items else -1)

    # --- Internal Slot for Item Selection Change ---
    @QtCore.Slot(int)
    def _on_analysis_item_selected(self, index: int):
        """Handles the selection change in the analysis item combo box."""
        self._selected_item_index = index
        self._selected_item_recording = None # Clear previous loaded recording
        
        if index < 0 or index >= len(self._analysis_items):
            log.debug(f"{self.__class__.__name__}: No valid analysis item selected (index {index}).")
            # Still need to update UI to reflect empty state
            try: self._update_ui_for_selected_item()
            except Exception as e: log.error(f"Error calling _update_ui_for_selected_item on empty selection: {e}", exc_info=True)
            return

        selected_item = self._analysis_items[index]
        item_type = selected_item.get('target_type')
        item_path = selected_item.get('path')

        log.debug(f"{self.__class__.__name__}: Selected analysis item {index}: Type={item_type}, Path={item_path}")

        # If the selected item is a whole recording, we need to load it
        if item_type == 'Recording' and item_path:
            try:
                log.info(f"{self.__class__.__name__}: Loading recording for analysis item: {item_path.name}")
                # Use the NeoAdapter passed during init
                self._selected_item_recording = self.neo_adapter.read_recording(item_path)
                log.info(f"{self.__class__.__name__}: Successfully loaded {item_path.name}")
            except (FileNotFoundError, FileReadError, SynaptipyError) as e:
                log.error(f"{self.__class__.__name__}: Failed to load recording {item_path.name}: {e}")
                QtWidgets.QMessageBox.warning(self, "Load Error", f"Could not load data for selected item:\n{item_path.name}\n\nError: {e}")
                self._selected_item_recording = None # Ensure it's None on error
            except Exception as e:
                log.exception(f"{self.__class__.__name__}: Unexpected error loading recording {item_path.name}")
                QtWidgets.QMessageBox.critical(self, "Load Error", f"Unexpected error loading:\n{item_path.name}\n\n{e}")
                self._selected_item_recording = None
        elif item_type in ["Current Trial", "Average Trace", "All Trials"]:
            # For these types, the data isn't stored directly in the item yet.
            # Option 1: Load the recording anyway (like 'Recording' type)
            # Option 2: Modify ExplorerTab to pass actual data arrays (more complex)
            # Let's use Option 1 for now for simplicity. Load the source file.
            if item_path:
                try:
                    log.info(f"{self.__class__.__name__}: Loading source recording for item: {item_path.name}")
                    self._selected_item_recording = self.neo_adapter.read_recording(item_path)
                except Exception as e:
                    log.error(f"{self.__class__.__name__}: Failed to load source recording {item_path.name} for item type {item_type}: {e}")
                    self._selected_item_recording = None
            else:
                log.warning(f"{self.__class__.__name__}: Item type {item_type} selected but path is missing.")
                self._selected_item_recording = None
        else:
            log.warning(f"{self.__class__.__name__}: Unknown or unhandled analysis item type: {item_type}")
            self._selected_item_recording = None

        # --- Call Subclass UI Update --- 
        # This should be called regardless of whether loading succeeded, 
        # so the subclass can update its UI (e.g., disable widgets if loading failed)
        try:
            # Clear plot before updating UI for new selection
            if self.plot_widget:
                self.plot_widget.clear()
            self._update_ui_for_selected_item()
        except NotImplementedError: # Catch if subclass forgot to implement
            log.error(f"Subclass {self.__class__.__name__} must implement _update_ui_for_selected_item()")
        except Exception as e:
            log.error(f"Error calling _update_ui_for_selected_item in {self.__class__.__name__}: {e}", exc_info=True)

    # --- ADDED: Base slot for save button click --- 
    @QtCore.Slot()
    def _on_save_button_clicked_base(self):
        """Handles the save button click, gets specific data, and requests save."""
        log.debug(f"{self.get_display_name()}: Save button clicked (base slot).")
        try:
            specific_data = self._get_specific_result_data()
            if specific_data is not None:
                self._request_save_result(specific_data)
                # Provide visual feedback to the user
                if hasattr(self, 'status_label') and self.status_label:
                    self.status_label.setText("Status: Results saved successfully")
            else:
                log.warning("Save requested, but _get_specific_result_data returned None.")
                QtWidgets.QMessageBox.warning(self, "Save Error", "No valid result available to save.")
                
                # Disable the save button as a precaution
                self._set_save_button_enabled(False)
        except NotImplementedError:
            log.error(f"Subclass {self.__class__.__name__} must implement _get_specific_result_data() to enable saving.")
            QtWidgets.QMessageBox.critical(self, "Save Error", "Save functionality not implemented for this tab.")
        except Exception as e:
            log.error(f"Error getting specific result data in {self.__class__.__name__}: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Error preparing result for saving:\n{e}")
    # --- END ADDED ---

    # --- Abstract Methods / Methods Subclasses MUST Implement ---
    def get_display_name(self) -> str:
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement get_display_name()")

    def _setup_ui(self):
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement _setup_ui()")
        # Subclass implementation MUST call self._setup_analysis_item_selector(layout) somewhere appropriate.
        # Subclass implementation SHOULD call self._setup_plot_area(layout) somewhere appropriate.
        # Subclass implementation CAN call self._setup_save_button(layout) to add the save button.

    def _update_ui_for_selected_item(self):
        """
        Subclasses MUST implement this method.
        Called AFTER an item is selected in the `analysis_item_combo` and 
        `self._selected_item_recording` has been potentially loaded.
        Subclass should update its specific UI elements (e.g., channel/trial 
        selectors, input fields) based on the data in `self._selected_item_recording`
        or the details in `self._analysis_items[self._selected_item_index]`.
        Should also handle the case where `self._selected_item_recording` is None (load failed).
        Typically, this method should also trigger plotting the relevant data.
        """
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement _update_ui_for_selected_item()")

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """
        Subclasses MUST implement this method if they use the save button.
        It should gather the specific results (value, units, parameters, etc.)
        from the tab's UI elements and return them as a dictionary.
        Return None if no valid result is currently available.
        The dictionary should NOT include common metadata like filename, analysis_type,
        timestamp, etc., as those are added by _request_save_result.
        It MUST include the 'data_source' key if applicable (value is 'average' or trial index).
        """
        # Default implementation returns None, indicating save is not supported or no result
        # or raise NotImplementedError explicitly if button setup *requires* implementation
        log.warning(f"{self.__class__.__name__}._get_specific_result_data() is not implemented.")
        return None

    # --- Optional Methods Subclasses Might Implement ---
    def _connect_signals(self):
        pass # Optional

    def cleanup(self):
        log.debug(f"Cleaning up {self.__class__.__name__}")
        pass # Optional

    # --- ADDED: Helper for Saving Results ---
    def _request_save_result(self, specific_result_data: Dict[str, Any]):
        """
        Collects common metadata and calls MainWindow's method to save the result.

        Args:
            specific_result_data: Dictionary containing results specific to this
                                      analysis tab (e.g., value, units, channel,
                                      data source selection).
        """
        log.debug(f"{self.get_display_name()}: Requesting to save result.")
        main_window = self.window() # Get reference to the top-level MainWindow
        if not hasattr(main_window, 'add_saved_result'):
            log.error("Cannot save result: MainWindow does not have 'add_saved_result' method.")
            QtWidgets.QMessageBox.critical(self, "Save Error", "Internal error: Cannot access result saving mechanism.")
            return

        if self._selected_item_index < 0 or self._selected_item_index >= len(self._analysis_items):
            log.warning("Cannot save result: No valid analysis item selected.")
            QtWidgets.QMessageBox.warning(self, "Save Error", "No analysis item selected.")
            return

        # --- Get Common Metadata --- 
        selected_item = self._analysis_items[self._selected_item_index]
        source_file_path = selected_item.get('path')
        source_file_name = source_file_path.name if source_file_path else "Unknown"
        item_target_type = selected_item.get('target_type') # Type selected in Explorer list
        item_trial_index = selected_item.get('trial_index') # Trial defined in Explorer list (if any)

        # --- Determine Actual Data Source Used --- 
        # This comes from the UI elements *within* this specific analysis tab
        data_source = specific_result_data.get('data_source', None) # e.g., "average" or trial index
        actual_trial_index = None
        data_source_type = "Unknown"
        if data_source == "average":
            data_source_type = "Average"
        elif isinstance(data_source, int):
            data_source_type = "Trial"
            actual_trial_index = data_source # 0-based
        else: # Handle cases where data source might be fixed by the item_type
            if item_target_type == "Current Trial":
                 data_source_type = "Trial"
                 actual_trial_index = item_trial_index
            elif item_target_type == "Average Trace":
                 data_source_type = "Average"

        # --- Get Analysis Type --- 
        analysis_type = self.get_display_name()

        # --- Combine Data --- 
        # Prioritize specific results passed in, then add common metadata
        final_result = {
            'analysis_type': analysis_type,
            'source_file_name': source_file_name,
            'source_file_path': str(source_file_path) if source_file_path else None,
            'item_target_type': item_target_type, # How the source was added
            'data_source_used': data_source_type, # Average or Trial
            'trial_index_used': actual_trial_index, # 0-based index if applicable
            **specific_result_data # Add the specific results from the subclass
        }

        # Remove the internal 'data_source' key if it exists in specific_result_data
        final_result.pop('data_source', None)

        log.debug(f"Final result data to save: {final_result}")

        # --- Call MainWindow Method --- 
        try:
            main_window.add_saved_result(final_result)
            # Optional: Give user feedback within the tab
            # e.g., self.save_status_label.setText("Result saved!")
        except Exception as e:
            log.error(f"Error calling main_window.add_saved_result: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Failed to save result:\n{e}")
    # --- END ADDED ---