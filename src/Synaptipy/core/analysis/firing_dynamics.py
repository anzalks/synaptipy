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
from Synaptipy.core.analysis.single_spike import calculate_spike_features, detect_spikes_threshold
from Synaptipy.core.constants import EPSILON_ISI_SUM, EPSILON_ISI_SUM_SQ
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
    broadening_indices = []  # Width_last / Width_first within each sweep

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
            # Guard against tiny or zero first ISI (< 1 µs is artifact)
            if isis[0] > 1e-6:
                ratio = float(isis[-1] / isis[0])
                # Clip to reasonable range to prevent huge ratios from artifacts
                adaptation_ratios.append(float(np.clip(ratio, 0, 1000)))
            else:
                adaptation_ratios.append(np.nan)
        else:
            adaptation_ratios.append(np.nan)

        # Spike Broadening Index: half-width of last spike / half-width of first spike
        broadening_idx = np.nan
        if count >= 2 and result.spike_indices is not None and len(result.spike_indices) >= 2:
            try:
                spike_idx_arr = result.spike_indices
                features = calculate_spike_features(data, time, spike_idx_arr)
                widths = [getattr(f, "half_width", None) for f in features]
                valid_widths = [w for w in widths if w is not None and not np.isnan(w) and w > 0]
                if len(valid_widths) >= 2:
                    broadening_idx = float(valid_widths[-1] / valid_widths[0])
            except (ValueError, TypeError, IndexError):
                pass
        broadening_indices.append(broadening_idx)

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
    fi_p_value = None
    fi_slope_se = None
    if rheobase_idx != -1 and rheobase_idx < len(sorted_counts) - 1:
        valid_slice = slice(rheobase_idx, None)
        x = sorted_currents[valid_slice]
        y = sorted_freqs[valid_slice]
        # Truncate at the maximum firing frequency to exclude the depolarisation
        # block region where frequency drops back toward 0 Hz.  Including those
        # points would produce a spuriously flat or negative slope.
        peak_idx = int(np.argmax(y)) + 1  # +1 so the peak point itself is included
        x = x[:peak_idx]
        y = y[:peak_idx]
        if len(x) >= 2:
            try:
                slope, _intercept, r_value, p_value, std_err = linregress(x, y)
                fi_slope = float(slope)
                r_squared = float(r_value**2)
                fi_p_value = float(p_value)
                fi_slope_se = float(std_err)
            except (ValueError, TypeError) as e:
                log.warning(f"Linear regression failed: {e}")

    return {
        "rheobase_pa": rheobase_pa,
        "fi_slope": fi_slope,
        "fi_r_squared": r_squared,
        "fi_p_value": fi_p_value,
        "fi_slope_se": fi_slope_se,
        "max_freq": float(np.max(frequencies)) if frequencies else 0.0,
        "spike_counts": spike_counts,
        "frequencies": frequencies,
        "adaptation_ratios": adaptation_ratios,
        "broadening_indices": broadening_indices,
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
        {
            "name": "analysis_start_s",
            "label": "Analysis Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Clip each sweep to this start time before counting spikes.",
        },
        {
            "name": "analysis_end_s",
            "label": "Analysis End (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Clip each sweep to this end time before counting spikes.",
        },
    ],
)
def run_excitability_analysis_wrapper(  # noqa: C901
    data_list: List[np.ndarray], time_list: List[np.ndarray], sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for Excitability Analysis (F-I Curve)."""
    try:
        threshold = kwargs.get("threshold", -20.0)
        start_current = kwargs.get("start_current", 0.0)
        step_current = kwargs.get("step_current", 10.0)
        refractory_ms = kwargs.get("refractory_ms", 2.0)
        analysis_start_s = float(kwargs.get("analysis_start_s", 0.0))
        analysis_end_s = float(kwargs.get("analysis_end_s", 0.5))

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

        # Clip each sweep to the analysis window when a valid window is set.
        if analysis_end_s > analysis_start_s:
            clipped_data: List[np.ndarray] = []
            clipped_time: List[np.ndarray] = []
            for d, t in zip(data_list, time_list):
                mask = (t >= analysis_start_s) & (t <= analysis_end_s)
                clipped_data.append(d[mask] if mask.any() else d)
                clipped_time.append(t[mask] if mask.any() else t)
            data_list = clipped_data
            time_list = clipped_time

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
                "fi_p_value": results.get("fi_p_value"),
                "fi_slope_se": results.get("fi_slope_se"),
                "max_freq_hz": results["max_freq"],
                "frequencies": results["frequencies"],
                "adaptation_ratios": results["adaptation_ratios"],
                "broadening_indices": results.get("broadening_indices", []),
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
    dynamic_burst: bool = False,
    burst_isi_fraction: float = 0.3,
    parameters: Optional[Dict[str, Any]] = None,
    data: Optional[np.ndarray] = None,
    time: Optional[np.ndarray] = None,
) -> BurstResult:
    """
    Detect bursts in a spike train.

    Args:
        spike_times: 1D array of spike times (seconds).
        max_isi_start: Max ISI to start a burst (s). Ignored when dynamic_burst=True.
        max_isi_end: Max ISI to continue a burst (s). Ignored when dynamic_burst=True.
        min_spikes: Minimum spikes per burst.
        dynamic_burst: When True, compute the mean ISI of the whole train and
            define the burst boundary as ``burst_isi_fraction * mean_isi``.
            This abandons hardcoded thresholds in favour of the train's own
            temporal structure.
        burst_isi_fraction: Fraction of mean ISI used as burst boundary when
            ``dynamic_burst=True`` (default 0.3, i.e. 30%).

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

    # Dynamic threshold: fraction of the global mean ISI
    if dynamic_burst and len(isis) >= 1:
        mean_isi = float(np.mean(isis))
        dyn_threshold = burst_isi_fraction * mean_isi
        max_isi_start = dyn_threshold
        max_isi_end = dyn_threshold

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

    intra_burst_freqs = []
    for b in bursts:
        dur = b[-1] - b[0]
        if dur > 0:
            intra_burst_freqs.append((len(b) - 1) / dur)
    burst_mean_frequency_hz = float(np.mean(intra_burst_freqs)) if intra_burst_freqs else None

    inter_burst_voltage_mv = None
    if data is not None and time is not None and num_bursts > 1:
        inter_burst_v_list = []
        for i in range(num_bursts - 1):
            end_burst1 = bursts[i][-1]
            start_burst2 = bursts[i + 1][0]
            mask = (time > end_burst1) & (time < start_burst2)
            if np.any(mask):
                inter_burst_v_list.append(np.mean(data[mask]))
        if inter_burst_v_list:
            inter_burst_voltage_mv = float(np.mean(inter_burst_v_list))

    return BurstResult(
        value=num_bursts,
        unit="bursts",
        is_valid=True,
        burst_count=num_bursts,
        spikes_per_burst_avg=float(np.mean(spikes_per_burst)),
        burst_duration_avg=float(np.mean(burst_durations)),
        burst_freq_hz=burst_freq,
        burst_mean_frequency_hz=burst_mean_frequency_hz,
        inter_burst_voltage_mv=inter_burst_voltage_mv,
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
    dynamic_burst: bool = False,
    burst_isi_fraction: float = 0.3,
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
        spike_result.spike_times,
        max_isi_start=max_isi_start,
        max_isi_end=max_isi_end,
        dynamic_burst=dynamic_burst,
        burst_isi_fraction=burst_isi_fraction,
        parameters=parameters,
        data=data,
        time=time,
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
        {"name": "dynamic_burst", "label": "Dynamic ISI Threshold", "type": "bool", "default": False},
        {
            "name": "burst_isi_fraction",
            "label": "Burst ISI Fraction:",
            "type": "float",
            "default": 0.3,
            "min": 0.01,
            "max": 1.0,
            "decimals": 2,
            "tooltip": "Spikes are in a burst if ISI < this fraction of the train mean ISI.",
            "visible_when": {"param": "dynamic_burst", "value": True},
        },
        {
            "name": "analysis_start_s",
            "label": "Analysis Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Clip the trace to this start time before detecting spikes.",
        },
        {
            "name": "analysis_end_s",
            "label": "Analysis End (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Clip the trace to this end time before detecting spikes.",
        },
    ],
    plots=[{"type": "brackets", "data": "bursts", "color": "r"}],
)
def run_burst_analysis_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """Wrapper for Burst Analysis."""
    threshold = kwargs.get("threshold", -20.0)
    max_isi_start = kwargs.get("max_isi_start", 0.01)
    max_isi_end = kwargs.get("max_isi_end", 0.1)
    dynamic_burst = kwargs.get("dynamic_burst", False)
    burst_isi_fraction = float(kwargs.get("burst_isi_fraction", 0.3))
    analysis_start_s = float(kwargs.get("analysis_start_s", 0.0))
    analysis_end_s = float(kwargs.get("analysis_end_s", 0.5))

    # Clip to analysis window when a valid window is specified.
    if analysis_end_s > analysis_start_s:
        mask = (time >= analysis_start_s) & (time <= analysis_end_s)
        if mask.any():
            data = data[mask]
            time = time[mask]

    result = analyze_spikes_and_bursts(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        threshold=threshold,
        max_isi_start=max_isi_start,
        max_isi_end=max_isi_end,
        dynamic_burst=dynamic_burst,
        burst_isi_fraction=burst_isi_fraction,
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
    adaptation_index: Optional[float] = None
    first_spike_delay_s: Optional[float] = None
    isis: Optional[np.ndarray] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        if self.is_valid:
            cv_str = f"{self.cv:.3f}" if self.cv is not None else "N/A"
            lv_str = f"{self.lv:.3f}" if self.lv is not None else "N/A"
            return f"TrainDynamicsResult(Spikes={self.spike_count}, CV={cv_str}, LV={lv_str})"
        return f"TrainDynamicsResult(Error: {self.error_message})"


def calculate_train_dynamics(spike_times: np.ndarray, analysis_start_s: float = 0.0) -> TrainDynamicsResult:
    """
    Compute native spike train statistical metrics.

    Includes Spike Frequency Adaptation (SFA) logic that mirrors established methodologies
    adaptation index methodologies (normalized differences between consecutive ISIs).

    Args:
        spike_times: 1D NumPy array of spike times in seconds.
        analysis_start_s: float, start time of stimulus/analysis window in seconds.

    Returns:
        TrainDynamicsResult object encapsulating calculated dynamics metrics.
    """
    spike_count = len(spike_times)
    first_spike_delay_s = float(spike_times[0] - analysis_start_s) if spike_count > 0 else float(np.nan)

    if spike_count < 2:
        return TrainDynamicsResult(
            value=None,
            unit="",
            is_valid=False,
            error_message="Requires at least 2 spikes for ISI calculations.",
            spike_count=spike_count,
            first_spike_delay_s=first_spike_delay_s,
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
            adaptation_index=np.nan,
            first_spike_delay_s=first_spike_delay_s,
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
            adaptation_index=np.nan,
            first_spike_delay_s=first_spike_delay_s,
            isis=isis,
        )

    isi_i = isis[:-1]
    isi_next = isis[1:]

    # Guard against division by zero with epsilon comparison
    cv2_denominator = isi_next + isi_i
    cv2_safe_mask = cv2_denominator > EPSILON_ISI_SUM
    cv2_array = np.where(cv2_safe_mask, 2.0 * np.abs(isi_next - isi_i) / cv2_denominator, np.nan)
    cv2_val = float(np.nanmean(cv2_array))

    lv_denominator_sq = (isi_i + isi_next) ** 2
    lv_safe_mask = lv_denominator_sq > EPSILON_ISI_SUM_SQ
    lv_array = np.where(lv_safe_mask, 3.0 * ((isi_i - isi_next) ** 2) / lv_denominator_sq, np.nan)
    lv_val = float(np.nanmean(lv_array))

    # Adaptation index: mean of (ISI[i+1] - ISI[i]) / (ISI[i+1] + ISI[i])
    adapt_denominator = isi_next + isi_i
    adapt_safe_mask = adapt_denominator > EPSILON_ISI_SUM
    adapt_array = np.where(adapt_safe_mask, (isi_next - isi_i) / adapt_denominator, np.nan)
    adaptation_index = float(np.nanmean(adapt_array))

    return TrainDynamicsResult(
        value=cv,
        unit="",
        is_valid=True,
        spike_count=spike_count,
        mean_isi_s=mean_isi,
        cv=cv,
        cv2=cv2_val,
        lv=lv_val,
        adaptation_index=adaptation_index,
        first_spike_delay_s=first_spike_delay_s,
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
            "default": -20.0,
            "min": -100.0,
            "max": 50.0,
            "step": 1.0,
            "tooltip": "Threshold to detect action potentials. Lower this for blunted or dendritic spikes.",
        },
        {
            "name": "analysis_start_s",
            "label": "Analysis Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Clip the trace to this start time before detecting spikes.",
        },
        {
            "name": "analysis_end_s",
            "label": "Analysis End (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Clip the trace to this end time before detecting spikes.",
        },
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
def run_train_dynamics_wrapper(  # noqa: C901
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for Spike Train Dynamics."""
    from Synaptipy.core.analysis.single_spike import calculate_spike_features

    ap_threshold = kwargs.get("spike_threshold", 0.0)
    ap_times = kwargs.get("action_potential_times", None)
    analysis_start_s = float(kwargs.get("analysis_start_s", 0.0))
    analysis_end_s = float(kwargs.get("analysis_end_s", 0.5))
    spike_indices = None
    # start_idx tracks the offset of the clipped window within the original
    # time array.  spike_indices returned by detect_spikes_threshold are
    # relative to the clipped subarray; adding start_idx converts them to
    # absolute indices so that show_spikes overlays land on actual peaks.
    start_idx = 0

    # Clip to analysis window when a valid window is specified.
    if analysis_end_s > analysis_start_s:
        mask = (time >= analysis_start_s) & (time <= analysis_end_s)
        if mask.any():
            start_idx = int(np.searchsorted(time, analysis_start_s))
            data = data[mask]
            time = time[mask]

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

    result = calculate_train_dynamics(ap_times, analysis_start_s=analysis_start_s)
    if not result.is_valid:
        return {"module_used": "firing_dynamics", "metrics": {"train_dynamics_error": result.error_message}}

    isi_ms = (result.isis * 1000.0).tolist() if result.isis is not None and len(result.isis) > 0 else []
    isi_numbers = list(range(1, len(isi_ms) + 1))

    # Spike broadening index: half_width_last / half_width_first for trains >= 3 spikes
    spike_broadening_index = float(np.nan)
    if spike_indices is not None and len(spike_indices) >= 3:
        try:
            features_list = calculate_spike_features(data, time, spike_indices)
            widths = [getattr(f, "half_width", None) for f in features_list]
            valid_widths = [w for w in widths if w is not None and not np.isnan(w)]
            if len(valid_widths) >= 3:
                spike_broadening_index = (
                    float(valid_widths[-1] / valid_widths[0]) if valid_widths[0] > 0 else float(np.nan)
                )
        except Exception as e:
            log.warning(f"Could not compute spike broadening index: {e}")

    metrics: Dict[str, Any] = {
        "spike_count": result.spike_count,
        "mean_isi_s": result.mean_isi_s,
        "cv": result.cv,
        "cv2": result.cv2,
        "lv": result.lv,
        "adaptation_index": float(result.adaptation_index) if result.adaptation_index is not None else float(np.nan),
        "first_spike_delay_ms": (
            result.first_spike_delay_s * 1000.0 if result.first_spike_delay_s is not None else float(np.nan)
        ),
        "first_isi_ms": float(isi_ms[0]) if len(isi_ms) > 0 else float(np.nan),
        "spike_broadening_index": spike_broadening_index,
        "isi_numbers": isi_numbers,
        "isi_ms": isi_ms,
    }
    if spike_indices is not None:
        # Convert relative (clipped) indices to absolute (full-array) indices
        # so that the show_spikes overlay in metadata_driven.py lands on the
        # actual spike peaks rather than the start of the recording.
        metrics["spike_indices"] = spike_indices + start_idx

    return {"module_used": "firing_dynamics", "metrics": metrics}


# ---------------------------------------------------------------------------
# Module-level tab aggregator
# ---------------------------------------------------------------------------
@AnalysisRegistry.register(
    "firing_dynamics",
    label="Excitability",
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
