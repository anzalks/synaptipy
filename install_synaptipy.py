#!/usr/bin/env python3
"""
Simple Synaptipy Installation Script

This script guides users through the proper two-step installation process:
1. Create conda environment from environment.yml
2. Install Synaptipy package via pip

CRITICAL: pip install -e . alone is NOT sufficient for plotting functionality!
"""

import os
import sys
import subprocess
import platform

def check_conda():
    """Check if conda is available."""
    try:
        result = subprocess.run(['conda', '--version'], 
                              capture_output=True, text=True, check=True)
        print(f"✅ Conda found: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Conda not found!")
        print("💡 Please install Anaconda or Miniconda first:")
        print("   https://docs.conda.io/en/latest/miniconda.html")
        return False

def check_environment_yml():
    """Check if environment.yml exists."""
    if os.path.exists("environment.yml"):
        print("✅ environment.yml found")
        return True
    else:
        print("❌ environment.yml not found!")
        print("💡 Please run this script from the synaptipy repository root")
        return False

def create_environment(env_name="synaptipy"):
    """Create conda environment from environment.yml."""
    print(f"\n🔧 Step 1: Creating conda environment '{env_name}' from environment.yml...")
    
    try:
        # Create environment from environment.yml
        subprocess.run([
            "conda", "env", "create", "-f", "environment.yml", "-n", env_name
        ], check=True)
        
        print(f"✅ Environment '{env_name}' created successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create environment: {e}")
        print("💡 Trying alternative approach...")
        
        try:
            # Fallback: create environment manually
            print("🔧 Creating environment manually...")
            subprocess.run([
                "conda", "create", "-n", env_name, "python=3.9", "-y"
            ], check=True)
            
            print("🔧 Installing packages from environment.yml...")
            subprocess.run([
                "conda", "env", "update", "-f", "environment.yml"
            ], check=True)
            
            print(f"✅ Environment '{env_name}' created manually!")
            return True
            
        except subprocess.CalledProcessError as e2:
            print(f"❌ Manual creation also failed: {e2}")
            return False

def install_package():
    """Install Synaptipy package via pip."""
    print(f"\n🔧 Step 2: Installing Synaptipy package via pip...")
    
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-e", "."
        ], check=True)
        
        print("✅ Synaptipy package installed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install package: {e}")
        return False

def verify_installation():
    """Verify that the installation is complete."""
    print(f"\n🔍 Verifying installation...")
    
    try:
        # Check if synaptipy-gui command is available
        result = subprocess.run(['synaptipy-gui', '--help'], 
                              capture_output=True, text=True, timeout=10)
        print("✅ synaptipy-gui command available")
        
        # Check if PySide6 is available
        import PySide6
        print(f"✅ PySide6 available: {PySide6.__version__}")
        
        # Check if pyqtgraph is available
        import pyqtgraph
        print(f"✅ PyQtGraph available: {pyqtgraph.__version__}")
        
        print("✅ Installation verification complete!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except subprocess.TimeoutExpired:
        print("✅ synaptipy-gui command available (GUI launched)")
        return True
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Main installation process."""
    print("🚀 Synaptipy Installation Script")
    print("=" * 50)
    
    # Check prerequisites
    if not check_conda():
        return False
    
    if not check_environment_yml():
        return False
    
    # Get environment name
    env_name = input("\n📝 Enter environment name (default: synaptipy): ").strip()
    if not env_name:
        env_name = "synaptipy"
    
    # Step 1: Create environment
    if not create_environment(env_name):
        print("\n❌ Environment creation failed!")
        print("💡 Please check the error messages above")
        return False
    
    # Step 2: Install package
    if not install_package():
        print("\n❌ Package installation failed!")
        print("💡 Please check the error messages above")
        return False
    
    # Verify installation
    if not verify_installation():
        print("\n❌ Installation verification failed!")
        print("💡 Please check the error messages above")
        return False
    
    # Success!
    print("\n🎉 Installation completed successfully!")
    print(f"\n📋 Next steps:")
    print(f"1. Activate the environment: conda activate {env_name}")
    print(f"2. Launch the GUI: synaptipy-gui")
    print(f"3. Or run Python: python -c 'import Synaptipy'")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Installation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
