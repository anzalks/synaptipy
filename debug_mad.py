
import sys
import numpy as np
from scipy.stats import median_abs_deviation

def debug_mad():
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
    
    # Calculate MAD of whole trace
    mad = median_abs_deviation(data, scale='normal')
    print(f"MAD (whole trace): {mad}")
    
    # Calculate SD of noise part
    print(f"Actual Noise SD: {noise_sd}")
    
    # Calculate MAD of flat part
    mad_flat = median_abs_deviation(data[:flat_len], scale='normal')
    print(f"MAD (flat part): {mad_flat}")
    
    # Calculate MAD of noisy part
    mad_noisy = median_abs_deviation(data[flat_len:], scale='normal')
    print(f"MAD (noisy part): {mad_noisy}")
    
    # If flat segment is large, it pulls median towards 0 (which is fine)
    # But it also pulls MAD down?
    # MAD = median(|x - median|)
    # If 25% is 0, and 75% is normal(0,1). Median is ~0.
    # |x - 0| is |x|.
    # We take median of |x|.
    # 25% are 0. 75% are |normal|.
    # The median of the combined set will be slightly lower than median of |normal|.
    # Median of |normal| is 0.6745.
    # If we add 25% zeros, the median of the distribution shifts left.
    
    # Let's verify.

if __name__ == '__main__':
    debug_mad()
