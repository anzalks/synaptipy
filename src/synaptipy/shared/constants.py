# -*- coding: utf-8 -*-
"""Shared constants for the Synaptipy application."""

# Plotting Constants
DEFAULT_PLOT_PEN_WIDTH = 1
PLOT_COLORS = [
    (0, 0, 255),  # Blue
    (255, 0, 0),  # Red
    (0, 150, 0),  # Green
    (200, 0, 200),  # Magenta
    (0, 200, 200),  # Cyan
    (255, 128, 0),  # Orange
    (100, 100, 100),  # Gray
]

# Wong (2011) Nature Methods 8:441 — colorblind-safe palette.
# Distinguishable under protanopia, deuteranopia, and tritanopia.
COLORBLIND_SAFE_PALETTE = [
    (0, 0, 0),  # Black
    (230, 159, 0),  # Orange
    (86, 180, 233),  # Sky Blue
    (0, 158, 115),  # Bluish Green
    (240, 228, 66),  # Yellow
    (0, 114, 178),  # Blue
    (213, 94, 0),  # Vermillion
    (204, 121, 167),  # Reddish Purple
]

TRIAL_COLOR = (55, 126, 184)  # Blueish (similar to  #377eb8)
AVERAGE_COLOR = (0, 0, 0)  # Black (#000000)
TRIAL_ALPHA = 100  # Alpha for overlaid trials (0-255)

# PyQtGraph Z-Ordering Constants (for layering plot elements)
Z_ORDER = {
    "grid": -1000,  # Grid lines should be behind everything
    "baseline": -500,  # Baseline lines behind data but above grid
    "data": 0,  # Data traces at default level
    "selection": 500,  # Selection indicators above data
    "annotation": 1000,  # Annotations on top
}

# Downsampling Constants
DOWNSAMPLING_THRESHOLD = 100000  # Apply auto-downsampling if samples > this

# Pre-compute the file filter for reuse
# NEO_FILE_FILTER = get_neo_file_filter()  # Removed as it is handled by NeoAdapter

# Make all constants available at the module level
__all__ = [
    "DEFAULT_PLOT_PEN_WIDTH",
    "PLOT_COLORS",
    "COLORBLIND_SAFE_PALETTE",
    "TRIAL_COLOR",
    "AVERAGE_COLOR",
    "TRIAL_ALPHA",
    "Z_ORDER",
    "DOWNSAMPLING_THRESHOLD",
    "APP_NAME",
    "SETTINGS_SECTION",
]

APP_NAME = "Synaptipy"
SETTINGS_SECTION = "Viewer"
