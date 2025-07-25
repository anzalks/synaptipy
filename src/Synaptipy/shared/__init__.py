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

Author: Anzal
Email: anzal.ks@gmail.com
"""

import logging
from typing import Dict, Any, Optional

# Core shared modules
from . import constants
from . import error_handling
from . import logging_config
from . import styling
from . import plot_factory

# Import key classes and functions for easy access
from .constants import (
    DEFAULT_PLOT_PEN_WIDTH,
    PLOT_COLORS,
    TRIAL_COLOR,
    AVERAGE_COLOR,
    TRIAL_ALPHA,
    Z_ORDER,
    NEO_FILE_FILTER,
    get_neo_file_filter
)

from .styling import (
    get_current_theme_mode,
    set_theme_mode,
    toggle_theme_mode,
    apply_stylesheet,
    configure_pyqtgraph_globally,
    configure_plot_widget,
    get_trial_pen,
    get_average_pen,
    get_baseline_pen,
    get_response_pen,
    get_grid_pen,
    style_button,
    style_label,
    style_result_display,
    style_info_label,
    style_error_message,
    THEME,
    PLOT_COLORS as STYLING_PLOT_COLORS
)

from .plot_factory import (
    SynaptipyPlotFactory,
    create_analysis_plot,
    create_explorer_plot,
    configure_plot_safely
)

from .error_handling import (
    SynaptipyError,
    FileReadError,
    UnsupportedFormatError,
    ExportError,
    SynaptipyFileNotFoundError,
    handle_error,
    log_error
)

from .logging_config import setup_logging

# Make all important items available at package level
__all__ = [
    # Constants
    'DEFAULT_PLOT_PEN_WIDTH',
    'PLOT_COLORS',
    'TRIAL_COLOR', 
    'AVERAGE_COLOR',
    'TRIAL_ALPHA',
    'Z_ORDER',
    'NEO_FILE_FILTER',
    'get_neo_file_filter',
    
    # Styling
    'get_current_theme_mode',
    'set_theme_mode', 
    'toggle_theme_mode',
    'apply_stylesheet',
    'configure_pyqtgraph_globally',
    'configure_plot_widget',
    'get_trial_pen',
    'get_average_pen',
    'get_baseline_pen',
    'get_response_pen', 
    'get_grid_pen',
    'style_button',
    'style_label',
    'style_result_display',
    'style_info_label',
    'style_error_message',
    'THEME',
    'STYLING_PLOT_COLORS',
    
    # Plot Factory
    'SynaptipyPlotFactory',
    'create_analysis_plot',
    'create_explorer_plot', 
    'configure_plot_safely',
    
    # Error Handling
    'SynaptipyError',
    'FileReadError',
    'UnsupportedFormatError',
    'ExportError', 
    'SynaptipyFileNotFoundError',
    'handle_error',
    'log_error',
    
    # Logging
    'setup_logging',
    
    # Modules
    'constants',
    'error_handling',
    'logging_config', 
    'styling',
    'plot_factory'
]