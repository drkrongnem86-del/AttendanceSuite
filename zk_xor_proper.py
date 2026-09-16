import os
import re
import struct

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
fpath = os.path.join(OUT_DIR, 'GET_STYLE0_data.dat')

with open(fpath, 'rb') as f:
    data = f.read()

file_size = len(data)
print(f'File size: {file_size} bytes')

# Try various Securelist-style XOR keys
# Per research: XOR with last 16 bytes of file + file size as key
print()
print('=== Securelist XOR schemes ===')

# Scheme 1: XOR with last 16 bytes (rolling key)
key_last16 = data[-16:]
d1 = bytes(b ^ key_last16[i % 16] for i, b in enumerate(data))
# Check for SQL at start
sql_pos = d1.find(b'SQLite format 3')
print(f'  Key=last 16 bytes: SQL at {sql_pos}')
# Show some text patterns
strs = re.findall(rb'[\x20-\x7e]{8,}', d1[:10000])
if strs:
    print(f'  Sample strings: {strs[:5]}')

# Scheme 2: XOR with file_size bytes (LE 4 bytes repeated)
key_fs4 = struct.pack('<I', file_size)
d2 = bytes(b ^ key_fs4[i % 4] for i, b in enumerate(data))
sql_pos = d2.find(b'SQLite format 3')
print(f'  Key=file_size LE 4B: SQL at {sql_pos}')
strs = re.findall(rb'[\x20-\x7e]{8,}', d2[:10000])
if strs:
    print(f'  Sample strings: {strs[:5]}')

# Scheme 3: XOR with file_size LE 8 bytes
key_fs8 = struct.pack('<Q', file_size)
d3 = bytes(b ^ key_fs8[i % 8] for i, b in enumerate(data))
sql_pos = d3.find(b'SQLite format 3')
print(f'  Key=file_size LE 8B: SQL at {sql_pos}')
strs = re.findall(rb'[\x20-\x7e]{8,}', d3[:10000])
if strs:
    print(f'  Sample strings: {strs[:5]}')

# Scheme 4: Last 16 + file_size (combined)
key_combined = key_last16 + struct.pack('<Q', file_size)
d4 = bytes(b ^ key_combined[i % len(key_combined)] for i, b in enumerate(data))
sql_pos = d4.find(b'SQLite format 3')
print(f'  Key=last16+size: SQL at {sql_pos}')
strs = re.findall(rb'[\x20-\x7e]{8,}', d4[:10000])
if strs:
    print(f'  Sample strings: {strs[:5]}')

# Scheme 5: file_size LE 4 bytes but starting from a specific offset (e.g., 256)
key_fs4_b = struct.pack('<I', file_size)
# Try XOR with file_size key but only applied AFTER some header
header_size = 256
d5 = bytearray(data[:header_size])
for i in range(header_size, len(data)):
    d5.append(data[i] ^ key_fs4_b[(i - header_size) % 4])
d5 = bytes(d5)
sql_pos = d5.find(b'SQLite format 3')
print(f'  Key=file_size after header (offset 256): SQL at {sql_pos}')

# Scheme 6: Last 16 bytes applied after header
d6 = bytearray(data[:header_size])
for i in range(header_size, len(data)):
    d6.append(data[i] ^ key_last16[(i - header_size) % 16])
d6 = bytes(d6)
sql_pos = d6.find(b'SQLite format 3')
print(f'  Key=last16 after header: SQL at {sql_pos}')

# Scheme 7: Combined last16+size after header
d7 = bytearray(data[:header_size])
key_c = key_last16 + struct.pack('<Q', file_size)
for i in range(header_size, len(data)):
    d7.append(data[i] ^ key_c[(i - header_size) % len(key_c)])
d7 = bytes(d7)
sql_pos = d7.find(b'SQLite format 3')
print(f'  Key=combined after header: SQL at {sql_pos}')

# Scheme 8: Reverse - XOR first N bytes with key, leave rest
key_fs_le = struct.pack('<I', file_size)
d8 = bytearray()
for i in range(len(data)):
    if i < 4:
        d8.append(data[i] ^ key_fs_le[i])
    else:
        d8.append(data[i])
d8 = bytes(d8)
sql_pos = d8.find(b'SQLite format 3')
print(f'  XOR first 4 bytes only: SQL at {sql_pos}')

# Save best candidates
for name, d in [('xor_last16', d1), ('xor_fs4', d2), ('xor_fs8', d3),
                ('xor_combined', d4), ('xor_fs4_after_header', d5),
                ('xor_last16_after_header', d6), ('xor_combined_after_header', d7),
                ('xor_first4', d8)]:
    out_path = os.path.join(OUT_DIR, f'data_{name}.bin')
    with open(out_path, 'wb') as f:
        f.write(d)
    # Check for SQLite
    has_sql = b'SQLite format 3' in d
    has_zip = d[:2] == b'PK'
    has_7z = d[:3] == b'7z\xbc\xaf'
    print(f'  Saved {name}: {len(d)} bytes, SQL={has_sql}, ZIP={has_zip}, 7Z={has_7z}')

# Also try: extract ATTLOG signature directly from raw data
print()
print('=== Direct ATTLOG search in raw data ===')
# ATT_LOG entries have specific format with PIN and datetime
# Try to find any pattern that looks like ATTLOG
for pattern in [b'ATT_LOG', b'ATTLOG', b'ATT_LOG_', b'CHECKTIME', b'BADGENUMBER', b'CHKTIME']:
    pos = data.find(pattern)
    if pos > -1:
        print(f'  Found "{pattern.decode()}" at offset {pos}')

# Try looking for 1383 (PIN) and 2026 (year)
print()
print('=== Looking for PIN 1383 with year 2026 ===')
for pattern in [b'1383\x002026-', b'2026-09', b'2026-08', b'267\x002026-']:
    pos = 0
    found = 0
    while True:
        pos = data.find(pattern, pos)
        if pos == -1 or found > 5:
            break
        print(f'  Found "{pattern[:20]}" at offset {pos}')
        pos += 1
        found += 1
