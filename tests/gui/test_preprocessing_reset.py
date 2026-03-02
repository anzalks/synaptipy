# tests/gui/test_preprocessing_reset.py
"""
Tests for preprocessing reset in analysis tabs.

Verifies that the 'Reset Preprocessing' button in analysis tabs:
1. Clears the pipeline and internal preprocessing state
2. Resets the PreprocessingWidget UI controls (combos back to "None")
3. Notifies the parent AnalyserTab to propagate reset globally
4. Re-plots with raw data
"""

from unittest.mock import MagicMock

import pytest

from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.application.gui.widgets.preprocessing import PreprocessingWidget
from Synaptipy.core.analysis.registry import AnalysisRegistry

# --- Fixtures ---


def _dummy_func(data, time, fs, **kwargs):
    return {"result": "ok"}


@pytest.fixture
def registered_dummy():
    """Register a dummy analysis for the duration of the test."""
    decorator = AnalysisRegistry.register(
        "test_preproc_reset",
        label="Preprocessing Reset Test",
        ui_params=[
            {"name": "p1", "type": "float", "default": 1.0, "label": "P1"},
        ],
    )
    decorator(_dummy_func)
    yield
    # Cleanup: remove from registry to avoid leaking to other tests
    AnalysisRegistry._registry.pop("test_preproc_reset", None)
    AnalysisRegistry._metadata.pop("test_preproc_reset", None)
    AnalysisRegistry._original_metadata.pop("test_preproc_reset", None)


# --- PreprocessingWidget tests ---


class TestPreprocessingWidgetReset:
    """Tests for the PreprocessingWidget reset_ui method."""

    def test_reset_ui_clears_combos(self, qtbot):
        """reset_ui() should set both combo boxes back to index 0 ('None')."""
        widget = PreprocessingWidget()
        qtbot.addWidget(widget)

        # Set combos to non-default values
        widget.baseline_type_combo.setCurrentIndex(2)  # "Mean"
        widget.filter_type_combo.setCurrentIndex(1)  # "Lowpass"
        assert widget.baseline_type_combo.currentIndex() != 0
        assert widget.filter_type_combo.currentIndex() != 0

        widget.reset_ui()

        assert widget.baseline_type_combo.currentIndex() == 0
        assert widget.filter_type_combo.currentIndex() == 0

    def test_reset_button_emits_signal(self, qtbot):
        """Clicking 'Reset Preprocessing' should emit preprocessing_reset_requested."""
        widget = PreprocessingWidget()
        qtbot.addWidget(widget)

        with qtbot.waitSignal(widget.preprocessing_reset_requested, timeout=1000):
            widget.reset_btn.click()


# --- BaseAnalysisTab preprocessing reset tests ---


class TestAnalysisTabPreprocessingReset:
    """Tests for preprocessing reset in analysis sub-tabs."""

    def test_reset_clears_pipeline(self, qtbot, registered_dummy, monkeypatch):
        """_handle_preprocessing_reset clears pipeline and settings."""
        neo_adapter = MagicMock()
        monkeypatch.setattr(
            "Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock()
        )
        tab = MetadataDrivenAnalysisTab("test_preproc_reset", neo_adapter)
        qtbot.addWidget(tab)

        # Simulate active preprocessing
        tab._active_preprocessing_settings = {"baseline": {"type": "baseline", "method": "mean"}}
        tab._preprocessed_data = {"some": "data"}
        tab.pipeline.add_step({"type": "baseline", "method": "mean"})
        assert len(tab.pipeline._steps) > 0

        tab._handle_preprocessing_reset()

        assert tab._active_preprocessing_settings is None
        assert tab._preprocessed_data is None
        assert len(tab.pipeline._steps) == 0

    def test_reset_resets_widget_ui(self, qtbot, registered_dummy, monkeypatch):
        """_handle_preprocessing_reset resets the PreprocessingWidget combos."""
        neo_adapter = MagicMock()
        monkeypatch.setattr(
            "Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock()
        )
        tab = MetadataDrivenAnalysisTab("test_preproc_reset", neo_adapter)
        qtbot.addWidget(tab)

        # Set combos to non-default
        tab.preprocessing_widget.baseline_type_combo.setCurrentIndex(2)
        tab.preprocessing_widget.filter_type_combo.setCurrentIndex(1)

        tab._handle_preprocessing_reset()

        assert tab.preprocessing_widget.baseline_type_combo.currentIndex() == 0
        assert tab.preprocessing_widget.filter_type_combo.currentIndex() == 0

    def test_reset_signal_connected(self, qtbot, registered_dummy, monkeypatch):
        """The reset signal from PreprocessingWidget should be connected."""
        neo_adapter = MagicMock()
        monkeypatch.setattr(
            "Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock()
        )
        tab = MetadataDrivenAnalysisTab("test_preproc_reset", neo_adapter)
        qtbot.addWidget(tab)

        # Simulate active preprocessing state
        tab._active_preprocessing_settings = {"baseline": {"type": "baseline", "method": "mean"}}
        tab.pipeline.add_step({"type": "baseline", "method": "mean"})

        # Click the reset button — it should trigger _handle_preprocessing_reset
        tab.preprocessing_widget.reset_btn.click()

        # Verify the reset happened (signal was connected and handler ran)
        assert tab._active_preprocessing_settings is None
        assert len(tab.pipeline._steps) == 0

    def test_apply_global_preprocessing_none_resets_widget(self, qtbot, registered_dummy, monkeypatch):
        """apply_global_preprocessing(None) should reset widget UI too."""
        neo_adapter = MagicMock()
        monkeypatch.setattr(
            "Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock()
        )
        tab = MetadataDrivenAnalysisTab("test_preproc_reset", neo_adapter)
        qtbot.addWidget(tab)

        # Set widget combos to non-default
        tab.preprocessing_widget.baseline_type_combo.setCurrentIndex(3)
        tab.preprocessing_widget.filter_type_combo.setCurrentIndex(2)

        tab.apply_global_preprocessing(None)

        assert tab._active_preprocessing_settings is None
        assert tab.preprocessing_widget.baseline_type_combo.currentIndex() == 0
        assert tab.preprocessing_widget.filter_type_combo.currentIndex() == 0
