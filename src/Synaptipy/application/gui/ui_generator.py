# src/Synaptipy/application/gui/ui_generator.py
# -*- coding: utf-8 -*-
"""
Helper module to generate UI widgets from metadata parameters.
"""
import logging
from typing import Any, Dict, List, Optional

from PySide6 import QtGui, QtWidgets

log = logging.getLogger(__name__)


class FlexibleDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    """
    A QDoubleSpinBox that allows truly free-form numeric entry.

    Standard QDoubleSpinBox rejects intermediate text states during editing
    (e.g. clearing the field, typing a lone "-", or entering more decimal
    places than `decimals`).  This subclass relaxes the validator so users
    can freely type a value and have it committed on focus-out / Enter.
    Adaptive decimal step-type is enabled so the arrow-key increment
    matches the magnitude of the current value.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStepType(QtWidgets.QAbstractSpinBox.StepType.AdaptiveDecimalStepType)

    # ------------------------------------------------------------------
    # Relax the validator so partial / intermediate text is not rejected
    # ------------------------------------------------------------------

    def validate(self, text: str, pos: int):
        """Allow empty, lone sign, or lone decimal point as intermediate states."""
        stripped = text.strip()
        if stripped in ("", "-", "+", ".", "-.", "+."):
            return (QtGui.QValidator.State.Intermediate, text, pos)
        return super().validate(text, pos)

    def fixup(self, text: str) -> str:
        """On invalid committed text keep the current value rather than snapping to minimum."""
        try:
            val = float(text)
            clamped = max(self.minimum(), min(self.maximum(), val))
            return f"{clamped:.{self.decimals()}f}"
        except (ValueError, TypeError):
            return f"{self.value():.{self.decimals()}f}"


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
        self.visibility_map: Dict[str, Dict[str, Any]] = {}

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
        if param.get("hidden", False):
            return

        name = param.get("name")
        label = param.get("label", name)
        param_type = param.get("type", "float")

        widget = None

        if param_type == "float":
            widget = FlexibleDoubleSpinBox()
            # Use a very wide range by default to avoid restricting the user
            widget.setRange(param.get("min", -1e9), param.get("max", 1e9))
            widget.setDecimals(param.get("decimals", 4))
            widget.setValue(param.get("default", 0.0))
            widget.valueChanged.connect(self._on_param_changed)

        elif param_type == "int":
            widget = QtWidgets.QSpinBox()
            widget.setRange(int(param.get("min", -1e9)), int(param.get("max", 1e9)))
            widget.setValue(int(param.get("default", 0)))
            widget.valueChanged.connect(self._on_param_changed)

        elif param_type == "choice" or param_type == "combo":
            widget = QtWidgets.QComboBox()
            # Handle both 'choices' and 'options' keys for flexibility
            items = param.get("choices") or param.get("options") or []
            widget.addItems(items)
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

        # Store visibility rule if present
        if "visible_when" in param:
            self.visibility_map[name] = {
                "widget": widget,
                # We might need to track the label widget too if we want to hide it
                "label": label if isinstance(label, QtWidgets.QWidget) else None,
                "rule": param["visible_when"],
            }

    def update_visibility(self, context: Dict[str, Any]):
        """
        Update widget visibility based on context.

        Args:
            context: Dictionary of current context variables
                     (e.g. ``{"clamp_mode": "voltage_clamp"}``).
                     In addition, the current values of all parameter
                     widgets are automatically merged in so that
                     ``visible_when: {param: "event_type", value: "Events"}``
                     works without extra plumbing.
        """
        # Augment fixed context with live widget values
        live_context: Dict[str, Any] = dict(context)
        for wname, w in self.widgets.items():
            if isinstance(w, QtWidgets.QComboBox):
                live_context[wname] = w.currentText()
            elif isinstance(w, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
                live_context[wname] = w.value()
            elif isinstance(w, QtWidgets.QCheckBox):
                live_context[wname] = w.isChecked()

        for name, info in self.visibility_map.items():
            rule = info["rule"]
            widget = info["widget"]

            # Support both "context" key (fixed context var) and "param" key
            # (another param widget's live value); "context" takes precedence.
            context_key = rule.get("context") or rule.get("param")
            expected_value = rule.get("value")

            if context_key and context_key in live_context:
                is_visible = live_context[context_key] == expected_value
            else:
                continue  # rule cannot be evaluated — leave as-is

            # Use FormLayout to hide the row (Label + Widget)
            if isinstance(self.layout, QtWidgets.QFormLayout):
                self.layout.setRowVisible(widget, is_visible)
            else:
                widget.setVisible(is_visible)
                if info["label"]:
                    info["label"].setVisible(is_visible)

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
