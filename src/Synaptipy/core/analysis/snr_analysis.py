"""
Custom Synaptipy Plugin: Signal-to-Noise Ratio (SNR) Analysis.

Drop this file in ~/.synaptipy/plugins/ and restart Synaptipy.
A new "Signal-to-Noise Ratio" tab will appear in the Analyser.
"""

import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# -- Part 1: Pure logic ------------------------------------------------
def calculate_snr(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    noise_start: float,
    noise_end: float,
    signal_start: float,
    signal_end: float,
) -> Dict[str, Any]:
    """
    Calculate signal-to-noise ratio.

    Args:
        data: 1-D voltage trace.
        time: 1-D time array in seconds.
        sampling_rate: Sampling rate in Hz.
        noise_start: Start of the noise-only window (seconds).
        noise_end: End of the noise-only window (seconds).
        signal_start: Start of the signal window (seconds).
        signal_end: End of the signal window (seconds).

    Returns:
        Dict with 'snr_db', 'noise_rms', 'signal_rms'.
    """
    if data.size == 0:
        return {"error": "Empty data array"}

    # Convert time boundaries to sample indices
    noise_i0 = int(np.searchsorted(time, noise_start, side="left"))
    noise_i1 = int(np.searchsorted(time, noise_end, side="right"))
    sig_i0 = int(np.searchsorted(time, signal_start, side="left"))
    sig_i1 = int(np.searchsorted(time, signal_end, side="right"))

    noise_segment = data[noise_i0:noise_i1]
    signal_segment = data[sig_i0:sig_i1]

    if noise_segment.size < 2 or signal_segment.size < 2:
        return {"error": "Window too narrow - need at least 2 samples"}

    noise_rms = float(np.sqrt(np.mean(noise_segment**2)))
    signal_rms = float(np.sqrt(np.mean(signal_segment**2)))

    if noise_rms == 0:
        return {"error": "Noise RMS is zero - cannot compute SNR"}

    snr_db = float(20.0 * np.log10(signal_rms / noise_rms))

    return {
        "snr_db": round(snr_db, 2),
        "noise_rms": round(noise_rms, 4),
        "signal_rms": round(signal_rms, 4),
        # Hidden keys for plot overlays (not shown in results table)
        "_noise_level": noise_rms,
        "_signal_level": signal_rms,
    }


# -- Part 2: Registry wrapper ------------------------------------------
@AnalysisRegistry.register(
    name="snr_analysis",
    label="Signal-to-Noise Ratio",
    ui_params=[
        {
            "name": "noise_start",
            "label": "Noise Window Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "noise_end",
            "label": "Noise Window End (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "signal_start",
            "label": "Signal Window Start (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "signal_end",
            "label": "Signal Window End (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
    ],
    plots=[
        # Draggable region for noise window (blue)
        {"type": "interactive_region", "data": ["noise_start", "noise_end"], "color": "b"},
        # Draggable region for signal window (green)
        {"type": "interactive_region", "data": ["signal_start", "signal_end"], "color": "g"},
        # Horizontal line at noise RMS level
        {"type": "hlines", "data": ["_noise_level"], "color": "b", "styles": ["dash"]},
        # Horizontal line at signal RMS level
        {"type": "hlines", "data": ["_signal_level"], "color": "g", "styles": ["solid"]},
    ],
)
def run_snr_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """Registry wrapper - extracts kwargs and calls pure logic."""
    return calculate_snr(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        noise_start=kwargs.get("noise_start", 0.0),
        noise_end=kwargs.get("noise_end", 0.1),
        signal_start=kwargs.get("signal_start", 0.1),
        signal_end=kwargs.get("signal_end", 0.5),
    )
