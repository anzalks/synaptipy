"""
Unit tests for the Input Resistance Analysis Tab (via MetadataDrivenAnalysisTab).
"""

import pytest
import numpy as np
from unittest.mock import MagicMock
from PySide6 import QtWidgets

from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.data_model import Channel, Recording

# Ensure the analysis modules are imported so registrations are active
import Synaptipy.core.analysis  # noqa: F401


# Fixtures for reuse in multiple tests
@pytest.fixture
def mock_neo_adapter():
    """Mock NeoAdapter with pre-set data for testing"""
    adapter = MagicMock(spec=NeoAdapter)

    # Create a mock recording with voltage and current channels
    recording = Recording(source_file=None)
    recording.sampling_rate = 10000.0  # 10 kHz
    recording.t_start = 0.0
    recording.duration = 1.0  # 1 second

    # Create voltage channel with a step response
    time_vec = np.linspace(0, 1, 10000)  # 1 second at 10kHz
    voltage_data = np.zeros_like(time_vec)
    voltage_data[2000:5000] = -10.0  # -10 mV step from 0.2s to 0.5s

    # Create a mock voltage channel
    v_channel = Channel(id="1", name="Vm", units="mV", sampling_rate=10000.0, data_trials=[voltage_data])
    v_channel.t_start = 0.0

    # Create current channel with a step
    current_data = np.zeros_like(time_vec)
    current_data[2000:5000] = -0.050  # -50 pA step from 0.2s to 0.5s

    # Create a mock current channel
    i_channel = Channel(id="2", name="Im", units="pA", sampling_rate=10000.0, data_trials=[current_data])
    i_channel.t_start = 0.0

    # Add channels to recording
    recording.channels = {"1": v_channel, "2": i_channel}

    # Set current_recording property instead of using get_current_recording method
    adapter.current_recording = recording

    return adapter


@pytest.fixture
def rin_tab(qtbot, mock_neo_adapter):
    """Fixture providing a MetadataDrivenAnalysisTab for rin_analysis."""
    tab = MetadataDrivenAnalysisTab(
        analysis_name="rin_analysis",
        neo_adapter=mock_neo_adapter,
    )
    qtbot.addWidget(tab)
    return tab


# Basic setup tests
def test_rin_tab_init(rin_tab):
    """Test that the tab initializes correctly"""
    assert rin_tab is not None
    assert rin_tab.plot_widget is not None
    assert rin_tab.get_display_name() == "Input Resistance"


def test_interactive_regions_present(rin_tab):
    """Test that interactive regions are created from baseline/response params."""
    # The metadata has baseline_start/baseline_end and response_start/response_end
    # so _setup_interactive_regions should create LinearRegionItems
    assert len(rin_tab._interactive_regions) > 0


def test_has_save_button(rin_tab):
    """Test that save button exists."""
    assert hasattr(rin_tab, "save_button")
    assert isinstance(rin_tab.save_button, QtWidgets.QPushButton)


def test_get_specific_result_data(rin_tab):
    """Test that the specific result data method returns the correct format"""
    # Set mock results
    rin_tab._last_analysis_result = {
        "Rin (MΩ)": 200.0,
        "Conductance (μS)": 5.0,
        "ΔV (mV)": 10.0,
        "ΔI (pA)": 50.0,
        "Baseline Window (s)": [0.0, 0.1],
        "Response Window (s)": [0.3, 0.4],
        "analysis_type": "Resistance",
    }

    # Get the specific result data
    result_data = rin_tab._get_specific_result_data()

    # Check the format
    assert isinstance(result_data, dict)
    # Check keys based on what's actually in the return value
    assert "Rin (MΩ)" in result_data or "Input Resistance (MΩ)" in result_data
    assert "Conductance (μS)" in result_data


def test_result_hlines_visualization(rin_tab):
    """Test that result h-lines are plotted from analysis results."""
    result_data = {
        "baseline_voltage_mv": -65.0,
        "steady_state_voltage_mv": -75.0,
        "rin_mohm": 200.0,
    }

    rin_tab._plot_analysis_visualizations(result_data)

    # Should have created h-lines for baseline and steady-state voltages
    assert len(rin_tab._result_hlines) > 0
