# Synaptipy 🧠

**Electrophysiology Visualization Suite** - Now available on Windows, macOS, and Linux! 🖥️ 🍎 🐧

[![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-brightgreen)](https://github.com/anzalks/synaptipy)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](https://opensource.org/licenses/AGPL-3.0)

## 🚀 **NEW: One-Command Installation!**

**Synaptipy now automatically handles ALL dependencies including Qt6 system libraries!**

```bash
# Single command installation - everything is handled automatically!
pip install -e .
```

✅ **No more manual Qt6 installation**  
✅ **No more dependency conflicts**  
✅ **Works on Windows, macOS, and Linux**  
✅ **Automatic environment detection and setup**

## ✨ Features

### 🧬 **Core Functionality**
- **Multi-format Support**: ABF, WCP, NWB, and more via Neo library
- **Interactive Visualization**: Real-time data exploration with PyQtGraph
- **Advanced Analysis**: Event detection, spike analysis, input resistance, RMP
- **Export Capabilities**: CSV, NWB, and custom formats

### 🎨 **User Experience**
- **Welcome Screen**: Beautiful loading interface with progress tracking
- **Smooth Transitions**: Seamless navigation between components
- **Brain Icon**: Neuroscience-themed visual identity 🧠
- **Progress Indicators**: Real-time loading status and feedback

### 🌍 **Intelligent Cross-Platform Styling**
- **Auto-detects system theme** (light/dark mode)
- **Native styling** for each operating system
- **White plot backgrounds** for optimal data visualization
- **No theme conflicts** - preserves system appearance
- **Consistent UI** across all platforms

### 🔧 **Developer Experience**
- **Modular Architecture**: Clean separation of concerns
- **Comprehensive Testing**: Unit tests for all components
- **Type Hints**: Full Python type annotation support
- **Documentation**: Extensive API and user guides

## 📦 Installation

### 🚀 **One-Command Installation (Recommended)**

```bash
# Clone the repository
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy

# Single command installation - everything is automatic!
pip install -e .
```

**That's it!** The setup automatically:
1. ✅ Installs all Python dependencies
2. ✅ Detects your operating system
3. ✅ Installs Qt6 system libraries
4. ✅ Ensures full GUI functionality

### 🔧 **Alternative: Conda Environment (Advanced Users)**

```bash
# Create environment
conda create -n synaptipy python=3.9
conda activate synaptipy

# Install Qt6 dependencies
conda install -c conda-forge qt pyside6 pyqtgraph

# Install Synaptipy
pip install -e .
```

## 🚀 Quick Start

### **Launch GUI Application**
```bash
# After installation, simply run:
synaptipy-gui
```

### **Programmatic Usage**
```python
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

# Load data
adapter = NeoAdapter()
recording = adapter.read_file("your_data.abf")

# Analyze
print(f"Loaded {len(recording.channels)} channels")
print(f"Duration: {recording.duration:.2f} seconds")
```

## 🖥️ **Cross-Platform Commands**

### **Windows**
```cmd
# Command Prompt
synaptipy-gui

# PowerShell
synaptipy-gui

# With conda
conda run -n synaptipy synaptipy-gui
```

### **macOS**
```bash
# Terminal
synaptipy-gui

# With conda
conda run -n synaptipy synaptipy-gui

# Python module
python -m Synaptipy.application
```

### **Linux**
```bash
# Terminal
synaptipy-gui

# With conda
conda run -n synaptipy synaptipy-gui

# Python module
python -m Synaptipy.application
```

## 📊 Screenshots

### **Welcome Screen**
*Beautiful loading interface with brain icon and progress tracking*

### **Main Interface**
*Clean, modern UI with system-native styling*

### **Analysis Tools**
*Comprehensive electrophysiology analysis capabilities*

*Note: New screenshots will be added as features are developed*

## 📚 Documentation

- **[User Guide](docs/user_guide.md)**: Complete user manual
- **[API Reference](docs/api_reference.md)**: Developer documentation
- **[Developer Guide](docs/developer_guide.md)**: Contributing guidelines
- **[Styling Guide](docs/development/styling_guide.md)**: UI/UX standards

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run GUI tests
pytest tests/application/gui/
```

## 🔧 Development Mode

### **Windows**
```cmd
# Activate environment
conda activate synaptipy

# Install in development mode
pip install -e .

# Run tests
pytest
```

### **macOS/Linux**
```bash
# Activate environment
conda activate synaptipy

# Install in development mode
pip install -e .

# Run tests
pytest
```

## 📝 Logs

### **Default Log Locations**
- **Windows**: `%USERPROFILE%\AppData\Local\synaptipy\logs\`
- **macOS**: `~/Library/Logs/synaptipy/`
- **Linux**: `~/.local/share/synaptipy/logs/`

### **Custom Log Directory**
```python
import logging
from Synaptipy.shared.logging_config import setup_logging

# Set custom log directory
setup_logging(log_dir="/path/to/custom/logs")
```

## 🆘 Troubleshooting

### **Theme/Styling Issues**
- **Problem**: UI looks different than expected
- **Solution**: The app automatically uses your system's native theme
- **Note**: Plots always have white backgrounds for optimal visualization

### **Startup Issues**
- **Problem**: App doesn't start or crashes
- **Solution**: Check logs in the default location
- **Note**: First run may take longer due to Qt6 installation

### **Performance Issues**
- **Problem**: Slow loading or unresponsive UI
- **Solution**: Ensure you have sufficient RAM (4GB+ recommended)
- **Note**: Large files (>100MB) may take time to load

### **Qt6/File Operation Issues**
- **Problem**: File dialogs don't work or GUI is broken
- **Solution**: The setup automatically installs Qt6 - if issues persist, run:
  ```bash
  conda install -c conda-forge qt pyside6 pyqtgraph
  ```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) and [Development Guide](docs/developer_guide.md).

### **Development Setup**
```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
pip install -e ".[dev]"
pytest
```

## 📄 License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Neo library** for multi-format electrophysiology data support
- **PySide6** for modern Qt6-based GUI framework
- **PyQtGraph** for high-performance scientific plotting
- **NWB** community for standardized data format support

## 📊 Supported File Formats

- **ABF** (Axon Binary Format) - via Neo
- **WCP** (WinWCP) - via Neo
- **NWB** (Neurodata Without Borders) - via PyNWB
- **HDF5** - via Neo
- **MAT** (MATLAB) - via Neo
- **And more** - any format supported by Neo library

## 💡 Usage Examples

### **Basic Data Loading**
```python
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

adapter = NeoAdapter()
recording = adapter.read_file("experiment.abf")
print(f"Channels: {len(recording.channels)}")
```

### **Event Detection**
```python
from Synaptipy.core.analysis.event_detection import EventDetector

detector = EventDetector()
events = detector.detect_events(recording.channels[0])
print(f"Detected {len(events)} events")
```

### **Export to NWB**
```python
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

exporter = NWBExporter()
exporter.export_recording(recording, "output.nwb")
```

---

**Status: Active Development** 🚀

*Synaptipy is actively developed and maintained. New features and improvements are added regularly.*

**What's New in Current Version:**
- ✅ **One-command installation** with automatic Qt6 handling
- ✅ **Cross-platform compatibility** (Windows, macOS, Linux)
- ✅ **Intelligent system theme detection** and native styling
- ✅ **Welcome screen** with progress tracking
- ✅ **Automatic dependency resolution** and conflict prevention
- ✅ **Comprehensive error handling** and user feedback

---

*For questions, issues, or contributions, please visit our [GitHub repository](https://github.com/anzalks/synaptipy).*
