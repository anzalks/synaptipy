"""Shared constants for the Synaptipy application."""

# Dictionary of known neo IO classes and their typical extensions
# Simplified list for file dialog filter
NEO_READER_EXTENSIONS = {
    'Axon': ['*.abf'],
    'NeuroExplorer': ['*.nex'],
    'Spike2': ['*.smr', '*.smrx'],
    'BrainVision': ['*.vhdr'],
    'Plexon': ['*.plx'],
    'Blackrock': ['*.ns*', '*.nev'],
    'NWB': ['*.nwb'],
    'Intan': ['*.rhd', '*.rhs'],
    'SpikeGLX': ['*.bin'], # Note: Needs .meta file too
    'OpenEphys': ['*.continuous', '*.spikes', '*.events'],
    'OpenEphysBinary': ['*.oebin'],
    'Igor': ['*.ibw', '*.pxp'],
    'Ced': ['*.smr', '*.smrx'], # Duplicate of Spike2 often
    # Add more common ones as needed
    'All Supported': [] # Placeholder, will be populated
}

def get_neo_file_filter():
    """Generates a file filter string for QFileDialog based on NEO_READER_EXTENSIONS."""
    filters = []
    all_exts = set()

    for name, exts in NEO_READER_EXTENSIONS.items():
        if name != 'All Supported':
            display_exts = " ".join(exts)
            filters.append(f"{name} Files ({display_exts})")
            for ext in exts:
                all_exts.add(ext)

    # Add the 'All Supported' filter at the beginning
    all_supported_str = " ".join(sorted(list(all_exts)))
    filters.insert(0, f"All Supported Files ({all_supported_str})")

    return ";;".join(filters)

# Example: "All Supported Files (*.abf *.nex *.smr *.smrx);;Axon Files (*.abf);;NeuroExplorer Files (*.nex)"
NEO_FILE_FILTER = get_neo_file_filter()

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
# Plotting Colors (RGB 0-255)
TRIAL_COLOR = (55, 126, 184)  # Blueish (similar to #377eb8)
AVERAGE_COLOR = (0, 0, 0)      # Black
TRIAL_ALPHA = 100              # Alpha for overlaid trials (0-255, lower is more transparent)
# Downsampling Constants
DOWNSAMPLING_THRESHOLD = 100000 # Apply auto-downsampling if samples > this