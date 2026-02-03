# src/Synaptipy/core/processing_pipeline.py
# -*- coding: utf-8 -*-
"""
Signal Processing Pipeline.

Formalizes the order of operations for signal processing (e.g., Baseline -> Filter).
Ensures that both visualization and analysis use the exact same processing sequence.
"""
import logging
from typing import List, Dict, Any, Optional
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
        self._steps = [s for s in self._steps if s.get('type') != step_type]
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

    def process(self, data: np.ndarray, fs: float, time_vector: Optional[np.ndarray] = None) -> np.ndarray:
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
                op_type = step.get('type')

                if op_type == 'baseline':
                    method = step.get('method', 'mode')
                    if method == 'mode':
                        decimals = step.get('decimals', 1)
                        result = signal_processor.subtract_baseline_mode(result, decimals=decimals)
                    elif method == 'mean':
                        result = signal_processor.subtract_baseline_mean(result)
                    elif method == 'median':
                        result = signal_processor.subtract_baseline_median(result)
                    elif method == 'linear':
                        result = signal_processor.subtract_baseline_linear(result)
                    elif method == 'region':
                        if time_vector is not None:
                            start_t = step.get('start_t', 0.0)
                            end_t = step.get('end_t', 0.0)
                            result = signal_processor.subtract_baseline_region(result, time_vector, start_t, end_t)
                        else:
                            log.warning("Region baseline requested but no time vector provided. Skipping.")

                elif op_type == 'filter':
                    method = step.get('method')
                    # Filters usually need 'order' which defaults to 5 in signal_processor if not passed
                    order = int(step.get('order', 5))
                    
                    if method == 'lowpass':
                        result = signal_processor.lowpass_filter(
                            result, step.get('cutoff'), fs, order=order
                        )
                    elif method == 'highpass':
                        result = signal_processor.highpass_filter(
                            result, step.get('cutoff'), fs, order=order
                        )
                    elif method == 'bandpass':
                        result = signal_processor.bandpass_filter(
                            result, step.get('low_cut'), step.get('high_cut'), fs, order=order
                        )
                    elif method == 'notch':
                        # Notch filter signature: (data, freq, Q, fs)
                        result = signal_processor.notch_filter(
                            result, step.get('freq'), step.get('q_factor'), fs
                        )

            except Exception as e:
                log.error(f"Error processing step {step}: {e}")
                # Continue or raise? For UI robustness, maybe log and continue, 
                # but for data correctness, maybe we should know.
                # Let's log error but keep the data as is from previous step (safe failure).

        return result
