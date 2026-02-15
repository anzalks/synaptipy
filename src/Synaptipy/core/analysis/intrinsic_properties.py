# src/Synaptipy/core/analysis/intrinsic_properties.py
# -*- coding: utf-8 -*-
"""
Analysis functions for intrinsic membrane properties.
"""
import logging
import numpy as np
from typing import Optional, Tuple, Dict, Any, Union
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
    parameters: Dict[str, Any] = None,
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
        return RinResult(
            value=None, unit="MOhm", is_valid=False, error_message="Current amplitude is zero",
            parameters=parameters or {}
        )

    try:
        # Find indices for baseline and response windows
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        response_mask = (time_vector >= response_window[0]) & (time_vector < response_window[1])

        if not np.any(baseline_mask) or not np.any(response_mask):
            log.warning("Cannot calculate Rin: Time windows yielded no data points.")
            return RinResult(
                value=None, unit="MOhm", is_valid=False, error_message="No data in windows", parameters=parameters or {}
            )

        # Calculate mean baseline and response voltages
        baseline_voltage = np.mean(voltage_trace[baseline_mask])
        response_voltage = np.mean(voltage_trace[response_mask])

        if np.isclose(response_voltage, baseline_voltage):
            # Handle case where response equals baseline
            delta_v = 0.0
        else:
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
            parameters=parameters or {},
        )

    except IndexError:
        log.exception("IndexError during Rin calculation. Check trace/time vector alignment and window validity.")
        return RinResult(
            value=None, unit="MOhm", is_valid=False, error_message="IndexError during calculation",
            parameters=parameters or {}
        )
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception(f"Unexpected error during Rin calculation: {e}")
        return RinResult(
            value=None, unit="MOhm", is_valid=False, error_message=str(e), parameters=parameters or {}
        )


def calculate_conductance(
    current_trace: np.ndarray,
    time_vector: np.ndarray,
    voltage_step: float,  # Delta V in mV
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float],
    parameters: Dict[str, Any] = None,
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
        return RinResult(
            value=None, unit="MOhm", is_valid=False, error_message="Voltage step is zero", parameters=parameters or {}
        )

    try:
        # Find indices
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        response_mask = (time_vector >= response_window[0]) & (time_vector < response_window[1])

        if not np.any(baseline_mask) or not np.any(response_mask):
            log.warning("Cannot calculate Conductance: Time windows yielded no data points.")
            return RinResult(
                value=None, unit="MOhm", is_valid=False, error_message="No data in windows", parameters=parameters or {}
            )

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
            parameters=parameters or {},
        )

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception(f"Unexpected error during Conductance calculation: {e}")
        return RinResult(
            value=None, unit="MOhm", is_valid=False, error_message=str(e), parameters=parameters or {}
        )


def _exp_growth(t, V_ss, V_0, tau):
    """Mono-exponential growth/decay function for fitting."""
    return V_ss + (V_0 - V_ss) * np.exp(-t / tau)


def _bi_exp_growth(t, V_ss, A_fast, tau_fast, A_slow, tau_slow):
    """
    Bi-exponential growth/decay function.

    V(t) = V_ss + A_fast * exp(-t / tau_fast) + A_slow * exp(-t / tau_slow)

    Args:
        t: Time array (s), starting at 0.
        V_ss: Steady-state voltage.
        A_fast: Amplitude of fast component.
        tau_fast: Time constant of fast component (s).
        A_slow: Amplitude of slow component.
        tau_slow: Time constant of slow component (s).
    """
    return V_ss + A_fast * np.exp(-t / tau_fast) + A_slow * np.exp(-t / tau_slow)


def calculate_tau(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    stim_start_time: float,
    fit_duration: float,
    model: str = 'mono',
    tau_bounds: Optional[Tuple[float, float]] = None,
) -> Optional[Union[float, Dict[str, float]]]:
    """
    Calculate Membrane Time Constant (Tau) by fitting an exponential
    to the voltage response after stimulus onset.

    Args:
        voltage_trace: 1D NumPy array of the voltage recording (mV).
        time_vector: 1D NumPy array of corresponding time points (s).
        stim_start_time: Time of stimulus onset (s).
        fit_duration: Duration of fit window after stimulus start (s).
        model: Fitting model, 'mono' for single-exponential or 'bi'
               for bi-exponential.
        tau_bounds: Tuple (min_tau, max_tau) in seconds. Constrains
                    allowed tau values. Defaults to (1e-4, 1.0) if None.

    Returns:
        For model='mono': Tau in ms (float), or None if fitting fails.
        For model='bi': Dict with keys {tau_fast_ms, tau_slow_ms,
                        amplitude_fast, amplitude_slow, V_ss}, or None.
    """
    if tau_bounds is None:
        tau_bounds = (1e-4, 1.0)
    tau_min, tau_max = tau_bounds

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

        if model == 'mono':
            # --- Single-exponential fit ---
            lower_bounds = [-np.inf, -np.inf, tau_min]
            upper_bounds = [np.inf, np.inf, tau_max]
            p0 = [V_ss_guess, V_0, 0.01]

            popt, _ = curve_fit(
                _exp_growth, t_fit, V_fit, p0=p0,
                bounds=(lower_bounds, upper_bounds), maxfev=5000
            )

            tau_ms = popt[2] * 1000  # convert tau to ms
            log.debug("Calculated Tau (mono): %.3f ms", tau_ms)
            return tau_ms

        elif model == 'bi':
            # --- Bi-exponential fit ---
            if len(t_fit) < 6:
                log.warning("Not enough data for bi-exponential fit (need >= 6).")
                return None

            # Initial guesses: split amplitude 60/40 fast/slow
            A_fast_guess = 0.6 * (V_0 - V_ss_guess)
            A_slow_guess = 0.4 * (V_0 - V_ss_guess)
            tau_fast_guess = min(0.005, tau_max * 0.1)
            tau_slow_guess = min(0.05, tau_max * 0.5)

            p0 = [V_ss_guess, A_fast_guess, tau_fast_guess,
                  A_slow_guess, tau_slow_guess]

            lower_bounds = [-np.inf, -np.inf, tau_min, -np.inf, tau_min]
            upper_bounds = [np.inf, np.inf, tau_max, np.inf, tau_max]

            popt, pcov = curve_fit(
                _bi_exp_growth, t_fit, V_fit, p0=p0,
                bounds=(lower_bounds, upper_bounds), maxfev=10000
            )

            V_ss_fit, A_fast, tau_fast, A_slow, tau_slow = popt

            # Ensure tau_fast < tau_slow (swap if needed)
            if tau_fast > tau_slow:
                tau_fast, tau_slow = tau_slow, tau_fast
                A_fast, A_slow = A_slow, A_fast

            result = {
                'tau_fast_ms': tau_fast * 1000,
                'tau_slow_ms': tau_slow * 1000,
                'amplitude_fast': A_fast,
                'amplitude_slow': A_slow,
                'V_ss': V_ss_fit,
            }
            log.debug(
                "Calculated Tau (bi): fast=%.3f ms, slow=%.3f ms",
                result['tau_fast_ms'], result['tau_slow_ms']
            )
            return result

        else:
            log.error("Unknown model '%s'. Use 'mono' or 'bi'.", model)
            return None

    except RuntimeError:
        log.warning("Optimal parameters not found for Tau calculation (model=%s).", model)
        return None
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception("Unexpected error during Tau calculation: %s", e)
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
            "visible_when": {"context": "clamp_mode", "value": "current_clamp"},
        },
        {
            "name": "voltage_step",
            "label": "Voltage Step (mV):",
            "type": "float",
            "default": -10.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
            "visible_when": {"context": "clamp_mode", "value": "voltage_clamp"},
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
            # If step is negative (hyperpolarizing), we look for min dv, else max dv
            is_negative_step = (current_amplitude < 0) or (current_amplitude == 0 and voltage_step < 0)

            if is_negative_step:
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

        # Prepare params dict
        params = {
            "current_amplitude": current_amplitude,
            "voltage_step": voltage_step,
            "auto_detect_pulse": auto_detect_pulse,
            "baseline_window": (baseline_start, baseline_end),
            "response_window": (response_start, response_end),
        }

        if is_voltage_clamp:
            result = calculate_conductance(
                data, time, voltage_step, (baseline_start, baseline_end), (response_start, response_end),
                parameters=params
            )
        else:
            result = calculate_rin(
                data, time, current_amplitude, (baseline_start, baseline_end), (response_start, response_end),
                parameters=params
            )

        if result.is_valid and result.value is not None:
            return {
                "rin_mohm": result.value,
                "conductance_us": result.conductance if result.conductance is not None else 0.0,
                "voltage_deflection_mv": result.voltage_deflection if result.voltage_deflection is not None else 0.0,
                "current_injection_pa": result.current_injection if result.current_injection is not None else 0.0,
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
        {
            "name": "tau_model",
            "label": "Model:",
            "type": "choice",
            "default": "mono",
            "options": ["mono", "bi"],
        },
        {
            "name": "tau_bound_min",
            "label": "Tau Min (s):",
            "type": "float",
            "default": 0.0001,
            "min": 0.0,
            "max": 1.0,
            "decimals": 5,
        },
        {
            "name": "tau_bound_max",
            "label": "Tau Max (s):",
            "type": "float",
            "default": 1.0,
            "min": 0.001,
            "max": 100.0,
            "decimals": 4,
        },
    ],
)
def run_tau_analysis_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """
    Wrapper function for Membrane Time Constant (Tau) analysis.

    Args:
        data: 1D NumPy array of voltage data (mV).
        time: 1D NumPy array of corresponding time points (s).
        sampling_rate: Sampling rate in Hz.
        **kwargs: Additional parameters:
            - stim_start_time: Time when stimulus starts (s, default: 0.1)
            - fit_duration: Duration of fit window (s, default: 0.05)
            - tau_model: 'mono' or 'bi' (default: 'mono')
            - tau_bound_min: Minimum tau bound (s, default: 0.0001)
            - tau_bound_max: Maximum tau bound (s, default: 1.0)

    Returns:
        Dictionary containing results suitable for DataFrame rows.
    """
    try:
        stim_start_time = kwargs.get("stim_start_time", 0.1)
        fit_duration = kwargs.get("fit_duration", 0.05)
        model = kwargs.get("tau_model", "mono")
        tau_bound_min = kwargs.get("tau_bound_min", 0.0001)
        tau_bound_max = kwargs.get("tau_bound_max", 1.0)
        tau_bounds = (tau_bound_min, tau_bound_max)

        result = calculate_tau(
            data, time, stim_start_time, fit_duration,
            model=model, tau_bounds=tau_bounds
        )

        params = {
            'stim_start_time': stim_start_time,
            'fit_duration': fit_duration,
            'model': model,
            'tau_bounds': tau_bounds,
        }

        if result is not None:
            if model == 'bi' and isinstance(result, dict):
                return {
                    "tau_fast_ms": result['tau_fast_ms'],
                    "tau_slow_ms": result['tau_slow_ms'],
                    "amplitude_fast": result['amplitude_fast'],
                    "amplitude_slow": result['amplitude_slow'],
                    "tau_model": model,
                    "parameters": params,
                }
            else:
                return {
                    "tau_ms": result,
                    "tau_model": model,
                    "parameters": params,
                }
        else:
            return {"tau_ms": None, "tau_error": "Tau calculation failed", "parameters": params}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_tau_analysis_wrapper: {e}", exc_info=True)
        return {"tau_ms": None, "tau_error": str(e)}

