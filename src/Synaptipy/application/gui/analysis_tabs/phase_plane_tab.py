# src/Synaptipy/application/gui/analysis_tabs/phase_plane_tab.py
# -*- coding: utf-8 -*-
"""
Analysis tab for Phase Plane (dV/dt vs V) visualization and analysis.
Refactored to use MetadataDrivenAnalysisTab architecture.
"""
import logging
from typing import Dict, Any
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)


class PhasePlaneTab(MetadataDrivenAnalysisTab):
    """
    Tab for Phase Plane Analysis.
    Visualizes dV/dt vs Voltage and detects threshold using phase plane kink.
    Inherits from MetadataDrivenAnalysisTab.
    """

    def __init__(self, neo_adapter: NeoAdapter, settings_ref=None, parent=None):
        super().__init__(
            analysis_name="phase_plane_analysis", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

        # Popup plot items
        self.popup_plot = None
        self.phase_curve = None
        self.threshold_marker = None
        self.max_dvdt_marker = None

        # Main plot items
        self.threshold_line = None

    def get_display_name(self) -> str:
        return "Phase Plane"

    def _setup_ui(self):
        super()._setup_ui()
        # Initialize main plot items
        if self.plot_widget:
            self.threshold_line = pg.InfiniteLine(
                angle=0, movable=False, pen=pg.mkPen("r", style=QtCore.Qt.PenStyle.DashLine)
            )
            self.plot_widget.addItem(self.threshold_line)
            self.threshold_line.setVisible(False)

    def _ensure_custom_items_on_plot(self):
        """Re-add custom plot items if they were removed by plot_widget.clear()."""
        if not self.plot_widget:
            return
        if self.threshold_line and self.threshold_line not in self.plot_widget.items:
            self.plot_widget.addItem(self.threshold_line)

    def _on_data_plotted(self):
        """Re-add custom items after plot_widget.clear() in _plot_selected_data."""
        self._ensure_custom_items_on_plot()
        super()._on_data_plotted()

    def _plot_analysis_visualizations(self, results: Any):  # noqa: C901
        """
        Visualize Phase Plane results.
        Called by BaseAnalysisTab._on_analysis_result.
        """
        self._ensure_custom_items_on_plot()

        if isinstance(results, dict) and "result" in results:
            result_data = results["result"]
        else:
            result_data = results

        if not isinstance(result_data, dict):
            return

        # --- 1. Update Main Plot (Threshold Line) ---
        threshold_v = result_data.get("threshold_v")
        if threshold_v is not None and self.threshold_line:
            self.threshold_line.setValue(threshold_v)
            self.threshold_line.setVisible(True)
        elif self.threshold_line:
            self.threshold_line.setVisible(False)

        # --- 2. Create/Update Popup Plot (Phase Plane) ---
        # --- 2. Create/Update Popup Plot (Phase Plane) ---
        if self.popup_plot is None or self.phase_curve is None:
            # If popup exists but curve is missing, we might need to clear/reset
            if self.popup_plot is not None:
                try:
                    self.popup_plot.close()
                except Exception:
                    pass
                self.popup_plot = None

            self.popup_plot = self.create_popup_plot("Phase Plane Plot", "Voltage (mV)", "dV/dt (V/s)")
            if self.popup_plot:
                self.phase_curve = self.popup_plot.plot(pen="b", name="Phase Loop")
                self.threshold_marker = self.popup_plot.plot(
                    pen=None, symbol="o", symbolBrush="r", symbolSize=10, name="Threshold"
                )
                self.max_dvdt_marker = self.popup_plot.plot(
                    pen=None, symbol="x", symbolBrush="g", symbolSize=10, name="Max dV/dt"
                )
            else:
                log.error("Failed to create popup plot for Phase Plane Analysis")
                return

        voltage = result_data.get("voltage")
        dvdt = result_data.get("dvdt")

        if voltage is not None and dvdt is not None:
            if self.phase_curve:  # Safety check
                if len(voltage) == len(dvdt):
                    self.phase_curve.setData(voltage, dvdt)
                else:
                    min_len = min(len(voltage), len(dvdt))
                    self.phase_curve.setData(voltage[:min_len], dvdt[:min_len])

        # Plot markers in popup
        threshold_dvdt = result_data.get("threshold_dvdt")
        if threshold_v is not None and threshold_dvdt is not None and self.threshold_marker:
            self.threshold_marker.setData([threshold_v], [threshold_dvdt])
        elif self.threshold_marker:
            self.threshold_marker.setData([], [])

        max_dvdt = result_data.get("max_dvdt")
        if max_dvdt is not None and voltage is not None and dvdt is not None and self.max_dvdt_marker:
            idx = np.argmax(dvdt)
            if idx < len(voltage):
                self.max_dvdt_marker.setData([voltage[idx]], [dvdt[idx]])
        elif self.max_dvdt_marker:
            self.max_dvdt_marker.setData([], [])

    def _display_analysis_results(self, result: Dict[str, Any]):
        """Display results in table."""
        if not self.results_table:
            return

        if isinstance(result, dict) and "result" in result:
            result_data = result["result"]
        else:
            result_data = result

        if not result_data:
            self.results_table.setRowCount(1)
            self.results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Status"))
            self.results_table.setItem(0, 1, QtWidgets.QTableWidgetItem("Analysis Failed"))
            return

        threshold_v = result_data.get("threshold_v")
        max_dvdt = result_data.get("max_dvdt")

        display_items = []
        if threshold_v is not None:
            display_items.append(("Threshold", f"{threshold_v:.2f} mV"))
        if max_dvdt is not None:
            display_items.append(("Max dV/dt", f"{max_dvdt:.2f} V/s"))

        self.results_table.setRowCount(len(display_items))
        for row, (k, v) in enumerate(display_items):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(k))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(v))


# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = PhasePlaneTab
