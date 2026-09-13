"""
zk_security_scan.py - Scan tất cả máy ZK, báo cáo:
  1. Comm Key (default 0 = không bảo mật)
  2. Telnet port (mở = risk)
  3. HTTP port 80 (/form/DataApp unauth = risk)
  4. Users có password (có thể dùng PIN+password verify)
  5. Có ATTLOG với Verify_Type=0 (Password) không
"""
import csv
import socket
import sys
import os
import time
import urllib.request
import http.cookiejar
import sqlite3
import io
import gzip
from zk import ZK
from datetime import datetime

DEVICES_CSV = r"D:\chamcong\devices.csv"

def read_devices():
    """Read devices.csv -> list of (ip, note, selected)"""
    devices = []
    with open(DEVICES_CSV, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 4 and row[1] == 'attendance' and not row[0].startswith('virtual'):
                devices.append((row[0], row[2], row[3] == '1'))
    return devices


def scan_port(host, port, timeout=1.5):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        r = s.connect_ex((host, port))
        s.close()
        return r == 0
    except:
        return False


def download_zkdb(host):
    """Download ZKDB.db from /form/DataApp"""
    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        # Get cookie
        opener.open(f"http://{host}/", timeout=2).read()
        # Get DataApp
        resp = opener.open(f"http://{host}/form/DataApp?style=0", timeout=10)
        data = resp.read()
        if len(data) < 1000:
            return None
        # Find GZIP
        gzip_off = data.find(b'\x1f\x8b\x08', 100)
        if gzip_off < 0:
            return None
        with gzip.GzipFile(fileobj=io.BytesIO(data[gzip_off:])) as gz:
            zkdb = gz.read()
        # Skip 512-byte header
        if zkdb[:8] == b'ZKDB.db\x00':
            zkdb = zkdb[512:]
        return zkdb
    except Exception as e:
        return None


def analyze_zkdb(zkdb_data):
    """Analyze ZKDB.db for password & verify_type info"""
    try:
        # Save to temp
        tmp = r'D:\chamcong\zk_data_extracted\scan_temp.db'
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        with open(tmp, 'wb') as f:
            f.write(zkdb_data)

        conn = sqlite3.connect(tmp)
        conn.text_factory = lambda b: b.decode('cp1252', errors='replace') if isinstance(b, bytes) else b
        cur = conn.cursor()

        # Total users
        cur.execute('SELECT COUNT(*) FROM USER_INFO')
        total_users = cur.fetchone()[0]

        # Users with password
        cur.execute("SELECT COUNT(*) FROM USER_INFO WHERE Password IS NOT NULL AND Password != ''")
        users_with_pwd = cur.fetchone()[0]

        # ATTLOG by verify_type
        cur.execute('SELECT Verify_Type, COUNT(*) FROM ATT_LOG GROUP BY Verify_Type')
        verify_types = {vt: cnt for vt, cnt in cur.fetchall()}

        # Has password verify records?
        has_pwd_verify = verify_types.get(0, 0) > 0

        # Firmware
        # From /form/DataApp we can also get firmware via SDK

        conn.close()
        os.unlink(tmp)

        return {
            'total_users': total_users,
            'users_with_pwd': users_with_pwd,
            'verify_types': verify_types,
            'has_pwd_verify': has_pwd_verify,
        }
    except Exception as e:
        return None


def scan_device(host, note):
    """Scan a single device"""
    result = {
        'host': host,
        'note': note,
        'port_4370': False,
        'port_23_telnet': False,
        'port_80_http': False,
        'comm_key_default': False,
        'can_download_zkdb': False,
        'fw_version': None,
        'serial': None,
        'platform': None,
        'total_users': None,
        'users_with_pwd': None,
        'verify_types': {},
        'has_pwd_verify': False,
        'can_pin_pwd': False,
        'error': None,
    }

    # Port scan
    result['port_4370'] = scan_port(host, 4370)
    result['port_23_telnet'] = scan_port(host, 23)
    result['port_80_http'] = scan_port(host, 80)

    # Try pyzk connect (assumes Comm Key = 0)
    if result['port_4370']:
        try:
            zk = ZK(host, port=4370, timeout=3, password=0)
            conn = zk.connect()
            result['comm_key_default'] = True  # default = 0 worked
            result['fw_version'] = conn.get_firmware_version()
            result['serial'] = conn.get_serialnumber()
            result['platform'] = conn.get_platform()

            # Get all users
            users = conn.get_users()
            result['total_users'] = len(users)
            result['users_with_pwd'] = sum(1 for u in users if u.password and u.password != '')

            # Get verify_types from ATT_LOG
            try:
                logs = conn.get_attendance()
                verify_count = {}
                for log in logs:
                    verify_count[log.status] = verify_count.get(log.status, 0) + 1
                result['verify_types'] = verify_count
                # Status 0=check-in, 1=check-out
            except Exception as e:
                result['verify_types'] = {}

            # Determine if can PIN+password verify
            # = at least 1 user with password + verify_type = 1 (FP) or -1 (any)
            result['can_pin_pwd'] = result['users_with_pwd'] > 0

            conn.disconnect()
        except Exception as e:
            result['error'] = f"pyzk: {e}"

    # Try download ZKDB.db (alternative)
    if result['port_80_http']:
        try:
            zkdb = download_zkdb(host)
            if zkdb and len(zkdb) > 1000:
                result['can_download_zkdb'] = True
                analysis = analyze_zkdb(zkdb)
                if analysis:
                    result['total_users'] = analysis['total_users']
                    result['users_with_pwd'] = analysis['users_with_pwd']
                    result['verify_types'] = analysis['verify_types']
                    result['has_pwd_verify'] = analysis['has_pwd_verify']
                    result['can_pin_pwd'] = result['users_with_pwd'] > 0
        except Exception as e:
            pass

    return result


def main():
    print(f"=== ZK Security Scan - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    devices = read_devices()
    print(f"Devices to scan: {len(devices)}")
    print()

    results = []
    for i, (host, note, selected) in enumerate(devices, 1):
        print(f"[{i}/{len(devices)}] Scanning {host} ({note}) ...", end=' ', flush=True)
        try:
            r = scan_device(host, note)
            results.append(r)
            status = "OK" if r['port_4370'] else "DOWN"
            if r.get('fw_version'):
                status += f" FW={r['fw_version'][:20]}"
            if r.get('comm_key_default'):
                status += " [Comm Key=0 RISK]"
            if r.get('port_23_telnet'):
                status += " [Telnet OPEN]"
            if r.get('users_with_pwd'):
                status += f" [{r['users_with_pwd']} NV có password]"
            print(status)
        except Exception as e:
            print(f"ERR: {e}")
            results.append({'host': host, 'note': note, 'error': str(e)})

    # Print summary
    print()
    print("=" * 100)
    print(f"{'#':<3} {'Host':<16} {'Note':<25} {'FW':<12} {'Users':<6} {'w/PWD':<7} {'PIN+PWD?':<10} {'CommKey':<8} {'Telnet':<7} {'HTTP':<5}")
    print("=" * 100)

    for i, r in enumerate(results, 1):
        fw = (r.get('fw_version') or '')[:11]
        users = str(r.get('total_users') or '?')
        pwd_users = str(r.get('users_with_pwd') or 0)
        pin_pwd = "✅ CÓ" if r.get('can_pin_pwd') else "❌"
        commkey = "❌=0" if r.get('comm_key_default') else "✅"
        telnet = "❌ OPEN" if r.get('port_23_telnet') else "✅ OFF"
        http = "✅" if r.get('port_80_http') else "❌"
        note = r.get('note', '')[:24]
        print(f"{i:<3} {r['host']:<16} {note:<25} {fw:<12} {users:<6} {pwd_users:<7} {pin_pwd:<10} {commkey:<8} {telnet:<7} {http:<5}")

    print()
    print("=" * 100)
    print("RỦI RO TỔNG:")
    risky = [r for r in results if r.get('comm_key_default') or r.get('port_23_telnet')]
    print(f"  - Comm Key default (0): {sum(1 for r in results if r.get('comm_key_default'))} máy")
    print(f"  - Telnet OPEN: {sum(1 for r in results if r.get('port_23_telnet'))} máy")
    print(f"  - PIN+Password users: {sum(1 for r in results if r.get('can_pin_pwd'))} máy CÓ THỂ dùng PIN+password")
    print(f"  - Có ATTLOG Password verify: {sum(1 for r in results if r.get('has_pwd_verify'))} máy")


if __name__ == "__main__":
    main()
