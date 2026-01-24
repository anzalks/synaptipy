# src/Synaptipy/application/gui/analysis_worker.py
# -*- coding: utf-8 -*-
"""
Worker class for running analysis tasks in a background thread.
"""
import logging
import traceback
import sys
from typing import Callable, Dict, Any, Optional

from PySide6 import QtCore

log = logging.getLogger(__name__)

class WorkerSignals(QtCore.QObject):
    """
    Defines the signals available from a running worker thread.
    Supported signals are:
    finished
        No data
    error
        tuple (exctype, value, traceback.format_exc() )
    result
        object data returned from processing, anything
    """
    finished = QtCore.Signal()
    error = QtCore.Signal(tuple)
    result = QtCore.Signal(object)

class AnalysisWorker(QtCore.QRunnable):
    """
    Worker thread for running analysis functions.
    Inherits from QRunnable to handle worker thread setup, signals and wrap-up.

    :param fn: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function
    """

    def __init__(self, fn: Callable, *args, **kwargs):
        super(AnalysisWorker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done
