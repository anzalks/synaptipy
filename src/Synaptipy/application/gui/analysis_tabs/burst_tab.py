# src/Synaptipy/application/gui/analysis_tabs/burst_tab.py
# -*- coding: utf-8 -*-
"""
Analysis tab for Burst Analysis.
Visualizes detected bursts on the raw trace.
"""
import logging
from typing import Any
import numpy as np
import pyqtgraph as pg

from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)


class BurstAnalysisTab(MetadataDrivenAnalysisTab):
    """
    Tab for Burst Analysis.
    Visualizes detected bursts using brackets/lines on the main plot.
    """

    def __init__(self, neo_adapter: NeoAdapter, settings_ref=None, parent=None):
        # Plot items
        self.burst_lines = []  # List of PlotCurveItems or similar for bursts
        self.spike_markers = None

        super().__init__(
            analysis_name="burst_analysis", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

    def get_display_name(self) -> str:
        return "Burst Analysis"

    def _setup_ui(self):
        super()._setup_ui()
        # Initialize spike markers
        if self.plot_widget:
            self.spike_markers = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush("r"))
            self.plot_widget.addItem(self.spike_markers)
            self.spike_markers.setVisible(False)

    def _ensure_custom_items_on_plot(self):
        """Re-add custom plot items if they were removed by plot_widget.clear()."""
        if not self.plot_widget:
            return
        if self.spike_markers and self.spike_markers not in self.plot_widget.items:
            self.plot_widget.addItem(self.spike_markers)

    def _on_channel_changed(self, index):
        """Re-add items to plot if cleared."""
        super()._on_channel_changed(index)
        self._ensure_custom_items_on_plot()

    def _on_data_plotted(self):
        """Re-add custom items after plot_widget.clear() in _plot_selected_data."""
        self._ensure_custom_items_on_plot()
        super()._on_data_plotted()

    def _clear_burst_visualizations(self):
        """Remove old burst lines."""
        if self.plot_widget:
            for item in self.burst_lines:
                if item in self.plot_widget.items:
                    self.plot_widget.removeItem(item)
            self.burst_lines.clear()

        if self.spike_markers:
            self.spike_markers.setData([])
            self.spike_markers.setVisible(False)

    def _plot_analysis_visualizations(self, results: Any):
        """
        Visualize Burst Analysis results.
        """
        self._ensure_custom_items_on_plot()
        self._clear_burst_visualizations()

        # Handle different result structures (Dict wrapper or Result Object)
        if isinstance(results, dict) and "result" in results:
            result_item = results["result"]
        else:
            result_item = results

        # Extract bursts list safely from Dict or Object
        bursts = []
        if hasattr(result_item, "bursts"):
            bursts = result_item.bursts
        elif isinstance(result_item, dict):
            bursts = result_item.get("bursts", [])

        if not bursts:
            return

        if bursts:
            # We want to draw a line above the burst.
            # Get Y-offset from current data max or fallback
            y_offset = 0
            if hasattr(self, "_current_plot_data") and self._current_plot_data:
                # Find max voltage to place markers above
                try:
                    y_offset = float(np.max(self._current_plot_data["data"])) + 10
                except Exception:
                    y_offset = 50
            else:
                y_offset = 50  # Fallback

            for burst_spikes in bursts:
                if len(burst_spikes) >= 2:
                    start_t = burst_spikes[0]
                    end_t = burst_spikes[-1]

                    # Draw a line
                    item = pg.PlotCurveItem([start_t, end_t], [y_offset, y_offset], pen=pg.mkPen("r", width=3))
                    self.plot_widget.addItem(item)
                    self.burst_lines.append(item)

        # Mark spikes within bursts explicitly

        all_burst_spikes = []
        if bursts:
            for b in bursts:
                all_burst_spikes.extend(b)

        if all_burst_spikes and hasattr(self, "_current_plot_data") and self._current_plot_data:
            # We need to find the voltage for these times.
            # This is inefficient without indices.
            # Let's just plot them at y_offset for now? Or try to map to voltage.
            # Mapping to voltage is better.
            time_vec = self._current_plot_data["time"]
            volt_vec = self._current_plot_data["data"]

            # Find indices (approximate)
            spike_indices = np.searchsorted(time_vec, all_burst_spikes)
            # Clip to bounds
            spike_indices = np.clip(spike_indices, 0, len(volt_vec) - 1)

            spike_volts = volt_vec[spike_indices]

            self.spike_markers.setData(all_burst_spikes, spike_volts)
            self.spike_markers.setVisible(True)
        else:
            self.spike_markers.setVisible(False)


# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = BurstAnalysisTab
