# tests/application/test_live_analysis_controller.py
# -*- coding: utf-8 -*-
"""
Tests for application/controllers/live_analysis_controller.py.

Covers previously uncovered lines:
  40-65  : AnalysisRunnable.run() - full spike detection path + error path
  112-113: _execute_analysis when no active trace in DataCache
  118    : _execute_analysis when data is None / empty
  123    : _execute_analysis when _pending_params is None
  139    : cleanup() stops active debounce timer
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from Synaptipy.application.controllers.live_analysis_controller import (
    AnalysisRunnable,
    LiveAnalysisController,
)
from Synaptipy.core.results import SpikeTrainResult

# ---------------------------------------------------------------------------
# AnalysisRunnable
# ---------------------------------------------------------------------------


class TestAnalysisRunnable:
    """Test the worker runnable that performs spike detection."""

    def test_run_emits_result(self, qtbot):
        """Lines 40-65: successful spike detection emits result signal."""
        rng = np.random.default_rng(0)
        # 1-second trace at 10 kHz – flat noise; threshold set very high so zero spikes
        data = rng.normal(-65.0, 0.5, 10_000)
        params = {"threshold": 20.0, "refractory_period": 0.002}

        runnable = AnalysisRunnable(data, fs=10_000.0, params=params, metadata={"channel": "Ch0"})
        received = []
        runnable.signals.result.connect(received.append)

        # Run synchronously (not via thread pool) for determinism
        runnable.run()

        assert len(received) == 1
        assert isinstance(received[0], SpikeTrainResult)

    def test_run_handles_exception_emits_error(self, qtbot):
        """AnalysisRunnable emits error signal when detect_spikes_threshold raises."""
        data = np.zeros(100)
        params = {"threshold": -20.0}

        runnable = AnalysisRunnable(data, fs=10_000.0, params=params)
        errors = []
        runnable.signals.error.connect(errors.append)

        with patch(
            "Synaptipy.application.controllers.live_analysis_controller.detect_spikes_threshold",
            side_effect=ValueError("Boom"),
        ):
            runnable.run()

        assert len(errors) == 1
        assert "Boom" in errors[0]

    def test_run_zero_fs_uses_fallback(self, qtbot):
        """AnalysisRunnable must not divide by zero when fs=0; uses fallback 10000."""
        data = np.zeros(100)
        params = {"threshold": -20.0}

        runnable = AnalysisRunnable(data, fs=0.0, params=params)
        received = []
        runnable.signals.result.connect(received.append)
        runnable.run()

        assert len(received) == 1

    def test_run_includes_metadata_in_params(self, qtbot):
        """Metadata dict is merged into the params passed to detect_spikes_threshold."""
        data = np.zeros(100)
        params = {"threshold": -20.0}
        meta = {"recording_id": "test_01"}

        captured_params = {}

        def fake_detect(data, time_vector, threshold, refractory, parameters=None):
            captured_params.update(parameters or {})
            return SpikeTrainResult(spike_times=np.array([]), parameters=parameters)

        with patch(
            "Synaptipy.application.controllers.live_analysis_controller.detect_spikes_threshold",
            side_effect=fake_detect,
        ):
            runnable = AnalysisRunnable(data, fs=10_000.0, params=params, metadata=meta)
            runnable.run()

        assert captured_params.get("recording_id") == "test_01"


# ---------------------------------------------------------------------------
# LiveAnalysisController
# ---------------------------------------------------------------------------


class TestLiveAnalysisController:
    def setup_method(self):
        self.controller = LiveAnalysisController()

    def teardown_method(self):
        self.controller.cleanup()
        self.controller.deleteLater()

    def test_no_active_trace_skips_analysis(self, qtbot):
        """Lines 112-113: no active trace in DataCache → analysis is skipped."""
        mock_cache = MagicMock()
        mock_cache.get_active_trace.return_value = None

        with patch(
            "Synaptipy.application.controllers.live_analysis_controller.DataCache.get_instance",
            return_value=mock_cache,
        ):
            self.controller._pending_params = {"threshold": -20.0}
            self.controller._execute_analysis()

        # No result emitted
        received = []
        self.controller.sig_analysis_finished.connect(received.append)
        assert len(received) == 0

    def test_empty_data_skips_analysis(self, qtbot):
        """Line 118: data is empty array → analysis is skipped."""
        mock_cache = MagicMock()
        mock_cache.get_active_trace.return_value = (np.array([]), 10_000.0, {})

        with patch(
            "Synaptipy.application.controllers.live_analysis_controller.DataCache.get_instance",
            return_value=mock_cache,
        ):
            self.controller._pending_params = {"threshold": -20.0}
            self.controller._execute_analysis()

        received = []
        self.controller.sig_analysis_finished.connect(received.append)
        assert len(received) == 0

    def test_none_data_skips_analysis(self, qtbot):
        """Line 118: data is None → analysis is skipped."""
        mock_cache = MagicMock()
        mock_cache.get_active_trace.return_value = (None, 10_000.0, {})

        with patch(
            "Synaptipy.application.controllers.live_analysis_controller.DataCache.get_instance",
            return_value=mock_cache,
        ):
            self.controller._pending_params = {"threshold": -20.0}
            self.controller._execute_analysis()

        received = []
        self.controller.sig_analysis_finished.connect(received.append)
        assert len(received) == 0

    def test_no_pending_params_skips_analysis(self, qtbot):
        """Line 123: _pending_params is None → analysis is skipped."""
        rng = np.random.default_rng(1)
        mock_cache = MagicMock()
        mock_cache.get_active_trace.return_value = (rng.normal(-65, 1, 1000), 10_000.0, {})

        with patch(
            "Synaptipy.application.controllers.live_analysis_controller.DataCache.get_instance",
            return_value=mock_cache,
        ):
            self.controller._pending_params = None
            self.controller._execute_analysis()

        received = []
        self.controller.sig_analysis_finished.connect(received.append)
        assert len(received) == 0

    def test_cleanup_stops_active_timer(self):
        """Line 139: cleanup() stops the debounce timer if it is active."""
        # Start the timer
        self.controller.debounce_timer.start()
        assert self.controller.debounce_timer.isActive()

        self.controller.cleanup()
        assert not self.controller.debounce_timer.isActive()

    def test_cleanup_when_timer_inactive_is_noop(self):
        """cleanup() must not raise when timer is already stopped."""
        assert not self.controller.debounce_timer.isActive()
        self.controller.cleanup()  # Should not raise

    def test_request_analysis_stores_params_and_starts_timer(self):
        """request_analysis() stores params and starts debounce timer."""
        params = {"threshold": -30.0}
        self.controller.request_analysis(params)
        assert self.controller._pending_params == params
        assert self.controller.debounce_timer.isActive()

    def test_on_result_emits_sig_analysis_finished(self, qtbot):
        """_on_result() re-emits the result via sig_analysis_finished."""
        mock_result = MagicMock(spec=SpikeTrainResult)
        received = []
        self.controller.sig_analysis_finished.connect(received.append)
        self.controller._on_result(mock_result)
        assert len(received) == 1
        assert received[0] is mock_result
