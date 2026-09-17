# PyInstaller spec for AttendanceSuite Launcher
# Build: pyinstaller --noconfirm build_attendance_suite.spec
# Output: dist/AttendanceSuite-v2.0.4.exe (onefile)

import sys, os
block_cipher = None

# Project paths
PROJECT_DIR = r'D:\chamcong\AttendanceSuite_source'
PYTHON_DIR = r'D:\chamcong\AttendanceSuite_Portable\python'

# Add site-packages to path
sys.path.insert(0, os.path.join(PYTHON_DIR, 'Lib', 'site-packages'))

# Assets to include (data files)
datas = [
    ('launcher.html', '.'),
    ('tools.html', '.'),
    ('devices.csv', '.'),
    ('attendance_web.py', '.'),
    ('punch_simulator.py', '.'),
]

# Hidden imports - pyzk, pywebview, etc.
hiddenimports = [
    'zk', 'zk.base', 'zk.const', 'zk.attendance', 'zk.user', 'zk.finger',
    'webview', 'webview.platforms.winforms', 'webview.platforms.edgechromium',
    'pythonnet', 'clr_loader', 'clr_loader.runtime',
    'certifi', 'charset_normalizer', 'idna', 'urllib3', 'requests',
    'sqlite3', 'gzip', 'tarfile',
    'pystray', 'PIL', 'PIL.Image',
]

a = Analysis(
    ['attendance_launcher.py'],
    pathex=[PROJECT_DIR, os.path.join(PYTHON_DIR, 'Lib', 'site-packages')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AttendanceSuite-v2.0.13',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
