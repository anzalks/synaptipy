import logging
import numpy as np
from typing import Dict, Any, Tuple, Optional
from Synaptipy.core.analysis.registry import AnalysisRegistry
from scipy import integrate
from Synaptipy.core.analysis.intrinsic_properties import calculate_rin, calculate_tau

log = logging.getLogger(__name__)


def calculate_capacitance_cc(tau_ms: float, rin_mohm: float) -> Optional[float]:
    """
    Calculate Cell Capacitance (Cm) from Current-Clamp data.
    Cm = Tau / Rin
    Args:
        tau_ms: Membrane time constant in ms.
        rin_mohm: Input resistance in MOhm.
    Returns:
        Capacitance in pF. Returns None if Rin is 0 or invalid.
    """
    if rin_mohm <= 0 or not np.isfinite(rin_mohm) or tau_ms <= 0:
        return None
    # tau (ms) / Rin (MOhm) = C (nF)
    # nF * 1000 = pF
    cm_nf = tau_ms / rin_mohm
    return cm_nf * 1000.0


def calculate_capacitance_vc(
    current_trace: np.ndarray,
    time_vector: np.ndarray,
    baseline_window: Tuple[float, float],
    transient_window: Tuple[float, float],
    voltage_step_amplitude_mv: float
) -> Optional[float]:
    """
    Calculate Cell Capacitance (Cm) from Voltage-Clamp using the
    area under the capacitive transient.
    Cm = Q / Delta_V
    Q = integral(I_transient(t) - I_steady_state) dt

    Args:
        current_trace: Current trace in pA.
        time_vector: Time vector in seconds.
        baseline_window: Tuple (start, end) in seconds before the step.
        transient_window: Tuple (start, end) in seconds spanning the transient and reaching steady state.
        voltage_step_amplitude_mv: The command voltage step amplitude in mV.

    Returns:
        Capacitance in pF. Returns None if inputs are invalid.
    """
    if voltage_step_amplitude_mv == 0:
        return None

    try:
        # 1. Calculate Steady-State baseline (holding current before step)
        base_mask = (time_vector >= baseline_window[0]) & (time_vector < baseline_window[1])
        if not np.any(base_mask):
            return None

        # 2. Extract transient and steady state during the step
        trans_mask = (time_vector >= transient_window[0]) & (time_vector < transient_window[1])
        if not np.any(trans_mask):
            return None

        t_trans = time_vector[trans_mask]
        i_trans = current_trace[trans_mask]

        # Calculate Steady-State during the step.
        # Typically the last 10-20% of the transient window is considered steady-state.
        end_idx = len(i_trans)
        ss_start_idx = int(end_idx * 0.8)
        if ss_start_idx >= end_idx:
            ss_start_idx = end_idx - 1

        i_steadystate = np.mean(i_trans[ss_start_idx:])

        # 3. Integrate area under transient curve (subtracting steady state)
        # We integrate the absolute difference to correctly handle both positive and negative steps
        delta_i = i_trans - i_steadystate

        # Integration via Trapezoidal rule
        # Q in pC (pA * s = pC)
        Q_pc = integrate.trapezoid(delta_i, t_trans)

        # Cm = Q / DeltaV.
        # Q is in pC, DeltaV is in mV.
        # C = pC / mV = (10^-12 C) / (10^-3 V) = 10^-9 F = nF
        # But wait. If step is negative (e.g., -5 mV), Q will be negative.
        # So Cm will be positive.
        cm_nf = Q_pc / voltage_step_amplitude_mv
        cm_pf = abs(cm_nf * 1000.0)  # abs() ensures positive Cm regardless of step polarity

        return float(cm_pf)

    except Exception as e:
        log.error(f"Error calculating VC capacitance: {e}")
        return None


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
        },
        {
            "name": "voltage_step_mv",
            "label": "VC Step (mV):",
            "type": "float",
            "default": -5.0,
            "min": -200.0,
            "max": 200.0,
            "decimals": 1,
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
    mode = kwargs.get("mode", "Current-Clamp")
    base_window = (kwargs.get("baseline_start_s", 0.0), kwargs.get("baseline_end_s", 0.1))
    resp_window = (kwargs.get("response_start_s", 0.1), kwargs.get("response_end_s", 0.3))

    if mode == "Current-Clamp":
        current_step = kwargs.get("current_amplitude_pa", -100.0)
        # Calculate Rin
        rin_result = calculate_rin(data, time, current_step, base_window, resp_window)
        if not rin_result.is_valid:
            return {"error": f"Rin calculation failed: {rin_result.error_message}"}

        fit_duration = min(0.1, resp_window[1] - resp_window[0])
        tau_result = calculate_tau(data, time, resp_window[0], fit_duration)
        if tau_result is None:
            return {"error": "Tau calculation failed (no fit)."}

        if isinstance(tau_result, dict):
            # Mono model returns {tau_ms: ...}, bi returns {tau_slow_ms: ...}
            tau_ms = tau_result.get(
                "tau_ms", tau_result.get("tau_slow_ms", 0)
            )
        else:
            tau_ms = tau_result

        cm_pf = calculate_capacitance_cc(tau_ms, rin_result.value)
        if cm_pf is None:
            return {"error": "Failed to calculate Cm from Tau/Rin"}

        return {
            "capacitance_pf": cm_pf,
            "tau_ms": tau_ms,
            "rin_mohm": rin_result.value,
            "mode": mode
        }

    elif mode == "Voltage-Clamp":
        voltage_step = kwargs.get("voltage_step_mv", -5.0)
        cm_pf = calculate_capacitance_vc(data, time, base_window, resp_window, voltage_step)
        if cm_pf is None:
            return {"error": "Failed to calculate Cm from Voltage-Clamp transient"}
        return {
            "capacitance_pf": cm_pf,
            "mode": mode
        }
    else:
        return {"error": "Unknown mode"}
