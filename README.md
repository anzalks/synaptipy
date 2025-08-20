# Synaptipy

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-green.svg)](https://github.com/anzalks/synaptipy)

Synaptipy is a multi-channel electrophysiology visualization and analysis toolkit designed for neuroscience and electrophysiology researchers. It provides a user-friendly interface for exploring, analyzing, and exporting electrophysiological data.

**Now available on Windows, macOS, and Linux!** 🖥️ 🍎 🐧

## Features

- **Data Loading**: Support for various electrophysiology file formats using the Neo library
- **Interactive Visualization**: Real-time plotting and navigation of multi-channel recordings
- **Built-in Analysis Tools**:
  - Input resistance/conductance calculations
  - Resting membrane potential analysis
  - Custom analysis plugins can be added
- **Export Capabilities**:
  - NWB (Neurodata Without Borders) export for standardized data sharing
  - CSV export of analysis results
- **User Experience**:
  - Welcome screen with loading progress during startup
  - Real-time progress tracking for application initialization
  - Smooth transition from loading to main interface
  - Brain icon and modern loading interface
- **Intelligent Cross-Platform Styling**:
  - Automatically detects and respects system theme (light/dark)
  - Native platform styling for consistent appearance
  - White plot backgrounds for optimal data visualization
  - No theme conflicts or patchwork styling
- **Extensible Architecture**: Easy to add new analysis methods or file format support

### What's New in Current Version
- 🆕 **Cross-Platform Support**: Now available on Windows, macOS, and Linux
- 🆕 **Intelligent Styling**: Automatically detects and respects your system theme
- 🆕 **Welcome Screen**: Modern loading interface with brain icon and progress tracking
- 🆕 **Improved Performance**: Faster startup times and smoother transitions
- 🆕 **Theme Consistency**: No more patchwork styling or theme conflicts

## Installation

### Prerequisites

- Python 3.9 or later
- pip or conda package manager

### Installing from Source

```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
pip install -e .
```

**⚠️ Note**: This installs all Python dependencies, but Qt6 system libraries must be available on your system for full GUI functionality (file dialogs, file operations, etc.).

For development:

```bash
pip install -e ".[dev]"
```

### Conda Environment Setup (Recommended)

For isolated development and testing:

```bash
# Create a new conda environment
conda create -n synaptipy python=3.9

# Activate the environment
conda activate synaptipy

# Install Qt6 system libraries and PySide6 (REQUIRED for GUI functionality)
conda install -c conda-forge qt pyside6 pyqtgraph

# Install Synaptipy in editable mode
pip install -e .
```

**⚠️ Important**: The Qt6 system libraries are required for file operations, file dialogs, and full GUI functionality. Installing only with `pip install -e .` will result in a partially functional application.

## Quick Start

### GUI Application

After installation, run the application using the commands shown in the [Usage](#running-the-application) section below.

**Startup Process**: The application features an intelligent welcome screen that provides:
- Real-time loading progress with detailed status updates
- Step-by-step initialization of core components (Qt framework, PyQtGraph, styling, main window, analysis modules)
- Brain icon and modern interface design
- Smooth transition to the main interface once loading is complete
- Consistent theme throughout the entire startup process

This significantly improves the user experience by providing clear feedback during startup and eliminating the previous slow loading times.

### Programmatic Usage

```python
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter
from Synaptipy.analysis.resistance_analysis import calculate_input_resistance

# Load a recording
neo_adapter = NeoAdapter()
recording = neo_adapter.read_recording("path/to/data.abf")

# Access channels
v_channel = recording.get_channel_by_name("Vm")
i_channel = recording.get_channel_by_name("Im")

# Analyze input resistance
result = calculate_input_resistance(
    v_channel=v_channel,
    i_channel=i_channel,
    baseline_window=[0.1, 0.2],  # seconds
    response_window=[0.5, 0.6],  # seconds
    trial_index=0
)

print(f"Input Resistance: {result['Rin (MΩ)']} MΩ")
```

See the [examples](examples/) directory for more detailed examples.

## Documentation

- [User Guide](docs/user_guide.md) - Detailed instructions for using Synaptipy
- [API Reference](docs/api_reference.md) - Documentation for developers
- [Styling Guide](docs/development/styling_guide.md) - Guide for UI styling and theming
- [Examples](examples/) - Example scripts demonstrating usage

## Styling & Theme System

Synaptipy features an intelligent cross-platform styling system that:

- **Automatically detects your system theme** (light/dark mode) on Windows, macOS, and Linux
- **Uses native platform styling** for consistent appearance across operating systems
- **Maintains white plot backgrounds** for optimal data visualization regardless of UI theme
- **Eliminates theme conflicts** that previously caused patchwork styling issues
- **Provides seamless user experience** from welcome screen through main interface

The application now maintains your preferred system theme throughout the entire session, ensuring a consistent and professional appearance.

## Testing

Run the test suite with:

```bash
python scripts/run_tests.py
```

Or run specific tests:

```bash
python scripts/run_tests.py --verbose --test test_main_window
```

## Troubleshooting

### Common Issues

**Theme/Styling Issues:**
- If you experience inconsistent UI themes or patchwork styling, ensure you're using the latest version
- The application automatically detects and respects your system theme
- Plot backgrounds remain white for optimal data visualization

**Startup Issues:**
- If the welcome screen doesn't transition to the main GUI, check the logs in `~/.synaptipy/logs/`
- Ensure all dependencies are properly installed in your conda environment
- Use `conda run -n synaptipy synaptipy-gui` for consistent environment execution

**Qt6/File Operation Issues:**
- If the GUI starts but file opening doesn't work, you're missing Qt6 system libraries
- Solution: `conda install -c conda-forge qt pyside6 pyqtgraph` before installing Synaptipy
- The `synaptipy` environment works because it has the full Qt6 stack installed
- The `sudeepta` environment fails because it only has Python packages without Qt6 system libraries

**Performance Issues:**
- The welcome screen now provides real-time feedback during startup
- Initial loading times have been significantly improved
- Check logs for any component initialization delays

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

When contributing UI components, please follow the [Styling Guide](docs/development/styling_guide.md) to maintain visual consistency.

## License

This project is licensed under the GNU Affero General Public License Version 3 - see the [LICENSE](LICENSE) file for details. This license ensures that modifications to the software, even when run as a network service, must be made available to users.

## Acknowledgments

- [Neo](https://neo.readthedocs.io/) - For reading electrophysiology file formats
- [PySide6](https://wiki.qt.io/Qt_for_Python) - For the GUI framework
- [pyqtgraph](https://pyqtgraph.readthedocs.io/) - For fast plotting capabilities
- [pynwb](https://pynwb.readthedocs.io/) - For NWB file format support

## Supported File Formats

Synaptipy uses the [neo](https://neo.readthedocs.io/) library under the hood, enabling it to read a wide variety of electrophysiology file formats. Some of the commonly supported formats include:

*   Axon Instruments / Molecular Devices (pCLAMP) (`.abf`)
*   NeuroExplorer (`.nex`)
*   CED (Spike2) (`.smr`, `.smrx`)
*   Plexon (`.plx`, `.pl2`)
*   Blackrock Microsystems (`.nsX`, `.nev`)
*   Neuralynx (`.ncs`, `.nev`, `.nse`, `.ntt`)
*   Tucker-Davis Technologies (TDT) (`.sev`, `.tev`, etc.)
*   Intan Technologies (`.rhd`, `.rhs`)
*   Open Ephys (`.continuous`, `.spikes`, `.oebin`)
*   BrainVision (`.vhdr`)
*   European Data Format (`.edf`)
*   Alpha Omega (`.mpx`)
*   MATLAB (`.mat`)
*   HDF5 (generic, NIX, NWB) (`.h5`, `.nix`, `.nwb`)
*   ASCII-based formats (`.txt`, `.csv`, `.asc`)

For a complete and up-to-date list, please refer to the [neo documentation](https://neo.readthedocs.io/en/latest/iolist.html).

## Screenshots

### Welcome Screen & Loading
The application starts with an intelligent welcome screen that shows real-time loading progress:
- Brain icon and modern interface design
- Step-by-step initialization progress
- Consistent theme throughout startup process

### Main Interface
The main application window provides:
- **Explorer Tab**: File loading and data visualization
- **Analyser Tab**: Multiple analysis tools (Event Detection, Resistance, Baseline, Spike Analysis)
- **Exporter Tab**: Data export in various formats (NWB, CSV)

### Analysis Tools
Built-in analysis capabilities include:
- Input resistance/conductance calculations
- Resting membrane potential analysis
- Event detection and spike analysis
- Custom analysis plugin support

*Note: New screenshots of the current version will be added here showing the welcome screen, main interface, and analysis tabs. For now, see the Legacy Screenshots section below for reference.*

## Usage

### Running the Application

#### Windows
```cmd
# Using installed entry point (recommended)
synaptipy-gui

# Or using conda run (if using conda environment)
conda run -n synaptipy synaptipy-gui

# Or using the Python module
python -m Synaptipy.application
```

#### macOS
```bash
# Using installed entry point (recommended)
synaptipy-gui

# Or using the Python module
python -m Synaptipy.application

# Or using conda run (if using conda environment)
conda run -n synaptipy synaptipy-gui
```

#### Linux
```bash
# Using installed entry point (recommended)
synaptipy-gui

# Or using the Python module
python -m Synaptipy.application

# Or using conda run (if using conda environment)
conda run -n synaptipy synaptipy-gui
```

### Development Mode

For more detailed logging and debugging information, run in development mode:

```bash
synaptipy-gui --dev
```

You can also set the environment variable `SYNAPTIPY_DEV_MODE=1` to achieve the same effect:

#### Windows
```cmd
# Command Prompt
set SYNAPTIPY_DEV_MODE=1 && synaptipy-gui

# PowerShell
$env:SYNAPTIPY_DEV_MODE=1; synaptipy-gui

# Conda environment
conda run -n synaptipy synaptipy-gui --dev
```

#### macOS/Linux
```bash
# Set environment variable and run
SYNAPTIPY_DEV_MODE=1 synaptipy-gui

# Or export for current session
export SYNAPTIPY_DEV_MODE=1
synaptipy-gui

# Conda environment
conda run -n synaptipy synaptipy-gui --dev
```

Development mode provides:
- Detailed logging output (file + console)
- Function call tracing for debugging
- Additional diagnostic information

### Logs

Logs are stored in the following locations by default:
- **Windows**: `C:\Users\<username>\.synaptipy\logs\`
- **macOS/Linux**: `~/.synaptipy/logs/`

You can specify a custom log directory with:

#### Windows
```cmd
synaptipy-gui --log-dir C:\custom\path\to\logs
```

#### macOS/Linux
```bash
synaptipy-gui --log-dir /custom/path/to/logs
```

## Legacy Screenshots
*Note: These are older screenshots from previous versions. The current version features:*
- Modern welcome screen with brain icon
- Improved UI styling and theme consistency
- Enhanced analysis tools and visualization
- Better cross-platform compatibility

![Legacy Screenshot 1](https://github.com/user-attachments/assets/4c379633-59b2-4f8b-aa5f-db0ea24eed91)
![Legacy Screenshot 2](https://github.com/user-attachments/assets/a1c35c20-f697-4a17-b1ea-62282b184c1d)
![Legacy Screenshot 3](https://github.com/user-attachments/assets/1ff65828-8d09-4992-b7a7-b4fda0e8cdbc)
![Legacy Screenshot 4](https://github.com/user-attachments/assets/03bf9064-e745-4913-a08d-39bb72d4d94e)

**Current Version Features:**
- ✅ Intelligent cross-platform styling
- ✅ Welcome screen with loading progress
- ✅ Consistent theme throughout application
- ✅ Improved startup performance
- ✅ Windows, macOS, and Linux support
