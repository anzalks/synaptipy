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


def test_analyser_tab_init(app, mock_neo_adapter):
    """Test that AnalyserTab initializes without error."""
    tab = AnalyserTab(neo_adapter=mock_neo_adapter)
    assert tab is not None
    assert isinstance(tab, QtWidgets.QWidget)
    assert tab.sub_tab_widget is not None
    # Verify batch analysis button exists
    assert hasattr(tab, "batch_analysis_btn")
    assert tab.batch_analysis_btn is not None
