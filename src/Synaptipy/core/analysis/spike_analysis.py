# src/Synaptipy/core/analysis/spike_analysis.py
# -*- coding: utf-8 -*-
"""
Analysis functions related to action potential detection and characterization.
"""
import logging
from typing import List, Dict, Any
import numpy as np
from scipy.signal import savgol_filter
from Synaptipy.core.results import SpikeTrainResult
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


def detect_spikes_threshold(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    threshold: float,
    refractory_samples: int,
    peak_search_window_samples: int = None,
    parameters: Dict[str, Any] = None,
    dvdt_threshold: float = 20.0,
) -> SpikeTrainResult:
    """
    Detects spikes based on a simple voltage threshold crossing with refractory period.

    Args:
        data: 1D NumPy array of voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        threshold: Voltage threshold for detection.
        refractory_samples: Minimum number of samples between detected spikes (applied based on threshold crossings).
        peak_search_window_samples: Optional. Number of samples to search for peak after crossing.
                                    Defaults to refractory_samples (or 5ms if refractory is 0).

    Returns:
        SpikeTrainResult object containing spike times and indices.
    """
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size < 2:
        log.warning("detect_spikes_threshold: Invalid data array provided.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False,
                                error_message="Invalid data array", parameters=parameters or {})
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        log.warning("detect_spikes_threshold: Time and data array shapes mismatch.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False,
                                error_message="Time and data mismatch", parameters=parameters or {})
    if not isinstance(threshold, (int, float)):
        log.warning("detect_spikes_threshold: Threshold must be numeric.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False,
                                error_message="Threshold must be numeric", parameters=parameters or {})
    if not isinstance(refractory_samples, int) or refractory_samples < 0:
        log.warning("detect_spikes_threshold: refractory_samples must be a non-negative integer.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False,
                                error_message="Invalid refractory period", parameters=parameters or {})

    try:
        # 1. Find indices where the data crosses the dv/dt threshold upwards
        dt = time[1] - time[0] if len(time) > 1 else 1.0
        dvdt = np.gradient(data, dt)
        dvdt_thresh_mvs = dvdt_threshold * 1000.0

        crossings = np.where((dvdt[:-1] < dvdt_thresh_mvs) & (dvdt[1:] >= dvdt_thresh_mvs))[0] + 1
        if crossings.size == 0:
            log.debug("No dv/dt threshold crossings found.")
            return SpikeTrainResult(value=0, unit="spikes", spike_times=np.array(
                []), spike_indices=np.array([]), parameters=parameters or {})

        # 2. Apply refractory period based on crossings
        if refractory_samples <= 0:
            valid_crossing_indices = crossings
        else:
            valid_crossings_list = [crossings[0]]  # Always accept the first crossing
            last_crossing_idx = crossings[0]
            for idx in crossings[1:]:
                if (idx - last_crossing_idx) >= refractory_samples:
                    valid_crossings_list.append(idx)
                    last_crossing_idx = idx
            valid_crossing_indices = np.array(valid_crossings_list)

        if valid_crossing_indices.size == 0:
            return SpikeTrainResult(value=0, unit="spikes", spike_times=np.array(
                []), spike_indices=np.array([]), parameters=parameters or {})

        # 3. Find peak index after each valid crossing
        peak_indices_list = []
        # Define search window for peak
        if peak_search_window_samples is None:
            peak_search_window_samples = (
                refractory_samples if refractory_samples > 0 else int(0.005 / (time[1] - time[0]))
            )  # Default to 5ms if no refractory

        for crossing_idx in valid_crossing_indices:
            search_start = crossing_idx
            search_end = min(crossing_idx + peak_search_window_samples, len(data))
            if search_start >= search_end:  # Should not happen, but safety
                peak_idx = crossing_idx  # Fallback to crossing index
            else:
                try:
                    # Find index of max value within the window relative to window start
                    relative_peak_idx = np.argmax(data[search_start:search_end])
                    # Convert to index relative to the whole data array
                    peak_idx = search_start + relative_peak_idx
                except ValueError:  # Handle potential errors if slice is unexpectedly empty
                    log.warning(f"ValueError finding peak after crossing index {crossing_idx}. Using crossing index.")
                    peak_idx = crossing_idx

            # Secondary confirmation: The peak voltage must be at least above the voltage threshold
            # (which acts as a minimum absolute voltage required for a spike, e.g., -20mV)
            if data[peak_idx] >= threshold:
                peak_indices_list.append(peak_idx)

        peak_indices_arr = np.array(peak_indices_list).astype(int)  # Ensure integer indices

        # 4. Get corresponding times for the peaks
        peak_times_arr = time[peak_indices_arr]
        log.debug(f"Detected {len(peak_indices_arr)} spike peaks.")

        mean_freq = 0.0
        if len(peak_times_arr) > 1:
            # Use the span between first and last spike, not total trace duration
            spike_span = peak_times_arr[-1] - peak_times_arr[0]
            if spike_span > 0:
                # N-1 intervals for N spikes
                mean_freq = (len(peak_times_arr) - 1) / spike_span

        return SpikeTrainResult(
            value=len(peak_indices_arr),
            unit="spikes",
            spike_times=peak_times_arr,
            spike_indices=peak_indices_arr,
            mean_frequency=mean_freq,
            parameters=parameters or {},
        )

    except IndexError as e:
        # This might happen if indexing goes wrong, e.g., with peak_indices_arr
        log.error(
            f"IndexError during spike detection: {e}. "
            f"Indices={peak_indices_arr if 'peak_indices_arr' in locals() else 'N/A'}",
            exc_info=True,
        )
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False,
                                error_message=str(e), parameters=parameters or {})
    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error during spike detection: {e}", exc_info=True)
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False,
                                error_message=str(e), parameters=parameters or {})


# --- Add other spike analysis functions here later ---
def calculate_spike_features(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    spike_indices: np.ndarray,
    dvdt_threshold: float = 20.0,
    ahp_window_sec: float = 0.05,
    onset_lookback: float = 0.01,
) -> List[Dict[str, Any]]:
    """
    Calculates detailed features for each detected spike using vectorized
    NumPy operations for performance.

    Computes: AP threshold, amplitude, half-width, rise time (10-90%),
    decay time (90-10%), AHP depth, AHP duration (return-to-baseline),
    ADP amplitude, and max/min dV/dt.

    Args:
        data: 1D NumPy array of voltage data (mV).
        time: 1D NumPy array of corresponding time points (s).
        spike_indices: 1D NumPy array of peak sample indices.
        dvdt_threshold: Threshold for AP onset detection (V/s, default 20.0).
        ahp_window_sec: Maximum AHP search window (s, default 0.05).
        onset_lookback: Time to look back from peak for onset (s, default 0.01).

    Returns:
        A list of dictionaries, one per spike, each containing:
        ap_threshold, amplitude, half_width, rise_time_10_90,
        decay_time_90_10, ahp_depth, ahp_duration_half, adp_amplitude,
        max_dvdt, min_dvdt.
    """
    if spike_indices is None or spike_indices.size == 0:
        return []

    # Ensure inputs are numpy arrays
    spike_indices = np.asarray(spike_indices, dtype=int)
    n_spikes = len(spike_indices)
    n_data = len(data)

    if n_data < 2:
        return []

    dt = time[1] - time[0]
    if dt <= 0:
        log.warning("Invalid time vector (dt <= 0). Cannot calculate features.")
        return []

    # Calculate dV/dt once
    dvdt = np.gradient(data, dt)

    # Threshold in user units (V/s usually, but data is often mV, check consistency)
    # The docstring says data is mV, but dvdt_threshold is V/s.
    # So we need to convert threshold to mV/s:  V/s * 1000 = mV/s
    threshold_val_mvs = dvdt_threshold * 1000.0

    # --- 1. Define Windows (in samples) ---
    lookback_samples = int(onset_lookback / dt)
    post_peak_samples = int(0.01 / dt)  # 10ms after peak for half-width/decay
    ahp_max_samples = int(ahp_window_sec / dt)
    # dvdt_window_samples removed (unused)

    # --- 2. Construct Vectorized Windows (Fancy Indexing) ---
    # We clip indices to [0, n_data-1] to avoid IndexError, then handle boundary effects later

    # Onset Window: [peak - lookback, peak]
    # We'll search backwards safely.

    # --- Vectorized AP Threshold (Onset) ---
    # Strategy:
    # We need to find the *first* point crossing threshold_val_mvs going backwards from peak.
    # Or simpler: Find last point crossing threshold in the lookback window.

    ap_thresholds = np.full(n_spikes, np.nan)
    thresh_indices = np.full(n_spikes, -1, dtype=int)

    # Create a 2D index array for the lookback windows
    # shape: (n_spikes, lookback_samples)
    # indices: peak - lookback + range(lookback)
    lookback_range = np.arange(-lookback_samples, 0)
    onset_window_indices = spike_indices[:, None] + lookback_range

    # Clip to valid range
    np.clip(onset_window_indices, 0, n_data - 1, out=onset_window_indices)

    # Extract dV/dt in these windows
    onset_dvdt_windows = dvdt[onset_window_indices]  # shape (n_spikes, lookback_samples)

    # Find where dV/dt > threshold
    # We want the *first* crossing in the window (which is the earliest time).
    # Actually, we usually want the point closest to the peak where it *starts* rising fast?
    # Standard: The point where dV/dt crosses the threshold *upwards* (or just exceeds it).
    # Since we are looking back, let's look for the *last* index in the window where it was below?
    # Actually, let's stick to the previous logic: "First crossing in the lookback window"?
    # Original code: crossings = np.where(dvdt_slice > threshold)[0]
    # if crossings: thresh_indices[i] = s_start + crossings[0]
    # This implies searching from lookback_start forward to peak. The first time it exceeds is the onset.

    crossings_mask = onset_dvdt_windows > threshold_val_mvs

    # We need the first True in each row
    has_crossing = np.any(crossings_mask, axis=1)

    # argmax returns the first index of the max value (True=1).
    first_crossing_rel_idx = np.argmax(crossings_mask, axis=1)

    # Calculate absolute indices
    # If no crossing, fallback to creating a default (e.g., peak - const)
    fallback_indices = np.maximum(0, spike_indices - int(0.001 / dt))  # 1ms before peak fallback

    found_thresh_indices = onset_window_indices[np.arange(n_spikes), first_crossing_rel_idx]

    thresh_indices = np.where(has_crossing, found_thresh_indices, fallback_indices)
    ap_thresholds = data[thresh_indices]

    # --- Vectorized Amplitude ---
    peak_vals = data[spike_indices]
    amplitudes = peak_vals - ap_thresholds

    # --- Vectorized Rise/Decay/Width ---

    # We need windows spanning from threshold to some time after peak
    # Because widths can be wide, let's take a generous window around peak
    # Start: threshold index, End: peak + post_peak_samples

    # Since threshold indices vary, we can't make a perfect rectangular matrix easily without masking.
    # Alternative: Use a fix window relative to peak: [peak - small, peak + large]
    # But width start point is before peak (at threshold).

    # Let's proceed with a fixed window relative to peak for width/decay/rise search.
    # Window: [peak - lookback, peak + post_peak_samples]
    # This covers the whole AP shape usually.

    full_window_len = lookback_samples + post_peak_samples
    full_window_range = np.arange(-lookback_samples, post_peak_samples)
    full_window_indices = spike_indices[:, None] + full_window_range
    np.clip(full_window_indices, 0, n_data - 1, out=full_window_indices)

    waveforms = data[full_window_indices]  # (n_spikes, full_window_len)

    # Pre-compute levels
    amp_50 = ap_thresholds + 0.5 * amplitudes
    amp_10 = ap_thresholds + 0.1 * amplitudes
    amp_90 = ap_thresholds + 0.9 * amplitudes

    half_widths = np.full(n_spikes, np.nan)
    rise_times = np.full(n_spikes, np.nan)
    decay_times = np.full(n_spikes, np.nan)

    # We need to find crossings in `waveforms` relative to `threshold_indices`
    # This is tricky fully vectorized because "first crossing after X" depends on X which varies per row.
    # However, Python loops over spikes for just the lightweight logic on extracted waveforms is fast enough
    # compared to full raw loops, OR we can try to be clever.
    # Given the strict "Pure NumPy Vectorization" requirement, let's try to be clever.

    # Relative index of peak in the waveform window is constant: `lookback_samples`
    rel_peak = lookback_samples

    # 1. Rise Time (10% to 90% in pre-peak part)
    # Mask pre-peak part: indices < rel_peak
    # We search backwards from peak for 90% and 10%? Or forwards from start?
    # Usually forwards from threshold.
    # Let's search in the part of waveform corresponding to [threshold_index, peak_index]

    # We will iterate row-by-row on the *extracted small waveforms*.
    # This avoids Python overhead of fancy indexing the big array, but is still a loop.
    # To be "Pure Vectorized", we can use boolean logic on the matrix.

    # Logic for Half Width:
    # 1. Find last time it crosses 50% BEFORE peak
    # 2. Find first time it crosses 50% AFTER peak

    # Create coordinate grids
    # shape (n_spikes, full_window_len)

    # Mask for pre-peak and post-peak
    # We can use the column indices of `waveforms` (0 to full_window_len-1)
    col_indices = np.arange(full_window_len)
    is_pre_peak = col_indices < rel_peak
    is_post_peak = col_indices > rel_peak

    # --- Half Width ---
    # Broadcast levels: (n_spikes, 1)
    lev_50 = amp_50[:, None]

    # Find crossings: where (trace < lev) changes to (trace > lev) or vice-versa
    # For pre-peak rising flank: last point where (val <= 50%)

    # We want the LAST index where this is true (closest to peak)
    # We can use trick: multiply existing indices by mask, take max
    # Indices are 0..window_len.
    # If mask is False (0), it becomes 0.
    # We want to properly handle "no crossing" (all False).

    # Create an index array where False -> -1
    idxs = np.tile(col_indices, (n_spikes, 1))

    # Pre-peak crossing (Rising 50%)
    # We want the last index < peak where val <= 50% (interpolated usually, but nearest neighbor for now)
    # Actually, simpler: First index < peak where val >= 50%? No, that might catch noise.
    # Safest: Last index < peak where val <= 50% -> the crossing is between this and next.

    # Let's map the extracted waveform indices back to absolute time for dt mult.
    # rel_idx * dt = time offset from window start.

    # Rise 50%
    # valid points: pre-peak, <= 50%
    # We want the right-most of these.
    temp_mask = is_pre_peak & (waveforms <= lev_50)
    # If a row has no True, it means it never went below 50% in window? (Baseline > 50%?)
    # Set those to nan.
    has_pre_50 = np.any(temp_mask, axis=1)

    # indices where mask is true. We want max index for each row.
    # We set False entries to -1 so they are not max.
    masked_idxs_pre = np.where(temp_mask, idxs, -1)
    idx_rise_50_rel = np.max(masked_idxs_pre, axis=1)  # This is the point just BEFORE crossing

    # Fall 50%
    # valid points: post-peak, <= 50%
    # We want the left-most of these (first point dropping below).
    temp_mask_post = is_post_peak & (waveforms <= lev_50)
    has_post_50 = np.any(temp_mask_post, axis=1)

    # Set False entries to infinity (big number) so they are not min
    masked_idxs_post = np.where(temp_mask_post, idxs, 999999)
    idx_fall_50_rel = np.min(masked_idxs_post, axis=1)  # First point below

    valid_width = has_pre_50 & has_post_50 & (idx_rise_50_rel != -1) & (idx_fall_50_rel != 999999)

    # Interpolation for better precision?
    # t = t1 + (level - y1) / (y2 - y1) * dt
    # Let's stick to simple index diff * dt per requirement "using nanoseconds...".
    # Standard logic: (idx_fall - idx_rise) * dt
    # But idx_rise is point BEFORE, idx_fall is point AFTER.
    # So Width is roughly (idx_fall - idx_rise) * dt ?
    # Refinement: Linear Interp.
    # Code below implements simple index diff for speed and robustness first.

    # Correcting "point before" vs "point after":
    # Rise: y[i] <= 50, y[i+1] >= 50. Crossing is at i + frac
    # Fall: y[j-1] >= 50, y[j] <= 50. Crossing is at j - frac
    # Let's just use indices.

    half_widths[valid_width] = (idx_fall_50_rel[valid_width] - idx_rise_50_rel[valid_width]) * dt * 1000.0

    # --- Rise Time (10-90) ---
    lev_10 = amp_10[:, None]
    lev_90 = amp_90[:, None]

    # 10%: Last point < peak where y <= 10%
    mask_10 = is_pre_peak & (waveforms <= lev_10)
    valid_10 = np.any(mask_10, axis=1)
    idx_10_rel = np.max(np.where(mask_10, idxs, -1), axis=1)

    # 90%: First point < peak where y >= 90% ?
    # Or Last point < peak where y <= 90%?
    # Usually "time from 10% to 90%".
    # 90% point is closer to peak.
    # Let's look for: First point > 10% index where y >= 90%?
    # Simpler: Last point < peak where y <= 90% (point before crossing 90)
    mask_90 = is_pre_peak & (waveforms <= lev_90)
    valid_90 = np.any(mask_90, axis=1)
    idx_90_rel = np.max(np.where(mask_90, idxs, -1), axis=1)

    valid_rise = valid_10 & valid_90 & (idx_90_rel > idx_10_rel)
    rise_times[valid_rise] = (idx_90_rel[valid_rise] - idx_10_rel[valid_rise]) * dt * 1000.0

    # --- Decay Time (90-10) ---
    # Post peak
    # 90%: First point > peak where y <= 90%
    mask_dec_90 = is_post_peak & (waveforms <= lev_90)
    valid_dec_90 = np.any(mask_dec_90, axis=1)
    idx_dec_90_rel = np.min(np.where(mask_dec_90, idxs, 999999), axis=1)

    # 10%: First point > peak where y <= 10%
    mask_dec_10 = is_post_peak & (waveforms <= lev_10)
    valid_dec_10 = np.any(mask_dec_10, axis=1)
    idx_dec_10_rel = np.min(np.where(mask_dec_10, idxs, 999999), axis=1)

    valid_decay = valid_dec_90 & valid_dec_10 & (idx_dec_10_rel > idx_dec_90_rel)
    decay_times[valid_decay] = (idx_dec_10_rel[valid_decay] - idx_dec_90_rel[valid_decay]) * dt * 1000.0

    # --- AHP Depth & Duration ---
    # Window: From peak to max ahp_max_samples, but capped by next spike for high-freq firing
    ahp_max_samples_per_spike = np.full(n_spikes, ahp_max_samples)
    if n_spikes > 1:
        dist_to_next = spike_indices[1:] - spike_indices[:-1]
        ahp_max_samples_per_spike[:-1] = np.minimum(ahp_max_samples, dist_to_next)

    ahp_range = np.arange(0, ahp_max_samples)
    ahp_indices = spike_indices[:, None] + ahp_range
    np.clip(ahp_indices, 0, n_data - 1, out=ahp_indices)

    ahp_waveforms = data[ahp_indices]  # (n_spikes, ahp_max_samples)

    # Mask invalid parts that bleed into next spike
    col_idxs_ahp = np.tile(np.arange(ahp_max_samples), (n_spikes, 1))
    valid_ahp_mask = col_idxs_ahp < ahp_max_samples_per_spike[:, None]

    # Smooth before peak/trough detection to reduce noise sensitivity
    window_length = int(0.005 / dt)  # 5ms smoothing window
    if window_length % 2 == 0:
        window_length += 1
    if window_length < 5:
        window_length = 5

    if ahp_waveforms.shape[1] >= window_length:
        smoothed_ahp = savgol_filter(ahp_waveforms, window_length, 3, axis=1)
    else:
        smoothed_ahp = ahp_waveforms

    temp_ahp = smoothed_ahp.copy()
    temp_ahp[~valid_ahp_mask] = np.inf  # Prevent selecting points in the next spike

    # Find relative index of the minimum
    ahp_min_rel_indices = np.argmin(temp_ahp, axis=1)

    # Calculate dynamic window mean (e.g., +/- 1ms around the minimum index)
    mean_window = int(0.001 / dt)
    ahp_min_vals = np.zeros(n_spikes)
    for i in range(n_spikes):
        idx = ahp_min_rel_indices[i]
        start = max(0, idx - mean_window)
        end = min(ahp_max_samples_per_spike[i], idx + mean_window + 1)
        ahp_min_vals[i] = np.mean(ahp_waveforms[i, start:end])

    ahp_depths = ap_thresholds - ahp_min_vals

    # Duration: From "AP End" (crossing threshold down) to recovery
    # This is complex to behave exactly like previous logical loop purely vectorized.
    # Approximation: Time from Peak to Recovery?
    # Requirement: "Return-to-baseline"

    # Let's simplify AHP duration for vectorization to:
    # "Time from Peak to when it recovers to (Threshold - 10% Amplitude)"
    # Or keep it blank if too complex, but user asked for "Pure NumPy Vectorization".
    # We can do it!

    # Recovery Target
    rec_targets = ap_thresholds - 0.1 * amplitudes
    rec_target_bcast = rec_targets[:, None]

    # Search AFTER the minimum
    # Mask: index > min_index AND value >= target AND within valid mask
    is_after_min = col_idxs_ahp > ahp_min_rel_indices[:, None]
    is_recovered = ahp_waveforms >= rec_target_bcast
    valid_recovery = is_after_min & is_recovered & valid_ahp_mask

    # First index where this is true
    # If never recovers, set to end
    has_recovery = np.any(valid_recovery, axis=1)
    rec_rel_indices = np.where(has_recovery, np.argmax(valid_recovery, axis=1), ahp_max_samples)

    # AP End: First crossing of threshold after peak
    thresh_bcast = ap_thresholds[:, None]
    is_below_thresh = ahp_waveforms < thresh_bcast
    # We want first index (after peak=0)
    # Note: peak is at column 0 ? Yes, ahp_waveforms starts at peak.
    # Actually peak is max, so it will be > threshold.
    has_ap_end = np.any(is_below_thresh, axis=1)
    ap_end_rel_indices = np.where(has_ap_end, np.argmax(is_below_thresh, axis=1), 0)

    # Duration
    ahp_durations = np.full(n_spikes, np.nan)
    valid_ahp_dur = has_recovery & has_ap_end & (rec_rel_indices > ap_end_rel_indices)
    ahp_durations[valid_ahp_dur] = (rec_rel_indices[valid_ahp_dur] - ap_end_rel_indices[valid_ahp_dur]) * dt * 1000.0

    # --- ADP Analysis (Simplified) ---
    # Previous logic: Look for peaks in a window after AP end.
    # We'll skip complex ADP peak finding in vectorized mode for now or simpler logic:
    # Max value between AP End and AHP Min?
    # If there is a "hump", the max will be higher than the line connecting them.
    # Let's just calculate "ADP Amplitude" as Max value in (AP_End + 2ms, AHP_Min) relative to AP_End val?
    # For exact parity with find_peaks, it's hard. We will provide a placeholder or simple max.

    adp_amplitudes = np.full(n_spikes, np.nan)

    # Vectorized ADP: Largest Local Maximum between AP End and End of AHP Window
    # We look for a local peak (convexity) to avoid detecting monotonic recovery as ADP.

    # helper for local max: val[i] > val[i-1] and val[i] > val[i+1]
    # ahp_waveforms shape: (n_spikes, ahp_max_samples)
    if ahp_max_samples > 2:
        val_mid = ahp_waveforms[:, 1:-1]
        val_left = ahp_waveforms[:, :-2]
        val_right = ahp_waveforms[:, 2:]

        is_local_max_inner = (val_mid > val_left) & (val_mid > val_right)

        # Pad to match shape (False at edges)
        is_local_max = np.pad(is_local_max_inner, ((0, 0), (1, 1)), mode='constant', constant_values=False)

        col_idxs = np.tile(np.arange(ahp_max_samples), (n_spikes, 1))

        # Mask: must be local max AND after AP end
        # We also usually want it before the AHP Min? Or can it be after?
        # Test case: Trough (-80) -> ADP (-75) -> Rest.
        # Here ADP is *after* the fast trough.
        # But if we just look for *any* local max after AP end, we might catch the ADP.
        # If there is no ADP (monotonic recovery), there is no local max.
        # If there is oscillation, we take the largest.

        valid_adp_mask = is_local_max & (col_idxs > ap_end_rel_indices[:, None])

        has_adp = np.any(valid_adp_mask, axis=1)

        # Calculate amplitudes where valid
        # We use a temp array filled with -inf
        temp_vals = ahp_waveforms.copy()
        temp_vals[~valid_adp_mask] = -np.inf

        adp_peaks = np.max(temp_vals, axis=1)

        # Amplitude defined as Peak - ahp_min_vals?
        # In test case: -75 - (-80) = 5. Correct.
        # In scenario 1 (hump on falling phase): Peak is high, AHP min is low. Amp is large.
        calced_adps = adp_peaks - ahp_min_vals

        adp_amplitudes = np.where(has_adp, calced_adps, np.nan)

    # --- Max/Min dV/dt ---
    # Window: [Threshold, Peak + 2ms]
    # Re-use onset_window logic?
    # Construct specific dV/dt window: [Threshold_Index, Peak + 5ms]

    # We already have thresh_indices (absolute).
    # We want max/min dvdt in range [thresh_indices, spike_indices + 2ms]
    # Since start varies, we can use a fixed window from [Peak - 2ms, Peak + 1ms] which usually covers it?
    # Or just use the 'full_window' we extracted earlier if it covers enough.
    # full_window is [-lookback, +post_peak] -> usually [-10ms, +10ms].
    # We need dV/dt of that.

    full_dvdt = np.gradient(waveforms, axis=1) / dt  # Gradient of the windowed voltage

    # We only care about the relevant subset for "max rise" (rising phase) and "max fall" (repolarization)
    # Rise: pre-peak. Fall: post-peak.
    # Use sentinel values to avoid zeroing by boolean multiply
    pre_peak_dvdt = np.where(is_pre_peak, full_dvdt, -np.inf)
    post_peak_dvdt = np.where(is_post_peak, full_dvdt, np.inf)

    max_dvdts = np.max(pre_peak_dvdt, axis=1)  # Max rise rate
    min_dvdts = np.min(post_peak_dvdt, axis=1)  # Max repolarization rate

    # --- Assemble Results ---
    features_list = []
    for i in range(n_spikes):
        features_list.append({
            "ap_threshold": float(ap_thresholds[i]),
            "amplitude": float(amplitudes[i]),
            "half_width": float(half_widths[i]),
            "rise_time_10_90": float(rise_times[i]),
            "decay_time_90_10": float(decay_times[i]),
            "ahp_depth": float(ahp_depths[i]),
            "ahp_duration_half": float(ahp_durations[i]),
            "adp_amplitude": float(adp_amplitudes[i]),
            "max_dvdt": float(max_dvdts[i]),
            "min_dvdt": float(min_dvdts[i]),
        })

    return features_list


def calculate_isi(spike_times):
    """Calculates inter-spike intervals from a list of spike times."""
    if len(spike_times) < 2:
        return np.array([])
    return np.diff(spike_times)


def analyze_multi_sweep_spikes(
    data_trials: List[np.ndarray], time_vector: np.ndarray, threshold: float, refractory_samples: int,
    dvdt_threshold: float = 20.0
) -> List[SpikeTrainResult]:
    """
    Analyzes spikes across multiple sweeps (trials).

    Args:
        data_trials: List of 1D NumPy arrays, each representing a sweep.
        time_vector: 1D NumPy array of time points (assumed same for all sweeps).
        threshold: Voltage threshold.
        refractory_samples: Refractory period in samples.

    Returns:
        List of SpikeTrainResult objects, one for each sweep.
    """
    results = []
    for i, trial_data in enumerate(data_trials):
        try:
            result = detect_spikes_threshold(
                trial_data, time_vector, threshold, refractory_samples, dvdt_threshold=dvdt_threshold
            )
            # Add trial index to metadata
            result.metadata["sweep_index"] = i
            results.append(result)
        except (ValueError, TypeError, KeyError, IndexError) as e:
            log.error(f"Error analyzing sweep {i}: {e}")
            # Return an error result for this sweep
            error_result = SpikeTrainResult(
                value=0, unit="spikes", is_valid=False, error_message=f"Sweep {i}: {str(e)}"
            )
            error_result.metadata["sweep_index"] = i
            results.append(error_result)

    return results


# --- Registry Wrapper for Batch Processing ---
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
    ],
    plots=[
        {"type": "hlines", "data": ["threshold"], "color": "r", "styles": ["dash"]},
        {"type": "markers", "x": "spike_times", "y": "spike_voltages", "color": "r"}
    ]
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
    """
    Wrapper function for spike detection that conforms to the registry interface.

    Args:
        data: 1D NumPy array of voltage data
        time: 1D NumPy array of corresponding time points (seconds)
        sampling_rate: Sampling rate in Hz
        threshold: Detection threshold in mV
        refractory_period: Refractory period in seconds

    Returns:
        Dictionary containing results.
    """
    try:
        refractory_samples = int(refractory_period * sampling_rate)
        peak_window_samples = int(peak_search_window * sampling_rate)

        params = {
            'threshold': threshold,
            'refractory_period': refractory_period,
            'peak_search_window': peak_search_window,
            'dvdt_threshold': dvdt_threshold,
            'ahp_window': ahp_window,
            'onset_lookback': onset_lookback,
        }

        # Run detection
        result = detect_spikes_threshold(
            data, time, threshold, refractory_samples,
            peak_search_window_samples=peak_window_samples,
            parameters=params, dvdt_threshold=dvdt_threshold
        )

        if result.is_valid:
            # Calculate spike features
            features_list = calculate_spike_features(
                data,
                time,
                result.spike_indices,
                dvdt_threshold=dvdt_threshold,
                ahp_window_sec=ahp_window,
                onset_lookback=onset_lookback,
            )

            # Aggregate features (Mean and Std Dev)
            stats = {}
            if features_list:
                # Convert list of dicts to dict of lists for easier aggregation
                feature_keys = features_list[0].keys()
                for key in feature_keys:
                    values = [f[key] for f in features_list if not np.isnan(f[key])]
                    if values:
                        stats[f"{key}_mean"] = np.mean(values)
                        stats[f"{key}_std"] = np.std(values)
                    else:
                        stats[f"{key}_mean"] = np.nan
                        stats[f"{key}_std"] = np.nan

            if result.spike_indices is not None and len(result.spike_indices) > 0:
                v_data = data[result.spike_indices]
            else:
                v_data = np.array([])
            output = {
                "spike_count": len(result.spike_indices) if result.spike_indices is not None else 0,
                "mean_freq_hz": result.mean_frequency if result.mean_frequency is not None else 0.0,
                "spike_times": result.spike_times,
                "spike_indices": result.spike_indices,
                "spike_voltages": v_data,
                "parameters": params,
            }
            output.update(stats)
            return output
        else:
            return {
                "spike_count": 0, "mean_freq_hz": 0.0,
                "spike_error": result.error_message or "Unknown error",
                "parameters": params,
            }

    except (ValueError, TypeError, KeyError, IndexError) as e:
        log.error(f"Error in run_spike_detection_wrapper: {e}", exc_info=True)
        return {"spike_count": 0, "mean_freq_hz": 0.0, "spike_error": str(e)}
