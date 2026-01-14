# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_submodules

project_root = os.path.abspath('.')

# Data folders to include (relative source -> target folder inside bundle)
datas = [
    (os.path.join(project_root, 'Icons'), 'Icons'),
    (os.path.join(project_root, 'Module-Effects'), 'Module-Effects'),
    (os.path.join(project_root, 'Modulos'), 'Modulos'),
]

# If you have an .ico file for the exe, include it by filename here (optional)
icon_file = os.path.join(project_root, 'icon.ico')
if not os.path.exists(icon_file):
    icon_file = None

# Collect hidden imports that PyInstaller sometimes misses
hidden_imports = []
# Common dynamic imports used by this project
hidden_imports += collect_submodules('google') if 'google' in sys.modules or os.path.isdir('google') else ['google.protobuf']
hidden_imports += ['psutil', 'scapy.all', 'zstandard']

block_cipher = None

a = Analysis(
    ['gui_app.py'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='BPSR-Module-Optimizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='BPSR-Module-Optimizer',
)
