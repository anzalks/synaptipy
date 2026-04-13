# src/Synaptipy/templates/plugin_template.py
# -*- coding: utf-8 -*-
"""
Synaptipy Plugin Template - Copy, Customise, and Drop In.

HOW TO USE:
    1. Copy this file to ~/.synaptipy/plugins/
       (on Windows: C:\\Users\\<you>\\.synaptipy\\plugins\\)
    2. Rename it to something descriptive, e.g. my_analysis.py
    3. Implement your logic in ``calculate_my_metric`` (Part 1).
    4. Configure the decorator in Part 2 (name, label, ui_params, plots).
    5. Restart Synaptipy - your analysis appears as a new Analyser tab.

No other files need to be modified.  The plugin system discovers this file
automatically at startup.

FULL EXAMPLES:
    examples/plugins/opto_jitter.py       - optogenetic latency jitter
    examples/plugins/ap_repolarization.py - max AP repolarization rate

DOCUMENTATION:
    docs/extending_synaptipy.md           - complete reference

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ============================================================
# PART 1 - PURE ANALYSIS LOGIC
# Write your algorithm here.  No GUI code.  Just NumPy / SciPy.
# ============================================================


def calculate_my_metric(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    window_start: float,
    window_end: float,
    threshold: float,
) -> Dict[str, Any]:
    """
    Replace this docstring and body with your own analysis logic.

    Args:
        data: 1-D NumPy array - the voltage (or current) trace for one sweep.
        time: 1-D NumPy array - time in seconds, same length as data.
        sampling_rate: Sampling rate in Hz.
        window_start: Start of the analysis window in seconds.
        window_end: End of the analysis window in seconds.
        threshold: Example numeric parameter.

    Returns:
        Dict with your results.  Keys become rows in the results table.
        Keys starting with '_' are hidden from the table (use for plot data).
        A key named 'error' triggers an error message in the GUI.
    """
    if data.size == 0:
        return {"error": "Empty data array"}

    i_start = int(np.searchsorted(time, window_start, side="left"))
    i_end = int(np.searchsorted(time, window_end, side="right"))
    segment = data[i_start:i_end]

    if segment.size < 2:
        return {"error": "Analysis window too narrow (need >= 2 samples)"}

    # Replace the lines below with your own metric calculations.
    mean_val = float(np.mean(segment))
    std_val = float(np.std(segment))
    above_count = int(np.sum(segment > threshold))

    return {
        "mean_value": round(mean_val, 4),
        "std_dev": round(std_val, 4),
        "points_above_threshold": above_count,
        "_threshold_level": threshold,
        "_mean_level": mean_val,
    }


# ============================================================
# PART 2 - REGISTRY WRAPPER
# Configure the decorator to define your tab name, parameters,
# and plot overlays.  The function body just calls Part 1.
# ============================================================


@AnalysisRegistry.register(
    name="my_custom_metric",              # CHANGE: unique internal name
    label="My Custom Metric",             # CHANGE: display name for the tab
    ui_params=[
        # CHANGE: define your parameter widgets here.
        # See docs/extending_synaptipy.md section 4 for all available types.
        {
            "name": "window_start",
            "label": "Window Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "window_end",
            "label": "Window End (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "threshold",
            "label": "Threshold:",
            "type": "float",
            "default": 0.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Values above this are counted",
        },
    ],
    plots=[
        # CHANGE: define your plot overlays here.
        # See docs/extending_synaptipy.md section 5 for all overlay types.
        {"type": "interactive_region", "data": ["window_start", "window_end"], "color": "g"},
        {"type": "hlines", "data": ["_threshold_level"], "color": "r", "styles": ["dash"]},
        {"type": "hlines", "data": ["_mean_level"], "color": "b", "styles": ["solid"]},
    ],
)
def run_my_custom_metric_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """
    Registry wrapper - extracts GUI parameters and calls the logic function.

    The signature ``(data, time, sampling_rate, **kwargs)`` is fixed.
    CHANGE: update ``kwargs.get()`` calls to match your ui_params names.
    """
    return calculate_my_metric(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        window_start=kwargs.get("window_start", 0.0),
        window_end=kwargs.get("window_end", 0.5),
        threshold=kwargs.get("threshold", 0.0),
    )
