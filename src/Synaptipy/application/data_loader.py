# src/Synaptipy/application/data_loader.py
# -*- coding: utf-8 -*-
"""
Background data loader for Synaptipy GUI application.

This module provides a Qt-based worker thread implementation for loading
electrophysiology files in the background, preventing UI freezing during
file I/O operations.
"""

import logging
from pathlib import Path

from PySide6 import QtCore

from Synaptipy.core.data_model import Recording

# Import from our package structure
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter
from Synaptipy.shared.data_cache import DataCache
from Synaptipy.shared.error_handling import SynaptipyError

log = logging.getLogger(__name__)

# Files larger than this threshold are automatically loaded in lazy (out-of-core)
# mode to prevent the application from exhausting system RAM.  Users can override
# this via the ``lazy_load`` parameter of :meth:`DataLoader.load_file`.
_LARGE_FILE_THRESHOLD_BYTES: int = 500 * 1024 * 1024  # 500 MB


class DataLoader(QtCore.QObject):
    """
    Qt-based worker for loading electrophysiology files in background threads.

    This class handles file loading operations in a separate thread to prevent
    UI freezing. It emits signals when data is ready or when errors occur.
    """

    # Qt signals
    data_ready = QtCore.Signal(object)  # Emits the loaded Recording object
    data_error = QtCore.Signal(str)  # Emits error message if loading fails
    loading_started = QtCore.Signal(str)  # Emits file path when loading starts
    loading_progress = QtCore.Signal(int)  # Emits progress percentage (0-100)

    def __init__(self, parent=None):
        """
        Initialize the DataLoader.

        Args:
            parent: Parent QObject for Qt object hierarchy
        """
        super().__init__(parent)
        log.debug("Initializing DataLoader...")

        # Initialize the NeoAdapter for file reading
        self.neo_adapter = NeoAdapter()

        # Initialize the data cache
        self.cache = DataCache.get_instance()
        log.debug("DataLoader initialization complete.")

    @staticmethod
    def _should_lazy_load(file_path: Path, lazy_load: bool) -> bool:
        """Return ``True`` when the file should be loaded lazily.

        Promotes *lazy_load* to ``True`` automatically for files whose size is
        at or above :data:`_LARGE_FILE_THRESHOLD_BYTES` (default 500 MB).
        """
        if lazy_load:
            return True
        try:
            file_size = Path(file_path).stat().st_size
            if file_size >= _LARGE_FILE_THRESHOLD_BYTES:
                log.warning(
                    "LargeFileGuard: file '%s' is %.1f MB (threshold %.0f MB). "
                    "Automatically switching to lazy (out-of-core) loading to "
                    "prevent OOM crash.",
                    Path(file_path).name,
                    file_size / (1024 * 1024),
                    _LARGE_FILE_THRESHOLD_BYTES / (1024 * 1024),
                )
                return True
        except OSError:
            pass  # Best-effort; fall back to caller's choice
        return False

    @QtCore.Slot(Path, bool)
    def load_file(self, file_path: Path, lazy_load: bool = False) -> None:  # noqa: C901
        """
        Load a file in the background thread.

        For files whose size exceeds ``_LARGE_FILE_THRESHOLD_BYTES`` (default
        500 MB), the loader automatically promotes to lazy (out-of-core) mode
        even when *lazy_load* is ``False``.  This prevents the application from
        exhausting system RAM on large recordings; the data is mapped into memory
        only on demand as the user navigates through channels and trials.

        Args:
            file_path: Path to the electrophysiology file to load.
            lazy_load: Whether to use lazy loading mode (default: False).
                       Automatically overridden to ``True`` for large files.
        """
        lazy_load = self._should_lazy_load(file_path, lazy_load)
        log.debug(f"Starting background load of file: {file_path} (lazy_load: {lazy_load})")

        try:
            # Emit signal that loading has started
            self.loading_started.emit(str(file_path))
            self.loading_progress.emit(10)

            # Validate file path
            if not isinstance(file_path, Path):
                file_path = Path(file_path)

            if not file_path.exists():
                error_msg = f"File not found: {file_path}"
                log.error(error_msg)
                self.data_error.emit(error_msg)
                return

            if not file_path.is_file():
                error_msg = f"Path is not a file: {file_path}"
                log.error(error_msg)
                self.data_error.emit(error_msg)
                return

            self.loading_progress.emit(20)

            # Check cache first
            cached_recording = self.cache.get(file_path)
            if cached_recording is not None:
                log.debug(f"Cache hit for: {file_path.name}")
                self.loading_progress.emit(100)
                self.data_ready.emit(cached_recording)
                return

            log.debug(f"Cache miss for: {file_path.name}")
            self.loading_progress.emit(30)

            # Load the recording using NeoAdapter
            log.debug(f"Calling neo_adapter.read_recording for: {file_path} (lazy: {lazy_load})")
            recording_data = self.neo_adapter.read_recording(file_path, lazy=lazy_load)

            self.loading_progress.emit(80)

            # Validate the loaded data
            if not isinstance(recording_data, Recording):
                error_msg = f"NeoAdapter returned invalid data type: {type(recording_data)}"
                log.error(error_msg)
                self.data_error.emit(error_msg)
                return

            if not recording_data.channels:
                error_msg = f"No channels found in file: {file_path}"
                log.error(error_msg)
                self.data_error.emit(error_msg)
                return

            self.loading_progress.emit(90)

            # Store in cache
            self.cache.put(file_path, recording_data)
            log.debug(f"Cached recording: {file_path.name}")

            self.loading_progress.emit(100)

            # Emit success signal with the loaded data
            log.debug(f"Successfully loaded file: {file_path} ({len(recording_data.channels)} channels)")
            self.data_ready.emit(recording_data)

        except SynaptipyError as e:
            # Handle known Synaptipy errors
            error_msg = f"Synaptipy error loading {file_path}: {e}"
            log.error(error_msg)
            self.data_error.emit(error_msg)

        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Unexpected error loading {file_path}: {e}"
            log.error(error_msg, exc_info=True)
            self.data_error.emit(error_msg)

        finally:
            # Ensure progress is complete
            self.loading_progress.emit(100)

    def cleanup(self) -> None:
        """
        Clean up resources when the loader is no longer needed.
        """
        log.debug("Cleaning up DataLoader...")
        # Clear the cache
        if hasattr(self, "cache"):
            self.cache.clear()
            log.debug("Cleared data cache")
