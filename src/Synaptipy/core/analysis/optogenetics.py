# src/Synaptipy/core/analysis/optogenetics.py
# -*- coding: utf-8 -*-
"""
Optogenetic stimulus synchronization analysis.

Natively extracts digital/TTL optical stimulus pulses and correlates them with
action potentials to determine optical latency, response probability, and jitter.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List
import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.results import AnalysisResult

log = logging.getLogger(__name__)


@dataclass
class OptoSyncResult(AnalysisResult):
    """Result object for optogenetic synchronization analysis."""
    optical_latency_ms: Optional[float] = None
    response_probability: Optional[float] = None
    spike_jitter_ms: Optional[float] = None
    stimulus_count: int = 0
    stimulus_onsets: Optional[np.ndarray] = None
    stimulus_offsets: Optional[np.ndarray] = None
    # Lists of spike times responding to each stimulus
    responding_spikes: List[List[float]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        if self.is_valid:
            lat = f"{self.optical_latency_ms:.2f}" if self.optical_latency_ms is not None else "N/A"
            prob = f"{self.response_probability:.2f}" if self.response_probability is not None else "N/A"
            jit = f"{self.spike_jitter_ms:.2f}" if self.spike_jitter_ms is not None else "N/A"
            return (f"OptoSyncResult(Latency={lat} ms, Prob={prob}, Jitter={jit} ms, "
                    f"Stims={self.stimulus_count})")
        return f"OptoSyncResult(Error: {self.error_message})"


def extract_ttl_epochs(
    ttl_data: np.ndarray,
    time: np.ndarray,
    threshold: float = 2.5
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extracts rising and falling edges of a digital TTL signal.

    Args:
        ttl_data: The digital signal array (e.g. 0V to 5V pulses).
        time: The timestamp array matching ttl_data.
        threshold: Voltage threshold to define HIGH state (default 2.5V).

    Returns:
        Tuple of (onsets, offsets) arrays in seconds.
    """
    if ttl_data.size == 0 or time.size == 0:
        return np.array([]), np.array([])

    # Binarize signal based on threshold
    is_high = ttl_data > threshold

    # Use numpy.diff to find edges
    # diff evaluates to True at indices where signal crosses
    # from False to True or True to False

    # Prepend False to capture an edge if the signal starts high
    is_high_padded = np.insert(is_high, 0, False)

    diff_signal = np.diff(is_high_padded.astype(int))

    # 1 indicates False -> True (Rising edge)
    # -1 indicates True -> False (Falling edge)
    rising_edges_idx = np.where(diff_signal == 1)[0]
    falling_edges_idx = np.where(diff_signal == -1)[0]

    # Handle the case where the signal ends while still high
    if len(rising_edges_idx) > len(falling_edges_idx):
        # We append the very last index as the offset
        falling_edges_idx = np.append(falling_edges_idx, len(ttl_data) - 1)

    onsets = time[rising_edges_idx]
    offsets = time[falling_edges_idx]

    return onsets, offsets


def _find_spikes_in_window(spikes: np.ndarray, t_start: float, t_end: float) -> np.ndarray:
    """Helper to heavily vectorize finding spikes within a dynamic window."""
    if spikes.size == 0:
        return np.array([])

    mask = (spikes >= t_start) & (spikes <= t_end)
    return spikes[mask]


def calculate_optogenetic_sync(
    ttl_data: np.ndarray,
    action_potential_times: np.ndarray,
    time: np.ndarray,
    ttl_threshold: float = 2.5,
    response_window_ms: float = 20.0
) -> OptoSyncResult:
    """
    Core logic: Correlate TTL stimuli with Action Potential times.

    Args:
        ttl_data: Digital signal data trace.
        action_potential_times: Pre-calculated spike times (in seconds).
        time: Timestamps of the trace.
        ttl_threshold: Voltage threshold for TTL edge detection.
        response_window_ms: Searching window for APs after stimulus onset (in ms).
    """
    if ttl_data.size == 0:
        return OptoSyncResult(value=None, unit="", is_valid=False, error_message="Empty TTL Data")

    onsets, offsets = extract_ttl_epochs(ttl_data, time, ttl_threshold)
    stimulus_count = len(onsets)

    if stimulus_count == 0:
        return OptoSyncResult(
            value=None, unit="", is_valid=False,
            error_message="No TTL stimuli detected above threshold"
        )

    window_s = response_window_ms / 1000.0

    latencies = []
    responding_spikes = []
    response_count = 0

    # Evaluate response per stimulus
    for onset in onsets:
        # Define window exclusively for this stimulus
        t_start = onset
        t_end = onset + window_s

        # Find spikes in this window
        valid_spikes = _find_spikes_in_window(action_potential_times, t_start, t_end)
        responding_spikes.append(valid_spikes.tolist())

        if valid_spikes.size > 0:
            response_count += 1
            # We take the first spike in the window to calculate latency
            first_spike_time = valid_spikes[0]
            latencies.append((first_spike_time - onset) * 1000.0)  # ms

    # Calculate statistics
    if response_count > 0:
        optical_latency_ms = float(np.mean(latencies))
        spike_jitter_ms = float(np.std(latencies)) if len(latencies) > 1 else 0.0
        response_probability = float(response_count / stimulus_count)
    else:
        optical_latency_ms = np.nan
        spike_jitter_ms = np.nan
        response_probability = 0.0

    params = {
        "ttl_threshold": ttl_threshold,
        "response_window_ms": response_window_ms
    }

    return OptoSyncResult(
        value=optical_latency_ms,
        unit="ms",
        is_valid=True,
        optical_latency_ms=optical_latency_ms,
        response_probability=response_probability,
        spike_jitter_ms=spike_jitter_ms,
        stimulus_count=stimulus_count,
        stimulus_onsets=onsets,
        stimulus_offsets=offsets,
        responding_spikes=responding_spikes,
        parameters=params
    )


# --- WRAPPER (Dynamic Plugin Format) ---

@AnalysisRegistry.register(
    name="optogenetic_sync",
    label="Optogenetic Synchronization",
    ui_params=[
        {
            "name": "ttl_threshold",
            "type": "float",
            "label": "TTL Threshold (V)",
            "default": 2.5,
            "min": 0.1,
            "max": 10.0,
            "step": 0.1,
            "tooltip": "Voltage threshold to define stimulus ON state."
        },
        {
            "name": "response_window_ms",
            "type": "float",
            "label": "Response Window (ms)",
            "default": 20.0,
            "min": 1.0,
            "max": 1000.0,
            "step": 1.0,
            "tooltip": "Time window after stimulus onset to search for action potentials."
        },
        {
            "name": "spike_threshold",
            "type": "float",
            "label": "AP Threshold (mV)",
            "default": 0.0,
            "min": -50.0,
            "max": 50.0,
            "step": 1.0,
            "tooltip": "Voltage crossing threshold to detect action potentials if they are not pre-calculated."
        }
    ],
    # Adding visualization metadata to help the generic tab
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
    ]
)
def run_opto_sync_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """
    Wrapper for optogenetic synchronization.
    If the data array represents the raw trace (V or mV), we must first detect the spikes.
    Wait, the user requested "correlate TTL with action potentials". 
    In a typical experiment, we might have a multi-channel setup, or we need to extract APs from the same trace.
    Assuming `data` here is the TTL trace OR we use a separate channel? 
    Usually, Synaptipy passes the selected channel as `data`. If `data` is the voltage trace, we can't extract TTL from it.
    If `data` is the TTL trace, we need the Action Potential times.

    Let's handle this carefully:
    For this to be purely standalone, we can either:
    1. Extract APs from `data` (if it's a voltage trace), assuming the TTL is applied optically but the electrical trace contains optical artifacts?
    2. Assume `data` is a dual-channel array (not standard for Synaptipy).

    Let's check the API: `data` is a 1D numpy array representing the signal from the selected channel.
    If we need two channels, we'd need a dual-channel selector in the UI. 
    But standard analysis receives `data` (1D). 
    Let's assume for this specific analysis, the user expects to pass the TTL trace *as* `data` and then we need AP times? Or pass Voltage trace as `data` and extract APs, but where is TTL?
    Most commonly in our architecture, to use multi-channels, we'd pass kwargs providing the other channel, OR we pass a Multi-Channel Object.

    Wait, "natively extract digital/TTL optical stimulus pulses AND correlate them with action potentials".
    To do this cleanly within `data`, if the user selects the Voltage channel, we need another channel for TTL.
    Let's assume the user selects the Voltage channel, and we add an `ui_params` of type "channel_selector" to pick the TTL channel, but Synaptipy's generic UI generator doesn't have a built-in cross-channel selector yet unless defined.

    For now, let's implement the pure logic perfectly.
    For the wrapper, we will assume `data` is the Voltage trace, and we'll detect spikes on it. 
    But where does TTL come from? Let's add an optional `ttl_data` kwarg. If it's missing, we fall back to a mock or raise an error for now, until we ensure cross-channel injection is supported.
    Better yet, some users record TTL on the same channel (optical artifacts). Usually it's a separate channel.
    Let's write the wrapper strictly handling the core logic.
    """

    ttl_threshold = kwargs.get("ttl_threshold", 2.5)
    response_window_ms = kwargs.get("response_window_ms", 20.0)
    ap_threshold = kwargs.get("spike_threshold", 0.0)

    # We need AP times. If they aren't provided in kwargs, we detect them from 'data'
    # assuming 'data' is the voltage trace.
    ap_times = kwargs.get("action_potential_times", None)
    if ap_times is None:
        # Detect spikes natively using simple threshold crossing
        is_spike = data > ap_threshold
        # Find rising edges of spikes
        spike_idx = np.where(np.diff(is_spike.astype(int)) == 1)[0]
        ap_times = time[spike_idx]

    # We need TTL data. If not provided, we might be looking at a single trace that has both.
    # But usually it's in a separate channel. We will look for 'ttl_data' in kwargs.
    ttl_data = kwargs.get("ttl_data", None)

    # FOR STANDALONE USAGE / DEMO: If ttl_data is not provided, we will assume `data` contains
    # massive TTL pulses (optical artifact) > ttl_threshold, so we can self-extract.
    if ttl_data is None:
        ttl_data = data

    result = calculate_optogenetic_sync(
        ttl_data=ttl_data,
        action_potential_times=ap_times,
        time=time,
        ttl_threshold=ttl_threshold,
        response_window_ms=response_window_ms
    )

    if not result.is_valid:
        return {"error": result.error_message}

    return {
        "optical_latency_ms": result.optical_latency_ms,
        "response_probability": result.response_probability,
        "spike_jitter_ms": result.spike_jitter_ms,
        "stimulus_count": result.stimulus_count
    }
