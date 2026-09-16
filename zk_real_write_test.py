# -*- coding: utf-8 -*-
"""
ZK X628 PRO - REAL DATA WRITE TEST
PREPARE_DATA flow + CMD_DATA + CMD_FREE_DATA - check if ATTLOG changes.
Plus: đọc full response data từ các commands trả 1501 (CMD_ACK_DATA).
"""
import sys, os, struct, time, json, sqlite3, io
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

print('=' * 70)
print(f'ZK X628 PRO - REAL DATA WRITE TEST')
print('=' * 70)

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'Connected: FW={z.get_firmware_version()}, Serial={z.get_serialnumber()}')

# === STEP 1: Get baseline ATTLOG count ===
print('\n[1] Get baseline ATTLOG count...')
try:
    sizes = z.read_sizes()
    print(f'  Free sizes: {sizes}')
    # sizes has: users, fingers, records, etc.
    baseline_attlog = sizes.get('record_count', 'unknown')
    baseline_users = sizes.get('user_count', 'unknown')
    print(f'  Baseline ATTLOG count: {baseline_attlog}')
    print(f'  Baseline users: {baseline_users}')
except Exception as e:
    print(f'  ERROR: {e}')

# === STEP 2: Try PREPARE_DATA → CMD_DATA flow với various payloads ===
print('\n[2] PREPARE_DATA flow với ATTLOG-like payload...')

# Real ATTLOG format from ZKDB.db:
# (ID, BADGENUMBER, CHECKTIME, CHECKTYPE, VERIFYCODE, SENSORID, Memoinfo, WorkCode, sn, UserExtFmt)
# Try various payload formats
payload_tests = [
    # Plain text format
    b'PIN=1\t2026-09-14 23:00:00\t0\t15\t0\t0\t0\t0\t0',
    # TSV (tab-separated) format like USB backup
    b'1\t2026-09-14 23:00:00\t0\t15\t0\t0\t0\t0\t0',
    # SQLite row format
    b'4\t1383\t2026-09-14 23:00:00\t1\t15\t0\t0\t0\t0\t0',
    # PUSH protocol format
    b'PIN=1383\tTime=2026-09-14 23:00:00\tStatus=1\tVerify=15',
    # ADMS-style format
    b'PIN=1383\t2026-09-14 23:00:00\t1\t15\t0\t0\t0\t0\t0',
    # Finger record
    b'PIN=1383\tFID=0\tSize=1024\tValid=1\tTemplate=AAAA',
    # User record
    b'PIN=1383\tName=TestUser\tPrivilege=14\tPassword=1',
    # Random binary
    b'\x01\x00\x00\x00\x83\x13\x00\x00' + b'\x00' * 100,
    # Larger payload
    b'A' * 4096,
    # UTF-16
    ('PIN=1383\t2026-09-14 23:00:00\t1\t15\t0\t0\t0\t0\t0').encode('utf-16-le'),
]

for i, payload in enumerate(payload_tests):
    print(f'\n  Test #{i+1}: payload={payload[:50]!r}...')
    try:
        # STEP 1: PREPARE_DATA with magic 20560
        prep_data = struct.pack('<H', 20560) + struct.pack('<I', len(payload))
        resp = z._ZK__send_command(const.CMD_PREPARE_DATA, prep_data)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'    PREPARE_DATA: {resp}')

        if code in (2000, 1500):
            # STEP 2: CMD_DATA with actual payload
            resp2 = z._ZK__send_command(const.CMD_DATA, payload)
            print(f'    CMD_DATA: {resp2}')

            # STEP 3: CMD_FREE_DATA
            resp3 = z._ZK__send_command(const.CMD_FREE_DATA, b'')
            print(f'    FREE_DATA: {resp3}')

            # Check ATTLOG count
            time.sleep(1)
            try:
                new_sizes = z.read_sizes()
                new_attlog = new_sizes.get('record_count', 'unknown')
                if new_attlog != baseline_attlog:
                    print(f'    🔥 ATTLOG COUNT CHANGED: {baseline_attlog} → {new_attlog}')
                    baseline_attlog = new_attlog
                else:
                    print(f'    ATTLOG count: {new_attlog} (no change)')
            except Exception as e:
                print(f'    check sizes: {e}')
    except Exception as e:
        err = str(e)[:60]
        print(f'    ERROR: {err}')

# === STEP 3: Test 0x2712 với payload 'FINGER' - đọc full response ===
print('\n[3] Test 0x2712 với payload "FINGER" - đọc full response...')
try:
    # CMD_GET_PULL_DATA
    resp = z._ZK__send_command(0x2712, b'FINGER')
    print(f'  Response: {resp}')
    # If status True and code 1501 = CMD_ACK_DATA, there's data attached
except Exception as e:
    print(f'  ERROR: {e}')

# === STEP 4: Test 0x0BC2 (CMD_APP_PULL_USERS) - đọc response data ===
print('\n[4] Test 0x0BC2 với payload - đọc response data...')
try:
    # Try various payloads
    for payload in [b'', b'PIN=1', b'\x01\x00\x00\x00']:
        resp = z._ZK__send_command(0x0BC2, payload)
        print(f'  Payload={payload!r}: {resp}')
except Exception as e:
    print(f'  ERROR: {e}')

# === STEP 5: Test 0x2744-0x2753 với read-style payloads ===
print('\n[5] Test 0x2744-0x2753 với read payloads...')
for cmd in [0x2744, 0x2745, 0x2750, 0x2751, 0x2752, 0x2753]:
    for payload in [b'', b'\x00\x00\x00\x00', b'1', b'\x01\x00\x00\x00']:
        try:
            resp = z._ZK__send_command(cmd, payload)
            code = resp.get('code') if isinstance(resp, dict) else resp
            if code not in (65535, 2000, 2001):
                print(f'  0x{cmd:04X} payload={payload!r}: {resp}')
        except Exception as e:
            pass

# === STEP 6: Test CMD_USER_WRQ (8) với payload format đặc biệt ===
print('\n[6] Test CMD_USER_WRQ (8) với payload format đặc biệt...')
user_payloads = [
    # Standard format (UID + privilege + name + card + password)
    b'1\x1414TestUser00000001',
    # UID + privilege + name + password (no card)
    b'1\x1414TestUser0001',
    # Just UID + privilege
    b'1\x1414',
    # UID + name
    b'1TestUser',
]
for p in user_payloads:
    try:
        resp = z._ZK__send_command(const.CMD_USER_WRQ, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  USER_WRQ {p[:30]!r}: {resp}')
    except Exception as e:
        print(f'  USER_WRQ {p[:30]!r}: {str(e)[:40]}')

# === STEP 7: Test direct pyzk.set_user() ===
print('\n[7] Test pyzk.set_user() - add real user...')
try:
    # This normally works (we verified before)
    # But check what error happens with non-existent UID
    z.set_user(uid=9999, name='TestUser9999', privilege=0, password='test', group_id='', user_id='', card='0')
    print(f'  set_user 9999: success (unexpected!)')

    # Check if user exists
    users = z.get_users()
    found = any(str(u.uid) == '9999' for u in users)
    if found:
        print(f'  🔥 USER 9999 ADDED to device!')
except Exception as e:
    print(f'  set_user 9999: {str(e)[:60]}')

# === STEP 8: Check existing users ===
print('\n[8] List existing users on device...')
try:
    users = z.get_users()
    print(f'  Total users: {len(users)}')
    # Show first 5
    for u in users[:5]:
        print(f'  - UID={u.uid}, name={u.name!r}, priv={u.privilege}, card={u.card!r}')
except Exception as e:
    print(f'  ERROR: {e}')

# === STEP 9: Final check - ATTLOG count ===
print('\n[9] Final ATTLOG count check...')
try:
    sizes = z.read_sizes()
    print(f'  Final free sizes: {sizes}')
    final_attlog = sizes.get('record_count', 'unknown')
    print(f'  Final ATTLOG count: {final_attlog}')
    if baseline_attlog != 'unknown' and final_attlog != 'unknown':
        if baseline_attlog != final_attlog:
            print(f'  🔥 ATTLOG CHANGED: {baseline_attlog} → {final_attlog}')
        else:
            print(f'  ATTLOG count unchanged: {baseline_attlog}')
except Exception as e:
    print(f'  ERROR: {e}')

z.disconnect()
print('\nDONE')
