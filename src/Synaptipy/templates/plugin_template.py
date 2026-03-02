# src/Synaptipy/templates/plugin_template.py
# -*- coding: utf-8 -*-
"""
Synaptipy Plugin Template — Copy, Customise, and Drop In.

HOW TO USE:
    1. Copy this file to ~/.synaptipy/plugins/
       (on Windows: C:\\Users\\<you>\\.synaptipy\\plugins\\)
    2. Rename it to something descriptive, e.g. my_snr_analysis.py
    3. Edit the sections marked CHANGE below.
    4. Restart Synaptipy — your analysis appears as a new Analyser tab.

No other files need to be modified — the plugin system discovers this file
automatically at startup.

WHAT YOU GET:
    - A new tab in the Analyser with parameter widgets generated from ui_params.
    - A Run button that calls your wrapper function.
    - A results table populated from the dict your wrapper returns.
    - Plot overlays (horizontal lines, regions, markers, etc.) driven by the
      plots list.

REFERENCE:
    Full documentation:  docs/extending_synaptipy.md
    Built-in examples:   src/Synaptipy/core/analysis/basic_features.py
                         src/Synaptipy/core/analysis/capacitance.py

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""
import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ╔═══════════════════════════════════════════════════════════════════╗
# ║  PART 1 — PURE ANALYSIS LOGIC                                    ║
# ║  Write your algorithm here. No GUI code. Just NumPy / SciPy.     ║
# ╚═══════════════════════════════════════════════════════════════════╝


def calculate_my_metric(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    window_start: float,
    window_end: float,
    threshold: float,
) -> Dict[str, Any]:
    """
    CHANGE: Replace this function with your own analysis logic.

    Args:
        data: 1-D NumPy array — the voltage (or current) trace for one sweep.
        time: 1-D NumPy array — time in seconds, same length as data.
        sampling_rate: Sampling rate in Hz.
        window_start: Start of the analysis window in seconds.
        window_end: End of the analysis window in seconds.
        threshold: Example numeric parameter.

    Returns:
        Dict with your results.  Keys become rows in the results table.
        Keys starting with '_' are hidden from the table (use for plot data).
        A key named 'error' triggers an error message in the GUI.
    """
    # --- Guard against bad input ---
    if data.size == 0:
        return {"error": "Empty data array"}

    # --- Convert time boundaries to sample indices ---
    i_start = int(np.searchsorted(time, window_start, side="left"))
    i_end = int(np.searchsorted(time, window_end, side="right"))
    segment = data[i_start:i_end]

    if segment.size < 2:
        return {"error": "Analysis window too narrow (need >= 2 samples)"}

    # --- Your analysis here ---
    mean_val = float(np.mean(segment))
    std_val = float(np.std(segment))
    above_count = int(np.sum(segment > threshold))

    return {
        # Public keys → shown in the results table
        "mean_value": round(mean_val, 4),
        "std_dev": round(std_val, 4),
        "points_above_threshold": above_count,
        # Private keys → hidden from table, available for plots
        "_threshold_level": threshold,
        "_mean_level": mean_val,
    }


# ╔═══════════════════════════════════════════════════════════════════╗
# ║  PART 2 — REGISTRY WRAPPER                                       ║
# ║  Configure the decorator to define your tab name, parameters,     ║
# ║  and plot overlays.  The function body just calls Part 1.          ║
# ╚═══════════════════════════════════════════════════════════════════╝


@AnalysisRegistry.register(
    # ── CHANGE: unique internal name (no spaces, used as identifier) ──
    name="my_custom_metric",
    # ── CHANGE: display name shown on the tab ──
    label="My Custom Metric",
    # ── CHANGE: parameter widgets ──
    # Each dict creates one widget.  Supported types:
    #   "float"  → spin box (decimals)       "int"    → spin box (integer)
    #   "bool"   → check box                 "choice" → drop-down combo box
    #
    # Optional fields on any type:
    #   "tooltip": "..."                 — hover text
    #   "hidden": True                   — param exists but no widget shown
    #   "visible_when": {"param": "X", "value": "Y"}  — shown only when X == Y
    ui_params=[
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
        # ── Uncomment to add more parameter types: ──
        # {
        #     "name": "direction",
        #     "label": "Direction:",
        #     "type": "choice",
        #     "choices": ["positive", "negative", "both"],
        #     "default": "positive",
        # },
        # {
        #     "name": "auto_detect",
        #     "label": "Auto-Detect Window",
        #     "type": "bool",
        #     "default": False,
        # },
        # {
        #     "name": "min_events",
        #     "label": "Min Events:",
        #     "type": "int",
        #     "default": 3,
        #     "min": 1,
        #     "max": 10000,
        # },
    ],
    # ── CHANGE: plot overlays ──
    # Each dict adds a visual element on top of the data trace.
    # Supported types:
    #   "interactive_region" — draggable shaded region (linked to 2 float params)
    #   "hlines"             — horizontal lines at result-dict values
    #   "vlines"             — vertical lines at result-dict values
    #   "markers"            — scatter points from result arrays
    #   "threshold_line"     — draggable h-line linked to a float param
    #   "overlay_fit"        — curve overlay (x/y arrays from result)
    #   "popup_xy"           — popup window with a scatter/line plot
    #   "brackets"           — burst bracket bars
    #   "event_markers"      — interactive click-to-edit event points
    plots=[
        # Draggable analysis window
        {"type": "interactive_region", "data": ["window_start", "window_end"], "color": "g"},
        # Threshold line (dashed red)
        {"type": "hlines", "data": ["_threshold_level"], "color": "r", "styles": ["dash"]},
        # Mean value line (solid blue)
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
    Registry wrapper — extracts GUI parameters and calls the logic function.

    CHANGE: Update kwargs.get() calls to match your ui_params names.

    The signature (data, time, sampling_rate, **kwargs) is fixed — do not change it.
    """
    return calculate_my_metric(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        window_start=kwargs.get("window_start", 0.0),
        window_end=kwargs.get("window_end", 0.5),
        threshold=kwargs.get("threshold", 0.0),
    )
