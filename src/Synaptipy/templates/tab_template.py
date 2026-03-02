# src/Synaptipy/templates/tab_template.py
"""
GOLDEN SAMPLE: GUI Tab Architecture.
Refers to: src/Synaptipy/application/gui/analysis_tabs/base.py
Use this structure for ALL new analysis tabs.
"""
from typing import Any, Dict, Optional

import pyqtgraph as pg
from PySide6 import QtCore

# Rule: Must inherit from MetadataDrivenAnalysisTab (preferred) or BaseAnalysisTab
from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter

# Rule: Import the result type you expect
# from Synaptipy.core.results import AnalysisResult

# Rule: Ensure the analysis module is imported to register it


class TemplateAnalysisTab(MetadataDrivenAnalysisTab):
    """
    Template for analysis tabs.
    1. Defines display name.
    2. Initializes plot items (lines/scatter) in __init__.
    3. Visualizes results in _plot_analysis_visualizations.
    """

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        # Rule: Pass the registry 'analysis_name' here so the base class finds parameters automatically
        super().__init__(
            analysis_name="template_metric", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

        # Rule: Initialize Plot Items here (Hidden by default)
        # Do NOT create new PlotWidgets. Use self.plot_widget provided by base.
        self.marker_item = pg.ScatterPlotItem(size=10, pen=pg.mkPen(None), brush=pg.mkBrush("r"))
        if self.plot_widget:
            self.plot_widget.addItem(self.marker_item)
            self.marker_item.setVisible(False)

    def get_display_name(self) -> str:
        return "Template Analysis"

    # --- LIFECYCLE HOOKS ---

    def _on_data_plotted(self):
        """
        Hook called automatically when the user changes 'Trial' or 'Channel'.
        Use this to reset/update visualizations based on raw data, NOT analysis results.
        """
        # Rule: Always clear your specific items first
        if self.marker_item:
            self.marker_item.setVisible(False)

        # Rule: Call super() to ensure state is consistent
        super()._on_data_plotted()

    def _plot_analysis_visualizations(self, results: Any):
        """
        Hook called automatically after analysis finishes.
        Use this to draw markers, lines, or regions based on the Result object.
        """
        # Rule: Handle the 'wrapper dict' vs 'result object' ambiguity
        result_obj = results["result"] if isinstance(results, dict) and "result" in results else results

        # Example: Plotting markers at specific indices
        if hasattr(result_obj, "indices") and self._current_plot_data:
            times = self._current_plot_data["time"][result_obj.indices]
            values = self._current_plot_data["data"][result_obj.indices]

            self.marker_item.setData(times, values)
            self.marker_item.setVisible(True)

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """
        Required for the 'Save' button to work.
        """
        if hasattr(self, "_last_analysis_result") and self._last_analysis_result:
            if hasattr(self._last_analysis_result, "to_dict"):
                return self._last_analysis_result.to_dict()
            return self._last_analysis_result
        return None


# Rule: Must export this variable for the dynamic loader to find the class
ANALYSIS_TAB_CLASS = TemplateAnalysisTab
