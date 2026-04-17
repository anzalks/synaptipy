"""
Tests for Event Detection via MetadataDrivenAnalysisTab.

Validates that the generic metadata-driven tab correctly handles
interactive event markers, threshold lines, and curated result display
for event detection analyses.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

# Ensure the analysis modules are imported so registrations are active
import Synaptipy.core.analysis  # noqa: F401
from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab


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


@pytest.fixture(scope="session")
def synaptic_events_tab(qapp):
    """Module-level aggregator tab for synaptic events (has method_selector)."""
    neo_adapter = MagicMock()
    return MetadataDrivenAnalysisTab(
        analysis_name="synaptic_events",
        neo_adapter=neo_adapter,
    )


def test_tab_uses_markers_type(event_tab):
    """Verify that event_detection_threshold uses 'markers' plot type for events."""
    plots_meta = event_tab.metadata.get("plots", [])
    marker_cfgs = [p for p in plots_meta if p.get("type") == "markers"]
    assert len(marker_cfgs) == 1
    assert marker_cfgs[0]["x"] == "_event_times"
    assert marker_cfgs[0]["y"] == "_event_peaks"
    # Interactive event_markers item is no longer used
    assert event_tab._event_markers_item is None


def test_tab_has_threshold_line(event_tab):
    """Verify that the threshold_line plot type creates a draggable InfiniteLine."""
    assert event_tab._threshold_line is not None


def test_tab_has_method_selector(synaptic_events_tab):
    """Verify that the synaptic_events module tab has a method combobox with 3 entries."""
    assert synaptic_events_tab.method_combobox is not None
    # Should have 3 methods
    assert synaptic_events_tab.method_combobox.count() == 3


def test_get_covered_analysis_names(synaptic_events_tab):
    """Verify covered names includes all method_selector alternatives."""
    covered = synaptic_events_tab.get_covered_analysis_names()
    assert "event_detection_threshold" in covered
    assert "event_detection_deconvolution" in covered
    assert "event_detection_baseline_peak" in covered


def test_visualization_with_wrapper_result(event_tab):
    """Test that markers appear when passing the standard wrapper dict format."""
    time_arr = event_tab._current_plot_data["time"]
    data_arr = event_tab._current_plot_data["data"]
    indices = np.array([10, 50, 100])
    result_dict = {
        "module_used": "synaptic_events",
        "metrics": {
            "event_count": 3,
            "frequency_hz": 3.0,
            "mean_amplitude": 10.0,
            "amplitude_sd": 1.0,
            "_event_times": time_arr[indices].tolist(),
            "_event_peaks": data_arr[indices].tolist(),
        },
    }

    event_tab._plot_analysis_visualizations(result_dict)

    # A scatter item should have been added to dynamic plot items
    assert len(event_tab._dynamic_plot_items) > 0


def test_visualization_with_flat_dict(event_tab):
    """Test that flat dict with _event_times/_event_peaks renders markers."""
    time_arr = event_tab._current_plot_data["time"]
    data_arr = event_tab._current_plot_data["data"]
    indices = np.array([10, 50, 100])
    result_dict = {
        "_event_times": time_arr[indices].tolist(),
        "_event_peaks": data_arr[indices].tolist(),
    }

    event_tab._plot_analysis_visualizations(result_dict)

    assert len(event_tab._dynamic_plot_items) > 0


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
