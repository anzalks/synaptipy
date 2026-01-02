
import numpy as np
from Synaptipy.core.analysis.spike_analysis import run_spike_detection_wrapper

def create_synthetic_ap(t, t_spike_start, rise_time=0.002, amplitude=80.0, threshold= -40.0):
    """Creates a basic AP waveform."""
    v = -70.0 * np.ones_like(t)
    
    # Rise
    rise_mask = (t >= t_spike_start) & (t < t_spike_start + rise_time)
    t_rise = t[rise_mask] - t_spike_start
    # slope = 80 mV / rise_time
    slope = amplitude / rise_time
    v[rise_mask] = -70.0 + slope * t_rise
    
    # Decay
    decay_start = t_spike_start + rise_time
    decay_mask = t >= decay_start
    t_decay = t[decay_mask] - decay_start
    v[decay_mask] = 10.0 - 80.0 * (1 - np.exp(-t_decay / 0.002)) * 1.5 
    v[v < -70.0] = -70.0
    
    return v, slope

def test_spike_params():
    dt = 0.00005 # 20 kHz
    t = np.arange(0, 0.1, dt)
    
    # Fast AP: 40 V/s
    data_fast, slope_fast = create_synthetic_ap(t, 0.02, rise_time=0.002, amplitude=80.0)
    
    # Slow AP: 10 V/s
    # This spike STARTS at -70mV.
    data_slow, slope_slow = create_synthetic_ap(t, 0.05, rise_time=0.008, amplitude=80.0) 
    print(f"\n--- Test Case: Slow AP (~10 V/s) ---")
    
    # 1. High Threshold (20 V/s) -> Should FAIL to find correct onset
    # It will fallback to "search start" which is 5ms before peak.
    res_high = run_spike_detection_wrapper(data_slow, t, 20000.0, dvdt_threshold=20.0)
    print(f"High Thresh (20 V/s) AP Threshold: {res_high.get('ap_threshold_mean', 'N/A')}")
    
    # 2. Low Threshold (5 V/s) -> Should FIND correct onset
    # Should be close to -70.0 mV
    res_low = run_spike_detection_wrapper(data_slow, t, 20000.0, dvdt_threshold=5.0)
    print(f"Low Thresh (5 V/s) AP Threshold: {res_low.get('ap_threshold_mean', 'N/A')}")
    
    # Assertions
    thresh_high = res_high.get('ap_threshold_mean')
    thresh_low = res_low.get('ap_threshold_mean')
    
    if thresh_high is None or thresh_low is None:
        print("FAIL: Could not calculate features.")
        exit(1)
        
    # High threshold should give a HIGHER voltage (later in the rise) because it missed the start
    # Low threshold should give a LOWER voltage (closer to baseline start) because it caught the start
    print(f"Difference: {thresh_high - thresh_low:.3f} mV")
    
    assert thresh_high > -60.0, f"High threshold should mis-detect onset (value {thresh_high} too low?)"
    assert thresh_low < -68.0, f"Low threshold should correctly detect onset near -70mV (got {thresh_low})"
    
    print("\nSUCCESS: Parameterized spike feature extraction works as expected.")

if __name__ == "__main__":
    test_spike_params()
