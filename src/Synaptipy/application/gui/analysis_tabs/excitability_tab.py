# src/Synaptipy/application/gui/analysis_tabs/excitability_tab.py
# -*- coding: utf-8 -*-
"""
Analysis tab for Excitability (F-I Curve) Analysis.
Visualizes F-I Curve in a popup window.
"""
import logging
from typing import Dict, Any, Optional
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets, QtCore

from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
import Synaptipy.core.analysis.excitability # Ensure registration

log = logging.getLogger(__name__)

class ExcitabilityTab(MetadataDrivenAnalysisTab):
    """
    Tab for Excitability Analysis.
    Visualizes F-I Curve (Frequency vs Current) in a popup window.
    """
    
    def __init__(self, neo_adapter: NeoAdapter, settings_ref=None, parent=None):
        # Popup plot items
        self.popup_plot = None
        self.fi_curve = None
        self.slope_line = None
        self.rheobase_marker = None
        
        super().__init__(analysis_name="excitability_analysis", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent)

    def get_display_name(self) -> str:
        return "Excitability Analysis"

    def cleanup(self):
        super().cleanup()
        if self.popup_plot:
            try:
                self.popup_plot.window().close()
            except:
                pass

    def _plot_analysis_visualizations(self, results: Any):
        """
        Visualize Excitability results (F-I Curve).
        """
        if isinstance(results, dict) and 'result' in results:
             result_data = results['result']
        else:
             result_data = results
             
        if not isinstance(result_data, dict):
            return

        # Extract data
        # The wrapper returns scalar stats but currently NOT the full arrays (frequencies, current_steps) needed for plotting!
        # I need to check `excitability.py` wrapper again.
        # It returns: 'rheobase_pa', 'fi_slope', 'fi_r_squared', 'max_freq_hz'.
        # It DOES NOT return 'frequencies' or 'current_steps' lists in the wrapper output.
        
        # Similar to Burst Analysis, I need to modify the wrapper to return the full arrays.
        # I will implement the plotting logic assuming they exist, then fix the wrapper.
        
        currents = result_data.get('current_steps')
        freqs = result_data.get('frequencies')
        
        # Create popup if needed
        if self.popup_plot is None:
            self.popup_plot = self.create_popup_plot("F-I Curve", "Current (pA)", "Frequency (Hz)")
            self.fi_curve = self.popup_plot.plot(pen='b', symbol='o', name="F-I Curve")
            self.slope_line = self.popup_plot.plot(pen=pg.mkPen('r', style=QtCore.Qt.PenStyle.DashLine), name="Slope Fit")
            self.rheobase_marker = self.popup_plot.plot(pen=None, symbol='t', symbolBrush='g', symbolSize=12, name="Rheobase")

        # Plot Data
        if currents is not None and freqs is not None:
            self.fi_curve.setData(currents, freqs)
            
            # Plot Slope Line
            slope = result_data.get('fi_slope')
            rheobase = result_data.get('rheobase_pa')
            
            if slope is not None and rheobase is not None and slope > 0:
                # Plot line from rheobase to max current
                max_curr = max(currents)
                x_line = [rheobase, max_curr]
                # y = m(x - x0) + y0? No, simple regression y = mx + c.
                # But we don't have intercept from wrapper.
                # We can estimate it or just plot a line starting from rheobase (approx 0 Hz or first spike freq).
                # Ideally wrapper should return intercept too.
                # For now, let's just mark Rheobase.
                self.rheobase_marker.setData([rheobase], [0]) # Plot at 0 Hz for visibility
            else:
                self.rheobase_marker.setData([], [])
                self.slope_line.setData([], [])

# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = ExcitabilityTab
