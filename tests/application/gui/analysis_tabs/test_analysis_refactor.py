
import pytest
from unittest.mock import MagicMock, patch

import numpy as np
from PySide6 import QtWidgets, QtCore  # noqa: F401

from Synaptipy.application.gui.analysis_tabs.base import BaseAnalysisTab
from Synaptipy.application.gui.analysis_tabs.spike_tab import SpikeAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.data_model import Recording, Channel

# Mock the registry to avoid import errors or missing plugins


@pytest.fixture(autouse=True)
def mock_registry():
    with patch('Synaptipy.core.analysis.registry.AnalysisRegistry.get_function') as mock_get:
        mock_get.return_value = lambda v, t, fs, **k: {'spike_times': [], 'metadata': {}}
        yield mock_get


@pytest.fixture
def mock_neo_adapter():
    return MagicMock(spec=NeoAdapter)


@pytest.fixture
def base_tab(mock_neo_adapter, qtbot):
    # BaseAnalysisTab is abstract, so we mock the abstract methods to instantiate it for testing
    # Or better, use a concrete subclass like SpikeAnalysisTab or a dummy subclass
    class TestTab(BaseAnalysisTab):
        def get_registry_name(self):
            return "test_analysis"

        def get_display_name(self):
            return "Test Tab"

        def _setup_ui(self):
            layout = QtWidgets.QVBoxLayout(self)
            self._setup_plot_area(layout)
            self._setup_data_selection_ui(layout)

        def _update_ui_for_selected_item(self):
            pass

        def _gather_analysis_parameters(self):
            return {}

        def _execute_core_analysis(self, params, data):
            return {}

        def _display_analysis_results(self, results):
            pass

        def _plot_analysis_visualizations(self, results):
            pass

    tab = TestTab(mock_neo_adapter)
    tab._setup_ui()
    qtbot.addWidget(tab)
    return tab


@pytest.fixture
def spike_tab(mock_neo_adapter, qtbot):
    tab = SpikeAnalysisTab(mock_neo_adapter)
    qtbot.addWidget(tab)
    return tab


def create_mock_recording():
    rec = MagicMock(spec=Recording)
    rec.channels = {}
    chan = MagicMock(spec=Channel)
    chan.name = "Ch1"
    chan.units = "mV"
    chan.sampling_rate = 1000.0
    chan.num_trials = 1

    # Data
    t = np.linspace(0, 1, 1000)
    d = np.sin(2 * np.pi * 5 * t)
    chan.get_data.return_value = d
    chan.get_relative_time_vector.return_value = t
    chan.get_averaged_data.return_value = d
    chan.get_relative_averaged_time_vector.return_value = t

    rec.channels["ch1"] = chan
    return rec


def test_plot_widget_existence(base_tab):
    """Verify plot widget is created and compatible."""
    assert base_tab.plot_widget is not None
    # In current code it is a PlotWidget. After refactor it might be a PlotItem or PlotWidget?
    # Our plan: self.plot_widget will be the PlotItem from the canvas.
    # Currently check if it has plot method
    assert hasattr(base_tab.plot_widget, 'plot')


def test_preprocessing_flow(base_tab):
    """Verify preprocessing request triggers pipeline/processing."""
    rec = create_mock_recording()
    base_tab._selected_item_recording = rec

    # Setup comboboxes to allow plotting
    base_tab.signal_channel_combobox.addItem("Ch1", "ch1")
    base_tab.signal_channel_combobox.setEnabled(True)
    base_tab.data_source_combobox.addItem("Trial 1", 0)
    base_tab.data_source_combobox.setEnabled(True)

    # Lets inspect the active settings
    settings = {'type': 'filter', 'method': 'lowpass', 'cutoff': 100}

    # We can mock _plot_selected_data to see if it gets called
    with patch.object(base_tab, '_plot_selected_data', wraps=base_tab._plot_selected_data) as mock_plot:
        with patch(
            'Synaptipy.application.controllers.analysis_plot_manager.AnalysisPlotManager.prepare_plot_data'
        ) as mock_prep:
            # Return a dummy package so it doesn't return None
            mock_prep.return_value = MagicMock(main_data=np.array(
                [0, 1]), main_time=np.array([0, 1]), context_traces=[])

            base_tab._handle_preprocessing_request(settings)

            # Settings are stored in nested format: filters keyed by method
            expected = {'filters': {'lowpass': settings}}
            assert base_tab._active_preprocessing_settings == expected
            assert mock_plot.called

            # Verify AnalysisPlotManager called with correct args
            assert mock_prep.called
            args, kwargs = mock_prep.call_args
            assert kwargs.get('preprocessing_settings') == expected
            # Verify callback is passed
            assert 'process_callback' in kwargs

            # Verify pipeline was updated
            assert len(base_tab.pipeline._steps) > 0
            assert base_tab.pipeline._steps[0] == settings


def test_pipeline_cleared_on_update(base_tab):
    """Verify pipeline is cleared when state is updated."""
    base_tab.pipeline.add_step({'type': 'dummy'})
    assert len(base_tab.pipeline._steps) == 1

    base_tab.update_state([])
    assert len(base_tab.pipeline._steps) == 0


def test_spike_tab_plot_items(spike_tab):
    """Verify SpikeTab adds its items to the plot widget."""
    spike_tab._setup_ui()
    # Check if items are added
    # SpikeTab adds spike_markers_item and threshold_line
    assert spike_tab.spike_markers_item is not None
    assert spike_tab.threshold_line is not None

    # Verify they are in the plot
    # plot_widget in base refactor is a PlotItem
    items = spike_tab.plot_widget.items

    assert spike_tab.spike_markers_item in items
    assert spike_tab.threshold_line in items
