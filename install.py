#!/usr/bin/env python3
"""
Cross-platform installation script for Synaptipy
Works on Windows, macOS, and Linux automatically
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def run_command(command, description, check=True, capture_output=True):
    """Run a command and provide user feedback."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=check, capture_output=capture_output, text=True)
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
        else:
            print(f"⚠️  {description} completed with warnings")
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        return False

def check_conda():
    """Check if conda is available."""
    try:
        result = subprocess.run(["conda", "--version"], capture_output=True, text=True, check=True)
        print(f"✅ Conda found: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def install_synaptipy():
    """Main installation function."""
    print("🚀 Synaptipy Cross-Platform Installation")
    print("=" * 50)
    
    # Detect OS
    os_name = platform.system()
    print(f"🌍 Detected OS: {os_name}")
    
    # Check conda
    if not check_conda():
        print("❌ Conda is not available!")
        print("\n📥 Please install Anaconda or Miniconda first:")
        if os_name == "Windows":
            print("   Windows: https://www.anaconda.com/download")
        elif os_name == "Darwin":  # macOS
            print("   macOS: https://www.anaconda.com/download")
        else:  # Linux
            print("   Linux: https://docs.conda.io/en/latest/miniconda.html")
        print("\nAfter installing conda, restart your terminal and run this script again.")
        return False
    
    # Check if environment already exists
    print("\n🔍 Checking existing environment...")
    result = subprocess.run(["conda", "env", "list"], capture_output=True, text=True, check=True)
    env_exists = "synaptipy" in result.stdout
    
    if env_exists:
        print("📦 Synaptipy environment already exists.")
        print("🔄 Attempting to update environment...")
        
        # Try to update the environment
        if not run_command("conda env update -n synaptipy -f environment.yml", "Updating conda environment"):
            print("\n⚠️  Environment update failed due to package conflicts.")
            print("🔄 Attempting to recreate environment...")
            
            # Remove the old environment
            if not run_command("conda env remove -n synaptipy -y", "Removing old environment"):
                print("❌ Failed to remove old environment. Please remove it manually:")
                print("   conda env remove -n synaptipy -y")
                return False
            
            # Create new environment
            if not run_command("conda env create -f environment.yml", "Creating new conda environment"):
                return False
        else:
            print("✅ Environment updated successfully")
    else:
        print("📦 Creating new Synaptipy environment...")
        if not run_command("conda env create -f environment.yml", "Creating conda environment"):
            return False
    
    # Activate environment and install package
    print("\n📥 Installing Synaptipy package...")
    
    # Use conda run to execute commands in the synaptipy environment
    if not run_command("conda run -n synaptipy pip install -e .", "Installing Synaptipy in development mode"):
        return False
    
    print("\n🎉 Installation completed successfully!")
    print("\n📋 Next steps:")
    print("1. Activate the environment: conda activate synaptipy")
    print("2. Run the GUI: synaptipy-gui")
    print("3. Run tests: python -m pytest")
    
    return True

def main():
    """Main entry point."""
    try:
        success = install_synaptipy()
        if success:
            print("\n✅ Synaptipy is ready to use!")
            sys.exit(0)
        else:
            print("\n❌ Installation failed. Please check the error messages above.")
            print("\n💡 Troubleshooting tips:")
            print("1. Ensure you have sufficient disk space (2-3GB recommended)")
            print("2. Try updating conda: conda update conda")
            print("3. Clear conda cache: conda clean --all")
            print("4. For persistent issues, manually remove the environment:")
            print("   conda env remove -n synaptipy -y")
            print("   Then run this script again.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Installation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
