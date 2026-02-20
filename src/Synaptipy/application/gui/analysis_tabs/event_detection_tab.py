# src/Synaptipy/application/gui/analysis_tabs/event_detection_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting synaptic events (Miniature and Evoked).
Refactored to inherit from MetadataDrivenAnalysisTab.
"""
import logging
from typing import Optional, Any, List
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


class EventDetectionTab(MetadataDrivenAnalysisTab):
    """
    QWidget for Synaptic Event Detection (Miniature and Evoked).
    Inherits from MetadataDrivenAnalysisTab.
    """

    # Define the class constant for dynamic loading
    ANALYSIS_TAB_CLASS = True

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        # Initialize map
        self.method_map = {
            "Threshold Based": "event_detection_threshold",
            "Deconvolution (Custom)": "event_detection_deconvolution",
            # "Baseline + Peak + Kinetics": "event_detection_baseline_peak"  # Uncomment if available
        }

        # Initialize with default method
        default_method = "event_detection_threshold"
        super().__init__(
            analysis_name=default_method, neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

        # Trigger initial params load
        self._on_method_changed()

    def get_display_name(self) -> str:
        return "Event Detection"

    def get_covered_analysis_names(self) -> List[str]:
        return list(self.method_map.values())

    def _setup_additional_controls(self, layout: QtWidgets.QFormLayout):
        """Add method selection to Parameters group."""
        self.method_combobox = QtWidgets.QComboBox()
        self.method_combobox.addItems(list(self.method_map.keys()))
        self.method_combobox.setToolTip("Choose the miniature event detection algorithm.")
        self.method_combobox.currentIndexChanged.connect(self._on_method_changed)

        layout.addRow("Method:", self.method_combobox)

        # "Detect" button
        self.analyze_button = QtWidgets.QPushButton("Detect Events")
        self.analyze_button.setToolTip("Run event detection")
        self.analyze_button.clicked.connect(self._trigger_analysis)

        # Add button as a row (spanning or labelled?)
        # layout.addRow(self.analyze_button) works but puts it in the second column usually
        # Let's try to put it nicely
        layout.addRow("", self.analyze_button)

        if (hasattr(self, "threshold_line")
                and self.threshold_line
                and self.threshold_line not in self.plot_widget.items):
            self.plot_widget.addItem(self.threshold_line)
            self.threshold_line.setZValue(90)

        # Ensure artifact curve is present
        if (hasattr(self, "artifact_curve_item")
                and self.artifact_curve_item
                and self.artifact_curve_item not in self.plot_widget.items):
            self.plot_widget.addItem(self.artifact_curve_item)
            self.artifact_curve_item.setZValue(80)

    def _setup_custom_plot_items(self):
        """Add markers and lines to the plot."""
        if not self.plot_widget:
            return

        # Markers for detected events
        self.event_markers_item = pg.ScatterPlotItem(size=10, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 150))
        self.plot_widget.addItem(self.event_markers_item)
        self.event_markers_item.setVisible(False)
        self.event_markers_item.setZValue(100)  # On top

        # Artifact Mask Visualization (Green overlay)
        # Use a pleasant sea green color for artifact regions to distinguish from red events
        self.artifact_curve_item = pg.PlotCurveItem(pen=pg.mkPen(color=(60, 179, 113, 200), width=3))
        self.plot_widget.addItem(self.artifact_curve_item)
        self.artifact_curve_item.setVisible(False)
        self.artifact_curve_item.setZValue(80)

        # Threshold line
        self.threshold_line = pg.InfiniteLine(
            angle=0, movable=True, pen=pg.mkPen("b", style=QtCore.Qt.PenStyle.DashLine)
        )
        self.plot_widget.addItem(self.threshold_line)
        self.threshold_line.setVisible(True)
        self.threshold_line.setZValue(90)
        self.threshold_line.sigPositionChangeFinished.connect(self._on_threshold_dragged)

    def _ensure_custom_items_on_plot(self):
        """Re-add custom plot items if they were removed by plot_widget.clear()."""
        if not self.plot_widget:
            return

        if (hasattr(self, "event_markers_item")
                and self.event_markers_item
                and self.event_markers_item not in self.plot_widget.items):
            self.plot_widget.addItem(self.event_markers_item)
            self.event_markers_item.setZValue(100)

        if (hasattr(self, "threshold_line")
                and self.threshold_line
                and self.threshold_line not in self.plot_widget.items):
            self.plot_widget.addItem(self.threshold_line)
            self.threshold_line.setZValue(90)

        if (hasattr(self, "artifact_curve_item")
                and self.artifact_curve_item
                and self.artifact_curve_item not in self.plot_widget.items):
            self.plot_widget.addItem(self.artifact_curve_item)
            self.artifact_curve_item.setZValue(80)

    def _on_channel_changed(self, index):
        """Re-add items to plot if cleared."""
        super()._on_channel_changed(index)
        self._ensure_custom_items_on_plot()

    def _on_data_plotted(self):
        """Re-add custom items after plot_widget.clear() in _plot_selected_data."""
        self._ensure_custom_items_on_plot()
        super()._on_data_plotted()

    def _on_method_changed(self):
        """Handle method switching."""
        if not hasattr(self, "method_combobox"):
            return

        method_name = self.method_combobox.currentText()
        registry_key = self.method_map.get(method_name)

        if registry_key:
            log.debug(f"Switching to analysis method: {registry_key}")
            # Update the core analysis name so _execute_core_analysis uses the right function
            self.analysis_name = registry_key

            # Update metadata
            self.metadata = AnalysisRegistry.get_metadata(registry_key)

            # Rebuild parameter widgets
            if hasattr(self, "param_generator"):
                ui_params = self.metadata.get("ui_params", [])
                self.param_generator.generate_widgets(ui_params, self._on_param_changed)

            # Clear results
            if hasattr(self, "results_text"):
                self.results_text.clear()
            if hasattr(self, "event_markers_item"):
                self.event_markers_item.setData([])
                self.event_markers_item.setVisible(False)
            if hasattr(self, "artifact_curve_item"):
                self.artifact_curve_item.setData([], [])
                self.artifact_curve_item.setVisible(False)

            # Trigger analysis (optional, maybe wait for user?)
            # self._trigger_analysis()

    def _plot_analysis_visualizations(self, results: Any):  # noqa: C901
        """Visualize analysis results (markers)."""
        # Ensure items are on the plot (they may have been removed by clear())
        self._ensure_custom_items_on_plot()

        if isinstance(results, dict) and "result" in results:
            result_data = results["result"]
        else:
            result_data = results

        # Support both object and dict
        is_obj = hasattr(result_data, "event_indices")

        event_indices = (
            result_data.event_indices
            if is_obj
            else (result_data.get("event_indices") if isinstance(result_data, dict) else None)
        )

        if (
            event_indices is not None
            and len(event_indices) > 0
            and hasattr(self, "_current_plot_data")
            and self._current_plot_data
        ):
            times = self._current_plot_data["time"][event_indices]
            voltages = self._current_plot_data["data"][event_indices]

            if self.event_markers_item:
                self.event_markers_item.setData(x=times, y=voltages)
                self.event_markers_item.setVisible(True)
        else:
            if self.event_markers_item:
                self.event_markers_item.setVisible(False)

        # Artifact Mask
        if hasattr(self, "artifact_curve_item"):
            artifact_mask = getattr(result_data, "artifact_mask", None)
            if artifact_mask is not None and hasattr(self, "_current_plot_data") and self._current_plot_data:
                # We want to plot the trace only where mask is True.
                # Create a copy of data and set non-artifact regions to NaN
                full_data = self._current_plot_data["data"]
                full_time = self._current_plot_data["time"]

                if len(full_data) == len(artifact_mask):
                    artifact_data = full_data.copy()
                    # Invert mask: set non-artifact to nan
                    artifact_data[~artifact_mask] = np.nan

                    self.artifact_curve_item.setData(full_time, artifact_data, connect="finite")
                    self.artifact_curve_item.setVisible(True)
                else:
                    self.artifact_curve_item.setVisible(False)
            else:
                self.artifact_curve_item.setVisible(False)

        # Threshold line
        if is_obj:
            threshold_val = getattr(result_data, "threshold", None) or getattr(result_data, "threshold_value", None)
        else:
            threshold_val = result_data.get("threshold") if isinstance(result_data, dict) else None
            if threshold_val is None and isinstance(result_data, dict):
                threshold_val = result_data.get("threshold_value")

        if threshold_val is not None and self.threshold_line:
            self.threshold_line.setValue(threshold_val)
            self.threshold_line.setVisible(True)
        elif self.threshold_line:
            self.threshold_line.setVisible(False)

    def _display_analysis_results(self, results: Any):  # noqa: C901
        """Override to provide table result summary."""
        if not self.results_table:
            return

        # Handle simplified result structure
        if isinstance(results, dict) and "result" in results:
            result_data = results["result"]
        else:
            result_data = results

        if not result_data:
            self.results_table.setRowCount(1)
            self.results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Status"))
            self.results_table.setItem(0, 1, QtWidgets.QTableWidgetItem("No Results"))
            return

        # Support both object and dict access for robustness
        def get_val(key, default=None):
            if hasattr(result_data, key):
                return getattr(result_data, key)
            elif isinstance(result_data, dict):
                return result_data.get(key, default)
            return default

        count = get_val("event_count", 0)
        freq = get_val("frequency_hz")
        mean_amp = get_val("mean_amplitude")
        amp_sd = get_val("amplitude_sd")
        thresh = get_val("threshold")

        display_items = []
        display_items.append(("Method", self.method_combobox.currentText()))
        display_items.append(("Count", str(count)))

        if freq is not None:
            display_items.append(("Frequency", f"{freq:.2f} Hz"))

        if mean_amp is not None:
            display_items.append(("Mean Amplitude", f"{mean_amp:.2f} ± {amp_sd:.2f}"))

        if thresh is not None:
            display_items.append(("Threshold", str(thresh)))

        self.results_table.setRowCount(len(display_items))
        for row, (k, v) in enumerate(display_items):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(k))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(v))

    def _on_threshold_dragged(self):
        """Handle threshold line drag event."""
        if not self.threshold_line:
            return

        new_val = self.threshold_line.value()
        log.debug(f"Event threshold dragged to: {new_val}")

        # Update parameter widget
        if hasattr(self, "param_generator") and "threshold" in self.param_generator.widgets:
            widget = self.param_generator.widgets["threshold"]
            # Block signals to prevent loop
            signals_blocked = widget.blockSignals(True)
            if isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setValue(new_val)
            widget.blockSignals(signals_blocked)

            # Trigger update
            if hasattr(self, "_on_param_changed"):
                self._on_param_changed()


# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = EventDetectionTab
