import gc
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Throwaway QSettings location for the session; see _isolate_qsettings().
_TEST_SETTINGS_DIR: "str | None" = None


def _isolate_qsettings() -> None:
    """Point QSettings at a throwaway location for the whole test session.

    Without this the suite reads, and can overwrite, the developer's real
    application preferences.  Every call site in the application constructs
    ``QSettings(APP_NAME, ...)``, which resolves to
    ``HKEY_CURRENT_USER\\Software\\Synaptipy\\Viewer`` on Windows: a developer
    who has switched "Enable Custom Plugins" off in the app makes the
    plugin-discovery tests fail on their machine while CI, which has no stored
    preference, passes.  Tests must depend on the repository, never on the state
    of the machine running them.

    The redirect has to be done by substituting the class.  ``setDefaultFormat``
    does not reach the ``(organization, application)`` constructor, which always
    uses ``NativeFormat``, and ``setPath`` explicitly has no effect on the
    Windows registry.  Substituting here in ``pytest_configure`` means the
    replacement is in place before collection imports any application module,
    including those that bind the name via ``from PySide6.QtCore import
    QSettings``.
    """
    global _TEST_SETTINGS_DIR
    from PySide6 import QtCore

    real_settings_cls = QtCore.QSettings
    ini_format = real_settings_cls.Format.IniFormat
    _TEST_SETTINGS_DIR = tempfile.mkdtemp(prefix="synaptipy-test-settings-")
    settings_dir = _TEST_SETTINGS_DIR

    class IsolatedQSettings(real_settings_cls):
        """QSettings that keeps the app's named scopes in a temp INI file.

        Only storage moves.  ``organizationName()`` and ``applicationName()``
        still report the names the caller asked for, so tests asserting that a
        component reads the canonical namespace keep their meaning.
        """

        def __init__(self, *args, **kwargs):
            # Only the (organization, application) form needs redirecting; every
            # other form already names an explicit file or format.
            organization = application = ""
            redirected = False
            if args and isinstance(args[0], str) and not str(args[0]).endswith(".ini"):
                organization = args[0]
                application = args[1] if len(args) > 1 and isinstance(args[1], str) else ""
                path = os.path.join(settings_dir, f"{organization}-{application or 'default'}.ini")
                super().__init__(path, ini_format)
                redirected = True
            else:
                super().__init__(*args, **kwargs)
            self._isolated_names = (organization, application) if redirected else None

        def organizationName(self):
            names = getattr(self, "_isolated_names", None)
            return names[0] if names else super().organizationName()

        def applicationName(self):
            names = getattr(self, "_isolated_names", None)
            return names[1] if names else super().applicationName()

    QtCore.QSettings = IsolatedQSettings


def pytest_configure(config):
    """Apply GC settings before any fixture runs.

    Disable cyclic GC in offscreen mode.
    Python's GC can trigger tp_dealloc on PySide6 wrapper objects while
    Qt's own C++ destructor chain is still running, causing SIGBUS on
    macOS and access-violations on Windows.  With GC disabled, objects
    are only freed when their refcount hits zero -- deterministic and safe.

    Note: ViewBoxMenu crashes in offscreen mode are prevented upstream by
    passing enableMenu=False to addPlot() in SynaptipyPlotCanvas.add_plot()
    when QT_QPA_PLATFORM=offscreen.  This uses PyQtGraph's own API to skip
    ViewBoxMenu construction entirely -- no monkey-patching needed.
    """
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        gc.disable()

    _isolate_qsettings()


@pytest.fixture(autouse=True)
def _drain_qt_events_after_test():
    """Global per-test drain of the Qt posted-event queue (Win/Linux only).

    pyqtgraph queues internal deferred callbacks (range/layout recalculations,
    ViewBox geometry updates) during plot operations.  If those callbacks fire
    during C++ object construction in the next test (inside widget.addPlot /
    PlotItem.__init__) they dereference already-freed C++ pointers causing
    access-violations (Windows).

    macOS is excluded: pyqtgraph keeps live state in its AllViews registry
    and internal geometry caches via posted events between tests.  Draining
    those events globally corrupts the long-lived session-scoped widget state
    and causes later widget.clear() calls to segfault.
    On macOS the X-link unlink in _unlink_all_plots() and the correct
    widget.clear()-first order are the only mechanisms needed.
    """
    yield
    if sys.platform != "darwin":
        try:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.removePostedEvents(None, 0)
        except Exception:
            pass


def pytest_sessionfinish(session, exitstatus):
    """Force-exit after tests to prevent crashes during Python/Qt teardown.

    PySide6 + pyqtgraph leave C++ objects partially alive at session end.
    Normal process exit triggers Qt DLL_PROCESS_DETACH / CRT atexit cleanup
    that dereferences freed C++ pointers → crash on all platforms.

    - macOS/Linux: os._exit() calls libc _exit() which skips C++ destructors,
      atexit handlers and Python GC — safe on these platforms.
    - Windows: os._exit() calls ExitProcess() which fires DLL_PROCESS_DETACH
      on all loaded DLLs (including Qt) → access violation on freed Qt C++
      objects.  RtlExitUserProcess() still runs LdrShutdownProcess() and
      therefore also fires DLL_PROCESS_DETACH → same crash.
      kernel32.TerminateProcess() is the ONLY Windows API that truly bypasses
      DLL_PROCESS_DETACH (per MSDN: "does not run the DLL entry function with
      DLL_PROCESS_DETACH").  argtypes must be set explicitly: without them,
      ctypes defaults GetCurrentProcess() restype to c_int (32-bit), and the
      pseudo-handle −1 is truncated to 0xFFFFFFFF instead of the correct 64-bit
      0xFFFFFFFFFFFFFFFF, causing TerminateProcess to fail with
      ERROR_INVALID_HANDLE and fall through to a normal (crashing) exit.
      We pass the pseudo-handle as ctypes.c_void_p(-1) directly to avoid the
      GetCurrentProcess return-type issue entirely.
    """
    if _TEST_SETTINGS_DIR:
        shutil.rmtree(_TEST_SETTINGS_DIR, ignore_errors=True)

    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        if sys.platform == "win32":
            import ctypes

            # kernel32.TerminateProcess bypasses DLL_PROCESS_DETACH per MSDN.
            # Must set argtypes so the 64-bit pseudo-handle (-1) is not
            # truncated to 32-bit 0xFFFFFFFF by ctypes' default c_int behaviour.
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            kernel32.TerminateProcess.restype = ctypes.c_bool
            # -1 == pseudo-handle constant for current process (GetCurrentProcess)
            kernel32.TerminateProcess(ctypes.c_void_p(-1), int(exitstatus))
        else:
            os._exit(exitstatus)


# Remove .verify_venv from sys.path to prevent its Python 3.13 scipy
# from shadowing the conda environment's scipy (Python 3.11)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_verify_venv = os.path.join(_project_root, ".verify_venv")
sys.path[:] = [p for p in sys.path if not p.startswith(_verify_venv)]

# Also invalidate any cached scipy imports from the wrong path
for mod_name in list(sys.modules.keys()):
    if mod_name == "scipy" or mod_name.startswith("scipy."):
        mod = sys.modules[mod_name]
        if mod is not None and hasattr(mod, "__file__") and mod.__file__ and ".verify_venv" in mod.__file__:
            del sys.modules[mod_name]


def pytest_ignore_collect(collection_path, config):
    """
    Hook to ignore files/directories during collection.
    Explicitly ignore .DS_Store to prevent PermissionError on macOS.
    """
    if collection_path.name == ".DS_Store":
        return True
    if collection_path.name in [".git", ".idea", "__pycache__"]:
        return True
    return None


@pytest.fixture(autouse=True)
def reset_datacache():
    """Ensure DataCache singleton is reset between tests."""
    try:
        from synaptipy.shared.data_cache import DataCache

        DataCache.reset_instance()
        yield
        DataCache.reset_instance()
    except ImportError:
        yield


@pytest.fixture(autouse=True)
def reset_session_manager(request):
    """Reset SessionManager without importing Qt into non-GUI tests."""
    qt_fixtures = {"qtbot", "qapp", "main_window"}
    fixturenames = set(getattr(request, "fixturenames", ()))
    test_path = Path(str(getattr(request.node, "path", ""))).as_posix()
    is_gui_test = (
        bool(fixturenames & qt_fixtures)
        or "/gui/" in test_path
        or test_path.startswith("tests/gui/")
        or "synaptipy.application.session_manager" in sys.modules
    )
    if not is_gui_test:
        yield
        return

    try:
        from synaptipy.application.session_manager import SessionManager

        if hasattr(SessionManager, "_instance"):
            SessionManager._instance = None
        yield
        if hasattr(SessionManager, "_instance"):
            SessionManager._instance = None
    except ImportError:
        yield


# --- Fixtures for test_main_window.py ---


@pytest.fixture
def main_window(qtbot):
    """Create a MainWindow instance for testing with proper cleanup."""
    from unittest.mock import patch

    with patch("PySide6.QtWidgets.QFileDialog") as mock_dialog, patch("PySide6.QtWidgets.QMessageBox") as mock_msgbox:

        mock_dialog.return_value.exec.return_value = False
        mock_dialog.getSaveFileName.return_value = ("", "")
        mock_dialog.getOpenFileName.return_value = ("", "")
        mock_msgbox.critical.return_value = None
        mock_msgbox.warning.return_value = None
        mock_msgbox.information.return_value = None

        from synaptipy.application.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        qtbot.wait(100)

        yield window

        # Cleanup: stop background threads before widget destruction
        if hasattr(window, "data_loader_thread") and window.data_loader_thread:
            window.data_loader_thread.quit()
            window.data_loader_thread.wait(2000)

        window.close()
        from PySide6.QtWidgets import QApplication

        _app = QApplication.instance()
        if _app:
            _app.processEvents()
        window.deleteLater()
        try:
            from PySide6.QtTest import QTest

            QTest.qWait(50)
        except Exception:
            for _ in range(5):
                if _app:
                    _app.processEvents()


# --- Fixtures for test_neo_adapter.py ---


@pytest.fixture
def neo_adapter_instance():
    """Create a NeoAdapter instance for testing."""
    from synaptipy.infrastructure.file_readers import NeoAdapter

    return NeoAdapter()


@pytest.fixture
def sample_abf_path():
    """Path to a sample ABF file for testing."""
    from pathlib import Path

    # Look for sample files in the examples/data directory
    project_root = Path(__file__).parent.parent
    examples_dir = project_root / "examples" / "data"
    sample_files = list(examples_dir.glob("*.abf"))

    if sample_files:
        return sample_files[0]

    # Fallback: create a pytest skip if no sample file exists
    pytest.skip("No sample ABF file found in examples/data directory")
