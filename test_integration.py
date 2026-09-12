"""Test integration giua 2 services (Viewer + Remote Punch)."""
import urllib.request
import urllib.error
import urllib.parse
import base64
import json
import time
import os

GOOD_CREDS = base64.b64encode(b'admin:bvdk2026').decode()
BASE_VIEWER = 'http://127.0.0.1:8080'
BASE_REMOTE = 'http://127.0.0.1:8082'


def req(url, method='GET', data=None, headers=None, timeout=5):
    h = dict(headers or {})
    if data is not None:
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode()
        else:
            data = data.encode() if isinstance(data, str) else data
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        return resp.status, resp.read().decode('utf-8', errors='ignore'), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='ignore')[:200], dict(e.headers)


# Test 1: Viewer online
print('Test 1: Viewer is online')
code, body, _ = req(BASE_VIEWER + '/api/status')
assert code == 200
print('  PASS')

# Test 2: Remote Punch online
print('Test 2: Remote Punch is online')
code, body, _ = req(BASE_REMOTE + '/healthz')
assert code == 200
print('  PASS')

# Test 3: POST punch to Remote Punch
print('Test 3: POST punch via Remote Punch')
code, body, _ = req(
    BASE_REMOTE + '/punch',
    method='POST',
    data={'user_id': '777', 'status': '0', 'device_ip': '172.16.0.212'},
    headers={'Authorization': 'Basic ' + GOOD_CREDS, 'X-Requested-With': 'XMLHttpRequest'},
)
print('  status:', code, 'body:', body[:100])
assert code == 200
data = json.loads(body)
assert data.get('ok') is True
print('  PASS')

# Test 4: Check stats
print('Test 4: Check stats after POST')
code, body, _ = req(BASE_REMOTE + '/api/stats', headers={'Authorization': 'Basic ' + GOOD_CREDS})
data = json.loads(body)
print('  pending_count:', data.get('pending_count'))
assert data.get('pending_count', 0) > 0
print('  PASS')

# Test 5: Viewer can see devices
print('Test 5: Viewer /api/devices')
code, body, _ = req(BASE_VIEWER + '/api/devices')
devs = json.loads(body)
print('  devices:', len(devs))
assert len(devs) > 0
print('  PASS')

print()
print('=== ALL TESTS PASS ===')
