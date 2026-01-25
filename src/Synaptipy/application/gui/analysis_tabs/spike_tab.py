# src/Synaptipy/application/gui/analysis_tabs/spike_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting spikes using a simple threshold.
Refactored to use MetadataDrivenAnalysisTab architecture.
"""
import logging
from typing import Optional, Dict, Any
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

# Import base class
from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.results import SpikeTrainResult
import Synaptipy.core.analysis.spike_analysis  # Ensure registration

log = logging.getLogger(__name__)


class SpikeAnalysisTab(MetadataDrivenAnalysisTab):
    """
    QWidget for Threshold-based Spike Detection.
    Inherits from MetadataDrivenAnalysisTab to use metadata-defined parameters.
    """

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        # Initialize with the specific analysis name "spike_detection"
        super().__init__(
            analysis_name="spike_detection", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

        # Spike-specific plot items
        self.spike_markers_item: Optional[pg.ScatterPlotItem] = None
        self.threshold_line: Optional[pg.InfiniteLine] = None
        self._last_spike_result: Optional[Dict[str, Any]] = None

        # Initialize plot items
        if self.plot_widget:
            self.spike_markers_item = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 150))
            self.threshold_line = pg.InfiniteLine(
                angle=0, movable=False, pen=pg.mkPen("r", style=QtCore.Qt.PenStyle.DashLine)
            )
            self.plot_widget.addItem(self.spike_markers_item)
            self.plot_widget.addItem(self.threshold_line)
            self.spike_markers_item.setVisible(False)
            self.threshold_line.setVisible(False)

    def get_display_name(self) -> str:
        return "Spike Detection (Threshold)"

    # _setup_ui is inherited from MetadataDrivenAnalysisTab
    # _gather_analysis_parameters is inherited
    # _execute_core_analysis is inherited (uses registry function)

    def _on_data_plotted(self):
        """
        Hook called by BaseAnalysisTab after plotting main data trace.
        Adds Spike-specific plot items: spike markers and threshold line.
        """
        log.debug(f"{self.get_display_name()}: _on_data_plotted hook called")

        # Clear previous spike analysis visualization
        if self.spike_markers_item:
            self.spike_markers_item.setData([])
            self.spike_markers_item.setVisible(False)
        if self.threshold_line:
            self.threshold_line.setVisible(False)

        # Validate that base class plotted data successfully
        if not self._current_plot_data or "time" not in self._current_plot_data:
            return

        # Update threshold line position if parameters are available
        params = self._gather_analysis_parameters()
        threshold = params.get("threshold")
        if threshold is not None and self.threshold_line:
            self.threshold_line.setValue(threshold)
            self.threshold_line.setVisible(True)

        # CRITICAL: Call parent to trigger analysis and enable save button
        super()._on_data_plotted()

    def _plot_analysis_visualizations(self, results: Any):
        """
        Visualize spike detection results.
        Called by BaseAnalysisTab._on_analysis_result.
        """
        # Handle both object and dict
        if isinstance(results, dict):
            # If wrapped in dict with 'result' key (from generic wrapper)
            if "result" in results:
                result_obj = results["result"]
            else:
                result_obj = results
        else:
            result_obj = results

        # Update Plot
        if hasattr(result_obj, "spike_indices") and result_obj.spike_indices is not None:
            spike_indices = result_obj.spike_indices
            if len(spike_indices) > 0 and self._current_plot_data:
                times = self._current_plot_data["time"][spike_indices]
                voltages = self._current_plot_data["data"][spike_indices]

                if self.spike_markers_item:
                    self.spike_markers_item.setData(times, voltages)
                    self.spike_markers_item.setVisible(True)
        elif isinstance(result_obj, dict) and "spike_indices" in result_obj:
            spike_indices = result_obj["spike_indices"]
            if spike_indices is not None and len(spike_indices) > 0 and self._current_plot_data:
                times = self._current_plot_data["time"][spike_indices]
                voltages = self._current_plot_data["data"][spike_indices]
                if self.spike_markers_item:
                    self.spike_markers_item.setData(times, voltages)
                    self.spike_markers_item.setVisible(True)

        # Update threshold line from result metadata (in case it changed)
        threshold = None
        if hasattr(result_obj, "metadata"):
            threshold = result_obj.metadata.get("threshold")
        elif isinstance(result_obj, dict):
            metadata = result_obj.get("metadata", {})
            threshold = metadata.get("threshold")

        if threshold is not None and self.threshold_line:
            self.threshold_line.setValue(threshold)
            self.threshold_line.setVisible(True)

    def _display_analysis_results(self, result: Any):
        """Display spike detection results in text edit."""
        if not result:
            self.results_text.setText("Analysis failed.")
            return

        # Handle both object and dict
        if isinstance(result, dict):
            metadata = result.get("metadata", {})
            spike_times = result.get("spike_times")
        else:
            metadata = getattr(result, "metadata", {})
            spike_times = getattr(result, "spike_times", None)

        threshold = metadata.get("threshold")
        refractory_ms = metadata.get("refractory_ms")
        units = metadata.get("units", "V")

        # spike_times is already extracted above
        num_spikes = len(spike_times) if spike_times is not None else 0

        results_str = f"--- Spike Detection Results ---\n"
        if threshold is not None:
            results_str += f"Threshold: {threshold:.3f} {units}\n"
        if refractory_ms is not None:
            results_str += f"Refractory: {refractory_ms:.2f} ms\n"
        results_str += f"\nDetected Spikes: {num_spikes}\n"

        if num_spikes > 0:
            rate = metadata.get("average_firing_rate_hz")
            if rate:
                results_str += f"Avg Firing Rate: {rate:.2f} Hz\n"

            isi_mean = metadata.get("isi_mean_ms")
            isi_std = metadata.get("isi_std_ms")
            if isi_mean:
                results_str += f"ISI: {isi_mean:.2f} ± {isi_std:.2f} ms\n"

            results_str += "\n--- Feature Averages ---\n"

            # Helper to add feature stats
            def add_stat(label, key_prefix, unit):
                mean = metadata.get(f"{key_prefix}_mean")
                std = metadata.get(f"{key_prefix}_std")
                if mean is not None:
                    nonlocal results_str
                    results_str += f"{label}: {mean:.2f} ± {std:.2f} {unit}\n"

            add_stat("Amplitude", "amplitude", "mV")
            add_stat("Half-Width", "half_width", "ms")
            add_stat("Rise Time", "rise_time", "ms")
            add_stat("Decay Time", "decay_time", "ms")
            add_stat("AHP Depth", "ahp_depth", "mV")
            add_stat("AHP Duration", "ahp_duration", "ms")
            add_stat("ADP Amp", "adp_amplitude", "mV")

        self.results_text.setText(results_str)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        # Use parent's stored result from _on_analysis_result
        if hasattr(self, "_last_analysis_result") and self._last_analysis_result:
            # If it's an object, try to convert to dict or return as is
            if hasattr(self._last_analysis_result, "to_dict"):
                return self._last_analysis_result.to_dict()
            if isinstance(self._last_analysis_result, dict):
                return self._last_analysis_result
            return {"result": self._last_analysis_result}
        return None


# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = SpikeAnalysisTab
