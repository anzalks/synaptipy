# src/Synaptipy/application/gui/analysis_worker.py
# -*- coding: utf-8 -*-
"""
Worker classes for running analysis tasks in background threads.

Provides three worker types:

* :class:`AnalysisWorker` — lightweight :class:`~PySide6.QtCore.QRunnable` for
  arbitrary callables (existing API, unchanged).
* :class:`BatchWorker` — :class:`~PySide6.QtCore.QThread` specialised for
  :class:`~Synaptipy.core.analysis.batch_engine.BatchAnalysisEngine` batch runs.
  Emits rich progress signals so the GUI remains 100% responsive.
* :class:`NwbExportWorker` — :class:`~PySide6.QtCore.QThread` for NWB file
  export.  Keeps the UI thread free during potentially slow HDF5 writes.
"""

import logging
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from PySide6 import QtCore

if TYPE_CHECKING:
    from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
    from Synaptipy.core.data_model import Recording
    from Synaptipy.infrastructure.exporters import NWBExporter

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
        except Exception:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


# ---------------------------------------------------------------------------
# BatchWorker — QThread for BatchAnalysisEngine
# ---------------------------------------------------------------------------


class BatchWorker(QtCore.QThread):
    """QThread wrapper for :class:`~Synaptipy.core.analysis.batch_engine.BatchAnalysisEngine`.

    All signals are emitted on the **GUI thread** (Qt's cross-thread signal
    delivery guarantee), so callers can safely update progress bars, log
    widgets, and result tables without manual ``QMetaObject.invokeMethod`` calls.

    Signals:
        progress: ``(current: int, total: int, message: str)`` — fired for each
            completed file, suitable for a :class:`~PySide6.QtWidgets.QProgressBar`.
        batch_finished: ``pandas.DataFrame`` — the complete aggregated result table,
            emitted once after all files are done (or after cancellation).
        batch_error: ``str`` — error message if an unhandled exception escapes the
            engine (individual file errors are captured inside the engine and end up
            as error rows in *batch_finished*).
    """

    progress = QtCore.Signal(int, int, str)
    batch_finished = QtCore.Signal(object)  # pandas.DataFrame
    batch_error = QtCore.Signal(str)

    def __init__(
        self,
        engine: "BatchAnalysisEngine",
        files: List,
        pipeline_config: List,
        channel_filter: Optional[List[str]] = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        """
        Initialise the batch worker.

        Args:
            engine: A configured :class:`BatchAnalysisEngine` instance.  Its
                :attr:`~BatchAnalysisEngine.max_workers` attribute controls whether
                the engine uses :class:`~concurrent.futures.ProcessPoolExecutor`
                internally.
            files: List of file paths or pre-loaded Recording objects.
            pipeline_config: Analysis pipeline configuration (list of task dicts).
            channel_filter: Optional list of channel names/IDs to restrict analysis to.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._engine = engine
        self._files = files
        self._pipeline_config = pipeline_config
        self._channel_filter = channel_filter

    def run(self) -> None:
        """Execute the batch run — called automatically by :meth:`QThread.start`."""
        try:
            df = self._engine.run_batch(
                self._files,
                self._pipeline_config,
                progress_callback=self._on_progress,
                channel_filter=self._channel_filter,
            )
            self.batch_finished.emit(df)
        except Exception:  # noqa: BLE001
            log.exception("BatchWorker: unhandled exception.")
            self.batch_error.emit(traceback.format_exc())

    def _on_progress(self, current: int, total: int, msg: str) -> None:
        """Relay engine progress callbacks to the GUI via Qt signal."""
        self.progress.emit(current, total, msg)

    def cancel(self) -> None:
        """Request the engine to stop after the current file completes."""
        if self._engine is not None:
            self._engine.cancel()
            log.debug("BatchWorker: cancellation requested.")


# ---------------------------------------------------------------------------
# NwbExportWorker — QThread for NWB file export
# ---------------------------------------------------------------------------


class NwbExportWorker(QtCore.QThread):
    """QThread wrapper for :class:`~Synaptipy.infrastructure.exporters.NWBExporter`.

    Running the NWB export on the UI thread blocks for several seconds on large
    recordings (pynwb serialises to HDF5 synchronously).  This worker moves the
    export to a background thread while the GUI stays responsive.

    Signals:
        export_finished: ``str`` — absolute path of the written NWB file.
        export_error: ``str`` — human-readable error message on failure.
    """

    export_finished = QtCore.Signal(str)  # output_filepath as str
    export_error = QtCore.Signal(str)

    def __init__(
        self,
        exporter: "NWBExporter",
        recording: "Recording",
        output_filepath: Path,
        nwb_metadata: Dict,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        """Initialise the NWB export worker.

        Args:
            exporter: A configured :class:`NWBExporter` instance.
            recording: The :class:`~Synaptipy.core.data_model.Recording` to export.
            output_filepath: Destination path for the ``.nwb`` file.
            nwb_metadata: Metadata dict accepted by :meth:`NWBExporter.export`.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._exporter = exporter
        self._recording = recording
        self._output_filepath = output_filepath
        self._nwb_metadata = nwb_metadata

    def run(self) -> None:
        """Execute the NWB export — called automatically by :meth:`QThread.start`."""
        try:
            self._exporter.export(self._recording, self._output_filepath, self._nwb_metadata)
            self.export_finished.emit(str(self._output_filepath))
        except Exception:  # noqa: BLE001
            log.exception("NwbExportWorker: unhandled exception.")
            self.export_error.emit(traceback.format_exc())
