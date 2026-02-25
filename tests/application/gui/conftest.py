"""
Fixtures for application/gui tests.
"""
import pytest
from unittest.mock import patch


@pytest.fixture(scope="session")
def main_window(qapp):  # noqa: C901
    """
    Create a MainWindow instance for testing with all dialogs mocked.

    Session-scoped to avoid PlotItem teardown/recreation crashes with
    PySide6 6.8+ in offscreen mode.  scope="module" tears down between
    modules, corrupting Qt's global PlotItem registry for the next
    module that creates a PlotItem.  scope="session" defers teardown to
    session-end, which pytest_sessionfinish skips via os._exit(0).

    State modified by individual tests is reset by the reset_main_window_state
    autouse fixture defined in test_main_window.py.
    """
    with patch("PySide6.QtWidgets.QFileDialog") as mock_dialog, \
            patch("PySide6.QtWidgets.QMessageBox") as mock_msgbox:

        # Configure dialog to return cancel by default
        mock_dialog.return_value.exec.return_value = False
        mock_dialog.getSaveFileName.return_value = ("", "")
        mock_dialog.getOpenFileName.return_value = ("", "")

        # Configure message box
        mock_msgbox.critical.return_value = None
        mock_msgbox.warning.return_value = None
        mock_msgbox.information.return_value = None

        # Import and create MainWindow
        from Synaptipy.application.gui.main_window import MainWindow

        window = MainWindow()

        # Wait for initialization
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            for _ in range(5):
                app.processEvents()

        yield window
        # No teardown: session-end is handled by os._exit(0) in
        # pytest_sessionfinish (root conftest.py), which exits before any
        # Qt destructor runs and avoids the PlotItem dangling-pointer crash.


# ViewBoxMenu is patched globally in tests/conftest.py::pytest_configure
# (before any widget is created) with a real QMenu subclass that is safe
# to construct and destruct in headless/offscreen mode.  No per-test
# patching needed here.
