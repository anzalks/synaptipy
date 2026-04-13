# src/Synaptipy/core/analysis/passive_properties.py
# -*- coding: utf-8 -*-
"""
Core Protocol Module 1: Passive Membrane Properties.

Consolidates: Resting Membrane Potential (RMP), Input Resistance (Rin),
Membrane Time Constant (Tau), Sag Ratio, and Capacitance analysis.

All registry wrapper functions return the standard namespaced schema::

    {
        "module_used": "passive_properties",
        "metrics": { ... flat result keys ... }
    }
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import linregress

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.results import RinResult, RmpResult

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers / internal constants
# ---------------------------------------------------------------------------


def _sag_nan_payload() -> Dict[str, float]:
    """Return sag fields as NaN when windows yield no samples (invalid user times)."""
    nan = float(np.nan)
    return {
        "sag_ratio": nan,
        "sag_percentage": nan,
        "v_peak": nan,
        "v_ss": nan,
        "v_baseline": nan,
        "rebound_depolarization": nan,
    }


def _exp_growth(t, V_ss, V_0, tau):
    """Mono-exponential growth/decay function for fitting."""
    return V_ss + (V_0 - V_ss) * np.exp(-t / tau)


def _bi_exp_growth(t, V_ss, A_fast, tau_fast, A_slow, tau_slow):
    """Bi-exponential growth/decay function."""
    return V_ss + A_fast * np.exp(-t / tau_fast) + A_slow * np.exp(-t / tau_slow)


# ---------------------------------------------------------------------------
# RMP
# ---------------------------------------------------------------------------


def calculate_rmp(data: np.ndarray, time: np.ndarray, baseline_window: Tuple[float, float]) -> RmpResult:  # noqa: C901
    """
    Calculate the Resting Membrane Potential (RMP) from a defined baseline window.

    Args:
        data: 1D NumPy array of voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        baseline_window: Tuple (start_time, end_time) defining the baseline period.

    Returns:
        RmpResult object.
    """
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size == 0:
        log.warning("calculate_rmp: Invalid data array provided.")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Invalid data array")
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        log.warning("calculate_rmp: Time and data array shapes mismatch.")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Time and data mismatch")
    if not isinstance(baseline_window, tuple) or len(baseline_window) != 2:
        log.warning("calculate_rmp: baseline_window must be a tuple of (start, end).")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Invalid baseline window format")

    start_t, end_t = baseline_window
    if not (isinstance(start_t, (int, float)) and isinstance(end_t, (int, float))):
        log.warning("calculate_rmp: baseline_window times must be numeric.")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Non-numeric window times")
    if start_t >= end_t:
        log.warning(f"calculate_rmp: Baseline start time ({start_t}) >= end time ({end_t}).")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message="Start time >= End time")

    try:
        start_idx = np.searchsorted(time, start_t, side="left")
        end_idx = np.searchsorted(time, end_t, side="right")

        if start_idx >= end_idx:
            log.warning(f"calculate_rmp: No data points found in baseline window {baseline_window}s.")
            return RmpResult(value=float(np.nan), unit="mV", is_valid=False, error_message="No data in window")

        baseline_data = data[start_idx:end_idx]
        if baseline_data.size == 0:
            return RmpResult(value=float(np.nan), unit="mV", is_valid=False, error_message="Empty data slice")

        rmp = np.mean(baseline_data)
        std_dev = np.std(baseline_data)
        duration = end_t - start_t

        try:
            window_time = time[start_idx:end_idx] - time[start_idx]
            slope, _ = np.polyfit(window_time, baseline_data, 1)
        except (ValueError, TypeError, np.linalg.LinAlgError):
            slope = None

        log.debug(f"Calculated RMP = {rmp:.3f} over {baseline_data.size} points.")
        return RmpResult(
            value=float(rmp),
            unit="mV",
            std_dev=float(std_dev),
            drift=float(slope) if slope is not None else None,
            duration=duration,
        )
    except IndexError as e:
        log.error(f"calculate_rmp: Indexing error: {e}")
        return RmpResult(value=None, unit="mV", is_valid=False, error_message=str(e))
    except (ValueError, TypeError, RuntimeError) as e:
        log.error(f"Error during RMP calculation: {e}", exc_info=True)
        return RmpResult(value=None, unit="mV", is_valid=False, error_message=str(e))


def calculate_baseline_stats(
    time: np.ndarray, voltage: np.ndarray, start_time: float, end_time: float
) -> Optional[Tuple[float, float]]:
    """Return (mean, std_dev) for a baseline window or None."""
    result = calculate_rmp(voltage, time, (start_time, end_time))
    if result.is_valid and result.value is not None:
        return (result.value, result.std_dev if result.std_dev is not None else 0.0)
    return None


def find_stable_baseline(
    data: np.ndarray, sample_rate: float, window_duration_s: float = 0.5, step_duration_s: float = 0.1
) -> Tuple[Optional[float], Optional[float], Optional[Tuple[float, float]]]:
    """Find the most stable (lowest variance) baseline segment by sliding window."""
    if len(data) == 0:
        return None, None, None

    n_points = len(data)
    window_samples = int(window_duration_s * sample_rate)
    step_samples = int(step_duration_s * sample_rate)

    window_samples = max(2, window_samples)
    step_samples = max(1, step_samples)

    if window_samples >= n_points:
        segment_data = data
        return float(np.mean(segment_data)), float(np.std(segment_data)), (0.0, n_points / sample_rate)

    min_variance = np.inf
    best_start_idx = None
    best_mean = None
    best_sd = None

    for i in range(0, n_points - window_samples + 1, step_samples):
        segment = data[i : i + window_samples]
        variance = np.var(segment)
        if variance < min_variance:
            min_variance = variance
            best_start_idx = i
            best_mean = np.mean(segment)
            best_sd = np.sqrt(variance)

    if best_start_idx is None:
        return None, None, None

    start_time = best_start_idx / sample_rate
    end_time = (best_start_idx + window_samples) / sample_rate
    return best_mean, best_sd, (start_time, end_time)


# ---------------------------------------------------------------------------
# Input Resistance (Rin) / Conductance
# ---------------------------------------------------------------------------


def calculate_rin(
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    current_amplitude: float,
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float],
    parameters: Dict[str, Any] = None,
) -> RinResult:
    """
    Calculate Input Resistance (Rin = delta_V / delta_I).

    Args:
        voltage_trace: 1D voltage array (mV).
        time_vector: 1D time array (s).
        current_amplitude: Current step amplitude (pA).
        baseline_window: (start, end) seconds for baseline.
        response_window: (start, end) seconds for response.
        parameters: Optional parameter dict stored in result.

    Returns:
        RinResult object.
    """
    try:
        delta_i_pa = float(current_amplitude)
    except (TypeError, ValueError):
        log.warning("Cannot calculate Rin: Invalid current amplitude.")
        return RinResult(
            value=float(np.nan),
            unit="MOhm",
            is_valid=False,
            error_message="Invalid current amplitude",
            parameters=parameters or {},
        )

    if delta_i_pa == 0.0:
        log.warning("Cannot calculate Rin: Current amplitude is zero.")
        return RinResult(value=float(np.nan), unit="MOhm", is_valid=False, error_message="Current amplitude is zero")

    try:
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        response_mask = (time_vector >= response_window[0]) & (time_vector < response_window[1])

        baseline_slice = voltage_trace[baseline_mask]
        response_slice = voltage_trace[response_mask]
        if baseline_slice.size == 0 or response_slice.size == 0:
            return RinResult(
                value=float(np.nan),
                unit="MOhm",
                is_valid=False,
                error_message="No data in windows",
                parameters=parameters or {},
            )

        baseline_voltage = np.mean(baseline_slice)
        response_voltage = np.mean(response_slice)
        delta_v = response_voltage - baseline_voltage

        delta_i_nA = abs(delta_i_pa) / 1000.0
        if delta_i_nA == 0.0:
            return RinResult(
                value=float(np.nan),
                unit="MOhm",
                is_valid=False,
                error_message="Current amplitude effectively zero",
                parameters=parameters or {},
            )

        rin = abs(delta_v) / delta_i_nA
        conductance_us = 1.0 / rin if rin != 0 else 0.0

        log.debug(f"Calculated Rin: dV={delta_v:.3f}, dI={delta_i_pa:.3f}, Rin={rin:.3f}")
        return RinResult(
            value=rin,
            unit="MOhm",
            conductance=conductance_us,
            voltage_deflection=delta_v,
            current_injection=delta_i_pa,
            baseline_voltage=baseline_voltage,
            steady_state_voltage=response_voltage,
            parameters=parameters or {},
        )
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception(f"Unexpected error during Rin calculation: {e}")
        return RinResult(value=None, unit="MOhm", is_valid=False, error_message=str(e), parameters=parameters or {})


def calculate_conductance(
    current_trace: np.ndarray,
    time_vector: np.ndarray,
    voltage_step: float,
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float],
    parameters: Dict[str, Any] = None,
) -> RinResult:
    """Calculate Conductance (G = delta_I / delta_V) from a voltage-clamp current trace."""
    if voltage_step == 0:
        return RinResult(
            value=None,
            unit="MOhm",
            is_valid=False,
            error_message="Voltage step is zero",
            parameters=parameters or {},
        )
    try:
        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        response_mask = (time_vector >= response_window[0]) & (time_vector < response_window[1])

        baseline_slice = current_trace[baseline_mask]
        response_slice = current_trace[response_mask]
        if baseline_slice.size == 0 or response_slice.size == 0:
            return RinResult(
                value=float(np.nan),
                unit="MOhm",
                is_valid=False,
                error_message="No data in windows",
                parameters=parameters or {},
            )

        baseline_current = np.mean(baseline_slice)
        response_current = np.mean(response_slice)
        delta_i = response_current - baseline_current  # pA

        conductance_ns = delta_i / voltage_step
        conductance_us = conductance_ns / 1000.0
        rin_megaohms = 1.0 / conductance_us if conductance_us != 0 else float("inf")

        return RinResult(
            value=rin_megaohms,
            unit="MOhm",
            conductance=conductance_us,
            voltage_deflection=voltage_step,
            current_injection=delta_i,
            baseline_voltage=None,
            steady_state_voltage=None,
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
    """Calculate the I-V relationship across multiple sweeps."""
    num_sweeps = len(sweeps)
    if num_sweeps == 0:
        return {"error": "No sweeps provided"}

    if len(current_steps) != num_sweeps:
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

    valid_indices = [i for i, dv in enumerate(delta_vs) if not np.isnan(dv)]
    valid_currents = [current_steps[i] for i in valid_indices]
    valid_delta_vs = [delta_vs[i] for i in valid_indices]

    rin_mohm = None
    r_squared = None
    iv_intercept = None

    if len(valid_currents) >= 2:
        try:
            currents_na = np.array(valid_currents) / 1000.0
            slope, intercept, r_value, p_value, std_err = linregress(currents_na, valid_delta_vs)
            rin_mohm = slope
            iv_intercept = intercept
            r_squared = r_value**2
        except Exception as e:
            log.warning(f"Linear regression failed during I-V curve calculation: {e}", exc_info=True)

    return {
        "rin_aggregate_mohm": rin_mohm,
        "iv_intercept": iv_intercept,
        "iv_r_squared": r_squared,
        "baseline_voltages": baseline_voltages,
        "steady_state_voltages": steady_state_voltages,
        "delta_vs": delta_vs,
        "current_steps": current_steps,
    }


# ---------------------------------------------------------------------------
# Tau (membrane time constant)
# ---------------------------------------------------------------------------


def calculate_tau(  # noqa: C901
    voltage_trace: np.ndarray,
    time_vector: np.ndarray,
    stim_start_time: float,
    fit_duration: float,
    model: str = "mono",
    tau_bounds: Optional[Tuple[float, float]] = None,
    artifact_blanking_ms: float = 0.5,
) -> Optional[Union[float, Dict[str, float]]]:
    """
    Calculate Membrane Time Constant (Tau) by fitting an exponential.

    Args:
        voltage_trace: 1D voltage array (mV).
        time_vector: 1D time array (s).
        stim_start_time: Stimulus onset time (s).
        fit_duration: Duration of fit window (s).
        model: 'mono' or 'bi'.
        tau_bounds: (min_tau, max_tau) in seconds. Defaults to (1e-4, 1.0).
        artifact_blanking_ms: Time to skip after stimulus onset (ms).

    Returns:
        For model='mono': dict with tau_ms, fit_time, fit_values.
        For model='bi': dict with tau_fast_ms, tau_slow_ms, amplitude_fast,
        amplitude_slow, V_ss, fit_time, fit_values.
        None if fitting fails fatally.
    """
    if tau_bounds is None:
        tau_bounds = (1e-4, 1.0)
    tau_min, tau_max = tau_bounds

    try:
        fit_start_time = stim_start_time + (artifact_blanking_ms / 1000.0)
        fit_end_time = stim_start_time + fit_duration

        fit_mask = (time_vector >= fit_start_time) & (time_vector < fit_end_time)
        t_fit = time_vector[fit_mask] - fit_start_time
        V_fit = voltage_trace[fit_mask]

        if len(t_fit) < 3:
            log.warning("Not enough data points to fit for Tau.")
            return None

        V_0 = V_fit[0]
        V_ss_guess = np.mean(V_fit[-5:])

        if model == "mono":
            lower_bounds = [-np.inf, -np.inf, tau_min]
            upper_bounds = [np.inf, np.inf, tau_max]
            p0 = [V_ss_guess, V_0, 0.01]

            try:
                popt, _ = curve_fit(_exp_growth, t_fit, V_fit, p0=p0, bounds=(lower_bounds, upper_bounds), maxfev=5000)
            except RuntimeError:
                log.warning("Optimal parameters not found for Tau (mono exponential fit).")
                return {"tau_ms": float(np.nan), "fit_time": [], "fit_values": []}

            tau_ms = popt[2] * 1000
            fit_values = _exp_growth(t_fit, *popt)
            fit_time = (t_fit + fit_start_time).tolist()
            log.debug("Calculated Tau (mono): %.3f ms", tau_ms)
            return {"tau_ms": tau_ms, "fit_time": fit_time, "fit_values": fit_values.tolist()}

        elif model == "bi":
            if len(t_fit) < 6:
                log.warning("Not enough data for bi-exponential fit (need >= 6).")
                return None

            A_fast_guess = 0.6 * (V_0 - V_ss_guess)
            A_slow_guess = 0.4 * (V_0 - V_ss_guess)
            tau_fast_guess = min(0.005, tau_max * 0.1)
            tau_slow_guess = min(0.05, tau_max * 0.5)
            p0 = [V_ss_guess, A_fast_guess, tau_fast_guess, A_slow_guess, tau_slow_guess]
            lower_bounds = [-np.inf, -np.inf, tau_min, -np.inf, tau_min]
            upper_bounds = [np.inf, np.inf, tau_max, np.inf, tau_max]

            try:
                popt, _ = curve_fit(
                    _bi_exp_growth, t_fit, V_fit, p0=p0, bounds=(lower_bounds, upper_bounds), maxfev=10000
                )
            except RuntimeError:
                log.warning("Optimal parameters not found for Tau (bi-exponential fit).")
                nan = float(np.nan)
                return {
                    "tau_fast_ms": nan,
                    "tau_slow_ms": nan,
                    "amplitude_fast": nan,
                    "amplitude_slow": nan,
                    "V_ss": nan,
                    "fit_time": [],
                    "fit_values": [],
                }

            V_ss_fit, A_fast, tau_fast, A_slow, tau_slow = popt
            if tau_fast > tau_slow:
                tau_fast, tau_slow = tau_slow, tau_fast
                A_fast, A_slow = A_slow, A_fast

            fit_values = _bi_exp_growth(t_fit, *popt)
            fit_time = (t_fit + fit_start_time).tolist()
            result = {
                "tau_fast_ms": tau_fast * 1000,
                "tau_slow_ms": tau_slow * 1000,
                "amplitude_fast": A_fast,
                "amplitude_slow": A_slow,
                "V_ss": V_ss_fit,
                "fit_time": fit_time,
                "fit_values": fit_values.tolist(),
            }
            log.debug(
                "Calculated Tau (bi): fast=%.3f ms, slow=%.3f ms",
                result["tau_fast_ms"],
                result["tau_slow_ms"],
            )
            return result
        else:
            log.error("Unknown model '%s'. Use 'mono' or 'bi'.", model)
            return None

    except RuntimeError:
        log.warning("Optimal parameters not found for Tau (model=%s).", model)
        return None
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.exception("Unexpected error during Tau calculation: %s", e)
        return None


# ---------------------------------------------------------------------------
# Sag Ratio
# ---------------------------------------------------------------------------


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

    Returns dict with keys sag_ratio, sag_percentage, v_peak, v_ss,
    v_baseline, rebound_depolarization.
    """
    try:
        dt = time_vector[1] - time_vector[0] if len(time_vector) > 1 else 1.0

        baseline_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        baseline_slice = voltage_trace[baseline_mask]
        if baseline_slice.size == 0:
            return _sag_nan_payload()
        v_baseline = float(np.mean(baseline_slice))

        peak_mask = (time_vector >= response_peak_window[0]) & (time_vector < response_peak_window[1])
        peak_data = voltage_trace[peak_mask]
        if peak_data.size == 0:
            return _sag_nan_payload()

        from scipy.signal import savgol_filter

        window_length = max(5, int((peak_smoothing_ms / 1000.0) / dt))
        if window_length % 2 == 0:
            window_length += 1

        if len(peak_data) >= window_length:
            smoothed_peak = savgol_filter(peak_data, window_length, 3)
            v_peak = float(np.min(smoothed_peak))
        else:
            v_peak = float(np.min(peak_data))

        ss_mask = (time_vector >= response_steady_state_window[0]) & (time_vector < response_steady_state_window[1])
        ss_slice = voltage_trace[ss_mask]
        if ss_slice.size == 0:
            return _sag_nan_payload()
        v_ss = float(np.mean(ss_slice))

        delta_v_peak = v_peak - v_baseline
        delta_v_ss = v_ss - v_baseline

        if delta_v_ss == 0:
            return _sag_nan_payload()

        sag_ratio = float(delta_v_peak / delta_v_ss)
        sag_percentage = 0.0 if delta_v_peak == 0 else float(100.0 * (v_peak - v_ss) / delta_v_peak)

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
        return _sag_nan_payload()


# ---------------------------------------------------------------------------
# Capacitance
# ---------------------------------------------------------------------------


def calculate_capacitance_cc(tau_ms: float, rin_mohm: float) -> Optional[float]:
    """
    Calculate Cell Capacitance (Cm) from Current-Clamp data.

    Cm = tau / Rin  (tau in ms, Rin in MOhm -> Cm in pF)
    """
    if rin_mohm <= 0 or not np.isfinite(rin_mohm) or tau_ms <= 0:
        return None
    cm_nf = tau_ms / rin_mohm
    return cm_nf * 1000.0


def calculate_capacitance_vc(
    current_trace: np.ndarray,
    time_vector: np.ndarray,
    baseline_window: Tuple[float, float],
    transient_window: Tuple[float, float],
    voltage_step_amplitude_mv: float,
) -> Optional[float]:
    """
    Calculate Cell Capacitance (Cm) from Voltage-Clamp using the area under
    the capacitive transient (Cm = Q / delta_V).

    Returns Cm in pF, or None on failure.
    """
    from scipy import integrate

    if voltage_step_amplitude_mv == 0:
        return None
    try:
        base_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        if not np.any(base_mask):
            return None
        trans_mask = (time_vector >= transient_window[0]) & (time_vector < transient_window[1])
        if not np.any(trans_mask):
            return None

        t_trans = time_vector[trans_mask]
        i_trans = current_trace[trans_mask]

        end_idx = len(i_trans)
        ss_start_idx = int(end_idx * 0.8)
        if ss_start_idx >= end_idx:
            ss_start_idx = end_idx - 1
        i_steadystate = np.mean(i_trans[ss_start_idx:])

        delta_i = i_trans - i_steadystate
        Q_pc = integrate.trapezoid(delta_i, t_trans)
        cm_nf = Q_pc / voltage_step_amplitude_mv
        cm_pf = abs(cm_nf * 1000.0)
        return float(cm_pf)
    except Exception as e:
        log.error(f"Error calculating VC capacitance: {e}")
        return None


# ---------------------------------------------------------------------------
# Registry Wrappers
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    "rmp_analysis",
    label="Baseline (RMP)",
    ui_params=[
        {
            "name": "baseline_start",
            "label": "Start Time (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "baseline_end",
            "label": "End Time (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {"name": "auto_detect", "label": "Auto-Detect Stable Segment", "type": "bool", "default": False},
        {
            "name": "window_duration",
            "label": "Auto Window (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "step_duration",
            "label": "Step Duration (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.001,
            "max": 1e9,
            "decimals": 4,
        },
    ],
    plots=[
        {"type": "interactive_region", "data": ["baseline_start", "baseline_end"], "color": "g"},
        {"type": "hlines", "data": ["rmp_mv"], "color": "r", "styles": ["solid"]},
        {"type": "hlines", "data": ["rmp_mv_plus_sd", "rmp_mv_minus_sd"], "color": "r", "styles": ["dash", "dash"]},
    ],
)
def run_rmp_analysis_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """Wrapper for RMP analysis. Returns namespaced schema."""
    try:
        baseline_start = kwargs.get("baseline_start", 0.0)
        baseline_end = kwargs.get("baseline_end", 0.1)
        auto_detect = kwargs.get("auto_detect", False)

        if auto_detect:
            window_duration = kwargs.get("window_duration", 0.5)
            step_duration = kwargs.get("step_duration", 0.1)
            mean, sd, window = find_stable_baseline(
                data, sampling_rate, window_duration_s=window_duration, step_duration_s=step_duration
            )
            if window:
                baseline_start, baseline_end = window
            else:
                baseline_start = time[0] if len(time) > 0 else 0.0
                baseline_end = time[-1] if len(time) > 0 else 0.1

        if len(time) > 0:
            baseline_end = min(baseline_end, time[-1])
            baseline_start = max(baseline_start, time[0])

        result = calculate_rmp(data, time, (baseline_start, baseline_end))

        if result.is_valid and result.value is not None:
            sd = result.std_dev if result.std_dev is not None else 0.0
            metrics = {
                "rmp_mv": result.value,
                "rmp_std": sd,
                "rmp_drift": result.drift if result.drift is not None else 0.0,
                "rmp_duration": result.duration if result.duration is not None else 0.0,
                "rmp_mv_plus_sd": result.value + sd,
                "rmp_mv_minus_sd": result.value - sd,
            }
        else:
            metrics = {"rmp_mv": None, "rmp_std": None, "rmp_error": result.error_message or "Unknown error"}

        return {"module_used": "passive_properties", "metrics": metrics}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_rmp_analysis_wrapper: {e}", exc_info=True)
        return {"module_used": "passive_properties", "metrics": {"rmp_mv": None, "rmp_error": str(e)}}


@AnalysisRegistry.register(
    "sag_ratio_analysis",
    label="Sag Ratio (Ih)",
    plots=[
        {"name": "Trace", "type": "trace"},
        {
            "type": "result_hlines",
            "keys": ["v_baseline", "v_peak", "v_ss"],
            "colors": {"v_baseline": "b", "v_peak": "m", "v_ss": "r"},
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
        {
            "name": "show_sag",
            "label": "Show Sag Analysis",
            "type": "bool",
            "default": True,
            "visible_when": {"param": "show_sag", "value": True},
        },
    ],
)
def run_sag_ratio_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """Wrapper for Sag Ratio analysis. Returns namespaced schema."""
    try:
        result = calculate_sag_ratio(
            voltage_trace=data,
            time_vector=time,
            baseline_window=(kwargs.get("baseline_start", 0.0), kwargs.get("baseline_end", 0.1)),
            response_peak_window=(kwargs.get("peak_window_start", 0.1), kwargs.get("peak_window_end", 0.3)),
            response_steady_state_window=(kwargs.get("ss_window_start", 0.8), kwargs.get("ss_window_end", 1.0)),
            peak_smoothing_ms=kwargs.get("peak_smoothing_ms", 5.0),
            rebound_window_ms=kwargs.get("rebound_window_ms", 100.0),
        )

        if result is not None:
            metrics = dict(result)
            sr = metrics.get("sag_ratio")
            if isinstance(sr, (float, np.floating)) and np.isnan(sr):
                metrics.setdefault("sag_error", "Invalid windows or insufficient data")
        else:
            metrics = {"sag_ratio": None, "sag_error": "Sag ratio calculation failed (check windows)"}

        return {"module_used": "passive_properties", "metrics": metrics}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_sag_ratio_wrapper: {e}", exc_info=True)
        return {"module_used": "passive_properties", "metrics": {"sag_ratio": None, "sag_error": str(e)}}


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
def run_rin_analysis_wrapper(  # noqa: C901
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for Input Resistance analysis. Returns namespaced schema."""
    try:
        current_amplitude = kwargs.get("current_amplitude", 0.0)
        auto_detect_pulse = kwargs.get("auto_detect_pulse", True)
        baseline_start = kwargs.get("baseline_start", 0.0)
        baseline_end = kwargs.get("baseline_end", 0.1)
        response_start = kwargs.get("response_start", 0.3)
        response_end = kwargs.get("response_end", 0.4)
        voltage_step = kwargs.get("voltage_step", 0.0)

        if current_amplitude == 0 and voltage_step == 0:
            return {
                "module_used": "passive_properties",
                "metrics": {
                    "rin_mohm": None,
                    "conductance_us": None,
                    "rin_error": "Current amplitude and Voltage step are zero",
                },
            }

        is_voltage_clamp = current_amplitude == 0 and voltage_step != 0

        if auto_detect_pulse:
            window_size = int(0.001 * sampling_rate)
            if window_size > 1:
                kernel = np.ones(window_size) / window_size
                smoothed_data = np.convolve(data, kernel, mode="same")
            else:
                smoothed_data = data

            dv = np.diff(smoothed_data)
            is_negative_step = (current_amplitude < 0) or (current_amplitude == 0 and voltage_step < 0)

            if is_negative_step:
                start_idx = np.argmin(dv)
                end_idx = start_idx + np.argmax(dv[start_idx:])
            else:
                start_idx = np.argmax(dv)
                end_idx = start_idx + np.argmin(dv[start_idx:])

            auto_start_time = time[start_idx]
            auto_end_time = time[end_idx]
            auto_baseline_end = auto_start_time - 0.005
            auto_baseline_start = max(time[0], auto_baseline_end - 0.1)
            auto_response_end = auto_end_time - 0.005
            auto_response_start = max(auto_start_time, auto_response_end - 0.1)

            bl_mask = (time >= auto_baseline_start) & (time < auto_baseline_end)
            resp_mask = (time >= auto_response_start) & (time < auto_response_end)
            if np.sum(bl_mask) >= 2 and np.sum(resp_mask) >= 2:
                baseline_start = auto_baseline_start
                baseline_end = auto_baseline_end
                response_start = auto_response_start
                response_end = auto_response_end

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
            metrics = {
                "rin_mohm": result.value,
                "conductance_us": result.conductance if result.conductance is not None else 0.0,
                "voltage_deflection_mv": result.voltage_deflection if result.voltage_deflection is not None else 0.0,
                "current_injection_pa": result.current_injection if result.current_injection is not None else 0.0,
                "baseline_voltage_mv": result.baseline_voltage if result.baseline_voltage is not None else 0.0,
                "steady_state_voltage_mv": (
                    result.steady_state_voltage if result.steady_state_voltage is not None else 0.0
                ),
                "auto_detected": auto_detect_pulse,
                "_used_baseline_start": baseline_start,
                "_used_baseline_end": baseline_end,
                "_used_response_start": response_start,
                "_used_response_end": response_end,
            }
        else:
            metrics = {
                "rin_mohm": None,
                "conductance_us": None,
                "rin_error": result.error_message or "Unknown error",
            }

        return {"module_used": "passive_properties", "metrics": metrics}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_rin_analysis_wrapper: {e}", exc_info=True)
        return {
            "module_used": "passive_properties",
            "metrics": {"rin_mohm": None, "conductance_us": None, "rin_error": str(e)},
        }


@AnalysisRegistry.register(
    "tau_analysis",
    label="Tau (Time Constant)",
    plots=[
        {"name": "Trace", "type": "trace"},
        {"type": "overlay_fit", "x": "fit_time", "y": "fit_values", "color": "r", "width": 2, "label": "Exp Fit"},
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
        {"name": "tau_model", "label": "Model:", "type": "choice", "default": "mono", "options": ["mono", "bi"]},
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
    """Wrapper for Tau analysis. Returns namespaced schema."""
    try:
        stim_start_time = kwargs.get("stim_start_time", 0.1)
        fit_duration = kwargs.get("fit_duration", 0.05)
        model = kwargs.get("tau_model", "mono")
        tau_bounds = (kwargs.get("tau_bound_min", 0.0001), kwargs.get("tau_bound_max", 1.0))
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

        def _with_tau_fit_error(out: Dict[str, Any]) -> Dict[str, Any]:
            if model == "bi":
                tf = out.get("tau_fast_ms")
                if isinstance(tf, (float, np.floating)) and np.isnan(tf):
                    out["tau_error"] = "Fit failed"
            else:
                tm = out.get("tau_ms")
                if isinstance(tm, (float, np.floating)) and np.isnan(tm):
                    out["tau_error"] = "Fit failed"
            return out

        if result is not None:
            if model == "bi" and isinstance(result, dict) and "tau_fast_ms" in result:
                metrics = _with_tau_fit_error(
                    {
                        "tau_fast_ms": result["tau_fast_ms"],
                        "tau_slow_ms": result["tau_slow_ms"],
                        "amplitude_fast": result["amplitude_fast"],
                        "amplitude_slow": result["amplitude_slow"],
                        "tau_model": model,
                        "parameters": params,
                        "fit_time": result.get("fit_time", []),
                        "fit_values": result.get("fit_values", []),
                    }
                )
            elif isinstance(result, dict) and "tau_ms" in result:
                metrics = _with_tau_fit_error(
                    {
                        "tau_ms": result["tau_ms"],
                        "tau_model": model,
                        "parameters": params,
                        "fit_time": result.get("fit_time", []),
                        "fit_values": result.get("fit_values", []),
                    }
                )
            else:
                metrics = {
                    "tau_ms": result if isinstance(result, (int, float)) else None,
                    "tau_model": model,
                    "parameters": params,
                }
        else:
            metrics = {"tau_ms": None, "tau_error": "Tau calculation failed", "parameters": params}

        return {"module_used": "passive_properties", "metrics": metrics}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_tau_analysis_wrapper: {e}", exc_info=True)
        return {"module_used": "passive_properties", "metrics": {"tau_ms": None, "tau_error": str(e)}}


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
    """Wrapper for multi-trial I-V Curve analysis. Returns namespaced schema."""
    try:
        start_current = kwargs.get("start_current", -50.0)
        step_current = kwargs.get("step_current", 10.0)
        baseline_window = (kwargs.get("baseline_start", 0.0), kwargs.get("baseline_end", 0.1))
        response_window = (kwargs.get("response_start", 0.3), kwargs.get("response_end", 0.4))

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

        results = calculate_iv_curve(
            sweeps=data_list,
            time_vectors=time_list,
            current_steps=current_steps,
            baseline_window=baseline_window,
            response_window=response_window,
        )

        if "error" in results:
            return {"module_used": "passive_properties", "metrics": {"iv_curve_error": results["error"]}}

        metrics = {
            "rin_aggregate_mohm": results["rin_aggregate_mohm"],
            "iv_intercept": results["iv_intercept"],
            "iv_r_squared": results["iv_r_squared"],
            "baseline_voltages": results["baseline_voltages"],
            "steady_state_voltages": results["steady_state_voltages"],
            "delta_vs": results["delta_vs"],
            "current_steps": results["current_steps"],
        }
        return {"module_used": "passive_properties", "metrics": metrics}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_iv_curve_wrapper: {e}", exc_info=True)
        return {"module_used": "passive_properties", "metrics": {"iv_curve_error": str(e)}}


@AnalysisRegistry.register(
    "capacitance_analysis",
    label="Capacitance",
    ui_params=[
        {
            "name": "mode",
            "label": "Mode:",
            "type": "choice",
            "options": ["Current-Clamp", "Voltage-Clamp"],
            "default": "Current-Clamp",
        },
        {
            "name": "current_amplitude_pa",
            "label": "CC Step (pA):",
            "type": "float",
            "default": -100.0,
            "min": -10000.0,
            "max": 10000.0,
            "decimals": 1,
            "visible_when": {"param": "mode", "value": "Current-Clamp"},
        },
        {
            "name": "voltage_step_mv",
            "label": "VC Step (mV):",
            "type": "float",
            "default": -5.0,
            "min": -200.0,
            "max": 200.0,
            "decimals": 1,
            "visible_when": {"param": "mode", "value": "Voltage-Clamp"},
        },
        {
            "name": "baseline_start_s",
            "label": "Baseline Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 100.0,
            "decimals": 4,
        },
        {
            "name": "baseline_end_s",
            "label": "Baseline End (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 100.0,
            "decimals": 4,
        },
        {
            "name": "response_start_s",
            "label": "Response Start (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 100.0,
            "decimals": 4,
        },
        {
            "name": "response_end_s",
            "label": "Response End (s):",
            "type": "float",
            "default": 0.3,
            "min": 0.0,
            "max": 100.0,
            "decimals": 4,
        },
    ],
)
def run_capacitance_analysis_wrapper(
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for Capacitance analysis. Returns namespaced schema."""
    mode = kwargs.get("mode", "Current-Clamp")
    base_window = (kwargs.get("baseline_start_s", 0.0), kwargs.get("baseline_end_s", 0.1))
    resp_window = (kwargs.get("response_start_s", 0.1), kwargs.get("response_end_s", 0.3))

    if mode == "Current-Clamp":
        current_step = kwargs.get("current_amplitude_pa", -100.0)
        rin_result = calculate_rin(data, time, current_step, base_window, resp_window)
        if not rin_result.is_valid:
            return {
                "module_used": "passive_properties",
                "metrics": {"error": f"Rin calculation failed: {rin_result.error_message}"},
            }

        fit_duration = min(0.1, resp_window[1] - resp_window[0])
        tau_result = calculate_tau(data, time, resp_window[0], fit_duration)
        if tau_result is None:
            return {"module_used": "passive_properties", "metrics": {"error": "Tau calculation failed (no fit)."}}

        if isinstance(tau_result, dict):
            tau_ms = tau_result.get("tau_ms", tau_result.get("tau_slow_ms", 0))
        else:
            tau_ms = tau_result

        cm_pf = calculate_capacitance_cc(tau_ms, rin_result.value)
        if cm_pf is None:
            return {"module_used": "passive_properties", "metrics": {"error": "Failed to calculate Cm from Tau/Rin"}}

        return {
            "module_used": "passive_properties",
            "metrics": {"capacitance_pf": cm_pf, "tau_ms": tau_ms, "rin_mohm": rin_result.value, "mode": mode},
        }

    elif mode == "Voltage-Clamp":
        voltage_step = kwargs.get("voltage_step_mv", -5.0)
        cm_pf = calculate_capacitance_vc(data, time, base_window, resp_window, voltage_step)
        if cm_pf is None:
            return {
                "module_used": "passive_properties",
                "metrics": {"error": "Failed to calculate Cm from Voltage-Clamp transient"},
            }
        return {"module_used": "passive_properties", "metrics": {"capacitance_pf": cm_pf, "mode": mode}}
    else:
        return {"module_used": "passive_properties", "metrics": {"error": "Unknown mode"}}


# ---------------------------------------------------------------------------
# Module-level tab aggregator
# ---------------------------------------------------------------------------
@AnalysisRegistry.register(
    "passive_properties",
    label="Passive Properties",
    method_selector={
        "Baseline (RMP)": "rmp_analysis",
        "Input Resistance": "rin_analysis",
        "Tau (Time Constant)": "tau_analysis",
        "Sag Ratio (Ih)": "sag_ratio_analysis",
        "I-V Curve": "iv_curve_analysis",
        "Capacitance": "capacitance_analysis",
    },
    ui_params=[],
    plots=[],
)
def passive_properties_module(**kwargs):
    """Module-level aggregator tab for all passive membrane property analyses."""
    return {}
