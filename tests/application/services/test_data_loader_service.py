# tests/application/services/test_data_loader_service.py
# -*- coding: utf-8 -*-
"""
Tests for DataLoaderService.

Verifies the async loading logic, signal emissions, and
thread_pool property without spawning real threads (workers are synchronised
with QThreadPool.waitForDone / qtbot.waitSignal).
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from synaptipy.application.services.data_loader_service import DataLoaderService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def neo_adapter():
    """Minimal mock that fakes read_recording."""
    adapter = MagicMock()
    return adapter


@pytest.fixture
def service(neo_adapter):
    """Return a DataLoaderService with a real QThreadPool."""
    svc = DataLoaderService(neo_adapter)
    yield svc
    # Drain any in-flight workers before teardown
    svc.wait_for_done()


# ---------------------------------------------------------------------------
# Structural / introspection tests
# ---------------------------------------------------------------------------


class TestDataLoaderServiceStructure:
    def test_has_signals(self, service):
        """Service exposes required Qt signals."""
        assert hasattr(service, "recording_loaded")
        assert hasattr(service, "load_failed")
        assert hasattr(service, "load_finished")

    def test_thread_pool_property(self, service):
        """thread_pool property returns a non-None QThreadPool."""
        from PySide6 import QtCore  # noqa: PLC0415

        assert service.thread_pool is not None
        assert isinstance(service.thread_pool, QtCore.QThreadPool)

    def test_wait_for_done_does_not_raise(self, service):
        """wait_for_done() can be called safely when no work is pending."""
        service.wait_for_done()  # should not raise


# ---------------------------------------------------------------------------
# Null-path fast-path tests (no threads spawned)
# ---------------------------------------------------------------------------


class TestNullPathFastPath:
    def test_none_path_emits_recording_loaded_none(self, service, qtbot):
        """load_recording(None) emits recording_loaded(None) synchronously."""
        received = []
        service.recording_loaded.connect(lambda r: received.append(r))

        service.load_recording(None)

        assert received == [None]

    def test_none_path_emits_load_finished(self, service, qtbot):
        """load_recording(None) also emits load_finished."""
        finished = []
        service.load_finished.connect(lambda: finished.append(True))

        service.load_recording(None)

        assert finished == [True]

    def test_empty_string_path_emits_recording_loaded_none(self, service, qtbot):
        """load_recording('') is treated as falsy and follows the fast-path."""
        received = []
        service.recording_loaded.connect(lambda r: received.append(r))

        service.load_recording("")

        assert received == [None]


# ---------------------------------------------------------------------------
# Async load - success path
# ---------------------------------------------------------------------------


class TestAsyncLoadSuccess:
    def test_load_recording_emits_result(self, service, neo_adapter, qtbot):
        """Successful load emits recording_loaded with the Recording object."""
        mock_recording = MagicMock()
        neo_adapter.read_recording.return_value = mock_recording

        with qtbot.waitSignal(service.recording_loaded, timeout=5000) as blocker:
            service.load_recording(Path("test.abf"))

        service.wait_for_done()
        assert blocker.args[0] is mock_recording

    def test_load_recording_emits_finished(self, service, neo_adapter, qtbot):
        """Successful load emits load_finished."""
        neo_adapter.read_recording.return_value = MagicMock()

        with qtbot.waitSignal(service.load_finished, timeout=5000):
            service.load_recording(Path("test.abf"))

        service.wait_for_done()

    def test_adapter_called_with_path(self, service, neo_adapter, qtbot):
        """neo_adapter.read_recording is called with the supplied path."""
        neo_adapter.read_recording.return_value = None
        path = Path("recording.abf")

        with qtbot.waitSignal(service.load_finished, timeout=5000):
            service.load_recording(path)

        service.wait_for_done()
        neo_adapter.read_recording.assert_called_once_with(path)


# ---------------------------------------------------------------------------
# Async load - error path
# ---------------------------------------------------------------------------


class TestAsyncLoadError:
    def test_exception_emits_load_failed(self, service, neo_adapter, qtbot):
        """If read_recording raises, load_failed is emitted with error info."""
        neo_adapter.read_recording.side_effect = OSError("disk error")

        with qtbot.waitSignal(service.load_failed, timeout=5000) as blocker:
            service.load_recording(Path("bad.abf"))

        service.wait_for_done()
        exctype, value, _ = blocker.args[0]
        assert issubclass(exctype, OSError)
        assert "disk error" in str(value)

    def test_exception_also_emits_finished(self, service, neo_adapter, qtbot):
        """load_finished is always emitted, even on error."""
        neo_adapter.read_recording.side_effect = RuntimeError("boom")

        with qtbot.waitSignal(service.load_finished, timeout=5000):
            service.load_recording(Path("bad.abf"))

        service.wait_for_done()
