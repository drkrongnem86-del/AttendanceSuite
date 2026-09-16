# -*- coding: utf-8 -*-
"""
ZK X628 PRO - RTLOG ANALYSIS
CMD_RTLOG_RRQ (0x5A) returned 1344 bytes data - REAL-TIME LOG!
Hãy parse format kỹ và tìm cách WRITE tương ứng.
"""
import sys, os, struct, time
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

print('=' * 70)
print(f'ZK X628 PRO - RTLOG ANALYSIS')
print('=' * 70)

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'Connected')

# Read RTLOG multiple times to see if data changes
print('\n[1] Read RTLOG 3 times với delay...')
for i in range(3):
    resp = z._ZK__send_command(0x5A, b'', response_size=8192)
    data = z._ZK__data
    if data:
        print(f'  Read #{i+1}: {len(data)} bytes, first 32 hex: {data[:32].hex()}')
        # Check total_size header
        if len(data) >= 4:
            total = struct.unpack('<I', data[:4])[0]
            print(f'    Total reported: {total} bytes')
            print(f'    Header: {data[:4].hex()}')
            # Show rows (after 4-byte header)
            print(f'    Data[:200]: {data[4:204].hex()}')
    else:
        print(f'  Read #{i+1}: no data')
    time.sleep(2)

# Parse format - find patterns
print('\n[2] Parse RTLOG format...')
resp = z._ZK__send_command(0x5A, b'', response_size=8192)
data = z._ZK__data
if data and len(data) >= 4:
    total_size = struct.unpack('<I', data[:4])[0]
    records_data = data[4:]
    print(f'  Total expected: {total_size}, actual: {len(records_data)}')

    # Try various record sizes
    for record_size in [16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64]:
        if len(records_data) >= total_size and total_size % record_size == 0:
            n_records = total_size // record_size
            print(f'  Record size {record_size} → {n_records} records (matches!)')
            # Show first record
            if n_records > 0:
                first = records_data[:record_size]
                print(f'    First record: {first.hex()}')
                # Try parsing as different formats
                if record_size == 16:
                    # Try (uid I + ts I + status B + punch B + reserved H + workcode I)
                    uid, ts, status, punch, res, wc = struct.unpack('<IIBBHI', first)
                    print(f'    Parse 16: uid={uid} ts={ts} status={status} punch={punch} res={res} wc={wc}')
                elif record_size == 8:
                    uid, status, ts, punch = struct.unpack('<HB4sB', first)
                    print(f'    Parse 8: uid={uid} status={status} ts_bytes={ts.hex()} punch={punch}')
        elif len(records_data) >= 16:
            n16 = len(records_data) // 16
            print(f'  Try record_size=16: {n16} records (data {len(records_data)} bytes)')

    # Try to find record header by looking for PINs known on device
    print('\n[3] Search for known PINs (1383 = THUYNTT4)...')
    pin_1383 = b'\x67\x05\x00\x00'  # 1383 little-endian
    pos = records_data.find(pin_1383)
    if pos >= 0:
        print(f'  Found PIN 1383 at offset {pos}: {records_data[pos-4:pos+20].hex()}')
        # Parse as 16-byte record
        if pos + 16 <= len(records_data):
            rec = records_data[pos:pos+16]
            uid, ts, status, punch, res, wc = struct.unpack('<IIBBHI', rec)
            print(f'    uid={uid} timestamp={ts} status={status} punch={punch} reserved={res} workcode={wc}')
            # Decode timestamp
            if ts > 0:
                # ZK timestamp: ((year%100)*12*31 + (month-1)*31 + day-1) * 86400 + h*3600 + m*60 + s
                secs = ts
                year_offset = secs // (12 * 31 * 86400)
                if 17 <= year_offset <= 30:  # 2017-2030
                    year = 2000 + year_offset
                    remaining = secs - year_offset * 12 * 31 * 86400
                    month = (remaining // (31 * 86400)) + 1
                    remaining = remaining - (month - 1) * 31 * 86400
                    day = (remaining // 86400) + 1
                    remaining = remaining - (day - 1) * 86400
                    hour = remaining // 3600
                    remaining = remaining - hour * 3600
                    minute = remaining // 60
                    second = remaining - minute * 60
                    print(f'    Decoded time: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}')
    else:
        print(f'  PIN 1383 not found in last {len(records_data)} bytes')

    # Show distinctive data after offset 256 (likely various records)
    for off in [0, 16, 32, 48, 64, 128, 256, 512, 768, 1024]:
        if off < len(records_data):
            print(f'\n  Offset {off}: {records_data[off:off+32].hex()}')

# === Test write attempts related to RTLOG ===
print('\n[4] Test WRITE commands for RTLOG...')
# 0x5A = CMD_RTLOG_RRQ. Try mirrors:
# 0x5B = CMD_SSRHTZ_RRQ (from gist) - or possibly RTLOG_WRQ?
# 0x5C = CMD_SSRHTZ_WRQ
write_candidates = [0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60]

for cmd in write_candidates:
    # Test first with empty payload
    try:
        resp = z._ZK__send_command(cmd, b'')
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  CMD 0x{cmd:04X} empty: code={code}')
        z.disconnect()
        z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
        z.connect()
    except Exception as e:
        print(f'  CMD 0x{cmd:04X} empty: {str(e)[:40]}')
        try:
            z.disconnect()
        except:
            pass
        z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
        z.connect()

# Test CMD_SSRHTZ_WRQ (0x5C) - might be SSR HTZ write
print('\n[5] Test CMD_SSRHTZ_WRQ (0x5C) with payload...')
try:
    payload = b'\x67\x05\x00\x00\x01'  # PIN 1383, status 1
    resp = z._ZK__send_command(0x5C, payload)
    code = resp.get('code') if isinstance(resp, dict) else resp
    print(f'  Code: {code}')
except Exception as e:
    print(f'  ERROR: {e}')

z.disconnect()
print('\nDONE')
