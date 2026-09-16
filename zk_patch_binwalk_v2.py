"""Clean Python 3.12 patch for binwalk - replace 'import imp' line"""
import os
import re

plugin_path = r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/core/plugin.py'

with open(plugin_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Inject shim BEFORE `import imp`
shim = """import os
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

        PY_SOURCE = 1
        PY_COMPILED = 2
        C_EXTENSION = 3
        PKG_DIRECTORY = 5

    imp = _ImpShim()
# --- end shim ---

"""

# Replace just the first `import imp` line with shim + imp availability
new_content = re.sub(
    r'^import imp$',
    shim,
    content,
    count=1,
    flags=re.MULTILINE,
)

if new_content == content:
    print("ERROR: 'import imp' line not found")
else:
    with open(plugin_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Patched plugin.py OK")