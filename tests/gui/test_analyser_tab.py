import pytest
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from Synaptipy.application.gui.analyser_tab import AnalyserTab
from Synaptipy.infrastructure.file_readers import NeoAdapter


@pytest.fixture
def app(qapp):
    return qapp


@pytest.fixture
def mock_neo_adapter():
    adapter = MagicMock(spec=NeoAdapter)
    return adapter


def test_analyser_tab_init(qtbot, mock_neo_adapter, monkeypatch):
    """Test that AnalyserTab initializes without error."""
    # Prevent heavy pyqtgraph instantiation to avoid macOS SIGABRT in offscreen runner
    monkeypatch.setattr(AnalyserTab, "_load_analysis_tabs", MagicMock())
    tab = AnalyserTab(neo_adapter=mock_neo_adapter)
    qtbot.addWidget(tab)
    assert tab is not None
    assert isinstance(tab, QtWidgets.QWidget)
    assert tab.sub_tab_widget is not None
    # Verify batch analysis button exists
    assert hasattr(tab, "batch_analysis_btn")
    assert tab.batch_analysis_btn is not None
