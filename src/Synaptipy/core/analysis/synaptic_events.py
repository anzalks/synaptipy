# src/Synaptipy/core/analysis/synaptic_events.py
# -*- coding: utf-8 -*-
"""
Core Protocol Module 4: Synaptic Events.

Consolidates all synaptic event detection methods (adaptive threshold,
template matching, baseline-peak-kinetics) from event_detection.py into
one self-contained module.

All registry wrapper functions return::

    {
        "module_used": "synaptic_events",
        "metrics": { ... flat result keys ... }
    }

Exports ``detect_minis_threshold`` as a backward-compatibility alias.
"""

import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy import signal
from scipy.stats import median_abs_deviation

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.results import EventDetectionResult
from Synaptipy.core.signal_processor import find_artifact_windows

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Adaptive Threshold Detection
# ---------------------------------------------------------------------------


def detect_events_threshold(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    threshold: float,
    polarity: str = "negative",
    refractory_period: float = 0.002,
    rolling_baseline_window_ms: Optional[float] = 100.0,
    artifact_mask: Optional[np.ndarray] = None,
) -> EventDetectionResult:
    """
    Detect events using topological prominence to handle shifting baselines.

    Incorporates a 2-STD noise floor check to prevent false positives.
    """
    if data.size < 2 or time.shape != data.shape:
        return EventDetectionResult(value=0, unit="Hz", is_valid=False, error_message="Invalid data/time shape")

    try:
        fs = 1.0 / (time[1] - time[0]) if len(time) > 1 else 10000.0

        if rolling_baseline_window_ms is not None and rolling_baseline_window_ms > 0:
            from scipy.ndimage import median_filter

            window_samples = int((rolling_baseline_window_ms / 1000.0) * fs)
            if window_samples % 2 == 0:
                window_samples += 1
            if window_samples >= 3:
                baseline = median_filter(data, size=window_samples)
                baseline_corrected_data = data - baseline
            else:
                baseline_corrected_data = data
        else:
            baseline_corrected_data = data

        is_negative = polarity == "negative"
        work_data = -baseline_corrected_data if is_negative else baseline_corrected_data

        noise_sd = median_abs_deviation(work_data, scale="normal")
        if noise_sd == 0:
            noise_sd = 1e-12

        abs_threshold = abs(threshold)
        min_prominence = max(abs_threshold, 2.0 * noise_sd)

        distance_samples = max(1, int(refractory_period * fs))
        min_width_samples = max(2, int(0.0002 * fs))

        peaks, _ = signal.find_peaks(
            work_data,
            prominence=min_prominence,
            height=abs_threshold,
            distance=distance_samples,
            width=min_width_samples,
        )

        n_artifacts_rejected = 0
        if artifact_mask is not None and len(peaks) > 0:
            valid_idx_mask = peaks < len(artifact_mask)
            peaks = peaks[valid_idx_mask]
            not_artifact_mask = ~artifact_mask[peaks]
            n_artifacts_rejected = int(np.sum(~not_artifact_mask))
            peaks = peaks[not_artifact_mask]

        event_indices = peaks.astype(int)
        if len(event_indices) > 0:
            event_times = time[event_indices]
            event_amplitudes = baseline_corrected_data[event_indices]
        else:
            event_times = np.array([])
            event_amplitudes = np.array([])

        num_events = len(event_indices)
        duration = time[-1] - time[0] if len(time) > 0 else 0
        frequency = num_events / duration if duration > 0 else 0.0
        mean_amplitude = float(np.mean(event_amplitudes)) if num_events > 0 else 0.0
        std_amplitude = float(np.std(event_amplitudes)) if num_events > 0 else 0.0

        return EventDetectionResult(
            value=frequency,
            unit="Hz",
            is_valid=True,
            event_count=num_events,
            frequency_hz=frequency,
            mean_amplitude=mean_amplitude,
            amplitude_sd=std_amplitude,
            event_indices=event_indices,
            event_times=event_times,
            event_amplitudes=event_amplitudes,
            detection_method="threshold_adaptive_prominence",
            threshold_value=threshold,
            direction=polarity,
            n_artifacts_rejected=n_artifacts_rejected,
            artifact_mask=artifact_mask,
            summary_stats={"noise_sd": float(noise_sd), "min_prominence_used": float(min_prominence)},
        )

    except Exception as e:
        log.error(f"Error during adaptive threshold event detection: {e}", exc_info=True)
        return EventDetectionResult(value=0, unit="Hz", is_valid=False, error_message=str(e))


# Backward compatibility alias
detect_minis_threshold = detect_events_threshold


@AnalysisRegistry.register(
    "event_detection_threshold",
    label="Event Detection (Threshold)",
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
        {"type": "markers", "x": "_event_times", "y": "_event_peaks", "color": "r", "symbol": "o"},
        {"type": "threshold_line", "param": "threshold"},
        {"type": "artifact_overlay"},
    ],
    ui_params=[
        {
            "name": "threshold",
            "label": "Threshold (pA/mV):",
            "type": "float",
            "default": 5.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
        },
        {
            "name": "refractory_period",
            "label": "Refractory (s):",
            "type": "float",
            "default": 0.005,
            "min": 0.0,
            "max": 1.0,
            "decimals": 4,
        },
        {
            "name": "rolling_baseline_window_ms",
            "label": "Rolling Baseline (ms):",
            "type": "float",
            "default": 100.0,
            "min": 0.0,
            "max": 5000.0,
            "decimals": 1,
        },
        {"name": "reject_artifacts", "label": "Reject Artifacts", "type": "bool", "default": False},
        {
            "name": "artifact_slope_threshold",
            "label": "Artifact Slope Thresh:",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
        },
        {"name": "artifact_padding_ms", "label": "Artifact Padding (ms):", "type": "float", "default": 2.0},
    ],
)
def run_event_detection_threshold_wrapper(
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for adaptive threshold event detection."""
    threshold = kwargs.get("threshold", 5.0)
    direction = kwargs.get("direction", "negative")
    refractory_period = kwargs.get("refractory_period", 0.005)
    rolling_baseline_window_ms = kwargs.get("rolling_baseline_window_ms", 100.0)

    reject_artifacts = kwargs.get("reject_artifacts", False)
    artifact_mask = None
    if reject_artifacts:
        slope_thresh = kwargs.get("artifact_slope_threshold", 20.0)
        padding_ms = kwargs.get("artifact_padding_ms", 2.0)
        artifact_mask = find_artifact_windows(data, sampling_rate, slope_thresh, padding_ms)

    result = detect_events_threshold(
        data,
        time,
        threshold,
        direction,
        refractory_period,
        rolling_baseline_window_ms=rolling_baseline_window_ms,
        artifact_mask=artifact_mask,
    )

    if not result.is_valid:
        return {"module_used": "synaptic_events", "metrics": {"event_error": result.error_message}}

    _idx = np.asarray(result.event_indices if result.event_indices is not None else [], dtype=int)
    return {
        "module_used": "synaptic_events",
        "metrics": {
            "event_count": result.event_count,
            "frequency_hz": result.frequency_hz,
            "mean_amplitude": result.mean_amplitude,
            "amplitude_sd": result.amplitude_sd,
            "_event_times": time[_idx].tolist() if len(_idx) > 0 else [],
            "_event_peaks": data[_idx].tolist() if len(_idx) > 0 else [],
            "_result_obj": result,
        },
    }


# ---------------------------------------------------------------------------
# 2. Parametric Template Matching
# ---------------------------------------------------------------------------


def detect_events_template(  # noqa: C901
    data: np.ndarray,
    sampling_rate: float,
    threshold_std: float,
    tau_rise: float,
    tau_decay: float,
    polarity: str = "negative",
    rolling_baseline_window_ms: Optional[float] = 100.0,
    artifact_mask: Optional[np.ndarray] = None,
    time: Optional[np.ndarray] = None,
    min_event_distance_ms: float = 0.0,
) -> EventDetectionResult:
    """Detect events using matched-filter (template) approach."""
    try:
        dt = 1.0 / sampling_rate
        n_points = len(data)

        kernel_duration = 5 * max(tau_decay, tau_rise)
        t_kernel = np.arange(0, kernel_duration, dt)

        if tau_decay == tau_rise:
            kernel = t_kernel * np.exp(-t_kernel / tau_decay)
        else:
            kernel = np.exp(-t_kernel / tau_decay) - np.exp(-t_kernel / tau_rise)

        if np.max(np.abs(kernel)) > 0:
            kernel /= np.max(np.abs(kernel))

        if rolling_baseline_window_ms is not None and rolling_baseline_window_ms > 0:
            from scipy.ndimage import median_filter

            window_samples = int((rolling_baseline_window_ms / 1000.0) * sampling_rate)
            if window_samples % 2 == 0:
                window_samples += 1
            if window_samples >= 3:
                baseline = median_filter(data, size=window_samples)
                baseline_corrected_data = data - baseline
            else:
                baseline_corrected_data = data
        else:
            baseline_corrected_data = data

        is_negative = polarity == "negative"
        work_data = -baseline_corrected_data if is_negative else baseline_corrected_data

        matched_filter_kernel = kernel[::-1]
        filtered_trace = signal.fftconvolve(work_data, matched_filter_kernel, mode="same")

        mad = median_abs_deviation(filtered_trace, scale="normal")
        if mad == 0:
            mad = 1e-12

        z_score_trace = (filtered_trace - np.median(filtered_trace)) / mad

        if min_event_distance_ms > 0:
            min_dist_samples = int((min_event_distance_ms / 1000.0) * sampling_rate)
        else:
            min_dist_samples = int(tau_decay * sampling_rate)
        if min_dist_samples < 1:
            min_dist_samples = 1

        peak_indices, _ = signal.find_peaks(z_score_trace, height=threshold_std, distance=min_dist_samples)

        kernel_peak_idx = int(np.argmax(kernel))
        kernel_center = (len(kernel) - 1) // 2
        template_offset = kernel_peak_idx - kernel_center
        refine_window = max(3, int(tau_rise * sampling_rate))

        if len(peak_indices) > 0:
            corrected_indices = np.empty_like(peak_indices)
            for i, idx in enumerate(peak_indices):
                shifted = idx + template_offset
                win_start = max(0, shifted - refine_window)
                win_end = min(n_points, shifted + refine_window + 1)
                local_peak = np.argmax(work_data[win_start:win_end])
                corrected_indices[i] = win_start + local_peak
            peak_indices = np.unique(corrected_indices)

        if artifact_mask is not None and len(peak_indices) > 0:
            n_mask = len(artifact_mask)
            valid_mask = peak_indices < n_mask
            not_artifact = ~artifact_mask[peak_indices[valid_mask]]
            peak_indices = peak_indices[valid_mask][not_artifact]

        event_count = len(peak_indices)
        event_indices = peak_indices.astype(int)
        event_amplitudes = baseline_corrected_data[event_indices] if event_count > 0 else np.array([])

        if time is not None and len(time) == n_points:
            time_axis = time
        else:
            time_axis = np.arange(n_points) * dt
        event_times = time_axis[event_indices] if event_count > 0 else np.array([])

        return EventDetectionResult(
            value=event_count,
            unit="counts",
            is_valid=True,
            event_count=event_count,
            event_indices=event_indices,
            event_times=event_times,
            event_amplitudes=event_amplitudes,
            detection_method="template_matching",
            tau_rise_ms=tau_rise * 1000.0,
            tau_decay_ms=tau_decay * 1000.0,
            threshold_sd=threshold_std,
            summary_stats={"noise_mad": mad},
            direction=polarity,
            artifact_mask=artifact_mask,
        )

    except Exception as e:
        log.error(f"Error during template event detection: {e}", exc_info=True)
        return EventDetectionResult(value=0, unit="Hz", is_valid=False, error_message=str(e))


@AnalysisRegistry.register(
    "event_detection_deconvolution",
    label="Event (Template Match)",
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
        {"type": "markers", "x": "_event_times", "y": "_event_peaks", "color": "r", "symbol": "o"},
        {"type": "threshold_line", "param": "threshold_sd"},
        {"type": "artifact_overlay"},
    ],
    ui_params=[
        {
            "name": "tau_rise_ms",
            "label": "Tau Rise (ms):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "tau_decay_ms",
            "label": "Tau Decay (ms):",
            "type": "float",
            "default": 5.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "threshold_sd",
            "label": "Threshold (SD):",
            "type": "float",
            "default": 4.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
        },
        {
            "name": "rolling_baseline_window_ms",
            "label": "Rolling Baseline (ms):",
            "type": "float",
            "default": 100.0,
            "min": 0.0,
            "max": 5000.0,
            "decimals": 1,
        },
        {"name": "reject_artifacts", "label": "Reject Artifacts", "type": "bool", "default": False},
        {
            "name": "artifact_slope_threshold",
            "label": "Artifact Slope Thresh:",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
        },
        {"name": "artifact_padding_ms", "label": "Artifact Padding (ms):", "type": "float", "default": 2.0},
        {
            "name": "min_event_distance_ms",
            "label": "Min Event Distance (ms):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1000.0,
            "decimals": 1,
            "tooltip": "Minimum distance between events (ms). 0 = use tau_decay.",
        },
        {
            "name": "filter_freq_hz",
            "label": "Filter Freq (Hz):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 100000.0,
            "decimals": 1,
            "hidden": True,
        },
    ],
)
def run_event_detection_template_wrapper(
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for template-matching event detection."""
    tau_rise_ms = kwargs.get("tau_rise_ms", 0.5)
    tau_decay_ms = kwargs.get("tau_decay_ms", 5.0)
    threshold_sd = kwargs.get("threshold_sd", 4.0)
    direction = kwargs.get("direction", "negative")

    tau_rise = tau_rise_ms / 1000.0
    tau_decay = tau_decay_ms / 1000.0

    reject_artifacts = kwargs.get("reject_artifacts", False)
    artifact_mask = None
    if reject_artifacts:
        slope_thresh = kwargs.get("artifact_slope_threshold", 20.0)
        padding_ms = kwargs.get("artifact_padding_ms", 2.0)
        artifact_mask = find_artifact_windows(data, sampling_rate, slope_thresh, padding_ms)

    result = detect_events_template(
        data=data,
        sampling_rate=sampling_rate,
        threshold_std=threshold_sd,
        tau_rise=tau_rise,
        tau_decay=tau_decay,
        polarity=direction,
        rolling_baseline_window_ms=kwargs.get("rolling_baseline_window_ms", 100.0),
        artifact_mask=artifact_mask,
        time=time,
        min_event_distance_ms=kwargs.get("min_event_distance_ms", 0.0),
    )

    if not result.is_valid:
        return {"module_used": "synaptic_events", "metrics": {"event_error": result.error_message}}

    _idx = np.asarray(result.event_indices if result.event_indices is not None else [], dtype=int)
    return {
        "module_used": "synaptic_events",
        "metrics": {
            "event_count": result.event_count,
            "tau_rise_ms": result.tau_rise_ms,
            "tau_decay_ms": result.tau_decay_ms,
            "threshold_sd": result.threshold_sd,
            "_event_times": time[_idx].tolist() if len(_idx) > 0 else [],
            "_event_peaks": data[_idx].tolist() if len(_idx) > 0 else [],
            "_result_obj": result,
        },
    }


# ---------------------------------------------------------------------------
# 3. Baseline + Peak + Kinetics Detection
# ---------------------------------------------------------------------------


def _find_stable_baseline_segment(
    data: np.ndarray,
    sample_rate: float,
    window_duration_s: float = 0.5,
    step_duration_s: float = 0.1,
) -> Tuple[Optional[float], Optional[float], Optional[Tuple[int, int]]]:
    """Find the most stable (lowest-variance) baseline segment."""
    n_points = len(data)
    window_samples = max(2, int(window_duration_s * sample_rate))
    step_samples = max(1, int(step_duration_s * sample_rate))

    if window_samples >= n_points:
        return float(np.mean(data)), float(np.std(data)), (0, n_points)

    min_variance = np.inf
    best: Optional[Tuple[int, int]] = None
    best_mean: Optional[float] = None
    best_sd: Optional[float] = None

    for i in range(0, n_points - window_samples + 1, step_samples):
        segment = data[i : i + window_samples]
        variance = float(np.var(segment))
        if variance < min_variance:
            min_variance = variance
            best = (i, i + window_samples)
            best_mean = float(np.mean(segment))
            best_sd = float(np.sqrt(variance))

    return best_mean, best_sd, best


def detect_events_baseline_peak_kinetics(  # noqa: C901
    data: np.ndarray,
    sample_rate: float,
    direction: str = "negative",
    baseline_window_s: float = 0.5,
    baseline_step_s: float = 0.1,
    threshold_sd_factor: float = 3.0,
    filter_freq_hz: Optional[float] = None,
    min_event_separation_ms: float = 5.0,
    auto_baseline: bool = True,
    rolling_baseline_window_ms: float = 0.0,
) -> EventDetectionResult:
    """Detect events via stable-baseline estimation then prominence-based peak finding."""
    if direction not in ["negative", "positive"]:
        return EventDetectionResult(value=0, unit="counts", is_valid=False, error_message="Invalid direction")

    baseline_mean, baseline_sd, _ = _find_stable_baseline_segment(data, sample_rate, baseline_window_s, baseline_step_s)
    if baseline_mean is None:
        return EventDetectionResult(value=0, unit="counts", is_valid=True, event_count=0)

    is_negative = direction == "negative"

    if rolling_baseline_window_ms > 0:
        from scipy.ndimage import median_filter

        window_samples = int((rolling_baseline_window_ms / 1000.0) * sample_rate)
        if window_samples % 2 == 0:
            window_samples += 1
        if window_samples >= 3:
            rolling_bl = median_filter(data, size=window_samples)
            work_data = data - rolling_bl
        else:
            work_data = data
    else:
        work_data = data

    signal_to_process = -work_data if is_negative else work_data

    noise_sd = median_abs_deviation(signal_to_process, scale="normal")
    if noise_sd == 0:
        noise_sd = baseline_sd if baseline_sd and baseline_sd > 0 else 1e-12

    threshold_val = threshold_sd_factor * noise_sd

    if filter_freq_hz and filter_freq_hz > 0:
        try:
            sos = signal.butter(4, filter_freq_hz, "low", fs=sample_rate, output="sos")
            signal_c = np.ascontiguousarray(signal_to_process, dtype=np.float64)
            sos_c = np.ascontiguousarray(sos, dtype=np.float64)
            fwd = signal.sosfilt(sos_c, signal_c)
            filtered = signal.sosfilt(sos_c, fwd[::-1])[::-1]
        except (ValueError, TypeError, IndexError):
            filtered = signal_to_process
    else:
        filtered = signal_to_process

    min_dist = max(1, int(min_event_separation_ms / 1000.0 * sample_rate))
    min_width = max(2, int(0.0002 * sample_rate))
    peaks, _ = signal.find_peaks(
        filtered,
        height=threshold_val,
        prominence=threshold_val * 0.5,
        distance=min_dist,
        width=min_width,
    )

    display_threshold_val = -threshold_val if is_negative else threshold_val

    return EventDetectionResult(
        value=len(peaks),
        unit="counts",
        is_valid=True,
        event_count=len(peaks),
        event_indices=peaks,
        detection_method="baseline_peak",
        summary_stats={"baseline_mean": baseline_mean, "baseline_sd": float(noise_sd)},
        threshold_value=display_threshold_val,
    )


@AnalysisRegistry.register(
    "event_detection_baseline_peak",
    label="Event (Baseline Peak)",
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
        {"type": "markers", "x": "_event_times", "y": "_event_peaks", "color": "r", "symbol": "o"},
        {"type": "artifact_overlay"},
    ],
    ui_params=[
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
        },
        {"name": "auto_baseline", "label": "Auto-Detect Baseline", "type": "bool", "default": True},
        {"name": "threshold_sd_factor", "label": "Threshold (SD Factor):", "type": "float", "default": 3.0},
        {
            "name": "min_event_separation_ms",
            "label": "Min Separation (ms):",
            "type": "float",
            "default": 5.0,
            "min": 0.1,
            "max": 1000.0,
            "decimals": 1,
        },
        {
            "name": "rolling_baseline_window_ms",
            "label": "Rolling Baseline (ms):",
            "type": "float",
            "default": 100.0,
            "min": 0.0,
            "max": 5000.0,
            "decimals": 1,
        },
        {
            "name": "baseline_window_s",
            "label": "Baseline Win (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.01,
            "max": 100.0,
            "decimals": 2,
        },
        {
            "name": "baseline_step_s",
            "label": "Baseline Step (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.01,
            "max": 100.0,
            "decimals": 2,
        },
    ],
)
def run_event_detection_baseline_peak_wrapper(
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for baseline-peak event detection."""
    direction = kwargs.get("direction", "negative")
    result = detect_events_baseline_peak_kinetics(
        data,
        sampling_rate,
        direction=direction,
        threshold_sd_factor=kwargs.get("threshold_sd_factor", 3.0),
        min_event_separation_ms=kwargs.get("min_event_separation_ms", 5.0),
        auto_baseline=kwargs.get("auto_baseline", True),
        baseline_window_s=kwargs.get("baseline_window_s", 0.5),
        baseline_step_s=kwargs.get("baseline_step_s", 0.1),
        rolling_baseline_window_ms=kwargs.get("rolling_baseline_window_ms", 100.0),
    )
    if not result.is_valid:
        return {"module_used": "synaptic_events", "metrics": {"event_error": result.error_message}}
    _idx = np.asarray(result.event_indices if result.event_indices is not None else [], dtype=int)
    return {
        "module_used": "synaptic_events",
        "metrics": {
            "event_count": result.event_count,
            "_event_times": time[_idx].tolist() if len(_idx) > 0 else [],
            "_event_peaks": data[_idx].tolist() if len(_idx) > 0 else [],
            "_result_obj": result,
        },
    }


# ---------------------------------------------------------------------------
# Module-level tab aggregator
# ---------------------------------------------------------------------------
@AnalysisRegistry.register(
    "synaptic_events",
    label="Synaptic Events",
    method_selector={
        "Threshold Based": "event_detection_threshold",
        "Deconvolution (Custom)": "event_detection_deconvolution",
        "Baseline + Peak + Kinetics": "event_detection_baseline_peak",
    },
    ui_params=[],
    plots=[],
)
def synaptic_events_module(**kwargs):
    """Module-level aggregator tab for synaptic event detection analyses."""
    return {}
