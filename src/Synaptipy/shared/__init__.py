# src/Synaptipy/shared/__init__.py
"""
Shared utilities and styling for the Synaptipy application.

This module contains:
- Styling constants and theme management
- Plot configuration utilities
- Common UI helper functions
- Logging configuration
- Error handling utilities
- Unified plot factory for Windows compatibility

Author: Anzal K Shahul
Email: anzal.ks@gmail.com
"""

import logging
from typing import Any, Dict, Optional

# Core shared modules
from . import constants, error_handling, logging_config, plot_factory, styling

# Import key classes and functions for easy access
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
from .plot_factory import SynaptipyPlotFactory, configure_plot_safely, create_analysis_plot, create_explorer_plot
from .styling import PLOT_COLORS as STYLING_PLOT_COLORS
from .styling import (
    apply_stylesheet,
    configure_plot_widget,
    configure_pyqtgraph_globally,
    get_average_pen,
    get_baseline_pen,
    get_grid_pen,
    get_response_pen,
    get_system_theme_mode,
    get_trial_pen,
    style_button,
    style_error_message,
    style_info_label,
    style_label,
    style_result_display,
)

# Make all important items available at package level
__all__ = [
    # Constants
    "DEFAULT_PLOT_PEN_WIDTH",
    "PLOT_COLORS",
    "TRIAL_COLOR",
    "AVERAGE_COLOR",
    "TRIAL_ALPHA",
    "Z_ORDER",
    # Styling
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
    "STYLING_PLOT_COLORS",
    # Plot Factory
    "SynaptipyPlotFactory",
    "create_analysis_plot",
    "create_explorer_plot",
    "configure_plot_safely",
    # Error Handling
    "SynaptipyError",
    "FileReadError",
    "UnsupportedFormatError",
    "ExportError",
    "SynaptipyFileNotFoundError",
    # Logging
    "setup_logging",
    # Modules
    "constants",
    "error_handling",
    "logging_config",
    "styling",
    "plot_factory",
]
