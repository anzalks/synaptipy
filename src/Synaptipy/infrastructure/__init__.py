# -*- coding: utf-8 -*-
"""
Infrastructure Layer for Synaptipy.

Handles interactions with external systems like the file system (reading/writing),
external libraries (neo, pynwb), and potentially databases or hardware interfaces.
"""

# It's often cleaner to import specific adapters/exporters directly from
# their subpackages (e.g., infrastructure.file_readers) rather than exposing
# them here.
__all__ = []
