#!/usr/bin/env python3
"""
Setup script for Synaptipy with complete dependency management.
This ensures that when someone runs 'pip install -e .', they get everything needed.
"""

import os
import sys
import subprocess
import platform
from setuptools import setup, find_packages
from setuptools.command.develop import develop
from setuptools.command.install import install

def install_all_dependencies_via_conda():
    """Install ALL dependencies via conda-forge for consistency."""
    print("🔧 Installing ALL dependencies via conda-forge for consistency...")
    
    # All packages that should come from conda-forge (same as working synaptipy env)
    conda_packages = [
        "qt",           # Qt6 system libraries
        "pyside6",      # Qt6 Python bindings
        "pyqtgraph",    # Plotting library
        "numpy",        # Core scientific computing
        "scipy",        # Scientific computing
        "neo",          # Electrophysiology data handling
        "pynwb",        # Neurodata without borders
        "tzlocal",      # Timezone handling
    ]
    
    try:
        print("📦 Installing packages via conda-forge...")
        subprocess.run([
            "conda", "install", "-c", "conda-forge", 
            *conda_packages, "-y"
        ], check=True)
        print("✅ All dependencies installed successfully via conda-forge")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install via conda: {e}")
        print("💡 Falling back to pip installation...")
        return install_dependencies_via_pip()
    except FileNotFoundError:
        print("❌ Conda not found, falling back to pip installation...")
        return install_dependencies_via_pip()
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def install_dependencies_via_pip():
    """Fallback: Install dependencies via pip if conda fails."""
    print("🐍 Installing dependencies via pip (fallback)...")
    
    pip_packages = [
        "numpy>=1.23.5",
        "PySide6>=6.5.0", 
        "pyqtgraph>=0.13.3",
        "neo>=0.12.0",
        "scipy",
        "pynwb>=2.5.0",
        "tzlocal",
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

def ensure_environment_consistency():
    """Ensure the environment has all required packages."""
    print("🔍 Checking environment consistency...")
    
    # Check if we're in a conda environment
    conda_env = os.environ.get('CONDA_DEFAULT_ENV')
    if conda_env:
        print(f"  📦 Detected conda environment: {conda_env}")
        
        # Verify key packages are available
        key_packages = ["numpy", "scipy", "PySide6", "pyqtgraph", "neo", "pynwb"]
        
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
        install_all_dependencies_via_conda()
        verify_qt6_availability()
        ensure_environment_consistency()

class PostInstallCommand(install):
    """Post-install command for regular installs."""
    def run(self):
        install.run(self)
        print("\n🚀 Post-install setup for regular install...")
        install_all_dependencies_via_conda()
        verify_qt6_availability()
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
            # These are the minimum requirements - actual installation happens via conda
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
