import sys
import os
import pytest
import gc


def pytest_configure(config):
    """Apply critical patches and GC settings before any fixture runs.

    1. Disable cyclic GC in offscreen mode.
       Python's GC can trigger tp_dealloc on PySide6 wrapper objects while
       Qt's own C++ destructor chain is still running, causing SIGBUS on
       macOS and access-violations on Windows.  With GC disabled, objects
       are only freed when their refcount hits zero -- deterministic and safe.

    2. Patch pyqtgraph's ViewBoxMenu with a minimal QMenu subclass.
       ViewBoxMenu.__init__ calls QShortcut/QAction APIs that crash PySide6
       in headless/offscreen mode (no real display platform).  We replace it
       with _SafeViewBoxMenu which:
         - Is a real QMenu subclass  → has proper C++ backing
         - Skips ViewBoxMenu's init  → never touches QShortcut/QAction
         - Is safely destructible    → Qt's C++ destructor works correctly
       MagicMock was used previously but has no C++ backing, so Qt's C++
       ViewBox destructor would SIGBUS  macOS / AV Windows when running
       widget.clear().
       This hook fires before any conftest fixture or widget is constructed.
    """
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        gc.disable()

    _install_safe_viewbox_menu()


def _install_safe_viewbox_menu():
    """Monkey-patch ViewBoxMenu in the pyqtgraph module namespace.

    Called once from pytest_configure (before any fixture / widget is created).
    Safe to call multiple times -- only patches if not already patched.
    """
    try:
        import pyqtgraph.graphicsItems.ViewBox.ViewBox as _vb_mod
        from PySide6.QtWidgets import QMenu

        if getattr(_vb_mod, '_synaptipy_menu_patched', False):
            return  # Already patched this session

        class _SafeViewBoxMenu(QMenu):
            """Minimal ViewBoxMenu for headless test mode.

            ViewBoxMenu inherits QMenu and on __init__ creates QShortcuts and
            QActions that require a real display platform -- PySide6 crashes
            in offscreen/CI mode.  This subclass inherits from QMenu directly
            (giving it proper C++ backing so Qt can safely destruct it) but
            skips all the problematic pyqtgraph setup.

            The right-click menu is irrelevant for automated tests.
            """
            def __init__(self, view):
                super().__init__()
                self.view = view  # pyqtgraph may read vb.menu.view

        _vb_mod.ViewBoxMenu = _SafeViewBoxMenu
        _vb_mod._synaptipy_menu_patched = True
    except Exception:
        pass  # Non-fatal: tests will crash on first plot if this fails


@pytest.fixture(autouse=True)
def _drain_qt_events_after_test():
    """Global per-test drain of the Qt posted-event queue (Win/Linux only).

    pyqtgraph queues internal deferred callbacks (range/layout recalculations,
    ViewBox geometry updates) during plot operations.  If those callbacks fire
    during C++ object construction in the next test (inside widget.addPlot /
    PlotItem.__init__) they dereference already-freed C++ pointers causing
    access-violations (Windows) or SIGBUS (macOS).

    removePostedEvents(None, 0) discards every pending posted event for every
    object without executing callbacks -- no re-entrancy risk, no side effects.

    macOS is excluded: pyqtgraph on macOS needs to process certain posted events
    as part of its own C++ ViewBox/PlotItem teardown sequence.  Discarding them
    leaves teardown incomplete and causes SIGBUS.  On macOS the signal
    disconnect inside clear_plots() is sufficient.
    """
    yield
    if sys.platform != 'darwin':
        try:
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.removePostedEvents(None, 0)
        except Exception:
            pass


def pytest_sessionfinish(session, exitstatus):
    """
    On macOS headless (offscreen), PySide6 and pyqtgraph frequently crash with Abort trap 6
    during the C++ garbage collection phase at the very end of the test session.
    A common workaround is to forcefully exit the process exactly after tests complete.
    """
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os._exit(exitstatus)


# Remove .verify_venv from sys.path to prevent its Python 3.13 scipy
# from shadowing the conda environment's scipy (Python 3.11)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_verify_venv = os.path.join(_project_root, '.verify_venv')
sys.path[:] = [p for p in sys.path if not p.startswith(_verify_venv)]

# Also invalidate any cached scipy imports from the wrong path
for mod_name in list(sys.modules.keys()):
    if mod_name == 'scipy' or mod_name.startswith('scipy.'):
        mod = sys.modules[mod_name]
        if mod is not None and hasattr(mod, '__file__') and mod.__file__ and '.verify_venv' in mod.__file__:
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

    with patch("PySide6.QtWidgets.QFileDialog") as mock_dialog, \
            patch("PySide6.QtWidgets.QMessageBox") as mock_msgbox:

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
        if hasattr(window, 'data_loader_thread') and window.data_loader_thread:
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
