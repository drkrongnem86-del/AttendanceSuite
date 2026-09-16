"""Patch binwalk for Windows: pwd/grp/os.geteuid modules"""
import os
import re

paths = [
    r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/modules/extractor.py',
    r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/__init__.py',
]

for p in paths:
    if not os.path.exists(p):
        print(f"SKIP: {p}")
        continue
    with open(p, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'Windows compat shim' in content:
        print(f"ALREADY PATCHED: {p}")
        continue

    # Add shim at top after docstring
    shim = """# Windows compat shim - pwd/grp/os.geteuid are POSIX-only
import sys as _sys
try:
    import pwd
except ImportError:
    class _PwdShim:
        @staticmethod
        def getpwuid(uid):
            return ('unknown', 'x', uid, uid, 'unknown', '/', '/bin/sh')
    pwd = _PwdShim()
try:
    import grp
except ImportError:
    class _GrpShim:
        @staticmethod
        def getgrgid(gid):
            return ('unknown', 'x', gid, ['unknown'])
    grp = _GrpShim()
if not hasattr(os, 'geteuid'):
    os.geteuid = lambda: 1
if not hasattr(os, 'getegid'):
    os.getegid = lambda: 1

"""

    # Insert shim after the first triple-quoted docstring or after the imports
    # Simple approach: just prepend
    new_content = shim + content
    with open(p, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"PATCHED: {p}")