# src/Synaptipy/application/gui/analysis_tabs/event_detection_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting synaptic events (Miniature and Evoked).
Refactored to use Template Method pattern and AnalysisRegistry.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .base import BaseAnalysisTab
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.core.analysis import event_detection as ed
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.infrastructure.file_readers import NeoAdapter
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                             QPushButton, QDoubleSpinBox, QFormLayout, QGroupBox, QSizePolicy, QSplitter)

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.event_detection_tab')

class EventDetectionTab(BaseAnalysisTab):
    """QWidget for Synaptic Event Detection (Miniature and Evoked)."""

    # Define the class constant for dynamic loading
    ANALYSIS_TAB_CLASS = True

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        super().__init__(neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent)

        # --- UI References --- 
        self.sub_tab_widget: Optional[QtWidgets.QTabWidget] = None
        self.splitter: Optional[QtWidgets.QSplitter] = None

        # Miniature Event Controls
        self.mini_method_combobox: Optional[QtWidgets.QComboBox] = None
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
        self.mini_baseline_prominence_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None 

        # Plotting related (Shared)
        self.event_markers_item: Optional[pg.ScatterPlotItem] = None

        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent AnalyserTab calling update_state()

    def get_display_name(self) -> str:
        return "Event Detection"

    def get_registry_name(self) -> str:
        """Return registry name based on selected method."""
        if not self.mini_method_combobox:
            return "event_detection_threshold" # Default
        selected_method_display = self.mini_method_combobox.currentText()
        return self.method_map.get(selected_method_display, "event_detection_threshold")

    def _setup_ui(self):
        """Create UI elements for the Event Detection tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # --- Use a Splitter for flexible layout ---
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # --- Left Side: Controls (Analysis Params, Results) ---
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        # Store reference for global controls injection
        self.global_controls_layout = left_layout
        
        # Data Selection Group (Shared)
        shared_controls_group = QtWidgets.QGroupBox("Data Selection")
        shared_controls_layout = QtWidgets.QFormLayout(shared_controls_group)
        self._setup_data_selection_ui(shared_controls_layout)
        left_layout.addWidget(shared_controls_group)
        
        # Analysis Controls Group
        analysis_controls_group = QtWidgets.QGroupBox("Analysis Parameters")
        analysis_controls_layout = QtWidgets.QVBoxLayout(analysis_controls_group)
        
        # Method Selection
        method_layout = QtWidgets.QFormLayout()
        self.mini_method_combobox = QtWidgets.QComboBox()
        # Map display names to registry keys
        self.method_map = {
            "Threshold Based": "event_detection_threshold",
            "Deconvolution (Custom)": "event_detection_deconvolution",
            "Baseline + Peak + Kinetics": "event_detection_baseline_peak"
        }
        self.mini_method_combobox.addItems(list(self.method_map.keys()))
        self.mini_method_combobox.setToolTip("Choose the miniature event detection algorithm.")
        method_layout.addRow("Method:", self.mini_method_combobox)
        
        # Shared Direction ComboBox
        self.mini_direction_combo = QtWidgets.QComboBox()
        self.mini_direction_combo.addItems(["negative", "positive"])
        self.mini_direction_combo.setToolTip("Detect events (peaks or threshold crossings) in this direction.")
        method_layout.addRow("Direction:", self.mini_direction_combo)
        analysis_controls_layout.addLayout(method_layout)
        
        # Stacked Widget for Parameter Groups
        self.mini_params_stack = QtWidgets.QStackedWidget()
        analysis_controls_layout.addWidget(self.mini_params_stack)
        
        # Create Parameter Groups
        self._create_parameter_groups()
        
        # Analysis Action Button
        self.analyze_button = QtWidgets.QPushButton("Detect Events")
        self.analyze_button.setToolTip("Run event detection with current parameters")
        analysis_controls_layout.addWidget(self.analyze_button)
        
        # Batch Button
        self._setup_batch_button(analysis_controls_layout)
        
        left_layout.addWidget(analysis_controls_group)
        
        # Results Group (Moved to Left)
        results_group = QtWidgets.QGroupBox("Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        self.mini_results_textedit = QtWidgets.QTextEdit()
        self.mini_results_textedit.setReadOnly(True)
        self.mini_results_textedit.setMaximumHeight(150)
        results_layout.addWidget(self.mini_results_textedit)
        left_layout.addWidget(results_group)
        
        # Save Button (Moved to Left)
        self._setup_save_button(left_layout)
        
        left_layout.addStretch() # Push everything up
        
        # Add left widget to splitter
        self.splitter.addWidget(left_widget)
        
        # --- Right Side: Plot Area ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout)
        
        # Add right widget to splitter
        self.splitter.addWidget(plot_container)
        
        # Set initial splitter sizes (33% left, 67% right)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(self.splitter)
        
        # Create event markers item
        if self.plot_widget:
            self.event_markers_item = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(0, 0, 255, 150))
            # Markers will be added to plot when data is loaded
        
        self.setLayout(main_layout)
        self._restore_state() # Restore splitter state
        self._on_mini_method_changed() # Set initial visibility

    def _create_parameter_groups(self):
        """Create parameter widgets for each method."""
        self._mini_params_group_map = {} 

        # 1. Threshold Based Parameters
        self.mini_threshold_group = QtWidgets.QGroupBox("Threshold Parameters")
        thresh_layout = QtWidgets.QFormLayout(self.mini_threshold_group)
        self.mini_threshold_edit = QtWidgets.QLineEdit("-5.0") 
        self.mini_threshold_label = QtWidgets.QLabel("Threshold:") 
        thresh_layout.addRow(self.mini_threshold_label, self.mini_threshold_edit)
        self.mini_params_stack.addWidget(self.mini_threshold_group)
        self._mini_params_group_map["Threshold Based"] = self.mini_threshold_group

        # 2. Deconvolution Parameters
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
        deconv_layout.addRow("Filter Cutoff:", self.mini_deconv_filter_spinbox)
        self.mini_deconv_threshold_sd_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_deconv_threshold_sd_spinbox.setRange(0.1, 20.0); self.mini_deconv_threshold_sd_spinbox.setValue(3.0); self.mini_deconv_threshold_sd_spinbox.setSuffix(" *SD")
        deconv_layout.addRow("Detection Thr:", self.mini_deconv_threshold_sd_spinbox)
        self.mini_params_stack.addWidget(self.mini_deconvolution_group)
        self._mini_params_group_map["Deconvolution (Custom)"] = self.mini_deconvolution_group

        # 3. Baseline + Peak Parameters
        self.mini_baseline_peak_group = QtWidgets.QGroupBox("Baseline+Peak Parameters")
        basepk_layout = QtWidgets.QFormLayout(self.mini_baseline_peak_group)
        self.mini_baseline_filter_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_baseline_filter_spinbox.setRange(0, 20000.0); self.mini_baseline_filter_spinbox.setValue(500.0); self.mini_baseline_filter_spinbox.setSuffix(" Hz")
        basepk_layout.addRow("Filter Cutoff:", self.mini_baseline_filter_spinbox)
        self.mini_baseline_prominence_spinbox = QtWidgets.QDoubleSpinBox()
        self.mini_baseline_prominence_spinbox.setRange(0, 10.0); self.mini_baseline_prominence_spinbox.setValue(0.0); self.mini_baseline_prominence_spinbox.setSuffix(" * ThrSD")
        basepk_layout.addRow("Min Prominence:", self.mini_baseline_prominence_spinbox)
        self.mini_params_stack.addWidget(self.mini_baseline_peak_group)
        self._mini_params_group_map["Baseline + Peak + Kinetics"] = self.mini_baseline_peak_group

    def _connect_signals(self):
        """Connect signals for Event Detection tab widgets."""
        # Use template method trigger
        self.analyze_button.clicked.connect(self._trigger_analysis)
        self.mini_method_combobox.currentIndexChanged.connect(self._on_mini_method_changed)
        
        # Connect parameter changes to debounced analysis
        if hasattr(self, 'mini_threshold_edit'):
            self.mini_threshold_edit.textChanged.connect(self._on_parameter_changed)
        if hasattr(self, 'mini_direction_combo'):
            self.mini_direction_combo.currentIndexChanged.connect(self._on_parameter_changed)
        if hasattr(self, 'mini_deconv_tau_rise_spinbox'):
            self.mini_deconv_tau_rise_spinbox.valueChanged.connect(self._on_parameter_changed)
        if hasattr(self, 'mini_deconv_tau_decay_spinbox'):
            self.mini_deconv_tau_decay_spinbox.valueChanged.connect(self._on_parameter_changed)
        if hasattr(self, 'mini_deconv_threshold_sd_spinbox'):
            self.mini_deconv_threshold_sd_spinbox.valueChanged.connect(self._on_parameter_changed)
        if hasattr(self, 'mini_baseline_filter_spinbox'):
            self.mini_baseline_filter_spinbox.valueChanged.connect(self._on_parameter_changed)
        if hasattr(self, 'mini_baseline_prominence_spinbox'):
            self.mini_baseline_prominence_spinbox.valueChanged.connect(self._on_parameter_changed)

    @QtCore.Slot()
    def _on_mini_method_changed(self):
        """Show the correct parameter group in the stack based on selected method."""
        if not self.mini_method_combobox or not self.mini_params_stack:
             return
             
        selected_method_display = self.mini_method_combobox.currentText()
        target_widget = self._mini_params_group_map.get(selected_method_display)

        if target_widget:
             self.mini_params_stack.setCurrentWidget(target_widget)
        
        # Handle Direction ComboBox Visibility
        # Direction is needed for Threshold and Baseline+Peak, but implicitly handled in Deconvolution (usually negative)
        is_deconv = (selected_method_display == "Deconvolution (Custom)")
        if self.mini_direction_combo:
            self.mini_direction_combo.setEnabled(not is_deconv)
            
        # Trigger re-analysis if auto-update is desired, or just let user click button
        # self._trigger_analysis()

    def _update_ui_for_selected_item(self):
        """Update UI when a new item is selected."""
        # Base class handles data loading. We just update control enablement.
        can_analyze = (self._selected_item_recording is not None and 
                      bool(self._selected_item_recording.channels))
        
        self.analyze_button.setEnabled(can_analyze)
        self.mini_method_combobox.setEnabled(can_analyze)
        
        if can_analyze and self._selected_item_recording.channels:
            first_channel = next(iter(self._selected_item_recording.channels.values()), None)
            if first_channel:
                units = first_channel.units or '?'
                if hasattr(self, 'mini_threshold_label') and self.mini_threshold_label:
                    self.mini_threshold_label.setText(f"Threshold ({units}):")

    def _on_data_plotted(self):
        """Hook called after plotting data."""
        # Clear previous markers
        if self.event_markers_item:
            self.event_markers_item.setData([])
            self.event_markers_item.setVisible(False)
            
        # Add marker item to plot if not already there
        if self.plot_widget and self.event_markers_item and self.event_markers_item not in self.plot_widget.items():
            self.plot_widget.addItem(self.event_markers_item)
            
        # Enable analyze button
        self.analyze_button.setEnabled(True)

    # --- Template Method Implementation ---

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """Gather parameters from UI."""
        selected_method_display = self.mini_method_combobox.currentText()
        registry_key = self.method_map.get(selected_method_display)
        
        params = {
            'method_display': selected_method_display,
            'registry_key': registry_key
        }
        
        try:
            if selected_method_display == "Threshold Based":
                params['threshold'] = float(self.mini_threshold_edit.text())
                params['direction'] = self.mini_direction_combo.currentText()
            
            elif selected_method_display == "Deconvolution (Custom)":
                params['tau_rise_ms'] = self.mini_deconv_tau_rise_spinbox.value()
                params['tau_decay_ms'] = self.mini_deconv_tau_decay_spinbox.value()
                params['filter_freq_hz'] = self.mini_deconv_filter_spinbox.value()
                params['threshold_sd'] = self.mini_deconv_threshold_sd_spinbox.value()
            
            elif selected_method_display == "Baseline + Peak + Kinetics":
                params['direction'] = self.mini_direction_combo.currentText()
                params['filter_freq_hz'] = self.mini_baseline_filter_spinbox.value()
                params['peak_prominence_factor'] = self.mini_baseline_prominence_spinbox.value()
                
            return params
        except ValueError:
            log.warning("Invalid parameter input")
            return {}

    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Execute analysis using Registry."""
        registry_key = params.get('registry_key')
        if not registry_key:
            return None
            
        func = AnalysisRegistry.get_function(registry_key)
        if not func:
            log.error(f"Analysis function {registry_key} not found")
            return None
            
        signal_data = data.get('data')
        sample_rate = data.get('sampling_rate')
        time_vec = data.get('time') # Get time vector
        
        if signal_data is None or sample_rate is None or time_vec is None:
            log.error("Missing data, time, or sampling rate for event detection.")
            return None
            
        # Prepare arguments based on function signature (simplified here)
        # In a robust system, we might inspect signature or use **params
        try:
            # Common args
            kwargs = params.copy()
            kwargs.pop('method_display', None)
            kwargs.pop('registry_key', None)
            
            # Call function
            # Note: The registered functions return different tuple structures
            # We need to handle them uniformly or check key
            
            # ALL registered functions are now WRAPPERS with signature:
            # (data, time, sampling_rate, **kwargs)
            
            if registry_key == "event_detection_threshold":
                # Wrapper returns dict with 'event_indices', 'summary_stats'
                result = func(signal_data, time_vec, sample_rate, **kwargs)
                indices = result.get('event_indices')
                stats = result.get('summary_stats')
                details = None
            elif registry_key == "event_detection_deconvolution":
                # Wrapper returns dict
                result = func(signal_data, time_vec, sample_rate, **kwargs)
                indices = result.get('event_indices')
                stats = result.get('summary_stats')
                details = None
            elif registry_key == "event_detection_baseline_peak":
                # Wrapper returns dict
                result = func(signal_data, time_vec, sample_rate, **kwargs)
                indices = result.get('event_indices')
                stats = result.get('summary_stats')
                details = result.get('event_details')
            else:
                return None
                
            return {
                'method': params.get('method_display'),
                'parameters': params,
                'event_indices': indices,
                'summary_stats': stats,
                'event_details': details,
                'num_events': len(indices) if indices is not None else 0
            }
            
        except Exception as e:
            log.error(f"Analysis execution failed: {e}", exc_info=True)
            return None

    def _display_analysis_results(self, results: Dict[str, Any]):
        """Display results in text area."""
        method = results.get('method')
        num_events = results.get('num_events', 0)
        stats = results.get('summary_stats', {})
        
        text = f"--- {method} Results ---\n"
        text += f"Detected Events: {num_events}\n"
        
        if 'frequency_hz' in stats:
            text += f"Frequency: {stats['frequency_hz']:.2f} Hz\n"
        if 'mean_amplitude' in stats:
            text += f"Mean Amplitude: {stats['mean_amplitude']:.2f}\n"
            
        # Add more details as needed
        self.mini_results_textedit.setText(text)
        
        # Store for saving
        self._last_analysis_result = results

    def _plot_analysis_visualizations(self, results: Dict[str, Any]):
        """Plot event markers."""
        indices = results.get('event_indices')
        if indices is not None and len(indices) > 0 and self._current_plot_data:
            time_vec = self._current_plot_data.get('time')
            data_vec = self._current_plot_data.get('data')
            
            if time_vec is not None and data_vec is not None:
                event_times = time_vec[indices]
                event_values = data_vec[indices]
                
                if self.event_markers_item:
                    self.event_markers_item.setData(x=event_times, y=event_values)
                    self.event_markers_item.setVisible(True)
        else:
            if self.event_markers_item:
                self.event_markers_item.setData([])
                self.event_markers_item.setVisible(False)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Return data for export."""
        if not self._last_analysis_result:
            return None
            
        # Convert numpy types to python types for JSON serialization if needed
        # For now, just return the dict
        return self._last_analysis_result

    # --- State Persistence ---
    def _save_state(self):
        """Save UI state (splitter position) to settings."""
        if self._settings and self.splitter:
            try:
                self._settings.setValue("EventDetectionTab/splitterState", self.splitter.saveState())
                log.debug("Saved EventDetectionTab splitter state.")
            except Exception as e:
                log.error(f"Failed to save EventDetectionTab state: {e}")

    def _restore_state(self):
        """Restore UI state (splitter position) from settings."""
        if self._settings and self.splitter:
            try:
                state = self._settings.value("EventDetectionTab/splitterState")
                if state:
                    self.splitter.restoreState(state)
                    log.debug("Restored EventDetectionTab splitter state.")
            except Exception as e:
                log.error(f"Failed to restore EventDetectionTab state: {e}")

    def cleanup(self):
        """Cleanup resources and save state."""
        self._save_state()
        super().cleanup()

# Expose the class for dynamic loading
ANALYSIS_TAB_CLASS = EventDetectionTab