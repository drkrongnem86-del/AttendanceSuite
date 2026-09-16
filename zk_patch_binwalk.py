"""Patch binwalk to support Python 3.12 (imp module removed)"""
import os
import sys

paths = [
    r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/core/plugin.py',
    r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/core/common.py',
    r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/core/compat.py',
]

for p in paths:
    if not os.path.exists(p):
        print(f"SKIP: {p} not found")
        continue
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    original = content
    # Replace `import imp` with Python 3.12 compatible version
    if 'import imp\n' in content or 'import imp\r\n' in content:
        content = content.replace('import imp\n', 'try:\n    import imp\nexcept ImportError:\n    import importlib as imp\n')
        content = content.replace('import imp\r\n', 'try:\r\n    import imp\r\nexcept ImportError:\r\n    import importlib as imp\r\n')
    # Some lines use imp.find_module / imp.load_module - leave those, the importlib fallback provides them via shim
    # Replace `imp.find_module` calls with importlib equivalents is risky; we'll use a compatibility shim
    shim = """
# --- Python 3.12 compat shim for binwalk ---
try:
    import imp
except ImportError:
    import importlib
    class _ImpShim:
        @staticmethod
        def find_module(name, path=None):
            try:
                spec = importlib.util.find_spec(name)
                if spec is None:
                    return None
                return (None, spec.origin, ('', '', 0)) if spec.origin else (None, '', ('', '', 0))
            except (ImportError, ValueError, AttributeError):
                return None

        @staticmethod
        def load_module(name, file=None, pathname=None, description=None):
            return importlib.import_module(name)

        PY_SOURCE = 1
        PY_COMPILED = 2
        C_EXTENSION = 3
    imp = _ImpShim()
"""
    if 'Python 3.12 compat shim' not in content:
        # Insert shim after imports
        if 'import imp\n' in content:
            content = content.replace('import imp\n', 'try:\n    import imp\nexcept ImportError:\n    pass\n' + shim)
    if content != original:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"PATCHED: {p}")
    else:
        print(f"NO CHANGE: {p}")

print("Done")