# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for AttendanceSuite Launcher

block_cipher = None

a = Analysis(
    ['attendance_suite.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('attendance_web.py', '.'),
        ('punch_simulator.py', '.'),
        ('remote_punch_service.py', '.'),
        ('config.json', '.'),
        ('devices.csv', '.'),
        ('launcher.html', '.'),
    ],
    hiddenimports=[
        'zk', 'zk.base', 'zk.const', 'zk.terminal', 'zk.exception',
        'http.server', 'socketserver', 'csv', 'json', 'urllib.parse',
        'struct', 'threading', 'shutil', 'subprocess', 'webbrowser',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AttendanceSuite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='AttendanceSuite',
)
