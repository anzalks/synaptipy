#!/usr/bin/env python3
"""
Setup script for Synaptipy with exact environment replication.
This ensures that when someone runs 'pip install -e .', they get EXACTLY the same environment
as the working synaptipy environment, just like DeepLabCut does.

CRITICAL: Use environment.yml for full installation to prevent Qt platform plugin errors.
PySide6 versions are pinned to match Qt system libraries exactly (6.7.3).
"""

import os
import sys
import subprocess
import platform
from setuptools import setup, find_packages
from setuptools.command.develop import develop
from setuptools.command.install import install

def install_exact_environment():
    """Install the exact environment from environment.yml (DeepLabCut style)."""
    print("🔧 Installing EXACT environment from environment.yml...")
    
    try:
        # Check if environment.yml exists
        if not os.path.exists("environment.yml"):
            print("❌ environment.yml not found!")
            print("💡 Please ensure you're in the synaptipy repository root")
            return False
        
        print("📦 Installing exact environment via conda...")
        print("🔄 This will install ALL packages with exact versions from working synaptipy env")
        print("🎯 PySide6 versions are pinned to match Qt system libraries (6.7.3)")
        
        # Install the exact environment
        subprocess.run([
            "conda", "env", "update", "-f", "environment.yml"
        ], check=True)
        
        print("✅ Exact environment installed successfully!")
        print("🎯 Your environment now matches the working synaptipy environment exactly")
        print("🔒 PySide6 versions locked to prevent Qt platform plugin errors")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install environment: {e}")
        print("💡 Trying alternative approach...")
        return install_environment_manually()
    except FileNotFoundError:
        print("❌ Conda not found")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def install_environment_manually():
    """Fallback: Install environment manually if conda env update fails."""
    print("🔧 Installing environment manually...")
    
    try:
        # Install Qt6 and core packages via conda-forge
        print("📦 Installing Qt6 and core packages via conda-forge...")
        print("🎯 Note: PySide6 will be installed via pip to ensure version matching")
        conda_packages = [
            "python=3.9.23",
            "qt=6.7.3",
            "pyqtgraph=0.13.7",
            "numpy=2.0.2",
            "scipy=1.13.1",
            "pip=25.1"
        ]
        
        subprocess.run([
            "conda", "install", "-c", "conda-forge", 
            *conda_packages, "-y"
        ], check=True)
        
        # Install pip packages with exact versions
        print("🐍 Installing pip packages with exact versions...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], check=True)
        
        print("✅ Environment installed manually")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Manual installation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def verify_environment():
    """Verify that the environment matches the working synaptipy environment."""
    print("🔍 Verifying environment...")
    
    try:
        # Check Python version
        import sys
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if python_version.startswith("3.9"):
            print(f"✅ Python version: {python_version}")
        else:
            print(f"❌ Python version {python_version} is not 3.9.x")
            return False
        
        # Check key packages
        key_packages = {
            "numpy": "2.0.2",
            "scipy": "1.13.1",
            "PySide6": "6.7.3",
            "pyqtgraph": "0.13.7",
            "neo": "0.14.2",
            "pynwb": "3.1.2",
            "tzlocal": "5.3.1"
        }
        
        for package, expected_version in key_packages.items():
            try:
                if package == "PySide6":
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
                    
            except ImportError as e:
                print(f"    ❌ {package} not available: {e}")
                return False
        
        print("✅ Environment verification complete - all packages match!")
        return True
        
    except Exception as e:
        print(f"❌ Environment verification failed: {e}")
        return False

class PostDevelopCommand(develop):
    """Post-install command for development installs."""
    def run(self):
        develop.run(self)
        print("\n🚀 Post-install setup for development mode...")
        install_exact_environment()
        verify_environment()

class PostInstallCommand(install):
    """Post-install command for regular installs."""
    def run(self):
        install.run(self)
        print("\n🚀 Post-install setup for regular install...")
        install_exact_environment()
        verify_environment()

if __name__ == "__main__":
    setup(
        name="Synaptipy",
        version="0.1.0",
        description="Electrophysiology Visualization Suite",
        python_requires=">=3.9",
        packages=find_packages(where="src"),
        package_dir={"": "src"},
        install_requires=[
            # These are the minimum requirements - actual installation happens via environment.yml
            # PySide6 versions are pinned to match Qt system libraries exactly
            "numpy>=2.0.2",
            "PySide6==6.7.3",  # EXACT VERSION - must match Qt system libraries
            "pyqtgraph>=0.13.7",
            "neo>=0.14.2",
            "scipy>=1.13.1",
            "pynwb>=3.1.2",
            "tzlocal>=5.3.1",
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
                "PySide6==6.7.3",  # EXACT VERSION - must match Qt system libraries
                "pyqtgraph>=0.13.7",
            ],
            "full": [
                "numpy>=2.0.2",
                "PySide6==6.7.3",  # EXACT VERSION - must match Qt system libraries
                "pyqtgraph>=0.13.7",
                "neo>=0.14.2",
                "scipy>=1.13.1",
                "pynwb>=3.1.2",
                "tzlocal>=5.3.1",
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
