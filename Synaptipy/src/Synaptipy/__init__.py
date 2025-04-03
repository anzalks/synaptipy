# -*- coding: utf-8 -*-
"""
Synaptipy: A multi-channel electrophysiology visualization and analysis toolkit.

This package provides tools for loading, visualizing, and exporting
electrophysiology data using the neo library and a Qt-based graphical interface.
"""

# PEP 396 style version marker
__version__ = "0.1.0"
__author__ = "Anzal KS" # Or your name/organization
__email__ = "anzalks@ncbs.res.in" # Or relevant contact
__license__ = "MIT" # Defined in the LICENSE file

# -*- coding: utf-8 -*-
"""
Shared Kernel for Synaptipy.

Contains utilities, constants, custom exceptions, and other common code
used across different layers (Core, Infrastructure, Application) of the
Synaptipy package.
"""

# Expose custom exception classes for easier catching elsewhere
from .error_handling import (
    SynaptipyError,
    FileReadError,
    UnsupportedFormatError,
    ProcessingError,
    PlottingError,
    ExportError
)

# Expose key constants or utilities if frequently needed directly
# Example: from .constants import PLOT_COLORS
# Example: from .utils import some_utility_function

# Define the public API for this subpackage
__all__ = [
    # Exceptions
    'SynaptipyError',
    'FileReadError',
    'UnsupportedFormatError',
    'ProcessingError',
    'PlottingError',
    'ExportError',
    # Add constants/utils here if explicitly exposed
]