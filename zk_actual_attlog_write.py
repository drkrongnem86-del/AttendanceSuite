# -*- coding: utf-8 -*-
"""
ZK X628 PRO - ACTUAL ATTLOG WRITE WITH PROPER FORMAT
Confirmed: ATTLOG = 99,825 records × 40 bytes + 4 byte header = 3,993,004 bytes
Record format: uid(H=2) + user_id(24s) + status(B=1) + ts(4s) + punch(B=1) + space(8s) = 40

Strategy: Gửi 1 fake record qua PREPARE_DATA + CMD_DATA. Nếu device accept,
records phải tăng 1 → 99826.
"""
import sys, struct, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
import zk
from zk import const
from datetime import datetime

DEVICE_IP = '172.16.0.214'

def encode_time(t):
    return ((t.year % 100) * 12 * 31 + (t.month - 1) * 31 + t.day - 1) * (24 * 60 * 60) + (t.hour * 60 + t.minute) * 60 + t.second

def make_attlog_40(uid, user_id_str, ts, status, punch):
    """Build 40-byte ATTLOG record"""
    name_bytes = user_id_str.encode('utf-8')[:24].ljust(24, b'\x00')
    ts_bytes = struct.pack('<I', ts)
    space = b'\x00' * 8
    return struct.pack('<H24sB4sB8s', uid, name_bytes, status, ts_bytes, punch, space)

print('=' * 70)
print(f'ZK X628 PRO - ACTUAL ATTLOG WRITE TEST')
print('=' * 70)

# === Test 1: Single record via PREPARE_DATA ===
print('\n[1] Single fake record via PREPARE_DATA + CMD_DATA...')
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()
print(f'  baseline: records={z.records}, users={z.users}')

# Build single fake record
ts = encode_time(datetime(2026, 9, 15, 10, 0, 0))
record = make_attlog_40(1383, '1383', ts, 0, 15)  # status=0 (in), punch=15 (finger)
print(f'  Record ({len(record)} bytes): {record.hex()}')

# Send via PREPARE_DATA + CMD_DATA
try:
    z.free_data()
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', 40))
    print(f'  PREPARE_DATA 40: {resp}')
    resp2 = z._ZK__send_command(const.CMD_DATA, record)
    print(f'  CMD_DATA: {resp2}')
    z.free_data()
    time.sleep(1)
    z.read_sizes()
    print(f'  After: records={z.records}')
    if z.records != 99825:
        delta = z.records - 99825
        print(f'  🔥🔥🔥 RECORDS CHANGED! delta={delta}')
except Exception as e:
    print(f'  ERROR: {e}')

# Refresh
try: z.disconnect()
except: pass
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()

# === Test 2: Multiple records - 100 fake records ===
print('\n[2] 100 fake records (4000 bytes)...')
buffer = b''
for i in range(100):
    rec = make_attlog_40(1383, '1383', ts + i*60, 0, 15)
    buffer += rec

try:
    z.free_data()
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(buffer)))
    print(f'  PREPARE_DATA {len(buffer)}: {resp}')

    # Send in 1024-byte chunks (like pyzk does)
    MAX_CHUNK = 1024
    remain = len(buffer)
    packets = remain // MAX_CHUNK
    print(f'  Packets: {packets}, last chunk: {remain % MAX_CHUNK}')

    for i in range(packets):
        chunk = buffer[i*MAX_CHUNK:(i+1)*MAX_CHUNK]
        resp = z._ZK__send_command(const.CMD_DATA, chunk)
        print(f'  CMD_DATA chunk #{i+1}: {resp}')

    if remain % MAX_CHUNK:
        resp = z._ZK__send_command(const.CMD_DATA, buffer[packets*MAX_CHUNK:])
        print(f'  CMD_DATA last chunk: {resp}')

    z.free_data()
    time.sleep(2)
    z.read_sizes()
    print(f'  After: records={z.records}')
    if z.records != 99825:
        delta = z.records - 99825
        print(f'  🔥🔥🔥 RECORDS CHANGED! delta={delta}')
except Exception as e:
    print(f'  ERROR: {e}')

# Refresh
try: z.disconnect()
except: pass
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()

# === Test 3: Full 99825 records + 1 fake = 99826 records ===
print('\n[3] Test with FULL existing buffer + 1 new record...')
try:
    # Read existing ATTLOG
    att_data, size = z.read_with_buffer(const.CMD_ATTLOG_RRQ)
    print(f'  Read existing: {size} bytes')

    # Build existing + 1 new
    full_buffer = att_data + make_attlog_40(1383, '1383', ts, 0, 15)
    print(f'  New buffer: {len(full_buffer)} bytes')

    # Send via PREPARE_DATA + CMD_DATA
    z.free_data()
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(full_buffer)))
    print(f'  PREPARE_DATA: {resp}')

    # Send in chunks
    MAX_CHUNK = 1024
    for i in range(0, len(full_buffer), MAX_CHUNK):
        chunk = full_buffer[i:i+MAX_CHUNK]
        resp = z._ZK__send_command(const.CMD_DATA, chunk)
        # Don't print every chunk
    print(f'  All chunks sent')

    z.free_data()
    time.sleep(2)

    # Verify
    try:
        z.read_sizes()
        print(f'  After: records={z.records}')
        delta = z.records - 99825
        if delta != 0:
            print(f'  🔥🔥🔥 RECORDS CHANGED! delta={delta}')
    except Exception as e:
        print(f'  Check failed: {e}')

    # Verify by reading ATTLOG
    new_att, new_size = z.read_with_buffer(const.CMD_ATTLOG_RRQ)
    print(f'  New ATTLOG size: {new_size} bytes')
    if new_size != size:
        print(f'  🔥 ATTLOG SIZE CHANGED! delta_bytes={new_size - size}')

except Exception as e:
    print(f'  ERROR: {e}')

# === Test 4: Try TSV format with size header ===
print('\n[4] Try TSV format...')
tsv = b'1383\t2026-09-15 11:00:00\t0\t15'
try:
    z.free_data()
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(tsv)))
    print(f'  PREPARE_DATA TSV: {resp}')
    resp2 = z._ZK__send_command(const.CMD_DATA, tsv)
    print(f'  CMD_DATA TSV: {resp2}')
    z.free_data()
    time.sleep(1)
    z.read_sizes()
    print(f'  After: records={z.records}')
except Exception as e:
    print(f'  ERROR: {e}')

# === Final ===
print('\n[Final]')
try:
    z.read_sizes()
    print(f'  records={z.records}, users={z.users}')
except:
    pass

try: z.disconnect()
except: pass
print('Done')
