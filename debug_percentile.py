
import sys
import numpy as np

def debug_percentile():
    fs = 1000.0
    duration = 2.0
    t = np.arange(int(duration * fs)) / fs
    
    noise_sd = 1.0
    data = np.random.normal(0, noise_sd, len(t))
    
    # Add flat segment (25% of data)
    flat_len = int(0.5 * fs)
    data[:flat_len] = 0.0
    
    # Add an event
    event_idx = int(1.0 * fs)
    data[event_idx] += 5.0
    
    # Calculate 68th percentile of whole trace
    abs_dev = np.abs(data)
    p68 = np.percentile(abs_dev, 68.27)
    print(f"68th Percentile (whole trace): {p68}")
    
    # Calculate 68th percentile of non-zero trace
    non_zero_abs_dev = abs_dev[abs_dev > 1e-9]
    p68_nz = np.percentile(non_zero_abs_dev, 68.27)
    print(f"68th Percentile (non-zero): {p68_nz}")
    
    print(f"Actual Noise SD: {noise_sd}")

if __name__ == '__main__':
    debug_percentile()
