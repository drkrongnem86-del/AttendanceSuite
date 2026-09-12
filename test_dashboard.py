"""Test dashboard moi co auth + mobile UI"""
import urllib.request
import urllib.error
import urllib.parse
import base64
import sys

GOOD_CREDS = base64.b64encode(b'admin:bvdk2026').decode()
BAD_CREDS = base64.b64encode(b'admin:wrongpass').decode()


def req(url, method='GET', data=None, headers=None):
    h = headers or {}
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=3)
        return resp.status, resp.read().decode('utf-8'), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='ignore')[:200], dict(e.headers)


# Test 1: health check (no auth)
print('=== Test 1: GET /healthz (no auth) ===')
code, body, _ = req('http://127.0.0.1:8082/healthz')
print(f'  status={code} body={body[:100]}')
assert code == 200, f'expected 200, got {code}'

# Test 2: / no auth -> 401
print('=== Test 2: GET / (no auth) -> 401 ===')
code, body, headers = req('http://127.0.0.1:8082/')
print(f'  status={code}')
assert code == 401, f'expected 401, got {code}'
assert 'WWW-Authenticate' in headers, 'no WWW-Authenticate'

# Test 3: / with correct auth
print('=== Test 3: GET / (correct auth) ===')
code, body, _ = req('http://127.0.0.1:8082/', headers={'Authorization': 'Basic ' + GOOD_CREDS})
print(f'  status={code} len={len(body)}')
assert code == 200
assert 'Cham Cong Tu Xa' in body, 'missing title'
assert 'quick-punch' in body, 'missing quick-punch class'
assert 'VAO CA' in body, 'missing VAO CA button'
assert 'TAN CA' in body, 'missing TAN CA button'
assert 'logout' in body.lower(), 'missing logout'
assert '@media' in body, 'missing mobile CSS'
assert '172.16.0.212' in body, 'missing device IP'
print('  [OK] All checks pass')

# Test 4: /api/stats
print('=== Test 4: GET /api/stats ===')
code, body, _ = req('http://127.0.0.1:8082/api/stats', headers={'Authorization': 'Basic ' + GOOD_CREDS})
print(f'  status={code} body={body[:200]}')
assert code == 200
import json
data = json.loads(body)
assert 'pending_count' in data
assert 'synced_count' in data
print('  [OK] Stats JSON valid')

# Test 5: POST /punch with auth
print('=== Test 5: POST /punch NV 421 status 0 ===')
code, body, headers = req(
    'http://127.0.0.1:8082/punch',
    method='POST',
    data={'user_id': '421', 'status': '0', 'device_ip': '172.16.0.212'},
    headers={'Authorization': 'Basic ' + GOOD_CREDS},
)
print(f'  status={code} location={headers.get("Location", "")}')
assert code in (200, 303)

# Test 6: POST /punch with AJAX
print('=== Test 6: POST /punch (AJAX) NV 999 status 1 ===')
code, body, _ = req(
    'http://127.0.0.1:8082/punch',
    method='POST',
    data={'user_id': '999', 'status': '1', 'device_ip': '172.16.0.214'},
    headers={'Authorization': 'Basic ' + GOOD_CREDS, 'X-Requested-With': 'XMLHttpRequest'},
)
print(f'  status={code} body={body[:150]}')
assert code == 200
data = json.loads(body)
assert data.get('ok') is True
print('  [OK] AJAX response valid')

# Test 7: wrong password
print('=== Test 7: GET / (wrong password) -> 401 ===')
code, _, _ = req('http://127.0.0.1:8082/', headers={'Authorization': 'Basic ' + BAD_CREDS})
print(f'  status={code}')
assert code == 401

# Test 8: invalid user_id
print('=== Test 8: POST /punch (invalid user_id) -> 400 ===')
code, body, _ = req(
    'http://127.0.0.1:8082/punch',
    method='POST',
    data={'user_id': 'abc', 'status': '0'},
    headers={'Authorization': 'Basic ' + GOOD_CREDS},
)
print(f'  status={code} body={body[:100]}')
assert code == 400

print()
print('=== ALL TESTS PASS ===')
