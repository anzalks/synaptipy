"""Debug script to check data ranges for all example files."""
from pathlib import Path
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter
import numpy as np

a = NeoAdapter()
data_dir = Path("examples/data")
files = sorted(data_dir.glob("*.abf"))

for f in files:
    try:
        r = a.read_recording(f)
        for cid, ch in r.channels.items():
            t = ch.get_relative_time_vector(0)
            d = ch.get_data(0)
            print(
                f"{f.name} | ch={cid} | t=[{t[0]:.4f}, {t[-1]:.4f}] | "
                f"d=[{np.min(d):.2f}, {np.max(d):.2f}] | "
                f"t_start={ch.t_start} | fs={ch.sampling_rate} | "
                f"trials={ch.num_trials}"
            )
    except Exception as e:
        print(f"{f.name}: ERROR - {e}")
