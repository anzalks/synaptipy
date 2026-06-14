# src/Synaptipy/core/analysis/single_spike.py
# -*- coding: utf-8 -*-
"""
Core Protocol Module 2: Single Spike Analysis.

Consolidates: Spike Detection, AP Characterisation (threshold, amplitude,
half-width, rise/decay times, AHP) and Phase Plane (dV/dt vs V) analysis.

All registry wrapper functions return::

    {
        "module_used": "single_spike",
        "metrics": { ... flat result keys ... }
    }
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.signal import savgol_filter

from Synaptipy.core.analysis.passive_properties import apply_ljp_correction
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.constants import DVDT_ARTIFACT_CEILING_VS, DVDT_THRESHOLD_VS, MIN_RISING_PHASE_MS
from Synaptipy.core.results import SpikeTrainResult

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spike Detection
# ---------------------------------------------------------------------------


def detect_spikes_threshold(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    threshold: float,
    refractory_samples: int,
    peak_search_window_samples: int = None,
    parameters: Dict[str, Any] = None,
    dvdt_threshold: float = 20.0,  # Default: DVDT_THRESHOLD_VS (Bean 2007)
) -> SpikeTrainResult:
    """
    Detect action potentials using a two-stage dV/dt-threshold crossing algorithm.

    Algorithm
    ---------
    1. **First-derivative computation**: :func:`numpy.gradient` is applied to
       *data* with sample spacing ``dt = time[1] - time[0]`` (s), yielding
       dV/dt in mV s⁻¹.
    2. **dV/dt crossing detection**: candidate spike onsets are identified as
       upward crossings of ``dvdt_threshold * 1000`` (mV s⁻¹).  Each
       crossing is the sample where dV/dt transitions from strictly below to
       at-or-above the threshold.
    3. **Refractory period enforcement**: candidate crossings separated by
       fewer than *refractory_samples* are suppressed, retaining only the
       first crossing in each refractory interval (greedy forward scan).
    4. **Peak localisation**: for each accepted onset, the voltage maximum
       within the next *peak_search_window_samples* is found.  The candidate
       is accepted as a spike only if ``data[peak_idx] >= threshold`` (mV).

    Parameters
    ----------
    data : np.ndarray
        1-D voltage array (mV).
    time : np.ndarray
        1-D time array aligned with *data* (s).
    threshold : float
        Minimum voltage a candidate peak must reach to be accepted as a
        spike (mV).  Guards against sub-threshold dV/dt transients.
    refractory_samples : int
        Minimum number of samples between successive accepted spike onsets.
        Convert from time: ``int(refractory_period_s * sampling_rate_hz)``.
    peak_search_window_samples : int, optional
        Number of samples to search forward from each onset crossing for the
        voltage peak.  Defaults to *refractory_samples* when ``None``.
    parameters : dict, optional
        Arbitrary parameter dict stored verbatim in the returned
        :class:`~Synaptipy.core.results.SpikeTrainResult` for provenance.
    dvdt_threshold : float, optional
        dV/dt threshold for onset detection (V s⁻¹, default 20.0).
        Converted internally to mV s⁻¹ by multiplication with 1000.

    Returns
    -------
    SpikeTrainResult
        Attributes populated on success:

        * ``value`` (int) – total spike count.
        * ``spike_times`` (np.ndarray) – peak times (s).
        * ``spike_indices`` (np.ndarray) – peak sample indices.
        * ``mean_frequency`` (float) – mean instantaneous firing rate
          ``(n_spikes - 1) / (t_last - t_first)`` (Hz); 0.0 for ≤ 1 spike.
        * ``is_valid`` (bool) – ``False`` when input arrays are malformed.
    """
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size < 2:
        return SpikeTrainResult(
            value=0, unit="spikes", is_valid=False, error_message="Invalid data array", parameters=parameters or {}
        )
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        return SpikeTrainResult(
            value=0,
            unit="spikes",
            is_valid=False,
            error_message="Time and data mismatch",
            parameters=parameters or {},
        )
    if not isinstance(threshold, (int, float)):
        return SpikeTrainResult(
            value=0,
            unit="spikes",
            is_valid=False,
            error_message="Threshold must be numeric",
            parameters=parameters or {},
        )
    if not isinstance(refractory_samples, int) or refractory_samples < 0:
        return SpikeTrainResult(
            value=0,
            unit="spikes",
            is_valid=False,
            error_message="Invalid refractory period",
            parameters=parameters or {},
        )

    try:
        dt = time[1] - time[0] if len(time) > 1 else 1.0
        dvdt = np.gradient(data, dt)
        dvdt_thresh_mvs = dvdt_threshold * 1000.0

        crossings = np.where((dvdt[:-1] < dvdt_thresh_mvs) & (dvdt[1:] >= dvdt_thresh_mvs))[0] + 1
        if crossings.size == 0:
            return SpikeTrainResult(
                value=0,
                unit="spikes",
                spike_times=np.array([]),
                spike_indices=np.array([]),
                parameters=parameters or {},
            )

        if refractory_samples <= 0:
            valid_crossing_indices = crossings
        else:
            valid_crossings_list = [crossings[0]]
            last_crossing_idx = crossings[0]
            for idx in crossings[1:]:
                if (idx - last_crossing_idx) >= refractory_samples:
                    valid_crossings_list.append(idx)
                    last_crossing_idx = idx
            valid_crossing_indices = np.array(valid_crossings_list)

        if valid_crossing_indices.size == 0:
            return SpikeTrainResult(
                value=0,
                unit="spikes",
                spike_times=np.array([]),
                spike_indices=np.array([]),
                parameters=parameters or {},
            )

        peak_indices_list = []
        if peak_search_window_samples is None:
            peak_search_window_samples = (
                refractory_samples if refractory_samples > 0 else int(0.005 / (time[1] - time[0]))
            )

        for crossing_idx in valid_crossing_indices:
            search_start = crossing_idx
            search_end = min(crossing_idx + peak_search_window_samples, len(data))
            if search_start >= search_end:
                peak_idx = crossing_idx
            else:
                try:
                    relative_peak_idx = np.argmax(data[search_start:search_end])
                    peak_idx = search_start + relative_peak_idx
                except ValueError:
                    peak_idx = crossing_idx

            if data[peak_idx] >= threshold:
                peak_indices_list.append(peak_idx)

        peak_indices_arr = np.array(peak_indices_list).astype(int)
        peak_times_arr = time[peak_indices_arr]

        mean_freq = 0.0
        if len(peak_times_arr) > 1:
            spike_span = peak_times_arr[-1] - peak_times_arr[0]
            if spike_span > 0:
                mean_freq = (len(peak_times_arr) - 1) / spike_span

        return SpikeTrainResult(
            value=len(peak_indices_arr),
            unit="spikes",
            spike_times=peak_times_arr,
            spike_indices=peak_indices_arr,
            mean_frequency=mean_freq,
            parameters=parameters or {},
        )

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error during spike detection: {e}", exc_info=True)
        return SpikeTrainResult(
            value=0, unit="spikes", is_valid=False, error_message=str(e), parameters=parameters or {}
        )


# ---------------------------------------------------------------------------
# AP Feature Extraction
# ---------------------------------------------------------------------------


def calculate_spike_features(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    spike_indices: np.ndarray,
    dvdt_threshold: float = 20.0,
    ahp_window_sec: float = 0.05,
    onset_lookback: float = 0.01,
    fahp_window_ms: Tuple[float, float] = (1.0, 5.0),
    mahp_window_ms: Tuple[float, float] = (10.0, 50.0),
) -> List[Dict[str, Any]]:
    """
    Calculate detailed features for each detected spike (vectorised NumPy).

    Returns list of dicts per spike: ap_threshold, amplitude, half_width,
    rise_time_10_90, decay_time_90_10, fahp_depth, mahp_depth,
    ahp_duration_half, adp_amplitude, max_dvdt, min_dvdt.

    AP threshold is detected via the peak of d2V/dt2 in the pre-spike lookback
    window (maximum curvature method).  Falls back to the first dV/dt crossing
    above ``dvdt_threshold`` when d2V/dt2 gives a boundary result.

    Args:
        data: 1-D voltage array (mV).
        time: Corresponding time array (s).
        spike_indices: Array of sample indices for each spike peak.
        dvdt_threshold: Fallback dV/dt threshold for AP onset (V/s).
        ahp_window_sec: Duration of AHP/ADP search window (s).
        onset_lookback: Lookback window before each spike peak (s).
        fahp_window_ms: (start, end) of fast-AHP window after peak (ms).
        mahp_window_ms: (start, end) of medium-AHP window after peak (ms).
    """
    if spike_indices is None or spike_indices.size == 0:
        return []

    spike_indices = np.asarray(spike_indices, dtype=int)
    n_spikes = len(spike_indices)
    n_data = len(data)
    if n_data < 2:
        return []

    dt = time[1] - time[0]
    if dt <= 0:
        log.warning("Invalid time vector (dt <= 0). Cannot calculate features.")
        return []

    dvdt = np.gradient(data, dt)
    d2vdt2 = np.gradient(dvdt, dt)

    lookback_samples = int(onset_lookback / dt)
    post_peak_samples = int(0.01 / dt)
    ahp_max_samples = int(ahp_window_sec / dt)

    # --- AP Threshold (onset) via dV/dt threshold crossing ---
    # The true physiological base of the action potential is standardly defined
    # as the point where the rising phase crosses a specific dV/dt threshold (e.g. 20 V/s).
    # The previous maximum curvature (d2vdt2) method was erroneously flagging the middle 
    # of the upstroke due to extreme voltage acceleration.
    lookback_range = np.arange(-lookback_samples, 0)
    onset_window_indices = spike_indices[:, None] + lookback_range
    np.clip(onset_window_indices, 0, n_data - 1, out=onset_window_indices)

    onset_dvdt_windows = dvdt[onset_window_indices]
    
    # We use the explicit dvdt_threshold parameter (converted to mV/s) to find the onset.
    target_thresh_mvs = dvdt_threshold * 1000.0
    crossings_mask = onset_dvdt_windows > target_thresh_mvs
    has_crossing = np.any(crossings_mask, axis=1)
    
    # We want the FIRST crossing in the lookback window.
    first_crossing_rel_idx = np.argmax(crossings_mask, axis=1)
    
    # If no crossing is found (e.g. extremely slow spike), fallback to a fixed window before peak.
    fallback_indices = np.maximum(0, spike_indices - int(0.002 / dt))
    
    found_thresh_indices = onset_window_indices[np.arange(n_spikes), first_crossing_rel_idx]
    thresh_indices = np.where(has_crossing, found_thresh_indices, fallback_indices)
    ap_thresholds = data[thresh_indices]

    # Biological QC on detected thresholds: flag as NaN when the
    # per-spike peak rising rate exceeds 300 V/s (artifact ceiling) or the
    # threshold-to-peak rising phase is shorter than 0.1 ms (false detection).
    onset_max_dvdt = np.max(onset_dvdt_windows, axis=1)
    rising_phase_s = (spike_indices - thresh_indices) * dt
    at_edge = (first_crossing_rel_idx == 0)
    artifact_flag = at_edge & (
        (onset_max_dvdt > DVDT_ARTIFACT_CEILING_VS * 1000.0) | (rising_phase_s < MIN_RISING_PHASE_MS / 1000.0)
    )
    ap_thresholds = np.where(artifact_flag, np.nan, ap_thresholds)

    peak_vals = data[spike_indices]
    amplitudes = peak_vals - ap_thresholds

    # --- Full waveform window ---
    full_window_len = lookback_samples + post_peak_samples
    full_window_range = np.arange(-lookback_samples, post_peak_samples)
    full_window_indices = spike_indices[:, None] + full_window_range
    np.clip(full_window_indices, 0, n_data - 1, out=full_window_indices)
    waveforms = data[full_window_indices]

    amp_50 = ap_thresholds + 0.5 * amplitudes
    amp_10 = ap_thresholds + 0.1 * amplitudes
    amp_90 = ap_thresholds + 0.9 * amplitudes

    half_widths = np.full(n_spikes, np.nan)
    rise_times = np.full(n_spikes, np.nan)
    decay_times = np.full(n_spikes, np.nan)

    rel_peak = lookback_samples
    col_indices = np.arange(full_window_len)
    is_pre_peak = col_indices < rel_peak
    is_post_peak = col_indices > rel_peak

    lev_50 = amp_50[:, None]
    idxs = np.tile(col_indices, (n_spikes, 1))

    temp_mask = is_pre_peak & (waveforms <= lev_50)
    has_pre_50 = np.any(temp_mask, axis=1)
    masked_idxs_pre = np.where(temp_mask, idxs, -1)
    idx_rise_50_rel = np.max(masked_idxs_pre, axis=1)

    temp_mask_post = is_post_peak & (waveforms <= lev_50)
    has_post_50 = np.any(temp_mask_post, axis=1)
    masked_idxs_post = np.where(temp_mask_post, idxs, 999999)
    idx_fall_50_rel = np.min(masked_idxs_post, axis=1)

    valid_width = has_pre_50 & has_post_50 & (idx_rise_50_rel != -1) & (idx_fall_50_rel != 999999)
    
    half_widths[valid_width] = (
        (idx_fall_50_rel[valid_width] - idx_rise_50_rel[valid_width])
        * dt
        * 1000.0
    )

    lev_10 = amp_10[:, None]
    lev_90 = amp_90[:, None]
    mask_10 = is_pre_peak & (waveforms <= lev_10)
    valid_10 = np.any(mask_10, axis=1)
    idx_10_rel = np.max(np.where(mask_10, idxs, -1), axis=1)
    mask_90 = is_pre_peak & (waveforms <= lev_90)
    valid_90 = np.any(mask_90, axis=1)
    idx_90_rel = np.max(np.where(mask_90, idxs, -1), axis=1)
    valid_rise = valid_10 & valid_90 & (idx_90_rel > idx_10_rel)
    
    rise_times[valid_rise] = (
        (idx_90_rel[valid_rise] - idx_10_rel[valid_rise])
        * dt
        * 1000.0
    )

    mask_dec_90 = is_post_peak & (waveforms <= lev_90)
    valid_dec_90 = np.any(mask_dec_90, axis=1)
    idx_dec_90_rel = np.min(np.where(mask_dec_90, idxs, 999999), axis=1)
    mask_dec_10 = is_post_peak & (waveforms <= lev_10)
    valid_dec_10 = np.any(mask_dec_10, axis=1)
    idx_dec_10_rel = np.min(np.where(mask_dec_10, idxs, 999999), axis=1)
    valid_decay = valid_dec_90 & valid_dec_10 & (idx_dec_10_rel > idx_dec_90_rel)
    
    decay_times[valid_decay] = (
        (idx_dec_10_rel[valid_decay] - idx_dec_90_rel[valid_decay])
        * dt
        * 1000.0
    )

    # --- AHP ---
    ahp_max_samples_per_spike = np.full(n_spikes, ahp_max_samples)
    if n_spikes > 1:
        dist_to_next = spike_indices[1:] - spike_indices[:-1]
        ahp_max_samples_per_spike[:-1] = np.minimum(ahp_max_samples, dist_to_next)

    ahp_range = np.arange(0, ahp_max_samples)
    ahp_indices = spike_indices[:, None] + ahp_range
    np.clip(ahp_indices, 0, n_data - 1, out=ahp_indices)
    ahp_waveforms = data[ahp_indices]

    col_idxs_ahp = np.tile(np.arange(ahp_max_samples), (n_spikes, 1))
    valid_ahp_mask = col_idxs_ahp < ahp_max_samples_per_spike[:, None]

    window_length = int(0.005 / dt)
    if window_length % 2 == 0:
        window_length += 1
    window_length = max(5, window_length)
    # Cap to trace width; if cap makes it even, step down to next odd so the
    # Savitzky-Golay constraint (window > polyorder=3) is preserved.
    n_cols = ahp_waveforms.shape[1]
    max_win = n_cols if n_cols % 2 == 1 else max(1, n_cols - 1)
    window_length = min(window_length, max_win)
    if window_length % 2 == 0:
        window_length = max(1, window_length - 1)

    if ahp_waveforms.shape[1] >= window_length and window_length >= 5:
        smoothed_ahp = savgol_filter(ahp_waveforms, window_length, 3, axis=1)
    else:
        smoothed_ahp = ahp_waveforms

    temp_ahp = smoothed_ahp.copy()
    temp_ahp[~valid_ahp_mask] = np.inf
    ahp_min_rel_indices = np.argmin(temp_ahp, axis=1)

    mean_window = int(0.001 / dt)
    ahp_min_vals = np.zeros(n_spikes)
    for i in range(n_spikes):
        idx = ahp_min_rel_indices[i]
        start = max(0, idx - mean_window)
        end = min(ahp_max_samples_per_spike[i], idx + mean_window + 1)
        ahp_min_vals[i] = np.mean(ahp_waveforms[i, start:end])

    rec_targets = ap_thresholds - 0.1 * amplitudes
    rec_target_bcast = rec_targets[:, None]
    is_after_min = col_idxs_ahp > ahp_min_rel_indices[:, None]
    is_recovered = ahp_waveforms >= rec_target_bcast
    valid_recovery = is_after_min & is_recovered & valid_ahp_mask
    has_recovery = np.any(valid_recovery, axis=1)
    rec_rel_indices = np.where(has_recovery, np.argmax(valid_recovery, axis=1), ahp_max_samples)

    thresh_bcast = ap_thresholds[:, None]
    is_below_thresh_ahp = ahp_waveforms < thresh_bcast
    has_ap_end = np.any(is_below_thresh_ahp, axis=1)
    ap_end_rel_indices = np.where(has_ap_end, np.argmax(is_below_thresh_ahp, axis=1), 0)

    ahp_durations = np.full(n_spikes, np.nan)
    valid_ahp_dur = has_recovery & has_ap_end & (rec_rel_indices > ap_end_rel_indices)
    ahp_durations[valid_ahp_dur] = (rec_rel_indices[valid_ahp_dur] - ap_end_rel_indices[valid_ahp_dur]) * dt * 1000.0

    # --- ADP ---
    adp_amplitudes = np.full(n_spikes, np.nan)
    if ahp_max_samples > 2:
        val_mid = ahp_waveforms[:, 1:-1]
        val_left = ahp_waveforms[:, :-2]
        val_right = ahp_waveforms[:, 2:]
        is_local_max_inner = (val_mid > val_left) & (val_mid > val_right)
        is_local_max = np.pad(is_local_max_inner, ((0, 0), (1, 1)), mode="constant", constant_values=False)
        col_idxs2 = np.tile(np.arange(ahp_max_samples), (n_spikes, 1))
        valid_adp_mask = is_local_max & (col_idxs2 > ap_end_rel_indices[:, None]) & (col_idxs2 < ahp_max_samples_per_spike[:, None])
        has_adp = np.any(valid_adp_mask, axis=1)
        temp_vals = ahp_waveforms.copy()
        temp_vals[~valid_adp_mask] = -np.inf
        adp_peaks = np.max(temp_vals, axis=1)
        calced_adps = adp_peaks - ahp_min_vals
        adp_amplitudes = np.where(has_adp, calced_adps, np.nan)

    # --- fAHP and mAHP (separate physiological windows) ---
    # fAHP: fast AHP (default 1-5 ms post-peak): Na+ channel-mediated repolarisation overshoot
    # mAHP: medium AHP (default 10-50 ms post-peak): K+ channel-mediated hyperpolarisation
    fahp_start = max(1, int(fahp_window_ms[0] / 1000.0 / dt))
    fahp_end = max(fahp_start + 1, int(fahp_window_ms[1] / 1000.0 / dt))
    mahp_start = max(1, int(mahp_window_ms[0] / 1000.0 / dt))
    mahp_end = max(mahp_start + 1, int(mahp_window_ms[1] / 1000.0 / dt))

    def _window_min(start_s: int, end_s: int) -> np.ndarray:
        """Return per-spike min voltage in [peak+start_s, peak+end_s)."""
        w_len = end_s - start_s
        if w_len <= 0:
            return np.full(n_spikes, np.nan)
        w_range = np.arange(start_s, end_s)
        w_indices = spike_indices[:, None] + w_range
        np.clip(w_indices, 0, n_data - 1, out=w_indices)
        return np.min(data[w_indices], axis=1)

    fahp_min_vals = _window_min(fahp_start, fahp_end)
    mahp_min_vals = _window_min(mahp_start, mahp_end)
    fahp_depths = ap_thresholds - fahp_min_vals
    mahp_depths = ap_thresholds - mahp_min_vals

    # --- max/min dV/dt ---
    raw_dvdt = np.gradient(waveforms, axis=1) / dt / 1000.0
    
    # Apply a dynamic sampling-rate dependent rolling window (standard ~0.1 ms)
    # to smooth the derivative, matching standard IPFX/eFEL smoothing behavior
    # and preventing single-sample noise spikes from inflating the rate.
    window_ms = 0.1
    window_size = max(3, int(window_ms / (dt * 1000.0)))
    if window_size % 2 == 0:
        window_size += 1
        
    kernel = np.ones(window_size) / window_size
    from scipy.ndimage import convolve1d
    full_dvdt = convolve1d(raw_dvdt, kernel, axis=1, mode='nearest')
    
    # Calculate column indices of thresholds
    rel_thresh_indices = thresh_indices - (spike_indices - lookback_samples)
    
    # max dV/dt strictly between threshold and peak
    valid_rise_mask = is_pre_peak[None, :] & (col_indices[None, :] >= rel_thresh_indices[:, None])
    pre_peak_dvdt = np.where(valid_rise_mask, full_dvdt, -np.inf)
    
    # min dV/dt after peak
    post_peak_dvdt = np.where(is_post_peak[None, :], full_dvdt, np.inf)
    
    max_dvdts = np.max(pre_peak_dvdt, axis=1)
    min_dvdts = np.min(post_peak_dvdt, axis=1)

    features_list = []
    for i in range(n_spikes):
        features_list.append(
            {
                "ap_threshold": float(ap_thresholds[i]),
                "amplitude": float(amplitudes[i]),
                "half_width": float(half_widths[i]),
                "rise_time_10_90": float(rise_times[i]),
                "decay_time_90_10": float(decay_times[i]),
                "fahp_depth": float(fahp_depths[i]),
                "mahp_depth": float(mahp_depths[i]),
                "ahp_duration_half": float(ahp_durations[i]),
                "adp_amplitude": float(adp_amplitudes[i]),
                "max_dvdt": float(max_dvdts[i]),
                "min_dvdt": float(min_dvdts[i]),
                "absolute_peak_mv": float(peak_vals[i]),
                "overshoot_mv": float(max(0.0, peak_vals[i])),
            }
        )
    return features_list


def calculate_isi(spike_times: np.ndarray) -> np.ndarray:
    """Return inter-spike intervals from spike_times array."""
    if len(spike_times) < 2:
        return np.array([])
    return np.diff(spike_times)


def analyze_multi_sweep_spikes(
    data_trials: List[np.ndarray],
    time_vector: np.ndarray,
    threshold: float,
    refractory_samples: int,
    dvdt_threshold: float = 20.0,
) -> List[SpikeTrainResult]:
    """Detect spikes across multiple sweeps."""
    results = []
    for i, trial_data in enumerate(data_trials):
        try:
            result = detect_spikes_threshold(
                trial_data, time_vector, threshold, refractory_samples, dvdt_threshold=dvdt_threshold
            )
            result.metadata["sweep_index"] = i
            results.append(result)
        except (ValueError, TypeError, KeyError, IndexError) as e:
            log.error(f"Error analyzing sweep {i}: {e}")
            error_result = SpikeTrainResult(
                value=0, unit="spikes", is_valid=False, error_message=f"Sweep {i}: {str(e)}"
            )
            error_result.metadata["sweep_index"] = i
            results.append(error_result)
    return results


# ---------------------------------------------------------------------------
# Phase Plane (dV/dt vs V)
# ---------------------------------------------------------------------------


def calculate_dvdt(voltage: np.ndarray, sampling_rate: float, sigma_ms: float = 0.1) -> np.ndarray:
    """
    Calculate dV/dt (V/s) with optional Savitzky-Golay smoothing.

    Computes the raw derivative first, then applies a Savitzky-Golay filter
    (polynomial order 3) directly to the derivative array.  This preserves
    the true max dV/dt better than pre-smoothing the voltage with a Gaussian,
    which attenuates the sharp upstroke of action potentials.

    Args:
        voltage: 1D voltage array (mV).
        sampling_rate: Sampling rate (Hz).
        sigma_ms: Smoothing window (ms). The SG window length is derived as
            ``max(5, int(sigma_ms / 1000 * sampling_rate))``, rounded up to the
            next odd integer.  Set to 0 for no smoothing.

    Returns:
        1D array of dV/dt in V/s.
    """
    dt = 1.0 / sampling_rate
    dvdt = np.gradient(voltage, dt) / 1000.0  # mV/s -> V/s

    if sigma_ms > 0 and len(dvdt) >= 5:
        # Dynamic window length derived from sigma_ms and sampling rate (must be odd >= 5)
        window_samples = max(5, int(sigma_ms / 1000.0 * sampling_rate))
        if window_samples % 2 == 0:
            window_samples += 1
        # Cap at signal length (savgol_filter requires window <= len)
        window_samples = min(window_samples, len(dvdt) if len(dvdt) % 2 == 1 else len(dvdt) - 1)
        if window_samples >= 5:
            dvdt = savgol_filter(dvdt, window_samples, 3)

    return dvdt


def get_phase_plane_trajectory(
    voltage: np.ndarray, sampling_rate: float, sigma_ms: float = 0.1
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (voltage, dvdt) phase-plane trajectory."""
    dvdt = calculate_dvdt(voltage, sampling_rate, sigma_ms)
    return voltage, dvdt


def detect_threshold_kink(
    voltage: np.ndarray,
    sampling_rate: float,
    dvdt_threshold: float = 20.0,
    kink_slope: float = 10.0,
    search_window_ms: float = 5.0,
    peak_indices: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Detect AP threshold using the dV/dt kink method.

    Returns array of threshold indices.
    """
    if peak_indices is None:
        res = detect_spikes_threshold(
            voltage, np.arange(len(voltage)) / sampling_rate, -20.0, int(0.002 * sampling_rate)
        )
        peak_indices = res.spike_indices

    dvdt = calculate_dvdt(voltage, sampling_rate, sigma_ms=0.1)
    threshold_indices = []
    search_samples = int((search_window_ms / 1000.0) * sampling_rate)

    for peak_idx in peak_indices:
        start_search = max(0, peak_idx - search_samples)
        dvdt_slice = dvdt[start_search:peak_idx]
        crossings = np.where(dvdt_slice > dvdt_threshold)[0]
        if crossings.size > 0:
            thresh_idx = start_search + crossings[0]
        else:
            thresh_idx = max(0, peak_idx - int(0.001 * sampling_rate))
        threshold_indices.append(thresh_idx)

    return np.array(threshold_indices)


# ---------------------------------------------------------------------------
# Registry Wrappers
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    "spike_detection",
    label="Spike Detection",
    ui_params=[
        {
            "name": "threshold",
            "label": "Threshold (mV):",
            "type": "float",
            "default": -20.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "refractory_period",
            "label": "Refractory (s):",
            "type": "float",
            "default": 0.002,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "peak_search_window",
            "label": "Peak Search (s):",
            "type": "float",
            "default": 0.005,
            "min": 0.0,
            "max": 1.0,
            "decimals": 4,
        },
        {
            "name": "dvdt_threshold",
            "label": "dV/dt Thresh (V/s):",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
            "max": 1e6,
            "decimals": 1,
        },
        {
            "name": "ahp_window",
            "label": "AHP Window (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "max": 10.0,
            "decimals": 3,
        },
        {
            "name": "onset_lookback",
            "label": "Onset Lookback (s):",
            "type": "float",
            "default": 0.01,
            "min": 0.0,
            "max": 0.1,
            "decimals": 3,
        },
        {
            "name": "ljp_correction_mv",
            "label": "LJP Correction (mV):",
            "type": "float",
            "default": 0.0,
            "min": -100.0,
            "max": 100.0,
            "decimals": 2,
            "tooltip": "Liquid Junction Potential in mV. V_true = V_recorded - LJP.",
        },
    ],
    plots=[
        {"type": "hlines", "data": ["threshold"], "color": "r", "styles": ["dash"]},
        {"type": "markers", "x": "spike_times", "y": "spike_voltages", "color": "r"},
    ],
)
def run_spike_detection_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    threshold: float = -20.0,
    refractory_period: float = 0.002,
    peak_search_window: float = 0.005,
    dvdt_threshold: float = 20.0,
    ahp_window: float = 0.05,
    onset_lookback: float = 0.01,
    **kwargs,
) -> Dict[str, Any]:
    """Wrapper for spike detection. Returns namespaced schema."""
    try:
        ljp_mv = float(kwargs.get("ljp_correction_mv", 0.0))
        data = apply_ljp_correction(data, ljp_mv)
        refractory_samples = int(refractory_period * sampling_rate)
        peak_window_samples = int(peak_search_window * sampling_rate)

        params = {
            "threshold": threshold,
            "refractory_period": refractory_period,
            "peak_search_window": peak_search_window,
            "dvdt_threshold": dvdt_threshold,
            "ahp_window": ahp_window,
            "onset_lookback": onset_lookback,
        }

        result = detect_spikes_threshold(
            data,
            time,
            threshold,
            refractory_samples,
            peak_search_window_samples=peak_window_samples,
            parameters=params,
            dvdt_threshold=dvdt_threshold,
        )

        if result.is_valid:
            features_list = calculate_spike_features(
                data,
                time,
                result.spike_indices,
                dvdt_threshold=dvdt_threshold,
                ahp_window_sec=ahp_window,
                onset_lookback=onset_lookback,
            )
            stats: Dict[str, Any] = {}
            if features_list:
                for key in features_list[0].keys():
                    values = [f[key] for f in features_list if not np.isnan(f[key])]
                    if values:
                        stats[f"{key}_mean"] = float(np.mean(values))
                        stats[f"{key}_std"] = float(np.std(values))
                    else:
                        stats[f"{key}_mean"] = np.nan
                        stats[f"{key}_std"] = np.nan

            v_data = (
                data[result.spike_indices]
                if result.spike_indices is not None and len(result.spike_indices) > 0
                else np.array([])
            )

            metrics: Dict[str, Any] = {
                "spike_count": len(result.spike_indices) if result.spike_indices is not None else 0,
                "mean_freq_hz": result.mean_frequency if result.mean_frequency is not None else 0.0,
                "spike_times": result.spike_times,
                "spike_indices": result.spike_indices,
                "spike_voltages": v_data,
                "threshold": threshold,
                "parameters": params,
            }
            metrics.update(stats)
        else:
            metrics = {
                "spike_count": 0,
                "mean_freq_hz": 0.0,
                "threshold": threshold,
                "spike_error": result.error_message or "Unknown error",
                "parameters": params,
            }

        return {"module_used": "single_spike", "metrics": metrics}

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_spike_detection_wrapper: {e}", exc_info=True)
        return {
            "module_used": "single_spike",
            "metrics": {"spike_count": 0, "mean_freq_hz": 0.0, "spike_error": str(e)},
        }


@AnalysisRegistry.register(
    "phase_plane_analysis",
    label="Phase Plane",
    plots=[
        {"name": "Trace", "type": "trace"},
        {"type": "popup_phase", "title": "Phase Plane"},
    ],
    ui_params=[
        {
            "name": "sigma_ms",
            "label": "Smoothing (ms):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "dvdt_threshold",
            "label": "dV/dt Thresh (V/s):",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "spike_threshold",
            "label": "Spike Detect Thresh (mV):",
            "type": "float",
            "default": -20.0,
            "min": -1000.0,
            "max": 1000.0,
            "decimals": 2,
        },
        {"name": "kink_slope", "label": "Kink Slope:", "type": "float", "default": 10.0, "hidden": True},
        {
            "name": "search_window_ms",
            "label": "Search Window (ms):",
            "type": "float",
            "default": 5.0,
            "min": 0.1,
            "max": 100.0,
            "decimals": 2,
        },
        {
            "name": "ljp_correction_mv",
            "label": "LJP Correction (mV):",
            "type": "float",
            "default": 0.0,
            "min": -100.0,
            "max": 100.0,
            "decimals": 2,
            "tooltip": "Liquid Junction Potential in mV. V_true = V_recorded - LJP.",
        },
    ],
)
def phase_plane_analysis_wrapper(
    voltage: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    sigma_ms: float = 0.1,
    dvdt_threshold: float = 20.0,
    **kwargs,
) -> Dict[str, Any]:
    """Wrapper for Phase Plane analysis. Returns namespaced schema."""
    spike_threshold = kwargs.get("spike_threshold", -20.0)
    search_window_ms = kwargs.get("search_window_ms", 5.0)
    kink_slope = kwargs.get("kink_slope", 10.0)

    ljp_mv = float(kwargs.get("ljp_correction_mv", 0.0))
    voltage = apply_ljp_correction(voltage, ljp_mv)

    v, dvdt = get_phase_plane_trajectory(voltage, sampling_rate, sigma_ms)

    spike_res = detect_spikes_threshold(voltage, time, spike_threshold, int(0.002 * sampling_rate))

    thresh_indices = detect_threshold_kink(
        voltage,
        sampling_rate,
        dvdt_threshold=dvdt_threshold,
        kink_slope=kink_slope,
        search_window_ms=search_window_ms,
        peak_indices=spike_res.spike_indices,
    )

    threshold_vals = voltage[thresh_indices] if thresh_indices.size > 0 else []

    metrics = {
        "voltage": v,
        "dvdt": dvdt,
        "threshold_indices": thresh_indices,
        "threshold_vals": threshold_vals,
        "threshold_v": float(np.mean(threshold_vals)) if len(threshold_vals) > 0 else np.nan,
        "threshold_dvdt": float(dvdt_threshold),
        "max_dvdt": float(np.max(dvdt)) if len(dvdt) > 0 else 0.0,
        "threshold_mean": float(np.mean(threshold_vals)) if len(threshold_vals) > 0 else np.nan,
    }
    return {"module_used": "single_spike", "metrics": metrics}


# Keep the original function name as an alias so existing code and tests still work
phase_plane_analysis = phase_plane_analysis_wrapper


# ---------------------------------------------------------------------------
# Module-level tab aggregator
# ---------------------------------------------------------------------------
@AnalysisRegistry.register(
    "single_spike",
    label="Spike Analysis",
    method_selector={
        "Spike Detection": "spike_detection",
        "Phase Plane": "phase_plane_analysis",
    },
    ui_params=[],
    plots=[],
)
def single_spike_module(**kwargs):
    """Module-level aggregator tab for single-spike analyses."""
    return {}
