# examples/plugins/spike_interface_integration.py
# -*- coding: utf-8 -*-
"""
Synaptipy Plugin: Extracellular Spike Detection via SpikeInterface.

Integrates seamlessly with the standard Synaptipy channel-selector pipeline:

1. The user opens a recording in Synaptipy and selects the extracellular
   field channel (e.g. "Field") in the Analyser tab exactly as for any other
   analysis.
2. Synaptipy passes the selected channel's 1-D numpy trace to this plugin
   wrapper, just like every other analysis function.
3. The plugin wraps the array in a ``spikeinterface.core.NumpyRecording`` and
   runs bandpass filtering + threshold-based peak detection entirely inside
   SpikeInterface - no external sorter binary required.
4. Detected spike times are returned for vline overlay on the trace view and
   summary metrics are shown in the results table.

Dependencies (not bundled with Synaptipy - install separately)::

    pip install spikeinterface

Usage
-----
Place this file in ``examples/plugins/`` or ``~/.synaptipy/plugins/`` for
automatic discovery by the Synaptipy plugin loader.

This file is part of Synaptipy, licensed under the GNU Affero General Public
License v3.0.  See the LICENSE file at the repository root for full details.
"""

import contextlib
import io
import logging
import warnings
from typing import Any, Dict, List, Optional

import numpy as np

from synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Part 1 - Pure analysis logic (no GUI imports, lazy SpikeInterface imports)
# ---------------------------------------------------------------------------


def _run_bandpass_filter(spp: Any, recording: Any, freq_min: float, freq_max: float, duration_s: float) -> Any:
    """Apply SpikeInterface bandpass filter safely across high- and low-cutoff regimes."""
    filter_kwargs: Dict[str, Any] = {
        "freq_min": float(freq_min),
        "freq_max": float(freq_max),
    }
    if float(freq_min) < 100.0:
        duration_ms = max(20.0, float(duration_s) * 1000.0)
        safe_margin_ms = min(max(5.0, 1000.0 / max(float(freq_min), 1.0)), max(5.0, 0.20 * duration_ms))
        filter_kwargs["ignore_low_freq_error"] = True
        filter_kwargs["margin_ms"] = float(safe_margin_ms)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*margin size.*", category=UserWarning)
        try:
            return spp.bandpass_filter(recording, **filter_kwargs)
        except TypeError:
            filter_kwargs.pop("ignore_low_freq_error", None)
            filter_kwargs.pop("margin_ms", None)
            return spp.bandpass_filter(recording, **filter_kwargs)


def _snap_low_freq_indices_to_raw_peaks(
    data: np.ndarray,
    sample_indices: List[int],
    sampling_rate: float,
    freq_max: float,
    peak_sign: str,
    exclude_sweep_ms: float,
) -> List[int]:
    """Refine filtered peak indices to raw waveform extrema when low-pass smoothing introduces phase lag."""
    if float(freq_max) >= 2000.0 or not sample_indices:
        return sample_indices
    max_half_s = min(0.5 / max(float(freq_max), 1.0), 0.0015, 0.45 * max(float(exclude_sweep_ms), 0.5) / 1000.0)
    half_win = max(1, int(round(max_half_s * float(sampling_rate))))
    med_val = float(np.median(data))
    snapped: List[int] = []
    for idx in sample_indices:
        lo = max(0, idx - half_win)
        hi = min(len(data), idx + half_win + 1)
        seg = data[lo:hi]
        if seg.size == 0:
            snapped.append(idx)
        elif peak_sign == "pos":
            snapped.append(lo + int(np.argmax(seg)))
        elif peak_sign == "neg":
            snapped.append(lo + int(np.argmin(seg)))
        else:
            snapped.append(lo + int(np.argmax(np.abs(seg - med_val))))
    return snapped


def detect_spikes_spikeinterface(
    data: np.ndarray,
    sampling_rate: float,
    freq_min: float,
    freq_max: float,
    threshold_mad: float,
    peak_sign: str,
    time: Optional[np.ndarray] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Detect spikes in a 1-D extracellular trace using SpikeInterface.

    The trace is wrapped in a ``NumpyRecording``, bandpass-filtered, and then
    processed by ``detect_peaks`` (``by_channel`` method, no external binary
    needed).  The noise floor is estimated robustly with the median absolute
    deviation (MAD) of the filtered trace.

    Args:
        data: 1-D voltage trace (any physical unit, e.g. mV or uV).
            Shape ``(N,)``.  The amplitude unit carries through to the
            reported threshold and noise values unchanged.
        sampling_rate: Sampling frequency in Hz.
        freq_min: Lower bandpass cutoff in Hz (typical: 300).
        freq_max: Upper bandpass cutoff in Hz (typical: 6000).
        threshold_mad: Spike threshold expressed as a multiple of the
            MAD-based noise estimate.  Increase to require larger spikes
            (less sensitive); decrease to detect smaller events (more
            sensitive).  A value of 5.0 follows the SpikeInterface / Kilosort
            convention and works well for extracellular field recordings with
            moderate SNR (3-10x); use 8-15 for very low-noise single-unit
            probes.
        peak_sign: Polarity of spikes to detect: ``"neg"`` (negative,
            typical for extracellular field recordings), ``"pos"``, or
            ``"both"``.
        **kwargs: Additional keyword arguments forwarded to ``detect_peaks``
            (e.g. ``exclude_sweep_ms``).  Unrecognised keys are ignored.

    Returns:
        Dict matching the Synaptipy result schema, or ``{"error": ...}`` on
        failure.
    """
    if data.ndim != 1 or data.size == 0:
        return {"error": "data must be a non-empty 1-D array"}
    if not np.isfinite(sampling_rate) or sampling_rate <= 0:
        return {"error": "sampling_rate must be a positive finite value"}
    nyquist_hz = float(sampling_rate) / 2.0
    if not (0 < freq_min < freq_max < nyquist_hz):
        return {"error": ("Bandpass cutoffs must satisfy 0 < freq_min < freq_max < " f"Nyquist ({nyquist_hz:g} Hz).")}

    # Lazy imports so the plugin loads even without spikeinterface installed
    try:
        import spikeinterface.core as sc
        import spikeinterface.preprocessing as spp
        from spikeinterface.sortingcomponents.peak_detection import detect_peaks
    except ImportError as exc:
        return {"error": f"SpikeInterface is not installed: {exc}"}

    log.info("SpikeInterface: starting sorting pipeline")
    duration_s = float(data.size) / float(sampling_rate)

    try:
        # ------------------------------------------------------------------ #
        # 1. Wrap the numpy trace in a NumpyRecording (1 channel, 1 segment) #
        # ------------------------------------------------------------------ #
        traces_2d = data.astype(np.float32).reshape(-1, 1)
        recording = sc.NumpyRecording(
            traces_list=[traces_2d],
            sampling_frequency=float(sampling_rate),
        )

        # ------------------------------------------------------------------ #
        # 2. Bandpass filter                                                 #
        # ------------------------------------------------------------------ #
        log.info("SpikeInterface: running sorter 'bandpass_filter'...")
        recording_f = _run_bandpass_filter(spp, recording, float(freq_min), float(freq_max), duration_s)

        # ------------------------------------------------------------------ #
        # 3. Noise estimate via MAD on the filtered trace                    #
        # ------------------------------------------------------------------ #
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*smaller than the recommended margin.*", category=UserWarning)
            warnings.filterwarnings("ignore", message=".*margin size.*", category=UserWarning)
            filt_traces: np.ndarray = recording_f.get_traces(segment_index=0).astype(np.float64).ravel()
        noise_estimate = float(np.median(np.abs(filt_traces)) / 0.6745)

        if not np.isfinite(noise_estimate) or noise_estimate < 1e-12:
            return {"error": "Noise estimate is effectively zero - check the input trace or filter band"}

        threshold_absolute = threshold_mad * noise_estimate
        exclude_ms = float(kwargs.get("exclude_sweep_ms", 5.0))

        # ------------------------------------------------------------------ #
        # 4. Detect peaks                                                    #
        # ------------------------------------------------------------------ #
        with (
            warnings.catch_warnings(),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            warnings.filterwarnings("ignore", message=".*signature of detect_peaks.*", category=UserWarning)
            warnings.filterwarnings("ignore", message=".*margin size.*", category=UserWarning)
            peaks = detect_peaks(
                recording_f,
                method="by_channel",
                detect_threshold=float(threshold_mad),
                peak_sign=peak_sign,
                exclude_sweep_ms=exclude_ms,
                noise_levels=np.array([noise_estimate]),
            )
    except Exception as exc:
        log.warning("SpikeInterface detection error: %s", exc)
        return {"error": f"SpikeInterface filter/detection failed: {exc}"}

    t0 = float(time[0]) if time is not None and len(time) > 0 else 0.0
    raw_indices = [int(i) for i in peaks["sample_index"] if 0 <= int(i) < len(data)]
    sample_indices = _snap_low_freq_indices_to_raw_peaks(
        data, raw_indices, float(sampling_rate), float(freq_max), peak_sign, exclude_ms
    )
    if time is not None and len(time) == len(data):
        spike_times_s: List[float] = [float(time[i]) for i in sample_indices]
    else:
        spike_times_s = [float(i) / float(sampling_rate) + t0 for i in sample_indices]
    spike_trace_y: List[float] = [float(data[i]) for i in sample_indices]
    spike_filtered_amplitudes: List[float] = [float(filt_traces[i]) for i in raw_indices if i < len(filt_traces)]
    spike_count = len(spike_times_s)
    firing_rate_hz = float(spike_count) / duration_s if duration_s > 0 else 0.0

    log.info("SpikeInterface: sorting complete - %d units found", spike_count)

    return {
        "module_used": "spike_interface",
        "metrics": {
            "Spike_Count": spike_count,
            "Noise_Estimate": round(noise_estimate, 4),
            "Threshold": round(threshold_absolute, 4),
            "Mean_Firing_Rate_Hz": round(firing_rate_hz, 4),
        },
        # Private: used for vline overlay and scatter markers on the Synaptipy trace view.
        # _spike_amplitudes uses raw trace y-values so markers sit on DC-offset traces;
        # _spike_filtered_amplitudes preserves bandpass-filtered peak values.
        "_spike_times": spike_times_s,
        "_spike_amplitudes": spike_trace_y,
        "_spike_trace_y": spike_trace_y,
        "_spike_filtered_amplitudes": spike_filtered_amplitudes,
    }


# ---------------------------------------------------------------------------
# Part 2 - Registry wrapper (decorator drives the GUI automatically)
# ---------------------------------------------------------------------------


@AnalysisRegistry.register(
    name="spike_interface_detection",
    label="Spike Detection (SpikeInterface)",
    expects_list=False,
    run_button=True,
    ui_params=[
        {
            "name": "freq_min",
            "label": "High-pass Freq (Hz):",
            "type": "float",
            "default": 300.0,
            "min": 1.0,
            "max": 10000.0,
            "decimals": 1,
            "tooltip": (
                "Lower cutoff of the bandpass pre-filter "
                "(typical: 300 Hz for extracellular spikes; 10-50 Hz for intracellular APs)."
            ),
        },
        {
            "name": "freq_max",
            "label": "Low-pass Freq (Hz):",
            "type": "float",
            "default": 6000.0,
            "min": 100.0,
            "max": 100000.0,
            "decimals": 1,
            "tooltip": (
                "Upper cutoff of the bandpass pre-filter.  " "Removes high-frequency noise (typical: 6000 Hz)."
            ),
        },
        {
            "name": "threshold_mad",
            "label": "Threshold (x MAD):",
            "type": "float",
            "default": 5.0,
            "min": 1.0,
            "max": 100.0,
            "decimals": 1,
            "tooltip": (
                "Spike threshold as a multiple of the MAD noise estimate.  "
                "Higher = fewer, larger spikes.  "
                "5 follows the SpikeInterface/Kilosort convention and works well "
                "for extracellular field recordings with moderate SNR."
            ),
        },
        {
            "name": "peak_sign",
            "label": "Peak polarity:",
            "type": "choice",
            "options": ["neg", "pos", "both"],
            "default": "neg",
            "tooltip": (
                "Polarity of spikes to detect.  " "Extracellular field recordings typically have negative spikes."
            ),
        },
        {
            "name": "exclude_sweep_ms",
            "label": "Refractory period (ms):",
            "type": "float",
            "default": 5.0,
            "min": 0.5,
            "max": 50.0,
            "decimals": 1,
            "tooltip": (
                "Minimum time (ms) between two detected spikes.  "
                "Prevents double-counting of secondary deflections in "
                "compound field potentials.  Typical: 3-5 ms."
            ),
        },
    ],
    plots=[
        {
            "type": "vlines",
            "data": "_spike_times",
            "color": "r",
        },
        {
            "type": "markers",
            "x": "_spike_times",
            "y": "_spike_amplitudes",
            "color": "r",
            "symbol": "o",
        },
    ],
)
def run_spike_interface_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Registry wrapper for spike_interface_detection.

    Extracts GUI parameters from kwargs and delegates to
    ``detect_spikes_spikeinterface``.  The ``data`` array comes directly from
    the Synaptipy channel selector - select the extracellular field channel
    before running this analysis.

    Args:
        data: 1-D voltage trace of the selected channel.
        time: 1-D time array in seconds (same length as data).
            Not used directly; sampling_rate is used instead.
        sampling_rate: Sampling frequency in Hz.
        **kwargs: GUI parameters injected by the analysis engine:
            ``freq_min``, ``freq_max``, ``threshold_mad``, ``peak_sign``.

    Returns:
        Result dict - see ``detect_spikes_spikeinterface`` for the schema.
    """
    freq_min_val = float(kwargs.get("freq_min", 300.0))
    freq_max_val = float(kwargs.get("freq_max", 6000.0))
    extra_warnings: List[str] = []
    if np.isfinite(sampling_rate) and sampling_rate > 0:
        nyq = float(sampling_rate) / 2.0
        if freq_max_val >= 0.95 * nyq and nyq > freq_min_val + 20.0:
            clamped_max = round(0.90 * nyq, 1)
            extra_warnings.append(
                f"Low-pass cutoff ({freq_max_val:g} Hz) exceeded Nyquist ({nyq:g} Hz) "
                f"and was clamped to {clamped_max:g} Hz."
            )
            freq_max_val = clamped_max

    res = detect_spikes_spikeinterface(
        data=data,
        sampling_rate=sampling_rate,
        freq_min=freq_min_val,
        freq_max=freq_max_val,
        threshold_mad=float(kwargs.get("threshold_mad", 5.0)),
        peak_sign=str(kwargs.get("peak_sign", "neg")),
        time=time,
        exclude_sweep_ms=float(kwargs.get("exclude_sweep_ms", 5.0)),
    )
    if extra_warnings and isinstance(res, dict):
        res["warnings"] = list(res.get("warnings", [])) + extra_warnings
    return res
