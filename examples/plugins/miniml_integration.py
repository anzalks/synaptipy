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

import logging
import sys
import traceback
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


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


def run_miniml_detection(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    threshold: float = 0.5,
    direction: str = "negative",
    model_path: str = "",
    miniml_core_path: str = "",
    batch_size: int = 64,
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

    try:
        sampling_interval = 1.0 / sampling_rate  # seconds per sample
        trace = MiniTrace(data=data, sampling_interval=sampling_interval)
        detector = EventDetection(
            data=trace,
            event_direction=direction,
            model_path=active_model,
            model_threshold=threshold,
            batch_size=batch_size,
        )
        detector.detect_events()
    except Exception as e:
        log.error("miniML detection failed:\n%s", traceback.format_exc())
        return {"error": f"miniML inference error: {str(e)}"}

    # event_locations: 1-D int array of sample indices
    ev_locs = np.asarray(detector.event_locations, dtype=np.int64)
    if ev_locs.size == 0:
        ev_times: np.ndarray = np.array([], dtype=float)
        ev_peaks: np.ndarray = np.array([], dtype=float)
    else:
        ev_times = ev_locs * sampling_interval + time[0]
        valid = ev_locs[ev_locs < len(data)]
        ev_peaks = data[valid] if valid.size > 0 else np.array([], dtype=float)
        if valid.size < ev_locs.size:
            ev_times = ev_times[: valid.size]

    duration = time[-1] - time[0] if len(time) > 1 else 0.0
    freq = float(len(ev_times)) / duration if duration > 0 else 0.0
    model_label = active_model.replace("\\", "/").split("/")[-1]

    return {
        "Event_Count": len(ev_times),
        "Frequency_Hz": round(freq, 2),
        "Model_Used": model_label,
        "_event_times": ev_times,
        "_event_peaks": ev_peaks,
    }


@AnalysisRegistry.register(
    name="miniml_events",
    label="miniML Events",
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
            "default": 64,
            "min": 1,
            "max": 1024,
            "tooltip": "Inference batch size. Larger values are faster but use more RAM.",
        },
    ],
    plots=[
        {
            "type": "markers",
            "x": "_event_times",
            "y": "_event_peaks",
            "color": "r",
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
    """
    return run_miniml_detection(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        threshold=kwargs.get("threshold", 0.5),
        direction=kwargs.get("direction", "negative"),
        batch_size=kwargs.get("batch_size", 64),
        model_path=kwargs.get("model_path", ""),
        miniml_core_path=kwargs.get("miniml_core_path", ""),
    )
