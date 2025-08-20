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

def install_qt6_dependencies():
    """Install Qt6 system libraries automatically."""
    print("🔧 Checking Qt6 system libraries...")
    
    try:
        # Try to import PySide6 to see if Qt6 is available
        import PySide6
        print("✅ Qt6 system libraries are already available")
        return True
    except ImportError:
        print("❌ PySide6 not found, will attempt to install Qt6...")
    except Exception as e:
        print(f"⚠️ Qt6 check failed: {e}")
    
    # Determine the platform and install Qt6
    system = platform.system().lower()
    
    try:
        if system == "windows":
            print("🪟 Windows detected - installing Qt6 via conda...")
            # Use conda to install Qt6 (most reliable on Windows)
            subprocess.run([
                "conda", "install", "-c", "conda-forge", 
                "qt", "pyside6", "pyqtgraph", "-y"
            ], check=True)
            print("✅ Qt6 installed successfully via conda")
            
        elif system == "darwin":  # macOS
            print("🍎 macOS detected - installing Qt6 via conda...")
            subprocess.run([
                "conda", "install", "-c", "conda-forge", 
                "qt", "pyside6", "pyqtgraph", "-y"
            ], check=True)
            print("✅ Qt6 installed successfully via conda")
            
        elif system == "linux":
            print("🐧 Linux detected - attempting to install Qt6...")
            # Try conda first, then system package manager
            try:
                subprocess.run([
                    "conda", "install", "-c", "conda-forge", 
                    "qt", "pyside6", "pyqtgraph", "-y"
                ], check=True)
                print("✅ Qt6 installed successfully via conda")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("📦 Conda not available, trying system package manager...")
                # Try common Linux package managers
                for pkg_mgr in ["apt", "yum", "dnf", "pacman", "zypper"]:
                    try:
                        if pkg_mgr == "apt":
                            subprocess.run(["sudo", "apt", "update"], check=True)
                            subprocess.run([
                                "sudo", "apt", "install", "-y", 
                                "qt6-base-dev", "qt6-declarative-dev"
                            ], check=True)
                        elif pkg_mgr == "yum":
                            subprocess.run([
                                "sudo", "yum", "install", "-y", 
                                "qt6-qtbase-devel", "qt6-qtdeclarative-devel"
                            ], check=True)
                        elif pkg_mgr == "dnf":
                            subprocess.run([
                                "sudo", "dnf", "install", "-y", 
                                "qt6-qtbase-devel", "qt6-qtdeclarative-devel"
                            ], check=True)
                        elif pkg_mgr == "pacman":
                            subprocess.run([
                                "sudo", "pacman", "-S", "--noconfirm", 
                                "qt6-base", "qt6-declarative"
                            ], check=True)
                        elif pkg_mgr == "zypper":
                            subprocess.run([
                                "sudo", "zypper", "install", "-y", 
                                "qt6-qtbase-devel", "qt6-qtdeclarative-devel"
                            ], check=True)
                        
                        print(f"✅ Qt6 installed successfully via {pkg_mgr}")
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue
                else:
                    print("❌ Could not install Qt6 via any package manager")
                    print("💡 Please install Qt6 manually or use conda")
                    return False
        else:
            print(f"❓ Unknown platform: {system}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Failed to install Qt6: {e}")
        print("💡 Please install Qt6 manually:")
        print("   - Windows/macOS: conda install -c conda-forge qt pyside6 pyqtgraph")
        print("   - Linux: Use your system package manager or conda")
        return False

class PostDevelopCommand(develop):
    """Post-install command for development installs."""
    def run(self):
        develop.run(self)
        install_qt6_dependencies()

class PostInstallCommand(install):
    """Post-install command for regular installs."""
    def run(self):
        install.run(self)
        install_qt6_dependencies()

if __name__ == "__main__":
    setup(
        name="Synaptipy",
        version="0.1.0",
        description="Electrophysiology Visualization Suite",
        python_requires=">=3.9",
        packages=find_packages(where="src"),
        package_dir={"": "src"},
        install_requires=[
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
