# src/Synaptipy/core/analysis/spike_analysis.py
# -*- coding: utf-8 -*-
"""
Analysis functions related to action potential detection and characterization.
"""
import logging
from typing import Tuple, List, Dict, Any
import numpy as np
from scipy import signal
from Synaptipy.core.results import SpikeTrainResult
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)

def detect_spikes_threshold(data: np.ndarray, time: np.ndarray, threshold: float, refractory_samples: int, peak_search_window_samples: int = None) -> SpikeTrainResult:
    """
    Detects spikes based on a simple voltage threshold crossing with refractory period.

    Args:
        data: 1D NumPy array of voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        threshold: Voltage threshold for detection.
        refractory_samples: Minimum number of samples between detected spikes (applied based on threshold crossings).
        peak_search_window_samples: Optional. Number of samples to search for peak after crossing. 
                                    Defaults to refractory_samples (or 5ms if refractory is 0).

    Returns:
        SpikeTrainResult object containing spike times and indices.
    """
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size < 2:
        log.warning("detect_spikes_threshold: Invalid data array provided.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message="Invalid data array")
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        log.warning("detect_spikes_threshold: Time and data array shapes mismatch.")
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message="Time and data mismatch")
    if not isinstance(threshold, (int, float)):
         log.warning("detect_spikes_threshold: Threshold must be numeric.")
         return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message="Threshold must be numeric")
    if not isinstance(refractory_samples, int) or refractory_samples < 0:
         log.warning("detect_spikes_threshold: refractory_samples must be a non-negative integer.")
         return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message="Invalid refractory period")

    try:
        # 1. Find indices where the data crosses the threshold upwards
        crossings = np.where((data[:-1] < threshold) & (data[1:] >= threshold))[0] + 1
        if crossings.size == 0:
            log.debug("No threshold crossings found.")
            return SpikeTrainResult(value=0, unit="spikes", spike_times=np.array([]), spike_indices=np.array([]))

        # 2. Apply refractory period based on crossings
        if refractory_samples <= 0:
             valid_crossing_indices = crossings
        else:
            valid_crossings_list = [crossings[0]] # Always accept the first crossing
            last_crossing_idx = crossings[0]
            for idx in crossings[1:]:
                if (idx - last_crossing_idx) >= refractory_samples:
                    valid_crossings_list.append(idx)
                    last_crossing_idx = idx
            valid_crossing_indices = np.array(valid_crossings_list)

        if valid_crossing_indices.size == 0: 
             return SpikeTrainResult(value=0, unit="spikes", spike_times=np.array([]), spike_indices=np.array([]))
             
        # 3. Find peak index after each valid crossing
        peak_indices_list = []
        # Define search window for peak
        if peak_search_window_samples is None:
             peak_search_window_samples = refractory_samples if refractory_samples > 0 else int(0.005 / (time[1]-time[0])) # Default to 5ms if no refractory
        
        for crossing_idx in valid_crossing_indices:
            search_start = crossing_idx
            search_end = min(crossing_idx + peak_search_window_samples, len(data))
            if search_start >= search_end: # Should not happen, but safety
                peak_idx = crossing_idx # Fallback to crossing index
            else:
                try:
                    # Find index of max value within the window relative to window start
                    relative_peak_idx = np.argmax(data[search_start:search_end])
                    # Convert to index relative to the whole data array
                    peak_idx = search_start + relative_peak_idx
                except ValueError: # Handle potential errors if slice is unexpectedly empty
                    log.warning(f"ValueError finding peak after crossing index {crossing_idx}. Using crossing index.")
                    peak_idx = crossing_idx 
                    
            peak_indices_list.append(peak_idx)
            
        peak_indices_arr = np.array(peak_indices_list).astype(int) # Ensure integer indices

        # 4. Get corresponding times for the peaks
        peak_times_arr = time[peak_indices_arr]
        log.debug(f"Detected {len(peak_indices_arr)} spike peaks.")
        
        mean_freq = 0.0
        if len(peak_times_arr) > 1:
             duration = time[-1] - time[0]
             if duration > 0:
                mean_freq = len(peak_times_arr) / duration

        return SpikeTrainResult(
            value=len(peak_indices_arr),
            unit="spikes",
            spike_times=peak_times_arr,
            spike_indices=peak_indices_arr,
            mean_frequency=mean_freq
        )

    except IndexError as e:
         # This might happen if indexing goes wrong, e.g., with peak_indices_arr
         log.error(f"IndexError during spike detection: {e}. Indices={peak_indices_arr if 'peak_indices_arr' in locals() else 'N/A'}", exc_info=True)
         return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message=str(e))
    except Exception as e:
        log.error(f"Error during spike detection: {e}", exc_info=True)
        return SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message=str(e))


# --- Add other spike analysis functions here later ---
def calculate_spike_features(
    data: np.ndarray, 
    time: np.ndarray, 
    spike_indices: np.ndarray, 
    dvdt_threshold: float = 20.0,
    ahp_window_sec: float = 0.05,
    onset_lookback: float = 0.01
) -> List[Dict[str, Any]]:
    """
    Calculates detailed features for each spike.
    Returns:
        A list of dictionaries, where each dictionary contains features
        for a single spike (e.g., amplitude, half_width, ahp_depth, dvdt_max).
    """
    if spike_indices.size == 0:
        return []

    dt = time[1] - time[0]
    dvdt = np.gradient(data, dt)
    features_list = []

    for peak_idx in spike_indices:
        # 1. Find Action Potential Threshold (20 V/s is a common value)
        search_end = peak_idx
        search_start = max(0, peak_idx - int(onset_lookback / dt))  # Look back window
        try:
            dvdt_slice = dvdt[search_start:search_end]
            data_slice = data[search_start:search_end]
            # Convert dvdt_threshold to V/s if it's not already (it is treated as V/s)
            # data is in mV, time in s, so dvdt is mV/s. 
            # 20 V/s = 20000 mV/s.
            threshold_val_mvs = dvdt_threshold * 1000.0
            
            threshold_crossings = np.where(dvdt_slice > threshold_val_mvs)[0]
            if threshold_crossings.size > 0:
                thresh_idx = search_start + threshold_crossings[0]
                ap_threshold = data[thresh_idx]
            else:
                thresh_idx = search_start # Fallback
                ap_threshold = data[thresh_idx]
        except:
            thresh_idx = peak_idx - 2 # fallback
            ap_threshold = data[thresh_idx]


        # 2. Spike Amplitude (from threshold to peak)
        peak_val = data[peak_idx]
        amplitude = peak_val - ap_threshold

        # 3. Spike Width at half-maximal amplitude
        half_amp = ap_threshold + amplitude / 2
        
        # Find rising and falling half-amp crossings
        pre_peak_slice = data[thresh_idx:peak_idx+1]
        post_peak_slice = data[peak_idx:peak_idx + int(0.01/dt)] # 10ms after peak

        try:
            rising_half_idx = thresh_idx + np.where(pre_peak_slice > half_amp)[0][0]
            falling_half_idx = peak_idx + np.where(post_peak_slice < half_amp)[0][0]
            half_width = (falling_half_idx - rising_half_idx) * dt * 1000  # in ms
        except IndexError:
            half_width = np.nan
            rising_half_idx = np.nan
            falling_half_idx = np.nan

        # --- NEW: Rise Time (10-90%) ---
        try:
            amp_10 = ap_threshold + 0.1 * amplitude
            amp_90 = ap_threshold + 0.9 * amplitude
            
            # Search in pre-peak slice
            rising_10_idx = thresh_idx + np.where(pre_peak_slice >= amp_10)[0][0]
            rising_90_idx = thresh_idx + np.where(pre_peak_slice >= amp_90)[0][0]
            
            rise_time_10_90 = (rising_90_idx - rising_10_idx) * dt * 1000 # ms
        except IndexError:
            rise_time_10_90 = np.nan

        # --- NEW: Decay Time (90-10%) ---
        try:
            # Search in post-peak slice
            # Note: post_peak_slice starts at peak_idx
            falling_90_idx_rel = np.where(post_peak_slice <= amp_90)[0]
            falling_10_idx_rel = np.where(post_peak_slice <= amp_10)[0]
            
            if falling_90_idx_rel.size > 0 and falling_10_idx_rel.size > 0:
                falling_90_idx = peak_idx + falling_90_idx_rel[0]
                falling_10_idx = peak_idx + falling_10_idx_rel[0]
                decay_time_90_10 = (falling_10_idx - falling_90_idx) * dt * 1000 # ms
            else:
                decay_time_90_10 = np.nan
        except IndexError:
            decay_time_90_10 = np.nan

        # 4. Afterhyperpolarization (AHP) depth & Duration
        ahp_search_end = min(len(data), peak_idx + int(ahp_window_sec / dt))
        ahp_slice = data[peak_idx:ahp_search_end]
        try:
            ahp_min_idx_rel = np.argmin(ahp_slice)
            ahp_min_val = ahp_slice[ahp_min_idx_rel]
            ahp_min_idx = peak_idx + ahp_min_idx_rel
            
            # AHP is relative to threshold (or RMP, but usually threshold in this context)
            ahp_depth = ap_threshold - ahp_min_val
            
            # AHP Duration at 50%
            if ahp_depth > 0:
                ahp_half_val = ahp_min_val + ahp_depth / 2
                # Search from falling_10_idx (end of AP) to ahp_min_idx for start of AHP half
                # And from ahp_min_idx onwards for end of AHP half
                
                # We need a robust start point. Let's use the point where it crosses threshold downwards
                threshold_cross_down_rel = np.where(post_peak_slice < ap_threshold)[0]
                if threshold_cross_down_rel.size > 0:
                    ap_end_idx = peak_idx + threshold_cross_down_rel[0]
                else:
                    ap_end_idx = peak_idx # fallback
                
                # Slice for AHP
                ahp_full_slice = data[ap_end_idx:ahp_search_end]
                
                # Find where it goes below half_val (start) and comes back up (end)
                # This is tricky because it might not come back up fully.
                # Simplified: width at half depth
                
                # Find crossings of ahp_half_val
                # We expect data to go down through half_val, hit min, go up through half_val
                below_half_indices = np.where(ahp_full_slice < ahp_half_val)[0]
                if below_half_indices.size > 1:
                    ahp_start_idx = ap_end_idx + below_half_indices[0]
                    ahp_end_idx = ap_end_idx + below_half_indices[-1]
                    ahp_duration_half = (ahp_end_idx - ahp_start_idx) * dt * 1000 # ms
                else:
                    ahp_duration_half = np.nan
            else:
                ahp_duration_half = np.nan
                
        except ValueError:
            ahp_depth = np.nan
            ahp_duration_half = np.nan

        # --- NEW: ADP (After-Depolarization) Detection ---
        # Look for a local maximum between AP end and AHP min
        # Or if AHP is delayed, a hump before it.
        # Simple definition: Local max after fast repolarization but before returning to baseline/AHP
        adp_amplitude = np.nan
        try:
            # Define a window for ADP: from decay_90 (approx) to some time later
            # Let's look in the first 10ms after the AP falls below threshold
            if 'ap_end_idx' in locals():
                adp_search_window = data[ap_end_idx:min(len(data), ap_end_idx + int(0.02/dt))]
                
                # We expect a hump. So derivative goes + then -
                # Or simply max value in this window is significantly higher than end of AP?
                # ADP is usually small.
                # Let's check if there is a peak in this window that is above the AHP start
                
                if adp_search_window.size > 5:
                    # Find peaks
                    adp_peaks, _ = signal.find_peaks(adp_search_window, prominence=0.5) # 0.5mV prominence
                    if adp_peaks.size > 0:
                        adp_val = adp_search_window[adp_peaks[0]]
                        adp_amplitude = adp_val - ap_threshold # Relative to threshold
                        # If ADP is below threshold (likely), this will be negative, which is fine.
                        # Usually ADP is defined relative to AHP min or Threshold.
                        # Let's define it as amplitude above the "expected" repolarization curve?
                        # For simplicity: Max voltage in the ADP window minus the voltage at AP end
                        adp_amplitude = adp_val - data[ap_end_idx]
        except Exception:
            pass


        # 5. Maximum rise and fall slopes (max/min dV/dt)
        dvdt_search_end = min(len(dvdt), peak_idx + int(0.005 / dt)) # 5ms after peak
        dvdt_search_slice = dvdt[thresh_idx:dvdt_search_end]

        try:
            max_dvdt = np.max(dvdt_search_slice)
            min_dvdt = np.min(dvdt_search_slice)
        except ValueError:
            max_dvdt, min_dvdt = np.nan, np.nan
            
        features_list.append({
            'ap_threshold': ap_threshold,
            'amplitude': amplitude,
            'half_width': half_width,
            'rise_time_10_90': rise_time_10_90,
            'decay_time_90_10': decay_time_90_10,
            'ahp_depth': ahp_depth,
            'ahp_duration_half': ahp_duration_half,
            'adp_amplitude': adp_amplitude,
            'max_dvdt': max_dvdt,
            'min_dvdt': min_dvdt
        })

    return features_list


def calculate_isi(spike_times):
    """Calculates inter-spike intervals from a list of spike times."""
    if len(spike_times) < 2:
        return np.array([])
    return np.diff(spike_times)

def analyze_multi_sweep_spikes(
    data_trials: List[np.ndarray],
    time_vector: np.ndarray,
    threshold: float,
    refractory_samples: int
) -> List[SpikeTrainResult]:
    """
    Analyzes spikes across multiple sweeps (trials).

    Args:
        data_trials: List of 1D NumPy arrays, each representing a sweep.
        time_vector: 1D NumPy array of time points (assumed same for all sweeps).
        threshold: Voltage threshold.
        refractory_samples: Refractory period in samples.

    Returns:
        List of SpikeTrainResult objects, one for each sweep.
    """
    results = []
    for i, trial_data in enumerate(data_trials):
        try:
            result = detect_spikes_threshold(trial_data, time_vector, threshold, refractory_samples)
            # Add trial index to metadata
            result.metadata['sweep_index'] = i
            results.append(result)
        except Exception as e:
            log.error(f"Error analyzing sweep {i}: {e}")
            # Return an error result for this sweep
            error_result = SpikeTrainResult(value=0, unit="spikes", is_valid=False, error_message=f"Sweep {i}: {str(e)}")
            error_result.metadata['sweep_index'] = i
            results.append(error_result)
            
    return results


# --- Registry Wrapper for Batch Processing ---
@AnalysisRegistry.register(
    "spike_detection",
    label="Spike Detection",
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
            "name": "refractory_period",
            "label": "Refractory (s):",
            "type": "float",
            "default": 0.002,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4
        },
        {
            "name": "peak_search_window",
            "label": "Peak Search (s):",
            "type": "float",
            "default": 0.005,
            "min": 0.0,
            "max": 1.0,
            "decimals": 4
        },
        {
            "name": "dvdt_threshold",
            "label": "dV/dt Thresh (V/s):",
            "type": "float",
            "default": 20.0,
            "min": 0.0,
            "max": 1e6,
            "decimals": 1
        },
        {
            "name": "ahp_window",
            "label": "AHP Window (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "default": 0.05,
            "min": 0.0,
            "max": 10.0,
            "decimals": 3
        },
        {
            "name": "onset_lookback",
            "label": "Onset Lookback (s):",
            "type": "float",
            "default": 0.01,
            "min": 0.0,
            "max": 0.1,
            "decimals": 3
        }
    ]
)
def run_spike_detection_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    threshold: float = -20.0,
    refractory_period: float = 0.002,
    peak_search_window: float = 0.005,
    dvdt_threshold: float = 20.0,
    ahp_window: float = 0.05,
    onset_lookback: float = 0.01,
    **kwargs
) -> Dict[str, Any]:
    """
    Wrapper function for spike detection that conforms to the registry interface.
    
    Args:
        data: 1D NumPy array of voltage data
        time: 1D NumPy array of corresponding time points (seconds)
        sampling_rate: Sampling rate in Hz
        threshold: Detection threshold in mV
        refractory_period: Refractory period in seconds
            
    Returns:
        Dictionary containing results.
    """
    try:
        refractory_samples = int(refractory_period * sampling_rate)
        peak_window_samples = int(peak_search_window * sampling_rate)
        
        # Run detection
        result = detect_spikes_threshold(data, time, threshold, refractory_samples, peak_search_window_samples=peak_window_samples)
        
        if result.is_valid:
            # Calculate spike features
            features_list = calculate_spike_features(
                data, 
                time, 
                result.spike_indices,
                dvdt_threshold=dvdt_threshold,
                ahp_window_sec=ahp_window,
                onset_lookback=onset_lookback
            )
            
            # Aggregate features (Mean and Std Dev)
            stats = {}
            if features_list:
                # Convert list of dicts to dict of lists for easier aggregation
                feature_keys = features_list[0].keys()
                for key in feature_keys:
                    values = [f[key] for f in features_list if not np.isnan(f[key])]
                    if values:
                        stats[f'{key}_mean'] = np.mean(values)
                        stats[f'{key}_std'] = np.std(values)
                    else:
                        stats[f'{key}_mean'] = np.nan
                        stats[f'{key}_std'] = np.nan
            
            output = {
                'spike_count': len(result.spike_indices) if result.spike_indices is not None else 0,
                'mean_freq_hz': result.mean_frequency if result.mean_frequency is not None else 0.0,
                'spike_times': result.spike_times,
                'spike_indices': result.spike_indices
            }
            output.update(stats)
            return output
        else:
            return {
                'spike_count': 0,
                'mean_freq_hz': 0.0,
                'spike_error': result.error_message or "Unknown error"
            }
            
    except Exception as e:
        log.error(f"Error in run_spike_detection_wrapper: {e}", exc_info=True)
        return {
            'spike_count': 0,
            'mean_freq_hz': 0.0,
            'spike_error': str(e)
        }