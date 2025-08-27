# Synaptipy

Electrophysiology Visualization Suite

## Installation

This package uses a **two-step installation process** that works across all operating systems:

### Step 1: Clone the repository
```bash
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy
```

### Step 2: Install the package
```bash
pip install -e .
```

That's it! The package will be installed in editable mode and ready to use.

## How it works

1. **Environment.yml**: Contains all the conda dependencies with OS-specific packages handled automatically
2. **Pyproject.toml**: Modern Python packaging configuration that handles the package setup
3. **Cross-platform**: Works on Windows, macOS, and Linux without modification

## Prerequisites

- Python 3.9 or higher
- Conda (Anaconda or Miniconda)
- Git

## Usage

After installation, you can:

- Run the GUI: `synaptipy-gui`
- Import in Python: `import Synaptipy`
- Run tests: `python -m pytest`

## Development

For development, the package is installed in editable mode, so changes to the source code are immediately available without reinstalling.

## 🚀 **Cross-Platform Installation**

**This method works on Windows, macOS, and Linux automatically!**

### Prerequisites
- [Anaconda](https://www.anaconda.com/download) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html) installed
- Python 3.11+ (automatically handled by conda)

### **Installation Steps**

```bash
# 1. Create conda environment (handles all OS-specific packages automatically)
conda env create -f environment.yml

# 2. Activate environment
conda activate synaptipy

# 3. Install Synaptipy (only Python packages, system libs already installed)
pip install -e .
```

### **What Happens Automatically:**

- ✅ **Windows**: Installs Visual C++ runtimes, Qt6 system libraries, optimized numpy/scipy
- ✅ **macOS**: Installs system libraries, Qt6 frameworks, optimized scientific packages  
- ✅ **Linux**: Installs system libraries, Qt6 binaries, optimized computing packages

### **Run the Application:**

```bash
# Launch the GUI
synaptipy-gui

# Or run tests
python -m pytest
```

## 🌍 **Cross-Platform Compatibility**

### **Automatic OS-Specific Package Resolution:**
- **Windows**: `ucrt`, `vc`, `vs2015_runtime`, `libclang13`, `libwinpthread`
- **macOS**: `libcxx`, `libcxxabi`, `libobjc`, `libtapi`, `llvm-tools`
- **Linux**: `libstdcxx-ng`, `libgcc-ng`, `libgomp`, `libgfortran-ng`

### **No Manual Configuration Required:**
- Conda automatically detects your OS and installs appropriate packages
- Binary compatibility issues are resolved automatically
- All dependencies are properly linked for your platform

## 📦 **What's Included**

The `environment.yml` file contains all necessary dependencies:

### **Core System (conda):**
- **Python**: 3.11 with optimized runtime
- **Scientific**: numpy 2.0.2, scipy 1.13.1 (MKL-optimized)
- **GUI**: Qt6 6.7.3, PySide6 6.7.3, pyqtgraph 0.13.7
- **System Libraries**: All OS-specific runtimes and dependencies

### **Python Packages (pip):**
- **Data**: neo 0.14.2, pynwb 3.1.2, h5py 3.14.0, pandas 2.3.1
- **Utilities**: attrs 25.3.0, jsonschema 4.25.1, quantities 0.16.2
- **Testing**: pytest, pytest-qt, pytest-mock (via extras_require["dev"])

## 🔧 **Alternative Installation Methods**

### **Development Installation (with test dependencies):**
```bash
conda env create -f environment.yml
conda activate synaptipy
pip install -e ".[dev]"
```

### **Production Installation:**
```bash
conda env create -f environment.yml
conda activate synaptipy
pip install .
```

## 🧪 **Development & Testing**

### **Running Tests:**
```bash
conda activate synaptipy
python -m pytest
```

### **Project Structure:**
```
src/Synaptipy/
├── application/     # GUI and CLI
├── core/           # Analysis and data processing
├── infrastructure/ # File readers and exporters
└── shared/         # Common utilities and styling
```

## 💡 **Why This Method Works for All OS**

1. **Conda Environment**: Handles all system-level dependencies automatically
2. **Channel Priority**: Uses conda-forge for optimized scientific packages
3. **Binary Compatibility**: Ensures Qt6 and PySide6 are properly linked
4. **OS Detection**: Conda automatically installs platform-specific packages
5. **No Manual Steps**: Eliminates the need for OS-specific installation procedures

## 🆘 **Troubleshooting**

### **Common Issues:**
- **"conda command not found"**: Install [Anaconda](https://www.anaconda.com/download) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- **Environment creation fails**: Ensure you have sufficient disk space (2-3GB recommended)
- **Import errors**: Always activate the `synaptipy` environment before running

### **Platform-Specific Notes:**
- **Windows**: May take longer for first-time setup due to larger binary downloads
- **macOS**: Works on Intel and Apple Silicon (M1/M2) automatically
- **Linux**: Compatible with most modern distributions (Ubuntu 18.04+, CentOS 7+, etc.)

## 📄 **License**

MIT License - see LICENSE file for details.

## 👨‍💻 **Author**

Anzal - anzal.ks@gmail.com

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

**🎯 This installation method ensures Synaptipy works identically on Windows, macOS, and Linux with zero manual configuration required!**
