# Synaptipy

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

Synaptipy is a multi-channel electrophysiology visualization and analysis toolkit designed for neuroscience and electrophysiology researchers. It provides a user-friendly interface for exploring, analyzing, and exporting electrophysiological data.

![Synaptipy Screenshot](docs/images/synaptipy_screenshot.png)

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
- **Consistent UI & Styling**:
  - Centralized styling system for visual consistency
  - Dark mode support with PyQtGraph integration
  - Theme-based customization
- **Extensible Architecture**: Easy to add new analysis methods or file format support

## Installation

### Prerequisites

- Python 3.9 or later
- pip or conda package manager

### Installing from PyPI

```bash
pip install synaptipy
```

### Installing from Source

```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
pip install .
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

### GUI Application

After installation, run the application:

```bash
# Using installed entry point
synaptipy-gui

# Or using the Python module
python -m Synaptipy
```

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

## Testing

Run the test suite with:

```bash
python scripts/run_tests.py
```

Or run specific tests:

```bash
python scripts/run_tests.py --verbose --test test_main_window
```

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

## Usage

### Running the Application

Run the GUI application from your terminal:

```bash
synaptipy-gui
```

### Development Mode

For more detailed logging and debugging information, run in development mode:

```bash
synaptipy-gui --dev
```

You can also set the environment variable `SYNAPTIPY_DEV_MODE=1` to achieve the same effect:

```bash
# Linux/macOS
SYNAPTIPY_DEV_MODE=1 synaptipy-gui

# Windows (PowerShell)
$env:SYNAPTIPY_DEV_MODE=1; synaptipy-gui
```

Development mode provides:
- Detailed logging output (file + console)
- Function call tracing for debugging
- Additional diagnostic information

### Logs

Logs are stored in `~/.synaptipy/logs/` by default. You can specify a custom log directory with:

```bash
synaptipy-gui --log-dir /custom/path/to/logs
```

## Screen grabs
![Screenshot 2025-04-07 at 12 55 35](https://github.com/user-attachments/assets/4c379633-59b2-4f8b-aa5f-db0ea24eed91)
![Screenshot 2025-04-07 at 12 56 11](https://github.com/user-attachments/assets/a1c35c20-f697-4a17-b1ea-62282b184c1d)
![Screenshot 2025-04-07 at 12 56 28](https://github.com/user-attachments/assets/1ff65828-8d09-4992-b7a7-b4fda0e8cdbc)
![Screenshot 2025-04-07 at 12 57 09](https://github.com/user-attachments/assets/03bf9064-e745-4913-a08d-39bb72d4d94e)
