from unittest.mock import MagicMock

import pytest
from PySide6 import QtWidgets

from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter


@pytest.fixture
def tab(qtbot, monkeypatch):
    neo_adapter = MagicMock(spec=NeoAdapter)
    # Prevent heavy pyqtgraph instantiation to avoid macOS SIGABRT in offscreen runner
    monkeypatch.setattr("Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock())
    # Use a real tab that inherits BaseAnalysisTab
    widget = MetadataDrivenAnalysisTab("spike_detection", neo_adapter)
    qtbot.addWidget(widget)
    return widget


def test_manual_trigger_shows_popup(tab, monkeypatch):
    """Test that manual call triggers popup."""
    # Mock data to be None
    tab._current_plot_data = None

    # Mock QMessageBox
    mock_warning = MagicMock()
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", mock_warning)

    # Call directly (manual)
    tab._trigger_analysis()

    # Assert popup shown
    mock_warning.assert_called_once()
    assert "No Data" in mock_warning.call_args[0][1]


def test_timer_trigger_suppresses_popup(tab, monkeypatch, qtbot):
    """Test that timer signal suppresses popup."""
    # Mock data to be None
    tab._current_plot_data = None

    # Mock QMessageBox
    mock_warning = MagicMock()
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", mock_warning)

    # We need to simulate the signal emission from the specific timer
    # We can connect the timer to the slot, then emit?
    # Or just use qtimer.timeout.emit()?

    # The tab has _analysis_debounce_timer
    timer = tab._analysis_debounce_timer

    # We can't easily "emit" from a QTimer in pytest-qt without starting it?
    # Actually, we can manually invoke the slot with the timer as sender.
    # But checking 'sender()' in python via direct call is tricky.
    # Best way: Actually start the timer with 0 interval and let event loop run.

    timer.setInterval(0)
    timer.setSingleShot(True)

    with qtbot.waitSignal(timer.timeout, timeout=1000):
        timer.start()

    # Wait for the slot to execute (it is connected to timeout)
    # The slot _trigger_analysis is connected in BaseAnalysisTab.__init__

    qtbot.wait(100)  # Give event loop time to process slot

    # Assert popup NOT shown
    mock_warning.assert_not_called()
