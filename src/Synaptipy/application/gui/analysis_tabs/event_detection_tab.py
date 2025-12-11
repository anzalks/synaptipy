# src/Synaptipy/application/gui/analysis_tabs/event_detection_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting synaptic events (Miniature and Evoked).
Refactored to use MetadataDrivenAnalysisTab architecture and ParameterWidgetGenerator.
"""
import logging
from typing import Optional, Dict, Any, List
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .base import BaseAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.application.gui.ui_generator import ParameterWidgetGenerator
import Synaptipy.core.analysis.event_detection # Ensure registration

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.event_detection_tab')

class EventDetectionTab(BaseAnalysisTab):
    """
    QWidget for Synaptic Event Detection (Miniature and Evoked).
    Uses ParameterWidgetGenerator to dynamically create UI for selected method.
    """

    # Define the class constant for dynamic loading
    ANALYSIS_TAB_CLASS = True

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        super().__init__(neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent)

        # --- UI References --- 
        self.splitter: Optional[QtWidgets.QSplitter] = None
        self.mini_method_combobox: Optional[QtWidgets.QComboBox] = None
        self.mini_results_textedit: Optional[QtWidgets.QTextEdit] = None
        
        # Parameter Stack
        self.mini_params_stack: Optional[QtWidgets.QStackedWidget] = None
        self._param_generators: Dict[str, ParameterWidgetGenerator] = {} # Map method name to generator

        # Map display names to registry keys
        self.method_map = {
            "Threshold Based": "event_detection_threshold",
            "Deconvolution (Custom)": "event_detection_deconvolution",
            "Baseline + Peak + Kinetics": "event_detection_baseline_peak"
        }

        # Plotting related
        self.event_markers_item: Optional[pg.ScatterPlotItem] = None
        self._last_event_result: Optional[Dict[str, Any]] = None

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

    def get_covered_analysis_names(self) -> List[str]:
        """Return all registry names covered by this tab."""
        return list(self.method_map.values())

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
        self.mini_method_combobox.addItems(list(self.method_map.keys()))
        self.mini_method_combobox.setToolTip("Choose the miniature event detection algorithm.")
        method_layout.addRow("Method:", self.mini_method_combobox)
        analysis_controls_layout.addLayout(method_layout)
        
        # Stacked Widget for Parameter Groups
        self.mini_params_stack = QtWidgets.QStackedWidget()
        analysis_controls_layout.addWidget(self.mini_params_stack)
        
        # Create Parameter Groups using Generator
        self._create_parameter_groups()
        
        # Analysis Action Button (Optional, but useful for explicit run)
        # Note: MetadataDrivenAnalysisTab uses reactive updates. 
        # Here we can keep the button or make it reactive.
        # Let's keep the button for consistency with previous behavior, 
        # but also hook up reactive changes if desired.
        self.analyze_button = QtWidgets.QPushButton("Detect Events")
        self.analyze_button.setToolTip("Run event detection with current parameters")
        analysis_controls_layout.addWidget(self.analyze_button)
        
        # Batch Button
        self._setup_batch_button(analysis_controls_layout)
        
        left_layout.addWidget(analysis_controls_group)
        
        # Results Group
        results_group = QtWidgets.QGroupBox("Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        self.mini_results_textedit = QtWidgets.QTextEdit()
        self.mini_results_textedit.setReadOnly(True)
        self.mini_results_textedit.setMaximumHeight(150)
        results_layout.addWidget(self.mini_results_textedit)
        left_layout.addWidget(results_group)
        
        # Save Button
        self._setup_save_button(left_layout)
        
        left_layout.addStretch() # Push everything up
        
        # Add left widget to splitter
        self.splitter.addWidget(left_widget)
        
        # --- Right Side: Plot Area ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout)
        
        # Initialize Plot Items
        if self.plot_widget:
            self.event_markers_item = pg.ScatterPlotItem(size=10, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 150))
            self.plot_widget.addItem(self.event_markers_item)
            self.event_markers_item.setVisible(False)
            
            self.threshold_line = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen('b', style=QtCore.Qt.PenStyle.DashLine))
            self.plot_widget.addItem(self.threshold_line)
            self.threshold_line.setVisible(False)
        
        # Add right widget to splitter
        self.splitter.addWidget(plot_container)
        
        # Set initial splitter sizes (33% left, 67% right)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(self.splitter)
        
        self.setLayout(main_layout)
        # self._restore_state() # Restore splitter state - Not available in BaseAnalysisTab yet
        
        # Initial setup
        self._on_mini_method_changed()

    def _create_parameter_groups(self):
        """Create parameter widgets for each method using ParameterWidgetGenerator."""
        self._param_generators = {}
        
        for method_display, registry_key in self.method_map.items():
            # Get metadata
            metadata = AnalysisRegistry.get_metadata(registry_key)
            ui_params = metadata.get('ui_params', [])
            
            # Create GroupBox and Layout
            group = QtWidgets.QGroupBox(f"{method_display} Parameters")
            layout = QtWidgets.QFormLayout(group)
            
            # Create Generator
            generator = ParameterWidgetGenerator(layout)
            generator.generate_widgets(ui_params, self._on_param_changed)
            
            # Store
            self._param_generators[registry_key] = generator
            self.mini_params_stack.addWidget(group)

    def _update_ui_for_selected_item(self):
        """Update UI when a new item is selected."""
        if not self._selected_item_recording:
            self.signal_channel_combobox.clear()
            if self.plot_widget:
                self.plot_widget.clear()
            return

        self.signal_channel_combobox.blockSignals(True)
        self.signal_channel_combobox.clear()
        
        for channel in self._selected_item_recording.channels.values():
            name = channel.name or f"Channel {channel.id}"
            self.signal_channel_combobox.addItem(name, userData=channel.id)
            
        self.signal_channel_combobox.blockSignals(False)
        
        if self.signal_channel_combobox.count() > 0:
            self.signal_channel_combobox.setCurrentIndex(0)
            self._on_channel_changed(0)
        
        # Analyze button
        self.analyze_button.clicked.connect(self._trigger_analysis)
        
        # Note: Parameter changes are connected via generator callback to _on_param_changed

    def _on_channel_changed(self, index):
        """Handle channel selection change."""
        if index < 0 or not self._selected_item_recording:
            return
            
        channel_id = self.signal_channel_combobox.itemData(index)
        if channel_id is None:
            return
            
        channel = self._selected_item_recording.channels.get(channel_id)
        if not channel:
            log.error(f"Channel ID {channel_id} not found.")
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
                
                # Re-create and add markers to ensure they are valid and on top
                self.event_markers_item = pg.ScatterPlotItem(size=10, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 200))
                self.event_markers_item.setZValue(100) # Ensure on top
                self.plot_widget.addItem(self.event_markers_item)
                self.event_markers_item.setVisible(False)
                
                # Re-create and add threshold line
                self.threshold_line = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen('b', style=QtCore.Qt.PenStyle.DashLine, width=2))
                self.threshold_line.setZValue(90) # Below markers, above trace
                self.plot_widget.addItem(self.threshold_line)
                self.threshold_line.setVisible(False)
                    
            # Trigger analysis
            self._trigger_analysis()
        else:
            log.warning(f"No data for channel {channel.name}")

    def _connect_signals(self):
        """Connect signals."""
        # Method selection
        self.mini_method_combobox.currentIndexChanged.connect(self._on_mini_method_changed)
        
        # Analyze button
        self.analyze_button.clicked.connect(self._trigger_analysis)
        
        # Note: Parameter changes are connected via generator callback to _on_param_changed

    def _on_mini_method_changed(self):
        """Handle method change."""
        idx = self.mini_method_combobox.currentIndex()
        if idx >= 0:
            self.mini_params_stack.setCurrentIndex(idx)
            # Clear results on method change
            self.mini_results_textedit.clear()
            if self.event_markers_item:
                self.event_markers_item.setData([])
                self.event_markers_item.setVisible(False)

    def _on_param_changed(self):
        """Handle parameter changes (debounce)."""
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """Gather parameters from the currently active generator."""
        registry_key = self.get_registry_name()
        generator = self._param_generators.get(registry_key)
        if generator:
            return generator.gather_params()
        return {}

    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the registered analysis function."""
        registry_key = self.get_registry_name()
        func = AnalysisRegistry.get_function(registry_key)
        
        if not func:
            raise ValueError(f"Analysis function '{registry_key}' not found.")
            
        voltage = data['data']
        time = data['time']
        fs = data['sampling_rate']
        
        try:
            # Call the function
            results = func(voltage, time, fs, **params)
            return results
        except Exception as e:
            log.error(f"Analysis execution failed: {e}")
            raise

    def _on_analysis_result(self, results: Any):
        """Handle analysis results."""
        if isinstance(results, dict) and 'result' in results:
             result_data = results['result']
        else:
             result_data = results

        self._last_event_result = result_data
        
        # Display Text
        self._display_analysis_results(result_data)
        
        # Update Plot
        self._plot_analysis_visualizations(result_data)
        
        # Enable save button
        self._set_save_button_enabled(True)
        
        # Update Accumulation UI
        self._update_accumulation_ui_state()

    def _plot_analysis_visualizations(self, result_data: Any):
        """Visualize analysis results on the plot."""
        if not isinstance(result_data, dict):
            return
            
        event_indices = result_data.get('event_indices')
        if event_indices is not None and len(event_indices) > 0 and self._current_plot_data:
            times = self._current_plot_data['time'][event_indices]
            voltages = self._current_plot_data['data'][event_indices]
            
            log.info(f"Plotting {len(event_indices)} events. First time: {times[0]:.4f}, Voltage: {voltages[0]:.4f}")
            
            if self.event_markers_item:
                # Use explicit keyword arguments for safety
                self.event_markers_item.setData(x=times, y=voltages)
                self.event_markers_item.setVisible(True)
                # Ensure it's added to the plot if it was somehow removed
                if self.event_markers_item not in self.plot_widget.listDataItems():
                     self.plot_widget.addItem(self.event_markers_item)
        else:
            if self.event_markers_item:
                self.event_markers_item.setVisible(False)
                
        # Update Threshold Line if available
        threshold_val = result_data.get('threshold') or result_data.get('threshold_value')
        if threshold_val is not None and self.threshold_line:
            self.threshold_line.setValue(threshold_val)
            self.threshold_line.setVisible(True)
        elif self.threshold_line:
            self.threshold_line.setVisible(False)

    def _display_analysis_results(self, result: Dict[str, Any]):
        """Display results in text edit."""
        if not result or 'event_error' in result:
            self.mini_results_textedit.setText(f"Analysis failed: {result.get('event_error', 'Unknown error')}")
            return

        count = result.get('event_count', 0)
        freq = result.get('frequency_hz')
        mean_amp = result.get('mean_amplitude')
        amp_sd = result.get('amplitude_sd')
        
        text = f"--- Event Detection Results ---\n"
        text += f"Method: {self.mini_method_combobox.currentText()}\n"
        text += f"Count: {count}\n"
        
        if freq is not None:
            text += f"Frequency: {freq:.2f} Hz\n"
        
        if mean_amp is not None:
            text += f"Mean Amplitude: {mean_amp:.2f} ± {amp_sd:.2f}\n"
            
        # Add specific details based on method
        if 'threshold' in result:
            text += f"Threshold Used: {result['threshold']}\n"
        if 'baseline_mean' in result:
            text += f"Baseline: {result['baseline_mean']:.2f} ± {result['baseline_sd']:.2f}\n"
            
        self.mini_results_textedit.setHtml(text)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        return self._last_event_result

# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = EventDetectionTab