# src/Synaptipy/core/analysis/__init__.py
"""
Synaptipy Analysis Sub-package.

Provides functions for analysing electrophysiology data represented
by the core data models.
"""
# Optionally expose key functions for easier import
from .basic_features import calculate_rmp
from .spike_analysis import detect_spikes_threshold

# Define what `from Synaptipy.core.analysis import *` imports (optional)
__all__ = [
    'calculate_rmp',
    'detect_spikes_threshold',
]