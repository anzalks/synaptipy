# tests/gui/test_metadata_driven_tab.py
from unittest.mock import MagicMock

import pytest
from PySide6 import QtWidgets

from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.application.gui.ui_generator import FlexibleDoubleSpinBox, ParameterWidgetGenerator
from Synaptipy.core.analysis.registry import AnalysisRegistry


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


# ---------------------------------------------------------------------------
# FlexibleDoubleSpinBox tests
# ---------------------------------------------------------------------------


def test_flexible_spinbox_is_subclass_of_double_spinbox(qtbot):
    """FlexibleDoubleSpinBox is-a QDoubleSpinBox (existing isinstance checks still pass)."""
    sb = FlexibleDoubleSpinBox()
    qtbot.addWidget(sb)
    assert isinstance(sb, QtWidgets.QDoubleSpinBox)


def test_flexible_spinbox_accepts_wide_range(qtbot):
    """FlexibleDoubleSpinBox accepts values well outside typical defaults."""
    sb = FlexibleDoubleSpinBox()
    qtbot.addWidget(sb)
    sb.setRange(-1e9, 1e9)
    sb.setDecimals(4)
    sb.setValue(12345.6789)
    assert abs(sb.value() - 12345.6789) < 0.001


def test_flexible_spinbox_allows_negative_entry(qtbot):
    """FlexibleDoubleSpinBox allows entering negative values freely."""
    sb = FlexibleDoubleSpinBox()
    qtbot.addWidget(sb)
    sb.setRange(-1e9, 1e9)
    sb.setValue(-999.5)
    assert sb.value() == pytest.approx(-999.5, abs=0.01)


def test_flexible_spinbox_adaptive_step(qtbot):
    """FlexibleDoubleSpinBox uses AdaptiveDecimalStepType (arrows scale with magnitude)."""
    sb = FlexibleDoubleSpinBox()
    qtbot.addWidget(sb)
    assert sb.stepType() == QtWidgets.QAbstractSpinBox.StepType.AdaptiveDecimalStepType


def test_generated_float_widget_is_flexible(qtbot):
    """ParameterWidgetGenerator creates FlexibleDoubleSpinBox for float params."""
    container = QtWidgets.QWidget()
    qtbot.addWidget(container)
    layout = QtWidgets.QFormLayout(container)
    gen = ParameterWidgetGenerator(layout)
    gen.generate_widgets(
        [{"name": "x", "type": "float", "default": 3.14, "label": "X"}],
        callback=None,
    )
    assert isinstance(gen.widgets["x"], FlexibleDoubleSpinBox)


# ---------------------------------------------------------------------------
# Param-based visibility tests
# ---------------------------------------------------------------------------


def test_param_based_visibility_in_generator(qtbot):
    """visible_when with 'param' key hides/shows dependent widgets correctly."""
    container = QtWidgets.QWidget()
    qtbot.addWidget(container)
    layout = QtWidgets.QFormLayout(container)
    gen = ParameterWidgetGenerator(layout)
    gen.generate_widgets(
        [
            {
                "name": "mode",
                "type": "choice",
                "choices": ["A", "B"],
                "default": "A",
                "label": "Mode",
            },
            {
                "name": "only_in_b",
                "type": "float",
                "default": 1.0,
                "label": "B Only",
                "visible_when": {"param": "mode", "value": "B"},
            },
        ],
        callback=None,
    )

    # Initially mode == "A" → "only_in_b" row should be hidden
    gen.update_visibility({})
    assert layout.isRowVisible(gen.widgets["only_in_b"]) is False

    # Switch mode to "B"
    gen.widgets["mode"].setCurrentText("B")
    gen.update_visibility({})
    assert layout.isRowVisible(gen.widgets["only_in_b"]) is True


# ---------------------------------------------------------------------------
# Interactive mode spinbox disabling
# ---------------------------------------------------------------------------


@pytest.fixture
def rin_analysis_registered():
    """Ensure rin_analysis is registered (it is by default via imports)."""
    # The rin_analysis is registered in intrinsic_properties via the @register decorator.
    # Importing the module is enough.
    import Synaptipy.core.analysis.intrinsic_properties  # noqa: F401

    yield


@pytest.fixture
def rin_tab(qtbot, rin_analysis_registered, monkeypatch):
    monkeypatch.setattr("Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock())
    neo_adapter = MagicMock()
    tab = MetadataDrivenAnalysisTab("rin_analysis", neo_adapter)
    qtbot.addWidget(tab)
    return tab


def test_interactive_mode_disables_spinboxes(rin_tab):
    """In Interactive mode, paired spinboxes become read-only."""
    tab = rin_tab
    if tab._region_mode_combo is None:
        pytest.skip("rin_analysis does not expose a region_mode_combo in this environment")

    # Switch to Interactive mode
    tab._region_mode_combo.setCurrentText("Interactive")
    tab._apply_region_mode()

    widgets = tab.param_generator.widgets
    for start_key, end_key in tab._region_spinbox_keys.items():
        for key in (start_key, end_key):
            w = widgets.get(key)
            if w is not None and hasattr(w, "isReadOnly"):
                assert w.isReadOnly(), f"Widget '{key}' should be read-only in Interactive mode"


def test_manual_mode_enables_spinboxes(rin_tab):
    """Switching back to Manual mode re-enables (makes writable) the spinboxes."""
    tab = rin_tab
    if tab._region_mode_combo is None:
        pytest.skip("rin_analysis does not expose a region_mode_combo in this environment")

    # First go Interactive, then Manual
    tab._region_mode_combo.setCurrentText("Interactive")
    tab._apply_region_mode()
    tab._region_mode_combo.setCurrentText("Manual")
    tab._apply_region_mode()

    widgets = tab.param_generator.widgets
    for start_key, end_key in tab._region_spinbox_keys.items():
        for key in (start_key, end_key):
            w = widgets.get(key)
            if w is not None and hasattr(w, "isReadOnly"):
                assert not w.isReadOnly(), f"Widget '{key}' should be writable in Manual mode"
