import sys
import os
import pytest

# Remove .verify_venv from sys.path to prevent its Python 3.13 scipy
# from shadowing the conda environment's scipy (Python 3.11)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_verify_venv = os.path.join(_project_root, '.verify_venv')
sys.path[:] = [p for p in sys.path if not p.startswith(_verify_venv)]

# Also invalidate any cached scipy imports from the wrong path
for mod_name in list(sys.modules.keys()):
    if mod_name == 'scipy' or mod_name.startswith('scipy.'):
        mod = sys.modules[mod_name]
        if mod is not None and hasattr(mod, '__file__') and mod.__file__ and '.verify_venv' in mod.__file__:
            del sys.modules[mod_name]


def pytest_ignore_collect(collection_path, config):
    """
    Hook to ignore files/directories during collection.
    Explicitly ignore .DS_Store to prevent PermissionError on macOS.
    """
    if collection_path.name == ".DS_Store":
        return True
    if collection_path.name in [".git", ".idea", "__pycache__"]:
        return True
    return None


@pytest.fixture(autouse=True)
def reset_datacache():
    """Ensure DataCache singleton is reset between tests."""
    try:
        from Synaptipy.shared.data_cache import DataCache
        DataCache.reset_instance()
        yield
        DataCache.reset_instance()
    except ImportError:
        yield
