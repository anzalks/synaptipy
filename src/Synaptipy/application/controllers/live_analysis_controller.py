import logging
from typing import Dict, Any, Optional

import numpy as np
from PySide6 import QtCore

from Synaptipy.core.results import SpikeTrainResult
from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold

log = logging.getLogger(__name__)


class AnalysisRunnable(QtCore.QRunnable):
    """
    Runnable worker for performing spike detection in a background thread.
    """

    class Signals(QtCore.QObject):
        result = QtCore.Signal(object)  # Emits SpikeTrainResult
        error = QtCore.Signal(str)

    def __init__(self, data: np.ndarray, time: np.ndarray, params: Dict[str, Any]):
        super().__init__()
        self.signals = self.Signals()
        self.data = data
        self.time = time
        self.params = params

    def run(self):
        try:
            # Extract parameters used by detect_spikes_threshold
            threshold = self.params.get("threshold", -20.0)
            refractory_sec = self.params.get("refractory_period", 0.002)

            # Convert refractory period to samples - we need sampling rate or dt for this. 
            # If time is provided, we can estimate dt.
            if len(self.time) > 1:
                dt = self.time[1] - self.time[0]
                fs = 1.0 / dt if dt > 0 else 10000.0  # Fallback
            else:
                fs = 10000.0 # Fallback

            refractory_samples = int(refractory_sec * fs)

            # Run Vectorized Detection
            result = detect_spikes_threshold(
                self.data, 
                self.time, 
                threshold, 
                refractory_samples,
                parameters=self.params
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
    sig_analysis_started = QtCore.Signal() # Optional: to show busy state

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Debounce Timer
        self.debounce_timer = QtCore.QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(50)  # 50ms wait
        self.debounce_timer.timeout.connect(self._execute_analysis)
        
        # Pending Request Data
        self._pending_data: Optional[np.ndarray] = None
        self._pending_time: Optional[np.ndarray] = None
        self._pending_params: Optional[Dict[str, Any]] = None
        
        # State
        self._is_running = False

    def request_analysis(self, data: np.ndarray, time: np.ndarray, params: Dict[str, Any]):
        """
        Public slot to request a new analysis run.
        Resets the debounce timer.
        """
        if data is None or time is None:
            return

        # Store latest request
        self._pending_data = data
        self._pending_time = time
        self._pending_params = params
        
        # Restart debounce timer - this effectively debounces by delaying execution
        self.debounce_timer.start()

    def _execute_analysis(self):
        """
        Called by timer timeout. Submits the job to thread pool.
        """
        if self._pending_data is None:
            return

        # Prepare Runnable
        # We need to define the runnable class inside or import it. It's defined above.
        runnable = AnalysisRunnable(
            self._pending_data, 
            self._pending_time, 
            self._pending_params.copy()
        )
        
        # Connect signals - using a lambda or direct connect depending on signature
        # Runnable signals are not standard QObjects in PySide potentially?
        # QRunnable is not a QObject, but we use a nested QObject for signals.
        runnable.signals.result.connect(self._on_result)
        runnable.signals.error.connect(self.sig_analysis_error.emit)
        
        self.sig_analysis_started.emit()
        QtCore.QThreadPool.globalInstance().start(runnable)

    def _on_result(self, result):
        """Forward result to UI."""
        self.sig_analysis_finished.emit(result)
