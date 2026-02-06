# src/Synaptipy/core/analysis/intrinsic_properties.py
# -*- coding: utf-8 -*-
"""
Analysis functions for intrinsic membrane properties.
"""
import logging
import numpy as np
from typing import Optional, Tuple, Dict, Any
from scipy.optimize import curve_fit
from Synaptipy.core.results import RinResult
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


def calculate_rin(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    current_amplitude: float,  # Assume user provides this (e.g., in pA)
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float],
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
        # Calculate Rin as magnitude (always positive) since resistance is a scalar property
        # Rin = |delta_V| / |delta_I|
        rin = abs(delta_v) / (abs(current_amplitude) / 1000.0)  # V=IR -> R = V/I. If V is mV, I is pA. We want MOhm.
        # mV / nA = MOhm. pA / 1000 = nA.

        conductance_us = 1000.0 / rin if rin != 0 else 0.0  # G = 1/R. 1/MOhm = uS.

        log.debug(
            f"Calculated Rin: dV={delta_v:.3f}, dI={current_amplitude:.3f}, Rin={rin:.3f}, G={conductance_us:.3f}"
        )

        return RinResult(
            value=rin,
            unit="MOhm",
            conductance=conductance_us,
            voltage_deflection=delta_v,
            current_injection=current_amplitude,
            baseline_voltage=baseline_voltage,
            steady_state_voltage=response_voltage,
        )

    except IndexError:
        log.exception("IndexError during Rin calculation. Check trace/time vector alignment and window validity.")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message="IndexError during calculation")
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception(f"Unexpected error during Rin calculation: {e}")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message=str(e))


def calculate_conductance(
    current_trace: np.ndarray,
    time_vector: np.ndarray,
    voltage_step: float,  # Delta V in mV
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float],
) -> RinResult:
    """
    Calculates Conductance (G) from a current trace response to a voltage step.

    G = delta_I / delta_V

    Args:
        current_trace: 1D NumPy array of the current recording (pA).
        time_vector: 1D NumPy array of corresponding time points.
        voltage_step: The amplitude of the voltage step (delta_V) in mV.
        baseline_window: Tuple (start_time, end_time) for baseline current.
        response_window: Tuple (start_time, end_time) for steady-state current.

    Returns:
        RinResult object (value is Rin in MOhm, but conductance field is populated).
    """
    if voltage_step == 0:
        log.warning("Cannot calculate Conductance: Voltage step is zero.")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message="Voltage step is zero")

    try:
        # Find indices
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        response_mask = (time_vector >= response_window[0]) & (time_vector < response_window[1])

        if not np.any(baseline_mask) or not np.any(response_mask):
            log.warning("Cannot calculate Conductance: Time windows yielded no data points.")
            return RinResult(value=None, unit="MOhm", is_valid=False, error_message="No data in windows")

        # Calculate mean baseline and response currents
        baseline_current = np.mean(current_trace[baseline_mask])
        response_current = np.mean(current_trace[response_mask])

        delta_i = response_current - baseline_current  # pA

        # G = I / V
        # pA / mV = nS (nano-Siemens)
        # We want uS (micro-Siemens)
        # pA = 1e-12 A, mV = 1e-3 V -> 1e-9 S = nS.
        # uS = nS / 1000.

        conductance_ns = delta_i / voltage_step  # nS
        conductance_us = conductance_ns / 1000.0  # uS

        # Calculate Rin (Resistance)
        # R = 1/G. 1/uS = MOhm.
        rin_megaohms = 1.0 / conductance_us if conductance_us != 0 else float("inf")

        log.debug(
            f"Calculated Conductance: dI={delta_i:.3f}, dV={voltage_step:.3f}, G={conductance_us:.3f} uS, "
            f"Rin={rin_megaohms:.3f} MOhm"
        )

        return RinResult(
            value=rin_megaohms,
            unit="MOhm",
            conductance=conductance_us,
            voltage_deflection=voltage_step,
            current_injection=delta_i,
            baseline_voltage=None,  # Not applicable for current trace
            steady_state_voltage=None,  # Not applicable
        )

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception(f"Unexpected error during Conductance calculation: {e}")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message=str(e))


def _exp_growth(t, V_ss, V_0, tau):
    """Exponential growth function for fitting."""
    return V_ss + (V_0 - V_ss) * np.exp(-t / tau)


# Placeholder for Tau calculation
def calculate_tau(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    stim_start_time: float,
    fit_duration: float,  # Time window after stimulus start to fit
) -> Optional[float]:
    """
    Placeholder for Membrane Time Constant (Tau) calculation.
    Typically involves fitting an exponential to the rising phase of the voltage response.
    """
    try:
        fit_start_time = stim_start_time
        fit_end_time = stim_start_time + fit_duration

        fit_mask = (time_vector >= fit_start_time) & (time_vector < fit_end_time)
        t_fit = time_vector[fit_mask] - fit_start_time  # Start time at 0 for fit
        V_fit = voltage_trace[fit_mask]

        if len(t_fit) < 3:
            log.warning("Not enough data points to fit for Tau.")
            return None

        V_0 = V_fit[0]
        V_ss_guess = np.mean(V_fit[-5:])  # Guess steady state from last few points

        # bounds (V_ss, V_0, tau)
        lower_bounds = [-np.inf, -np.inf, 0.0001]  # tau > 0
        upper_bounds = [np.inf, np.inf, 1.0]  # tau < 1s

        p0 = [V_ss_guess, V_0, 0.01]  # Initial guess for tau = 10ms

        popt, _ = curve_fit(_exp_growth, t_fit, V_fit, p0=p0, bounds=(lower_bounds, upper_bounds))

        tau_ms = popt[2] * 1000  # convert tau to ms
        log.debug(f"Calculated Tau: {tau_ms:.3f} ms")
        return tau_ms
    except RuntimeError:
        log.warning("Optimal parameters not found for Tau calculation.")
        return None
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception(f"Unexpected error during Tau calculation: {e}")
        return None


# Placeholder for Sag potential calculation
def calculate_sag_ratio(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    baseline_window: Tuple[float, float],
    response_peak_window: Tuple[float, float],  # Window to find the peak hyperpolarization
    response_steady_state_window: Tuple[float, float],  # Window for steady-state hyperpolarization
) -> Optional[float]:
    """
    Placeholder for Sag Potential Ratio calculation.
    Sag = (V_peak - V_baseline) / (V_steady_state - V_baseline) or similar definitions.
    Requires a hyperpolarizing current step.
    """
    try:
        # Baseline
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        if not np.any(baseline_mask):
            return None
        v_baseline = np.mean(voltage_trace[baseline_mask])

        # Peak hyperpolarization
        peak_mask = (time_vector >= response_peak_window[0]) & (time_vector < response_peak_window[1])
        if not np.any(peak_mask):
            return None
        v_peak = np.min(voltage_trace[peak_mask])

        # Robustness Check: If peak is outlier, use percentile
        # Use 1st percentile for hyperpolarizing peak to avoid single-point noise
        if len(voltage_trace[peak_mask]) > 10:
            v_peak = np.percentile(voltage_trace[peak_mask], 1)
        else:
            v_peak = np.min(voltage_trace[peak_mask])

        # Steady-state hyperpolarization
        ss_mask = (time_vector >= response_steady_state_window[0]) & (time_vector < response_steady_state_window[1])
        if not np.any(ss_mask):
            return None
        v_ss = np.mean(voltage_trace[ss_mask])

        delta_v_peak = v_peak - v_baseline
        delta_v_ss = v_ss - v_baseline

        if delta_v_ss == 0:
            return None  # Avoid division by zero

        sag_ratio = delta_v_peak / delta_v_ss
        log.debug(f"Calculated Sag Ratio: {sag_ratio:.3f}")
        return sag_ratio
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception(f"Unexpected error during Sag calculation: {e}")
        return None


# --- Registry Wrappers for Batch Processing ---
@AnalysisRegistry.register(
    "rin_analysis",
    ui_params=[
        {
            "name": "current_amplitude",
            "label": "Current Step (pA):",
            "type": "float",
            "default": -50.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "voltage_step",
            "label": "Voltage Step (mV):",
            "type": "float",
            "default": -10.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {"name": "auto_detect_pulse", "label": "Auto-Detect Pulse", "type": "bool", "default": True},
        {
            "name": "baseline_start",
            "label": "Baseline Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "baseline_end",
            "label": "Baseline End (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "response_start",
            "label": "Response Start (s):",
            "type": "float",
            "default": 0.3,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "response_end",
            "label": "Response End (s):",
            "type": "float",
            "default": 0.4,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
    ],
)
def run_rin_analysis_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """
    Wrapper function for Input Resistance (Rin) analysis that conforms to the registry interface.

    Args:
        data: 1D NumPy array of voltage data
        time: 1D NumPy array of corresponding time points (seconds)
        sampling_rate: Sampling rate in Hz
        **kwargs: Additional parameters:
            - current_amplitude: Current step amplitude in pA (required)
            - auto_detect_pulse: Whether to auto-detect pulse windows (default: True)
            - baseline_start: Start time of baseline window (default: 0.0)
            - baseline_end: End time of baseline window (default: 0.1)
            - response_start: Start time of response window (default: 0.3)
            - response_end: End time of response window (default: 0.4)

    Returns:
        Dictionary containing results suitable for DataFrame rows.
    """
    try:
        current_amplitude = kwargs.get("current_amplitude", 0.0)
        auto_detect_pulse = kwargs.get("auto_detect_pulse", True)

        baseline_start = kwargs.get("baseline_start", 0.0)
        baseline_end = kwargs.get("baseline_end", 0.1)
        response_start = kwargs.get("response_start", 0.3)
        response_end = kwargs.get("response_end", 0.4)

        if current_amplitude == 0 and kwargs.get("voltage_step", 0.0) == 0:
            return {
                "rin_mohm": None,
                "conductance_us": None,
                "rin_error": "Current amplitude and Voltage step are zero",
            }

        # Determine mode (IC or VC)
        is_voltage_clamp = current_amplitude == 0 and kwargs.get("voltage_step", 0.0) != 0
        voltage_step = kwargs.get("voltage_step", 0.0)

        # Auto-detection logic
        if auto_detect_pulse:
            # Detect sharp transitions in voltage (proxy for current step start/end)
            # A better way would be to use the stimulus trace if available, but here we only have voltage.
            # We look for the largest derivatives.

            # Smooth slightly to reduce noise
            # simple moving average
            window_size = int(0.001 * sampling_rate)  # 1ms
            if window_size > 1:
                kernel = np.ones(window_size) / window_size
                smoothed_data = np.convolve(data, kernel, mode="same")
            else:
                smoothed_data = data

            dv = np.diff(smoothed_data)

            # Find start (largest change)
            # If current is negative (hyperpolarizing), we look for min dv, else max dv
            if current_amplitude < 0:
                start_idx = np.argmin(dv)
                # For end, we look for the opposite change (max dv) after start
                end_idx = start_idx + np.argmax(dv[start_idx:])
            else:
                start_idx = np.argmax(dv)
                end_idx = start_idx + np.argmin(dv[start_idx:])

            start_time = time[start_idx]
            end_time = time[end_idx]

            # Define windows relative to pulse
            # Baseline: 100ms before pulse start
            baseline_end = start_time - 0.005  # 5ms buffer
            baseline_start = max(time[0], baseline_end - 0.1)

            # Response: End of pulse (steady state)
            # Take last 100ms of the pulse
            response_end = end_time - 0.005  # 5ms buffer
            response_start = max(start_time, response_end - 0.1)

            log.debug(
                f"Auto-detected pulse: Start={start_time:.3f}s, End={end_time:.3f}s. "
                f"Baseline=[{baseline_start:.3f}, {baseline_end:.3f}], "
                f"Response=[{response_start:.3f}, {response_end:.3f}]"
            )

        if is_voltage_clamp:
            result = calculate_conductance(
                data, time, voltage_step, (baseline_start, baseline_end), (response_start, response_end)
            )
        else:
            result = calculate_rin(
                data, time, current_amplitude, (baseline_start, baseline_end), (response_start, response_end)
            )

        if result.is_valid and result.value is not None:
            return {
                "rin_mohm": result.value,
                "conductance_us": result.conductance if result.conductance is not None else 0.0,
                "voltage_deflection_mv": result.voltage_deflection if result.voltage_deflection is not None else 0.0,
                "baseline_voltage_mv": result.baseline_voltage if result.baseline_voltage is not None else 0.0,
                "steady_state_voltage_mv": (
                    result.steady_state_voltage if result.steady_state_voltage is not None else 0.0
                ),
                "auto_detected": auto_detect_pulse,
            }
        else:
            return {"rin_mohm": None, "conductance_us": None, "rin_error": result.error_message or "Unknown error"}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_rin_analysis_wrapper: {e}", exc_info=True)
        return {"rin_mohm": None, "conductance_us": None, "rin_error": str(e)}


@AnalysisRegistry.register(
    "tau_analysis",
    label="Membrane Time Constant (Tau)",
    ui_params=[
        {
            "name": "stim_start_time",
            "label": "Stim Start (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "fit_duration",
            "label": "Fit Duration (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
    ],
)
def run_tau_analysis_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """
    Wrapper function for Membrane Time Constant (Tau) analysis.

    Args:
        data: 1D NumPy array of voltage data
        time: 1D NumPy array of corresponding time points (seconds)
        sampling_rate: Sampling rate in Hz
        **kwargs: Additional parameters:
            - stim_start_time: Time when stimulus starts (default: 0.1)
            - fit_duration: Duration of fit window in seconds (default: 0.05)

    Returns:
        Dictionary containing results suitable for DataFrame rows.
    """
    try:
        stim_start_time = kwargs.get("stim_start_time", 0.1)
        fit_duration = kwargs.get("fit_duration", 0.05)

        tau_ms = calculate_tau(data, time, stim_start_time, fit_duration)

        if tau_ms is not None:
            return {
                "tau_ms": tau_ms,
            }
        else:
            return {"tau_ms": None, "tau_error": "Tau calculation failed"}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_tau_analysis_wrapper: {e}", exc_info=True)
        return {"tau_ms": None, "tau_error": str(e)}
