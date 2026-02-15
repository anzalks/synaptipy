"""
Signal processing utilities for Synaptipy.
Includes filtering and trace quality checks.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional


def _get_scipy():
    """Lazily import scipy modules. Returns (signal_module, stats_module, has_scipy).

    Does NOT cache to prevent mock leakage between tests.
    """
    try:
        import scipy.signal as sig
        import scipy.stats as st
        return sig, st, True
    except ImportError:
        return None, None, False


log = logging.getLogger(__name__)


def validate_sampling_rate(fs: float) -> bool:
    """
    Validate sampling rate and warn if suspiciously low.

    Args:
        fs: Sampling rate in Hz.

    Returns:
        True if valid (positive), False otherwise.
    """
    if fs <= 0:
        log.error("Sampling rate must be positive, got %s", fs)
        return False
    if fs < 100:
        log.warning(
            "Sampling rate is suspiciously low (<100 Hz). Are you using kHz instead of Hz?"
        )
    return True


def check_trace_quality(data: np.ndarray, sampling_rate: float) -> Dict[str, Any]:  # noqa: C901
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
        signal, stats, has_scipy = _get_scipy()
        if not has_scipy:
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

        # 4. Low-Frequency Variance ("wobbly" baseline detection)
        # Apply <1Hz lowpass filter and measure variance of slow drift.
        nyq = 0.5 * sampling_rate
        lf_cutoff = 1.0 / nyq
        if 0 < lf_cutoff < 1 and len(detrended) > 30:
            try:
                sos_lf = signal.butter(2, lf_cutoff, btype='low', output='sos')
                lf_signal = signal.sosfiltfilt(sos_lf, detrended, padtype='odd')
                lf_variance = float(np.var(lf_signal))
                results["metrics"]["lf_variance"] = lf_variance

                # Compare to overall noise variance
                hf_variance = float(np.var(detrended - lf_signal))
                if hf_variance > 0 and lf_variance > 2.0 * hf_variance:
                    results["warnings"].append(
                        f"Low-frequency instability detected "
                        f"(LF var={lf_variance:.4f} > 2x HF var={hf_variance:.4f})"
                    )
            except Exception as lf_err:
                log.debug("LF variance check skipped: %s", lf_err)
        else:
            results["metrics"]["lf_variance"] = None

    except (ValueError, TypeError, RuntimeError) as e:
        log.error(f"Error during trace quality check: {e}")
        results["is_good"] = False
        results["error"] = str(e)

    return results


def _validate_filter_input(data: np.ndarray, fs: float, order: int = 5) -> tuple:
    """
    Common validation for all filter functions.

    Returns:
        (is_valid, data_or_error_msg)
        If valid: (True, data)
        If invalid: (False, original_data) - caller should return this unchanged
    """
    # Empty data check
    if data is None or len(data) == 0:
        log.warning("Empty data provided to filter. Returning unchanged.")
        return False, data if data is not None else np.array([])

    # Sampling rate check
    if fs <= 0:
        log.error(f"Sampling rate must be positive, got {fs}")
        return False, data

    # Order validation
    if order < 1 or order > 10:
        log.warning(f"Filter order {order} outside recommended range [1, 10]. Clamping.")
        order = max(1, min(10, order))

    # NaN/Inf check
    if np.any(np.isnan(data)) or np.any(np.isinf(data)):
        log.warning("Data contains NaN or Inf values. Returning unchanged.")
        return False, data

    # Minimum length check for filtfilt (needs at least 3*order samples)
    min_length = 3 * order + 1
    if len(data) < min_length:
        log.warning(f"Data too short ({len(data)} samples) for filter order {order}. Need at least {min_length}.")
        return False, data

    return True, data


def bandpass_filter(data: np.ndarray, lowcut: float, highcut: float, fs: float, order: int = 5) -> np.ndarray:
    """
    Apply a Butterworth bandpass filter to the data.
    Uses Second Order Sections (SOS) for numerical stability.

    Args:
        data: Input signal array
        lowcut: Low cutoff frequency in Hz
        highcut: High cutoff frequency in Hz
        fs: Sampling frequency in Hz
        order: Filter order (1-10, default 5)

    Returns:
        Filtered data, or original data if filtering fails
    """
    signal, _, has_scipy = _get_scipy()
    if not has_scipy:
        log.warning("Scipy not available. Cannot apply bandpass filter.")
        return data

    # Validate input
    is_valid, result = _validate_filter_input(data, fs, order)
    if not is_valid:
        return result

    # Clamp order
    order = max(1, min(10, order))

    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq

    # Bounds check
    if low <= 0 or low >= 1:
        log.warning(f"Low cutoff {lowcut} Hz out of bounds for fs={fs} Hz. Returning original.")
        return data
    if high <= 0 or high >= 1:
        log.warning(f"High cutoff {highcut} Hz out of bounds for fs={fs} Hz. Returning original.")
        return data
    if low >= high:
        log.warning(f"Low cutoff {lowcut} Hz >= high cutoff {highcut} Hz. Returning original.")
        return data

    try:
        # Use SOS format for numerical stability
        sos = signal.butter(order, [low, high], btype="band", output='sos')
        y = signal.sosfiltfilt(sos, data, padtype='odd')
        return y
    except Exception as e:
        log.error(f"Bandpass filter failed: {e}")
        return data


def lowpass_filter(data: np.ndarray, cutoff: float, fs: float, order: int = 5) -> np.ndarray:
    """
    Apply a Butterworth lowpass filter.
    Uses Second Order Sections (SOS) for numerical stability.

    Args:
        data: Input signal array
        cutoff: Cutoff frequency in Hz
        fs: Sampling frequency in Hz
        order: Filter order (1-10, default 5)

    Returns:
        Filtered data, or original data if filtering fails
    """
    signal, _, has_scipy = _get_scipy()
    if not has_scipy:
        log.warning("Scipy not available. Cannot apply lowpass filter.")
        return data

    # Validate input
    is_valid, result = _validate_filter_input(data, fs, order)
    if not is_valid:
        return result

    # Clamp order
    order = max(1, min(10, order))

    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq

    # Bounds check (was missing!)
    if normal_cutoff <= 0 or normal_cutoff >= 1:
        log.warning(f"Cutoff {cutoff} Hz out of bounds for fs={fs} Hz. Returning original.")
        return data

    try:
        # Use SOS format for numerical stability
        sos = signal.butter(order, normal_cutoff, btype="low", analog=False, output='sos')
        y = signal.sosfiltfilt(sos, data, padtype='odd')
        return y
    except Exception as e:
        log.error(f"Lowpass filter failed: {e}")
        return data


def highpass_filter(data: np.ndarray, cutoff: float, fs: float, order: int = 5) -> np.ndarray:
    """
    Apply a Butterworth highpass filter.
    Uses Second Order Sections (SOS) for numerical stability.

    Args:
        data: Input signal array
        cutoff: Cutoff frequency in Hz
        fs: Sampling frequency in Hz
        order: Filter order (1-10, default 5)

    Returns:
        Filtered data, or original data if filtering fails
    """
    signal, _, has_scipy = _get_scipy()
    if not has_scipy:
        log.warning("Scipy not available. Cannot apply highpass filter.")
        return data

    # Validate input
    is_valid, result = _validate_filter_input(data, fs, order)
    if not is_valid:
        return result

    # Clamp order
    order = max(1, min(10, order))

    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq

    # Bounds check
    if normal_cutoff <= 0 or normal_cutoff >= 1:
        log.warning(f"Cutoff {cutoff} Hz out of bounds for fs={fs} Hz. Returning original.")
        return data

    try:
        # Use SOS format for numerical stability
        sos = signal.butter(order, normal_cutoff, btype="high", analog=False, output='sos')
        y = signal.sosfiltfilt(sos, data, padtype='odd')
        return y
    except Exception as e:
        log.error(f"Highpass filter failed: {e}")
        return data


def notch_filter(data: np.ndarray, freq: float, Q: float, fs: float) -> np.ndarray:
    """
    Apply a notch filter to remove a specific frequency.
    Uses SOS format via zpk2sos for numerical stability.

    Args:
        data: Input signal array
        freq: Notch frequency in Hz
        Q: Quality factor (higher = narrower notch)
        fs: Sampling frequency in Hz

    Returns:
        Filtered data, or original data if filtering fails
    """
    signal, _, has_scipy = _get_scipy()
    if not has_scipy:
        log.warning("Scipy not available. Cannot apply notch filter.")
        return data

    # Validate input (order=2 for notch is standard)
    is_valid, result = _validate_filter_input(data, fs, order=2)
    if not is_valid:
        return result

    nyq = 0.5 * fs
    freq_norm = freq / nyq

    # Bounds check
    if freq_norm <= 0 or freq_norm >= 1:
        log.warning(f"Notch frequency {freq} Hz out of bounds for fs={fs} Hz. Returning original.")
        return data

    # Q factor validation
    if Q <= 0:
        log.warning(f"Q factor must be positive, got {Q}. Using Q=30.")
        Q = 30.0

    try:
        # Get zpk representation and convert to SOS for stability
        b, a = signal.iirnotch(freq_norm, Q)
        # Convert to zpk then to sos for stability
        z, p, k = signal.tf2zpk(b, a)
        sos = signal.zpk2sos(z, p, k)
        y = signal.sosfiltfilt(sos, data, padtype='odd')
        return y
    except Exception as e:
        log.error(f"Notch filter failed: {e}")
        return data


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

    _, stats, has_scipy = _get_scipy()
    if not has_scipy:
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

    signal, _, has_scipy = _get_scipy()
    if not has_scipy:
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


def find_artifact_windows(
    data: np.ndarray, fs: float, slope_threshold: float, padding_ms: float = 2.0
) -> np.ndarray:
    """
    Identify time windows containing high-slope artifacts.

    Algorithm:
    1. Calculate absolute gradient of the data.
    2. Threshold gradient to find high-slope points.
    3. Dilate the boolean mask by `padding_ms` to capture the artifact tail/ringing.

    Args:
        data: Signal array.
        fs: Sampling rate in Hz.
        slope_threshold: Threshold for the absolute gradient (e.g. pA/sample or mV/sample).
        padding_ms: Time to expand the mask around detected peaks (in milliseconds).

    Returns:
        Boolean mask of the same shape as `data`, where True indicates an artifact.
    """
    if data is None or len(data) == 0:
        return np.array([], dtype=bool)

    # Lazily import scipy
    _, _, has_scipy = _get_scipy()
    if not has_scipy:
        log.warning("Scipy not available. Cannot perform artifact dilation.")
        # Fallback: just return thresholded gradient without dilation
        grad = np.abs(np.gradient(data))
        return grad > slope_threshold

    import scipy.ndimage as ndimage

    # 1. Gradient
    grad = np.abs(np.gradient(data))

    # 2. Threshold
    mask = grad > slope_threshold

    # 3. Dilation
    if padding_ms > 0:
        # Interpret padding_ms as Post-Padding (artifact tail).
        # We allow a small fixed Pre-Padding to cover the rising edge.
        post_padding_samples = int((padding_ms / 1000.0) * fs)
        
        # Small fixed pre-padding (0.25 ms or 2 samples minimum)
        pre_padding_ms = 0.25
        pre_padding_samples = int((pre_padding_ms / 1000.0) * fs)
        pre_padding_samples = max(2, pre_padding_samples) 
        
        # Create asymmetric structure
        # Size = 2 * max_reach + 1 to keep center aligned
        max_reach = max(pre_padding_samples, post_padding_samples)
        structure_len = 2 * max_reach + 1
        structure = np.zeros(structure_len, dtype=bool)
        
        center = max_reach
        
        # Left side of kernel (negative offsets) -> Looks at future (right) -> Dilates LEFT (Pre-padding)
        # Right side of kernel (positive offsets) -> Looks at past (left) -> Dilates RIGHT (Post-padding)
        start_idx = center - pre_padding_samples
        end_idx = center + post_padding_samples + 1
        structure[start_idx:end_idx] = True
        
        mask = ndimage.binary_dilation(mask, structure=structure)

    return mask

