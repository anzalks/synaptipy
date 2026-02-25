# Synaptipy

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/anzalks/synaptipy)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![CI](https://github.com/anzalks/synaptipy/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/anzalks/synaptipy/actions/workflows/test.yml)
[![Docs](https://github.com/anzalks/synaptipy/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/anzalks/synaptipy/actions/workflows/docs.yml)
[![Documentation Status](https://readthedocs.org/projects/synaptipy/badge/?version=latest)](https://synaptipy.readthedocs.io/en/latest/)
[![Code style: flake8](https://img.shields.io/badge/code%20style-flake8-black)](https://flake8.pycqa.org/)

**Electrophysiology Visualization & Analysis Suite**

> 📖 **Full documentation**: [synaptipy.readthedocs.io](https://synaptipy.readthedocs.io/en/latest/)

Synaptipy is a high-performance graphical user interface (GUI) designed for the visualization and analysis of electrophysiological data, specifically focusing on Patch Clamp and intracellular recordings. Built on Python and the Qt6 framework, it provides a robust, cross-platform solution for managing complex datasets and executing batch analysis pipelines.

## Key Features

### Advanced Signal Visualization
The application leverages hardware-accelerated plotting to handle high-frequency sampling data with minimal latency.
- **High-Performance Rendering**: Capable of displaying traces with millions of data points at 60 fps using OpenGL-based rendering.
- **Interactive Navigation**: Seamless zooming, panning, and scaling of waveforms.
- **Multi-File Explorer**: A tree-based file management system that synchronizes with the analysis view, allowing for rapid dataset traversal.

### Analysis Modules
Synaptipy includes a comprehensive suite of analysis tools designed for neuronal characterization.

#### Spike Detection & Analysis
Automated detection and parameterization of Action Potentials (APs).
- **Detection Logic**: Configurable threshold-based detection with refractory period filtering.
- **Metrics**: Calculates AP amplitude, half-width, rise time, decay time, and after-hyperpolarization (AHP).

#### Burst Analysis
Identification of firing bursts based on inter-spike intervals (ISI).
- **Algorithms**: Implements standard burst detection algorithms (e.g., Poisson Surprise or max interval methods).
- **Metrics**: Burst duration, spike count per burst, intra-burst frequency.

#### Intrinsic Properties
Automated extraction of sub-threshold membrane properties.
- **Resting Membrane Potential (RMP)**: Statistical calculation of baseline voltage.
- **Input Resistance (Rin)**: Derived from voltage responses to hyperpolarizing current steps.
- **Membrane Time Constant (Tau)**: Exponential fitting of the voltage decay.

#### Event Detection (Miniature Analysis)
Detection of spontaneous synaptic events in voltage or current clamp.
- **Methods**: Template matching and threshold-crossing detection algorithms.
- **Filtering**: Integrated digital filters (Low-pass, High-pass, Notch) for signal conditioning prior to detection.

#### Phase Plane Analysis
Visualization of Action Potential dynamics in phase space.
- **Plotting**: Generates dV/dt versus Voltage plots for analyzing initiation dynamics and threshold voltages.

### Batch Processing Engine
A dedicated engine for processing large datasets without manual intervention.
- **Pipeline Architecture**: Users can define sequential analysis steps (e.g., Filter -> Spike Detect -> Burst Analysis).
- **Background Execution**: Analysis tasks run in separate threads to maintain GUI responsiveness.
- **Metadata Handling**: Automatic extraction of recording metadata (Gain, Sampling Rate, DateTime) for structured results.
- **Data Export**: Aggregated results are exported to CSV formats compatible with statistical software (Python/Pandas, R, MATLAB).

## Technical Architecture

Synaptipy adheres to a strict "Separation of Concerns" architecture for maintainability and scientific accuracy.

- **Core Layer**: Contains pure Python logic for signal processing and analysis. It is strictly decoupled from the GUI, ensuring that analysis algorithms can be tested and verified independently.
- **Application Layer**: Manages the PySide6 (Qt6) based user interface, handling user interactions and visualization state.
- **Infrastructure Layer**: Handles file I/O operations using the Neo and PyNWB libraries, ensuring broad compatibility with electrophysiology file formats (ABF, NWB, etc.).

| Component | Technology | Version Requirement |
|-----------|------------|---------------------|
| **Language** | Python | 3.10+ |
| **GUI Framework** | PySide6 | >= 6.7.0 |
| **Plotting Engine** | PyQtGraph | >= 0.13.0 |
| **Data Standard** | Neo / PyNWB | >= 0.14.0 / >= 3.1.0 |
| **Computation** | SciPy / NumPy | >= 1.13.0 / >= 2.0.0 |

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

- **Stable / latest**: https://synaptipy.readthedocs.io/en/latest/
- **Tutorial**: https://synaptipy.readthedocs.io/en/latest/tutorial/index.html
- **API Reference**: https://synaptipy.readthedocs.io/en/latest/api_reference.html

## Contributing

Contributions are welcome. Please refer to the [online developer guide](https://synaptipy.readthedocs.io/en/latest/developer_guide.html) or the `docs/` directory for development standards. Use the `rules.md` file as the authoritative source for architectural compliance and code style.

## License

This project is licensed under the GNU Affero General Public License v3 (AGPLv3). See the [LICENSE](LICENSE) file for complete details.

---
**Synaptipy Development Team**
