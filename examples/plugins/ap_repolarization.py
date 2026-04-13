# examples/plugins/ap_repolarization.py
# -*- coding: utf-8 -*-
"""
Example Synaptipy Plugin: Maximum Action-Potential Repolarization Rate.

Measures the steepest rate of membrane-potential decline (dV/dt minimum)
during the falling phase of an action potential.  A large negative dV/dt
corresponds to rapid repolarization, which reflects the combined activity of
voltage-gated potassium channels and sodium-channel inactivation.

Usage
-----
This file is automatically discovered when placed in either:
- ``examples/plugins/`` (loaded out-of-the-box by Synaptipy)
- ``~/.synaptipy/plugins/`` (user copy, takes precedence over example)

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Part 1 - Pure analysis logic (no GUI imports)
# ---------------------------------------------------------------------------


def calculate_ap_repolarization(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    window_start: float,
    window_end: float,
    spike_threshold: float,
) -> Dict[str, Any]:
    """
    Find the maximum repolarization rate of the first action potential.

    The algorithm:
    1. Extract the analysis window ``[window_start, window_end]`` from the trace.
    2. Identify the first sample that crosses ``spike_threshold`` from below
       (AP onset).
    3. Compute the first derivative using ``np.gradient``.
    4. Find the absolute minimum of the derivative (steepest negative slope) -
       this is the maximum repolarization rate in V/s.
    5. Report the value and its time coordinate for a marker overlay.

    Args:
        data: 1-D voltage trace in mV.
        time: 1-D time array in seconds, same length as data.
        sampling_rate: Sampling rate in Hz.
        window_start: Start of the search window in seconds.
        window_end: End of the search window in seconds.
        spike_threshold: Voltage (mV) that marks AP onset.

    Returns:
        Dict with result keys or ``{"error": ...}`` on failure.
    """
    if data.size == 0:
        return {"error": "Empty data array"}

    win_i0 = int(np.searchsorted(time, window_start, side="left"))
    win_i1 = int(np.searchsorted(time, window_end, side="right"))
    win_time = time[win_i0:win_i1]
    win_data = data[win_i0:win_i1]

    if win_data.size < 4:
        return {"error": "Analysis window too narrow (need >= 4 samples)"}

    # Locate AP onset: first crossing of spike_threshold from below
    above = win_data > spike_threshold
    crossings = np.where(np.diff(above.astype(int)) == 1)[0]
    if crossings.size == 0:
        return {"error": f"No spike crossing {spike_threshold} mV found in window"}

    ap_start_idx = int(crossings[0]) + 1

    # Work on data from AP onset to end of window
    ap_data = win_data[ap_start_idx:]
    ap_time = win_time[ap_start_idx:]

    if ap_data.size < 4:
        return {"error": "Too few samples after AP onset"}

    # First derivative via gradient (V/sample -> V/s)
    dvdt = np.gradient(ap_data, ap_time)

    # Max repolarization = most negative dV/dt
    min_idx = int(np.argmin(dvdt))
    max_dvdt = float(dvdt[min_idx])  # negative value in V/s
    repol_time = float(ap_time[min_idx])
    repol_val = float(ap_data[min_idx])

    return {
        "module_used": "ap_repolarization",
        "metrics": {
            "Max_Repol_V_s": round(max_dvdt, 2),
        },
        # Flat scalar keys shown in the results table
        "Max_Repol_V_s": round(max_dvdt, 2),
        "Repol_Time_s": round(repol_time, 6),
        "Repol_Voltage_mV": round(repol_val, 4),
        # Private scalars for the markers plot overlay (hidden from table)
        "_repol_time": repol_time,
        "_repol_val": repol_val,
    }


# ---------------------------------------------------------------------------
# Part 2 - Registry wrapper
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    name="ap_repolarization",
    label="Max Repolarization Rate",
    ui_params=[
        {
            "name": "window_start",
            "label": "Window Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Start of the time window to search for an action potential",
        },
        {
            "name": "window_end",
            "label": "Window End (s):",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "End of the time window to search for an action potential",
        },
        {
            "name": "spike_threshold",
            "label": "Spike Threshold (mV):",
            "type": "float",
            "default": -20.0,
            "min": -200.0,
            "max": 200.0,
            "decimals": 2,
            "tooltip": "Voltage crossing that marks the start of the action potential",
        },
    ],
    plots=[
        {
            "type": "interactive_region",
            "data": ["window_start", "window_end"],
            "color": "g",
        },
        {
            "type": "markers",
            "x": "_repol_time",
            "y": "_repol_val",
            "color": "b",
        },
    ],
)
def run_ap_repolarization_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """
    Registry wrapper for ap_repolarization.

    Extracts GUI parameters from kwargs and delegates to
    ``calculate_ap_repolarization``.
    """
    return calculate_ap_repolarization(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        window_start=float(kwargs.get("window_start", 0.0)),
        window_end=float(kwargs.get("window_end", 1.0)),
        spike_threshold=float(kwargs.get("spike_threshold", -20.0)),
    )
