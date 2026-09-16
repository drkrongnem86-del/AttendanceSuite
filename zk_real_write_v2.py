# -*- coding: utf-8 -*-
"""
ZK X628 PRO - REAL ATTLOG WRITE TEST (v2)
Format đúng từ pyzk source:
- PREPARE_DATA: pack('I', size) - 4 bytes uint32 only
- CMD_DATA: binary chunks of 1024 bytes
- ATTLOG record (16 bytes): user_id(I) + timestamp(I) + status(B) + punch(B) + reserved(H) + workcode(I)
- Timestamp encode: ((year%100)*12*31 + (month-1)*31 + day-1)*86400 + hour*3600 + min*60 + sec
"""
import sys, os, struct, time
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

def encode_time(t):
    """Encode datetime thành uint32 như pyzk làm"""
    return ((t.year % 100) * 12 * 31 + (t.month - 1) * 31 + t.day - 1) * (24 * 60 * 60) + (t.hour * 60 + t.minute) * 60 + t.second

def make_attlog_record(user_id, dt, status=0, punch=15, workcode=0):
    """Pack 1 ATTLOG record 16 bytes"""
    ts = encode_time(dt)
    return struct.pack('<IIBBHI', user_id, ts, status, punch, 0, workcode)

print('=' * 70)
print(f'ZK X628 PRO - REAL ATTLOG WRITE TEST v2')
print('=' * 70)

# === TEST 1: Write 1 fake ATTLOG record ===
print('\n[1] Write 1 fake ATTLOG record...')
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'  Connected')

# Baseline
z.read_sizes()
baseline_records = z.records
print(f'  Baseline records: {baseline_records}')

# Build 1 record: PIN=1383, time=2026-09-14 17:30:00, status=1 (out), punch=15 (finger)
test_dt = datetime(2026, 9, 14, 17, 30, 0)
record = make_attlog_record(1383, test_dt, status=1, punch=15)
print(f'  Record: {record.hex()}')

# Build complete buffer (16 bytes)
buffer = record
size = len(buffer)

# FREE_DATA first
z.free_data()

# PREPARE_DATA - 4 bytes uint32 size
prep = struct.pack('I', size)
resp = z._ZK__send_command(const.CMD_PREPARE_DATA, prep)
print(f'  PREPARE_DATA: {resp}')

# CMD_DATA - send actual data
resp2 = z._ZK__send_command(const.CMD_DATA, buffer)
print(f'  CMD_DATA: {resp2}')

# FREE_DATA
z.free_data()
print(f'  FREE_DATA done')

time.sleep(1)

# Check new count
try:
    z.read_sizes()
    new_records = z.records
    print(f'  After write: records = {new_records}')
    if new_records != baseline_records:
        print(f'  🔥🔥🔥 RECORDS CHANGED! {baseline_records} → {new_records} 🔥🔥🔥')
    else:
        print(f'  records unchanged: {baseline_records}')
except Exception as e:
    print(f'  Check failed: {e}')

z.disconnect()
print('  Disconnected')

# === TEST 2: Try different buffer formats ===
print('\n[2] Try different buffer formats...')
formats = [
    # Format A: just 1 record 16 bytes
    ('1x16', make_attlog_record(1383, datetime(2026, 9, 14, 17, 31, 0), 1, 15)),
    # Format B: 2 records 32 bytes
    ('2x16', make_attlog_record(1383, datetime(2026, 9, 14, 17, 32, 0), 0, 15) +
              make_attlog_record(1383, datetime(2026, 9, 14, 17, 33, 0), 1, 15)),
    # Format C: 8-byte format (legacy)
    ('1x8', struct.pack('<HB4sB', 1383, 1, struct.pack('<I', encode_time(datetime(2026, 9, 14, 17, 34, 0))), 15)),
    # Format D: 40-byte format (with name)
    ('1x40', struct.pack('<H24sB4sB8s', 1383, b'THUYNTT4\x00' + b'\x00'*15, 1,
                          struct.pack('<I', encode_time(datetime(2026, 9, 14, 17, 35, 0))), 15, b'\x00'*8)),
    # Format E: with size prefix in buffer
    ('with_size', struct.pack('I', 16) + make_attlog_record(1383, datetime(2026, 9, 14, 17, 36, 0), 1, 15)),
    # Format F: TSV text
    ('tsv', b'1383\t2026-09-14 17:37:00\t1\t15'),
    # Format G: TSV multi-line
    ('tsv_multi', b'1383\t2026-09-14 17:38:00\t1\t15\n1383\t2026-09-14 17:39:00\t0\t15'),
]

for name, buf in formats:
    print(f'\n  [{name}] len={len(buf)}, hex={buf[:32].hex() if len(buf) > 0 else "empty"}')
    z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
    try:
        z.connect()
        z.read_sizes()
        before = z.records

        z.free_data()
        prep = struct.pack('I', len(buf))
        resp = z._ZK__send_command(const.CMD_PREPARE_DATA, prep)
        print(f'    PREPARE_DATA: code={resp.get("code")}')

        if resp.get('code') in (2000, 1500):
            resp2 = z._ZK__send_command(const.CMD_DATA, buf)
            print(f'    CMD_DATA: {resp2}')
            z.free_data()

            time.sleep(0.5)
            try:
                z.read_sizes()
                after = z.records
                if after != before:
                    print(f'    🔥 RECORDS CHANGED! {before} → {after}')
                else:
                    print(f'    records: {before} (no change)')
            except Exception as e:
                print(f'    check failed: {str(e)[:40]}')
        z.disconnect()
    except Exception as e:
        print(f'    ERROR: {str(e)[:80]}')
    time.sleep(0.3)

# === TEST 3: Write 16-byte record + read back to verify ===
print('\n[3] Write record + read back via get_attendance...')
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()
print(f'  Before: records={z.records}')

# Write 1 record
test_dt = datetime(2026, 9, 14, 17, 50, 0)
record = make_attlog_record(1383, test_dt, status=1, punch=15)

z.free_data()
z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(record)))
z._ZK__send_command(const.CMD_DATA, record)
z.free_data()

time.sleep(1)

# Read back
try:
    z.read_sizes()
    print(f'  After: records={z.records}')

    # Get attendance and look for our test record
    attendances = z.get_attendance()
    print(f'  Got {len(attendances)} attendance records')

    # Find records near 2026-09-14 17:50
    found = False
    for att in attendances[-50:]:  # last 50 records
        if att.timestamp.year == 2026 and att.timestamp.month == 9 and att.timestamp.day == 14 and att.timestamp.hour == 17:
            print(f'  - {att}')
            if att.timestamp.minute == 50:
                found = True

    if found:
        print(f'  🔥🔥🔥 FOUND OUR FAKE RECORD! 🔥🔥🔥')
except Exception as e:
    print(f'  Read failed: {e}')

z.disconnect()
print('  Disconnected')

print('\n' + '=' * 70)
print('DONE')
print('=' * 70)
