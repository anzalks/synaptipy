# src/Synaptipy/application/gui/analysis_tabs/rmp_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for calculating Baseline signal properties (Mean/SD).
Refactored to use MetadataDrivenAnalysisTab architecture and ParameterWidgetGenerator.
"""
import logging
from typing import Optional, Dict, Any
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .base import BaseAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.application.gui.ui_generator import ParameterWidgetGenerator
import Synaptipy.core.analysis.basic_features # Ensure registration

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rmp_tab')

class BaselineAnalysisTab(BaseAnalysisTab):
    """
    QWidget for Baseline analysis with interactive plotting.
    Uses ParameterWidgetGenerator for parameter inputs.
    """

    # Define constants for analysis modes
    _MODE_INTERACTIVE = "Interactive"
    _MODE_MANUAL = "Manual"
    _MODE_AUTOMATIC = "Automatic"

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        super().__init__(neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent)

        # UI References
        self.splitter: Optional[QtWidgets.QSplitter] = None
        self.mode_combobox: Optional[QtWidgets.QComboBox] = None
        self.param_generator: Optional[ParameterWidgetGenerator] = None
        
        self.results_label: Optional[QtWidgets.QLabel] = None
        self.status_label: Optional[QtWidgets.QLabel] = None
        
        # Plotting
        self.interactive_region: Optional[pg.LinearRegionItem] = None
        self.baseline_mean_line: Optional[pg.InfiniteLine] = None
        self.baseline_plus_sd_line: Optional[pg.InfiniteLine] = None
        self.baseline_minus_sd_line: Optional[pg.InfiniteLine] = None
        
        self._last_baseline_result: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._connect_signals()
        self._on_mode_changed()

    def get_display_name(self) -> str:
        return "Baseline Analysis"

    def get_registry_name(self) -> str:
        return "rmp_analysis"

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
        params_group = QtWidgets.QGroupBox("Analysis Parameters")
        params_layout = QtWidgets.QVBoxLayout(params_group)
        
        # Mode Selection
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel("Mode:"))
        self.mode_combobox = QtWidgets.QComboBox()
        self.mode_combobox.addItems([self._MODE_INTERACTIVE, self._MODE_MANUAL, self._MODE_AUTOMATIC])
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
        left_layout.addWidget(params_group)
        
        # Action Button
        self.calc_button = QtWidgets.QPushButton("Calculate Baseline")
        self.calc_button.clicked.connect(self._trigger_analysis)
        left_layout.addWidget(self.calc_button)
        

        
        # Results
        results_group = QtWidgets.QGroupBox("Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        self.results_label = QtWidgets.QLabel("Mean ± SD: --")
        self.results_label.setWordWrap(True)
        results_layout.addWidget(self.results_label)
        left_layout.addWidget(results_group)
        
        # Save Button
        self._setup_save_button(left_layout)
        
        # Accumulation UI
        self._setup_accumulation_ui(left_layout)
        
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
        
        # Initialize Plot Items
        if self.plot_widget:
            self.interactive_region = pg.LinearRegionItem(values=[0, 0.1], bounds=[0, 1], movable=True)
            self.interactive_region.setBrush(pg.mkBrush(0, 255, 0, 30))
            self.plot_widget.addItem(self.interactive_region)
            
            self.baseline_mean_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', width=2))
            self.baseline_plus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
            self.baseline_minus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
            
            self.plot_widget.addItem(self.baseline_mean_line)
            self.plot_widget.addItem(self.baseline_plus_sd_line)
            self.plot_widget.addItem(self.baseline_minus_sd_line)
            
            self.baseline_mean_line.setVisible(False)
            self.baseline_plus_sd_line.setVisible(False)
            self.baseline_minus_sd_line.setVisible(False)
            
            self.interactive_region.sigRegionChanged.connect(self._on_region_changed)

    def _connect_signals(self):
        self.mode_combobox.currentIndexChanged.connect(self._on_mode_changed)
        if self.signal_channel_combobox:
            self.signal_channel_combobox.currentIndexChanged.connect(self._on_channel_changed)
            
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
                
                # Re-add region
                if self.interactive_region:
                    self.plot_widget.addItem(self.interactive_region)
                    
                # Re-add lines if they exist
                if self.baseline_mean_line:
                    self.plot_widget.addItem(self.baseline_mean_line)
                    self.baseline_mean_line.setVisible(False)
                if self.baseline_plus_sd_line:
                    self.plot_widget.addItem(self.baseline_plus_sd_line)
                    self.baseline_plus_sd_line.setVisible(False)
                if self.baseline_minus_sd_line:
                    self.plot_widget.addItem(self.baseline_minus_sd_line)
                    self.baseline_minus_sd_line.setVisible(False)

    def _on_mode_changed(self):
        mode = self.mode_combobox.currentText()
        is_interactive = (mode == self._MODE_INTERACTIVE)
        is_automatic = (mode == self._MODE_AUTOMATIC)
        
        if self.interactive_region:
            self.interactive_region.setVisible(is_interactive)
            
        # Update generator widgets state
        # auto_detect checkbox
        auto_detect_widget = self.param_generator.widgets.get('auto_detect')
        if auto_detect_widget:
            # Force auto_detect value based on mode
            if is_automatic:
                auto_detect_widget.setChecked(True)
                auto_detect_widget.setEnabled(False) # Lock it
            else:
                auto_detect_widget.setChecked(False)
                # In manual mode, user could technically check it, but mode combo overrides?
                # Let's disable it in interactive/manual to avoid confusion, 
                # or let manual mode use it if they want (but then it becomes automatic).
                # Simpler: Lock it to False in Interactive/Manual.
                auto_detect_widget.setEnabled(False) 
                
        # Time widgets
        time_widgets = ['baseline_start', 'baseline_end']
        for name in time_widgets:
            widget = self.param_generator.widgets.get(name)
            if widget:
                # Enabled only in Manual mode
                widget.setEnabled(mode == self._MODE_MANUAL)
                
        # Window duration (for auto)
        win_dur_widget = self.param_generator.widgets.get('window_duration')
        if win_dur_widget:
            win_dur_widget.setEnabled(is_automatic)

    def _on_region_changed(self):
        if self.mode_combobox.currentText() != self._MODE_INTERACTIVE:
            return
            
        if self.interactive_region:
            min_x, max_x = self.interactive_region.getRegion()
            self.param_generator.set_params({'baseline_start': min_x, 'baseline_end': max_x})
            self._on_param_changed()

    def _on_param_changed(self):
        # Sync region if Manual
        if self.mode_combobox.currentText() == self._MODE_MANUAL:
            params = self.param_generator.gather_params()
            if self.interactive_region:
                self.interactive_region.setRegion([params.get('baseline_start', 0), params.get('baseline_end', 0.1)])
                
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        params = self.param_generator.gather_params()
        
        # Enforce auto_detect based on mode (just in case UI didn't update param)
        mode = self.mode_combobox.currentText()
        if mode == self._MODE_AUTOMATIC:
            params['auto_detect'] = True
        else:
            params['auto_detect'] = False
            
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

        self._last_baseline_result = result_data
        self._last_baseline_result = result_data
        self._display_analysis_results(result_data)
        
        # Enable save button
        self._set_save_button_enabled(True)
        
        # Update Accumulation UI state
        self._update_accumulation_ui_state()
        
        # Update Plot Lines
        if result_data and 'rmp_mv' in result_data and result_data['rmp_mv'] is not None:
            mean = result_data['rmp_mv']
            sd = result_data.get('rmp_std', 0)
            
            self.baseline_mean_line.setValue(mean)
            self.baseline_mean_line.setVisible(True)
            
            self.baseline_plus_sd_line.setValue(mean + sd)
            self.baseline_plus_sd_line.setVisible(True)
            
            self.baseline_minus_sd_line.setValue(mean - sd)
            self.baseline_minus_sd_line.setVisible(True)
        else:
            self.baseline_mean_line.setVisible(False)
            self.baseline_plus_sd_line.setVisible(False)
            self.baseline_minus_sd_line.setVisible(False)

    def _display_analysis_results(self, result: Dict[str, Any]):
        if not result or 'rmp_error' in result:
            self.results_label.setText(f"Error: {result.get('rmp_error', 'Unknown')}")
            return
            
        mean = result.get('rmp_mv')
        sd = result.get('rmp_std')
        drift = result.get('rmp_drift')
        
        text = f"Mean: {mean:.2f} mV\nSD: {sd:.3f} mV"
        if drift is not None:
            text += f"\nDrift: {drift:.4f} mV/s"
            
        self.results_label.setText(text)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        return self._last_baseline_result

# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = BaselineAnalysisTab