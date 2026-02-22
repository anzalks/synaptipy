# src/Synaptipy/application/gui/analysis_tabs/iv_curve_tab.py
# -*- coding: utf-8 -*-
"""
Analysis tab for I-V Curve Analysis.
Visualizes the Current-Voltage relationship in a popup window.
"""
import logging
import numpy as np
from typing import Any
import pyqtgraph as pg
from PySide6 import QtCore

from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)


class IVCurveTab(MetadataDrivenAnalysisTab):
    """
    Tab for I-V Curve Analysis.
    Visualizes Voltage response vs Injected Current in a popup window.
    """

    def __init__(self, neo_adapter: NeoAdapter, settings_ref=None, parent=None):
        # Popup plot items
        self.popup_plot = None
        self.iv_data_points = None
        self.slope_line = None

        super().__init__(
            analysis_name="iv_curve_analysis", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

    def get_display_name(self) -> str:
        return "I-V Curve"

    def _plot_analysis_visualizations(self, results: Any):
        """
        Visualize I-V Curve results.
        """
        if isinstance(results, dict) and "result" in results:
            result_data = results["result"]
        else:
            result_data = results

        if not isinstance(result_data, dict):
            return

        # Extract data
        currents = result_data.get("current_steps")
        delta_vs = result_data.get("delta_vs")

        if currents is None or delta_vs is None:
            return

        # Filter out NaNs for plotting
        valid_indices = [i for i, dv in enumerate(delta_vs) if not np.isnan(dv)]
        plot_currents = [currents[i] for i in valid_indices]
        plot_delta_vs = [delta_vs[i] for i in valid_indices]

        # Create popup if needed
        if self.popup_plot is None:
            self.popup_plot = self.create_popup_plot("I-V Curve", "Current (pA)", "Voltage Response (mV)")
            self.iv_data_points = self.popup_plot.plot(pen=None, symbol="o", symbolBrush="b", name="V steady-state")
            self.slope_line = self.popup_plot.plot(
                pen=pg.mkPen("r", width=2, style=QtCore.Qt.PenStyle.DashLine), name="Rin Fit"
            )

        if not plot_currents:
            return

        # Plot Data Points
        self.iv_data_points.setData(plot_currents, plot_delta_vs)

        # Plot Regression Line
        rin_mohm = result_data.get("rin_aggregate_mohm")
        intercept = result_data.get("iv_intercept")

        if rin_mohm is not None and intercept is not None:
            # Generate end points for the line
            min_cur = min(plot_currents)
            max_cur = max(plot_currents)

            # Fit line: y = mx + c where x is in nA for Rin.
            # currents is in pA, so x_na = x_pa / 1000.
            y_min = rin_mohm * (min_cur / 1000.0) + intercept
            y_max = rin_mohm * (max_cur / 1000.0) + intercept

            self.slope_line.setData([min_cur, max_cur], [y_min, y_max])
        else:
            self.slope_line.setData([], [])


# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = IVCurveTab
