#!/usr/bin/env python3
"""Check what's left of ZKDB.db after partial upload."""
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

def download_file(conn, path, timeout_s=10):
    r = send_cmd(conn, 0x6A6, (path + '\x00').encode())
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
                if chunks > 100 and len(total) > 0: break
        except socket.timeout: break
    return total

zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
conn = zk.connect()
print('[+] Connected')

try: conn.disable_device()
except: pass

print('\n[*] Downloading current ZKDB.db...')
zkdb = download_file(conn, '/mnt/mtdblock/data/ZKDB.db', timeout_s=15)
print('  Got {} bytes'.format(len(zkdb)))

out = 'D:\\chamcong\\zk_inject_workspace\\current_zkdb_' + str(int(time.time())) + '.db'
with open(out, 'wb') as f:
    f.write(zkdb)
print('  Saved:', out)

# Try SQLite open
import sqlite3
try:
    db = sqlite3.connect(out)
    cur = db.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 5")
    print('  Tables:', [r[0] for r in cur.fetchall()])
    cur.execute('SELECT COUNT(*) FROM ATT_LOG')
    print('  ATT_LOG:', cur.fetchone()[0])
    db.close()
except Exception as e:
    print('  SQLite:', e)
    print('  First 100:', zkdb[:100])
    print('  Last 100:', zkdb[-100:])

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass
