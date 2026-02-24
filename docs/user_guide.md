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
  - PySide6 (Qt bindings for Python)
  - pyqtgraph (plotting library)
  - neo (data loading library)
  - numpy, scipy (numerical processing)
  - pynwb (NWB export functionality)
  - Other utility libraries

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

Synaptipy supports a wide variety of electrophysiology file formats through the neo library, including:

- Axon ABF files (.abf)
- Spike2 files (.smr, .smrx)
- NeuroExplorer files (.nex)
- Many others (see the [neo documentation](https://neo.readthedocs.io/en/latest/iolist.html) for the full list)

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

### Input Resistance/Conductance Analysis

1. Select data for analysis from the Explorer tab
2. Switch to the Analyser tab and select "Resistance/Conductance" sub-tab
3. Choose analysis mode:
   - **Interactive Mode**: Drag the baseline and response regions directly on the plot
   - **Manual Mode**: Enter specific time windows for baseline and response
4. Results will be displayed showing:
   - Input resistance in MΩ
   - Conductance in μS
   - Voltage and current changes
5. Click "Save Result" to store the analysis for later export

### Baseline/RMP Analysis

1. Select a channel for analysis
2. Specify the time window for baseline calculation
3. Choose analysis method:
   - **Mean**: Calculates the average over the specified window
   - **Median**: Uses the median (more robust to outliers)
4. Results will display the baseline value and variability metrics
5. Save results as needed

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
