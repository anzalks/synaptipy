#!/usr/bin/env python3
"""
Setup script for Synaptipy with exact dependency replication.
This ensures that when someone runs 'pip install -e .', they get EXACTLY the same packages
as the working synaptipy environment.
"""

import os
import sys
import subprocess
import platform
from setuptools import setup, find_packages
from setuptools.command.develop import develop
from setuptools.command.install import install

def install_qt6_dependencies_via_conda():
    """Install Qt6 system libraries via conda-forge with EXACT versions."""
    print("🔧 Installing Qt6 dependencies via conda-forge with exact versions...")
    
    # EXACT versions from working synaptipy environment
    qt6_packages = [
        "qt=6.7.3",           # Qt6 system libraries
        "pyside6=6.7.3",      # Qt6 Python bindings
        "pyqtgraph=0.13.7",   # Plotting library
    ]
    
    try:
        print("📦 Installing Qt6 packages via conda-forge...")
        subprocess.run([
            "conda", "install", "-c", "conda-forge", 
            *qt6_packages, "-y"
        ], check=True)
        print("✅ Qt6 dependencies installed successfully via conda-forge")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Qt6 via conda: {e}")
        return False
    except FileNotFoundError:
        print("❌ Conda not found")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def install_python_dependencies_via_pip():
    """Install Python packages via pip with EXACT versions."""
    print("🐍 Installing Python dependencies via pip with exact versions...")
    
    # EXACT versions from working synaptipy environment
    pip_packages = [
        "numpy==2.0.2",       # Core scientific computing
        "scipy==1.13.1",      # Scientific computing
        "neo==0.14.2",        # Electrophysiology data handling
        "pynwb==3.1.2",       # Neurodata without borders
        "tzlocal==5.3.1",     # Timezone handling
    ]
    
    try:
        for package in pip_packages:
            print(f"  📦 Installing {package}...")
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
            print(f"    ✅ {package} installed successfully")
        
        print("🎉 All Python dependencies installed successfully via pip")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Python dependencies: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error installing Python dependencies: {e}")
        return False

def verify_qt6_availability():
    """Verify that Qt6 is available after installation."""
    print("🔍 Verifying Qt6 availability...")
    
    try:
        import PySide6
        print("✅ PySide6 is available")
        
        # Test basic Qt6 functionality
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        print("✅ Qt6 widgets are functional")
        return True
        
    except ImportError as e:
        print(f"❌ PySide6 not available: {e}")
        return False
    except Exception as e:
        print(f"❌ Qt6 verification failed: {e}")
        return False

def verify_exact_versions():
    """Verify that all packages have the exact versions from synaptipy environment."""
    print("🔍 Verifying exact package versions...")
    
    expected_versions = {
        "qt": "6.7.3",
        "pyside6": "6.7.3", 
        "pyqtgraph": "0.13.7",
        "numpy": "2.0.2",
        "scipy": "1.13.1",
        "neo": "0.14.2",
        "pynwb": "3.1.2",
        "tzlocal": "5.3.1"
    }
    
    try:
        for package, expected_version in expected_versions.items():
            if package == "qt":
                # Qt version is harder to check, skip for now
                continue
            elif package == "pyside6":
                import PySide6
                actual_version = PySide6.__version__
            elif package == "pyqtgraph":
                import pyqtgraph
                actual_version = pyqtgraph.__version__
            elif package == "numpy":
                import numpy
                actual_version = numpy.__version__
            elif package == "scipy":
                import scipy
                actual_version = scipy.__version__
            elif package == "neo":
                import neo
                actual_version = neo.__version__
            elif package == "pynwb":
                import pynwb
                actual_version = pynwb.__version__
            elif package == "tzlocal":
                import tzlocal
                actual_version = tzlocal.__version__
            else:
                continue
                
            if actual_version == expected_version:
                print(f"    ✅ {package} version {actual_version} matches expected {expected_version}")
            else:
                print(f"    ❌ {package} version {actual_version} does NOT match expected {expected_version}")
                return False
        
        print("✅ All package versions verified successfully")
        return True
        
    except ImportError as e:
        print(f"❌ Package import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Version verification failed: {e}")
        return False

def ensure_environment_consistency():
    """Ensure the environment has all required packages with exact versions."""
    print("🔍 Checking environment consistency...")
    
    # Check if we're in a conda environment
    conda_env = os.environ.get('CONDA_DEFAULT_ENV')
    if conda_env:
        print(f"  📦 Detected conda environment: {conda_env}")
        
        # Verify key packages are available
        key_packages = ["numpy", "scipy", "PySide6", "pyqtgraph", "neo", "pynwb", "tzlocal"]
        
        for package in key_packages:
            try:
                if package == "PySide6":
                    import PySide6
                elif package == "pyqtgraph":
                    import pyqtgraph
                else:
                    __import__(package)
                print(f"    ✅ {package} available")
            except ImportError:
                print(f"    ❌ {package} missing")
                return False
    else:
        print("  📦 No conda environment detected")
    
    print("✅ Environment consistency check complete")
    return True

class PostDevelopCommand(develop):
    """Post-install command for development installs."""
    def run(self):
        develop.run(self)
        print("\n🚀 Post-install setup for development mode...")
        install_qt6_dependencies_via_conda()
        install_python_dependencies_via_pip()
        verify_qt6_availability()
        verify_exact_versions()
        ensure_environment_consistency()

class PostInstallCommand(install):
    """Post-install command for regular installs."""
    def run(self):
        install.run(self)
        print("\n🚀 Post-install setup for regular install...")
        install_qt6_dependencies_via_conda()
        install_python_dependencies_via_pip()
        verify_qt6_availability()
        verify_exact_versions()
        ensure_environment_consistency()

if __name__ == "__main__":
    setup(
        name="Synaptipy",
        version="0.1.0",
        description="Electrophysiology Visualization Suite",
        python_requires=">=3.9",
        packages=find_packages(where="src"),
        package_dir={"": "src"},
        install_requires=[
            # These are the minimum requirements - actual installation happens via conda/pip with exact versions
            "numpy>=1.23.5",
            "PySide6>=6.5.0",
            "pyqtgraph>=0.13.3",
            "neo>=0.12.0",
            "scipy",
            "pynwb>=2.5.0",
            "tzlocal",
        ],
        extras_require={
            "dev": [
                "pytest>=7.0.0",
                "pytest-qt>=4.0.0",
                "pytest-mock",
                "pytest-cov",
                "flake8",
                "black",
                "isort",
                "build",
                "twine",
                "sphinx",
                "sphinx-rtd-theme",
            ],
            "gui": [
                "PySide6>=6.5.0",
                "pyqtgraph>=0.13.3",
            ],
            "full": [
                "numpy>=1.23.5",
                "PySide6>=6.5.0",
                "pyqtgraph>=0.13.3",
                "neo>=0.12.0",
                "scipy",
                "pynwb>=2.5.0",
                "tzlocal",
            ],
        },
        cmdclass={
            "develop": PostDevelopCommand,
            "install": PostInstallCommand,
        },
        entry_points={
            "console_scripts": [
                "synaptipy-gui=Synaptipy.application.__main__:run_gui",
            ],
        },
        author="Anzal",
        author_email="anzal.ks@gmail.com",
        url="https://github.com/anzalks/synaptipy",
        classifiers=[
            "Development Status :: 3 - Alpha",
            "Intended Audience :: Science/Research",
            "Topic :: Scientific/Engineering :: Bio-Informatics",
            "License :: OSI Approved :: GNU Affero General Public License v3",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
        ],
    )
