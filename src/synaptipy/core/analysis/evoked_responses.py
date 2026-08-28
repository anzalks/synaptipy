# src/synaptipy/core/analysis/evoked_responses.py
# -*- coding: utf-8 -*-
"""
Core Protocol Module 5: Evoked Responses.

Consolidates optogenetic stimulus synchronization (TTL-gated latency,
probability, jitter analysis) from optogenetics.py.

All registry wrapper functions return::

    {
        "module_used": "evoked_responses",
        "metrics": { ... flat result keys ... }
    }
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import curve_fit

from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.analysis.single_spike import detect_spikes_threshold
from synaptipy.core.analysis.synaptic_events import detect_events_template, detect_events_threshold
from synaptipy.core.results import AnalysisResult
from synaptipy.core.signal_processor import find_artifact_windows

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class OptoSyncResult(AnalysisResult):
    """Result object for optogenetic synchronization analysis."""

    optical_latency_ms: Optional[float] = None
    response_probability: Optional[float] = None
    spike_jitter_ms: Optional[float] = None
    stimulus_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    stimulus_onsets: Optional[np.ndarray] = None
    stimulus_offsets: Optional[np.ndarray] = None
    responding_spikes: List[List[float]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        if self.is_valid:
            lat = f"{self.optical_latency_ms:.2f}" if self.optical_latency_ms is not None else "N/A"
            prob = f"{self.response_probability:.2f}" if self.response_probability is not None else "N/A"
            jit = f"{self.spike_jitter_ms:.2f}" if self.spike_jitter_ms is not None else "N/A"
            return (
                f"OptoSyncResult(Latency={lat} ms, Prob={prob}, "
                f"Success={self.success_count}/{self.stimulus_count}, "
                f"Jitter={jit} ms)"
            )
        return f"OptoSyncResult(Error: {self.error_message})"


# ---------------------------------------------------------------------------
# TTL Extraction
# ---------------------------------------------------------------------------


def extract_ttl_epochs(
    ttl_data: np.ndarray,
    time: np.ndarray,
    threshold: float = 2.5,
    auto_threshold: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extract rising and falling edges of a digital TTL signal.

    Returns:
        Tuple of (onsets, offsets) arrays in seconds.
    """
    if ttl_data.size == 0 or time.size == 0:
        return np.array([]), np.array([])

    is_high = ttl_data > threshold

    if auto_threshold:
        n_high = np.count_nonzero(is_high)
        if n_high == 0 or n_high == len(is_high):
            data_min = float(np.min(ttl_data))
            data_max = float(np.max(ttl_data))
            data_range = data_max - data_min
            if data_range > 0.3:  # require >300 mV swing (lowered from 1V to support low-voltage TTL)
                auto_thr = data_min + data_range * 0.5
                log.info(
                    "TTL threshold %.3f produced no edges; auto-adjusting to midpoint %.3f "
                    "(data range %.3f - %.3f).",
                    threshold,
                    auto_thr,
                    data_min,
                    data_max,
                )
                is_high = ttl_data > auto_thr

    is_high_padded = np.insert(is_high, 0, False)
    diff_signal = np.diff(is_high_padded.astype(int))
    rising_edges_idx = np.where(diff_signal == 1)[0]
    falling_edges_idx = np.where(diff_signal == -1)[0]

    if len(rising_edges_idx) > len(falling_edges_idx):
        falling_edges_idx = np.append(falling_edges_idx, len(ttl_data) - 1)

    onsets = time[rising_edges_idx]
    offsets = time[falling_edges_idx]
    return onsets, offsets


def _find_spikes_in_window(spikes: np.ndarray, t_start: float, t_end: float) -> np.ndarray:
    """Vectorised helper: return spikes within [t_start, t_end]."""
    if spikes.size == 0:
        return np.array([])
    mask = (spikes >= t_start) & (spikes <= t_end)
    return spikes[mask]


# ---------------------------------------------------------------------------
# Core Analysis
# ---------------------------------------------------------------------------


def calculate_optogenetic_sync(
    ttl_data: np.ndarray,
    action_potential_times: np.ndarray,
    time: np.ndarray,
    ttl_threshold: float = 2.5,
    response_window_ms: float = 20.0,
) -> OptoSyncResult:
    """
    Correlate TTL stimuli with action potential times.

    Args:
        ttl_data: Digital signal data trace.
        action_potential_times: Pre-calculated spike/event times (seconds).
        time: Timestamps of the trace.
        ttl_threshold: Voltage threshold for TTL edge detection.
        response_window_ms: Search window for APs after stimulus onset (ms).

    Returns:
        OptoSyncResult.
    """
    if ttl_data.size == 0:
        return OptoSyncResult(value=None, unit="", is_valid=False, error_message="Empty TTL Data")

    onsets, offsets = extract_ttl_epochs(ttl_data, time, ttl_threshold)
    stimulus_count = len(onsets)

    if stimulus_count == 0:
        return OptoSyncResult(
            value=None,
            unit="",
            is_valid=False,
            error_message="No TTL stimuli detected above threshold",
        )

    window_s = response_window_ms / 1000.0
    latencies = []
    responding_spikes = []
    response_count = 0

    for onset in onsets:
        valid_spikes = _find_spikes_in_window(action_potential_times, onset, onset + window_s)
        responding_spikes.append(valid_spikes.tolist())
        if valid_spikes.size > 0:
            response_count += 1
            latencies.append((valid_spikes[0] - onset) * 1000.0)

    failure_count = stimulus_count - response_count

    # Latency and jitter are computed only over *successful* trials to prevent
    # NaN propagation from failure trials.
    if response_count > 0:
        optical_latency_ms = float(np.mean(latencies))
        spike_jitter_ms = float(np.std(latencies)) if len(latencies) > 1 else 0.0
        response_probability = float(response_count / stimulus_count)
    else:
        optical_latency_ms = np.nan
        spike_jitter_ms = np.nan
        response_probability = 0.0

    return OptoSyncResult(
        value=optical_latency_ms,
        unit="ms",
        is_valid=True,
        optical_latency_ms=optical_latency_ms,
        response_probability=response_probability,
        spike_jitter_ms=spike_jitter_ms,
        stimulus_count=stimulus_count,
        success_count=response_count,
        failure_count=failure_count,
        stimulus_onsets=onsets,
        stimulus_offsets=offsets,
        responding_spikes=responding_spikes,
        parameters={"ttl_threshold": ttl_threshold, "response_window_ms": response_window_ms},
    )


# ---------------------------------------------------------------------------
# Shared scatter-marker helper
# ---------------------------------------------------------------------------


def _peak_pos_s(
    data: np.ndarray,
    time: np.ndarray,
    onset_s: float,
    polarity: str,
    blank_s: float,
    win_s: float,
) -> Tuple[float, float]:
    """Return ``(peak_time, peak_raw_value)`` for scatter-plot overlays.

    Searches a post-stimulus window (after artifact blanking) for the extremum
    matching *polarity* and returns its time and raw signal value.  On failure
    (e.g. window out of range) falls back to the onset time and the signal
    value at that sample.

    Args:
        data: 1-D signal trace.
        time: 1-D time vector (same length as *data*).
        onset_s: Stimulus onset time in seconds.
        polarity: ``"negative"`` or ``"positive"``.
        blank_s: Artifact-blanking duration in seconds.
        win_s: Response-search window duration in seconds.

    Returns:
        Tuple of ``(peak_time_s, peak_raw_value)``.
    """
    i0 = int(np.searchsorted(time, onset_s + blank_s))
    i1 = min(int(np.searchsorted(time, onset_s + win_s)) + 1, len(data))
    if i1 <= i0:
        fallback = min(int(np.searchsorted(time, onset_s)), len(data) - 1)
        return onset_s, float(data[fallback])
    seg = data[i0:i1]
    off = int(np.argmin(seg) if polarity == "negative" else np.argmax(seg))
    return float(time[i0 + off]), float(seg[off])


# ---------------------------------------------------------------------------
# Paired-Pulse Ratio with Residual Subtraction
# ---------------------------------------------------------------------------


def calculate_paired_pulse_ratio(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    stim1_onset_s: float,
    stim2_onset_s: float,
    response_window_ms: float = 20.0,
    baseline_window_ms: float = 5.0,
    fit_decay_from_ms: float = 5.0,
    fit_decay_window_ms: float = 30.0,
    polarity: str = "negative",
    artifact_blanking_ms: float = 1.0,
) -> Dict[str, Any]:
    """Calculate Paired-Pulse Ratio with residual decay subtraction.

    Without subtracting the residual exponential decay of the first event
    under the second stimulus window, the measured amplitude of the second
    response is artificially inflated (facilitation) or deflated (depression),
    yielding biologically invalid PPR values.

    Algorithm:

    1. Measure amplitude of response 1 (R1) relative to its local pre-stimulus
       baseline.
    2. Fit a mono-exponential decay to the *tail* of R1 (from
       ``fit_decay_from_ms`` to ``fit_decay_window_ms`` after stim1_onset).
    3. Extrapolate the decay curve to estimate the residual baseline level at
       stim2_onset.
    4. Measure amplitude of response 2 (R2_raw) relative to its own pre-stimulus
       sample.
    5. Subtract the residual decay value from R2_raw to obtain R2_corrected.
    6. Return ``paired_pulse_ratio = R2_corrected / R1``.

    Args:
        data: 1-D voltage/current array (mV or pA).
        time: 1-D time array (s).
        stim1_onset_s: Time of first stimulus onset (s).
        stim2_onset_s: Time of second stimulus onset (s).
        response_window_ms: Duration after each stimulus to search for peak (ms).
        baseline_window_ms: Pre-stimulus baseline window (ms) to compute local
            baseline for each response.
        fit_decay_from_ms: Offset from stim1_onset to start fitting decay (ms).
            Should be after the initial transient.
        fit_decay_window_ms: Window duration for decay fit (ms).
        polarity: ``"negative"`` (inward/downward events, e.g. EPSCs) or
            ``"positive"``.
        artifact_blanking_ms: Duration (ms) after each stimulus onset to ignore
            when searching for the peak response (default 1.0).  Prevents the
            stimulus shock-wave artefact from being identified as the biological
            response peak.

    Returns:
        Dict with keys:

        - ``r1_amplitude``         – amplitude of first response (baseline-subtracted)
        - ``r2_amplitude_raw``     – raw amplitude of second response
        - ``r2_amplitude_corrected`` – R2 after subtracting residual decay
        - ``residual_at_stim2``    – estimated residual baseline at stim2_onset
        - ``paired_pulse_ratio``   – R2_corrected / R1
        - ``decay_tau_ms``         – time constant of first event decay (ms)
        - ``ppr_error``            – None on success; error string on failure
    """
    out: Dict[str, Any] = {
        "r1_amplitude": None,
        "r2_amplitude_raw": None,
        "r2_amplitude_corrected": None,
        "residual_at_stim2": None,
        "paired_pulse_ratio": None,
        "decay_tau_ms": None,
        "ppr_error": None,
    }

    if data.size < 2 or time.shape != data.shape:
        out["ppr_error"] = "Invalid data or time array"
        return out

    fs = 1.0 / float(time[1] - time[0])  # noqa: F841

    def _nearest_idx(t: float) -> int:
        return int(np.searchsorted(time, t))

    def _local_baseline(stim_onset_s: float) -> float:
        bl_start_s = stim_onset_s - baseline_window_ms / 1000.0
        bl_start_s = max(bl_start_s, float(time[0]))
        i0 = _nearest_idx(bl_start_s)
        i1 = _nearest_idx(stim_onset_s)
        i1 = max(i0 + 1, i1)
        segment = data[i0:i1]
        return float(np.mean(segment)) if segment.size > 0 else float(data[_nearest_idx(stim_onset_s)])

    def _response_peak(stim_onset_s: float, baseline: float) -> Tuple[float, float]:
        """Return (peak_amplitude, raw_peak_value) relative to baseline.

        Data within ``artifact_blanking_ms`` of the stimulus onset are excluded
        so that the stimulus artefact is never mistaken for the biological peak.
        """
        blank_s = artifact_blanking_ms / 1000.0
        win_start = _nearest_idx(stim_onset_s + blank_s)
        win_end = min(_nearest_idx(stim_onset_s + response_window_ms / 1000.0) + 1, len(data))
        if win_end <= win_start:
            return 0.0, baseline
        segment = data[win_start:win_end]
        if polarity == "negative":
            peak_raw = float(np.min(segment))
            return baseline - peak_raw, peak_raw
        else:
            peak_raw = float(np.max(segment))
            return peak_raw - baseline, peak_raw

    # --- R1 ---
    bl1 = _local_baseline(stim1_onset_s)
    r1_amp, _ = _response_peak(stim1_onset_s, bl1)
    out["r1_amplitude"] = r1_amp

    if r1_amp <= 0:
        out["ppr_error"] = "R1 amplitude <= 0; cannot compute PPR"
        return out

    # --- Exponential decay fit on R1 tail ---
    def _mono_exp(t: np.ndarray, a: float, tau: float, c: float) -> np.ndarray:
        return a * np.exp(-t / tau) + c

    fit_start_s = stim1_onset_s + fit_decay_from_ms / 1000.0
    fit_end_s = stim1_onset_s + (fit_decay_from_ms + fit_decay_window_ms) / 1000.0
    fit_end_s = min(fit_end_s, stim2_onset_s)

    i_fit0 = _nearest_idx(fit_start_s)
    i_fit1 = _nearest_idx(fit_end_s)
    if i_fit1 - i_fit0 < 4:
        # Fallback: no residual correction
        bl2 = _local_baseline(stim2_onset_s)
        r2_amp_raw, _ = _response_peak(stim2_onset_s, bl2)
        out["r2_amplitude_raw"] = r2_amp_raw
        out["r2_amplitude_corrected"] = r2_amp_raw
        out["residual_at_stim2"] = 0.0
        out["decay_tau_ms"] = None
        if r1_amp > 0:
            out["paired_pulse_ratio"] = r2_amp_raw / r1_amp
        out["ppr_error"] = "Decay fit window too short; no residual correction applied"
        return out

    t_fit = (time[i_fit0:i_fit1] - time[i_fit0]) * 1000.0  # ms
    y_fit = data[i_fit0:i_fit1]
    # Amplitude at fit start relative to long-run asymptote (approx bl1)
    a0 = float(y_fit[0] - bl1) if polarity == "positive" else float(bl1 - y_fit[0])
    a0 = max(a0, 1e-6)
    tau0 = max(1.0, float(t_fit[-1]) / 3.0)

    residual_at_stim2 = 0.0
    tau_ms = None

    def _bi_exp(t: np.ndarray, a_f: float, tau_f: float, a_s: float, tau_s: float, c: float) -> np.ndarray:
        return a_f * np.exp(-t / tau_f) + a_s * np.exp(-t / tau_s) + c

    try:
        t_at_stim2_ms = (stim2_onset_s - time[i_fit0]) * 1000.0
        t_fit_abs = time[i_fit0:i_fit1]
        # Strict amplitude bound: ±3x R1 amplitude prevents parameter explosion.
        amp_bound = max(a0 * 3.0, abs(r1_amp) * 2.0, 1e-6)

        _fit_func = None
        _popt = None

        # ── Attempt bi-exponential fit (requires >= 8 samples for 5 params) ──
        if len(t_fit) >= 8:
            try:
                if polarity == "negative":
                    bi_p0 = [-a0 * 0.7, tau0 * 0.3, -a0 * 0.3, tau0, bl1]
                    bi_lower = [-amp_bound, 0.1, -amp_bound, 0.1, bl1 - abs(r1_amp) * 2]
                    bi_upper = [0.0, tau0 * 100, 0.0, tau0 * 100, bl1 + abs(r1_amp)]
                else:
                    bi_p0 = [a0 * 0.7, tau0 * 0.3, a0 * 0.3, tau0, bl1]
                    bi_lower = [0.0, 0.1, 0.0, 0.1, bl1 - abs(r1_amp)]
                    bi_upper = [amp_bound, tau0 * 100, amp_bound, tau0 * 100, bl1 + abs(r1_amp) * 2]
                popt_bi, pcov_bi = curve_fit(_bi_exp, t_fit, y_fit, p0=bi_p0, bounds=(bi_lower, bi_upper), maxfev=4000)
                # Fall back if covariance matrix cannot be estimated (degenerate fit).
                if np.any(~np.isfinite(pcov_bi)):
                    raise ValueError("Infinite covariance: bi-exp degenerate")
                a_f_fit, tau_f_fit, a_s_fit, tau_s_fit, _ = popt_bi
                total_amp = abs(a_f_fit) + abs(a_s_fit)
                if total_amp < 1e-12:
                    raise ValueError("Bi-exp amplitudes effectively zero")
                # Amplitude-weighted dominant time constant (section 15.5).
                tau_ms = (abs(a_f_fit) * tau_f_fit + abs(a_s_fit) * tau_s_fit) / total_amp
                _fit_func = _bi_exp
                _popt = popt_bi
            except (RuntimeError, ValueError) as _bi_exc:
                log.debug("PPR bi-exp failed (%s); falling back to mono-exp.", _bi_exc)

        # ── Mono-exponential fallback ──
        if _popt is None:
            try:
                if polarity == "negative":
                    popt_mono, _ = curve_fit(
                        _mono_exp,
                        t_fit,
                        y_fit,
                        p0=[-a0, tau0, bl1],
                        bounds=([-amp_bound, 0.1, bl1 - abs(r1_amp) * 2], [0.0, tau0 * 50, bl1 + abs(r1_amp)]),
                        maxfev=3000,
                    )
                else:
                    popt_mono, _ = curve_fit(
                        _mono_exp,
                        t_fit,
                        y_fit,
                        p0=[a0, tau0, bl1],
                        bounds=([0.0, 0.1, bl1 - abs(r1_amp)], [amp_bound, tau0 * 50, bl1 + abs(r1_amp) * 2]),
                        maxfev=3000,
                    )
                tau_ms = float(popt_mono[1])
                _fit_func = _mono_exp
                _popt = popt_mono
            except (RuntimeError, ValueError) as _mono_exc:
                log.debug("PPR mono-exp fallback failed (%s); tau_ms stays NaN.", _mono_exc)

        out["decay_tau_ms"] = tau_ms
        residual_at_stim2 = float(_fit_func(t_at_stim2_ms, *_popt)) - bl1
        out["residual_at_stim2"] = residual_at_stim2
        # Store fitted curve for visual overlay (private keys hidden from results table).
        out["_ppr_fit_times"] = t_fit_abs.tolist()
        out["_ppr_fit_values"] = [float(_fit_func(tv, *_popt)) for tv in t_fit]
    except Exception as exc:
        log.warning("PPR decay fit failed: %s", exc)
        out["ppr_error"] = f"Decay fit failed: {exc}"

    # --- R2 ---
    bl2 = _local_baseline(stim2_onset_s)
    r2_amp_raw, r2_peak_raw = _response_peak(stim2_onset_s, bl2)
    out["r2_amplitude_raw"] = r2_amp_raw

    # Compute the corrected R2 amplitude measured from bl1 (the true resting
    # baseline before any stimulation), not from bl2 (the local baseline just
    # before stim2 which may be contaminated by the R1 decay tail).
    #
    # Scientific rationale (Zucker & Regehr 2002, Regehr 2012):
    #   The "raw" amplitude r2_amp_raw is measured from bl2.  When the R1 decay
    #   has not fully returned to baseline by stim2, bl2 < bl1 (for inward/
    #   negative events) or bl2 > bl1 (for outward/positive events).  Using bl2
    #   as reference therefore underestimates the true R2 amplitude.  The
    #   corrected amplitude is obtained by using bl1 as the reference, which
    #   directly captures the contamination without relying on a potentially
    #   poor extrapolation of the decay fit.
    #
    #   Derivation:
    #     r2_peak_raw = actual peak value (returned by _response_peak)
    #     Negative: r2_corrected = bl1 - r2_peak_raw
    #     Positive: r2_corrected = r2_peak_raw - bl1
    #
    #   When residual is negligible (bl2 ≈ bl1): r2_corrected ≈ r2_amp_raw.
    #   When residual is significant: r2_corrected uses bl1 as reference.
    if polarity == "negative":
        r2_corrected = bl1 - r2_peak_raw
    else:
        r2_corrected = r2_peak_raw - bl1

    out["r2_amplitude_corrected"] = float(r2_corrected)

    if r1_amp > 0:
        out["paired_pulse_ratio"] = float(r2_corrected) / r1_amp

    return out


# ---------------------------------------------------------------------------
# N-Pulse Paired-Pulse Ratio
# ---------------------------------------------------------------------------


def calculate_n_pulse_ratio(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    stim_onsets: np.ndarray,
    response_window_ms: float = 20.0,
    baseline_window_ms: float = 5.0,
    fit_decay_from_ms: float = 5.0,
    fit_decay_window_ms: float = 30.0,
    polarity: str = "negative",
    artifact_blanking_ms: float = 1.0,
) -> Dict[str, Any]:
    """N-pulse PPR with iterative cumulative decay subtraction.

    For each pulse *i* the cumulative residual from all prior pulses'
    fitted decays is subtracted before measuring amplitude and fitting
    the current pulse's isolated decay (Thanawala & Bhatt 2013;
    Wesseling & Lo 2002).

    Algorithm:

    1. Measure bl1 (resting baseline before stim 1).
    2. For pulse *i*:

       a. Find the peak in the raw trace.
       b. Evaluate the cumulative residual from all prior decay fits at the peak time.
       c. amplitude_corrected = (bl1 - peak) - cumulative_residual (per polarity).
       d. Subtract the cumulative residual from the raw trace in the decay-fit window.
       e. Fit mono-/bi-exponential to the isolated decay.
       f. Store the fit for use in subsequent pulses' corrections.

    3. ratio_i = amplitude_corrected_i / amplitude_corrected_1.

    The overlay curves shown on the raw trace are the isolated fits with
    the prior cumulative residual added back, so they visually align with
    the actual data.
    """
    n = len(stim_onsets)
    out: Dict[str, Any] = {
        "n_pulses": n,
        "amplitudes_raw": [],
        "amplitudes_corrected": [],
        "ratios": [],
        "decay_taus_ms": [],
        "residuals": [],
        "_all_fit_times": [],
        "_all_fit_values": [],
        "ppr_error": None,
    }

    if data.size < 2 or time.shape != data.shape:
        out["ppr_error"] = "Invalid data or time array"
        return out
    if n < 2:
        out["ppr_error"] = "Need at least 2 stimulus onsets"
        return out

    def _nearest_idx(t: float) -> int:
        return int(np.searchsorted(time, t))

    def _local_baseline(stim_onset_s: float) -> float:
        bl_start_s = max(stim_onset_s - baseline_window_ms / 1000.0, float(time[0]))
        i0 = _nearest_idx(bl_start_s)
        i1 = max(i0 + 1, _nearest_idx(stim_onset_s))
        seg = data[i0:i1]
        if seg.size > 0:
            return float(np.mean(seg))
        return float(data[_nearest_idx(stim_onset_s)])

    def _response_peak(onset_s: float) -> Tuple[float, float]:
        blank_s = artifact_blanking_ms / 1000.0
        win_s = response_window_ms / 1000.0
        i0 = _nearest_idx(onset_s + blank_s)
        i1 = min(_nearest_idx(onset_s + win_s) + 1, len(data))
        if i1 <= i0:
            return 0.0, onset_s
        seg = data[i0:i1]
        idx = int(np.argmin(seg)) if polarity == "negative" else int(np.argmax(seg))
        return float(seg[idx]), float(time[i0 + idx])

    bl1 = _local_baseline(stim_onsets[0])

    def _mono_exp(t, a, tau, c):
        return a * np.exp(-t / tau) + c

    def _bi_exp(t, a_f, tau_f, a_s, tau_s, c):
        return a_f * np.exp(-t / tau_f) + a_s * np.exp(-t / tau_s) + c

    # Each entry: (fit_func, popt, t_ref_s) where t_ref_s is the absolute
    # time corresponding to t_rel=0 in the fit.  Evaluating at absolute
    # time t_abs: fit_func((t_abs - t_ref_s) * 1000, *popt).
    _decay_fits: list = []

    def _cumulative_residual_scalar(t_abs: float) -> float:
        total = 0.0
        for ff, pp, tr in _decay_fits:
            t_rel = (t_abs - tr) * 1000.0
            if t_rel >= 0:
                total += ff(t_rel, *pp) - bl1
        return total

    def _cumulative_residual_array(t_abs_arr: np.ndarray) -> np.ndarray:
        res = np.zeros(len(t_abs_arr))
        for ff, pp, tr in _decay_fits:
            t_rel = (t_abs_arr - tr) * 1000.0
            mask = t_rel >= 0
            if np.any(mask):
                res[mask] += ff(t_rel[mask], *pp) - bl1
        return res

    for i in range(n):
        peak_raw, peak_time = _response_peak(stim_onsets[i])

        cum_res = _cumulative_residual_scalar(peak_time) if _decay_fits else 0.0

        bl_local = _local_baseline(stim_onsets[i])
        if polarity == "negative":
            amp_raw = bl_local - peak_raw
            amp_corrected = (bl1 - peak_raw) + cum_res
        else:
            amp_raw = peak_raw - bl_local
            amp_corrected = (peak_raw - bl1) - cum_res

        out["amplitudes_raw"].append(float(amp_raw))
        out["amplitudes_corrected"].append(float(amp_corrected))
        out["residuals"].append(float(cum_res))

        # --- Fit this pulse's isolated decay ---
        if i < n - 1:
            fit_end_s = stim_onsets[i + 1]
        else:
            fit_end_s = stim_onsets[i] + (fit_decay_from_ms + fit_decay_window_ms) / 1000.0
        fit_end_s = min(fit_end_s, float(time[-1]))

        fit_start_s = stim_onsets[i] + fit_decay_from_ms / 1000.0
        i_fit0 = _nearest_idx(fit_start_s)
        i_fit1 = _nearest_idx(fit_end_s)

        tau_ms = None
        if i_fit1 - i_fit0 >= 4:
            t_fit_abs = time[i_fit0:i_fit1]
            t_fit = (t_fit_abs - t_fit_abs[0]) * 1000.0

            # Subtract cumulative prior residual to isolate this pulse.
            y_raw = data[i_fit0:i_fit1].copy()
            if _decay_fits:
                y_fit = y_raw - _cumulative_residual_array(t_fit_abs)
            else:
                y_fit = y_raw

            a0 = float(y_fit[0] - bl1) if polarity == "positive" else float(bl1 - y_fit[0])
            a0 = max(a0, 1e-6)
            tau0 = max(1.0, float(t_fit[-1]) / 3.0)
            amp_bound = max(a0 * 3.0, abs(amp_corrected) * 2.0, 1e-6)

            _fit_func = None
            _popt = None

            if len(t_fit) >= 8:
                try:
                    if polarity == "negative":
                        bi_p0 = [-a0 * 0.7, tau0 * 0.3, -a0 * 0.3, tau0, bl1]
                        bi_lb = [-amp_bound, 0.1, -amp_bound, 0.1, bl1 - abs(amp_corrected) * 2]
                        bi_ub = [0.0, tau0 * 100, 0.0, tau0 * 100, bl1 + abs(amp_corrected)]
                    else:
                        bi_p0 = [a0 * 0.7, tau0 * 0.3, a0 * 0.3, tau0, bl1]
                        bi_lb = [0.0, 0.1, 0.0, 0.1, bl1 - abs(amp_corrected)]
                        bi_ub = [amp_bound, tau0 * 100, amp_bound, tau0 * 100, bl1 + abs(amp_corrected) * 2]
                    popt_bi, pcov_bi = curve_fit(
                        _bi_exp,
                        t_fit,
                        y_fit,
                        p0=bi_p0,
                        bounds=(bi_lb, bi_ub),
                        maxfev=4000,
                    )
                    if np.any(~np.isfinite(pcov_bi)):
                        raise ValueError("degenerate")
                    a_f, tau_f, a_s, tau_s, _ = popt_bi
                    total = abs(a_f) + abs(a_s)
                    if total > 1e-12:
                        tau_ms = (abs(a_f) * tau_f + abs(a_s) * tau_s) / total
                    _fit_func = _bi_exp
                    _popt = popt_bi
                except (RuntimeError, ValueError):
                    pass

            if _popt is None:
                try:
                    if polarity == "negative":
                        popt_m, _ = curve_fit(
                            _mono_exp,
                            t_fit,
                            y_fit,
                            p0=[-a0, tau0, bl1],
                            bounds=(
                                [-amp_bound, 0.1, bl1 - abs(amp_corrected) * 2],
                                [0.0, tau0 * 50, bl1 + abs(amp_corrected)],
                            ),
                            maxfev=3000,
                        )
                    else:
                        popt_m, _ = curve_fit(
                            _mono_exp,
                            t_fit,
                            y_fit,
                            p0=[a0, tau0, bl1],
                            bounds=(
                                [0.0, 0.1, bl1 - abs(amp_corrected)],
                                [amp_bound, tau0 * 50, bl1 + abs(amp_corrected) * 2],
                            ),
                            maxfev=3000,
                        )
                    tau_ms = float(popt_m[1])
                    _fit_func = _mono_exp
                    _popt = popt_m
                except (RuntimeError, ValueError):
                    pass

            if _fit_func is not None and _popt is not None:
                _decay_fits.append((_fit_func, _popt, float(t_fit_abs[0])))

                # Overlay on the raw trace: isolated fit + prior residual.
                fit_isolated = np.array([_fit_func(tv, *_popt) for tv in t_fit])
                if len(_decay_fits) > 1:
                    prior_res = np.zeros(len(t_fit_abs))
                    for ff, pp, tr in _decay_fits[:-1]:
                        t_rel = (t_fit_abs - tr) * 1000.0
                        mask = t_rel >= 0
                        if np.any(mask):
                            prior_res[mask] += ff(t_rel[mask], *pp) - bl1
                    overlay = fit_isolated + prior_res
                else:
                    overlay = fit_isolated

                out["_all_fit_times"].append(t_fit_abs.tolist())
                out["_all_fit_values"].append(overlay.tolist())
            else:
                out["_all_fit_times"].append([])
                out["_all_fit_values"].append([])
        else:
            out["_all_fit_times"].append([])
            out["_all_fit_values"].append([])

        out["decay_taus_ms"].append(tau_ms)

    r1 = out["amplitudes_corrected"][0]
    if r1 > 0:
        out["ratios"] = [float(a) / r1 for a in out["amplitudes_corrected"]]
    else:
        out["ratios"] = [float("nan")] * n
        out["ppr_error"] = "R1 amplitude <= 0; cannot compute ratios"

    return out


# ---------------------------------------------------------------------------
# Registry Wrapper
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    name="optogenetic_sync",
    label="Evoked Sync",
    requires_secondary_channel={
        "param_name": "ttl_data",
        "label": "TTL / Stimulus Channel:",
        "tooltip": "Select the digital/TTL or stimulus channel (optical or electrical).",
    },
    ui_params=[
        {
            "name": "ttl_threshold",
            "type": "float",
            "label": "TTL Threshold (V)",
            "default": 2.5,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Voltage threshold to define stimulus ON state.",
        },
        {
            "name": "response_window_ms",
            "type": "float",
            "label": "Response Window (ms)",
            "default": 20.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 2,
            "tooltip": "Time window after stimulus onset to search for events.",
        },
        {
            "name": "event_detection_type",
            "type": "choice",
            "label": "Event Type:",
            "choices": ["Spikes", "Events (Threshold)", "Events (Template)"],
            "default": "Spikes",
            "tooltip": (
                "Spikes: detect action potentials by threshold crossing.\n"
                "Events (Threshold): detect synaptic events by adaptive prominence.\n"
                "Events (Template): detect events by template/matched-filter."
            ),
        },
        {
            "name": "spike_threshold",
            "type": "float",
            "label": "AP Threshold (mV)",
            "default": 0.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 2,
            "tooltip": "Voltage threshold to detect action potentials.",
            "visible_when": {"param": "event_detection_type", "value": "Spikes"},
        },
        {
            "name": "event_threshold",
            "type": "float",
            "label": "Event Threshold (pA/mV)",
            "default": 5.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Prominence threshold for event detection.",
            "visible_when": {"param": "event_detection_type", "value": "Events (Threshold)"},
        },
        {
            "name": "event_direction",
            "type": "choice",
            "label": "Event Direction:",
            "choices": ["negative", "positive"],
            "default": "negative",
            "tooltip": (
                "Direction of the evoked response. Defaults to negative for "
                "voltage-clamp (inward currents) and positive for current-clamp "
                "(depolarising potentials); change it to override."
            ),
            "default_by_clamp_mode": {"voltage_clamp": "negative", "current_clamp": "positive"},
            "visible_when": {"param": "event_detection_type", "value": "Events (Threshold)"},
        },
        {
            "name": "event_refractory_s",
            "type": "float",
            "label": "Refractory (s)",
            "default": 0.002,
            "min": 0.0,
            "max": 10.0,
            "decimals": 4,
            "visible_when": {"param": "event_detection_type", "value": "Events (Threshold)"},
        },
        {
            "name": "template_tau_rise_ms",
            "type": "float",
            "label": "Tau Rise (ms)",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 3,
            "visible_when": {"param": "event_detection_type", "value": "Events (Template)"},
        },
        {
            "name": "template_tau_decay_ms",
            "type": "float",
            "label": "Tau Decay (ms)",
            "default": 5.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 3,
            "visible_when": {"param": "event_detection_type", "value": "Events (Template)"},
        },
        {
            "name": "template_threshold_sd",
            "type": "float",
            "label": "Template Threshold (SD)",
            "default": 4.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 2,
            "visible_when": {"param": "event_detection_type", "value": "Events (Template)"},
        },
        {
            "name": "template_direction",
            "type": "choice",
            "label": "Template Direction:",
            "choices": ["negative", "positive"],
            "default": "negative",
            "tooltip": (
                "Direction of the evoked response. Defaults to negative for "
                "voltage-clamp (inward currents) and positive for current-clamp "
                "(depolarising potentials); change it to override."
            ),
            "default_by_clamp_mode": {"voltage_clamp": "negative", "current_clamp": "positive"},
            "visible_when": {"param": "event_detection_type", "value": "Events (Template)"},
        },
        {
            "name": "template_kernel_shape",
            "label": "Template Kernel Shape:",
            "type": "choice",
            "choices": ["bi-exponential", "mono-exponential"],
            "default": "bi-exponential",
            "tooltip": (
                "bi-exponential uses distinct tau_rise and tau_decay. " "mono-exponential uses only tau_decay."
            ),
            "visible_when": {"param": "event_detection_type", "value": "Events (Template)"},
        },
        {
            "name": "template_kernel_multipliers",
            "label": "Template Multipliers:",
            "type": "string",
            "default": "1.0, 2.0, 3.0",
            "tooltip": (
                "Comma-separated tau_decay scaling factors for the kernel bank. "
                "E.g. '1.0, 2.0, 3.0' (Cable theory predicts ~2-3x slowdown for distal inputs)."
            ),
            "visible_when": {"param": "event_detection_type", "value": "Events (Template)"},
        },
        {
            "name": "response_polarity",
            "type": "choice",
            "label": "Peak Polarity:",
            "choices": ["max", "min", "abs"],
            "default": "max",
            "tooltip": (
                "Direction to search for the peak response within the window. Defaults "
                "to min for voltage-clamp (inward currents) and max for current-clamp "
                "(depolarising potentials); change it to override."
            ),
            "default_by_clamp_mode": {"voltage_clamp": "min", "current_clamp": "max"},
        },
        {
            "name": "amplitude_window_ms",
            "type": "float",
            "label": "Amplitude Window (ms):",
            "default": 100.0,
            "min": 0.0,
            "max": 10000.0,
            "decimals": 1,
            "tooltip": (
                "Window (ms after stimulus onset) used to find the peak response amplitude. "
                "Independent of the event-detection Response Window. Should be wide enough "
                "to cover the full response (e.g. 100 ms for slow EPSPs/EPSCs)."
            ),
        },
        {
            "name": "baseline_window_ms",
            "type": "float",
            "label": "Baseline Window (ms):",
            "default": 5.0,
            "min": 0.0,
            "max": 1000.0,
            "decimals": 2,
            "tooltip": (
                "Window immediately before each stimulus onset used as the baseline. "
                "Reported response amplitudes are peak minus this baseline."
            ),
        },
        {
            "name": "artifact_blanking_ms",
            "type": "float",
            "label": "Artifact Blanking (ms):",
            "default": 1.0,
            "min": 0.0,
            "max": 50.0,
            "decimals": 2,
            "tooltip": "Data within this window after each stimulus onset are excluded from peak detection.",
        },
        {
            "name": "reject_artifacts",
            "label": "Reject Slope Artifacts",
            "type": "bool",
            "default": False,
            "tooltip": (
                "Detect and mask sharp slope-transients (e.g. electrical stimulation "
                "artefacts) before event detection.  Only applied when Event Type is "
                "'Events (Threshold)' or 'Events (Template)'."
            ),
        },
        {
            "name": "artifact_slope_threshold",
            "label": "Artifact Slope Thresh:",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
            "max": 1e6,
            "decimals": 1,
            "tooltip": "Slope (units/ms) above which a transient is classified as an artefact.",
            "visible_when": {"param": "reject_artifacts", "value": True},
        },
        {
            "name": "artifact_padding_ms",
            "label": "Artifact Padding (ms):",
            "type": "float",
            "default": 2.0,
            "min": 0.0,
            "max": 100.0,
            "decimals": 1,
            "tooltip": "Samples within this window around each detected artefact are also masked.",
            "visible_when": {"param": "reject_artifacts", "value": True},
        },
    ],
    plots=[
        {"name": "Trace", "type": "trace", "show_events": True},
        {"type": "vlines", "data": "stimulus_onsets"},
        {"type": "markers", "x": "_peak_times", "y": "_peak_amps", "symbol": "d"},
    ],
)
def run_opto_sync_wrapper(  # noqa: C901
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs
) -> Dict[str, Any]:
    """
    Wrapper for optogenetic synchronization analysis.

    Correlates TTL/optical stimulus pulses with detected events.
    """
    ttl_threshold = kwargs.get("ttl_threshold", 2.5)
    response_window_ms = kwargs.get("response_window_ms", 20.0)
    amplitude_window_ms = float(kwargs.get("amplitude_window_ms", 100.0))
    event_detection_type = kwargs.get("event_detection_type", "Spikes")
    response_polarity = kwargs.get("response_polarity", "max")
    artifact_blanking_ms = float(kwargs.get("artifact_blanking_ms", 1.0))
    baseline_window_ms = float(kwargs.get("baseline_window_ms", 5.0))

    # Build slope-based artifact mask for event detection types if requested.
    _reject_artifacts = kwargs.get("reject_artifacts", False)
    _artifact_mask = None
    if _reject_artifacts and event_detection_type in ("Events (Threshold)", "Events (Template)"):
        _slope_thresh = kwargs.get("artifact_slope_threshold", 20.0)
        _padding_ms = kwargs.get("artifact_padding_ms", 2.0)
        _artifact_mask = find_artifact_windows(data, sampling_rate, _slope_thresh, _padding_ms)

    ap_times = kwargs.get("action_potential_times", None)

    if ap_times is None:
        if event_detection_type == "Spikes":
            ap_threshold = kwargs.get("spike_threshold", 0.0)
            refractory_samples = max(1, int(0.002 * sampling_rate))
            spike_result = detect_spikes_threshold(
                data, time, threshold=ap_threshold, refractory_samples=refractory_samples
            )
            has_spikes = spike_result.spike_indices is not None and len(spike_result.spike_indices) > 0
            ap_times = time[spike_result.spike_indices] if has_spikes else np.array([])

        elif event_detection_type == "Events (Threshold)":
            ev_threshold = kwargs.get("event_threshold", 5.0)
            direction = kwargs.get("event_direction", "negative")
            refractory = kwargs.get("event_refractory_s", 0.002)
            ev_result = detect_events_threshold(
                data,
                time,
                threshold=ev_threshold,
                polarity=direction,
                refractory_period=refractory,
                artifact_mask=_artifact_mask,
            )
            if ev_result.is_valid and ev_result.event_times is not None and len(ev_result.event_times) > 0:
                ap_times = ev_result.event_times
            else:
                ap_times = np.array([])

        elif event_detection_type == "Events (Template)":
            tau_rise = kwargs.get("template_tau_rise_ms", 0.5) / 1000.0
            tau_decay = kwargs.get("template_tau_decay_ms", 5.0) / 1000.0
            threshold_sd = kwargs.get("template_threshold_sd", 4.0)
            direction = kwargs.get("template_direction", "negative")
            _raw_km = kwargs.get("template_kernel_multipliers", "1.0, 2.0, 3.0")
            try:
                _km = [float(x.strip()) for x in _raw_km.split(",") if x.strip()]
                if not _km:
                    raise ValueError("empty")
            except (ValueError, AttributeError):
                _km = [1.0, 2.0, 3.0]
            ev_result = detect_events_template(
                data=data,
                sampling_rate=sampling_rate,
                threshold_std=threshold_sd,
                tau_rise=tau_rise,
                tau_decay=tau_decay,
                polarity=direction,
                time=time,
                artifact_mask=_artifact_mask,
                kernel_multipliers=_km,
                kernel_shape=kwargs.get("template_kernel_shape", "bi-exponential"),
            )
            if ev_result.is_valid and ev_result.event_times is not None and len(ev_result.event_times) > 0:
                ap_times = ev_result.event_times
            else:
                ap_times = np.array([])

        else:
            ap_times = np.array([])
            log.warning("Unknown event_detection_type '%s'; defaulting to no events.", event_detection_type)

    ttl_data = kwargs.get("ttl_data", None)
    if ttl_data is None:
        return {
            "module_used": "evoked_responses",
            "metrics": {
                "error": "Optogenetic synchronization requires a recorded TTL channel or verified protocol timing."
            },
        }

    result = calculate_optogenetic_sync(
        ttl_data=ttl_data,
        action_potential_times=ap_times,
        time=time,
        ttl_threshold=ttl_threshold,
        response_window_ms=response_window_ms,
    )

    if not result.is_valid:
        return {"module_used": "evoked_responses", "metrics": {"error": result.error_message}}

    # Find peak response voltage within each TTL stimulus window.
    # Uses amplitude_window_ms (independent, default 100 ms) so that the
    # peak search always covers the full response regardless of the narrower
    # event-detection Response Window.  The first artifact_blanking_ms after
    # each stimulus onset are skipped to exclude the stimulus artefact.
    #
    # ``_peak_amps`` stays in absolute signal units because the plot draws its
    # markers in data coordinates; the reported amplitudes are the same peaks
    # measured against a pre-stimulus baseline, which is the quantity that is
    # comparable across cells and conditions.
    _peak_times: List[float] = []
    _peak_amps: List[float] = []
    _response_amps: List[float] = []
    _amp_window_s = amplitude_window_ms / 1000.0
    _blank_s = artifact_blanking_ms / 1000.0
    _baseline_s = baseline_window_ms / 1000.0
    if result.stimulus_onsets is not None and len(data) > 0:
        for _onset in result.stimulus_onsets:
            _idx_start = int(np.searchsorted(time, _onset + _blank_s, side="left"))
            _idx_end = int(np.searchsorted(time, _onset + _amp_window_s, side="right"))
            _idx_start = max(0, min(_idx_start, len(data) - 1))
            _idx_end = max(_idx_start + 1, min(_idx_end, len(data)))
            _window_data = data[_idx_start:_idx_end]
            if len(_window_data) == 0:
                continue
            if response_polarity == "min":
                _local_idx = int(np.argmin(_window_data))
            elif response_polarity == "abs":
                _local_idx = int(np.argmax(np.abs(_window_data)))
            else:
                _local_idx = int(np.argmax(_window_data))
            _abs_idx = _idx_start + _local_idx
            _peak_times.append(float(time[_abs_idx]))
            _peak_amps.append(float(data[_abs_idx]))

            # Baseline over the window immediately preceding the stimulus.
            _base_start = int(np.searchsorted(time, _onset - _baseline_s, side="left"))
            _base_end = int(np.searchsorted(time, _onset, side="left"))
            _base_start = max(0, _base_start)
            _base_end = max(_base_start + 1, min(_base_end, len(data)))
            _base_data = data[_base_start:_base_end]
            if len(_base_data) > 0:
                _response_amps.append(float(data[_abs_idx] - np.mean(_base_data)))

    if _response_amps:
        _mean_amp = float(np.mean(_response_amps))
        _sd_amp = float(np.std(_response_amps, ddof=1)) if len(_response_amps) > 1 else 0.0
    else:
        _mean_amp = np.nan
        _sd_amp = np.nan

    # Response probability as a percentage for human-readable reporting.
    resp_prob_pct = round(result.response_probability * 100.0, 2) if result.response_probability is not None else np.nan

    return {
        "module_used": "evoked_responses",
        "metrics": {
            "optical_latency_ms": result.optical_latency_ms,
            "response_probability": result.response_probability,
            "response_probability_pct": resp_prob_pct,
            "spike_jitter_ms": result.spike_jitter_ms,
            "mean_response_amplitude": _mean_amp,
            "response_amplitude_sd": _sd_amp,
            "stimulus_count": result.stimulus_count,
            "Success Count": result.success_count,
            "Failure Count": result.failure_count,
            "event_count": len(ap_times),
            "event_times": ap_times.tolist() if hasattr(ap_times, "tolist") else list(ap_times),
            "stimulus_onsets": (result.stimulus_onsets.tolist() if result.stimulus_onsets is not None else []),
            "response_amplitudes": _response_amps,
            "_peak_times": _peak_times,
            "_peak_amps": _peak_amps,
        },
    }


# ---------------------------------------------------------------------------
# PPR Registry Wrapper
# ---------------------------------------------------------------------------


def _build_stim_onsets(
    time: np.ndarray,
    n_pulses: int,
    kwargs: dict,
    warnings: Optional[List[str]] = None,
) -> "np.ndarray | str":
    """Build stim onset array from TTL or manual parameters.

    Returns the onset array on success, or an error string on failure.

    When TTL detection is requested it is never silently replaced by the manual
    onset spinboxes: a paired-pulse ratio computed from placeholder onsets is
    indistinguishable from a real measurement in the results table, so a failed
    detection is reported as an error the caller must surface.
    """
    use_ttl = bool(kwargs.get("use_ttl", False))
    stim_onsets = None

    if use_ttl:
        ttl_data = kwargs.get("ttl_data", None)
        if ttl_data is None or len(ttl_data) == 0:
            return (
                "'Detect Stim from TTL' is enabled but no TTL channel is selected. "
                "Choose the TTL / stimulus channel above, or disable TTL detection "
                "to enter stimulus onsets manually."
            )
        ttl_threshold = float(kwargs.get("ttl_threshold", 2.5))
        detected, _ = extract_ttl_epochs(ttl_data, time, ttl_threshold)
        if detected is None or len(detected) < 2:
            found = 0 if detected is None else len(detected)
            return (
                f"TTL detection found {found} stimulus onset(s) above {ttl_threshold:g} V; "
                "at least 2 are needed. Check the TTL channel and threshold, or "
                "disable TTL detection to enter onsets manually."
            )
        if len(detected) < n_pulses and warnings is not None:
            warnings.append(
                f"TTL detection found {len(detected)} onsets but {n_pulses} pulses were "
                f"requested; analysing {len(detected)} pulses."
            )
        stim_onsets = detected[:n_pulses]
        log.debug("PPR: TTL detected %d onsets, using first %d", len(detected), len(stim_onsets))

    if stim_onsets is None:
        s1 = float(kwargs.get("stim1_onset_s", 0.1))
        s2 = float(kwargs.get("stim2_onset_s", 0.2))
        isi = s2 - s1
        if isi <= 0:
            return "Stim2 must be after Stim1"
        stim_onsets = np.array([s1 + i * isi for i in range(n_pulses)])
        if warnings is not None:
            warnings.append(
                f"Stimulus onsets entered manually (first at {s1:g} s, ISI {isi * 1000.0:g} ms); "
                "not verified against a recorded TTL channel."
            )

    n_requested = len(stim_onsets)
    stim_onsets = stim_onsets[stim_onsets < float(time[-1])]
    if len(stim_onsets) < 2:
        return "Need at least 2 onsets within recording"
    if len(stim_onsets) < n_requested and warnings is not None:
        warnings.append(
            f"{n_requested - len(stim_onsets)} stimulus onset(s) fall beyond the end of "
            f"the recording ({float(time[-1]):.4g} s) and were dropped."
        )
    return stim_onsets


@AnalysisRegistry.register(
    "paired_pulse_ratio",
    label="Paired-Pulse Ratio",
    # Unticking "Detect Stim from TTL" hands stimulus timing to the onset
    # spinboxes below.  That is the user declaring the timing explicitly, so it
    # satisfies the stimulus-timing requirement the same way a TTL channel does;
    # the result carries a warning recording that the timing was manual.
    manual_stimulus_timing={"param": "use_ttl", "manual_value": False},
    requires_secondary_channel={
        "param_name": "ttl_data",
        "label": "TTL / Stimulus Channel:",
        "tooltip": "Optional TTL channel.  When 'Detect Stim from TTL' is enabled, "
        "stimulus times are read from this channel instead of the manual spinboxes.",
    },
    plots=[
        {"name": "Trace", "type": "trace"},
        {"type": "vlines", "data": "_stim_onsets"},
        {
            "type": "trace_overlay",
            "start_time": "_baseline_start_s",
            "end_time": "_baseline_end_s",
            "color": "#228B22",
            "width": 3,
            "opacity": 50,
        },
        {
            "type": "event_fit_overlay",
            "times_key": "_ppr_fit_times",
            "values_key": "_ppr_fit_values",
            "color": "#ff9900",
            "width": 2,
            "opacity": 85,
        },
        {"type": "markers", "x": "_peak_times", "y": "_peak_amps", "symbol": "d", "color": "#cc0000"},
    ],
    ui_params=[
        {
            "name": "use_ttl",
            "label": "Detect Stim from TTL:",
            "type": "bool",
            "default": True,
            "tooltip": "When enabled, stimulus onsets are detected automatically "
            "from the TTL channel.  Select the TTL channel in the secondary-channel "
            "dropdown above.  Disable to enter stimulus onsets manually.",
        },
        {
            "name": "ttl_threshold",
            "label": "TTL Threshold (V):",
            "type": "float",
            "default": 2.5,
            "min": -100.0,
            "max": 100.0,
            "decimals": 3,
            "tooltip": "Binarisation threshold for TTL edge detection.",
            "visible_when": {"param": "use_ttl", "value": True},
        },
        {
            "name": "n_pulses",
            "label": "Number of Pulses:",
            "type": "int",
            "default": 2,
            "min": 2,
            "max": 100,
            "tooltip": "Number of stimulus pulses.  All ratios are normalised to R1.",
        },
        {
            "name": "stim1_onset_s",
            "label": "Stim 1 Onset (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "visible_when": {"param": "use_ttl", "value": False},
        },
        {
            "name": "stim2_onset_s",
            "label": "Stim 2 Onset (s):",
            "type": "float",
            "default": 0.2,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Time of the second stimulus.  For N > 2 pulses the inter-stimulus "
            "interval is derived from (Stim2 - Stim1) and applied uniformly.",
            "visible_when": {"param": "use_ttl", "value": False},
        },
        {
            "name": "polarity",
            "label": "Event Polarity:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
            "tooltip": (
                "Direction of the evoked response. Defaults to negative for "
                "voltage-clamp (inward currents) and positive for current-clamp "
                "(depolarising potentials); change it to override."
            ),
            "default_by_clamp_mode": {"voltage_clamp": "negative", "current_clamp": "positive"},
        },
        {
            "name": "response_window_ms",
            "label": "Response Window (ms):",
            "type": "float",
            "default": 20.0,
            "min": 1.0,
            "max": 500.0,
            "decimals": 1,
        },
        {
            "name": "baseline_window_ms",
            "label": "Baseline Window (ms):",
            "type": "float",
            "default": 5.0,
            "min": 1.0,
            "max": 100.0,
            "decimals": 1,
        },
        {
            "name": "fit_decay_from_ms",
            "label": "Decay Fit Start (ms):",
            "type": "float",
            "default": 5.0,
            "min": 0.0,
            "max": 100.0,
            "decimals": 1,
            "tooltip": "Offset from each stimulus onset to begin fitting the decay (skip initial transient).",
        },
        {
            "name": "fit_decay_window_ms",
            "label": "Decay Fit Window (ms):",
            "type": "float",
            "default": 30.0,
            "min": 5.0,
            "max": 500.0,
            "decimals": 1,
        },
        {
            "name": "artifact_blanking_ms",
            "label": "Artifact Blanking (ms):",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 50.0,
            "decimals": 2,
            "tooltip": "Data within this window after each stimulus onset are excluded from peak detection.",
        },
    ],
)
def run_ppr_wrapper(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """Wrapper for N-pulse Paired-Pulse Ratio analysis."""
    warnings: List[str] = []
    n_pulses = int(kwargs.get("n_pulses", 2))
    stim_onsets = _build_stim_onsets(time, n_pulses, kwargs, warnings)
    if isinstance(stim_onsets, str):
        return {
            "module_used": "evoked_responses",
            "metrics": {"ppr_error": stim_onsets},
            "warnings": warnings,
        }

    polarity = kwargs.get("polarity", "negative")
    response_window_ms = float(kwargs.get("response_window_ms", 20.0))
    baseline_window_ms = float(kwargs.get("baseline_window_ms", 5.0))
    fit_decay_from_ms = float(kwargs.get("fit_decay_from_ms", 5.0))
    fit_decay_window_ms = float(kwargs.get("fit_decay_window_ms", 30.0))
    artifact_blanking_ms = float(kwargs.get("artifact_blanking_ms", 1.0))

    result = calculate_n_pulse_ratio(
        data=data,
        time=time,
        stim_onsets=stim_onsets,
        response_window_ms=response_window_ms,
        baseline_window_ms=baseline_window_ms,
        fit_decay_from_ms=fit_decay_from_ms,
        fit_decay_window_ms=fit_decay_window_ms,
        polarity=polarity,
        artifact_blanking_ms=artifact_blanking_ms,
    )

    blank_s = artifact_blanking_ms / 1000.0
    win_s = response_window_ms / 1000.0
    peak_times = []
    peak_amps = []
    for onset in stim_onsets:
        pt, pv = _peak_pos_s(data, time, onset, polarity, blank_s, win_s)
        peak_times.append(pt)
        peak_amps.append(pv)

    n_actual = len(stim_onsets)
    metrics: Dict[str, Any] = {
        "n_pulses": n_actual,
        "ppr_error": result["ppr_error"],
        "_stim_onsets": stim_onsets.tolist(),
        "_baseline_start_s": float(stim_onsets[0]) - baseline_window_ms / 1000.0,
        "_baseline_end_s": float(stim_onsets[0]),
        "_peak_times": peak_times,
        "_peak_amps": peak_amps,
    }

    for i in range(n_actual):
        suffix = f"_p{i + 1}"
        metrics[f"amplitude_raw{suffix}"] = result["amplitudes_raw"][i]
        metrics[f"amplitude_corrected{suffix}"] = result["amplitudes_corrected"][i]
        metrics[f"ratio{suffix}"] = result["ratios"][i]
        metrics[f"residual{suffix}"] = result["residuals"][i]
        metrics[f"decay_tau_ms{suffix}"] = result["decay_taus_ms"][i]

    all_fit_t = []
    all_fit_v = []
    for ft, fv in zip(result["_all_fit_times"], result["_all_fit_values"]):
        if ft:
            all_fit_t.append(ft)
            all_fit_v.append(fv)
    metrics["_ppr_fit_times"] = all_fit_t if all_fit_t else None
    metrics["_ppr_fit_values"] = all_fit_v if all_fit_v else None

    return {"module_used": "evoked_responses", "metrics": metrics, "warnings": warnings}


# ---------------------------------------------------------------------------
# Stimulus Train STP
# ---------------------------------------------------------------------------


def calculate_stimulus_train_stp(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    stim_onsets: np.ndarray,
    polarity: str = "negative",
    response_window_ms: float = 20.0,
    baseline_window_ms: float = 5.0,
    artifact_blanking_ms: float = 1.0,
) -> Dict[str, Any]:
    """Compute short-term plasticity (STP) amplitudes for a stimulus train.

    For each stimulus onset the function measures a baseline immediately
    preceding the stimulus, then finds the peak response in a post-stimulus
    window (after artifact blanking).  Amplitudes are normalised to R1 to
    yield the STP profile.

    Args:
        data: 1-D voltage or current trace.
        time: 1-D time vector (seconds, same length as data).
        stim_onsets: Stimulus onset times in seconds, ordered chronologically.
        polarity: ``"negative"`` for inward/hyperpolarising events,
            ``"positive"`` for outward/depolarising events.
        response_window_ms: Duration of the post-stimulus peak-search window
            in milliseconds.
        baseline_window_ms: Duration of the pre-stimulus baseline window in
            milliseconds.
        artifact_blanking_ms: Data within this interval after each onset are
            excluded from peak detection.

    Returns:
        Dictionary with keys ``amplitudes``, ``amplitudes_norm``,
        ``pulse_numbers``, ``stim_onsets`` and descriptive metric keys.
    """
    if data.size < 2 or time.shape != data.shape:
        return {"stp_error": "Invalid data or time array"}

    blank_s = artifact_blanking_ms / 1000.0
    win_s = response_window_ms / 1000.0
    bl_s = baseline_window_ms / 1000.0

    def _idx(t: float) -> int:
        return int(np.searchsorted(time, t))

    def _baseline(onset: float) -> float:
        i0 = _idx(max(onset - bl_s, float(time[0])))
        i1 = max(_idx(onset), i0 + 1)
        seg = data[i0:i1]
        return float(np.mean(seg)) if seg.size > 0 else float(data[_idx(onset)])

    def _amplitude(onset: float, baseline: float) -> float:
        i_start = _idx(onset + blank_s)
        i_end = min(_idx(onset + win_s) + 1, len(data))
        if i_end <= i_start:
            return 0.0
        seg = data[i_start:i_end]
        if polarity == "negative":
            return float(baseline - np.min(seg))
        return float(np.max(seg) - baseline)

    amplitudes: List[float] = []
    peak_times: List[float] = []
    peak_values: List[float] = []
    for onset in stim_onsets:
        bl = _baseline(onset)
        amplitudes.append(_amplitude(onset, bl))
        pt, pv = _peak_pos_s(data, time, float(onset), polarity, blank_s, win_s)
        peak_times.append(pt)
        peak_values.append(pv)

    n = len(amplitudes)
    pulse_numbers = list(range(1, n + 1))
    r1 = amplitudes[0] if amplitudes else 1.0
    amplitudes_norm = [a / r1 if r1 != 0.0 else float("nan") for a in amplitudes]

    ratios: Dict[str, Any] = {}
    for i in range(1, n):
        ratios[f"R{i + 1}/R1"] = round(amplitudes_norm[i], 4)

    stp_type = "none"
    if n >= 2:
        stp_type = "facilitation" if amplitudes[1] > amplitudes[0] else "depression"

    return {
        "pulse_count": n,
        "r1_amplitude": round(amplitudes[0], 4) if amplitudes else None,
        "stp_type": stp_type,
        **ratios,
        "amplitudes": [round(a, 4) for a in amplitudes],
        "amplitudes_norm": amplitudes_norm,
        "pulse_numbers": pulse_numbers,
        "_stim_onsets": stim_onsets.tolist(),
        "_peak_times": peak_times,
        "_peak_amps": peak_values,
    }


@AnalysisRegistry.register(
    "stimulus_train_stp",
    label="Stimulus Train (STP)",
    # See paired_pulse_ratio: the frequency/start-time parameters are an explicit
    # manual declaration of stimulus timing.
    manual_stimulus_timing={"param": "use_ttl", "manual_value": False},
    requires_secondary_channel={
        "param_name": "ttl_data",
        "label": "TTL / Stimulus Channel:",
        "tooltip": "Select the TTL/trigger channel to auto-detect stimulus times.  "
        "Leave unset to use the manual frequency and start-time parameters.",
    },
    ui_params=[
        {
            "name": "use_ttl",
            "label": "Detect Stim from TTL:",
            "type": "bool",
            "default": True,
            "tooltip": "When enabled, stimulus times are detected from the TTL channel.  "
            "When disabled, times are generated from the frequency and start-time "
            "parameters below.",
        },
        {
            "name": "ttl_threshold",
            "label": "TTL Threshold (V):",
            "type": "float",
            "default": 2.5,
            "min": -100.0,
            "max": 100.0,
            "decimals": 3,
            "visible_when": {"param": "use_ttl", "value": True},
        },
        {
            "name": "stim_start_s",
            "label": "First Stim Onset (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
            "tooltip": "Time of the first stimulus pulse. Used when TTL detection is disabled.",
            "visible_when": {"param": "use_ttl", "value": False},
        },
        {
            "name": "stim_frequency_hz",
            "label": "Stim Frequency (Hz):",
            "type": "float",
            "default": 10.0,
            "min": 0.1,
            "max": 1000.0,
            "decimals": 1,
            "tooltip": "Stimulation frequency in Hz. Used when TTL detection is disabled.",
            "visible_when": {"param": "use_ttl", "value": False},
        },
        {
            "name": "n_pulses",
            "label": "Number of Pulses:",
            "type": "int",
            "default": 5,
            "min": 2,
            "max": 100,
            "tooltip": "Maximum number of stimulus pulses to include.",
        },
        {
            "name": "polarity",
            "label": "Event Polarity:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
            "tooltip": (
                "Direction of the evoked response. Defaults to negative for "
                "voltage-clamp (inward currents) and positive for current-clamp "
                "(depolarising potentials); change it to override."
            ),
            "default_by_clamp_mode": {"voltage_clamp": "negative", "current_clamp": "positive"},
        },
        {
            "name": "response_window_ms",
            "label": "Response Window (ms):",
            "type": "float",
            "default": 20.0,
            "min": 1.0,
            "max": 500.0,
            "decimals": 1,
        },
        {
            "name": "baseline_window_ms",
            "label": "Baseline Window (ms):",
            "type": "float",
            "default": 5.0,
            "min": 1.0,
            "max": 100.0,
            "decimals": 1,
        },
        {
            "name": "artifact_blanking_ms",
            "label": "Artifact Blanking (ms):",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 50.0,
            "decimals": 2,
            "tooltip": "Data within this window after each stimulus onset are excluded from " "peak detection.",
        },
    ],
    plots=[
        {"name": "Trace", "type": "trace"},
        {"type": "vlines", "data": "_stim_onsets"},
        {"type": "markers", "x": "_peak_times", "y": "_peak_amps", "symbol": "d", "color": "#ff6600"},
        {
            "type": "popup_xy",
            "title": "STP Profile",
            "x": "pulse_numbers",
            "y": "amplitudes_norm",
            "x_label": "Pulse Number",
            "y_label": "Normalised Amplitude (R_n / R_1)",
        },
    ],
)
def run_stimulus_train_stp_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """Wrapper for Stimulus Train STP analysis.

    Stimulus times are either detected from an optional TTL/trigger channel or
    generated from a user-supplied frequency and start time.  For each pulse the
    wrapper measures a baseline-subtracted peak amplitude and normalises the
    series to R1 to produce the STP profile.
    """
    use_ttl = bool(kwargs.get("use_ttl", True))
    ttl_threshold = float(kwargs.get("ttl_threshold", 2.5))
    stim_start_s = float(kwargs.get("stim_start_s", 0.1))
    stim_frequency_hz = float(kwargs.get("stim_frequency_hz", 10.0))
    n_pulses = int(kwargs.get("n_pulses", 5))
    polarity = str(kwargs.get("polarity", "negative"))
    response_window_ms = float(kwargs.get("response_window_ms", 20.0))
    baseline_window_ms = float(kwargs.get("baseline_window_ms", 5.0))
    artifact_blanking_ms = float(kwargs.get("artifact_blanking_ms", 1.0))

    # --- Determine stimulus onsets ---
    stim_onsets: Optional[np.ndarray] = None
    warnings: List[str] = []

    # TTL detection is never silently replaced by the manual frequency
    # parameters: an STP profile built from a placeholder 10 Hz train looks
    # exactly like a measured one in the results table.
    if use_ttl:
        ttl_data = kwargs.get("ttl_data", None)
        if ttl_data is None or len(ttl_data) == 0:
            return {
                "module_used": "evoked_responses",
                "metrics": {
                    "stp_error": (
                        "'Detect Stim from TTL' is enabled but no TTL channel is selected. "
                        "Choose the TTL / stimulus channel above, or disable TTL detection "
                        "to use the manual frequency parameters."
                    )
                },
            }
        detected, _ = extract_ttl_epochs(ttl_data, time, ttl_threshold)
        if detected is None or len(detected) == 0:
            return {
                "module_used": "evoked_responses",
                "metrics": {
                    "stp_error": (
                        f"TTL detection found no stimulus onsets above {ttl_threshold:g} V. "
                        "Check the TTL channel and threshold, or disable TTL detection "
                        "to use the manual frequency parameters."
                    )
                },
            }
        if len(detected) < n_pulses:
            warnings.append(
                f"TTL detection found {len(detected)} onsets but {n_pulses} pulses were "
                f"requested; analysing {len(detected)} pulses."
            )
        stim_onsets = detected[:n_pulses]
        log.debug("STP: TTL detected %d onsets, using first %d", len(detected), len(stim_onsets))
    else:
        if stim_frequency_hz <= 0.0:
            return {
                "module_used": "evoked_responses",
                "metrics": {"stp_error": "Stimulus frequency must be > 0 Hz"},
            }
        isi = 1.0 / stim_frequency_hz
        stim_onsets = np.array([stim_start_s + i * isi for i in range(n_pulses)])
        warnings.append(
            f"Stimulus onsets generated from manual parameters ({stim_start_s:g} s, "
            f"{stim_frequency_hz:g} Hz, {n_pulses} pulses); not verified against a "
            "recorded TTL channel."
        )

    # Clip to recording duration.
    n_requested = len(stim_onsets)
    stim_onsets = stim_onsets[stim_onsets < float(time[-1])]
    if len(stim_onsets) == 0:
        return {
            "module_used": "evoked_responses",
            "metrics": {"stp_error": "No stimulus onsets lie within the recording duration"},
        }
    if len(stim_onsets) < n_requested:
        warnings.append(
            f"{n_requested - len(stim_onsets)} stimulus onset(s) fall beyond the end of "
            f"the recording ({float(time[-1]):.4g} s) and were dropped."
        )

    result = calculate_stimulus_train_stp(
        data=data,
        time=time,
        stim_onsets=stim_onsets,
        polarity=polarity,
        response_window_ms=response_window_ms,
        baseline_window_ms=baseline_window_ms,
        artifact_blanking_ms=artifact_blanking_ms,
    )

    return {"module_used": "evoked_responses", "metrics": result, "warnings": warnings}


# ---------------------------------------------------------------------------
# Module-level tab aggregator
# ---------------------------------------------------------------------------
@AnalysisRegistry.register(
    "evoked_responses",
    label="Evoked Responses",
    requires_secondary_channel={
        "param_name": "ttl_data",
        "label": "TTL / Stimulus Channel:",
        "tooltip": "Select the digital/TTL or stimulus channel (optical or electrical).",
    },
    method_selector={
        "Evoked Sync": "optogenetic_sync",
        "Paired-Pulse Ratio": "paired_pulse_ratio",
        "Stimulus Train (STP)": "stimulus_train_stp",
    },
    ui_params=[],
    plots=[],
)
def evoked_responses_module(**kwargs):
    """Module-level aggregator tab for evoked-response analyses."""
    return {}
