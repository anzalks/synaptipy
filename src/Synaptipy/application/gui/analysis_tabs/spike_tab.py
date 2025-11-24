# src/Synaptipy/application/gui/analysis_tabs/spike_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting spikes using a simple threshold.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# Import base class using relative path within analysis_tabs package
from .base import BaseAnalysisTab
# Import needed core components using absolute paths
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.core.analysis import spike_analysis # Import the analysis function
from Synaptipy.infrastructure.file_readers import NeoAdapter # <<< ADDED
from Synaptipy.core.results import SpikeTrainResult
from Synaptipy.shared.styling import style_button  # Import styling functions

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.spike_tab')

class SpikeAnalysisTab(BaseAnalysisTab):
    """QWidget for Threshold-based Spike Detection."""

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        super().__init__(neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent)

        # --- UI References specific to Spike ---
        # NOTE: channel_combobox and data_source_combobox are now inherited from BaseAnalysisTab
        # Spike parameters
        self.threshold_edit: Optional[QtWidgets.QLineEdit] = None
        self.refractory_edit: Optional[QtWidgets.QLineEdit] = None
        # Action button
        self.detect_button: Optional[QtWidgets.QPushButton] = None # Renamed from run_button
        # Results display
        self.results_textedit: Optional[QtWidgets.QTextEdit] = None
        # ADDED: Plotting related
        self.plot_widget: Optional[pg.PlotWidget] = None
        self.voltage_plot_item: Optional[pg.PlotDataItem] = None
        self.spike_markers_item: Optional[pg.ScatterPlotItem] = None
        self._current_plot_data: Optional[Dict[str, Any]] = None # To store time, voltage, spikes
        self._last_spike_result: Optional[Dict[str, Any]] = None # Store last result for saving
        # Keep internal list of items to analyse (inherited from BaseAnalysisTab)
        # REMOVED: self._analysis_items_for_spike: List[Dict[str, Any]] = [] # Use inherited _analysis_items
        # REMOVED: self._current_recording_for_ui: Optional[Recording] = None # Use inherited _selected_item_recording


        self._setup_ui()
        self._connect_signals()
        # Initial state set by parent AnalyserTab calling update_state()

    def get_display_name(self) -> str:
        return "Spike Detection (Threshold)"

    def _setup_ui(self):
        """Create UI elements for Spike analysis."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # --- Top Horizontal Section ---
        top_section_layout = QtWidgets.QHBoxLayout()
        top_section_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # --- Left: Controls Group ---
        self.controls_group = QtWidgets.QGroupBox("Configuration")
        # Limit width and vertical expansion
        self.controls_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        controls_layout = QtWidgets.QVBoxLayout(self.controls_group)
        controls_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Channel/Data Source (now handled by base class)
        channel_layout = QtWidgets.QFormLayout()
        self._setup_data_selection_ui(channel_layout)
        controls_layout.addLayout(channel_layout)

        # Threshold Input
        threshold_layout = QtWidgets.QFormLayout()
        self.threshold_edit = QtWidgets.QLineEdit("0.0")
        self.threshold_edit.setValidator(QtGui.QDoubleValidator())
        self.threshold_edit.setToolTip("Signal threshold for spike/event detection.")
        self.threshold_edit.setEnabled(False)
        # Store the label widget itself to update its text later
        self.threshold_label = QtWidgets.QLabel("Threshold (?):")
        threshold_layout.addRow(self.threshold_label, self.threshold_edit)
        # ADDED: Refractory Period Input
        self.refractory_edit = QtWidgets.QLineEdit("2.0") # Default 2 ms
        self.refractory_edit.setValidator(QtGui.QDoubleValidator(0.1, 1000.0, 2)) # Min 0.1ms, Max 1s
        self.refractory_edit.setToolTip("Minimum time between detected spikes (refractory period in ms).")
        self.refractory_edit.setEnabled(False)
        threshold_layout.addRow("Refractory (ms):", self.refractory_edit)
        # END ADDED
        controls_layout.addLayout(threshold_layout)

        # Run Button
        self.detect_button = QtWidgets.QPushButton("Detect Spikes")
        self.detect_button.setEnabled(False)
        self.detect_button.setToolTip("Detect spikes on the currently plotted trace using specified parameters.")
        style_button(self.detect_button, 'primary')  # Apply consistent styling directly
        controls_layout.addWidget(self.detect_button)

        controls_layout.addStretch(1)
        top_section_layout.addWidget(self.controls_group) # Add controls to left

        # --- Right: Results Group ---
        self.results_group = QtWidgets.QGroupBox("Results")
        self.results_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Maximum)
        results_layout = QtWidgets.QVBoxLayout(self.results_group)
        self.results_textedit = QtWidgets.QTextEdit()
        self.results_textedit.setReadOnly(True)
        self.results_textedit.setFixedHeight(150) # Make it larger for more features
        self.results_textedit.setPlaceholderText("Spike counts, rates, and features will appear here...")
        results_layout.addWidget(self.results_textedit)
        self._setup_save_button(results_layout) # Add save button here
        results_layout.addStretch(1)
        top_section_layout.addWidget(self.results_group) # Add results to right

        # Add top section to main layout
        main_layout.addLayout(top_section_layout)

        # --- Bottom: Plot Area ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout)
        
        main_layout.addWidget(plot_container, stretch=1)
        
        # Create spike-specific plot items but don't add to plot yet
        # They will be added when data is loaded to prevent Qt graphics errors
        if self.plot_widget:
            self.spike_markers_item = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 150))
            self.threshold_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
            # Items will be added to plot when data is loaded

        self.setLayout(main_layout)

    def _connect_signals(self):
        """Connect signals specific to Spike tab widgets."""
        # NOTE: Channel and Data Source signals are now connected by BaseAnalysisTab._setup_data_selection_ui
        # Plotting and visualization will happen via _on_data_plotted() hook
        
        # Connect detect button
        # PHASE 2: Use template method (direct call, no debouncing for button)
        self.detect_button.clicked.connect(self._trigger_analysis)
        
        # PHASE 3: Connect parameter changes to debounced analysis
        self.threshold_edit.textChanged.connect(self._on_parameter_changed)
        self.refractory_edit.textChanged.connect(self._on_parameter_changed)

    # --- Overridden Methods from Base ---
    def _update_ui_for_selected_item(self):
        """
        Update Spike tab UI for new analysis item.
        NOTE: Channel/data source population and plotting are now handled by BaseAnalysisTab.
        """
        log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
        
        # Clear previous results (but NOT _current_plot_data - base class manages it)
        self.results_textedit.setText("")
        self._last_spike_result = None
        if self.detect_button:
            self.detect_button.setEnabled(False)
        if self.save_button:
            self.save_button.setEnabled(False)
        
        # Determine if analysis can be performed
        can_analyze = (self._selected_item_recording is not None and 
                      bool(self._selected_item_recording.channels))

        # Enable/disable controls
        self.threshold_edit.setEnabled(can_analyze)
        self.refractory_edit.setEnabled(can_analyze)
        self.detect_button.setEnabled(can_analyze)

        # Update threshold label with units if channel is available
        if can_analyze and self._selected_item_recording.channels:
            first_channel = next(iter(self._selected_item_recording.channels.values()), None)
            if first_channel and self.threshold_label:
                units = first_channel.units or '?'
                self.threshold_label.setText(f"Threshold ({units}):")
        else:
            if self.threshold_label:
                self.threshold_label.setText("Threshold (?):")

    # --- PHASE 1 REFACTORING: Hook for Spike-Specific Plot Items ---
    def _on_data_plotted(self):
        """
        Hook called by BaseAnalysisTab after plotting main data trace.
        Adds Spike-specific plot items: spike markers and threshold line.
        """
        log.debug(f"{self.get_display_name()}: _on_data_plotted hook called")
        
        # Clear previous spike analysis
        self.results_textedit.clear()
        if self.spike_markers_item:
            self.spike_markers_item.setData([])
            self.spike_markers_item.setVisible(False)
        if self.threshold_line:
            self.threshold_line.setVisible(False)
        
        # Validate that base class plotted data successfully
        if not self._current_plot_data or 'time' not in self._current_plot_data:
            log.debug("No plot data available, skipping Spike-specific items")
            self.detect_button.setEnabled(False)
            return

        # Add spike-specific visualization items (removed by base class clear())
        if self.spike_markers_item:
            self.plot_widget.addItem(self.spike_markers_item)
        if self.threshold_line:
            self.plot_widget.addItem(self.threshold_line) 

        # Enable detection button now that data is plotted
        self.detect_button.setEnabled(True)
        
        # Update threshold label with correct units
        if self._current_plot_data.get('units') and self.threshold_label:
            units = self._current_plot_data['units']
            self.threshold_label.setText(f"Threshold ({units}):")
        
        log.debug(f"{self.get_display_name()}: Spike-specific plot items added successfully")
    # --- END PHASE 1 REFACTORING ---

    # --- Private Helper Methods specific to Spike Tab ---
    def _validate_params(self) -> bool:
        """Validates Spike Detection parameters."""
        try:
            float(self.threshold_edit.text()) # Check if threshold is a valid float
            r=float(self.refractory_edit.text())
            return r>=0 # Refractory must be non-negative
        except (ValueError, TypeError):
            return False

    # --- REMOVED: _run_spike_analysis (Dead Code) ---
    # This method was replaced by the template method pattern (_execute_core_analysis)
    # and is no longer connected to the UI.

    # --- Base Class Method Implementation --- 
    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        # Gathers the specific Spike analysis details for saving.
        
        if not self._last_spike_result:
            log.debug("_get_specific_result_data (Spike): No spike analysis results available.")
            return None
            
        # Return a copy of the stored result
        return self._last_spike_result.copy()

    # --- PHASE 2: Template Method Pattern Implementation ---
    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """Gather spike detection parameters from UI."""
        if not self._validate_params():
            log.warning("Invalid spike detection parameters")
            return {}
        
        threshold = float(self.threshold_edit.text())
        refractory_ms = float(self.refractory_edit.text())
        refractory_s = refractory_ms / 1000.0
        
        params = {
            'threshold': threshold,
            'refractory_ms': refractory_ms,
            'refractory_s': refractory_s
        }
        log.debug(f"Gathered spike parameters: {params}")
        return params
    
    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Optional[SpikeTrainResult]:
        """Execute spike detection analysis."""
        if not params:
            return None
        
        # Get data
        voltage = data.get('voltage') or data.get('data')
        time = data.get('time')
        rate = data.get('rate')
        units = data.get('units', 'V')
        
        if voltage is None or time is None:
            log.error("Missing voltage or time in plotted data")
            return None

        # Calculate rate if missing
        if rate is None or rate <= 0:
            if len(time) > 1:
                rate = 1.0 / (time[1] - time[0])
            else:
                log.error("Cannot calculate sampling rate from time vector (length <= 1)")
                return None
        
        # Get parameters
        threshold = params.get('threshold')
        refractory_s = params.get('refractory_s')
        
        try:
            # Calculate refractory in samples
            refractory_period_samples = int(refractory_s * rate)
            
            # Run detection
            log.info(f"Running spike detection: Threshold={threshold:.3f}, Refractory={refractory_s:.4f}s")
            result_obj = spike_analysis.detect_spikes_threshold(
                voltage, time, threshold, refractory_period_samples
            )
            
            if not result_obj.is_valid:
                raise ValueError(f"Spike detection function returned error: {result_obj.error_message}")
            
            spike_indices = result_obj.spike_indices
            
            if spike_indices is None:
                spike_indices = np.array([])
            
            num_spikes = len(spike_indices)
            log.info(f"Detected {num_spikes} spikes")
            
            # Store parameters in metadata
            result_obj.metadata['threshold'] = threshold
            result_obj.metadata['refractory_ms'] = params.get('refractory_ms')
            result_obj.metadata['units'] = units
            
            if num_spikes > 0:
                # Calculate spike features
                features_list = spike_analysis.calculate_spike_features(voltage, time, spike_indices)
                if features_list:
                    result_obj.metadata['spike_features'] = features_list
                    
                    # Calculate mean and SD for each feature
                    amplitudes = [f['amplitude'] for f in features_list if not np.isnan(f['amplitude'])]
                    half_widths = [f['half_width'] for f in features_list if not np.isnan(f['half_width'])]
                    ahp_depths = [f['ahp_depth'] for f in features_list if not np.isnan(f['ahp_depth'])]
                    
                    if amplitudes:
                        result_obj.metadata['amplitude_mean'] = np.mean(amplitudes)
                        result_obj.metadata['amplitude_std'] = np.std(amplitudes)
                    if half_widths:
                        result_obj.metadata['half_width_mean'] = np.mean(half_widths)
                        result_obj.metadata['half_width_std'] = np.std(half_widths)
                    if ahp_depths:
                        result_obj.metadata['ahp_depth_mean'] = np.mean(ahp_depths)
                        result_obj.metadata['ahp_depth_std'] = np.std(ahp_depths)
                
                # Calculate ISI
                spike_times = result_obj.spike_times
                if spike_times is not None:
                    isis = spike_analysis.calculate_isi(spike_times)
                    if isis.size > 0:
                        result_obj.metadata['isi_mean_ms'] = np.mean(isis) * 1000
                        result_obj.metadata['isi_std_ms'] = np.std(isis) * 1000
                
                # Get spike voltages for plotting
                result_obj.metadata['spike_voltages'] = voltage[spike_indices]
            
            return result_obj
            
        except Exception as e:
            log.error(f"Spike detection failed: {e}", exc_info=True)
            return None
    
    def _display_analysis_results(self, result: SpikeTrainResult):
        """Display spike detection results in text edit."""
        if not result or not result.is_valid:
            self.results_textedit.setText("Analysis failed.")
            self._last_spike_result = None
            return

        threshold = result.metadata.get('threshold')
        refractory_ms = result.metadata.get('refractory_ms')
        units = result.metadata.get('units', 'V')
        
        spike_times = result.spike_times
        num_spikes = len(spike_times) if spike_times is not None else 0
        
        results_str = f"--- Spike Detection Results ---\nThreshold: {threshold:.3f} {units}\nRefractory: {refractory_ms:.2f} ms\n\n"
        results_str += f"Number of Spikes: {num_spikes}\n"
        
        if num_spikes > 0:
            avg_rate = result.mean_frequency if result.mean_frequency else 0
            results_str += f"Average Firing Rate: {avg_rate:.2f} Hz\n"
            
            results_str += "\n--- Spike Features (Mean ± SD) ---\n"
            if 'amplitude_mean' in result.metadata:
                results_str += f"Amplitude: {result.metadata['amplitude_mean']:.2f} ± {result.metadata['amplitude_std']:.2f} {units}\n"
            if 'half_width_mean' in result.metadata:
                results_str += f"Half-width: {result.metadata['half_width_mean']:.3f} ± {result.metadata['half_width_std']:.3f} ms\n"
            if 'ahp_depth_mean' in result.metadata:
                results_str += f"AHP Depth: {result.metadata['ahp_depth_mean']:.2f} ± {result.metadata['ahp_depth_std']:.2f} {units}\n"
            if 'isi_mean_ms' in result.metadata:
                results_str += f"Mean ISI: {result.metadata['isi_mean_ms']:.2f} ± {result.metadata['isi_std_ms']:.2f} ms\n"
        
        self.results_textedit.setText(results_str)
        log.info(f"Spike detection results displayed: {num_spikes} spikes")
        
        # Store results for saving (convert to dict)
        self._last_spike_result = {
            'threshold': threshold,
            'threshold_units': units,
            'refractory_period_ms': refractory_ms,
            'spike_count': num_spikes,
            'average_firing_rate_hz': result.mean_frequency,
            'spike_times_s': result.spike_times.tolist() if result.spike_times is not None else [],
            'spike_features': result.metadata.get('spike_features', []),
            'analysis_type': 'Spike Detection',
            'source_file_name': self._selected_item_recording.source_file.name if self._selected_item_recording else "Unknown"
        }
    
    def _plot_analysis_visualizations(self, result: SpikeTrainResult):
        """Update plot with spike markers and threshold line."""
        # Clear previous markers
        if self.spike_markers_item:
            self.spike_markers_item.setData([])
        
        # Show threshold line
        if self.threshold_line:
            threshold = result.metadata.get('threshold') if result else None
            if threshold is not None:
                self.threshold_line.setValue(threshold)
                self.threshold_line.setVisible(True)
        
        if not result or not result.is_valid:
            return

        # Plot spike markers if spikes detected
        spike_times = result.spike_times
        spike_voltages = result.metadata.get('spike_voltages')
        
        if spike_times is not None and len(spike_times) > 0 and self.spike_markers_item:
            if spike_voltages is not None:
                self.spike_markers_item.setData(x=spike_times, y=spike_voltages)
                red_brush = pg.mkBrush(255, 0, 0, 150)
                self.spike_markers_item.setBrush(red_brush)
                self.spike_markers_item.setVisible(True)
                log.debug(f"Plotted {len(spike_times)} spike markers")
    # --- END PHASE 2 ---

# --- END CLASS SpikeAnalysisTab ---

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = SpikeAnalysisTab