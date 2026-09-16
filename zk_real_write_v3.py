# -*- coding: utf-8 -*-
"""
ZK X628 PRO - REAL ATTLOG WRITE TEST v3
Phát hiện: device ACK_OK but records KHÔNG tăng. Thử:
1. Ghi NHIỀU records (10+)
2. Sleep + restart
3. Đợi lâu hơn
4. Check ATTLOG count qua raw CMD_ATTLOG_RRQ
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
    return ((t.year % 100) * 12 * 31 + (t.month - 1) * 31 + t.day - 1) * (24 * 60 * 60) + (t.hour * 60 + t.minute) * 60 + t.second

print('=' * 70)
print(f'ZK X628 PRO - REAL ATTLOG WRITE TEST v3')
print('=' * 70)

# === TEST 1: Write 100 8-byte records then check + restart ===
print('\n[1] Write 100 fake 8-byte records, then restart device...')
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()

z.read_sizes()
baseline = z.records
print(f'  Baseline: records={baseline}, record_size={baseline}*8={baseline*8} bytes')

# Build 100 fake 8-byte records
buffer = b''
for i in range(100):
    dt = datetime(2026, 9, 14, 18, i % 60, 0)
    ts = encode_time(dt)
    # Format: uid(H) + status(B) + ts(4s) + punch(B)
    rec = struct.pack('<HB4sB', 1383, 1, struct.pack('<I', ts), 15)
    buffer += rec

print(f'  Buffer: {len(buffer)} bytes = 100 records')

# Send via PREPARE_DATA + CMD_DATA + FREE_DATA
z.free_data()
resp = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(buffer)))
print(f'  PREPARE_DATA: {resp}')

resp2 = z._ZK__send_command(const.CMD_DATA, buffer)
print(f'  CMD_DATA: {resp2}')

z.free_data()
print(f'  FREE_DATA done')

# Wait
print('  Waiting 5s...')
time.sleep(5)

# Check without restart
try:
    z.read_sizes()
    after_no_restart = z.records
    print(f'  After write (no restart): records={after_no_restart}')
    if after_no_restart != baseline:
        print(f'  🔥 CHANGED WITHOUT RESTART! {baseline} → {after_no_restart}')
except Exception as e:
    print(f'  Check failed: {e}')

# Try CMD_REFRESHDATA
print('\n  CMD_REFRESHDATA...')
try:
    resp3 = z._ZK__send_command(const.CMD_REFRESHDATA, b'')
    print(f'  REFRESHDATA: {resp3}')
    time.sleep(2)
    z.read_sizes()
    after_refresh = z.records
    print(f'  After refresh: records={after_refresh}')
except Exception as e:
    print(f'  REFRESHDATA failed: {e}')

# Restart device!
print('\n  CMD_RESTART to flush...')
try:
    resp4 = z._ZK__send_command(const.CMD_RESTART, b'')
    print(f'  RESTART: {resp4}')
except Exception as e:
    print(f'  RESTART failed: {e}')

# Wait for restart
print('  Waiting 30s for device restart...')
time.sleep(30)

# Reconnect
print('\n  Reconnect after restart...')
try:
    z.disconnect()
except:
    pass

z2 = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
try:
    z2.connect()
    print(f'  Reconnected')
    z2.read_sizes()
    after_restart = z2.records
    print(f'  After RESTART: records={after_restart}')
    if after_restart != baseline:
        print(f'  🔥🔥🔥 RECORDS CHANGED AFTER RESTART! {baseline} → {after_restart} 🔥🔥🔥')
    else:
        print(f'  records unchanged after restart: {baseline}')

    # Get last few records
    atts = z2.get_attendance()
    print(f'  Total attendances: {len(atts)}')
    print(f'  Last 5 records:')
    for a in atts[-5:]:
        print(f'    {a}')
    z2.disconnect()
except Exception as e:
    print(f'  Reconnect failed: {e}')

# === TEST 2: Try direct CMD_ATTLOG_RRQ with response_size = small ===
print('\n[2] Read raw ATTLOG count via CMD_ATTLOG_RRQ with small response...')
z3 = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z3.connect()

# CMD_ATTLOG_RRQ (13) with empty payload, response_size=1024
# Header should have 4-byte size
try:
    resp = z3._ZK__send_command(const.CMD_ATTLOG_RRQ, b'', response_size=1024)
    code = resp.get('code') if isinstance(resp, dict) else resp
    print(f'  CMD_ATTLOG_RRQ: code={code}')
    data = z3._ZK__data
    if data:
        # First 4 bytes = total size
        if len(data) >= 4:
            total_size = struct.unpack('<I', data[:4])[0]
            print(f'  Total ATTLOG size: {total_size} bytes')
            print(f'  Total records: {total_size // 8} (8-byte) or {total_size // 16} (16-byte) or {total_size // 40} (40-byte)')
except Exception as e:
    print(f'  Failed: {e}')

z3.disconnect()

print('\n' + '=' * 70)
print('DONE')
print('=' * 70)
