# src/Synaptipy/core/analysis/excitability.py
# -*- coding: utf-8 -*-
"""
Analysis functions for excitability properties (F-I Curve, Rheobase).
"""
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from scipy.stats import linregress
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold

log = logging.getLogger(__name__)

def calculate_fi_curve(
    sweeps: List[np.ndarray],
    time_vectors: List[np.ndarray],
    current_steps: Optional[List[float]] = None,
    threshold: float = -20.0,
    refractory_ms: float = 2.0
) -> Dict[str, Any]:
    """
    Calculates F-I Curve properties from a set of sweeps.

    Args:
        sweeps: List of voltage traces (1D arrays).
        time_vectors: List of corresponding time vectors.
        current_steps: List of current amplitudes for each sweep. If None, inferred.
        threshold: Spike detection threshold (mV).
        refractory_ms: Refractory period (ms).

    Returns:
        Dictionary with F-I curve properties:
        - rheobase_pa: Minimum current to elicit a spike.
        - fi_slope: Slope of the linear part of the F-I curve (Hz/pA).
        - max_freq: Maximum firing frequency observed.
        - spike_counts: List of spike counts per sweep.
        - frequencies: List of firing frequencies per sweep.
        - current_steps: List of current steps used.
    """
    num_sweeps = len(sweeps)
    if num_sweeps == 0:
        return {'error': "No sweeps provided"}

    # Infer current steps if not provided (simple heuristic: index as proxy or assume 10pA steps)
    # For now, if not provided, we'll return raw counts mapped to sweep index, but rheobase/slope will be limited.
    if current_steps is None:
        log.warning("Current steps not provided. Using sweep indices as proxy for current steps.")
        current_steps = list(range(num_sweeps))
        
    if len(current_steps) != num_sweeps:
        log.warning(f"Mismatch between sweeps ({num_sweeps}) and current_steps ({len(current_steps)}). Truncating to minimum.")
        min_len = min(num_sweeps, len(current_steps))
        sweeps = sweeps[:min_len]
        time_vectors = time_vectors[:min_len]
        current_steps = current_steps[:min_len]

    spike_counts = []
    frequencies = []
    
    # 1. Detect spikes in each sweep
    for i, (data, time) in enumerate(zip(sweeps, time_vectors)):
        sampling_rate = 1.0 / (time[1] - time[0]) if len(time) > 1 else 10000.0
        refractory_samples = int((refractory_ms / 1000.0) * sampling_rate)
        
        result = detect_spikes_threshold(data, time, threshold, refractory_samples)
        
        count = len(result.spike_indices) if result.spike_indices is not None else 0
        freq = result.mean_frequency if result.mean_frequency is not None else 0.0
        
        spike_counts.append(count)
        frequencies.append(freq)

    # 2. Calculate Rheobase
    rheobase_pa = None
    rheobase_idx = -1
    
    # Sort by current to ensure we find the *first* step
    sorted_indices = np.argsort(current_steps)
    sorted_currents = np.array(current_steps)[sorted_indices]
    sorted_counts = np.array(spike_counts)[sorted_indices]
    sorted_freqs = np.array(frequencies)[sorted_indices]
    
    for i, count in enumerate(sorted_counts):
        if count > 0:
            rheobase_pa = sorted_currents[i]
            rheobase_idx = i
            break
            
    # 3. Calculate Slope (Gain)
    # Use points from rheobase onwards
    fi_slope = None
    r_squared = None
    
    if rheobase_idx != -1 and rheobase_idx < len(sorted_counts) - 1:
        # Take points where freq > 0 (or from rheobase onwards)
        valid_indices = slice(rheobase_idx, None)
        x = sorted_currents[valid_indices]
        y = sorted_freqs[valid_indices]
        
        if len(x) >= 2:
            try:
                slope, intercept, r_value, p_value, std_err = linregress(x, y)
                fi_slope = slope
                r_squared = r_value**2
            except Exception as e:
                log.warning(f"Linear regression failed: {e}")

    return {
        'rheobase_pa': rheobase_pa,
        'fi_slope': fi_slope,
        'fi_r_squared': r_squared,
        'max_freq': np.max(frequencies) if frequencies else 0.0,
        'spike_counts': spike_counts,
        'frequencies': frequencies,
        'current_steps': current_steps
    }


@AnalysisRegistry.register(
    "excitability_analysis",
    ui_params=[
        {
            "name": "threshold",
            "label": "Threshold (mV):",
            "type": "float",
            "default": -20.0,
            "min": -100.0,
            "max": 100.0,
            "decimals": 1
        },
        {
            "name": "start_current",
            "label": "Start Current (pA):",
            "type": "float",
            "default": 0.0,
            "min": -1000.0,
            "max": 1000.0,
            "decimals": 1
        },
        {
            "name": "step_current",
            "label": "Step Current (pA):",
            "type": "float",
            "default": 10.0,
            "min": -100.0,
            "max": 100.0,
            "decimals": 1
        }
    ]
)
def run_excitability_analysis_wrapper(
    data_list: List[np.ndarray],
    time_list: List[np.ndarray],
    sampling_rate: float,
    **kwargs
) -> Dict[str, Any]:
    """
    Wrapper for Excitability Analysis (F-I Curve).
    
    Args:
        data_list: List of voltage traces (sweeps).
        time_list: List of time vectors.
        sampling_rate: Sampling rate (Hz).
        **kwargs:
            - threshold: Spike threshold (mV).
            - start_current: Starting current step (pA).
            - step_current: Delta current per step (pA).
            
    Returns:
        Dictionary of results.
    """
    try:
        threshold = kwargs.get('threshold', -20.0)
        start_current = kwargs.get('start_current', 0.0)
        step_current = kwargs.get('step_current', 10.0)
        
        # Infer current steps based on start/step and number of sweeps
        num_sweeps = len(data_list)
        current_steps = [start_current + i * step_current for i in range(num_sweeps)]
        
        results = calculate_fi_curve(
            sweeps=data_list,
            time_vectors=time_list,
            current_steps=current_steps,
            threshold=threshold
        )
        
        if 'error' in results:
            return {'excitability_error': results['error']}
            
        return {
            'rheobase_pa': results['rheobase_pa'],
            'fi_slope': results['fi_slope'],
            'fi_r_squared': results['fi_r_squared'],
            'max_freq_hz': results['max_freq'],
            # We can't easily return lists in a flat dict for CSV, so we summarize
            # or we could return a JSON string if needed, but for now keep it scalar
        }
        
    except Exception as e:
        log.error(f"Error in run_excitability_analysis_wrapper: {e}", exc_info=True)
        return {'excitability_error': str(e)}
