# src/Synaptipy/core/analysis/spike_analysis.py
# -*- coding: utf-8 -*-
"""
Analysis functions related to action potential detection and characterization.
"""
import logging
from typing import Tuple
import numpy as np

log = logging.getLogger('Synaptipy.core.analysis.spike_analysis')

def detect_spikes_threshold(data: np.ndarray, time: np.ndarray, threshold: float, refractory_samples: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Detects spikes based on a simple voltage threshold crossing with refractory period.

    Args:
        data: 1D NumPy array of voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        threshold: Voltage threshold for detection.
        refractory_samples: Minimum number of samples between detected spikes (applied based on threshold crossings).

    Returns:
        A tuple containing:
            - peak_indices: NumPy array of sample indices where spike PEAKS were detected.
            - peak_times: NumPy array of corresponding spike peak times (seconds).
        Returns empty arrays if no spikes are detected or an error occurs.
    """
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size < 2:
        log.warning("detect_spikes_threshold: Invalid data array provided.")
        return np.array([]), np.array([])
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        log.warning("detect_spikes_threshold: Time and data array shapes mismatch.")
        return np.array([]), np.array([])
    if not isinstance(threshold, (int, float)):
         log.warning("detect_spikes_threshold: Threshold must be numeric.")
         return np.array([]), np.array([])
    if not isinstance(refractory_samples, int) or refractory_samples < 0:
         log.warning("detect_spikes_threshold: refractory_samples must be a non-negative integer.")
         return np.array([]), np.array([])

    try:
        # 1. Find indices where the data crosses the threshold upwards
        crossings = np.where((data[:-1] < threshold) & (data[1:] >= threshold))[0] + 1
        if crossings.size == 0:
            log.debug("No threshold crossings found.")
            return np.array([]), np.array([])

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
             return np.array([]), np.array([])
             
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
        return peak_indices_arr, peak_times_arr

    except IndexError as e:
         # This might happen if indexing goes wrong, e.g., with peak_indices_arr
         log.error(f"IndexError during spike detection: {e}. Indices={peak_indices_arr if 'peak_indices_arr' in locals() else 'N/A'}", exc_info=True)
         return np.array([]), np.array([])
    except Exception as e:
        log.error(f"Error during spike detection: {e}", exc_info=True)
        return np.array([]), np.array([])

# --- Add other spike analysis functions here later ---
# def calculate_spike_features(data, time, spike_indices): ...
# def calculate_isi(spike_times): ...