# src/Synaptipy/core/analysis/firing_dynamics.py
# -*- coding: utf-8 -*-
"""
Core Protocol Module 3: Firing Dynamics.

Consolidates: Excitability (F-I curve), Burst Analysis, and Spike Train
    Dynamics into one self-contained module.

All registry wrapper functions return::

    {
        "module_used": "firing_dynamics",
        "metrics": { ... flat result keys ... }
    }
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.stats import linregress

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.analysis.single_spike import detect_spikes_threshold
from Synaptipy.core.results import AnalysisResult, BurstResult

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excitability (F-I Curve)
# ---------------------------------------------------------------------------


def calculate_fi_curve(  # noqa: C901
    sweeps: List[np.ndarray],
    time_vectors: List[np.ndarray],
    current_steps: Optional[List[float]] = None,
    threshold: float = -20.0,
    refractory_ms: float = 2.0,
) -> Dict[str, Any]:
    """
    Calculate F-I Curve properties from a set of sweeps.

    Args:
        sweeps: List of voltage traces (1D arrays).
        time_vectors: List of corresponding time vectors.
        current_steps: List of current amplitudes for each sweep. If None, inferred.
        threshold: Spike detection threshold (mV).
        refractory_ms: Refractory period (ms).

    Returns:
        Dictionary with rheobase_pa, fi_slope, max_freq, spike_counts, frequencies,
        adaptation_ratios, current_steps.
    """
    num_sweeps = len(sweeps)
    if num_sweeps == 0:
        return {"error": "No sweeps provided"}

    if current_steps is None:
        log.warning("Current steps not provided. Using sweep indices as proxy for current steps.")
        current_steps = list(range(num_sweeps))

    if len(current_steps) != num_sweeps:
        log.warning(f"Mismatch between sweeps ({num_sweeps}) and current_steps ({len(current_steps)}). Truncating.")
        min_len = min(num_sweeps, len(current_steps))
        sweeps = sweeps[:min_len]
        time_vectors = time_vectors[:min_len]
        current_steps = current_steps[:min_len]

    spike_counts = []
    frequencies = []
    adaptation_ratios = []

    for i, (data, time) in enumerate(zip(sweeps, time_vectors)):
        dt = time[1] - time[0] if len(time) > 1 else 1e-4
        sampling_rate = 1.0 / dt
        refractory_samples = int((refractory_ms / 1000.0) * sampling_rate)
        result = detect_spikes_threshold(data, time, threshold, refractory_samples)
        count = len(result.spike_indices) if result.spike_indices is not None else 0
        freq = result.mean_frequency if result.mean_frequency is not None else 0.0
        spike_counts.append(count)
        frequencies.append(freq)
        if count >= 3 and result.spike_times is not None:
            isis = np.diff(result.spike_times)
            if isis[0] > 0:
                adaptation_ratios.append(float(isis[-1] / isis[0]))
            else:
                adaptation_ratios.append(np.nan)
        else:
            adaptation_ratios.append(np.nan)

    sorted_indices = np.argsort(current_steps)
    sorted_currents = np.array(current_steps)[sorted_indices]
    sorted_counts = np.array(spike_counts)[sorted_indices]
    sorted_freqs = np.array(frequencies)[sorted_indices]

    rheobase_pa = None
    rheobase_idx = -1
    for i, count in enumerate(sorted_counts):
        if count > 0:
            rheobase_pa = float(sorted_currents[i])
            rheobase_idx = i
            break

    fi_slope = None
    r_squared = None
    if rheobase_idx != -1 and rheobase_idx < len(sorted_counts) - 1:
        valid_slice = slice(rheobase_idx, None)
        x = sorted_currents[valid_slice]
        y = sorted_freqs[valid_slice]
        if len(x) >= 2:
            try:
                slope, _intercept, r_value, _p, _se = linregress(x, y)
                fi_slope = float(slope)
                r_squared = float(r_value**2)
            except (ValueError, TypeError) as e:
                log.warning(f"Linear regression failed: {e}")

    return {
        "rheobase_pa": rheobase_pa,
        "fi_slope": fi_slope,
        "fi_r_squared": r_squared,
        "max_freq": float(np.max(frequencies)) if frequencies else 0.0,
        "spike_counts": spike_counts,
        "frequencies": frequencies,
        "adaptation_ratios": adaptation_ratios,
        "current_steps": current_steps,
    }


@AnalysisRegistry.register(
    "excitability_analysis",
    label="Excitability",
    requires_multi_trial=True,
    plots=[
        {
            "type": "popup_xy",
            "title": "F-I Curve",
            "x": "current_steps",
            "y": "frequencies",
            "x_label": "Current (pA)",
            "y_label": "Frequency (Hz)",
        },
    ],
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
            "name": "start_current",
            "label": "Start Current (pA):",
            "type": "float",
            "default": 0.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "step_current",
            "label": "Step Current (pA):",
            "type": "float",
            "default": 10.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "refractory_ms",
            "label": "Refractory (ms):",
            "type": "float",
            "default": 2.0,
            "min": 0.0,
            "max": 1000.0,
            "decimals": 2,
        },
    ],
)
def run_excitability_analysis_wrapper(
    data_list: List[np.ndarray], time_list: List[np.ndarray], sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for Excitability Analysis (F-I Curve)."""
    try:
        threshold = kwargs.get("threshold", -20.0)
        start_current = kwargs.get("start_current", 0.0)
        step_current = kwargs.get("step_current", 10.0)
        refractory_ms = kwargs.get("refractory_ms", 2.0)

        if isinstance(data_list, np.ndarray):
            if data_list.ndim == 1:
                data_list = [data_list]
                time_list = [time_list] if isinstance(time_list, np.ndarray) else time_list
            elif data_list.ndim == 2:
                data_list = [data_list[i] for i in range(data_list.shape[0])]
                if isinstance(time_list, np.ndarray) and time_list.ndim == 1:
                    time_list = [time_list for _ in range(len(data_list))]
                elif isinstance(time_list, np.ndarray) and time_list.ndim == 2:
                    time_list = [time_list[i] for i in range(time_list.shape[0])]

        if isinstance(time_list, np.ndarray):
            time_list = [time_list]

        num_sweeps = len(data_list)
        current_steps = [start_current + i * step_current for i in range(num_sweeps)]

        results = calculate_fi_curve(
            sweeps=data_list,
            time_vectors=time_list,
            current_steps=current_steps,
            threshold=threshold,
            refractory_ms=refractory_ms,
        )

        if "error" in results:
            return {"module_used": "firing_dynamics", "metrics": {"excitability_error": results["error"]}}

        return {
            "module_used": "firing_dynamics",
            "metrics": {
                "rheobase_pa": results["rheobase_pa"],
                "fi_slope": results["fi_slope"],
                "fi_r_squared": results["fi_r_squared"],
                "max_freq_hz": results["max_freq"],
                "frequencies": results["frequencies"],
                "adaptation_ratios": results["adaptation_ratios"],
                "current_steps": results["current_steps"],
            },
        }

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_excitability_analysis_wrapper: {e}", exc_info=True)
        return {"module_used": "firing_dynamics", "metrics": {"excitability_error": str(e)}}


# ---------------------------------------------------------------------------
# Burst Analysis
# ---------------------------------------------------------------------------


def calculate_bursts_logic(
    spike_times: np.ndarray,
    max_isi_start: float = 0.01,
    max_isi_end: float = 0.2,
    min_spikes: int = 2,
    parameters: Optional[Dict[str, Any]] = None,
) -> BurstResult:
    """
    Detect bursts in a spike train.

    Args:
        spike_times: 1D array of spike times (seconds).
        max_isi_start: Max ISI to start a burst (s).
        max_isi_end: Max ISI to continue a burst (s).
        min_spikes: Minimum spikes per burst.

    Returns:
        BurstResult object.
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
    current_burst: List[float] = []
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

    if in_burst and len(current_burst) >= min_spikes:
        bursts.append(current_burst)

    num_bursts = len(bursts)
    if num_bursts == 0:
        return BurstResult(
            value=0,
            unit="bursts",
            is_valid=True,
            burst_count=0,
            bursts=[],
            parameters=parameters or {},
        )

    spikes_per_burst = [len(b) for b in bursts]
    burst_durations = [b[-1] - b[0] for b in bursts]
    duration = spike_times[-1] - spike_times[0] if len(spike_times) > 0 else 0
    burst_freq = num_bursts / duration if duration > 0 else 0.0

    return BurstResult(
        value=num_bursts,
        unit="bursts",
        is_valid=True,
        burst_count=num_bursts,
        spikes_per_burst_avg=float(np.mean(spikes_per_burst)),
        burst_duration_avg=float(np.mean(burst_durations)),
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
    parameters: Optional[Dict[str, Any]] = None,
) -> BurstResult:
    """Detect spikes then detect bursts."""
    refractory_samples = int((refractory_ms / 1000.0) * sampling_rate)
    spike_result = detect_spikes_threshold(data, time, threshold, refractory_samples, parameters=parameters)
    if not spike_result.is_valid:
        return BurstResult(value=0, unit="bursts", is_valid=False, error_message=spike_result.error_message)
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
        {"name": "min_spikes", "label": "Min Spikes:", "type": "int", "default": 2, "min": 2, "max": 1000},
    ],
    plots=[{"type": "brackets", "data": "bursts", "color": "r"}],
)
def run_burst_analysis_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """Wrapper for Burst Analysis."""
    threshold = kwargs.get("threshold", -20.0)
    max_isi_start = kwargs.get("max_isi_start", 0.01)
    max_isi_end = kwargs.get("max_isi_end", 0.1)

    result = analyze_spikes_and_bursts(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        threshold=threshold,
        max_isi_start=max_isi_start,
        max_isi_end=max_isi_end,
        parameters=kwargs,
    )

    if not result.is_valid:
        return {"module_used": "firing_dynamics", "metrics": {"burst_error": result.error_message}}

    return {
        "module_used": "firing_dynamics",
        "metrics": {
            "burst_count": result.burst_count,
            "spikes_per_burst_avg": result.spikes_per_burst_avg,
            "burst_duration_avg": result.burst_duration_avg,
            "burst_freq_hz": result.burst_freq_hz,
            "bursts": result.bursts,
            "_result_obj": result,
        },
    }


# ---------------------------------------------------------------------------
# Spike Train Dynamics
# ---------------------------------------------------------------------------


@dataclass
class TrainDynamicsResult(AnalysisResult):
    """Result object for spike train dynamics analysis."""

    spike_count: int = 0
    mean_isi_s: Optional[float] = None
    cv: Optional[float] = None
    cv2: Optional[float] = None
    lv: Optional[float] = None
    isis: Optional[np.ndarray] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        if self.is_valid:
            cv_str = f"{self.cv:.3f}" if self.cv is not None else "N/A"
            lv_str = f"{self.lv:.3f}" if self.lv is not None else "N/A"
            return f"TrainDynamicsResult(Spikes={self.spike_count}, CV={cv_str}, LV={lv_str})"
        return f"TrainDynamicsResult(Error: {self.error_message})"


def calculate_train_dynamics(spike_times: np.ndarray) -> TrainDynamicsResult:
    """
    Compute native spike train statistical metrics.

    Args:
        spike_times: 1D NumPy array of spike times in seconds.

    Returns:
        TrainDynamicsResult.
    """
    spike_count = len(spike_times)
    if spike_count < 2:
        return TrainDynamicsResult(
            value=None,
            unit="",
            is_valid=False,
            error_message="Requires at least 2 spikes for ISI calculations.",
            spike_count=spike_count,
        )

    isis = np.diff(spike_times)
    mean_isi = float(np.mean(isis))
    cv = float(np.std(isis) / mean_isi) if mean_isi > 0 else np.nan

    if spike_count < 3:
        return TrainDynamicsResult(
            value=mean_isi,
            unit="s",
            is_valid=True,
            spike_count=spike_count,
            mean_isi_s=mean_isi,
            cv=cv,
            cv2=np.nan,
            lv=np.nan,
            isis=isis,
        )

    isis = isis[isis > 0]
    if len(isis) < 2:
        return TrainDynamicsResult(
            value=mean_isi,
            unit="s",
            is_valid=True,
            spike_count=spike_count,
            mean_isi_s=mean_isi,
            cv=cv,
            cv2=np.nan,
            lv=np.nan,
            isis=isis,
        )

    isi_i = isis[:-1]
    isi_next = isis[1:]

    cv2_array = 2.0 * np.abs(isi_next - isi_i) / (isi_next + isi_i)
    cv2_val = float(np.mean(cv2_array))

    lv_array = 3.0 * ((isi_i - isi_next) ** 2) / ((isi_i + isi_next) ** 2)
    lv_val = float(np.mean(lv_array))

    return TrainDynamicsResult(
        value=cv,
        unit="",
        is_valid=True,
        spike_count=spike_count,
        mean_isi_s=mean_isi,
        cv=cv,
        cv2=cv2_val,
        lv=lv_val,
        isis=isis,
    )


@AnalysisRegistry.register(
    name="train_dynamics",
    label="Spike Train Dynamics",
    ui_params=[
        {
            "name": "spike_threshold",
            "type": "float",
            "label": "AP Threshold (mV)",
            "default": 0.0,
            "min": -50.0,
            "max": 50.0,
            "step": 1.0,
            "tooltip": "Threshold to detect action potentials.",
        }
    ],
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
        {
            "type": "popup_xy",
            "title": "ISI Plot",
            "x": "isi_numbers",
            "y": "isi_ms",
            "x_label": "ISI Number",
            "y_label": "ISI (ms)",
        },
    ],
)
def run_train_dynamics_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """Wrapper for Spike Train Dynamics."""
    ap_threshold = kwargs.get("spike_threshold", 0.0)
    ap_times = kwargs.get("action_potential_times", None)
    spike_indices = None

    if ap_times is None:
        refractory_samples = max(1, int(0.002 * sampling_rate))
        spike_result = detect_spikes_threshold(
            data, time, threshold=ap_threshold, refractory_samples=refractory_samples
        )
        if spike_result.spike_indices is not None and len(spike_result.spike_indices) > 0:
            spike_indices = spike_result.spike_indices
            ap_times = time[spike_indices]
        else:
            spike_indices = np.array([], dtype=int)
            ap_times = np.array([])

    result = calculate_train_dynamics(ap_times)
    if not result.is_valid:
        return {"module_used": "firing_dynamics", "metrics": {"train_dynamics_error": result.error_message}}

    isi_ms = (result.isis * 1000.0).tolist() if result.isis is not None and len(result.isis) > 0 else []
    isi_numbers = list(range(1, len(isi_ms) + 1))

    metrics: Dict[str, Any] = {
        "spike_count": result.spike_count,
        "mean_isi_s": result.mean_isi_s,
        "cv": result.cv,
        "cv2": result.cv2,
        "lv": result.lv,
        "isi_numbers": isi_numbers,
        "isi_ms": isi_ms,
    }
    if spike_indices is not None:
        metrics["spike_indices"] = spike_indices

    return {"module_used": "firing_dynamics", "metrics": metrics}


# ---------------------------------------------------------------------------
# Module-level tab aggregator
# ---------------------------------------------------------------------------
@AnalysisRegistry.register(
    "firing_dynamics",
    label="Firing Dynamics",
    method_selector={
        "Excitability": "excitability_analysis",
        "Burst Analysis": "burst_analysis",
        "Spike Train Dynamics": "train_dynamics",
    },
    ui_params=[],
    plots=[],
)
def firing_dynamics_module(**kwargs):
    """Module-level aggregator tab for firing-dynamics analyses."""
    return {}
