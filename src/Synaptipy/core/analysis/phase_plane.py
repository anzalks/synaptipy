# src/Synaptipy/core/analysis/phase_plane.py
# -*- coding: utf-8 -*-
"""
Analysis functions for Phase Plane (dV/dt vs V) analysis.
"""
import logging
import numpy as np
from scipy.ndimage import gaussian_filter1d
from typing import Tuple, Optional, Dict, Any
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


def calculate_dvdt(voltage: np.ndarray, sampling_rate: float, sigma_ms: float = 0.1) -> np.ndarray:
    """
    Calculates the first derivative of voltage with respect to time (dV/dt).

    Args:
        voltage: 1D NumPy array of voltage data (mV).
        sampling_rate: Sampling rate in Hz.
        sigma_ms: Standard deviation for Gaussian smoothing in milliseconds.
                  Set to 0 to disable smoothing.

    Returns:
        1D NumPy array of dV/dt (V/s).
    """
    dt = 1.0 / sampling_rate

    # Optional smoothing
    if sigma_ms > 0:
        sigma_samples = (sigma_ms / 1000.0) * sampling_rate
        if sigma_samples > 0.5:
            voltage_smooth = gaussian_filter1d(voltage, sigma_samples)
        else:
            voltage_smooth = voltage
    else:
        voltage_smooth = voltage

    # Calculate derivative
    # dV (mV) / dt (s) = mV/s.
    # We usually want V/s. So divide by 1000.
    dvdt = np.gradient(voltage_smooth, dt) / 1000.0

    return dvdt


def get_phase_plane_trajectory(
    voltage: np.ndarray, sampling_rate: float, sigma_ms: float = 0.1
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns the phase plane trajectory (V, dV/dt).

    Args:
        voltage: 1D NumPy array of voltage data.
        sampling_rate: Sampling rate in Hz.
        sigma_ms: Smoothing parameter.

    Returns:
        Tuple (voltage, dvdt).
    """
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
    Detects AP threshold using the 'kink' method in phase plane.
    Threshold is often defined where dV/dt crosses a value (e.g. 20 V/s)
    or where the slope of dV/dt (d2V/dt2) increases sharply.

    Args:
        voltage: Voltage trace.
        sampling_rate: Sampling rate.
        dvdt_threshold: Simple dV/dt threshold (V/s).
        kink_slope: Slope of phase plane (d(dV/dt)/dV) or similar metric.
                    Here we use a simplified approach: first point where dV/dt > dvdt_threshold.
        search_window_ms: Lookback window from peak to find threshold.
        peak_indices: Indices of AP peaks. If None, peaks are detected first.

    Returns:
        Array of threshold indices.
    """
    if peak_indices is None:
        # Simple peak detection if not provided
        from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold

        # Use a high threshold to just find peaks
        res = detect_spikes_threshold(
            voltage, np.arange(len(voltage)) / sampling_rate, -20.0, int(0.002 * sampling_rate)
        )
        peak_indices = res.spike_indices

    dvdt = calculate_dvdt(voltage, sampling_rate, sigma_ms=0.1)
    threshold_indices = []

    _dt = 1.0 / sampling_rate  # noqa: F841
    search_samples = int((search_window_ms / 1000.0) * sampling_rate)

    for peak_idx in peak_indices:
        # Search backwards from peak
        start_search = max(0, peak_idx - search_samples)

        # Slice of dV/dt before peak
        dvdt_slice = dvdt[start_search:peak_idx]

        # Find last point where dV/dt < dvdt_threshold before it goes high
        # Or first point where dV/dt > dvdt_threshold

        # Let's look for the crossing of dvdt_threshold
        crossings = np.where(dvdt_slice > dvdt_threshold)[0]

        if crossings.size > 0:
            # The first crossing in this window is the candidate
            # But we want the *start* of the rise.
            # Often defined as 20 V/s.
            thresh_idx_rel = crossings[0]
            thresh_idx = start_search + thresh_idx_rel
        else:
            # Fallback: point of max curvature?
            # Or just a fixed derivative value
            thresh_idx = max(0, peak_idx - int(0.001 * sampling_rate))  # 1ms before

        threshold_indices.append(thresh_idx)

    return np.array(threshold_indices)


@AnalysisRegistry.register(
    "phase_plane_analysis",
    label="Phase Plane Analysis",
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
    ],
)
def phase_plane_analysis(
    voltage: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    sigma_ms: float = 0.1,
    dvdt_threshold: float = 20.0,
    **kwargs,
) -> Dict[str, Any]:
    """
    Wrapper for Phase Plane analysis.

    Args:
        voltage: Voltage trace
        time: Time array
        sampling_rate: Sampling rate
        sigma_ms: Smoothing sigma
        dvdt_threshold: Threshold for dV/dt detection

    Returns:
        Dict with analysis results
    """
    # Calculate Phase Plane
    v, dvdt = get_phase_plane_trajectory(voltage, sampling_rate, sigma_ms)

    # Detect Threshold
    # First detect peaks to guide threshold search
    # Use a simple threshold for peak detection
    from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold

    spike_res = detect_spikes_threshold(voltage, time, -20.0, int(0.002 * sampling_rate))

    thresh_indices = detect_threshold_kink(
        voltage, sampling_rate, dvdt_threshold=dvdt_threshold, peak_indices=spike_res.spike_indices
    )

    threshold_vals = voltage[thresh_indices] if thresh_indices.size > 0 else []

    return {
        "voltage": v,
        "dvdt": dvdt,
        "threshold_indices": thresh_indices,
        "threshold_vals": threshold_vals,
        "max_dvdt": np.max(dvdt) if len(dvdt) > 0 else 0.0,
        "threshold_mean": np.mean(threshold_vals) if len(threshold_vals) > 0 else np.nan,
    }
