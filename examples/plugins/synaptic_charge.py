# examples/plugins/synaptic_charge.py
# -*- coding: utf-8 -*-
"""
Example Synaptipy Plugin: Synaptic Charge Transfer (Area Under Curve).

Measures the total charge delivered by a postsynaptic current by integrating
the current trace inside a user-defined time window using the trapezoidal rule,
and locates the peak amplitude within the window.

Visual overlays
---------------
* A draggable region shows the integration window on the trace.
* A shaded fill highlights the integrated area between the trace and zero baseline.
* A star marker indicates the absolute peak within the window.

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


def calculate_synaptic_charge(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    integration_start: float,
    integration_end: float,
) -> Dict[str, Any]:
    """
    Compute synaptic charge (area under curve) within a time window.

    The algorithm:
    1. Slice the trace to ``[integration_start, integration_end]``.
    2. Integrate using ``np.trapezoid`` (trapezoidal rule, result in pA*s = pC).
    3. Find the sample with the largest absolute amplitude in the window.
    4. Return the charge, peak amplitude, and hidden arrays for plot overlays.

    Args:
        data: 1-D current trace in pA (or any linear signal units).
        time: 1-D time array in seconds, same length as ``data``.
        sampling_rate: Sampling rate in Hz.
        integration_start: Start of the integration window in seconds.
        integration_end: End of the integration window in seconds.

    Returns:
        Dict with result keys or ``{"error": ...}`` on failure.
    """
    if data.size == 0:
        return {"error": "Empty data array"}

    if integration_start >= integration_end:
        return {"error": "integration_start must be less than integration_end"}

    win_i0 = int(np.searchsorted(time, integration_start, side="left"))
    win_i1 = int(np.searchsorted(time, integration_end, side="right"))
    int_x = time[win_i0:win_i1]
    int_y = data[win_i0:win_i1]

    if int_x.size < 2:
        return {"error": "Integration window too narrow (need >= 2 samples)"}

    # Area under curve via trapezoidal integration (pA * s = pC)
    auc_val = float(np.trapezoid(int_y, int_x))

    # Absolute peak within the integration window
    peak_idx_rel = int(np.argmax(np.abs(int_y)))
    peak_t = float(int_x[peak_idx_rel])
    peak_v = float(int_y[peak_idx_rel])

    # Baseline is the zero line (y = 0)
    baseline_arr = np.zeros(len(int_x))

    return {
        "module_used": "synaptic_charge",
        "metrics": {
            "Charge_pC": round(auc_val, 6),
            "Peak_Amp": round(peak_v, 4),
        },
        # Flat scalar keys shown in the results table
        "Charge_pC": round(auc_val, 6),
        "Peak_Amp": round(peak_v, 4),
        # Private arrays for plot overlays (hidden from results table)
        "_int_x": int_x,
        "_int_y": int_y,
        "_baseline": baseline_arr,
        "_peak_t": np.array([peak_t]),
        "_peak_v": np.array([peak_v]),
    }


# ---------------------------------------------------------------------------
# Part 2 - Registry wrapper
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    name="synaptic_charge",
    label="Synaptic Charge (AUC)",
    ui_params=[
        {
            "name": "integration_start",
            "label": "Integration Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Start of the integration window in seconds",
        },
        {
            "name": "integration_end",
            "label": "Integration End (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "End of the integration window in seconds",
        },
    ],
    plots=[
        {
            "type": "interactive_region",
            "data": ["integration_start", "integration_end"],
            "color": "gray",
        },
        {
            "type": "fill_between",
            "x": "_int_x",
            "y1": "_int_y",
            "y2": "_baseline",
            "color": "blue",
        },
        {
            "type": "markers",
            "x": "_peak_t",
            "y": "_peak_v",
            "color": "r",
            "symbol": "star",
        },
    ],
)
def run_synaptic_charge_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Registry wrapper - extracts kwargs and calls the pure logic function."""
    return calculate_synaptic_charge(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        integration_start=kwargs.get("integration_start", 0.0),
        integration_end=kwargs.get("integration_end", 0.1),
    )
