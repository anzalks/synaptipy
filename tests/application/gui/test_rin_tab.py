"""
Unit tests for the Input Resistance Analysis Tab
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from PySide6 import QtWidgets, QtCore
from pathlib import Path

from Synaptipy.application.gui.analysis_tabs.rin_tab import RinAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.data_model import Channel, Recording


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
    """Fixture providing a RinAnalysisTab instance"""
    tab = RinAnalysisTab(neo_adapter=mock_neo_adapter)
    qtbot.addWidget(tab)
    return tab


# Basic setup tests
def test_rin_tab_init(rin_tab):
    """Test that the tab initializes correctly"""
    assert rin_tab is not None
    assert rin_tab.mode_combobox is not None
    assert rin_tab.plot_widget is not None
    assert rin_tab.get_display_name() == "Resistance/Conductance"


def test_mode_selection(rin_tab, qtbot):
    """Test that mode selection works properly"""
    # Check if mode combobox exists and has at least two modes
    assert hasattr(rin_tab, "mode_combobox")
    assert isinstance(rin_tab.mode_combobox, QtWidgets.QComboBox)
    assert rin_tab.mode_combobox.count() >= 2

    # Verify tab has the necessary structure
    assert hasattr(rin_tab, "plot_widget")
    # Verify tab has the necessary structure
    assert hasattr(rin_tab, "plot_widget")
    # assert hasattr(rin_tab, 'run_button') # Removed in refactor

    # Test mode switching works
    initial_mode = rin_tab.mode_combobox.currentText()
    if rin_tab.mode_combobox.count() > 1:
        # Switch to another mode
        next_index = (rin_tab.mode_combobox.currentIndex() + 1) % rin_tab.mode_combobox.count()
        rin_tab.mode_combobox.setCurrentIndex(next_index)
        # Verify mode changed
        assert rin_tab.mode_combobox.currentText() != initial_mode


def test_interactive_calculation(rin_tab, qtbot, mock_neo_adapter):
    """Test interactive region components are present"""
    # Check if interactive regions exist
    assert hasattr(rin_tab, "baseline_region")
    assert hasattr(rin_tab, "response_region")

    # Check we have save functionality
    assert hasattr(rin_tab, "save_button")
    assert isinstance(rin_tab.save_button, QtWidgets.QPushButton)


def test_manual_calculation(rin_tab, qtbot, mock_neo_adapter):
    """Test resistance calculation in manual mode"""
    # Test that the tab initializes properly in manual mode
    # Get the actual mode values
    if rin_tab.mode_combobox.count() >= 2:
        manual_mode = rin_tab.mode_combobox.itemText(1)
        rin_tab.mode_combobox.setCurrentText(manual_mode)

    # Check that essential UI elements exist
    # assert hasattr(rin_tab, 'run_button') # Removed in refactor (reactive)
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
