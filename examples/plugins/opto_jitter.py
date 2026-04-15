# examples/plugins/opto_jitter.py
# -*- coding: utf-8 -*-
"""
Example Synaptipy Plugin: Optogenetic Latency Jitter.

Measures the trial-to-trial variability (jitter) in the latency from a TTL
stimulus pulse to the first evoked spike across sweeps.

Usage
-----
This file is automatically discovered when placed in either:
- ``examples/plugins/`` (loaded out-of-the-box by Synaptipy)
- ``~/.synaptipy/plugins/`` (user copy, takes precedence over example)

The plugin requires a secondary channel carrying the TTL/digital stimulus
signal in addition to the primary voltage channel.

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


def calculate_opto_jitter(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    secondary_data: np.ndarray,
    ttl_threshold: float,
    search_start: float,
    search_end: float,
    spike_threshold: float,
) -> Dict[str, Any]:
    """
    Compute per-sweep spike latencies from TTL onset and return jitter.

    The function expects ``data`` to be a 2-D array of shape
    ``(n_sweeps, n_samples)`` or a 1-D array for a single sweep.
    ``secondary_data`` carries the TTL signal with the same shape.

    The algorithm:
    1. Detect TTL onset (first crossing of ``ttl_threshold`` from below).
    2. Within ``[ttl_onset + search_start, ttl_onset + search_end]`` find the
       first sample where ``data`` exceeds ``spike_threshold``.
    3. Convert the sample offset to milliseconds.
    4. Report the mean latency, standard deviation (jitter), and the
       per-sweep latency array.

    Args:
        data: Voltage trace(s).  Shape ``(n_samples,)`` or
            ``(n_sweeps, n_samples)``.
        time: Time vector in seconds, length ``n_samples``.
        sampling_rate: Sampling rate in Hz.
        secondary_data: TTL/digital channel with the same shape as ``data``.
        ttl_threshold: Voltage threshold that defines the TTL rising edge.
        search_start: Start of the spike-search window relative to TTL onset
            (seconds).
        search_end: End of the spike-search window relative to TTL onset
            (seconds).
        spike_threshold: Voltage threshold (mV) for spike detection.

    Returns:
        Dict with result keys or ``{"error": ...}`` on failure.
    """
    if data.size == 0:
        return {"error": "Empty data array"}
    if secondary_data.size == 0:
        return {"error": "Empty secondary (TTL) channel"}

    # Normalise to 2-D
    if data.ndim == 1:
        data = data[np.newaxis, :]
        secondary_data = secondary_data[np.newaxis, :]

    n_sweeps, n_samples = data.shape
    if secondary_data.shape != data.shape:
        return {"error": f"Shape mismatch: data {data.shape} vs TTL {secondary_data.shape}"}

    dt = 1.0 / sampling_rate
    search_start_samples = int(round(search_start * sampling_rate))
    search_end_samples = int(round(search_end * sampling_rate))

    latencies_ms = []
    sweep_numbers = []

    for sweep_idx in range(n_sweeps):
        ttl_trace = secondary_data[sweep_idx]
        v_trace = data[sweep_idx]

        # Detect first TTL rising-edge crossing
        above = ttl_trace > ttl_threshold
        crossings = np.where(np.diff(above.astype(int)) == 1)[0]
        if crossings.size == 0:
            log.debug("Sweep %d: no TTL crossing found", sweep_idx)
            continue
        ttl_onset_idx = int(crossings[0]) + 1  # first sample above threshold

        # Define search window in samples
        win_start = ttl_onset_idx + search_start_samples
        win_end = ttl_onset_idx + search_end_samples
        win_start = max(0, win_start)
        win_end = min(n_samples, win_end)

        if win_end <= win_start:
            log.debug("Sweep %d: search window empty after clipping", sweep_idx)
            continue

        window = v_trace[win_start:win_end]
        spike_candidates = np.where(window > spike_threshold)[0]

        if spike_candidates.size == 0:
            log.debug("Sweep %d: no spike above threshold in search window", sweep_idx)
            continue

        first_spike_offset = int(spike_candidates[0])
        latency_s = (search_start_samples + first_spike_offset) * dt
        latency_ms = latency_s * 1000.0
        latencies_ms.append(latency_ms)
        sweep_numbers.append(sweep_idx + 1)

    if len(latencies_ms) < 2:
        # Report counts so callers can distinguish 0% from low-N cases.
        n_detected = len(latencies_ms)
        n_failures = n_sweeps - n_detected
        return {
            "error": (
                f"Too few sweeps with detected spikes ({n_detected}/{n_sweeps}) "
                "to compute jitter - need at least 2."
            ),
            # Include partial counts even on failure so batch engines can aggregate.
            "metrics": {
                "Success Count": n_detected,
                "Failure Count": n_failures,
                "Response Probability (%)": round(n_detected / max(n_sweeps, 1) * 100.0, 2),
            },
        }

    lat_arr = np.array(latencies_ms, dtype=float)
    jitter_val = float(np.std(lat_arr, ddof=1))
    mean_latency = float(np.mean(lat_arr))

    n_failures = n_sweeps - len(latencies_ms)
    resp_prob_pct = round(len(latencies_ms) / max(n_sweeps, 1) * 100.0, 2)

    return {
        "module_used": "opto_jitter",
        "metrics": {
            "Jitter_ms": round(jitter_val, 4),
            "Mean_Latency_ms": round(mean_latency, 4),
            "N_Sweeps_Detected": len(latencies_ms),
            "Success Count": len(latencies_ms),
            "Failure Count": n_failures,
            "Response Probability (%)": resp_prob_pct,
        },
        # Private arrays for the popup_xy plot overlay (hidden from table)
        "_sweep_numbers": np.array(sweep_numbers, dtype=float),
        "_latencies": lat_arr,
    }


# ---------------------------------------------------------------------------
# Part 2 - Registry wrapper
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    name="opto_jitter",
    label="Opto Latency Jitter",
    requires_secondary_channel=True,
    ui_params=[
        {
            "name": "ttl_threshold",
            "label": "TTL Threshold (V):",
            "type": "float",
            "default": 0.5,
            "min": -100.0,
            "max": 100.0,
            "decimals": 3,
            "tooltip": "Voltage level that defines the TTL rising edge on the secondary channel",
        },
        {
            "name": "search_start",
            "label": "Search Window Start (s):",
            "type": "float",
            "default": 0.001,
            "min": 0.0,
            "max": 10.0,
            "decimals": 4,
            "tooltip": "Start of the spike-search window relative to TTL onset",
        },
        {
            "name": "search_end",
            "label": "Search Window End (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "max": 10.0,
            "decimals": 4,
            "tooltip": "End of the spike-search window relative to TTL onset",
        },
        {
            "name": "spike_threshold",
            "label": "Spike Threshold (mV):",
            "type": "float",
            "default": -20.0,
            "min": -200.0,
            "max": 200.0,
            "decimals": 2,
            "tooltip": "Voltage above which a depolarisation is counted as a spike",
        },
    ],
    plots=[
        {
            "type": "popup_xy",
            "title": "Spike Latency per Sweep",
            "x": "_sweep_numbers",
            "y": "_latencies",
            "x_label": "Sweep Number",
            "y_label": "Latency (ms)",
        },
    ],
)
def run_opto_jitter_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """
    Registry wrapper for opto_jitter.

    Extracts GUI parameters from kwargs and delegates to
    ``calculate_opto_jitter``.  The secondary TTL channel is expected under
    ``kwargs["secondary_data"]`` when provided by the batch engine or the
    metadata-driven tab.
    """
    secondary_data = kwargs.get("secondary_data", np.array([]))
    if isinstance(secondary_data, list):
        secondary_data = np.asarray(secondary_data, dtype=float)

    return calculate_opto_jitter(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        secondary_data=secondary_data,
        ttl_threshold=float(kwargs.get("ttl_threshold", 0.5)),
        search_start=float(kwargs.get("search_start", 0.001)),
        search_end=float(kwargs.get("search_end", 0.05)),
        spike_threshold=float(kwargs.get("spike_threshold", -20.0)),
    )
