# src/Synaptipy/application/gui/analysis_tabs/spike_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting spikes using a simple threshold.
Refactored to use MetadataDrivenAnalysisTab architecture.
"""
import logging
from typing import Optional, Dict, Any
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

# Import base class
from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)


class SpikeAnalysisTab(MetadataDrivenAnalysisTab):
    """
    QWidget for Threshold-based Spike Detection.
    Inherits from MetadataDrivenAnalysisTab to use metadata-defined parameters.
    """

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        # Spike-specific plot items
        self.spike_markers_item: Optional[pg.ScatterPlotItem] = None
        self.threshold_line: Optional[pg.InfiniteLine] = None
        self._last_spike_result: Optional[Dict[str, Any]] = None

        # Initialize with the specific analysis name "spike_detection"
        super().__init__(
            analysis_name="spike_detection", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

    def _setup_ui(self):
        """Setup UI and initialize plot items."""
        # Call parent to setup layout and plot area
        super()._setup_ui()

        # Initialize plot items now that plot_widget is created
        if self.plot_widget:
            self.spike_markers_item = pg.ScatterPlotItem(
                size=8, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 150),
                name="Spikes", hoverable=True, tip="t={x:.4f}s, v={y:.2f}mV"
            )
            # Add to plot
            self.plot_widget.addItem(self.spike_markers_item)
            # Z-value high to be on top
            self.spike_markers_item.setZValue(10)

            # Threshold line
            self.threshold_line = pg.InfiniteLine(
                angle=0, movable=True, pen=pg.mkPen("r", style=QtCore.Qt.PenStyle.DashLine)
            )
            self.plot_widget.addItem(self.threshold_line)

            self.spike_markers_item.setVisible(False)
            # Ensure visible and connect signal
            self.threshold_line.setVisible(True)
            self.threshold_line.sigPositionChangeFinished.connect(self._on_threshold_dragged)

    def get_display_name(self) -> str:
        return "Spike Detection"

    # _setup_ui is inherited from MetadataDrivenAnalysisTab
    # _gather_analysis_parameters is inherited
    # _execute_core_analysis is inherited (uses registry function)

    def _ensure_custom_items_on_plot(self):
        """Re-add custom plot items if they were removed by plot_widget.clear()."""
        if not self.plot_widget:
            return
        if self.spike_markers_item and self.spike_markers_item not in self.plot_widget.items:
            self.plot_widget.addItem(self.spike_markers_item)
            self.spike_markers_item.setZValue(10)
        if self.threshold_line and self.threshold_line not in self.plot_widget.items:
            self.plot_widget.addItem(self.threshold_line)

    def _on_data_plotted(self):
        """
        Hook called by BaseAnalysisTab after plotting main data trace.
        Adds Spike-specific plot items: spike markers and threshold line.
        """
        log.debug(f"{self.get_display_name()}: _on_data_plotted hook called")

        # Re-add items that may have been removed by plot_widget.clear()
        self._ensure_custom_items_on_plot()

        # Clear previous spike analysis visualization (markers only)
        if self.spike_markers_item:
            self.spike_markers_item.setData([])
            self.spike_markers_item.setVisible(False)

        # Validate that base class plotted data successfully
        if not self._current_plot_data or "time" not in self._current_plot_data:
            return

        # Update threshold line position and ensure it is visible
        params = self._gather_analysis_parameters()
        threshold = params.get("threshold")
        if threshold is not None and self.threshold_line:
            self.threshold_line.setValue(threshold)
        if self.threshold_line:
            self.threshold_line.setVisible(True)

        # CRITICAL: Call parent to trigger analysis and enable save button
        super()._on_data_plotted()

    def _plot_analysis_visualizations(self, results: Any):  # noqa: C901
        """
        Visualize spike detection results.
        Called by BaseAnalysisTab._on_analysis_result.
        """
        # Ensure items are on the plot (they may have been removed by clear())
        self._ensure_custom_items_on_plot()

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
            import numpy as np
            spike_indices = np.array(spike_indices, dtype=int)
            if len(spike_indices) > 0 and self._current_plot_data:
                times = self._current_plot_data["time"][spike_indices]
                voltages = self._current_plot_data["data"][spike_indices]

                if self.spike_markers_item:
                    self.spike_markers_item.setData(x=times, y=voltages)
                    self.spike_markers_item.setVisible(True)
        elif isinstance(result_obj, dict) and "spike_indices" in result_obj:
            spike_indices = result_obj["spike_indices"]
            import numpy as np
            spike_indices = np.array(spike_indices, dtype=int)
            if spike_indices is not None and len(spike_indices) > 0 and self._current_plot_data:
                times = self._current_plot_data["time"][spike_indices]
                voltages = self._current_plot_data["data"][spike_indices]
                if self.spike_markers_item:
                    self.spike_markers_item.setData(x=times, y=voltages)
                    self.spike_markers_item.setVisible(True)

        # Update threshold line from result parameters (in case it changed)
        threshold = None
        if hasattr(result_obj, "parameters"):
            threshold = result_obj.parameters.get("threshold")
        elif hasattr(result_obj, "metadata"):
            threshold = result_obj.metadata.get("threshold")
        elif isinstance(result_obj, dict):
            params = result_obj.get("parameters", result_obj.get("metadata", {}))
            threshold = params.get("threshold")

        if threshold is not None and self.threshold_line:
            self.threshold_line.setValue(threshold)
            self.threshold_line.setVisible(True)

    def _display_analysis_results(self, result: Any):  # noqa: C901
        """Display spike detection results in table."""
        if not self.results_table:
            return

        if not result:
            self.results_table.setRowCount(1)
            self.results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Status"))
            self.results_table.setItem(0, 1, QtWidgets.QTableWidgetItem("Analysis Failed"))
            return

        # Handle both object and dict
        if isinstance(result, dict):
            metadata = result.get("parameters", result.get("metadata", {}))
            spike_times = result.get("spike_times")
            
            # Extract flat stats if present
            rate = result.get("mean_freq_hz", metadata.get("average_firing_rate_hz"))
            isi_mean = result.get("isi_mean_ms", metadata.get("isi_mean_ms"))
            isi_std = result.get("isi_std_ms", metadata.get("isi_std_ms"))
        else:
            metadata = getattr(result, "metadata", getattr(result, "parameters", {}))
            spike_times = getattr(result, "spike_times", None)
            
            rate = metadata.get("average_firing_rate_hz") if hasattr(result, "metadata") else getattr(result, "mean_frequency", None)
            isi_mean = metadata.get("isi_mean_ms") if hasattr(result, "metadata") else None
            isi_std = metadata.get("isi_std_ms") if hasattr(result, "metadata") else None

        threshold = metadata.get("threshold")
        refractory_ms = metadata.get("refractory_period", metadata.get("refractory_ms"))
        if refractory_ms is not None and refractory_ms < 1.0:
            refractory_ms = refractory_ms * 1000.0  # Convert to ms if it's in seconds
        
        units = metadata.get("units", "V") if hasattr(result, "metadata") else "mV"
        num_spikes = len(spike_times) if spike_times is not None else 0

        display_items = []
        if threshold is not None:
            display_items.append(("Threshold", f"{threshold:.3f} {units}"))
        if refractory_ms is not None:
            display_items.append(("Refractory", f"{refractory_ms:.2f} ms"))
        display_items.append(("Detected Spikes", str(num_spikes)))

        if num_spikes > 0:
            if rate is not None:
                display_items.append(("Avg Firing Rate", f"{rate:.2f} Hz"))

            if isi_mean is not None:
                display_items.append(("ISI", f"{isi_mean:.2f} ± {isi_std:.2f} ms"))

            # Helper to add feature stats
            import numpy as np
            def add_stat(label, key):
                mean_val = result.get(f"{key}_mean", metadata.get(f"{key}_mean")) if isinstance(result, dict) else metadata.get(f"{key}_mean")
                std_val = result.get(f"{key}_std", metadata.get(f"{key}_std")) if isinstance(result, dict) else metadata.get(f"{key}_std")
                if mean_val is not None and std_val is not None and not np.isnan(mean_val):
                    unit_str = "ms" if "width" in key or "time" in key else "mV"
                    if "dvdt" in key:
                        unit_str = "V/s"
                    display_items.append((label, f"{mean_val:.2f} ± {std_val:.2f} {unit_str}"))

            add_stat("Amplitude", "amplitude")
            add_stat("Half-Width", "half_width_ms")
            add_stat("Rise Time", "rise_time_ms")
            add_stat("Decay Time", "decay_time_ms")
            add_stat("AHP Depth", "ahp_depth")
            add_stat("Max dV/dt", "max_dvdt")
            add_stat("Min dV/dt", "min_dvdt")
            add_stat("AHP Duration", "ahp_duration")
            add_stat("ADP Amp", "adp_amplitude")

        self.results_table.setRowCount(len(display_items))
        for row, (k, v) in enumerate(display_items):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(k))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(v))

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

    def _on_threshold_dragged(self):
        """Handle threshold line drag event."""
        if not self.threshold_line:
            return

        new_val = self.threshold_line.value()
        log.debug(f"Threshold dragged to: {new_val}")

        # Update parameter widget
        if hasattr(self, "param_generator") and "threshold" in self.param_generator.widgets:
            widget = self.param_generator.widgets["threshold"]
            # Block signals to prevent loop (param change -> plot update -> line update)
            signals_blocked = widget.blockSignals(True)
            if isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setValue(new_val)
            widget.blockSignals(signals_blocked)

            # Manually trigger parameter change callback
            if hasattr(self, "_on_param_changed"):
                self._on_param_changed()


# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = SpikeAnalysisTab
