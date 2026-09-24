# PyInstaller spec for AttendanceSuite Launcher (v2.0.13 style)
# Build: pyinstaller --noconfirm build_attendance_suite.spec
# Output: dist/AttendanceSuite-v{VERSION}-Launcher.exe (onefile)
#
# Entry point: attendance_launcher.py
#   - Wraps attendance_web.py (v2.6.11 backend) in-process via threading
#   - Opens native pywebview window pointing to launcher.html
#   - Single-instance lock + auto port cleanup
#
# Project paths use abspath(__file__) so this spec works on any CI/local machine.

import sys, os
block_cipher = None

# Project paths - relative to this spec file
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_DIR = SPEC_DIR

# Assets to include (data files)
#   attendance_web.py  - the v2.6.11 backend server (started in-process by launcher)
#   launcher.html      - UI loaded by pywebview via http://localhost:8080/launcher.html
#   templates/         - all backend HTML pages (all_links, attlog_tools, inject, etc.)
#   devices.csv        - device list (27 attendance + virtual devices)
#   config.json        - backend config (if present)
datas = [
    ('attendance_web.py', '.'),
    ('launcher.html', '.'),
    ('devices.csv', '.'),
    ('config.json', '.'),
    ('templates', 'templates'),
    ('inject_routes.py', '.'),
    ('security_routes.py', '.'),
]

# Hidden imports
#   zk.*        - pyzk for ZK device communication (port 4370)
#   webview.*   - pywebview native window (uses Win32 API via pythonnet)
#   pystray     - system tray icon (used for tray mode, also referenced by spec v2.0.13)
#   PIL         - for tray icon image
#   openpyxl    - backend dependency for Excel reports
hiddenimports = [
    'zk', 'zk.base', 'zk.const', 'zk.attendance', 'zk.user', 'zk.finger', 'zk.exception',
    'webview', 'webview.platforms.winforms', 'webview.platforms.edgechromium',
    'pythonnet', 'clr_loader', 'clr_loader.runtime',
    'certifi', 'charset_normalizer', 'idna', 'urllib3', 'requests',
    'sqlite3', 'gzip', 'tarfile',
    'pystray', 'PIL', 'PIL.Image',
    'openpyxl',
]

a = Analysis(
    ['attendance_launcher.py'],
    pathex=[PROJECT_DIR],
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

# Output name follows GH Actions convention: AttendanceSuite-v{VERSION}-Launcher.exe
# On local builds (no env var), falls back to AttendanceSuite-Launcher.exe
_VERSION = os.environ.get('ATTENDANCE_VERSION', 'local')
_OUTPUT_NAME = f'AttendanceSuite-v{_VERSION}-Launcher' if _VERSION != 'local' else 'AttendanceSuite-Launcher'

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=_OUTPUT_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,         # keep console so user can see [Launcher] logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)