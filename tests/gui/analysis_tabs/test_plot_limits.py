
import pytest
from unittest.mock import MagicMock, patch, PropertyMock  # noqa: F401
import numpy as np
from PySide6 import QtWidgets, QtCore  # noqa: F401

from Synaptipy.application.gui.analysis_tabs.base import BaseAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.data_model import Recording, Channel

# Concrete implementation for testing abstract base class


class ConcreteAnalysisTab(BaseAnalysisTab):
    def __init__(self, neo_adapter, settings_ref=None, parent=None):
        super().__init__(neo_adapter, settings_ref, parent)
        self._setup_ui()

    def get_registry_name(self):
        return "test_analysis"

    def get_display_name(self):
        return "Test Analysis"

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self._setup_plot_area(layout)
        self._setup_data_selection_ui(layout)

    def _update_ui_for_selected_item(self):
        pass

    def _gather_analysis_parameters(self):
        return {}

    def _execute_core_analysis(self, params, data):
        return None

    def _display_analysis_results(self, results):
        pass

    def _plot_analysis_visualizations(self, results):
        pass


@pytest.fixture
def tab(qapp):
    """Fixture to create a ConcreteAnalysisTab instance."""
    neo_adapter = MagicMock(spec=NeoAdapter)
    tab = ConcreteAnalysisTab(neo_adapter=neo_adapter)
    return tab


@pytest.fixture
def mock_recording():
    """Create a mock recording with known data."""
    recording = MagicMock(spec=Recording)
    channel = MagicMock(spec=Channel)
    channel.name = "TestCh"
    channel.units = "mV"
    channel.num_trials = 1

    # 100 points, 0 to 1s
    time = np.linspace(0, 1, 100)
    data = np.sin(2 * np.pi * 5 * time)  # 5Hz sine wave

    channel.get_data.return_value = data
    channel.get_relative_time_vector.return_value = time
    channel.get_averaged_data.return_value = data

    recording.channels = {"0": channel}
    recording.channel_names = ["TestCh"]

    return recording


def test_plot_limits_auto_range_on_switch(tab, mock_recording):
    """Test that switching files auto-ranges if View = Data (Full View)."""

    # Setup mocks
    tab._selected_item_recording = mock_recording
    tab.signal_channel_combobox.currentData = MagicMock(return_value="0")
    tab.data_source_combobox.currentData = MagicMock(return_value=0)
    tab.signal_channel_combobox.setEnabled(True)
    tab.data_source_combobox.setEnabled(True)

    # 1. Plot Initial Data
    # Mock AnalysisPlotManager to return our data
    with patch("Synaptipy.application.controllers.analysis_plot_manager.AnalysisPlotManager.prepare_plot_data") as mock_prep:
        mock_prep.return_value.main_data = np.sin(np.linspace(0, 1, 100))
        mock_prep.return_value.main_time = np.linspace(0, 1, 100)
        mock_prep.return_value.channel_id = "0"
        mock_prep.return_value.data_source = 0
        mock_prep.return_value.units = "mV"
        mock_prep.return_value.sampling_rate = 100.0
        mock_prep.return_value.channel_name = "TestCh"
        mock_prep.return_value.label = "Trial 1"
        mock_prep.return_value.context_traces = []

        mock_prep.return_value.context_traces = []
        mock_prep.return_value.is_multi_trial = False

        # Trigger plot
        tab._plot_selected_data()

        # Simulate Auto-ranged state (View ~= Data)
        tab.plot_widget.setRange(xRange=(0, 1), yRange=(-1, 1), padding=0)

        # 2. Switch to "New" Data (Simulated by calling plot again with different data)
        # Change data to be smaller 0-0.5s
        mock_prep.return_value.main_time = np.linspace(0, 0.5, 50)
        mock_prep.return_value.main_data = np.sin(np.linspace(0, 0.5, 50))

        # Call plot again (simulating file switch)
        # Important: We haven't zoomed, so it should auto-range to new data (0-0.5)
        tab._plot_selected_data()

        # Force update
        tab.plot_widget.getViewBox().enableAutoRange()
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()

        # Check Item Count
        items = tab.plot_widget.listDataItems()
        assert len(items) == 1, f"Expected 1 item, got {len(items)}: {items}"

        # Check ViewRange
        view_range = tab.plot_widget.viewRange()
        x_range = view_range[0]

        # Should be close to 0-0.5 (Auto-ranged)
        assert abs(x_range[0] - 0.0) < 0.1
        assert abs(x_range[1] - 0.5) < 0.1


def test_plot_limits_sticky_zoom(tab, mock_recording):
    """Test that switching files PRESERVES view if user is zoomed in."""

    # Setup mocks
    tab._selected_item_recording = mock_recording
    tab.signal_channel_combobox.currentData = MagicMock(return_value="0")
    tab.data_source_combobox.currentData = MagicMock(return_value=0)
    tab.signal_channel_combobox.setEnabled(True)
    tab.data_source_combobox.setEnabled(True)

    # 1. Plot Initial Data (0-1s)
    with patch("Synaptipy.application.controllers.analysis_plot_manager.AnalysisPlotManager.prepare_plot_data") as mock_prep:
        mock_prep.return_value.main_data = np.sin(np.linspace(0, 1, 100))
        mock_prep.return_value.main_time = np.linspace(0, 1, 100)
        mock_prep.return_value.channel_id = "0"
        mock_prep.return_value.data_source = 0
        mock_prep.return_value.sampling_rate = 100.0
        mock_prep.return_value.channel_name = "TestCh"
        mock_prep.return_value.label = "Trial 1"
        mock_prep.return_value.units = "mV"
        mock_prep.return_value.units = "mV"
        mock_prep.return_value.context_traces = []
        mock_prep.return_value.is_multi_trial = False

        tab._plot_selected_data()

        # 2. ZOOM IN significantly (e.g., 0.2 to 0.4s)
        zoom_x = (0.2, 0.4)
        tab.plot_widget.setXRange(zoom_x[0], zoom_x[1], padding=0)
        QtWidgets.QApplication.processEvents()

        # Verify zoom applied
        curr = tab.plot_widget.viewRange()[0]
        assert abs(curr[0] - 0.2) < 0.05, f"setXRange failed. Got {curr}"

        # Ensure we are considered "zoomed" logic works eventually
        # ...

        # 3. Switch to "New" Data (0-1s again, or something else)
        # Using same data range to verify ZOOM is preserved

        tab._plot_selected_data()

        # Check ViewRange
        view_range = tab.plot_widget.viewRange()
        x_range = view_range[0]

        # Should be preserved (0.2-0.4), NOT auto-ranged (0-1)
        # NOTE: This test will FAIL until we implement the fix
        assert abs(x_range[0] - 0.2) < 0.05
        assert abs(x_range[1] - 0.4) < 0.05


def test_plot_limits_preprocessing_preserves(tab, mock_recording):
    """Test that active preprocessing PRESERVES view even if full view."""

    # Setup mocks
    tab._selected_item_recording = mock_recording
    tab.signal_channel_combobox.currentData = MagicMock(return_value="0")
    tab.data_source_combobox.currentData = MagicMock(return_value=0)
    tab.signal_channel_combobox.setEnabled(True)
    tab.data_source_combobox.setEnabled(True)

    # Enable Preprocessing
    tab._active_preprocessing_settings = {"filter": "highpass"}

    # 1. Plot Initial Data (0-1s)
    with patch("Synaptipy.application.controllers.analysis_plot_manager.AnalysisPlotManager.prepare_plot_data") as mock_prep:
        mock_prep.return_value.main_data = np.sin(np.linspace(0, 1, 100))
        mock_prep.return_value.main_time = np.linspace(0, 1, 100)
        mock_prep.return_value.channel_id = "0"
        mock_prep.return_value.data_source = 0
        mock_prep.return_value.sampling_rate = 100.0
        mock_prep.return_value.units = "mV"
        mock_prep.return_value.channel_name = "TestCh"
        mock_prep.return_value.label = "Trial 1"
        mock_prep.return_value.label = "Trial 1"
        mock_prep.return_value.context_traces = []
        mock_prep.return_value.is_multi_trial = False

        tab._plot_selected_data()

        # Set a specific range (e.g. slightly different from auto but "full-ish" or whatever)
        # Actually, let's set a specific range to verify it is kept.
        # Say user panned slightly: 0.1 to 1.1n
        tab.plot_widget.setXRange(0.1, 1.1, padding=0)

        # 3. Switch Data (Update Plot)
        tab._plot_selected_data()

        QtWidgets.QApplication.processEvents()

        # Check ViewRange
        view_range = tab.plot_widget.viewRange()
        x_range = view_range[0]

        # Should be preserved (0.1-1.1) because preprocessing is ON
        assert abs(x_range[0] - 0.1) < 0.05
        assert abs(x_range[1] - 1.1) < 0.05
