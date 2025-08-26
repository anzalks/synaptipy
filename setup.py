#!/usr/bin/env python3
"""
Setup for Synaptipy
"""

from setuptools import setup, find_packages

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
    
    # Core dependencies
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
