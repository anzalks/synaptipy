# src/Synaptipy/core/analysis/synaptic_events.py
# -*- coding: utf-8 -*-
"""
Core Protocol Module 4: Synaptic Events.

Consolidates all synaptic event detection methods (adaptive threshold,
template matching, baseline-peak-kinetics) from event_detection.py into
one self-contained module.

All registry wrapper functions return::

    {
        "module_used": "synaptic_events",
        "metrics": { ... flat result keys ... }
    }

Exports ``detect_minis_threshold`` as a backward-compatibility alias.
"""

import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy import signal
from scipy.optimize import curve_fit
from scipy.stats import median_abs_deviation

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.results import EventDetectionResult
from Synaptipy.core.signal_processor import find_artifact_windows

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quiescent Noise Floor
# ---------------------------------------------------------------------------


def find_quiescent_baseline_rms(
    data: np.ndarray,
    sample_rate: float,
    window_ms: float = 20.0,
) -> Tuple[float, Tuple[int, int]]:
    """
    Identify the quietest (minimum-variance) segment in a trace via a sliding
    window and return its RMS as the noise floor.

    Unlike a fixed pre-trace window (e.g. ``trace[0:50]``), this approach is
    robust to recordings with spontaneous activity at the start: the search
    considers the *entire* trace, selecting the 20 ms chunk with the smallest
    variance regardless of its position.

    Args:
        data: 1D signal array (mV or pA).
        sample_rate: Sampling rate (Hz).
        window_ms: Duration of the sliding window (ms, default 20).

    Returns:
        Tuple of (rms_noise_floor, (start_idx, end_idx)) where the indices
        define the quiescent window used for the RMS calculation.
    """
    n = len(data)
    window_samples = max(2, int(window_ms / 1000.0 * sample_rate))
    step_samples = max(1, window_samples // 2)

    min_var = np.inf
    best_start = 0

    for i in range(0, n - window_samples + 1, step_samples):
        chunk = data[i : i + window_samples]
        var = float(np.var(chunk))
        if var < min_var:
            min_var = var
            best_start = i

    best_end = best_start + window_samples
    quiescent_chunk = data[best_start:best_end]
    rms = float(np.sqrt(np.mean(quiescent_chunk**2)))
    return rms, (best_start, best_end)


# ---------------------------------------------------------------------------
# Dynamic AUC / Charge Integration
# ---------------------------------------------------------------------------


def calculate_event_charge_dynamic(
    data: np.ndarray,
    event_index: int,
    sample_rate: float,
    local_baseline: float,
    polarity: str = "negative",
    max_duration_ms: float = 100.0,
) -> float:
    """
    Integrate event charge (area under curve) with a dynamic boundary.

    The integration ends at whichever comes first:
    - The signal returns to ``local_baseline`` (event complete).
    - A large derivative transient indicates the onset of a subsequent
      summating event (onset detected as |dV/dt| > 3x the noise in the
      early derivative).

    Args:
        data: 1D signal array.
        event_index: Sample index of the event peak.
        sample_rate: Sampling rate (Hz).
        local_baseline: Local baseline voltage/current level.
        polarity: ``"negative"`` or ``"positive"``.
        max_duration_ms: Hard cap on integration window (ms).

    Returns:
        Signed charge (area under curve relative to baseline, in units of
        data * seconds, e.g. mV·s or pA·s).
    """
    dt = 1.0 / sample_rate
    max_samples = max(2, int(max_duration_ms / 1000.0 * sample_rate))
    start = int(event_index)
    end = min(start + max_samples, len(data))

    segment = data[start:end]
    if len(segment) < 2:
        return 0.0

    # Boundary 1: signal returns to local baseline
    if polarity == "negative":
        returned = np.where(segment >= local_baseline)[0]
    else:
        returned = np.where(segment <= local_baseline)[0]
    baseline_return_idx = int(returned[0]) if len(returned) > 0 else len(segment)

    # Boundary 2: onset of subsequent event (derivative transient)
    dvdt_seg = np.diff(segment[:baseline_return_idx]) if baseline_return_idx > 1 else np.array([])
    onset_idx = baseline_return_idx
    if len(dvdt_seg) > 4:
        # Estimate noise from the first quarter of the derivative
        n_noise = max(2, len(dvdt_seg) // 4)
        noise_std = float(np.std(dvdt_seg[:n_noise]))
        if noise_std > 0:
            min_pts = max(1, int(0.001 * sample_rate))  # skip first 1 ms
            if polarity == "negative":
                candidates = np.where(dvdt_seg < -3.0 * noise_std)[0]
            else:
                candidates = np.where(dvdt_seg > 3.0 * noise_std)[0]
            candidates = candidates[candidates >= min_pts]
            if len(candidates) > 0:
                onset_idx = min(baseline_return_idx, int(candidates[0]))

    integration_end = max(1, onset_idx)
    t_seg = np.arange(integration_end) * dt
    trace_slice = segment[:integration_end]
    charge = float(np.trapezoid(trace_slice - local_baseline, t_seg))
    return charge


# ---------------------------------------------------------------------------
# Bi-Exponential Decay Kinetics Fitting
# ---------------------------------------------------------------------------


def fit_biexponential_decay(  # noqa: C901
    data: np.ndarray,
    event_index: int,
    sample_rate: float,
    local_baseline: float,
    polarity: str = "negative",
    fit_window_ms: float = 80.0,
) -> Dict[str, Any]:
    """Fit mono- and bi-exponential decays to a synaptic event.

    Tries a bi-exponential fit first. Falls back to mono-exponential when the
    bi-exp fit does not converge or yields non-physical parameters (negative
    amplitudes or time constants).

    Bi-exponential model (relative to baseline)::

        f(t) = A_fast * exp(-t / tau_fast) + A_slow * exp(-t / tau_slow)

    with A_fast + A_slow normalised by the event peak amplitude at t=0.

    Args:
        data: 1-D signal array.
        event_index: Sample index of the event peak.
        sample_rate: Sampling rate (Hz).
        local_baseline: Local baseline level (same units as data).
        polarity: ``"negative"`` or ``"positive"``.
        fit_window_ms: Maximum duration of the decay segment to fit (ms).

    Returns:
        Dict with keys:

        - ``tau_mono_ms``    – mono-exp time constant (ms)
        - ``tau_fast_ms``    – fast component time constant (ms); ``None`` if
          bi-exp did not converge
        - ``tau_slow_ms``    – slow component time constant (ms); ``None`` if
          bi-exp did not converge
        - ``bi_exp_converged`` – True when bi-exp fit was accepted
        - ``decay_fit_error`` – ``None`` when fit succeeded; error message
          string otherwise
    """
    result: Dict[str, Any] = {
        "tau_mono_ms": None,
        "tau_fast_ms": None,
        "tau_slow_ms": None,
        "bi_exp_converged": False,
        "decay_fit_error": None,
    }

    dt = 1.0 / sample_rate
    max_samples = max(4, int(fit_window_ms / 1000.0 * sample_rate))
    start = int(event_index)
    end = min(start + max_samples, len(data))
    segment = data[start:end]

    if len(segment) < 5:
        result["decay_fit_error"] = "Segment too short"
        return result

    # Build relative amplitude trace (positive, regardless of polarity)
    if polarity == "negative":
        y = local_baseline - segment
    else:
        y = segment - local_baseline

    peak_amp = float(y[0]) if y.size > 0 else 0.0
    if peak_amp <= 0:
        result["decay_fit_error"] = "Non-positive peak amplitude"
        return result

    # Find where signal returns to baseline (positive threshold cross)
    returned = np.where(y <= 0)[0]
    decay_end = int(returned[0]) if len(returned) > 0 else len(y)
    y_fit = y[:decay_end]
    t_fit = np.arange(len(y_fit)) * dt * 1000.0  # ms

    if len(t_fit) < 4:
        result["decay_fit_error"] = "Decay segment too short after baseline crossing"
        return result

    # --- Mono-exponential fit ---
    def mono_exp(t: np.ndarray, a: float, tau: float) -> np.ndarray:
        return a * np.exp(-t / tau)

    tau_mono_ms = None
    try:
        p0_mono = [peak_amp, max(0.1, t_fit[-1] / 3.0)]
        bounds_mono = ([0.0, 0.01], [peak_amp * 10, t_fit[-1] * 20 + 1.0])
        popt_m, _ = curve_fit(mono_exp, t_fit, y_fit, p0=p0_mono, bounds=bounds_mono, maxfev=2000)
        tau_mono_ms = float(popt_m[1])
        result["tau_mono_ms"] = tau_mono_ms
    except Exception as exc_m:
        result["decay_fit_error"] = f"Mono-exp failed: {exc_m}"
        return result

    # --- Bi-exponential fit ---
    def bi_exp(t: np.ndarray, a_f: float, tau_f: float, a_s: float, tau_s: float) -> np.ndarray:
        return a_f * np.exp(-t / tau_f) + a_s * np.exp(-t / tau_s)

    try:
        # Initialise: fast half of mono, slow twice; amplitudes split equally
        p0_bi = [peak_amp * 0.6, tau_mono_ms * 0.4, peak_amp * 0.4, tau_mono_ms * 2.0]
        bounds_bi = (
            [0.0, 0.01, 0.0, 0.01],
            [peak_amp * 5, tau_mono_ms * 5, peak_amp * 5, tau_mono_ms * 50 + 1.0],
        )
        popt_b, _ = curve_fit(bi_exp, t_fit, y_fit, p0=p0_bi, bounds=bounds_bi, maxfev=4000)
        a_f, tau_f, a_s, tau_s = popt_b

        # Sanity: both amplitudes and both taus must be positive and tau_fast < tau_slow
        if a_f > 0 and a_s > 0 and tau_f > 0 and tau_s > 0 and tau_f != tau_s:
            tau_fast = min(tau_f, tau_s)
            tau_slow = max(tau_f, tau_s)
            result["tau_fast_ms"] = float(tau_fast)
            result["tau_slow_ms"] = float(tau_slow)
            result["bi_exp_converged"] = True
    except Exception:
        # Bi-exp failed; mono-exp result is still valid
        pass

    return result


# ---------------------------------------------------------------------------
# 1. Adaptive Threshold Detection
# ---------------------------------------------------------------------------


def compute_local_pre_event_baseline(
    data: np.ndarray,
    event_indices: np.ndarray,
    sample_rate: float,
    pre_event_window_ms: float = 2.0,
    polarity: str = "negative",
) -> np.ndarray:
    """
    Compute a local pre-event baseline voltage for each detected event.

    For summ ating synaptic events that ride on the decay of a previous event,
    the global resting potential is a poor amplitude reference. This function
    searches the `pre_event_window_ms` immediately preceding each event peak
    and returns the local "foot" voltage:

    - Negative polarity: the maximum (most depolarised) voltage in the search
      window - i.e. the point before the hyperpolarising/inward current event
      begins to deflect the trace.
    - Positive polarity: the minimum (most hyperpolarised) voltage.

    Args:
        data: 1D voltage/current array.
        event_indices: Integer indices of detected event peaks.
        sample_rate: Sampling rate in Hz.
        pre_event_window_ms: Duration (ms) of the search window before each
            peak (default 2.0 ms, valid range 1-3 ms recommended).
        polarity: "negative" or "positive".

    Returns:
        1D float array of local baseline values, one per event.
    """
    if len(event_indices) == 0:
        return np.array([], dtype=float)

    search_samples = max(1, int(pre_event_window_ms / 1000.0 * sample_rate))
    local_baselines = np.empty(len(event_indices), dtype=float)

    for k, idx in enumerate(event_indices):
        win_start = max(0, int(idx) - search_samples)
        win_end = max(win_start + 1, int(idx))
        segment = data[win_start:win_end]
        if segment.size == 0:
            local_baselines[k] = float(data[max(0, int(idx))])
        elif polarity == "negative":
            # Foot of a negative event: highest voltage before the downswing.
            local_baselines[k] = float(np.max(segment))
        else:
            # Foot of a positive event: lowest voltage before the upswing.
            local_baselines[k] = float(np.min(segment))

    return local_baselines


# ---------------------------------------------------------------------------
# Paired-Pulse Ratio with Residual Decay Subtraction
# ---------------------------------------------------------------------------


def _fit_p1_decay_residual(
    data: np.ndarray,
    time: np.ndarray,
    peak1_idx: int,
    s2_t: float,
    global_baseline: float,
    sample_rate: float,
) -> Tuple[float, float]:
    """Fit mono-exp decay to P1 tail; return (residual_at_p2, tau_p1_ms)."""
    nan = float("nan")
    max_decay_samples = min(int(0.2 * sample_rate), int((s2_t - time[peak1_idx]) * sample_rate) - 1)
    decay_end_idx = min(peak1_idx + max(4, max_decay_samples), len(data) - 1)

    if decay_end_idx <= peak1_idx + 3:
        return 0.0, nan

    t_decay = time[peak1_idx:decay_end_idx] - time[peak1_idx]
    i_decay = data[peak1_idx:decay_end_idx] - global_baseline

    def _mono_exp_ppr(t, A, tau):
        return A * np.exp(-t / tau)

    tau_guess = float(t_decay[-1] / 3.0) if t_decay[-1] > 0 else 0.01
    p0 = [float(i_decay[0]) if i_decay.size > 0 else 1.0, tau_guess]
    try:
        popt, _ = curve_fit(
            _mono_exp_ppr,
            t_decay,
            i_decay,
            p0=p0,
            bounds=([-np.inf, 1e-4], [np.inf, 2.0]),
            maxfev=2000,
        )
        tau_p1_ms = float(popt[1]) * 1000.0
        t_at_s2 = s2_t - time[peak1_idx]
        residual_at_p2 = float(_mono_exp_ppr(t_at_s2, *popt))
        return residual_at_p2, tau_p1_ms
    except (RuntimeError, ValueError):
        log.debug("PPR: mono-exp decay fit did not converge; using zero residual.")
        return 0.0, nan


def _measure_ppr_peak(
    data: np.ndarray,
    time: np.ndarray,
    onset_s: float,
    baseline: float,
    resp_samples: int,
    polarity: str,
) -> Tuple[float, int]:
    """Return (amplitude, peak_index) relative to *baseline* in a post-onset window."""
    nan = float("nan")
    onset_idx = int(np.searchsorted(time, onset_s, side="left"))
    end_idx = min(onset_idx + resp_samples, len(data))
    if onset_idx >= end_idx:
        return nan, onset_idx
    segment = data[onset_idx:end_idx]
    if polarity == "negative":
        rel_idx = int(np.argmin(segment))
    else:
        rel_idx = int(np.argmax(segment))
    peak_idx = onset_idx + rel_idx
    amp = float(data[peak_idx]) - float(baseline)
    return amp, peak_idx


def calculate_paired_pulse_ratio(
    data: np.ndarray,
    time: np.ndarray,
    stimulus_onsets_s: np.ndarray,
    sample_rate: float,
    response_window_ms: float = 20.0,
    polarity: str = "negative",
) -> Dict[str, Any]:
    """Calculate the Paired-Pulse Ratio (PPR) with residual decay correction.

    A naive amplitude ratio (P2/P1) is contaminated by the unresolved decay
    tail of the first response.  This function:

    1. Fits a mono-exponential decay to the P1 tail.
    2. Evaluates the fitted tail at the P2 onset to obtain the *residual*
       baseline offset.
    3. Measures P2 amplitude relative to the corrected (residual-subtracted)
       baseline instead of the global baseline.

    PPR = A2_corrected / A1

    Parameters
    ----------
    data : np.ndarray
        1-D signal array (pA or mV).
    time : np.ndarray
        1-D time array (seconds), same length as *data*.
    stimulus_onsets_s : np.ndarray
        1-D array of stimulus onset times (seconds).  At least two are required.
    sample_rate : float
        Sampling rate (Hz).
    response_window_ms : float
        Duration (ms) of the post-stimulus window searched for the peak.
    polarity : str
        ``"negative"`` for inward currents/hyperpolarisations;
        ``"positive"`` for depolarisations.

    Returns
    -------
    dict
        Keys:

        - ``ppr``                  – corrected P2/P1 amplitude ratio
        - ``ppr_naive``            – uncorrected P2/P1 ratio (no residual subtraction)
        - ``amplitude_p1``         – P1 amplitude relative to pre-stimulus baseline
        - ``amplitude_p2_corrected`` – P2 amplitude after residual subtraction
        - ``amplitude_p2_naive``   – P2 amplitude relative to global baseline
        - ``residual_at_p2``       – predicted P1 tail amplitude at P2 onset
        - ``tau_p1_ms``            – time constant of the P1 decay fit (ms)
        - ``interpulse_interval_ms`` – interval between S1 and S2 (ms)
        - ``error``                – error message string when calculation fails
    """
    nan = float(np.nan)
    result: Dict[str, Any] = {
        "ppr": nan,
        "ppr_naive": nan,
        "amplitude_p1": nan,
        "amplitude_p2_corrected": nan,
        "amplitude_p2_naive": nan,
        "residual_at_p2": nan,
        "tau_p1_ms": nan,
        "interpulse_interval_ms": nan,
        "error": None,
    }

    if len(stimulus_onsets_s) < 2:
        result["error"] = "Need at least 2 stimulus onsets for PPR."
        return result

    resp_samples = max(2, int(response_window_ms / 1000.0 * sample_rate))

    def _measure_peak(onset_s: float, baseline: float) -> Tuple[float, int]:
        return _measure_ppr_peak(data, time, onset_s, baseline, resp_samples, polarity)

    try:
        s1_t = float(stimulus_onsets_s[0])
        s2_t = float(stimulus_onsets_s[1])
        isi_ms = (s2_t - s1_t) * 1000.0
        result["interpulse_interval_ms"] = isi_ms

        # Pre-S1 baseline (5 ms before S1)
        base_mask = (time >= s1_t - 0.005) & (time < s1_t)
        if not np.any(base_mask):
            result["error"] = "No pre-S1 baseline samples."
            return result
        global_baseline = float(np.mean(data[base_mask]))

        # P1 amplitude
        amp_p1, peak1_idx = _measure_peak(s1_t, global_baseline)
        if np.isnan(amp_p1) or amp_p1 == 0.0:
            result["error"] = "P1 amplitude is zero or NaN."
            return result
        result["amplitude_p1"] = amp_p1

        # Naive P2 amplitude (no correction)
        amp_p2_naive, peak2_idx = _measure_peak(s2_t, global_baseline)
        result["amplitude_p2_naive"] = amp_p2_naive
        if amp_p1 != 0.0:
            result["ppr_naive"] = float(amp_p2_naive / amp_p1)

        # ------------------------------------------------------------------ #
        # Fit mono-exponential decay to P1 tail to predict residual at S2    #
        # ------------------------------------------------------------------ #
        residual_at_p2, tau_p1_ms = _fit_p1_decay_residual(data, time, peak1_idx, s2_t, global_baseline, sample_rate)
        if not np.isnan(tau_p1_ms):
            result["tau_p1_ms"] = tau_p1_ms

        result["residual_at_p2"] = residual_at_p2

        # Corrected P2 amplitude: subtract the predicted residual from the baseline
        corrected_p2_baseline = global_baseline + residual_at_p2
        amp_p2_corrected, _ = _measure_peak(s2_t, corrected_p2_baseline)
        result["amplitude_p2_corrected"] = amp_p2_corrected

        if amp_p1 != 0.0:
            result["ppr"] = float(amp_p2_corrected / amp_p1)

    except (ValueError, TypeError, IndexError) as e:
        result["error"] = str(e)
        log.warning("calculate_paired_pulse_ratio: %s", e)

    return result


def detect_events_threshold(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    threshold: float,
    polarity: str = "negative",
    refractory_period: float = 0.002,
    rolling_baseline_window_ms: Optional[float] = 100.0,
    artifact_mask: Optional[np.ndarray] = None,
    use_quiescent_noise_floor: bool = True,
    quiescent_window_ms: float = 20.0,
) -> EventDetectionResult:
    """
    Detect events using topological prominence to handle shifting baselines.

    By default uses a quiescent-noise-floor estimate: the RMS of the
    minimum-variance 20 ms chunk in the trace is used to set a dynamic
    noise threshold, preventing false positives even when spontaneous
    activity dominates the beginning of the recording.
    """
    if data.size < 2 or time.shape != data.shape:
        return EventDetectionResult(value=0, unit="Hz", is_valid=False, error_message="Invalid data/time shape")

    try:
        fs = 1.0 / (time[1] - time[0]) if len(time) > 1 else 10000.0

        if rolling_baseline_window_ms is not None and rolling_baseline_window_ms > 0:
            from scipy.ndimage import median_filter

            window_samples = int((rolling_baseline_window_ms / 1000.0) * fs)
            if window_samples % 2 == 0:
                window_samples += 1
            if window_samples >= 3:
                baseline = median_filter(data, size=window_samples)
                baseline_corrected_data = data - baseline
            else:
                baseline_corrected_data = data
        else:
            baseline_corrected_data = data

        is_negative = polarity == "negative"
        work_data = -baseline_corrected_data if is_negative else baseline_corrected_data

        if use_quiescent_noise_floor:
            # Dynamic noise floor: RMS of the quietest window in the trace
            quiescent_rms, _ = find_quiescent_baseline_rms(work_data, fs, window_ms=quiescent_window_ms)
            noise_sd = quiescent_rms if quiescent_rms > 0 else 1e-12
        else:
            noise_sd = median_abs_deviation(work_data, scale="normal")
            if noise_sd == 0:
                noise_sd = 1e-12

        abs_threshold = abs(threshold)
        min_prominence = max(abs_threshold, 2.0 * noise_sd)

        distance_samples = max(1, int(refractory_period * fs))
        min_width_samples = max(2, int(0.0002 * fs))

        peaks, _ = signal.find_peaks(
            work_data,
            prominence=min_prominence,
            height=abs_threshold,
            distance=distance_samples,
            width=min_width_samples,
        )

        n_artifacts_rejected = 0
        if artifact_mask is not None and len(peaks) > 0:
            valid_idx_mask = peaks < len(artifact_mask)
            peaks = peaks[valid_idx_mask]
            not_artifact_mask = ~artifact_mask[peaks]
            n_artifacts_rejected = int(np.sum(~not_artifact_mask))
            peaks = peaks[not_artifact_mask]

        event_indices = peaks.astype(int)
        if len(event_indices) > 0:
            event_times = time[event_indices]
            event_amplitudes = baseline_corrected_data[event_indices]
        else:
            event_times = np.array([])
            event_amplitudes = np.array([])

        num_events = len(event_indices)
        duration = time[-1] - time[0] if len(time) > 0 else 0
        frequency = num_events / duration if duration > 0 else 0.0
        mean_amplitude = float(np.mean(event_amplitudes)) if num_events > 0 else 0.0
        std_amplitude = float(np.std(event_amplitudes)) if num_events > 0 else 0.0

        return EventDetectionResult(
            value=frequency,
            unit="Hz",
            is_valid=True,
            event_count=num_events,
            frequency_hz=frequency,
            mean_amplitude=mean_amplitude,
            amplitude_sd=std_amplitude,
            event_indices=event_indices,
            event_times=event_times,
            event_amplitudes=event_amplitudes,
            detection_method="threshold_adaptive_prominence",
            threshold_value=threshold,
            direction=polarity,
            n_artifacts_rejected=n_artifacts_rejected,
            artifact_mask=artifact_mask,
            summary_stats={"noise_sd": float(noise_sd), "min_prominence_used": float(min_prominence)},
        )

    except Exception as e:
        log.error(f"Error during adaptive threshold event detection: {e}", exc_info=True)
        return EventDetectionResult(value=0, unit="Hz", is_valid=False, error_message=str(e))


# Backward compatibility alias
detect_minis_threshold = detect_events_threshold


@AnalysisRegistry.register(
    "event_detection_threshold",
    label="Event Detection (Threshold)",
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
        {"type": "markers", "x": "_event_times", "y": "_event_peaks", "color": "r", "symbol": "o"},
        {"type": "threshold_line", "param": "threshold"},
        {"type": "artifact_overlay"},
    ],
    ui_params=[
        {
            "name": "threshold",
            "label": "Threshold (pA/mV):",
            "type": "float",
            "default": 5.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
        },
        {
            "name": "refractory_period",
            "label": "Refractory (s):",
            "type": "float",
            "default": 0.005,
            "min": 0.0,
            "max": 1.0,
            "decimals": 4,
        },
        {
            "name": "rolling_baseline_window_ms",
            "label": "Rolling Baseline (ms):",
            "type": "float",
            "default": 100.0,
            "min": 0.0,
            "max": 5000.0,
            "decimals": 1,
        },
        {"name": "reject_artifacts", "label": "Reject Artifacts", "type": "bool", "default": False},
        {
            "name": "artifact_slope_threshold",
            "label": "Artifact Slope Thresh:",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
        },
        {"name": "artifact_padding_ms", "label": "Artifact Padding (ms):", "type": "float", "default": 2.0},
        {
            "name": "use_quiescent_noise_floor",
            "label": "Quiescent Noise Floor",
            "type": "bool",
            "default": True,
            "tooltip": "Use minimum-variance sliding window to estimate noise, ignoring bursts at recording start.",
        },
        {
            "name": "quiescent_window_ms",
            "label": "Quiescent Window (ms):",
            "type": "float",
            "default": 20.0,
            "min": 1.0,
            "max": 500.0,
            "decimals": 1,
            "visible_when": {"param": "use_quiescent_noise_floor", "value": True},
        },
    ],
)
def run_event_detection_threshold_wrapper(
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for adaptive threshold event detection."""
    threshold = kwargs.get("threshold", 5.0)
    direction = kwargs.get("direction", "negative")
    refractory_period = kwargs.get("refractory_period", 0.005)
    rolling_baseline_window_ms = kwargs.get("rolling_baseline_window_ms", 100.0)
    use_quiescent_noise_floor = kwargs.get("use_quiescent_noise_floor", True)
    quiescent_window_ms = float(kwargs.get("quiescent_window_ms", 20.0))

    reject_artifacts = kwargs.get("reject_artifacts", False)
    artifact_mask = None
    if reject_artifacts:
        slope_thresh = kwargs.get("artifact_slope_threshold", 20.0)
        padding_ms = kwargs.get("artifact_padding_ms", 2.0)
        artifact_mask = find_artifact_windows(data, sampling_rate, slope_thresh, padding_ms)

    result = detect_events_threshold(
        data,
        time,
        threshold,
        direction,
        refractory_period,
        rolling_baseline_window_ms=rolling_baseline_window_ms,
        artifact_mask=artifact_mask,
        use_quiescent_noise_floor=use_quiescent_noise_floor,
        quiescent_window_ms=quiescent_window_ms,
    )

    if not result.is_valid:
        return {"module_used": "synaptic_events", "metrics": {"event_error": result.error_message}}

    _idx = np.asarray(result.event_indices if result.event_indices is not None else [], dtype=int)

    # Compute local pre-event baseline for each detected event (handles summating events).
    local_baselines = compute_local_pre_event_baseline(data, _idx, sampling_rate, polarity=direction)
    if len(_idx) > 0:
        if direction == "negative":
            local_amplitudes = local_baselines - data[_idx]
        else:
            local_amplitudes = data[_idx] - local_baselines
    else:
        local_amplitudes = np.array([], dtype=float)

    # Dynamic AUC: integrate each event charge with a dynamic boundary
    event_charges = []
    for k, idx in enumerate(_idx):
        lb = float(local_baselines[k]) if k < len(local_baselines) else float(np.mean(data))
        charge = calculate_event_charge_dynamic(data, idx, sampling_rate, lb, polarity=direction)
        event_charges.append(charge)
    mean_charge = float(np.mean(event_charges)) if event_charges else 0.0

    # Bi-exponential decay kinetics (aggregate over all detected events)
    tau_fast_list = []
    tau_slow_list = []
    tau_mono_list = []
    for k, idx in enumerate(_idx):
        lb = float(local_baselines[k]) if k < len(local_baselines) else float(np.mean(data))
        kin = fit_biexponential_decay(data, idx, sampling_rate, lb, polarity=direction)
        if kin["tau_mono_ms"] is not None:
            tau_mono_list.append(kin["tau_mono_ms"])
        if kin["bi_exp_converged"]:
            tau_fast_list.append(kin["tau_fast_ms"])
            tau_slow_list.append(kin["tau_slow_ms"])

    mean_tau_mono = float(np.mean(tau_mono_list)) if tau_mono_list else float("nan")
    mean_tau_fast = float(np.mean(tau_fast_list)) if tau_fast_list else None
    mean_tau_slow = float(np.mean(tau_slow_list)) if tau_slow_list else None

    return {
        "module_used": "synaptic_events",
        "metrics": {
            "event_count": result.event_count,
            "frequency_hz": result.frequency_hz,
            "mean_amplitude": result.mean_amplitude,
            "amplitude_sd": result.amplitude_sd,
            "mean_local_amplitude": float(np.mean(local_amplitudes)) if local_amplitudes.size > 0 else 0.0,
            "mean_event_charge": mean_charge,
            "tau_mono_ms": mean_tau_mono,
            "tau_fast_ms": mean_tau_fast,
            "tau_slow_ms": mean_tau_slow,
            "_event_charges": event_charges,
            "_event_times": time[_idx].tolist() if len(_idx) > 0 else [],
            "_event_peaks": data[_idx].tolist() if len(_idx) > 0 else [],
            "_local_baselines": local_baselines.tolist() if local_baselines.size > 0 else [],
            "_local_amplitudes": local_amplitudes.tolist() if local_amplitudes.size > 0 else [],
            "_result_obj": result,
        },
    }


# ---------------------------------------------------------------------------
# 2. Parametric Template Matching
# ---------------------------------------------------------------------------


def detect_events_template(  # noqa: C901
    data: np.ndarray,
    sampling_rate: float,
    threshold_std: float,
    tau_rise: float,
    tau_decay: float,
    polarity: str = "negative",
    rolling_baseline_window_ms: Optional[float] = 100.0,
    artifact_mask: Optional[np.ndarray] = None,
    time: Optional[np.ndarray] = None,
    min_event_distance_ms: float = 0.0,
) -> EventDetectionResult:
    """Detect events using a multi-kernel matched-filter bank.

    Three kernels are built using the specified tau_rise and tau_decay × 1, 2, 3
    to tolerate dendritic filtering that prolongs event decay (Cable theory
    predicts a ~2-3× slowdown for distal inputs).  A combined z-score trace
    (pointwise maximum across the three filtered traces) is used for peak
    detection, improving sensitivity to both somatic and dendritic events.
    """
    try:
        dt = 1.0 / sampling_rate
        n_points = len(data)

        def _build_kernel(td: float) -> np.ndarray:
            """Alpha/bi-exponential kernel for a given tau_decay."""
            kernel_duration = 5 * max(td, tau_rise)
            t_k = np.arange(0, kernel_duration, dt)
            if td == tau_rise:
                k = t_k * np.exp(-t_k / td)
            else:
                k = np.exp(-t_k / td) - np.exp(-t_k / tau_rise)
            max_abs = np.max(np.abs(k))
            if max_abs > 0:
                k /= max_abs
            return k

        kernels = [_build_kernel(tau_decay * scale) for scale in (1.0, 2.0, 3.0)]

        if rolling_baseline_window_ms is not None and rolling_baseline_window_ms > 0:
            from scipy.ndimage import median_filter

            window_samples = int((rolling_baseline_window_ms / 1000.0) * sampling_rate)
            if window_samples % 2 == 0:
                window_samples += 1
            if window_samples >= 3:
                baseline = median_filter(data, size=window_samples)
                baseline_corrected_data = data - baseline
            else:
                baseline_corrected_data = data
        else:
            baseline_corrected_data = data

        is_negative = polarity == "negative"
        work_data = -baseline_corrected_data if is_negative else baseline_corrected_data

        # Compute filtered traces and z-scores for each kernel.
        # Each kernel's matched-filter peak is shifted from the true event time by
        # (kernel_peak_idx - kernel_center) samples; align all z-score traces to
        # the primary (1x) kernel reference so that the max-combination produces a
        # single sharp peak per event rather than multiple spread-out humps.
        primary_kernel = kernels[0]
        kernel_center_0 = (len(primary_kernel) - 1) // 2
        ref_offset = int(np.argmax(primary_kernel)) - kernel_center_0  # 1x shift

        z_traces = []
        for k in kernels:
            matched_k = k[::-1]
            filtered = signal.fftconvolve(work_data, matched_k, mode="same")
            mad = median_abs_deviation(filtered, scale="normal")
            if mad == 0:
                mad = 1e-12
            z = (filtered - np.median(filtered)) / mad
            # Align this kernel's peak to the primary kernel's reference
            k_offset = int(np.argmax(k)) - (len(k) - 1) // 2
            relative_shift = k_offset - ref_offset
            if relative_shift != 0:
                z = np.roll(z, relative_shift)
                if relative_shift > 0:
                    z[:relative_shift] = 0.0
                else:
                    z[relative_shift:] = 0.0
            z_traces.append(z)

        z_score_trace = np.max(np.stack(z_traces, axis=0), axis=0)
        # Noise estimate from the primary (unscaled) kernel for return metadata
        mad = float(median_abs_deviation(signal.fftconvolve(work_data, kernels[0][::-1], mode="same"), scale="normal"))
        if mad == 0:
            mad = 1e-12

        if min_event_distance_ms > 0:
            min_dist_samples = int((min_event_distance_ms / 1000.0) * sampling_rate)
        else:
            min_dist_samples = int(tau_decay * sampling_rate)
        if min_dist_samples < 1:
            min_dist_samples = 1

        peak_indices, _ = signal.find_peaks(z_score_trace, height=threshold_std, distance=min_dist_samples)

        # Peak refinement: z_score peaks are aligned to the primary kernel reference,
        # so apply only the primary kernel's offset when searching for the raw data peak.
        kernel_peak_idx = int(np.argmax(primary_kernel))
        template_offset = kernel_peak_idx - kernel_center_0
        refine_window = max(3, int(tau_rise * sampling_rate))

        if len(peak_indices) > 0:
            corrected_indices = np.empty_like(peak_indices)
            for i, idx in enumerate(peak_indices):
                shifted = idx + template_offset
                win_start = max(0, shifted - refine_window)
                win_end = min(n_points, shifted + refine_window + 1)
                local_peak = np.argmax(work_data[win_start:win_end])
                corrected_indices[i] = win_start + local_peak
            peak_indices = np.unique(corrected_indices)

        if artifact_mask is not None and len(peak_indices) > 0:
            n_mask = len(artifact_mask)
            valid_mask = peak_indices < n_mask
            not_artifact = ~artifact_mask[peak_indices[valid_mask]]
            peak_indices = peak_indices[valid_mask][not_artifact]

        event_count = len(peak_indices)
        event_indices = peak_indices.astype(int)
        event_amplitudes = baseline_corrected_data[event_indices] if event_count > 0 else np.array([])

        if time is not None and len(time) == n_points:
            time_axis = time
        else:
            time_axis = np.arange(n_points) * dt
        event_times = time_axis[event_indices] if event_count > 0 else np.array([])

        return EventDetectionResult(
            value=event_count,
            unit="counts",
            is_valid=True,
            event_count=event_count,
            event_indices=event_indices,
            event_times=event_times,
            event_amplitudes=event_amplitudes,
            detection_method="template_matching",
            tau_rise_ms=tau_rise * 1000.0,
            tau_decay_ms=tau_decay * 1000.0,
            threshold_sd=threshold_std,
            summary_stats={"noise_mad": mad},
            direction=polarity,
            artifact_mask=artifact_mask,
        )

    except Exception as e:
        log.error(f"Error during template event detection: {e}", exc_info=True)
        return EventDetectionResult(value=0, unit="Hz", is_valid=False, error_message=str(e))


@AnalysisRegistry.register(
    "event_detection_deconvolution",
    label="Event (Template Match)",
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
        {"type": "markers", "x": "_event_times", "y": "_event_peaks", "color": "r", "symbol": "o"},
        {"type": "threshold_line", "param": "threshold_sd"},
        {"type": "artifact_overlay"},
    ],
    ui_params=[
        {
            "name": "tau_rise_ms",
            "label": "Tau Rise (ms):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "tau_decay_ms",
            "label": "Tau Decay (ms):",
            "type": "float",
            "default": 5.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "threshold_sd",
            "label": "Threshold (SD):",
            "type": "float",
            "default": 4.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
        },
        {
            "name": "rolling_baseline_window_ms",
            "label": "Rolling Baseline (ms):",
            "type": "float",
            "default": 100.0,
            "min": 0.0,
            "max": 5000.0,
            "decimals": 1,
        },
        {"name": "reject_artifacts", "label": "Reject Artifacts", "type": "bool", "default": False},
        {
            "name": "artifact_slope_threshold",
            "label": "Artifact Slope Thresh:",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
        },
        {"name": "artifact_padding_ms", "label": "Artifact Padding (ms):", "type": "float", "default": 2.0},
        {
            "name": "min_event_distance_ms",
            "label": "Min Event Distance (ms):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1000.0,
            "decimals": 1,
            "tooltip": "Minimum distance between events (ms). 0 = use tau_decay.",
        },
        {
            "name": "filter_freq_hz",
            "label": "Filter Freq (Hz):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 100000.0,
            "decimals": 1,
            "hidden": True,
        },
    ],
)
def run_event_detection_template_wrapper(
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for template-matching event detection."""
    tau_rise_ms = kwargs.get("tau_rise_ms", 0.5)
    tau_decay_ms = kwargs.get("tau_decay_ms", 5.0)
    threshold_sd = kwargs.get("threshold_sd", 4.0)
    direction = kwargs.get("direction", "negative")

    tau_rise = tau_rise_ms / 1000.0
    tau_decay = tau_decay_ms / 1000.0

    reject_artifacts = kwargs.get("reject_artifacts", False)
    artifact_mask = None
    if reject_artifacts:
        slope_thresh = kwargs.get("artifact_slope_threshold", 20.0)
        padding_ms = kwargs.get("artifact_padding_ms", 2.0)
        artifact_mask = find_artifact_windows(data, sampling_rate, slope_thresh, padding_ms)

    result = detect_events_template(
        data=data,
        sampling_rate=sampling_rate,
        threshold_std=threshold_sd,
        tau_rise=tau_rise,
        tau_decay=tau_decay,
        polarity=direction,
        rolling_baseline_window_ms=kwargs.get("rolling_baseline_window_ms", 100.0),
        artifact_mask=artifact_mask,
        time=time,
        min_event_distance_ms=kwargs.get("min_event_distance_ms", 0.0),
    )

    if not result.is_valid:
        return {"module_used": "synaptic_events", "metrics": {"event_error": result.error_message}}

    _idx = np.asarray(result.event_indices if result.event_indices is not None else [], dtype=int)

    # Compute local pre-event baseline for each event (handles summating events).
    local_baselines = compute_local_pre_event_baseline(data, _idx, sampling_rate, polarity=direction)
    if len(_idx) > 0:
        if direction == "negative":
            local_amplitudes = local_baselines - data[_idx]
        else:
            local_amplitudes = data[_idx] - local_baselines
    else:
        local_amplitudes = np.array([], dtype=float)

    return {
        "module_used": "synaptic_events",
        "metrics": {
            "event_count": result.event_count,
            "tau_rise_ms": result.tau_rise_ms,
            "tau_decay_ms": result.tau_decay_ms,
            "threshold_sd": result.threshold_sd,
            "mean_local_amplitude": float(np.mean(local_amplitudes)) if local_amplitudes.size > 0 else 0.0,
            "_event_times": time[_idx].tolist() if len(_idx) > 0 else [],
            "_event_peaks": data[_idx].tolist() if len(_idx) > 0 else [],
            "_local_baselines": local_baselines.tolist() if local_baselines.size > 0 else [],
            "_local_amplitudes": local_amplitudes.tolist() if local_amplitudes.size > 0 else [],
            "_result_obj": result,
        },
    }


# ---------------------------------------------------------------------------
# 3. Baseline + Peak + Kinetics Detection
# ---------------------------------------------------------------------------


def _find_stable_baseline_segment(
    data: np.ndarray,
    sample_rate: float,
    window_duration_s: float = 0.5,
    step_duration_s: float = 0.1,
) -> Tuple[Optional[float], Optional[float], Optional[Tuple[int, int]]]:
    """Find the most stable (lowest-variance) baseline segment."""
    n_points = len(data)
    window_samples = max(2, int(window_duration_s * sample_rate))
    step_samples = max(1, int(step_duration_s * sample_rate))

    if window_samples >= n_points:
        return float(np.mean(data)), float(np.std(data)), (0, n_points)

    min_variance = np.inf
    best: Optional[Tuple[int, int]] = None
    best_mean: Optional[float] = None
    best_sd: Optional[float] = None

    for i in range(0, n_points - window_samples + 1, step_samples):
        segment = data[i : i + window_samples]
        variance = float(np.var(segment))
        if variance < min_variance:
            min_variance = variance
            best = (i, i + window_samples)
            best_mean = float(np.mean(segment))
            best_sd = float(np.sqrt(variance))

    return best_mean, best_sd, best


def detect_events_baseline_peak_kinetics(  # noqa: C901
    data: np.ndarray,
    sample_rate: float,
    direction: str = "negative",
    baseline_window_s: float = 0.5,
    baseline_step_s: float = 0.1,
    threshold_sd_factor: float = 3.0,
    filter_freq_hz: Optional[float] = None,
    min_event_separation_ms: float = 5.0,
    auto_baseline: bool = True,
    rolling_baseline_window_ms: float = 0.0,
) -> EventDetectionResult:
    """Detect events via stable-baseline estimation then prominence-based peak finding."""
    if direction not in ["negative", "positive"]:
        return EventDetectionResult(value=0, unit="counts", is_valid=False, error_message="Invalid direction")

    baseline_mean, baseline_sd, _ = _find_stable_baseline_segment(data, sample_rate, baseline_window_s, baseline_step_s)
    if baseline_mean is None:
        return EventDetectionResult(value=0, unit="counts", is_valid=True, event_count=0)

    is_negative = direction == "negative"

    if rolling_baseline_window_ms > 0:
        from scipy.ndimage import median_filter

        window_samples = int((rolling_baseline_window_ms / 1000.0) * sample_rate)
        if window_samples % 2 == 0:
            window_samples += 1
        if window_samples >= 3:
            rolling_bl = median_filter(data, size=window_samples)
            work_data = data - rolling_bl
        else:
            work_data = data
    else:
        work_data = data

    signal_to_process = -work_data if is_negative else work_data

    noise_sd = median_abs_deviation(signal_to_process, scale="normal")
    if noise_sd == 0:
        noise_sd = baseline_sd if baseline_sd and baseline_sd > 0 else 1e-12

    threshold_val = threshold_sd_factor * noise_sd

    if filter_freq_hz and filter_freq_hz > 0:
        try:
            sos = signal.butter(4, filter_freq_hz, "low", fs=sample_rate, output="sos")
            signal_c = np.ascontiguousarray(signal_to_process, dtype=np.float64)
            sos_c = np.ascontiguousarray(sos, dtype=np.float64)
            fwd = signal.sosfilt(sos_c, signal_c)
            filtered = signal.sosfilt(sos_c, fwd[::-1])[::-1]
        except (ValueError, TypeError, IndexError):
            filtered = signal_to_process
    else:
        filtered = signal_to_process

    min_dist = max(1, int(min_event_separation_ms / 1000.0 * sample_rate))
    min_width = max(2, int(0.0002 * sample_rate))
    peaks, _ = signal.find_peaks(
        filtered,
        height=threshold_val,
        prominence=threshold_val * 0.5,
        distance=min_dist,
        width=min_width,
    )

    display_threshold_val = -threshold_val if is_negative else threshold_val

    return EventDetectionResult(
        value=len(peaks),
        unit="counts",
        is_valid=True,
        event_count=len(peaks),
        event_indices=peaks,
        detection_method="baseline_peak",
        summary_stats={"baseline_mean": baseline_mean, "baseline_sd": float(noise_sd)},
        threshold_value=display_threshold_val,
    )


@AnalysisRegistry.register(
    "event_detection_baseline_peak",
    label="Event (Baseline Peak)",
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
        {"type": "markers", "x": "_event_times", "y": "_event_peaks", "color": "r", "symbol": "o"},
        {"type": "artifact_overlay"},
    ],
    ui_params=[
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
        },
        {"name": "auto_baseline", "label": "Auto-Detect Baseline", "type": "bool", "default": True},
        {"name": "threshold_sd_factor", "label": "Threshold (SD Factor):", "type": "float", "default": 3.0},
        {
            "name": "min_event_separation_ms",
            "label": "Min Separation (ms):",
            "type": "float",
            "default": 5.0,
            "min": 0.1,
            "max": 1000.0,
            "decimals": 1,
        },
        {
            "name": "rolling_baseline_window_ms",
            "label": "Rolling Baseline (ms):",
            "type": "float",
            "default": 100.0,
            "min": 0.0,
            "max": 5000.0,
            "decimals": 1,
        },
        {
            "name": "baseline_window_s",
            "label": "Baseline Win (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.01,
            "max": 100.0,
            "decimals": 2,
        },
        {
            "name": "baseline_step_s",
            "label": "Baseline Step (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.01,
            "max": 100.0,
            "decimals": 2,
        },
    ],
)
def run_event_detection_baseline_peak_wrapper(
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """Wrapper for baseline-peak event detection."""
    direction = kwargs.get("direction", "negative")
    result = detect_events_baseline_peak_kinetics(
        data,
        sampling_rate,
        direction=direction,
        threshold_sd_factor=kwargs.get("threshold_sd_factor", 3.0),
        min_event_separation_ms=kwargs.get("min_event_separation_ms", 5.0),
        auto_baseline=kwargs.get("auto_baseline", True),
        baseline_window_s=kwargs.get("baseline_window_s", 0.5),
        baseline_step_s=kwargs.get("baseline_step_s", 0.1),
        rolling_baseline_window_ms=kwargs.get("rolling_baseline_window_ms", 100.0),
    )
    if not result.is_valid:
        return {"module_used": "synaptic_events", "metrics": {"event_error": result.error_message}}
    _idx = np.asarray(result.event_indices if result.event_indices is not None else [], dtype=int)
    return {
        "module_used": "synaptic_events",
        "metrics": {
            "event_count": result.event_count,
            "_event_times": time[_idx].tolist() if len(_idx) > 0 else [],
            "_event_peaks": data[_idx].tolist() if len(_idx) > 0 else [],
            "_result_obj": result,
        },
    }


# ---------------------------------------------------------------------------
# Module-level tab aggregator
# ---------------------------------------------------------------------------
@AnalysisRegistry.register(
    "synaptic_events",
    label="Synaptic Events",
    method_selector={
        "Threshold Based": "event_detection_threshold",
        "Deconvolution (Custom)": "event_detection_deconvolution",
        "Baseline + Peak + Kinetics": "event_detection_baseline_peak",
    },
    ui_params=[],
    plots=[],
)
def synaptic_events_module(**kwargs):
    """Module-level aggregator tab for synaptic event detection analyses."""
    return {}
