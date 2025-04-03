# -*- coding: utf-8 -*-
"""
File Readers Submodule for Synaptipy Infrastructure.

Contains adapters (primarily using the 'neo' library) for reading various
electrophysiology file formats and converting them into Synaptipy's
internal data models (Recording, Channel).
"""

# Expose available file reader adapters
from .neo_adapter import NeoAdapter

# Define the public API for this subpackage
__all__ = [
    'NeoAdapter',
]