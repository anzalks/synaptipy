#!/usr/bin/env python3
"""
Cross-platform setup for Synaptipy
Handles all dependencies via single environment.yml while preserving source locks and versions
"""

import os
import sys
import subprocess
from pathlib import Path
from setuptools import setup, find_packages
from setuptools.command.develop import develop
from setuptools.command.install import install

# Get the directory containing this setup.py
SETUP_DIR = Path(__file__).parent


def create_conda_environment():
    """Create the conda environment with all dependencies."""
    env_name = "synaptipy"
    
    print("🔧 Setting up Synaptipy environment...")
    
    # Check if conda is available
    try:
        subprocess.run(["conda", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: conda is not available. Please install Anaconda or Miniconda first.")
        print("Visit: https://docs.conda.io/en/latest/miniconda.html")
        sys.exit(1)
    
    # Check if environment already exists
    result = subprocess.run(
        ["conda", "env", "list"], 
        capture_output=True, 
        text=True, 
        check=True
    )
    
    env_exists = env_name in result.stdout
    
    # Environment file
    env_file = SETUP_DIR / "environment.yml"
    if not env_file.exists():
        print(f"❌ Environment file not found: {env_file}")
        return False
    
    try:
        if env_exists:
            print(f"Environment '{env_name}' already exists. Updating...")
            subprocess.run([
                "conda", "env", "update", "-n", env_name, "-f", str(env_file)
            ], check=True)
        else:
            print(f"Creating new environment '{env_name}'...")
            subprocess.run([
                "conda", "env", "create", "-n", env_name, "-f", str(env_file)
            ], check=True)
        
        print(f"✅ Environment '{env_name}' is ready!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create/update environment: {e}")
        return False


class DevelopCommand(develop):
    """Custom develop command that sets up the conda environment."""
    
    def run(self):
        create_conda_environment()
        super().run()


class InstallCommand(install):
    """Custom install command that sets up the conda environment."""
    
    def run(self):
        create_conda_environment()
        super().run()


# Package configuration
setup(
    name="Synaptipy",
    version="0.1.0",
    description="Electrophysiology Visualization Suite",
    author="Anzal",
    author_email="anzal.ks@gmail.com",
    url="https://github.com/anzalks/synaptipy",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    
    # Core dependencies (cross-platform)
    install_requires=[
        "numpy>=2.0.2",
        "pyqtgraph>=0.13.7",
        "neo>=0.14.2",
        "scipy>=1.13.1",
        "pynwb>=3.1.2",
        "tzlocal>=5.3.1",
        "h5py>=3.14.0",
        "hdmf>=4.1.0",
        "jsonschema>=4.25.1",
        "quantities>=0.16.2",
        "referencing>=0.36.0",
        "pandas>=2.3.1",
    ],
    
    # Development dependencies
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
            "pyqtgraph>=0.13.7",
        ],
        "full": [
            "numpy>=2.0.2",
            "pyqtgraph>=0.13.7",
            "neo>=0.14.2",
            "scipy>=1.13.1",
            "pynwb>=3.1.2",
            "tzlocal>=5.3.1",
            "h5py>=3.14.0",
            "hdmf>=4.1.0",
            "jsonschema>=4.25.1",
            "quantities>=0.16.2",
            "referencing>=0.36.0",
            "pandas>=2.3.1",
        ],
    },
    
    # Entry points
    entry_points={
        "console_scripts": [
            "synaptipy-gui=Synaptipy.application.__main__:run_gui",
        ],
    },
    
    # Custom commands
    cmdclass={
        "develop": DevelopCommand,
        "install": InstallCommand,
    },
    
    # Package data
    include_package_data=True,
    package_data={
        "Synaptipy": ["*.yml", "*.yaml", "*.txt"],
    },
    
    # Classifiers
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Visualization",
    ],
    
    # Project URLs
    project_urls={
        "Bug Reports": "https://github.com/anzalks/synaptipy/issues",
        "Source": "https://github.com/anzalks/synaptipy",
        "Documentation": "https://github.com/anzalks/synaptipy/docs",
    },
)
