# -*- coding: utf-8 -*-
"""
Shared Kernel for Synaptipy.

Contains utilities, constants, custom exceptions, and other common code
used across different layers (Core, Infrastructure, Application) of the
Synaptipy package.
"""

# Expose custom exception classes for easier catching elsewhere
# The '.' here correctly refers to the 'error_handling.py' file
# within the SAME directory (the 'shared' package).
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
    # Exceptions are correctly listed here
    'SynaptipyError',
    'FileReadError',
    'UnsupportedFormatError',
    'ProcessingError',
    'PlottingError',
    'ExportError',
    # Add constants/utils here if explicitly exposed
]