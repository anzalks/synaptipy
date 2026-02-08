"""
Signal processing utilities for Synaptipy.
Includes filtering and trace quality checks.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional

try:
    import scipy.signal as signal
    import scipy.stats as stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    signal = None
    stats = None

log = logging.getLogger(__name__)


def check_trace_quality(data: np.ndarray, sampling_rate: float) -> Dict[str, Any]:
    """
    Assess the quality of a recording trace.

    Checks for:
    - Signal-to-Noise Ratio (SNR) estimation
    - Baseline Drift
    - 50/60Hz Line Noise contamination

    Args:
        data: 1D numpy array of the signal (e.g., voltage in mV or current in pA).
        sampling_rate: Sampling rate in Hz.

    Returns:
        Dictionary containing quality metrics and flags.
    """
    if data is None or len(data) == 0:
        return {"is_good": False, "error": "Empty data"}

    results = {"is_good": True, "warnings": [], "metrics": {}}

    try:
        if not HAS_SCIPY:
            results["warnings"].append("Scipy not installed. Detailed quality metrics unavailable.")
            return results

        # 1. Baseline Drift (Linear Trend)
        # Fit a line to the data to estimate drift
        x = np.arange(len(data))
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, data)

        # Total drift over the recording
        total_drift = slope * len(data)
        results["metrics"]["drift_slope"] = slope
        results["metrics"]["total_drift"] = total_drift

        # Threshold: Arbitrary for now, say > 5mV or 20pA drift is "high" depending on units
        # We'll just flag it if it's significant relative to signal std
        if abs(total_drift) > 5.0 * np.std(data):
            results["warnings"].append(f"Significant baseline drift detected ({total_drift:.2f} units)")
            # results['is_good'] = False  # Don't fail automatically, just warn

        # 2. RMS Noise / SNR
        # Estimate noise from the detrended signal
        detrended = data - (slope * x + intercept)
        rms_noise = np.sqrt(np.mean(detrended**2))
        results["metrics"]["rms_noise"] = rms_noise

        # SNR is hard without knowing what the "Signal" is (spikes? PSPs?)
        # We can just report the noise level for now.

        # 3. Line Noise (50Hz / 60Hz)
        # Compute Power Spectral Density
        freqs, psd = signal.welch(detrended, fs=sampling_rate, nperseg=min(len(data), 4096))

        # Check 50Hz and 60Hz bands
        def check_freq_power(target_freq, bandwidth=2.0):
            idx = np.where((freqs >= target_freq - bandwidth) & (freqs <= target_freq + bandwidth))[0]
            if len(idx) == 0:
                return 0.0
            power_in_band = np.mean(psd[idx])

            # Compare to neighboring baseline (e.g. target +/- 10Hz)
            base_idx = np.where((freqs >= target_freq - 10) & (freqs <= target_freq + 10))[0]
            baseline_power = np.mean(psd[base_idx]) if len(base_idx) > 0 else 1.0

            return power_in_band / baseline_power if baseline_power > 0 else 0.0

        power_ratio_50 = check_freq_power(50.0)
        power_ratio_60 = check_freq_power(60.0)

        results["metrics"]["line_noise_50hz_ratio"] = power_ratio_50
        results["metrics"]["line_noise_60hz_ratio"] = power_ratio_60

        if power_ratio_50 > 10.0:  # Threshold for "significant" peak
            results["warnings"].append("Significant 50Hz line noise detected")
        if power_ratio_60 > 10.0:
            results["warnings"].append("Significant 60Hz line noise detected")

    except (ValueError, TypeError, RuntimeError) as e:
        log.error(f"Error during trace quality check: {e}")
        results["is_good"] = False
        results["error"] = str(e)

    return results


def bandpass_filter(data: np.ndarray, lowcut: float, highcut: float, fs: float, order: int = 5) -> np.ndarray:
    """
    Apply a Butterworth bandpass filter to the data.
    Uses Second Order Sections (SOS) for numerical stability.
    """
    if not HAS_SCIPY:
        log.warning("Scipy not available. Cannot apply bandpass filter.")
        return data

    if fs <= 0:
        raise ValueError("Sampling rate must be positive")

    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq

    # Bounds check
    if low <= 0 or high >= 1:
        log.warning(
            f"Filter frequencies {lowcut}-{highcut} Hz are out of bounds for fs={fs} Hz. Returning original data."
        )
        return data

    # Use SOS format for numerical stability (critical for low freq / high fs ratios)
    sos = signal.butter(order, [low, high], btype="band", output='sos')
    y = signal.sosfiltfilt(sos, data)

    return y


def lowpass_filter(data: np.ndarray, cutoff: float, fs: float, order: int = 5) -> np.ndarray:
    """
    Apply a Butterworth lowpass filter.
    Uses Second Order Sections (SOS) for numerical stability.
    """
    if not HAS_SCIPY:
        log.warning("Scipy not available. Cannot apply lowpass filter.")
        return data

    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq

    # Use SOS format for numerical stability
    sos = signal.butter(order, normal_cutoff, btype="low", analog=False, output='sos')
    y = signal.sosfiltfilt(sos, data)

    return y


def highpass_filter(data: np.ndarray, cutoff: float, fs: float, order: int = 5) -> np.ndarray:
    """
    Apply a Butterworth highpass filter.
    Uses Second Order Sections (SOS) for numerical stability.
    """
    if not HAS_SCIPY:
        log.warning("Scipy not available. Cannot apply highpass filter.")
        return data

    if fs <= 0:
        raise ValueError("Sampling rate must be positive")

    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq

    # Bounds check
    if normal_cutoff <= 0 or normal_cutoff >= 1:
        log.warning(
            f"Filter frequency {cutoff} Hz is out of bounds for fs={fs} Hz. Returning original data."
        )
        return data

    # Use SOS format for numerical stability (critical for low freq / high fs ratios)
    sos = signal.butter(order, normal_cutoff, btype="high", analog=False, output='sos')
    y = signal.sosfiltfilt(sos, data)

    return y


def notch_filter(data: np.ndarray, freq: float, Q: float, fs: float) -> np.ndarray:
    """
    Apply a notch filter to remove a specific frequency.
    """
    if not HAS_SCIPY:
        log.warning("Scipy not available. Cannot apply notch filter.")
        return data

    if fs <= 0:
        raise ValueError("Sampling rate must be positive")

    nyq = 0.5 * fs
    freq_norm = freq / nyq

    # Bounds check
    if freq_norm <= 0 or freq_norm >= 1:
        log.warning(
            f"Notch frequency {freq} Hz is out of bounds for fs={fs} Hz. Returning original data."
        )
        return data

    b, a = signal.iirnotch(freq_norm, Q)

    # Pad signal
    padlen = 3 * max(len(b), len(a))
    if len(data) <= padlen:
        y = signal.filtfilt(b, a, data)
    else:
        y = signal.filtfilt(b, a, data, padlen=padlen)

    return y


def subtract_baseline_mode(data: np.ndarray, decimals: Optional[int] = None) -> np.ndarray:
    """
    Subtract baseline using the mode of the distribution of values.

    Args:
        data: Input signal array
        decimals: Number of decimal places to round to for mode calculation.
                 If None, it tries to infer a reasonable precision or defaults to 1.

    Returns:
        Data with baseline subtracted (aligned to 0)
    """
    if data is None or len(data) == 0:
        return data

    if not HAS_SCIPY:
        log.warning("Scipy not available. Cannot use mode for baseline subtraction. Using median.")
        return subtract_baseline_median(data)

    # Infer decimals if not provided? For now default to 1 as per original behavior if None
    # Better yet, let's keep it explicit.
    if decimals is None:
        decimals = 1

    # Round data to bin values
    rounded_data = np.round(data, decimals)

    # Calculate mode
    try:
        # scipy.stats.mode returns (mode_array, count_array)
        # Using keepdims=False for scalar result in newer scipy
        # But older scipy might not have keepdims, or return array.
        mode_result = stats.mode(rounded_data, axis=None, keepdims=False)

        if np.isscalar(mode_result.mode):
            baseline_offset = mode_result.mode
        elif np.ndim(mode_result.mode) == 0:
            baseline_offset = mode_result.mode.item()
        else:
            baseline_offset = mode_result.mode[0]

    except (ValueError, TypeError, IndexError) as e:
        log.warning(f"Mode calculation failed: {e}. Fallback to median.")
        baseline_offset = np.median(data)

    log.debug(f"Baseline subtraction (Mode): Calculated offset = {baseline_offset}")
    return data - baseline_offset


def subtract_baseline_mean(data: np.ndarray) -> np.ndarray:
    """Subtract the mean of the entire signal."""
    if data is None or len(data) == 0:
        return data
    return data - np.mean(data)


def subtract_baseline_median(data: np.ndarray) -> np.ndarray:
    """Subtract the median of the entire signal."""
    if data is None or len(data) == 0:
        return data
    return data - np.median(data)


def subtract_baseline_linear(data: np.ndarray) -> np.ndarray:
    """
    Subtract a linear trend (detrend) from the signal.
    Useful for removing drift.
    """
    if data is None or len(data) == 0:
        return data

    if not HAS_SCIPY:
        log.warning("Scipy not available. Cannot detrend.")
        return data

    return signal.detrend(data, type='linear')


def subtract_baseline_region(data: np.ndarray, t: np.ndarray, start_t: float, end_t: float) -> np.ndarray:
    """
    Subtract the mean value calculated from a specific time window.

    Args:
        data: Signal array
        t: Time vector (must be same length as data)
        start_t: Start time of baseline window
        end_t: End time of baseline window
    """
    if data is None or len(data) == 0 or t is None or len(t) == 0:
        return data

    mask = (t >= start_t) & (t <= end_t)
    if not np.any(mask):
        log.warning(f"Baseline region {start_t}-{end_t} contains no data points. Returning original.")
        return data

    baseline_offset = np.mean(data[mask])
    log.debug(f"Baseline subtraction (Region {start_t}-{end_t}): Calculated offset = {baseline_offset:.4f}")
    return data - baseline_offset
