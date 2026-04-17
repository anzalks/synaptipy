# src/Synaptipy/infrastructure/file_readers/neo_source_handle.py
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import neo
import numpy as np

from Synaptipy.core.source_interfaces import SourceHandle

log = logging.getLogger(__name__)


class NeoSourceHandle(SourceHandle):
    """
    Concrete implementation of SourceHandle using Neo for file I/O.
    Wraps a neo.Block or a neo.io reader to provide on-demand data access.
    """

    def __init__(self, source_path: Path, block: Optional[neo.Block] = None, reader=None):
        self._source_path = source_path
        self._block = block
        self._reader = reader
        self._channel_map: Dict[str, Dict[str, int]] = {}

    @property
    def source_identifier(self) -> str:
        return str(self._source_path)

    def set_channel_map(self, channel_map: Dict[str, Any]):
        """
        Sets the mapping required to locate a channel's data within the Neo structure.
        Format: channel_id -> { 'signal_index': int, 'channel_offset': int }
        """
        self._channel_map = channel_map

    def load_channel_data(self, channel_id: str, trial_index: int) -> Optional[np.ndarray]:
        """
        Loads data using the Neo Block structure and the pre-computed channel map.
        """
        if not self._block:
            log.warning("NeoSourceHandle: No block loaded, cannot load data.")
            return None

        if trial_index < 0 or trial_index >= len(self._block.segments):
            log.warning(f"NeoSourceHandle: Trial index {trial_index} out of range.")
            return None

        segment = self._block.segments[trial_index]

        # Retrieve location info from map
        mapping = self._channel_map.get(channel_id)
        if not mapping:
            log.warning(f"NeoSourceHandle: No mapping found for channel '{channel_id}'.")
            return None

        sig_idx = mapping.get("signal_index")
        ch_offset = mapping.get("channel_offset", 0)

        if sig_idx is None or sig_idx >= len(segment.analogsignals):
            log.debug(f"NeoSourceHandle: Signal index {sig_idx} invalid for " f"segment {trial_index}.")
            return None

        analog_signal = segment.analogsignals[sig_idx]

        # Retrieve specific channel column
        if analog_signal.shape[1] > ch_offset:
            data = analog_signal[:, ch_offset]
            if hasattr(data, "magnitude"):
                return data.magnitude
            return np.array(data)

        return None

    def get_metadata(self) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        if self._block and hasattr(self._block, "annotations"):
            meta.update(self._block.annotations)
        return meta

    def close(self):
        if self._reader and hasattr(self._reader, "close"):
            self._reader.close()
