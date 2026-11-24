# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 6.x compatible spec file.
# Removed: block_cipher / cipher (removed in 6.0), win_no_prefer_redirects,
# win_private_assemblies (removed in 6.0), a.zipfiles in COLLECT (removed in 6.0).
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os
import platform
import re
import sys

# Read project version from pyproject.toml so the macOS bundle version stays
# in sync automatically without manual edits after each release bump.
# SPECPATH is the directory of the spec file (already the repo root); do NOT
# call os.path.dirname() on it or we would look one level above the repo.
_PYPROJECT = os.path.join(os.path.abspath(SPECPATH), "pyproject.toml")
with open(_PYPROJECT, encoding="utf-8") as _f:
    _match = re.search(r'^version\s*=\s*"([^"]+)"', _f.read(), re.MULTILINE)
_APP_VERSION = _match.group(1) if _match else "0.0.0"

_IS_DARWIN = sys.platform == "darwin"
# UPX corrupts Mach-O code signatures on macOS and PySide6/Qt6 shared-library
# headers on Windows (0xC0000409) and Linux (SIGABRT 134); Inno Setup (lzma2)
# and AppImage (mksquashfs) already compress the packaged bundles natively.
_USE_UPX = False
# Pin Mach-O slice architecture on macOS so universal2 Python/Qt binaries are
# thinned to match single-arch scientific wheels (arm64 vs x86_64), preventing
# silent architecture-mismatch crashes on launch.
_TARGET_ARCH = (os.environ.get("SYNAPTIPY_TARGET_ARCH") or platform.machine()) if _IS_DARWIN else None


def _safe_collect_submodules(pkg_name):
    try:
        return [
            mod
            for mod in collect_submodules(pkg_name)
            if ".tests." not in mod
            and not mod.endswith(".tests")
            and not mod.startswith("pyqtgraph.examples")
        ]
    except Exception:
        return []


def _safe_collect_data_files(pkg_name):
    try:
        return collect_data_files(pkg_name)
    except Exception:
        return []


# Collect hidden imports for dynamic imports.
# Note: pyqtgraph, neo, and pynwb all use plugin/registry patterns and require
# collect_submodules to enumerate their subpackages.  hdmf uses dynamic type
# registration (TypeMap) at import time; dask uses lazy top-level imports that
# the bytecode scanner does not follow without explicit collection.
hiddenimports = [
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_pdf",
    "matplotlib.backends.backend_svg",
]
for _pkg in (
    "pyqtgraph",
    "neo",
    "quantities",
    "scipy",
    "h5py",
    "pynwb",
    "hdmf",
    "dask",
    "ruamel",
    "tzlocal",
    "jsonschema",
    "jsonschema_specifications",
    "referencing",
    "pyabf",
):
    hiddenimports += _safe_collect_submodules(_pkg)
# Ensure every runtime synaptipy module is available for dynamically imported
# bundled/user plugins (~/.synaptipy/plugins) while omitting copy-only templates.
hiddenimports += [
    _mod
    for _mod in _safe_collect_submodules("synaptipy")
    if not _mod.startswith("synaptipy.templates")
]

# Include user-facing local resources while excluding Sphinx build caches and
# internal development reports.  The rendered HTML manual and QtHelp (.qhc/.qch)
# archives remain available offline in the desktop bundle.
datas = []
_RESOURCE_ROOT = os.path.join("src", "synaptipy", "resources")
_RESOURCE_EXCLUDED_PARTS = {".doctrees", "_sources", "_modules", "development_logs", "decisions", "__pycache__"}
for _root, _dirs, _files in os.walk(_RESOURCE_ROOT):
    _dirs[:] = [d for d in _dirs if d not in _RESOURCE_EXCLUDED_PARTS]
    for _filename in _files:
        if _filename.endswith((".pyc", ".pyo")) or _filename == ".DS_Store":
            continue
        _source = os.path.join(_root, _filename)
        _relative_parent = os.path.relpath(_root, _RESOURCE_ROOT)
        _destination = os.path.join("synaptipy", "resources", _relative_parent)
        datas.append((_source, _destination))
# Example plugins shipped in-repo -- consumed via _get_bundled_plugin_dir() in
# frozen builds; walk explicitly so __pycache__/.pyc files are never bundled.
_PLUGINS_ROOT = os.path.join("examples", "plugins")
if os.path.isdir(_PLUGINS_ROOT):
    for _filename in sorted(os.listdir(_PLUGINS_ROOT)):
        if _filename.endswith(".py") and _filename != "__init__.py":
            datas.append(
                (
                    os.path.join(_PLUGINS_ROOT, _filename),
                    os.path.join("synaptipy", "examples", "plugins"),
                )
            )
for _data_pkg in ("pynwb", "hdmf", "neo", "jsonschema_specifications", "tzdata"):
    datas += _safe_collect_data_files(_data_pkg)

# Determine appropriate icon based on OS
icon_ext = ".icns" if _IS_DARWIN else ".ico"
icon_path = os.path.join("src", "synaptipy", "resources", "icons", f"logo{icon_ext}")

# Exclude pure developer, linter, test, documentation, and unused GUI-binding
# packages present in the CI build environment while keeping full scipy/numpy
# scientific subpackages bundled for custom user plugins (~/.synaptipy/plugins).
_EXCLUDED_MODULES = [
    "tkinter",
    "_tkinter",
    "pytest",
    "_pytest",
    "pytestqt",
    "pytest_cov",
    "pytest_mock",
    "pytest_timeout",
    "xdist",
    "execnet",
    "nbval",
    "flake8",
    "pycodestyle",
    "pyflakes",
    "mccabe",
    "black",
    "blib2to3",
    "isort",
    "sphinx",
    "sphinx_rtd_theme",
    "myst_parser",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "sphinx_design",
    "docutils",
    "alabaster",
    "snowballstemmer",
    "imagesize",
    "IPython",
    "ipykernel",
    "jupyter_client",
    "jupyter_core",
    "nbformat",
    "notebook",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "wx",
]

a = Analysis(
    ["src/synaptipy/application/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDED_MODULES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="synaptipy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=_USE_UPX,
    console=False,
    disable_windowed_traceback=False,
    target_arch=_TARGET_ARCH,
    codesign_identity="-" if _IS_DARWIN else None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=_USE_UPX,
    upx_exclude=[],
    name="synaptipy",
)

if _IS_DARWIN:
    app = BUNDLE(
        coll,
        name="Synaptipy.app",
        version=_APP_VERSION,
        icon=icon_path if os.path.exists(icon_path) else None,
        bundle_identifier="com.anzalks.synaptipy",
        info_plist={
            "NSPrincipalClass": "NSApplication",
            "NSRequiresAquaSystemAppearance": False,
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
            "CFBundleName": "Synaptipy",
            "CFBundleDisplayName": "Synaptipy",
            "CFBundleShortVersionString": _APP_VERSION,
            "CFBundleVersion": _APP_VERSION,
            "CFBundlePackageType": "APPL",
            "CFBundleIconFile": "logo.icns",
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Electrophysiology Recording",
                    "CFBundleTypeRole": "Viewer",
                    "LSHandlerRank": "Alternate",
                    "CFBundleTypeExtensions": [
                        "abf",
                        "nwb",
                        "wcp",
                        "smr",
                        "smrx",
                        "edf",
                        "bdf",
                        "axgx",
                        "axgd",
                        "cfs",
                        "dat",
                        "ibw",
                        "h5",
                        "hdf5",
                    ],
                }
            ],
        },
    )
