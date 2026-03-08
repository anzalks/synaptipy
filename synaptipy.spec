# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_hiddenimports
import os
import sys

block_cipher = None

# Collect hidden imports for dynamic imports
hiddenimports = []
hiddenimports += collect_hiddenimports('pyqtgraph')
hiddenimports += collect_hiddenimports('neo')
hiddenimports += collect_hiddenimports('quantities')
hiddenimports += collect_hiddenimports('scipy')
hiddenimports += collect_hiddenimports('h5py')
hiddenimports += collect_hiddenimports('pynwb')

# Include our local resources
datas = [('src/Synaptipy/resources', 'Synaptipy/resources')]

# Determine appropriate icon based on OS
icon_ext = '.icns' if sys.platform == 'darwin' else '.ico'
icon_path = os.path.join('src', 'Synaptipy', 'resources', 'icons', f'logo{icon_ext}')

a = Analysis(
    ['src/Synaptipy/application/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Synaptipy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Synaptipy',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Synaptipy.app',
        icon=icon_path if os.path.exists(icon_path) else None,
        bundle_identifier='com.anzalks.synaptipy',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'False',
            'CFBundleShortVersionString': '0.1.0',
        },
    )
