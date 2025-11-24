# src/Synaptipy/core/analysis/event_detection.py
# -*- coding: utf-8 -*-
"""
Analysis functions for detecting synaptic events (miniature, evoked).
"""
import logging
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
from scipy import signal
from scipy.stats import median_abs_deviation

log = logging.getLogger('Synaptipy.core.analysis.event_detection')
from Synaptipy.core.analysis.registry import AnalysisRegistry


# --- Registry Wrapper for Batch Processing (Mini Detection) ---
@AnalysisRegistry.register("mini_detection")
def run_mini_detection_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs
) -> Dict[str, Any]:
    """
    Wrapper function for miniature event detection that conforms to the registry interface.
    
    Args:
        data: 1D NumPy array of current/voltage data
        time: 1D NumPy array of corresponding time points (seconds)
        sampling_rate: Sampling rate in Hz
        **kwargs: Additional parameters:
            - threshold: Absolute amplitude threshold (default: 5.0)
            - direction: 'negative' or 'positive' (default: 'negative')
            
    Returns:
        Dictionary containing results suitable for DataFrame rows.
    """
    try:
        threshold = kwargs.get('threshold', 5.0)
        direction = kwargs.get('direction', 'negative')
        
        result = detect_minis_threshold(data, time, threshold, direction)
        
        if result is not None:
            return {
                'event_count': result.get('event_count', 0),
                'frequency_hz': result.get('frequency_hz', 0.0),
                'mean_amplitude': result.get('mean_amplitude', 0.0),
                'amplitude_sd': result.get('amplitude_sd', 0.0),
                'detection_method': result.get('detection_method', 'threshold'),
                'threshold_value': result.get('threshold_value', threshold),
                'direction': result.get('direction', direction),
            }
        else:
            return {
                'event_count': 0,
                'frequency_hz': 0.0,
                'event_error': "Detection failed"
            }
            
    except Exception as e:
        log.error(f"Error in run_mini_detection_wrapper: {e}", exc_info=True)
        return {
            'event_count': 0,
            'frequency_hz': 0.0,
            'event_error': str(e)
        }

def detect_minis_threshold(
    data: np.ndarray, 
    time: np.ndarray, 
    threshold: float, 
    direction: str = 'negative',
    # Add other relevant params later: refractory, min_duration, etc.
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    Detects miniature events based on a simple amplitude threshold.
    
    Args:
        data: 1D NumPy array of current or voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        threshold: Absolute amplitude threshold for detection (must be positive).
        direction: 'negative' or 'positive' indicates event polarity.
        **kwargs: Placeholder for future parameters.
        
    Returns:
        A dictionary containing detection results (e.g., 'event_indices', 
        'event_times', 'event_amplitudes', 'frequency_hz', 'mean_amplitude') 
        or None if detection fails.
    """
    log.warning("detect_minis_threshold function is a placeholder - using basic logic.")
    # Basic validation
    if not isinstance(data, np.ndarray) or data.ndim != 1 or data.size < 2:
        log.error("Invalid data array provided.")
        return None
    if not isinstance(time, np.ndarray) or time.shape != data.shape:
        log.error("Time and data array shapes mismatch.")
        return None
    if not isinstance(threshold, (int, float)) or threshold <= 0:
        log.error("Threshold must be a positive number.")
        return None
    if direction not in ['negative', 'positive']:
        log.error("Direction must be 'negative' or 'positive'.")
        return None
        
    try:
        is_negative_going = (direction == 'negative')
        
        # --- REPLACE WITH REFINED THRESHOLD LOGIC --- 
        # (Current placeholder logic copied from GUI tab)
        if is_negative_going:
            crossings = np.where(data < -threshold)[0]
        else:
            crossings = np.where(data > threshold)[0]

        event_indices = np.array([])
        event_times = np.array([])
        event_amplitudes = np.array([])

        if len(crossings) > 0:
            diffs = np.diff(crossings)
            event_start_indices = crossings[np.concatenate(([True], diffs > 1))]
            event_indices = event_start_indices # Simple peak finding needed here
            event_times = time[event_indices]
            event_amplitudes = data[event_indices] # Placeholder - should be peak amp relative to baseline
        # --- END PLACEHOLDER --- 

        num_events = len(event_indices)
        duration = time[-1] - time[0]
        frequency = num_events / duration if duration > 0 else 0
        mean_amplitude = np.mean(event_amplitudes) if num_events > 0 else 0.0
        std_amplitude = np.std(event_amplitudes) if num_events > 0 else 0.0

        results = {
            'event_indices': event_indices,
            'event_times': event_times,
            'event_amplitudes': event_amplitudes,
            'event_count': num_events,
            'frequency_hz': frequency,
            'mean_amplitude': mean_amplitude,
            'amplitude_sd': std_amplitude,
            'detection_method': 'threshold',
            'threshold_value': threshold,
            'direction': direction
        }
        log.info(f"Threshold detection found {num_events} events.")
        return results

    except Exception as e:
        log.error(f"Error during threshold event detection: {e}", exc_info=True)
        return None


def detect_minis_automatic_mad(
    data: np.ndarray, 
    time: np.ndarray, 
    direction: str = 'negative',
    k: float = 5.0,
    baseline_window: Optional[Tuple[float, float]] = None,
    # Add other relevant params later: refractory, min_duration, etc.
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    Detects miniature events using a threshold based on Median Absolute Deviation (MAD).
    Threshold = median ± k * MAD
    
    Args:
        data: 1D NumPy array of current or voltage data.
        time: 1D NumPy array of corresponding time points (seconds).
        direction: 'negative' or 'positive' indicates event polarity.
        k: Multiplier for MAD to set the threshold (default: 5.0).
        baseline_window: Optional tuple (start_time, end_time) to calculate noise statistics.
                         If None, uses the entire trace (less ideal).
        **kwargs: Placeholder for future parameters.
        
    Returns:
        A dictionary containing detection results (e.g., 'event_indices', 
        'event_times', 'event_amplitudes', 'frequency_hz', 'mean_amplitude', 'calculated_threshold') 
        or None if detection fails.
    """
    log.warning("detect_minis_automatic_mad function is not yet implemented.")
    # --- IMPLEMENTATION NEEDED ---
    # 1. Validate inputs (data, time, direction, k)
    # 2. Determine baseline data (use window or whole trace)
    # 3. Calculate median and MAD of baseline
    # 4. Calculate threshold = k * MAD
    # 5. Apply detection logic (similar to threshold method, but use median +/- threshold)
    #    - Might need refinement (peak finding, refractory period etc.)
    # 6. Package results in a dictionary, including calculated_threshold
    # --- END IMPLEMENTATION NEEDED ---
    return None 

# --- Registry Wrapper for Batch Processing (Threshold Method) ---
@AnalysisRegistry.register("event_detection_threshold")
def detect_events_threshold_crossing(data: np.ndarray, threshold: float, direction: str) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Detects events by simple threshold crossing.

    Args:
        data: 1D numpy array of the signal.
        threshold: The threshold value.
        direction: 'positive' or 'negative' crossing.

    Returns:
        A tuple containing:
            - indices: Numpy array of event start indices.
            - stats: Dictionary with basic statistics ('count', 'mean_val', 'std_val').
    """
    if direction == 'negative':
        crossings = np.where(data < threshold)[0]
    elif direction == 'positive':
        crossings = np.where(data > threshold)[0]
    else:
        raise ValueError("Direction must be 'positive' or 'negative'")

    if len(crossings) == 0:
        return np.array([]), {'count': 0}

    # Find the start of each continuous block of threshold crossings
    diffs = np.diff(crossings)
    event_starts = np.concatenate(([crossings[0]], crossings[np.where(diffs > 1)[0] + 1]))

    count = len(event_starts)
    if count > 0:
        mean_val = np.mean(data[event_starts])
        std_val = np.std(data[event_starts])
    else:
        mean_val = np.nan
        std_val = np.nan

    stats = {
        'count': count,
        'mean_val': mean_val,
        'std_val': std_val
    }

    return event_starts, stats


def _mad_to_std(mad_value: float) -> float:
    """Converts Median Absolute Deviation (MAD) to Standard Deviation (SD).
    Assumes underlying normal distribution.
    Conversion factor is approximately 1.4826.
    """
    return mad_value * 1.4826


@AnalysisRegistry.register("event_detection_deconvolution")
def detect_events_deconvolution_custom(
    data: np.ndarray,
    sample_rate: float,
    tau_rise_ms: float,
    tau_decay_ms: float,
    threshold_sd: float,
    filter_freq_hz: Optional[float] = None,
    min_event_separation_ms: float = 2.0,
    regularization_factor: float = 0.01 # Small factor relative to peak kernel power
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Detects events using a custom FFT-based deconvolution approach.

    Args:
        data: 1D numpy array of the signal.
        sample_rate: Sampling rate in Hz.
        tau_rise_ms: Rise time constant in milliseconds.
        tau_decay_ms: Decay time constant in milliseconds.
        threshold_sd: Detection threshold in multiples of the estimated noise SD
                      of the deconvolved trace.
        filter_freq_hz: Optional cutoff frequency for a low-pass Butterworth
                        filter applied before deconvolution (Hz). If None, no filter.
        min_event_separation_ms: Minimum time between detected event peaks (ms).
        regularization_factor: Factor to stabilize deconvolution (relative to peak power).

    Returns:
        A tuple containing:
            - indices: Numpy array of detected event peak indices.
            - stats: Dictionary with basic statistics ('count').
    """
    if tau_decay_ms <= tau_rise_ms:
        raise ValueError("tau_decay_ms must be greater than tau_rise_ms")

    n_points = len(data)
    dt = 1.0 / sample_rate

    # --- 1. Optional Pre-filtering ---
    if filter_freq_hz is not None and filter_freq_hz > 0:
        if filter_freq_hz >= sample_rate / 2:
             log.warning(f"Filter frequency ({filter_freq_hz} Hz) is >= Nyquist frequency ({sample_rate / 2} Hz). Skipping filter.")
             filtered_data = data.copy()
        else:
            try:
                sos = signal.butter(4, filter_freq_hz, btype='low', analog=False, output='sos', fs=sample_rate)
                filtered_data = signal.sosfiltfilt(sos, data)
                log.debug(f"Applied low-pass filter at {filter_freq_hz} Hz.")
            except Exception as e:
                log.error(f"Error applying filter: {e}. Using original data.")
                filtered_data = data.copy()
    else:
        filtered_data = data.copy()

    # --- 2. Generate Kernel ---
    tau_rise_samples = tau_rise_ms / 1000.0 / dt
    tau_decay_samples = tau_decay_ms / 1000.0 / dt
    kernel_len = int(10 * tau_decay_samples) # Make kernel sufficiently long
    if kernel_len < 10: # Ensure minimum length
        kernel_len = 10
    if kernel_len > n_points // 2: # Prevent overly long kernel for short data
        kernel_len = n_points // 2
        log.warning(f"Kernel length limited to {kernel_len} points due to data length.")
        
    t_kernel = np.arange(kernel_len) * dt
    kernel = (np.exp(-t_kernel / (tau_decay_ms / 1000.0)) -
              np.exp(-t_kernel / (tau_rise_ms / 1000.0)))

    # Normalize kernel (peak to 1 for interpretability, though FFT norm handles scale)
    if np.max(kernel) > 1e-9:
         kernel /= np.max(kernel)
    else:
         log.warning("Kernel peak is near zero. Check time constants.")
         # Create a tiny impulse if kernel is zero
         kernel = np.zeros(kernel_len)
         kernel[0] = 1e-6

    log.debug(f"Generated kernel: length={kernel_len}, tau_r={tau_rise_samples:.1f} samples, tau_d={tau_decay_samples:.1f} samples")

    # --- 3. Deconvolution via FFT with Regularization ---
    # Ensure kernel is same length as data for FFT (pad with zeros)
    kernel_padded = np.zeros(n_points)
    kernel_padded[:kernel_len] = kernel

    data_fft = np.fft.fft(filtered_data)
    kernel_fft = np.fft.fft(kernel_padded)

    # Regularization: Add small value based on kernel power spectrum peak
    kernel_power = np.abs(kernel_fft)**2
    epsilon = regularization_factor * np.max(kernel_power)
    if epsilon < 1e-12:
        epsilon = 1e-12 # Floor value
        
    log.debug(f"Deconvolution regularization epsilon: {epsilon:.2e}")

    # Deconvolve (Wiener-like regularization)
    deconvolved_fft = data_fft * np.conj(kernel_fft) / (kernel_power + epsilon)
    deconvolved_trace = np.fft.ifft(deconvolved_fft).real

    log.debug(f"Deconvolution completed. Deconvolved trace length: {len(deconvolved_trace)}")

    # --- 4. Thresholding & Peak Finding ---
    # Estimate noise SD of the deconvolved trace using MAD
    # Use a central portion, avoiding potential edge artifacts from FFT/filtering
    start_idx = max(kernel_len, n_points // 10) # Start after kernel/edge region
    end_idx = n_points - start_idx
    if start_idx >= end_idx: # Handle very short traces
        trace_for_noise_est = deconvolved_trace
    else:
        trace_for_noise_est = deconvolved_trace[start_idx:end_idx]
        
    if len(trace_for_noise_est) < 2: # Need at least 2 points for MAD
        log.warning("Cannot estimate noise from deconvolved trace (too short). Using fallback estimate.")
        # Fallback: estimate noise from original data and scale down (crude)
        mad_raw = median_abs_deviation(filtered_data, scale='normal')
        noise_sd_deconv = mad_raw * 0.1 # Guess: deconvolution improves SNR 10x
    else:
        mad_deconv = median_abs_deviation(trace_for_noise_est, scale='normal')
        if mad_deconv < 1e-12:
             log.warning("MAD of deconvolved trace is near zero. Check parameters or data.")
             mad_deconv = 1e-12 # Avoid zero SD
        noise_sd_deconv = mad_deconv # MAD with scale='normal' approximates SD
        
    detection_level = threshold_sd * noise_sd_deconv
    log.debug(f"Deconvolved trace noise SD (est.): {noise_sd_deconv:.3g}, Detection level: {detection_level:.3g}")

    # Find peaks
    min_dist_samples = int(min_event_separation_ms / 1000.0 * sample_rate)
    if min_dist_samples < 1:
        min_dist_samples = 1

    # Note: The deconvolved trace might be inverted depending on kernel normalization/polarity
    # We assume positive peaks correspond to events. If events are negative,
    # find peaks on -deconvolved_trace or adjust kernel generation.
    # Let's assume the user wants positive peaks in the deconvolved trace
    # (or negative events become positive peaks after deconvolution with a positive kernel)
    peak_indices, _ = signal.find_peaks(deconvolved_trace, height=detection_level, distance=min_dist_samples)

    log.info(f"Found {len(peak_indices)} raw peaks using custom deconvolution.")

    # --- 5. Output ---
    stats = {
        'count': len(peak_indices),
        # Add more stats later if needed (e.g., based on original data at peak_indices)
    }

    return peak_indices, stats 

# Function adapted from rmp_analysis - might need refinement
def _find_stable_baseline_segment(data: np.ndarray, sample_rate: float,
                                 window_duration_s: float = 0.5,
                                 step_duration_s: float = 0.1) -> Tuple[Optional[float], Optional[float], Optional[Tuple[int, int]]]:
    """Finds the most stable baseline segment based on minimum variance.

    Args:
        data: 1D numpy array of the signal.
        sample_rate: Sampling rate in Hz.
        window_duration_s: Duration of the sliding window in seconds.
        step_duration_s: Step size for sliding the window in seconds.

    Returns:
        A tuple containing:
            - baseline_mean: Mean of the most stable segment (or None).
            - baseline_sd: Standard deviation of the most stable segment (or None).
            - segment_indices: Tuple of (start_index, end_index) for the segment (or None).
    """
    n_points = len(data)
    window_samples = int(window_duration_s * sample_rate)
    step_samples = int(step_duration_s * sample_rate)

    if window_samples < 2 or step_samples < 1:
        log.warning(f"Baseline window ({window_samples}) or step ({step_samples}) too small. Adjust parameters.")
        window_samples = max(2, window_samples)
        step_samples = max(1, step_samples)
       
    if window_samples >= n_points:
        log.warning("Baseline window duration >= data length. Using full trace.")
        segment_data = data
        mean_val = np.mean(segment_data)
        sd_val = np.std(segment_data)
        return mean_val, sd_val, (0, n_points)

    min_variance = np.inf
    best_segment_indices = None
    best_mean = None
    best_sd = None

    for i in range(0, n_points - window_samples + 1, step_samples):
        segment = data[i : i + window_samples]
        variance = np.var(segment)
        if variance < min_variance:
            min_variance = variance
            best_segment_indices = (i, i + window_samples)
            best_mean = np.mean(segment)
            best_sd = np.sqrt(variance)
           
    if best_segment_indices is None:
         log.warning("Could not find a stable baseline segment.")
         return None, None, None
        
    log.debug(f"Found stable baseline: Mean={best_mean:.3f}, SD={best_sd:.3f}, Indices={best_segment_indices}")
    return best_mean, best_sd, best_segment_indices


def _calculate_simplified_kinetics(data: np.ndarray, peak_index: int, baseline_value: float,
                                  sample_rate: float) -> Dict[str, float]:
    """Calculates simplified 10-90% rise time and time to 50% decay.

    Args:
        data: 1D data array.
        peak_index: Index of the detected peak.
        baseline_value: Baseline value relative to which amplitude is measured.
        sample_rate: Sampling rate in Hz.

    Returns:
        Dictionary with 'rise_time_ms' and 'decay_half_time_ms'. Values are np.nan if calculation fails.
    """
    kinetics = {'rise_time_ms': np.nan, 'decay_half_time_ms': np.nan}
    dt_ms = 1000.0 / sample_rate

    try:
        peak_value = data[peak_index]
        relative_amplitude = peak_value - baseline_value
        is_positive_event = relative_amplitude > 0

        if abs(relative_amplitude) < 1e-9: # Avoid division by zero for flat events
            return kinetics
           
        # --- Rise Time (10-90%) ---
        amp_10 = baseline_value + 0.1 * relative_amplitude
        amp_90 = baseline_value + 0.9 * relative_amplitude
       
        search_start_rise = max(0, peak_index - int(0.1 * sample_rate)) # Search up to 100ms before peak
        trace_before_peak = data[search_start_rise:peak_index+1]

        indices_10 = np.where(trace_before_peak >= amp_10 if is_positive_event else trace_before_peak <= amp_10)[0]
        indices_90 = np.where(trace_before_peak >= amp_90 if is_positive_event else trace_before_peak <= amp_90)[0]

        if len(indices_10) > 0 and len(indices_90) > 0:
            # Find first time it crosses 10% and 90% going towards peak
            idx_10 = search_start_rise + indices_10[0]
            idx_90 = search_start_rise + indices_90[0]
            if idx_90 > idx_10:
                kinetics['rise_time_ms'] = (idx_90 - idx_10) * dt_ms
               
        # --- Decay Time (Time to 50% from peak) ---
        amp_50_decay = baseline_value + 0.5 * relative_amplitude
        search_end_decay = min(len(data), peak_index + int(0.5 * sample_rate)) # Search up to 500ms after peak
        trace_after_peak = data[peak_index:search_end_decay]
       
        indices_50_decay = np.where(trace_after_peak <= amp_50_decay if is_positive_event else trace_after_peak >= amp_50_decay)[0]
       
        if len(indices_50_decay) > 0:
            # Find first time it crosses back to 50% after peak
            idx_50 = peak_index + indices_50_decay[0]
            if idx_50 > peak_index:
                kinetics['decay_half_time_ms'] = (idx_50 - peak_index) * dt_ms
               
    except Exception as e:
        log.warning(f"Error calculating simplified kinetics for peak at {peak_index}: {e}", exc_info=False)

    return kinetics


@AnalysisRegistry.register("event_detection_baseline_peak")
def detect_events_baseline_peak_kinetics(
    data: np.ndarray,
    sample_rate: float,
    direction: str = 'negative', # Detect negative or positive peaks
    baseline_window_s: float = 0.5,
    baseline_step_s: float = 0.1,
    threshold_sd_factor: float = 3.0,
    filter_freq_hz: Optional[float] = None,
    min_event_separation_ms: float = 5.0,
    peak_prominence_factor: Optional[float] = None # Optional: Require peak prominence relative to threshold_sd*noise_sd
) -> Tuple[np.ndarray, Dict[str, Any], Optional[List[Dict[str, Any]]]]:
    """Detects events by finding peaks relative to a stable baseline,
       and calculates simplified kinetics.

    Args:
        data: 1D numpy array of the signal.
        sample_rate: Sampling rate in Hz.
        direction: 'negative' or 'positive' peak detection.
        baseline_window_s: Duration of the window to find stable baseline.
        baseline_step_s: Step size for the baseline window.
        threshold_sd_factor: Threshold for peak detection in multiples of baseline SD.
        filter_freq_hz: Optional cutoff frequency for low-pass filtering before peak detection.
        min_event_separation_ms: Minimum time between detected peaks.
        peak_prominence_factor: Optional factor. If set, peaks must have a prominence of at least
                                 peak_prominence_factor * threshold_sd_factor * baseline_sd.

    Returns:
        A tuple containing:
            - indices: Numpy array of detected event peak indices.
            - summary_stats: Dictionary with summary statistics ('count', 'baseline_mean', 'baseline_sd', 'threshold').
            - event_details: List of dictionaries, one per event, with 'index', 'amplitude', 'rise_time_ms', 'decay_half_time_ms'. (or None if error)
    """
    if direction not in ['negative', 'positive']:
        raise ValueError("Direction must be 'negative' or 'positive'")

    is_negative = (direction == 'negative')
    signal_to_process = -data if is_negative else data # Always look for positive peaks

    # --- 1. Find Stable Baseline --- 
    baseline_mean_orig, baseline_sd_orig, _ = _find_stable_baseline_segment(
        data, sample_rate, baseline_window_s, baseline_step_s
    )
    if baseline_mean_orig is None or baseline_sd_orig is None:
        log.error("Failed to find stable baseline. Cannot proceed.")
        return np.array([]), {'count': 0}, None
       
    # Adjust baseline mean based on direction for thresholding the processed signal
    baseline_mean_processed = -baseline_mean_orig if is_negative else baseline_mean_orig
    baseline_sd = baseline_sd_orig # SD is invariant to sign flip
    
    if baseline_sd < 1e-12: # Avoid zero SD
        log.warning("Baseline SD is near zero. Setting to small value.")
        baseline_sd = 1e-12

    # --- 2. Set Adaptive Threshold --- 
    threshold_abs_deviation = threshold_sd_factor * baseline_sd
    detection_threshold = baseline_mean_processed + threshold_abs_deviation
    log.debug(f"Baseline Peak Detection: Threshold set at {detection_threshold:.3g} (Baseline={baseline_mean_processed:.3g}, ThrSD={threshold_abs_deviation:.3g})")

    # --- 3. Optional Filtering ---
    if filter_freq_hz is not None and filter_freq_hz > 0:
        if filter_freq_hz >= sample_rate / 2:
             log.warning(f"Filter frequency ({filter_freq_hz} Hz) is >= Nyquist frequency ({sample_rate / 2} Hz). Skipping filter.")
             filtered_signal_to_process = signal_to_process.copy()
        else:
            try:
                sos = signal.butter(4, filter_freq_hz, btype='low', analog=False, output='sos', fs=sample_rate)
                filtered_signal_to_process = signal.sosfiltfilt(sos, signal_to_process)
                log.debug(f"Applied low-pass filter at {filter_freq_hz} Hz for peak finding.")
            except Exception as e:
                log.error(f"Error applying filter: {e}. Using unfiltered data for peak finding.")
                filtered_signal_to_process = signal_to_process.copy()
    else:
        filtered_signal_to_process = signal_to_process.copy()
       
    # --- 4. Detect Peaks --- 
    min_dist_samples = int(min_event_separation_ms / 1000.0 * sample_rate)
    if min_dist_samples < 1:
        min_dist_samples = 1

    prominence_value = None
    if peak_prominence_factor is not None and peak_prominence_factor > 0:
        prominence_value = peak_prominence_factor * threshold_abs_deviation
        log.debug(f"Requiring peak prominence >= {prominence_value:.3g}")
       
    try:
        peak_indices, properties = signal.find_peaks(
            filtered_signal_to_process, 
            height=detection_threshold, 
            distance=min_dist_samples,
            prominence=prominence_value
        )
        log.info(f"Found {len(peak_indices)} peaks using baseline+peak method.")
    except Exception as e:
        log.error(f"Error during scipy.signal.find_peaks: {e}", exc_info=True)
        return np.array([]), {'count': 0, 'baseline_mean': baseline_mean_orig, 'baseline_sd': baseline_sd_orig, 'threshold': detection_threshold if is_negative else -detection_threshold}, None
       
    # --- 5. Calculate Kinetics & Amplitude for Each Peak --- 
    event_details = []
    if len(peak_indices) > 0:
        for idx in peak_indices:
            amplitude = data[idx] - baseline_mean_orig # Amplitude relative to original baseline
            kinetics = _calculate_simplified_kinetics(data, idx, baseline_mean_orig, sample_rate)
            event_details.append({
                'index': idx,
                'amplitude': amplitude,
                'rise_time_ms': kinetics['rise_time_ms'],
                'decay_half_time_ms': kinetics['decay_half_time_ms']
            })
           
    # --- 6. Prepare Output --- 
    summary_stats = {
        'count': len(peak_indices),
        'baseline_mean': baseline_mean_orig,
        'baseline_sd': baseline_sd_orig,
        'threshold': detection_threshold if not is_negative else -detection_threshold # Return threshold in original data polarity
    }
    # Could add mean amplitude, freq etc. to summary stats if needed
   
    return peak_indices, summary_stats, event_details 