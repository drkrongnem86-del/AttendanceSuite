"""Test integration cuoi cung - 2 service chay song song"""
import urllib.request
import urllib.error
import urllib.parse
import base64
import json

GOOD = base64.b64encode(b'admin:bvdk2026').decode()


def req(url, method='GET', data=None, headers=None, timeout=3):
    h = dict(headers or {})
    if isinstance(data, dict):
        # form-encoded
        data = urllib.parse.urlencode(data).encode()
    elif isinstance(data, str):
        data = data.encode()
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        return resp.status, resp.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='ignore')[:200]


# Test 1: Web legacy endpoint (no auth)
print('Test 1: POST /api/remote-punch (web, no auth) - legacy endpoint')
code, body = req(
    'http://127.0.0.1:8080/api/remote-punch',
    method='POST',
    data=json.dumps({'user_id': '421', 'status': 0, 'device_ip': '172.16.0.212'}),
    headers={'Content-Type': 'application/json'},
)
print(f'  status={code} body={body[:100]}')
assert code == 200

# Test 2: Dashboard new (with auth)
print('Test 2: GET dashboard (with auth)')
code, body = req('http://127.0.0.1:8082/',
                 headers={'Authorization': 'Basic ' + GOOD})
print(f'  status={code} len={len(body)}')
assert code == 200 and 'Cham Cong Tu Xa' in body

# Test 3: /healthz (no auth)
print('Test 3: GET /healthz (no auth)')
code, body = req('http://127.0.0.1:8082/healthz')
print(f'  status={code} body={body}')
assert code == 200 and 'ok' in body

# Test 4: /api/stats
print('Test 4: GET /api/stats')
code, body = req('http://127.0.0.1:8082/api/stats',
                 headers={'Authorization': 'Basic ' + GOOD})
print(f'  status={code} body={body[:200]}')
assert code == 200
data = json.loads(body)
assert 'pending_count' in data

# Test 5: Punch via dashboard
print('Test 5: POST /punch (dashboard AJAX) NV 999 status 1')
code, body = req(
    'http://127.0.0.1:8082/punch',
    method='POST',
    data={'user_id': '999', 'status': '1', 'device_ip': '172.16.0.214'},
    headers={'Authorization': 'Basic ' + GOOD, 'X-Requested-With': 'XMLHttpRequest'},
)
print(f'  status={code} body={body}')
assert code == 200
data = json.loads(body)
assert data.get('ok') is True

# Test 6: 404 cho path khong ton tai
print('Test 6: GET /api/nonexistent -> 404')
code, _ = req('http://127.0.0.1:8082/api/nonexistent',
              headers={'Authorization': 'Basic ' + GOOD})
print(f'  status={code}')

print()
print('=== ALL INTEGRATION TESTS PASS ===')
