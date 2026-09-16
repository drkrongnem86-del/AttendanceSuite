# -*- coding: utf-8 -*-
"""
ZK X628 PRO - PLAIN TSV WRITE TEST
Critical finding: PREPARE_DATA với payload PlainTSV (PIN\tTime\tStatus\tVerify)
trả code 1501 (CMD_ACK_DATA) - device parse thành công!
Test fresh connection + variants để xác định format chính xác.
"""
import sys, os, struct, time
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'Dchamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

print('=' * 70)
print(f'ZK X628 PRO - PLAIN TSV WRITE TEST')
print('=' * 70)

def get_counts(z):
    z.read_sizes()
    return z.records, z.users

# === TEST 1: Fresh connection + baseline + PlainTSV write ===
print('\n[1] Fresh connection + PlainTSV write...')
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'  Connected: FW={z.get_firmware_version()}, Serial={z.get_serialnumber()}')

baseline_records, baseline_users = get_counts(z)
print(f'  Baseline: records={baseline_records}, users={baseline_users}')

# Send PREPARE_DATA với PlainTSV
payload = b'1383\t2026-09-14 17:30:00\t1\t15'
print(f'\n  Sending PREPARE_DATA với payload: {payload!r}')

try:
    prep = struct.pack('<H', 20560) + struct.pack('<I', len(payload))
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, prep)
    print(f'  PREPARE_DATA: {resp}')

    if resp.get('code') == 1501:
        # Device wants data - send CMD_DATA
        print(f'  → Device ready (code 1501), sending CMD_DATA...')
        resp2 = z._ZK__send_command(const.CMD_DATA, payload)
        print(f'  CMD_DATA: {resp2}')

        # Read back data
        data = z._ZK__data
        if data:
            print(f'  data after CMD_DATA: {len(data)} bytes')
            print(f'  data first 100: {data[:100]!r}')

        # FREE_DATA
        resp3 = z._ZK__send_command(const.CMD_FREE_DATA, b'')
        print(f'  FREE_DATA: {resp3}')

        time.sleep(1)
        new_records, new_users = get_counts(z)
        print(f'\n  After write: records={baseline_records} → {new_records}')
        if new_records != baseline_records:
            print(f'  🔥🔥🔥 RECORDS CHANGED! {baseline_records} → {new_records} 🔥🔥🔥')
        else:
            print(f'  records unchanged: {baseline_records}')
except Exception as e:
    print(f'  ERROR: {str(e)[:80]}')

z.disconnect()
print('  Disconnected')

# === TEST 2: Variants của PlainTSV format ===
print('\n[2] Test variants của PlainTSV format (each new connection)...')
variants = [
    b'1383\t2026-09-14 17:30:00\t1\t15',                    # Base
    b'1383\t2026-09-14 17:30:00',                            # No status/verify
    b'1383\t2026-09-14 17:30:00\t1',                         # Only status
    b'1383 2026-09-14 17:30:00 1 15',                        # Space sep
    b'1383,2026-09-14 17:30:00,1,15',                        # Comma sep
    b'1383|2026-09-14 17:30:00|1|15',                        # Pipe sep
    b'1383:2026-09-14 17:30:00:1:15',                        # Colon sep
    b'PIN=1383\tTIME=2026-09-14 17:30:00\tSTATUS=1\tVERIFY=15',
    b'PIN\t1383\tTIME\t2026-09-14 17:30:00\tSTATUS\t1\tVERIFY\t15',
    b'1383\t17:30\t1\t15\t2026-09-14',                       # Time first
    b'1383\t14/09/2026 17:30:00\t1\t15',                     # DD/MM/YYYY format
    b'1383\t09/14/2026 17:30:00\t1\t15',                     # MM/DD/YYYY format
    b'1383\t2026-09-14T17:30:00\t1\t15',                     # ISO format
    b'1383\t2026-09-14 17:30:00.000\t1\t15',                 # With milliseconds
    b'1\t1383\t2026-09-14 17:30:00\t1\t15\t0',               # With UID prefix 0
    b'1383\t2026-09-14 17:30:00\t1\t15\t0\t0\t0\t0\t0',     # 10 columns (full ATTLOG)
]

for payload in variants:
    print(f'\n  Payload: {payload[:60]!r}')
    z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
    try:
        z.connect()
        # Read baseline
        z.read_sizes()
        before = z.records

        # PREPARE_DATA
        prep = struct.pack('<H', 20560) + struct.pack('<I', len(payload))
        resp = z._ZK__send_command(const.CMD_PREPARE_DATA, prep)
        code = resp.get('code')
        print(f'    PREPARE_DATA: code={code}')

        if code == 1501:
            # Send CMD_DATA
            resp2 = z._ZK__send_command(const.CMD_DATA, payload)
            code2 = resp2.get('code') if isinstance(resp2, dict) else resp2
            print(f'    CMD_DATA: code={code2}')

            # FREE
            z._ZK__send_command(const.CMD_FREE_DATA, b'')

            time.sleep(0.5)
            try:
                z.read_sizes()
                after = z.records
                if after != before:
                    print(f'    🔥 RECORDS CHANGED! {before} → {after}')
                else:
                    print(f'    records: {before} (no change)')
            except:
                pass

        z.disconnect()
    except Exception as e:
        err = str(e)[:40]
        print(f'    ERROR: {err}')
        try:
            z.disconnect()
        except:
            pass
    time.sleep(0.3)

# === TEST 3: Send multiple PREPARE_DATA + CMD_DATA without disconnect ===
print('\n[3] Multiple PREPARE_DATA flows trong 1 session...')
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()
print(f'  Baseline: records={z.records}, users={z.users}')

payloads_to_try = [
    b'1383\t2026-09-14 17:30:00\t1\t15',          # PlainTSV
    b'9999\t2026-09-14 17:30:00\t1\t15',          # Different PIN
    b'1383\t2026-09-14 17:31:00\t1\t15',          # Different time
    b'1383\t2026-09-14 17:32:00\t1\t15',          # Different time 2
]

for payload in payloads_to_try:
    try:
        prep = struct.pack('<H', 20560) + struct.pack('<I', len(payload))
        resp = z._ZK__send_command(const.CMD_PREPARE_DATA, prep)
        code = resp.get('code')
        print(f'  PREPARE {payload[:40]!r}: code={code}')

        if code == 1501:
            resp2 = z._ZK__send_command(const.CMD_DATA, payload)
            print(f'  CMD_DATA: {resp2}')
            z._ZK__send_command(const.CMD_FREE_DATA, b'')
            time.sleep(0.5)
            z.read_sizes()
            print(f'  records now: {z.records}')
    except Exception as e:
        print(f'  ERROR: {str(e)[:60]}')
        break

z.disconnect()
print('  Disconnected')

# === TEST 4: Test what 0x2712 'FINGER' actually does with response_size ===
print('\n[4] 0x2712 with response_size=0...')
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()

for payload in [b'FINGER', b'ATTLOG', b'1', b'']:
    try:
        resp = z._ZK__send_command(0x2712, payload, response_size=0)
        print(f'  0x2712 {payload!r}: {resp}')
    except Exception as e:
        print(f'  0x2712 {payload!r}: {str(e)[:40]}')

# Get any data attached
try:
    data = z._ZK__data
    if data:
        print(f'  __data after: {len(data)} bytes, first 100: {data[:100]!r}')
except:
    pass

z.disconnect()
print('\nDONE')
