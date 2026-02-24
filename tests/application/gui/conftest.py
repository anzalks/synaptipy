"""
Fixtures for application/gui tests.
"""
import sys
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="module")
def main_window(qapp):
    """
    Create a MainWindow instance for testing with all dialogs mocked.

    Module-scoped to avoid repeated Qt object creation/destruction cycles
    that crash with PySide6 6.8+ in offscreen mode (PlotItem.ctrl is a
    parentless QWidget whose teardown corrupts global Qt state, causing
    the second MainWindow creation to crash at PlotItem.__init__:235).

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

        # Cleanup: stop background threads before widget destruction
        if hasattr(window, 'data_loader_thread') and window.data_loader_thread:
            window.data_loader_thread.quit()
            if not window.data_loader_thread.wait(2000):
                window.data_loader_thread.terminate()
                window.data_loader_thread.wait(1000)

        app = QApplication.instance()
        if app:
            app.processEvents()

        window.close()

        if app:
            app.processEvents()

        # Schedule C++ object deletion then wait for cascading child
        # deletions to complete (macOS/Windows need multiple event rounds).
        window.deleteLater()
        try:
            from PySide6.QtTest import QTest
            QTest.qWait(50)  # 50 ms: processes events continuously
        except Exception:
            for _ in range(5):
                if app:
                    app.processEvents()


@pytest.fixture(autouse=True)
def patch_viewbox_menu():
    """
    Patch pyqtgraph's ViewBoxMenu on macOS and Windows to prevent segfaults/
    access violations with PySide6 6.8+ in offscreen mode.

    The ViewBoxMenu is only the right-click context menu; it has no effect on
    viewRange(), setXRange(), setYRange() or any other state tested here.
    Linux (xvfb) handles this correctly so no patch is needed there.
    """
    if sys.platform in ('darwin', 'win32'):
        try:
            import pyqtgraph.graphicsItems.ViewBox.ViewBox as _vb_mod
            with patch.object(_vb_mod, 'ViewBoxMenu', MagicMock):
                yield
            return
        except (ImportError, AttributeError):
            pass
    yield
