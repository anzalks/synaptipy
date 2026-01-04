# src/Synaptipy/application/gui/analysis_tabs/rmp_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for calculating Baseline signal properties (Mean/SD).
Refactored to use MetadataDrivenAnalysisTab architecture fully.
"""
import logging
from typing import Optional, Dict, Any
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry
import Synaptipy.core.analysis.basic_features # Ensure registration

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rmp_tab')

class BaselineAnalysisTab(MetadataDrivenAnalysisTab):
    """
    QWidget for Baseline analysis with interactive plotting.
    Inherits from MetadataDrivenAnalysisTab for standardized behavior.
    """

    # Define constants for analysis modes - these map to the 'mode' parameter in UI metadata if present,
    # or we handle them locally.
    _MODE_INTERACTIVE = "Interactive"
    _MODE_MANUAL = "Manual"
    _MODE_AUTOMATIC = "Automatic"

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        # Plotting items - Initialize BEFORE super().__init__ incase setup_ui uses them
        self.interactive_region: Optional[pg.LinearRegionItem] = None
        self.baseline_mean_line: Optional[pg.InfiniteLine] = None
        self.baseline_plus_sd_line: Optional[pg.InfiniteLine] = None
        self.baseline_minus_sd_line: Optional[pg.InfiniteLine] = None

        # We need to init MetadataDriven with the registry name
        super().__init__(analysis_name="rmp_analysis", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent)
        
        # Initialize custom controls
        self._on_mode_changed()

    def get_display_name(self) -> str:
        return "Baseline Analysis"

    def _setup_additional_controls(self, layout: QtWidgets.QVBoxLayout):
        """Add custom mode selection if not covered by metadata."""
        # Check if 'mode' is in metadata params. If not, add custom combo.
        # RMP metadata usually has time ranges, but maybe not 'mode'.
        # Let's check? AnalysisRegistry.get_metadata("rmp_analysis")
        # Assuming we add a custom mode switcher on top of the auto-generated params.
        
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel("Mode:"))
        self.mode_combobox = QtWidgets.QComboBox()
        self.mode_combobox.addItems([self._MODE_INTERACTIVE, self._MODE_MANUAL, self._MODE_AUTOMATIC])
        self.mode_combobox.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combobox)
        layout.addLayout(mode_layout)

    def _setup_custom_plot_items(self):
        """Initialize plot items."""
        if not self.plot_widget:
            return
            
        self.interactive_region = pg.LinearRegionItem(values=[0, 0.1], bounds=[0, 1], movable=True)
        self.interactive_region.setBrush(pg.mkBrush(0, 255, 0, 30))
        self.plot_widget.addItem(self.interactive_region)
        self.interactive_region.sigRegionChanged.connect(self._on_region_changed)
        
        self.baseline_mean_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', width=2))
        self.baseline_plus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
        self.baseline_minus_sd_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine))
        
        self.plot_widget.addItem(self.baseline_mean_line)
        self.plot_widget.addItem(self.baseline_plus_sd_line)
        self.plot_widget.addItem(self.baseline_minus_sd_line)
        
        # Hide initially
        self.baseline_mean_line.setVisible(False)
        self.baseline_plus_sd_line.setVisible(False)
        self.baseline_minus_sd_line.setVisible(False)

    def _on_mode_changed(self):
        if not hasattr(self, 'mode_combobox'): return
        
        mode = self.mode_combobox.currentText()
        is_interactive = (mode == self._MODE_INTERACTIVE)
        is_automatic = (mode == self._MODE_AUTOMATIC)
        
        if self.interactive_region:
            self.interactive_region.setVisible(is_interactive)
            
        # Update generator widgets state if they exist
        if hasattr(self, 'param_generator'):
            # auto_detect checkbox
            auto_detect_widget = self.param_generator.widgets.get('auto_detect')
            if auto_detect_widget:
                if is_automatic:
                    auto_detect_widget.setChecked(True)
                    auto_detect_widget.setEnabled(False)
                else:
                    auto_detect_widget.setChecked(False)
                    auto_detect_widget.setEnabled(False) 
            
            # Time widgets
            for name in ['baseline_start', 'baseline_end']:
                widget = self.param_generator.widgets.get(name)
                if widget:
                    widget.setEnabled(mode == self._MODE_MANUAL)
                    
            # Window duration
            win_dur_widget = self.param_generator.widgets.get('window_duration')
            if win_dur_widget:
                win_dur_widget.setEnabled(is_automatic)

    def _on_region_changed(self):
        if not hasattr(self, 'mode_combobox') or self.mode_combobox.currentText() != self._MODE_INTERACTIVE:
            return
            
        if self.interactive_region and hasattr(self, 'param_generator'):
            min_x, max_x = self.interactive_region.getRegion()
            self.param_generator.set_params({'baseline_start': min_x, 'baseline_end': max_x})
            self._on_param_changed()

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """Override to inject auto_detect param based on mode."""
        if hasattr(self, 'param_generator'):
            params = self.param_generator.gather_params()
        else:
            params = {}
            
        if hasattr(self, 'mode_combobox'):
            mode = self.mode_combobox.currentText()
            params['auto_detect'] = (mode == self._MODE_AUTOMATIC)
            
        return params

    def _on_channel_changed(self, channel_index: int):
        """Handle channel switch to update interactive region."""
        super()._on_channel_changed(channel_index)
        
        # Auto-scale region if it's currently at default [0, 0.1] or out of bounds
        if self.interactive_region and self._current_plot_data:
            time_vec = self._current_plot_data['time']
            if len(time_vec) > 1:
                t_start = time_vec[0]
                t_end = time_vec[-1]
                duration = t_end - t_start
                
                # Check if current region is "default-like" or invalid
                curr_min, curr_max = self.interactive_region.getRegion()
                if (curr_min == 0 and curr_max == 0.1) or (curr_max > t_end) or (curr_min < t_start):
                     # Reset to 10% or 200ms, whichever is smaller/sane
                     default_width = min(duration * 0.2, 0.5) # Max 500ms default
                     self.interactive_region.setRegion([t_start, t_start + default_width])
                
                # Update bounds
                self.interactive_region.setBounds([t_start, t_end])
                
                # Check if items are attached to the plot (BaseAnalysisTab might clear plot)
                if self.plot_widget:
                    if self.interactive_region not in self.plot_widget.items():
                         self.plot_widget.addItem(self.interactive_region)
                    
                    for line in [self.baseline_mean_line, self.baseline_plus_sd_line, self.baseline_minus_sd_line]:
                        if line and line not in self.plot_widget.items():
                            self.plot_widget.addItem(line)
                
                # Ensure visibility if in interactive mode
                self._on_mode_changed()

    def _plot_analysis_visualizations(self, results: Any):
        """Visualize RMP results."""
        if isinstance(results, dict) and 'result' in results:
             result_data = results['result']
        else:
             result_data = results
             
        if not isinstance(result_data, dict):
            return

        if 'rmp_mv' in result_data and result_data['rmp_mv'] is not None:
            mean = result_data['rmp_mv']
            sd = result_data.get('rmp_std', 0)
            
            if self.baseline_mean_line:
                self.baseline_mean_line.setValue(mean)
                self.baseline_mean_line.setVisible(True)
            if self.baseline_plus_sd_line:
                self.baseline_plus_sd_line.setValue(mean + sd)
                self.baseline_plus_sd_line.setVisible(True)
            if self.baseline_minus_sd_line:
                self.baseline_minus_sd_line.setValue(mean - sd)
                self.baseline_minus_sd_line.setVisible(True)
        else:
            if self.baseline_mean_line: self.baseline_mean_line.setVisible(False)
            if self.baseline_plus_sd_line: self.baseline_plus_sd_line.setVisible(False)
            if self.baseline_minus_sd_line: self.baseline_minus_sd_line.setVisible(False)

    def _on_analysis_result(self, results: Any):
        """Override to customize result display text."""
        super()._on_analysis_result(results)
        
        if isinstance(results, dict) and 'result' in results:
             result_data = results['result']
        else:
             result_data = results

        if not result_data or 'rmp_error' in result_data:
            text = f"Error: {result_data.get('rmp_error', 'Unknown')}"
        else:
            mean = result_data.get('rmp_mv')
            sd = result_data.get('rmp_std')
            drift = result_data.get('rmp_drift')
            text = f"<h3>Baseline Analysis</h3>"
            text += f"<b>Mean:</b> {mean:.2f} mV<br>"
            text += f"<b>SD:</b> {sd:.3f} mV<br>"
            if drift is not None:
                text += f"<b>Drift:</b> {drift:.4f} mV/s"

        if hasattr(self, 'results_text'):
            self.results_text.setHtml(text)

# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = BaselineAnalysisTab