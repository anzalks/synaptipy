import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from Synaptipy.application.gui.analysis_tabs.event_detection_tab import EventDetectionTab
from Synaptipy.core.results import EventDetectionResult


# Mock the registry to return metadata for our testing
@pytest.fixture
def mock_registry():
    with patch("Synaptipy.core.analysis.registry.AnalysisRegistry.get_metadata") as mock_get_meta:
        mock_get_meta.return_value = {"ui_params": [{"name": "threshold", "type": "float", "default": -20.0}]}
        yield mock_get_meta


@pytest.fixture
def event_tab(qapp, mock_registry):
    neo_adapter = MagicMock()
    tab = EventDetectionTab(neo_adapter)

    # Setup dummy plot data
    tab._current_plot_data = {"time": np.linspace(0, 1, 1000), "data": np.random.randn(1000)}

    # Setup dummy plot widget items
    tab.plot_widget = MagicMock()
    tab.event_markers_item = MagicMock()
    tab.threshold_line = MagicMock()
    tab.threshold_line.value.return_value = -20.0

    return tab


def test_visualization_with_object_result(event_tab):
    """Test that visualization works with EventDetectionResult object."""
    # Create a result object
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

    # Call visualization
    event_tab._plot_analysis_visualizations(result_obj)

    # Assert markers were updated
    event_tab.event_markers_item.setData.assert_called()
    call_args = event_tab.event_markers_item.setData.call_args
    assert call_args is not None
    assert "x" in call_args.kwargs or len(call_args.args) > 0  # check arg presence

    # Assert visible
    event_tab.event_markers_item.setVisible.assert_called_with(True)

    # Assert threshold line updated
    event_tab.threshold_line.setValue.assert_called_with(-20.0)


def test_visualization_with_dict_result(event_tab):
    """Test backwards compatibility with dictionary results."""
    result_dict = {"event_indices": np.array([10, 50, 100]), "threshold": -15.0}

    event_tab._plot_analysis_visualizations(result_dict)

    event_tab.event_markers_item.setVisible.assert_called_with(True)
    event_tab.threshold_line.setValue.assert_called_with(-15.0)


def test_display_results_with_object(event_tab):
    """Test result table display with object."""
    # Mock results_table (QTableWidget)
    event_tab.results_table = MagicMock()
    # Also need method_combobox since display logic uses it
    event_tab.method_combobox = MagicMock()
    event_tab.method_combobox.currentText.return_value = "Threshold Based"

    result_obj = EventDetectionResult(
        value=5,
        unit="events",
        event_indices=np.array([10, 20, 30, 40, 50]),
        event_times=np.array([0.01, 0.02, 0.03, 0.04, 0.05]),
        event_count=5,
        frequency_hz=2.5,
        threshold_value=-20.0
    )
    event_tab._current_event_indices = [10, 20, 30, 40, 50]

    event_tab._display_analysis_results(result_obj)

    # Check table population
    # Should call setRowCount and setItem
    event_tab.results_table.setRowCount.assert_called()

    # Check that setItem was called with appropriate values
    # We can check if "Count" and "5" were set
    # The implementation iterates and calls setItem(row, col, item)
    # We can inspect call_args_list or just verify setItem called enough times
    assert event_tab.results_table.setItem.called

    # Inspect arguments to verify content
    # args: (row, col, QTableWidgetItem)
    found_count = False
    found_freq = False

    for call in event_tab.results_table.setItem.call_args_list:
        args = call.args
        item = args[2]
        if hasattr(item, "text"):
            text = item.text()
            if text == "5":
                found_count = True
            if "5.00" in text:  # 5.00 Hz
                found_freq = True

    assert found_count, "Count value '5' not found in table items"
    assert found_freq, "Frequency value '5.00 Hz' not found in table items"
