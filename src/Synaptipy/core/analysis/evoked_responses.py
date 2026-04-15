# src/Synaptipy/core/analysis/evoked_responses.py
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

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.analysis.single_spike import detect_spikes_threshold
from Synaptipy.core.analysis.synaptic_events import detect_events_template, detect_events_threshold
from Synaptipy.core.results import AnalysisResult

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
            if data_range > 0:
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
        """Return (peak_amplitude, raw_peak_value) relative to baseline."""
        win_start = _nearest_idx(stim_onset_s)
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
    try:
        # Fit in the direction of the event
        if polarity == "negative":
            popt, _ = curve_fit(
                _mono_exp,
                t_fit,
                y_fit,
                p0=[-a0, tau0, bl1],
                bounds=([-a0 * 20, 0.1, bl1 - r1_amp * 2], [0.0, tau0 * 50, bl1 + r1_amp]),
                maxfev=3000,
            )
        else:
            popt, _ = curve_fit(
                _mono_exp,
                t_fit,
                y_fit,
                p0=[a0, tau0, bl1],
                bounds=([0.0, 0.1, bl1 - r1_amp], [a0 * 20, tau0 * 50, bl1 + r1_amp * 2]),
                maxfev=3000,
            )
        tau_ms = float(popt[1])
        out["decay_tau_ms"] = tau_ms
        # Evaluate decay at stim2_onset
        t_at_stim2_ms = (stim2_onset_s - time[i_fit0]) * 1000.0
        residual_at_stim2 = float(_mono_exp(t_at_stim2_ms, *popt)) - bl1
        out["residual_at_stim2"] = residual_at_stim2
    except Exception as exc:
        log.warning("PPR decay fit failed: %s", exc)
        out["ppr_error"] = f"Decay fit failed: {exc}"

    # --- R2 ---
    bl2 = _local_baseline(stim2_onset_s)
    r2_amp_raw, r2_peak_raw = _response_peak(stim2_onset_s, bl2)
    out["r2_amplitude_raw"] = r2_amp_raw

    # Subtract residual decay from R2 to get corrected amplitude
    if polarity == "negative":
        # The residual decay raises the apparent baseline under R2
        corrected_bl2 = bl2 + residual_at_stim2
    else:
        corrected_bl2 = bl2 + residual_at_stim2

    if polarity == "negative":
        r2_corrected = corrected_bl2 - r2_peak_raw
    else:
        r2_corrected = r2_peak_raw - corrected_bl2

    out["r2_amplitude_corrected"] = float(r2_corrected)

    if r1_amp > 0:
        out["paired_pulse_ratio"] = float(r2_corrected) / r1_amp

    return out


# ---------------------------------------------------------------------------
# Registry Wrapper
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    name="optogenetic_sync",
    label="Optogenetic Synchronization",
    requires_secondary_channel={
        "param_name": "ttl_data",
        "label": "TTL Channel:",
        "tooltip": "Select the digital/TTL channel containing optical stimulus pulses.",
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
            "visible_when": {"param": "event_detection_type", "value": "Events (Template)"},
        },
        {
            "name": "response_polarity",
            "type": "choice",
            "label": "Peak Polarity:",
            "choices": ["max", "min", "abs"],
            "default": "max",
            "tooltip": "Direction to search for peak response voltage within the window.",
        },
    ],
    plots=[
        {"name": "Trace", "type": "trace", "show_events": True},
        {"type": "vlines", "data": "stimulus_onsets", "color": "c"},
        {"type": "markers", "x": "_peak_times", "y": "_peak_amps", "color": "y", "symbol": "d"},
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
    event_detection_type = kwargs.get("event_detection_type", "Spikes")
    response_polarity = kwargs.get("response_polarity", "max")

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
            ev_result = detect_events_template(
                data=data,
                sampling_rate=sampling_rate,
                threshold_std=threshold_sd,
                tau_rise=tau_rise,
                tau_decay=tau_decay,
                polarity=direction,
                time=time,
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
        log.debug("No TTL data provided; using voltage trace as fallback for TTL edge detection.")
        ttl_data = data

    result = calculate_optogenetic_sync(
        ttl_data=ttl_data,
        action_potential_times=ap_times,
        time=time,
        ttl_threshold=ttl_threshold,
        response_window_ms=response_window_ms,
    )

    if not result.is_valid:
        return {"module_used": "evoked_responses", "metrics": {"error": result.error_message}}

    # Find peak response voltage within each TTL stimulus window
    _peak_times: List[float] = []
    _peak_amps: List[float] = []
    _window_s = response_window_ms / 1000.0
    if result.stimulus_onsets is not None and len(data) > 0:
        for _onset in result.stimulus_onsets:
            _idx_start = int(np.searchsorted(time, _onset, side="left"))
            _idx_end = int(np.searchsorted(time, _onset + _window_s, side="right"))
            _idx_start = max(0, min(_idx_start, len(data) - 1))
            _idx_end = max(_idx_start + 1, min(_idx_end, len(data)))
            _window_data = data[_idx_start:_idx_end]
            if len(_window_data) > 0:
                if response_polarity == "min":
                    _local_idx = int(np.argmin(_window_data))
                elif response_polarity == "abs":
                    _local_idx = int(np.argmax(np.abs(_window_data)))
                else:
                    _local_idx = int(np.argmax(_window_data))
                _abs_idx = _idx_start + _local_idx
                _peak_times.append(float(time[_abs_idx]))
                _peak_amps.append(float(data[_abs_idx]))

    # Response probability as a percentage for human-readable reporting.
    resp_prob_pct = round(result.response_probability * 100.0, 2) if result.response_probability is not None else np.nan

    return {
        "module_used": "evoked_responses",
        "metrics": {
            "optical_latency_ms": result.optical_latency_ms,
            "response_probability": result.response_probability,
            "Response Probability (%)": resp_prob_pct,
            "spike_jitter_ms": result.spike_jitter_ms,
            "stimulus_count": result.stimulus_count,
            "Success Count": result.success_count,
            "Failure Count": result.failure_count,
            "event_count": len(ap_times),
            "event_times": ap_times.tolist() if hasattr(ap_times, "tolist") else list(ap_times),
            "stimulus_onsets": (result.stimulus_onsets.tolist() if result.stimulus_onsets is not None else []),
            "_peak_times": _peak_times,
            "_peak_amps": _peak_amps,
        },
    }


# ---------------------------------------------------------------------------
# PPR Registry Wrapper
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    "paired_pulse_ratio",
    label="Paired-Pulse Ratio",
    plots=[
        {"name": "Trace", "type": "trace"},
        {"type": "vlines", "data": "_stim_onsets", "color": "c"},
    ],
    ui_params=[
        {
            "name": "stim1_onset_s",
            "label": "Stim 1 Onset (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "stim2_onset_s",
            "label": "Stim 2 Onset (s):",
            "type": "float",
            "default": 0.2,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "polarity",
            "label": "Event Polarity:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
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
            "tooltip": "Offset from Stim1 onset to begin fitting the decay (skip initial transient).",
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
    ],
)
def run_ppr_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """Wrapper for Paired-Pulse Ratio analysis with residual decay subtraction."""
    stim1_onset_s = float(kwargs.get("stim1_onset_s", 0.1))
    stim2_onset_s = float(kwargs.get("stim2_onset_s", 0.2))
    polarity = kwargs.get("polarity", "negative")
    response_window_ms = float(kwargs.get("response_window_ms", 20.0))
    baseline_window_ms = float(kwargs.get("baseline_window_ms", 5.0))
    fit_decay_from_ms = float(kwargs.get("fit_decay_from_ms", 5.0))
    fit_decay_window_ms = float(kwargs.get("fit_decay_window_ms", 30.0))

    result = calculate_paired_pulse_ratio(
        data=data,
        time=time,
        stim1_onset_s=stim1_onset_s,
        stim2_onset_s=stim2_onset_s,
        response_window_ms=response_window_ms,
        baseline_window_ms=baseline_window_ms,
        fit_decay_from_ms=fit_decay_from_ms,
        fit_decay_window_ms=fit_decay_window_ms,
        polarity=polarity,
    )

    return {
        "module_used": "evoked_responses",
        "metrics": {
            "r1_amplitude": result["r1_amplitude"],
            "r2_amplitude_raw": result["r2_amplitude_raw"],
            "r2_amplitude_corrected": result["r2_amplitude_corrected"],
            "residual_at_stim2": result["residual_at_stim2"],
            "paired_pulse_ratio": result["paired_pulse_ratio"],
            "decay_tau_ms": result["decay_tau_ms"],
            "ppr_error": result["ppr_error"],
            "_stim_onsets": [stim1_onset_s, stim2_onset_s],
        },
    }


# ---------------------------------------------------------------------------
# Module-level tab aggregator
# ---------------------------------------------------------------------------
@AnalysisRegistry.register(
    "evoked_responses",
    label="Optogenetics",
    requires_secondary_channel={
        "param_name": "ttl_data",
        "label": "TTL Channel:",
        "tooltip": "Select the digital/TTL channel containing optical stimulus pulses.",
    },
    method_selector={
        "Optogenetic Sync": "optogenetic_sync",
        "Paired-Pulse Ratio": "paired_pulse_ratio",
    },
    ui_params=[],
    plots=[],
)
def evoked_responses_module(**kwargs):
    """Module-level aggregator tab for evoked-response analyses."""
    return {}
