
import sys
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from PySide6 import QtWidgets
import numpy as np

from Synaptipy.application.gui.explorer.explorer_tab import ExplorerTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from Synaptipy.core.data_model import Recording, Channel


@pytest.fixture(scope="session")
def explorer_tab(qapp):
    neo_adapter = MagicMock(spec=NeoAdapter)
    nwb_exporter = MagicMock(spec=NWBExporter)
    status_bar = QtWidgets.QStatusBar()

    # Mock styles to avoid theme issues; patch only wraps construction
    with patch('Synaptipy.shared.styling.style_button'):
        tab = ExplorerTab(neo_adapter, nwb_exporter, status_bar)
    return tab


@pytest.fixture(autouse=True)
def reset_processing_state(explorer_tab):
    """Clear accumulated preprocessing settings before every test."""
    explorer_tab._active_preprocessing_settings = {}
    yield
    # Drain any pending Qt events queued during the test (e.g. from signal
    # emissions via preprocessing_widget).  Use removePostedEvents rather than
    # processEvents: the former cancels queued events (safe, no code executed)
    # while the latter executes them and can cause re-entrant crashes on Windows
    # in offscreen mode with PySide6 >= 6.7.
    #
    # macOS guard: mirrors all other per-test drain fixtures in this repo.
    # removePostedEvents corrupts pyqtgraph AllViews on macOS.
    if sys.platform == 'darwin':
        return
    try:
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.removePostedEvents(None, 0)
    except Exception:
        pass


def create_mock_recording(name="test.wcp", duration=1.0):
    recording = MagicMock(spec=Recording)
    recording.source_file = Path(name)
    recording.duration = duration
    recording.sampling_rate = 1000.0
    recording.max_trials = 10

    channel = MagicMock(spec=Channel)
    channel.name = "ch1"
    channel.units = "mV"
    channel.num_trials = 10
    channel.sampling_rate = 1000.0

    # Data
    t = np.linspace(0, duration, int(duration * 1000))
    d = np.zeros_like(t) + 10.0  # DC 10
    channel.get_data.return_value = d
    channel.get_relative_time_vector.return_value = t

    recording.channels = {"ch1": channel}
    return recording


def test_preprocessing_integration(explorer_tab, qtbot):
    """
    Verify that triggering preprocessing in the widget results in
    updated plots using the processed data.
    """
    # 1. Load Recording
    rec = create_mock_recording()
    explorer_tab.thread_pool = MagicMock()  # Block threads
    explorer_tab._display_recording(rec)

    # 2. Trigger Baseline Subtraction via Widget Signal
    # We simulate the signal emission
    settings = {'type': 'baseline', 'method': 'mean'}

    with patch('Synaptipy.core.signal_processor.subtract_baseline_mean') as mock_process:
        # Mock processor to return modified data
        mock_process.return_value = np.zeros(1000)  # Flat zero

        # Emit signal
        explorer_tab.preprocessing_widget.preprocessing_requested.emit(settings)

        # 3. Verify processor was called
        # The processing happens in _update_plot (on-the-fly) or via cache.
        # In current explorer, it stores _active_preprocessing_settings and calls _update_plot.
        # _update_plot calls signal_processor.

        assert explorer_tab._active_preprocessing_settings == {'baseline': settings}

        # Verify mock called (triggered by _update_plot)
        assert mock_process.called


def test_pipeline_transition_check(explorer_tab):
    """
    Test that will verify pipeline usage once refactored.
    Currently checks legacy dictionary method.
    """
    # Load mock recording first
    rec = create_mock_recording()
    explorer_tab.thread_pool = MagicMock()
    explorer_tab._display_recording(rec)

    settings = {'type': 'filter', 'method': 'lowpass', 'cutoff': 100}
    explorer_tab._handle_preprocessing_request(settings)
    assert explorer_tab._active_preprocessing_settings == {'filters': {'lowpass': settings}}
    # In future, we will check:
    # assert len(explorer_tab.pipeline.get_steps()) > 0
