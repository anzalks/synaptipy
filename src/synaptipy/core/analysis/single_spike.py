# src/synaptipy/core/analysis/single_spike.py
# -*- coding: utf-8 -*-
"""
Core Protocol Module 2: Single Spike Analysis.

Consolidates: Spike Detection, AP Characterisation (threshold, amplitude,
half-width, rise/decay times, fAHP/mAHP, ADP) and Phase Plane (dV/dt vs V)
analysis.

All registry wrapper functions return::

    {
        "module_used": "single_spike",
        "metrics": { ... flat result keys ... }
    }

References
----------
- Hodgkin, A. L., & Huxley, A. F. (1952). J. Physiol., 117(4), 500-544.
  doi:10.1113/jphysiol.1952.sp004764
- Jenerick, H. (1963). Biophys. J., 3(5), 363-377.
  doi:10.1016/S0006-3495(63)86827-7
- Storm, J. F. (1987). J. Physiol., 385, 733-759.
  doi:10.1113/jphysiol.1987.sp016517
- Azouz, R., Jensen, M. S., & Yaari, Y. (1996). J. Physiol., 492(1), 211-223.
  doi:10.1113/jphysiol.1996.sp021302
- Henze, D. A., & Buzsaki, G. (2001). Neuroscience, 105(1), 121-130.
  doi:10.1016/S0306-4522(01)00167-1
- Sah, P., & Faber, E. S. L. (2002). Prog. Neurobiol., 66(5), 345-353.
  doi:10.1016/S0301-0082(02)00004-7
- Sekerli, M., Del Negro, C. A., Lee, R. H., & Butera, R. J. (2004).
  IEEE Trans. Biomed. Eng., 51(9), 1665-1672. doi:10.1109/TBME.2004.827827
- Naundorf, B., Wolf, F., & Volgushev, M. (2006). Nature, 440(7087), 1060-1063.
  doi:10.1038/nature04610
- Bean, B. P. (2007). Nat. Rev. Neurosci., 8(6), 451-465. doi:10.1038/nrn2148
- Gouwens, N. W., Sorensen, S. A., Berg, J., et al. (2019). Nat. Neurosci.,
  22(7), 1182-1195. doi:10.1038/s41593-019-0417-0
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.signal import savgol_filter

from synaptipy.core.analysis.passive_properties import apply_ljp_correction
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.constants import DVDT_ARTIFACT_CEILING_VS, MIN_RISING_PHASE_MS
from synaptipy.core.results import SingleSpikeResult, SpikeTrainResult

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
        :class:`~synaptipy.core.results.SpikeTrainResult` for provenance.
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

        # Apply 5 kHz low-pass filter using BLAS-safe SOS filter
        from scipy.signal import butter

        from synaptipy.core.signal_processor import _sosfiltfilt_safe

        nyq = 0.5 / dt
        if 5000.0 < nyq:
            sos = butter(4, 5000.0, btype="low", output="sos", fs=1.0 / dt)
            data_filtered = _sosfiltfilt_safe(sos, data)
        else:
            data_filtered = data

        dvdt = np.gradient(data_filtered, dt)
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

        peak_indices_list = []
        if peak_search_window_samples is None:
            peak_search_window_samples = (
                refractory_samples if refractory_samples > 0 else int(0.005 / (time[1] - time[0]))
            )

        last_accepted_crossing = -refractory_samples - 1 if refractory_samples > 0 else -1
        for idx_c, crossing_idx in enumerate(crossings):
            if refractory_samples > 0 and (crossing_idx - last_accepted_crossing) < refractory_samples:
                continue
            search_start = int(crossing_idx)
            next_crossing = int(crossings[idx_c + 1]) if idx_c + 1 < len(crossings) else len(data)
            search_end = min(search_start + peak_search_window_samples, next_crossing, len(data))
            if search_start >= search_end:
                peak_idx = search_start
            else:
                try:
                    relative_peak_idx = int(np.argmax(data[search_start:search_end]))
                    peak_idx = search_start + relative_peak_idx
                except ValueError:
                    peak_idx = search_start

            # Only commit refractory suppression when peak actually crosses voltage threshold
            # and does not duplicate the preceding spike peak in high-frequency trains (>200 Hz).
            if data[peak_idx] >= threshold and (not peak_indices_list or peak_idx > peak_indices_list[-1]):
                peak_indices_list.append(peak_idx)
                last_accepted_crossing = crossing_idx

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

    Returns list of SingleSpikeResult instances per spike, containing metrics like:
    ap_threshold, amplitude, half_width, rise_time_10_90, decay_time_90_10,
    fahp_depth, mahp_depth, ahp_duration_half, adp_amplitude, max_dvdt, min_dvdt.

    Methodology aligns with established electrophysiology standards:

    - AP threshold (onset) is strictly defined as the first point in the pre-spike
      lookback window where the discrete derivative dV/dt exceeds the specified
      ``dvdt_threshold`` (default 20 V/s).
    - ADP and AHP logic strictly follows the exact trough/peak finding methodology
      to ensure accurate feature extraction.

    Args:
        data: 1-D voltage array (mV).
        time: Corresponding time array (s).
        spike_indices: Array of sample indices for each spike peak.
        dvdt_threshold: The dV/dt threshold for AP onset (V/s). Default 20.0.
        ahp_window_sec: Duration of AHP/ADP search window (s).
        onset_lookback: Lookback window before each spike peak (s).
        fahp_window_ms: (start, end) of fast-AHP window after peak (ms).
        mahp_window_ms: (start, end) of medium-AHP window after peak (ms).

    Returns:
        A list of SingleSpikeResult objects.
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

    # Apply 9.9 kHz low-pass Bessel filter for clean derivative calculation (BLAS-safe)
    from scipy.signal import bessel

    from synaptipy.core.signal_processor import _sosfiltfilt_safe

    nyq = 0.5 / dt
    if 9900.0 < nyq:
        sos = bessel(4, 9900.0, btype="low", output="sos", fs=1.0 / dt)
        data_filtered = _sosfiltfilt_safe(sos, data)
    else:
        data_filtered = data

    dvdt = np.gradient(data_filtered, dt)

    lookback_samples = max(1, int(onset_lookback / dt))
    post_peak_samples = int(0.01 / dt)
    ahp_max_samples = int(ahp_window_sec / dt)

    # --- AP Threshold (onset) via dV/dt threshold crossing ---
    # Bound each spike's lookback window strictly after the preceding spike peak so
    # fast-spiking (>100 Hz) trains never lock onto the prior spike's upstroke while
    # preserving full inter-spike ramps on slower trains.
    lookback_range = np.arange(-lookback_samples, 0)
    raw_onset_indices = spike_indices[:, None] + lookback_range
    onset_min_idx = np.zeros(n_spikes, dtype=int)
    if n_spikes > 1:
        onset_min_idx[1:] = spike_indices[:-1] + 1
    in_interspike_window = raw_onset_indices >= onset_min_idx[:, None]
    onset_window_indices = np.clip(raw_onset_indices, 0, n_data - 1)

    onset_dvdt_windows = dvdt[onset_window_indices]
    masked_upstroke_dvdt = np.where(in_interspike_window, onset_dvdt_windows, -np.inf)

    # We use the explicit dvdt_threshold parameter (converted to mV/s) to find the onset.
    target_thresh_mvs = dvdt_threshold * 1000.0

    # PHASE-PLANE BACKWARD SEARCH:
    # Scan backward from the point of MAXIMUM dV/dt within the bounded pre-spike window.
    max_dvdt_rel_idx = np.argmax(masked_upstroke_dvdt, axis=1)

    # Create a mask that is only valid within the inter-spike window and BEFORE max dV/dt
    col_idxs = np.tile(np.arange(lookback_samples), (n_spikes, 1))
    valid_search_mask = (col_idxs <= max_dvdt_rel_idx[:, None]) & in_interspike_window

    below_thresh_mask = (onset_dvdt_windows < target_thresh_mvs) & valid_search_mask
    has_crossing = np.any(below_thresh_mask, axis=1)

    # Reverse the mask to search backward from the max dV/dt
    rev_below = below_thresh_mask[:, ::-1]
    first_below_rev_idx = np.argmax(rev_below, axis=1)

    # Convert reversed index back to original window index
    first_below_idx = lookback_samples - 1 - first_below_rev_idx
    # The actual onset is the first sample >= threshold, which is one sample
    # after it falls below threshold.
    first_crossing_rel_idx = np.minimum(first_below_idx + 1, lookback_samples - 1)

    # If no crossing is found, fallback to a fixed window before peak.
    fallback_indices = np.maximum(0, spike_indices - int(0.002 / dt))

    found_thresh_indices = onset_window_indices[np.arange(n_spikes), first_crossing_rel_idx]
    thresh_indices = np.where(has_crossing, found_thresh_indices, fallback_indices)
    ap_thresholds = data[thresh_indices]

    # Biological QC on detected thresholds: flag as NaN when the
    # per-spike peak rising rate exceeds 300 V/s (artifact ceiling) or the
    # threshold-to-peak rising phase is shorter than 0.1 ms (false detection).
    onset_max_dvdt = np.max(onset_dvdt_windows, axis=1)
    rising_phase_s = (spike_indices - thresh_indices) * dt
    at_edge = first_crossing_rel_idx == 0
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

    safe_idx_rise_50 = np.clip(idx_rise_50_rel, 0, full_window_len - 2)
    safe_idx_fall_50 = np.clip(idx_fall_50_rel, 1, full_window_len - 1)

    # Linear interpolation for 50% rise
    y0_rise = waveforms[np.arange(n_spikes), safe_idx_rise_50]
    y1_rise = waveforms[np.arange(n_spikes), safe_idx_rise_50 + 1]
    dy_rise = y1_rise - y0_rise
    dy_rise[dy_rise == 0] = 1e-9
    frac_rise = (amp_50 - y0_rise) / dy_rise
    x_rise = safe_idx_rise_50 + frac_rise

    # Linear interpolation for 50% fall
    y0_fall = waveforms[np.arange(n_spikes), safe_idx_fall_50 - 1]
    y1_fall = waveforms[np.arange(n_spikes), safe_idx_fall_50]
    dy_fall = y1_fall - y0_fall
    dy_fall[dy_fall == 0] = -1e-9
    frac_fall = (amp_50 - y0_fall) / dy_fall
    x_fall = (safe_idx_fall_50 - 1) + frac_fall

    half_widths[valid_width] = (x_fall[valid_width] - x_rise[valid_width]) * dt * 1000.0

    lev_10 = amp_10[:, None]
    lev_90 = amp_90[:, None]
    mask_10 = is_pre_peak & (waveforms <= lev_10)
    valid_10 = np.any(mask_10, axis=1)
    idx_10_rel = np.max(np.where(mask_10, idxs, -1), axis=1)
    mask_90 = is_pre_peak & (waveforms <= lev_90)
    valid_90 = np.any(mask_90, axis=1)
    idx_90_rel = np.max(np.where(mask_90, idxs, -1), axis=1)
    valid_rise = valid_10 & valid_90 & (idx_90_rel > idx_10_rel)

    safe_idx_10 = np.clip(idx_10_rel, 0, full_window_len - 2)
    safe_idx_90 = np.clip(idx_90_rel, 0, full_window_len - 2)

    # Linear interpolation for 10%
    y0_10 = waveforms[np.arange(n_spikes), safe_idx_10]
    y1_10 = waveforms[np.arange(n_spikes), safe_idx_10 + 1]
    dy_10 = y1_10 - y0_10
    dy_10[dy_10 == 0] = 1e-9
    frac_10 = (amp_10 - y0_10) / dy_10
    x_10 = safe_idx_10 + frac_10

    # Linear interpolation for 90%
    y0_90 = waveforms[np.arange(n_spikes), safe_idx_90]
    y1_90 = waveforms[np.arange(n_spikes), safe_idx_90 + 1]
    dy_90 = y1_90 - y0_90
    dy_90[dy_90 == 0] = 1e-9
    frac_90 = (amp_90 - y0_90) / dy_90
    x_90 = safe_idx_90 + frac_90

    rise_times[valid_rise] = (x_90[valid_rise] - x_10[valid_rise]) * dt * 1000.0

    mask_dec_90 = is_post_peak & (waveforms <= lev_90)
    valid_dec_90 = np.any(mask_dec_90, axis=1)
    idx_dec_90_rel = np.min(np.where(mask_dec_90, idxs, 999999), axis=1)
    mask_dec_10 = is_post_peak & (waveforms <= lev_10)
    valid_dec_10 = np.any(mask_dec_10, axis=1)
    idx_dec_10_rel = np.min(np.where(mask_dec_10, idxs, 999999), axis=1)
    valid_decay = valid_dec_90 & valid_dec_10 & (idx_dec_10_rel > idx_dec_90_rel)

    safe_idx_dec_10 = np.clip(idx_dec_10_rel, 1, full_window_len - 1)
    safe_idx_dec_90 = np.clip(idx_dec_90_rel, 1, full_window_len - 1)

    # Linear interpolation for decay 90%
    y0_d90 = waveforms[np.arange(n_spikes), safe_idx_dec_90 - 1]
    y1_d90 = waveforms[np.arange(n_spikes), safe_idx_dec_90]
    dy_d90 = y1_d90 - y0_d90
    dy_d90[dy_d90 == 0] = -1e-9
    frac_d90 = (amp_90 - y0_d90) / dy_d90
    x_d90 = (safe_idx_dec_90 - 1) + frac_d90

    # Linear interpolation for decay 10%
    y0_d10 = waveforms[np.arange(n_spikes), safe_idx_dec_10 - 1]
    y1_d10 = waveforms[np.arange(n_spikes), safe_idx_dec_10]
    dy_d10 = y1_d10 - y0_d10
    dy_d10[dy_d10 == 0] = -1e-9
    frac_d10 = (amp_10 - y0_d10) / dy_d10
    x_d10 = (safe_idx_dec_10 - 1) + frac_d10

    decay_times[valid_decay] = (x_d10[valid_decay] - x_d90[valid_decay]) * dt * 1000.0

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

    # DYNAMIC AHP BOUNDING:
    # Require V < ap_threshold at the upward dV/dt zero-crossing so suprathreshold
    # repolarisation shoulders/ADPs above threshold are not mistaken for the AHP trough.
    ahp_dvdt = dvdt[ahp_indices]
    ahp_dvdt[~valid_ahp_mask] = -1.0  # Ignore invalid regions
    if ahp_dvdt.shape[1] > 1:
        below_ap_thr = np.isnan(ap_thresholds[:, None]) | (ahp_waveforms[:, :-1] < ap_thresholds[:, None])
        crossing_mask = (ahp_dvdt[:, :-1] < 0) & (ahp_dvdt[:, 1:] >= 0) & below_ap_thr
        has_crossing = np.any(crossing_mask, axis=1)
        first_crossing_idx = np.argmax(crossing_mask, axis=1) + 1
    else:
        has_crossing = np.zeros(n_spikes, dtype=bool)
        first_crossing_idx = np.zeros(n_spikes, dtype=int)

    # Fallback to argmin if no clean zero-crossing is found
    ahp_min_rel_indices = np.where(has_crossing, first_crossing_idx, np.argmin(temp_ahp, axis=1))

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

    # --- ADP (variation-diminishing Gaussian-smoothed waveform, bounded before next AP onset) ---
    adp_amplitudes = np.full(n_spikes, np.nan)
    if ahp_max_samples > 3:
        from scipy.ndimage import gaussian_filter1d

        adp_sigma = max(1.0, 0.0002 / dt)
        adp_smooth = gaussian_filter1d(ahp_waveforms.astype(np.float64), sigma=adp_sigma, axis=1, mode="nearest")

        adp_bound_per_spike = ahp_max_samples_per_spike.copy()
        if n_spikes > 1:
            dist_to_next_onset = np.maximum(1, thresh_indices[1:] - spike_indices[:-1])
            adp_bound_per_spike[:-1] = np.minimum(adp_bound_per_spike[:-1], dist_to_next_onset)

        for i in range(n_spikes):
            bound = int(min(adp_bound_per_spike[i], ahp_max_samples))
            if bound < 4:
                continue
            seg = adp_smooth[i, :bound]
            mid = seg[1:-1]
            # Fast trough: first genuine local minimum below AP threshold
            min_locs = np.where((mid <= seg[:-2]) & (mid < seg[2:]) & (mid < ap_thresholds[i]))[0] + 1
            if min_locs.size == 0:
                continue
            trough_idx = int(min_locs[0])
            # Candidate local maxima after the fast trough
            post = seg[trough_idx:]
            if post.size < 3:
                continue
            post_mid = post[1:-1]
            max_rel = np.where((post_mid > post[:-2]) & (post_mid >= post[2:]))[0] + 1
            for m_rel in max_rel:
                m_idx = trough_idx + int(m_rel)
                if m_idx + 1 >= bound:
                    break
                rise_amp = float(seg[m_idx] - seg[trough_idx])
                post_drop = float(seg[m_idx] - np.min(seg[m_idx + 1 : bound]))
                # Require genuine depolarizing hump (>0.25 mV rise AND >=0.20 mV subsequent repolarization)
                if rise_amp > 0.25 and post_drop >= 0.20:
                    adp_amplitudes[i] = rise_amp
                    break

    # --- fAHP and mAHP (separate physiological windows) ---
    # fAHP: fast AHP (default 1-5 ms post-peak): BK and Kv3 K+ channel-mediated fast repolarisation (Storm, 1987)
    # mAHP: medium AHP (default 10-50 ms post-peak): SK Ca2+-activated K+ channel hyperpolarisation (Sah & Faber, 2002)
    fahp_start = max(1, int(fahp_window_ms[0] / 1000.0 / dt))
    fahp_end = max(fahp_start + 1, int(fahp_window_ms[1] / 1000.0 / dt))
    mahp_start = max(1, int(mahp_window_ms[0] / 1000.0 / dt))
    mahp_end = max(mahp_start + 1, int(mahp_window_ms[1] / 1000.0 / dt))

    next_spike_limit = np.full(n_spikes, n_data, dtype=int)
    if n_spikes > 1:
        next_spike_limit[:-1] = np.minimum(n_data, thresh_indices[1:])

    def _window_min(start_s: int, end_s: int) -> np.ndarray:
        """Return per-spike min voltage in [peak+start_s, min(peak+end_s, next_onset, n_data))."""
        w_len = end_s - start_s
        if w_len <= 0:
            return np.full(n_spikes, np.nan)
        w_range = np.arange(start_s, end_s)
        raw_w_idx = spike_indices[:, None] + w_range
        valid_w = (raw_w_idx >= 0) & (raw_w_idx < next_spike_limit[:, None])
        safe_w_idx = np.clip(raw_w_idx, 0, n_data - 1)
        vals = np.where(valid_w, data[safe_w_idx], np.inf)
        mins = np.min(vals, axis=1)
        return np.where(np.isfinite(mins), mins, np.nan)

    fahp_min_vals = _window_min(fahp_start, fahp_end)
    mahp_min_vals = _window_min(mahp_start, mahp_end)
    fahp_depths = ap_thresholds - fahp_min_vals
    mahp_depths = ap_thresholds - mahp_min_vals

    # --- max/min dV/dt ---
    raw_dvdt = np.gradient(waveforms, axis=1) / dt / 1000.0

    # Apply a dynamic sampling-rate dependent rolling window (standard ~0.1 ms)
    # to smooth the derivative, matching standard smoothing behavior
    # and preventing single-sample noise spikes from inflating the rate.
    window_ms = 0.1
    window_size = max(3, int(window_ms / (dt * 1000.0)))
    if window_size % 2 == 0:
        window_size += 1

    kernel = np.ones(window_size) / window_size
    from scipy.ndimage import convolve1d

    full_dvdt = convolve1d(raw_dvdt, kernel, axis=1, mode="nearest")

    # Calculate column indices of thresholds
    rel_thresh_indices = thresh_indices - (spike_indices - lookback_samples)

    # max dV/dt strictly between threshold and peak
    valid_rise_mask = is_pre_peak[None, :] & (col_indices[None, :] >= rel_thresh_indices[:, None])
    pre_peak_dvdt = np.where(valid_rise_mask, full_dvdt, -np.inf)

    # min dV/dt after peak
    post_peak_dvdt = np.where(is_post_peak[None, :], full_dvdt, np.inf)

    max_dvdts = np.max(pre_peak_dvdt, axis=1)
    min_dvdts = np.min(post_peak_dvdt, axis=1)

    # --- New Active Features ---
    ap_delays = time[thresh_indices]

    ahp_times = np.zeros(n_spikes)
    for i in range(n_spikes):
        ahp_times[i] = time[ahp_indices[i, ahp_min_rel_indices[i]]]

    trough_vs = ahp_min_vals

    upstroke_downstroke_ratios = np.full(n_spikes, np.nan)
    valid_ratio = min_dvdts != 0
    upstroke_downstroke_ratios[valid_ratio] = max_dvdts[valid_ratio] / np.abs(min_dvdts[valid_ratio])

    phase_plane_areas = np.full(n_spikes, np.nan)
    ap_widths_arbitrary = [None] * n_spikes

    for i in range(n_spikes):
        start_idx = thresh_indices[i]
        end_idx = spike_indices[i] + ap_end_rel_indices[i]

        # Calculate Phase Plane Area (Shoelace formula)
        if start_idx < end_idx:
            # Find the local slice within the full_dvdt window
            rel_start = (start_idx - spike_indices[i]) + lookback_samples
            rel_end = (end_idx - spike_indices[i]) + lookback_samples

            # Ensure boundaries are within full_dvdt shape
            rel_start = max(0, min(rel_start, full_window_len - 1))
            rel_end = max(0, min(rel_end, full_window_len))

            if rel_end > rel_start + 2:
                x = data[start_idx : start_idx + (rel_end - rel_start)]
                y = full_dvdt[i, rel_start:rel_end]

                if len(x) == len(y):
                    # Closed Shoelace polygon (Jenerick, 1963): closing edge makes area
                    # strictly invariant to scalar voltage offsets (e.g. LJP correction).
                    area = 0.5 * np.abs(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]) + x[-1] * y[0] - x[0] * y[-1])
                    phase_plane_areas[i] = area

    features_list = []
    for i in range(n_spikes):
        features_list.append(
            SingleSpikeResult(
                value=None,
                unit="mV",
                ap_threshold=float(ap_thresholds[i]),
                amplitude=float(amplitudes[i]),
                half_width=float(half_widths[i]),
                rise_time_10_90=float(rise_times[i]),
                decay_time_90_10=float(decay_times[i]),
                fahp_depth=float(fahp_depths[i]),
                mahp_depth=float(mahp_depths[i]),
                ahp_duration_half=float(ahp_durations[i]),
                adp_amplitude=float(adp_amplitudes[i]),
                max_dvdt=float(max_dvdts[i]),
                min_dvdt=float(min_dvdts[i]),
                absolute_peak_mv=float(peak_vals[i]),
                overshoot_mv=float(max(0.0, peak_vals[i])),
                ap_delay=float(ap_delays[i]),
                ap_width_arbitrary=ap_widths_arbitrary[i],
                ahp_time=float(ahp_times[i]),
                upstroke_downstroke_ratio=float(upstroke_downstroke_ratios[i]),
                phase_plane_area=float(phase_plane_areas[i]),
                trough_v=float(trough_vs[i]),
            )
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


def _resolve_single_kink_index(
    v_slice: np.ndarray,
    dvdt_slice: np.ndarray,
    lower_bound: int,
    peak_idx: int,
    sampling_rate: float,
    dvdt_threshold: float,
    kink_slope: float,
) -> int:
    """Resolve the AP onset index within [lower_bound, peak_idx)."""
    if dvdt_slice.size == 0:
        return max(0, int(peak_idx) - 1)
    # Search backward only up to peak upstroke velocity so dV/dt -> 0 near the
    # AP peak cannot misplace threshold onto the peak shoulder.
    upstroke_end = int(np.argmax(dvdt_slice)) + 1
    upstroke_dvdt = dvdt_slice[:upstroke_end]
    if np.any(upstroke_dvdt > dvdt_threshold):
        below_mask = np.where(upstroke_dvdt <= dvdt_threshold)[0]
        if below_mask.size > 0 and below_mask[-1] + 1 < upstroke_dvdt.size:
            return lower_bound + int(below_mask[-1]) + 1
        crossings = np.where(upstroke_dvdt > dvdt_threshold)[0]
        if crossings.size > 0:
            return lower_bound + int(crossings[0])
    if kink_slope > 0 and v_slice.size >= 3:
        dv = np.diff(v_slice)
        ddvdt = np.diff(dvdt_slice)
        phase_slope = np.where(np.abs(dv) > 1e-6, ddvdt / dv, 0.0)
        kink_hits = np.where((phase_slope >= kink_slope) & (dvdt_slice[1:] > 0))[0]
        if kink_hits.size > 0:
            return lower_bound + int(kink_hits[0]) + 1
    return max(lower_bound, int(peak_idx) - int(0.001 * sampling_rate))


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
    search_samples = max(1, int((search_window_ms / 1000.0) * sampling_rate))

    for i_pk, peak_idx in enumerate(peak_indices):
        lower_bound = max(0, int(peak_idx) - search_samples)
        if i_pk > 0 and int(peak_indices[i_pk - 1]) < int(peak_idx):
            prev_pk = int(peak_indices[i_pk - 1])
            lower_bound = max(lower_bound, prev_pk + int(np.argmin(voltage[prev_pk:peak_idx])))
        thresh_idx = _resolve_single_kink_index(
            voltage[lower_bound:peak_idx],
            dvdt[lower_bound:peak_idx],
            lower_bound,
            int(peak_idx),
            sampling_rate,
            dvdt_threshold,
            kink_slope,
        )
        threshold_indices.append(thresh_idx)

    return np.array(threshold_indices, dtype=int)


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
        if "refractory_ms" in kwargs and float(kwargs["refractory_ms"]) >= 0:
            refractory_period = float(kwargs["refractory_ms"]) / 1000.0
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
                import dataclasses

                # Collect attributes dynamically from the first valid result
                first_feat = features_list[0]
                feat_dict = dataclasses.asdict(first_feat)
                valid_keys = [
                    k
                    for k in feat_dict.keys()
                    if k
                    not in [
                        "value",
                        "unit",
                        "is_valid",
                        "error_message",
                        "quality_flags",
                        "confidence",
                        "metadata",
                        "parameters",
                    ]
                ]

                for key in valid_keys:
                    values = [
                        getattr(f, key)
                        for f in features_list
                        if getattr(f, key) is not None and not np.isnan(getattr(f, key))
                    ]
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

            n_spk = len(result.spike_indices) if result.spike_indices is not None else 0
            trace_dur = float(time[-1] - time[0]) if len(time) > 1 else 0.0
            stim_onset_s = float(kwargs.get("stim_onset_s", time[0] if len(time) > 0 else 0.0))
            stim_end_s = float(kwargs.get("stim_end_s", time[-1] if len(time) > 0 else 0.0))
            if "stim_onset_s" in kwargs and "stim_end_s" in kwargs and stim_end_s > stim_onset_s:
                win_dur = stim_end_s - stim_onset_s
                n_win = (
                    int(np.sum((result.spike_times >= stim_onset_s) & (result.spike_times <= stim_end_s)))
                    if result.spike_times is not None and n_spk > 0
                    else 0
                )
                win_freq_hz = float(n_win / win_dur)
            else:
                win_freq_hz = (n_spk / trace_dur) if trace_dur > 0 else 0.0
            first_lat_s = float(result.spike_times[0] - stim_onset_s) if n_spk > 0 else np.nan
            metrics: Dict[str, Any] = {
                "spike_count": n_spk,
                "mean_freq_hz": result.mean_frequency if result.mean_frequency is not None else 0.0,
                "window_frequency_hz": win_freq_hz,
                "first_spike_latency_s": first_lat_s,
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
    if spike_res.spike_indices is not None and len(spike_res.spike_indices) > 0:
        win_s = max(1, int(0.002 * sampling_rate))
        spk_max_vals = [float(np.max(dvdt[max(0, int(pk) - win_s) : int(pk) + 1])) for pk in spike_res.spike_indices]
        max_dvdt_val = float(np.max(spk_max_vals)) if spk_max_vals else float(np.max(dvdt))
    else:
        max_dvdt_val = float(np.max(dvdt)) if len(dvdt) > 0 else 0.0

    metrics = {
        "voltage": v,
        "dvdt": dvdt,
        "threshold_indices": thresh_indices,
        "threshold_vals": threshold_vals,
        "threshold_v": float(np.mean(threshold_vals)) if len(threshold_vals) > 0 else np.nan,
        "threshold_dvdt": float(dvdt_threshold),
        "max_dvdt": max_dvdt_val,
        "trace_max_dvdt": float(np.max(dvdt)) if len(dvdt) > 0 else 0.0,
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
