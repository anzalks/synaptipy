import pytest
from unittest.mock import MagicMock, patch
import numpy as np
import pyqtgraph as pg

from Synaptipy.application.gui.analysis_tabs.burst_tab import BurstAnalysisTab
from Synaptipy.core.results import BurstResult


@pytest.fixture
def burst_tab(qapp):
    neo_adapter = MagicMock()
    with patch("Synaptipy.core.analysis.registry.AnalysisRegistry.get_metadata") as mock_meta:
        mock_meta.return_value = {}  # Empty metadata for burst is fine/default
        tab = BurstAnalysisTab(neo_adapter)

    # Setup dummy plot data
    tab._current_plot_data = {"time": np.linspace(0, 10, 10000), "data": np.random.randn(10000)}

    # Setup dummy plot widget items
    tab.plot_widget = MagicMock()
    # Mock items list
    tab.burst_lines = []
    tab.spike_markers = MagicMock()

    return tab


def test_burst_visualization_object(burst_tab):
    """Test visualization with BurstResult object."""
    bursts = [[1.0, 1.01, 1.02, 1.05], [5.0, 5.01, 5.02]]  # Burst 1  # Burst 2

    result = BurstResult(value=2, unit="bursts", burst_count=2, bursts=bursts)

    burst_tab._plot_analysis_visualizations(result)

    # Check lines added - we expect 2 lines
    assert len(burst_tab.burst_lines) == 2
    assert burst_tab.plot_widget.addItem.call_count >= 2

    # Check spike markers updated
    burst_tab.spike_markers.setData.assert_called()
    burst_tab.spike_markers.setVisible.assert_called_with(True)


def test_burst_visualization_dict(burst_tab):
    """Test visualization with dictionary (legacy)."""
    burst_data = {"bursts": [[2.0, 2.1, 2.2]]}

    burst_tab._plot_analysis_visualizations(burst_data)

    assert len(burst_tab.burst_lines) == 1
    burst_tab.spike_markers.setVisible.assert_called_with(True)
