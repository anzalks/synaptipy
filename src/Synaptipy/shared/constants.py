# -*- coding: utf-8 -*-
"""Shared constants for the Synaptipy application."""

# Plotting Constants
DEFAULT_PLOT_PEN_WIDTH = 1
PLOT_COLORS = [
    (0, 0, 255),    # Blue
    (255, 0, 0),    # Red
    (0, 150, 0),    # Green
    (200, 0, 200),  # Magenta
    (0, 200, 200),  # Cyan
    (255, 128, 0),  # Orange
    (100, 100, 100),# Gray
    # Add more colors if needed
]
TRIAL_COLOR = (55, 126, 184)  # Blueish (similar to #377eb8)
AVERAGE_COLOR = (0, 0, 0)  # Black (#000000)
TRIAL_ALPHA = 100              # Alpha for overlaid trials (0-255)

# PyQtGraph Z-Ordering Constants (for layering plot elements)
Z_ORDER = {
    'grid': -1000,      # Grid lines should be behind everything
    'baseline': -500,   # Baseline lines behind data but above grid
    'data': 0,          # Data traces at default level
    'selection': 500,   # Selection indicators above data
    'annotation': 1000, # Annotations on top
}

# Downsampling Constants
DOWNSAMPLING_THRESHOLD = 100000 # Apply auto-downsampling if samples > this

# Pre-compute the file filter for reuse
# NEO_FILE_FILTER = get_neo_file_filter() # Removed as it is handled by NeoAdapter

# Make all constants available at the module level
__all__ = [
    'DEFAULT_PLOT_PEN_WIDTH',
    'PLOT_COLORS',
    'TRIAL_COLOR',
    'AVERAGE_COLOR',
    'TRIAL_ALPHA',
    'Z_ORDER',
    'DOWNSAMPLING_THRESHOLD',
    'APP_NAME',
    'SETTINGS_SECTION',
]

APP_NAME = "Synaptipy"
SETTINGS_SECTION = "Viewer"