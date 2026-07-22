# src/synaptipy/shared/__init__.py
"""Shared utilities for Synaptipy.

The package initializer intentionally imports only non-GUI modules. Styling and
plot factory helpers are loaded lazily via ``__getattr__`` so headless commands
such as ``python -m synaptipy --version`` and ``synaptipy-batch --help`` do not
import PySide6.
"""

from importlib import import_module
from typing import Any

from . import constants, error_handling, logging_config
from .constants import (
    AVERAGE_COLOR,
    DEFAULT_PLOT_PEN_WIDTH,
    PLOT_COLORS,
    TRIAL_ALPHA,
    TRIAL_COLOR,
    Z_ORDER,
)
from .error_handling import (
    ExportError,
    FileReadError,
    SynaptipyError,
    SynaptipyFileNotFoundError,
    UnsupportedFormatError,
)
from .logging_config import setup_logging

_LAZY_EXPORTS = {
    "apply_stylesheet": ("styling", "apply_stylesheet"),
    "configure_pyqtgraph_globally": ("styling", "configure_pyqtgraph_globally"),
    "configure_plot_widget": ("styling", "configure_plot_widget"),
    "get_trial_pen": ("styling", "get_trial_pen"),
    "get_average_pen": ("styling", "get_average_pen"),
    "get_baseline_pen": ("styling", "get_baseline_pen"),
    "get_response_pen": ("styling", "get_response_pen"),
    "get_grid_pen": ("styling", "get_grid_pen"),
    "style_button": ("styling", "style_button"),
    "style_label": ("styling", "style_label"),
    "style_result_display": ("styling", "style_result_display"),
    "style_info_label": ("styling", "style_info_label"),
    "style_error_message": ("styling", "style_error_message"),
    "get_system_theme_mode": ("styling", "get_system_theme_mode"),
    "SynaptipyPlotFactory": ("plot_factory", "SynaptipyPlotFactory"),
    "styling": ("styling", None),
    "plot_factory": ("plot_factory", None),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(f"{__name__}.{module_name}")
    value = module if attr_name is None else getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    "DEFAULT_PLOT_PEN_WIDTH",
    "PLOT_COLORS",
    "TRIAL_COLOR",
    "AVERAGE_COLOR",
    "TRIAL_ALPHA",
    "Z_ORDER",
    "apply_stylesheet",
    "configure_pyqtgraph_globally",
    "configure_plot_widget",
    "get_trial_pen",
    "get_average_pen",
    "get_baseline_pen",
    "get_response_pen",
    "get_grid_pen",
    "style_button",
    "style_label",
    "style_result_display",
    "style_info_label",
    "style_error_message",
    "get_system_theme_mode",
    "SynaptipyPlotFactory",
    "SynaptipyError",
    "FileReadError",
    "UnsupportedFormatError",
    "ExportError",
    "SynaptipyFileNotFoundError",
    "setup_logging",
    "constants",
    "error_handling",
    "logging_config",
    "styling",
    "plot_factory",
]
