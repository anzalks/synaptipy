# src/Synaptipy/application/gui/analysis_tabs/rin_tab.py
# -*- coding: utf-8 -*-
"""
Analysis tab for calculating Input Resistance (Rin) with interactive selection.
Refactored to inherit from MetadataDrivenAnalysisTab.
"""
import logging
from typing import Optional, Dict, Any
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from .metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)


class RinAnalysisTab(MetadataDrivenAnalysisTab):
    """
    Widget for Input Resistance/Conductance calculation with interactive plotting.
    Now inherits from MetadataDrivenAnalysisTab for unified architecture.
    """

    # Class constants for modes
    _MODE_INTERACTIVE = "Interactive (Regions)"
    _MODE_MANUAL = "Manual (Time Windows)"

    def __init__(self, neo_adapter: NeoAdapter, settings_ref: Optional[QtCore.QSettings] = None, parent=None):
        # Initialize the base class with the registry name 'rin_analysis'
        super().__init__(
            analysis_name="rin_analysis", neo_adapter=neo_adapter, settings_ref=settings_ref, parent=parent
        )

    def get_display_name(self) -> str:
        return "Resistance/Conductance"

    def get_covered_analysis_names(self) -> list[str]:
        return ["rin_analysis", "tau_analysis"]

    def _setup_additional_controls(self, layout: QtWidgets.QFormLayout):
        """Add mode selection to Parameters group."""
        self.mode_combobox = QtWidgets.QComboBox()
        self.mode_combobox.addItem(self._MODE_INTERACTIVE)
        self.mode_combobox.addItem(self._MODE_MANUAL)
        self.mode_combobox.currentIndexChanged.connect(self._on_mode_changed)

        layout.addRow("Mode:", self.mode_combobox)

    def _setup_custom_plot_items(self):
        """Add regions and lines to the plot."""
        if not self.plot_widget:
            return

        # Regions for interactive selection
        # Use semi-transparent brushes
        self.baseline_region = pg.LinearRegionItem(values=[0, 0.1], brush=pg.mkBrush(0, 0, 255, 50))
        self.response_region = pg.LinearRegionItem(values=[0.3, 0.4], brush=pg.mkBrush(255, 0, 0, 50))

        self.plot_widget.addItem(self.baseline_region)
        self.plot_widget.addItem(self.response_region)

        self.baseline_region.sigRegionChanged.connect(self._on_region_changed)
        self.response_region.sigRegionChanged.connect(self._on_region_changed)

        # Visualization lines for results
        self.baseline_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("b", style=QtCore.Qt.PenStyle.DashLine))
        self.response_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("r", style=QtCore.Qt.PenStyle.DashLine))

        self.plot_widget.addItem(self.baseline_line)
        self.plot_widget.addItem(self.response_line)
        self.baseline_line.setVisible(False)
        self.response_line.setVisible(False)

        # Trigger initial mode update
        self._on_mode_changed()

    def _on_mode_changed(self):
        """Handle switching between Interactive and Manual modes."""
        mode = self.mode_combobox.currentText()
        is_interactive = mode == self._MODE_INTERACTIVE

        if hasattr(self, "baseline_region"):
            self.baseline_region.setVisible(is_interactive)
            self.response_region.setVisible(is_interactive)

        # Disable/Enable parameter widgets based on mode
        # We need to access the generator in the base class via self.param_generator
        if hasattr(self, "param_generator"):
            time_params = ["baseline_start", "baseline_end", "response_start", "response_end"]
            for name in time_params:
                widget = self.param_generator.widgets.get(name)
                if widget:
                    # In interactive mode, disable manual inputs
                    widget.setEnabled(not is_interactive)

            # Disable auto_detect in interactive mode?
            auto_detect = self.param_generator.widgets.get("auto_detect_pulse")
            if auto_detect:
                auto_detect.setEnabled(not is_interactive)

            # If switching TO interactive, sync regions to params (or vice versa? usually regions take precedence)
            if is_interactive:
                self._on_region_changed()

    def _on_region_changed(self):
        """Update generator params when regions move (Interactive Mode)."""
        if self.mode_combobox.currentText() != self._MODE_INTERACTIVE:
            return

        if hasattr(self, "baseline_region"):
            min_x, max_x = self.baseline_region.getRegion()
            self.param_generator.set_params({"baseline_start": min_x, "baseline_end": max_x})

        if hasattr(self, "response_region"):
            min_x, max_x = self.response_region.getRegion()
            self.param_generator.set_params({"response_start": min_x, "response_end": max_x})

        # Trigger analysis (debounce handled by base class)
        self._on_param_changed()

    def _on_param_changed(self):
        """Handle parameter changes (Override to sync regions in Manual Mode)."""
        # Sync regions if in Manual mode
        if hasattr(self, "mode_combobox") and self.mode_combobox.currentText() == self._MODE_MANUAL:
            if hasattr(self, "param_generator"):
                params = self.param_generator.gather_params()
                if hasattr(self, "baseline_region"):
                    self.baseline_region.setRegion([params.get("baseline_start", 0), params.get("baseline_end", 0.1)])
                if hasattr(self, "response_region"):
                    self.response_region.setRegion([params.get("response_start", 0.3), params.get("response_end", 0.4)])

        # Call base class to trigger debounce
        super()._on_param_changed()

    def _on_channel_changed(self):
        """Handle channel selection change to update UI for clamp mode."""
        super()._on_channel_changed()
        self._update_ui_for_clamp_mode()
        
    def _update_ui_for_clamp_mode(self):
        """Show/Hide parameters based on Current Clamp vs Voltage Clamp."""
        if not hasattr(self, "param_generator") or not self.param_generator.widgets:
            return

        # Determine mode from units
        is_voltage_clamp = False # Default to Current Clamp
        units = "V" # Default
        
        if self._selected_item_channel:
             units = self._selected_item_channel.units or "V"
             if "A" in units or "amp" in units.lower():
                 is_voltage_clamp = True
        
        # Identify widgets to toggle
        # Current Step Params (for Current Clamp)
        cc_widgets = ["pulse_amplitude_pa", "pulse_amplitude"] 
        # Voltage Step Params (for Voltage Clamp - if they existed in metadata)
        vc_widgets = ["pulse_amplitude_mv"] # Assuming this might exist or be mapped
        
        # If we reuse 'pulse_amplitude_pa' for both but just change label, that's easier.
        # But 'pa' is hardcoded. 
        # Let's assume metadata has 'pulse_amplitude_pa' and we rename it if Voltage Clamp?
        # Or if metadata has both?
        
        # Strategy: Rename label of 'pulse_amplitude_pa' to 'pulse_amplitude_mv' if V-Clamp?
        # And update unit label?
        
        widget = self.param_generator.widgets.get("pulse_amplitude_pa") or self.param_generator.widgets.get("pulse_amplitude")
        
        if widget:
            # helper to find label in FormLayout
            label_item = self.generated_params_layout.labelForField(widget)
            if label_item:
                if is_voltage_clamp:
                     label_item.setText("Voltage Step (mV):")
                     widget.setToolTip("Amplitude of the voltage step command (mV)")
                else:
                     label_item.setText("Current Step (pA):")
                     widget.setToolTip("Amplitude of the current step command (pA)")

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """Override to enforce mode-specific logic."""
        params = super()._gather_analysis_parameters()
        
        # If interactive, force auto_detect to False (we are manually setting regions)
        if hasattr(self, "mode_combobox") and self.mode_combobox.currentText() == self._MODE_INTERACTIVE:
            params["auto_detect_pulse"] = False
            
        return params

    def _ensure_custom_items_on_plot(self):
        """Re-add custom plot items if they were removed by plot_widget.clear()."""
        if not self.plot_widget:
            return

        # Regions
        if self.baseline_region and self.baseline_region not in self.plot_widget.items:
            self.plot_widget.addItem(self.baseline_region)
        if self.response_region and self.response_region not in self.plot_widget.items:
            self.plot_widget.addItem(self.response_region)

        # Lines
        if self.baseline_line and self.baseline_line not in self.plot_widget.items:
            self.plot_widget.addItem(self.baseline_line)
        if self.response_line and self.response_line not in self.plot_widget.items:
            self.plot_widget.addItem(self.response_line)

    def _on_data_plotted(self):
        """Re-add custom items after plot_widget.clear() in _plot_selected_data."""
        self._ensure_custom_items_on_plot()
        super()._on_data_plotted()

    def _plot_analysis_visualizations(self, results: Any):
        """Override to update result lines."""
        self._ensure_custom_items_on_plot()

        if isinstance(results, dict) and "result" in results:
            result_data = results["result"]
        else:
            result_data = results

        if not isinstance(result_data, dict):
            return

        # Update visualization lines
        if "baseline_voltage_mv" in result_data:
            self.baseline_line.setValue(result_data["baseline_voltage_mv"])
            self.baseline_line.setVisible(True)
        else:
            self.baseline_line.setVisible(False)

        if "steady_state_voltage_mv" in result_data:
            self.response_line.setValue(result_data["steady_state_voltage_mv"])
            self.response_line.setVisible(True)
        else:
            self.response_line.setVisible(False)


# Export the class for dynamic loading
ANALYSIS_TAB_CLASS = RinAnalysisTab
