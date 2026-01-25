"""
Signal processing utilities for Synaptipy.
Includes filtering and trace quality checks.
"""

import logging
import numpy as np
from scipy import signal, stats
from typing import Dict, Any, Tuple, Optional

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
            # results['is_good'] = False # Don't fail automatically, just warn

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

    except Exception as e:
        log.error(f"Error during trace quality check: {e}")
        results["is_good"] = False
        results["error"] = str(e)

    return results


def bandpass_filter(data: np.ndarray, lowcut: float, highcut: float, fs: float, order: int = 5) -> np.ndarray:
    """
    Apply a Butterworth bandpass filter to the data.
    """
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

    b, a = signal.butter(order, [low, high], btype="band")
    y = signal.filtfilt(b, a, data)
    return y


def lowpass_filter(data: np.ndarray, cutoff: float, fs: float, order: int = 5) -> np.ndarray:
    """
    Apply a Butterworth lowpass filter.
    """
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = signal.butter(order, normal_cutoff, btype="low", analog=False)
    y = signal.filtfilt(b, a, data)
    return y
