"""
Utilities for generating synthetic test data files.

This module provides functions to create synthetic electrophysiology data
for testing purposes, avoiding the need to include large real recordings
in the repository.
"""

import numpy as np
import os
from pathlib import Path
import logging

# Try to import Neo for file writing, but provide alternative if not available
try:
    import neo
    import quantities as pq

    NEO_AVAILABLE = True
except ImportError:
    NEO_AVAILABLE = False

# Set up logging
logger = logging.getLogger(__name__)


def generate_sine_wave(duration=1.0, frequency=10.0, sampling_rate=10000, amplitude=1.0, phase=0.0):
    """
    Generate a sine wave with specified parameters.

    Args:
        duration (float): Duration in seconds
        frequency (float): Frequency in Hz
        sampling_rate (int): Sampling rate in Hz
        amplitude (float): Amplitude of the sine wave
        phase (float): Phase offset in radians

    Returns:
        tuple: (time_array, data_array)
    """
    num_samples = int(duration * sampling_rate)
    time = np.linspace(0, duration, num_samples, endpoint=False)
    data = amplitude * np.sin(2 * np.pi * frequency * time + phase)
    return time, data


def generate_voltage_clamp_step(
    duration=1.0, step_start=0.2, step_duration=0.5, baseline=-70.0, step_amplitude=-10.0, sampling_rate=10000
):
    """
    Generate a voltage clamp step protocol.

    Args:
        duration (float): Total duration in seconds
        step_start (float): When the step starts in seconds
        step_duration (float): Duration of the step in seconds
        baseline (float): Baseline holding potential in mV
        step_amplitude (float): Amplitude of the step in mV
        sampling_rate (int): Sampling rate in Hz

    Returns:
        tuple: (time_array, voltage_array)
    """
    num_samples = int(duration * sampling_rate)
    time = np.linspace(0, duration, num_samples, endpoint=False)
    voltage = np.ones_like(time) * baseline

    # Calculate sample indices for step
    step_start_idx = int(step_start * sampling_rate)
    step_end_idx = int((step_start + step_duration) * sampling_rate)

    # Apply step
    if step_end_idx > step_start_idx and step_start_idx < len(voltage):
        end_idx = min(step_end_idx, len(voltage))
        voltage[step_start_idx:end_idx] = baseline + step_amplitude

    return time, voltage


def generate_current_response(
    voltage_time, voltage_data, input_resistance=100.0, capacitance=20.0, sampling_rate=10000, noise_level=0.02
):
    """
    Generate a current response to a voltage command based on a simple RC model.

    Args:
        voltage_time (array): Time points
        voltage_data (array): Voltage command data
        input_resistance (float): Input resistance in MOhm
        capacitance (float): Membrane capacitance in pF
        sampling_rate (int): Sampling rate in Hz
        noise_level (float): Amount of noise to add (fraction of signal amplitude)

    Returns:
        array: Current response data
    """
    # Convert from MOhm to Ohm and pF to F
    resistance = input_resistance * 1e6  # MOhm to Ohm
    cap = capacitance * 1e-12  # pF to F

    # Calculate time step
    dt = 1.0 / sampling_rate

    # Initialize current array
    current = np.zeros_like(voltage_data)

    # Calculate steady-state currents (I = V/R)
    steady_state = voltage_data / resistance

    # First point
    current[0] = steady_state[0]

    # Calculate time constant (tau = RC)
    tau = resistance * cap
    decay_factor = np.exp(-dt / tau)

    # Apply simple RC model with time constant
    for i in range(1, len(voltage_data)):
        # If voltage changes, add capacitive current
        if voltage_data[i] != voltage_data[i - 1]:
            cap_current = (voltage_data[i] - voltage_data[i - 1]) * cap / dt
        else:
            cap_current = 0

        # Current is sum of resistive (steady-state) and capacitive components
        current[i] = steady_state[i] + cap_current

    # Add noise
    if noise_level > 0:
        noise = np.random.normal(0, noise_level * np.ptp(current), size=current.shape)
        current += noise

    return current


def create_dummy_abf_file(output_path, sampling_rate=10000, duration=1.0):
    """
    Create a dummy ABF file with voltage and current channels.

    Args:
        output_path (str or Path): Path to save the ABF file
        sampling_rate (int): Sampling rate in Hz
        duration (float): Recording duration in seconds

    Returns:
        bool: True if successful, False otherwise
    """
    if not NEO_AVAILABLE:
        logger.error("Neo library not available. Cannot create ABF file.")
        return False

    try:
        # Generate voltage step protocol
        time, voltage = generate_voltage_clamp_step(
            duration=duration,
            sampling_rate=sampling_rate,
            baseline=-70.0,
            step_amplitude=-10.0,
            step_start=0.2,
            step_duration=0.5,
        )

        # Generate current response
        current = generate_current_response(
            time, voltage, input_resistance=100.0, capacitance=20.0, sampling_rate=sampling_rate
        )

        # Create Neo objects
        block = neo.Block(name="Test Block")
        segment = neo.Segment(name="Test Segment")
        block.segments.append(segment)

        # Create voltage signal
        voltage_signal = neo.AnalogSignal(
            voltage * pq.mV, sampling_rate=sampling_rate * pq.Hz, t_start=0 * pq.s, name="Vm", channel_index=0
        )
        voltage_signal.annotations["channel_name"] = "Vm"

        # Create current signal
        current_signal = neo.AnalogSignal(
            current * pq.pA, sampling_rate=sampling_rate * pq.Hz, t_start=0 * pq.s, name="Im", channel_index=1
        )
        current_signal.annotations["channel_name"] = "Im"

        # Add signals to segment
        segment.analogsignals.append(voltage_signal)
        segment.analogsignals.append(current_signal)

        # Create a writer
        writer = neo.io.NixIO(filename=str(output_path))
        writer.write_block(block)
        writer.close()

        logger.info(f"Created test file at: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to create test file: {e}")
        return False


if __name__ == "__main__":
    # Setup basic logging
    logging.basicConfig(level=logging.INFO)

    # Path to the test data directory
    test_data_dir = Path(__file__).parent.parent / "data"
    os.makedirs(test_data_dir, exist_ok=True)

    # Create a dummy NWB file
    if NEO_AVAILABLE:
        sample_path = test_data_dir / "sample_synthetic.nix"
        if create_dummy_abf_file(sample_path):
            print(f"Created synthetic test file at: {sample_path}")
        else:
            print("Failed to create synthetic test file")
    else:
        print("Neo not available. Cannot create test files.")
