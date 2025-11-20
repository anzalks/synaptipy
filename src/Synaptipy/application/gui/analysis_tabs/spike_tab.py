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
from Synaptipy.shared.styling import style_button  # Import styling functions

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.spike_tab')

class SpikeAnalysisTab(BaseAnalysisTab):
    """QWidget for Threshold-based Spike Detection."""

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__(neo_adapter=neo_adapter, parent=parent)

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

        # Analysis Item Selector (inherited)
        item_selector_layout = QtWidgets.QFormLayout()
        self._setup_analysis_item_selector(item_selector_layout)
        controls_layout.addLayout(item_selector_layout)

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
        
        # 1. Check if analysis was run and results exist
        if not self._current_plot_data or 'spike_times' not in self._current_plot_data:
            log.debug("_get_specific_result_data (Spike): No spike analysis results available.")
            return None
            
        spike_times = self._current_plot_data.get('spike_times')
        spike_indices = self._current_plot_data.get('spike_indices')
        voltage = self._current_plot_data.get('voltage') # Needed for peak values
        features = self._current_plot_data.get('spike_features')
        
        # Check if spike_times is valid (e.g., a non-empty numpy array)
        if spike_times is None or not isinstance(spike_times, np.ndarray):
             log.debug(f"_get_specific_result_data (Spike): spike_times is invalid or empty ({type(spike_times)}).")
             # Allow saving even if 0 spikes were detected, just need parameters
             # return None 
             pass # Continue to save parameters even if no spikes

        # 2. Get parameters used for the analysis
        try:
            threshold = float(self.threshold_edit.text())
            refractory_ms = float(self.refractory_edit.text())
        except (ValueError, TypeError):
            log.error("_get_specific_result_data (Spike): Could not read parameters from UI for saving.")
            return None # Cannot save without valid parameters

        # 3. Get data source information
        channel_id = self.signal_channel_combobox.currentData()
        channel_name = self.signal_channel_combobox.currentText().split(' (')[0] # Extract name before ID
        data_source = self.data_source_combobox.currentData() # "average" or trial index (int)
        data_source_text = self.data_source_combobox.currentText()

        if channel_id is None or data_source is None:
            log.warning("Cannot get specific Spike data: Missing channel or data source selection.")
            return None
            
        # 4. Gather results
        num_spikes = len(spike_times) if spike_times is not None else 0
        avg_rate = 0.0
        spike_peak_values = []
        if num_spikes > 0 and voltage is not None and spike_indices is not None:
             time_full = self._current_plot_data.get('time')
             if time_full is not None and time_full.size > 1:
                 duration = time_full[-1] - time_full[0]
                 avg_rate = num_spikes / duration if duration > 0 else 0
             # Get peak voltage values using the indices
             try:
                 spike_peak_values = voltage[spike_indices].tolist()
             except IndexError:
                  log.warning("Spike indices out of bounds for voltage array when getting peaks.")
                  spike_peak_values = [] # Set empty if indices are bad
        
        specific_data = {
            # Analysis Parameters
            'threshold': threshold,
            'threshold_units': self._current_plot_data.get('units', 'unknown'),
            'refractory_period_ms': refractory_ms,
            # Results
            'spike_count': num_spikes,
            'average_firing_rate_hz': avg_rate,
            'spike_times_s': spike_times.tolist() if spike_times is not None else [],
            'spike_peak_values': spike_peak_values, # Add peak values
            'spike_features': features,
            # Data Source Info (for base class)
            'channel_id': channel_id,
            'channel_name': channel_name,
            'data_source': data_source, 
            'data_source_label': data_source_text # Add readable label
            # Note: Base class adds file path etc.
        }
        log.debug(f"_get_specific_result_data (Spike) returning: {specific_data}")
        return specific_data

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
    
    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                log.warning(f"Sampling rate missing, calculated from time vector: {rate:.2f} Hz")
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
            # spike_times_from_func = result_obj.spike_times # Not strictly needed as we recalc from indices later but good to have
            
            if spike_indices is None:
                spike_indices = np.array([])
            
            num_spikes = len(spike_indices)
            log.info(f"Detected {num_spikes} spikes")
            
            # Calculate results
            results = {
                'num_spikes': num_spikes,
                'spike_indices': spike_indices,
                'threshold': threshold,
                'refractory_ms': params.get('refractory_ms'),
                'units': units,
                'result_object': result_obj # Store the full object if needed
            }
            
            if num_spikes > 0:
                spike_times = time[spike_indices]
                duration = time[-1] - time[0]
                avg_rate = num_spikes / duration if duration > 0 else 0
                
                results['spike_times'] = spike_times
                results['avg_rate'] = avg_rate
                results['duration'] = duration
                
                # Calculate spike features
                features_list = spike_analysis.calculate_spike_features(voltage, time, spike_indices)
                if features_list:
                    results['spike_features'] = features_list
                    
                    # Calculate mean and SD for each feature
                    amplitudes = [f['amplitude'] for f in features_list if not np.isnan(f['amplitude'])]
                    half_widths = [f['half_width'] for f in features_list if not np.isnan(f['half_width'])]
                    ahp_depths = [f['ahp_depth'] for f in features_list if not np.isnan(f['ahp_depth'])]
                    
                    if amplitudes:
                        results['amplitude_mean'] = np.mean(amplitudes)
                        results['amplitude_std'] = np.std(amplitudes)
                    if half_widths:
                        results['half_width_mean'] = np.mean(half_widths)
                        results['half_width_std'] = np.std(half_widths)
                    if ahp_depths:
                        results['ahp_depth_mean'] = np.mean(ahp_depths)
                        results['ahp_depth_std'] = np.std(ahp_depths)
                
                # Calculate ISI
                isis = spike_analysis.calculate_isi(spike_times)
                if isis.size > 0:
                    results['isi_mean_ms'] = np.mean(isis) * 1000
                    results['isi_std_ms'] = np.std(isis) * 1000
                
                # Get spike voltages for plotting
                results['spike_voltages'] = voltage[spike_indices]
            
            return results
            
        except Exception as e:
            log.error(f"Spike detection failed: {e}", exc_info=True)
            return None
    
    def _display_analysis_results(self, results: Dict[str, Any]):
        """Display spike detection results in text edit."""
        threshold = results.get('threshold')
        refractory_ms = results.get('refractory_ms')
        units = results.get('units', 'V')
        num_spikes = results.get('num_spikes', 0)
        
        results_str = f"--- Spike Detection Results ---\nThreshold: {threshold:.3f} {units}\nRefractory: {refractory_ms:.2f} ms\n\n"
        results_str += f"Number of Spikes: {num_spikes}\n"
        
        if num_spikes > 0:
            avg_rate = results.get('avg_rate', 0)
            results_str += f"Average Firing Rate: {avg_rate:.2f} Hz\n"
            
            results_str += "\n--- Spike Features (Mean ± SD) ---\n"
            if 'amplitude_mean' in results:
                results_str += f"Amplitude: {results['amplitude_mean']:.2f} ± {results['amplitude_std']:.2f} {units}\n"
            if 'half_width_mean' in results:
                results_str += f"Half-width: {results['half_width_mean']:.3f} ± {results['half_width_std']:.3f} ms\n"
            if 'ahp_depth_mean' in results:
                results_str += f"AHP Depth: {results['ahp_depth_mean']:.2f} ± {results['ahp_depth_std']:.2f} {units}\n"
            if 'isi_mean_ms' in results:
                results_str += f"Mean ISI: {results['isi_mean_ms']:.2f} ± {results['isi_std_ms']:.2f} ms\n"
        
        self.results_textedit.setText(results_str)
        log.info(f"Spike detection results displayed: {num_spikes} spikes")
        
        # Store results in current_plot_data for saving
        if self._current_plot_data:
            self._current_plot_data['spike_indices'] = results.get('spike_indices', np.array([]))
            self._current_plot_data['spike_times'] = results.get('spike_times', np.array([]))
            self._current_plot_data['spike_features'] = results.get('spike_features', [])
    
    def _plot_analysis_visualizations(self, results: Dict[str, Any]):
        """Update plot with spike markers and threshold line."""
        # Clear previous markers
        if self.spike_markers_item:
            self.spike_markers_item.setData([])
        
        # Show threshold line
        if self.threshold_line:
            threshold = results.get('threshold')
            if threshold is not None:
                self.threshold_line.setValue(threshold)
                self.threshold_line.setVisible(True)
        
        # Plot spike markers if spikes detected
        num_spikes = results.get('num_spikes', 0)
        if num_spikes > 0 and self.spike_markers_item:
            spike_times = results.get('spike_times')
            spike_voltages = results.get('spike_voltages')
            
            if spike_times is not None and spike_voltages is not None:
                self.spike_markers_item.setData(x=spike_times, y=spike_voltages)
                red_brush = pg.mkBrush(255, 0, 0, 150)
                self.spike_markers_item.setBrush(red_brush)
                self.spike_markers_item.setVisible(True)
                log.debug(f"Plotted {num_spikes} spike markers")
    # --- END PHASE 2 ---

# --- END CLASS SpikeAnalysisTab ---

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = SpikeAnalysisTab