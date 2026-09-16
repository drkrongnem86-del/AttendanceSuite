"""Patch remaining binwalk files for Python 3.12"""
import re

files_to_patch = {
    r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/core/module.py': [
        # Find "import imp" inside `try:` block (line 707)
        (r'\bimport imp\b', 'try:\n    import imp\nexcept ImportError:\n    import importlib as imp'),
    ],
    r'D:/chamcong/AttendanceSuite_Portable/python/Lib/site-packages/binwalk/core/plugin.py': [
        # The shim is already there at line 6 - clean up the redundant import on line 9
        (r'\n    import imp\n', '\n    pass  # imp already provided by shim above\n'),
    ],
}

for path, patches in files_to_patch.items():
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    orig = content
    for pattern, replacement in patches:
        content = re.sub(pattern, replacement, content, count=1)
    if content != orig:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"PATCHED: {path}")
    else:
        print(f"NO CHANGE: {path}")