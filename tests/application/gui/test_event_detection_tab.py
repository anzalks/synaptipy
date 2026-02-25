"""
Tests for Event Detection via MetadataDrivenAnalysisTab.

Validates that the generic metadata-driven tab correctly handles
interactive event markers, threshold lines, and curated result display
for event detection analyses.
"""
import pytest
from unittest.mock import MagicMock
import numpy as np

from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.core.results import EventDetectionResult

# Ensure the analysis modules are imported so registrations are active
import Synaptipy.core.analysis  # noqa: F401


@pytest.fixture(scope="session")
def event_tab(qapp):
    neo_adapter = MagicMock()
    tab = MetadataDrivenAnalysisTab(
        analysis_name="event_detection_threshold",
        neo_adapter=neo_adapter,
    )

    # Setup dummy plot data
    tab._current_plot_data = {
        "time": np.linspace(0, 1, 1000),
        "data": np.random.randn(1000),
    }

    return tab


def test_tab_has_event_markers(event_tab):
    """Verify that the event_markers plot type creates an interactive scatter item."""
    assert event_tab._event_markers_item is not None


def test_tab_has_threshold_line(event_tab):
    """Verify that the threshold_line plot type creates a draggable InfiniteLine."""
    assert event_tab._threshold_line is not None


def test_tab_has_method_selector(event_tab):
    """Verify that the method_selector metadata creates a method combobox."""
    assert event_tab.method_combobox is not None
    # Should have 3 methods
    assert event_tab.method_combobox.count() == 3


def test_get_covered_analysis_names(event_tab):
    """Verify covered names includes all method_selector alternatives."""
    covered = event_tab.get_covered_analysis_names()
    assert "event_detection_threshold" in covered
    assert "event_detection_deconvolution" in covered
    assert "event_detection_baseline_peak" in covered


def test_visualization_with_object_result(event_tab):
    """Test that visualization works with EventDetectionResult object."""
    result_obj = EventDetectionResult(
        value=3,
        unit="events",
        event_indices=np.array([10, 50, 100]),
        event_times=np.array([0.01, 0.05, 0.1]),
        event_count=3,
        frequency_hz=3.0,
        mean_amplitude=10.0,
        amplitude_sd=1.0,
        threshold_value=-20.0,
    )

    event_tab._plot_analysis_visualizations(result_obj)

    # Markers should now be populated
    assert len(event_tab._current_event_indices) == 3
    assert event_tab._event_markers_item.isVisible()


def test_visualization_with_dict_result(event_tab):
    """Test backwards compatibility with dictionary results."""
    result_dict = {"event_indices": np.array([10, 50, 100]), "threshold": -15.0}

    event_tab._plot_analysis_visualizations(result_dict)

    assert len(event_tab._current_event_indices) == 3
    assert event_tab._event_markers_item.isVisible()
    # Threshold line should be updated
    assert event_tab._threshold_line.value() == pytest.approx(-15.0)


def test_display_results_curated(event_tab):
    """Test curated event result table display."""
    event_tab._current_event_indices = [10, 20, 30, 40, 50]
    event_tab._update_curated_event_table()

    assert event_tab.results_table.rowCount() >= 3
    # Find "Count" row
    found_count = False
    for row in range(event_tab.results_table.rowCount()):
        item = event_tab.results_table.item(row, 0)
        if item and item.text() == "Count":
            val = event_tab.results_table.item(row, 1).text()
            assert val == "5"
            found_count = True
    assert found_count, "Count row not found in results table"
