# src/Synaptipy/core/analysis/intrinsic_properties.py
# -*- coding: utf-8 -*-
"""
Analysis functions for intrinsic membrane properties.
"""
import logging
import numpy as np
from typing import Optional, Tuple

log = logging.getLogger(__name__)

def calculate_rin(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    current_amplitude: float, # Assume user provides this (e.g., in pA)
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float]
) -> Optional[float]:
    """
    Calculates Input Resistance (Rin) from a voltage trace response to a current step.

    Rin = delta_V / delta_I

    Args:
        voltage_trace: 1D NumPy array of the voltage recording.
        time_vector: 1D NumPy array of corresponding time points.
        current_amplitude: The amplitude of the current step (delta_I). Assumed to be non-zero.
                           Units should be consistent with voltage (e.g., pA for mV -> MOhm).
        baseline_window: Tuple (start_time, end_time) for the baseline voltage calculation.
        response_window: Tuple (start_time, end_time) for the steady-state voltage response calculation.

    Returns:
        Calculated input resistance (e.g., in MOhms if V is mV and I is pA),
        or None if calculation is not possible (e.g., invalid windows, zero current).
    """
    if current_amplitude == 0:
        log.warning("Cannot calculate Rin: Current amplitude is zero.")
        return None

    try:
        # Find indices for baseline and response windows
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        response_mask = (time_vector >= response_window[0]) & (time_vector < response_window[1])

        if not np.any(baseline_mask) or not np.any(response_mask):
            log.warning("Cannot calculate Rin: Time windows yielded no data points.")
            return None

        # Calculate mean baseline and response voltages
        baseline_voltage = np.mean(voltage_trace[baseline_mask])
        response_voltage = np.mean(voltage_trace[response_mask])

        delta_v = response_voltage - baseline_voltage
        rin = delta_v / current_amplitude # V=IR -> R = V/I

        log.info(f"Calculated Rin: dV={delta_v:.3f}, dI={current_amplitude:.3f}, Rin={rin:.3f}")
        return rin

    except IndexError:
        log.exception("IndexError during Rin calculation. Check trace/time vector alignment and window validity.")
        return None
    except Exception as e:
        log.exception(f"Unexpected error during Rin calculation: {e}")
        return None

# Placeholder for Tau calculation
def calculate_tau(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    stim_start_time: float,
    fit_duration: float # Time window after stimulus start to fit
) -> Optional[float]:
    """
    Placeholder for Membrane Time Constant (Tau) calculation.
    Typically involves fitting an exponential to the rising phase of the voltage response.
    """
    log.warning("Tau calculation not yet implemented.")
    # Implementation would involve:
    # 1. Selecting the relevant portion of the trace after stim_start_time.
    # 2. Fitting an exponential function (e.g., single or double).
    # 3. Extracting the time constant(s) from the fit.
    return None


# Placeholder for Sag potential calculation
def calculate_sag_ratio(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    baseline_window: Tuple[float, float],
    response_peak_window: Tuple[float, float], # Window to find the peak hyperpolarization
    response_steady_state_window: Tuple[float, float] # Window for steady-state hyperpolarization
) -> Optional[float]:
    """
    Placeholder for Sag Potential Ratio calculation.
    Sag = (V_peak - V_baseline) / (V_steady_state - V_baseline) or similar definitions.
    Requires a hyperpolarizing current step.
    """
    log.warning("Sag calculation not yet implemented.")
    # Implementation would involve finding V_peak and V_steady_state within their windows
    # relative to V_baseline.
    return None 