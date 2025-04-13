# src/Synaptipy/core/analysis/basic_features.py
# -*- coding: utf-8 -*-
"""
Analysis functions for basic electrophysiological features from single traces.
"""
import logging
from typing import Optional, Tuple
import numpy as np

log = logging.getLogger('Synaptipy.core.analysis.basic_features')

def calculate_rmp(data: np.ndarray, time: np.ndarray, baseline_window: Tuple[float, float]) -> Optional[float]:
    """
    Calculates the Resting Membrane Potential (RMP) from a defined baseline window.

    Args:
        data: 1D NumPy array of voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        baseline_window: Tuple (start_time, end_time) defining the baseline period in seconds.

    Returns:
        The calculated mean RMP (float) or None if calculation fails
        (e.g., invalid window, empty data slice).
    #todo convert it into a dynamic setup
    """
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size == 0:
        log.warning("calculate_rmp: Invalid data array provided.")
        return None
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        log.warning("calculate_rmp: Time and data array shapes mismatch.")
        return None
    if not isinstance(baseline_window, tuple) or len(baseline_window) != 2:
         log.warning("calculate_rmp: baseline_window must be a tuple of (start, end).")
         return None

    start_t, end_t = baseline_window
    if not (isinstance(start_t, (int, float)) and isinstance(end_t, (int, float))):
         log.warning("calculate_rmp: baseline_window times must be numeric.")
         return None
    if start_t >= end_t:
         log.warning(f"calculate_rmp: Baseline start time ({start_t}) >= end time ({end_t}).")
         return None

    try:
        # Find indices corresponding to the time window
        start_idx = np.searchsorted(time, start_t, side='left')
        end_idx = np.searchsorted(time, end_t, side='right') # Use 'right' to include endpoint if exact match

        if start_idx >= end_idx:
             log.warning(f"calculate_rmp: No data points found in baseline window {baseline_window}s.")
             return None # Empty or invalid window slice

        baseline_data = data[start_idx:end_idx]

        if baseline_data.size == 0:
             log.warning(f"calculate_rmp: Baseline data slice is empty for window {baseline_window}s.")
             return None

        rmp = np.mean(baseline_data)
        log.debug(f"Calculated RMP = {rmp:.3f} over {baseline_data.size} points.")
        return float(rmp)

    except IndexError:
         log.error(f"calculate_rmp: Indexing error, likely invalid time window {baseline_window}s for time vector range {time[0]:.3f}-{time[-1]:.3f}s.")
         return None
    except Exception as e:
        log.error(f"Error during RMP calculation: {e}", exc_info=True)
        return None

# --- Add other basic features here later ---
# def calculate_input_resistance(voltage_trace, current_step, time, baseline_window, step_window): ...
# def calculate_tau(voltage_trace, time, fit_window): ...