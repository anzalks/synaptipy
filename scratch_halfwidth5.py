import numpy as np
if not hasattr(np, "unicode_"):
    np.unicode_ = np.str_
if not hasattr(np, "VisibleDeprecationWarning"):
    np.VisibleDeprecationWarning = DeprecationWarning

from Synaptipy.core.analysis.single_spike import calculate_spike_features
import pandas as pd
from allensdk.core.cell_types_cache import CellTypesCache
import os

ctc = CellTypesCache(manifest_file=os.path.join("paper/allen_cache", "manifest.json"))
ephys_data = ctc.get_ephys_data(480087928)
sweep = ephys_data.get_sweep(40) # A long square sweep
v = sweep["response"] * 1e3
i = sweep["stimulus"] * 1e12
sr = sweep["sampling_rate"]
t = np.arange(len(v)) / sr

from Synaptipy.core.analysis.single_spike import detect_spikes_threshold
res = detect_spikes_threshold(v, t, -20.0, int(0.002 * sr))
features = calculate_spike_features(v, t, res.spike_indices)

print(f"Detected {len(features)} spikes")
if len(features) > 0:
    for i, f in enumerate(features[:2]):
        print(f"Spike {i}: HW={f['half_width']:.3f} ms, thresh={f['ap_threshold']:.2f} mV, amp={f['amplitude']:.2f} mV, rise={f['rise_time_10_90']:.3f} ms, decay={f['decay_time_90_10']:.3f} ms")
