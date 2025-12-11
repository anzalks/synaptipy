# Synaptipy

**Electrophysiology Visualization & Analysis Suite**



Synaptipy is a modern, high-performance GUI application designed for visualizing and analyzing electrophysiological data (Patch Clamp, intracellular recordings). Built with Python and Qt6, it offers a seamless cross-platform experience with powerful batch processing capabilities.

## 🚀 Key Features

### 📊 Advanced Visualization

- **High-Performance Plotting**: Smoothly handle large datasets with interactive zoom and pan (60fps).
- **Multi-File Explorer**: Navigate your data easily with a tree-based file explorer.
- **Rich Analysis Modules**: Built-in tools for:
    - **Phase Plane Analysis**: dV/dt vs V plots with cycle detection.
    - **Spike Detection**: Automated AP detection with customizable thresholds.
    - **Passive Properties**: Calculate RMP, Input Resistance (Rin), and Tau.
    - **Event Detection**: Detect miniature events with template matching or thresholding.

### ⚡ Batch Processing System

- **Automated Pipelines**: Create analysis pipelines to process hundreds of files automatically.
- **Background Processing**: Heavy computations run in the background, keeping the UI responsive.
- **Metadata Integration**: Automatically extract and use metadata for analysis grouping.
- **Result Export**: One-click export to CSV for statistical analysis in Python/R/Matlab.

## 🛠️ Installation

**Supported OS**: Windows, macOS, Linux
**Prerequisites**: [Anaconda](https://www.anaconda.com/download) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html)

The recommended installation method uses `pip` inside a `conda` environment to ensure maximum compatibility.

```bash
# 1. Clone the repository
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy

# 2. Create the environment (installs system deps)
conda env create -f environment.yml

# 3. Activate the environment
conda activate synaptipy

# 4. Install the application
pip install -e .
```

### Quick Verification
Run the test suite to ensure everything is set up correctly:
```bash
python -m pytest
```

## 🖥️ Usage

### Running the Application
```bash
synaptipy-gui
# OR
python -m Synaptipy.application
```

### Batch Analysis Example
You can also run analyses programmatically:

```python
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from pathlib import Path

# Initialize Engine
engine = BatchAnalysisEngine()

# Define Pipeline
pipeline = [
    {
        'analysis': 'spike_detection',
        'scope': 'all_trials',
        'params': {'threshold': -20.0, 'refractory_ms': 2.0}
    }
]

# Run
results = engine.run_batch([Path("data/file1.abf")], pipeline)
print(results)
```

## 📦 Tech Stack

| Component | Technology | Description |
|-----------|------------|-------------|
| **Core** | Python 3.11 | Logic and Computation |
| **GUI** | PySide6 (Qt6) | Modern UI Framework |
| **Plotting** | PyQtGraph | High-performance GPU-accelerated plotting |
| **Data** | Neo / PyNWB | Electrophysiology Data Standards |
| **Analysis** | SciPy / NumPy | Scientific Computing |

## 🤝 Contributing

We welcome contributions! Please check the [Developer Guide](docs/developer_guide.md) for details on setting up your dev environment and the [Styling Guide](docs/development/styling_guide.md) for UI consistency.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
**Made with ❤️ by the Synaptipy Team**
