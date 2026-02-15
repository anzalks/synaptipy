# src/Synaptipy/application/controllers/live_analysis_controller.py
# -*- coding: utf-8 -*-
"""
Live Analysis Controller.
Coordinates real-time analysis (spikes, events) during navigation.
Enforces 'Single Source of Truth' by fetching data from DataCache.
"""
import logging
from typing import Dict, Any, Optional

import numpy as np
from PySide6 import QtCore

from Synaptipy.core.results import SpikeTrainResult
from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold
from Synaptipy.shared.data_cache import DataCache

log = logging.getLogger(__name__)


class AnalysisRunnable(QtCore.QRunnable):
    """
    Runnable worker for performing spike detection in a background thread.
    """

    class Signals(QtCore.QObject):
        result = QtCore.Signal(object)  # Emits SpikeTrainResult
        error = QtCore.Signal(str)

    def __init__(self, data: np.ndarray, fs: float, params: Dict[str, Any], metadata: Dict[str, Any] = None):
        super().__init__()
        self.signals = self.Signals()
        self.data = data
        self.fs = fs
        self.params = params
        self.metadata = metadata or {}

    def run(self):
        try:
            # Extract parameters
            threshold = self.params.get("threshold", -20.0)
            refractory_sec = self.params.get("refractory_period", 0.002)

            # Convert refractory period to samples
            fs = self.fs if self.fs > 0 else 10000.0
            refractory_samples = int(refractory_sec * fs)

            # Generate time vector if needed by detection (usually it generates indices)
            # detect_spikes_threshold expects time array or we can adapt it.
            # Looking at signature: (data, time_vector, ...)
            # We can generate relative time vector from fs
            time_vector = np.arange(len(self.data)) / fs

            # Run Vectorized Detection
            # Note: We pass the params dict as 'parameters' to be stored in result
            result = detect_spikes_threshold(
                self.data, 
                time_vector, 
                threshold, 
                refractory_samples,
                parameters={**self.params, **self.metadata}
            )
            
            self.signals.result.emit(result)

        except Exception as e:
            log.error(f"Error in AnalysisRunnable: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class LiveAnalysisController(QtCore.QObject):
    """
    Bridge between UI inputs and the vectorized backend.
    Handles debouncing and threading.
    """

    sig_analysis_finished = QtCore.Signal(object)  # SpikeTrainResult
    sig_analysis_error = QtCore.Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Debounce Timer
        self.debounce_timer = QtCore.QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(50)  # 50ms wait
        self.debounce_timer.timeout.connect(self._execute_analysis)
        
        # Store params only - Data comes from DataCache
        self._pending_params: Optional[Dict[str, Any]] = None
        
        # Thread Pool
        self.thread_pool = QtCore.QThreadPool.globalInstance()

    def request_analysis(self, params: Dict[str, Any]):
        """
        Public slot to request a new analysis run.
        Resets the debounce timer.
        
        Args:
            params: Analysis parameters (threshold, etc.)
        """
        self._pending_params = params
        # Restart debounce timer
        self.debounce_timer.start()

    def _execute_analysis(self):
        """
        Called by timer timeout. Fetches ACTIVE TRACE from DataCache.
        """
        cache = DataCache.get_instance()
        active_trace = cache.get_active_trace()
        
        if not active_trace:
            log.debug("LiveAnalysis: No active trace in DataCache. Skipping.")
            return

        data, fs, metadata = active_trace
        
        if data is None or len(data) == 0:
            return

        if self._pending_params is None:
            # Should not happen if triggered by request, but possible if timer expired
            # without params (unlikely)
            return

        # Prepare Runnable
        runnable = AnalysisRunnable(
            data, 
            fs, 
            self._pending_params.copy(),
            metadata
        )
        
        runnable.signals.result.connect(self._on_result)
        runnable.signals.error.connect(self.sig_analysis_error.emit)
        
        self.thread_pool.start(runnable)

    def _on_result(self, result: SpikeTrainResult):
        """
        Handle analysis completion.
        1. Update Data Model (if applicable).
        2. Emit signal for UI.
        """
        self.sig_analysis_finished.emit(result)

    def cleanup(self):
        """Stop any pending analysis and timers."""
        if self.debounce_timer.isActive():
            self.debounce_timer.stop()
        # Optional: Cancel running runnables if we had handles, but QThreadPool manages them.
