# src/synaptipy/infrastructure/file_readers/neo_source_handle.py
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import neo
import numpy as np

from synaptipy.core.source_interfaces import SourceHandle

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

    @staticmethod
    def _extract_1d_channel_array(analog_signal: Any, ch_offset: int) -> Optional[np.ndarray]:
        """Materialize proxy if needed, select *ch_offset*, rescale real Neo signals to mV/pA, and flatten."""
        proxy_cls = getattr(getattr(neo, "io", None), "proxyobjects", None)
        proxy_type = getattr(proxy_cls, "AnalogSignalProxy", ()) if proxy_cls is not None else ()
        if proxy_type and isinstance(analog_signal, proxy_type):
            try:
                analog_signal = analog_signal.load(channel_indexes=[ch_offset])
                ch_offset = 0
            except TypeError:
                analog_signal = analog_signal.load()

        shape = getattr(analog_signal, "shape", ())
        n_cols = shape[1] if len(shape) > 1 else 1
        if n_cols <= ch_offset:
            return None

        col = analog_signal[:, ch_offset] if len(shape) > 1 else analog_signal
        col_mod = type(col).__module__
        if (col_mod.startswith("neo") or col_mod.startswith("quantities")) and hasattr(col, "rescale"):
            for target_unit in ("mV", "pA"):
                try:
                    return np.asarray(col.rescale(target_unit).magnitude, dtype=float).ravel()
                except ValueError:
                    continue
        if hasattr(col, "magnitude") and isinstance(col.magnitude, np.ndarray):
            return np.asarray(col.magnitude).ravel()
        return np.asarray(col).ravel()

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

        return self._extract_1d_channel_array(segment.analogsignals[sig_idx], ch_offset)

    def get_metadata(self) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        if self._block and hasattr(self._block, "annotations"):
            meta.update(self._block.annotations)
        return meta

    def close(self):
        if self._reader and hasattr(self._reader, "close"):
            self._reader.close()
