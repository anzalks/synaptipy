# -*- coding: utf-8 -*-
"""
Synaptipy Plugin for miniML Event Detection
https://github.com/delvendahl/miniML

This file is a **GUI plugin template** for Synaptipy's @AnalysisRegistry
system. It is NOT a standalone script. Drop it (or a copy) into
~/.synaptipy/plugins/ and enable "Enable Custom Plugins" in
Edit > Preferences to have it appear as a tab in the Analyser.

miniML is NOT a pip-installable package. It must be cloned from GitHub and
its core/ directory must be reachable from Python.

Setup (3 steps):
    1. Clone miniML once (outside the Synaptipy directory):
           git clone https://github.com/delvendahl/miniML.git ~/PycharmProjects/miniML

    2. Install miniML Python dependencies into your Synaptipy environment:
           conda activate synaptipy
           pip install "tensorflow>=2.12,<2.16" h5py scikit-learn ruptures==1.1.10

    3. In the Analyser "miniML Events" tab:
       - Paste the full path to the miniML core/ directory into "miniML core/ Path"
         e.g. /Users/you/PycharmProjects/miniML/core
       - Paste the full path to your .h5 model file into "Model Path (.h5)"
         e.g. /Users/you/PycharmProjects/miniML/models/GC_mEPSC_model.h5
       - Click Run Analysis.

miniML class API (as of commit 9bab948):
    MiniTrace(data, sampling_interval=<1/fs in seconds>)
    EventDetection(data=trace, event_direction='negative'|'positive',
                   model_path=<str>, model_threshold=<float>, batch_size=<int>)
    detector.detect_events()   # populates event_locations (sample indices)
    trace.sampling             # sampling interval in seconds (= 1/fs)
"""

import contextlib
import io
import logging
import sys
import traceback
from typing import Any, Dict

import numpy as np

from synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


class _StreamToLogger(io.TextIOBase):
    """Redirect a stream (stdout/stderr) to a Python logger line by line."""

    def __init__(self, logger: logging.Logger, level: int = logging.INFO) -> None:
        super().__init__()
        self._logger = logger
        self._level = level
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            stripped = line.rstrip()
            if stripped:
                self._logger.log(self._level, "%s", stripped)
        return len(s)

    def flush(self) -> None:
        if self._buf.strip():
            self._logger.log(self._level, "%s", self._buf.rstrip())
            self._buf = ""


def _import_miniml(miniml_core_path: str):
    """Lazily import miniML classes after adding core/ to sys.path.

    Returns (MiniTrace, EventDetection) or raises ImportError.
    """
    import os

    core_path = miniml_core_path.strip()
    if not core_path:
        raise ImportError(
            "miniML core/ path is empty. "
            "Paste the path to the miniML/core/ directory "
            "(the folder containing miniML.py) into the 'miniML core/ Path' field."
        )
    # TensorFlow >= 2.16 ships Keras 3 by default; .h5 models saved under
    # Keras 2 require the tf_keras compatibility layer.  Setting this env var
    # before TF imports redirects tf.keras → tf_keras (Keras 2 API).
    os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    try:
        import importlib

        miniml_mod = importlib.import_module("miniML")
        MiniTrace = miniml_mod.MiniTrace
        EventDetection = miniml_mod.EventDetection
    except Exception as exc:
        raise ImportError(
            f"Could not import miniML from '{core_path}': {type(exc).__name__}: {exc}. "
            "Make sure the path points to the miniML/core/ directory "
            "(the folder that contains miniML.py and miniML_functions.py)."
        ) from exc
    return MiniTrace, EventDetection


def _locate_event_peaks(
    data: np.ndarray,
    ev_locs: np.ndarray,
    valid_mask: np.ndarray,
    direction: str,
    window_size: int,
    sampling_interval: float,
    time_start: float,
):
    """Map validated onset indices to amplitude-peak times and data values."""
    valid_locs = ev_locs[valid_mask]
    if valid_locs.size == 0:
        return [], []
    half_win = max(1, window_size // 2)
    find_extremum = np.argmin if direction == "negative" else np.argmax
    peak_indices = np.empty(len(valid_locs), dtype=np.int64)
    for k, onset in enumerate(valid_locs):
        end_idx = min(int(onset) + half_win, len(data))
        seg = data[int(onset) : end_idx]
        peak_indices[k] = onset + find_extremum(seg) if len(seg) > 0 else onset
    ev_times = (peak_indices * sampling_interval + time_start).tolist()
    ev_peaks = data[peak_indices].tolist()
    return ev_times, ev_peaks


def _compute_event_scores(detector: Any, ev_locs: np.ndarray, valid_mask: np.ndarray):
    """Extract per-event confidence scores from the detector if available."""
    if hasattr(detector, "event_scores") and len(detector.event_scores) == len(ev_locs):
        scores_arr = np.asarray(detector.event_scores)[valid_mask]
        if len(scores_arr) > 0:
            return (
                scores_arr.tolist(),
                round(float(np.mean(scores_arr)), 4),
                round(float(np.min(scores_arr)), 4),
            )
    return None, None, None


def run_miniml_detection(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    threshold: float = 0.5,
    direction: str = "negative",
    model_path: str = "",
    miniml_core_path: str = "",
    batch_size: int = 512,
    window_size: int = 600,
    rel_prom_cutoff: float = 0.25,
    convolve_win: int = 20,
    gradient_convolve_win: int = 40,
) -> Dict[str, Any]:
    """Run miniML inference on a single trial and return event metrics.

    Parameters
    ----------
    data:
        Raw voltage or current trace (1-D NumPy array).
    time:
        Corresponding time vector (seconds).
    sampling_rate:
        Acquisition sampling rate in Hz.
    threshold:
        miniML model_threshold in [0, 1]. Higher values reduce false positives.
    direction:
        ``"negative"`` for inward currents; ``"positive"`` for outward events.
    model_path:
        Absolute path to the miniML ``.h5`` model file.
    miniml_core_path:
        Absolute path to the miniML ``core/`` directory.
    batch_size:
        Inference batch size. Larger values are faster but use more RAM.
    window_size:
        Detection window size in samples.
    rel_prom_cutoff:
        Sensitivity for overlapping events (relative prominence cutoff).
    convolve_win:
        Smoothing filter window size in samples.
    gradient_convolve_win:
        Gradient filter window size in samples.

    Returns
    -------
    dict
        ``Event_Count``, ``Frequency_Hz``, ``Model_Used`` are shown in the
        results table. ``_event_times`` and ``_event_peaks`` drive the marker
        overlay on the plot.
    """
    if data.size == 0:
        return {"error": "Empty data array provided."}

    active_model = model_path.strip()
    if not active_model:
        return {
            "error": (
                "No model path provided. " "Paste the full path to your .h5 model file into the 'Model Path' field."
            )
        }

    try:
        MiniTrace, EventDetection = _import_miniml(miniml_core_path)
    except ImportError as exc:
        return {"error": str(exc)}

    log.info("miniML: libraries imported from '%s'", miniml_core_path.strip())

    try:
        sampling_interval = 1.0 / sampling_rate  # seconds per sample
        trace = MiniTrace(data=data, sampling_interval=sampling_interval)
        log.info(
            "miniML: trace - %.3f s at %.0f Hz (%d samples)",
            float(time[-1] - time[0]),
            sampling_rate,
            data.size,
        )
        detector = EventDetection(
            data=trace,
            event_direction=direction,
            model_path=active_model,
            model_threshold=threshold,
            batch_size=batch_size,
            window_size=window_size,
        )
        log.info(
            "miniML: running inference (batch=%d, threshold=%.2f, direction=%s)...",
            batch_size,
            threshold,
            direction,
        )
        _stdout_capture = _StreamToLogger(log, logging.INFO)
        _stderr_capture = _StreamToLogger(log, logging.WARNING)
        with contextlib.redirect_stdout(_stdout_capture), contextlib.redirect_stderr(_stderr_capture):
            detector.detect_events(
                eval=True,
                rel_prom_cutoff=rel_prom_cutoff,
                convolve_win=convolve_win,
                gradient_convolve_win=gradient_convolve_win,
            )
        _stdout_capture.flush()
        _stderr_capture.flush()
        log.info(
            "miniML: inference done - %d raw locations",
            len(getattr(detector, "event_locations", [])),
        )
    except Exception as e:
        log.error("miniML detection failed:\n%s", traceback.format_exc())
        return {"error": f"miniML inference error: {str(e)}"}

    # event_locations: 1-D int array of onset sample indices (steepest-slope point).
    # Shift each marker to the amplitude peak within the next window_size//2 samples.
    ev_locs = np.asarray(detector.event_locations, dtype=np.int64)
    valid_mask = (ev_locs >= 0) & (ev_locs < len(data))
    ev_times, ev_peaks = _locate_event_peaks(
        data, ev_locs, valid_mask, direction, window_size, sampling_interval, time[0]
    )

    duration = float(time[-1] - time[0]) if len(time) > 1 else 0.0
    freq = float(len(ev_times)) / duration if duration > 0 else 0.0
    model_label = active_model.replace("\\", "/").split("/")[-1]

    # Per-event amplitudes: data values at amplitude-peak positions.
    if len(ev_peaks) > 0:
        amps_arr = np.array(ev_peaks)
        mean_amp = round(float(np.mean(amps_arr)), 4)
        std_amp = round(float(np.std(amps_arr)), 4)
    else:
        mean_amp = None
        std_amp = None

    # Inter-event intervals in milliseconds.
    if len(ev_times) >= 2:
        iei_arr = np.diff(np.array(ev_times)) * 1000.0
        mean_iei = round(float(np.mean(iei_arr)), 4)
        std_iei = round(float(np.std(iei_arr)), 4)
    else:
        mean_iei = None
        std_iei = None

    # Per-event model confidence scores (miniML >= certain versions).
    ev_scores, mean_score, min_score = _compute_event_scores(detector, ev_locs, valid_mask)

    log.info(
        "miniML: %d events | %.2f Hz | mean amplitude %.1f pA | mean IEI %.1f ms",
        len(ev_times),
        freq,
        mean_amp if mean_amp is not None else float("nan"),
        mean_iei if mean_iei is not None else float("nan"),
    )
    if mean_score is not None:
        log.info("miniML: mean model score = %.3f (min = %.3f)", mean_score, min_score)

    return {
        "Event_Count": len(ev_times),
        "Frequency_Hz": round(freq, 2),
        "Model_Used": model_label,
        "Mean_Amplitude_pA": mean_amp,
        "Std_Amplitude_pA": std_amp,
        "Mean_IEI_ms": mean_iei,
        "Std_IEI_ms": std_iei,
        "Mean_Score": mean_score,
        "Min_Score": min_score,
        "_event_times": ev_times,
        "_event_peaks": ev_peaks,
        "_event_scores": ev_scores,
        "_event_amplitudes": ev_peaks,
    }


@AnalysisRegistry.register(
    name="miniml_events",
    label="miniML Events",
    expects_list=False,
    run_button=True,
    ui_params=[
        {
            "name": "miniml_core_path",
            "label": "miniML core/ Path:",
            "type": "dirpath",
            "default": "",
            "placeholder": "/path/to/miniML/core",
            "tooltip": (
                "Absolute path to the miniML/core/ directory "
                "(the folder containing miniML.py). "
                "Clone miniML from https://github.com/delvendahl/miniML"
            ),
        },
        {
            "name": "model_path",
            "label": "Model Path (.h5):",
            "type": "filepath",
            "default": "",
            "placeholder": "/path/to/miniML/models/GC_lstm_model.h5",
            "tooltip": (
                "Absolute path to the miniML Keras model file (.h5). "
                "Model files live in the miniML/models/ directory of the cloned repo."
            ),
        },
        {
            "name": "threshold",
            "label": "Prediction Threshold:",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "decimals": 2,
            "tooltip": "miniML score cutoff [0, 1]. Higher = fewer false positives.",
        },
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
            "tooltip": "negative = inward currents (mEPSCs/IPSCs); positive = outward events.",
        },
        {
            "name": "batch_size",
            "label": "Batch Size:",
            "type": "int",
            "default": 512,
            "min": 1,
            "max": 4096,
            "tooltip": "Inference batch size (miniML default: 512). Reduce if out of memory.",
        },
        {
            "name": "window_size",
            "label": "Window Size (samples):",
            "type": "int",
            "default": 600,
            "min": 1,
            "max": 10000,
            "tooltip": "Detection window size",
        },
        {
            "name": "rel_prom_cutoff",
            "label": "Rel. Prominence Cutoff:",
            "type": "float",
            "default": 0.25,
            "min": 0.0,
            "max": 1.0,
            "decimals": 3,
            "tooltip": "Sensitivity for overlapping events (miniML default: 0.25)",
        },
        {
            "name": "convolve_win",
            "label": "Convolve Window:",
            "type": "int",
            "default": 20,
            "min": 0,
            "max": 1000,
            "tooltip": "Hann window size for smoothing (miniML default: 20; 0 = use lowpass filter instead)",
        },
        {
            "name": "gradient_convolve_win",
            "label": "Gradient Convolve Window:",
            "type": "int",
            "default": 40,
            "min": 1,
            "max": 500,
            "tooltip": "Hann window size for gradient smoothing (miniML default: 2 x convolve_win = 40)",
        },
    ],
    plots=[
        {
            "type": "markers",
            "x": "_event_times",
            "y": "_event_peaks",
            "color": "r",
            "symbol": "o",
            "tooltip": "miniML Detected Events",
        }
    ],
)
def run_miniml_events_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Synaptipy registry wrapper for miniML event detection.

    Delegates to :func:`run_miniml_detection`.  All keyword arguments are
    populated automatically from the ``ui_params`` widgets when the user
    clicks **Run Analysis**.

    Columns returned in the results table / CSV export:

    ========================  ================================================
    Key                       Description
    ========================  ================================================
    ``Event_Count``           Number of detected events
    ``Frequency_Hz``          Event frequency (events / recording duration)
    ``Model_Used``            Filename of the .h5 model
    ``Mean_Amplitude_pA``     Mean amplitude at the peak of each event
    ``Std_Amplitude_pA``      Standard deviation of per-event amplitudes
    ``Mean_IEI_ms``           Mean inter-event interval in milliseconds
    ``Std_IEI_ms``            Standard deviation of IEI in milliseconds
    ``Mean_Score``            Mean miniML model confidence score (if available)
    ``Min_Score``             Minimum confidence score (quality filter proxy)
    ``_event_times``          Per-event peak times (s) — drives marker overlay
    ``_event_peaks``          Per-event amplitude values — drives marker overlay
    ``_event_scores``         Per-event confidence scores list (private)
    ``_event_amplitudes``     Per-event amplitudes list (private, same as peaks)
    ========================  ================================================
    """
    return run_miniml_detection(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        threshold=kwargs.get("threshold", 0.5),
        direction=kwargs.get("direction", "negative"),
        batch_size=kwargs.get("batch_size", 512),
        model_path=kwargs.get("model_path", ""),
        miniml_core_path=kwargs.get("miniml_core_path", ""),
        window_size=kwargs.get("window_size", 600),
        rel_prom_cutoff=kwargs.get("rel_prom_cutoff", 0.25),
        convolve_win=kwargs.get("convolve_win", 20),
        gradient_convolve_win=kwargs.get("gradient_convolve_win", 40),
    )
