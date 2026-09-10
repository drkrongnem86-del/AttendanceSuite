# -*- coding: utf-8 -*-
"""
zk_recon.py - Discovery toàn diện cho máy chấm công ZKTeco X628 PRO
Chạy tại máy trong mạng LAN BV, output ra zk_recon_report.json
Gửi file này lại cho người phân tích.

Usage:
  python zk_recon.py [--out zk_recon_report.json]
"""
import os
import sys
import json
import socket
import struct
import time
import urllib.request
import urllib.error
import ssl
from datetime import datetime

socket.setdefaulttimeout(3.0)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


# ============ CONFIG ============
DEVICES_CSV = "devices.csv"  # optional, neu co trong cung thu muc
OUT_FILE = "zk_recon_report.json"

# Port can scan
PORTS_TO_SCAN = [
    (80, "http"), (443, "https"), (8080, "http-alt"), (8000, "http-alt2"),
    (4370, "zk-udp"), (4370, "zk-tcp"),  # ZK protocol
    (8081, "x628-sim"), (8888, "alt"), (9999, "alt"),
    (80, "isapi"), (8080, "isapi"),
]

# HTTP paths can thu tren moi may
HTTP_PATHS = [
    "/", "/index.html", "/login", "/login.html", "/admin",
    "/checkin", "/checkin.html", "/punch", "/attendance",
    "/iclock", "/iclock/", "/iclock/cdata",
    "/iWsService", "/iWSService",
    "/cgi-bin/", "/cgi-bin/checkin.cgi", "/cgi-bin/attendance",
    "/form", "/form.html", "/form/checkin",
    "/att", "/attlog", "/attlog.html",
    "/api/", "/api/checkin", "/api/punch", "/api/v1/",
    "/adms", "/adms/", "/adms/command",
    "/ISAPI/", "/ISAPI/ContentMgmt/InputProxy",
    "/SDK/", "/SDK/web",
    "/user", "/users", "/device", "/devices",
    "/zk", "/zkweb", "/zknet",
    "/cgi-bin/AttSnap", "/cgi-bin/attlog",
]

# ZK protocol commands (UDP 4370) - test connection
# Reference: pyzk source code
ZK_CMD_CONNECT = 1000
ZK_CMD_EXIT = 1001
ZK_CMD_ENABLEDEVICE = 1002
ZK_CMD_DISABLEDEVICE = 1003
ZK_CMD_RESTART = 1004
ZK_CMD_POWEROFF = 1005
ZK_CMD_SLEEP = 1006
ZK_CMD_RESUME = 1007
ZK_CMD_TESTVOICE = 1017
ZK_CMD_GETVERSION = 1100
ZK_CMD_DEV = 1102
ZK_CMD_DATA = 1500
ZK_CMD_DATA_WRRQ = 1503
ZK_CMD_DATA_RDY = 1504
ZK_CMD_DB_RRQ = 1502
# Attendance log read
ZK_CMD_ATTLOG_RRQ = 1501


# ============ HTTP PROBE ============
def http_probe(ip, port, use_ssl=False, timeout=2.0):
    """Thu 1 request GET den ip:port, tra ve (code, size, preview, has_form)."""
    scheme = "https" if use_ssl else "http"
    url = f"{scheme}://{ip}:{port}/"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        if use_ssl:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                body = r.read(50000)
                code = r.status
        else:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(50000)
                code = r.status
        txt = body.decode(errors='ignore').lower()
        has_form = '<form' in txt or '<input' in txt
        return {'code': code, 'size': len(body),
                'preview': body[:500].decode(errors='ignore'),
                'has_form': has_form}
    except urllib.error.HTTPError as e:
        return {'code': e.code, 'size': 0, 'preview': '', 'has_form': False}
    except Exception as e:
        return {'code': None, 'error': str(e)[:80]}


def scan_http_paths(ip, port, use_ssl=False, timeout=1.5):
    """Scan nhieu path tren 1 host:port."""
    results = []
    scheme = "https" if use_ssl else "http"
    for path in HTTP_PATHS:
        url = f"{scheme}://{ip}:{port}{path}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            if use_ssl:
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                    body = r.read(50000)
                    code = r.status
            else:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read(50000)
                    code = r.status
            if code == 200 and 0 < len(body) < 50000:
                txt = body.decode(errors='ignore').lower()
                keywords = []
                for kw in ['checkin', 'punch', 'vân tay', 'fingerprint', 'login',
                           'admin', 'zkteco', 'x628', 'iclock', 'adms',
                           'attlog', 'attendance', 'user id', 'mã nv']:
                    if kw in txt:
                        keywords.append(kw)
                results.append({
                    'path': path, 'code': code, 'size': len(body),
                    'has_form': '<form' in txt or '<input' in txt,
                    'keywords': keywords[:5],
                    'preview': body[:300].decode(errors='ignore').replace('\n', ' ')[:200],
                })
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                results.append({'path': path, 'code': e.code, 'auth_required': True})
        except Exception:
            pass
    return results


# ============ ZK PROTOCOL PROBE ============
def zk_udp_ping(ip, port=4370, timeout=2.0):
    """
    Thu gui ZK CMD_CONNECT (1000) qua UDP den may.
    Neu may phan hoi -> mo co the ket noi ZK protocol.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        # ZK header: command (2 bytes) + checksum (2 bytes) + session_id (2 bytes) + reply_id (2 bytes) + data
        # CMD_CONNECT = 1000
        cmd = struct.pack('<HHHH', 1000, 0, 0, 0) + b'\x00' * 4
        s.sendto(cmd, (ip, port))
        data, addr = s.recvfrom(1024)
        s.close()
        if len(data) >= 8:
            reply_cmd, _, session, reply_id = struct.unpack('<HHHH', data[:8])
            return {
                'reply_cmd': reply_cmd,
                'session_id': session,
                'reply_id': reply_id,
                'raw_hex': data[:32].hex(),
                'reachable': True,
            }
        return {'reachable': True, 'short_reply': data.hex()}
    except socket.timeout:
        return {'reachable': False, 'reason': 'timeout (may khong phan hoi UDP)'}
    except Exception as e:
        return {'reachable': False, 'reason': str(e)[:80]}


def zk_tcp_connect(ip, port=4370, timeout=2.0):
    """
    Thu TCP connect den ZK port 4370.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t0 = time.time()
        s.connect((ip, port))
        ms = int((time.time() - t0) * 1000)
        s.close()
        return {'tcp_open': True, 'latency_ms': ms}
    except Exception as e:
        return {'tcp_open': False, 'reason': str(e)[:80]}


# ============ ICLOUD / ICLOCK PUSH PROBE ============
def probe_iclock(ip, port=80, timeout=2.0):
    """
    Thu goi ICLOCK PUSH protocol nhu mot server.
    Mot so may ZK cho phep server PUSH lenh xuong may.
    """
    results = []
    # Thu GET /iclock/getrequest (may yeu cau server lay lenh)
    for path in ['/iclock/getrequest', '/iclock/devicecmd', '/iclock/ping',
                 '/iWsService', '/iWsService/']:
        url = f"http://{ip}:{port}{path}"
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'iClock Proxy',
                'Content-Type': 'text/plain',
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(2000)
                txt = body.decode(errors='ignore')
                results.append({
                    'path': path, 'method': 'GET',
                    'code': r.status, 'body_preview': txt[:200]
                })
        except urllib.error.HTTPError as e:
            results.append({'path': path, 'method': 'GET', 'code': e.code})
        except Exception:
            pass
    return results


# ============ SECUTIME PROBE ============
def probe_secutime(ip='172.16.0.31', ports=(80, 8080, 443)):
    """
    Neu Secutime dang chay, thu cac path API pho bien.
    """
    results = []
    paths = ['/', '/api/', '/api/login', '/api/employees', '/api/attendance',
             '/iclock', '/iclock/', '/iWsService', '/iWsService/',
             '/iclock/getrequest', '/cgi-bin/', '/login',
             '/swagger', '/api/swagger', '/docs',
             '/api/v1/', '/api/v1/employees', '/api/v1/attendance',
             '/api/v1/employee/checkin', '/api/v1/device/punch']
    for port in ports:
        scheme = "https" if port == 443 else "http"
        for path in paths:
            url = f"{scheme}://{ip}:{port}{path}"
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                if port == 443:
                    with urllib.request.urlopen(req, timeout=1.5, context=ctx) as r:
                        body = r.read(20000)
                        code = r.status
                else:
                    with urllib.request.urlopen(req, timeout=1.5) as r:
                        body = r.read(20000)
                        code = r.status
                if code == 200:
                    txt = body.decode(errors='ignore').lower()
                    kws = [k for k in ['employee', 'attendance', 'secutime', 'zkteco',
                                       'checkin', 'punch', 'iclock', 'login']
                           if k in txt]
                    results.append({
                        'port': port, 'path': path, 'code': code,
                        'size': len(body), 'keywords': kws[:5],
                        'preview': body[:300].decode(errors='ignore').replace('\n', ' ')[:200],
                    })
            except Exception:
                pass
    return results


# ============ MAIN ============
def load_devices_csv():
    """Load devices.csv neu co, tra ve list cac IP."""
    ips = []
    if not os.path.exists(DEVICES_CSV):
        # fallback: hardcode list tu project
        ips = [
            "172.16.0.30", "172.16.0.31", "172.16.0.200", "172.16.0.212",
            "172.16.0.213", "172.16.0.214", "172.16.0.215", "172.16.0.217",
            "172.16.0.218", "172.16.0.219", "172.16.0.220", "172.16.0.221",
            "172.16.0.222", "172.16.0.223", "172.16.0.224", "172.16.0.225",
            "172.16.0.226", "172.16.0.228", "172.16.1.204", "172.16.1.210",
            "172.16.1.211", "172.16.1.212", "172.16.8.139", "172.16.8.140",
            "172.16.30.50", "172.16.100.201",
        ]
        return ips
    try:
        with open(DEVICES_CSV, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.lower().startswith('ip,'):
                    continue
                parts = line.split(',')
                ip = parts[0].strip()
                if ip:
                    ips.append(ip)
    except Exception as e:
        print(f"[!] Loi doc devices.csv: {e}")
    return ips


def main():
    out = {
        'started_at': datetime.now().isoformat(),
        'scanner_version': 'zk_recon v1.0',
        'note': 'Chay tai may trong mang LAN BV. Gui file nay lai cho nguoi phan tich.',
        'devices': [],
        'secutime': {},
        'summary': {},
    }

    ips = load_devices_csv()
    print(f"[*] Scan {len(ips)} thiet bi...\n")

    for i, ip in enumerate(ips, 1):
        print(f"[{i}/{len(ips)}] {ip}")
        dev = {
            'ip': ip,
            'tcp_4370': None,
            'udp_4370': None,
            'http_80': None,
            'https_443': None,
            'http_alt_ports': [],
            'interesting_paths': [],
        }

        # 1. TCP 4370 (ZK port)
        dev['tcp_4370'] = zk_tcp_connect(ip, 4370)

        # 2. UDP 4370 (ZK protocol ping)
        dev['udp_4370'] = zk_udp_ping(ip, 4370, timeout=1.5)

        # 3. HTTP root probes
        dev['http_80'] = http_probe(ip, 80, use_ssl=False)
        dev['https_443'] = http_probe(ip, 443, use_ssl=True)

        # 4. HTTP 8080, 8000
        for port in (8080, 8000):
            r = http_probe(ip, port, use_ssl=False, timeout=1.0)
            if r.get('code') not in (None, 0):
                dev['http_alt_ports'].append({'port': port, **r})

        # 5. Scan paths on port 80 (may co web that su)
        if dev['http_80'].get('code') == 200:
            paths = scan_http_paths(ip, 80)
            if paths:
                dev['interesting_paths'].extend([{**p, 'port': 80} for p in paths])

        # 6. Scan paths on port 8080 if open
        for port in (8080, 8000):
            r = next((x for x in dev['http_alt_ports'] if x.get('port') == port), None)
            if r and r.get('code') == 200:
                paths = scan_http_paths(ip, port)
                if paths:
                    dev['interesting_paths'].extend([{**p, 'port': port} for p in paths])

        # 7. ICLOCK PUSH probe (port 80)
        iclock = probe_iclock(ip, 80)
        if iclock:
            dev['iclock_probe'] = iclock

        # Summary
        hits = []
        if dev['tcp_4370'] and dev['tcp_4370'].get('tcp_open'):
            hits.append('tcp4370_open')
        if dev['udp_4370'] and dev['udp_4370'].get('reachable'):
            hits.append('udp4370_responds')
        if dev['http_80'] and dev['http_80'].get('code') == 200:
            hits.append('http80_ok')
        if dev['http_80'] and dev['http_80'].get('has_form'):
            hits.append('http80_has_form')
        if dev['http_80'] and dev['http_80'].get('code') in (401, 403):
            hits.append(f'http80_auth_required')
        if dev['https_443'] and dev['https_443'].get('code') == 200:
            hits.append('https443_ok')
        if dev['interesting_paths']:
            hits.append(f"paths_found:{len(dev['interesting_paths'])}")
        if dev.get('iclock_probe'):
            hits.append(f"iclock_paths:{len(dev['iclock_probe'])}")

        dev['verdict'] = hits
        out['devices'].append(dev)

        print(f"   verdict: {', '.join(hits) if hits else 'no response'}")

    # Secutime server
    print("\n[*] Probe Secutime server (172.16.0.31)...")
    out['secutime'] = probe_secutime('172.16.0.31')

    # Summary
    summary = {
        'total_devices': len(ips),
        'tcp_4370_open': sum(1 for d in out['devices']
                             if d['tcp_4370'] and d['tcp_4370'].get('tcp_open')),
        'udp_4370_responds': sum(1 for d in out['devices']
                                 if d['udp_4370'] and d['udp_4370'].get('reachable')),
        'http_80_ok': sum(1 for d in out['devices']
                          if d['http_80'] and d['http_80'].get('code') == 200),
        'http_80_with_form': sum(1 for d in out['devices']
                                 if d['http_80'] and d['http_80'].get('has_form')),
        'interesting_paths_total': sum(len(d.get('interesting_paths', []))
                                      for d in out['devices']),
        'secutime_paths_found': len(out['secutime']),
    }
    out['summary'] = summary
    out['finished_at'] = datetime.now().isoformat()

    # Write output
    out_path = OUT_FILE
    if len(sys.argv) > 1 and sys.argv[1] == '--out':
        out_path = sys.argv[2]

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)

    print("\n" + "=" * 70)
    print(f"[OK] Report saved: {os.path.abspath(out_path)}")
    print(f"     Total: {summary['total_devices']} devices")
    print(f"     TCP 4370 open: {summary['tcp_4370_open']}")
    print(f"     UDP 4370 responds: {summary['udp_4370_responds']}")
    print(f"     HTTP 80 OK: {summary['http_80_ok']}")
    print(f"     HTTP 80 with form: {summary['http_80_with_form']}")
    print(f"     Interesting paths: {summary['interesting_paths_total']}")
    print(f"     Secutime paths: {summary['secutime_paths_found']}")
    print("=" * 70)
    print("\nGUI FILE NAY LAI cho nguoi phan tich.")


if __name__ == '__main__':
    main()
