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

# Define the primary public API exposed directly by 'import Synaptipy'
# Usually just metadata for library packages.
__all__ = ['__version__', '__author__', '__email__', '__license__']

# Optional: Configure root logger basic settings if not done elsewhere
# import logging
# logging.getLogger(__name__).addHandler(logging.NullHandler())