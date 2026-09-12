"""Test v1.4.0 - config + rate limit + audit + CORS."""
import urllib.request
import urllib.error
import urllib.parse
import base64
import json
import sys

GOOD_CREDS = base64.b64encode(b'admin:bvdk2026').decode()
BAD_CREDS = base64.b64encode(b'admin:wrongpass').decode()
BASE = 'http://127.0.0.1:8082'


def req(url, method='GET', data=None, headers=None, timeout=5):
    h = dict(headers or {})
    if data is not None and method == 'POST':
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode()
        else:
            data = data.encode() if isinstance(data, str) else data
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        return resp.status, resp.read().decode('utf-8', errors='ignore'), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='ignore')[:300], dict(e.headers)


def auth():
    return {'Authorization': 'Basic ' + GOOD_CREDS}


def test(name, fn):
    print(f'=== {name} ===')
    try:
        fn()
        print(f'  [PASS]\n')
        return True
    except AssertionError as e:
        print(f'  [FAIL] {e}\n')
        return False
    except Exception as e:
        print(f'  [ERROR] {type(e).__name__}: {e}\n')
        return False


# ============ TEST 1: /healthz returns version ============
def t1():
    code, body, _ = req(f'{BASE}/healthz')
    assert code == 200, f'expected 200, got {code}'
    data = json.loads(body)
    assert data.get('ok') is True
    assert data.get('version') == '1.4.0', f'version: {data.get("version")}'
    assert 'service' in data


# ============ TEST 2: /api/stats includes channels_active ============
def t2():
    code, body, _ = req(f'{BASE}/api/stats', headers=auth())
    assert code == 200
    data = json.loads(body)
    assert 'channels_active' in data
    assert isinstance(data['channels_active'], list)


# ============ TEST 3: /api/config masks passwords ============
def t3():
    code, body, _ = req(f'{BASE}/api/config', headers=auth())
    assert code == 200
    data = json.loads(body)
    assert data.get('ok') is True
    cfg = data.get('config', {})
    assert 'auth' in cfg
    assert cfg['auth']['pass'] == '***', f'auth.pass leaked: {cfg["auth"]["pass"]}'
    assert 'secutime' in cfg
    assert cfg['secutime']['pass'] == '***', f'secutime.pass leaked: {cfg["secutime"]["pass"]}'
    assert cfg['auth']['user'] == 'admin'
    assert cfg['rate_limit']['max_requests'] > 0


# ============ TEST 4: /api/config without auth -> 401 ============
def t4():
    code, body, _ = req(f'{BASE}/api/config')
    assert code == 401


# ============ TEST 5: OPTIONS preflight returns 204 + CORS headers ============
def t5():
    code, body, headers = req(f'{BASE}/api/remote-punch', method='OPTIONS',
                              headers={'Origin': 'https://example.com'})
    assert code == 204, f'expected 204, got {code}'
    assert headers.get('Access-Control-Allow-Origin') in ('https://example.com', '*'), \
        f'CORS origin missing: {headers.get("Access-Control-Allow-Origin")}'
    assert 'Access-Control-Allow-Methods' in headers
    assert 'Access-Control-Allow-Headers' in headers


# ============ TEST 6: GET responses include CORS headers ============
def t6():
    code, body, headers = req(f'{BASE}/api/stats', headers=auth())
    assert code == 200
    assert 'Access-Control-Allow-Origin' in headers, 'CORS missing on GET'


# ============ TEST 7: /api/audit requires auth ============
def t7():
    code, body, _ = req(f'{BASE}/api/audit?tail=10')
    assert code == 401


# ============ TEST 8: /api/audit returns entries ============
def t8():
    req(f'{BASE}/', headers={'Authorization': 'Basic ' + BAD_CREDS})  # Failed auth
    req(f'{BASE}/api/stats', headers=auth())
    import time
    time.sleep(0.1)
    code, body, _ = req(f'{BASE}/api/audit?tail=20', headers=auth())
    assert code == 200
    data = json.loads(body)
    assert data.get('ok') is True
    assert data.get('count', 0) > 0, 'no audit entries'
    line = data['lines'][0]
    assert '| ip=' in line
    assert '| action=' in line
    assert '| result=' in line


# ============ TEST 9: Rate limit triggers after N requests ============
def t9():
    xff_headers = {**auth(), 'X-Forwarded-For': '10.99.99.99'}
    codes = []
    for i in range(115):
        code, body, _ = req(f'{BASE}/api/stats', headers=xff_headers, timeout=2)
        codes.append(code)
        if code == 429:
            break
    assert 429 in codes, f'expected 429 in codes, got: {codes[:20]}...'
    code, body, headers = req(f'{BASE}/api/stats', headers=xff_headers, timeout=2)
    if code == 429:
        assert 'Retry-After' in headers
        data = json.loads(body)
        assert 'retry_after' in data


# ============ TEST 10: POST /punch with bad device_ip -> 400 ============
def t10():
    code, body, _ = req(f'{BASE}/punch', method='POST',
                        data={'user_id': '123', 'status': '0', 'device_ip': 'bad ip with spaces!'},
                        headers=auth())
    assert code == 400, f'expected 400, got {code}: {body[:100]}'


# ============ TEST 11: POST /punch happy path -> 200 ============
def t11():
    code, body, _ = req(f'{BASE}/punch', method='POST',
                        data={'user_id': '999', 'status': '0', 'device_ip': '172.16.0.212'},
                        headers=auth())
    assert code in (200, 303), f'expected 200/303, got {code}'


# ============ TEST 12: Auth failure is audited ============
def t12():
    req(f'{BASE}/', headers={'Authorization': 'Basic ' + BAD_CREDS})
    import time
    time.sleep(0.1)
    code, body, _ = req(f'{BASE}/api/audit?tail=50', headers=auth())
    data = json.loads(body)
    found_denied = any('auth_failed' in line and 'result=denied' in line for line in data['lines'])
    assert found_denied, f'no auth_failed audit entry. Lines: {data["lines"][-5:]}'


# ============ Run all ============
tests = [t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12]
passed = 0
failed = 0
for t in tests:
    if test(t.__name__, t):
        passed += 1
    else:
        failed += 1

print('=' * 60)
print(f'RESULT: {passed}/{len(tests)} PASS, {failed} FAIL')
print('=' * 60)
sys.exit(0 if failed == 0 else 1)
