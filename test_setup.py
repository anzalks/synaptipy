#!/usr/bin/env python3
"""
Test script to verify Synaptipy setup and dependencies.
Run this after installation to ensure everything is working.
"""

def test_imports():
    """Test that all required modules can be imported."""
    print("🧪 Testing Synaptipy imports...")
    
    try:
        # Test core imports
        print("  📦 Testing core modules...")
        from Synaptipy.core.data_model import Recording, Channel
        from Synaptipy.core.analysis import basic_features, event_detection, intrinsic_properties, spike_analysis
        print("    ✅ Core modules imported successfully")
        
        # Test infrastructure imports
        print("  🔧 Testing infrastructure modules...")
        from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter
        from Synaptipy.infrastructure.exporters.csv_exporter import CSVExporter
        from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
        print("    ✅ Infrastructure modules imported successfully")
        
        # Test shared utilities
        print("  🛠️ Testing shared utilities...")
        from Synaptipy.shared.constants import *
        from Synaptipy.shared.styling import apply_stylesheet, configure_pyqtgraph_globally
        print("    ✅ Shared utilities imported successfully")
        
        # Test GUI components (if available)
        print("  🖥️ Testing GUI components...")
        try:
            from Synaptipy.application.gui.main_window import MainWindow
            from Synaptipy.application.gui.explorer_tab import ExplorerTab
            from Synaptipy.application.gui.analyser_tab import AnalyserTab
            print("    ✅ GUI components imported successfully")
        except ImportError as e:
            print(f"    ⚠️ GUI components not available: {e}")
        
        print("\n🎉 All imports successful! Synaptipy is properly installed.")
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_qt6_availability():
    """Test if Qt6 is available."""
    print("\n🔧 Testing Qt6 availability...")
    
    try:
        import PySide6
        print(f"  ✅ PySide6 available: {PySide6.__version__}")
        
        # Test if we can create a basic Qt application
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        print("  ✅ Qt6 application creation successful")
        
        return True
        
    except ImportError:
        print("  ❌ PySide6 not available")
        return False
    except Exception as e:
        print(f"  ❌ Qt6 test failed: {e}")
        return False

def test_pyqtgraph():
    """Test if PyQtGraph is available."""
    print("\n📊 Testing PyQtGraph availability...")
    
    try:
        import pyqtgraph
        print(f"  ✅ PyQtGraph available: {pyqtgraph.__version__}")
        return True
    except ImportError:
        print("  ❌ PyQtGraph not available")
        return False
    except Exception as e:
        print(f"  ❌ PyQtGraph test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Synaptipy Setup Verification")
    print("=" * 40)
    
    # Test imports
    imports_ok = test_imports()
    
    # Test Qt6
    qt6_ok = test_qt6_availability()
    
    # Test PyQtGraph
    pyqtgraph_ok = test_pyqtgraph()
    
    # Summary
    print("\n📋 Test Summary")
    print("=" * 40)
    print(f"  Core Imports: {'✅ PASS' if imports_ok else '❌ FAIL'}")
    print(f"  Qt6 Support:  {'✅ PASS' if qt6_ok else '❌ FAIL'}")
    print(f"  PyQtGraph:   {'✅ PASS' if pyqtgraph_ok else '❌ FAIL'}")
    
    if all([imports_ok, qt6_ok, pyqtgraph_ok]):
        print("\n🎉 All tests passed! Synaptipy is ready to use.")
        print("   Run 'synaptipy-gui' to launch the application.")
    else:
        print("\n⚠️ Some tests failed. Please check the installation.")
        if not qt6_ok:
            print("   Qt6 issue: Try 'conda install -c conda-forge qt pyside6 pyqtgraph'")
        if not pyqtgraph_ok:
            print("   PyQtGraph issue: Try 'pip install pyqtgraph'")

if __name__ == "__main__":
    main()
