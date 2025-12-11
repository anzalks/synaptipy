# src/Synaptipy/application/gui/analysis_tabs/rin_tab.py
# -*- coding: utf-8 -*-
"""
Analysis tab for calculating Input Resistance (Rin) with interactive selection.
Refactored to use MetadataDrivenAnalysisTab architecture and ParameterWidgetGenerator.
"""
import logging
from typing import Optional, Dict, Any, Tuple
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .base import BaseAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.application.gui.ui_generator import ParameterWidgetGenerator
import Synaptipy.core.analysis.intrinsic_properties # Ensure registration

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rin_tab')

class RinAnalysisTab(BaseAnalysisTab):
    """
    Widget for Input Resistance/Conductance calculation with interactive plotting.
    Uses ParameterWidgetGenerator for parameter inputs.
    """

    # Class constants for modes
    _MODE_INTERACTIVE = "Interactive (Regions)"
    _MODE_MANUAL = "Manual (Time Windows)"

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        super().__init__(neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent)

        # UI References
        self.splitter: Optional[QtWidgets.QSplitter] = None
        self.mode_combobox: Optional[QtWidgets.QComboBox] = None
        self.param_generator: Optional[ParameterWidgetGenerator] = None
        self.params_group: Optional[QtWidgets.QGroupBox] = None
        
        self.results_label: Optional[QtWidgets.QLabel] = None
        self.status_label: Optional[QtWidgets.QLabel] = None
        
        # Plotting
        self.baseline_region: Optional[pg.LinearRegionItem] = None
        self.response_region: Optional[pg.LinearRegionItem] = None
        self.baseline_line: Optional[pg.InfiniteLine] = None
        self.response_line: Optional[pg.InfiniteLine] = None
        
        self._last_rin_result: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._connect_signals()
        self._on_mode_changed()

    def get_display_name(self) -> str:
        return "Resistance/Conductance"

    def get_registry_name(self) -> str:
        return "rin_analysis"

    def get_covered_analysis_names(self) -> list[str]:
        return ["rin_analysis", "tau_analysis"]

    def _setup_ui(self):
        """Set up the UI elements."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Splitter
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # --- Left Side: Controls ---
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        # Global controls
        self.global_controls_layout = left_layout
        
        # Data Selection
        data_group = QtWidgets.QGroupBox("Data Selection")
        data_layout = QtWidgets.QFormLayout(data_group)
        self._setup_data_selection_ui(data_layout)
        left_layout.addWidget(data_group)
        
        # Analysis Parameters
        self.params_group = QtWidgets.QGroupBox("Analysis Parameters")
        params_layout = QtWidgets.QVBoxLayout(self.params_group)
        
        # Mode Selection
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel("Mode:"))
        self.mode_combobox = QtWidgets.QComboBox()
        self.mode_combobox.addItem(self._MODE_INTERACTIVE)
        self.mode_combobox.addItem(self._MODE_MANUAL)
        mode_layout.addWidget(self.mode_combobox)
        params_layout.addLayout(mode_layout)
        
        # Generator for Parameters
        form_layout = QtWidgets.QFormLayout()
        self.param_generator = ParameterWidgetGenerator(form_layout)
        
        # Get metadata
        metadata = AnalysisRegistry.get_metadata(self.get_registry_name())
        ui_params = metadata.get('ui_params', [])
        self.param_generator.generate_widgets(ui_params, self._on_param_changed)
        
        params_layout.addLayout(form_layout)
        left_layout.addWidget(self.params_group)
        
        # Action Button
        self.calc_button = QtWidgets.QPushButton("Calculate Rin/G")
        self.calc_button.clicked.connect(self._trigger_analysis)
        left_layout.addWidget(self.calc_button)
        

        
        # Results
        results_group = QtWidgets.QGroupBox("Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        self.results_label = QtWidgets.QLabel("No results.")
        self.results_label.setWordWrap(True)
        results_layout.addWidget(self.results_label)
        left_layout.addWidget(results_group)
        
        # Save Button
        self._setup_save_button(left_layout)
        
        left_layout.addStretch()
        self.splitter.addWidget(left_widget)
        
        # --- Right Side: Plot ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout)
        self.splitter.addWidget(plot_container)
        
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        main_layout.addWidget(self.splitter)
        
        # Initialize Regions
        if self.plot_widget:
            self.baseline_region = pg.LinearRegionItem(values=[0, 0.1], brush=pg.mkBrush(0, 0, 255, 50))
            self.response_region = pg.LinearRegionItem(values=[0.3, 0.4], brush=pg.mkBrush(255, 0, 0, 50))
            self.plot_widget.addItem(self.baseline_region)
            self.plot_widget.addItem(self.response_region)
            
            self.baseline_region.sigRegionChanged.connect(self._on_region_changed)
            self.response_region.sigRegionChanged.connect(self._on_region_changed)
            
            self.baseline_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('b', style=QtCore.Qt.PenStyle.DashLine))
            self.response_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
            self.plot_widget.addItem(self.baseline_line)
            self.plot_widget.addItem(self.response_line)
            self.baseline_line.setVisible(False)
            self.response_line.setVisible(False)

    def _connect_signals(self):
        self.mode_combobox.currentIndexChanged.connect(self._on_mode_changed)
        if self.signal_channel_combobox:
            self.signal_channel_combobox.currentIndexChanged.connect(self._on_channel_changed)
        # Generator callback connected in generate_widgets

    def _update_ui_for_selected_item(self):
        """Update UI when a new item is selected."""
        if not self._selected_item_recording:
            if self.signal_channel_combobox:
                self.signal_channel_combobox.clear()
            if self.plot_widget:
                self.plot_widget.clear()
            return

        if self.signal_channel_combobox:
            self.signal_channel_combobox.blockSignals(True)
            self.signal_channel_combobox.clear()
            
            for channel in self._selected_item_recording.channels.values():
                name = channel.name or f"Channel {channel.id}"
                self.signal_channel_combobox.addItem(name, userData=channel.id)
                
            self.signal_channel_combobox.blockSignals(False)
            
            if self.signal_channel_combobox.count() > 0:
                self.signal_channel_combobox.setCurrentIndex(0)
                self._on_channel_changed(0)

    def _on_channel_changed(self, index):
        """Handle channel selection change."""
        if index < 0 or not self._selected_item_recording:
            return
            
        channel_id = self.signal_channel_combobox.itemData(index)
        if channel_id is None:
            return
            
        channel = self._selected_item_recording.channels.get(channel_id)
        if not channel:
            return
            
        # Extract data
        if channel.data_trials and len(channel.data_trials) > 0:
            data = channel.data_trials[0].flatten()
            sampling_rate = self._selected_item_recording.sampling_rate
            
            # Create time array
            time = np.arange(len(data)) / sampling_rate
            
            self._current_plot_data = {
                'time': time,
                'data': data,
                'sampling_rate': sampling_rate
            }
            
            # Plot
            if self.plot_widget:
                self.plot_widget.clear()
                self.plot_widget.plot(time, data, pen='k')
                
                # Re-add regions
                if self.baseline_region:
                    self.plot_widget.addItem(self.baseline_region)
                if self.response_region:
                    self.plot_widget.addItem(self.response_region)
                    
                # Re-add lines if they exist
                if self.baseline_line:
                    self.plot_widget.addItem(self.baseline_line)
                if self.response_line:
                    self.plot_widget.addItem(self.response_line)

    def _on_mode_changed(self):
        mode = self.mode_combobox.currentText()
        is_interactive = (mode == self._MODE_INTERACTIVE)
        
        if self.baseline_region:
            self.baseline_region.setVisible(is_interactive)
        if self.response_region:
            self.response_region.setVisible(is_interactive)
            
        # In Interactive mode, we might want to hide time spinboxes but keep amplitude inputs?
        # The generator creates all widgets.
        # We can disable time widgets in interactive mode.
        # Time widgets: baseline_start, baseline_end, response_start, response_end
        time_params = ['baseline_start', 'baseline_end', 'response_start', 'response_end']
        for name in time_params:
            widget = self.param_generator.widgets.get(name)
            if widget:
                widget.setEnabled(not is_interactive)
                
        # Also disable auto_detect in interactive mode?
        auto_detect = self.param_generator.widgets.get('auto_detect_pulse')
        if auto_detect:
            auto_detect.setEnabled(not is_interactive)

    def _on_region_changed(self):
        """Update generator widgets from regions."""
        if self.mode_combobox.currentText() != self._MODE_INTERACTIVE:
            return
            
        if self.baseline_region:
            min_x, max_x = self.baseline_region.getRegion()
            self.param_generator.set_params({'baseline_start': min_x, 'baseline_end': max_x})
            
        if self.response_region:
            min_x, max_x = self.response_region.getRegion()
            self.param_generator.set_params({'response_start': min_x, 'response_end': max_x})
            
        # Trigger analysis (debounce)
        self._on_param_changed()

    def _on_param_changed(self):
        """Handle parameter changes."""
        # Sync regions if in Manual mode
        if self.mode_combobox.currentText() == self._MODE_MANUAL:
            params = self.param_generator.gather_params()
            if self.baseline_region:
                self.baseline_region.setRegion([params.get('baseline_start', 0), params.get('baseline_end', 0.1)])
            if self.response_region:
                self.response_region.setRegion([params.get('response_start', 0.3), params.get('response_end', 0.4)])
        
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        params = self.param_generator.gather_params()
        
        # If interactive, force auto_detect to False (we are manually setting regions)
        if self.mode_combobox.currentText() == self._MODE_INTERACTIVE:
            params['auto_detect_pulse'] = False
            
        return params

    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        func = AnalysisRegistry.get_function(self.get_registry_name())
        if not func:
            return {}
            
        return func(data['data'], data['time'], data['sampling_rate'], **params)

    def _on_analysis_result(self, results: Any):
        if isinstance(results, dict) and 'result' in results:
             result_data = results['result']
        else:
             result_data = results

        self._last_rin_result = result_data
        self._display_analysis_results(result_data)
        
        # Enable save button
        self._set_save_button_enabled(True)
        
        # Update Accumulation UI state
        self._update_accumulation_ui_state()
        
        # Update visualization lines
        if result_data and 'baseline_voltage_mv' in result_data:
            self.baseline_line.setValue(result_data['baseline_voltage_mv'])
            self.baseline_line.setVisible(True)
        else:
            self.baseline_line.setVisible(False)
            
        if result_data and 'steady_state_voltage_mv' in result_data:
            self.response_line.setValue(result_data['steady_state_voltage_mv'])
            self.response_line.setVisible(True)
        else:
            self.response_line.setVisible(False)

    def _display_analysis_results(self, result: Dict[str, Any]):
        if not result or 'rin_error' in result:
            self.results_label.setText(f"Error: {result.get('rin_error', 'Unknown')}")
            return
            
        text = "--- Results ---\n"
        if result.get('rin_mohm') is not None:
            text += f"Rin: {result['rin_mohm']:.2f} MOhm\n"
        if result.get('conductance_us') is not None:
            text += f"Conductance: {result['conductance_us']:.3f} uS\n"
        if result.get('voltage_deflection_mv') is not None:
            text += f"Delta V: {result['voltage_deflection_mv']:.2f} mV\n"
            
        self.results_label.setText(text)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        return self._last_rin_result

# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = RinAnalysisTab