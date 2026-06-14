#!/usr/bin/env python3
"""
SynaptiPy eNeuro Demo Script
Generates a demonstration dataset and performs automated extraction
of electrophysiological properties (Task 14).
"""

import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path

from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.core.analysis.passive_properties import calculate_rin
from Synaptipy.core.analysis.single_spike import detect_spikes_threshold

def create_demo_data():
    """Create a realistic synthetic recording for the demo."""
    recording = Recording(source_file=None)
    recording.sampling_rate = 20000.0  # 20 kHz
    recording.t_start = 0.0
    recording.duration = 1.0  # 1 second
    time_vec = np.linspace(0, 1, 20000)

    # Voltage trace with a resting potential and a spike
    voltage_data = np.ones_like(time_vec) * -70.0
    # Add a step depolarization
    voltage_data[4000:16000] = -50.0 
    
    # Simulate a spike
    spike_idx = 8000
    voltage_data[spike_idx:spike_idx+20] = np.linspace(-50, 30, 20)
    voltage_data[spike_idx+20:spike_idx+60] = np.linspace(30, -80, 40)
    voltage_data[spike_idx+60:spike_idx+200] = np.linspace(-80, -50, 140)

    # Add noise
    voltage_data += np.random.normal(0, 0.5, size=voltage_data.shape)

    v_channel = Channel(
        id="1", name="Vm", units="mV", sampling_rate=20000.0, data_trials=[voltage_data]
    )

    current_data = np.zeros_like(time_vec)
    current_data[4000:16000] = -100.0  # -100 pA step for Rin
    current_data += np.random.normal(0, 1.0, size=current_data.shape)

    i_channel = Channel(
        id="2", name="Im", units="pA", sampling_rate=20000.0, data_trials=[current_data]
    )

    recording.channels[v_channel.name] = v_channel
    recording.channels[i_channel.name] = i_channel
    return recording, time_vec

def main():
    print("==================================================")
    print("SynaptiPy eNeuro Demonstration Script")
    print("==================================================")
    
    t0 = time.time()
    recording, time_vec = create_demo_data()
    print(f"Created synthetic 2-channel recording ({recording.sampling_rate} Hz)")

    v_channel = recording.channels["Vm"]
    i_channel = recording.channels["Im"]

    # 1. Passive Properties
    print("\n[1/2] Analyzing Input Resistance...")
    res_result = calculate_rin(
        voltage_trace=v_channel.data_trials[0],
        time_vector=time_vec,
        current_amplitude=-100.0,
        baseline_window=(0.0, 0.15),
        response_window=(0.6, 0.75),
    )
    print(f"  -> Rin: {res_result.value:.2f} MΩ")
    print(f"  -> Conductance: {res_result.conductance:.3f} μS")

    # 2. Spike Detection
    print("\n[2/2] Detecting Action Potentials...")
    spikes = detect_spikes_threshold(
        data=v_channel.data_trials[0],
        time=time_vec,
        threshold=-20.0,
        refractory_samples=int(0.002 * v_channel.sampling_rate),
        dvdt_threshold=20.0
    )
    from Synaptipy.core.analysis.single_spike import calculate_spike_features
    print(f"  -> Detected {spikes.value} spike(s)")
    if spikes.value > 0:
        features = calculate_spike_features(
            data=v_channel.data_trials[0],
            time=time_vec,
            spike_indices=spikes.spike_indices,
            dvdt_threshold=20.0
        )
        if len(features) > 0:
            print(f"  -> First AP Peak: {features[0]['absolute_peak_mv']:.1f} mV")
            print(f"  -> First AP Threshold: {features[0]['ap_threshold']:.1f} mV")
            print(f"  -> First AP Amplitude: {features[0]['amplitude']:.1f} mV")

    t1 = time.time()
    print("\n==================================================")
    print(f"Demo completed successfully in {(t1-t0)*1000:.1f} ms.")
    print("==================================================")

if __name__ == "__main__":
    main()
