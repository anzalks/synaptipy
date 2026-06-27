#!/usr/bin/env python3
"""
Basic Usage Example for Synaptipy

This example demonstrates programmatic usage of Synaptipy for loading
electrophysiology data, analyzing input resistance, and exporting results.
Figures are saved to disk as PDF (vector, publication-ready) and PNG (raster).

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import matplotlib
import numpy as np
from matplotlib import pyplot as plt

from synaptipy.analysis.resistance_analysis import calculate_input_resistance
from synaptipy.core.data_model import Channel, Recording

# ---------------------------------------------------------------------------
# Publication-quality rcParams -- inject before any figure is created
# ---------------------------------------------------------------------------
matplotlib.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 8,
        "axes.titlesize": 8,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "lines.linewidth": 0.8,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "pdf.fonttype": 42,  # editable text in Illustrator / Inkscape
        "ps.fonttype": 42,
    }
)


def _draw_l_scale_bar(ax, x0, y0, dx, dy, x_label, y_label, fontsize=7):
    """Draw an L-shaped scale bar on *ax* and hide all axes decorations."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.plot([x0, x0 + dx], [y0, y0], color="k", linewidth=1.5, solid_capstyle="butt", clip_on=False)
    ax.plot([x0, x0], [y0, y0 + dy], color="k", linewidth=1.5, solid_capstyle="butt", clip_on=False)
    ax.text(x0 + dx / 2, y0 - 0.12 * dy, x_label, ha="center", va="top", fontsize=fontsize)
    ax.text(
        x0 - 0.01 * (ax.get_xlim()[1] - ax.get_xlim()[0]),
        y0 + dy / 2,
        y_label,
        ha="right",
        va="center",
        fontsize=fontsize,
        rotation=90,
    )


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
        id="1", name="Vm", units="mV", sampling_rate=10000.0, data_trials=[voltage_data], trial_t_starts=[0.0]
    )

    # Create current channel with a step response
    current_data = np.zeros_like(time_vec)
    current_data[2000:5000] = -50.0  # -50 pA step from 0.2s to 0.5s

    # Add some noise
    current_data += np.random.normal(0, 1.0, size=current_data.shape)

    # Create a mock current channel
    i_channel = Channel(
        id="2", name="Im", units="pA", sampling_rate=10000.0, data_trials=[current_data], trial_t_starts=[0.0]
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
        trial_index=0,  # Use first trial
    )

    # Print results
    print(f"Input Resistance: {result['Rin (MΩ)']:.2f} MΩ")
    print(f"Conductance: {result['Conductance (μS)']:.2f} μS")
    print(f"ΔV: {result['ΔV (mV)']:.2f} mV")
    print(f"ΔI: {result['ΔI (pA)']:.2f} pA")

    # -----------------------------------------------------------------------
    # Publication-quality figure: voltage + current traces with L-scale bars
    # -----------------------------------------------------------------------
    v_data = v_channel.data_trials[0]
    i_data = i_channel.data_trials[0]

    fig, (ax_v, ax_i) = plt.subplots(
        2,
        1,
        figsize=(3.5, 3.0),
        gridspec_kw={"height_ratios": [3, 2], "hspace": 0.05},
    )

    # Voltage trace
    ax_v.plot(time_vec, v_data, color="k", linewidth=0.6)
    ax_v.set_title("Input Resistance Analysis", pad=4)

    # Current trace
    ax_i.plot(time_vec, i_data, color="#c0392b", linewidth=0.6)

    # Highlight analysis windows on current panel only
    ax_i.axvspan(baseline_window[0], baseline_window[1], alpha=0.15, color="#27ae60", label="Baseline")
    ax_i.axvspan(response_window[0], response_window[1], alpha=0.15, color="#e74c3c", label="Response")
    ax_i.legend(frameon=False, loc="lower right")

    # L-shaped scale bars --------------------------------------------------
    # Voltage panel: 100 ms, 5 mV
    ax_v.set_xlim(time_vec[0], time_vec[-1])
    ax_v.set_ylim(v_data.min() - 1, v_data.max() + 1)
    _draw_l_scale_bar(
        ax_v,
        x0=time_vec[-1] - 0.18,
        y0=v_data.min() + 0.05 * (v_data.max() - v_data.min()),
        dx=0.100,
        dy=5.0,
        x_label="100 ms",
        y_label="5 mV",
    )

    # Current panel: 100 ms, 20 pA
    ax_i.set_xlim(time_vec[0], time_vec[-1])
    ax_i.set_ylim(i_data.min() - 5, i_data.max() + 5)
    _draw_l_scale_bar(
        ax_i,
        x0=time_vec[-1] - 0.18,
        y0=i_data.min() + 0.05 * (i_data.max() - i_data.min()),
        dx=0.100,
        dy=20.0,
        x_label="100 ms",
        y_label="20 pA",
    )

    # Annotate Rin on the voltage panel
    ax_v.text(
        0.02,
        0.95,
        f"Rin = {result['Rin (MΩ)']:.1f} MΩ",
        transform=ax_v.transAxes,
        va="top",
        ha="left",
        fontsize=7,
    )

    plt.savefig("fig_input_resistance.pdf", bbox_inches="tight")
    plt.savefig("fig_input_resistance.png", bbox_inches="tight")
    plt.close("all")
    print("Figures saved: fig_input_resistance.pdf / .png")

    # Option: Export to NWB (uncomment to use)
    """
    print("\nExporting to NWB...")
    nwb_exporter = NWBExporter()
    output_path = Path('./output_recording.nwb')

    # Set metadata
    metadata = {
        'session_description': 'Example recording from synaptipy',
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


if __name__ == "__main__":
    main()
