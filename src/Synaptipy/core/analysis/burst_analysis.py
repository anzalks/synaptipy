# src/Synaptipy/core/analysis/burst_analysis.py
# -*- coding: utf-8 -*-
"""
Analysis functions for detecting and characterizing bursts of action potentials.
"""
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold

log = logging.getLogger(__name__)

def detect_bursts(
    spike_times: np.ndarray,
    max_isi_start: float = 0.01,
    max_isi_end: float = 0.2,
    min_spikes: int = 2
) -> Dict[str, Any]:
    """
    Detects bursts in a spike train.
    
    A burst is defined as a sequence of spikes where:
    1. The ISI between the first two spikes is <= max_isi_start.
    2. The burst continues as long as ISIs are <= max_isi_end.
    
    Args:
        spike_times: 1D array of spike times (seconds).
        max_isi_start: Max ISI to start a burst (seconds).
        max_isi_end: Max ISI to continue a burst (seconds).
        min_spikes: Minimum number of spikes to constitute a burst.
        
    Returns:
        Dictionary with burst statistics:
        - burst_count: Total number of bursts.
        - spikes_per_burst_avg: Average number of spikes in a burst.
        - burst_duration_avg: Average duration of bursts.
        - burst_freq_hz: Frequency of bursts (bursts per second).
    """
    if len(spike_times) < min_spikes:
        return {
            'burst_count': 0,
            'spikes_per_burst_avg': 0.0,
            'burst_duration_avg': 0.0,
            'burst_freq_hz': 0.0
        }
        
    isis = np.diff(spike_times)
    bursts = []
    current_burst = []
    
    in_burst = False
    
    for i, isi in enumerate(isis):
        if not in_burst:
            if isi <= max_isi_start:
                in_burst = True
                current_burst = [spike_times[i], spike_times[i+1]]
        else:
            if isi <= max_isi_end:
                current_burst.append(spike_times[i+1])
            else:
                in_burst = False
                if len(current_burst) >= min_spikes:
                    bursts.append(current_burst)
                current_burst = []
                
    # Check if last burst was valid
    if in_burst and len(current_burst) >= min_spikes:
        bursts.append(current_burst)
        
    # Calculate stats
    num_bursts = len(bursts)
    if num_bursts == 0:
        return {
            'burst_count': 0,
            'spikes_per_burst_avg': 0.0,
            'burst_duration_avg': 0.0,
            'burst_freq_hz': 0.0
        }
        
    spikes_per_burst = [len(b) for b in bursts]
    burst_durations = [b[-1] - b[0] for b in bursts]
    
    duration = spike_times[-1] - spike_times[0] if len(spike_times) > 0 else 0
    burst_freq = num_bursts / duration if duration > 0 else 0.0
    
    return {
        'burst_count': num_bursts,
        'spikes_per_burst_avg': np.mean(spikes_per_burst),
        'burst_duration_avg': np.mean(burst_durations),
        'burst_freq_hz': burst_freq,
        'bursts': bursts # List of lists of spike times in each burst
    }


@AnalysisRegistry.register(
    "burst_analysis",
    ui_params=[
        {
            "name": "threshold",
            "label": "Threshold (mV):",
            "type": "float",
            "default": -20.0,
            "min": -1e9,
            "max": 1e9,
            "decimals": 4
        },
        {
            "name": "max_isi_start",
            "label": "Max ISI Start (s):",
            "type": "float",
            "default": 0.01,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4
        },
        {
            "name": "max_isi_end",
            "label": "Max ISI End (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4
        }
    ]
)
def run_burst_analysis_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs
) -> Dict[str, Any]:
    """
    Wrapper for Burst Analysis.
    
    Args:
        data: Voltage trace.
        time: Time vector.
        sampling_rate: Sampling rate.
        **kwargs:
            - threshold: Spike detection threshold.
            - max_isi_start: Max ISI to start burst.
            - max_isi_end: Max ISI to end burst.
            
    Returns:
        Dictionary of burst stats.
    """
    try:
        threshold = kwargs.get('threshold', -20.0)
        max_isi_start = kwargs.get('max_isi_start', 0.01)
        max_isi_end = kwargs.get('max_isi_end', 0.1)
        
        # 1. Detect spikes first
        refractory_ms = 2.0 
        refractory_samples = int((refractory_ms / 1000.0) * sampling_rate)
        
        spike_result = detect_spikes_threshold(data, time, threshold, refractory_samples)
        
        if not spike_result.is_valid or spike_result.spike_times is None:
             return {
                'burst_count': 0,
                'burst_error': spike_result.error_message or "Spike detection failed"
            }
            
        # 2. Detect bursts
        # Note: detect_bursts returns stats, but we need the actual bursts list.
        # We need to modify detect_bursts or just call the logic here?
        # detect_bursts returns a dict. It calculates 'bursts' internally but doesn't return them.
        # Let's modify detect_bursts to return the raw bursts too? 
        # Or just re-implement the call here since we can't easily change the inner function signature without breaking others?
        # Actually, let's modify detect_bursts to return 'bursts' list in the dict.
        
        burst_stats = detect_bursts(
            spike_result.spike_times,
            max_isi_start=max_isi_start,
            max_isi_end=max_isi_end
        )
        
        # Wait, I need to modify detect_bursts to return the list.
        # Let's assume I will modify detect_bursts in the same file.
        
        return burst_stats
        
    except Exception as e:
        log.error(f"Error in run_burst_analysis_wrapper: {e}", exc_info=True)
        return {'burst_error': str(e)}
