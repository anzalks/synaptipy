# src/Synaptipy/application/gui/analysis_tabs/event_detection_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting synaptic events (Miniature and Evoked).
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import time

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .base import BaseAnalysisTab
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.core.analysis import event_detection as ed
from Synaptipy.infrastructure.file_readers import NeoAdapter
# from Synaptipy.application.gui.plotting.plotting_utils import CustomPlotWidget # Removed import
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                             QPushButton, QDoubleSpinBox, QFormLayout, QGroupBox, QSizePolicy)
from PySide6.QtCore import Qt, Signal as pyqtSignal, QTimer # Use Signal alias if needed, though direct use is fine

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.event_detection_tab')

class EventDetectionTab(BaseAnalysisTab):
    """QWidget for Synaptic Event Detection (Miniature and Evoked)."""

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__(neo_adapter=neo_adapter, parent=parent)

        # --- UI References --- 
        self.channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None

        # Miniature Event Controls
        self.mini_method_combobox: Optional[QtWidgets.QComboBox] = None
        self.mini_detect_button: Optional[QtWidgets.QPushButton] = None
        self.mini_results_textedit: Optional[QtWidgets.QTextEdit] = None
        
        # Parameter Groups (will be added to a stacked widget)
        self.mini_params_stack: Optional[QtWidgets.QStackedWidget] = None
        self._mini_params_group_map: Dict[str, QtWidgets.QWidget] = {} # To map method name to widget

        self.mini_threshold_group: Optional[QtWidgets.QGroupBox] = None
        self.mini_deconvolution_group: Optional[QtWidgets.QGroupBox] = None
        self.mini_baseline_peak_group: Optional[QtWidgets.QGroupBox] = None

        # Specific Parameter Widgets
        self.mini_threshold_edit: Optional[QtWidgets.QLineEdit] = None # For Threshold Based
        self.mini_direction_combo: Optional[QtWidgets.QComboBox] = None # For Threshold, Baseline+Peak
        
        self.mini_deconv_tau_rise_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.mini_deconv_tau_decay_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.mini_deconv_filter_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.mini_deconv_threshold_sd_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None

        self.mini_baseline_filter_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.mini_baseline_prominence_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None # Optional prominence

        # Plotting related (Shared)
        self.plot_widget: Optional[pg.PlotWidget] = None
        self.data_plot_item: Optional[pg.PlotDataItem] = None
        self.event_markers_item: Optional[pg.ScatterPlotItem] = None
        self._current_plot_data: Optional[Dict[str, Any]] = None

        # Analysis results
        self._last_analysis_result: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent AnalyserTab calling update_state()

    def get_display_name(self) -> str:
        return "Event Detection"

    def _setup_ui(self):
        """Create UI elements for the Event Detection tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5) # Add some margins
        main_layout.setSpacing(5)

        # --- Top Horizontal Section for Controls and Sub-Tabs ---
        top_section_layout = QtWidgets.QHBoxLayout()
        top_section_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Left Side: Top Controls Area (Shared) ---
        shared_controls_group = QtWidgets.QGroupBox("Data Selection")
        # Limit width and vertical expansion
        shared_controls_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        shared_controls_layout = QtWidgets.QVBoxLayout(shared_controls_group)
        shared_controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        item_selector_layout = QtWidgets.QFormLayout()
        self._setup_analysis_item_selector(item_selector_layout)
        shared_controls_layout.addLayout(item_selector_layout)

        channel_select_layout = QtWidgets.QHBoxLayout()
        channel_select_layout.addWidget(QtWidgets.QLabel("Plot Channel:"))
        self.channel_combobox = QtWidgets.QComboBox()
        self.channel_combobox.setToolTip("Select the current or voltage channel to analyze.")
        self.channel_combobox.setEnabled(False)
        channel_select_layout.addWidget(self.channel_combobox, stretch=1)
        shared_controls_layout.addLayout(channel_select_layout)

        data_source_layout = QtWidgets.QHBoxLayout()
        data_source_layout.addWidget(QtWidgets.QLabel("Data Source:"))
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace.")
        self.data_source_combobox.setEnabled(False)
        data_source_layout.addWidget(self.data_source_combobox, stretch=1)
        shared_controls_layout.addLayout(data_source_layout)
        
        top_section_layout.addWidget(shared_controls_group) # Add data selection to the left

        # --- Right Side: Sub-Tab Widget ---
        self.sub_tab_widget = QtWidgets.QTabWidget()
        top_section_layout.addWidget(self.sub_tab_widget, stretch=1) # Add sub-tabs to the right, allow stretch

        # Add the top horizontal section to the main layout
        main_layout.addLayout(top_section_layout)

        # --- Populate Sub-Tabs (Miniature, Evoked) ---
        # (The content setup for these tabs remains the same internally)

        # --- Miniature Event Sub-Tab Content --- 
        miniature_widget = QtWidgets.QWidget()
        miniature_layout = QtWidgets.QVBoxLayout(miniature_widget)
        miniature_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Horizontal Layout for Method + Parameters (Inside Miniature tab)
        method_params_layout = QtWidgets.QHBoxLayout()
        method_params_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Method Selection Group 
        mini_method_group = QtWidgets.QGroupBox("Miniature Detection Method")
        mini_method_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Preferred) # Limit width
        mini_method_layout = QtWidgets.QFormLayout(mini_method_group)
        
        self.mini_method_combobox = QtWidgets.QComboBox()
        # Define method names consistently
        method_threshold = "Threshold Based"
        method_deconv = "Deconvolution (Custom)"
        method_baseline = "Baseline + Peak + Kinetics"
        self.mini_method_combobox.addItems([
            method_threshold, 
            method_deconv, 
            method_baseline
        ])
        self.mini_method_combobox.setToolTip("Choose the miniature event detection algorithm.")
        mini_method_layout.addRow("Method:", self.mini_method_combobox)
        
        # Shared Direction ComboBox (used by multiple methods)
        self.mini_direction_combo = QtWidgets.QComboBox()
        self.mini_direction_combo.addItems(["negative", "positive"])
        self.mini_direction_combo.setToolTip("Detect events (peaks or threshold crossings) in this direction.")
        # Add it to the method group layout
        mini_method_layout.addRow("Event Direction:", self.mini_direction_combo)
        
        method_params_layout.addWidget(mini_method_group) 

        # Stacked Widget for Parameter Groups
        self.mini_params_stack = QtWidgets.QStackedWidget()
        method_params_layout.addWidget(self.mini_params_stack, stretch=1) 

        # Create Parameter Groups and add to Stack 
        self._mini_params_group_map = {} # Reset map

        # 1. Threshold Based Parameters
        self.mini_threshold_group = QtWidgets.QGroupBox("Threshold Parameters")
        thresh_layout = QtWidgets.QFormLayout(self.mini_threshold_group)
        self.mini_threshold_edit = QtWidgets.QLineEdit("-5.0") # Default negative
        self.mini_threshold_edit.setToolTip("Amplitude threshold value. Units match plot.")
        # Store the label widget itself to update its text later
        self.mini_threshold_label = QtWidgets.QLabel("Threshold Value (?):") 
        thresh_layout.addRow(self.mini_threshold_label, self.mini_threshold_edit) # Use stored label widget
        thresh_layout.addRow(QtWidgets.QLabel("(Direction set in Method group)")) # Clarify direction location
        self.mini_params_stack.addWidget(self.mini_threshold_group)
        self._mini_params_group_map[method_threshold] = self.mini_threshold_group

        # 3. Deconvolution (Custom) Parameters
        self.mini_deconvolution_group = QtWidgets.QGroupBox("Deconvolution Parameters")
        deconv_layout = QtWidgets.QFormLayout(self.mini_deconvolution_group)
        self.mini_deconv_tau_rise_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_deconv_tau_rise_spinbox.setRange(0.1, 1000.0); self.mini_deconv_tau_rise_spinbox.setValue(1.0); self.mini_deconv_tau_rise_spinbox.setSuffix(" ms")
        deconv_layout.addRow("Tau Rise:", self.mini_deconv_tau_rise_spinbox)
        self.mini_deconv_tau_decay_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_deconv_tau_decay_spinbox.setRange(0.1, 5000.0); self.mini_deconv_tau_decay_spinbox.setValue(5.0); self.mini_deconv_tau_decay_spinbox.setSuffix(" ms")
        deconv_layout.addRow("Tau Decay:", self.mini_deconv_tau_decay_spinbox)
        self.mini_deconv_filter_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_deconv_filter_spinbox.setRange(0, 20000.0); self.mini_deconv_filter_spinbox.setValue(1000.0); self.mini_deconv_filter_spinbox.setSuffix(" Hz")
        self.mini_deconv_filter_spinbox.setToolTip("Pre-filter cutoff (0 = None)")
        deconv_layout.addRow("Filter Cutoff:", self.mini_deconv_filter_spinbox)
        self.mini_deconv_threshold_sd_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_deconv_threshold_sd_spinbox.setRange(0.1, 20.0); self.mini_deconv_threshold_sd_spinbox.setValue(3.0); self.mini_deconv_threshold_sd_spinbox.setSuffix(" *SD")
        self.mini_deconv_threshold_sd_spinbox.setToolTip("Threshold based on deconvolved trace noise SD")
        deconv_layout.addRow("Detection Thr (SD):", self.mini_deconv_threshold_sd_spinbox)
        deconv_layout.addRow(QtWidgets.QLabel("(Direction is implicitly negative)")) # Deconv assumes neg events for now
        self.mini_params_stack.addWidget(self.mini_deconvolution_group)
        self._mini_params_group_map[method_deconv] = self.mini_deconvolution_group

        # 4. Baseline + Peak + Kinetics Parameters (Simplified)
        self.mini_baseline_peak_group = QtWidgets.QGroupBox("Baseline+Peak Parameters")
        basepk_layout = QtWidgets.QFormLayout(self.mini_baseline_peak_group)
        self.mini_baseline_filter_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_baseline_filter_spinbox.setRange(0, 20000.0); self.mini_baseline_filter_spinbox.setValue(500.0); self.mini_baseline_filter_spinbox.setSuffix(" Hz")
        self.mini_baseline_filter_spinbox.setToolTip("Pre-filter before peak finding (0 = None)")
        basepk_layout.addRow("Filter Cutoff:", self.mini_baseline_filter_spinbox)
        self.mini_baseline_prominence_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_baseline_prominence_spinbox.setRange(0, 10.0); self.mini_baseline_prominence_spinbox.setValue(0.0); self.mini_baseline_prominence_spinbox.setSuffix(" * ThrSD") # 0 means disabled
        self.mini_baseline_prominence_spinbox.setToolTip("Optional peak prominence factor (relative to auto-Threshold*SD, 0=Disabled)")
        basepk_layout.addRow("Min Prominence Factor:", self.mini_baseline_prominence_spinbox)
        basepk_layout.addRow(QtWidgets.QLabel("(Direction set in Method group)"))
        basepk_layout.addRow(QtWidgets.QLabel("(Baseline/Threshold calculated automatically)")) # Add note
        self.mini_params_stack.addWidget(self.mini_baseline_peak_group)
        self._mini_params_group_map[method_baseline] = self.mini_baseline_peak_group

        # Add the horizontal layout containing Method+Params to the miniature tab's layout
        miniature_layout.addLayout(method_params_layout) 

        # Miniature Action Button 
        self.mini_detect_button = QtWidgets.QPushButton("Detect Miniature Events")
        self.mini_detect_button.setEnabled(False)
        self.mini_detect_button.setToolTip("Detect miniature events using the selected method and parameters.")
        self.mini_detect_button.setMinimumHeight(30)
        mini_button_layout = QtWidgets.QHBoxLayout()
        mini_button_layout.addStretch()
        mini_button_layout.addWidget(self.mini_detect_button)
        mini_button_layout.addStretch()
        miniature_layout.addLayout(mini_button_layout)

        # Miniature Results Display Area
        mini_results_group = QtWidgets.QGroupBox("Results")
        mini_results_layout = QtWidgets.QVBoxLayout(mini_results_group)
        self.mini_results_textedit = QtWidgets.QTextEdit()
        self.mini_results_textedit.setReadOnly(True)
        self.mini_results_textedit.setFixedHeight(150) # Slightly taller for kinetics
        self.mini_results_textedit.setPlaceholderText("Event count, frequency, amplitude, kinetics will appear here...")
        mini_results_layout.addWidget(self.mini_results_textedit)
        miniature_layout.addWidget(mini_results_group)

        # Miniature Save Button 
        self._setup_save_button(miniature_layout)

        miniature_layout.addStretch(1)
        self.sub_tab_widget.addTab(miniature_widget, "Miniature") # Add the populated widget to the sub-tab

        # --- Evoked Event Sub-Tab (Placeholder) ---
        evoked_widget = QtWidgets.QWidget()
        evoked_layout = QtWidgets.QVBoxLayout(evoked_widget)
        evoked_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        placeholder_label = QtWidgets.QLabel("Evoked Event Analysis (Not Yet Implemented)")
        placeholder_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        evoked_layout.addWidget(placeholder_label)
        evoked_layout.addStretch(1)
        self.sub_tab_widget.addTab(evoked_widget, "Evoked")

        # --- Plot Area (Shared, placed below the top section) ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout)
        
        # Create event markers but don't add to plot yet
        # They will be added when data is loaded to prevent Qt graphics errors
        if self.plot_widget:
            self.event_markers_item = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(0, 0, 255, 150))
            # Markers will be added to plot when data is loaded
        
        main_layout.addWidget(plot_container, stretch=1) # Add plot below controls/tabs section

        self.setLayout(main_layout)
        self._on_mini_method_changed() # Set initial visibility for params

    def _connect_signals(self):
        """Connect signals for Event Detection tab widgets."""
        self.channel_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        self.data_source_combobox.currentIndexChanged.connect(self._plot_selected_trace)
        self.mini_detect_button.clicked.connect(self._run_miniature_event_detection)
        self.mini_method_combobox.currentIndexChanged.connect(self._on_mini_method_changed)

    @QtCore.Slot()
    def _on_mini_method_changed(self):
        """Show the correct parameter group in the stack based on selected method."""
        if not self.mini_method_combobox or not self.mini_params_stack or not self._mini_params_group_map:
             return
             
        selected_method = self.mini_method_combobox.currentText()
        target_widget = self._mini_params_group_map.get(selected_method)

        if target_widget:
             self.mini_params_stack.setCurrentWidget(target_widget)
             log.debug(f"Mini method changed to: {selected_method}. Set stack to widget: {target_widget.__class__.__name__}")
        else:
             log.warning(f"No parameter widget mapped for method: {selected_method}")
             # Optionally set to a default or empty widget if needed
             # self.mini_params_stack.setCurrentIndex(0) # Or find an appropriate default

        # --- Handle Direction ComboBox Visibility ---
        # Direction combo is needed for all methods except Deconvolution (currently)
        is_deconv = (selected_method == "Deconvolution (Custom)")
        direction_visible = not is_deconv
        
        if self.mini_direction_combo:
            # Find the direction combo within the method group layout
            layout = self.mini_method_combobox.parent().layout() 
            if isinstance(layout, QtWidgets.QFormLayout):
                 for i in range(layout.rowCount()):
                    label_item = layout.itemAt(i, QtWidgets.QFormLayout.ItemRole.LabelRole)
                    widget_item = layout.itemAt(i, QtWidgets.QFormLayout.ItemRole.FieldRole)
                    if widget_item and widget_item.widget() == self.mini_direction_combo:
                         # Found the row for the direction combo
                         label_widget = label_item.widget() if label_item else None
                         field_widget = widget_item.widget()
                         
                         if label_widget: label_widget.setVisible(direction_visible)
                         if field_widget: field_widget.setVisible(direction_visible)
                         log.debug(f"Set Direction combo visibility to {direction_visible}")
                         break # Stop searching once found
            else:
                 # Fallback if layout structure changes unexpectedly
                 log.warning("Could not find direction combo in expected QFormLayout to control visibility.")
                 self.mini_direction_combo.setVisible(direction_visible)

    def _update_ui_for_selected_item(self):
        """Update Event Detection tab UI for new analysis item."""
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        self._current_plot_data = None
        if self.mini_results_textedit: self.mini_results_textedit.setText("")
        if self.mini_detect_button: self.mini_detect_button.setEnabled(False)
        if self.save_button: self.save_button.setEnabled(False)

        # Populate Channel ComboBox
        self.channel_combobox.blockSignals(True)
        self.channel_combobox.clear()
        all_channels_found = False # Use a single flag
        if self._selected_item_recording and self._selected_item_recording.channels:
            # Iterate once and add all channels
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                 units = getattr(channel, 'units', '')
                 display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{units}]"
                 self.channel_combobox.addItem(display_name, userData=chan_id)
                 all_channels_found = True # Mark if we add at least one

        if not all_channels_found:
            self.channel_combobox.addItem("No Channels Found")
        else:
            self.channel_combobox.setCurrentIndex(0) # Select first channel if found

        self.channel_combobox.setEnabled(all_channels_found)
        self.channel_combobox.blockSignals(False)

        # Populate Data Source ComboBox
        self.data_source_combobox.blockSignals(True)
        self.data_source_combobox.clear()
        self.data_source_combobox.setEnabled(False)
        can_analyze = False
        if all_channels_found and self._selected_item_recording:
            selected_item_details = self._analysis_items[self._selected_item_index]
            item_type = selected_item_details.get('target_type')
            item_trial_index = selected_item_details.get('trial_index')
            num_trials = 0
            has_average = False
            first_channel = next(iter(self._selected_item_recording.channels.values()), None)
            if first_channel:
                 num_trials = getattr(first_channel, 'num_trials', 0)
                 # Check multiple ways for average data existence
                 if hasattr(first_channel, 'get_averaged_data') and first_channel.get_averaged_data() is not None: has_average = True
                 elif hasattr(first_channel, 'has_average_data') and first_channel.has_average_data(): has_average = True
                 elif getattr(first_channel, '_averaged_data', None) is not None: has_average = True

            if item_type == "Current Trial" and item_trial_index is not None and 0 <= item_trial_index < num_trials:
                self.data_source_combobox.addItem(f"Trial {item_trial_index + 1}", userData=item_trial_index)
                can_analyze = True
            elif item_type == "Average Trace" and has_average:
                self.data_source_combobox.addItem("Average Trace", userData="average")
                can_analyze = True
            elif item_type == "Recording" or item_type == "All Trials":
                if has_average: self.data_source_combobox.addItem("Average Trace", userData="average")
                if num_trials > 0:
                    for i in range(num_trials):
                        self.data_source_combobox.addItem(f"Trial {i + 1}", userData=i)
                if self.data_source_combobox.count() > 0:
                    self.data_source_combobox.setEnabled(True)
                    can_analyze = True
                else:
                    self.data_source_combobox.addItem("No Trials/Average")
            else:
                 self.data_source_combobox.addItem("Invalid Source Item")
                 log.warning(f"Invalid source item type: {item_type}")
        else:
             self.data_source_combobox.addItem("N/A")
        self.data_source_combobox.blockSignals(False)

        # <<< ADDED: Update dynamic labels >>>
        if all_channels_found and self._selected_item_recording:
            first_chan_id = self.channel_combobox.currentData()
            first_channel = self._selected_item_recording.channels.get(first_chan_id)
            if first_channel:
                units = first_channel.units or '?'
                # Update Threshold Label
                if hasattr(self, 'mini_threshold_label') and self.mini_threshold_label: # Check attribute exists
                    self.mini_threshold_label.setText(f"Threshold Value ({units}):")
        else:
            # Reset labels if no suitable channel
            if hasattr(self, 'mini_threshold_label') and self.mini_threshold_label: # Check attribute exists
                 self.mini_threshold_label.setText("Threshold Value (?):")
        # <<< END ADDED >>>

        # Enable/Disable Miniature Controls
        mini_controls_enabled = can_analyze
        if self.mini_method_combobox: self.mini_method_combobox.setEnabled(mini_controls_enabled)
        if self.mini_detect_button: self.mini_detect_button.setEnabled(mini_controls_enabled)
        self._on_mini_method_changed() # Update parameter visibility/stack based on current method

        # Plot Initial Trace
        if mini_controls_enabled:
            self._plot_selected_trace()
        else:
            if self.plot_widget: self.plot_widget.clear()
            if self.channel_combobox: self.channel_combobox.setEnabled(False)
            if self.data_source_combobox: self.data_source_combobox.setEnabled(False)


    def _plot_selected_trace(self):
        """Plots the selected trace and clears previous events."""
        plot_succeeded = False
        self._current_plot_data = None
        if self.mini_results_textedit: self.mini_results_textedit.clear()
        if self.event_markers_item: self.event_markers_item.setData([])
        if self.save_button: self.save_button.setEnabled(False)

        # Clear plot widget completely first
        if self.plot_widget: self.plot_widget.clear()
        # Re-add markers item after clearing
        if self.plot_widget and self.event_markers_item:
             if self.event_markers_item not in self.plot_widget.items():
                 self.plot_widget.addItem(self.event_markers_item)
             self.event_markers_item.setVisible(False) # Keep hidden initially

        if not self._selected_item_recording or not self.channel_combobox or not self.data_source_combobox:
            if self.mini_detect_button: self.mini_detect_button.setEnabled(False)
            return

        chan_id = self.channel_combobox.currentData()
        source_data_key = self.data_source_combobox.currentData()
        if chan_id is None or source_data_key is None:
             if self.mini_detect_button: self.mini_detect_button.setEnabled(False)
             return

        channel = self._selected_item_recording.channels.get(chan_id)
        log.debug(f"Event Plotting: Ch {chan_id}, Source Key: {source_data_key}")

        # <<< ADDED: Update dynamic labels on plot >>>
        if channel and hasattr(self, 'mini_threshold_label') and self.mini_threshold_label: # Check attribute exists
            units = channel.units or '?'
            self.mini_threshold_label.setText(f"Threshold Value ({units}):")
        # <<< END ADDED >>>

        time_vec, data_vec = None, None
        data_label = "Plot Error"
        units = "?"
        sample_rate = None

        try:
            if channel:
                units = channel.units or "?"
                sample_rate = channel.sampling_rate
                if sample_rate is None:
                     log.error(f"Sample rate missing for channel {chan_id}")
                     raise ValueError("Missing sample rate")

                if source_data_key == "average":
                    data_vec = channel.get_averaged_data()
                    time_vec = channel.get_relative_averaged_time_vector()
                    data_label = f"{channel.name or chan_id} (Average)"
                elif isinstance(source_data_key, int):
                    trial_index = source_data_key
                    if 0 <= trial_index < channel.num_trials:
                        data_vec = channel.get_data(trial_index)
                        time_vec = channel.get_relative_time_vector(trial_index)
                        data_label = f"{channel.name or chan_id} (Trial {trial_index + 1})"
                    else:
                        log.warning(f"Invalid trial index {trial_index} for Ch {chan_id}")
                else:
                     log.warning(f"Unknown data source key: {source_data_key}")

            if time_vec is not None and data_vec is not None:
                self.data_plot_item = self.plot_widget.plot(time_vec, data_vec, pen='k', name=data_label)
                # --- Get Label from Data Model --- 
                units = channel.units or "?"
                base_label = channel.get_primary_data_label()
                self.plot_widget.setLabel('left', base_label, units=units)
                # --- End Get Label from Data Model --- 
                self.plot_widget.setLabel('bottom', 'Time', units='s')
                self.plot_widget.setTitle(data_label)
                self._current_plot_data = {
                    'time': time_vec,
                    'data': data_vec,
                    'units': units,
                    'sampling_rate': sample_rate
                }
                
                # Set data ranges for zoom synchronization
                x_range = (time_vec.min(), time_vec.max())
                y_range = (data_vec.min(), data_vec.max())
                self.set_data_ranges(x_range, y_range)
                
                plot_succeeded = True
                log.debug(f"Event Detection Plotting Success. Rate: {sample_rate}")
                self.plot_widget.autoRange()
            else:
                log.warning(f"Event Plotting: No valid data vector for Ch {chan_id}, Source: {source_data_key}")
                if self.plot_widget: self.plot_widget.setTitle("Plot Error: No Data Vector")
                self._current_plot_data = None

        except Exception as e:
            log.error(f"Event Plotting Error: Ch {chan_id}, Source {source_data_key}: {e}", exc_info=True)
            if self.plot_widget: self.plot_widget.setTitle("Plot Error")
            self._current_plot_data = None

        if self.mini_detect_button: self.mini_detect_button.setEnabled(plot_succeeded)
        self._on_mini_method_changed() # Ensure parameter groups update state too
        # Clear results & disable save regardless, analysis needs re-run
        if self.mini_results_textedit: self.mini_results_textedit.clear()
        if self.save_button: self.save_button.setEnabled(False)


    @QtCore.Slot()
    def _run_miniature_event_detection(self):
        """Runs Miniature Event Detection based on selected method and parameters."""
        log.debug("Run Miniature Event Detection triggered.")
        
        if not self._current_plot_data:
            log.warning("Cannot run mini detection: No data plotted.")
            QtWidgets.QMessageBox.warning(self, "No Data", "Please select and plot data first.")
            return

        data = self._current_plot_data.get('data')
        sample_rate = self._current_plot_data.get('sampling_rate')
        units = self._current_plot_data.get('units', '?')
        
        if data is None or sample_rate is None or sample_rate <= 0:
            log.error("Cannot run mini detection: Invalid data or sample rate in current plot data.")
            QtWidgets.QMessageBox.critical(self, "Invalid Data", "Internal error: Plotted data is missing or invalid.")
            return

        selected_method = self.mini_method_combobox.currentText()
        log.info(f"Attempting detection using method: {selected_method}")

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        if self.mini_results_textedit: self.mini_results_textedit.clear()
        if self.event_markers_item: self.event_markers_item.setData([])
        
        run_successful = False
        results_str = f"--- {selected_method} Results ---\n"
        self._last_analysis_result = None # Clear previous results
        peak_indices = np.array([])
        event_details_list = None # For baseline+peak method

        try:
            # --- Call Appropriate Core Function --- 
            if selected_method == "Threshold Based":
                try:
                    threshold = float(self.mini_threshold_edit.text())
                    direction = self.mini_direction_combo.currentText()
                    if (direction == 'negative' and threshold > 0) or (direction == 'positive' and threshold < 0):
                         log.warning(f"Threshold sign ({threshold}) contradicts direction ('{direction}'). Using absolute value.")
                         # Threshold func expects positive value, direction handles sign internally? NO - func needs absolute val threshold?
                         # Let's try passing the value as is for now, core func should handle it.
                         pass # Pass threshold as entered
                    log.info(f"Params: threshold={threshold}, direction={direction}")
                    # Using the generic threshold crossing function now
                    peak_indices, stats = ed.detect_events_threshold_crossing(data, threshold, direction)
                    results_str += f"Direction: {direction}\nThreshold Value: {threshold:.3g} {units}\n"
                    results_str += f"Detected Events: {stats.get('count', 0)}\n"
                    self._last_analysis_result = {
                        'method': selected_method,
                        'parameters': {'threshold': threshold, 'direction': direction},
                        'summary_stats': stats,
                        'event_indices': peak_indices,
                        'event_details': None # No detailed kinetics from this method
                    }
                    run_successful = True
                except ValueError:
                    raise ValueError("Invalid threshold value entered.")
                except Exception as e:
                     raise RuntimeError(f"Threshold detection failed: {e}")
            
            elif selected_method == "Deconvolution (Custom)":
                tau_rise = self.mini_deconv_tau_rise_spinbox.value()
                tau_decay = self.mini_deconv_tau_decay_spinbox.value()
                filter_freq = self.mini_deconv_filter_spinbox.value()
                threshold_sd = self.mini_deconv_threshold_sd_spinbox.value()
                filter_freq_param = filter_freq if filter_freq > 0 else None
                log.info(f"Params: rise={tau_rise}ms, decay={tau_decay}ms, filter={filter_freq_param}Hz, thr_sd={threshold_sd}")
                if tau_decay <= tau_rise: raise ValueError("Tau Decay must be > Tau Rise")
                
                peak_indices, stats = ed.detect_events_deconvolution_custom(
                    data, sample_rate, tau_rise, tau_decay, threshold_sd, filter_freq_param
                )
                results_str += (f"Parameters: Rise={tau_rise:.1f}ms, Decay={tau_decay:.1f}ms, Filter={filter_freq_param or 'None'}Hz, Thr={threshold_sd:.1f}*SD\n")
                results_str += f"Detected Events: {stats.get('count', 0)}\n"
                self._last_analysis_result = {
                    'method': selected_method,
                    'parameters': {'tau_rise': tau_rise, 'tau_decay': tau_decay, 'filter': filter_freq_param, 'thr_sd': threshold_sd},
                    'summary_stats': stats,
                    'event_indices': peak_indices,
                    'event_details': None # No detailed kinetics from this method yet
                }
                run_successful = True

            elif selected_method == "Baseline + Peak + Kinetics":
                direction = self.mini_direction_combo.currentText()
                filter_freq = self.mini_baseline_filter_spinbox.value()
                prominence_factor = self.mini_baseline_prominence_spinbox.value()
                filter_freq_param = filter_freq if filter_freq > 0 else None
                prominence_param = prominence_factor if prominence_factor > 0 else None
                log.info(f"Params: dir={direction}, filter={filter_freq_param}Hz, prominence={prominence_param}. Baseline/Threshold auto-calculated.")
                
                peak_indices, summary_stats, event_details_list = ed.detect_events_baseline_peak_kinetics(
                    data, sample_rate, direction, 
                    filter_freq_param, 
                    peak_prominence_factor=prominence_param
                )
                
                results_str += (f"Parameters: Dir={direction}, Filter={filter_freq_param or 'None'}Hz, Prominence={prominence_param or 'None'}\n")
                results_str += f"Baseline Mean (auto): {summary_stats.get('baseline_mean', np.nan):.3g} {units}\n"
                results_str += f"Baseline SD (auto): {summary_stats.get('baseline_sd', np.nan):.3g} {units}\n"
                results_str += f"Detection Threshold (auto): {summary_stats.get('threshold', np.nan):.3g} {units}\n"
                results_str += f"Detected Events: {summary_stats.get('count', 0)}\n\n"
                
                if event_details_list:
                     # Calculate summary stats from details
                     amps = np.array([d['amplitude'] for d in event_details_list])
                     rise_times = np.array([d['rise_time_ms'] for d in event_details_list])
                     decay_times = np.array([d['decay_half_time_ms'] for d in event_details_list])
                     time_vec = self._current_plot_data.get('time', np.array([0, 1])) # Get time for freq calc
                     duration = time_vec[-1] - time_vec[0] if len(time_vec) > 1 else 1.0
                     freq = len(amps) / duration if duration > 0 else 0.0
                     
                     results_str += f"Frequency: {freq:.3f} Hz\n"
                     results_str += f"Mean Amplitude: {np.nanmean(amps):.3g} +/- {np.nanstd(amps):.3g} {units}\n"
                     results_str += f"Mean 10-90 Rise Time: {np.nanmean(rise_times):.3g} +/- {np.nanstd(rise_times):.3g} ms\n"
                     results_str += f"Mean Decay Half-Time: {np.nanmean(decay_times):.3g} +/- {np.nanstd(decay_times):.3g} ms\n"
                     
                     summary_stats['frequency_hz'] = freq
                     summary_stats['mean_amplitude'] = np.nanmean(amps)
                     summary_stats['amplitude_sd'] = np.nanstd(amps)
                     summary_stats['mean_rise_time_ms'] = np.nanmean(rise_times)
                     summary_stats['rise_time_sd_ms'] = np.nanstd(rise_times)
                     summary_stats['mean_decay_half_time_ms'] = np.nanmean(decay_times)
                     summary_stats['decay_half_time_sd_ms'] = np.nanstd(decay_times)
                     
                self._last_analysis_result = {
                    'method': selected_method,
                    'parameters': {'direction': direction, 'filter': filter_freq_param, 'prominence': prominence_param},
                    'summary_stats': summary_stats,
                    'event_indices': peak_indices,
                    'event_details': event_details_list 
                }
                run_successful = True

            else:
                raise NotImplementedError(f"Method '{selected_method}' is not implemented.")

            # --- Plot Markers --- 
            if run_successful and len(peak_indices) > 0:
                 event_times = peak_indices / sample_rate
                 # Use original data for plotting marker values
                 event_values = data[peak_indices] 
                 if self.event_markers_item:
                     self.event_markers_item.setData(x=event_times, y=event_values)
                     self.event_markers_item.setVisible(True)
                     log.info(f"Plotted {len(peak_indices)} event markers.")
                 else:
                     log.warning("Event marker item not available for plotting.")
            else:
                 if self.event_markers_item: self.event_markers_item.setData([]) # Clear if no events

        except Exception as e:
            log.error(f"Error during {selected_method} detection: {e}", exc_info=True)
            results_str += f"\nError: {e}"
            if self.event_markers_item: self.event_markers_item.setData([]) # Clear markers on error
            self._last_analysis_result = None
            run_successful = False

        finally:
            if self.mini_results_textedit: self.mini_results_textedit.setText(results_str)
            QtWidgets.QApplication.restoreOverrideCursor()
            if self.save_button: self.save_button.setEnabled(run_successful and self._last_analysis_result is not None)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Gathers the specific Event Detection analysis details for saving."""
        if not self._last_analysis_result:
            log.debug("_get_specific_result_data (EventDetection): No analysis results available.")
            return None

        # Get data source information
        channel_id = self.channel_combobox.currentData()
        channel_name = self.channel_combobox.currentText().split(' (')[0]
        data_source = self.data_source_combobox.currentData()
        data_source_text = self.data_source_combobox.currentText()
        units = self._current_plot_data.get('units', '?') if self._current_plot_data else '?'

        if channel_id is None or data_source is None:
            log.warning("Cannot get specific Event Detection data: Missing channel or data source.")
            return None

        # Format the data for saving
        method = self._last_analysis_result.get('method', 'Unknown')
        parameters = self._last_analysis_result.get('parameters', {})
        
        # Remove parameters no longer set via UI for Baseline+Peak method
        if method == "Baseline + Peak + Kinetics":
            parameters.pop('baseline_win', None)
            parameters.pop('baseline_step', None)
            parameters.pop('thr_sd', None)

        specific_data = {
            'method': method,
            'parameters': parameters, # Use potentially modified parameters dict
            'summary_stats': self._last_analysis_result.get('summary_stats', {}),
            'event_indices': self._last_analysis_result.get('event_indices', np.array([])).tolist(),
            'event_details': self._last_analysis_result.get('event_details', None), 
             # Data Source Info (for base class)
            'channel_id': channel_id,
            'channel_name': channel_name,
            'data_source': data_source,
            'data_source_label': data_source_text,
            'units': units
        }
        # Add sample rate to parameters if available
        if self._current_plot_data and 'sampling_rate' in self._current_plot_data:
             specific_data['parameters']['sampling_rate_hz'] = self._current_plot_data['sampling_rate']
             
        log.debug(f"_get_specific_result_data (EventDetection) returning keys: {list(specific_data.keys())}")
        return specific_data


# --- END CLASS EventDetectionTab ---

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = EventDetectionTab 