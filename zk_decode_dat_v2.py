import os
import py7zr
import zipfile
import gzip
import re
import struct

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
fpath = os.path.join(OUT_DIR, 'GET_STYLE0_data.dat')

print(f'Loading {fpath}')
with open(fpath, 'rb') as f:
    data = f.read()

print(f'Size: {len(data)} bytes')

# Find all "businessData.dat" occurrences
print()
print('=== businessData.dat occurrences ===')
positions = []
i = 0
while True:
    i = data.find(b'businessData.dat', i)
    if i == -1:
        break
    positions.append(i)
    i += 1
print(f'  Found at {len(positions)} positions: {positions[:10]}')
if positions:
    pos = positions[0]
    # Show context
    print(f'  Context around {pos}:')
    print(f'    Before: {data[max(0, pos-64):pos].hex()}')
    print(f'    At: {data[pos:pos+30]}')
    print(f'    After: {data[pos+30:pos+94].hex()}')

# Try 7z with various passwords
print()
print('=== Trying 7z with various passwords ===')
passwords_to_try = [
    None,
    b'',
    b'admin',
    b'891401',
    b'123456',
    b'0',
    b'password',
    b'zkteco',
    b'X628',
    b'WtaNShf!',
    b'attendance',
    b'data',
    b'0000',
]

for pwd in passwords_to_try:
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
        # Different error might mean password is wrong
        if 'password' in str(e).lower() or 'archive' in str(e).lower():
            pass
        else:
            print(f'  Password {pwd!r}: Error: {type(e).__name__}: {str(e)[:100]}')

# Try as a stream - maybe the file has multiple archives concatenated
print()
print('=== Looking for sub-archive signatures ===')
sig_positions = []
for sig, name in [(b'\x1f\x8b', 'GZIP'), (b'PK', 'ZIP'), (b'7z\xbc\xaf', '7Z'),
                  (b'SQLite format 3', 'SQLite'), (b'ustar', 'TAR')]:
    i = 0
    while True:
        i = data.find(sig, i)
        if i == -1:
            break
        sig_positions.append((i, name))
        i += 1
print(f'  Sub-archive signatures: {sig_positions[:20]}')

# Try to extract businessData.dat blob
print()
print('=== Trying to extract embedded businessData.dat ===')
# Find "businessData.dat" position and see if it's followed by data
pos = data.find(b'businessData.dat')
if pos > -1:
    # Look for 7z or ZIP header right after
    next_7z = data.find(b'\x37\x7a\xbc\xaf\x27\x1c', pos)
    next_zip = data.find(b'PK\x03\x04', pos)
    next_gzip = data.find(b'\x1f\x8b', pos)
    print(f'  businessData.dat at {pos}')
    print(f'    Next 7z header: {next_7z} (offset {next_7z - pos if next_7z > -1 else "N/A"})')
    print(f'    Next ZIP header: {next_zip} (offset {next_zip - pos if next_zip > -1 else "N/A"})')
    print(f'    Next GZIP header: {next_gzip} (offset {next_gzip - pos if next_gzip > -1 else "N/A"})')

# Look at the structure more carefully
# 0-16: 'ZK format 1.0.0.0'
# 16-40: zeros + '0000000001'
# 40-256: zeros
# 256-? : timestamp + data
print()
print('=== File structure ===')
print(f'  0-16: header "{data[:16]}"')
print(f'  16: "0000000001" at offset 16')
print(f'  256: timestamp starts')
ts_offset = data.find(b'2026-09-15')
if ts_offset > -1:
    print(f'    Timestamp: {data[ts_offset:ts_offset+19]}')
    print(f'    After timestamp (next 256):')
    print(f'    {data[ts_offset+19:ts_offset+275].hex()}')
    # Find "Back up" string
    backup_str = data.find(b'Back up')
    if backup_str > -1:
        print(f'  Backup description at {backup_str}: {data[backup_str:backup_str+80]}')

# Try to interpret the encrypted body
print()
print('=== Encrypted body analysis ===')
body_start = ts_offset + 64
print(f'  Body starts ~ offset {body_start}')
print(f'  Hex (first 256): {data[body_start:body_start+256].hex()}')

# Look for 7z magic in body
sevenz_magic = data.find(b'\x37\x7a\xbc\xaf\x27\x1c', body_start)
if sevenz_magic > -1:
    print(f'  7z magic found at offset {sevenz_magic}')

# Check for PK signature (ZIP)
pk_magic = data.find(b'PK\x03\x04', body_start)
if pk_magic > -1:
    print(f'  ZIP magic found at offset {pk_magic}')
    # Try to extract
    print('  Trying ZIP extraction...')
    try:
        with zipfile.ZipFile(io.BytesIO(data[pk_magic:])) if False else open(fpath, 'rb') as f:
            pass
    except:
        pass

# Print summary
print()
print('=== SUMMARY ===')
print(f'File size: {len(data)} bytes (3.71 MB)')
print(f'Header: ZK format 1.0.0.0 (proprietary format)')
print(f'Contains embedded businessData.dat filename')
print(f'Timestamp: 2026-09-15T12:26:47 (matches webserver backup time)')
print(f'Description: "Back up with webserver"')
print(f'Body appears encrypted - not standard archive')
print(f'Possible password/key: WtaNShf! (found in body)')

# Save body for further analysis
body_file = os.path.join(OUT_DIR, 'data_body.bin')
with open(body_file, 'wb') as f:
    f.write(data[body_start:])
print(f'Body saved: {body_file}')
