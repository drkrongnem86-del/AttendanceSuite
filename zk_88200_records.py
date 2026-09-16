# -*- coding: utf-8 -*-
"""
ZK X628 PRO - WRITE TEST WITH 20-byte ATTLOG records
Total records: 88200 với 20 bytes/record = 88,204 với 8 bytes/record
Format 20-byte: uid(I) + ts(I) + ts2(I) + name(20) → let's verify
Format 40-byte: uid(H) + name(24) + ts(4s) + status(B) + punch(B) + space(8s) = 40
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

print('=' * 70)
print(f'ZK X628 PRO - 20-byte ATTLOG WRITE TEST')
print('=' * 70)

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()
print(f'Baseline records: {z.records}')

# Get RTLOG data with 88204 records
print('\n[1] Get RTLOG to verify record format...')
z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', 0xFF))
resp = z._ZK__send_command(0x58, b'', response_size=8192)
data = z._ZK__data
if data:
    total = struct.unpack('<I', data[:4])[0]
    print(f'  CMD 0x58 total: {total}')
    resp = z._ZK__send_command(0x59, b'', response_size=8192)
    data = z._ZK__data
    if data:
        total = struct.unpack('<I', data[:4])[0]
        print(f'  CMD 0x59 total: {total}')
        # Show first 5 records of 40-byte format (since it's clearly structured)
        # First record check
        print(f'  First 80 bytes (records 1-2 in 40-byte format):')
        first_two = data[4:4+80]
        for i in range(0, len(first_two), 40):
            rec = first_two[i:i+40]
            if len(rec) >= 40:
                uid_h = struct.unpack('<H', rec[:2])[0]
                name = rec[2:26].split(b'\x00')[0].decode(errors='ignore')
                ts_bytes = rec[26:30]
                ts = struct.unpack('<I', ts_bytes)[0]
                status = rec[30]
                punch = rec[31]
                space = rec[32:40]
                print(f'    Record @ {i}: uid={uid_h} name={name!r} ts={ts} status={status} punch={punch} space={space.hex()}')

# Now construct fake ATTLOG record và send via PREPARE_DATA + CMD_DATA
print('\n[2] Build 40-byte fake ATTLOG + try PREPARE_DATA write...')

test_dt = datetime(2026, 9, 15, 9, 0, 0)
ts = encode_time(test_dt)

# 40-byte format: uid(H) + name(24s) + ts(4s) + status(B) + punch(B) + space(8s)
fake_record_40 = struct.pack('<H24sI BB8s',
                               1383,
                               b'THUYNTT4\x00' + b'\x00'*15,  # 24 bytes
                               ts,
                               0, 15,
                               b'\x00'*8)

# 8-byte format
fake_record_8 = struct.pack('<HB4sB', 1383, 0, struct.pack('<I', ts), 15)

# 16-byte format
fake_record_16 = struct.pack('<IIBBHI', 1383, ts, 0, 15, 0, 0)

# Just header (4 bytes)
fake_header = struct.pack('I', 16)

print(f'  fake_record_40 hex: {fake_record_40.hex()}')
print(f'  fake_record_16 hex: {fake_record_16.hex()}')
print(f'  fake_record_8 hex: {fake_record_8.hex()}')

# === Test 1: PREPARE_DATA + CMD_DATA with 40-byte record ===
print('\n[3] PREPARE_DATA + CMD_DATA với 40-byte ATTLOG record...')
try:
    z.free_data()
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(fake_record_40)))
    print(f'  PREPARE_DATA: {resp}')
    resp2 = z._ZK__send_command(const.CMD_DATA, fake_record_40)
    print(f'  CMD_DATA: {resp2}')
    z.free_data()
    time.sleep(1)
    z.read_sizes()
    new_count = z.records
    print(f'  After: records={z.records}, baseline={99825}')
    if new_count != 99825:
        print(f'  🔥 RECORDS CHANGED!')
except Exception as e:
    print(f'  ERROR: {e}')

# Refresh
try: z.disconnect()
except: pass
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()

# === Test 2: PREPARE_DATA + CMD_DATA with 16-byte record ===
print('\n[4] PREPARE_DATA + CMD_DATA với 16-byte ATTLOG record...')
try:
    z.free_data()
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(fake_record_16)))
    print(f'  PREPARE_DATA: {resp}')
    resp2 = z._ZK__send_command(const.CMD_DATA, fake_record_16)
    print(f'  CMD_DATA: {resp2}')
    z.free_data()
    time.sleep(1)
    z.read_sizes()
    print(f'  After: records={z.records}')
except Exception as e:
    print(f'  ERROR: {e}')

# === Test 3: PREPARE_DATA + CMD_DATA with 8-byte record ===
print('\n[5] PREPARE_DATA + CMD_DATA với 8-byte ATTLOG record...')
try:
    z.free_data()
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(fake_record_8)))
    print(f'  PREPARE_DATA: {resp}')
    resp2 = z._ZK__send_command(const.CMD_DATA, fake_record_8)
    print(f'  CMD_DATA: {resp2}')
    z.free_data()
    time.sleep(1)
    z.read_sizes()
    print(f'  After: records={z.records}')
except Exception as e:
    print(f'  ERROR: {e}')

# === Test 4: PREPARE_DATA với big size (50000 = full buffer), then check ===
print('\n[6] PREPARE_DATA with large size = full buffer...')
try:
    z.free_data()
    # Total ATTLOG size = 88204
    resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', 88204))
    print(f'  PREPARE_DATA 88204: {resp}')
    # Try without sending data
    z.free_data()
    resp2 = z._ZK__send_command(0x59, b'', response_size=8192)
    code = resp2.get('code') if isinstance(resp2, dict) else resp2
    print(f'  CMD 0x59 after PREPARE: {code}')
except Exception as e:
    print(f'  ERROR: {e}')

# === Test 5: Check ATTLOG directly via read_with_buffer (gets real ATTLOG) ===
print('\n[7] Read all ATTLOG records via read_with_buffer + count them...')
try:
    att_data, size = z.read_with_buffer(const.CMD_ATTLOG_RRQ)
    print(f'  Total ATTLOG size: {size} bytes')
    # Parse as 8-byte records
    n8 = size // 8
    print(f'  If 8-byte format: {n8} records')
    n16 = size // 16
    print(f'  If 16-byte format: {n16} records')
    n40 = size // 40
    print(f'  If 40-byte format: {n40} records')
    n20 = size // 20
    print(f'  If 20-byte format: {n20} records')

    # Search for PIN 1383 to confirm format
    pin_1383_packed = struct.pack('<H', 1383)
    pos = att_data.find(pin_1383_packed)
    if pos >= 0:
        print(f'  Found PIN 1383 (H) at offset {pos}')
        # Check record at this offset (assume 40-byte)
        if pos + 40 <= len(att_data):
            rec = att_data[pos:pos+40]
            uid_h = struct.unpack('<H', rec[:2])[0]
            name = rec[2:26].split(b'\x00')[0].decode(errors='ignore')
            ts_bytes = rec[26:30]
            ts = struct.unpack('<I', ts_bytes)[0]
            status = rec[30]
            punch = rec[31]
            print(f'    Parse 40: uid={uid_h} name={name!r} ts={ts} status={status} punch={punch}')
    # Try PIN as uint32
    pin_1383_packed_i = struct.pack('<I', 1383)
    pos2 = att_data.find(pin_1383_packed_i)
    if pos2 >= 0:
        print(f'  Found PIN 1383 (I) at offset {pos2}')

    # Show first and last records
    print(f'\n  First 80 bytes: {att_data[:80].hex()}')
    print(f'  Last 80 bytes: {att_data[-80:].hex()}')

    # Count records - try 8 bytes first
    print('\n  Count records assuming 8-byte format:')
    count = 0
    last_uid = 0
    for i in range(0, len(att_data), 8):
        if i + 8 > len(att_data): break
        uid_h, status, ts_bytes, punch = struct.unpack('<HB4sB', att_data[i:i+8])
        if uid_h > 0 and uid_h < 10000:
            count += 1
            last_uid = uid_h
    print(f'    Valid records: {count}, last UID: {last_uid}')

except Exception as e:
    print(f'  ERROR: {e}')

# Final
try:
    z.read_sizes()
    print(f'\n[Final] records={z.records}')
except:
    pass
try: z.disconnect()
except: pass
print('Done')
