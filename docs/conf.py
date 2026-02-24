# docs/conf.py
# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
# Add the project src/ directory to sys.path so that autodoc can import the
# package without requiring a full installation.
sys.path.insert(0, os.path.abspath("../src"))

# ---------------------------------------------------------------------------
# Mock heavy / platform-specific import dependencies so that Sphinx autodoc
# can import every module even in a minimal CI / ReadTheDocs build environment
# where PySide6, pyqtgraph, etc. are not installed.
# ---------------------------------------------------------------------------
_MOCK_MODULES = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtOpenGL",
    "pyqtgraph",
    "pyqtgraph.opengl",
    "neo",
    "neo.io",
    "neo.core",
    "neo.rawio",
    "pynwb",
    "h5py",
    "hdmf",
    "quantities",
    "scipy",
    "scipy.signal",
    "scipy.optimize",
    "scipy.stats",
    "pandas",
]

for _mod in _MOCK_MODULES:
    sys.modules[_mod] = MagicMock()

# ---------------------------------------------------------------------------
# Project information
# ---------------------------------------------------------------------------
project = "Synaptipy"
copyright = "2024, Anzal K Shahul"
author = "Anzal K Shahul"

# Retrieve version from the package itself
try:
    from Synaptipy import __version__ as _version  # noqa: E402
    release = _version
    version = ".".join(_version.split(".")[:2])
except Exception:
    version = "0.1"
    release = "0.1.0"

# ---------------------------------------------------------------------------
# General configuration
# ---------------------------------------------------------------------------
extensions = [
    # Core
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",          # Google / NumPy docstring support
    "sphinx.ext.viewcode",          # Add [source] links
    "sphinx.ext.intersphinx",       # Cross-references to external docs
    "sphinx.ext.todo",              # .. todo:: directives
    "sphinx.ext.coverage",          # Coverage checks
    # Third-party
    "myst_parser",                   # Parse .md files with MyST
    "sphinx_autodoc_typehints",     # Render type hints in autodoc
    "sphinx_copybutton",            # Copy-button on code blocks
    "sphinx_design",                # Cards, grids, tabs, etc.
]

# Autosummary: generate stub files automatically
autosummary_generate = True

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_preprocess_types = True
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_attr_annotations = True

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "private-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autoclass_content = "both"

# MyST parser settings
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "html_image",
    "tasklist",
]
myst_heading_anchors = 3

# Source suffixes
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "scipy": ("https://docs.scipy.org/doc/scipy/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
}

# The master toctree document
master_doc = "index"

# Patterns to exclude from documentation build
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Pygments syntax highlighting style
pygments_style = "sphinx"
# Use "none" so code blocks without an explicit language tag are not lexed
# (avoids warnings for ASCII-art / emoji-containing blocks in dev logs)
highlight_language = "none"

# ---------------------------------------------------------------------------
# HTML output options – ReadTheDocs theme
# ---------------------------------------------------------------------------
html_theme = "sphinx_rtd_theme"

html_theme_options = {
    "logo_only": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": True,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

html_context = {
    "display_github": True,
    "github_user": "anzalks",
    "github_repo": "synaptipy",
    "github_version": "main",
    "conf_py_path": "/docs/",
}

# Custom static files (CSS overrides, images, etc.)
html_static_path = ["_static"]

html_css_files = [
    "custom.css",
]

# html_logo = "_static/logo.png"
# html_favicon = "_static/favicon.ico"

html_last_updated_fmt = "%b %d, %Y"

# ---------------------------------------------------------------------------
# LaTeX / PDF output options
# ---------------------------------------------------------------------------
latex_elements: dict = {}
latex_documents = [
    (
        master_doc,
        "Synaptipy.tex",
        "Synaptipy Documentation",
        "Anzal K Shahul",
        "manual",
    ),
]

# ---------------------------------------------------------------------------
# Todo extension
# ---------------------------------------------------------------------------
todo_include_todos = True
