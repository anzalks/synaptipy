# src/Synaptipy/core/analysis/burst_analysis.py
# -*- coding: utf-8 -*-
"""
Analysis functions for detecting and characterizing bursts of action potentials.
"""
import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold
from Synaptipy.core.results import BurstResult

log = logging.getLogger(__name__)


def calculate_bursts_logic(
    spike_times: np.ndarray,
    max_isi_start: float = 0.01,
    max_isi_end: float = 0.2,
    min_spikes: int = 2,
    parameters: Dict[str, Any] = None,
) -> BurstResult:
    """
    Detects bursts in a spike train (Pure Logic).

    Args:
        spike_times: 1D array of spike times (seconds).
        max_isi_start: Max ISI to start a burst (seconds).
        max_isi_end: Max ISI to continue a burst (seconds).
        min_spikes: Minimum number of spikes to constitute a burst.

    Returns:
        BurstResult object
    """
    if spike_times is None or len(spike_times) < min_spikes:
        return BurstResult(
            value=0,
            unit="bursts",
            is_valid=True,
            burst_count=0,
            spikes_per_burst_avg=0.0,
            burst_duration_avg=0.0,
            burst_freq_hz=0.0,
            bursts=[],
            parameters=parameters or {},
        )

    isis = np.diff(spike_times)
    bursts = []
    current_burst = []

    in_burst = False

    for i, isi in enumerate(isis):
        if not in_burst:
            if isi <= max_isi_start:
                in_burst = True
                current_burst = [spike_times[i], spike_times[i + 1]]
        else:
            if isi <= max_isi_end:
                current_burst.append(spike_times[i + 1])
            else:
                in_burst = False
                if len(current_burst) >= min_spikes:
                    bursts.append(current_burst)
                current_burst = []

    # Check if last burst was valid
    if in_burst and len(current_burst) >= min_spikes:
        bursts.append(current_burst)

    # Calculate stats
    num_bursts = len(bursts)
    if num_bursts == 0:
        return BurstResult(value=0, unit="bursts", is_valid=True, burst_count=0, bursts=[], parameters=parameters or {})

    spikes_per_burst = [len(b) for b in bursts]
    burst_durations = [b[-1] - b[0] for b in bursts]

    duration = spike_times[-1] - spike_times[0] if len(spike_times) > 0 else 0
    burst_freq = num_bursts / duration if duration > 0 else 0.0

    return BurstResult(
        value=num_bursts,
        unit="bursts",
        is_valid=True,
        burst_count=num_bursts,
        spikes_per_burst_avg=np.mean(spikes_per_burst),
        burst_duration_avg=np.mean(burst_durations),
        burst_freq_hz=burst_freq,
        bursts=bursts,
        parameters=parameters or {},
    )


def analyze_spikes_and_bursts(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    threshold: float,
    max_isi_start: float,
    max_isi_end: float,
    refractory_ms: float = 2.0,
    parameters: Dict[str, Any] = None,
) -> BurstResult:
    """
    Orchestration: Detects spikes then detects bursts.
    """
    refractory_samples = int((refractory_ms / 1000.0) * sampling_rate)

    spike_result = detect_spikes_threshold(data, time, threshold, refractory_samples, parameters=parameters)

    if not spike_result.is_valid:
        res = BurstResult(value=0, unit="bursts", is_valid=False, error_message=spike_result.error_message)
        # Propagate error
        return res

    if spike_result.spike_times is None:
        return BurstResult(value=0, unit="bursts", is_valid=True, burst_count=0, bursts=[])

    return calculate_bursts_logic(
        spike_result.spike_times, max_isi_start=max_isi_start, max_isi_end=max_isi_end, parameters=parameters
    )


@AnalysisRegistry.register(
    "burst_analysis",
    label="Burst",
    ui_params=[
        {
            "name": "threshold",
            "label": "Threshold (mV):",
            "type": "float",
            "default": -20.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "max_isi_start",
            "label": "Max ISI Start (s):",
            "type": "float",
            "default": 0.01,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "max_isi_end",
            "label": "Max ISI End (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "min_spikes",
            "label": "Min Spikes:",
            "type": "int",
            "default": 2,
            "min": 2,
            "max": 1000,
        },
    ],
    plots=[
        {"type": "brackets", "data": "bursts", "color": "r"},
    ],
)
def run_burst_analysis_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """
    Wrapper for Burst Analysis.
    """
    # 1. Extract params (Wrapper Logic)
    threshold = kwargs.get("threshold", -20.0)
    max_isi_start = kwargs.get("max_isi_start", 0.01)
    max_isi_end = kwargs.get("max_isi_end", 0.1)

    # 2. Call Core Logic (Orchestrator)
    result = analyze_spikes_and_bursts(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        threshold=threshold,
        max_isi_start=max_isi_start,
        max_isi_end=max_isi_end,
        parameters=kwargs,
    )

    # 3. Flattener (Result -> Dict)
    if not result.is_valid:
        return {"burst_error": result.error_message}

    return {
        "burst_count": result.burst_count,
        "spikes_per_burst_avg": result.spikes_per_burst_avg,
        "burst_duration_avg": result.burst_duration_avg,
        "burst_freq_hz": result.burst_freq_hz,
        "bursts": result.bursts,
        # Pass the full object if GUI needs it for advanced visualization
        "result": result,
    }
