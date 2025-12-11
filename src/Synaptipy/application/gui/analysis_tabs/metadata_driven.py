# src/Synaptipy/application/gui/analysis_tabs/metadata_driven.py
# -*- coding: utf-8 -*-
"""
Generic Analysis Tab that generates its UI from metadata.

This module provides a generic implementation of BaseAnalysisTab that can
adapt to any registered analysis function by reading its metadata (ui_params)
from the AnalysisRegistry.
"""
import logging
from typing import Dict, Any, Optional, List
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets, QtCore

from Synaptipy.application.gui.analysis_tabs.base import BaseAnalysisTab
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)

class MetadataDrivenAnalysisTab(BaseAnalysisTab):
    """
    A generic analysis tab that builds its UI from metadata.
    """
    
    def __init__(self, analysis_name: str, neo_adapter, settings_ref=None, parent=None):
        """
        Initialize the metadata-driven tab.
        
        Args:
            analysis_name: The name of the registered analysis function.
            neo_adapter: NeoAdapter instance.
            settings_ref: QSettings reference.
            parent: Parent widget.
        """
        self.analysis_name = analysis_name
        self.metadata = AnalysisRegistry.get_metadata(analysis_name)
        self.param_widgets: Dict[str, QtWidgets.QWidget] = {}
        self._popup_windows = []
        
        super().__init__(neo_adapter, settings_ref, parent)
        self._setup_ui()

    def get_registry_name(self) -> str:
        return self.analysis_name

    def get_display_name(self) -> str:
        # Use label from metadata if available, else format the name
        return self.metadata.get('label', self.analysis_name.replace('_', ' ').title())

    def _setup_ui(self):
        """Setup the UI components dynamically based on metadata."""
        main_layout = QtWidgets.QHBoxLayout(self)
        
        # --- Create Splitter ---
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- Left Control Panel ---
        control_panel = QtWidgets.QWidget()
        control_layout = QtWidgets.QVBoxLayout(control_panel)
        control_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        
        # Global controls container (will be populated by AnalyserTab)
        self.global_controls_layout = QtWidgets.QVBoxLayout()
        control_layout.addLayout(self.global_controls_layout)
        
        # Channel Selection (Standard for all tabs)
        # Use BaseAnalysisTab's setup method for universal selection (Channel + Data Source)
        self._setup_data_selection_ui(control_layout)
        
        # self.signal_channel_combobox = QtWidgets.QComboBox()
        # self.signal_channel_combobox.currentIndexChanged.connect(self._on_channel_changed)
        # control_layout.addWidget(QtWidgets.QLabel("Signal Channel:"))
        # control_layout.addWidget(self.signal_channel_combobox)
        
        # Parameters Group
        params_group = QtWidgets.QGroupBox("Parameters")
        self.params_layout = QtWidgets.QFormLayout(params_group)
        
        # Use ParameterWidgetGenerator
        from Synaptipy.application.gui.ui_generator import ParameterWidgetGenerator
        self.param_generator = ParameterWidgetGenerator(self.params_layout)
        
        ui_params = self.metadata.get('ui_params', [])
        self.param_generator.generate_widgets(ui_params, self._on_param_changed)
            
        control_layout.addWidget(params_group)
        
        # Results Group
        results_group = QtWidgets.QGroupBox("Results")
        self.results_layout = QtWidgets.QFormLayout(results_group)
        self.results_labels: Dict[str, QtWidgets.QLabel] = {}
        
        # We don't know the result keys ahead of time, so we'll add them dynamically
        # or we could add a text area for generic output
        self.results_text = QtWidgets.QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(150)
        self.results_layout.addRow(self.results_text)
        
        control_layout.addWidget(results_group)
        
        # Status Label
        self.status_label = QtWidgets.QLabel("Ready")
        control_layout.addWidget(self.status_label)
        
        # Save Button
        self._setup_save_button(control_layout)
        
        # Accumulation UI
        self._setup_accumulation_ui(control_layout)
        
        control_layout.addStretch()
        
        # Add control panel to splitter
        splitter.addWidget(control_panel)

        # --- Right Plot Area ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        self._setup_plot_area(plot_layout, stretch_factor=0) # Stretch handled by splitter
        splitter.addWidget(plot_container)
        
        # Set Splitter Sizes (1/3 Left, 2/3 Right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        
        # Basic plot setup
        if self.plot_widget:
            self.plot_widget.showGrid(x=True, y=True)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Return the last analysis result for saving."""
        # For metadata-driven tabs, the result is usually a dictionary or object
        # If it's an object, we might need to convert it to a dict
        log.info(f"{self.__class__.__name__}._get_specific_result_data: _last_analysis_result is None? {self._last_analysis_result is None}")
        if not self._last_analysis_result:
            log.warning(f"{self.__class__.__name__}._get_specific_result_data: returning None because _last_analysis_result is falsy")
            return None
        
        # Start with the result data
        if hasattr(self._last_analysis_result, '__dict__'):
            result = dict(self._last_analysis_result.__dict__)
        elif isinstance(self._last_analysis_result, dict):
            result = dict(self._last_analysis_result)  # Copy to avoid modifying original
        else:
            # Fallback for simple types
            result = {'result': self._last_analysis_result}
        
        # CRITICAL: Add data_source key which is required by _request_save_result
        if self.data_source_combobox and self.data_source_combobox.isEnabled():
            data_source = self.data_source_combobox.currentData()
            result['data_source'] = data_source
        
        return result


    def _update_ui_for_selected_item(self):
        """Update UI when a new item is selected."""
        # Base class handles population of channel/source combos now
        # We just need to ensure plot is cleared if nothing selected
        if not self._selected_item_recording:
            if self.plot_widget:
                self.plot_widget.clear()

    def _on_channel_changed(self, index):
        """Handle channel selection change."""
        # Now handled by BaseAnalysisTab._plot_selected_data via signal connection
        # But we might need to trigger analysis?
        # BaseAnalysisTab._plot_selected_data calls _on_data_plotted hook.
        # We can trigger analysis there.
        pass
        
    def _on_data_plotted(self):
        """Hook called after data is plotted."""
        # Trigger analysis when new data is plotted
        self._trigger_analysis()

    def _on_param_changed(self):
        """Handle parameter changes."""
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """Gather parameters from UI widgets."""
        return self.param_generator.gather_params()

    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the registered analysis function."""
        func = AnalysisRegistry.get_function(self.analysis_name)
        if not func:
            raise ValueError(f"Analysis function '{self.analysis_name}' not found.")
            
        # Prepare arguments
        # Most analysis functions expect (data, time, sampling_rate, **kwargs)
        # or similar. We need to be flexible or enforce a standard signature.
        # Synaptipy standard seems to be: func(data, time, sampling_rate, **params)
        
        voltage = data['data']
        time = data['time']
        fs = data['sampling_rate']
        
        try:
            # Call the function
            results = func(voltage, time, fs, **params)
            
            # If results is a list (like spikes), wrap it?
            # Or if it's a dict, pass it through.
            if isinstance(results, list):
                return {'list_results': results}
            elif isinstance(results, dict):
                return results
            else:
                return {'result': results}
                
        except Exception as e:
            log.error(f"Analysis execution failed: {e}")
            raise

    def _on_analysis_result(self, results: Dict[str, Any]):
        """Update UI with results."""
        log.info(f"{self.__class__.__name__}._on_analysis_result called with results type: {type(results)}")
        
        if not self.plot_widget:
            log.warning(f"{self.__class__.__name__}._on_analysis_result: plot_widget is None, returning early")
            return
        
        # Store results for save functionality
        self._last_analysis_result = results
        log.info(f"{self.__class__.__name__}: Stored _last_analysis_result, is None? {self._last_analysis_result is None}")
            
        # Do NOT clear the plot here, as it removes the raw trace!
        # The raw trace is plotted in _plot_selected_data.
        # self.plot_widget.clear() 
        
        # Display text results
        text_output = []
        for k, v in results.items():
            if isinstance(v, (float, int)):
                text_output.append(f"{k}: {v:.4g}")
            elif isinstance(v, list):
                text_output.append(f"{k}: {len(v)} items")
            else:
                text_output.append(f"{k}: {str(v)}")
        
        self.results_text.setText("\n".join(text_output))
        self.status_label.setText("Status: Analysis Complete")
        
        # Enable save button
        self._set_save_button_enabled(True)
        
        # Call the visualization hook for subclasses (CRITICAL FIX)
        self._plot_analysis_visualizations(results)
        
        # Update Accumulation UI state
        self._update_accumulation_ui_state()
