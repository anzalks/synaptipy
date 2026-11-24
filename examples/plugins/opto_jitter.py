# examples/plugins/opto_jitter.py
# -*- coding: utf-8 -*-
"""
Example Synaptipy Plugin: Optogenetic / Evoked Latency Jitter.

Measures the trial-to-trial variability (sample standard deviation, jitter) in
the latency from TTL stimulus pulses to evoked spikes or postsynaptic peak
deflections across sweeps (Sabatini & Regehr, 1999, Annu. Rev. Physiol.
61:521-542, doi:10.1146/annurev.physiol.61.1.521; Boyden et al., 2005, Nat.
Neurosci. 8:1263-1268, doi:10.1038/nn1525).

Usage
-----
This file is automatically discovered when placed in either:
- ``examples/plugins/`` (loaded out-of-the-box by Synaptipy)
- ``~/.synaptipy/plugins/`` (user copy, takes precedence over example)

The plugin requires a secondary channel carrying the TTL/digital stimulus
signal in addition to the primary signal channel.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from typing import Any, Dict, List, Tuple

import numpy as np

from synaptipy.core.analysis.evoked_responses import extract_ttl_epochs
from synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Part 1 - Pure analysis logic (no GUI imports)
# ---------------------------------------------------------------------------


def _first_spike_crossing_offset(
    v_trace: np.ndarray,
    win_start: int,
    win_end: int,
    spike_threshold: float,
) -> float:
    """Return sub-sample offset from ``win_start`` of first upward threshold crossing, or NaN."""
    window = v_trace[win_start:win_end]
    if window.size == 0:
        return float("nan")
    prev_val = float(v_trace[win_start - 1]) if win_start > 0 else float("-inf")
    padded = np.concatenate(([prev_val], window))
    upward = np.where((padded[:-1] <= spike_threshold) & (padded[1:] > spike_threshold))[0]
    if upward.size == 0:
        return float("nan")
    idx = int(upward[0])
    v0 = float(padded[idx])
    v1 = float(padded[idx + 1])
    if np.isfinite(v0) and v1 > v0:
        frac = (spike_threshold - v0) / (v1 - v0)
        return float(max(0.0, idx - 1.0 + frac))
    return float(idx)


def _peak_deflection_offset(
    v_trace: np.ndarray,
    ttl_onset_idx: int,
    win_start: int,
    win_end: int,
    sampling_rate: float,
) -> float:
    """Return sample offset from ``win_start`` of a prominent evoked EPSP/EPSC peak, or NaN."""
    window = v_trace[win_start:win_end]
    if window.size < 2:
        return float("nan")
    base_samples = max(5, int(round(0.010 * sampling_rate)))
    b0 = max(0, ttl_onset_idx - base_samples)
    b1 = max(b0 + 1, ttl_onset_idx)
    base_seg = v_trace[b0:b1]
    base_mean = float(np.mean(base_seg)) if base_seg.size > 0 else float(v_trace[0])
    base_sd = float(np.std(base_seg)) if base_seg.size > 1 else 0.0
    noise_floor = max(base_sd * 3.5, 0.25)

    centered = window - base_mean
    local_idx = int(np.argmax(np.abs(centered)))
    prominence = float( abs(centered[local_idx]) )
    if not np.isfinite(prominence) or prominence < noise_floor:
        return float("nan")
    return float(local_idx)


def _resolve_time_vector(time: Any, n_samples: int, sampling_rate: float) -> np.ndarray:
    """Resolve 1-D time vector of length ``n_samples`` from ndarray or multi-trial list."""
    cand = None
    if isinstance(time, (list, tuple)) and len(time) > 0 and time[0] is not None:
        cand = np.asarray(time[0], dtype=float).ravel()
    elif time is not None:
        try:
            cand = np.asarray(time, dtype=float).ravel()
        except (TypeError, ValueError):
            cand = None
    if cand is not None and cand.size >= n_samples:
        return cand[:n_samples]
    return np.arange(n_samples, dtype=float) / float(sampling_rate)


def _detect_ttl_onset_indices(
    ttl_sweep: np.ndarray,
    t_vec: np.ndarray,
    ttl_threshold: float,
) -> np.ndarray:
    """Return sample indices of rising TTL edges using adaptive midpoint fallback."""
    onsets_s, _ = extract_ttl_epochs(ttl_sweep, t_vec, threshold=ttl_threshold, auto_threshold=True)
    if onsets_s is None or len(onsets_s) == 0:
        return np.array([], dtype=int)
    idx = np.searchsorted(t_vec, onsets_s, side="left")
    return np.clip(idx, 0, len(ttl_sweep) - 1).astype(int)


def _scan_mode_latencies(
    data: np.ndarray,
    secondary_data: np.ndarray,
    t_vec: np.ndarray,
    ttl_threshold: float,
    search_start_samples: int,
    search_end_samples: int,
    spike_threshold: float,
    sampling_rate: float,
    mode: str,
) -> Tuple[List[float], List[int], int, List[float]]:
    """Collect ``(latencies_ms, event_indices, n_stim_events, canonical_onsets_s)``."""
    n_sweeps, n_samples = data.shape
    dt = 1.0 / sampling_rate
    latencies_ms: List[float] = []
    event_numbers: List[int] = []
    canonical_onsets: List[float] = []
    n_stim_events = 0
    stim_counter = 0

    for sweep_idx in range(n_sweeps):
        onset_indices = _detect_ttl_onset_indices(secondary_data[sweep_idx], t_vec, ttl_threshold)
        if onset_indices.size == 0:
            continue
        if not canonical_onsets:
            canonical_onsets = [float(t_vec[i]) for i in onset_indices]

        for pos_i, ttl_onset_idx in enumerate(onset_indices):
            stim_counter += 1
            n_stim_events += 1
            next_onset_idx = int(onset_indices[pos_i + 1]) if pos_i + 1 < len(onset_indices) else n_samples
            win_start = max(0, int(ttl_onset_idx) + search_start_samples)
            win_end = min(n_samples, next_onset_idx, int(ttl_onset_idx) + search_end_samples)
            if win_end <= win_start:
                continue

            if mode == "Peak Deflection":
                offset = _peak_deflection_offset(
                    data[sweep_idx], int(ttl_onset_idx), win_start, win_end, sampling_rate
                )
            else:
                offset = _first_spike_crossing_offset(data[sweep_idx], win_start, win_end, spike_threshold)

            if np.isnan(offset):
                continue
            latency_s = ((win_start - int(ttl_onset_idx)) + offset) * dt
            latencies_ms.append(latency_s * 1000.0)
            event_numbers.append(sweep_idx + 1 if onset_indices.size == 1 else stim_counter)

    return latencies_ms, event_numbers, n_stim_events, canonical_onsets


def _build_main_plot_overlays(
    mean_trace: np.ndarray,
    t_vec: np.ndarray,
    canonical_onsets: List[float],
    eff_start_s: float,
    search_end: float,
    spike_threshold: float,
    sampling_rate: float,
    mode_used: str,
) -> Dict[str, List[float]]:
    """Compute main-plot trigger lines, cyan window overlays, and response markers on the mean trace."""
    t_end = float(t_vec[-1]) if t_vec.size > 0 else 0.0
    win_starts: List[float] = []
    win_ends: List[float] = []
    det_times: List[float] = []
    det_amps: List[float] = []

    for i, onset_s in enumerate(canonical_onsets):
        next_s = canonical_onsets[i + 1] if i + 1 < len(canonical_onsets) else t_end
        ws = min(t_end, onset_s + eff_start_s)
        we = min(t_end, next_s, onset_s + search_end)
        if we <= ws:
            continue
        win_starts.append(float(ws))
        win_ends.append(float(we))

        i_on = int(np.searchsorted(t_vec, onset_s, side="left"))
        i0 = int(np.searchsorted(t_vec, ws, side="left"))
        i1 = max(i0 + 1, min(len(mean_trace), int(np.searchsorted(t_vec, we, side="right"))))
        seg = mean_trace[i0:i1]
        if seg.size == 0:
            continue

        if mode_used == "Threshold Crossing":
            off = _first_spike_crossing_offset(mean_trace, i0, i1, spike_threshold)
            pick_idx = min(len(mean_trace) - 1, i0 + int(round(off))) if np.isfinite(off) else i0 + int(np.argmax(seg))
        else:
            b0 = max(0, i_on - max(5, int(round(0.010 * sampling_rate))))
            base_val = float(np.mean(mean_trace[b0 : max(b0 + 1, i_on)]))
            pick_idx = i0 + int(np.argmax(np.abs(seg - base_val)))

        det_times.append(float(t_vec[pick_idx]))
        det_amps.append(float(mean_trace[pick_idx]))

    return {
        "_stim_onsets": canonical_onsets,
        "_window_starts_s": win_starts,
        "_window_ends_s": win_ends,
        "_detected_times": det_times,
        "_detected_amps": det_amps,
    }


def _coerce_sweep_matrix(raw: Any, label: str) -> tuple:
    """Convert a 1-D/2-D ndarray or list of 1-D sweeps into a 2-D float array without ValueError on ragged sweeps."""
    if raw is None:
        return None, f"Empty {label}", False
    if isinstance(raw, (list, tuple)):
        if len(raw) == 0:
            return np.array([], dtype=float), None, True
        sweeps = [np.asarray(sw, dtype=float).ravel() for sw in raw if sw is not None]
        if not sweeps:
            return np.array([], dtype=float), None, True
        lengths = [sw.size for sw in sweeps]
        min_len, max_len = min(lengths), max(lengths)
        if min_len == 0:
            return np.array([], dtype=float), None, True
        if min_len != max_len:
            if min_len < 2:
                return (
                    None,
                    f"Ragged sweep lengths in {label} have fewer than 2 common samples (min={min_len}, max={max_len})",
                    True,
                )
            log.warning(
                "Opto jitter: ragged sweep lengths in %s (min=%d, max=%d); truncating to %d samples.",
                label,
                min_len,
                max_len,
                min_len,
            )
            sweeps = [sw[:min_len] for sw in sweeps]
        return np.vstack(sweeps), None, True

    try:
        arr = np.asarray(raw, dtype=float)
    except ValueError as exc:
        return None, f"Invalid {label}: {exc}", False
    return arr, None, False


def calculate_opto_jitter(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    secondary_data: np.ndarray,
    ttl_threshold: float,
    search_start: float,
    search_end: float,
    spike_threshold: float,
    blanking_window: float = 1.0,
    detection_mode: str = "Threshold Crossing",
) -> Dict[str, Any]:
    """Compute per-stimulus response latencies from TTL onset and return jitter."""
    data, data_err, data_was_list = _coerce_sweep_matrix(data, "data array")
    if data_err:
        return {"error": data_err}
    secondary_data, sec_err, sec_was_list = _coerce_sweep_matrix(secondary_data, "secondary (TTL) channel")
    if sec_err:
        return {"error": sec_err}

    if data is None or data.size == 0:
        return {"error": "Empty data array"}
    if secondary_data is None or secondary_data.size == 0:
        return {"error": "Empty secondary (TTL) channel"}

    if data.ndim == 1:
        data = data[np.newaxis, :]
    if secondary_data.ndim == 1:
        secondary_data = secondary_data[np.newaxis, :]

    if (
        (data_was_list or sec_was_list)
        and data.shape[0] == secondary_data.shape[0]
        and data.shape[1] != secondary_data.shape[1]
    ):
        common_samples = min(data.shape[1], secondary_data.shape[1])
        if common_samples < 2:
            return {"error": f"Shape mismatch: data {data.shape} vs TTL {secondary_data.shape}"}
        data = data[:, :common_samples]
        secondary_data = secondary_data[:, :common_samples]

    n_sweeps, n_samples = data.shape
    if secondary_data.shape != data.shape:
        return {"error": f"Shape mismatch: data {data.shape} vs TTL {secondary_data.shape}"}

    t_vec = _resolve_time_vector(time, n_samples, sampling_rate)
    effective_search_start_s = max(search_start, max(0.0, blanking_window / 1000.0))
    search_start_samples = int(round(effective_search_start_s * sampling_rate))
    search_end_samples = int(round(search_end * sampling_rate))

    primary_mode = "Peak Deflection" if detection_mode == "Peak Deflection" else "Threshold Crossing"
    latencies_ms, sweep_numbers, n_stim_events, canonical_onsets = _scan_mode_latencies(
        data,
        secondary_data,
        t_vec,
        ttl_threshold,
        search_start_samples,
        search_end_samples,
        spike_threshold,
        sampling_rate,
        primary_mode,
    )
    mode_used = primary_mode

    if len(latencies_ms) < 2 and detection_mode == "Auto (Spikes or Peak)" and n_stim_events > 0:
        peak_lat, peak_nums, _, peak_onsets = _scan_mode_latencies(
            data,
            secondary_data,
            t_vec,
            ttl_threshold,
            search_start_samples,
            search_end_samples,
            spike_threshold,
            sampling_rate,
            "Peak Deflection",
        )
        if len(peak_lat) >= 2:
            latencies_ms = peak_lat
            sweep_numbers = peak_nums
            canonical_onsets = peak_onsets or canonical_onsets
            mode_used = "Peak Deflection"

    denom_events = n_stim_events if n_stim_events > 0 else n_sweeps
    overlays = _build_main_plot_overlays(
        np.mean(data, axis=0),
        t_vec,
        canonical_onsets,
        effective_search_start_s,
        search_end,
        spike_threshold,
        sampling_rate,
        mode_used,
    )

    if len(latencies_ms) < 2:
        n_detected = len(latencies_ms)
        n_failures = max(0, denom_events - n_detected)
        return {
            "error": (
                f"Too few stimuli with detected responses ({n_detected}/{denom_events}) "
                "to compute jitter - need at least 2."
            ),
            "metrics": {
                "Success Count": n_detected,
                "Failure Count": n_failures,
                "Response Probability (%)": (
                    round(n_detected / denom_events * 100.0, 2) if n_stim_events > 0 else 0.0
                ),
            },
            **overlays,
        }

    lat_arr = np.array(latencies_ms, dtype=float)
    jitter_val = float(np.std(lat_arr, ddof=1))
    mean_latency = float(np.mean(lat_arr))
    n_failures = max(0, denom_events - len(latencies_ms))
    resp_prob_pct = round(len(latencies_ms) / max(denom_events, 1) * 100.0, 2)

    return {
        "module_used": "opto_jitter",
        "metrics": {
            "Jitter_ms": round(jitter_val, 4),
            "Mean_Latency_ms": round(mean_latency, 4),
            "N_Sweeps_Detected": len(latencies_ms),
            "Success Count": len(latencies_ms),
            "Failure Count": n_failures,
            "Response Probability (%)": resp_prob_pct,
            "Detection_Mode_Used": mode_used,
        },
        "_sweep_numbers": np.array(sweep_numbers, dtype=float),
        "_latencies": lat_arr,
        **overlays,
    }


# ---------------------------------------------------------------------------
# Part 2 - Registry wrapper
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    name="opto_jitter",
    label="Opto Latency Jitter",
    expects_list=True,
    requires_multi_trial=True,
    requires_secondary_channel={
        "param_name": "secondary_data",
        "label": "TTL / Stimulus Channel:",
        "tooltip": "Select the TTL channel used to identify each optical or electrical stimulus onset.",
    },
    protocol_requirements={
        "families": ("single_stim", "paired_pulse", "stimulus_train", "optogenetic"),
        "requires_stimulus_timing": True,
        "requires_multi_trial": True,
        "description": "Verified stimulus timing across repeated sweeps",
    },
    ui_params=[
        {
            "name": "detection_mode",
            "label": "Detection Mode:",
            "type": "choice",
            "choices": ["Auto (Spikes or Peak)", "Threshold Crossing", "Peak Deflection"],
            "default": "Auto (Spikes or Peak)",
            "tooltip": (
                "Auto uses upward Spike Threshold crossing when suprathreshold spikes are present, "
                "falling back to evoked EPSP/EPSC peak latency for subthreshold responses."
            ),
        },
        {
            "name": "ttl_threshold",
            "label": "TTL Threshold (V/mV):",
            "type": "float",
            "default": 2.5,
            "min": -10000.0,
            "max": 10000.0,
            "decimals": 3,
            "tooltip": "TTL rising-edge threshold (auto-scales to midpoint if channel is recorded in mV).",
        },
        {
            "name": "search_start",
            "label": "Search Window Start (s):",
            "type": "float",
            "default": 0.001,
            "min": 0.0,
            "max": 10.0,
            "decimals": 4,
            "tooltip": "Start of the response-search window relative to TTL onset",
        },
        {
            "name": "search_end",
            "label": "Search Window End (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "max": 10.0,
            "decimals": 4,
            "tooltip": "End of the response-search window relative to TTL onset",
        },
        {
            "name": "blanking_window",
            "label": "Artifact Blanking Window (ms):",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 50.0,
            "decimals": 2,
            "tooltip": "Duration (ms) immediately after TTL onset ignored to exclude stimulus artifacts.",
        },
        {
            "name": "spike_threshold",
            "label": "Spike Threshold (mV):",
            "type": "float",
            "default": -20.0,
            "min": -200.0,
            "max": 200.0,
            "decimals": 2,
            "tooltip": "Voltage crossing level used in Threshold Crossing / Auto spike detection",
            "visible_when": {"param": "detection_mode", "value": "Threshold Crossing"},
        },
    ],
    plots=[
        {"type": "vlines", "data": "_stim_onsets"},
        {"type": "trace_overlay", "start_time": "_window_starts_s", "end_time": "_window_ends_s"},
        {"type": "markers", "x": "_detected_times", "y": "_detected_amps", "color": "#d62728", "symbol": "d"},
        {
            "type": "popup_xy",
            "title": "Response Latency per Stimulus",
            "x": "_sweep_numbers",
            "y": "_latencies",
            "x_label": "Stimulus / Sweep Index",
            "y_label": "Latency (ms)",
        },
    ],
)
def run_opto_jitter_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """Registry wrapper for opto_jitter."""
    secondary_data = kwargs.get("secondary_data", np.array([]))
    return calculate_opto_jitter(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        secondary_data=secondary_data,
        ttl_threshold=float(kwargs.get("ttl_threshold", 2.5)),
        search_start=float(kwargs.get("search_start", 0.001)),
        search_end=float(kwargs.get("search_end", 0.05)),
        spike_threshold=float(kwargs.get("spike_threshold", -20.0)),
        blanking_window=float(kwargs.get("blanking_window", 1.0)),
        detection_mode=str(kwargs.get("detection_mode", "Auto (Spikes or Peak)")),
    )
