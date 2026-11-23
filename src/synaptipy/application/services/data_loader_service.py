# src/synaptipy/application/services/data_loader_service.py
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
from typing import Any, Optional, Set

from PySide6 import QtCore

from synaptipy.application.gui.analysis_worker import AnalysisWorker

log = logging.getLogger(__name__)


class _LoadRelay(QtCore.QObject):
    """Main-thread QObject slot relay ensuring worker signals marshal onto DataLoaderService's thread."""

    def __init__(self, service: "DataLoaderService", token: int) -> None:
        super().__init__(service)
        self._service = service
        self._token = token

    @QtCore.Slot(object)
    def on_result(self, result: Any) -> None:
        self._service._handle_worker_result(self._token, result)

    @QtCore.Slot(tuple)
    def on_error(self, err: tuple) -> None:
        self._service._handle_worker_error(self._token, err)

    @QtCore.Slot()
    def on_finished(self) -> None:
        try:
            self._service._handle_worker_finished(self._token)
        finally:
            self._service._relays.discard(self)
            self.deleteLater()


class DataLoaderService(QtCore.QObject):
    """Service that loads :class:`~synaptipy.core.data_model.Recording` objects
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
                         returns a :class:`~synaptipy.core.data_model.Recording`
                         or ``None``.
            parent:      Optional Qt parent for memory-management purposes.
        """
        super().__init__(parent)
        self._neo_adapter = neo_adapter
        self._thread_pool = QtCore.QThreadPool()
        self._request_seq: int = 0
        self._active_token: int = 0
        self._current_emit_token: Optional[int] = None
        self._relays: Set[_LoadRelay] = set()
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

    def _emit_with_token(self, token: int, emit_fn: Any, *args: Any) -> None:
        """Emit a signal while exposing *token* on ``_current_emit_token``."""
        prev = self._current_emit_token
        self._current_emit_token = token
        try:
            emit_fn(*args)
        finally:
            self._current_emit_token = prev

    def _handle_worker_result(self, token: int, result: Any) -> None:
        if token != self._active_token:
            log.debug("DataLoaderService: ignoring stale load result (token=%d, active=%d)", token, self._active_token)
            return
        self._emit_with_token(token, self.recording_loaded.emit, result)

    def _handle_worker_error(self, token: int, err: tuple) -> None:
        if token != self._active_token:
            log.debug("DataLoaderService: ignoring stale load error (token=%d, active=%d)", token, self._active_token)
            return
        self._emit_with_token(token, self.load_failed.emit, err)

    def _handle_worker_finished(self, token: int) -> None:
        if token != self._active_token:
            log.debug("DataLoaderService: ignoring stale load finish (token=%d, active=%d)", token, self._active_token)
            return
        self._emit_with_token(token, self.load_finished.emit)

    def load_recording(self, path: Optional[Any], token: Optional[int] = None) -> int:
        """Submit an asynchronous load of the recording at *path*.

        Results are delivered through the :attr:`recording_loaded` /
        :attr:`load_failed` / :attr:`load_finished` signals rather than via a
        return value, so this method returns immediately.

        Args:
            path: File-system path understood by *neo_adapter*.  ``None`` or a
                  falsy value causes :attr:`recording_loaded` to be emitted with
                  ``None`` (no error, no thread spawned).
            token: Optional monotonic request identifier from the caller.
        """
        self._request_seq += 1
        req_token = token if token is not None else self._request_seq
        self._active_token = req_token

        if not path:
            # Emit immediately on the calling thread - no worker needed.
            self._emit_with_token(req_token, self.recording_loaded.emit, None)
            self._emit_with_token(req_token, self.load_finished.emit)
            return req_token

        def _load(p: Any):
            return self._neo_adapter.read_recording(p)

        relay = _LoadRelay(self, req_token)
        self._relays.add(relay)

        worker = AnalysisWorker(_load, path)
        worker.signals.result.connect(relay.on_result)
        worker.signals.error.connect(relay.on_error)
        worker.signals.finished.connect(relay.on_finished)

        log.debug("DataLoaderService: starting async load for %s (token=%d)", path, req_token)
        self._thread_pool.start(worker)
        return req_token

    def load_recording_direct(self, recording: Any, token: Optional[int] = None) -> int:
        """Emit a pre-loaded recording directly without spawning a background thread.

        Use this for in-memory recordings (e.g. synthetic multi-file averages)
        that do not need to be read from disk.

        Args:
            recording: A :class:`~synaptipy.core.data_model.Recording` instance
                       (or ``None``) to deliver to connected slots immediately.
            token: Optional monotonic request identifier from the caller.
        """
        self._request_seq += 1
        req_token = token if token is not None else self._request_seq
        self._active_token = req_token
        log.debug("DataLoaderService: emitting in-memory recording directly (token=%d).", req_token)
        self._emit_with_token(req_token, self.recording_loaded.emit, recording)
        self._emit_with_token(req_token, self.load_finished.emit)
        return req_token

    def wait_for_done(self) -> None:
        """Block until all pending load operations have completed.

        Intended for use in tests or shutdown sequences - do not call from the
        main GUI event loop.
        """
        self._thread_pool.waitForDone()
