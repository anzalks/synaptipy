# src/Synaptipy/shared/data_cache.py
# -*- coding: utf-8 -*-
"""
Data cache implementation for Synaptipy application.

This module provides a Singleton in-memory cache for Recording objects and
manages the 'Active Trace' state, serving as the Single Source of Truth
for the current analysis context.
"""
import logging
from pathlib import Path
from typing import Dict, Optional, Any, Tuple
from collections import OrderedDict
import threading
import numpy as np

from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)


class DataCache:
    """
    Singleton in-memory cache for Recording objects and Active Trace state.
    Enforces 'Single Source of Truth' for the current analysis context.
    
    Thread-safe Singleton implementation.
    """
    
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DataCache, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_size: int = 10):
        """
        Initialize the data cache.
        
        Args:
            max_size: Maximum number of recordings to cache (default: 10)
        """
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:
                return
            self.max_size = max_size
            self._cache: OrderedDict[Path, Recording] = OrderedDict()
            
            # Active Trace State (Single Source of Truth for Live Analysis)
            # Tuple: (data_array, sampling_rate, metadata_dict)
            self._active_trace: Optional[Tuple[np.ndarray, float, Dict[str, Any]]] = None
            
            self._initialized = True
            log.debug(f"Initialized DataCache Singleton with max_size={max_size}")

    @classmethod
    def get_instance(cls) -> 'DataCache':
        """Get the singleton instance."""
        if cls._instance is None:
            return cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance for testing purposes."""
        with cls._lock:
            cls._instance = None

    def get(self, path: Path) -> Optional[Recording]:
        """
        Retrieve a Recording object from the cache.

        Args:
            path: File path to look up

        Returns:
            Recording object if found, None otherwise
        """
        if not isinstance(path, Path):
            path = Path(path)

        with self._lock:
            if path in self._cache:
                # Move to end (most recently used)
                recording = self._cache.pop(path)
                self._cache[path] = recording
                log.debug(f"Cache hit for: {path.name}")
                return recording

        log.debug(f"Cache miss for: {path.name}")
        return None

    def put(self, path: Path, recording: Recording) -> None:
        """
        Store a Recording object in the cache.

        Args:
            path: File path to use as key
            recording: Recording object to cache
        """
        if not isinstance(path, Path):
            path = Path(path)

        if not isinstance(recording, Recording):
            log.warning(f"Attempted to cache non-Recording object: {type(recording)}")
            return

        with self._lock:
            # Remove existing entry if present
            if path in self._cache:
                del self._cache[path]

            # Add new entry
            self._cache[path] = recording

            # Evict oldest entries if cache is full
            while len(self._cache) > self.max_size:
                oldest_path, oldest_recording = self._cache.popitem(last=False)
                log.debug(f"Evicted from cache: {oldest_path.name}")
                # Clean up the evicted recording if needed
                self._cleanup_recording(oldest_recording)

        log.debug(f"Cached recording: {path.name} (cache size: {len(self._cache)}/{self.max_size})")

    def remove(self, path: Path) -> bool:
        """
        Remove a specific Recording from the cache.

        Args:
            path: File path to remove

        Returns:
            True if removed, False if not found
        """
        if not isinstance(path, Path):
            path = Path(path)

        with self._lock:
            if path in self._cache:
                recording = self._cache.pop(path)
                self._cleanup_recording(recording)
                log.debug(f"Removed from cache: {path.name}")
                return True

        return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            log.debug(f"Clearing cache ({len(self._cache)} entries)")
            for recording in self._cache.values():
                self._cleanup_recording(recording)
            self._cache.clear()
            self._active_trace = None

    def size(self) -> int:
        """Return the current number of cached recordings."""
        with self._lock:
            return len(self._cache)

    def is_full(self) -> bool:
        """Check if the cache is at maximum capacity."""
        with self._lock:
            return len(self._cache) >= self.max_size

    def contains(self, path: Path) -> bool:
        """Check if a path exists in the cache."""
        if not isinstance(path, Path):
            path = Path(path)
        with self._lock:
            return path in self._cache

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary containing cache statistics
        """
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "utilization": len(self._cache) / self.max_size if self.max_size > 0 else 0,
                "cached_files": [str(path) for path in self._cache.keys()],
            }

    # --- Active Trace Management (Single Source of Truth) ---

    def set_active_trace(self, data: np.ndarray, fs: float, metadata: Dict[str, Any] = None):
        """
        Update the currently active trace data.
        This is the "Source of Truth" for Live Analysis independent of the UI.
        
        Args:
            data: Numpy array of the trace data.
            fs: Sampling rate in Hz.
            metadata: Context metadata (e.g. channel_id, trial_index).
        """
        with self._lock:
            self._active_trace = (data, fs, metadata or {})
            # log.debug(f"Active trace updated in DataCache. Samples: {len(data)}, fs: {fs}")

    def get_active_trace(self) -> Optional[Tuple[np.ndarray, float, Dict[str, Any]]]:
        """
        Retrieve the currently active trace.
        
        Returns:
            Tuple (data, fs, metadata) or None if not set.
        """
        with self._lock:
            return self._active_trace

    def clear_active_trace(self):
        """Clear the active trace."""
        with self._lock:
            self._active_trace = None

    # --- Internal Cleanup ---

    def _cleanup_recording(self, recording: Recording) -> None:
        """
        Clean up a Recording object when it's evicted from cache.

        This method can be extended to perform any necessary cleanup
        operations on the Recording object.

        Args:
            recording: Recording object to clean up
        """
        try:
            # Clear any large data structures that might be held in memory
            if hasattr(recording, "channels"):
                for channel in recording.channels.values():
                    # Clear loaded data from channels
                    if hasattr(channel, "data_trials"):
                        channel.data_trials.clear()
                    # Clear any other cached data
                    if hasattr(channel, "current_data_trials"):
                        channel.current_data_trials.clear()

            # Clear neo objects if they're no longer needed
            if hasattr(recording, "neo_block"):
                recording.neo_block = None
            if hasattr(recording, "neo_reader"):
                recording.neo_reader = None

            log.debug(f"Cleaned up recording: {recording.source_file.name}")
        except Exception as e:
            log.warning(f"Error during recording cleanup: {e}")

    def __len__(self) -> int:
        """Return the number of cached recordings."""
        return len(self._cache)

    def __contains__(self, path: Path) -> bool:
        """Check if a path exists in the cache."""
        return self.contains(path)

    def __repr__(self) -> str:
        """Return a string representation of the cache."""
        with self._lock:
            return f"DataCache(size={len(self._cache)}/{self.max_size}, files={list(self._cache.keys())})"
