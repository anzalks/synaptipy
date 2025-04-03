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
AVERAGE_COLOR = (0, 0, 0)      # Black
TRIAL_ALPHA = 100              # Alpha for overlaid trials (0-255)


# Downsampling Constants
DOWNSAMPLING_THRESHOLD = 100000 # Apply auto-downsampling if samples > this

# --- REMOVED NEO_READER_EXTENSIONS dictionary ---
# --- REMOVED get_neo_file_filter function ---
# --- REMOVED NEO_FILE_FILTER constant ---