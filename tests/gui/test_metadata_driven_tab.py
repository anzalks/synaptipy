# tests/gui/test_metadata_driven_tab.py
import pytest
from PySide6 import QtWidgets
from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.core.analysis.registry import AnalysisRegistry
from unittest.mock import MagicMock


# Register a dummy analysis for testing - MOVED TO FIXTURE
def dummy_analysis_func(data, time, fs, **kwargs):
    return {"result": "success", "kwargs": kwargs}


@pytest.fixture
def registered_analysis():
    """Register the dummy analysis for the duration of the test."""
    # Register
    decorator = AnalysisRegistry.register(
        "test_analysis",
        label="Test Analysis",
        ui_params=[
            {"name": "param1", "type": "float", "default": 1.0, "label": "Param 1"},
            {"name": "param2", "type": "int", "default": 5, "label": "Param 2"},
            {"name": "param3", "type": "choice", "choices": ["A", "B"], "default": "A", "label": "Param 3"},
            {"name": "param4", "type": "bool", "default": True, "label": "Param 4"},
        ],
    )
    decorator(dummy_analysis_func)

    yield


@pytest.fixture
def test_tab(qtbot, registered_analysis, monkeypatch):
    neo_adapter = MagicMock()
    # Prevent heavy pyqtgraph instantiation to avoid macOS SIGABRT in offscreen runner
    monkeypatch.setattr("Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock())
    tab = MetadataDrivenAnalysisTab("test_analysis", neo_adapter)
    qtbot.addWidget(tab)
    return tab


def test_metadata_tab_creation(test_tab):
    """Test that the tab creates widgets based on metadata."""
    tab = test_tab

    # Check if widgets were created
    widgets = tab.param_generator.widgets
    assert "param1" in widgets
    assert "param2" in widgets
    assert "param3" in widgets
    assert "param4" in widgets

    # Check widget types
    assert isinstance(widgets["param1"], QtWidgets.QDoubleSpinBox)
    assert isinstance(widgets["param2"], QtWidgets.QSpinBox)
    assert isinstance(widgets["param3"], QtWidgets.QComboBox)
    assert isinstance(widgets["param4"], QtWidgets.QCheckBox)

    # Check default values
    assert widgets["param1"].value() == 1.0
    assert widgets["param2"].value() == 5
    assert widgets["param3"].currentText() == "A"
    assert widgets["param4"].isChecked() is True


def test_parameter_gathering(test_tab):
    """Test that parameters are correctly gathered from widgets."""
    tab = test_tab

    # Modify values
    widgets = tab.param_generator.widgets
    widgets["param1"].setValue(2.5)
    widgets["param2"].setValue(10)
    widgets["param3"].setCurrentText("B")
    widgets["param4"].setChecked(False)

    params = tab._gather_analysis_parameters()

    assert params["param1"] == 2.5
    assert params["param2"] == 10
    assert params["param3"] == "B"
    assert params["param4"] is False
