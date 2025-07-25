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

# Neo File Constants
NEO_READER_EXTENSIONS = {
    'ABF': ['abf'],
    'AsciiSignal': ['txt', 'asc', 'csv'],
    'Axon': ['abf', 'dat'],
    'BlackRock': ['nev', 'ns1', 'ns2', 'ns3', 'ns4', 'ns5', 'ns6'],
    'Brainware': ['f32', 'stim'],
    'CED': ['smr', 'son'],
    'EEGLAB': ['set', 'fdt'],
    'EDF': ['edf', 'bdf'],
    'IGOR': ['ibw'],
    'IntanRHD': ['rhd'],
    'MatrixMarket': ['mtx'],
    'Matlab': ['mat'],
    'MEF': ['mef'],
    'NeoMatlab': ['mat'],
    'NEX': ['nex', 'nex5'],
    'NI': ['nev'],
    'NWB': ['nwb', 'h5'],
    'OpenEphys': ['continuous', 'spikes', 'events'],
    'OpenEphysBinary': ['dat'],
    'Plexon': ['plx', 'pl2'],
    'RawBinary': ['raw', 'bin'],
    'Spike2': ['smr'],
    'SpikegadgetsIO': ['rec'],
    'Tdt': ['tbk', 'tev', 'tsq'],
    'WinEdr': ['wcp', 'EDR'],
    'WinWcp': ['wcp']
}

def get_neo_file_filter():
    """
    Generate a file filter string for QFileDialog based on Neo supported formats.
    
    Returns:
        str: A formatted string for use in file dialogs
    """
    filter_parts = []
    all_extensions = []
    
    # Add individual format entries
    for format_name, extensions in NEO_READER_EXTENSIONS.items():
        ext_list = [f"*.{ext}" for ext in extensions]
        all_extensions.extend(ext_list)
        filter_parts.append(f"{format_name} Files ({' '.join(ext_list)})")
    
    # Add 'All Supported' entry at the beginning
    if all_extensions:
        all_extensions = sorted(set(all_extensions))  # Remove duplicates and sort
        filter_parts.insert(0, f"All Supported Formats ({' '.join(all_extensions)})")
    
    # Add 'All Files' entry at the end
    filter_parts.append("All Files (*)")
    
    # Join with ;; separator for Qt
    return ";;".join(filter_parts)

# Pre-compute the file filter for reuse
NEO_FILE_FILTER = get_neo_file_filter()

# Make all constants available at the module level
__all__ = [
    'DEFAULT_PLOT_PEN_WIDTH',
    'PLOT_COLORS',
    'TRIAL_COLOR',
    'AVERAGE_COLOR',
    'TRIAL_ALPHA',
    'Z_ORDER',
    'DOWNSAMPLING_THRESHOLD',
    'NEO_READER_EXTENSIONS',
    'get_neo_file_filter',
    'NEO_FILE_FILTER',
]