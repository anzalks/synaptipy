import gc
import os
import sys

import pytest


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
        from Synaptipy.shared.data_cache import DataCache

        DataCache.reset_instance()
        yield
        DataCache.reset_instance()
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

        from Synaptipy.application.gui.main_window import MainWindow

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
    from Synaptipy.infrastructure.file_readers import NeoAdapter

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
