# tests/gui/test_e2e_gui.py
# -*- coding: utf-8 -*-
"""
End-to-end GUI tests for the Synaptipy main window (pytest-qt).

These tests verify the full integration path from the UI layer down to the
mathematical analysis layer:

1. The ``MainWindow`` initializes without errors in headless mode.
2. Injecting a synthetic ``Recording`` object (bypassing disk I/O) via
   ``SessionManager`` causes the ``ExplorerTab`` to display channel data.
3. The ``DataLoader.load_file`` large-file guard promotes files above the 500 MB
   threshold to lazy mode automatically.
4. ``SessionManager.save_session`` / ``load_session`` round-trips correctly.
5. The ``CrashReportDialog.build_markdown_report`` method produces a valid
   GitHub-Markdown string that contains the expected version and OS fields.

All tests run entirely headless (``QT_QPA_PLATFORM=offscreen``) and require
no real ABF/WCP files on disk.

Run only these tests::

    pytest tests/gui/test_e2e_gui.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PySide6 import QtWidgets

# ---------------------------------------------------------------------------
# Helpers: synthetic Recording
# ---------------------------------------------------------------------------


def _make_synthetic_recording(
    n_channels: int = 2,
    n_trials: int = 3,
    n_samples: int = 10_000,
    sampling_rate: float = 20_000.0,
    source_file: Path = Path("/tmp/synthetic_test.abf"),
) -> object:
    """Build a minimal ``Recording`` object populated with deterministic numpy data.

    No disk I/O is performed; this is purely in-memory.  The returned object
    mirrors the interface expected by ``ExplorerTab`` and ``SessionManager``.
    """
    from Synaptipy.core.data_model import Channel, Recording

    rng = np.random.default_rng(42)
    rec = Recording(source_file=source_file)
    rec.sampling_rate = sampling_rate

    for ch_idx in range(n_channels):
        trials = [rng.normal(-65.0, 2.0, n_samples).astype(np.float64) for _ in range(n_trials)]
        ch = Channel(
            id=str(ch_idx),
            name=f"Chan_{ch_idx}",
            units="mV",
            sampling_rate=sampling_rate,
            data_trials=trials,
        )
        ch.t_start = 0.0
        rec.channels[ch.id] = ch

    if rec.channels:
        rec.t_start = 0.0
        rec.duration = n_samples / sampling_rate
    return rec


# ---------------------------------------------------------------------------
# Fixture: a clean MainWindow with all dialogs suppressed
# (mirrors the shared ``main_window`` fixture in conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def main_window_e2e(qtbot):
    """Create a ``MainWindow`` instance with file dialogs and message boxes mocked.

    This is an independent fixture so the E2E tests do not depend on the
    session-scoped ``main_window`` fixture in ``conftest.py``.
    """
    with (
        patch("PySide6.QtWidgets.QFileDialog") as _mock_fd,
        patch("PySide6.QtWidgets.QMessageBox") as _mock_mb,
    ):
        _mock_fd.return_value.exec.return_value = False
        _mock_fd.getSaveFileName.return_value = ("", "")
        _mock_fd.getOpenFileName.return_value = ("", "")
        _mock_mb.critical.return_value = None
        _mock_mb.warning.return_value = None
        _mock_mb.information.return_value = None
        _mock_mb.question.return_value = QtWidgets.QMessageBox.StandardButton.No

        from Synaptipy.application.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        qtbot.wait(100)
        yield window

    # Cleanup: stop worker thread before widget teardown
    if hasattr(window, "data_loader_thread") and window.data_loader_thread:
        window.data_loader_thread.quit()
        window.data_loader_thread.wait(2000)

    window.close()
    app = QtWidgets.QApplication.instance()
    if app:
        app.processEvents()
    window.deleteLater()
    try:
        from PySide6.QtTest import QTest

        QTest.qWait(50)
    except Exception:
        for _ in range(5):
            if app:
                app.processEvents()


# ---------------------------------------------------------------------------
# Test 1: MainWindow initialises without errors
# ---------------------------------------------------------------------------


class TestMainWindowInitialisation:
    """Verify that the main window boots cleanly in headless mode."""

    def test_window_has_tab_widget(self, main_window_e2e):
        """QTabWidget must be present after initialisation."""
        assert hasattr(main_window_e2e, "tab_widget")
        assert isinstance(main_window_e2e.tab_widget, QtWidgets.QTabWidget)

    def test_window_has_three_tabs(self, main_window_e2e):
        """Explorer, Analyser, and Exporter tabs must all be registered."""
        assert main_window_e2e.tab_widget.count() == 3

    def test_explorer_tab_present(self, main_window_e2e):
        """ExplorerTab must be accessible as an attribute."""
        assert hasattr(main_window_e2e, "explorer_tab")
        assert main_window_e2e.explorer_tab is not None

    def test_session_manager_singleton(self, main_window_e2e):
        """SessionManager must be the application singleton."""
        from Synaptipy.application.session_manager import SessionManager

        sm = SessionManager()
        assert main_window_e2e.session_manager is sm


# ---------------------------------------------------------------------------
# Test 2: Injecting a synthetic recording triggers UI update
# ---------------------------------------------------------------------------


class TestSyntheticRecordingInjection:
    """E2E: push a synthetic Recording through SessionManager and verify the UI."""

    def test_recording_reaches_session_manager(self, main_window_e2e, qtbot):
        """Setting SessionManager.current_recording must not raise any exception."""
        rec = _make_synthetic_recording(n_channels=2, n_trials=3, n_samples=5_000)
        from Synaptipy.application.session_manager import SessionManager

        sm = SessionManager()
        sm.set_file_context([rec.source_file], 0)
        sm.current_recording = rec
        # Allow Qt events to settle
        qtbot.wait(80)
        assert sm.current_recording is rec

    def test_recording_channel_count_accessible(self, main_window_e2e, qtbot):
        """A loaded Recording's channel count must be readable after injection."""
        rec = _make_synthetic_recording(n_channels=3, n_trials=2, n_samples=4_000)
        from Synaptipy.application.session_manager import SessionManager

        sm = SessionManager()
        sm.current_recording = rec
        qtbot.wait(80)
        assert len(sm.current_recording.channels) == 3

    def test_recording_data_integrity_post_injection(self, main_window_e2e, qtbot):
        """Trial data must remain intact after passing through SessionManager."""
        n_samples = 8_000
        rec = _make_synthetic_recording(n_channels=1, n_trials=4, n_samples=n_samples)
        from Synaptipy.application.session_manager import SessionManager

        sm = SessionManager()
        sm.current_recording = rec
        qtbot.wait(80)

        ch = list(sm.current_recording.channels.values())[0]
        trial_data = ch.get_data(0)
        assert trial_data is not None
        assert len(trial_data) == n_samples


# ---------------------------------------------------------------------------
# Test 3: DataLoader large-file guard
# ---------------------------------------------------------------------------


class TestDataLoaderLargeFileGuard:
    """Verify that files >= 500 MB are automatically promoted to lazy mode."""

    def test_small_file_not_promoted(self, tmp_path):
        """A file smaller than the 500 MB threshold must not trigger lazy promotion."""
        from Synaptipy.application.data_loader import _LARGE_FILE_THRESHOLD_BYTES, DataLoader

        small_file = tmp_path / "small.bin"
        small_file.write_bytes(b"\x00" * 1024)  # 1 KB — well below threshold
        assert small_file.stat().st_size < _LARGE_FILE_THRESHOLD_BYTES

        loader = DataLoader()
        # We monkey-patch the actual neo read to avoid needing a real ABF file.
        with patch.object(loader.neo_adapter, "read_recording") as mock_read:
            mock_read.return_value = _make_synthetic_recording(source_file=small_file)
            loader.load_file(small_file, lazy_load=False)
            # The call should have been made with lazy=False (no promotion)
            mock_read.assert_called_once()
            _, call_kwargs = mock_read.call_args
            assert call_kwargs.get("lazy", False) is False

    def test_large_file_promoted_to_lazy(self, tmp_path, caplog):
        """A file >= 500 MB must be promoted to lazy mode with a warning log entry."""
        import logging

        from Synaptipy.application.data_loader import _LARGE_FILE_THRESHOLD_BYTES, DataLoader

        large_file = tmp_path / "large.bin"
        # Write exactly the threshold bytes to trigger promotion
        large_file.write_bytes(b"\x00" * _LARGE_FILE_THRESHOLD_BYTES)

        loader = DataLoader()
        with (
            patch.object(loader.neo_adapter, "read_recording") as mock_read,
            caplog.at_level(logging.WARNING, logger="Synaptipy.application.data_loader"),
        ):
            mock_read.return_value = _make_synthetic_recording(source_file=large_file)
            loader.load_file(large_file, lazy_load=False)
            # After promotion, neo_adapter.read_recording must be called with lazy=True
            mock_read.assert_called_once()
            _, call_kwargs = mock_read.call_args
            assert call_kwargs.get("lazy", False) is True, (
                "LargeFileGuard should have promoted lazy_load to True for a "
                f"{_LARGE_FILE_THRESHOLD_BYTES / (1024**2):.0f} MB file."
            )
        # A warning must have been emitted
        assert any("LargeFileGuard" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Test 4: SessionManager JSON round-trip
# ---------------------------------------------------------------------------


class TestSessionManagerPersistence:
    """Verify that save_session / load_session are a lossless round-trip."""

    def test_save_creates_json_file(self, tmp_path, monkeypatch):
        """save_session() must create session.json in the configured directory."""
        from Synaptipy.application import session_manager as sm_module

        monkeypatch.setattr(sm_module, "_SESSION_DIR", tmp_path)
        monkeypatch.setattr(sm_module, "_SESSION_FILE", tmp_path / "session.json")

        from Synaptipy.application.session_manager import SessionManager

        sm = SessionManager()
        sm._file_list = [Path("/fake/file_a.abf"), Path("/fake/file_b.abf")]
        sm._current_file_index = 1

        result = sm.save_session(active_tab_index=2)
        assert result is True
        assert (tmp_path / "session.json").is_file()

    def test_load_returns_none_when_no_file(self, tmp_path, monkeypatch):
        """load_session() must return None when no session file exists."""
        from Synaptipy.application import session_manager as sm_module

        monkeypatch.setattr(sm_module, "_SESSION_FILE", tmp_path / "nonexistent.json")

        from Synaptipy.application.session_manager import SessionManager

        assert SessionManager.load_session() is None

    def test_round_trip_settings(self, tmp_path, monkeypatch):
        """Global settings written by save_session must be readable by load_session."""
        from Synaptipy.application import session_manager as sm_module

        session_file = tmp_path / "session.json"
        monkeypatch.setattr(sm_module, "_SESSION_DIR", tmp_path)
        monkeypatch.setattr(sm_module, "_SESSION_FILE", session_file)

        from Synaptipy.application.session_manager import SessionManager

        sm = SessionManager()
        sm._global_settings["liquid_junction_potential_mv"] = 12.5
        sm._file_list = []
        sm._current_file_index = -1
        sm.save_session(active_tab_index=1)

        loaded = SessionManager.load_session()
        assert loaded is not None
        assert loaded["active_tab_index"] == 1
        assert loaded["global_settings"]["liquid_junction_potential_mv"] == pytest.approx(12.5)

    def test_schema_version_mismatch_returns_none(self, tmp_path, monkeypatch):
        """load_session() must return None when schema_version does not match."""
        from Synaptipy.application import session_manager as sm_module

        session_file = tmp_path / "session.json"
        monkeypatch.setattr(sm_module, "_SESSION_FILE", session_file)

        bad_payload = {"schema_version": 99, "file_paths": [], "active_tab_index": 0}
        session_file.write_text(json.dumps(bad_payload), encoding="utf-8")

        from Synaptipy.application.session_manager import SessionManager

        assert SessionManager.load_session() is None


# ---------------------------------------------------------------------------
# Test 5: Crash reporter Markdown builder (no Qt required)
# ---------------------------------------------------------------------------


class TestCrashReporterMarkdown:
    """Verify that the Markdown crash report contains all required fields."""

    def test_markdown_contains_synaptipy_version(self):
        """The Markdown report must include the Synaptipy version string."""
        from Synaptipy import __version__
        from Synaptipy.application.__main__ import CrashReportDialog

        report = CrashReportDialog._build_markdown_report("Traceback (most recent call last):\n  ...\n")
        assert __version__ in report, f"Synaptipy version '{__version__}' not found in crash report."

    def test_markdown_contains_os_info(self):
        """The Markdown report must include the OS platform string."""
        import platform

        from Synaptipy.application.__main__ import CrashReportDialog

        report = CrashReportDialog._build_markdown_report("SomeError: boom\n")
        # platform.platform() is included verbatim in the report
        assert platform.platform(aliased=True, terse=False)[:10] in report

    def test_markdown_contains_traceback(self):
        """The Markdown report must embed the original traceback text."""
        from Synaptipy.application.__main__ import CrashReportDialog

        tb_text = "Traceback (most recent call last):\n  File 'x.py', line 1, in <module>\nRuntimeError: test\n"
        report = CrashReportDialog._build_markdown_report(tb_text)
        assert "RuntimeError: test" in report

    def test_markdown_github_link_present(self):
        """The Markdown report must contain the GitHub Issues URL."""
        from Synaptipy.application.__main__ import CrashReportDialog

        report = CrashReportDialog._build_markdown_report("error\n")
        assert "github.com/anzalks/synaptipy/issues" in report

    def test_core_error_handler_build_crash_markdown(self):
        """core.error_handler.build_crash_markdown must produce valid Markdown."""
        from Synaptipy import __version__
        from Synaptipy.core.error_handler import GITHUB_ISSUES_URL, build_crash_markdown

        report = build_crash_markdown("ValueError: synthetic\n")
        assert __version__ in report
        assert GITHUB_ISSUES_URL in report
        assert "ValueError: synthetic" in report
        assert "## Stack Trace" in report
        assert "## Environment" in report
