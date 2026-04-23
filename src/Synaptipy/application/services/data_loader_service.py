# src/Synaptipy/application/services/data_loader_service.py
# -*- coding: utf-8 -*-
"""
Asynchronous recording-loader service for analysis tabs.

Decouples the UI (BaseAnalysisTab and subclasses) from the concurrency model
by encapsulating all thread-pool and worker-state management in one place.
Consumers connect to :attr:`recording_loaded`, :attr:`load_failed`, and
:attr:`load_finished` instead of creating :class:`AnalysisWorker` objects
directly.
"""

import logging
from typing import Any, Optional

from PySide6 import QtCore

from Synaptipy.application.gui.analysis_worker import AnalysisWorker

log = logging.getLogger(__name__)


class DataLoaderService(QtCore.QObject):
    """Service that loads :class:`~Synaptipy.core.data_model.Recording` objects
    in background threads and notifies subscribers via Qt signals.

    Usage::

        service = DataLoaderService(neo_adapter, parent=self)
        service.recording_loaded.connect(self._on_load_success)
        service.load_failed.connect(self._on_load_error)
        service.load_finished.connect(self._on_load_finished)
        service.load_recording(path)

    The service owns a dedicated :class:`~PySide6.QtCore.QThreadPool` so that
    analysis-tab loading is isolated from the application-wide pool.
    """

    # Emitted with the loaded Recording (or None when path is empty/None).
    recording_loaded = QtCore.Signal(object)
    # Emitted with a (exctype, value, traceback_str) tuple on failure.
    load_failed = QtCore.Signal(tuple)
    # Emitted unconditionally when the worker finishes (success or error).
    load_finished = QtCore.Signal()

    def __init__(self, neo_adapter: Any, parent: Optional[QtCore.QObject] = None) -> None:
        """
        Initialise the service.

        Args:
            neo_adapter: An object with a ``read_recording(path)`` method that
                         returns a :class:`~Synaptipy.core.data_model.Recording`
                         or ``None``.
            parent:      Optional Qt parent for memory-management purposes.
        """
        super().__init__(parent)
        self._neo_adapter = neo_adapter
        self._thread_pool = QtCore.QThreadPool()
        log.debug(
            "DataLoaderService initialised (max threads: %d)",
            self._thread_pool.maxThreadCount(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def thread_pool(self) -> QtCore.QThreadPool:
        """Expose the internal thread pool for external introspection or testing."""
        return self._thread_pool

    def load_recording(self, path: Optional[Any]) -> None:
        """Submit an asynchronous load of the recording at *path*.

        Results are delivered through the :attr:`recording_loaded` /
        :attr:`load_failed` / :attr:`load_finished` signals rather than via a
        return value, so this method returns immediately.

        Args:
            path: File-system path understood by *neo_adapter*.  ``None`` or a
                  falsy value causes :attr:`recording_loaded` to be emitted with
                  ``None`` (no error, no thread spawned).
        """
        if not path:
            # Emit immediately on the calling thread - no worker needed.
            self.recording_loaded.emit(None)
            self.load_finished.emit()
            return

        def _load(p: Any):
            return self._neo_adapter.read_recording(p)

        worker = AnalysisWorker(_load, path)
        worker.signals.result.connect(self.recording_loaded)
        worker.signals.error.connect(self.load_failed)
        worker.signals.finished.connect(self.load_finished)

        log.debug("DataLoaderService: starting async load for %s", path)
        self._thread_pool.start(worker)

    def wait_for_done(self) -> None:
        """Block until all pending load operations have completed.

        Intended for use in tests or shutdown sequences - do not call from the
        main GUI event loop.
        """
        self._thread_pool.waitForDone()
