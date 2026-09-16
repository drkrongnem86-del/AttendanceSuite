"""Re-pack modified ZKDB.db and try to upload to 172.16.254.202"""
import os
import sys
import io
import gzip
import sqlite3
import time
import requests

sys.stdout.reconfigure(encoding='utf-8')

DEVICE_IP = '172.16.254.202'
BASE_URL = f'http://{DEVICE_IP}'
WORK_DIR = r'D:/chamcong/zk_fw_attempts/web_restore_test'

# Step 1: Read modified ZKDB.db
zkdb_path = os.path.join(WORK_DIR, 'ZKDB.db')
with open(zkdb_path, 'rb') as f:
    zkdb_data = f.read()
print(f'ZKDB.db: {len(zkdb_data)} bytes')

# Step 2: Build minimal TAR (header + data + padding + end-of-archive)
file_size = len(zkdb_data)
new_tar_data = bytearray()

# TAR header (512 bytes)
tar_header = bytearray(512)
fn_bytes = b'ZKDB.db'
tar_header[0:len(fn_bytes)] = fn_bytes
tar_header[100:107] = b'0000755'
tar_header[108:112] = b'0000'
tar_header[116:120] = b'0000'
size_str = f'{file_size:011o}\x00'.encode()
tar_header[124:124+len(size_str)] = size_str
tar_header[136:148] = b'15252234061\x00'
tar_header[156] = ord('0')  # regular file
tar_header[257:263] = b'ustar\x00'
tar_header[148:156] = b'        '  # checksum placeholder
chk = sum(tar_header)
chk_str = f'{chk:06o}\x00 '.encode()
tar_header[148:148+len(chk_str)] = chk_str
new_tar_data.extend(tar_header)
new_tar_data.extend(zkdb_data)
# Padding to 512-byte boundary
pad_len = ((file_size + 511) // 512) * 512 - file_size
new_tar_data.extend(b'\x00' * pad_len)
# End-of-archive (two zero blocks)
new_tar_data.extend(b'\x00' * 1024)

new_tar_path = os.path.join(WORK_DIR, 'ZKDB_new.tar')
with open(new_tar_path, 'wb') as f:
    f.write(bytes(new_tar_data))
print(f'New TAR: {len(new_tar_data)} bytes')

# Step 3: GZIP compress
gz_buf = io.BytesIO()
with gzip.GzipFile(fileobj=gz_buf, mode='wb') as gz_out:
    gz_out.write(bytes(new_tar_data))
gz_data = gz_buf.getvalue()
print(f'Compressed: {len(gz_data)} bytes')

gz_path = os.path.join(WORK_DIR, 'businessData_new.dat.gz')
with open(gz_path, 'wb') as f:
    f.write(gz_data)
print(f'Saved: {gz_path}')

# Step 4: Test upload endpoints
print('\n' + '='*70)
print('TESTING UPLOAD ENDPOINTS')
print('='*70)

upload_endpoints = [
    '/form/DataApp',
    '/form/DataApp?style=0',
    '/form/DataApp?Restore=1',
    '/iWsService',
    '/form/RestoreData',
]

for ep in upload_endpoints:
    print(f'\n  Testing {ep}...')
    # POST multipart
    try:
        files = {'file': ('businessData.dat', gz_data, 'application/octet-stream')}
        r = requests.post(f'{BASE_URL}{ep}', files=files, timeout=5)
        print(f'    POST multipart: {r.status_code}, len={len(r.content)}, first 80: {r.content[:80]!r}')
    except Exception as e:
        print(f'    POST multipart: error {e}')
    # POST raw
    try:
        r = requests.post(f'{BASE_URL}{ep}', data=gz_data, headers={'Content-Type': 'application/octet-stream'}, timeout=5)
        print(f'    POST raw: {r.status_code}, len={len(r.content)}, first 80: {r.content[:80]!r}')
    except Exception as e:
        print(f'    POST raw: error {e}')

# Step 5: Check if upload affected ATTLOG count
print('\n' + '='*70)
print('VERIFICATION')
print('='*70)
time.sleep(3)
r = requests.get(f'{BASE_URL}/form/DataApp?style=1', timeout=30)
if r.status_code == 200 and r.content[:15] == b'ZK format 1.0.0.0':
    count = int(r.content[15:25])
    print(f'Current ATTLOG count: {count}')
    if count == 49204:
        print('*** COUNT INCREASED FROM 49203 -> 49204 ***')
        print('*** INSERT VIA WEB UPLOAD WORKS! ***')
    elif count > 49203:
        print(f'*** COUNT CHANGED: 49203 -> {count} ***')
    else:
        print(f'    Count unchanged or decreased ({count} vs 49203)')
else:
    print(f'Header: {r.content[:50]}')