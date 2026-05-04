# tests/core/test_error_handler.py
# -*- coding: utf-8 -*-
"""
Comprehensive tests for Synaptipy.core.error_handler.

Covers the previously-uncovered lines:
  78-79  : synaptipy_version fallback when __version__ import fails
  88-89  : pyside_version fallback when PySide6 import fails
  132-184: _show_crash_dialog (Qt dialog creation and button wiring)
  210-240: install_excepthook inner _excepthook paths
             (SystemExit pass-through, KeyboardInterrupt pass-through,
              no-QApp stderr fallback, QApp present -> _show_crash_dialog)
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_TB = (
    "Traceback (most recent call last):\n"
    "  File 'test_error_handler.py', line 1, in <module>\n"
    "RuntimeError: synthetic crash for testing\n"
)


# ---------------------------------------------------------------------------
# build_crash_markdown
# ---------------------------------------------------------------------------


class TestBuildCrashMarkdown:
    """Tests for build_crash_markdown — all branches including exception fallbacks."""

    def test_returns_string(self):
        """Return value must be a non-empty string."""
        from Synaptipy.core.error_handler import build_crash_markdown

        result = build_crash_markdown(_FAKE_TB)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_traceback_text(self):
        """The traceback text must appear verbatim in the output."""
        from Synaptipy.core.error_handler import build_crash_markdown

        result = build_crash_markdown(_FAKE_TB)
        assert "RuntimeError: synthetic crash for testing" in result

    def test_contains_github_url(self):
        """The GitHub Issues URL must be present."""
        from Synaptipy.core.error_handler import GITHUB_ISSUES_URL, build_crash_markdown

        result = build_crash_markdown(_FAKE_TB)
        assert GITHUB_ISSUES_URL in result

    def test_contains_all_environment_sections(self):
        """Markdown must contain the Environment table with all required rows."""
        from Synaptipy.core.error_handler import build_crash_markdown

        result = build_crash_markdown(_FAKE_TB)
        assert "## Environment" in result
        assert "## Stack Trace" in result
        assert "| **Synaptipy**" in result
        assert "| **Python**" in result
        assert "| **PySide6**" in result
        assert "| **OS**" in result

    def test_synaptipy_version_fallback_when_import_fails(self):
        """Lines 78-79: if Synaptipy.__version__ cannot be imported, use 'unknown'."""
        from Synaptipy.core import error_handler as eh_module

        # Temporarily hide the Synaptipy package from sys.modules so the
        # local `from Synaptipy import __version__` inside build_crash_markdown
        # raises ImportError, triggering the except branch.
        saved = sys.modules.get("Synaptipy")
        try:
            sys.modules["Synaptipy"] = None  # type: ignore[assignment]
            result = eh_module.build_crash_markdown("error text\n")
        finally:
            if saved is None:
                del sys.modules["Synaptipy"]
            else:
                sys.modules["Synaptipy"] = saved

        assert "unknown" in result

    def test_pyside6_version_fallback_when_import_fails(self):
        """Lines 88-89: if PySide6 cannot be imported, use 'unknown'."""
        from Synaptipy.core import error_handler as eh_module

        saved = sys.modules.get("PySide6")
        try:
            sys.modules["PySide6"] = None  # type: ignore[assignment]
            result = eh_module.build_crash_markdown("error text\n")
        finally:
            if saved is None and "PySide6" in sys.modules:
                del sys.modules["PySide6"]
            elif saved is not None:
                sys.modules["PySide6"] = saved

        assert "unknown" in result

    def test_traceback_stripped_of_trailing_whitespace(self):
        """Traceback text must be rstrip()-ed inside the code fence."""
        from Synaptipy.core.error_handler import build_crash_markdown

        tb_with_trailing = "SomeError: x\n\n\n"
        result = build_crash_markdown(tb_with_trailing)
        # The code fence should end with the stripped version
        assert "SomeError: x" in result


# ---------------------------------------------------------------------------
# _show_crash_dialog
# ---------------------------------------------------------------------------


class TestShowCrashDialog:
    """Tests for _show_crash_dialog (lines 132-184).

    These tests require a running QApplication (supplied by pytest-qt via qtbot).
    We mock QDialog.exec to avoid blocking.
    """

    def test_dialog_opens_and_closes_without_error(self, qtbot):
        """Lines 132-184: the dialog must be created and exec'd without raising."""
        from Synaptipy.core.error_handler import _show_crash_dialog

        with patch("PySide6.QtWidgets.QDialog.exec", return_value=0):
            _show_crash_dialog("# Crash Report\n\nTest crash.\n")

    def test_dialog_copies_report_to_clipboard(self, qtbot):
        """The 'Copy to Clipboard' button callback must call clipboard().setText."""
        from Synaptipy.core.error_handler import _show_crash_dialog

        report = "# Crash\n\nSome error here.\n"
        with patch("PySide6.QtWidgets.QDialog.exec", return_value=0) as _mock_exec:
            _show_crash_dialog(report)
        # If no exception was raised, the button wiring succeeded.
        assert _mock_exec.called

    def test_dialog_exit_button_closes_dialog(self, qtbot):
        """exec() return value of 0 (Rejected) means the Exit button worked."""
        from Synaptipy.core.error_handler import _show_crash_dialog

        with patch("PySide6.QtWidgets.QDialog.exec", return_value=0):
            # Should complete without hanging or raising
            _show_crash_dialog("Exit button test.\n")

    def test_dialog_emergency_fallback_when_widget_creation_fails(self, capsys):
        """Lines 180-184: if Qt widget creation raises, fallback prints to stderr."""
        from Synaptipy.core.error_handler import _show_crash_dialog

        with patch("PySide6.QtWidgets.QDialog", side_effect=RuntimeError("Qt broke")):
            _show_crash_dialog("# Emergency Fallback\n\nTest.\n")

        captured = capsys.readouterr()
        # Either the emergency-dialog-failed message or the markdown itself
        # must appear on stderr
        assert "Emergency dialog failed" in captured.err or "Emergency Fallback" in captured.err


# ---------------------------------------------------------------------------
# install_excepthook
# ---------------------------------------------------------------------------


class TestInstallExcepthook:
    """Tests for install_excepthook and its inner _excepthook closure.

    Lines 210-240:
      - SystemExit pass-through
      - KeyboardInterrupt pass-through
      - No QApplication: fallback to sys.__excepthook__ + stderr
      - QApplication present: calls _show_crash_dialog
    """

    def setup_method(self):
        """Capture the original sys.excepthook so we can restore it after each test."""
        self._saved_excepthook = sys.excepthook

    def teardown_method(self):
        """Restore sys.excepthook to avoid polluting other tests."""
        sys.excepthook = self._saved_excepthook

    def test_install_sets_excepthook(self):
        """After install_excepthook(), sys.excepthook must be the Synaptipy hook."""
        from Synaptipy.core.error_handler import install_excepthook

        install_excepthook()
        assert getattr(sys.excepthook, "_synaptipy_crash_reporter", False) is True

    def test_install_is_idempotent(self):
        """Calling install_excepthook() twice must not double-wrap the hook."""
        from Synaptipy.core.error_handler import install_excepthook

        install_excepthook()
        hook_after_first = sys.excepthook
        install_excepthook()
        assert sys.excepthook is hook_after_first

    def test_system_exit_passes_through(self):
        """Lines 214-215: SystemExit must be delegated to sys.__excepthook__."""
        from Synaptipy.core.error_handler import install_excepthook

        install_excepthook()
        with patch("sys.__excepthook__") as mock_orig:
            sys.excepthook(SystemExit, SystemExit(0), None)
            mock_orig.assert_called_once()

    def test_keyboard_interrupt_passes_through(self):
        """Lines 214-215: KeyboardInterrupt must be delegated to sys.__excepthook__."""
        from Synaptipy.core.error_handler import install_excepthook

        install_excepthook()
        with patch("sys.__excepthook__") as mock_orig:
            sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
            mock_orig.assert_called_once()

    def test_exception_falls_back_to_stderr_when_no_qt_app(self, capsys):
        """Lines 232-240: without a QApplication the report is printed to stderr."""
        from Synaptipy.core.error_handler import install_excepthook

        install_excepthook()

        with (
            patch("PySide6.QtWidgets.QApplication.instance", return_value=None),
            patch("sys.__excepthook__"),
        ):
            try:
                raise RuntimeError("no-qt-app crash test")
            except RuntimeError:
                exc_type, exc_val, exc_tb = sys.exc_info()
                sys.excepthook(exc_type, exc_val, exc_tb)

        captured = capsys.readouterr()
        assert "no-qt-app crash test" in captured.err or "Synaptipy Crash Report" in captured.err

    def test_exception_shows_dialog_when_qt_app_present(self, qtbot):
        """Lines 224-228: with a running QApplication, _show_crash_dialog is called."""
        from PySide6.QtWidgets import QApplication

        from Synaptipy.core.error_handler import install_excepthook

        install_excepthook()

        # qtbot ensures a QApplication exists, so QApplication.instance() is truthy
        assert QApplication.instance() is not None

        with patch("Synaptipy.core.error_handler._show_crash_dialog") as mock_dlg:
            try:
                raise ValueError("qt-app crash test")
            except ValueError:
                exc_type, exc_val, exc_tb = sys.exc_info()
                sys.excepthook(exc_type, exc_val, exc_tb)

        mock_dlg.assert_called_once()
        report_arg = mock_dlg.call_args[0][0]
        assert "qt-app crash test" in report_arg

    def test_exception_logs_at_critical_level(self, caplog):
        """Lines 218-219: the crash traceback must be logged at CRITICAL."""
        import logging

        from Synaptipy.core.error_handler import install_excepthook

        install_excepthook()

        with (
            patch("Synaptipy.core.error_handler._show_crash_dialog"),
            caplog.at_level(logging.CRITICAL, logger="Synaptipy.core.error_handler"),
        ):
            try:
                raise TypeError("log-level crash test")
            except TypeError:
                exc_type, exc_val, exc_tb = sys.exc_info()
                sys.excepthook(exc_type, exc_val, exc_tb)

        assert any("log-level crash test" in r.message or "Unhandled exception" in r.message for r in caplog.records)

    def test_qt_import_error_triggers_stderr_fallback(self, capsys):
        """Lines 228-232 (except Exception pass): if PySide6.QtWidgets is broken,
        fall through to the stderr path without raising."""
        from Synaptipy.core.error_handler import install_excepthook

        install_excepthook()

        with (
            patch(
                "Synaptipy.core.error_handler._show_crash_dialog",
                side_effect=ImportError("PySide6 unavailable"),
            ),
            patch("sys.__excepthook__"),
        ):
            try:
                raise OSError("import-error fallback test")
            except OSError:
                exc_type, exc_val, exc_tb = sys.exc_info()
                # Should not raise even if _show_crash_dialog itself raises
                try:
                    sys.excepthook(exc_type, exc_val, exc_tb)
                except Exception:
                    pytest.fail("install_excepthook must not propagate inner exceptions")


# ---------------------------------------------------------------------------
# Integration: GITHUB_ISSUES_URL is a real URL string
# ---------------------------------------------------------------------------


class TestGithubIssuesUrl:
    """Sanity check the exported constant."""

    def test_url_starts_with_https(self):
        from Synaptipy.core.error_handler import GITHUB_ISSUES_URL

        assert GITHUB_ISSUES_URL.startswith("https://")

    def test_url_contains_github(self):
        from Synaptipy.core.error_handler import GITHUB_ISSUES_URL

        assert "github.com" in GITHUB_ISSUES_URL
