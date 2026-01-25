# src/Synaptipy/application/gui/analysis_tabs/event_detection_tab.py
# -*- coding: utf-8 -*-
"""
Analysis sub-tab for detecting synaptic events (Miniature and Evoked).
Refactored to inherit from MetadataDrivenAnalysisTab.
"""
import logging
from typing import Optional, Dict, Any, List
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry
import Synaptipy.core.analysis.event_detection  # Ensure registration

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
            # "Baseline + Peak + Kinetics": "event_detection_baseline_peak" # Uncomment if available
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

    def _setup_additional_controls(self, layout: QtWidgets.QVBoxLayout):
        """Add method selection combobox."""
        method_layout = QtWidgets.QFormLayout()
        self.method_combobox = QtWidgets.QComboBox()
        self.method_combobox.addItems(list(self.method_map.keys()))
        self.method_combobox.setToolTip("Choose the miniature event detection algorithm.")
        self.method_combobox.currentIndexChanged.connect(self._on_method_changed)

        method_layout.addRow("Method:", self.method_combobox)
        layout.addLayout(method_layout)

        # We can also add an explicit "Detect" button if desired, though generic tab is reactive
        # Let's add it for clarity/consistency with old behavior
        self.analyze_button = QtWidgets.QPushButton("Detect Events")
        self.analyze_button.setToolTip("Run event detection")
        self.analyze_button.clicked.connect(self._trigger_analysis)
        layout.addWidget(self.analyze_button)

    def _setup_custom_plot_items(self):
        """Add markers and lines to the plot."""
        if not self.plot_widget:
            return

        # Markers for detected events
        self.event_markers_item = pg.ScatterPlotItem(size=10, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 150))
        self.plot_widget.addItem(self.event_markers_item)
        self.event_markers_item.setVisible(False)
        self.event_markers_item.setZValue(100)  # On top

        # Threshold line
        self.threshold_line = pg.InfiniteLine(
            angle=0, movable=True, pen=pg.mkPen("b", style=QtCore.Qt.PenStyle.DashLine)
        )
        self.plot_widget.addItem(self.threshold_line)
        self.threshold_line.setVisible(False)
        self.threshold_line.setVisible(False)
        self.threshold_line.setZValue(90)

    def _on_channel_changed(self, index):
        """Re-add items to plot if cleared."""
        super()._on_channel_changed(index)
        if self.plot_widget:
            if self.event_markers_item and self.event_markers_item not in self.plot_widget.items():
                self.plot_widget.addItem(self.event_markers_item)
            if self.threshold_line and self.threshold_line not in self.plot_widget.items():
                self.plot_widget.addItem(self.threshold_line)

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

            # Trigger analysis (optional, maybe wait for user?)
            # self._trigger_analysis()

    def _plot_analysis_visualizations(self, results: Any):
        """Visualize analysis results (markers)."""
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

    def _on_analysis_result(self, results: Any):
        """Override to provide custom HTML result summary."""
        # Call super to handle storage, plot hook, save button
        super()._on_analysis_result(results)

        # Now update the text with HTML summary
        if isinstance(results, dict) and "result" in results:
            result_data = results["result"]
        else:
            result_data = results

        if not result_data:
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

        text = f"<h3>Event Detection Results</h3>"
        text += f"<b>Method:</b> {self.method_combobox.currentText()}<br>"
        text += f"<b>Count:</b> {count}<br>"

        if freq is not None:
            text += f"<b>Frequency:</b> {freq:.2f} Hz<br>"

        if mean_amp is not None:
            text += f"<b>Mean Amplitude:</b> {mean_amp:.2f} ± {amp_sd:.2f}<br>"

        thresh = get_val("threshold")
        if thresh is not None:
            text += f"<b>Threshold:</b> {thresh}<br>"

        if hasattr(self, "results_text"):  # MetadataDriven uses results_text (TextEdit)
            self.results_text.setHtml(text)


# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = EventDetectionTab
