# tests/application/test_ux_layer.py
from unittest.mock import MagicMock, patch
import numpy as np
from PySide6 import QtCore, QtGui

from Synaptipy.shared.data_cache import DataCache
from Synaptipy.application.controllers.shortcut_manager import ShortcutManager
from Synaptipy.application.controllers.analysis_formatter import AnalysisResultFormatter
from Synaptipy.core.results import SpikeTrainResult
from Synaptipy.application.controllers.live_analysis_controller import LiveAnalysisController

# --- DataCache Tests ---


def test_datacache_singleton():
    c1 = DataCache.get_instance()
    c2 = DataCache.get_instance()
    assert c1 is c2


def test_datacache_active_trace():
    cache = DataCache.get_instance()
    cache.clear_active_trace()
    assert cache.get_active_trace() is None

    data = np.zeros(100)
    fs = 1000.0
    meta = {"channel_id": 1}

    cache.set_active_trace(data, fs, meta)

    trace = cache.get_active_trace()
    assert trace is not None
    assert np.array_equal(trace[0], data)
    assert trace[1] == fs
    assert trace[2] == meta

    cache.clear_active_trace()
    assert cache.get_active_trace() is None

# --- ShortcutManager Tests ---


def test_shortcut_manager_space():
    mock_nav = MagicMock()
    manager = ShortcutManager(navigation_controller=mock_nav)

    event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Space, QtCore.Qt.NoModifier)
    handled = manager.handle_key_press(event)

    assert handled is True
    mock_nav.next_file.assert_called_once()


def test_shortcut_manager_ignore_loops():
    mock_nav = MagicMock()
    manager = ShortcutManager(navigation_controller=mock_nav)

    event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_A, QtCore.Qt.NoModifier)
    handled = manager.handle_key_press(event)

    assert handled is False
    mock_nav.next_file.assert_not_called()

# --- AnalysisFormatter Tests ---


def test_analysis_formatter_spike_result():
    # Test with Dict
    res_dict = {
        "analysis_type": "Spike Detection (Threshold)",
        "spike_count": 10,
        "average_firing_rate_hz": 5.5,
        "threshold": -20,
        "threshold_units": "mV"
    }
    val, details = AnalysisResultFormatter.format_result(res_dict)
    assert "10 spikes" in val
    assert "5.50 Hz" in val
    assert "Threshold: -20.0 mV" in details[0]

    # Test with Object
    res_obj = SpikeTrainResult(
        value=10.0,  # Dummy for base class
        unit="Hz",  # Dummy for base class
        spike_times=np.array([0.1, 0.2, 0.3]),
        spike_indices=np.array([100, 200, 300]),
        mean_frequency=10.0,
        parameters={"threshold": -30, "refractory_period": 0.002}
    )
    val2, details2 = AnalysisResultFormatter.format_result(res_obj)
    assert "3 spikes" in val2
    assert "10.00 Hz" in val2
    assert "Threshold: -30.0 mV" in details2[0]
    assert "Refractory: 2.0 ms" in details2[1]

# --- LiveAnalysisController Tests ---


@patch("Synaptipy.application.controllers.live_analysis_controller.DataCache")
def test_live_analysis_controller_fetch(mock_datacache_cls, qtbot):
    # Setup Mock DataCache
    mock_instance = MagicMock()
    mock_datacache_cls.get_instance.return_value = mock_instance

    data = np.zeros(1000)
    fs = 10000.0
    mock_instance.get_active_trace.return_value = (data, fs, {})

    controller = LiveAnalysisController()
    # qtbot.addWidget(controller) # Removed: Controller is QObject not Widget

    # Request analysis
    params = {"threshold": -20.0}
    controller.request_analysis(params)

    # Since it uses a timer (50ms), we need to wait or force call
    # Let's force call _execute_analysis directly to avoid waiting/async issues
    # But wait, threading?
    # We patch thread_pool start to run synchronously or verify call

    with patch.object(controller.thread_pool, 'start') as mock_start:
        controller._execute_analysis()

        # Verify it called get_active_trace
        mock_instance.get_active_trace.assert_called()

        # Verify it started a runnable
        mock_start.assert_called_once()

    controller.cleanup()
