import os
import subprocess
import gzip
import tarfile
import py7zr

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
device_path = os.path.join(OUT_DIR, 'GET_AUTH_891401_device_5418194560548.dat')

print(f'Trying small config file: {device_path}')
with open(device_path, 'rb') as f:
    data = f.read()
print(f'Size: {len(data)} bytes')

# Try as tar.gz
print('\n=== As tar.gz ===')
tgz_path = os.path.join(OUT_DIR, 'device.dat.tgz')
with open(tgz_path, 'wb') as f:
    f.write(data)

try:
    with tarfile.open(tgz_path, mode='r:gz') as t:
        names = t.getnames()
        print(f'  {len(names)} members:')
        for n in names[:10]:
            print(f'    {n}')
except Exception as e:
    print(f'  Error: {type(e).__name__}: {str(e)[:200]}')

# Try py7zr on small file
print('\n=== py7zr ===')
for pwd in [None, b'', b'admin', b'891401', b'WtaNShf!', b'3324224660202']:
    try:
        with py7zr.SevenZipFile(device_path, mode='r', password=pwd) as z:
            names = z.getnames()
            print(f'  Password {pwd!r}: opened! {len(names)} entries')
            for n in names[:5]:
                print(f'    {n}')
            break
    except py7zr.exceptions.Bad7zFile as e:
        pass
    except Exception as e:
        err_str = str(e)[:100]
        if 'password' in err_str.lower():
            print(f'  Password {pwd!r}: encrypted')
        else:
            print(f'  Password {pwd!r}: {type(e).__name__}')

# Try gzip on small
print('\n=== gzip ===')
try:
    decompressed = gzip.decompress(data)
    print(f'  Decompressed: {len(decompressed)} bytes')
    # Show first ASCII strings
    import re
    strs = re.findall(rb'[\x20-\x7e]{4,}', decompressed[:500])
    for s in strs:
        print(f'    {s}')
except Exception as e:
    print(f'  Error: {type(e).__name__}')

# XOR decryption on small file
print('\n=== XOR on small file ===')
import struct
key = data[-16:]
print(f'  Last 16: {key.hex()}')

for key_name, key_bytes in [
    ('last 16', data[-16:]),
    ('size LE', struct.pack('<I', len(data))),
    ('serial', b'3324224660202'),
    ('commpwd', b'admin'),
]:
    decrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
    if decrypted[:2] == b'\x1f\x8b':
        print(f'  {key_name}: GZIP!')
        try:
            d = gzip.decompress(decrypted)
            print(f'    Decompressed: {len(d)} bytes')
            strs = re.findall(rb'[\x20-\x7e]{6,}', d[:500])
            for s in strs[:10]:
                print(f'    {s}')
        except Exception as e:
            print(f'    Gzip error: {e}')
    elif decrypted[:15] == b'SQLite format 3':
        print(f'  {key_name}: SQLite!')

# Try as raw SQLite - skip header
print('\n=== Look for SQLite in body ===')
# Find first non-header byte
for start in [0, 16, 256, 1024, 1108]:
    chunk = data[start:start+16]
    if chunk[:15] == b'SQLite format 3':
        print(f'  SQLite at offset {start}!')
        break

# Maybe the device_5418194560548.dat is a binary config blob
# Try parsing as struct
print('\n=== Parse as ZK config blob ===')
# Header: 256 bytes
# Then 'businessData.dat' filename at offset 1056 (we saw earlier)
# Then timestamp + description

# Look for ATTLOG or config table
import re
patterns = ['ATT', 'LOG', 'CONFIG', 'SERVER', 'IP', 'PORT', 'PWD', 'PASSWORD', 'ENABLE', 'FLAG']
for p in patterns:
    cnt = data.count(p.encode())
    if cnt > 0:
        print(f'  Found "{p}" {cnt} times')
