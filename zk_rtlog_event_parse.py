# -*- coding: utf-8 -*-
"""
ZK X628 PRO - CMD 0x58/0x59 ANALYSIS (TRUE WRITE COMMAND!)
CMD 0x58 returns code=1500 (PREPARE_DATA)
CMD 0x59 returns code=1501 (DATA ready)
This is the REAL WRITE command!
Hãy parse format và gửi ATTLOG record.
"""
import sys, struct, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
import zk
from zk import const

DEVICE_IP = '172.16.0.214'

def encode_time(t):
    return ((t.year % 100) * 12 * 31 + (t.month - 1) * 31 + t.day - 1) * (24 * 60 * 60) + (t.hour * 60 + t.minute) * 60 + t.second

def decode_time(t):
    year_offset = t // (12 * 31 * 86400)
    if 17 <= year_offset <= 30:
        year = 2000 + year_offset
        remaining = t - year_offset * 12 * 31 * 86400
        month = (remaining // (31 * 86400)) + 1
        remaining = remaining - (month - 1) * 31 * 86400
        day = (remaining // 86400) + 1
        remaining = remaining - (day - 1) * 86400
        hour = remaining // 3600
        remaining = remaining - hour * 3600
        minute = remaining // 60
        second = remaining - minute * 60
        return f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
    return f"?({year_offset})"

print('=' * 70)
print(f'ZK X628 PRO - CMD 0x58/0x59 RTLOG WRITE ANALYSIS')
print('=' * 70)

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()
baseline = z.records
print(f'Connected, baseline records={baseline}')

# Subscribe events
z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', 0xFF))

# Get the data first
print('\n[1] Trigger CMD 0x58/0x59 to see what device sends...')
for cmd_id in [0x58, 0x59]:
    try:
        resp = z._ZK__send_command(cmd_id, b'', response_size=8192)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        print(f'  CMD 0x{cmd_id:02X}: code={code}, data_len={len(data) if data else 0}')
        if data and len(data) > 4:
            total = struct.unpack('<I', data[:4])[0]
            print(f'    Total header: {total}')
            # Try various record sizes
            for rec_size in [8, 16, 20, 32, 40, 64, 80, 128]:
                if total > 0 and total % rec_size == 0:
                    n = total // rec_size
                    print(f'    Possible: {rec_size} bytes/record × {n} records')
                    # Show first record
                    rec_data = data[4:4+rec_size]
                    print(f'      First record: {rec_data.hex()}')
                    # Try parsing
                    if rec_size == 16:
                        try:
                            uid, ts, status, punch, res, wc = struct.unpack('<IIBBHI', rec_data)
                            print(f'      Parse 16-bytes: uid={uid} ts={decode_time(ts)} status={status} punch={punch} res={res} wc={wc}')
                        except:
                            pass
                    elif rec_size == 8:
                        try:
                            uid, status, ts_bytes, punch = struct.unpack('<HB4sB', rec_data)
                            ts = struct.unpack('<I', ts_bytes)[0]
                            print(f'      Parse 8-bytes: uid={uid} status={status} ts={ts}({decode_time(ts)}) punch={punch}')
                        except:
                            pass
    except Exception as e:
        print(f'  CMD 0x{cmd_id:02X}: ERROR {e}')

# Try sending ATTLOG data via CMD 0x58/0x59
print('\n[2] Now try sending fake ATTLOG via CMD 0x58/0x59...')

# Step 1: try with various ATTLOG formats via PREPARE_DATA flow
attlog_payloads = [
    # 16-byte binary ATTLOG (1 record)
    struct.pack('<IIBBHI', 1383, encode_time(__import__('datetime').datetime(2026, 9, 15, 8, 30, 0)), 0, 15, 0, 0),
    # 8-byte binary ATTLOG (1 record)
    struct.pack('<HB4sB', 1383, 0, struct.pack('<I', encode_time(__import__('datetime').datetime(2026, 9, 15, 8, 30, 0))), 15),
    # TSV
    b'1383\t2026-09-15 08:30:00\t0\t15',
    # Header + payload (like pyzk)
    struct.pack('I', 16) + struct.pack('<IIBBHI', 1383, encode_time(__import__('datetime').datetime(2026, 9, 15, 8, 30, 0)), 0, 15, 0, 0),
]

# Refresh connection
try:
    z.disconnect()
except:
    pass
z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
z.read_sizes()
print(f'  Fresh connect, records={z.records}')
z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', 0xFF))

for i, payload in enumerate(attlog_payloads, 1):
    print(f'\n  Try payload #{i}: {payload[:40]!r}...')
    try:
        # Send via PREPARE_DATA flow with CMD 0x58
        # First PREPARE_DATA with size only
        prep = struct.pack('I', len(payload))
        resp = z._ZK__send_command(const.CMD_PREPARE_DATA, prep)
        print(f'    PREPARE_DATA: {resp}')

        # Then CMD 0x59 to send/handshake
        resp2 = z._ZK__send_command(0x59, payload, response_size=4096)
        code2 = resp2.get('code') if isinstance(resp2, dict) else resp2
        data = z._ZK__data
        print(f'    CMD 0x59 (DATA): code={code2}, data_len={len(data) if data else 0}')
        if data:
            print(f'    data first 80: {data[:80].hex()}')

        # Free data
        z.free_data()
        time.sleep(0.5)

        # Check count
        try:
            z.read_sizes()
            if z.records != baseline:
                print(f'    🔥🔥🔥 RECORDS CHANGED: {baseline} → {z.records}')
                baseline = z.records
            else:
                print(f'    records: {z.records}')
        except Exception as e:
            print(f'    check failed: {str(e)[:40]}')
    except Exception as e:
        print(f'    ERROR: {str(e)[:60]}')

    # Refresh after each test
    try:
        z.disconnect()
    except:
        pass
    z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
    z.connect()
    z.read_sizes()
    z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', 0xFF))

# === Test: read RTLOG with CMD_QUERY_DATA (0x5DF) + FCT_ATTLOG=1 ===
print('\n[3] CMD_QUERY_DATA (0x5DF) with FCT_ATTLOG=1 (read using buffered)...')
try:
    payload = struct.pack('<bhii', 1, const.CMD_ATTLOG_RRQ, 1, 0)  # fct=ATTLOG=1, ext=0
    resp = z._ZK__send_command(0x5DF, payload, response_size=8192)
    code = resp.get('code') if isinstance(resp, dict) else resp
    data = z._ZK__data
    print(f'  Code: {code}, data_len={len(data) if data else 0}')
    if data:
        print(f'  Data[:80]: {data[:80].hex()}')
except Exception as e:
    print(f'  ERROR: {e}')

# Check final state
try:
    z.read_sizes()
    print(f'\n[Final] records={z.records}, users={z.users}')
except Exception as e:
    print(f'  Final check fail: {e}')

try:
    z.disconnect()
except:
    pass
print('\nDone')
