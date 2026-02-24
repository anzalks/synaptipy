"""
Fixtures for application/gui tests.
"""
import sys
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def main_window(qtbot):
    """
    Create a MainWindow instance for testing with all dialogs mocked.

    This fixture creates a real MainWindow but patches all QFileDialog
    and QMessageBox calls to prevent blocking in headless mode.
    Includes robust cleanup to prevent segfaults during teardown.
    """
    # Patch all file dialogs and message boxes before importing MainWindow
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
        qtbot.addWidget(window)

        # Wait for initialization
        qtbot.wait(100)

        yield window

        # Cleanup: stop background threads before widget destruction
        if hasattr(window, 'data_loader_thread') and window.data_loader_thread:
            window.data_loader_thread.quit()
            if not window.data_loader_thread.wait(2000):
                window.data_loader_thread.terminate()
                window.data_loader_thread.wait(1000)

        # Process pending events before closing
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.processEvents()

        window.close()

        # Process events again after close
        if app:
            app.processEvents()

        # Schedule C++ object deletion and drain the event queue
        window.deleteLater()
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
