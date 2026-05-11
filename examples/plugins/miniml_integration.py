# -*- coding: utf-8 -*-
"""
Synaptipy Plugin for miniML Event Detection
https://github.com/delvendahl/miniML

This file is a **GUI plugin template** for Synaptipy's @AnalysisRegistry
system. It is NOT a standalone script. Drop it (or a copy) into
~/.synaptipy/plugins/ and enable "Enable Custom Plugins" in
Edit > Preferences to have it appear as a tab in the Analyser.

Dependencies (NOT bundled with Synaptipy - install separately):
    pip install miniML ruptures==1.1.10

Before use, set DEFAULT_MODEL_PATH below to the path of your downloaded
miniML Keras model (.h5 file).
"""

import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)

# Update this path to the location of your downloaded miniML model
DEFAULT_MODEL_PATH = "path/to/your/model.h5"

try:
    from miniML import EventDetection, MiniTrace

    MINIML_AVAILABLE = True
except ImportError:
    MINIML_AVAILABLE = False


def run_miniml_detection(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    threshold: float = 0.5,
    direction: str = "negative",
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
        miniML prediction threshold in [0, 1]. Higher values reduce false
        positives at the expense of recall.
    direction:
        ``"negative"`` for inward/downward currents (IPSCs, mEPSCs in
        voltage-clamp); ``"positive"`` for outward/upward events.

    Returns
    -------
    dict
        Keys ``Event_Count`` and ``Frequency_Hz`` are shown in the results
        table. Keys prefixed with ``_`` (``_event_times``, ``_event_peaks``)
        are private and used for plot overlays only.
    """
    if not MINIML_AVAILABLE:
        return {"error": "miniML is not installed. Run: pip install miniML ruptures==1.1.10"}
    if data.size == 0:
        return {"error": "Empty data array provided."}

    try:
        input_data = data if direction == "negative" else -data
        trace = MiniTrace(input_data, dt=1.0 / sampling_rate)
        detector = EventDetection(DEFAULT_MODEL_PATH, trace)
        detector.detect_events(threshold=threshold)
        ev_times = detector.event_times
        ev_peaks = detector.event_peaks
    except Exception as e:
        log.error("miniML detection failed: %s", e)
        return {"error": f"miniML inference error: {str(e)}"}

    duration = time[-1] - time[0] if len(time) > 1 else 0.0
    freq = len(ev_times) / duration if duration > 0 else 0.0

    return {
        "module_used": "miniML_detection",
        "metrics": {
            "Event_Count": len(ev_times),
            "Frequency_Hz": float(round(freq, 2)),
        },
        "Event_Count": len(ev_times),
        "Frequency_Hz": float(round(freq, 2)),
        "_event_times": ev_times,
        "_event_peaks": ev_peaks,
    }


@AnalysisRegistry.register(
    name="miniml_events",
    label="miniML Events",
    ui_params=[
        {
            "name": "threshold",
            "label": "Prediction Threshold:",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "decimals": 2,
        },
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
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

    Delegates to :func:`run_miniml_detection`; ``kwargs`` are populated
    automatically from the ``ui_params`` widgets in the Analyser tab.
    """
    return run_miniml_detection(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        threshold=kwargs.get("threshold", 0.5),
        direction=kwargs.get("direction", "negative"),
    )
