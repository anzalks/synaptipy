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
from abc import ABC, abstractmethod

from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import numpy as np

# Use absolute path to import NeoAdapter and Recording
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.shared.error_handling import SynaptipyError, FileReadError
from Synaptipy.shared.styling import (
    style_button,
)
from Synaptipy.shared.plot_zoom_sync import PlotZoomSyncManager

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.base')

# Custom metaclass to resolve Qt/ABC metaclass conflict
class QABCMeta(type(QtWidgets.QWidget), type(ABC)):
    """Metaclass that combines Qt's metaclass with ABC's metaclass."""
    pass

class BaseAnalysisTab(QtWidgets.QWidget, ABC, metaclass=QABCMeta):
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
        
        # --- PHASE 1: Data Selection and Plotting ---
        self.signal_channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        self._current_plot_data: Optional[Dict[str, Any]] = None
        
        # --- PHASE 2: Analysis Results ---
        self._last_analysis_result: Optional[Dict[str, Any]] = None
        
        # --- PHASE 3: Debounce Timer for Parameter Changes ---
        self._analysis_debounce_timer: Optional[QtCore.QTimer] = None
        self._debounce_delay_ms: int = 500  # 500ms delay for debouncing
        
        # Initialize debounce timer
        self._analysis_debounce_timer = QtCore.QTimer(self)
        self._analysis_debounce_timer.setSingleShot(True)
        self._analysis_debounce_timer.timeout.connect(self._trigger_analysis)
        
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

    def _update_plot_pens_only(self):
        """Efficiently update only the pen properties of existing plot items without recreating data."""
        if not self.plot_widget:
            return
            
        try:
            # Get current pens from customization manager
            from Synaptipy.shared.plot_customization import get_single_trial_pen, get_average_pen, get_grid_pen
            single_trial_pen = get_single_trial_pen()
            average_pen = get_average_pen()
            grid_pen = get_grid_pen()
            
            # Update pens for existing plot data items
            for item in self.plot_widget.plotItem.items:
                if isinstance(item, pg.PlotDataItem):
                    # Determine which pen to apply based on item properties or name
                    if hasattr(item, 'opts') and 'name' in item.opts:
                        item_name = item.opts['name']
                        if 'average' in item_name.lower() or 'avg' in item_name.lower():
                            item.setPen(average_pen)
                        else:
                            item.setPen(single_trial_pen)
                    else:
                        # Default to single trial pen if we can't determine the type
                        item.setPen(single_trial_pen)
            
            # Update grid
            try:
                alpha = grid_pen.alpha() if hasattr(grid_pen, 'alpha') else 0.3
                self.plot_widget.showGrid(x=True, y=True, alpha=alpha)
            except Exception as e:
                log.warning(f"Could not update grid: {e}")
                
            log.debug(f"[ANALYSIS-BASE] Pen update complete for {self.__class__.__name__}")
            
        except ImportError:
            log.warning(f"Could not import plot customization - skipping pen update for {self.__class__.__name__}")
        except Exception as e:
            log.error(f"Error updating plot pens for {self.__class__.__name__}: {e}")

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

        # Normal grid configuration with customization support
        try:
            # Try to use customized grid settings
            try:
                from Synaptipy.shared.plot_customization import get_grid_pen, is_grid_enabled
                if is_grid_enabled():
                    grid_pen = get_grid_pen()
                    if grid_pen:
                        # Get alpha value from pen color
                        alpha = 0.3  # Default alpha
                        if hasattr(grid_pen, 'color') and hasattr(grid_pen.color(), 'alpha'):
                            alpha = grid_pen.color().alpha() / 255.0
                            log.debug(f"Using grid pen alpha: {alpha} (opacity: {alpha * 100:.1f}%)")
                        else:
                            log.debug("Using default grid alpha: 0.3")
                        
                        self.plot_widget.showGrid(x=True, y=True, alpha=alpha)
                        log.debug(f"[ANALYSIS-BASE] Customized grid configuration successful for {self.__class__.__name__} with alpha: {alpha}")
                    else:
                        self.plot_widget.showGrid(x=False, y=False)
                        log.debug(f"[ANALYSIS-BASE] Grid disabled for {self.__class__.__name__}")
                else:
                    self.plot_widget.showGrid(x=False, y=False)
                    log.debug(f"[ANALYSIS-BASE] Grid disabled for {self.__class__.__name__}")
            except ImportError:
                self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
                log.debug(f"[ANALYSIS-BASE] Default grid configuration successful for {self.__class__.__name__}")
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
        
        # Create save plot button
        self.save_plot_button = QtWidgets.QPushButton("Save Plot")
        self.save_plot_button.setToolTip("Save plot as PNG or PDF")
        
        # Apply consistent button styling
        style_button(self.save_plot_button)
        
        # Connect to save functionality
        self.save_plot_button.clicked.connect(self._on_save_plot_clicked)
        
        button_layout.addWidget(self.save_plot_button)
        button_layout.addStretch()  # Push button to center
        
        # Add button layout to main layout
        layout.addLayout(button_layout)
        
        log.debug(f"Reset view button setup for {self.__class__.__name__}")

    def _on_reset_view_clicked(self):
        """Handle reset view button click."""
        log.info(f"[ANALYSIS-BASE] Reset view clicked for {self.__class__.__name__}")
        self.auto_range_plot()
        log.debug(f"[ANALYSIS-BASE] Reset view triggered for {self.__class__.__name__}")

    def _on_save_plot_clicked(self):
        """Handle save plot button click."""
        log.info(f"[ANALYSIS-BASE] Save plot clicked for {self.__class__.__name__}")
        
        if not self.plot_widget:
            log.warning(f"[ANALYSIS-BASE] No plot widget available for saving")
            return
            
        try:
            from Synaptipy.application.gui.plot_save_dialog import save_plot_with_dialog
            
            # Generate default filename based on tab name
            default_filename = f"{self.__class__.__name__.lower().replace('tab', '')}_plot"
            
            # Show save dialog and save plot
            success = save_plot_with_dialog(
                self.plot_widget, 
                parent=self, 
                default_filename=default_filename
            )
            
            if success:
                log.info(f"[ANALYSIS-BASE] Plot saved successfully for {self.__class__.__name__}")
            else:
                log.debug(f"[ANALYSIS-BASE] Plot save cancelled for {self.__class__.__name__}")
                
        except Exception as e:
            log.error(f"[ANALYSIS-BASE] Failed to save plot for {self.__class__.__name__}: {e}")
            # Show error message to user
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self, 
                "Save Error", 
                f"Failed to save plot:\n{str(e)}"
            )

    def _setup_zoom_sync(self):
        """Initialize the zoom synchronization manager for reset functionality only."""
        if not self.plot_widget:
            return
            
        self.zoom_sync = PlotZoomSyncManager(self)
        self.zoom_sync.setup_plot_widget(self.plot_widget)
        
        # Set callback for range changes
        self.zoom_sync.on_range_changed = self._on_plot_range_changed
        
        # Apply system theme colors to the selection rectangle
        try:
            from Synaptipy.shared.zoom_theme import apply_theme_with_custom_selection
            # Apply custom selection rectangle with theme
            apply_theme_with_custom_selection(self.plot_widget.getViewBox())
        except Exception as e:
            log.debug(f"Failed to apply theme to plot widget: {e}")
        
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
            
            # PHASE 1: Populate channel and data source comboboxes if they exist
            if self.signal_channel_combobox and self.data_source_combobox:
                self._populate_channel_and_source_comboboxes()
            
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
    @abstractmethod
    def get_display_name(self) -> str:
        """Return the display name for this analysis tab."""
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement get_display_name()")

    @abstractmethod
    def _setup_ui(self):
        """
        Set up the UI for this analysis tab.
        Subclass implementation MUST call self._setup_analysis_item_selector(layout) somewhere appropriate.
        Subclass implementation SHOULD call self._setup_plot_area(layout) somewhere appropriate.
        Subclass implementation CAN call self._setup_save_button(layout) to add the save button.
        """
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement _setup_ui()")

    @abstractmethod
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
    
    # --- PHASE 2: Abstract Methods for Template Method Pattern ---
    # BUG 2 FIX: These are the ONLY declarations of these methods - no duplicates
    
    @abstractmethod
    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """
        Gather analysis parameters from UI widgets.
        
        Returns:
            Dictionary containing all parameters needed for analysis.
            Return empty dict if parameters are invalid.
        """
        pass
    
    @abstractmethod
    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Execute the core analysis logic.
        
        Args:
            params: Parameters gathered from _gather_analysis_parameters
            data: Current plot data dictionary
        
        Returns:
            Dictionary containing analysis results, or None if analysis fails.
            NOTE: Return type is Optional to allow returning None on failure.
        """
        pass
    
    @abstractmethod
    def _display_analysis_results(self, results: Dict[str, Any]):
        """
        Display analysis results in UI widgets.
        
        Args:
            results: Analysis results dictionary from _execute_core_analysis
        """
        pass
    
    @abstractmethod
    def _plot_analysis_visualizations(self, results: Dict[str, Any]):
        """
        Update plot with analysis-specific visualizations (markers, lines, etc.).
        
        Args:
            results: Analysis results dictionary from _execute_core_analysis
        """
        pass

    # --- PHASE 1: Data Selection and Plotting Infrastructure ---
    def _setup_data_selection_ui(self, layout: QtWidgets.QLayout):
        """
        Adds channel and data source selection combo boxes to the provided layout.
        Called by subclasses in their _setup_ui method.
        """
        # Signal Channel Selection
        self.signal_channel_combobox = QtWidgets.QComboBox()
        self.signal_channel_combobox.setToolTip("Select the signal channel to plot and analyze.")
        self.signal_channel_combobox.setEnabled(False)
        
        # Data Source Selection (Trial vs Average)
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)
        
        # Add to layout
        if isinstance(layout, QtWidgets.QFormLayout):
            layout.addRow("Signal Channel:", self.signal_channel_combobox)
            layout.addRow("Data Source:", self.data_source_combobox)
        else:
            # Fallback for other layouts
            hbox1 = QtWidgets.QHBoxLayout()
            hbox1.addWidget(QtWidgets.QLabel("Signal Channel:"))
            hbox1.addWidget(self.signal_channel_combobox, stretch=1)
            layout.addLayout(hbox1)
            
            hbox2 = QtWidgets.QHBoxLayout()
            hbox2.addWidget(QtWidgets.QLabel("Data Source:"))
            hbox2.addWidget(self.data_source_combobox, stretch=1)
            layout.addLayout(hbox2)
        
        # Connect signals to trigger plotting when selection changes
        self.signal_channel_combobox.currentIndexChanged.connect(self._plot_selected_data)
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_data)
        
        log.debug(f"{self.__class__.__name__}: Data selection UI setup complete")
    
    def _populate_channel_and_source_comboboxes(self):
        """
        Populate channel and data source comboboxes based on the currently loaded recording.
        Called automatically by the base class when an analysis item is selected.
        """
        log.debug(f"{self.__class__.__name__}: Populating channel and source comboboxes")
        
        # Clear previous selections
        self.signal_channel_combobox.blockSignals(True)
        self.data_source_combobox.blockSignals(True)
        self.signal_channel_combobox.clear()
        self.data_source_combobox.clear()
        
        has_channels = False
        
        # Populate Channel ComboBox
        if self._selected_item_recording and self._selected_item_recording.channels:
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                units = getattr(channel, 'units', '')
                display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{units}]"
                self.signal_channel_combobox.addItem(display_name, userData=chan_id)
                has_channels = True
        
        if not has_channels:
            self.signal_channel_combobox.addItem("No Channels Found")
            self.signal_channel_combobox.setEnabled(False)
            self.data_source_combobox.addItem("N/A")
            self.data_source_combobox.setEnabled(False)
            self.signal_channel_combobox.blockSignals(False)
            self.data_source_combobox.blockSignals(False)
            return
        
        self.signal_channel_combobox.setEnabled(True)
        self.signal_channel_combobox.setCurrentIndex(0)
        
        # Populate Data Source ComboBox
        selected_item_details = self._analysis_items[self._selected_item_index] if self._selected_item_index >= 0 else {}
        item_type = selected_item_details.get('target_type')
        item_trial_index = selected_item_details.get('trial_index')
        
        # Get trial info from first channel
        first_channel = next(iter(self._selected_item_recording.channels.values()), None)
        num_trials = 0
        has_average = False
        
        if first_channel:
            num_trials = getattr(first_channel, 'num_trials', 0)
            # Check for average data
            if hasattr(first_channel, 'get_averaged_data') and first_channel.get_averaged_data() is not None:
                has_average = True
            elif hasattr(first_channel, 'has_average_data') and first_channel.has_average_data():
                has_average = True
            elif getattr(first_channel, '_averaged_data', None) is not None:
                has_average = True
        
        # Populate based on item type
        if item_type == "Current Trial" and item_trial_index is not None and 0 <= item_trial_index < num_trials:
            self.data_source_combobox.addItem(f"Trial {item_trial_index + 1}", userData=item_trial_index)
        elif item_type == "Average Trace" and has_average:
            self.data_source_combobox.addItem("Average Trace", userData="average")
        else:  # "Recording" or "All Trials"
            if has_average:
                self.data_source_combobox.addItem("Average Trace", userData="average")
            for i in range(num_trials):
                self.data_source_combobox.addItem(f"Trial {i + 1}", userData=i)
        
        if self.data_source_combobox.count() > 0:
            self.data_source_combobox.setEnabled(True)
        else:
            self.data_source_combobox.addItem("No Data Available")
            self.data_source_combobox.setEnabled(False)
        
        self.signal_channel_combobox.blockSignals(False)
        self.data_source_combobox.blockSignals(False)
        
        log.debug(f"{self.__class__.__name__}: Comboboxes populated - {self.signal_channel_combobox.count()} channels, {self.data_source_combobox.count()} sources")
        
        # Trigger initial plot
        self._plot_selected_data()
    
    @QtCore.Slot()
    def _plot_selected_data(self):
        """
        Centralized plotting method that fetches data based on selected channel and source,
        plots it, and calls the _on_data_plotted hook for subclass-specific additions.
        """
        log.debug(f"{self.__class__.__name__}: Plotting selected data")
        
        # Clear current plot data
        self._current_plot_data = None
        
        # Validate UI elements
        if not self.plot_widget or not self.signal_channel_combobox or not self.data_source_combobox:
            log.warning(f"{self.__class__.__name__}: Plot widget or comboboxes not initialized")
            return
        
        # Validate selections
        if not self.signal_channel_combobox.isEnabled() or not self.data_source_combobox.isEnabled():
            log.debug(f"{self.__class__.__name__}: Comboboxes disabled, skipping plot")
            if self.plot_widget:
                self.plot_widget.clear()
            return
        
        # Get selected channel and data source
        chan_id = self.signal_channel_combobox.currentData()
        data_source = self.data_source_combobox.currentData()
        
        if chan_id is None or data_source is None:
            log.debug(f"{self.__class__.__name__}: No valid selection")
            if self.plot_widget:
                self.plot_widget.clear()
            return
        
        # Validate recording
        if not self._selected_item_recording or chan_id not in self._selected_item_recording.channels:
            log.warning(f"{self.__class__.__name__}: Channel {chan_id} not found in recording")
            if self.plot_widget:
                self.plot_widget.clear()
            return
        
        # Get channel
        channel = self._selected_item_recording.channels[chan_id]
        
        # Fetch data
        try:
            if data_source == "average":
                data_vec = channel.get_averaged_data()
                time_vec = channel.get_relative_averaged_time_vector()
                data_label = "Average"
            elif isinstance(data_source, int):
                data_vec = channel.get_data(data_source)
                time_vec = channel.get_relative_time_vector(data_source)
                data_label = f"Trial {data_source + 1}"
            else:
                log.error(f"{self.__class__.__name__}: Invalid data source: {data_source}")
                if self.plot_widget:
                    self.plot_widget.clear()
                return
            
            if data_vec is None or time_vec is None:
                log.warning(f"{self.__class__.__name__}: No data available for {data_label}")
                if self.plot_widget:
                    self.plot_widget.clear()
                return
            
            # Store current plot data
            self._current_plot_data = {
                'data': data_vec,
                'time': time_vec,
                'channel_id': chan_id,
                'data_source': data_source,
                'units': channel.units or '?',
                'sampling_rate': channel.sampling_rate,
                'channel_name': channel.name or f'Ch {chan_id}'
            }
            
            # Clear plot
            self.plot_widget.clear()
            
            # Plot data
            try:
                from Synaptipy.shared.plot_customization import get_single_trial_pen, get_average_pen
                if data_source == "average":
                    pen = get_average_pen()
                else:
                    pen = get_single_trial_pen()
            except ImportError:
                pen = pg.mkPen(color=(0, 0, 0), width=1)
            
            self.plot_widget.plot(time_vec, data_vec, pen=pen, name=data_label)
            
            # Set labels
            self.plot_widget.setLabel('bottom', 'Time', units='s')
            self.plot_widget.setLabel('left', channel.name or f'Ch {chan_id}', units=channel.units)
            self.plot_widget.setTitle(f"{channel.name or f'Channel {chan_id}'} - {data_label}")
            
            # Set data ranges for zoom sync
            if time_vec is not None and data_vec is not None and len(time_vec) > 0 and len(data_vec) > 0:
                x_range = (float(np.min(time_vec)), float(np.max(time_vec)))
                y_range = (float(np.min(data_vec)), float(np.max(data_vec)))
                self.set_data_ranges(x_range, y_range)
            
            log.info(f"{self.__class__.__name__}: Successfully plotted {data_label} from channel {chan_id}")
            
            # Call hook for subclass-specific plot items
            self._on_data_plotted()
            
        except Exception as e:
            log.error(f"{self.__class__.__name__}: Error plotting data: {e}", exc_info=True)
            if self.plot_widget:
                self.plot_widget.clear()
            self._current_plot_data = None
    
    def _on_data_plotted(self):
        """
        Hook method called after data has been successfully plotted by the base class.
        Subclasses should override this to add their specific plot items (e.g., regions, markers).
        """
        pass  # Default implementation does nothing
    
    # --- PHASE 2: Template Method Pattern ---
    @QtCore.Slot()
    def _trigger_analysis(self):
        """
        Template method that orchestrates the analysis workflow.
        This method should NOT be overridden by subclasses.
        
        Workflow:
        1. Validate data availability
        2. Set wait cursor
        3. Gather parameters from UI (via abstract method)
        4. Execute core analysis (via abstract method)
        5. Display results (via abstract method)
        6. Update plot visualizations (via abstract method)
        7. Enable save button
        8. Handle errors and restore cursor
        """
        log.debug(f"{self.__class__.__name__}: Triggering analysis")
        
        # Validate data
        if not self._current_plot_data:
            log.warning(f"{self.__class__.__name__}: No data available for analysis")
            QtWidgets.QMessageBox.warning(
                self,
                "No Data",
                "Please load and plot data before running analysis."
            )
            return
        
        # Set wait cursor
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        self._last_analysis_result = None
        
        try:
            # Step 1: Gather parameters from subclass UI
            params = self._gather_analysis_parameters()
            if not params:
                log.warning(f"{self.__class__.__name__}: No parameters gathered")
                self._set_save_button_enabled(False)
                return
            
            # Step 2: Execute core analysis
            results = self._execute_core_analysis(params, self._current_plot_data)
            
            # BUG 1 FIX: Check if results is None before proceeding
            if results is None:
                log.warning(f"{self.__class__.__name__}: Analysis returned None")
                QtWidgets.QMessageBox.warning(
                    self,
                    "Analysis Failed",
                    "Analysis could not be completed. Please check your parameters and data."
                )
                self._set_save_button_enabled(False)
                return
            
            # Store results for saving
            self._last_analysis_result = results
            
            # Step 3: Display results in UI
            self._display_analysis_results(results)
            
            # Step 4: Update plot visualizations
            self._plot_analysis_visualizations(results)
            
            # Enable save button
            self._set_save_button_enabled(True)
            
            log.info(f"{self.__class__.__name__}: Analysis completed successfully")
            
        except Exception as e:
            log.error(f"{self.__class__.__name__}: Analysis failed: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self,
                "Analysis Error",
                f"An error occurred during analysis:\n{str(e)}"
            )
            self._set_save_button_enabled(False)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
    
    # --- PHASE 3: Debounced Parameter Change Handler ---
    @QtCore.Slot()
    def _on_parameter_changed(self):
        """
        Called when a parameter widget changes.
        Starts/restarts the debounce timer to trigger analysis after a delay.
        """
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)
            log.debug(f"{self.__class__.__name__}: Parameter changed, debounce timer started")
    
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

        # --- Check for Existing Result ---
        existing_index = -1
        if hasattr(main_window, 'saved_results'):
            for i, res in enumerate(main_window.saved_results):
                # Define what "same result" means.
                # Usually: Same file, same analysis type, same data source (trial/avg)
                if (res.get('source_file_path') == final_result.get('source_file_path') and
                    res.get('analysis_type') == final_result.get('analysis_type') and
                    res.get('data_source_used') == final_result.get('data_source_used') and
                    res.get('trial_index_used') == final_result.get('trial_index_used')):
                    existing_index = i
                    break
        
        if existing_index >= 0:
            reply = QtWidgets.QMessageBox.question(
                self, 
                "Overwrite Result?",
                f"A result for '{analysis_type}' on this data already exists.\nDo you want to overwrite it?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                log.info("Save cancelled by user (overwrite denied).")
                return

        # --- Call MainWindow Method --- 
        try:
            # If overwriting, we might need a way to tell MainWindow to replace.
            # If add_saved_result just appends, we might have duplicates.
            # Let's assume we can replace if we have the index, OR we just append and let the user manage (but user asked to "rewrite").
            # If MainWindow has 'update_saved_result', use it. Else, maybe 'saved_results[i] = ...' ?
            # Safest is to check if we can replace.
            
            if existing_index >= 0 and hasattr(main_window, 'saved_results'):
                 main_window.saved_results[existing_index] = final_result
                 # We also need to refresh the results view in MainWindow if it exists
                 if hasattr(main_window, 'results_tab') and hasattr(main_window.results_tab, 'refresh_results'):
                     main_window.results_tab.refresh_results()
                 elif hasattr(main_window, 'refresh_results_display'):
                     main_window.refresh_results_display()
                 log.info(f"Overwrote existing result at index {existing_index}")
                 if hasattr(self, 'status_label') and self.status_label:
                    self.status_label.setText("Status: Result overwritten successfully")
            else:
                main_window.add_saved_result(final_result)
                if hasattr(self, 'status_label') and self.status_label:
                    self.status_label.setText("Status: Result saved successfully")
            
        except Exception as e:
            log.error(f"Error saving result: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Failed to save result:\n{e}")
    # --- END ADDED ---