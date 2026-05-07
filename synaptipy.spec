# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 6.x compatible spec file.
# Removed: block_cipher / cipher (removed in 6.0), win_no_prefer_redirects,
# win_private_assemblies (removed in 6.0), a.zipfiles in COLLECT (removed in 6.0).
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os
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

# Collect hidden imports for dynamic imports
hiddenimports = []
hiddenimports += collect_submodules("pyqtgraph")
hiddenimports += collect_submodules("neo")
hiddenimports += collect_submodules("quantities")
hiddenimports += collect_submodules("scipy")
hiddenimports += collect_submodules("h5py")
hiddenimports += collect_submodules("pynwb")

# Explicit extras frequently missed by bytecode scanning despite collect_submodules
hiddenimports += [
    "PySide6.QtSvg",
    "PySide6.QtXml",
    "pyqtgraph.graphicsItems",
    "scipy.special",
    "scipy.spatial.transform",
]

# Include our local resources (icons, stylesheets, and compiled Qt Help docs)
datas = [("src/Synaptipy/resources", "Synaptipy/resources")]
# Example plugins shipped in-repo — consumed via EXAMPLES_PLUGIN_DIR in frozen builds
datas += [("examples/plugins", "Synaptipy/examples/plugins")]
datas += collect_data_files("pynwb")
datas += collect_data_files("hdmf")

# Determine appropriate icon based on OS
icon_ext = ".icns" if sys.platform == "darwin" else ".ico"
icon_path = os.path.join("src", "Synaptipy", "resources", "icons", f"logo{icon_ext}")

a = Analysis(
    ["src/Synaptipy/application/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Synaptipy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Synaptipy",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Synaptipy.app",
        icon=icon_path if os.path.exists(icon_path) else None,
        bundle_identifier="com.anzalks.synaptipy",
        info_plist={
            "NSPrincipalClass": "NSApplication",
            "NSHighResolutionCapable": "True",
            "LSBackgroundOnly": "False",
            "CFBundleShortVersionString": _APP_VERSION,
        },
    )
