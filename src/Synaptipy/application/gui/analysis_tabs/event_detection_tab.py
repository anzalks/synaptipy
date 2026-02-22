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
            "Baseline + Peak + Kinetics": "event_detection_baseline_peak"
        }

        # Initialize with default method
        default_method = "event_detection_threshold"
        super().__init__(
            analysis_name=default_method, neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

        # Trigger initial params load
        self._on_method_changed()
        self._current_event_indices = []

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
        self.event_markers_item.sigClicked.connect(self._on_marker_clicked)

        # Intercept clicks on the plot for adding markers
        self.plot_widget.scene().sigMouseClicked.connect(self._on_plot_clicked)

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

    def _on_channel_changed(self, index=None):
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
            # Do not check len > 0 here, so we capture empty results too
        ):
            self._current_event_indices = list(np.array(event_indices, dtype=int))
            self._update_event_markers()
        else:
            self._current_event_indices = []
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

    def _display_analysis_results(self, results: Any):
        """Override to provide table result summary directly from the curated list."""
        self._update_table_from_curation()

    def _update_event_markers(self):
        """Redraw markers based on current valid indices."""
        if not hasattr(self, "_current_plot_data") or not self._current_plot_data:
            return

        indices = np.array(self._current_event_indices, dtype=int)
        if len(indices) > 0:
            times = self._current_plot_data["time"][indices]
            voltages = self._current_plot_data["data"][indices]
            self.event_markers_item.setData(x=times, y=voltages)
            self.event_markers_item.setVisible(True)
        else:
            self.event_markers_item.setData(x=[], y=[])
            self.event_markers_item.setVisible(False)

    def _update_table_from_curation(self):
        """Update the results table using the latest curated indices."""
        if not self.results_table:
            return

        count = len(self._current_event_indices)
        if count == 0:
            self.results_table.setRowCount(1)
            self.results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Status"))
            self.results_table.setItem(0, 1, QtWidgets.QTableWidgetItem("No Events"))
            return

        if not hasattr(self, "_current_plot_data") or not self._current_plot_data:
            return

        indices = np.array(self._current_event_indices, dtype=int)
        try:
            amplitudes = self._current_plot_data["data"][indices]
        except IndexError:
            return

        duration = self._current_plot_data["time"][-1] - self._current_plot_data["time"][0]
        freq = count / duration if duration > 0 else 0.0
        mean_amp = float(np.mean(amplitudes))
        amp_sd = float(np.std(amplitudes))

        display_items = [
            ("Method", self.method_combobox.currentText() + " (Curated)"),
            ("Count", str(count)),
            ("Frequency", f"{freq:.2f} Hz"),
            ("Mean Amplitude", f"{mean_amp:.2f} ± {amp_sd:.2f}"),
        ]

        # Add Threshold if available from UI
        if self.threshold_line and self.threshold_line.isVisible():
            display_items.append(("Threshold", f"{self.threshold_line.value():.2f}"))

        self.results_table.setRowCount(len(display_items))
        for row, (k, v) in enumerate(display_items):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(k))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(v))

    def _on_marker_clicked(self, scatter, points, ev):
        """Remove event marker on click."""
        if len(points) == 0:
            return
        ev.accept()

        pos = points[0].pos()
        clicked_time = pos.x()
        times = self._current_plot_data["time"]

        # Add slight tolerance for floating point matching
        dt = times[1] - times[0] if len(times) > 1 else 0.001
        tolerance = dt * 1.5

        for i, e_idx in enumerate(self._current_event_indices):
            if abs(times[e_idx] - clicked_time) <= tolerance:
                self._current_event_indices.pop(i)
                break

        self._update_event_markers()
        self._update_table_from_curation()

    def _on_plot_clicked(self, ev):
        """Add event marker on ctrl-click."""
        if not ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            return

        if not getattr(self, "_current_plot_data", None):
            return

        # Map scene coordinates to data coordinates
        pos = self.plot_widget.plotItem.vb.mapSceneToView(ev.scenePos())
        clicked_time = pos.x()

        times = self._current_plot_data["time"]
        if clicked_time < times[0] or clicked_time > times[-1]:
            return

        # Find closest index
        idx = int(np.argmin(np.abs(times - clicked_time)))

        # Add to indices if not already present
        if idx not in self._current_event_indices:
            self._current_event_indices.append(idx)
            self._current_event_indices.sort()

            self._update_event_markers()
            self._update_table_from_curation()

    def _on_threshold_dragged(self):
        """Handle threshold line drag event."""
        if not self.threshold_line:
            return

        new_val = self.threshold_line.value()
        log.debug(f"Event threshold dragged to: {new_val}")

        # Update parameter widget if it exists (e.g. standard Threshold Based method)
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
