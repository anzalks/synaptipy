# src/Synaptipy/core/analysis/spike_analysis.py
# -*- coding: utf-8 -*-
"""
Analysis functions related to action potential detection and characterization.
"""
import logging
from typing import List, Dict, Any
import numpy as np
from scipy import signal
from Synaptipy.core.results import SpikeTrainResult
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


def detect_spikes_threshold(
    data: np.ndarray,
    time: np.ndarray,
    threshold: float,
    refractory_samples: int,
    peak_search_window_samples: int = None,
) -> SpikeTrainResult:
    """
    Detects spikes based on a simple voltage threshold crossing with refractory period.

    Args:
        data: 1D NumPy array of voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        threshold: Voltage threshold for detection.
        refractory_samples: Minimum number of samples between detected spikes (applied based on threshold crossings).
        peak_search_window_samples: Optional. Number of samples to search for peak after crossing.
                                    Defaults to refractory_samples (or 5ms if refractory is 0).

    Returns:
        SpikeTrainResult object containing spike times and indices.
    """
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size < 2:
        log.warning("detect_spikes_threshold: Invalid data array provided.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message="Invalid data array")
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        log.warning("detect_spikes_threshold: Time and data array shapes mismatch.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message="Time and data mismatch")
    if not isinstance(threshold, (int, float)):
        log.warning("detect_spikes_threshold: Threshold must be numeric.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message="Threshold must be numeric")
    if not isinstance(refractory_samples, int) or refractory_samples < 0:
        log.warning("detect_spikes_threshold: refractory_samples must be a non-negative integer.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message="Invalid refractory period")

    try:
        # 1. Find indices where the data crosses the threshold upwards
        crossings = np.where((data[:-1] < threshold) & (data[1:] >= threshold))[0] + 1
        if crossings.size == 0:
            log.debug("No threshold crossings found.")
            return SpikeTrainResult(value=0, unit="spikes", spike_times=np.array([]), spike_indices=np.array([]))

        # 2. Apply refractory period based on crossings
        if refractory_samples <= 0:
            valid_crossing_indices = crossings
        else:
            valid_crossings_list = [crossings[0]]  # Always accept the first crossing
            last_crossing_idx = crossings[0]
            for idx in crossings[1:]:
                if (idx - last_crossing_idx) >= refractory_samples:
                    valid_crossings_list.append(idx)
                    last_crossing_idx = idx
            valid_crossing_indices = np.array(valid_crossings_list)

        if valid_crossing_indices.size == 0:
            return SpikeTrainResult(value=0, unit="spikes", spike_times=np.array([]), spike_indices=np.array([]))

        # 3. Find peak index after each valid crossing
        peak_indices_list = []
        # Define search window for peak
        if peak_search_window_samples is None:
            peak_search_window_samples = (
                refractory_samples if refractory_samples > 0 else int(0.005 / (time[1] - time[0]))
            )  # Default to 5ms if no refractory

        for crossing_idx in valid_crossing_indices:
            search_start = crossing_idx
            search_end = min(crossing_idx + peak_search_window_samples, len(data))
            if search_start >= search_end:  # Should not happen, but safety
                peak_idx = crossing_idx  # Fallback to crossing index
            else:
                try:
                    # Find index of max value within the window relative to window start
                    relative_peak_idx = np.argmax(data[search_start:search_end])
                    # Convert to index relative to the whole data array
                    peak_idx = search_start + relative_peak_idx
                except ValueError:  # Handle potential errors if slice is unexpectedly empty
                    log.warning(f"ValueError finding peak after crossing index {crossing_idx}. Using crossing index.")
                    peak_idx = crossing_idx

            peak_indices_list.append(peak_idx)

        peak_indices_arr = np.array(peak_indices_list).astype(int)  # Ensure integer indices

        # 4. Get corresponding times for the peaks
        peak_times_arr = time[peak_indices_arr]
        log.debug(f"Detected {len(peak_indices_arr)} spike peaks.")

        mean_freq = 0.0
        if len(peak_times_arr) > 1:
            duration = time[-1] - time[0]
            if duration > 0:
                mean_freq = len(peak_times_arr) / duration

        return SpikeTrainResult(
            value=len(peak_indices_arr),
            unit="spikes",
            spike_times=peak_times_arr,
            spike_indices=peak_indices_arr,
            mean_frequency=mean_freq,
        )

    except IndexError as e:
        # This might happen if indexing goes wrong, e.g., with peak_indices_arr
        log.error(
            f"IndexError during spike detection: {e}. "
            f"Indices={peak_indices_arr if 'peak_indices_arr' in locals() else 'N/A'}",
            exc_info=True,
        )
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message=str(e))
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error during spike detection: {e}", exc_info=True)
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message=str(e))


# --- Add other spike analysis functions here later ---
def calculate_spike_features(
    data: np.ndarray,
    time: np.ndarray,
    spike_indices: np.ndarray,
    dvdt_threshold: float = 20.0,
    ahp_window_sec: float = 0.05,
    onset_lookback: float = 0.01,
) -> List[Dict[str, Any]]:
    """
    Calculates detailed features for each detected spike using vectorized
    NumPy operations for performance.

    Computes: AP threshold, amplitude, half-width, rise time (10-90%),
    decay time (90-10%), AHP depth, AHP duration (return-to-baseline),
    ADP amplitude, and max/min dV/dt.

    AHP uses an adaptive return-to-baseline algorithm: after finding the
    AHP minimum, it searches forward until voltage recovers to
    ``threshold - 0.1 * amplitude`` or the slope reaches >= 0 mV/s.
    The ``ahp_window_sec`` parameter acts as a maximum search window.

    Args:
        data: 1D NumPy array of voltage data (mV).
        time: 1D NumPy array of corresponding time points (s).
        spike_indices: 1D NumPy array of peak sample indices.
        dvdt_threshold: Threshold for AP onset detection (V/s, default 20.0).
        ahp_window_sec: Maximum AHP search window (s, default 0.05).
        onset_lookback: Time to look back from peak for onset (s, default 0.01).

    Returns:
        A list of dictionaries, one per spike, each containing:
        ap_threshold, amplitude, half_width, rise_time_10_90,
        decay_time_90_10, ahp_depth, ahp_duration_half, adp_amplitude,
        max_dvdt, min_dvdt.
    """
    if spike_indices is None or spike_indices.size == 0:
        return []

    n_spikes = len(spike_indices)
    n_data = len(data)
    dt = time[1] - time[0]
    dvdt = np.gradient(data, dt)

    # Convert threshold to mV/s (data is in mV, time in s)
    threshold_val_mvs = dvdt_threshold * 1000.0

    # Window sizes in samples
    lookback_samples = int(onset_lookback / dt)
    post_peak_samples = int(0.01 / dt)  # 10ms after peak for half-width
    ahp_max_samples = int(ahp_window_sec / dt)
    dvdt_post_samples = int(0.005 / dt)  # 5ms for dV/dt search
    adp_search_samples = int(0.02 / dt)  # 20ms for ADP

    # --- Build index arrays for vectorized window extraction ---
    spike_idx = spike_indices.astype(int)

    # Pre-peak onset window indices: shape (n_spikes, lookback_samples)
    onset_starts = np.maximum(0, spike_idx - lookback_samples)

    # --- Vectorized AP Threshold Detection ---
    ap_thresholds = np.full(n_spikes, np.nan)
    thresh_indices = np.full(n_spikes, 0, dtype=int)

    for i in range(n_spikes):
        s_start = onset_starts[i]
        s_end = spike_idx[i]
        if s_start >= s_end:
            thresh_indices[i] = max(0, spike_idx[i] - 2)
            ap_thresholds[i] = data[thresh_indices[i]]
            continue
        dvdt_slice = dvdt[s_start:s_end]
        crossings = np.where(dvdt_slice > threshold_val_mvs)[0]
        if crossings.size > 0:
            thresh_indices[i] = s_start + crossings[0]
        else:
            thresh_indices[i] = s_start
        ap_thresholds[i] = data[thresh_indices[i]]

    # --- Vectorized Amplitude ---
    peak_vals = data[spike_idx]
    amplitudes = peak_vals - ap_thresholds

    # --- Vectorized Half-Width, Rise Time, Decay Time ---
    half_widths = np.full(n_spikes, np.nan)
    rise_times = np.full(n_spikes, np.nan)
    decay_times = np.full(n_spikes, np.nan)
    half_amps = ap_thresholds + amplitudes / 2.0
    amp_10 = ap_thresholds + 0.1 * amplitudes
    amp_90 = ap_thresholds + 0.9 * amplitudes

    # Post-peak ends (clipped to data length)
    post_ends = np.minimum(spike_idx + post_peak_samples, n_data)

    for i in range(n_spikes):
        ti = thresh_indices[i]
        pi = spike_idx[i]
        pe = post_ends[i]

        if ti >= pi or pi >= pe:
            continue

        pre_peak = data[ti:pi + 1]
        post_peak = data[pi:pe]

        # Half-width
        try:
            rising_cross = np.where(pre_peak > half_amps[i])[0]
            falling_cross = np.where(post_peak < half_amps[i])[0]
            if rising_cross.size > 0 and falling_cross.size > 0:
                r_idx = ti + rising_cross[0]
                f_idx = pi + falling_cross[0]
                half_widths[i] = (f_idx - r_idx) * dt * 1000.0
        except (IndexError, ValueError):
            pass

        # Rise time 10-90%
        try:
            r10 = np.where(pre_peak >= amp_10[i])[0]
            r90 = np.where(pre_peak >= amp_90[i])[0]
            if r10.size > 0 and r90.size > 0:
                rise_times[i] = (r90[0] - r10[0]) * dt * 1000.0
        except (IndexError, ValueError):
            pass

        # Decay time 90-10%
        try:
            f90 = np.where(post_peak <= amp_90[i])[0]
            f10 = np.where(post_peak <= amp_10[i])[0]
            if f90.size > 0 and f10.size > 0:
                decay_times[i] = (f10[0] - f90[0]) * dt * 1000.0
        except (IndexError, ValueError):
            pass

    # --- AHP with Return-to-Baseline Search ---
    ahp_depths = np.full(n_spikes, np.nan)
    ahp_durations = np.full(n_spikes, np.nan)

    for i in range(n_spikes):
        pi = spike_idx[i]
        ahp_end = min(n_data, pi + ahp_max_samples)
        if pi >= ahp_end:
            continue

        ahp_slice = data[pi:ahp_end]
        if ahp_slice.size == 0:
            continue

        # Find AHP minimum
        ahp_min_rel = np.argmin(ahp_slice)
        ahp_min_val = ahp_slice[ahp_min_rel]
        ahp_depth = ap_thresholds[i] - ahp_min_val
        ahp_depths[i] = ahp_depth

        if ahp_depth <= 0 or ahp_min_rel == 0:
            continue

        # Return-to-baseline search: from AHP minimum forward
        # Recovery target: threshold - 0.1 * amplitude
        recovery_target = ap_thresholds[i] - 0.1 * amplitudes[i]
        post_min_slice = ahp_slice[ahp_min_rel:]

        if post_min_slice.size < 2:
            continue

        # Method 1: Voltage recovers to target
        recovery_by_voltage = np.where(post_min_slice >= recovery_target)[0]
        # Method 2: Slope reaches >= 0 mV/s (signal stops hyperpolarizing)
        post_min_dvdt = np.gradient(post_min_slice, dt)
        recovery_by_slope = np.where(post_min_dvdt >= 0)[0]

        # Use whichever comes first
        recovery_idx = None
        if recovery_by_voltage.size > 0 and recovery_by_slope.size > 0:
            recovery_idx = min(recovery_by_voltage[0], recovery_by_slope[0])
        elif recovery_by_voltage.size > 0:
            recovery_idx = recovery_by_voltage[0]
        elif recovery_by_slope.size > 0:
            recovery_idx = recovery_by_slope[0]

        if recovery_idx is not None and recovery_idx > 0:
            # Find where the AP crosses threshold downward (start of AHP)
            post_peak = data[pi:min(n_data, pi + post_peak_samples)]
            thresh_cross = np.where(post_peak < ap_thresholds[i])[0]
            if thresh_cross.size > 0:
                ap_end_offset = thresh_cross[0]
            else:
                ap_end_offset = 0

            # AHP duration: from AP end to recovery point
            total_ahp_samples = (ahp_min_rel + recovery_idx) - ap_end_offset
            if total_ahp_samples > 0:
                ahp_durations[i] = total_ahp_samples * dt * 1000.0  # ms

    # --- ADP Detection ---
    adp_amplitudes = np.full(n_spikes, np.nan)
    for i in range(n_spikes):
        pi = spike_idx[i]
        # Find AP end (threshold crossing downward)
        post_end = min(n_data, pi + post_peak_samples)
        post_peak_slice = data[pi:post_end]
        thresh_cross = np.where(post_peak_slice < ap_thresholds[i])[0]
        if thresh_cross.size == 0:
            continue
        ap_end_idx = pi + thresh_cross[0]

        adp_end = min(n_data, ap_end_idx + adp_search_samples)
        adp_window = data[ap_end_idx:adp_end]
        if adp_window.size <= 5:
            continue

        try:
            adp_peaks, _ = signal.find_peaks(adp_window, prominence=0.5)
            if adp_peaks.size > 0:
                adp_amplitudes[i] = adp_window[adp_peaks[0]] - data[ap_end_idx]
        except (ValueError, TypeError):
            pass

    # --- Vectorized max/min dV/dt ---
    max_dvdts = np.full(n_spikes, np.nan)
    min_dvdts = np.full(n_spikes, np.nan)

    for i in range(n_spikes):
        ti = thresh_indices[i]
        dvdt_end = min(len(dvdt), spike_idx[i] + dvdt_post_samples)
        if ti < dvdt_end:
            dvdt_slice = dvdt[ti:dvdt_end]
            if dvdt_slice.size > 0:
                max_dvdts[i] = np.max(dvdt_slice)
                min_dvdts[i] = np.min(dvdt_slice)

    # --- Assemble output (same format as before for compatibility) ---
    features_list = []
    for i in range(n_spikes):
        features_list.append({
            "ap_threshold": ap_thresholds[i],
            "amplitude": amplitudes[i],
            "half_width": half_widths[i],
            "rise_time_10_90": rise_times[i],
            "decay_time_90_10": decay_times[i],
            "ahp_depth": ahp_depths[i],
            "ahp_duration_half": ahp_durations[i],
            "adp_amplitude": adp_amplitudes[i],
            "max_dvdt": max_dvdts[i],
            "min_dvdt": min_dvdts[i],
        })

    return features_list


def calculate_isi(spike_times):
    """Calculates inter-spike intervals from a list of spike times."""
    if len(spike_times) < 2:
        return np.array([])
    return np.diff(spike_times)


def analyze_multi_sweep_spikes(
    data_trials: List[np.ndarray], time_vector: np.ndarray, threshold: float, refractory_samples: int
) -> List[SpikeTrainResult]:
    """
    Analyzes spikes across multiple sweeps (trials).

    Args:
        data_trials: List of 1D NumPy arrays, each representing a sweep.
        time_vector: 1D NumPy array of time points (assumed same for all sweeps).
        threshold: Voltage threshold.
        refractory_samples: Refractory period in samples.

    Returns:
        List of SpikeTrainResult objects, one for each sweep.
    """
    results = []
    for i, trial_data in enumerate(data_trials):
        try:
            result = detect_spikes_threshold(trial_data, time_vector, threshold, refractory_samples)
            # Add trial index to metadata
            result.metadata["sweep_index"] = i
            results.append(result)
        except (ValueError, TypeError, KeyError, IndexError) as e:
            log.error(f"Error analyzing sweep {i}: {e}")
            # Return an error result for this sweep
            error_result = SpikeTrainResult(
                value=0, unit="spikes", is_valid=False, error_message=f"Sweep {i}: {str(e)}"
            )
            error_result.metadata["sweep_index"] = i
            results.append(error_result)

    return results


# --- Registry Wrapper for Batch Processing ---
@AnalysisRegistry.register(
    "spike_detection",
    label="Spike Detection",
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
            "name": "refractory_period",
            "label": "Refractory (s):",
            "type": "float",
            "default": 0.002,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "peak_search_window",
            "label": "Peak Search (s):",
            "type": "float",
            "default": 0.005,
            "min": 0.0,
            "max": 1.0,
            "decimals": 4,
        },
        {
            "name": "dvdt_threshold",
            "label": "dV/dt Thresh (V/s):",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
            "max": 1e6,
            "decimals": 1,
        },
        {
            "name": "ahp_window",
            "label": "AHP Window (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "default": 0.05,
            "min": 0.0,
            "max": 10.0,
            "decimals": 3,
        },
        {
            "name": "onset_lookback",
            "label": "Onset Lookback (s):",
            "type": "float",
            "default": 0.01,
            "min": 0.0,
            "max": 0.1,
            "decimals": 3,
        },
    ],
)
def run_spike_detection_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    threshold: float = -20.0,
    refractory_period: float = 0.002,
    peak_search_window: float = 0.005,
    dvdt_threshold: float = 20.0,
    ahp_window: float = 0.05,
    onset_lookback: float = 0.01,
    **kwargs,
) -> Dict[str, Any]:
    """
    Wrapper function for spike detection that conforms to the registry interface.

    Args:
        data: 1D NumPy array of voltage data
        time: 1D NumPy array of corresponding time points (seconds)
        sampling_rate: Sampling rate in Hz
        threshold: Detection threshold in mV
        refractory_period: Refractory period in seconds

    Returns:
        Dictionary containing results.
    """
    try:
        refractory_samples = int(refractory_period * sampling_rate)
        peak_window_samples = int(peak_search_window * sampling_rate)

        params = {
            'threshold': threshold,
            'refractory_period': refractory_period,
            'peak_search_window': peak_search_window,
            'dvdt_threshold': dvdt_threshold,
            'ahp_window': ahp_window,
            'onset_lookback': onset_lookback,
        }

        # Run detection
        result = detect_spikes_threshold(
            data, time, threshold, refractory_samples, peak_search_window_samples=peak_window_samples
        )

        if result.is_valid:
            # Calculate spike features
            features_list = calculate_spike_features(
                data,
                time,
                result.spike_indices,
                dvdt_threshold=dvdt_threshold,
                ahp_window_sec=ahp_window,
                onset_lookback=onset_lookback,
            )

            # Aggregate features (Mean and Std Dev)
            stats = {}
            if features_list:
                # Convert list of dicts to dict of lists for easier aggregation
                feature_keys = features_list[0].keys()
                for key in feature_keys:
                    values = [f[key] for f in features_list if not np.isnan(f[key])]
                    if values:
                        stats[f"{key}_mean"] = np.mean(values)
                        stats[f"{key}_std"] = np.std(values)
                    else:
                        stats[f"{key}_mean"] = np.nan
                        stats[f"{key}_std"] = np.nan

            output = {
                "spike_count": len(result.spike_indices) if result.spike_indices is not None else 0,
                "mean_freq_hz": result.mean_frequency if result.mean_frequency is not None else 0.0,
                "spike_times": result.spike_times,
                "spike_indices": result.spike_indices,
                "parameters": params,
            }
            output.update(stats)
            return output
        else:
            return {
                "spike_count": 0, "mean_freq_hz": 0.0,
                "spike_error": result.error_message or "Unknown error",
                "parameters": params,
            }

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_spike_detection_wrapper: {e}", exc_info=True)
        return {"spike_count": 0, "mean_freq_hz": 0.0, "spike_error": str(e)}
