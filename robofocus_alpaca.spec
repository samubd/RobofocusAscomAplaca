# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for Robofocus ASCOM Alpaca Driver.

Build the executable with:
    pyinstaller robofocus_alpaca.spec

This will create:
    dist/RobofocusAlpaca/RobofocusAlpaca.exe
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os

# Collect all FastAPI/Uvicorn dependencies
hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'robofocus_alpaca.api.app',
    'robofocus_alpaca.api.routes',
    'robofocus_alpaca.api.gui_api',
    'robofocus_alpaca.api.discovery',
    'robofocus_alpaca.protocol.robofocus_serial',
    'robofocus_alpaca.simulator.mock_serial',
    'robofocus_alpaca.simulator.web_api',
]

# Collect static files (HTML, CSS, JS)
static_files = []
static_dir = os.path.join('robofocus_alpaca', 'static')
if os.path.exists(static_dir):
    for root, dirs, files in os.walk(static_dir):
        for file in files:
            file_path = os.path.join(root, file)
            # Destination path in the bundle
            dest_path = os.path.dirname(file_path)
            static_files.append((file_path, dest_path))

a = Analysis(
    ['robofocus_alpaca/__main__.py'],
    pathex=[],
    binaries=[],
    datas=static_files,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RobofocusAlpaca',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keep console window for logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RobofocusAlpaca',
)
