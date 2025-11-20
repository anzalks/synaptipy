# src/Synaptipy/core/analysis/intrinsic_properties.py
# -*- coding: utf-8 -*-
"""
Analysis functions for intrinsic membrane properties.
"""
import logging
import numpy as np
from typing import Optional, Tuple
from scipy.optimize import curve_fit
from Synaptipy.core.results import RinResult

log = logging.getLogger(__name__)

def calculate_rin(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    current_amplitude: float, # Assume user provides this (e.g., in pA)
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float]
) -> RinResult:
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
        RinResult object.
    """
    if current_amplitude == 0:
        log.warning("Cannot calculate Rin: Current amplitude is zero.")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message="Current amplitude is zero")

    try:
        # Find indices for baseline and response windows
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        response_mask = (time_vector >= response_window[0]) & (time_vector < response_window[1])

        if not np.any(baseline_mask) or not np.any(response_mask):
            log.warning("Cannot calculate Rin: Time windows yielded no data points.")
            return RinResult(value=None, unit="MOhm", is_valid=False, error_message="No data in windows")

        # Calculate mean baseline and response voltages
        baseline_voltage = np.mean(voltage_trace[baseline_mask])
        response_voltage = np.mean(voltage_trace[response_mask])

        delta_v = response_voltage - baseline_voltage
        rin = delta_v / (current_amplitude / 1000.0) # V=IR -> R = V/I. If V is mV, I is pA. We want MOhm.
        # mV / nA = MOhm. pA / 1000 = nA.

        log.info(f"Calculated Rin: dV={delta_v:.3f}, dI={current_amplitude:.3f}, Rin={rin:.3f}")
        
        return RinResult(
            value=rin,
            unit="MOhm",
            voltage_deflection=delta_v,
            current_injection=current_amplitude,
            baseline_voltage=baseline_voltage,
            steady_state_voltage=response_voltage
        )

    except IndexError:
        log.exception("IndexError during Rin calculation. Check trace/time vector alignment and window validity.")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message="IndexError during calculation")
    except Exception as e:
        log.exception(f"Unexpected error during Rin calculation: {e}")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message=str(e))

def _exp_growth(t, V_ss, V_0, tau):
    """Exponential growth function for fitting."""
    return V_ss + (V_0 - V_ss) * np.exp(-t / tau)

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
    try:
        fit_start_time = stim_start_time
        fit_end_time = stim_start_time + fit_duration

        fit_mask = (time_vector >= fit_start_time) & (time_vector < fit_end_time)
        t_fit = time_vector[fit_mask] - fit_start_time # Start time at 0 for fit
        V_fit = voltage_trace[fit_mask]

        if len(t_fit) < 3:
            log.warning("Not enough data points to fit for Tau.")
            return None
        
        V_0 = V_fit[0]
        V_ss_guess = np.mean(V_fit[-5:]) # Guess steady state from last few points

        # bounds (V_ss, V_0, tau)
        lower_bounds = [-np.inf, -np.inf, 0.0001] # tau > 0
        upper_bounds = [np.inf, np.inf, 1.0]     # tau < 1s

        p0 = [V_ss_guess, V_0, 0.01] # Initial guess for tau = 10ms

        popt, _ = curve_fit(_exp_growth, t_fit, V_fit, p0=p0, bounds=(lower_bounds, upper_bounds))
        
        tau_ms = popt[2] * 1000 # convert tau to ms
        log.info(f"Calculated Tau: {tau_ms:.3f} ms")
        return tau_ms
    except RuntimeError:
        log.warning("Optimal parameters not found for Tau calculation.")
        return None
    except Exception as e:
        log.exception(f"Unexpected error during Tau calculation: {e}")
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
    try:
        # Baseline
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        if not np.any(baseline_mask): return None
        v_baseline = np.mean(voltage_trace[baseline_mask])

        # Peak hyperpolarization
        peak_mask = (time_vector >= response_peak_window[0]) & (time_vector < response_peak_window[1])
        if not np.any(peak_mask): return None
        v_peak = np.min(voltage_trace[peak_mask])

        # Steady-state hyperpolarization
        ss_mask = (time_vector >= response_steady_state_window[0]) & (time_vector < response_steady_state_window[1])
        if not np.any(ss_mask): return None
        v_ss = np.mean(voltage_trace[ss_mask])

        delta_v_peak = v_peak - v_baseline
        delta_v_ss = v_ss - v_baseline
        
        if delta_v_ss == 0:
            return None # Avoid division by zero

        sag_ratio = delta_v_peak / delta_v_ss
        log.info(f"Calculated Sag Ratio: {sag_ratio:.3f}")
        return sag_ratio
    except Exception as e:
        log.exception(f"Unexpected error during Sag calculation: {e}")
        return None 