# Synaptipy

[![PyPI](https://img.shields.io/pypi/v/Synaptipy?color=blue&label=PyPI)](https://pypi.org/project/Synaptipy/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/anzalks/synaptipy)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![CI](https://github.com/anzalks/synaptipy/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/anzalks/synaptipy/actions/workflows/test.yml)
[![Core Test Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/anzalks/synaptipy/python-coverage-comment-action-data/endpoint.json)](https://github.com/anzalks/synaptipy/actions/workflows/test.yml)
[![Docs](https://github.com/anzalks/synaptipy/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/anzalks/synaptipy/actions/workflows/docs.yml)
[![Documentation Status](https://readthedocs.org/projects/synaptipy/badge/?version=latest)](https://synaptipy.readthedocs.io/en/latest/)
[![Qt6](https://img.shields.io/badge/Qt-6-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/imports-isort-%231674b1?labelColor=ef8336)](https://pycqa.github.io/isort/)
[![Lint: flake8](https://img.shields.io/badge/lint-flake8-blue)](https://flake8.pycqa.org/)
[![Collaborators Welcome](https://img.shields.io/badge/collaborators-welcome-brightgreen?logo=github&logoColor=white)](https://github.com/anzalks/synaptipy)
[![Release](https://img.shields.io/github/v/release/anzalks/synaptipy?include_prereleases&label=release&color=orange)](https://github.com/anzalks/synaptipy/releases)

**Open-source electrophysiology analysis for wet-lab neuroscientists - no coding required.**

Full documentation: [synaptipy.readthedocs.io](https://synaptipy.readthedocs.io/en/latest/)

Synaptipy is a cross-platform desktop application that turns raw patch-clamp recordings into publication-ready measurements. Load any `.abf`, `.wcp`, `.nwb`, or [other supported file](#supported-file-formats), and within seconds you can extract resting membrane potential, input resistance, action-potential features, synaptic event kinetics, and more - all from a point-and-click GUI with no Python knowledge required.

When you are ready to scale up, the same analysis pipeline runs automatically across hundreds of files in batch mode, and all results export to CSV or NWB for downstream use in Excel, R, or Python.

---

## Quick Start - from install to first result in 3 steps

### Step 1: Download and install

**No Python needed.** Download the pre-compiled application for your operating system from the [Releases page](https://github.com/anzalks/Synaptipy/releases):

- **Windows** - run `Synaptipy_Setup_v0.1.1.exe`
- **macOS** - open `Synaptipy_v0.1.1.dmg` and drag to Applications
- **Linux** - `chmod +x Synaptipy-v0.1.1-x86_64.AppImage` then run it

### Step 2: Load your recording

Launch Synaptipy and drag-and-drop your recording file (`.abf`, `.wcp`, `.nwb`, or any [supported format](#supported-file-formats)) into the **Explorer** tab. Traces render immediately.

### Step 3: Analyse

Click the **Analyser** tab. Select a channel, pick an analysis (e.g. **Input Resistance** or **Spike Detection**), and click **Run**. Results appear in the table below the plot and can be exported to CSV with one click.

---

## What can Synaptipy measure?

### Intrinsic membrane properties (passive tab)
- **Resting membrane potential (RMP)** - mean or median over a quiescent window
- **Input resistance (Rin)** - automatically detects the current-step edges; falls back gracefully if auto-detection fails
- **Membrane time constant (Tau)** - single-exponential fit to the voltage decay after a current step
- **Sag ratio (Ih)** - peak-to-steady-state hyperpolarisation ratio; includes rebound depolarisation
- **I-V curve** - current-voltage relationship across a multi-trial step protocol
- **Membrane capacitance** - from Tau/Rin in current-clamp or from capacitive-transient integration in voltage-clamp

### Action potential features (spike analysis tab)
- **Spike detection** - threshold-crossing detection with refractory-period filtering
- **Per-spike features** - amplitude, half-width, rise time, decay time, threshold voltage, fAHP, mAHP
- **Phase-plane analysis** - dV/dt vs. voltage trajectory; threshold voltage via kink-slope criterion

### Excitability (excitability tab)
- **F-I curve** - rheobase, slope, maximum firing frequency, and spike-frequency adaptation ratio
- **Burst analysis** - burst count, spikes per burst, burst duration, intra-burst frequency
- **Spike-train statistics** - mean ISI, CV, local variation (LV), CV2

### Synaptic events (synaptic events tab)
- **Threshold detection** - prominence-based, baseline-drift-tolerant; click to accept/reject events
- **Template matching** - double-exponential deconvolution for miniature events
- **Baseline-to-peak** - amplitude and kinetics for evoked or spontaneous events

### Optogenetics (opto tab)
- **TTL correlation** - latency, response probability, and jitter between optical stimulus and response

---

## Batch processing

Repeat any analysis across all files in a folder automatically:

1. Open the **Batch** tab, add your files, configure the pipeline
2. Click **Run** - the GUI stays responsive while analysis runs in the background
3. Export the complete results table to CSV

```python
# Or run headlessly from a script:
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from pathlib import Path

engine = BatchAnalysisEngine()
results = engine.run_batch(
    [Path("recording.abf")],
    [{"analysis": "spike_detection", "scope": "all_trials",
      "params": {"threshold": -20.0, "refractory_ms": 2.0}}],
)
print(results)
```

---

## FAIR data compliance - NWB export

Synaptipy exports both raw traces and analysis results to the
[Neurodata Without Borders (NWB)](https://www.nwb.org) format, ensuring your
data meets FAIR (Findable, Accessible, Interoperable, Reusable) requirements
for journal submission and data sharing.

---

## Visual validation

Every analysis result can be inspected visually before export:

- OpenGL-accelerated trace rendering (handles multi-million-sample recordings at interactive frame rates)
- Interactive zooming, panning, and per-channel amplitude scaling
- Grand-average overlay across any combination of files and trials
- Popup plots for I-V curves, F-I curves, and phase planes

---

## Supported file formats

File I/O is handled through the [Neo](https://neo.readthedocs.io) library:

| Format | Extension(s) | Acquisition system |
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

Any format supported by Neo but not listed above can be added via the `IODict` in the infrastructure layer.

---

## Installing from source (developers and power users)

If you want to use Synaptipy programmatically, write custom plugins, or contribute to development, install from source:

```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
conda env create -f environment.yml
conda activate synaptipy
pip install -e ".[dev]"
python -m pytest        # verify installation
synaptipy               # launch the GUI
```

---

## Documentation

- [Full documentation (stable)](https://synaptipy.readthedocs.io/en/latest/)
- [Quick-start tutorial](https://synaptipy.readthedocs.io/en/latest/tutorial/index.html)
- [API reference](https://synaptipy.readthedocs.io/en/latest/api_reference.html)
- [Developer guide](https://synaptipy.readthedocs.io/en/latest/developer_guide.html)

---

## Contributing

Contributions are welcome - whether adding a new analysis module, supporting an additional file format, or improving documentation. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [developer guide](https://synaptipy.readthedocs.io/en/latest/developer_guide.html) for project conventions and the contribution workflow.

---

## For developers - architecture and plugin system

<details>
<summary>Click to expand technical details</summary>

### Architecture overview

Synaptipy follows a strict separation-of-concerns design:

- **Core layer** - pure Python analysis logic, fully decoupled from the GUI and independently testable
- **Application layer** - PySide6 (Qt6) user interface and plugin manager
- **Infrastructure layer** - file I/O via Neo and PyNWB; NWB export

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.10 - 3.12 |
| GUI Framework | PySide6 | 6.7.3 (pinned) |
| Plotting Engine | PyQtGraph | 0.13.0+ |
| Electrophysiology I/O | Neo | 0.14.0+ |
| NWB Export | PyNWB | 3.1.0+ |
| Numerical Computation | SciPy / NumPy | 1.13.0+ / 2.0.0+ |

### Analysis registry pattern

New analysis functions are registered with the `@AnalysisRegistry.register` decorator. The `ui_params` list drives the GUI parameter panel automatically, and the same parameters serialise directly to the batch engine - there is no separate configuration step.

```python
@AnalysisRegistry.register(
    name="my_analysis",
    ui_params=[{"name": "threshold", "type": "float", "default": -20.0}],
    plots=["overlay"],
)
def my_analysis_wrapper(data, time, fs, params):
    ...
    return {"module_used": "my_analysis", "metrics": {"threshold_mv": threshold}}
```

### Plugin interface

Any Python script placed in `~/.synaptipy/plugins/` that uses `@AnalysisRegistry.register` is automatically discovered at startup and available in both the interactive analyser and batch pipeline.

A fully documented template lives at `src/Synaptipy/templates/analysis_template.py`.

**Return schema** - every wrapper must return:
```python
return {
    "module_used": "my_plugin",
    "metrics": {"Val1": 1.0, "Val2": 2.0},
}
```
Private keys (prefixed with `_`) pass data to plot overlays without appearing in the results table.

**Hot-reload** - toggling "Enable Custom Plugins" in Edit > Preferences reloads all plugins and regenerates the UI without restarting the application.

### Cross-file trial averaging

While in "Cycle Single Trial" mode, click "Add Current Trial to Avg Set" to capture a trial. Navigate to other files and continue adding trials. Enable "Plot Selected Avg" to overlay the grand average.

Shape mismatch is handled by NaN-padding shorter arrays and computing the column-wise `nanmean`, so recordings of different durations average correctly without truncation.

</details>

---

## Dependencies and citations

Synaptipy builds on the following open-source libraries. If you use Synaptipy in published research, please consider citing the relevant upstream packages.

| Library | Role | Citation |
|---|---|---|
| [Neo](https://neo.readthedocs.io) | Electrophysiology file I/O | Garcia S et al. (2014). *Front. Neuroinformatics* 8:10. [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010) |
| [PyNWB](https://pynwb.readthedocs.io) | NWB data export | Rubel O et al. (2022). *eLife* 11:e78362. [doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362) |
| [PySide6](https://doc.qt.io/qtforpython/) | Qt6 GUI framework | Qt for Python, The Qt Company |
| [PyQtGraph](https://www.pyqtgraph.org) | Signal plotting | Campagnola L et al. https://www.pyqtgraph.org |
| [SciPy](https://scipy.org) | Signal processing and curve fitting | Virtanen P et al. (2020). *Nature Methods* 17:261-272. [doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2) |
| [NumPy](https://numpy.org) | Array computation | Harris CR et al. (2020). *Nature* 585:357-362. [doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2) |

## License

Synaptipy is free and open-source software licensed under the GNU Affero General Public License v3 (AGPLv3). See the [LICENSE](LICENSE) file for full terms.


**Open-Source Electrophysiology Visualization and Analysis Suite**

Full documentation: [synaptipy.readthedocs.io](https://synaptipy.readthedocs.io/en/latest/)

Synaptipy is a cross-platform, open-source application for the visualization and analysis of electrophysiological recordings. It is designed around a modular, extensible architecture that supports interactive single-recording analysis, large-scale batch processing, and integration of custom user-written analysis routines via a plugin interface. The primary focus is whole-cell patch-clamp and intracellular recordings; however, any electrophysiology signal whose file format is supported by the Neo I/O library can be loaded, visualised, and processed - including extracellular, sharp-electrode, and multi-channel recordings. File-format support is therefore not a limitation of Synaptipy itself but of the underlying Neo reader for a given format.

## Analysis Capabilities

Synaptipy provides 15 built-in analysis routines organised into five core module tabs, each available interactively in the GUI and as a composable unit in the batch processing pipeline.

**Tab 1: Intrinsic Properties**
- **Baseline (RMP)** - mean or median membrane potential measured over a user-defined quiescent window
- **Input Resistance** - delta-V / delta-I from a voltage response to a hyperpolarising current step; auto-detects step edges from the stimulus derivative and falls back gracefully when auto-detection fails
- **Tau (Time Constant)** - single-exponential fit to the voltage decay after a current step; returns NaN with a clear error flag when the fit fails
- **Sag Ratio (Ih)** - quantifies hyperpolarisation-activated sag as the peak-to-steady-state voltage ratio; includes rebound depolarisation measurement after stimulus offset
- **I-V Curve** - current-voltage relationship across a multi-trial step protocol; fits aggregate Rin from the slope
- **Capacitance** - membrane capacitance derived from Tau/Rin in current-clamp, or from capacitive-transient integration in voltage-clamp

**Tab 2: Spike Analysis**
- **Spike Detection** - threshold-crossing AP detection with refractory period filtering; extracts per-spike amplitude, half-width, rise time, decay time, threshold voltage, and after-hyperpolarisation (AHP)
- **Phase Plane** - dV/dt vs. voltage trajectory for AP initiation dynamics; detects threshold via a kink-slope criterion and reports mean threshold voltage and maximum dV/dt

**Tab 3: Excitability**
- **Excitability (F-I Curve)** - multi-trial rheobase, F-I slope, maximum firing frequency, and spike-frequency adaptation ratio; generates a popup F-I scatter plot
- **Burst Analysis** - max-ISI burst detection; reports burst count, mean spikes per burst, mean burst duration, and intra-burst frequency
- **Spike Train Dynamics** - ISI statistics including mean ISI, coefficient of variation (CV), local variation (LV), and CV2; generates a popup ISI plot

**Tab 4: Synaptic Events**
- **Event Detection (Threshold)** - prominence-based threshold detection that accommodates shifting baselines and overlapping events; interactive event markers with click-to-remove and Ctrl+click-to-add
- **Event (Template Match)** - parametric deconvolution against a user-defined double-exponential template for miniature event detection
- **Event (Baseline Peak)** - direct baseline-to-peak amplitude detection with kinetics estimation for evoked or spontaneous events

**Tab 5: Optogenetics**
- **Optogenetic Synchronisation** - extracts TTL/digital stimulus pulses from a secondary channel and correlates them with spikes or synaptic events to compute optical latency, response probability, and jitter

## Extensibility and Plugin Interface

Synaptipy is built around a central `AnalysisRegistry` that maps named analysis functions to the GUI and batch engine via a decorator. Any Python script placed in `~/.synaptipy/plugins/` that uses the `@AnalysisRegistry.register` decorator is automatically discovered at startup and made available in both the interactive analyser and the batch processing pipeline - no modification to the core package is required.

A fully documented template (`src/Synaptipy/templates/analysis_template.py`) defines the required function signature and return types, enabling researchers to integrate custom algorithms without any knowledge of the GUI internals.

### Hot-Reloadable Plugin Ecosystem

Plugins are first-class citizens, not an afterthought. The plugin system is designed for zero-friction iteration:

- **No restart required for toggling:** When the user checks or unchecks "Enable Custom Plugins" in **Edit > Preferences**, Synaptipy calls `PluginManager.reload_plugins()` to purge all plugin-contributed entries from the `AnalysisRegistry` and re-execute every plugin file discovered on disk. It then calls `AnalyserTab.rebuild_analysis_tabs()` to regenerate the entire Analyser tab UI from the updated registry - all within the running process, with no application restart needed.
- **Scoped unregistration:** Only plugin-sourced analyses (those flagged as `source="plugin"` in registry metadata) are removed during a reload. Built-in analyses are untouched.
- **Two discovery paths:** `examples/plugins/` is scanned first (bundled examples), then `~/.synaptipy/plugins/` (user additions). A user copy with the same filename always takes precedence, enabling personalised variants without modifying the Synaptipy installation.
- **Crash isolation:** A syntax error or import failure in one plugin is caught and logged; remaining plugins still load and appear in the UI.

**Plug & Play Data Export**: The batch engine processes custom plugin outputs dynamically. Any key in the `metrics` dict returned by a plugin wrapper automatically generates its own CSV column during batch export.

**Plugin Return Schema:** Every wrapper function must return a nested dict:
```python
return {
    "module_used": "my_plugin",
    "metrics": {"Val1": 1.0, "Val2": 2.0},
}
```
Private keys (prefixed with `_`) pass data to plot overlays without appearing in the results table. See `docs/extending_synaptipy.md` for the full specification.

## Supported File Formats

File I/O is handled through the [Neo](https://neo.readthedocs.io) library, giving Synaptipy broad compatibility across acquisition systems:

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

Any format supported by Neo but not listed above can be made available by adding a corresponding entry to the `IODict` in the infrastructure layer.

## Visualization

- OpenGL-accelerated trace rendering via PyQtGraph capable of displaying multi-million sample recordings at interactive frame rates
- Tree-based multi-file explorer with synchronised analysis view
- Interactive zooming, panning, and per-channel scaling
- Batch result overlays and popup plots (I-V curves, F-I curves, phase planes) generated directly within the GUI

### Cross-File Trial Averaging

Synaptipy's Explorer tab supports manual grand-average construction across any combination of files and trials:

- While in **"Cycle Single Trial"** mode, click **"Add Current Trial to Avg Set"** to capture the currently displayed trial (including any active preprocessing pipeline transforms).
- Navigate freely to other files - even files of different durations or recording protocols - and continue adding trials. The global selection accumulates across the entire session.
- Enable **"Plot Selected Avg"** to overlay the grand average on the current recording view.
- **Shape-mismatch safety:** When computing the average, each trial is accumulated with `sum[:min_len] += trial[:min_len]` where `min_len = min(len(accumulator), len(trial))`. This dynamically truncates to the shortest array in the selection, preventing NumPy broadcast errors when recordings have different durations. The resulting average is plotted against the time vector of the first trial added.
- The selection persists until the user clears it, enabling iterative comparison as new files are loaded.

## Batch Processing

- Composable pipeline architecture: chain any registered analysis steps in sequence
- Background execution in worker threads - the GUI remains responsive during batch runs
- Automatic metadata extraction (sampling rate, gain, recording datetime)
- Results exported to CSV, compatible with Python/Pandas, R, and MATLAB
- NWB export for standards-compliant data archival

## Technical Architecture

Synaptipy follows a strict separation-of-concerns design:

- **Core layer** - pure Python analysis logic, fully decoupled from the GUI and independently testable
- **Application layer** - PySide6 (Qt6) user interface and plugin manager
- **Infrastructure layer** - file I/O via Neo and PyNWB; NWB export

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.10 - 3.12 |
| GUI Framework | PySide6 | 6.7.3 (pinned) |
| Plotting Engine | PyQtGraph | 0.13.0+ |
| Electrophysiology I/O | Neo | 0.14.0+ |
| NWB Export | PyNWB | 3.1.0+ |
| Numerical Computation | SciPy / NumPy | 1.13.0+ / 2.0.0+ |

## Installation

Synaptipy is available both as a standalone application and as a Python package.

## Download and Installation

You do not need to install Python or any dependencies to run Synaptipy. We provide pre-compiled, standalone applications for all major operating systems.

[Download the Beta Release Here](https://github.com/anzalks/Synaptipy/releases)

Choose the correct file for your operating system from the release assets:
* **Windows:** Download `Synaptipy_Setup_v0.1.0b6.exe` and run the installer.
* **macOS:** Download `Synaptipy_v0.1.0b6.dmg`, open the disk image, and drag Synaptipy to your Applications folder.
* **Linux:** Download `Synaptipy-v0.1.0b6-x86_64.AppImage`, make the file executable (`chmod +x Synaptipy-v0.1.0b6-x86_64.AppImage`), and run it directly.

### Python Package Installation
For researchers who wish to use Synaptipy programmatically or develop custom plugins, you can install it via `conda` / `pip`:

#### Prerequisites
- [Anaconda](https://www.anaconda.com/download) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html)

### Setup Instructions

1. **Clone the Repository**
 ```bash
 git clone https://github.com/anzalks/synaptipy.git
 cd synaptipy
 ```

2. **Create the Environment**
 This step installs Python and all required system dependencies defined in `environment.yml`.
 ```bash
 conda env create -f environment.yml
 ```

3. **Activate the Environment**
 ```bash
 conda activate synaptipy
 ```

4. **Install the Application**
 Install the package in editable mode to allow for local development.
 ```bash
 pip install -e ".[dev]"
 ```

### Verification
To verify the installation, execute the comprehensive test suite:
```bash
python -m pytest
```

## Quick Start

Get from installation to your first analysis in under 60 seconds:

1. **Launch the application** from your terminal:
   ```bash
   synaptipy
   ```

2. **Load a recording** - drag and drop an `.abf`, `.nwb`, `.wcp`, or any
   [supported file](#supported-file-formats) into the Explorer tab. The traces
   render immediately with OpenGL-accelerated plotting.

3. **Analyse** - click the **Analyser** tab. Select a channel, choose an
   analysis (e.g., Spike Detection or Input Resistance), adjust parameters if
   needed, and click **Run**. Results appear in the table below the plot and
   can be exported to CSV.

For headless / scripted use, the batch engine works without the GUI:

```python
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from pathlib import Path

engine = BatchAnalysisEngine()
results = engine.run_batch(
    [Path("recording.abf")],
    [{"analysis": "spike_detection", "scope": "all_trials",
      "params": {"threshold": -20.0, "refractory_ms": 2.0}}],
)
print(results)
```

## Usage

### Graphical Interface
Launch the main application window:
```bash
synaptipy
```
Alternatively, run the module directly:
```bash
python -m Synaptipy.application
```

### Programmatic Analysis
The core analysis engine can be utilized in scripts for headless processing:

```python
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from pathlib import Path

# Initialize the Analysis Engine
engine = BatchAnalysisEngine()

# Define an Analysis Pipeline
pipeline = [
 {
 'analysis': 'spike_detection',
 'scope': 'all_trials',
 'params': {'threshold': -20.0, 'refractory_ms': 2.0}
 }
]

# Execute on Data Files
file_path = Path("data/example_recording.abf")
results = engine.run_batch([file_path], pipeline)
print(results)
```

## Documentation

Full API reference, tutorials, and the developer guide are hosted on ReadTheDocs:

- [Full documentation (stable)](https://synaptipy.readthedocs.io/en/latest/)
- [Quick-start tutorial](https://synaptipy.readthedocs.io/en/latest/tutorial/index.html)
- [API reference](https://synaptipy.readthedocs.io/en/latest/api_reference.html)
- [Developer guide](https://synaptipy.readthedocs.io/en/latest/developer_guide.html)

## Contributing

Collaborations and contributions are welcome. Whether you are adding a new analysis module, supporting an additional file format, or improving the documentation, please refer to the [developer guide](https://synaptipy.readthedocs.io/en/latest/developer_guide.html) for project structure, coding standards, and the contribution workflow. The plugin interface provides the lowest-friction path to integrating custom analysis routines.

## Dependencies and Citations

Synaptipy builds on the following open-source libraries. If you use Synaptipy in published research, please consider citing the relevant upstream packages alongside the Synaptipy repository.

| Library | Role in Synaptipy | Citation |
|---|---|---|
| [Neo](https://neo.readthedocs.io) | Electrophysiology file I/O (all supported formats) | Garcia S et al. (2014). *Neo: an object model for handling electrophysiology data in multiple formats.* Front. Neuroinformatics 8:10. [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010) |
| [PyNWB](https://pynwb.readthedocs.io) | NWB data export | Rubel O et al. (2022). *The Neurodata Without Borders ecosystem for neurophysiological data science.* eLife 11:e78362. [doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362) |
| [PySide6](https://doc.qt.io/qtforpython/) | Qt6 GUI framework | Qt for Python, The Qt Company. https://doc.qt.io/qtforpython/ |
| [PyQtGraph](https://www.pyqtgraph.org) | OpenGL-accelerated signal plotting | Campagnola L et al. PyQtGraph. https://www.pyqtgraph.org |
| [SciPy](https://scipy.org) | Signal processing and numerical fitting | Virtanen P et al. (2020). *SciPy 1.0: Fundamental algorithms for scientific computing in Python.* Nature Methods 17:261-272. [doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2) |
| [NumPy](https://numpy.org) | Array computation | Harris CR et al. (2020). *Array programming with NumPy.* Nature 585:357-362. [doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2) |

## License

Synaptipy is free and open-source software licensed under the GNU Affero General Public License v3 (AGPLv3). See the [LICENSE](LICENSE) file for full terms.
