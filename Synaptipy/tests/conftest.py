import pytest
from PySide6 import QtWidgets
import sys

# Make sure src directory is included for imports if running pytest from root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.application.gui.main_window import MainWindow
from pathlib import Path


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
    # Cleanup (if needed): window.close()

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
    # !! Replace with the actual name of your small test ABF file !!
    # !! Ensure this file exists in tests/data/ !!
    file_path = test_data_dir / "sample_axon.abf"
    if not file_path.exists():
         pytest.skip(f"Test data file not found: {file_path}") # Skip test if data is missing
    return file_path

# Add fixtures for other file types (.smr, .nex etc.) if you have test data for them