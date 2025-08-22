#!/usr/bin/env python3
"""
Plot Customization Dialog for Synaptipy

This module provides a dialog interface for users to customize plot styling
including colors, line widths, and transparency for different plot types.

Author: Anzal
Email: anzal.ks@gmail.com
"""

import logging
import copy
from typing import Dict, Any, Optional
from PySide6 import QtCore, QtWidgets, QtGui
import pyqtgraph as pg

from Synaptipy.shared.plot_customization import get_plot_customization_manager

log = logging.getLogger(__name__)

class PlotCustomizationDialog(QtWidgets.QDialog):
    """
    Dialog for customizing plot styling preferences.
    
    Provides options for colors, line widths, and transparency for:
    - Average plots
    - Single trial plots
    - Grid lines
    """
    
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Plot Customization")
        self.setModal(True)
        self.resize(600, 500)
        
        self.customization_manager = get_plot_customization_manager()
        # Get a deep copy of preferences to avoid reference issues
        self.current_preferences = copy.deepcopy(self.customization_manager.get_all_preferences())
        # Store original preferences when dialog opens - use deep copy
        self._original_preferences = copy.deepcopy(self.customization_manager.get_all_preferences())
        
        log.info("=== DIALOG INITIALIZATION ===")
        log.info(f"Manager preferences: {self.customization_manager.get_all_preferences()}")
        log.info(f"Current preferences: {self.current_preferences}")
        log.info(f"Original preferences: {self._original_preferences}")
        
        self._setup_ui()
        self._load_current_preferences()
        self._connect_signals()
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title_label = QtWidgets.QLabel("Plot Customization")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)
        
        # Create tab widget for different plot types
        self.tab_widget = QtWidgets.QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Add tabs for each plot type
        self._create_average_tab()
        self._create_single_trial_tab()
        self._create_grid_tab()
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.reset_button = QtWidgets.QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._reset_to_defaults)
        
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.apply_button.clicked.connect(self._apply_changes)
        
        self.ok_button = QtWidgets.QPushButton("OK")
        self.ok_button.clicked.connect(self._ok_clicked)
        
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.ok_button)
        
        layout.addLayout(button_layout)
    
    def _create_average_tab(self):
        """Create the average plot customization tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Color selection
        color_group = QtWidgets.QGroupBox("Color")
        color_layout = QtWidgets.QHBoxLayout(color_group)
        
        self.average_color_combo = QtWidgets.QComboBox()
        self._populate_color_combo(self.average_color_combo)
        
        color_layout.addWidget(QtWidgets.QLabel("Line Color:"))
        color_layout.addWidget(self.average_color_combo)
        color_layout.addStretch()
        
        layout.addWidget(color_group)
        
        # Width selection
        width_group = QtWidgets.QGroupBox("Line Width")
        width_layout = QtWidgets.QHBoxLayout(width_group)
        
        self.average_width_combo = QtWidgets.QComboBox()
        self._populate_width_combo(self.average_width_combo)
        
        width_layout.addWidget(QtWidgets.QLabel("Width (pts):"))
        width_layout.addWidget(self.average_width_combo)
        width_layout.addStretch()
        
        layout.addWidget(width_group)
        
        # Transparency selection
        transparency_group = QtWidgets.QGroupBox("Transparency")
        transparency_layout = QtWidgets.QHBoxLayout(transparency_group)
        
        self.average_transparency_combo = QtWidgets.QComboBox()
        self._populate_transparency_combo(self.average_transparency_combo)
        
        transparency_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        transparency_layout.addWidget(self.average_transparency_combo)
        transparency_layout.addStretch()
        
        layout.addWidget(transparency_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Average")
    
    def _create_single_trial_tab(self):
        """Create the single trial plot customization tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Color selection
        color_group = QtWidgets.QGroupBox("Color")
        color_layout = QtWidgets.QHBoxLayout(color_group)
        
        self.single_trial_color_combo = QtWidgets.QComboBox()
        self._populate_color_combo(self.single_trial_color_combo)
        
        color_layout.addWidget(QtWidgets.QLabel("Line Color:"))
        color_layout.addWidget(self.single_trial_color_combo)
        color_layout.addStretch()
        
        layout.addWidget(color_group)
        
        # Width selection
        width_group = QtWidgets.QGroupBox("Line Width")
        width_layout = QtWidgets.QHBoxLayout(width_group)
        
        self.single_trial_width_combo = QtWidgets.QComboBox()
        self._populate_width_combo(self.single_trial_width_combo)
        
        width_layout.addWidget(QtWidgets.QLabel("Width (pts):"))
        width_layout.addWidget(self.single_trial_width_combo)
        width_layout.addStretch()
        
        layout.addWidget(width_group)
        
        # Transparency selection
        transparency_group = QtWidgets.QGroupBox("Transparency")
        transparency_layout = QtWidgets.QHBoxLayout(transparency_group)
        
        self.single_trial_transparency_combo = QtWidgets.QComboBox()
        self._populate_transparency_combo(self.single_trial_transparency_combo)
        
        transparency_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        transparency_layout.addWidget(self.single_trial_transparency_combo)
        transparency_layout.addStretch()
        
        layout.addWidget(transparency_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Single Trial")
    
    def _create_grid_tab(self):
        """Create the grid customization tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Color selection
        color_group = QtWidgets.QGroupBox("Color")
        color_layout = QtWidgets.QHBoxLayout(color_group)
        
        self.grid_color_combo = QtWidgets.QComboBox()
        self._populate_color_combo(self.grid_color_combo)
        
        color_layout.addWidget(QtWidgets.QLabel("Grid Color:"))
        color_layout.addWidget(self.grid_color_combo)
        color_layout.addStretch()
        
        layout.addWidget(color_group)
        
        # Width selection
        width_group = QtWidgets.QGroupBox("Line Width")
        width_layout = QtWidgets.QHBoxLayout(width_group)
        
        self.grid_width_combo = QtWidgets.QComboBox()
        self._populate_width_combo(self.grid_width_combo)
        
        width_layout.addWidget(QtWidgets.QLabel("Width (pts):"))
        width_layout.addWidget(self.grid_width_combo)
        width_layout.addStretch()
        
        layout.addWidget(width_group)
        
        # Transparency selection
        transparency_group = QtWidgets.QGroupBox("Transparency")
        transparency_layout = QtWidgets.QHBoxLayout(transparency_group)
        
        self.grid_transparency_combo = QtWidgets.QComboBox()
        self._populate_transparency_combo(self.grid_transparency_combo)
        
        transparency_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        transparency_layout.addWidget(self.grid_transparency_combo)
        transparency_layout.addStretch()
        
        layout.addWidget(transparency_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Grid")
    
    def _populate_color_combo(self, combo: QtWidgets.QComboBox):
        """Populate a color combo box with matplotlib color options."""
        # Include both named colors and the original matplotlib blue
        colors = [
            ('Matplotlib Blue', '#377eb8'),  # Original matplotlib blue
            ('Black', 'black'),
            ('Blue', 'blue'), 
            ('Orange', 'orange'), 
            ('Red', 'red'), 
            ('Purple', 'purple'), 
            ('Cyan', 'cyan'), 
            ('Green', 'green'),
            ('Yellow', 'yellow'), 
            ('Brown', 'brown'), 
            ('Pink', 'pink'), 
            ('Gray', 'gray'), 
            ('Olive', 'olive'), 
            ('Navy', 'navy'), 
            ('Teal', 'teal'),
            ('Maroon', 'maroon'), 
            ('Lime', 'lime'), 
            ('Aqua', 'aqua'), 
            ('Silver', 'silver'), 
            ('Fuchsia', 'fuchsia')
        ]

        for color_name, color_value in colors:
            combo.addItem(color_name, color_value)
    
    def _populate_width_combo(self, combo: QtWidgets.QComboBox):
        """Populate a width combo box with line width options."""
        widths = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
        
        for width in widths:
            combo.addItem(f"{width} pts", width)
    
    def _populate_transparency_combo(self, combo: QtWidgets.QComboBox):
        """Populate a transparency combo box with opacity options."""
        opacities = [20, 30, 40, 50, 60, 70, 80, 90, 100]
        
        for opacity in opacities:
            combo.addItem(f"{opacity}%", opacity)
    
    def _load_current_preferences(self):
        """Load current preferences into the UI controls."""
        try:
            # Average preferences
            self._set_combo_value(self.average_color_combo, self.current_preferences['average']['color'])
            self._set_combo_value(self.average_width_combo, self.current_preferences['average']['width'])
            self._set_combo_value(self.average_transparency_combo, self.current_preferences['average']['transparency'])
            
            # Single trial preferences
            self._set_combo_value(self.single_trial_color_combo, self.current_preferences['single_trial']['color'])
            self._set_combo_value(self.single_trial_width_combo, self.current_preferences['single_trial']['width'])
            self._set_combo_value(self.single_trial_transparency_combo, self.current_preferences['single_trial']['transparency'])
            
            # Grid preferences
            self._set_combo_value(self.grid_color_combo, self.current_preferences['grid']['color'])
            self._set_combo_value(self.grid_width_combo, self.current_preferences['grid']['width'])
            self._set_combo_value(self.grid_transparency_combo, self.current_preferences['grid']['transparency'])
            
            log.debug("Current preferences loaded into UI")
        except Exception as e:
            log.error(f"Failed to load current preferences: {e}")
    
    def _set_combo_value(self, combo: QtWidgets.QComboBox, value: Any):
        """Set the combo box to display a specific value."""
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                break
    
    def _connect_signals(self):
        """Connect UI control signals."""
        # Connect all combo boxes to update preferences
        self.average_color_combo.currentIndexChanged.connect(self._on_average_color_changed)
        self.average_width_combo.currentIndexChanged.connect(self._on_average_width_changed)
        self.average_transparency_combo.currentIndexChanged.connect(self._on_average_transparency_changed)
        
        self.single_trial_color_combo.currentIndexChanged.connect(self._on_single_trial_color_changed)
        self.single_trial_width_combo.currentIndexChanged.connect(self._on_single_trial_width_changed)
        self.single_trial_transparency_combo.currentIndexChanged.connect(self._on_single_trial_transparency_changed)
        
        self.grid_color_combo.currentIndexChanged.connect(self._on_grid_color_changed)
        self.grid_width_combo.currentIndexChanged.connect(self._on_grid_width_changed)
        self.grid_transparency_combo.currentIndexChanged.connect(self._on_grid_transparency_changed)
    
    def _on_average_color_changed(self):
        """Handle average color change."""
        color = self.average_color_combo.currentData()
        log.info(f"=== AVERAGE COLOR CHANGED ===")
        log.info(f"New color: {color}")
        log.info(f"Before update - current_preferences: {self.current_preferences}")
        self.current_preferences['average']['color'] = color
        log.info(f"After update - current_preferences: {self.current_preferences}")
        log.info(f"Original preferences: {self._original_preferences}")
        log.info(f"Manager preferences: {self.customization_manager.get_all_preferences()}")
    
    def _on_average_width_changed(self):
        """Handle average width change."""
        width = self.average_width_combo.currentData()
        self.current_preferences['average']['width'] = width
    
    def _on_average_transparency_changed(self):
        """Handle average transparency change."""
        transparency = self.average_transparency_combo.currentData()
        self.current_preferences['average']['transparency'] = transparency
    
    def _on_single_trial_color_changed(self):
        """Handle single trial color change."""
        color = self.single_trial_color_combo.currentData()
        self.current_preferences['single_trial']['color'] = color
    
    def _on_single_trial_width_changed(self):
        """Handle single trial width change."""
        width = self.single_trial_width_combo.currentData()
        self.current_preferences['single_trial']['width'] = width
    
    def _on_single_trial_transparency_changed(self):
        """Handle single trial transparency change."""
        transparency = self.single_trial_transparency_combo.currentData()
        self.current_preferences['single_trial']['transparency'] = transparency
    
    def _on_grid_color_changed(self):
        """Handle grid color change."""
        color = self.grid_color_combo.currentData()
        self.current_preferences['grid']['color'] = color
    
    def _on_grid_width_changed(self):
        """Handle grid width change."""
        width = self.grid_width_combo.currentData()
        self.current_preferences['grid']['width'] = width
    
    def _on_grid_transparency_changed(self):
        """Handle grid transparency change."""
        transparency = self.grid_transparency_combo.currentData()
        self.current_preferences['grid']['transparency'] = transparency
    
    def _reset_to_defaults(self):
        """Reset all preferences to default values."""
        try:
            self.customization_manager.reset_to_defaults()
            self.current_preferences = copy.deepcopy(self.customization_manager.get_all_preferences())
            self._load_current_preferences()
            # Reset the original preferences reference - use deep copy
            self._original_preferences = copy.deepcopy(self.current_preferences)
            log.info("Preferences reset to defaults")
        except Exception as e:
            log.error(f"Failed to reset preferences: {e}")
    
    def _apply_changes(self):
        """Apply current changes and save preferences."""
        try:
            # Check if preferences actually changed
            if self._preferences_changed():
                # Use batch update for better performance
                if hasattr(self.customization_manager, 'update_preferences_batch'):
                    success = self.customization_manager.update_preferences_batch(
                        self.current_preferences, 
                        emit_signal=True
                    )
                    if success:
                        log.info("Plot preferences applied and saved via batch update")
                        # Update the original preferences reference after successful save
                        self._original_preferences = copy.deepcopy(self.current_preferences)
                    else:
                        log.warning("Batch update failed - falling back to individual updates")
                        # Fallback to individual updates
                        self.customization_manager.save_preferences()
                        self._original_preferences = copy.deepcopy(self.current_preferences)
                else:
                    # Fallback for older versions
                    self.customization_manager.save_preferences()
                    self._original_preferences = copy.deepcopy(self.current_preferences)
                    log.info("Plot preferences applied and saved (fallback method)")
                
                # Signal is already emitted by the customization manager
                # No need to call _notify_plot_update() here
            else:
                log.info("No changes detected - skipping save and update")
            
        except Exception as e:
            log.error(f"Failed to apply preferences: {e}")

    def _preferences_changed(self):
        """Check if preferences have actually changed from the original."""
        try:
            log.info("=== CHECKING FOR PREFERENCE CHANGES ===")
            log.info(f"Current preferences: {self.current_preferences}")
            log.info(f"Original preferences: {self._original_preferences}")
            
            # Compare current preferences with the original ones
            for plot_type in self.current_preferences:
                for property_name in self.current_preferences[plot_type]:
                    current_value = self.current_preferences[plot_type][property_name]
                    original_value = self._original_preferences[plot_type][property_name]
                    
                    log.info(f"Comparing {plot_type}.{property_name}: current='{current_value}' vs original='{original_value}'")
                    
                    if current_value != original_value:
                        log.info(f"Change detected: {plot_type}.{property_name} = '{current_value}' (was '{original_value}')")
                        return True
            
            log.info("No changes detected in preferences comparison")
            return False
        except Exception as e:
            log.warning(f"Could not check preference changes: {e}")
            return True  # Assume changed if we can't check

    def _notify_plot_update(self):
        """Notify the application that plots need to be updated."""
        try:
            # The signal is already emitted in save_preferences()
            # Just log that we've notified about the update
            log.debug("Plot update notification sent via global signal")
        except Exception as e:
            log.warning(f"Failed to trigger plot updates: {e}")

    def _ok_clicked(self):
        """Handle OK button click - apply changes and close."""
        self._apply_changes()
        self.accept()
