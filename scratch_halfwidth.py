import numpy as np
from Synaptipy.core.analysis.single_spike import detect_spikes_threshold, calculate_spike_features
import pyabf

abf = pyabf.ABF("examples/data/2023_04_11_0021.abf")
for s in range(abf.sweepCount):
    abf.setSweep(s)
    data = abf.sweepY
    time = abf.sweepX
    sampling_rate = abf.dataRate

    res = detect_spikes_threshold(data, time, -20.0, int(0.002 * sampling_rate))
    features = calculate_spike_features(data, time, res.spike_indices)
    
    if len(features) > 0:
        print(f"Sweep {s}: Detected {len(features)} spikes")
        for i, f in enumerate(features[:2]):
            print(f"  Spike {i}: HW={f['half_width']:.3f} ms, thresh={f['ap_threshold']:.2f} mV, amp={f['amplitude']:.2f} mV, rise={f['rise_time_10_90']:.3f} ms, decay={f['decay_time_90_10']:.3f} ms")
        break
