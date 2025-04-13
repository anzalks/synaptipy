# -*- coding: utf-8 -*-
"""
Core Domain Layer for Synaptipy.

Contains the fundamental business logic and data models representing
electrophysiology concepts, independent of UI or infrastructure details.
"""

# Expose the primary data model classes for easier import
from .data_model import Recording, Channel, Experiment

# Explicitly define the public API of this subpackage
__all__ = [
    'Recording',
    'Channel',
    'Experiment',
    # Add EventDetector, SignalProcessor here if/when they are implemented
    # and intended for direct use from outside the core layer.
]