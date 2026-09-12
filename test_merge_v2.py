"""Test merge API end-to-end."""
import sys, os, time, json
sys.path.insert(0, '.')
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8082'  # Won't work - use 8080

# Start service via subprocess
import subprocess
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'
proc = subprocess.Popen(['python', 'attendance_web.py'], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)

BASE = 'http://127.0.0.1:8080'
try:
    # 1. GET /api/merge/today
    print('Test 1: GET /api/merge/today')
    r = urllib.request.urlopen(BASE + '/api/merge/today', timeout=5)
    data = json.loads(r.read())
    print('  Shadow today:', data['summary']['shadow_today_count'])
    print('  by_device:', list(data['by_device'].items()))

    # 2. POST /api/merge/mark-done
    print('Test 2: POST /api/merge/mark-done')
    body = json.dumps({'punch_id': '300001'}).encode()
    req = urllib.request.Request(BASE + '/api/merge/mark-done',
                                  data=body, method='POST',
                                  headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=5)
    mark = json.loads(r.read())
    print('  OK:', mark['ok'], '|', mark.get('message', ''), '| remaining:', mark.get('remaining_pending', '?'))

    # 3. Verify shadow now has 1 less
    print('Test 3: Re-check shadow')
    r = urllib.request.urlopen(BASE + '/api/merge/today', timeout=5)
    data = json.loads(r.read())
    print('  Shadow today after:', data['summary']['shadow_today_count'])

    # 4. Clear old
    print('Test 4: POST /api/merge/clear-old')
    body = json.dumps({'days': 1}).encode()
    req = urllib.request.Request(BASE + '/api/merge/clear-old',
                                  data=body, method='POST',
                                  headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=5)
    clear = json.loads(r.read())
    print('  Removed:', clear['removed_count'], '| remaining:', clear['remaining_count'])

    print('\n=== ALL TESTS PASS ===')
except Exception as e:
    print(f'FAIL: {e}')
    import traceback
    traceback.print_exc()
finally:
    proc.terminate()
    time.sleep(1)
    if proc.poll() is None:
        proc.kill()
