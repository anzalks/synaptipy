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
        refractory_samples: Minimum number of samples between detected spikes.

    Returns:
        A tuple containing:
            - spike_indices: NumPy array of sample indices where spikes were detected.
            - spike_times: NumPy array of corresponding spike times (seconds).
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
        # Find indices where the data crosses the threshold upwards
        # Compare data[i] < threshold and data[i+1] >= threshold
        crossings = np.where((data[:-1] < threshold) & (data[1:] >= threshold))[0] + 1
        if crossings.size == 0:
            log.debug("No threshold crossings found.")
            return np.array([]), np.array([])

        # Apply simple refractory period
        if refractory_samples <= 0:
             # No refractory period, return all crossings
             spike_indices_arr = crossings
        else:
            spike_indices = [crossings[0]] # Always accept the first crossing
            last_spike_idx = crossings[0]
            for idx in crossings[1:]:
                if (idx - last_spike_idx) >= refractory_samples:
                    spike_indices.append(idx)
                    last_spike_idx = idx
            spike_indices_arr = np.array(spike_indices)

        if spike_indices_arr.size == 0: # Could happen if only one crossing and refractory > 0
             return np.array([]), np.array([])

        # Get corresponding times
        spike_times_arr = time[spike_indices_arr]
        log.debug(f"Detected {len(spike_indices_arr)} spikes.")
        return spike_indices_arr, spike_times_arr

    except IndexError as e:
         # This might happen if indexing goes wrong, e.g., with spike_indices_arr
         log.error(f"IndexError during spike detection: {e}. Indices={spike_indices_arr if 'spike_indices_arr' in locals() else 'N/A'}", exc_info=True)
         return np.array([]), np.array([])
    except Exception as e:
        log.error(f"Error during spike detection: {e}", exc_info=True)
        return np.array([]), np.array([])

# --- Add other spike analysis functions here later ---
# def calculate_spike_features(data, time, spike_indices): ...
# def calculate_isi(spike_times): ...