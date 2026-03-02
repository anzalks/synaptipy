# Synaptipy

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/anzalks/synaptipy)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![CI](https://github.com/anzalks/synaptipy/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/anzalks/synaptipy/actions/workflows/test.yml)
[![Docs](https://github.com/anzalks/synaptipy/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/anzalks/synaptipy/actions/workflows/docs.yml)
[![Documentation Status](https://readthedocs.org/projects/synaptipy/badge/?version=latest)](https://synaptipy.readthedocs.io/en/latest/)
[![Qt6](https://img.shields.io/badge/Qt-6-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/imports-isort-%231674b1?labelColor=ef8336)](https://pycqa.github.io/isort/)
[![Lint: flake8](https://img.shields.io/badge/lint-flake8-blue)](https://flake8.pycqa.org/)
[![Collaborators Welcome](https://img.shields.io/badge/collaborators-welcome-brightgreen?logo=github&logoColor=white)](https://github.com/anzalks/synaptipy)
[![Release](https://img.shields.io/github/v/release/anzalks/synaptipy?include_prereleases&label=release&color=orange)](https://github.com/anzalks/synaptipy/releases)

**Open-Source Electrophysiology Visualization and Analysis Suite**

Full documentation: [synaptipy.readthedocs.io](https://synaptipy.readthedocs.io/en/latest/)

Synaptipy is a cross-platform, open-source application for the visualization and analysis of electrophysiological recordings. It is designed around a modular, extensible architecture that supports interactive single-recording analysis, large-scale batch processing, and integration of custom user-written analysis routines via a plugin interface. The primary focus is whole-cell patch-clamp and intracellular recordings; however, any electrophysiology signal whose file format is supported by the Neo I/O library can be loaded, visualised, and processed — including extracellular, sharp-electrode, and multi-channel recordings. File-format support is therefore not a limitation of Synaptipy itself but of the underlying Neo reader for a given format.

## Analysis Capabilities

Synaptipy provides 15 built-in analysis modules, each available interactively in the GUI and as a composable unit in the batch processing pipeline.

**Intrinsic Membrane Properties**
- Resting Membrane Potential (RMP) — statistical baseline extraction from a user-defined window
- Input Resistance (Rin) — delta-V / delta-I from voltage response to a hyperpolarizing current step
- Membrane Time Constant (Tau) — single-exponential fit to the voltage decay after a current step
- I-V Curve — current–voltage relationship and aggregate Rin from multi-trial step protocols
- Sag Ratio (I_h) — quantifies hyperpolarisation-activated sag from the ratio of peak-to-steady-state deflection, with rebound depolarisation measurement
- Cell Capacitance (Cm) — derived from Tau/Rin in current-clamp, or capacitive-transient integration in voltage-clamp

**Action Potential Analysis**
- Spike Detection — threshold- and dV/dt-based AP detection with refractory period filtering; extracts amplitude, half-width, rise time, decay time, threshold voltage, and after-hyperpolarisation (AHP)
- Burst Analysis — max-ISI burst detection; reports burst count, mean spikes per burst, burst duration, and intra-burst frequency
- Spike Train Dynamics — inter-spike interval (ISI) statistics, coefficient of variation (CV), CV2, and local variation (LV)
- Excitability / F-I Curve (multi-trial) — rheobase, F-I slope, maximum firing frequency, and spike-frequency adaptation ratio
- Phase Plane Analysis — dV/dt versus voltage plot for AP initiation dynamics and threshold characterisation

**Synaptic Event Detection**
- Adaptive Threshold — prominence-based detection that accommodates shifting baselines and overlapping events
- Template Matching — parametric deconvolution using a user-defined double-exponential template for miniature event detection
- Baseline-Peak — direct baseline-to-peak amplitude detection for evoked or spontaneous events

**Optogenetics**
- Optogenetic Synchronisation — extracts TTL/digital stimulus pulses from a secondary channel and correlates them with spikes to compute optical latency, response probability, and jitter

## Extensibility and Plugin Interface

Synaptipy is built around a central `AnalysisRegistry` that maps named analysis functions to the GUI and batch engine via a decorator. Any Python script placed in `~/.synaptipy/plugins/` that uses the `@AnalysisRegistry.register` decorator is automatically discovered at startup and made available in both the interactive analyser and the batch processing pipeline — no modification to the core package is required.

A fully documented template (`src/Synaptipy/templates/analysis_template.py`) defines the required function signature and return types, enabling researchers to integrate custom algorithms without any knowledge of the GUI internals.

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
| MATLAB | `.mat` | — |
| ASCII / CSV | `.txt`, `.csv`, `.tsv` | — |

Any format supported by Neo but not listed above can be made available by adding a corresponding entry to the `IODict` in the infrastructure layer.

## Visualization

- OpenGL-accelerated trace rendering capable of displaying multi-million sample recordings at interactive frame rates
- Tree-based multi-file explorer with synchronised analysis view
- Interactive zooming, panning, and per-channel scaling
- Batch result overlays and popup plots (I-V curves, F-I curves, phase planes) generated directly within the GUI

## Batch Processing

- Composable pipeline architecture: chain any registered analysis steps in sequence
- Background execution in worker threads — the GUI remains responsive during batch runs
- Automatic metadata extraction (sampling rate, gain, recording datetime)
- Results exported to CSV, compatible with Python/Pandas, R, and MATLAB
- NWB export for standards-compliant data archival

## Technical Architecture

Synaptipy follows a strict separation-of-concerns design:

- **Core layer** — pure Python analysis logic, fully decoupled from the GUI and independently testable
- **Application layer** — PySide6 (Qt6) user interface and plugin manager
- **Infrastructure layer** — file I/O via Neo and PyNWB; NWB export

| Component | Technology | Minimum Version |
|---|---|---|
| Language | Python | 3.10 |
| GUI Framework | PySide6 | 6.7.0 |
| Plotting Engine | PyQtGraph | 0.13.0 |
| Electrophysiology I/O | Neo | 0.14.0 |
| NWB Export | PyNWB | 3.1.0 |
| Numerical Computation | SciPy / NumPy | 1.13.0 / 2.0.0 |

## Installation

Synaptipy is compatible with Windows, macOS, and Linux. The implementation relies on `conda` for environment management to handle system-level dependencies efficiently.

### Prerequisites
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
| [SciPy](https://scipy.org) | Signal processing and numerical fitting | Virtanen P et al. (2020). *SciPy 1.0: Fundamental algorithms for scientific computing in Python.* Nature Methods 17:261–272. [doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2) |
| [NumPy](https://numpy.org) | Array computation | Harris CR et al. (2020). *Array programming with NumPy.* Nature 585:357–362. [doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2) |

## License

Synaptipy is free and open-source software licensed under the GNU Affero General Public License v3 (AGPLv3). See the [LICENSE](LICENSE) file for full terms.
