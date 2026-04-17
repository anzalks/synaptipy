# src/Synaptipy/core/processing_pipeline.py
# -*- coding: utf-8 -*-
"""
Signal Processing Pipeline.

Formalizes the order of operations for signal processing (e.g., Baseline -> Filter).
Ensures that both visualization and analysis use the exact same processing sequence.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from Synaptipy.core import signal_processor

log = logging.getLogger(__name__)


class SignalProcessingPipeline:
    """
    Manages an ordered list of signal processing steps.
    """

    def __init__(self):
        self._steps: List[Dict[str, Any]] = []

    def add_step(self, step_config: Dict[str, Any], index: Optional[int] = None):
        """
        Add a processing step to the pipeline.

        Args:
            step_config: Dictionary defining the step (e.g., {'type': 'baseline', 'method': 'mean'})
            index: Optional index to insert at. If None, appends to end.
        """
        if index is not None:
            self._steps.insert(index, step_config)
        else:
            self._steps.append(step_config)
        log.debug(f"Added pipeline step: {step_config}")

    def remove_step_by_type(self, step_type: str):
        """Remove all steps of a specific type (e.g. 'baseline')."""
        original_count = len(self._steps)
        self._steps = [s for s in self._steps if s.get("type") != step_type]
        if len(self._steps) < original_count:
            log.debug(f"Removed steps of type '{step_type}'")

    def clear(self):
        """Clear all steps."""
        self._steps.clear()
        log.debug("Pipeline cleared")

    def get_steps(self) -> List[Dict[str, Any]]:
        """Return a copy of the current steps."""
        return [s.copy() for s in self._steps]

    def set_steps(self, steps: List[Dict[str, Any]]):
        """Replace all steps."""
        self._steps = [s.copy() for s in steps]
        log.debug(f"Pipeline steps set to: {self._steps}")

    def process(  # noqa: C901
        self, data: np.ndarray, fs: float, time_vector: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Apply all steps in order to the data.

        Args:
            data: Input signal array
            fs: Sampling rate in Hz
            time_vector: Optional time vector (required for region-based baseline)

        Returns:
            Processed data array
        """
        if data is None or len(data) == 0:
            return data

        result = data.copy()

        for step in self._steps:
            try:
                op_type = step.get("type")

                if op_type == "baseline":
                    method = step.get("method", "mode")
                    start_t = step.get("start_t")
                    end_t = step.get("end_t")
                    use_region = (
                        start_t is not None
                        and end_t is not None
                        and time_vector is not None
                        and method in ("mean", "median", "mode")
                    )
                    if method == "mode":
                        if use_region:
                            mask = (time_vector >= float(start_t)) & (time_vector <= float(end_t))
                            if np.any(mask):
                                decimals = int(step.get("decimals", 1))
                                rounded = np.round(result[mask], decimals)
                                if len(rounded):
                                    vals, counts = np.unique(rounded, return_counts=True)
                                    result = result - float(vals[np.argmax(counts)])
                            else:
                                decimals = int(step.get("decimals", 1))
                                result = signal_processor.subtract_baseline_mode(result, decimals=decimals)
                        else:
                            decimals = int(step.get("decimals", 1))
                            result = signal_processor.subtract_baseline_mode(result, decimals=decimals)
                    elif method == "mean":
                        if use_region:
                            result = signal_processor.subtract_baseline_region(
                                result, time_vector, float(start_t), float(end_t)
                            )
                        else:
                            result = signal_processor.subtract_baseline_mean(result)
                    elif method == "median":
                        if use_region:
                            mask = (time_vector >= float(start_t)) & (time_vector <= float(end_t))
                            if np.any(mask):
                                result = result - float(np.median(result[mask]))
                            else:
                                result = signal_processor.subtract_baseline_median(result)
                        else:
                            result = signal_processor.subtract_baseline_median(result)
                    elif method == "linear":
                        result = signal_processor.subtract_baseline_linear(result)
                    elif method == "region":
                        if time_vector is not None:
                            st = float(step.get("start_t", 0.0))
                            et = float(step.get("end_t", 0.0))
                            result = signal_processor.subtract_baseline_region(result, time_vector, st, et)
                        else:
                            log.warning("Region baseline requested but no time vector provided. Skipping.")

                elif op_type == "filter":
                    method = step.get("method")
                    order = int(step.get("order", 5))

                    if method == "lowpass":
                        result = signal_processor.lowpass_filter(result, float(step.get("cutoff")), fs, order=order)
                    elif method == "highpass":
                        result = signal_processor.highpass_filter(result, float(step.get("cutoff")), fs, order=order)
                    elif method == "bandpass":
                        result = signal_processor.bandpass_filter(
                            result, float(step.get("low_cut")), float(step.get("high_cut")), fs, order=order
                        )
                    elif method == "notch":
                        result = signal_processor.notch_filter(
                            result, float(step.get("freq")), float(step.get("q_factor")), fs
                        )

                elif op_type == "artifact":
                    if time_vector is not None:
                        onset = float(step.get("onset_time", 0.0))
                        duration = float(step.get("duration_ms", 0.5))
                        method = step.get("method", "hold")
                        result = signal_processor.blank_artifact(result, time_vector, onset, duration, method=method)
                    else:
                        log.warning("Artifact blanking requested but no time " "vector provided. Skipping.")

                # Check for bad data after each step
                if result is not None:
                    if np.any(np.isnan(result)) or np.any(np.isinf(result)):
                        log.error(f"Step {op_type}/{step.get('method')} produced invalid data (NaN/Inf)")

            except Exception as e:
                log.error(f"Error processing step {step}: {e}")

        return result


# ---------------------------------------------------------------------------
# Immutable Trace Correction Pipeline
# ---------------------------------------------------------------------------


def _apply_pn_subtraction(result: np.ndarray, pn_traces, pn_scale: float) -> np.ndarray:
    """Step B: P/N leak subtraction helper."""
    pn_arr = np.asarray(pn_traces, dtype=float)
    if pn_arr.ndim == 1:
        pn_arr = pn_arr[np.newaxis, :]
    if pn_arr.shape[1] == result.shape[0]:
        pn_mean = pn_arr.mean(axis=0) * float(pn_scale)
        result = result - pn_mean
        log.debug(
            "apply_trace_corrections: Step B — P/N leak subtracted (%d sweeps, scale=%.3f).",
            pn_arr.shape[0],
            pn_scale,
        )
    else:
        log.warning(
            "apply_trace_corrections: Step B skipped — pn_traces length %d != data length %d.",
            pn_arr.shape[1],
            result.shape[0],
        )
    return result


def _apply_noise_floor_zeroing(result: np.ndarray, time: np.ndarray, pre_event_window_s: tuple) -> np.ndarray:
    """Step C: scalar pre-event noise-floor zeroing helper."""
    t0, t1 = float(pre_event_window_s[0]), float(pre_event_window_s[1])
    mask = (time >= t0) & (time < t1)
    if np.any(mask):
        floor_offset = float(np.median(result[mask]))
        result = result - floor_offset
        log.debug(
            "apply_trace_corrections: Step C — noise floor zeroed (%.4f mV, window %.3f-%.3f s).",
            floor_offset,
            t0,
            t1,
        )
    else:
        log.warning(
            "apply_trace_corrections: Step C skipped — no samples in window %.3f-%.3f s.",
            t0,
            t1,
        )
    return result


def apply_trace_corrections(
    data: np.ndarray,
    time: np.ndarray,
    fs: float,
    *,
    ljp_mv: float = 0.0,
    pn_traces: Optional[np.ndarray] = None,
    pn_scale: float = 1.0,
    pre_event_window_s: Optional[tuple] = None,
    artifact_interp_steps: Optional[List[Dict[str, Any]]] = None,
    filter_steps: Optional[List[Dict[str, Any]]] = None,
) -> np.ndarray:
    """Apply the immutable five-step trace correction in a guaranteed order.

    Regardless of the order the user toggles settings in the GUI, **this
    function must be used as the single entry point for all backend
    corrections** so that the execution order is always:

    Step A - LJP Voltage Offset
        ``V_true = V_recorded - ljp_mv``

    Step B - P/N Leak Subtraction
        If *pn_traces* is supplied, compute the per-sample mean across the
        sub-threshold repetitions, scale by *pn_scale*, and subtract from the
        corrected trace.  This removes capacitive transients and steady-state
        leak currents without affecting the signal of interest.

    Step C - Scalar Noise-Floor Zeroing
        Subtract the median of the user-specified pre-event window
        ``pre_event_window_s = (t_start, t_end)``.  Because the LJP and
        P/N corrections have already been applied, this median reflects only
        the residual noise floor, not a physiological offset.

    Step D - Pre-filter Artifact Interpolation
        Linearly interpolate across each stimulus artifact defined in
        *artifact_interp_steps*.  Running this **after** A-C and **before**
        filtering prevents Gibbs ringing: the DSP filter operates on an
        already-flat waveform without sharp transient edges.

    Step E - DSP Filtering
        Apply any filters listed in *filter_steps* (same dict schema as
        ``SignalProcessingPipeline``: ``{'type': 'filter', 'method': 'lowpass',
        'cutoff': 1000, 'order': 5}``).  Running filters **after** A-D
        prevents edge artefacts from the transient subtraction from being
        smeared across the waveform.

    Args:
        data:                Raw (uncorrected) signal array.
        time:                Time vector aligned with *data* (seconds).
        fs:                  Sampling rate in Hz.
        ljp_mv:              Liquid Junction Potential in mV.  Step A only
                             runs when ``ljp_mv != 0.0``.
        pn_traces:           2-D array of shape ``(n_sweeps, n_samples)``
                             containing the sub-threshold P/N sweeps.  Step B
                             is skipped when *pn_traces* is ``None``.
        pn_scale:            Scalar factor applied to the averaged P/N
                             template before subtraction (default 1.0).
        pre_event_window_s:  ``(t_start, t_end)`` tuple in seconds.  Step C
                             is skipped when this is ``None``.
        artifact_interp_steps: List of artifact dicts with keys
                             ``onset_time`` (s) and ``duration_ms`` (ms).
                             Each defines a stimulus artifact to linearly
                             interpolate.  Step D is skipped when ``None``.
        filter_steps:        List of filter dicts consumed by
                             ``SignalProcessingPipeline.process()``.  Step E
                             is skipped when the list is empty or ``None``.

    Returns:
        Corrected signal array (always a copy — the input is never mutated).
    """
    if data is None or data.size == 0:
        return data

    result: np.ndarray = data.copy()

    # ------------------------------------------------------------------
    # Step A — Liquid Junction Potential subtraction
    # ------------------------------------------------------------------
    if ljp_mv != 0.0:
        result = result - float(ljp_mv)
        log.debug("apply_trace_corrections: Step A — LJP %.4f mV subtracted.", ljp_mv)

    # ------------------------------------------------------------------
    # Step B — P/N Leak Subtraction
    # ------------------------------------------------------------------
    if pn_traces is not None:
        result = _apply_pn_subtraction(result, pn_traces, pn_scale)

    # ------------------------------------------------------------------
    # Step C — Pre-event Scalar Zeroing (median of pre-event window)
    # ------------------------------------------------------------------
    if pre_event_window_s is not None and time is not None and time.size == result.size:
        result = _apply_noise_floor_zeroing(result, time, pre_event_window_s)

    # ------------------------------------------------------------------
    # Step D — Pre-filter Artifact Interpolation
    # Linear interpolation across stimulus artifacts must occur AFTER
    # baseline zeroing (Step C) and BEFORE filtering (Step E).  This
    # ordering prevents Gibbs ringing: the filter operates on an already
    # flat waveform without the sharp transient edges of the artifact.
    # ------------------------------------------------------------------
    if artifact_interp_steps:
        for art in artifact_interp_steps:
            onset = float(art.get("onset_time", 0.0))
            duration_ms = float(art.get("duration_ms", 0.5))
            from Synaptipy.core import signal_processor as _sp

            result = _sp.blank_artifact(result, time, onset, duration_ms, method="linear")
        log.debug(
            "apply_trace_corrections: Step D — %d artifact interpolation step(s) applied.",
            len(artifact_interp_steps),
        )

    # ------------------------------------------------------------------
    # Step E — Signal Filtering
    # ------------------------------------------------------------------
    if filter_steps:
        pipeline = SignalProcessingPipeline()
        pipeline.set_steps(filter_steps)
        result = pipeline.process(result, fs, time_vector=time)
        log.debug("apply_trace_corrections: Step E — %d filter step(s) applied.", len(filter_steps))

    return result
