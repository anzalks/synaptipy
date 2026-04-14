# examples/plugins/synaptic_charge.py
# -*- coding: utf-8 -*-
"""
Advanced Synaptipy Plugin: Synaptic Charge Transfer (AUC) with Baseline Correction.

Measures the total charge delivered by a postsynaptic current by:
1. Slicing the trace to a user-defined search window.
2. Computing the baseline using a pre-window average or global mean.
3. Subtracting the baseline and locating the peak (largest or most-negative).
4. Walking outward from the peak to find zero-crossing bounds.
5. Integrating strictly between those bounds with the trapezoidal rule.

Visual overlays
---------------
* Draggable LinearRegionItem marks the search window.
* Shaded FillBetweenItem shows the integrated area above zero-baseline.
* Star marker indicates the detected peak.
* Dashed h-line shows the computed baseline level.

Usage
-----
Place in ``examples/plugins/`` or ``~/.synaptipy/plugins/`` for auto-discovery.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure analysis logic
# ---------------------------------------------------------------------------


def _find_zero_crossing_left(baseline_subtracted: np.ndarray, peak_idx: int) -> int:
    """
    Step backward from *peak_idx* until the trace crosses zero (baseline).

    Returns the index of the last sample still on the same side as the peak,
    i.e. the sample just before the crossing, clamped to 0.

    Args:
        baseline_subtracted: 1-D baseline-subtracted trace.
        peak_idx: Index of the detected peak.

    Returns:
        Left-bound index (>= 0).
    """
    if peak_idx <= 0 or len(baseline_subtracted) == 0:
        return 0
    peak_sign = np.sign(baseline_subtracted[peak_idx])
    if peak_sign == 0:
        return peak_idx
    for i in range(peak_idx - 1, -1, -1):
        if np.sign(baseline_subtracted[i]) != peak_sign:
            return i + 1
    return 0


def _find_zero_crossing_right(baseline_subtracted: np.ndarray, peak_idx: int) -> int:
    """
    Step forward from *peak_idx* until the trace crosses zero (baseline).

    Returns the index of the last sample still on the same side as the peak,
    clamped to len - 1.

    Args:
        baseline_subtracted: 1-D baseline-subtracted trace.
        peak_idx: Index of the detected peak.

    Returns:
        Right-bound index (<= len - 1).
    """
    n = len(baseline_subtracted)
    if peak_idx >= n - 1 or n == 0:
        return n - 1
    peak_sign = np.sign(baseline_subtracted[peak_idx])
    if peak_sign == 0:
        return peak_idx
    for i in range(peak_idx + 1, n):
        if np.sign(baseline_subtracted[i]) != peak_sign:
            return i - 1
    return n - 1


def calculate_synaptic_charge(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    window_start: float,
    window_end: float,
    baseline_method: str = "Pre-Window",
    detection_method: str = "Absolute Peak",
    pre_window_duration: float = 0.05,
) -> Dict[str, Any]:
    """
    Compute synaptic charge using peak-to-baseline zero-crossing integration.

    The algorithm:
    1. Slice the trace to ``[window_start, window_end]``.
    2. Calculate the baseline (Pre-Window average or Global mean).
    3. Subtract the baseline.
    4. Find the peak (largest absolute amplitude, or most-negative).
    5. Walk backward and forward from the peak to find zero-crossing bounds.
    6. Integrate the baseline-subtracted trace between bounds with
       ``np.trapz`` (result in pA*s = pC).

    Args:
        data: 1-D current trace (pA or any linear signal units).
        time: 1-D time array (seconds), same length as ``data``.
        sampling_rate: Sampling rate in Hz.
        window_start: Start of the search window in seconds.
        window_end: End of the search window in seconds.
        baseline_method: "Pre-Window" or "Global".
        detection_method: "Absolute Peak" or "Negative Peak".
        pre_window_duration: Duration of the pre-window baseline period (s).

    Returns:
        Dict following ``{"module_used": ..., "metrics": {...}}`` schema, or
        ``{"error": ...}`` on failure.
    """
    if data.size == 0:
        return {"error": "Empty data array"}
    if window_start >= window_end:
        return {"error": "window_start must be less than window_end"}

    # ---- 1. Compute baseline ----
    if baseline_method == "Pre-Window":
        pre_start = max(time[0], window_start - pre_window_duration)
        pre_end = window_start
        pre_mask = (time >= pre_start) & (time < pre_end)
        pre_slice = data[pre_mask]
        baseline_val = float(np.mean(pre_slice)) if pre_slice.size > 0 else float(np.mean(data))
    else:
        baseline_val = float(np.mean(data))

    # ---- 2. Slice the search window ----
    win_i0 = int(np.searchsorted(time, window_start, side="left"))
    win_i1 = int(np.searchsorted(time, window_end, side="right"))
    # Clamp to valid range
    win_i0 = max(0, min(win_i0, len(data) - 1))
    win_i1 = max(win_i0 + 1, min(win_i1, len(data)))

    win_time = time[win_i0:win_i1]
    win_data = data[win_i0:win_i1]

    if win_time.size < 2:
        return {"error": "Search window too narrow (need >= 2 samples)"}

    # ---- 3. Baseline-subtract the window ----
    win_bs = win_data - baseline_val

    # ---- 4. Find the peak ----
    if detection_method == "Negative Peak":
        peak_idx_rel = int(np.argmin(win_bs))
    else:
        peak_idx_rel = int(np.argmax(np.abs(win_bs)))

    peak_t = float(win_time[peak_idx_rel])
    peak_v_abs = float(win_data[peak_idx_rel])
    peak_v_bs = float(win_bs[peak_idx_rel])

    # ---- 5. Zero-crossing search from peak ----
    left_idx = _find_zero_crossing_left(win_bs, peak_idx_rel)
    right_idx = _find_zero_crossing_right(win_bs, peak_idx_rel)

    # Ensure at least 2 points for integration
    if right_idx <= left_idx:
        right_idx = min(left_idx + 1, len(win_bs) - 1)

    # ---- 6. Extract bounded slice ----
    int_x = win_time[left_idx : right_idx + 1]
    int_y_bs = win_bs[left_idx : right_idx + 1]
    int_y_abs = win_data[left_idx : right_idx + 1]
    baseline_arr = np.full(len(int_x), baseline_val)

    if int_x.size < 2:
        return {"error": "Integration region too narrow after zero-crossing search"}

    # ---- 7. Integrate (trapezoidal rule, pA*s = pC) ----
    charge_pc = float(np.trapezoid(int_y_bs, int_x))

    metrics: Dict[str, Any] = {
        # Public metrics visible in results table
        "Charge_pC": round(charge_pc, 6),
        "Peak_Amp": round(peak_v_abs, 4),
        "Peak_Amp_Baseline_Subtracted": round(peak_v_bs, 4),
        "Baseline_pA": round(baseline_val, 4),
        "Integration_Start_s": round(float(int_x[0]), 6),
        "Integration_End_s": round(float(int_x[-1]), 6),
    }

    return {
        "module_used": "synaptic_charge",
        "metrics": metrics,
        # Private arrays at top level for plot overlays (hidden from results table)
        "_int_x": int_x,
        "_int_y": int_y_abs,
        "_baseline": baseline_arr,
        "_peak_t": np.array([peak_t]),
        "_peak_v": np.array([peak_v_abs]),
    }


# ---------------------------------------------------------------------------
# Registry wrapper
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    name="synaptic_charge",
    label="Synaptic Charge (AUC)",
    ui_params=[
        {
            "name": "baseline_method",
            "label": "Baseline Method:",
            "type": "choice",
            "options": ["Pre-Window", "Global"],
            "default": "Pre-Window",
            "tooltip": "Pre-Window uses a short window before the search window; Global uses the entire trace mean.",
        },
        {
            "name": "detection_method",
            "label": "Detection Method:",
            "type": "choice",
            "options": ["Absolute Peak", "Negative Peak"],
            "default": "Absolute Peak",
            "tooltip": "Absolute Peak finds the largest-magnitude deflection; Negative Peak finds the most negative.",
        },
        {
            "name": "window_start",
            "label": "Search Window Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Start of the event search window in seconds.",
        },
        {
            "name": "window_end",
            "label": "Search Window End (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "End of the event search window in seconds.",
        },
        {
            "name": "pre_window_duration",
            "label": "Pre-Window Duration (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.001,
            "max": 10.0,
            "decimals": 4,
            "tooltip": "Duration of the baseline period immediately before the search window.",
            "visible_when": {"param": "baseline_method", "value": "Pre-Window"},
        },
    ],
    plots=[
        {
            "type": "interactive_region",
            "data": ["window_start", "window_end"],
            "color": "blue",
        },
        {
            "type": "fill_between",
            "x": "_int_x",
            "y1": "_int_y",
            "y2": "_baseline",
            "brush": [0, 150, 255, 100],
        },
        {
            "type": "markers",
            "x": "_peak_t",
            "y": "_peak_v",
            "color": "r",
            "symbol": "star",
        },
        {
            "type": "hlines",
            "values": ["Baseline_pA"],
            "colors": ["b"],
            "styles": ["dash"],
        },
    ],
)
def run_synaptic_charge_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Registry wrapper for synaptic charge analysis."""
    return calculate_synaptic_charge(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        window_start=kwargs.get("window_start", 0.0),
        window_end=kwargs.get("window_end", 0.1),
        baseline_method=kwargs.get("baseline_method", "Pre-Window"),
        detection_method=kwargs.get("detection_method", "Absolute Peak"),
        pre_window_duration=kwargs.get("pre_window_duration", 0.05),
    )
