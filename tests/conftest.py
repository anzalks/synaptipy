import os
import pytest

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