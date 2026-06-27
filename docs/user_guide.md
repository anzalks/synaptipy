# Synaptipy User Guide

This document describes installation, configuration, and operation of Synaptipy for electrophysiology data visualization and analysis.

## Table of Contents

- [Installation](#installation)
 - [Requirements](#requirements)
 - [Standard Installation](#standard-installation)
 - [Developer Installation](#developer-installation)
- [Getting Started](#getting-started)
 - [Running the Application](#running-the-application)
 - [User Interface Overview](#user-interface-overview)
 - [Quick Start with Demo Data](#quick-start-with-demo-data)
- [Loading Data](#loading-data)
 - [Supported File Formats](#supported-file-formats)
 - [Opening Files](#opening-files)
- [Using the Explorer Tab](#using-the-explorer-tab)
 - [Navigation Controls](#navigation-controls)
 - [Plot Options](#plot-options)
- [Using the Analyser Tab](#using-the-analyser-tab)
 - [Input Resistance/Conductance Analysis](#input-resistanceconductance-analysis)
 - [Baseline/RMP Analysis](#baselinermp-analysis)
 - [Evoked Responses](#evoked-responses)
 - [Sag Ratio (Ih) Analysis](#sag-ratio-ih-analysis)
- [Using the Exporter Tab](#using-the-exporter-tab)
 - [Exporting to NWB](#exporting-to-nwb)
 - [Exporting Analysis Results](#exporting-analysis-results)
- [Advanced Options](#advanced-options)
 - [Command Line Arguments](#command-line-arguments)
 - [Logging and Debugging](#logging-and-debugging)
- [Generating Publication-Quality Figures](#generating-publication-quality-figures)
 - [Standard rcParams block](#standard-rcparams-block)
 - [L-shaped scale bar for electrophysiology traces](#l-shaped-scale-bar-for-electrophysiology-traces)
 - [Statistical transparency: strip plots instead of bare bar charts](#statistical-transparency-strip-plots-instead-of-bare-bar-charts)
 - [Saving figures for headless / CI environments](#saving-figures-for-headless--ci-environments)
- [Licensing](#licensing)
- [Troubleshooting](#troubleshooting)

## Installation

### System Requirements

**Operating Systems:**
- macOS 10.15 (Catalina) or later
- Windows 10/11 (64-bit)
- Linux (Ubuntu 20.04+, Fedora 35+, or equivalent)

**Hardware:**
- CPU: Multi-core processor (quad-core or better recommended for batch processing)
- RAM: 8 GB minimum, 16 GB recommended for large recordings (>500 MB)
- Display: 1920×1080 resolution or higher recommended for optimal interface layout
- GPU: Optional - Experimental opt-in OpenGL hardware acceleration available in Settings -> Performance; discrete GPU improves performance with high-density traces

**Software Requirements:**
- Python 3.10-3.12 (3.11 recommended)
- Anaconda or Miniconda (recommended) or pip

### Dependencies

Dependencies are automatically installed during package installation:
- [PySide6](https://doc.qt.io/qtforpython-6/) - Qt6 bindings for Python (GUI framework)
- [PyQtGraph](https://www.pyqtgraph.org) - plotting library (with experimental OpenGL support)
- [Neo](https://neo.readthedocs.io/en/latest/) - electrophysiology file I/O (Garcia et al., 2014, *Front. Neuroinformatics* [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010))
- [NumPy](https://numpy.org) / [SciPy](https://scipy.org) - numerical computation and signal processing
- [PyNWB](https://pynwb.readthedocs.io/en/stable/) - NWB data export (Rubel et al., 2022, *eLife* [doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362))

### Standard Installation

**WARNING: PySide6 must remain pinned to version 6.7.3 due to QTBUG-130070.**

Synaptipy is available both as a standalone application and as a Python package.

#### Default Install (PyPI)

The recommended approach for most users is to install Synaptipy directly via pip into a standard Python environment (Python 3.10-3.12).

```bash
pip install synaptipy
```

#### Conda Install

If you prefer using Anaconda or Miniconda, you can create a dedicated environment using our repository's environment file:

```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
conda env create -f environment.yml
conda activate synaptipy
pip install synaptipy
```

#### Standalone Application

Pre-built installers for macOS (`.dmg`), Windows (`.exe`), and Linux (`.AppImage`) are available on the [GitHub Releases page](https://github.com/anzalks/synaptipy/releases).
- **macOS**: Open the `.dmg` and drag Synaptipy to the Applications folder.
- **Windows**: Execute the `_Setup.exe` installer.
- **Linux**: Mark the `.AppImage` file executable (`chmod +x Synaptipy-*.AppImage`) and execute.

### Developer Installation

For developers, users who want to modify the application, or users who want the bleeding-edge main branch, install from source using Conda/Miniconda:

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

### Demo Data

A set of example recordings may be downloaded automatically for testing purposes.

1. Select **Help > Download Demo Data...** A banner appears below the menu bar.
2. Select **Download Demo Data**. The application downloads five example recordings
   from the public repository to `~/Documents/SynaptiPy_Demo/`:

   | File | Format | Description |
   |------|--------|-------------|
   | `2023_04_11_0018.abf` | ABF v2 | Whole-cell current-clamp, step protocol |
   | `2023_04_11_0019.abf` | ABF v2 | Whole-cell current-clamp, ramp protocol |
   | `2023_04_11_0021.abf` | ABF v2 | Voltage-clamp, IV curve |
   | `2023_04_11_0022.abf` | ABF v2 | Optogenetic stimulation protocol |
   | `240326_003.wcp` | WinWCP | WinWCP current-clamp recording |

3. Upon completion, the banner closes and the first ABF file is opened in
   the **Explorer Tab**.
4. The **Help > Download Demo Data...** menu item is disabled for the session
   (and on subsequent launches if files are already present).

**Note:** An internet connection is required. Files already present are not
re-downloaded. If a download is interrupted, partially written files are
removed.

## Loading Data

### Supported File Formats

File I/O is handled through the [Neo](https://neo.readthedocs.io/en/latest/) library
(Garcia et al., 2014, *Front. Neuroinformatics*, [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010)).
Synaptipy can load any recording format for which Neo provides a reader - this includes
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
| MATLAB | `.mat` | - |
| ASCII / CSV | `.txt`, `.csv`, `.tsv` | - |

For the full list of Neo-supported formats, see the
[Neo I/O documentation](https://neo.readthedocs.io/en/latest/iolist.html).

> **Note:** Allen Cell Types Database NWB files (NWB format 2.2–2.3) may
> produce `UserWarning: ignoring namespace` messages when opened. These are
> benign version-mismatch warnings from pynwb and do not affect data
> integrity. All voltage traces and stimulus waveforms are read correctly.

### Opening Files

1. Click "Open File..." in the menu or use the shortcut (Ctrl+O or Cmd+O)
2. Navigate to your data file and select it
3. The file will open in the Explorer tab
4. If other files with the same extension exist in the folder, they will be available
   for navigation with **Prev / Next File** - this applies whether you opened one
   file or many, and whether you used the menu, drag-and-drop, or
   **Help > Download Demo Data**

## Using the Explorer Tab

The Explorer tab has three resizable panels: the **Configuration panel** on the
left, the **Plot area** in the centre, and the **File / Analysis panel** on the
right. Drag the divider handles between the panels to resize them to suit your
screen. The default widths are 320 px (left), 800 px (centre), and 360 px
(right).

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
- **Performance**:
  - `_force_opaque_trials`: For datasets with >10 overlapping trials, you can enable "Force Opaque Trials" in Plot Preferences to improve rendering performance.
- **Cross-File Trial Averaging**:
  While in "Cycle Single Trial" mode, you can manually build a grand average
  from any combination of files and trials across the entire session:
  1. Use the **"Mark Current Trial"** button to add the currently
     displayed trial - including any active preprocessing transforms - to the
     pending selection set.
  2. Navigate freely between files (even files of different durations or
     sampling protocols) and continue marking trials. The pending selection
     accumulates until you add it to the Analysis Set.
  3. Click **"Add Marked Trials to Set"** to move the pending selections into
     the Analysis Set used by the Analyser tab. Marks are cleared automatically
     after adding, so clicking the button again without marking new trials
     produces a "No trials marked" notice rather than an "already added" warning.
  4. Enable **"Plot Selected Avg"** to overlay the grand average on the current
     recording view.

  **Sending to the Analyser:** Once you have built an Analysis Set in the
  Explorer, switch to the **Analyser** tab, select **"Cross-File Average"** as
  the data source, and choose any registered analysis routine. The Analyser
  will display faint per-trial traces alongside a bold grand average so that
  trial-to-trial variability is always visible. The header label shows the
  item count and file count (e.g. **"3 items (2 files)"**) so you always know
  exactly how many trials are included.

  **Shape-mismatch handling:** Because recordings from different files may have
  different durations, the accumulator uses
  `sum[:min_len] += trial[:min_len]` where
  `min_len = min(len(accumulator), len(trial))`. This silently truncates every
  trial to the shortest array in the selection before summing, so recordings
  with different lengths never cause a NumPy broadcast error. The resulting
  average is plotted against the time vector of the first trial added to the
  set.
- **Channel Selection**: Choose which channel to view from the dropdown
- **Channel Visibility**: Use the per-channel show/hide checkboxes to hide channels
  you are not interested in. When a channel is hidden its plot row collapses
  entirely - no blank white space remains in the canvas. Re-checking the box
  restores the row immediately.
- **Downsampling**: Enable/disable automatic downsampling for large datasets
- **Interactive Cursor**: Enable crosshair cursors to place persistent markers at
  specific (time, amplitude) coordinates on the trace. In **Delta Mode**, successive
  cursor placements report the difference (Δt, ΔV or ΔI) between points. Use
  **Undo** and **Clear** to manage placed cursors.
- **Trial Quality Metrics**: Displays series resistance (Rs), membrane capacitance
  (Cm), and signal-to-noise ratio (SNR) for the current trial, extracted from the
  recording metadata. Values update automatically during trial navigation.

## Using the Analyser Tab

The Analyser tab provides 17 built-in analysis routines organised into five
module tabs. Each sub-tab is auto-generated from registry metadata and provides
parameter widgets, an interactive plot, a results table, and plot overlays.

The five Analyser pillars are:

| Pillar | Registry name | What it covers |
|---|---|---|
| **Intrinsic Properties** | `passive_properties` | RMP, Rin, Tau, Sag Ratio, I-V Curve, Capacitance |
| **Spike Analysis** | `single_spike` | Spike detection, Phase-plane analysis |
| **Excitability** | `firing_dynamics` | F-I curve, Burst analysis, Spike Train Dynamics |
| **Synaptic Events** | `synaptic_events` | Event detection (threshold, template match, baseline-to-peak) |
| **Evoked Responses** | `evoked_responses` | Evoked Sync, Paired-Pulse Ratio, Stimulus Train (STP) |

All analysis sub-tabs share the following interface behaviours:

- **Preprocessing indicator** - A coloured banner appears at the top of the
 Analyser whenever preprocessing (baseline subtraction, digital filtering) is
 active. The banner lists each active step so the operator is always aware that
 the analysed signal differs from the raw acquisition.
- **Session count badge** - The "Add to Session" and "View Session" buttons
 display a count of accumulated results (e.g. "Add to Session (5)"). This
 provides an at-a-glance indication of session progress without opening the
 session summary.
- **Auto-save** - Session state is persisted automatically every five minutes
 to reduce the risk of data loss during prolonged recording sessions.
- **Free-form numeric input** - Number fields accept freely typed values;
 intermediate states (empty field, a lone minus sign, etc.) are tolerated while
 typing. Stepping uses adaptive decimal increments.
- **Parameter validation feedback** - Parameters outside their valid range are
 highlighted with a red border, providing immediate visual indication without
 blocking interaction.
- **Parameter tooltips** - All parameter widgets display descriptive tooltips
 drawn from the analysis registry metadata, describing what the parameter
 controls and its expected units.
- **Interactive vs Manual mode** - Sub-tabs that have draggable plot regions
 (e.g. Rin, Tau, Capacitance) expose a mode selector. In **Interactive** mode
 the time-window spinboxes are read-only and driven by the plot regions.
 Switching to **Manual** mode unlocks all spinboxes for direct entry.
- **Conditional parameter visibility** - Parameters irrelevant to the current
 clamp mode or analysis type are hidden automatically.
- **Statistical annotations on popup plots** - Popup scatter and curve-fit plots
 display quantitative annotations (R², regression slope, τ, event counts)
 directly on the figure for immediate reference.

### Input Resistance/Conductance Analysis

1. Select data for analysis from the Explorer tab
2. Switch to the Analyser tab and select the *Input Resistance* sub-tab
3. Choose analysis mode:
 - **Interactive Mode**: Drag the blue (baseline) and red (response) regions
 on the plot - the time-window spinboxes update in real time and become
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

### Evoked Responses

The **Evoked Responses** tab contains three analysis sub-tabs for stimulus-evoked
measurements.

#### Evoked Sync

1. Load a recording that contains a TTL/digital stimulus channel alongside the
 signal channel
2. Switch to the *Evoked Sync* sub-tab in the Analyser
3. Select the TTL channel from the channel selector and set the **TTL Threshold**
 voltage used to binarise the stimulus signal
4. Choose the **Event Detection Type**:
 - **Spikes** - threshold-crossing AP detection; set the **Spike Threshold** (mV)
 - **Events (Threshold)** - prominence-based threshold event detection; set
 **Event Threshold**, **Event Direction**, and **Refractory Period**
 - **Events (Template)** - matched-filter cross-correlation using a bi-exponential kernel; set
 **Rise Tau**, **Decay Tau**, **Template Threshold** (SD), and
 **Template Direction**.
 A bank of three kernels scaled at 1x, 2x, and 3x the user-specified decay
 constant is applied automatically to tolerate dendritic filtering; events
 are detected on the pointwise maximum of the three z-scored filtered traces.
 Only the parameters relevant to the selected detection mode are shown.
5. Set the **Response Window** (ms) to define how far after each TTL onset
 to search for an event
6. Results include optical latency, response probability, jitter, stimulus
 count, and event count
7. Click "Save Result" to store for later export

#### Paired-Pulse Ratio

1. Load a two-pulse paired-stimulus recording
2. Switch to the *Paired-Pulse Ratio* sub-tab
3. Configure the two stimulus times (**Pulse 1 Time**, **Pulse 2 Time**, in seconds)
4. Set the **Amplitude Measurement Window (ms)** used to measure R1 and R2
5. Enable **Subtract R1 Tail** to fit a mono- or bi-exponential decay to the
 R1 tail and subtract the residual baseline at the time of the second stimulus;
 this prevents contamination of R2 by the decaying R1 current
6. Results include R1 amplitude, R2 amplitude, PPR (R2/R1), and, when tail
 subtraction is enabled, the corrected R2 and corrected PPR
7. Click "Save Result" to store for later export

#### Stimulus Train (STP)

1. Load a multi-pulse train recording
2. Switch to the *Stimulus Train (STP)* sub-tab
3. Set **Number of Pulses** and the inter-stimulus interval (**ISI (ms)**)
4. Set the **First Pulse Time (s)** and the **Amplitude Window (ms)**
 used to measure each response amplitude
5. Results include per-pulse amplitudes, amplitudes normalised to R1, and an
 STP classification (facilitation or depression) based on whether the mean
 normalised amplitude over pulses 2-N is above or below 1.0
6. Click "Save Result" to store for later export

### Sag Ratio (Ih) Analysis

1. Load a recording containing a hyperpolarising current-step protocol
2. Switch to the *Sag Ratio (Ih)* sub-tab in the Analyser
3. Configure the measurement windows:
 - **Baseline Start / End** - resting membrane potential window (before the step)
 - **Peak Window Start / End** - early part of the step where the sag minimum occurs
 - **Steady-State Start / End** - late part of the step where voltage has plateaued
4. Adjust **Peak Smoothing (ms)** to control Savitzky-Golay smoothing of the
 peak detection (default 5 ms). Increase for noisy traces
5. Set **Rebound Window (ms)** to control how far after stimulus offset the
 rebound depolarisation is measured (default 100 ms)
6. Results include:
 - **sag_ratio** - ratio form (>1 indicates I_h sag, 1 = no sag)
 - **sag_percentage** - percentage of sag deflection
 - **v_peak**, **v_ss**, **v_baseline** - the three voltage levels
 - **rebound_depolarization** - post-stimulus rebound amplitude
7. The plot shows horizontal lines at V_baseline (blue), V_peak (magenta),
 and V_ss (red)

### Additional Analysis Modules

The following analysis modules are also available in the Analyser tab.
All parameters are auto-generated from registry metadata and include tooltips,
valid ranges, and conditional visibility based on clamp mode.

**Intrinsic Properties tab:**
- **Tau (Time Constant)** - Single or bi-exponential fit to the voltage decay
  after a current step. Returns tau in ms with an overlay of the fitted curve.
  A **cyan trace overlay** automatically highlights the 5 ms baseline window
  immediately before the step onset for at-a-glance verification.
- **I-V Curve** - Current-voltage relationship across multi-trial step protocols.
  Fits aggregate Rin from the slope and opens a popup I-V scatter plot.
- **Capacitance** - Membrane capacitance from Tau/Rin (current-clamp) or
  capacitive-transient integration (voltage-clamp).  In current-clamp mode the
  series resistance ($R_s$) is automatically estimated from the fast voltage
  artifact at step onset (0.1 ms window) and used in the corrected formula
  $C_m = \tau / (R_{\text{in}} - R_s)$.

**Spike Analysis tab:**
- **Phase Plane** - dV/dt vs. voltage trajectory for AP initiation dynamics.
  Detects threshold via kink-slope criterion; reports mean threshold voltage
  and maximum dV/dt. Opens a popup phase-plane plot.

**Excitability tab:**
- **Excitability (F-I Curve)** - Multi-trial rheobase, F-I slope, maximum
  firing frequency, and spike-frequency adaptation index (normalized ISI-difference
  method). Opens a popup F-I scatter plot. Requires multi-trial recordings.
- **Burst Analysis** - Max-ISI burst detection; reports burst count, mean
  spikes per burst, mean burst duration, and intra-burst frequency.
- **Spike Train Dynamics** - ISI statistics: mean ISI, coefficient of variation
  (CV), local variation (LV), and CV2. Opens a popup ISI plot.

**Synaptic Events tab:**
- **Event Detection (Template Match)** - Matched-filter cross-correlation using a
  bi-exponential kernel for miniature event detection. A fixed bank of three
  kernels at 1x, 2x, and 3x the user-specified decay constant is convolved with
  the trace; events are detected on the pointwise maximum of the three z-scored
  outputs, providing automatic tolerance for dendritic cable filtering.
  Configurable parameters: rise tau, decay tau, threshold in SD, and direction.
- **Event Detection (Baseline Peak)** - Direct baseline-to-peak amplitude
  detection with kinetics estimation for evoked or spontaneous events.

### Visual Validation Overlays

Several analysis sub-tabs draw semi-transparent overlays directly on top of the
raw trace to assist with visual validation of the analysis windows and fitted
curves. These overlays are rendered entirely in pyqtgraph and do not affect the
underlying data.

| Overlay type | Where it appears | Default colour |
|---|---|---|
| **Trace overlay** (cyan) | Baseline region highlighted before the stimulus | Cyan (#00cfff) |
| **Event fit overlay** (amber) | Bi-exponential or mono-exponential decay fits on the P1 tail in PPR | Amber (#ff9900) |

**Customising overlay appearance:**

1. Open **Edit > Plot Preferences** (or the settings toolbar button).
2. Switch to the **Trace Overlay** tab to adjust the highlight colour, line
   width, and opacity with a slider.
3. Switch to the **Event Fit Overlay** tab to adjust the fitted-curve colour,
   width, and opacity.

All overlay settings are persisted via QSettings and restored across sessions.

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

:::{note}
The NWB exporter writes:

- Voltage/current traces as `CurrentClampSeries` / `VoltageClampSeries` with SI
  unit conversion
- Electrode metadata and session information
- **Stimulus waveforms** via a 3-step fallback: (1) raw digitized command
  waveform from the acquisition file; (2) synthetic step waveform reconstructed
  from ABF epoch metadata (description notes "Synthetic stimulus array
  reconstructed from protocol metadata."); (3) `stimulus=None` with a warning
  appended to the response trace description when no waveform is available
- **IntracellularRecordingsTable** linking each response to its electrode and
  stimulus series
- **SimultaneousRecordingsTable** and **SequentialRecordingsTable** for NWB 2.x
  icephys sweep grouping
- **ProcessingModule** containing discrete event arrays (spike times, synaptic
  event times) produced by the batch engine, stored as HDMF `DynamicTable`
  objects

See [NWB Export Mapping](nwb_mapping.md) for full container mapping details.
:::

### Exporting Analysis Results

1. Navigate to the "Analysis Results" sub-tab in the Exporter tab
2. Click "Refresh Results" to see all saved analysis results
3. Select which results to export
4. Specify the CSV output file location.
5. Click "Export Selected" to create the output.
 - **Note**: If your exported results contain *multiple different types of analysis* (e.g. some RMP results and some Spike Detection results), Synaptipy will automatically generate a **ZIP Archive** containing separate, perfectly cleanly formatted CSV files for each unique analysis type, fully supporting custom plugin columns!

#### GraphPad Prism Export

For direct import into GraphPad Prism, use `CSVExporter.export_to_prism_format`
from the Python API.  The method writes a **grouped-column** CSV where each
column represents one experimental condition and each row is an individual
replicate observation.  Columns of unequal length are padded with empty cells
so Prism can compute group statistics without warnings.

```python
from pathlib import Path
from synaptipy.infrastructure.exporters.csv_exporter import CSVExporter

exporter = CSVExporter()
exporter.export_to_prism_format(
    results,                      # list of result dicts from BatchAnalysisEngine
    Path("my_experiment.csv"),    # base path; actual file: my_experiment_prism_rin_mohm.csv
    metric="rin_mohm",            # which scalar metric to export
    group_by_key="Condition",     # key in each result row that labels the group
)
```

The output CSV columns are the unique group labels; each value is rounded to
six significant figures.  A companion `_provenance.json` is written alongside
the CSV recording the Synaptipy version, timestamp, and export parameters.

### Exporting Plots

Every Explorer and Analyser sub-tab includes a **Save Plot** button. The export
dialog provides three predefined presets for common publication workflows:

| Preset | Format | Resolution | Typical use |
|--------|--------|------------|-------------|
| Journal Quality | PDF (vector) | 300 DPI | Manuscript figure submission |
| Presentation | PNG (raster) | 150 DPI | Slide decks and posters |
| Web | PNG (raster) | 72 DPI | Online supplementary material |

Select **Custom** to choose format (PNG, JPG, SVG, PDF) and DPI independently.
Vector formats (SVG, PDF) retain editable text elements suitable for post-hoc
annotation in illustration software.

## Advanced Options

### Reproducibility: How GUI Adjustments Serialize to the Batch Engine

A key design goal of Synaptipy is that any parameter tweak made interactively
in the GUI produces an identical result when replayed by the headless
`BatchAnalysisEngine`.  This section explains the serialization pathway.

#### Parameter capture

Every widget in an analysis tab (spin-boxes, check-boxes, combo-boxes,
draggable region handles) corresponds to one entry in the tab's
`ui_params` list, which is declared alongside the
`@AnalysisRegistry.register(...)` decorator for that analysis function.  The
parameter name, type, and current value are stored together.

When the user clicks **Run Analysis**, the tab calls
`_gather_analysis_parameters()`, which iterates over every `ui_params` entry
and reads the current widget value.  The result is a plain Python dictionary:

```python
# Example parameter dict for the Tau analysis tab
params = {
    "stim_start_time": 0.200,   # s  (from a QDoubleSpinBox)
    "fit_duration":    0.300,   # s
    "model":           "mono",  # (from a QComboBox)
    "artifact_blanking_ms": 0.5,
}
```

#### Interactive region handles

Draggable baseline or fit windows rendered as `pyqtgraph.LinearRegionItem`
objects are two-way linked to the corresponding spin-box pair via Qt signals.
Dragging the region emits `sigRegionChangeFinished`, which updates the
spin-box values.  Conversely, typing in a spin-box moves the region.
At the moment of analysis, the spin-box values - not the graphical object
positions - are read into the parameter dictionary.  The graphical object is
therefore only a visual convenience; the canonical parameter value is always
the spin-box number.

#### SessionManager serialization

`SessionManager` (a singleton) stores:

```python
# Simplified SessionManager state
{
    "active_analysis": "tau_analysis",
    "preprocessing_settings": { "lowpass_hz": 2000 },
    "analysis_params": {
        "tau_analysis": {
            "stim_start_time": 0.200,
            "fit_duration":    0.300,
            "model":           "mono",
        },
        ...
    }
}
```

These dictionaries are serialized to JSON when the user saves a session file
(**File - Save Session**).  Loading a session file restores them, so every
tab shows the same parameter values as when the session was saved.

#### Batch engine replay

The `BatchAnalysisEngine` accepts a list of file paths plus a parameter
dictionary in exactly the same format produced by `_gather_analysis_parameters()`:

```python
from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
import synaptipy.core.analysis  # populates the registry

engine = BatchAnalysisEngine()

pipeline = [
    {
        "analysis": "tau_analysis",
        "scope": "all_trials",
        "params": {
            "stim_start_time": 0.200,
            "fit_duration":    0.300,
            "model":           "mono",
            "artifact_blanking_ms": 0.5,
        },
    }
]

results = engine.run_batch(
    files=["cell_01.abf", "cell_02.abf"],
    pipeline_config=pipeline,
)
```

Because both paths invoke the same registered wrapper function with the same
parameter dictionary, the batch result is mathematically identical to the
GUI result - provided the same preprocessing pipeline is applied.

#### Preprocessing pipeline

Preprocessing settings (filters, baseline subtraction) are stored in
`SessionManager().preprocessing_settings` as a nested dictionary and can be
passed to the engine via the `preprocessing_settings` argument of
`BatchAnalysisEngine.run()`.  The engine applies the identical
`ProcessingPipeline` that the GUI uses, ensuring the batch trace matches the
trace the user visually validated.

### Preferences

Open **Edit > Preferences** (or **Synaptipy > Preferences** on macOS) to access the application settings:

| Setting | Description |
|---------|-------------|
| **Scroll Behavior** | Choose Natural, Inverted, or System scroll direction for plots. |
| **Appearance** | Switch between Light, Dark, or System color theme. **Light** and **Dark** use the cross-platform Fusion style with an explicit color palette. **System** restores the OS-native style and palette exactly as it was at application startup. Switching between all three modes is fully reversible at runtime with no restart required. |
| **Enable Custom Plugins** | When checked, Synaptipy loads Python plugins from `~/.synaptipy/plugins/` and `examples/plugins/`. See below for the hot-reload mechanism. |

### Version Checking

The application performs a version check at startup. If a newer release is
detected on [GitHub Releases](https://github.com/anzalks/synaptipy/releases),
a yellow banner appears below the menu bar displaying the version number and a
link to release notes. The banner may be dismissed.

A manual check may be initiated via **Help > Check for Updates...**. Status
bar messages indicate:

- *"Checking for updates..."* - check in progress.
- *"You are on the latest version."* - no newer release detected.
- Yellow banner - newer version available.

The check consists of a single request to the GitHub Releases API
(`api.github.com`). If the system is offline or behind a firewall, the check
fails silently.

#### Enable Custom Plugins - Hot-Reload Mechanism

Toggling "Enable Custom Plugins" does **not** require an application restart.
When the checkbox state changes and the dialog is accepted, Synaptipy:

1. Calls `PluginManager.reload_plugins()`, which first calls
   `AnalysisRegistry.unregister_plugins()` to purge every plugin-sourced
   entry (those flagged `source="plugin"`) from the registry while leaving
   all built-in analyses intact.
2. If the setting is now **enabled**, re-executes every `.py` file discovered
   in `examples/plugins/` (bundled examples) then `~/.synaptipy/plugins/`
   (user additions). Each file's `@AnalysisRegistry.register(...)` decorator
   re-runs and re-populates the registry.
3. Calls `AnalyserTab.rebuild_analysis_tabs()` to destroy the existing
   sub-tab widgets and regenerate them from the updated registry - all within
   the running process.

The net effect is that plugin tabs appear or disappear immediately without
reloading the application. A syntax error or import failure in a single plugin
is caught and logged; remaining plugins still load normally.

> **Tip:** If you install a new plugin file while Synaptipy is running, open
> Preferences and toggle "Enable Custom Plugins" off then on to force an
> immediate reload of all plugins from disk.

#### Included Example Plugins

Synaptipy ships five ready-to-run example plugins in `examples/plugins/`.
With **Enable Custom Plugins** active they load automatically:

| Plugin file | Analyser tab label | What it measures |
|-------------|--------------------|------------------|
| `synaptic_charge.py` | Synaptic Charge (AUC) | Area under a postsynaptic current trace (total charge in pC); shaded fill + peak star overlay |
| `opto_jitter.py` | Opto Latency Jitter | Trial-to-trial variability in spike latency after an optogenetic TTL pulse |
| `ap_repolarization.py` | AP Repolarization Rate | Maximum rate of membrane-potential decline (dV/dt minimum) during an action potential |
| `miniml_integration.py` | miniML Events | Deep-learning miniature event detection via [miniML](https://github.com/delvendahl/miniML); requires additional setup (see [extending_synaptipy.md](extending_synaptipy.md#12-deep-learning--third-party-integrations-eg-miniml)) |
| `spike_interface_integration.py` | SpikeInterface Spikes | Spike detection via [SpikeInterface](https://spikeinterface.readthedocs.io/); requires `pip install spikeinterface` (see [extending_synaptipy.md](extending_synaptipy.md#11-spikeinterface-integration-plugin)) |

Copy any of these files to `~/.synaptipy/plugins/` and edit your copy to create
a personalised variant without modifying the Synaptipy installation.

### Command Line Arguments

Synaptipy supports several command-line arguments:

```bash
synaptipy --help # Show help
synaptipy --dev # Run in development mode with detailed logging
synaptipy --log-dir /path/to/logs # Specify custom log directory
synaptipy --verbose # Enable verbose output
synaptipy --file /path/to/data.abf # Open a file directly on launch
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

## Generating Publication-Quality Figures

Synaptipy's programmatic API is designed for direct use in manuscript
workflows. The code patterns below are used in every example in the
`examples/` directory and can be copy-pasted into your own analysis scripts.

### Standard `rcParams` block

Place this block at the top of any script or notebook cell, before creating
any figure object. It sets sans-serif typography, 8 pt fonts appropriate for
single-column journal figures, and removes the top and right spines:

```python
import matplotlib
matplotlib.rcParams.update({
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
    "figure.dpi": 150,      # screen preview
    "savefig.dpi": 300,     # output files
    "pdf.fonttype": 42,     # editable text in Illustrator / Inkscape
    "ps.fonttype": 42,
})
```

Figure sizes follow single-column (3.5 in) or double-column (7.0 in) widths
typical for *Nature*, *eLife*, and *Journal of Neuroscience* styles:

```python
fig, ax = plt.subplots(figsize=(3.5, 2.5))   # single-column
fig, ax = plt.subplots(figsize=(7.0, 3.0))   # double-column
```

### L-shaped scale bar for electrophysiology traces

Raw electrophysiology traces should omit conventional axes ticks and instead
carry an explicit L-shaped scale bar showing the time and amplitude scales.
This matches the standard used in most patch-clamp publications.

```python
# Remove axes decorations entirely
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_xticks([])
ax.set_yticks([])

# Draw the L-bar using plot() and text()
# Adjust x0, y0, sb_dx, sb_dy to your data range
sb_x0 = time[-1] - 0.15      # right-aligned, 15 % from right edge
sb_y0 = data.min() + 0.05 * (data.max() - data.min())
sb_dx = 0.100                 # 100 ms horizontal arm
sb_dy = 10.0                  # 10 mV vertical arm

ax.plot([sb_x0, sb_x0 + sb_dx], [sb_y0, sb_y0],
        color="k", linewidth=1.5, solid_capstyle="butt", clip_on=False)
ax.plot([sb_x0, sb_x0], [sb_y0, sb_y0 + sb_dy],
        color="k", linewidth=1.5, solid_capstyle="butt", clip_on=False)
ax.text(sb_x0 + sb_dx / 2, sb_y0 - 1.2, "100 ms",
        ha="center", va="top", fontsize=7)
ax.text(sb_x0 - 0.01, sb_y0 + sb_dy / 2, "10 mV",
        ha="right", va="center", fontsize=7, rotation=90)
```

### Statistical transparency: strip plots instead of bare bar charts

Rather than plotting only the group mean, overlay individual data points
with horizontal jitter so reviewers can assess the underlying distribution:

```python
import numpy as np

rng = np.random.default_rng(0)
x_pos = np.arange(len(groups))

fig, ax = plt.subplots(figsize=(3.5, 2.5))
for i, (label, values) in enumerate(groups.items()):
    jitter = rng.uniform(-0.15, 0.15, size=len(values))
    ax.scatter(x_pos[i] + jitter, values,
               s=12, color="#4393c3", alpha=0.7, linewidths=0, zorder=3)

# Mean bar with SEM error bar
means = [np.mean(v) for v in groups.values()]
sems  = [np.std(v, ddof=1) / np.sqrt(len(v)) for v in groups.values()]
ax.bar(x_pos, means, width=0.45,
       color="#d1e5f0", edgecolor="#4393c3", linewidth=0.8, zorder=2)
ax.errorbar(x_pos, means, yerr=sems, fmt="none",
            ecolor="#2166ac", elinewidth=1.0, capsize=2, zorder=4)
ax.set_xticks(x_pos)
ax.set_xticklabels(list(groups.keys()), rotation=40, ha="right")
```

### Saving figures for headless / CI environments

Always save figures to disk and close them explicitly. Never call `plt.show()`
in batch scripts or CI pipelines -- it blocks execution in headless
environments:

```python
plt.savefig("figure_01.pdf", bbox_inches="tight")
plt.savefig("figure_01.png", bbox_inches="tight")
plt.close("all")
```

The PDF uses `pdf.fonttype=42` (set in the `rcParams` block above), which
embeds fonts as TrueType outlines. This makes text fully editable in Adobe
Illustrator, Inkscape, and most journal submission portals.

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

### Biological Troubleshooting

These scenarios describe what analysis outputs mean in terms of patch-clamp
physiology, not just software errors.

**"Tau returns NaN after a current step"**

A failed exponential fit almost always means one of:
1. The patch is leaky - the cell membrane has not sealed properly (seal
   resistance below ~1 GOhm), so the voltage decays non-exponentially.
2. The cell has not fully charged - the current step is too short for the
   membrane RC to reach steady-state. Increase the step duration (>5 x tau,
   typically 200-500 ms for neurons).
3. The fit window includes the stimulus artifact - check that
   **Baseline End** is placed after the artifact but before the voltage
   plateau, and that **Fit Start** skips the initial capacitive transient.
4. Access resistance is too high (>30 MOhm for whole-cell) - the series
   resistance is limiting current delivery, making the apparent decay
   multi-exponential. Compensate or replace the pipette.

**"Input resistance (Rin) is abnormally low (< 50 MOhm for a cortical neuron)"**

- The holding current is wrong: the cell may be partially clamped at an
  unphysiological potential. Check your resting Vm before stepping.
- Shunt conductance: an imperfect seal or damaged membrane adds parallel
  conductance that reduces apparent Rin. Check seal resistance.
- The step amplitude is too large - nonlinear I-V conductances (Ih, inward
  rectifier K+) are activated. Use small hyperpolarising steps (5-20 pA).

**"Spike threshold is reported as NaN"**

The d2V/dt2 AP onset detector returns NaN when:
- The dV/dt at the detected threshold point is outside the biological range
  (> 300 V/s indicates a digital artifact; < 2 V/s indicates a noise
  crossing rather than a true AP upstroke).
- The rising phase of the AP is shorter than 0.2 ms (photo-electric artifact
  or electrical transient picked up from the stimulator).
- Increase filtering (Savitzky-Golay smoothing) or reduce the onset lookback
  window if thresholds are unreliable on noisy recordings.

**"Synaptic charge (AUC) is negative or much larger than expected"**

- Check that the baseline method is set to **Pre-Window (Local 10 ms)**.
  A global baseline corrupts the measurement when holding current drifts
  during long recording epochs.
- Verify the search window does not include the stimulus artifact. Set
  **Search Window Start** at least 2 ms after the stimulus.
- If the cell is in voltage-clamp, check the polarity: PSCs are downward
  (negative) in the standard convention. Use **Detection Method: Negative Peak**
  for IPSCs or **Absolute Peak** when sign is uncertain.

**"Opto-jitter is impossibly short (< 1 ms)"**

This almost always means the photo-electric artifact from the LED or laser
shutter is being detected as a spike. Set the **Artifact Blanking Window**
to at least 1-2 ms. Genuine monosynaptic latencies are 2-5 ms for direct
ChR2-expressing targets; disynaptic latencies are 8-15 ms.

**"Rs QC warning in batch output: Series resistance destabilized"**

The Rs warning appears when the series resistance increased by more than
20% (default) compared to the first sweep. This typically means:
- The pipette tip clogged partially during the recording.
- The gigaohm seal broke down gradually.
Sweeps flagged with `rs_qc_warning` should be excluded from analysis. The
default threshold (20%) can be adjusted via the `rs_tolerance` parameter
in `BatchAnalysisEngine.run_batch()`.

---

## Analysis Parameter Reference

The table below explains every common parameter in biological terms so you
can choose values that match your experimental design.

| Parameter | Unit | Biological meaning | Typical range |
|---|---|---|---|
| `prominence` | mV or pA | Minimum height of an event above the local baseline. Prevents noise peaks from being counted as real spikes or synaptic events. | 5-30 mV (spikes); 5-50 pA (PSCs) |
| `width` | ms | Minimum duration of an event at half-maximum. Excludes electrical transients that are far narrower than real APs (0.5-2 ms) or PSCs (2-20 ms). | 0.3-1.0 ms (spikes); 2-10 ms (PSCs) |
| `threshold` | mV or pA | Voltage (or current) level a trace must cross to be counted as an event. Set just above the noise floor. | -20 mV (spikes); 3 x noise RMS (PSCs) |
| `refractory_period` | ms | Minimum inter-event interval. Prevents double-counting the same AP or the same PSC. Should be slightly shorter than the fastest real inter-event interval in your data. | 2-5 ms (spikes); 5-20 ms (PSCs) |
| `baseline_window` | ms or s | Duration of the pre-event window used to measure the resting level. Shorter windows (10 ms) track slow holding-current drift more accurately than long windows. | 5-20 ms |
| `onset_lookback` | ms | How far before each spike peak to search for the AP onset (threshold crossing). Should span the full AP upstroke plus noise margin. | 2-5 ms |
| `smoothing` | ms | Width of the Savitzky-Golay smoothing kernel applied to the trace before differentiation (dV/dt). Increase for noisy recordings; decrease to preserve fast upstroke kinetics. | 0.1-0.5 ms |
| `step_onset_time` | s | Time of the voltage or current step command. Auto-detected from the stimulus derivative; override if auto-detection fails. | Protocol-dependent |
| `voltage_step_mv` | mV | Amplitude of the VC command step. Required for Rs and Cm calculation. Use the actual command amplitude, not the measured response. | -10 to -5 mV (typical access resistance protocol) |
| `blanking_window` | ms | Duration after a TTL stimulus to ignore. Prevents the photo-electric artifact from the LED from being misclassified as a spike. | 1-2 ms |
| `rs_tolerance` | fraction | Maximum fractional increase in series resistance before a sweep is flagged as unstable. 0.20 = flag sweeps where Rs has increased by >20% compared to Sweep 1. | 0.10-0.30 |

### Getting Help

If you encounter issues not covered here:

1. Check the [GitHub Issues](https://github.com/anzalks/synaptipy/issues) for known problems
2. Create a new issue with details about your problem
3. Include the log files and error messages in your report
