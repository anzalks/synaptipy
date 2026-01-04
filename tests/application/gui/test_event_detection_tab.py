import pytest
from unittest.mock import MagicMock, patch
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

from Synaptipy.application.gui.analysis_tabs.event_detection_tab import EventDetectionTab
from Synaptipy.core.results import EventDetectionResult
from Synaptipy.core.analysis.registry import AnalysisRegistry

# Mock the registry to return metadata for our testing
@pytest.fixture
def mock_registry():
    with patch('Synaptipy.core.analysis.registry.AnalysisRegistry.get_metadata') as mock_get_meta:
        mock_get_meta.return_value = {
            'ui_params': [{'name': 'threshold', 'type': 'float', 'default': -20.0}]
        }
        yield mock_get_meta

@pytest.fixture
def event_tab(qapp, mock_registry):
    neo_adapter = MagicMock()
    tab = EventDetectionTab(neo_adapter)
    
    # Setup dummy plot data
    tab._current_plot_data = {
        'time': np.linspace(0, 1, 1000),
        'data': np.random.randn(1000)
    }
    
    # Setup dummy plot widget items
    tab.plot_widget = MagicMock()
    tab.event_markers_item = MagicMock()
    tab.threshold_line = MagicMock()
    
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
        threshold_value=-20.0
    )
    
    # Call visualization
    event_tab._plot_analysis_visualizations(result_obj)
    
    # Assert markers were updated
    event_tab.event_markers_item.setData.assert_called()
    call_args = event_tab.event_markers_item.setData.call_args
    assert call_args is not None
    assert 'x' in call_args.kwargs or len(call_args.args) > 0 # check arg presence
    
    # Assert visible
    event_tab.event_markers_item.setVisible.assert_called_with(True)
    
    # Assert threshold line updated
    event_tab.threshold_line.setValue.assert_called_with(-20.0)

def test_visualization_with_dict_result(event_tab):
    """Test backwards compatibility with dictionary results."""
    result_dict = {
        'event_indices': np.array([10, 50, 100]),
        'threshold': -15.0
    }
    
    event_tab._plot_analysis_visualizations(result_dict)
    
    event_tab.event_markers_item.setVisible.assert_called_with(True)
    event_tab.threshold_line.setValue.assert_called_with(-15.0)

def test_display_results_with_object(event_tab):
    """Test result text display with object."""
    event_tab.results_text = MagicMock()
    
    result_obj = EventDetectionResult(
        value=5,
        unit="events",
        event_indices=np.array([]), 
        event_times=np.array([]),
        event_count=5,
        frequency_hz=2.5
    )
    
    event_tab._on_analysis_result(result_obj)
    
    # Check text set
    event_tab.results_text.setHtml.assert_called()
    html_arg = event_tab.results_text.setHtml.call_args[0][0]
    assert "Count:</b> 5" in html_arg
    assert "Frequency:</b> 2.50 Hz" in html_arg
