#!/usr/bin/env python3
"""
Simple installation script for Synaptipy
Uses single environment.yml for cross-platform compatibility
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent


def check_conda():
    """Check if conda is available and working."""
    try:
        result = subprocess.run(
            ["conda", "--version"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        print(f"✅ Conda found: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Conda is not available or not working properly.")
        print("Please install Anaconda or Miniconda first:")
        print("  - Windows: https://docs.conda.io/en/latest/miniconda.html")
        print("  - macOS: https://docs.conda.io/en/latest/miniconda.html")
        print("  - Linux: https://docs.conda.io/en/latest/miniconda.html")
        return False


def check_python_version():
    """Check if Python version is compatible."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        print(f"✅ Python version compatible: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python version {version.major}.{version.minor}.{version.micro} is not compatible.")
        print("Synaptipy requires Python 3.9 or higher.")
        return False


def create_conda_environment(env_name="synaptipy", force=False):
    """Create the conda environment with all dependencies."""
    print(f"\n🔧 Setting up Synaptipy environment...")
    
    # Check if environment already exists
    result = subprocess.run(
        ["conda", "env", "list"], 
        capture_output=True, 
        text=True, 
        check=True
    )
    
    env_exists = env_name in result.stdout
    
    if env_exists and not force:
        print(f"Environment '{env_name}' already exists.")
        response = input("Do you want to update it? (y/N): ").lower().strip()
        if response not in ['y', 'yes']:
            print("Skipping environment update.")
            return True
    
    # Environment file
    env_file = SCRIPT_DIR / "environment.yml"
    if not env_file.exists():
        print(f"❌ Environment file not found: {env_file}")
        return False
    
    try:
        if env_exists:
            print(f"Updating existing environment '{env_name}'...")
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


def install_package(env_name="synaptipy", editable=True):
    """Install the Synaptipy package in the specified environment."""
    print(f"\n📦 Installing Synaptipy package in '{env_name}' environment...")
    
    try:
        # Activate environment and install package
        if editable:
            cmd = ["conda", "run", "-n", env_name, "pip", "install", "-e", "."]
            print("Installing in editable mode...")
        else:
            cmd = ["conda", "run", "-n", env_name, "pip", "install", "."]
            print("Installing in regular mode...")
        
        subprocess.run(cmd, check=True)
        print("✅ Package installation completed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Package installation failed: {e}")
        return False


def verify_installation(env_name="synaptipy"):
    """Verify that the installation was successful."""
    print(f"\n🔍 Verifying installation in '{env_name}' environment...")
    
    try:
        # Test importing the package
        result = subprocess.run([
            "conda", "run", "-n", env_name, "python", "-c", 
            "import Synaptipy; print('✅ Synaptipy imported successfully')"
        ], capture_output=True, text=True, check=True)
        
        print(result.stdout.strip())
        
        # Test the GUI entry point
        result = subprocess.run([
            "conda", "run", "-n", env_name, "python", "-c", 
            "from Synaptipy.application.__main__ import run_gui; print('✅ GUI entry point accessible')"
        ], capture_output=True, text=True, check=True)
        
        print(result.stdout.strip())
        
        print("✅ Installation verification completed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation verification failed: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False


def show_usage_instructions(env_name="synaptipy"):
    """Show instructions for using the installed package."""
    print(f"\n🚀 Synaptipy is now ready to use!")
    print(f"\nTo activate the environment:")
    print(f"  conda activate {env_name}")
    
    print(f"\nTo run the GUI:")
    print(f"  synaptipy-gui")
    print(f"  # or")
    print(f"  python -m Synaptipy.application")
    
    print(f"\nTo run tests:")
    print(f"  pytest tests/")
    
    print(f"\nTo deactivate the environment:")
    print(f"  conda deactivate")


def main():
    """Main installation function."""
    parser = argparse.ArgumentParser(
        description="Simple installation script for Synaptipy"
    )
    parser.add_argument(
        "--env-name", 
        default="synaptipy",
        help="Name of the conda environment (default: synaptipy)"
    )
    parser.add_argument(
        "--force", 
        action="store_true",
        help="Force recreation of existing environment"
    )
    parser.add_argument(
        "--no-editable", 
        action="store_true",
        help="Install package in regular mode (not editable)"
    )
    parser.add_argument(
        "--skip-verify", 
        action="store_true",
        help="Skip installation verification"
    )
    
    args = parser.parse_args()
    
    print("🚀 Synaptipy Installation")
    print("=" * 40)
    
    # Check prerequisites
    if not check_conda():
        sys.exit(1)
    
    if not check_python_version():
        sys.exit(1)
    
    # Create/update conda environment
    if not create_conda_environment(args.env_name, args.force):
        sys.exit(1)
    
    # Install package
    if not install_package(args.env_name, not args.no_editable):
        sys.exit(1)
    
    # Verify installation
    if not args.skip_verify:
        if not verify_installation(args.env_name):
            print("⚠️  Installation verification failed, but the package may still work.")
            print("Try running the application to test functionality.")
    
    # Show usage instructions
    show_usage_instructions(args.env_name)
    
    print(f"\n✅ Installation completed successfully!")
    print(f"Environment: {args.env_name}")


if __name__ == "__main__":
    main()
