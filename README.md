# Synaptipy

Electrophysiology Visualization Suite

## 🚀 **Cross-Platform Installation (Recommended)**

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

- ✅ **Windows**: Installs Visual C++ runtimes, Qt6 system libraries, and all dependencies
- ✅ **macOS**: Installs Qt6 system libraries, system dependencies, and all packages
- ✅ **Linux**: Installs system libraries, Qt6 dependencies, and all packages
- ✅ **All OS**: Creates isolated Python environment with exact package versions

### **Why This Works:**

The `environment.yml` file uses a **minimal conda approach** that:
1. **Creates a basic Python 3.11 environment** with only essential build tools
2. **Installs all scientific packages via pip** to avoid conda version conflicts
3. **Lets pip handle OS-specific binary compatibility** automatically
4. **Avoids complex conda dependency resolution** that can fail on newer OS versions

## 🧪 **Testing Your Installation**

```bash
# Activate the environment
conda activate synaptipy

# Run all tests
python -m pytest

# Run tests with coverage
python -m pytest --cov=Synaptipy
```

## 🖥️ **Running the Application**

```bash
# Activate the environment
conda activate synaptipy

# Start the GUI application
python -m Synaptipy.application

# Or use the console script
synaptipy-gui
```

## 📦 **What's Included**

### **Core Scientific Libraries**
- **NumPy 2.3.2**: Advanced array operations and numerical computing
- **SciPy 1.16.1**: Scientific computing and optimization
- **Pandas 2.3.2**: Data manipulation and analysis
- **Neo 0.14.2**: Electrophysiology data handling
- **PyNWB 3.1.2**: Neurodata Without Borders format support

### **GUI Framework**
- **PySide6 6.9.2**: Modern Qt6-based GUI framework
- **PyQtGraph 0.13.7**: High-performance plotting and visualization
- **Cross-platform compatibility**: Works on Windows, macOS, and Linux

### **Data Processing**
- **H5Py 3.14.0**: HDF5 file format support
- **Quantities 0.16.2**: Physical quantities with units
- **HDMF 4.1.0**: Hierarchical Data Modeling Framework

### **Development Tools**
- **Pytest 8.4.1**: Testing framework
- **Pytest-Qt 4.5.0**: Qt testing support
- **Pytest-Mock**: Mocking support for tests

## 🔧 **Development Setup**

```bash
# Clone the repository
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy

# Install in development mode
conda env create -f environment.yml
conda activate synaptipy
pip install -e .

# Activate environment
conda activate synaptipy

# Run tests
python -m pytest

# Make changes and test
python -m pytest tests/
```

## 🌍 **Cross-Platform Compatibility**

| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| **Python 3.11** | ✅ | ✅ | ✅ |
| **Qt6/PySide6** | ✅ | ✅ | ✅ |
| **Scientific Libraries** | ✅ | ✅ | ✅ |
| **GUI Applications** | ✅ | ✅ | ✅ |
| **File I/O** | ✅ | ✅ | ✅ |
| **Testing** | ✅ | ✅ | ✅ |

## 🚨 **Troubleshooting**

### **Common Issues**

1. **Conda not found**: Install [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
2. **Environment creation fails**: Try `conda env remove -n synaptipy -y` then recreate
3. **Package conflicts**: The minimal environment.yml should avoid most conflicts
4. **macOS version issues**: The pip-based approach handles newer macOS versions better

### **Getting Help**

- **Issues**: [GitHub Issues](https://github.com/anzalks/synaptipy/issues)
- **Documentation**: [docs/](docs/) directory
- **Tests**: Run `python -m pytest` to verify installation

## 📚 **Documentation**

- **[User Guide](docs/user_guide.md)**: Getting started with Synaptipy
- **[API Reference](docs/api_reference.md)**: Complete API documentation
- **[Developer Guide](docs/developer_guide.md)**: Contributing to the project
- **[Styling Guide](docs/development/styling_guide.md)**: UI consistency guidelines

## 🤝 **Contributing**

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) and [Development Guide](docs/developer_guide.md).

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- **Qt6/PySide6**: Modern cross-platform GUI framework
- **Scientific Python Ecosystem**: NumPy, SciPy, Pandas, and more
- **Electrophysiology Community**: For feedback and testing

---

**Made with ❤️ by the Synaptipy Team**
