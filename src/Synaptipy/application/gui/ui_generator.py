# src/Synaptipy/application/gui/ui_generator.py
# -*- coding: utf-8 -*-
"""
Helper module to generate UI widgets from metadata parameters.
"""
import logging
from typing import Dict, Any, List, Optional
from PySide6 import QtWidgets, QtCore

log = logging.getLogger(__name__)


class ParameterWidgetGenerator:
    """
    Generates and manages widgets for analysis parameters based on metadata.
    """

    def __init__(self, parent_layout: QtWidgets.QFormLayout):
        """
        Initialize the generator.

        Args:
            parent_layout: The QFormLayout where widgets will be added.
        """
        self.layout = parent_layout
        self.widgets: Dict[str, QtWidgets.QWidget] = {}
        self.callbacks: List[callable] = []

    def generate_widgets(self, ui_params: List[Dict[str, Any]], callback: Optional[callable] = None):
        """
        Generate widgets for the given parameters.

        Args:
            ui_params: List of parameter definitions.
            callback: Optional function to call when a parameter changes.
        """
        self.clear_widgets()
        if callback:
            self.callbacks.append(callback)

        if not ui_params:
            self.layout.addRow(QtWidgets.QLabel("No parameters defined."))
            return

        for param in ui_params:
            self._create_widget_for_param(param)

    def clear_widgets(self):
        """Remove all generated widgets from the layout."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.widgets.clear()

    def _create_widget_for_param(self, param: Dict[str, Any]):
        """Create and add a widget for a single parameter."""
        name = param.get("name")
        label = param.get("label", name)
        param_type = param.get("type", "float")

        widget = None

        if param_type == "float":
            widget = QtWidgets.QDoubleSpinBox()
            # Use a very wide range by default to avoid restricting the user
            widget.setRange(param.get("min", -1e9), param.get("max", 1e9))
            widget.setDecimals(param.get("decimals", 4))
            widget.setValue(param.get("default", 0.0))
            widget.setSingleStep(10 ** (-param.get("decimals", 4)))
            widget.valueChanged.connect(self._on_param_changed)

        elif param_type == "int":
            widget = QtWidgets.QSpinBox()
            widget.setRange(int(param.get("min", -1e9)), int(param.get("max", 1e9)))
            widget.setValue(int(param.get("default", 0)))
            widget.valueChanged.connect(self._on_param_changed)

        elif param_type == "choice":
            widget = QtWidgets.QComboBox()
            widget.addItems(param.get("choices", []))
            default = param.get("default")
            if default:
                widget.setCurrentText(str(default))
            widget.currentTextChanged.connect(self._on_param_changed)

        elif param_type == "bool":
            widget = QtWidgets.QCheckBox()
            widget.setChecked(param.get("default", False))
            widget.stateChanged.connect(self._on_param_changed)

        else:
            log.warning(f"Unknown parameter type '{param_type}' for {name}")
            return

        self.layout.addRow(label, widget)
        self.widgets[name] = widget

    def _on_param_changed(self):
        """Trigger registered callbacks."""
        for cb in self.callbacks:
            cb()

    def gather_params(self) -> Dict[str, Any]:
        """Gather current values from all widgets."""
        params = {}
        for name, widget in self.widgets.items():
            if isinstance(widget, QtWidgets.QDoubleSpinBox) or isinstance(widget, QtWidgets.QSpinBox):
                params[name] = widget.value()
            elif isinstance(widget, QtWidgets.QComboBox):
                params[name] = widget.currentText()
            elif isinstance(widget, QtWidgets.QCheckBox):
                params[name] = widget.isChecked()
        return params

    def set_params(self, params: Dict[str, Any]):
        """Set widget values programmatically."""
        for name, value in params.items():
            if name in self.widgets:
                widget = self.widgets[name]
                if isinstance(widget, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
                    widget.setValue(value)
                elif isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentText(str(value))
                elif isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
