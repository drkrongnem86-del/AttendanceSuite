# -*- coding: utf-8 -*-
"""
ZK X628 PRO - ATTLOG WRITE TEST (proper)
Use z.records / z.users instance attrs after read_sizes().
Test PREPARE_DATA → CMD_DATA → check if records count changes.
"""
import sys, os, struct, time
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

print('=' * 70)
print(f'ZK X628 PRO - ATTLOG WRITE TEST (PROPER)')
print('=' * 70)

def get_counts(z):
    """Get records/users counts via CMD_GET_FREE_SIZES"""
    z.read_sizes()
    return z.records, z.users

def get_attlog_count_via_cmd(z):
    """Get raw ATTLOG count via CMD_ATTLOG_RRQ header"""
    # The raw response header has 4-byte size
    resp = z._ZK__send_command(const.CMD_ATTLOG_RRQ, b'', response_size=8)
    if resp.get('status'):
        data = z._ZK__data
        if data and len(data) >= 4:
            # First 4 bytes = total size
            return struct.unpack('<I', data[:4])[0]
    return None

# Connect
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'Connected: FW={z.get_firmware_version()}, Serial={z.get_serialnumber()}')

# Baseline
print('\n[1] Baseline...')
records, users = get_counts(z)
print(f'  records (ATTLOG count): {records}')
print(f'  users: {users}')

# Try ATTLOG via raw cmd
raw_count = get_attlog_count_via_cmd(z)
print(f'  raw ATTLOG header count: {raw_count}')

# === TEST 1: PREPARE_DATA flow với ATTLOG payload formats ===
print('\n[2] PREPARE_DATA flow test...')

# Build payload that LOOKS like a real attendance record
# Real ATT_LOG row from ZKDB.db:
# (4, '1383', '2026-09-14 17:30:00', 1, 15, 0, 0, 0, '', 0)
# When sent via ZK protocol, format might be:
# "PIN\tTime\tStatus\tVerify\t..." or specific binary

test_payloads = [
    # Format 1: TSV (like USB backup)
    (b'PIN=1383\tTime=2026-09-14 17:30:00\tStatus=1\tVerify=15', 'TSV'),
    # Format 2: Plain TSV
    (b'1383\t2026-09-14 17:30:00\t1\t15', 'PlainTSV'),
    # Format 3: With UID prefix
    (b'1\t1383\t2026-09-14 17:30:00\t1\t15\t0', 'UID_Prefix'),
    # Format 4: PUSH-style
    (b'PIN\t1383\tDATETIME\t2026-09-14 17:30:00\tSTATUS\t1\tVERIFY\t15', 'PUSH_Style'),
    # Format 5: Just timestamp + PIN
    (b'1383 2026-09-14 17:30:00 1 15', 'Space_Sep'),
    # Format 6: Binary struct
    (struct.pack('<I', 1383) + b'2026-09-14 17:30:00\x00' + struct.pack('<I', 1) + struct.pack('<I', 15), 'Binary'),
    # Format 7: Empty test
    (b'\x00' * 256, 'Zeros'),
    # Format 8: SQLite row dump
    (b'(1383, \'2026-09-14 17:30:00\', 1, 15)', 'SQLite'),
]

for payload, desc in test_payloads:
    print(f'\n  [{desc}] payload={payload[:50]!r}...')
    try:
        # PREPARE_DATA
        prep = struct.pack('<H', 20560) + struct.pack('<I', len(payload))
        resp = z._ZK__send_command(const.CMD_PREPARE_DATA, prep)
        print(f'    PREPARE_DATA: {resp}')

        if resp.get('code') in (2000, 1500):
            # CMD_DATA
            resp2 = z._ZK__send_command(const.CMD_DATA, payload)
            print(f'    CMD_DATA: {resp2}')

            # CMD_FREE_DATA
            resp3 = z._ZK__send_command(const.CMD_FREE_DATA, b'')
            print(f'    FREE_DATA: {resp3}')

            data = z._ZK__data
            if data:
                print(f'    data after PREPARE flow: {len(data)} bytes, first 80: {data[:80]!r}')

            time.sleep(0.5)
            # Check counts
            new_records, new_users = get_counts(z)
            print(f'    records: {records} → {new_records}')
            if new_records != records:
                print(f'    🔥🔥🔥 RECORDS CHANGED! {records} → {new_records} 🔥🔥🔥')
                records = new_records
            if new_users != users:
                print(f'    🔥 USERS CHANGED! {users} → {new_users}')
                users = new_users
    except Exception as e:
        err = str(e)[:60]
        print(f'    ERROR: {err}')

# === TEST 2: Try 0x2712 (CMD_GET_PULL_DATA) với magic payloads - check returned data ===
print('\n[3] Test 0x2712 với payloads - đọc full data response...')
test_data_payloads = [
    b'FINGER',
    b'ATTLOG',
    b'USER',
    b'OPLOG',
    b'SMS',
    b'UDATA',
    b'1',
    b'0',
    b'',
    b'\x00',
    b'\x01\x00\x00\x00',
    b'\x00\x10\x00\x00',
]
for payload in test_data_payloads:
    try:
        resp = z._ZK__send_command(0x2712, payload, response_size=4096)
        if isinstance(resp, dict) and resp.get('code') in (1500, 1501, 2002):
            data = z._ZK__data
            if data:
                print(f'  0x2712 {payload!r}: code={resp["code"]}, data_len={len(data)}, data[:64]={data[:64]!r}')
        else:
            code = resp.get('code') if isinstance(resp, dict) else resp
            print(f'  0x2712 {payload!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        print(f'  0x2712 {payload!r}: {err}')

# === TEST 3: Try 0x2711 (CMD_SET_PULL_DATA) với ON/OFF payloads ===
print('\n[4] Test 0x2711 (SET_PULL_DATA) - check if it triggers data flow...')
for payload in [b'ON', b'OFF', b'1', b'0', b'\x01', b'\x00']:
    try:
        resp = z._ZK__send_command(0x2711, payload, response_size=4096)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  0x2711 {payload!r}: {resp}')

        # After SET, try GET
        if code == 2000:
            resp2 = z._ZK__send_command(0x2712, b'', response_size=4096)
            data = z._ZK__data
            if data and len(data) > 0:
                print(f'    → After SET, GET returned {len(data)} bytes: {data[:64]!r}')
    except Exception as e:
        print(f'  0x2711 {payload!r}: {str(e)[:40]}')

# === TEST 4: Try 0x0BC2 with proper payload format ===
print('\n[5] Test 0x0BC2 (APP_PULL_USERS) với proper payloads...')
for payload in [b'\x01\x00\x00\x00', b'1', b'PIN=1', b'\x00\x00\x00\x00',
                struct.pack('<II', 1, 100), b'1,2,3,4,5']:
    try:
        resp = z._ZK__send_command(0x0BC2, payload, response_size=4096)
        code = resp.get('code') if isinstance(resp, dict) else resp
        if code == 1501 or code == 2002:
            data = z._ZK__data
            print(f'  0x0BC2 {payload[:30]!r}: code={code}, data={data[:100]!r}')
        else:
            print(f'  0x0BC2 {payload[:30]!r}: {resp}')
    except Exception as e:
        print(f'  0x0BC2 {payload[:30]!r}: {str(e)[:40]}')

# === TEST 5: Final check ===
print('\n[6] Final state check...')
final_records, final_users = get_counts(z)
print(f'  Final: records={final_records}, users={final_users}')
print(f'  CHANGE: records {records - final_records if isinstance(records, int) and isinstance(final_records, int) else "?"}')

z.disconnect()
print('\nDONE')
