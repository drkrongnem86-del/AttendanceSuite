import os
import struct
import re
import json
import sqlite3
import zipfile
import gzip

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
fpath = os.path.join(OUT_DIR, 'GET_STYLE0_data.dat')

print(f'Loading {fpath}')
with open(fpath, 'rb') as f:
    data = f.read()

print(f'Size: {len(data)} bytes ({len(data) / 1024 / 1024:.2f} MB)')
print()

# Magic bytes
print('First 256 bytes hex:')
print(data[:256].hex())
print()
print('First 256 bytes raw:')
print(repr(data[:256]))
print()

# Check various archive formats
print('=== Format identification ===')
if data[:2] == b'\x1f\x8b':
    print('GZIP file detected')
elif data[:2] == b'PK':
    print('ZIP file detected')
elif data[:3] == b'7z\xbc\xaf':
    print('7Z file detected')
elif data[:4] == b'ustar':
    print('TAR archive detected')
else:
    print(f'Unknown format, first 16 bytes: {data[:16].hex()}')

# Find ASCII strings
print()
print('=== ASCII strings (length >= 8) ===')
strs = re.findall(rb'[\x20-\x7e]{8,}', data)
for s in strs[:30]:
    print(f'  {s}')

# Look for SQLite signature (header 'SQLite format 3')
print()
print('=== Looking for embedded SQLite ===')
for i in range(0, len(data) - 16, 4096):
    if data[i:i+15] == b'SQLite format 3':
        print(f'  Found SQLite at offset {i} (0x{i:x})')

# Look for ATTLOG strings
print()
print('=== Looking for ATT_LOG table hints ===')
attlog_positions = []
for i in range(0, len(data) - 8):
    if data[i:i+8] == b'ATT_LOG':
        attlog_positions.append(i)
        if len(attlog_positions) > 10:
            break
print(f'  ATT_LOG found at: {attlog_positions[:10]}')

# Try to find structured table format
print()
print('=== Looking for table-like structures ===')
# ATT_LOG table in ZK DB has columns: ID, BADGENUMBER, CHECKTIME, CHECKTYPE, VERIFYCODE, ...
# Try to find CHECKTIME pattern (YYYY-MM-DD HH:MM:SS)
chk_positions = []
for i in range(0, len(data) - 19):
    if data[i+4] == ord('-') and data[i+7] == ord('-') and data[i+10] == ord(' ') and data[i+13] == ord(':'):
        if data[i:i+4].isdigit():
            chk_positions.append(i)
            if len(chk_positions) > 5:
                break
print(f'  DateTime pattern found at: {chk_positions}')

# Try ZIP
print()
print('=== Trying ZIP ===')
try:
    with zipfile.ZipFile(fpath) as z:
        print(f'  ZIP opened, {len(z.namelist())} entries:')
        for name in z.namelist()[:10]:
            print(f'    {name}')
except Exception as e:
    print(f'  Not ZIP: {type(e).__name__}')

# Try GZIP
print()
print('=== Trying GZIP ===')
try:
    decompressed = gzip.decompress(data)
    print(f'  Decompressed: {len(decompressed)} bytes')
except Exception as e:
    print(f'  Not GZIP: {type(e).__name__}')

# Try zlib at various offsets
print()
print('=== Trying ZLIB at various offsets ===')
import zlib
for offset in [0, 16, 256, 1024, 4096, 8192]:
    try:
        d = zlib.decompress(data[offset:])
        print(f'  Zlib at {offset}: {len(d)} bytes')
        break
    except:
        pass

# Check if it's a 7z
print()
print('=== Trying 7Z ===')
try:
    import py7zr
    with py7zr.SevenZipFile(fpath, mode='r') as z:
        names = z.getnames()
        print(f'  7Z opened, {len(names)} entries:')
        for n in names[:10]:
            print(f'    {n}')
except Exception as e:
    print(f'  Not 7Z: {type(e).__name__}: {str(e)[:200]}')

# Try XOR decryption with common keys
print()
print('=== Trying XOR decryption ===')
for key_str in ['admin', '891401', '123456', '0', 'X628']:
    key = key_str.encode()
    decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data[:64]))
    if decrypted[:2] == b'\x1f\x8b' or decrypted[:4] == b'7z\xbc\xaf' or decrypted[:2] == b'PK' or decrypted[:15] == b'SQLite format 3':
        print(f'  XOR with key "{key_str}" -> looks like archive: {decrypted[:16].hex()}')
    # Look for printable text
    printable = sum(1 for c in decrypted if 32 <= c <= 126)
    if printable > 40:
        print(f'  XOR with key "{key_str}" -> mostly printable: {decrypted[:64]}')

# Save first 1MB for inspection
out_sample = os.path.join(OUT_DIR, 'data_sample_first_1mb.bin')
with open(out_sample, 'wb') as f:
    f.write(data[:1024*1024])
print(f'\nFirst 1MB sample saved: {out_sample}')
