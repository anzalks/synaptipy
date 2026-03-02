# src/Synaptipy/core/analysis/intrinsic_properties.py
# -*- coding: utf-8 -*-
"""
Analysis functions for intrinsic membrane properties.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import linregress

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.results import RinResult

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
            value=None,
            unit="MOhm",
            is_valid=False,
            error_message="Current amplitude is zero",
            parameters=parameters or {},
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
        # Calculate Rin = |delta_V| / |delta_I|
        # Units: voltage in mV, current in pA
        # mV / (pA / 1000) = mV / nA = MOhm
        delta_i_nA = abs(current_amplitude) / 1000.0
        if delta_i_nA == 0:
            log.warning("Current amplitude effectively zero after conversion.")
            return RinResult(
                value=None,
                unit="MOhm",
                is_valid=False,
                error_message="Current amplitude effectively zero",
                parameters=parameters or {},
            )
        rin = abs(delta_v) / delta_i_nA

        # Conductance: G = 1/R. 1/MOhm = μS (micro-Siemens)
        # 1 MOhm = 10^6 Ohm, so 1/(MOhm) = 10^-6 S = 1 μS
        conductance_us = 1.0 / rin if rin != 0 else 0.0

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
            value=None,
            unit="MOhm",
            is_valid=False,
            error_message="IndexError during calculation",
            parameters=parameters or {},
        )
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception(f"Unexpected error during Rin calculation: {e}")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message=str(e), parameters=parameters or {})


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
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message=str(e), parameters=parameters or {})


def calculate_iv_curve(
    sweeps: List[np.ndarray],
    time_vectors: List[np.ndarray],
    current_steps: List[float],
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float],
) -> Dict[str, Any]:
    """
    Calculates the Current-Voltage (I-V) relationship and aggregate Input Resistance (Rin)
    across multiple traces/sweeps.

    Args:
        sweeps: List of voltage traces.
        time_vectors: List of corresponding time vectors.
        current_steps: List of injected current step amplitudes in pA.
        baseline_window: Tuple (start_time, end_time) for the baseline calculation.
        response_window: Tuple (start_time, end_time) for steady-state response calculation.

    Returns:
        Dictionary with I-V Curve properties including aggregate Rin(MOhm).
    """
    num_sweeps = len(sweeps)
    if num_sweeps == 0:
        return {"error": "No sweeps provided"}

    if len(current_steps) != num_sweeps:
        log.warning(
            f"Mismatch between sweeps ({num_sweeps}) and current_steps ({len(current_steps)}). Truncating to minimum."
        )
        min_len = min(num_sweeps, len(current_steps))
        sweeps = sweeps[:min_len]
        time_vectors = time_vectors[:min_len]
        current_steps = current_steps[:min_len]

    baseline_voltages = []
    steady_state_voltages = []
    delta_vs = []

    for voltage_trace, time_vector in zip(sweeps, time_vectors):
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        response_mask = (time_vector >= response_window[0]) & (time_vector < response_window[1])

        if not np.any(baseline_mask) or not np.any(response_mask):
            baseline_voltages.append(np.nan)
            steady_state_voltages.append(np.nan)
            delta_vs.append(np.nan)
            continue

        v_base = np.mean(voltage_trace[baseline_mask])
        v_resp = np.mean(voltage_trace[response_mask])

        baseline_voltages.append(v_base)
        steady_state_voltages.append(v_resp)
        delta_vs.append(v_resp - v_base)

    # Filter out NaNs for linear regression
    valid_indices = [i for i, dv in enumerate(delta_vs) if not np.isnan(dv)]
    valid_currents = [current_steps[i] for i in valid_indices]
    valid_delta_vs = [delta_vs[i] for i in valid_indices]

    rin_mohm = None
    r_squared = None
    iv_intercept = None

    if len(valid_currents) >= 2:
        try:
            # Rin is standardly (Delta V) / (Delta I).
            # Convert current to nA to get Rin in MOhm (mV / nA = MOhm).
            currents_na = np.array(valid_currents) / 1000.0

            # Use delta V vs delta I for Rin calculation
            slope, intercept, r_value, p_value, std_err = linregress(currents_na, valid_delta_vs)
            rin_mohm = slope
            iv_intercept = intercept
            r_squared = r_value**2
        except Exception as e:
            log.warning(f"Linear regression failed during I-V curve trace calculation: {e}", exc_info=True)

    return {
        "rin_aggregate_mohm": rin_mohm,
        "iv_intercept": iv_intercept,
        "iv_r_squared": r_squared,
        "baseline_voltages": baseline_voltages,
        "steady_state_voltages": steady_state_voltages,
        "delta_vs": delta_vs,
        "current_steps": current_steps,
    }


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
    model: str = "mono",
    tau_bounds: Optional[Tuple[float, float]] = None,
    artifact_blanking_ms: float = 0.5,
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
        artifact_blanking_ms: Time to skip after stimulus onset to ignore
                              the fast capacitive artifact, in ms.

    Returns:
        For model='mono': Tau in ms (float), or None if fitting fails.
        For model='bi': Dict with keys {tau_fast_ms, tau_slow_ms,
                        amplitude_fast, amplitude_slow, V_ss}, or None.
    """
    if tau_bounds is None:
        tau_bounds = (1e-4, 1.0)
    tau_min, tau_max = tau_bounds

    try:
        fit_start_time = stim_start_time + (artifact_blanking_ms / 1000.0)
        fit_end_time = stim_start_time + fit_duration

        fit_mask = (time_vector >= fit_start_time) & (time_vector < fit_end_time)
        t_fit = time_vector[fit_mask] - fit_start_time  # Start time at 0 for fit
        V_fit = voltage_trace[fit_mask]

        if len(t_fit) < 3:
            log.warning("Not enough data points to fit for Tau.")
            return None

        V_0 = V_fit[0]
        V_ss_guess = np.mean(V_fit[-5:])  # Guess steady state from last few points

        if model == "mono":
            # --- Single-exponential fit ---
            lower_bounds = [-np.inf, -np.inf, tau_min]
            upper_bounds = [np.inf, np.inf, tau_max]
            p0 = [V_ss_guess, V_0, 0.01]

            popt, _ = curve_fit(_exp_growth, t_fit, V_fit, p0=p0, bounds=(lower_bounds, upper_bounds), maxfev=5000)

            tau_ms = popt[2] * 1000  # convert tau to ms

            # Generate fit curve for overlay visualisation
            fit_values = _exp_growth(t_fit, *popt)
            fit_time = (t_fit + fit_start_time).tolist()
            fit_values_list = fit_values.tolist()

            log.debug("Calculated Tau (mono): %.3f ms", tau_ms)
            return {
                "tau_ms": tau_ms,
                "fit_time": fit_time,
                "fit_values": fit_values_list,
            }

        elif model == "bi":
            # --- Bi-exponential fit ---
            if len(t_fit) < 6:
                log.warning("Not enough data for bi-exponential fit (need >= 6).")
                return None

            # Initial guesses: split amplitude 60/40 fast/slow
            A_fast_guess = 0.6 * (V_0 - V_ss_guess)
            A_slow_guess = 0.4 * (V_0 - V_ss_guess)
            tau_fast_guess = min(0.005, tau_max * 0.1)
            tau_slow_guess = min(0.05, tau_max * 0.5)

            p0 = [V_ss_guess, A_fast_guess, tau_fast_guess, A_slow_guess, tau_slow_guess]

            lower_bounds = [-np.inf, -np.inf, tau_min, -np.inf, tau_min]
            upper_bounds = [np.inf, np.inf, tau_max, np.inf, tau_max]

            popt, pcov = curve_fit(
                _bi_exp_growth, t_fit, V_fit, p0=p0, bounds=(lower_bounds, upper_bounds), maxfev=10000
            )

            V_ss_fit, A_fast, tau_fast, A_slow, tau_slow = popt

            # Ensure tau_fast < tau_slow (swap if needed)
            if tau_fast > tau_slow:
                tau_fast, tau_slow = tau_slow, tau_fast
                A_fast, A_slow = A_slow, A_fast

            # Generate fit curve for overlay visualisation
            fit_values = _bi_exp_growth(t_fit, *popt)
            fit_time = (t_fit + fit_start_time).tolist()
            fit_values_list = fit_values.tolist()

            result = {
                "tau_fast_ms": tau_fast * 1000,
                "tau_slow_ms": tau_slow * 1000,
                "amplitude_fast": A_fast,
                "amplitude_slow": A_slow,
                "V_ss": V_ss_fit,
                "fit_time": fit_time,
                "fit_values": fit_values_list,
            }
            log.debug("Calculated Tau (bi): fast=%.3f ms, slow=%.3f ms", result["tau_fast_ms"], result["tau_slow_ms"])
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


def calculate_sag_ratio(  # noqa: C901
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    baseline_window: Tuple[float, float],
    response_peak_window: Tuple[float, float],
    response_steady_state_window: Tuple[float, float],
    peak_smoothing_ms: float = 5.0,
    rebound_window_ms: float = 100.0,
) -> Optional[Dict[str, float]]:
    """
    Calculate Sag Potential Ratio from a hyperpolarising current step.

    The sag ratio quantifies the contribution of hyperpolarisation-activated
    cation current (I_h) to the voltage response.  Two conventions are
    reported:

    * **Ratio form** (``sag_ratio``):
      ``(V_peak - V_baseline) / (V_ss - V_baseline)``.
      Values > 1 indicate sag; 1 means no sag.

    * **Percentage form** (``sag_percentage``):
      ``100 * (V_peak - V_ss) / (V_peak - V_baseline)``.

    V_peak is extracted as the minimum of a Savitzky-Golay smoothed trace
    within *response_peak_window*.  V_ss is the arithmetic mean over
    *response_steady_state_window*.

    Args:
        voltage_trace: 1-D voltage array (mV).
        time_vector: 1-D time array (s).
        baseline_window: (start, end) seconds for baseline voltage.
        response_peak_window: (start, end) seconds to search for peak
            hyperpolarisation (typically the first 50-100 ms of the step).
        response_steady_state_window: (start, end) seconds for steady-state
            measurement (typically the last 50-100 ms of the step).
        peak_smoothing_ms: Savitzky-Golay smoothing window for V_peak
            extraction, in milliseconds.  Default 5.0 ms.
        rebound_window_ms: Duration (ms) after stimulus offset in which to
            measure rebound depolarisation.  Default 100.0 ms.

    Returns:
        Dictionary with keys ``sag_ratio``, ``sag_percentage``, ``v_peak``,
        ``v_ss``, ``v_baseline``, ``rebound_depolarization``; or *None* if
        the calculation cannot be performed.
    """
    try:
        dt = time_vector[1] - time_vector[0] if len(time_vector) > 1 else 1.0

        # Baseline
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        if not np.any(baseline_mask):
            return None
        v_baseline = float(np.mean(voltage_trace[baseline_mask]))

        # Peak hyperpolarization — Savitzky-Golay smoothing for robustness
        peak_mask = (time_vector >= response_peak_window[0]) & (time_vector < response_peak_window[1])
        if not np.any(peak_mask):
            return None
        peak_data = voltage_trace[peak_mask]

        from scipy.signal import savgol_filter

        window_length = max(5, int((peak_smoothing_ms / 1000.0) / dt))
        if window_length % 2 == 0:
            window_length += 1

        if len(peak_data) >= window_length:
            smoothed_peak = savgol_filter(peak_data, window_length, 3)
            v_peak = float(np.min(smoothed_peak))
        else:
            v_peak = float(np.min(peak_data))

        # Steady-state hyperpolarization
        ss_mask = (time_vector >= response_steady_state_window[0]) & (time_vector < response_steady_state_window[1])
        if not np.any(ss_mask):
            return None
        v_ss = float(np.mean(voltage_trace[ss_mask]))

        delta_v_peak = v_peak - v_baseline
        delta_v_ss = v_ss - v_baseline

        if delta_v_ss == 0:
            return None  # Avoid division by zero

        sag_ratio = float(delta_v_peak / delta_v_ss)

        # Sag percentage: 100 * (V_peak - V_ss) / (V_peak - V_baseline)
        if delta_v_peak == 0:
            sag_percentage = 0.0
        else:
            sag_percentage = float(100.0 * (v_peak - v_ss) / delta_v_peak)

        # Rebound depolarization
        rebound_start = response_steady_state_window[1]
        rebound_end = rebound_start + (rebound_window_ms / 1000.0)
        rebound_mask = (time_vector >= rebound_start) & (time_vector < rebound_end)

        if np.any(rebound_mask):
            rebound_data = voltage_trace[rebound_mask]
            if len(rebound_data) >= window_length:
                smoothed_rebound = savgol_filter(rebound_data, window_length, 3)
                v_rebound_max = float(np.max(smoothed_rebound))
            else:
                v_rebound_max = float(np.max(rebound_data))
            rebound_depolarization = v_rebound_max - v_baseline
        else:
            rebound_depolarization = 0.0

        log.debug(
            "Sag Ratio=%.3f, Sag%%=%.1f%%, Rebound=%.3f mV",
            sag_ratio,
            sag_percentage,
            rebound_depolarization,
        )
        return {
            "sag_ratio": sag_ratio,
            "sag_percentage": sag_percentage,
            "v_peak": v_peak,
            "v_ss": v_ss,
            "v_baseline": v_baseline,
            "rebound_depolarization": rebound_depolarization,
        }
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception("Error during Sag calculation: %s", e)
        return None


# --- Registry Wrappers for Batch Processing ---
@AnalysisRegistry.register(
    "sag_ratio_analysis",
    label="Sag Ratio (Ih)",
    plots=[
        {"name": "Trace", "type": "trace"},
        {
            "type": "result_hlines",
            "keys": ["v_baseline", "v_peak", "v_ss"],
            "colors": {
                "v_baseline": "b",
                "v_peak": "m",
                "v_ss": "r",
            },
        },
    ],
    ui_params=[
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
            "name": "peak_window_start",
            "label": "Peak Window Start (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "peak_window_end",
            "label": "Peak Window End (s):",
            "type": "float",
            "default": 0.3,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "ss_window_start",
            "label": "Steady-State Start (s):",
            "type": "float",
            "default": 0.8,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "ss_window_end",
            "label": "Steady-State End (s):",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "peak_smoothing_ms",
            "label": "Peak Smoothing (ms):",
            "type": "float",
            "default": 5.0,
            "min": 0.0,
            "max": 50.0,
            "decimals": 1,
        },
        {
            "name": "rebound_window_ms",
            "label": "Rebound Window (ms):",
            "type": "float",
            "default": 100.0,
            "min": 0.0,
            "max": 1000.0,
            "decimals": 1,
        },
    ],
)
def run_sag_ratio_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """Wrapper function for Sag Ratio analysis that conforms to the registry interface.

    Args:
        data: 1D NumPy array of voltage data (mV).
        time: 1D NumPy array of corresponding time points (s).
        sampling_rate: Sampling rate in Hz.
        **kwargs: Additional parameters:
            - baseline_start / baseline_end: Baseline window (s).
            - peak_window_start / peak_window_end: Peak search window (s).
            - ss_window_start / ss_window_end: Steady-state window (s).
            - peak_smoothing_ms: Savitzky-Golay smoothing (ms, default 5.0).
            - rebound_window_ms: Rebound measurement window (ms, default 100.0).

    Returns:
        Dictionary containing sag ratio results suitable for DataFrame rows.
    """
    try:
        baseline_start = kwargs.get("baseline_start", 0.0)
        baseline_end = kwargs.get("baseline_end", 0.1)
        peak_start = kwargs.get("peak_window_start", 0.1)
        peak_end = kwargs.get("peak_window_end", 0.3)
        ss_start = kwargs.get("ss_window_start", 0.8)
        ss_end = kwargs.get("ss_window_end", 1.0)
        peak_smoothing = kwargs.get("peak_smoothing_ms", 5.0)
        rebound_window = kwargs.get("rebound_window_ms", 100.0)

        result = calculate_sag_ratio(
            voltage_trace=data,
            time_vector=time,
            baseline_window=(baseline_start, baseline_end),
            response_peak_window=(peak_start, peak_end),
            response_steady_state_window=(ss_start, ss_end),
            peak_smoothing_ms=peak_smoothing,
            rebound_window_ms=rebound_window,
        )

        if result is not None:
            return {
                "sag_ratio": result["sag_ratio"],
                "sag_percentage": result["sag_percentage"],
                "v_peak": result["v_peak"],
                "v_ss": result["v_ss"],
                "v_baseline": result["v_baseline"],
                "rebound_depolarization": result["rebound_depolarization"],
            }
        else:
            return {
                "sag_ratio": None,
                "sag_error": "Sag ratio calculation failed (check windows)",
            }

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_sag_ratio_wrapper: {e}", exc_info=True)
        return {"sag_ratio": None, "sag_error": str(e)}


@AnalysisRegistry.register(
    "rin_analysis",
    label="Input Resistance",
    plots=[
        {"name": "Trace", "type": "trace"},
        {
            "type": "result_hlines",
            "keys": ["baseline_voltage_mv", "steady_state_voltage_mv"],
            "colors": {"baseline_voltage_mv": "b", "steady_state_voltage_mv": "r"},
        },
    ],
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
            # We look for the largest derivatives in a smoothed trace.

            # Smooth slightly to reduce noise
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

            auto_start_time = time[start_idx]
            auto_end_time = time[end_idx]

            # Define windows relative to pulse
            # Baseline: 100ms before pulse start
            auto_baseline_end = auto_start_time - 0.005  # 5ms buffer
            auto_baseline_start = max(time[0], auto_baseline_end - 0.1)

            # Response: End of pulse (steady state), last 100ms of the pulse
            auto_response_end = auto_end_time - 0.005  # 5ms buffer
            auto_response_start = max(auto_start_time, auto_response_end - 0.1)

            # Validate: ensure both windows contain at least a few samples
            bl_mask = (time >= auto_baseline_start) & (time < auto_baseline_end)
            resp_mask = (time >= auto_response_start) & (time < auto_response_end)
            auto_windows_valid = np.sum(bl_mask) >= 2 and np.sum(resp_mask) >= 2

            if auto_windows_valid:
                baseline_start = auto_baseline_start
                baseline_end = auto_baseline_end
                response_start = auto_response_start
                response_end = auto_response_end
                log.debug(
                    f"Auto-detected pulse: Start={auto_start_time:.3f}s, End={auto_end_time:.3f}s. "
                    f"Baseline=[{baseline_start:.3f}, {baseline_end:.3f}], "
                    f"Response=[{response_start:.3f}, {response_end:.3f}]"
                )
            else:
                log.warning(
                    "Auto-detected windows are empty "
                    f"(baseline=[{auto_baseline_start:.3f}, {auto_baseline_end:.3f}], "
                    f"response=[{auto_response_start:.3f}, {auto_response_end:.3f}]). "
                    "Falling back to user-provided spinbox values."
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
                data,
                time,
                voltage_step,
                (baseline_start, baseline_end),
                (response_start, response_end),
                parameters=params,
            )
        else:
            result = calculate_rin(
                data,
                time,
                current_amplitude,
                (baseline_start, baseline_end),
                (response_start, response_end),
                parameters=params,
            )

        if result.is_valid and result.value is not None:
            out = {
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
            # Emit the actual windows used so the GUI can sync spinboxes
            out["_used_baseline_start"] = baseline_start
            out["_used_baseline_end"] = baseline_end
            out["_used_response_start"] = response_start
            out["_used_response_end"] = response_end
            return out
        else:
            return {"rin_mohm": None, "conductance_us": None, "rin_error": result.error_message or "Unknown error"}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_rin_analysis_wrapper: {e}", exc_info=True)
        return {"rin_mohm": None, "conductance_us": None, "rin_error": str(e)}


@AnalysisRegistry.register(
    "tau_analysis",
    label="Tau (Time Constant)",
    plots=[
        {"name": "Trace", "type": "trace"},
        {
            "type": "overlay_fit",
            "x": "fit_time",
            "y": "fit_values",
            "color": "r",
            "width": 2,
            "label": "Exp Fit",
        },
    ],
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
            "name": "artifact_blanking_ms",
            "label": "Blanking (ms):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 10.0,
            "decimals": 2,
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
            - artifact_blanking_ms: Blanking period in ms (default: 0.5)
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
        artifact_blanking_ms = kwargs.get("artifact_blanking_ms", 0.5)

        result = calculate_tau(
            data,
            time,
            stim_start_time,
            fit_duration,
            model=model,
            tau_bounds=tau_bounds,
            artifact_blanking_ms=artifact_blanking_ms,
        )

        params = {
            "stim_start_time": stim_start_time,
            "fit_duration": fit_duration,
            "model": model,
            "tau_bounds": tau_bounds,
        }

        if result is not None:
            if model == "bi" and isinstance(result, dict) and "tau_fast_ms" in result:
                return {
                    "tau_fast_ms": result["tau_fast_ms"],
                    "tau_slow_ms": result["tau_slow_ms"],
                    "amplitude_fast": result["amplitude_fast"],
                    "amplitude_slow": result["amplitude_slow"],
                    "tau_model": model,
                    "parameters": params,
                    "fit_time": result.get("fit_time", []),
                    "fit_values": result.get("fit_values", []),
                }
            elif isinstance(result, dict) and "tau_ms" in result:
                return {
                    "tau_ms": result["tau_ms"],
                    "tau_model": model,
                    "parameters": params,
                    "fit_time": result.get("fit_time", []),
                    "fit_values": result.get("fit_values", []),
                }
            else:
                # Legacy fallback (shouldn't happen with updated calculate_tau)
                return {
                    "tau_ms": result if isinstance(result, (int, float)) else None,
                    "tau_model": model,
                    "parameters": params,
                }
        else:
            return {"tau_ms": None, "tau_error": "Tau calculation failed", "parameters": params}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_tau_analysis_wrapper: {e}", exc_info=True)
        return {"tau_ms": None, "tau_error": str(e)}


@AnalysisRegistry.register(
    "iv_curve_analysis",
    label="I-V Curve",
    requires_multi_trial=True,
    plots=[
        {"name": "Trace", "type": "trace"},
        {
            "type": "popup_xy",
            "title": "I-V Curve",
            "x": "current_steps",
            "y": "delta_vs",
            "x_label": "Current (pA)",
            "y_label": "Voltage Response (mV)",
            "slope_key": "rin_aggregate_mohm",
            "intercept_key": "iv_intercept",
            "x_scale": 0.001,
        },
    ],
    ui_params=[
        {
            "name": "start_current",
            "label": "Start Current (pA):",
            "type": "float",
            "default": -50.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "step_current",
            "label": "Step Current (pA):",
            "type": "float",
            "default": 10.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
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
def run_iv_curve_wrapper(
    data_list: List[np.ndarray], time_list: List[np.ndarray], sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """
    Wrapper for Multi-Trial I-V Curve Analysis.
    """
    try:
        start_current = kwargs.get("start_current", -50.0)
        step_current = kwargs.get("step_current", 10.0)

        baseline_start = kwargs.get("baseline_start", 0.0)
        baseline_end = kwargs.get("baseline_end", 0.1)
        response_start = kwargs.get("response_start", 0.3)
        response_end = kwargs.get("response_end", 0.4)

        # Handle formatting of inputs
        if isinstance(data_list, np.ndarray):
            if data_list.ndim == 1:
                data_list = [data_list]
                time_list = [time_list] if isinstance(time_list, np.ndarray) else time_list
            elif data_list.ndim == 2:
                data_list = [data_list[i] for i in range(data_list.shape[0])]
                if isinstance(time_list, np.ndarray) and time_list.ndim == 1:
                    time_list = [time_list for _ in range(len(data_list))]
                elif isinstance(time_list, np.ndarray) and time_list.ndim == 2:
                    time_list = [time_list[i] for i in range(time_list.shape[0])]

        if isinstance(time_list, np.ndarray):
            time_list = [time_list]

        num_sweeps = len(data_list)
        current_steps = [start_current + i * step_current for i in range(num_sweeps)]

        baseline_window = (baseline_start, baseline_end)
        response_window = (response_start, response_end)

        results = calculate_iv_curve(
            sweeps=data_list,
            time_vectors=time_list,
            current_steps=current_steps,
            baseline_window=baseline_window,
            response_window=response_window,
        )

        if "error" in results:
            return {"iv_curve_error": results["error"]}

        return {
            "rin_aggregate_mohm": results["rin_aggregate_mohm"],
            "iv_intercept": results["iv_intercept"],
            "iv_r_squared": results["iv_r_squared"],
            "baseline_voltages": results["baseline_voltages"],
            "steady_state_voltages": results["steady_state_voltages"],
            "delta_vs": results["delta_vs"],
            "current_steps": results["current_steps"],
        }

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_iv_curve_wrapper: {e}", exc_info=True)
        return {"iv_curve_error": str(e)}
