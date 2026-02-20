"""
Unit tests for the Baseline/RMP Analysis Tab - Testing Refactored Version
"""

import pytest
import numpy as np
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from pathlib import Path

from Synaptipy.application.gui.analysis_tabs.rmp_tab import BaselineAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.data_model import Channel, Recording


@pytest.fixture
def mock_neo_adapter():
    """Mock NeoAdapter with pre-set data for testing"""
    adapter = MagicMock(spec=NeoAdapter)

    # Create a mock recording with voltage channel
    recording = Recording(source_file=Path("test.abf"))
    recording.sampling_rate = 10000.0  # 10 kHz
    recording.t_start = 0.0
    recording.duration = 1.0  # 1 second

    # Create voltage channel with baseline signal
    _time_vec = np.linspace(0, 1, 10000)  # 1 second at 10kHz  # noqa: F841
    voltage_data = np.random.normal(-70.0, 2.0, 10000)  # -70 mV baseline with noise

    # Create a mock voltage channel
    v_channel = Channel(id="1", name="Vm", units="mV", sampling_rate=10000.0, data_trials=[voltage_data])
    v_channel.t_start = 0.0
    # num_trials is a property calculated from data_trials length

    # Add channels to recording
    recording.channels = {"1": v_channel}

    # Mock the read_recording method
    adapter.read_recording = MagicMock(return_value=recording)

    return adapter


@pytest.fixture
def rmp_tab(qtbot, mock_neo_adapter):
    """Fixture providing a BaselineAnalysisTab instance"""
    tab = BaselineAnalysisTab(neo_adapter=mock_neo_adapter)
    qtbot.addWidget(tab)
    return tab


# Basic setup tests
def test_rmp_tab_init(rmp_tab):
    """Test that the tab initializes correctly"""
    assert rmp_tab is not None
    assert rmp_tab.mode_combobox is not None
    assert rmp_tab.plot_widget is not None
    assert rmp_tab.get_display_name() == "Baseline"


def test_has_data_selection_widgets(rmp_tab):
    """Test that data selection widgets exist"""
    # These should exist either in base class or subclass
    assert hasattr(rmp_tab, "signal_channel_combobox")
    assert hasattr(rmp_tab, "data_source_combobox")
    # Note: analysis_item_combo is now in the parent AnalyserTab, not in individual tabs
    assert hasattr(rmp_tab, "global_controls_layout")  # For receiving global controls


def test_mode_selection(rmp_tab, qtbot):
    """Test that mode selection works properly"""
    assert hasattr(rmp_tab, "mode_combobox")
    assert isinstance(rmp_tab.mode_combobox, QtWidgets.QComboBox)
    assert rmp_tab.mode_combobox.count() >= 2  # At least Interactive and Manual

    # Test mode switching
    initial_mode = rmp_tab.mode_combobox.currentText()
    if rmp_tab.mode_combobox.count() > 1:
        next_index = (rmp_tab.mode_combobox.currentIndex() + 1) % rmp_tab.mode_combobox.count()
        rmp_tab.mode_combobox.setCurrentIndex(next_index)
        assert rmp_tab.mode_combobox.currentText() != initial_mode


def test_interactive_region_exists(rmp_tab):
    """Test that interactive region component is present"""
    assert hasattr(rmp_tab, "interactive_region")
    assert rmp_tab.interactive_region is not None


def test_save_button_exists(rmp_tab):
    """Test that save functionality exists"""
    assert hasattr(rmp_tab, "save_button")
    assert isinstance(rmp_tab.save_button, QtWidgets.QPushButton)


def test_update_state_with_items(rmp_tab, mock_neo_adapter):
    """Test that update_state populates UI correctly"""
    # Create mock analysis items
    test_items = [{"path": Path("test.abf"), "target_type": "Recording", "trial_index": None}]

    # Call update_state (this is called by parent AnalyserTab)
    rmp_tab.update_state(test_items)

    # Check that internal analysis items list was updated
    # Note: analysis_item_combo is now managed by parent AnalyserTab
    assert rmp_tab._analysis_items == test_items


def test_baseline_result_storage(rmp_tab):
    """Test that baseline results can be stored"""
    # Set mock results
    rmp_tab._last_baseline_result = {
        "baseline_mean": -70.0,
        "baseline_sd": 2.0,
        "baseline_units": "mV",
        "calculation_method": "window_interactive",
    }

    # Verify storage
    assert rmp_tab._last_baseline_result is not None
    assert rmp_tab._last_baseline_result["baseline_mean"] == -70.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
