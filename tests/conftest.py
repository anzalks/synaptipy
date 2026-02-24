import sys
import os
import pytest
import gc
from unittest.mock import MagicMock, patch as mock_patch


@pytest.fixture(scope="session", autouse=True)
def patch_viewbox_menu_globally():
    """
    On macOS and Windows, PySide6 6.8+ crashes inside ViewBoxMenu.__init__
    when pyqtgraph plots are created in offscreen mode. This session-scoped
    fixture patches ViewBoxMenu to a MagicMock for the entire test session,
    guaranteeing it is active before any fixture or widget is constructed.

    ViewBoxMenu is only the right-click context menu; all plot state methods
    (viewRange, setXRange, setYRange, autoRange, etc.) live in ViewBox and
    are completely unaffected. Linux runs under xvfb-run and is fine.
    """
    if sys.platform in ('darwin', 'win32'):
        try:
            import pyqtgraph.graphicsItems.ViewBox.ViewBox as _vb_mod
            patcher = mock_patch.object(_vb_mod, 'ViewBoxMenu', MagicMock)
            patcher.start()
            yield
            patcher.stop()
            return
        except (ImportError, AttributeError):
            pass
    yield


def pytest_configure(config):
    """Disable garbage collection entirely during pytest headless mode to prevent mid-test PySide6 Abort trap 6."""
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        gc.disable()


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
