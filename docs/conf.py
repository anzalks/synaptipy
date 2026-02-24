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
copyright = "2024, Anzal KS"
author = "Anzal KS"

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
        "Anzal KS",
        "manual",
    ),
]

# ---------------------------------------------------------------------------
# Todo extension
# ---------------------------------------------------------------------------
todo_include_todos = True

# ---------------------------------------------------------------------------
# Screenshot helper — runs at the start of every Sphinx build.
#
# The comprehensive tutorial lives in documents/tutorial.md and references
# images as  screenshots/<name>.png  (relative to that file).  When the
# tutorial is included via MyST's {include} directive from
# docs/tutorial/index.md, Sphinx resolves image paths relative to the
# *including* file, i.e. docs/tutorial/.  We therefore mirror the original
# screenshots folder into docs/tutorial/screenshots/ so that every image
# reference resolves correctly without touching the source tutorial file.
# ---------------------------------------------------------------------------
def setup(app):  # noqa: D103
    import pathlib
    import shutil

    docs_dir = pathlib.Path(__file__).parent
    documents_dir = docs_dir.parent / "documents"

    # ── 1. Sync tutorial content ────────────────────────────────────────────
    # documents/tutorial.md is the canonical source; keep docs/tutorial/index.md
    # up-to-date so Sphinx can find it within its source tree.
    src_tutorial = documents_dir / "tutorial.md"
    dst_tutorial = docs_dir / "tutorial" / "index.md"
    if src_tutorial.exists():
        dst_tutorial.parent.mkdir(parents=True, exist_ok=True)
        if (
            not dst_tutorial.exists()
            or src_tutorial.stat().st_mtime > dst_tutorial.stat().st_mtime
        ):
            shutil.copy2(src_tutorial, dst_tutorial)

    # ── 2. Mirror screenshots into docs/tutorial/screenshots/ ───────────────
    # The tutorial references images as  screenshots/<name>.png  relative to
    # its own file location.  Copying them here keeps paths consistent without
    # modifying the source tutorial.
    src_shots = documents_dir / "screenshots"
    dst_shots = docs_dir / "tutorial" / "screenshots"
    if src_shots.is_dir():
        dst_shots.mkdir(parents=True, exist_ok=True)
        for img in src_shots.glob("*.png"):
            dest_file = dst_shots / img.name
            if not dest_file.exists() or img.stat().st_mtime > dest_file.stat().st_mtime:
                shutil.copy2(img, dest_file)
