import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock


def pytest_ignore_collect(collection_path, config):
    """
    Hook to ignore files/directories during collection.
    Explicitly ignore .DS_Store to prevent PermissionError on macOS.
    """
    if collection_path.name == '.DS_Store':
        return True
    # Also ignore .git and generic system folders
    if collection_path.name in ['.git', '.idea', '__pycache__']:
        return True
    return None


# --- Fixtures for test_main_window.py ---

@pytest.fixture
def main_window(qtbot):
    """Create a MainWindow instance for testing."""
    from Synaptipy.application.gui.main_window import MainWindow
    
    # Create main window
    window = MainWindow()
    qtbot.addWidget(window)
    
    return window


# --- Fixtures for test_neo_adapter.py ---

@pytest.fixture
def neo_adapter_instance():
    """Create a NeoAdapter instance for testing."""
    from Synaptipy.infrastructure.file_readers import NeoAdapter
    return NeoAdapter()


@pytest.fixture
def sample_abf_path():
    """Path to a sample ABF file for testing."""
    # Look for sample files in the examples/data directory
    project_root = Path(__file__).parent
    examples_dir = project_root / "examples" / "data"
    sample_files = list(examples_dir.glob("*.abf"))
    
    if sample_files:
        return sample_files[0]
    
    # Fallback: create a pytest skip if no sample file exists
    pytest.skip("No sample ABF file found in examples/data directory")