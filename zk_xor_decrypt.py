import os
import re
import gzip

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
fpath = os.path.join(OUT_DIR, 'GET_STYLE0_data.dat')

with open(fpath, 'rb') as f:
    data = f.read()

file_size = len(data)
last_16 = data[-16:]
print(f'File size: {file_size} bytes')
print(f'Last 16 bytes: {last_16.hex()}')
print(f'Last 16 ASCII: {last_16}')

# XOR key = last 16 bytes + file size (per Securelist research)
# Try various XOR schemes
print()
print('=== XOR decryption attempts ===')

# Method 1: Simple XOR with last 16 bytes (rolling)
def xor_decrypt(data, key):
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))

# Method 2: XOR with last 16 bytes + size
key_with_size = last_16 + file_size.to_bytes(8, 'little')

methods = [
    ('Last 16 bytes XOR', last_16),
    ('Last 16 + size (LE)', key_with_size),
    ('Last 16 + size (BE)', last_16 + file_size.to_bytes(8, 'big')),
    ('Serial number as key', b'3324224660202'),
    ('CommPwd as key', b'admin'),
    ('admin + size', b'admin' + file_size.to_bytes(8, 'little')),
    ('Magic 0x37 0x7A 0xBC 0xAF', b'\x37\x7a\xbc\xaf\x27\x1c'),
]

for name, key in methods:
    decrypted = xor_decrypt(data, key)
    # Check for known formats
    if decrypted[:2] == b'\x1f\x8b':
        print(f'  {name}: GZIP detected!')
        try:
            d = gzip.decompress(decrypted[:min(1024, len(decrypted))])
            print(f'    Decompressed first 1KB OK, size: {len(d)}')
        except:
            pass
    elif decrypted[:4] == b'7z\xbc\xaf':
        print(f'  {name}: 7Z detected!')
    elif decrypted[:2] == b'PK':
        print(f'  {name}: ZIP detected!')
    elif decrypted[:15] == b'SQLite format 3':
        print(f'  {name}: SQLite detected!')
    elif decrypted[:16] == b'ZK format 1.0.0.0':
        print(f'  {name}: ZK format detected (double encryption?)')

    # Check printable
    printable = sum(1 for c in decrypted[:64] if 32 <= c <= 126)
    if printable > 40:
        print(f'  {name}: printable text (first 64 bytes): {decrypted[:64]}')

# Try XOR with single bytes (brute force byte)
print()
print('=== Single-byte XOR brute force ===')
for xor_byte in range(256):
    # Just check first 16 bytes
    test = bytes(b ^ xor_byte for b in data[:16])
    if test.startswith(b'PK') or test.startswith(b'7z') or test.startswith(b'SQLite format'):
        print(f'  XOR 0x{xor_byte:02x}: {test[:16]}')

# Try XOR at specific offsets
print()
print('=== XOR with file_size at specific positions ===')
# Sometimes key is applied only at certain offsets
for offset in [256, 1024, 1088, 1108]:
    test = data[offset:offset+16]
    key = file_size.to_bytes(8, 'little')
    decrypted = bytes(b ^ key[i % 8] for i, b in enumerate(test))
    print(f'  Offset {offset}: {decrypted}')

# Try looking for embedded SQLite at various offsets with XOR
print()
print('=== Searching for SQLite with XOR ===')
for xor_key in [b'\x00', b'\x01', b'\xff', b'admin', b'3324224660202', last_16, file_size.to_bytes(8, 'little')]:
    decoded = bytes(b ^ xor_key[i % len(xor_key)] for i, b in enumerate(data))
    pos = decoded.find(b'SQLite format 3')
    if pos > -1:
        print(f'  Found SQLite at offset {pos} with key {xor_key.hex()[:40]}')

# Check if file has multiple "ZK format" headers (concatenated backups)
zk_count = data.count(b'ZK format')
print(f'\n=== ZK format occurrences: {zk_count} ===')

# Try smaller key variations
print()
print('=== Smaller XOR key attempts ===')
for key_len in [4, 8, 16]:
    for key_start in [0, file_size - key_len, 1024 - key_len, 2048 - key_len]:
        if key_start < 0 or key_start + key_len > len(data):
            continue
        key = data[key_start:key_start + key_len]
        # XOR first 64 bytes
        test = bytes(b ^ key[i % key_len] for i, b in enumerate(data[:64]))
        if test[:4] in [b'PK\x03\x04', b'7z\xbc\xaf', b'SQLi'] or test[:15] == b'SQLite format 3':
            print(f'  Key at {key_start} (len {key_len}): {test[:16]}')

# Save the data with most promising XOR (last 16 bytes) for analysis
out_xor = os.path.join(OUT_DIR, 'data_xor_last16.bin')
with open(out_xor, 'wb') as f:
    f.write(xor_decrypt(data, last_16))
print(f'\nXOR with last 16 bytes saved: {out_xor}')

# Also try with serial
out_serial = os.path.join(OUT_DIR, 'data_xor_serial.bin')
with open(out_serial, 'wb') as f:
    f.write(xor_decrypt(data, b'3324224660202'))
print(f'XOR with serial saved: {out_serial}')
