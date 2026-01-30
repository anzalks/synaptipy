#!/usr/bin/env python3
"""
Basic Usage Example for Synaptipy

This example demonstrates programmatic usage of Synaptipy for loading
electrophysiology data, analyzing input resistance, and exporting results.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import numpy as np
from matplotlib import pyplot as plt

# Import Synaptipy components
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.analysis.resistance_analysis import calculate_input_resistance


def create_synthetic_data():
    """Create a synthetic voltage clamp recording for demonstration"""
    # Create a recording
    recording = Recording(source_file=None)
    recording.sampling_rate = 10000.0  # 10 kHz
    recording.t_start = 0.0
    recording.duration = 1.0  # 1 second

    # Create voltage channel with a step response
    time_vec = np.linspace(0, 1, 10000)  # 1 second at 10kHz
    voltage_data = np.zeros_like(time_vec)
    voltage_data[2000:5000] = -10.0  # -10 mV step from 0.2s to 0.5s

    # Add some noise
    voltage_data += np.random.normal(0, 0.2, size=voltage_data.shape)

    # Create a mock voltage channel
    v_channel = Channel(
        id="1",
        name="Vm",
        units="mV",
        sampling_rate=10000.0,
        data_trials=[voltage_data],
        trial_t_starts=[0.0]
    )

    # Create current channel with a step response
    current_data = np.zeros_like(time_vec)
    current_data[2000:5000] = -50.0  # -50 pA step from 0.2s to 0.5s

    # Add some noise
    current_data += np.random.normal(0, 1.0, size=current_data.shape)

    # Create a mock current channel
    i_channel = Channel(
        id="2",
        name="Im",
        units="pA",
        sampling_rate=10000.0,
        data_trials=[current_data],
        trial_t_starts=[0.0]
    )

    # Add channels to recording
    recording.add_channel(v_channel)
    recording.add_channel(i_channel)

    return recording, time_vec


def main():
    """Main function demonstrating Synaptipy usage"""
    print("Synaptipy Basic Usage Example")
    print("-----------------------------")

    # Option 1: Load from an existing file (uncomment if you have data files)
    """
    filepath = Path("path/to/your/data.abf")
    if not filepath.exists():
        print(f"Error: File {filepath} does not exist.")
        sys.exit(1)

    # Use Neo adapter to load the file
    neo_adapter = NeoAdapter()
    try:
        recording = neo_adapter.read_recording(filepath)
        print(f"Successfully loaded {filepath}")
        print(f"Recording has {len(recording.channels)} channels")
        for channel in recording.channels:
            print(f"Channel: {channel.name} ({channel.units})")
    except Exception as e:
        print(f"Error loading file: {e}")
        sys.exit(1)
    """

    # Option 2: Use synthetic data (for demonstration)
    recording, time_vec = create_synthetic_data()
    print("Created synthetic recording with 2 channels")
    print(f"Recording duration: {recording.duration}s at {recording.sampling_rate}Hz")

    # Analyze input resistance
    print("\nAnalyzing input resistance...")

    # Get voltage and current channels
    v_channel = recording.get_channel_by_name("Vm")
    i_channel = recording.get_channel_by_name("Im")

    # Define baseline and response windows
    baseline_window = [0.0, 0.15]  # seconds
    response_window = [0.3, 0.45]  # seconds

    # Calculate input resistance
    result = calculate_input_resistance(
        v_channel=v_channel,
        i_channel=i_channel,
        baseline_window=baseline_window,
        response_window=response_window,
        trial_index=0  # Use first trial
    )

    # Print results
    print(f"Input Resistance: {result['Rin (MΩ)']:.2f} MΩ")
    print(f"Conductance: {result['Conductance (μS)']:.2f} μS")
    print(f"ΔV: {result['ΔV (mV)']:.2f} mV")
    print(f"ΔI: {result['ΔI (pA)']:.2f} pA")

    # Plot the data and analysis
    plt.figure(figsize=(10, 6))

    # Plot voltage trace
    plt.subplot(2, 1, 1)
    plt.plot(time_vec, v_channel.data_trials[0], 'b-', label='Voltage')
    plt.axvspan(baseline_window[0], baseline_window[1], alpha=0.2, color='green', label='Baseline')
    plt.axvspan(response_window[0], response_window[1], alpha=0.2, color='red', label='Response')
    plt.ylabel('Voltage (mV)')
    plt.legend()
    plt.title('Input Resistance Analysis')

    # Plot current trace
    plt.subplot(2, 1, 2)
    plt.plot(time_vec, i_channel.data_trials[0], 'r-', label='Current')
    plt.axvspan(baseline_window[0], baseline_window[1], alpha=0.2, color='green', label='Baseline')
    plt.axvspan(response_window[0], response_window[1], alpha=0.2, color='red', label='Response')
    plt.xlabel('Time (s)')
    plt.ylabel('Current (pA)')
    plt.legend()

    # Option: Export to NWB (uncomment to use)
    """
    print("\nExporting to NWB...")
    nwb_exporter = NWBExporter()
    output_path = Path('./output_recording.nwb')

    # Set metadata
    metadata = {
        'session_description': 'Example recording from Synaptipy',
        'experimenter': 'Example User',
        'lab': 'Example Lab',
        'institution': 'Example Institution',
        'experiment_description': 'Test experiment',
        'session_id': 'test123'
    }

    # Export to NWB
    try:
        nwb_exporter.export(recording, output_path, metadata)
        print(f"Successfully exported to {output_path}")
    except Exception as e:
        print(f"Error exporting to NWB: {e}")
    """

    print("\nExample completed.")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
