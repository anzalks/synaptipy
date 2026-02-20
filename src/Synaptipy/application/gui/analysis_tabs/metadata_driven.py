# src/Synaptipy/application/gui/analysis_tabs/metadata_driven.py
# -*- coding: utf-8 -*-
"""
Generic Analysis Tab that generates its UI from metadata.

This module provides a generic implementation of BaseAnalysisTab that can
adapt to any registered analysis function by reading its metadata (ui_params)
from the AnalysisRegistry.
"""
import logging
from typing import Dict, Any, Optional
import numpy as np
from PySide6 import QtWidgets, QtCore

from Synaptipy.application.gui.analysis_tabs.base import BaseAnalysisTab
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


class MetadataDrivenAnalysisTab(BaseAnalysisTab):
    """
    A generic analysis tab that builds its UI from metadata.
    """

    def __init__(self, analysis_name: str, neo_adapter, settings_ref=None, parent=None):
        """
        Initialize the metadata-driven tab.

        Args:
            analysis_name: The name of the registered analysis function.
            neo_adapter: NeoAdapter instance.
            settings_ref: QSettings reference.
            parent: Parent widget.
        """
        self.analysis_name = analysis_name
        self.metadata = AnalysisRegistry.get_metadata(analysis_name)
        self.param_widgets: Dict[str, QtWidgets.QWidget] = {}
        self._popup_windows = []

        super().__init__(neo_adapter, settings_ref, parent)
        self._setup_ui()

    def get_registry_name(self) -> str:
        return self.analysis_name

    def get_display_name(self) -> str:
        # Use label from metadata if available, else format the name
        return self.metadata.get("label", self.analysis_name.replace("_", " ").title())

    def _setup_ui(self):
        """Setup the UI components dynamically based on metadata."""
        main_layout = QtWidgets.QHBoxLayout(self)

        # --- Create Splitter ---
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # --- Left Control Panel (wrapped in scroll area for small screens) ---
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMinimumWidth(250)

        control_panel = QtWidgets.QWidget()
        control_layout = QtWidgets.QVBoxLayout(control_panel)
        control_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Global controls container (will be populated by AnalyserTab)
        self.global_controls_layout = QtWidgets.QVBoxLayout()
        control_layout.addLayout(self.global_controls_layout)

        # Channel Selection & Data Source (Standard for all tabs)
        self._setup_data_selection_ui(control_layout)

        # --- Preprocessing Widget ---
        # Explicitly place it here (after Data Source, before Params)
        if self.preprocessing_widget:
            control_layout.addWidget(self.preprocessing_widget)
            self.preprocessing_widget.setVisible(True)

        # Parameters Group
        params_group = QtWidgets.QGroupBox("Parameters")
        # Use a VBoxLayout for the group to stack permanent and generated layouts
        params_group_layout = QtWidgets.QVBoxLayout(params_group)

        # 1. Permanent/Custom Controls Layout (Hook for subclasses)
        self.permanent_params_layout = QtWidgets.QFormLayout()
        params_group_layout.addLayout(self.permanent_params_layout)

        # Separator (Optional)
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        params_group_layout.addWidget(line)

        # 2. Generated Parameters Layout
        self.generated_params_layout = QtWidgets.QFormLayout()
        params_group_layout.addLayout(self.generated_params_layout)

        # Use ParameterWidgetGenerator on the GENERATED layout
        from Synaptipy.application.gui.ui_generator import ParameterWidgetGenerator

        self.param_generator = ParameterWidgetGenerator(self.generated_params_layout)

        ui_params = self.metadata.get("ui_params", [])
        self.param_generator.generate_widgets(ui_params, self._on_param_changed)

        # Hook for subclasses to add extra controls (e.g. Method Selector)
        # We pass the PERMANENT params layout so they are NOT deleted by generator updates
        self._setup_additional_controls(self.permanent_params_layout)

        # 3. Reset Button
        reset_btn = QtWidgets.QPushButton("Reset Parameters")
        reset_btn.setToolTip("Reset all parameters to default values")
        reset_btn.clicked.connect(self.reset_parameters)
        params_group_layout.addWidget(reset_btn)

        control_layout.addWidget(params_group)

        # Results Group
        results_group = QtWidgets.QGroupBox("Results")
        self.results_layout = QtWidgets.QFormLayout(results_group)
        self.results_labels: Dict[str, QtWidgets.QLabel] = {}

        # We don't know the result keys ahead of time, so we'll add them dynamically
        # or we could add a text area for generic output
        # self.results_text = QtWidgets.QTextEdit()
        # self.results_text.setReadOnly(True)
        # self.results_text.setMaximumHeight(150)
        # self.results_layout.addRow(self.results_text)

        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(2)
        self.results_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.results_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setMaximumHeight(200)
        self.results_layout.addRow(self.results_table)

        control_layout.addWidget(results_group)

        # Status Label
        self.status_label = QtWidgets.QLabel("Ready")
        control_layout.addWidget(self.status_label)

        # Save Button
        self._setup_save_button(control_layout)

        # Accumulation UI
        self._setup_accumulation_ui(control_layout)

        control_layout.addStretch()

        # Set the control panel as the scroll area widget
        scroll_area.setWidget(control_panel)

        # Add scroll area to splitter (instead of control_panel directly)
        splitter.addWidget(scroll_area)

        # --- Right Plot Area ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        self._setup_plot_area(plot_layout, stretch_factor=0)  # Stretch handled by splitter
        splitter.addWidget(plot_container)

        # Set Splitter Sizes (1/3 Left, 2/3 Right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        # Basic plot setup
        if self.plot_widget:
            self.plot_widget.showGrid(x=True, y=True)
            self._setup_custom_plot_items()

    def reset_parameters(self):
        """Reset generated parameters to defaults defined in metadata."""
        if hasattr(self, "param_generator") and self.metadata:
            ui_params = self.metadata.get("ui_params", [])
            # Re-generating widgets will reset them to defaults
            self.param_generator.generate_widgets(ui_params, self._on_param_changed)
            # Also notify any changes
            self._on_param_changed()

        # If subclass has custom logic for reset (e.g. RinTab logic), trigger it
        if hasattr(self, "_on_channel_changed"):
            # Re-apply mode logic
            self._on_channel_changed()

    def _setup_additional_controls(self, layout: QtWidgets.QFormLayout):
        """Hook for subclasses to add extra controls (e.g., method selector) to the Parameters form."""
        pass

    def _setup_custom_plot_items(self):
        """Hook for subclasses to add extra plot items (e.g., regions)."""
        pass

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Return the last analysis result for saving."""
        # For metadata-driven tabs, the result is usually a dictionary or object
        # If it's an object, we might need to convert it to a dict
        log.debug(
            f"{self.__class__.__name__}._get_specific_result_data: _last_analysis_result is None? "
            f"{self._last_analysis_result is None}"
        )
        if not self._last_analysis_result:
            log.warning(
                f"{self.__class__.__name__}._get_specific_result_data: returning None because "
                f"_last_analysis_result is falsy"
            )
            return None

        # Start with the result data
        if hasattr(self._last_analysis_result, "__dict__"):
            result = dict(self._last_analysis_result.__dict__)
        elif isinstance(self._last_analysis_result, dict):
            result = dict(self._last_analysis_result)  # Copy to avoid modifying original
        else:
            # Fallback for simple types
            result = {"result": self._last_analysis_result}

        # CRITICAL: Add data_source key which is required by _request_save_result
        if self.data_source_combobox and self.data_source_combobox.isEnabled():
            data_source = self.data_source_combobox.currentData()
            result["data_source"] = data_source

        return result

    def _update_ui_for_selected_item(self):
        """Update UI when a new item is selected."""
        # Base class handles population of channel/source combos now
        # We just need to ensure plot is cleared if nothing selected
        if not self._selected_item_recording:
            if self.plot_widget:
                self.plot_widget.clear()

        # Update visibility based on new item context
        self._update_parameter_visibility()

    def _on_channel_changed(self, index=None):
        """Handle channel selection change."""
        # Trigger visibility update (channel units might have changed)
        self._update_parameter_visibility()

        # BaseAnalysisTab._plot_selected_data calls _on_data_plotted hook.
        # We can trigger analysis there.
        pass

    def _update_parameter_visibility(self):
        """Calculate context and update parameter visibility."""
        if not hasattr(self, "param_generator"):
            return

        context = {}

        # 1. Determine Clamp Mode
        # Logic: If channel units contain 'A' (Amps), it's Voltage Clamp (measuring Current)
        # If channel units contain 'V' (Volts), it's Current Clamp (measuring Voltage)
        # Default to Current Clamp if unknown

        is_voltage_clamp = False

        if self.signal_channel_combobox:
            # Get channel name string
            channel_name = self.signal_channel_combobox.currentData()

            # Fetch channel object
            channel = None
            if (channel_name and self._selected_item_recording
                    and channel_name in self._selected_item_recording.channels):
                channel = self._selected_item_recording.channels[channel_name]

            if channel:
                units = channel.units or "V"
                if "A" in units or "amp" in units.lower():
                    is_voltage_clamp = True

        context["clamp_mode"] = "voltage_clamp" if is_voltage_clamp else "current_clamp"

        # Update generator
        self.param_generator.update_visibility(context)

    def _on_data_plotted(self):
        """Hook called after data is plotted."""
        # Trigger analysis when new data is plotted
        self._trigger_analysis()

    def _on_param_changed(self):
        """Handle parameter changes."""
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """Gather parameters from UI widgets."""
        return self.param_generator.gather_params()

    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the registered analysis function."""
        func = AnalysisRegistry.get_function(self.analysis_name)
        if not func:
            raise ValueError(f"Analysis function '{self.analysis_name}' not found.")

        # Prepare arguments
        # Most analysis functions expect (data, time, sampling_rate, **kwargs)
        # or similar. We need to be flexible or enforce a standard signature.
        # Synaptipy standard seems to be: func(data, time, sampling_rate, **params)

        voltage = data["data"]
        time = data["time"]
        fs = data["sampling_rate"]

        try:
            # Call the function
            results = func(voltage, time, fs, **params)

            # If results is a list (like spikes), wrap it?
            # Or if it's a dict, pass it through.
            if isinstance(results, list):
                return {"list_results": results}
            elif isinstance(results, dict):
                return results
            else:
                return {"result": results}

        except Exception as e:
            log.error(f"Analysis execution failed: {e}")
            raise

    def _display_analysis_results(self, results: Dict[str, Any]):  # noqa: C901
        """
        Display analysis results in text area.
        Implements abstract method from BaseAnalysisTab.
        """
        if not self.results_table:
            return

        try:
            # robust extraction of items
            items = []
            if isinstance(results, dict):
                items = list(results.items())
            elif hasattr(results, "__dict__"):
                items = [(k, v) for k, v in results.__dict__.items() if not k.startswith("_")]
            else:
                # Fallback
                items = [("Result", str(results))]

            # Filter out complex objects like arrays for the simple table view
            display_items = []
            for k, v in items:
                try:
                    # Sanitize Key
                    key_str = str(k).replace("_", " ").title()

                    # Sanitize Value
                    if isinstance(v, (np.ndarray, list, dict)) and not isinstance(v, (float, int, str, bool)):
                        # Skip large arrays or complex nested dicts in the summary table
                        # or show a summary string
                        if isinstance(v, (list, np.ndarray)):
                            val_str = f"{type(v).__name__} (len={len(v)})"
                        else:
                            val_str = str(type(v))
                    elif isinstance(v, float):
                        val_str = f"{v:.4g}"
                    else:
                        val_str = str(v)

                    display_items.append((key_str, val_str))
                except Exception as e:
                    log.warning(f"Skipping result item {k}: {e}")
                    continue

            self.results_table.setRowCount(len(display_items))
            self.results_table.setColumnCount(2)  # Ensure column count

            for row, (k, v) in enumerate(display_items):
                key_item = QtWidgets.QTableWidgetItem(k)
                val_item = QtWidgets.QTableWidgetItem(v)

                self.results_table.setItem(row, 0, key_item)
                self.results_table.setItem(row, 1, val_item)

        except Exception as e:
            log.error(f"Error displaying results: {e}")
            # Fallback to simple popup if table fails
            self.results_table.setRowCount(1)
            self.results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Error"))
            self.results_table.setItem(0, 1, QtWidgets.QTableWidgetItem("See Logs"))

# Export key class (But do NOT export ANALYSIS_TAB_CLASS as this class requires arguments)
# ANALYSIS_TAB_CLASS = MetadataDrivenAnalysisTab
