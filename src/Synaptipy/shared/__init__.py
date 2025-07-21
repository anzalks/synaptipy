# -*- coding: utf-8 -*-
"""
Shared Kernel for Synaptipy.

Contains utilities, constants, custom exceptions, and other common code
used across different layers (Core, Infrastructure, Application) of the
Synaptipy package.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

# Expose custom exception classes for easier catching elsewhere
# The '.' here correctly refers to the 'error_handling.py' file
# within the SAME directory (the 'shared' package).
from .error_handling import (
    SynaptipyError,
    FileReadError,
    SynaptipyFileNotFoundError,
    UnsupportedFormatError,
    ProcessingError,
    PlottingError,
    ExportError
)

# Expose key constants and utilities for easier imports
from .constants import (
    PLOT_COLORS,
    TRIAL_COLOR,
    AVERAGE_COLOR,
    TRIAL_ALPHA,
    DEFAULT_PLOT_PEN_WIDTH,
    NEO_FILE_FILTER
)

# Import styling module components for easier access
from .styling import (
    apply_stylesheet,
    configure_plot_widget,
    get_trial_pen,
    get_average_pen,
    get_baseline_pen,
    get_response_pen,
    style_button,
    style_label,
    style_result_display,
    THEME,
    get_current_theme_mode,
    set_theme_mode,
    toggle_theme_mode
)

# Define the public API for this subpackage
__all__ = [
    # Exceptions
    'SynaptipyError',
    'FileReadError',
    'SynaptipyFileNotFoundError',
    'UnsupportedFormatError',
    'ProcessingError',
    'PlottingError',
    'ExportError',
    
    # Constants
    'PLOT_COLORS',
    'TRIAL_COLOR',
    'AVERAGE_COLOR',
    'TRIAL_ALPHA', 
    'DEFAULT_PLOT_PEN_WIDTH',
    'NEO_FILE_FILTER',
    
    # Styling utilities
    'apply_stylesheet',
    'configure_plot_widget',
    'get_trial_pen',
    'get_average_pen',
    'get_baseline_pen',
    'get_response_pen',
    'style_button',
    'style_label',
    'style_result_display',
    'THEME',
    'get_current_theme_mode',
    'set_theme_mode',
    'toggle_theme_mode'
]