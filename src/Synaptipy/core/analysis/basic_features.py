# src/Synaptipy/core/analysis/basic_features.py
# -*- coding: utf-8 -*-
"""
Analysis functions for basic electrophysiological features from single traces.
"""
import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.results import RmpResult

log = logging.getLogger(__name__)


def calculate_rmp(data: np.ndarray, time: np.ndarray, baseline_window: Tuple[float, float]) -> RmpResult:  # noqa: C901
    """
    Calculates the Resting Membrane Potential (RMP) from a defined baseline window.

    Args:
        data: 1D NumPy array of voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        baseline_window: Tuple (start_time, end_time) defining the baseline period in seconds.

    Returns:
        RmpResult object.
    """
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size == 0:
        log.warning("calculate_rmp: Invalid data array provided.")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Invalid data array")
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        log.warning("calculate_rmp: Time and data array shapes mismatch.")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Time and data mismatch")
    if not isinstance(baseline_window, tuple) or len(baseline_window) != 2:
        log.warning("calculate_rmp: baseline_window must be a tuple of (start, end).")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Invalid baseline window format")

    start_t, end_t = baseline_window
    if not (isinstance(start_t, (int, float)) and isinstance(end_t, (int, float))):
        log.warning("calculate_rmp: baseline_window times must be numeric.")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Non-numeric window times")
    if start_t >= end_t:
        log.warning(f"calculate_rmp: Baseline start time ({start_t}) >= end time ({end_t}).")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Start time >= End time")

    try:
        # Find indices corresponding to the time window
        start_idx = np.searchsorted(time, start_t, side="left")
        end_idx = np.searchsorted(time, end_t, side="right")  # Use 'right' to include endpoint if exact match

        if start_idx >= end_idx:
            log.warning(f"calculate_rmp: No data points found in baseline window {baseline_window}s.")
            return RmpResult(value=None, unit="mV", is_valid=False, error_message="No data in window")

        baseline_data = data[start_idx:end_idx]

        if baseline_data.size == 0:
            log.warning(f"calculate_rmp: Baseline data slice is empty for window {baseline_window}s.")
            return RmpResult(value=None, unit="mV", is_valid=False, error_message="Empty data slice")

        rmp = np.mean(baseline_data)
        std_dev = np.std(baseline_data)
        duration = end_t - start_t

        # Calculate drift (linear regression slope)
        try:
            # Use time relative to start of window for stability
            window_time = time[start_idx:end_idx] - time[start_idx]
            slope, _ = np.polyfit(window_time, baseline_data, 1)
        except (ValueError, TypeError, np.linalg.LinAlgError):
            slope = None

        log.debug(f"Calculated RMP = {rmp:.3f} over {baseline_data.size} points.")
        return RmpResult(
            value=float(rmp),
            unit="mV",
            std_dev=float(std_dev),
            drift=float(slope) if slope is not None else None,
            duration=duration,
        )

    except IndexError as e:
        log.error(f"calculate_rmp: Indexing error: {e}")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message=str(e))
    except (ValueError, TypeError, RuntimeError) as e:
        log.error(f"Error during RMP calculation: {e}", exc_info=True)
        return RmpResult(value=None, unit="mV", is_valid=False, error_message=str(e))


def calculate_baseline_stats(
    time: np.ndarray, voltage: np.ndarray, start_time: float, end_time: float
) -> Optional[Tuple[float, float]]:
    """
    Calculates baseline statistics (mean and standard deviation) from a time window.

    This is a convenience function that provides a simple tuple return format
    for compatibility with existing code.

    Args:
        time: 1D NumPy array of corresponding time points (seconds).
        voltage: 1D NumPy array of voltage data.
        start_time: Start time of the baseline window (seconds).
        end_time: End time of the baseline window (seconds).

    Returns:
        Tuple of (mean, std_dev) if successful, None otherwise.
    """
    result = calculate_rmp(voltage, time, (start_time, end_time))
    if result.is_valid and result.value is not None:
        return (result.value, result.std_dev if result.std_dev is not None else 0.0)
    return None


def find_stable_baseline(
    data: np.ndarray, sample_rate: float, window_duration_s: float = 0.5, step_duration_s: float = 0.1
) -> Tuple[Optional[float], Optional[float], Optional[Tuple[float, float]]]:
    """
    Finds the most stable baseline segment based on minimum variance.

    Args:
        data: 1D numpy array of the signal.
        sample_rate: Sampling rate in Hz.
        window_duration_s: Duration of the sliding window in seconds.
        step_duration_s: Step size for sliding the window in seconds.

    Returns:
        A tuple containing:
            - baseline_mean: Mean of the most stable segment (or None).
            - baseline_sd: Standard deviation of the most stable segment (or None).
            - time_window: Tuple of (start_time, end_time) for the segment (or None).
    """
    if len(data) == 0:
        return None, None, None

    n_points = len(data)
    window_samples = int(window_duration_s * sample_rate)
    step_samples = int(step_duration_s * sample_rate)

    if window_samples < 2 or step_samples < 1:
        log.warning(f"Baseline window ({window_samples}) or step ({step_samples}) too small. Adjust parameters.")
        window_samples = max(2, window_samples)
        step_samples = max(1, step_samples)

    if window_samples >= n_points:
        # log.warning("Baseline window duration >= data length. Using full trace.")
        segment_data = data
        mean_val = np.mean(segment_data)
        sd_val = np.std(segment_data)
        return mean_val, sd_val, (0.0, n_points / sample_rate)

    min_variance = np.inf
    best_start_idx = None
    best_mean = None
    best_sd = None

    # Limit search for very long traces to avoid freezing?
    # For now, full search is fine for typical traces.
    for i in range(0, n_points - window_samples + 1, step_samples):
        segment = data[i : i + window_samples]
        variance = np.var(segment)
        if variance < min_variance:
            min_variance = variance
            best_start_idx = i
            best_mean = np.mean(segment)
            best_sd = np.sqrt(variance)

    if best_start_idx is None:
        return None, None, None

    start_time = best_start_idx / sample_rate
    end_time = (best_start_idx + window_samples) / sample_rate

    return best_mean, best_sd, (start_time, end_time)


# --- Registry Wrapper for Batch Processing ---
@AnalysisRegistry.register(
    "rmp_analysis",
    label="Baseline (RMP)",
    ui_params=[
        {
            "name": "baseline_start",
            "label": "Start Time (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "baseline_end",
            "label": "End Time (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {"name": "auto_detect", "label": "Auto-Detect Stable Segment", "type": "bool", "default": False},
        {
            "name": "window_duration",
            "label": "Auto Window (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "step_duration",
            "label": "Step Duration (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.001,
            "max": 1e9,
            "decimals": 4,
        },
    ],
    plots=[
        {"type": "interactive_region", "data": ["baseline_start", "baseline_end"], "color": "g"},
        {"type": "hlines", "data": ["rmp_mv"], "color": "r", "styles": ["solid"]},
        {"type": "hlines", "data": ["rmp_mv_plus_sd", "rmp_mv_minus_sd"], "color": "r", "styles": ["dash", "dash"]},
    ],
)
def run_rmp_analysis_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """
    Wrapper function for RMP analysis that conforms to the registry interface.
    """
    try:
        # Extract parameters from kwargs
        baseline_start = kwargs.get("baseline_start", 0.0)
        baseline_end = kwargs.get("baseline_end", 0.1)
        auto_detect = kwargs.get("auto_detect", False)

        if auto_detect:
            window_duration = kwargs.get("window_duration", 0.5)
            step_duration = kwargs.get("step_duration", 0.1)
            # Use shared helper
            mean, sd, window = find_stable_baseline(
                data, sampling_rate, window_duration_s=window_duration, step_duration_s=step_duration
            )

            if window:
                baseline_start, baseline_end = window
                log.debug(f"Auto-detected stable baseline: {baseline_start:.3f} - {baseline_end:.3f} s")
            else:
                log.warning("Auto-detection failed or data too short. Using full trace.")
                baseline_start = time[0]
                baseline_end = time[-1]

        # Validate window is within data range
        if len(time) > 0:
            if baseline_end > time[-1]:
                baseline_end = time[-1]
            if baseline_start < time[0]:
                baseline_start = time[0]

        # Call the actual RMP calculation function
        result = calculate_rmp(data, time, (baseline_start, baseline_end))

        if result.is_valid and result.value is not None:
            sd = result.std_dev if result.std_dev is not None else 0.0
            return {
                "rmp_mv": result.value,
                "rmp_std": sd,
                "rmp_drift": result.drift if result.drift is not None else 0.0,
                "rmp_duration": result.duration if result.duration is not None else 0.0,
                "rmp_mv_plus_sd": result.value + sd,
                "rmp_mv_minus_sd": result.value - sd,
            }
        else:
            return {"rmp_mv": None, "rmp_std": None, "rmp_error": result.error_message or "Unknown error"}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_rmp_analysis_wrapper: {e}", exc_info=True)
        return {"rmp_mv": None, "rmp_std": None, "rmp_error": str(e)}


# --- Add other basic features here later ---
# def calculate_input_resistance(voltage_trace, current_step, time, baseline_window, step_window): ...
# def calculate_tau(voltage_trace, time, fit_window): ...
