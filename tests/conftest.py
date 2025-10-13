import pytest
from PySide6 import QtWidgets
import sys
from pathlib import Path

# Make sure src directory is included for imports if running pytest from root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.application.gui.main_window import MainWindow


@pytest.fixture(scope="session")
def neo_adapter_instance():
    """Provides a reusable instance of NeoAdapter for tests."""
    return NeoAdapter()

@pytest.fixture(scope="function") # Use 'function' scope for GUI tests to get a fresh window each time
def qt_app(qapp):
    """
    Provides the QApplication instance.
    'qapp' is a fixture provided by pytest-qt.
    """
    return qapp

@pytest.fixture(scope="function")
def main_window(qtbot):
    """
    Creates an instance of the MainWindow and registers it with qtbot.
    'qtbot' is a fixture from pytest-qt for interacting with Qt widgets.
    """
    window = MainWindow()
    # qtbot.addWidget(window) # Not strictly necessary unless interacting heavily before show()
    yield window # Use yield if cleanup is needed after the test
    
    # Cleanup: Ensure worker thread is properly stopped
    if hasattr(window, 'data_loader_thread') and window.data_loader_thread:
        try:
            # Disconnect signals to prevent any pending operations
            if hasattr(window, 'data_loader') and window.data_loader:
                window.data_loader.data_ready.disconnect()
                window.data_loader.data_error.disconnect()
                window.data_loader.loading_started.disconnect()
                window.data_loader.loading_progress.disconnect()
            
            # Request thread to quit
            window.data_loader_thread.quit()
            
            # Wait for thread to finish (with timeout)
            if not window.data_loader_thread.wait(1000):  # 1 second timeout
                window.data_loader_thread.terminate()
                window.data_loader_thread.wait(500)  # Wait 0.5 more second after terminate
        except Exception as e:
            print(f"Warning: Error during thread cleanup: {e}")
    
    # Close the window
    window.close()

# --- Fixture for Test Data ---
# IMPORTANT: How you manage test data is crucial.
# Option 1: Generate dummy data programmatically (best if possible)
# Option 2: Include very small, non-proprietary sample files in the repo (e.g., in tests/data/)
# Option 3: Download sample data during test setup (more complex)

@pytest.fixture(scope="session")
def test_data_dir():
    """Provides the path to the test data directory."""
    return Path(__file__).parent / "data"

@pytest.fixture(scope="session")
def sample_abf_path(test_data_dir):
    """Provides the path to a sample ABF file for testing."""
    # Try to find the real file first
    file_path = test_data_dir / "sample_axon.abf"
    
    # If the file doesn't exist, try to use a synthetic alternative
    if not file_path.exists():
        try:
            # First try a NIX file (easier to create with Neo)
            nix_path = test_data_dir / "sample_synthetic.nix"
            if nix_path.exists():
                return nix_path
                
            # If no synthetic file exists, try to create one
            from tests.shared.test_data_generation import create_dummy_abf_file
            synthetic_path = test_data_dir / "sample_synthetic.nix"
            if create_dummy_abf_file(synthetic_path):
                return synthetic_path
        except Exception as e:
            pytest.skip(f"Cannot create synthetic test data: {e}")
    
    # If we get here and the file still doesn't exist, skip the test
    if not file_path.exists():
        pytest.skip(f"Test data file not found: {file_path} and could not create synthetic alternative")
    
    return file_path

# Add fixtures for other file types (.smr, .nex etc.) if you have test data for them