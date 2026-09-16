import os
import subprocess
import gzip
import tarfile

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
fpath = os.path.join(OUT_DIR, 'GET_STYLE0_data.dat')

print(f'Loading {fpath}')
with open(fpath, 'rb') as f:
    data = f.read()

print(f'Size: {len(data)} bytes')
print()

# Try as tar.gz via subprocess
print('=== Method 1: gunzip + tar via subprocess ===')
out_dir_tar = os.path.join(OUT_DIR, 'tar_extract')
os.makedirs(out_dir_tar, exist_ok=True)
# Save as .tgz
tgz_path = os.path.join(OUT_DIR, 'data.dat.tgz')
with open(tgz_path, 'wb') as f:
    f.write(data)
print(f'Saved as .tgz: {tgz_path}')

# Try gunzip
print('\n--- Trying gunzip ---')
import shutil
gz_path = os.path.join(OUT_DIR, 'data.dat.gz')
shutil.copy(tgz_path, gz_path)
try:
    result = subprocess.run(['gzip', '-d', '-f', gz_path], capture_output=True, timeout=60)
    print(f'  gunzip exit: {result.returncode}')
    if result.stdout:
        print(f'  stdout: {result.stdout.decode()[:200]}')
    if result.stderr:
        print(f'  stderr: {result.stderr.decode()[:200]}')
except FileNotFoundError:
    print('  gzip not found, trying Python')
except Exception as e:
    print(f'  Error: {e}')

# Try Python gzip
print('\n--- Trying Python gzip ---')
try:
    with gzip.open(tgz_path, 'rb') as f:
        decompressed = f.read()
    print(f'  Decompressed: {len(decompressed)} bytes')
    with open(os.path.join(OUT_DIR, 'data.dat.extracted'), 'wb') as f:
        f.write(decompressed)
except Exception as e:
    print(f'  Error: {type(e).__name__}: {str(e)[:200]}')

# Try tarfile directly
print('\n--- Trying tarfile.open ---')
try:
    with tarfile.open(tgz_path, mode='r:gz') as t:
        members = t.getnames()
        print(f'  Members ({len(members)}):')
        for m in members[:30]:
            print(f'    {m}')
        # Extract
        t.extractall(path=out_dir_tar)
        print(f'  Extracted to: {out_dir_tar}')
except Exception as e:
    print(f'  Error: {type(e).__name__}: {str(e)[:200]}')

# Try as tar (uncompressed)
print('\n=== Method 2: tar directly ===')
tar_path = os.path.join(OUT_DIR, 'data.dat.tar')
with open(tar_path, 'wb') as f:
    f.write(data)
try:
    with tarfile.open(tar_path, mode='r:') as t:
        members = t.getnames()
        print(f'  Members ({len(members)}):')
        for m in members[:30]:
            print(f'    {m}')
        t.extractall(path=out_dir_tar)
        print(f'  Extracted to: {out_dir_tar}')
except Exception as e:
    print(f'  Error: {type(e).__name__}: {str(e)[:200]}')

# Try as bz2
print('\n=== Method 3: bz2 ===')
try:
    import bz2
    decompressed = bz2.decompress(data)
    print(f'  Decompressed: {len(decompressed)} bytes')
except Exception as e:
    print(f'  Error: {type(e).__name__}')

# Try as xz
print('\n=== Method 4: xz ===')
try:
    import lzma
    decompressed = lzma.decompress(data)
    print(f'  Decompressed: {len(decompressed)} bytes')
except Exception as e:
    print(f'  Error: {type(e).__name__}')

# Try as zstd
print('\n=== Method 5: zstd ===')
try:
    import zstandard
    dctx = zstandard.ZstdDecompressor()
    decompressed = dctx.decompress(data)
    print(f'  Decompressed: {len(decompressed)} bytes')
except ImportError:
    print('  zstandard not installed')
except Exception as e:
    print(f'  Error: {type(e).__name__}')

# Try as 7z with all sorts of options
print('\n=== Method 6: py7zr with various passwords ===')
import py7zr
for pwd in [None, b'', b'admin', b'891401', b'WtaNShf!', b'3324224660202', b'X628PRO', b'x628pro', b'password', b'123456']:
    try:
        with py7zr.SevenZipFile(fpath, mode='r', password=pwd) as z:
            names = z.getnames()
            print(f'  Password {pwd!r}: opened! {len(names)} entries')
            for n in names[:5]:
                print(f'    {n}')
            break
    except py7zr.exceptions.Bad7zFile as e:
        pass
    except Exception as e:
        err_str = str(e)[:100]
        if 'encrypted' in err_str.lower() or 'password' in err_str.lower():
            print(f'  Password {pwd!r}: needs different password ({err_str})')
        else:
            print(f'  Password {pwd!r}: Error: {type(e).__name__}: {err_str}')

# List extracted files
print('\n=== Extracted files ===')
if os.path.exists(out_dir_tar):
    for root, dirs, files in os.walk(out_dir_tar):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, out_dir_tar)
            print(f'  {rel}: {os.path.getsize(full)} bytes')
