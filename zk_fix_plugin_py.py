"""Fix binwalk/core/plugin.py header for Python 3.12"""
import os

path = r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/core/plugin.py'

# Read original full content
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the # Core code comment - the file should start with the shim BEFORE that
shim_block = """# Core code for supporting and managing plugins.

import os
import sys

# --- Python 3.12 compat shim (imp module removed in 3.12) ---
try:
    import imp
except ImportError:
    import importlib
    import importlib.util

    class _ImpShim:
        @staticmethod
        def find_module(name, path=None):
            try:
                spec = importlib.util.find_spec(name)
                if spec is None:
                    return None
                origin = getattr(spec, 'origin', None) or ''
                return (None, origin, ('', '', 0))
            except (ImportError, ValueError, AttributeError):
                return None

        @staticmethod
        def load_module(name, file=None, pathname=None, description=None):
            return importlib.import_module(name)

        @staticmethod
        def load_source(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load spec for {name} from {path}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        PY_SOURCE = 1
        PY_COMPILED = 2
        C_EXTENSION = 3
        PKG_DIRECTORY = 5

    imp = _ImpShim()
# --- end shim ---


"""

# Find the start of original content (after the corrupted shim block)
# The original starts with "class Plugin(object):"
idx = content.find('class Plugin(object):')
if idx < 0:
    print("ERROR: 'class Plugin(object):' not found")
else:
    # Get the original class definition and everything after
    original_rest = content[idx:]
    new_content = shim_block + original_rest
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"Rewrote {path} - {len(content)} -> {len(new_content)} bytes")