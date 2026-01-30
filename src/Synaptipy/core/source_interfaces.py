# src/Synaptipy/core/source_interfaces.py
from typing import Protocol, Optional, Any, Dict

import numpy as np


class SourceHandle(Protocol):
    """
    Abstract interface for a data source (e.g., file on disk, network stream).
    Decouples the core domain from specific I/O libraries like Neo.
    """

    @property
    def source_identifier(self) -> str:
        """Returns a string identifier for the source (e.g., file path)."""
        ...

    def load_channel_data(
        self, channel_id: str, trial_index: int
    ) -> Optional[np.ndarray]:
        """Loads data for a specific channel and trial index."""
        ...

    def get_metadata(self) -> Dict[str, Any]:
        """Returns metadata associated with the source."""
        ...

    def close(self):
        """Release any underlying resources (e.g., file handles)."""
        ...
