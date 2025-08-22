# Synaptipy 🧠

**Electrophysiology Visualization Suite** - Now available on Windows, macOS, and Linux! 🖥️ 🍎 🐧

[![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-brightgreen)](https://github.com/anzalks/synaptipy)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](https://opensource.org/licenses/AGPL-3.0)

## 🚀 **NEW: One-Command Installation!**

**Synaptipy now installs everything automatically with a single command!**

```bash
# Single command installation - everything is automatic!
pip install -e .
```

✅ **Automatic environment creation** from environment.yml  
✅ **All Qt6 system libraries** installed automatically  
✅ **All Python packages** with exact versions  
✅ **No more dependency conflicts** - perfect match every time  
✅ **Works on Windows, macOS, and Linux**  

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
1. ✅ **Creates synaptipy environment** from environment.yml
2. ✅ **Installs Qt6 system libraries** (PySide6, Qt6, etc.) via conda
3. ✅ **Installs scientific computing packages** (numpy, scipy, etc.) via conda
4. ✅ **Installs Python packages** (neo, pynwb, etc.) via pip
5. ✅ **Installs Synaptipy package** in development mode
6. ✅ **Ensures binary compatibility** between Qt6 and PySide6
7. ✅ **Makes synaptipy-gui command available**

### 🚀 **What Happens During Installation:**

When you run `pip install -e .`, the setup automatically:

- **🔧 Environment Setup**: Creates `synaptipy` environment from `environment.yml`
- **🎨 Qt6 Installation**: Installs Qt6 system libraries and PySide6 Python bindings
- **🧮 Scientific Computing**: Installs optimized numpy, scipy, and PyQtGraph
- **📦 Python Packages**: Installs neo, pynwb, and other dependencies
- **✅ Verification**: Checks that everything is properly installed and compatible

### 🔧 **Alternative: Manual Environment Creation (Advanced Users)**

If you prefer manual control:

```bash
# Create synaptipy environment manually
conda env create -n synaptipy -f environment.yml

# Activate and install
conda activate synaptipy
pip install -e .
```

## 🚨 **Troubleshooting: PySide6 Issues**

### **Automatic Fix (Recommended)**
The setup now **automatically detects and fixes** PySide6 conflicts:
```bash
pip install -e .  # Automatically removes conflicting packages and installs correct ones
```

### **Why This Happens**
- **pip-installed PySide6**: Causes Qt binary compatibility issues → plotting fails
- **conda-installed PySide6**: Properly linked to Qt system libraries → plotting works
- **Our setup**: Automatically ensures conda installation for compatibility

## 🚀 Quick Start

### **Installation & Launch**
```bash
# 1. Clone and enter repository
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy

# 2. Install everything automatically (creates synaptipy environment)
pip install -e .

# 3. Launch the GUI
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

# With conda (synaptipy environment)
conda run -n synaptipy synaptipy-gui
```

### **macOS**
```bash
# Terminal
synaptipy-gui

# With conda (synaptipy environment)
conda run -n synaptipy synaptipy-gui

# Python module
python -m Synaptipy.application
```

### **Linux**
```bash
# Terminal
synaptipy-gui

# With conda (synaptipy environment)
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
# Install everything automatically
pip install -e .

# Run tests
pytest
```

### **macOS/Linux**
```bash
# Install everything automatically
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
- **Solution**: The setup automatically installs ALL dependencies - if issues persist, run:
  ```bash
  conda env update -n synaptipy -f environment.yml
  ```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) and [Development Guide](docs/developer_guide.md).

### **Development Setup**
```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy

# Install everything automatically (including dev dependencies)
pip install -e ".[dev]"

# Run tests
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
- ✅ **Automatic environment creation** from environment.yml
- ✅ **Cross-platform compatibility** (Windows, macOS, Linux)
- ✅ **Intelligent system theme detection** and native styling
- ✅ **Welcome screen** with progress tracking
- ✅ **Automatic dependency resolution** and conflict prevention
- ✅ **Comprehensive error handling** and user feedback

---

*For questions, issues, or contributions, please visit our [GitHub repository](https://github.com/anzalks/synaptipy).*
