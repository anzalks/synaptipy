# Synaptipy User Guide

This guide provides detailed instructions for installing, configuring, and using Synaptipy for electrophysiology data visualization and analysis.

## Table of Contents

- [Installation](#installation)
  - [Requirements](#requirements)
  - [Standard Installation](#standard-installation)
  - [Developer Installation](#developer-installation)
- [Getting Started](#getting-started)
  - [Running the Application](#running-the-application)
  - [User Interface Overview](#user-interface-overview)
- [Loading Data](#loading-data)
  - [Supported File Formats](#supported-file-formats)
  - [Opening Files](#opening-files)
- [Using the Explorer Tab](#using-the-explorer-tab)
  - [Navigation Controls](#navigation-controls)
  - [Plot Options](#plot-options)
- [Using the Analyser Tab](#using-the-analyser-tab)
  - [Input Resistance/Conductance Analysis](#input-resistanceconductance-analysis)
  - [Baseline/RMP Analysis](#baselinermp-analysis)
  - [Optogenetic Synchronization](#optogenetic-synchronization)
  - [Sag Ratio (Ih) Analysis](#sag-ratio-ih-analysis)
- [Using the Exporter Tab](#using-the-exporter-tab)
  - [Exporting to NWB](#exporting-to-nwb)
  - [Exporting Analysis Results](#exporting-analysis-results)
- [Advanced Options](#advanced-options)
  - [Command Line Arguments](#command-line-arguments)
  - [Logging and Debugging](#logging-and-debugging)
- [Licensing](#licensing)
- [Troubleshooting](#troubleshooting)

## Installation

### Requirements

- Python 3.10 or higher
- Dependencies are automatically installed during package installation:
  - [PySide6](https://doc.qt.io/qtforpython/) — Qt6 bindings for Python (GUI framework)
  - [PyQtGraph](https://www.pyqtgraph.org) — OpenGL-accelerated plotting library
  - [Neo](https://neo.readthedocs.io) — electrophysiology file I/O (Garcia et al., 2014, *Front. Neuroinformatics* [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010))
  - [NumPy](https://numpy.org) / [SciPy](https://scipy.org) — numerical computation and signal processing
  - [PyNWB](https://pynwb.readthedocs.io) — NWB data export (Rubel et al., 2022, *eLife* [doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362))

### Standard Installation

Synaptipy is not yet published on PyPI. Install from source using the conda environment:

```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
conda env create -f environment.yml
conda activate synaptipy
pip install .
```

### Developer Installation

For contributing to Synaptipy, install in editable mode with development dependencies:

```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
conda env create -f environment.yml
conda activate synaptipy
pip install -e ".[dev]"
```

## Getting Started

### Running the Application

After installation, run the application using one of these methods:

1. **Using the installed entry point:**
   ```bash
   synaptipy
   ```

2. **Using the Python module:**
   ```bash
   python -m Synaptipy
   ```

### User Interface Overview

The Synaptipy interface consists of three main tabs:

1. **Explorer Tab**: View and navigate through data files, with interactive plotting
2. **Analyser Tab**: Perform various analyses on the loaded data
3. **Exporter Tab**: Export data and results to different formats

## Loading Data

### Supported File Formats

File I/O is handled through the [Neo](https://neo.readthedocs.io) library
(Garcia et al., 2014, *Front. Neuroinformatics*, [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010)).
Synaptipy can load any recording format for which Neo provides a reader — this includes
whole-cell patch-clamp and intracellular recordings as well as extracellular, sharp-electrode,
and multi-channel data, provided the file format is supported. Confirmed formats include:

| Format | Extension(s) | Acquisition System |
|---|---|---|
| Axon Binary Format | `.abf` | Axon / Molecular Devices |
| WinWCP | `.wcp` | Strathclyde Electrophysiology Software |
| CED / Spike2 | `.smr`, `.smrx` | Cambridge Electronic Design |
| Igor Pro | `.ibw`, `.pxp` | WaveMetrics |
| Intan | `.rhd`, `.rhs` | Intan Technologies |
| Neurodata Without Borders | `.nwb` | NWB standard |
| BrainVision | `.vhdr` | Brain Products |
| European Data Format | `.edf` | EDF/EDF+ |
| Plexon | `.plx`, `.pl2` | Plexon |
| Open Ephys | `.continuous`, `.oebin` | Open Ephys |
| Tucker Davis Technologies | `.tev`, `.tbk` | TDT |
| Neuralynx | `.ncs`, `.nse`, `.nev` | Neuralynx |
| NeuroExplorer | `.nex` | NeuroExplorer |
| MATLAB | `.mat` | — |
| ASCII / CSV | `.txt`, `.csv`, `.tsv` | — |

For the full list of Neo-supported formats, see the
[Neo I/O documentation](https://neo.readthedocs.io/en/latest/iolist.html).

### Opening Files

1. Click "Open File..." in the menu or use the shortcut (Ctrl+O or Cmd+O)
2. Navigate to your data file and select it
3. The file will open in the Explorer tab
4. If other files with the same extension exist in the folder, they will be available for navigation

## Using the Explorer Tab

### Navigation Controls

- **Zoom**: Use the mouse wheel, or zoom buttons
- **Pan**: Click and drag in the plot area
- **Reset View**: Click the "Reset View" button to return to the initial view
- **Navigate Between Files**:
  - Use the "Previous File" and "Next File" buttons (if multiple files were found)
  - The current file index is shown between the navigation buttons

### Plot Options

- **Plot Mode**:
  - "Overlay All + Avg": Shows all trials with the average highlighted
  - "Cycle Single Trial": Shows one trial at a time with navigation controls
- **Channel Selection**: Choose which channel to view from the dropdown
- **Downsampling**: Enable/disable automatic downsampling for large datasets

## Using the Analyser Tab

All analysis sub-tabs share the following interface behaviours:

- **Free-form numeric input** — Number fields accept freely typed values;
  intermediate states (empty field, a lone minus sign, etc.) are tolerated while
  typing. Stepping uses adaptive decimal increments.
- **Interactive vs Manual mode** — Sub-tabs that have draggable plot regions
  (e.g. Rin, Tau, Capacitance) expose a mode selector. In **Interactive** mode
  the time-window spinboxes are read-only and driven by the plot regions.
  Switching to **Manual** mode unlocks all spinboxes for direct entry.
- **Conditional parameter visibility** — Parameters irrelevant to the current
  clamp mode or analysis type are hidden automatically.

### Input Resistance/Conductance Analysis

1. Select data for analysis from the Explorer tab
2. Switch to the Analyser tab and select the *Input Resistance* sub-tab
3. Choose analysis mode:
   - **Interactive Mode**: Drag the blue (baseline) and red (response) regions
     on the plot — the time-window spinboxes update in real time and become
     read-only
   - **Manual Mode**: Unlock the spinboxes and type time windows directly
4. Enable **Auto Detect Pulse** to let the analysis locate step edges
   automatically from the stimulus derivative. If auto-detection produces
   invalid windows (e.g. due to action potentials in the trace), the analysis
   falls back to the current spinbox values and updates the spinboxes
   to reflect the windows actually used
5. Results will be displayed showing:
   - Input resistance in MΩ
   - Conductance in μS
   - Voltage and current changes
6. Click "Save Result" to store the analysis for later export

### Baseline/RMP Analysis

1. Select a channel for analysis
2. Specify the time window for baseline calculation
3. Choose analysis method:
   - **Mean**: Calculates the average over the specified window
   - **Median**: Uses the median (more robust to outliers)
4. Results will display the baseline value and variability metrics
5. Save results as needed

### Optogenetic Synchronization

1. Load a recording that contains a TTL/digital stimulus channel alongside the
   signal channel
2. Switch to the *Optogenetic Synchronization* sub-tab in the Analyser
3. Select the TTL channel from the channel selector and set the **TTL Threshold**
   voltage used to binarise the stimulus signal
4. Choose the **Event Detection Type**:
   - **Spikes** — threshold-crossing AP detection; set the **Spike Threshold** (mV)
   - **Events (Threshold)** — prominence-based threshold event detection; set
     **Event Threshold**, **Event Direction**, and **Refractory Period**
   - **Events (Template)** — double-exponential template matching; set
     **Rise Tau**, **Decay Tau**, **Template Threshold** (SD), and
     **Template Direction**
   Only the parameters relevant to the selected detection mode are shown.
5. Set the **Response Window** (ms) to define how far after each TTL onset
   to search for an event
6. Results include optical latency, response probability, jitter, stimulus
   count, and event count
7. Click "Save Result" to store for later export

### Sag Ratio (Ih) Analysis

1. Load a recording containing a hyperpolarising current-step protocol
2. Switch to the *Sag Ratio (Ih)* sub-tab in the Analyser
3. Configure the measurement windows:
   - **Baseline Start / End** — resting membrane potential window (before the step)
   - **Peak Window Start / End** — early part of the step where the sag minimum occurs
   - **Steady-State Start / End** — late part of the step where voltage has plateaued
4. Adjust **Peak Smoothing (ms)** to control Savitzky–Golay smoothing of the
   peak detection (default 5 ms). Increase for noisy traces
5. Set **Rebound Window (ms)** to control how far after stimulus offset the
   rebound depolarisation is measured (default 100 ms)
6. Results include:
   - **sag_ratio** — ratio form (>1 indicates I_h sag, 1 = no sag)
   - **sag_percentage** — percentage of sag deflection
   - **v_peak**, **v_ss**, **v_baseline** — the three voltage levels
   - **rebound_depolarization** — post-stimulus rebound amplitude
7. The plot shows horizontal lines at V_baseline (blue), V_peak (magenta),
   and V_ss (red)

## Using the Exporter Tab

### Exporting to NWB

1. Load a recording in the Explorer tab
2. Navigate to the Exporter tab and select the "NWB Export" sub-tab
3. Specify the output file location
4. Fill in required metadata:
   - Session description
   - Experimenter information
   - Lab/institution details
5. Click "Export to NWB" and wait for the export to complete

### Exporting Analysis Results

1. Navigate to the "Analysis Results" sub-tab in the Exporter tab
2. Click "Refresh Results" to see all saved analysis results
3. Select which results to export
4. Specify the CSV output file location
5. Click "Export Selected" to create the CSV file

## Advanced Options

### Command Line Arguments

Synaptipy supports several command-line arguments:

```bash
synaptipy --help                          # Show help
synaptipy --dev                           # Run in development mode with detailed logging
synaptipy --log-dir /path/to/logs         # Specify custom log directory
synaptipy --verbose                       # Enable verbose output
synaptipy --file /path/to/data.abf        # Open a file directly on launch
```

### Logging and Debugging

Logs are stored in `~/.synaptipy/logs/` by default. In development mode, logs include detailed information for debugging.

To activate development mode:

```bash
# Using command line flag
synaptipy --dev

# Using environment variable
SYNAPTIPY_DEV_MODE=1 synaptipy
```

## Licensing

Synaptipy is released under the GNU Affero General Public License Version 3 (AGPL-3.0). This license ensures that the software remains free and open source, even when used as a service over a network.

Key aspects of the AGPL-3.0 license:

- You are free to use, modify, and distribute the software
- If you modify the software, you must release the modified source code
- If you use the software to provide a service over a network, you must make the complete source code available to users of that service
- Any derivative works must also be licensed under AGPL-3.0

For the full license text, see the LICENSE file in the root of the Synaptipy repository.

## Troubleshooting

### Common Issues

1. **File Format Not Recognized**:
   - Ensure the file is one of the supported formats
   - Check if you have the necessary dependencies for that format
   - Some formats require additional libraries not included by default

2. **GUI Display Issues**:
   - Ensure PySide6 is properly installed
   - Try updating your graphics drivers
   - If running remotely, ensure X forwarding is enabled

3. **Performance Problems with Large Files**:
   - Enable downsampling for visualization
   - Increase system RAM if possible
   - Consider splitting very large recordings into smaller files

4. **Export Failures**:
   - Check available disk space
   - Ensure write permissions for the target directory
   - For NWB exports, verify all required metadata is provided

### Getting Help

If you encounter issues not covered here:

1. Check the [GitHub Issues](https://github.com/anzalks/synaptipy/issues) for known problems
2. Create a new issue with details about your problem
3. Include the log files and error messages in your report
