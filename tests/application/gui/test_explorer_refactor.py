import pytest
import numpy as np
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from Synaptipy.application.gui.explorer.explorer_tab import ExplorerTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from Synaptipy.core.data_model import Recording, Channel


@pytest.fixture
def explorer_tab(qtbot):
    neo_adapter = NeoAdapter()
    nwb_exporter = NWBExporter()
    status_bar = QtWidgets.QStatusBar()

    tab = ExplorerTab(neo_adapter, nwb_exporter, status_bar)
    qtbot.addWidget(tab)
    return tab


def test_explorer_tab_init(explorer_tab):
    assert explorer_tab is not None
    assert explorer_tab.plot_canvas is not None
    assert explorer_tab.sidebar is not None
    assert explorer_tab.config_panel is not None
    assert explorer_tab.toolbar is not None
    assert explorer_tab.y_controls is not None


def test_explorer_plotting(explorer_tab, qtbot):
    # Mock Data
    recording = MagicMock(spec=Recording)
    recording.source_file = MagicMock()
    recording.source_file.name = "test.wcp"
    recording.duration = 1.0
    recording.sampling_rate = 1000.0
    recording.max_trials = 10

    channel = MagicMock(spec=Channel)
    channel.name = "Ch1"
    channel.units = "mV"
    channel.num_trials = 10
    channel.get_primary_data_label.return_value = "Voltage (mV)"

    # Mock Data Returns
    t = np.linspace(0, 1, 1000)
    d = np.sin(2 * np.pi * 5 * t)
    channel.get_data.return_value = d
    channel.get_relative_time_vector.return_value = t
    channel.get_averaged_data.return_value = d  # Just return same data for avg

    recording.channels = {"ch1": channel}

    # Load Data
    explorer_tab._display_recording(recording)

    # Check Plot Rebuild
    assert "ch1" in explorer_tab.plot_canvas.channel_plots
    assert len(explorer_tab.plot_canvas.channel_plot_data_items["ch1"]) > 0

    # Test Trial Cycling
    explorer_tab.current_plot_mode = explorer_tab.PlotMode.CYCLE_SINGLE
    explorer_tab._update_plot()

    assert explorer_tab.current_trial_index == 0
    explorer_tab._next_trial()
    assert explorer_tab.current_trial_index == 1

    # Verify plot updated (check call count or data if possible, for now just no crash)

    explorer_tab._prev_trial()
    assert explorer_tab.current_trial_index == 0

    # Test Sidebar Selection (Manual Call)
    explorer_tab._on_channel_visibility_changed("ch1", False)
    assert not explorer_tab.plot_canvas.channel_plots["ch1"].isVisible()


def test_explorer_synchronization(explorer_tab, qtbot):
    # Setup Mock Data
    recording = MagicMock(spec=Recording)
    recording.channels = {}
    recording.duration = 10.0
    recording.sampling_rate = 1000.0
    recording.max_trials = 10

    channel = MagicMock(spec=Channel)
    channel.get_data.return_value = np.zeros(100)
    channel.get_relative_time_vector.return_value = np.linspace(0, 10, 100)
    channel.get_primary_data_label.return_value = "V"
    channel.units = "V"
    channel.units = "V"
    channel.name = "Ch1"
    recording.channels["ch1"] = channel

    recording.source_file = MagicMock()
    recording.source_file.name = "test.wcp"

    explorer_tab._display_recording(recording)

    # 1. Test X Zoom Application
    # Base X range is 0-10. Zoom slider = 1 (100% visible)
    # Change Zoom to 50 (~2% visible?)
    explorer_tab.toolbar.x_zoom_slider.setValue(50)
    explorer_tab._apply_x_zoom(50)

    plot_item = explorer_tab.plot_canvas.get_plot("ch1")
    vb = plot_item.getViewBox()
    x_range = vb.viewRange()[0]
    assert x_range[1] - x_range[0] < 10.0  # Should be zoomed in

    # 2. Test Y Global Zoom
    # Initial Y setup
    explorer_tab.y_controls.global_y_slider.setValue(1)
    # Apply zoom
    explorer_tab._apply_global_y_zoom(50)
    y_range = vb.viewRange()[1]
    # Check if range is smaller than base range (Mock data is 0, base range likely small but zoom should shrink it)

    # 3. Test Signal Sync (Reverse)
    # Simulate ViewBox Change
    explorer_tab._on_vb_x_range_changed("ch1", (4.0, 6.0))  # 20% of range, center 5
    # Should update scrollbar
    assert explorer_tab.x_scrollbar.value() > 0
    assert 4000 < explorer_tab.x_scrollbar.value() < 6000  # Center approx 5000


def test_sidebar_sync(explorer_tab, qtbot, tmp_path):
    # Create dummy file structure
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    dummy_file = data_dir / "test.wcp"
    dummy_file.touch()

    # Mock file model to avoid actual FS load latency issues in test or use real model with wait?
    # The real ExplorerSidebar uses QFileSystemModel which is async.
    # Testing async QFileSystemModel is hard in unit tests without a lot of waiting.
    # However, we can verify that sync_to_file calls setRootIndex on the tree.

    explorer_tab.sidebar.file_tree = MagicMock()
    explorer_tab.sidebar.file_model = MagicMock()

    # Setup mock index
    mock_idx = MagicMock()
    mock_idx.isValid.return_value = True
    explorer_tab.sidebar.file_model.index.return_value = mock_idx

    from pathlib import Path

    explorer_tab.sidebar.sync_to_file(dummy_file)

    # Check if setRootIndex was called with parent dir index
    explorer_tab.sidebar.file_model.index.assert_any_call(str(dummy_file.parent))
    explorer_tab.sidebar.file_tree.setRootIndex.assert_called_once()

    # Check if scrollTo/setCurrentIndex was called for the file
    explorer_tab.sidebar.file_model.index.assert_any_call(str(dummy_file))
    explorer_tab.sidebar.file_tree.scrollTo.assert_called_once()
    explorer_tab.sidebar.file_tree.setCurrentIndex.assert_called_once()
