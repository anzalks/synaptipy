# Synaptipy

[![PyPI](https://img.shields.io/pypi/v/Synaptipy?color=blue&label=PyPI)](https://pypi.org/project/Synaptipy/)
[![Python](https://img.shields.io/badge/python-3.10--3.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/anzalks/synaptipy)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![CI](https://github.com/anzalks/synaptipy/actions/workflows/test.yml/badge.svg)](https://github.com/anzalks/synaptipy/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/anzalks/synaptipy/branch/main/graph/badge.svg)](https://codecov.io/gh/anzalks/synaptipy)
[![Documentation Status](https://readthedocs.org/projects/synaptipy/badge/?version=latest)](https://synaptipy.readthedocs.io/en/latest/)
[![Qt6](https://img.shields.io/badge/Qt-6-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/imports-isort-%231674b1?labelColor=ef8336)](https://pycqa.github.io/isort/)
[![Lint: flake8](https://img.shields.io/badge/lint-flake8-blue)](https://flake8.pycqa.org/)
[![Release](https://img.shields.io/github/v/release/anzalks/synaptipy?include_prereleases&label=release&color=orange)](https://github.com/anzalks/synaptipy/releases)

**Open-Source Electrophysiology Visualization and Analysis Suite** | v0.1.2b6

Full documentation: [synaptipy.readthedocs.io](https://synaptipy.readthedocs.io/en/latest/)

Synaptipy is a cross-platform, open-source application for the visualization and analysis of electrophysiological recordings. It is designed around a modular, extensible architecture that supports interactive single-recording analysis, large-scale batch processing, and integration of custom user-written analysis routines via a plugin interface. The primary focus is whole-cell patch-clamp and intracellular recordings; any electrophysiology signal whose file format is supported by the [Neo](https://neo.readthedocs.io) I/O library can be loaded, visualised, and processed, including extracellular, sharp-electrode, and multi-channel recordings.

---

## Installation

### Prerequisites

- [Anaconda](https://www.anaconda.com/download) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- Python 3.11 is recommended (3.10 and 3.12 are also supported)

### From source (recommended)

```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
conda env create -f environment.yml   # creates the 'synaptipy' environment with Python 3.11
conda activate synaptipy
pip install -e ".[dev]"
```

The `environment.yml` file specifies all required dependencies. Python 3.11 is the tested and recommended interpreter; to enforce it explicitly, pass the `--python` flag:

```bash
conda create -n synaptipy python=3.11
conda activate synaptipy
pip install -e ".[dev]"
```

### Verify the installation

```bash
python -m pytest   # runs the full test suite
synaptipy          # launches the graphical interface
```

### Standalone application

Pre-compiled binaries for Windows, macOS, and Linux are available on the [Releases page](https://github.com/anzalks/Synaptipy/releases). Download the file matching your operating system from the v0.1.2b6 release assets:

- **Windows:** `Synaptipy_Setup_v0.1.2b6.exe`
- **macOS:** `Synaptipy_v0.1.2b6.dmg` - open the disk image and drag to Applications
- **Linux:** `Synaptipy-v0.1.2b6-x86_64.AppImage` - mark as executable (`chmod +x`) and run

---

## Usage

### Graphical interface

```bash
synaptipy
# or equivalently:
python -m Synaptipy
```

Load a recording by dragging a file into the **Explorer** tab, then navigate to the **Analyser** tab to select a channel and run an analysis. Results are displayed in a table and can be exported to CSV.

### Programmatic (headless) use

The batch engine operates independently of the graphical interface:

```python
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from pathlib import Path

engine = BatchAnalysisEngine()
pipeline = [
    {
        "analysis": "spike_detection",
        "scope": "all_trials",
        "params": {"threshold": -20.0, "refractory_ms": 2.0},
    }
]
results = engine.run_batch([Path("recording.abf")], pipeline)
print(results)
```

---

## Analysis Capabilities

Synaptipy provides 17 built-in analysis routines organised into five module tabs. Each routine is available interactively in the graphical interface and as a composable unit in the batch processing pipeline.

### Tab 1: Intrinsic Properties

- **Baseline (RMP)** - mean membrane potential measured over a user-defined quiescent window; reports mean, standard deviation, and an estimate of linear drift
- **Input Resistance** - delta-V / delta-I from a voltage response to a hyperpolarising current step; returns mean, peak, and steady-state Rin separately to distinguish Ih-sag contributions
- **Tau (Time Constant)** - single-exponential or bi-exponential fit to the voltage decay after a current step; fit quality is gated by R² >= 0.80 and NaN is returned with an explicit flag when the gate is not met
- **Sag Ratio (Ih)** - peak-to-steady-state voltage ratio during a hyperpolarising step; includes rebound depolarisation measured after stimulus offset
- **I-V Curve** - current-voltage relationship across a multi-trial step protocol; fits an aggregate Rin from a linear regression and computes a dynamic rectification index
- **Capacitance** - membrane capacitance derived from Tau / Rin in current-clamp, or from capacitive-transient integration and mono-exponential fit in voltage-clamp

### Tab 2: Spike Analysis

- **Spike Detection** - threshold-crossing action-potential detection with refractory-period filtering; extracts per-spike amplitude, half-width, rise time, decay time, threshold voltage, and after-hyperpolarisation (AHP)
- **Phase Plane** - dV/dt vs. voltage trajectory for action-potential initiation dynamics; threshold voltage is detected via a kink-slope criterion; reports mean threshold voltage and maximum dV/dt

### Tab 3: Excitability

- **Excitability (F-I Curve)** - multi-trial rheobase, F-I slope, maximum firing frequency, and spike-frequency adaptation ratio; generates a popup F-I scatter plot
- **Burst Analysis** - max-ISI burst detection; reports burst count, mean spikes per burst, mean burst duration, and intra-burst frequency
- **Spike Train Dynamics** - inter-spike interval statistics including mean ISI, coefficient of variation (CV), local variation (LV), and CV2; generates a popup ISI plot

### Tab 4: Synaptic Events

- **Event Detection (Threshold)** - prominence-based detection that accommodates baseline drift and overlapping events; interactive event markers can be individually accepted or rejected
- **Event (Template Match)** - matched-filter cross-correlation using a bi-exponential kernel with user-defined rise and decay time constants; three kernel scales (1x, 2x, 3x the decay constant) are evaluated to accommodate dendritic-filtering variability
- **Event (Baseline Peak)** - direct baseline-to-peak amplitude detection with kinetics estimation for evoked or spontaneous events

### Tab 5: Evoked Responses

- **Evoked Sync** - extracts TTL or digital stimulus pulses from a secondary channel and correlates them with detected spikes or synaptic events; reports optical latency, response probability, and trial-to-trial jitter
- **Paired-Pulse Ratio** - measures R1 and R2 amplitudes for a two-pulse protocol; fits a mono- or bi-exponential decay to the R1 tail and subtracts the residual at the time of the second stimulus before computing the ratio, avoiding contamination of R2 by the decaying R1 baseline
- **Stimulus Train (STP)** - measures response amplitudes across a multi-pulse stimulus train and normalises each pulse to R1 to generate a short-term plasticity (STP) profile; classifies the result as facilitation or depression

---

## Visualization

- Trace rendering via PyQtGraph, capable of handling multi-million-sample recordings at interactive frame rates
- Tree-based multi-file explorer with synchronised trial navigation and per-channel amplitude scaling
- Interactive zooming and panning with explicit view-range management
- Popup plots for I-V curves, F-I curves, phase planes, and ISI distributions

### Cross-file trial averaging

The Explorer tab supports grand-average construction across an arbitrary selection of files and trials. While in **Cycle Single Trial** mode, activate **Add Current Trial to Avg Set** to capture the current trial. Navigate to other files and continue adding trials; the accumulated set persists across the session. Enable **Plot Selected Avg** to overlay the mean trace. Shape mismatches between recordings of different durations are resolved by truncating all trials to the length of the shortest array in the selection.

---

## Batch Processing

- Composable pipeline architecture: any registered analysis steps can be chained in sequence
- Analysis runs in a background worker thread; the graphical interface remains responsive
- Automatic extraction of recording metadata (sampling rate, gain, acquisition datetime)
- Results exported to CSV in wide format (scalar metrics) and long format (event arrays), compatible with Python/Pandas, R, and MATLAB
- NWB 2.x export with icephys sweep tables, a three-step stimulus reconstruction fallback, and a discrete-event `ProcessingModule` for FAIR-compliant data archival

---

## Plugin Interface

Synaptipy is built around a central `AnalysisRegistry` that maps named analysis functions to the graphical interface and batch engine via a decorator. Any Python script placed in `~/.synaptipy/plugins/` that uses the `@AnalysisRegistry.register` decorator is discovered at startup and made available in both the interactive analyser and the batch pipeline without modification to the core package.

A documented template at `src/Synaptipy/templates/analysis_template.py` defines the required function signature and return schema.

```python
@AnalysisRegistry.register(
    name="my_analysis",
    label="My Analysis",
    ui_params=[{"name": "threshold", "type": "float", "default": -20.0}],
    plots=[{"name": "Trace", "type": "trace"}],
)
def my_analysis_wrapper(data, time, sampling_rate, **kwargs):
    ...
    return {
        "module_used": "my_analysis",
        "metrics": {"threshold_mv": kwargs["threshold"]},
    }
```

Every wrapper must return a nested dictionary with a `module_used` key and a `metrics` sub-dictionary. Keys prefixed with `_` pass arrays to plot overlays without appearing in the results table. The full specification is in `docs/extending_synaptipy.md`.

Plugin discovery follows two paths: `examples/plugins/` (bundled examples) and `~/.synaptipy/plugins/` (user additions). A user copy with an identical filename takes precedence. Toggling **Enable Custom Plugins** in **Edit > Preferences** reloads all plugins and regenerates the Analyser tab UI within the running process. Import errors in individual plugins are caught and logged; the remaining plugins continue to load normally.

---

## NWB Export and FAIR Compliance

Synaptipy exports raw traces and analysis results to [Neurodata Without Borders (NWB) 2.x](https://www.nwb.org):

- Raw electrophysiology traces stored as `CurrentClampSeries` / `VoltageClampSeries`
- Sweep-level organisation via `IntracellularRecordingsTable`, `SimultaneousRecordingsTable`, and `SequentialRecordingsTable` (NWB 2.x icephys best-practice hierarchy)
- Stimulus waveform reconstruction from ABF epoch metadata when the command channel is absent; a three-step fallback (raw channel -> synthetic reconstruction -> `stimulus=None` with a warning) ensures NWB conformance for recordings with incomplete stimulus records
- Discrete event data (spike times, synaptic event times, amplitudes) written as `DynamicTable` objects inside a `ProcessingModule` when the batch engine produces `_raw_arrays` output
- Electrode metadata and session provenance fields

---

## Supported File Formats

File I/O is handled through the [Neo](https://neo.readthedocs.io) library:

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

Additional formats supported by Neo can be made available by adding the corresponding entry to the `IODict` in the infrastructure layer.

---

## Technical Architecture

Synaptipy follows a separation-of-concerns design with three layers:

- **Core layer** - pure Python analysis logic, fully decoupled from the graphical interface and independently testable
- **Application layer** - PySide6 (Qt6) user interface and plugin manager
- **Infrastructure layer** - file I/O via Neo and PyNWB; NWB export

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.10 - 3.12 (3.11 recommended) |
| GUI Framework | PySide6 | 6.7.3 (pinned) |
| Plotting Engine | PyQtGraph | 0.13.3+ |
| Electrophysiology I/O | Neo | 0.14.0+ |
| NWB Export | PyNWB | 3.1.0+ |
| Numerical Computation | SciPy / NumPy | 1.14.0+ / 2.0.0+ |

PySide6 is pinned to 6.7.3 on all platforms. PySide6 6.8.0 contains a known crash on Windows (QTBUG-130070) and 6.10.x introduced internal signal-connection changes that produce segmentation faults in the pyqtgraph rendering path under the offscreen platform plugin. The pin will be reviewed when an upstream fix is available.

---

## Documentation

- [Full documentation](https://synaptipy.readthedocs.io/en/latest/)
- [API reference](https://synaptipy.readthedocs.io/en/latest/api_reference.html)
- [Developer guide](https://synaptipy.readthedocs.io/en/latest/developer_guide.html)
- [Extending Synaptipy (plugin guide)](docs/extending_synaptipy.md)

---

## Contributing

Contributions are welcome. The preferred contribution pathway for new analysis routines is the plugin interface, which requires no modification to the core package. For changes to the core, infrastructure, or application layers, refer to [CONTRIBUTING.md](CONTRIBUTING.md) and the [developer guide](https://synaptipy.readthedocs.io/en/latest/developer_guide.html) for project conventions, coding standards, and the contribution workflow.

---

## Dependencies and Citations

Synaptipy builds on the following open-source libraries. When using Synaptipy in published research, please consider citing the relevant upstream packages alongside the Synaptipy repository.

| Library | Role | Citation |
|---|---|---|
| [Neo](https://neo.readthedocs.io) | Electrophysiology file I/O | Garcia S et al. (2014). *Front. Neuroinformatics* 8:10. [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010) |
| [PyNWB](https://pynwb.readthedocs.io) | NWB data export | Rubel O et al. (2022). *eLife* 11:e78362. [doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362) |
| [PySide6](https://doc.qt.io/qtforpython/) | Qt6 GUI framework | Qt for Python, The Qt Company. https://doc.qt.io/qtforpython/ |
| [PyQtGraph](https://www.pyqtgraph.org) | Signal rendering | Campagnola L et al. PyQtGraph. https://www.pyqtgraph.org |
| [SciPy](https://scipy.org) | Signal processing and curve fitting | Virtanen P et al. (2020). *Nature Methods* 17:261-272. [doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2) |
| [NumPy](https://numpy.org) | Array computation | Harris CR et al. (2020). *Nature* 585:357-362. [doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2) |

---

## License

Synaptipy is free and open-source software licensed under the GNU Affero General Public License v3 (AGPLv3). See the [LICENSE](LICENSE) file for full terms.
