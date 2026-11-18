# src/synaptipy/core/analysis/preprocessing.py
# -*- coding: utf-8 -*-
"""
Registered signal-preprocessing processors for BatchAnalysisEngine and CLI parity.

Each processor wraps the pure DSP primitives in ``synaptipy.core.signal_processor``
and registers with ``@AnalysisRegistry.register_processor`` (``type="preprocessing"``)
so GUI preprocessing pipelines execute identically in headless batch runs.
"""

from typing import Any

import numpy as np

from synaptipy.core import signal_processor
from synaptipy.core.analysis.registry import AnalysisRegistry


def _subtract_region_stat(
    data: np.ndarray, time: np.ndarray, start_t: float, end_t: float, method: str, decimals: int
) -> np.ndarray:
    """Subtract region mode or median when a valid time window is supplied."""
    mask = (time >= start_t) & (time <= end_t)
    if not np.any(mask):
        return (
            signal_processor.subtract_baseline_mode(data, decimals=decimals)
            if method == "mode"
            else signal_processor.subtract_baseline_median(data)
        )
    if method == "mode":
        rounded = np.round(data[mask], decimals)
        vals, counts = np.unique(rounded, return_counts=True)
        return data - float(vals[np.argmax(counts)])
    return data - float(np.median(data[mask]))


@AnalysisRegistry.register_processor("baseline_subtraction", label="Baseline Subtraction")
def run_baseline_subtraction_processor(
    data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs: Any
) -> np.ndarray:
    """Subtract baseline offset using mode, mean, median, linear, constant, or region mode."""
    method = str(kwargs.get("method", kwargs.get("mode", "mean"))).strip().lower()
    start_t = kwargs.get("start_t", kwargs.get("start_time", kwargs.get("window_start")))
    end_t = kwargs.get("end_t", kwargs.get("end_time", kwargs.get("window_end")))
    use_region = start_t is not None and end_t is not None and time is not None and float(end_t) > float(start_t)

    if method == "constant" or "offset_value" in kwargs:
        return data - float(kwargs.get("offset_value", 0.0))
    if method in ("detrend", "linear"):
        return signal_processor.subtract_baseline_linear(data)
    if method == "region":
        st = float(start_t) if start_t is not None else 0.0
        et = float(end_t) if end_t is not None else 0.1
        return signal_processor.subtract_baseline_region(data, time, st, et)
    if method in ("mode", "median"):
        decimals = int(kwargs.get("decimals", 1))
        if use_region:
            return _subtract_region_stat(data, time, float(start_t), float(end_t), method, decimals)
        return (
            signal_processor.subtract_baseline_mode(data, decimals=decimals)
            if method == "mode"
            else signal_processor.subtract_baseline_median(data)
        )
    if use_region:
        return signal_processor.subtract_baseline_region(data, time, float(start_t), float(end_t))
    return signal_processor.subtract_baseline_mean(data)


@AnalysisRegistry.register_processor("lowpass_filter", label="Lowpass Filter")
def run_lowpass_processor(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs: Any) -> np.ndarray:
    """Apply zero-phase lowpass filter."""
    cutoff = float(kwargs.get("cutoff", kwargs.get("cutoff_hz", 1000.0)))
    order = int(kwargs.get("order", 5))
    ftype = str(kwargs.get("filter_type", "butterworth"))
    return signal_processor.lowpass_filter(data, cutoff=cutoff, fs=sampling_rate, order=order, filter_type=ftype)


@AnalysisRegistry.register_processor("highpass_filter", label="Highpass Filter")
def run_highpass_processor(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs: Any) -> np.ndarray:
    """Apply zero-phase highpass filter."""
    cutoff = float(kwargs.get("cutoff", kwargs.get("cutoff_hz", 1.0)))
    order = int(kwargs.get("order", 5))
    ftype = str(kwargs.get("filter_type", "butterworth"))
    return signal_processor.highpass_filter(data, cutoff=cutoff, fs=sampling_rate, order=order, filter_type=ftype)


@AnalysisRegistry.register_processor("bandpass_filter", label="Bandpass Filter")
def run_bandpass_processor(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs: Any) -> np.ndarray:
    """Apply zero-phase bandpass filter."""
    lowcut = float(kwargs.get("lowcut", kwargs.get("low_cut", kwargs.get("low_freq", 1.0))))
    highcut = float(kwargs.get("highcut", kwargs.get("high_cut", kwargs.get("high_freq", 1000.0))))
    order = int(kwargs.get("order", 5))
    ftype = str(kwargs.get("filter_type", "butterworth"))
    return signal_processor.bandpass_filter(
        data, lowcut=lowcut, highcut=highcut, fs=sampling_rate, order=order, filter_type=ftype
    )


@AnalysisRegistry.register_processor("notch_filter", label="Notch Filter")
def run_notch_processor(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs: Any) -> np.ndarray:
    """Apply single-frequency line-noise notch filter."""
    freq = float(kwargs.get("freq", kwargs.get("frequency_hz", 50.0)))
    q_factor = float(kwargs.get("Q", kwargs.get("q_factor", 30.0)))
    return signal_processor.notch_filter(data, freq=freq, Q=q_factor, fs=sampling_rate)


@AnalysisRegistry.register_processor("comb_filter", label="Harmonic Comb Filter")
def run_comb_processor(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs: Any) -> np.ndarray:
    """Apply multi-harmonic line-noise notch comb filter."""
    freq = float(kwargs.get("freq", kwargs.get("fundamental_hz", 50.0)))
    q_factor = float(kwargs.get("Q", kwargs.get("q_factor", 30.0)))
    max_harmonics = kwargs.get("max_harmonics")
    max_h = int(max_harmonics) if max_harmonics is not None else None
    return signal_processor.multi_harmonic_notch(
        data, fundamental_hz=freq, fs=sampling_rate, max_harmonics=max_h, Q=q_factor
    )


@AnalysisRegistry.register_processor("detrend_filter", label="Linear Detrend")
def run_detrend_processor(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs: Any) -> np.ndarray:
    """Remove linear or constant drift from trace."""
    method = str(kwargs.get("method", "linear")).strip().lower()
    if method == "constant":
        return signal_processor.subtract_baseline_mean(data)
    return signal_processor.subtract_baseline_linear(data)
