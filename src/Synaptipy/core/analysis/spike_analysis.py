# src/Synaptipy/core/analysis/spike_analysis.py
# -*- coding: utf-8 -*-
"""
Analysis functions related to action potential detection and characterization.
"""
import logging
from typing import Tuple, List, Dict, Any
import numpy as np
from Synaptipy.core.results import SpikeTrainResult

log = logging.getLogger('Synaptipy.core.analysis.spike_analysis')

def detect_spikes_threshold(data: np.ndarray, time: np.ndarray, threshold: float, refractory_samples: int) -> SpikeTrainResult:
    """
    Detects spikes based on a simple voltage threshold crossing with refractory period.

    Args:
        data: 1D NumPy array of voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        threshold: Voltage threshold for detection.
        refractory_samples: Minimum number of samples between detected spikes (applied based on threshold crossings).

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
            valid_crossings_list = [crossings[0]] # Always accept the first crossing
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
        # Define search window for peak (e.g., next refractory_samples, or fixed ms)
        # Let's use refractory_samples as a simple window limit for now
        peak_search_window_samples = refractory_samples if refractory_samples > 0 else int(0.005 / (time[1]-time[0])) # Default to 5ms if no refractory
        
        for crossing_idx in valid_crossing_indices:
            search_start = crossing_idx
            search_end = min(crossing_idx + peak_search_window_samples, len(data))
            if search_start >= search_end: # Should not happen, but safety
                peak_idx = crossing_idx # Fallback to crossing index
            else:
                try:
                    # Find index of max value within the window relative to window start
                    relative_peak_idx = np.argmax(data[search_start:search_end])
                    # Convert to index relative to the whole data array
                    peak_idx = search_start + relative_peak_idx
                except ValueError: # Handle potential errors if slice is unexpectedly empty
                    log.warning(f"ValueError finding peak after crossing index {crossing_idx}. Using crossing index.")
                    peak_idx = crossing_idx 
                    
            peak_indices_list.append(peak_idx)
            
        peak_indices_arr = np.array(peak_indices_list).astype(int) # Ensure integer indices

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
            mean_frequency=mean_freq
        )

    except IndexError as e:
         # This might happen if indexing goes wrong, e.g., with peak_indices_arr
         log.error(f"IndexError during spike detection: {e}. Indices={peak_indices_arr if 'peak_indices_arr' in locals() else 'N/A'}", exc_info=True)
         return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message=str(e))
    except Exception as e:
        log.error(f"Error during spike detection: {e}", exc_info=True)
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message=str(e))


# --- Add other spike analysis functions here later ---
def calculate_spike_features(data, time, spike_indices):
    """
    Calculates detailed features for each spike.
    Returns:
        A list of dictionaries, where each dictionary contains features
        for a single spike (e.g., amplitude, half_width, ahp_depth, dvdt_max).
    """
    if spike_indices.size == 0:
        return []

    dt = time[1] - time[0]
    dvdt = np.gradient(data, dt)
    features_list = []

    for peak_idx in spike_indices:
        # 1. Find Action Potential Threshold (20 V/s is a common value)
        search_end = peak_idx
        search_start = max(0, peak_idx - int(0.005 / dt))  # 5ms before peak
        try:
            dvdt_slice = dvdt[search_start:search_end]
            data_slice = data[search_start:search_end]
            threshold_crossings = np.where(dvdt_slice > 20000)[0] # dV/dt in V/s, data in mV
            if threshold_crossings.size > 0:
                thresh_idx = search_start + threshold_crossings[0]
                ap_threshold = data[thresh_idx]
            else:
                thresh_idx = search_start # Fallback
                ap_threshold = data[thresh_idx]
        except:
            thresh_idx = peak_idx - 2 # fallback
            ap_threshold = data[thresh_idx]


        # 2. Spike Amplitude (from threshold to peak)
        amplitude = data[peak_idx] - ap_threshold

        # 3. Spike Width at half-maximal amplitude
        half_amp = ap_threshold + amplitude / 2
        
        # Find rising and falling half-amp crossings
        pre_peak_slice = data[thresh_idx:peak_idx+1]
        post_peak_slice = data[peak_idx:peak_idx + int(0.01/dt)] # 10ms after peak

        try:
            rising_half_idx = thresh_idx + np.where(pre_peak_slice > half_amp)[0][0]
            falling_half_idx = peak_idx + np.where(post_peak_slice < half_amp)[0][0]
            half_width = (falling_half_idx - rising_half_idx) * dt * 1000  # in ms
        except IndexError:
            half_width = np.nan

        # 4. Afterhyperpolarization (AHP) depth
        ahp_search_end = min(len(data), peak_idx + int(0.02 / dt)) # 20ms after peak
        ahp_slice = data[peak_idx:ahp_search_end]
        try:
            ahp_min_val = np.min(ahp_slice)
            ahp_depth = ap_threshold - ahp_min_val
        except ValueError:
            ahp_depth = np.nan

        # 5. Maximum rise and fall slopes (max/min dV/dt)
        dvdt_search_end = min(len(dvdt), peak_idx + int(0.005 / dt)) # 5ms after peak
        dvdt_search_slice = dvdt[thresh_idx:dvdt_search_end]

        try:
            max_dvdt = np.max(dvdt_search_slice)
            min_dvdt = np.min(dvdt_search_slice)
        except ValueError:
            max_dvdt, min_dvdt = np.nan, np.nan
            
        features_list.append({
            'ap_threshold': ap_threshold,
            'amplitude': amplitude,
            'half_width': half_width,
            'ahp_depth': ahp_depth,
            'max_dvdt': max_dvdt,
            'min_dvdt': min_dvdt
        })

    return features_list


def calculate_isi(spike_times):
    """Calculates inter-spike intervals from a list of spike times."""
    if len(spike_times) < 2:
        return np.array([])
    return np.diff(spike_times)

def analyze_multi_sweep_spikes(
    data_trials: List[np.ndarray],
    time_vector: np.ndarray,
    threshold: float,
    refractory_samples: int
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
            result.metadata['sweep_index'] = i
            results.append(result)
        except Exception as e:
            log.error(f"Error analyzing sweep {i}: {e}")
            # Return an error result for this sweep
            error_result = SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message=f"Sweep {i}: {str(e)}")
            error_result.metadata['sweep_index'] = i
            results.append(error_result)
            
    return results