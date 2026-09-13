# -*- coding: utf-8 -*-
"""
Attendance Log Viewer - Web-based
Phan biet may cham cong van tay (attendance) va may ky van tay (signing)

Version: 1.2.0 (build 3)
- Daily report with shift detection (pair In/Out, calc hours)
- Today view (who is in/out, working count)
- Excel export (.xls format)
- All v1.1.0 features (Virtual Device, sort, etc.)
"""
import sys
import os
import re
import json
import csv
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime, timedelta
from struct import unpack

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

# Shift (ca) detection by time of day
SHIFTS = {
    'morning':  {'name': 'Ca sang',  'start': '06:00', 'end': '12:00', 'color': '#ffd166'},
    'afternoon':{'name': 'Ca chieu', 'start': '12:00', 'end': '18:00', 'color': '#06d6a0'},
    'evening':  {'name': 'Ca toi',   'start': '18:00', 'end': '22:00', 'color': '#118ab2'},
    'night':    {'name': 'Ca dem',   'start': '22:00', 'end': '06:00', 'color': '#073b4c'},
}


def _detect_ca(time_str):
    """Detect ca (shift) from time HH:MM:SS. Returns 'morning'/'afternoon'/'evening'/'night'."""
    if not time_str or ':' not in time_str:
        return None
    try:
        h = int(time_str.split(':')[0])
        if 6 <= h < 12:
            return 'morning'
        elif 12 <= h < 18:
            return 'afternoon'
        elif 18 <= h < 22:
            return 'evening'
        else:  # 22-23, 0-5
            return 'night'
    except:
        return None


def _khoa_from_device(device_ip):
    """Map device_ip -> khoa (department) using devices.csv notes.
    'May 1' -> 'Khoa 1', 'May 16 + Web' -> 'Khoa 16', etc.
    Falls back to Note from devices.csv, then IP.
    """
    if not device_ip:
        return 'N/A'
    # Cache lookup in devices_state
    for d in devices_state:
        if d.get('ip') == device_ip:
            note = d.get('note', '').strip()
            if note:
                # Heuristics: "May 1" / "May 16 + Web" -> "Khoa 1" / "Khoa 16"
                if note.lower().startswith('may'):
                    parts = note.split()
                    if len(parts) >= 2:
                        num = parts[1].replace('+', '').strip()
                        if num.isdigit():
                            return f'Khoa {num}'
                return note
            return device_ip
    return device_ip


def _list_khoa():
    """Return sorted list of unique khoa from devices_state."""
    khoas = set()
    for d in devices_state:
        k = _khoa_from_device(d.get('ip', ''))
        if k:
            khoas.add(k)
    return sorted(khoas)

devices_state = []
all_records = []
fetch_status = {'running': False, 'progress': 0, 'total': 0, 'message': 'San sang', 'cancel_requested': False}


def load_devices():
    devices_state.clear()
    if not os.path.exists(DEVICES_FILE):
        return
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


def ping_device(ip, timeout=1.2):
    """
    Quick TCP connect probe to ZK port 4370.
    Returns (ok:bool, latency_ms:int, err:str).
    Used by /api/live to show real-time device status grid.
    """
    import socket
    import time
    if not ip:
        return False, 0, 'empty ip'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t0 = time.time()
        s.connect((ip, 4370))
        s.close()
        ms = int((time.time() - t0) * 1000)
        return True, ms, ''
    except Exception as e:
        return False, 0, str(e)[:60]


def live_status_worker(devices_snapshot):
    """
    Probe every device in parallel; update devices_state['ping_*'] fields.
    Runs in a background thread so the HTTP request returns immediately.
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {d['ip']: pool.submit(ping_device, d['ip'], 1.5) for d in devices_snapshot}
        for d in devices_snapshot:
            ip = d['ip']
            try:
                ok, ms, err = futures[ip].result(timeout=2.5)
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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🏥 AttendanceSuite - BVĐK Ninh Thuận</title>
<style>
:root {
  --primary: #1976d2;
  --primary-hover: #1565c0;
  --primary-light: #e3f2fd;
  --success: #2e7d32;
  --success-light: #e8f5e9;
  --warning: #f57c00;
  --warning-light: #fff3e0;
  --danger: #d32f2f;
  --danger-light: #ffebee;
  --bg: #f5f7fa;
  --card: #ffffff;
  --border: #e0e4e8;
  --border-light: #f0f2f5;
  --text: #2c3e50;
  --text-muted: #6b7c93;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
  --shadow: 0 2px 8px rgba(0,0,0,0.08);
  --radius: 8px;
  --radius-sm: 6px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.topbar {
  background: var(--card);
  border-bottom: 1px solid var(--border);
  padding: 12px 24px;
  display: flex; align-items: center; gap: 16px;
  box-shadow: var(--shadow-sm);
  position: sticky; top: 0; z-index: 100;
}
.topbar h1 { font-size: 18px; font-weight: 600; color: var(--primary); display: flex; align-items: center; gap: 8px; }
.topbar .subtitle { font-size: 12px; color: var(--text-muted); }
.conn-badge {
  margin-left: auto;
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px;
  background: var(--success-light); color: var(--success);
  border-radius: 20px; font-size: 12px; font-weight: 500;
}
.conn-badge.offline { background: var(--danger-light); color: var(--danger); }
.conn-badge .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: currentColor;
  animation: pulse 2s infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

.container { display: flex; height: calc(100vh - 64px); }
.sidebar {
  width: 380px;
  background: var(--card);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  flex-shrink: 0;
}
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  margin-bottom: 10px;
  box-shadow: var(--shadow-sm);
}
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px;
}
.card-title { font-size: 13px; font-weight: 600; color: var(--text); text-transform: uppercase; letter-spacing: 0.5px; }
.card-subtitle { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

button {
  padding: 8px 14px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
  background: transparent;
  color: var(--text);
  display: inline-flex; align-items: center; gap: 4px;
}
button:hover { transform: translateY(-1px); box-shadow: var(--shadow-sm); }
button:active { transform: translateY(0); }
.btn-primary { background: var(--primary); color: white; }
.btn-primary:hover { background: var(--primary-hover); }
.btn-success { background: var(--success); color: white; }
.btn-danger { background: var(--danger); color: white; }
.btn-warning { background: var(--warning); color: white; }
.btn-outline { background: white; border-color: var(--border); }
.btn-outline:hover { background: #f0f4f8; border-color: var(--text-muted); }
.btn-ghost { background: transparent; color: var(--text-muted); }
.btn-ghost:hover { background: #f0f4f8; color: var(--text); }
button:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; box-shadow: none !important; }

.toolbar {
  padding: 12px 24px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
  flex-wrap: wrap;
}
.toolbar label { font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 4px; }
.toolbar input, .toolbar select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  background: white;
  color: var(--text);
}
.toolbar input:focus, .toolbar select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(25,118,210,0.12);
}

.device-list { flex: 1; overflow-y: auto; padding: 8px 0; }
.device-item {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
  transition: all 0.1s;
  font-size: 13px;
  border-left: 3px solid transparent;
}
.device-item:hover { background: #f8f9fa; }
.device-item.selected { background: var(--primary-light); border-left-color: var(--primary); }
.device-item .row1 { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.device-item .ip { font-weight: 600; font-family: 'SF Mono', Consolas, monospace; font-size: 13px; }
.device-item .type-badge {
  font-size: 10px; padding: 2px 6px; border-radius: 4px;
  color: white; font-weight: 600; text-transform: uppercase;
}
.device-item .row2 { font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.type-badge.cc { background: var(--success); }
.type-badge.ky { background: #9c27b0; }
.type-badge.sv { background: #607d8b; }
.type-badge.gw { background: #795548; }
.type-badge.virt { background: var(--warning); }
.type-badge.unknown { background: #9e9e9e; }

.status-pill {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
}
.pill-online { background: var(--success-light); color: var(--success); }
.pill-offline { background: var(--danger-light); color: var(--danger); }
.pill-pending { background: var(--warning-light); color: var(--warning); }
.pill-processing { background: var(--primary-light); color: var(--primary); }
.pill-empty { background: #eceff1; color: var(--text-muted); }

.log-table { flex: 1; overflow: auto; background: var(--card); }
table { width: 100%; border-collapse: collapse; }
thead th {
  position: sticky; top: 0;
  background: #f8f9fa;
  padding: 12px 16px;
  text-align: left;
  font-size: 11px; font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.5px;
  border-bottom: 2px solid var(--border);
  z-index: 1;
  white-space: nowrap;
}
tbody td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-light);
  font-size: 13px;
  font-family: 'SF Mono', Consolas, monospace;
  color: var(--text);
}
tbody tr:hover { background: #f8f9fa; }
tbody tr:nth-child(even) { background: #fafbfc; }
tbody tr:nth-child(even):hover { background: #f0f4f8; }
.status-checkin { color: var(--success); font-weight: 600; }
.status-checkout { color: var(--danger); font-weight: 600; }
.status-break { color: var(--warning); font-weight: 600; }
.status-ot { color: #7b1fa2; font-weight: 600; }
.uid-cell { color: var(--primary); font-weight: 600; }

.status-bar {
  background: var(--card);
  border-top: 1px solid var(--border);
  padding: 10px 24px;
  display: flex; align-items: center; gap: 16px;
  font-size: 12px;
  color: var(--text-muted);
}
.status-bar .progress { flex: 1; max-width: 300px; height: 6px; background: var(--border-light); border-radius: 3px; overflow: hidden; }
.progress-bar { background: var(--primary); height: 100%; width: 0; transition: width 0.3s; }
.status-bar.error { color: var(--danger); }
.status-bar.error .progress-bar { background: var(--danger); }

.empty {
  padding: 80px 20px;
  text-align: center;
  color: var(--text-muted);
}
.empty h3 { font-size: 18px; margin-bottom: 8px; color: var(--text); }
.empty p { font-size: 14px; }

/* ===== Backward compat aliases (de HTML cu van render dung) ===== */
.header { background: var(--card); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
.header h1 { font-size: 18px; font-weight: 600; color: var(--primary); }
.header p { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.toolbar { background: var(--card); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.toolbar input, .toolbar select { padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 13px; background: white; color: var(--text); }
.toolbar input:focus, .toolbar select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(25,118,210,0.12); }
.toolbar label { color: var(--text-muted); font-size: 12px; display: flex; align-items: center; gap: 4px; }
.container { display: flex; height: calc(100vh - 140px); }
.left-panel { width: 380px; background: var(--card); border-right: 1px solid var(--border); overflow-y: auto; flex-shrink: 0; }
.left-header { padding: 14px 16px; border-bottom: 1px solid var(--border); }
.left-header h2 { font-size: 13px; font-weight: 600; color: var(--text); text-transform: uppercase; letter-spacing: 0.5px; }
.left-header p { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.left-header .btn-row { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
.filter-row { padding: 10px 16px; border-bottom: 1px solid var(--border); display: flex; gap: 8px; font-size: 12px; }
.filter-row label { color: var(--text-muted); }
.log-filter-row { padding: 10px 16px; background: #f8f9fa; border-bottom: 1px solid var(--border); display: flex; gap: 12px; align-items: center; flex-wrap: wrap; font-size: 12px; }
.log-filter-row label { color: var(--text-muted); display: flex; align-items: center; gap: 4px; }
.log-filter-row select, .log-filter-row input { font-size: 12px; padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px; background: white; }
.right-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.right-header { padding: 12px 16px; background: #f8f9fa; border-bottom: 1px solid var(--border); display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.right-header h2 { font-size: 13px; font-weight: 600; color: var(--text); }
.right-header input { padding: 6px 10px; border: 1px solid var(--border); border-radius: 4px; font-size: 13px; }
.device-list { flex: 1; overflow-y: auto; }
.device-item { padding: 10px 16px; border-bottom: 1px solid var(--border-light); cursor: pointer; transition: all 0.1s; font-size: 13px; border-left: 3px solid transparent; }
.device-item:hover { background: #f8f9fa; }
.device-item.selected { background: var(--primary-light); border-left-color: var(--primary); }
.device-item.signing { background: #f3e8ff; }
.device-item .row1 { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.device-item .ip { font-weight: 600; font-family: 'SF Mono', Consolas, monospace; }
.device-item .type-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; color: white; font-weight: 600; }
.device-item .status { font-size: 11px; color: var(--text-muted); }
.device-item .status.ok { color: var(--success); }
.device-item .status.fail { color: var(--danger); }
.device-item .row2 { display: flex; gap: 4px; margin-top: 4px; align-items: center; }
.type-select { font-size: 11px; padding: 4px 6px; border-radius: 4px; border: 1px solid var(--border); background: white; }
.log-table { flex: 1; overflow: auto; background: var(--card); }
.status-bar { background: var(--card); border-top: 1px solid var(--border); padding: 10px 24px; display: flex; align-items: center; gap: 16px; font-size: 12px; color: var(--text-muted); }
.status-bar .progress { flex: 1; max-width: 300px; height: 6px; background: var(--border-light); border-radius: 3px; overflow: hidden; }
.status-bar.error { color: var(--danger); }
.status-bar.error .progress-bar { background: var(--danger); }

/* Old button classes - map to new */
.btn-secondary { background: var(--primary); color: white; border: none; }
.btn-secondary:hover { background: var(--primary-hover); }
.btn-stop { background: var(--danger); color: white; border: none; }
.btn-stop:hover { background: #b71c1c; }
.btn-stop:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-small { padding: 5px 10px; font-size: 12px; background: var(--primary); color: white; border: none; border-radius: 4px; }
.btn-small:hover { background: var(--primary-hover); }

.empty { padding: 80px 20px; text-align: center; color: var(--text-muted); }
.checkbox { width: 16px; height: 16px; cursor: pointer; accent-color: var(--primary); }
.legend { font-size: 11px; color: var(--text-muted); padding: 4px 0; display: flex; gap: 12px; flex-wrap: wrap; }
.legend span { display: inline-flex; align-items: center; gap: 4px; }
.legend .badge { font-size: 10px; padding: 1px 5px; border-radius: 3px; color: white; font-weight: 600; }

.checkbox { width: 16px; height: 16px; cursor: pointer; accent-color: var(--primary); }

.modal {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.4);
  z-index: 1000; overflow-y: auto;
  animation: fadeIn 0.2s;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal-content {
  background: var(--card);
  max-width: 1100px;
  margin: 40px auto;
  border-radius: var(--radius);
  padding: 0;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
  overflow: hidden;
}
.modal-header {
  padding: 16px 24px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.modal-header h2 { font-size: 16px; font-weight: 600; }
.modal-body { padding: 24px; }
.modal-close {
  background: transparent; border: none; cursor: pointer;
  font-size: 18px; color: var(--text-muted);
  padding: 4px 10px; border-radius: 4px;
}
.modal-close:hover { background: #f0f4f8; color: var(--text); }

.kpi-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px; margin-bottom: 16px;
}
.kpi {
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
}
.kpi .v { font-size: 22px; font-weight: 700; line-height: 1.1; }
.kpi .l { font-size: 11px; color: var(--text-muted); margin-top: 2px; text-transform: uppercase; letter-spacing: 0.3px; }
.kpi.warn .v { color: var(--warning); }
.kpi.danger .v { color: var(--danger); }
.kpi.success .v { color: var(--success); }
.kpi.info .v { color: var(--primary); }

.legend { font-size: 11px; color: var(--text-muted); padding: 4px 0; display: flex; gap: 12px; flex-wrap: wrap; }
.legend span { display: inline-flex; align-items: center; gap: 4px; }
.legend .badge { font-size: 10px; padding: 1px 5px; border-radius: 3px; color: white; font-weight: 600; }

.banner {
  background: #fff8e1; border-left: 4px solid var(--warning);
  padding: 12px 16px; border-radius: var(--radius-sm); margin-bottom: 12px;
  color: #5d4037; font-size: 13px;
}
.banner.danger { background: var(--danger-light); border-color: var(--danger); color: #b71c1c; }
.banner.success { background: var(--success-light); border-color: var(--success); color: #1b5e20; }
.banner.info { background: var(--primary-light); border-color: var(--primary); color: #0d47a1; }

@media (max-width: 900px) {
  .sidebar { width: 320px; }
  .toolbar { padding: 8px 12px; }
}
</style>
</head>
<body>
<div class="topbar">
  <h1>🏥 AttendanceSuite</h1>
  <span class="subtitle">BVĐK Ninh Thuận · Quản lý chấm công</span>
  <span class="conn-badge" id="connStatus"><span class="dot"></span>Đang kết nối...</span>
</div>
<div class="toolbar">
  <label>Từ:</label>
  <input type="date" id="dateFrom" value="">
  <label>Đến:</label>
  <input type="date" id="dateTo" value="">
  <label><input type="checkbox" id="chkDate" checked> Lọc theo ngày</label>
  <button class="btn-primary" id="btnFetch" onclick="fetchLogs()">⬇ Lấy log (4 song song)</button>
  <button class="btn-danger" id="btnStop" onclick="stopFetch()" disabled>⏹ Dừng</button>
  <button class="btn-outline" id="btnExport" onclick="exportCsv()">📄 Export CSV</button>
  <button class="btn-outline" id="btnReport" onclick="openReport()">📊 Báo cáo</button>
  <button class="btn-outline" id="btnToday" onclick="openToday()">📅 Hôm nay</button>
  <button class="btn-outline" id="btnExcel" onclick="exportExcel()">📑 Excel</button>
  <button class="btn-warning" id="btnMerge" onclick="openMerge()">⚠ So sánh Shadow Log</button>
  <button class="btn-danger" id="btnAlerts" onclick="window.open('/alerts', '_blank')">🚨 NV quên chấm</button>
  <button class="btn-success" id="btnBackup" onclick="triggerBackup()">💾 Backup ngay</button>
  <a href="/merge" class="btn-outline" style="text-decoration:none;display:inline-flex;align-items:center">🔀 MERGE Workflow →</a>
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
        <button class="btn-small" onclick="setAll(true)">✓ Chon tat ca (CC)</button>
        <button class="btn-small" onclick="setAll(false)">✗ Bo chon</button>
        <button class="btn-small" onclick="setInvert()" title="Dao nguoc chon">⇅ Chon nguoc</button>
        <button class="btn-small" onclick="setOnlineOnly()" title="Chi chon may dang online (ping OK)">📡 Chi may online</button>
      </div>
      <div class="btn-row" style="margin-top:4px">
        <label style="font-size:11px;color:#666;margin-right:4px">Subnet:</label>
        <input type="text" id="subnetFilter" placeholder="vd: 172.16.0 hoac .212" 
               style="width:130px;padding:2px 6px;border:1px solid #ccc;border-radius:3px;font-size:11px"
               oninput="applySubnetFilter()">
        <button class="btn-small" onclick="clearSubnetFilter()">Clear</button>
        <span id="selCounter" style="margin-left:auto;font-size:11px;color:#107c10;font-weight:600"></span>
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
  const subnetEl = document.getElementById('subnetFilter');
  const subnet = (subnetEl ? subnetEl.value : '').trim();
  let count = {total: 0, att: 0, sel: 0, visible: 0};
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
    // Subnet filter (substring match trong IP)
    if (subnet && d.ip.indexOf(subnet) < 0) return;
    count.visible++;
    const item = document.createElement('div');
    item.className = 'device-item ' + d.type + (d.selected ? ' selected' : '');
    const canSelect = (d.type === 'attendance');
    const statusClass = d.status === 'OK' ? 'ok' : (d.status === 'FAIL' ? 'fail' : '');
    const typeName = TYPE_NAMES[d.type] || '?';
    const typeColor = TYPE_COLORS[d.type] || '#888';
    const isProcessing = d.status === 'Processing...' || d.status === 'Connecting...';
    const statusText = isProcessing ? '<span style="color:#007acc">⏳ ' + d.status + '</span>' : d.status;
    // v1.4.0: live status pill (online/offline/chua probe)
    let livePill = '';
    if (d.ping_ok === true) {
      livePill = '<span style="background:#107c10;color:white;padding:1px 5px;border-radius:3px;font-size:10px;margin-left:4px">● ' + (d.ping_ms || 0) + 'ms</span>';
    } else if (d.ping_ok === false) {
      livePill = '<span style="background:#c50f1f;color:white;padding:1px 5px;border-radius:3px;font-size:10px;margin-left:4px">○ offline</span>';
    }
    item.innerHTML =
      '<div class="row1">' +
        '<input type="checkbox" class="checkbox" ' + (d.selected ? 'checked' : '') +
        (canSelect ? '' : ' disabled') +
        ' onclick="event.stopPropagation(); toggleSelect(\'' + d.ip + '\', this.checked);">' +
        '<span class="type-badge" style="background:' + typeColor + '">' + typeName + '</span>' +
        '<span class="ip">' + d.ip + '</span>' + livePill +
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
  const filterTxt = (search || subnet) ? ' (loc: ' + count.visible + ' visible)' : '';
  document.getElementById('devCount').textContent = count.total + ' thiet bi (' + count.att + ' cham cong, ' + count.sel + ' dang chon)' + filterTxt;
  document.getElementById('summary').textContent = ' | ' + allRecords.length.toLocaleString() + ' logs';
  updateSelCounter();
}

function updateSelCounter() {
  const el = document.getElementById('selCounter');
  if (!el) return;
  const cc = allDevices.filter(function(d) { return d.type === 'attendance'; });
  const sel = cc.filter(function(d) { return d.selected; });
  if (cc.length === 0) { el.textContent = ''; return; }
  const onlineSel = sel.filter(function(d) { return d.ping_ok === true; });
  const offlineSel = sel.filter(function(d) { return d.ping_ok === false; });
  const unknownSel = sel.filter(function(d) { return d.ping_ok === null || d.ping_ok === undefined; });
  let txt = 'Chon: ' + sel.length + '/' + cc.length;
  if (onlineSel.length > 0) txt += ' | ' + onlineSel.length + ' online';
  if (offlineSel.length > 0) txt += ' | ' + offlineSel.length + ' offline';
  if (unknownSel.length > 0) txt += ' | ' + unknownSel.length + ' chua probe';
  el.textContent = txt;
  el.style.color = offlineSel.length > 0 ? '#c50f1f' : '#107c10';
}

function applyFilter() { renderDevices(); }

function setAll(sel) {
  allDevices.forEach(function(d) { if (d.type === 'attendance') d.selected = sel; });
  saveAndReload();
}
function setAllAttendance(sel) {
  allDevices.forEach(function(d) { if (d.type === 'attendance') d.selected = sel; });
  saveAndReload();
}

// === NEW v1.4.0: selection helpers ===
function setInvert() {
  // Dao nguoc: may dang chon thanh khong chon va nguoc lai (chi tren may CC)
  allDevices.forEach(function(d) {
    if (d.type === 'attendance') d.selected = !d.selected;
  });
  saveAndReload();
}
function setOnlineOnly() {
  // Chi chon may co ping_ok === true (can probe truoc qua /api/live)
  let probeFirst = allDevices.some(function(d) { return d.type === 'attendance' && d.ping_ok === null; });
  if (probeFirst) {
    if (!confirm('Chua probe live status. Bam OK de probe ngay roi chon may online.')) return;
    // Trigger probe via fetch /api/live, sau do re-select
    fetch('/api/live').then(function(r){ return r.json(); }).then(function(data){
      allDevices.forEach(function(d) {
        if (d.type !== 'attendance') return;
        const live = (data.devices || []).find(function(x){ return x.ip === d.ip; });
        d.ping_ok = live ? live.ping_ok : null;
        d.selected = (d.ping_ok === true);
      });
      saveAndReload();
    }).catch(function(e){
      alert('Probe loi: ' + e.message);
    });
    return;
  }
  allDevices.forEach(function(d) {
    if (d.type === 'attendance') d.selected = (d.ping_ok === true);
  });
  saveAndReload();
}
function applySubnetFilter() {
  // Loc device list theo subnet pattern (khong phai select, chi loc hien thi)
  renderDeviceList();
}
function clearSubnetFilter() {
  document.getElementById('subnetFilter').value = '';
  renderDeviceList();
}

async function toggleSelect(ip, sel) {
  const dev = allDevices.find(function(d) { return d.ip === ip; });
  if (dev) { dev.selected = sel; }
  await saveAndReload();
}

async function changeType(ip, newType) {
  const dev = allDevices.find(function(d) { return d.ip === ip; });
  if (dev) { dev.type = newType; dev.selected = (newType === 'attendance'); }
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
    // Update topbar conn badge
    const cs = document.getElementById('connStatus');
    if (cs) {
      cs.classList.remove('offline');
      if (s.running) {
        cs.innerHTML = '<span class="dot"></span>Đang lấy log: ' + s.progress + '/' + s.total;
      } else {
        cs.innerHTML = '<span class="dot"></span>Sẵn sàng';
      }
    }
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

// === REPORT FILTERS ===
function applyReportFilter() {
  const fca = document.getElementById('f-ca');
  const fkhoa = document.getElementById('f-khoa');
  if (fca) reportState.ca = fca.value;
  if (fkhoa) reportState.khoa = fkhoa.value;
  openReport();
}
function resetReportFilter() {
  reportState.ca = '';
  reportState.khoa = '';
  openReport();
}

// === BACKUP TRIGGER ===
async function triggerBackup() {
  if (!confirm('Backup ngay D:\\\\chamcong\\\\backups\\\\?')) return;
  try {
    const r = await fetch('/api/backup/now', {method: 'POST'});
    const d = await r.json();
    if (d.ok) {
      alert('Backup OK: ' + d.message + '\\n' + d.files.join('\\n'));
    } else {
      alert('Backup loi: ' + d.message);
    }
  } catch (e) {
    alert('Backup failed: ' + e);
  }
}

// === REPORTS ===
let reportState = {ca: '', khoa: '', shifts: [], khoas: []};
async function openReport() {
  document.getElementById('reportModal').style.display = 'block';
  document.getElementById('reportContent').innerHTML = '<p style="color:#888">Dang tai bao cao...</p>';
  try {
    // Initial fetch to get shifts/khoas
    if (reportState.shifts.length === 0) {
      const r0 = await fetch('/api/report/daily');
      const d0 = await r0.json();
      reportState.shifts = d0.shifts || [];
      reportState.khoas = d0.khoas || [];
    }
    const qs = new URLSearchParams();
    if (reportState.ca) qs.set('ca', reportState.ca);
    if (reportState.khoa) qs.set('khoa', reportState.khoa);
    const url = '/api/report/daily' + (qs.toString() ? '?' + qs : '');
    const r = await fetch(url);
    const data = await r.json();
    // Filter UI
    let html = '<h3 style="color:#00d4ff;margin-top:0">Bao cao theo ngay</h3>';
    html += '<div style="display:flex;gap:8px;margin:10px 0;align-items:center">';
    html += '<label>Ca: <select id="f-ca" style="padding:4px;background:#0a1220;color:#e0e0e0;border:1px solid #2a3a5a;border-radius:4px">';
    html += '<option value="">-- Tat ca --</option>';
    for (const s of reportState.shifts) {
      const sel = s.id === reportState.ca ? ' selected' : '';
      html += '<option value="' + s.id + '"' + sel + '>' + s.name + '</option>';
    }
    html += '</select></label>';
    html += '<label>Khoa: <select id="f-khoa" style="padding:4px;background:#0a1220;color:#e0e0e0;border:1px solid #2a3a5a;border-radius:4px">';
    html += '<option value="">-- Tat ca --</option>';
    for (const k of reportState.khoas) {
      const sel = k === reportState.khoa ? ' selected' : '';
      html += '<option value="' + k + '"' + sel + '>' + k + '</option>';
    }
    html += '</select></label>';
    html += '<button onclick="applyReportFilter()" style="padding:4px 12px;background:#1976d2;color:#fff;border:none;border-radius:4px;cursor:pointer">Ap dung</button>';
    if (reportState.ca || reportState.khoa) {
      html += '<button onclick="resetReportFilter()" style="padding:4px 12px;background:#666;color:#fff;border:none;border-radius:4px;cursor:pointer">Xoa loc</button>';
    }
    html += '</div>';
    html += '<p style="color:#888">Tong: ' + data.total_nvs + ' luot NV x ' + data.days.length + ' ngay';
    if (data.filters && (data.filters.ca || data.filters.khoa)) {
      html += ' (loc: ' + (data.filters.ca || '*') + ' / ' + (data.filters.khoa || '*') + ')';
    }
    html += '</p>';
    for (const day of data.days.slice(0, 30)) {
      html += '<h4 style="color:#5fff7f;margin:10px 0 5px">' + day.date + ' (' + day.nvs.length + ' NV)</h4>';
      html += '<table style="width:100%;font-size:12px;border-collapse:collapse">';
      html += '<tr style="background:#1a2a3a"><th style="padding:4px;text-align:left">Ma NV</th><th>Khoa</th><th>Ca</th><th>Check-In</th><th>Check-Out</th><th>Gio</th><th>TT</th><th>Thiet bi</th></tr>';
      for (const nv of day.nvs) {
        const statusColor = nv.status === 'Complete' ? '#5fff7f' : '#ffd700';
        const caColor = ({'morning':'#ffd166','afternoon':'#06d6a0','evening':'#118ab2','night':'#073b4c'})[nv.ca] || '#888';
        html += '<tr style="border-top:1px solid #2a3a5a"><td style="padding:4px">' + nv.user_id + '</td>';
        html += '<td style="font-size:11px;color:#aaa">' + (nv.khoa||'') + '</td>';
        html += '<td style="color:' + caColor + ';font-size:11px">' + (nv.ca_name||'') + '</td>';
        html += '<td>' + nv.first_in + '</td><td>' + nv.last_out + '</td>';
        html += '<td>' + nv.hours_worked + 'h</td>';
        html += '<td style="color:' + statusColor + '">' + nv.status + '</td>';
        html += '<td style="font-size:10px;color:#888">' + nv.devices.join(',') + '</td></tr>';
      }
      html += '</table>';
    }
    if (data.days.length > 30) html += '<p style="color:#888">... va ' + (data.days.length - 30) + ' ngay khac</p>';
    document.getElementById('reportContent').innerHTML = html;
    // Re-attach event handlers for filters
    const fca = document.getElementById('f-ca');
    const fkhoa = document.getElementById('f-khoa');
    if (fca) fca.onchange = () => { reportState.ca = fca.value; };
    if (fkhoa) fkhoa.onchange = () => { reportState.khoa = fkhoa.value; };
  } catch (e) {
    document.getElementById('reportContent').innerHTML = '<p style="color:#f88">Loi: ' + e.message + '</p>';
  }
}

function closeReport() {
  document.getElementById('reportModal').style.display = 'none';
}

// === MERGE: shadow log vs real device log ===
async function openMerge() {
  document.getElementById('mergeModal').style.display = 'block';
  const c = document.getElementById('mergeContent');
  c.innerHTML = '<p style="color:#888">Dang so sanh...</p>';
  try {
    const r = await fetch('/api/merge');
    const data = await r.json();
    renderMerge(data);
  } catch (e) {
    c.innerHTML = '<p style="color:#c50f1f">Loi: ' + e.message + '</p>';
  }
}
function closeMerge() {
  document.getElementById('mergeModal').style.display = 'none';
}
function renderMerge(d) {
  const c = document.getElementById('mergeContent');
  const s = d.summary || {};
  let html = '';
  // Warning banner
  html += '<div style="background:#4a1a1a;border:1px solid #6a2a2a;padding:12px;border-radius:6px;margin-bottom:16px">';
  html += '<div style="color:#ff8888;font-weight:bold;margin-bottom:6px">⚠ GIỚI HẠN FIRMWARE X628 PRO 6.60</div>';
  html += '<div style="font-size:12px;color:#fff">' + (s.note || '') + '</div>';
  html += '</div>';
  // Summary cards
  html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px">';
  const cards = [
    {label: 'Shadow Pending', val: s.shadow_pending_count, color: '#ffd700'},
    {label: 'Synced', val: s.shadow_synced_count, color: '#10b981'},
    {label: 'Failed', val: s.shadow_failed_count, color: '#ef4444'},
    {label: 'Real device records', val: s.real_device_records_count, color: '#00d4ff'},
  ];
  for (const card of cards) {
    html += '<div style="background:#1e293b;padding:10px;border-radius:6px;text-align:center">';
    html += '<div style="font-size:24px;font-weight:700;color:' + card.color + '">' + (card.val || 0) + '</div>';
    html += '<div style="font-size:11px;color:#94a3b8;margin-top:2px">' + card.label + '</div>';
    html += '</div>';
  }
  html += '</div>';
  // Delta: missing on device
  const missing = d.missing_on_device || [];
  html += '<h3 style="color:#ff8888;margin:16px 0 8px">🔴 MISSING TRÊN MÁY (cần merge tay): ' + missing.length + '</h3>';
  if (missing.length === 0) {
    html += '<p style="color:#10b981">Không có punch nào pending thiếu trên máy.</p>';
  } else {
    html += '<div style="max-height:300px;overflow-y:auto;background:#1e293b;border-radius:6px;padding:8px;margin-bottom:12px">';
    html += '<table style="width:100%;font-size:12px;color:#fff"><thead><tr style="background:#334155">';
    html += '<th style="padding:4px">ID</th><th>NV</th><th>Thời gian</th><th>TT</th><th>Máy</th><th>Note</th>';
    html += '</tr></thead><tbody>';
    for (const p of missing) {
      html += '<tr style="border-bottom:1px solid #334155">';
      html += '<td style="padding:3px 4px">' + (p.punch_id || '').slice(-6) + '</td>';
      html += '<td style="color:#00d4ff;font-weight:bold">' + (p.user_id || '') + '</td>';
      html += '<td>' + (p.timestamp || '') + '</td>';
      html += '<td>' + (p.status_name || '') + '</td>';
      html += '<td style="font-family:monospace;font-size:11px">' + (p.device_ip || '') + '</td>';
      html += '<td style="font-size:11px;color:#94a3b8">' + (p.note || '') + '</td>';
      html += '</tr>';
    }
    html += '</tbody></table></div>';
    html += '<button onclick="exportMissingCSV()" style="background:#107c10;color:#fff;border:0;padding:8px 16px;border-radius:4px;cursor:pointer;margin-right:8px">📥 Xuất CSV (để in tay)</button>';
    html += '<button onclick="copyMissingText()" style="background:#007acc;color:#fff;border:0;padding:8px 16px;border-radius:4px;cursor:pointer">📋 Copy text</button>';
  }
  // Matched on device
  const matched = d.matched_on_device || [];
  if (matched.length > 0) {
    html += '<h3 style="color:#10b981;margin:16px 0 8px">✅ ĐÃ CÓ TRÊN MÁY (không cần làm): ' + matched.length + '</h3>';
    html += '<details><summary style="color:#94a3b8;cursor:pointer">Click xem chi tiết</summary>';
    html += '<div style="max-height:200px;overflow-y:auto;background:#1e293b;border-radius:6px;padding:8px;margin-top:8px">';
    html += '<table style="width:100%;font-size:12px;color:#fff"><thead><tr style="background:#334155">';
    html += '<th style="padding:4px">ID</th><th>NV</th><th>Thời gian</th><th>Máy</th>';
    html += '</tr></thead><tbody>';
    for (const p of matched) {
      html += '<tr style="border-bottom:1px solid #334155">';
      html += '<td style="padding:3px 4px">' + (p.punch_id || '').slice(-6) + '</td>';
      html += '<td style="color:#00d4ff;font-weight:bold">' + (p.user_id || '') + '</td>';
      html += '<td>' + (p.timestamp || '') + '</td>';
      html += '<td style="font-family:monospace;font-size:11px">' + (p.device_ip || '') + '</td>';
      html += '</tr>';
    }
    html += '</tbody></table></div></details>';
  }
  // Shadow log paths info
  html += '<div style="margin-top:16px;padding:10px;background:#0f172a;border-radius:4px;font-size:11px;color:#94a3b8">';
  html += '<div style="color:#00d4ff;font-weight:bold;margin-bottom:4px">📁 Shadow log files:</div>';
  for (const [k, v] of Object.entries(d.shadow_log || {})) {
    html += '<div>• ' + k + ': ' + v + '</div>';
  }
  html += '</div>';
  // Store for export
  window._missingData = missing;
  c.innerHTML = html;
}
function exportMissingCSV() {
  if (!window._missingData || !window._missingData.length) {
    alert('Khong co du lieu');
    return;
  }
  let csv = 'punch_id,user_id,timestamp,status,status_name,device_ip,note\n';
  for (const p of window._missingData) {
    csv += (p.punch_id || '') + ',' + (p.user_id || '') + ',' + (p.timestamp || '') + ',' +
           (p.status || '') + ',' + (p.status_name || '') + ',' + (p.device_ip || '') + ',' +
           (p.note || '') + '\n';
  }
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'merge_missing_' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click();
}
function copyMissingText() {
  if (!window._missingData || !window._missingData.length) {
    alert('Khong co du lieu');
    return;
  }
  let txt = '=== PUNCH CAN MERGE TAY VAO MAY ===\n\n';
  for (const p of window._missingData) {
    txt += p.timestamp + ' | NV ' + p.user_id + ' | ' + p.status_name + ' | May ' + p.device_ip + '\n';
  }
  navigator.clipboard.writeText(txt).then(() => alert('Da copy ' + window._missingData.length + ' dong'));
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

<!-- Merge Modal (shadow log vs real device log) -->
<div id="mergeModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:9999;overflow-y:auto">
  <div style="background:#0f1729;border:1px solid #2a3a5a;max-width:1200px;margin:30px auto;padding:20px;border-radius:6px;color:#fff">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px">
      <h2 style="color:#ff8888;margin:0">⚠ So sánh Shadow Log vs Log máy thật</h2>
      <button onclick="closeMerge()" style="background:#5a1a1a;color:#fff;border:1px solid #6a2a2a;padding:6px 14px;border-radius:4px;cursor:pointer">Dong [X]</button>
    </div>
    <div id="mergeContent"><p style="color:#888">Dang tai...</p></div>
  </div>
</div>
</body>
</html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/merge':
            self._handle_merge_page()
            return
        if path == '/' or path == '/index.html':
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
        elif path == '/security':
            self._handle_security_page()
        elif path == '/punch':
            self._handle_punch_page()
        elif path == '/api/security/scan':
            self._handle_security_scan()
        elif path.startswith('/api/security/device/') and path.endswith('/verify'):
            parts = path.split('/')
            ip = parts[4] if len(parts) > 4 else ''
            qs = self._parse_qs()
            pin = qs.get('pin', [''])[0]
            password = qs.get('password', [''])[0]
            self._handle_security_verify(ip, pin, password)
        elif path.startswith('/api/security/device/') and path.endswith('/attlog-count'):
            parts = path.split('/')
            ip = parts[4] if len(parts) > 4 else ''
            self._handle_attlog_count(ip)
        elif path == '/api/punch/log':
            self._handle_punch_log()
        elif path == '/api/punch/manual':
            data = self._read_json_body()
            self._handle_punch_manual(data)
        elif path == '/api/merge':
            self._handle_merge()
        elif path.startswith('/api/merge/today'):
            self._handle_merge_today()
        elif path == '/api/alerts/missing' or path == '/api/alerts':
            self._handle_alerts_missing()
        elif path == '/alerts' or path == '/alerts.html':
            self._handle_alerts_page()
        elif path == '/api/backup/status':
            # List existing backups
            backup_root = os.path.join(SCRIPT_DIR, 'backups')
            backups = []
            if os.path.exists(backup_root):
                for d in sorted(os.listdir(backup_root), reverse=True):
                    full = os.path.join(backup_root, d)
                    if os.path.isdir(full):
                        files = os.listdir(full)
                        size = sum(os.path.getsize(os.path.join(full, f)) for f in files
                                   if os.path.isfile(os.path.join(full, f)))
                        backups.append({'date': d, 'files': len(files), 'size_mb': round(size/1024/1024, 2),
                                        'file_names': files})
            self.send_json({'backups': backups[:30], 'root': backup_root})
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
                pending_path = os.path.join(SCRIPT_DIR, 'pending_punches.csv')
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
        elif path == '/api/merge/mark-done':
            self._handle_merge_mark_done(data)
        elif path == '/api/merge/clear-old':
            self._handle_merge_clear_old(data)
        elif path == '/api/punch/manual':
            try:
                body = json.loads(raw) if raw else {}
            except:
                body = {}
            self._handle_punch_manual(body)
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
        elif path == '/api/backup/now':
            # Manual backup trigger
            ok, msg, count, files = _do_backup_now()
            self.send_json({'ok': ok, 'message': msg, 'count': count, 'files': files})
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

    def _parse_qs(self):
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(self.path)
        return parse_qs(parsed.query)

    def _read_json_body(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 0:
                body = self.rfile.read(length)
                return json.loads(body.decode('utf-8'))
        except Exception:
            pass
        return {}

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

    def _parse_filters(self):
        """Parse ca/khoa filter from query string."""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        return {
            'ca': (qs.get('ca', [''])[0] or '').lower().strip(),
            'khoa': (qs.get('khoa', [''])[0] or '').strip(),
            'date_from': (qs.get('date_from', [''])[0] or '').strip(),
            'date_to': (qs.get('date_to', [''])[0] or '').strip(),
        }

    def _handle_alerts_missing(self):
        """NV không có check-in trong ngày hôm nay (sau 8h sáng).
        Returns list of missing users based on those who punched yesterday or recent days.
        Also includes 'forgot checkout' alerts (in but no out by 22h).
        """
        from collections import defaultdict
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        now_h = datetime.now().hour
        now_m = datetime.now().minute
        # Active users = who punched in last 7 days
        from datetime import timedelta
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        active_users = set()
        for r in all_records:
            if r.get('date', '') >= cutoff_date:
                active_users.add(str(r.get('user_id', '')))
        # Today's punches
        today_recs = [r for r in all_records if r.get('date') == today]
        today_users_in = set(str(r.get('user_id', '')) for r in today_recs if r.get('status') == 0)
        today_users_out = set(str(r.get('user_id', '')) for r in today_recs if r.get('status') == 1)
        # Alerts
        missing_checkin = sorted(active_users - today_users_in)
        # Forgot checkout: punched in but no out (after 22h)
        forgot_checkout = []
        if now_h >= 22:
            forgot_checkout = sorted(today_users_in - today_users_out)
        # User names from devices.csv notes (best-effort)
        # Note: this app doesn't have user names - they come from ZK directly.
        # For alerts we just return user_id.
        result = {
            'date': today,
            'now': datetime.now().strftime('%H:%M:%S'),
            'active_users': len(active_users),
            'punched_today': len(today_users_in),
            'missing_checkin': missing_checkin,
            'missing_count': len(missing_checkin),
            'forgot_checkout': forgot_checkout,
            'forgot_count': len(forgot_checkout),
            'thresholds': {
                'missing_checkin_alert_after': '08:00',
                'forgot_checkout_alert_after': '22:00',
                'active_window_days': 7,
            }
        }
        # If time before 8h, don't show missing_checkin
        if now_h < 8:
            result['warning'] = 'Truoc 8:00, chua canh bao missing check-in'
        self.send_json(result)

    def _handle_alerts_page(self):
        """Trang alerts rieng - UI cho NV quen cham."""
        page = '''<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"><title>Alerts - NV quên chấm</title>
<style>
body{font-family:Segoe UI,Arial;margin:0;padding:24px;background:#f5f5f5}
h1{color:#d32f2f}.card{background:#fff;padding:20px;border-radius:8px;margin-bottom:16px;box-shadow:0 2px 4px rgba(0,0,0,.1)}
.kpi{display:flex;gap:16px;margin-bottom:16px}.kpi-item{flex:1;padding:16px;background:#fff;border-radius:8px;text-align:center;box-shadow:0 2px 4px rgba(0,0,0,.1)}
.kpi-num{font-size:32px;font-weight:bold;color:#1976d2}.kpi-label{color:#666;margin-top:8px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden}
th,td{padding:10px;text-align:left;border-bottom:1px solid #eee}
th{background:#1976d2;color:#fff;font-weight:500}
tr:hover{background:#f5f5f5}
.red{color:#d32f2f;font-weight:bold}
.btn{padding:8px 16px;background:#1976d2;color:#fff;border:none;border-radius:4px;cursor:pointer;margin-right:8px}
.btn:hover{background:#1565c0}
.warning{background:#fff3cd;padding:12px;border-radius:4px;border-left:4px solid #ffc107}
</style></head><body>
<h1>⚠️ Alerts - NV Quên Chấm Công</h1>
<div id="warning" style="display:none" class="warning"></div>
<div class="kpi">
  <div class="kpi-item"><div class="kpi-num" id="kpi-active">-</div><div class="kpi-label">NV hoạt động (7 ngày)</div></div>
  <div class="kpi-item"><div class="kpi-num" id="kpi-punched">-</div><div class="kpi-label">Đã chấm hôm nay</div></div>
  <div class="kpi-item"><div class="kpi-num red" id="kpi-missing">-</div><div class="kpi-label">Quên check-in</div></div>
  <div class="kpi-item"><div class="kpi-num red" id="kpi-forgot">-</div><div class="kpi-label">Quên check-out</div></div>
</div>
<button class="btn" onclick="loadAlerts()">🔄 Refresh</button>
<button class="btn" onclick="exportCSV()">📥 Xuất CSV</button>
<div class="card">
  <h2>⚠️ NV Quên Check-in</h2>
  <table id="missing-table"><thead><tr><th>PIN</th></tr></thead><tbody></tbody></table>
</div>
<div class="card">
  <h2>⚠️ NV Quên Check-out (sau 22h)</h2>
  <table id="forgot-table"><thead><tr><th>PIN</th></tr></thead><tbody></tbody></table>
</div>
<script>
async function loadAlerts(){
  const r = await fetch('/api/alerts/missing');
  const d = await r.json();
  document.getElementById('kpi-active').textContent = d.active_users;
  document.getElementById('kpi-punched').textContent = d.punched_today;
  document.getElementById('kpi-missing').textContent = d.missing_count;
  document.getElementById('kpi-forgot').textContent = d.forgot_count;
  document.getElementById('now').textContent = d.now;
  const m = document.getElementById('missing-table').querySelector('tbody');
  m.innerHTML = '';
  d.missing_checkin.forEach(pin => {
    const tr = document.createElement('tr'); tr.innerHTML = `<td class="red">${pin}</td>`; m.appendChild(tr);
  });
  const f = document.getElementById('forgot-table').querySelector('tbody');
  f.innerHTML = '';
  d.forgot_checkout.forEach(pin => {
    const tr = document.createElement('tr'); tr.innerHTML = `<td class="red">${pin}</td>`; f.appendChild(tr);
  });
  const w = document.getElementById('warning');
  if(d.warning){w.style.display='block';w.textContent=d.warning;}else{w.style.display='none';}
}
function exportCSV(){
  let csv='PIN\\n';
  document.querySelectorAll('#missing-table tbody tr').forEach(r=>{csv+=r.cells[0].textContent+'\\n';});
  const blob=new Blob([csv],{type:'text/csv'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='missing_checkin_'+new Date().toISOString().slice(0,10)+'.csv';a.click();
}
loadAlerts();
setInterval(loadAlerts, 60000);  // Refresh every 60s
</script></body></html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        body = page.encode('utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_daily_report(self):
        """Build daily report: for each NV on each day, calculate total hours worked.
        Filters: ?ca=morning/afternoon/evening/night, ?khoa=Khoa1
        """
        from collections import defaultdict
        filters = self._parse_filters()
        ca_filter = filters['ca']  # 'morning' / 'afternoon' / 'evening' / 'night' or ''
        khoa_filter = filters['khoa']  # e.g. 'Khoa 1' or ''

        report = defaultdict(lambda: defaultdict(list))  # date -> nv -> [records]
        for r in all_records:
            d = r.get('date', '')
            nv = str(r.get('user_id', ''))
            if not (d and nv):
                continue
            # Filter by ca (based on time)
            if ca_filter:
                rc_ca = _detect_ca(r.get('time', ''))
                if rc_ca != ca_filter:
                    continue
            # Filter by khoa (based on device_ip)
            if khoa_filter:
                rc_khoa = _khoa_from_device(r.get('device_ip', ''))
                if rc_khoa != khoa_filter:
                    continue
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
                devices = list(set(r.get('device_ip', '') for r in recs))
                # Ca inferred from first check-in time
                nv_ca = _detect_ca(first_in) if first_in else None
                khoa = _khoa_from_device(devices[0]) if devices else 'N/A'
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
                    'khoa': khoa,
                    'ca': nv_ca,
                    'ca_name': SHIFTS.get(nv_ca, {}).get('name', '') if nv_ca else '',
                    'status': 'Complete' if not any(p[2] is None for p in pairs) and len(pairs) > 0 else 'Incomplete',
                })
            summary.append(day_data)
        self.send_json({
            'days': summary,
            'total_nvs': sum(len(d['nvs']) for d in summary),
            'filters': {'ca': ca_filter, 'khoa': khoa_filter},
            'shifts': [{'id': k, 'name': v['name']} for k, v in SHIFTS.items()],
            'khoas': _list_khoa(),
        })

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
</style>
</head>
<body>
<h1>📡 Live Device Status</h1>
<div class="sub">BVĐK Ninh Thuận - Khoa Cấp Cứu Lưu Ký - Auto-probe mỗi 8 giây</div>
<div>
  <button onclick="probe()">🔄 Probe ngay</button>
  <button onclick="window.close()">✕ Đóng</button>
  <span class="refresh-info" id="info">Đang tải...</span>
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
async function probe() {
  document.getElementById('info').textContent = 'Đang probe...';
  try {
    const r = await fetch('/api/live');
    const data = await r.json();
    render(data);
  } catch (e) {
    document.getElementById('info').textContent = 'Lỗi: ' + e.message;
  }
}
function render(data) {
  const stats = document.getElementById('stats');
  stats.innerHTML =
    '<div class="stat"><div class="v">' + data.checked + '</div><div class="l">Tổng thiết bị</div></div>' +
    '<div class="stat ok"><div class="v">' + data.online + '</div><div class="l">Online</div></div>' +
    '<div class="stat fail"><div class="v">' + data.offline + '</div><div class="l">Offline</div></div>' +
    '<div class="stat"><div class="v">' + data.probed_at.split(' ')[1] + '</div><div class="l">Probe lúc</div></div>';
  const tbody = document.getElementById('rows');
  let i = 1;
  tbody.innerHTML = data.devices.map(function(d) {
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
  document.getElementById('info').textContent = 'Cập nhật lúc ' + data.probed_at + ' - tự refresh sau 8s';
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

    def _handle_merge(self):
        """
        Compare shadow log (pending_punches.csv from remote_punch_service) with
        real device log (all_records). Return which shadow punches are missing
        on devices, which are already in device, etc.

        Useful khi khong the ghi truc tiep vao may ZK X628 PRO (firmware 6.60 chan).
        BS co the dung ket qua de merge thu cong hoac in ra de NV xac nhan.
        """
        result = {
            'shadow_log': {
                'pending_file': os.path.join(SCRIPT_DIR, 'pending_punches.csv'),
                'synced_file': os.path.join(SCRIPT_DIR, 'synced_punches.csv'),
                'failed_file': os.path.join(SCRIPT_DIR, 'failed_punches.csv'),
            },
            'shadow_pending': [],
            'shadow_synced': [],
            'shadow_failed': [],
            'missing_on_device': [],
            'matched_on_device': [],
            'summary': {},
        }
        # Read shadow CSVs
        for key, path in [
            ('shadow_pending', result['shadow_log']['pending_file']),
            ('shadow_synced', result['shadow_log']['synced_file']),
            ('shadow_failed', result['shadow_log']['failed_file']),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            result[key].append(row)
                except Exception as e:
                    result.setdefault('errors', []).append('Read ' + key + ': ' + str(e)[:80])

        # Build set of (user_id, timestamp) from real device records
        real_set = set()
        for r in all_records:
            real_set.add((str(r.get('user_id', '')), str(r.get('timestamp', ''))))

        # Compare: for each pending, check if it's in real_set
        for p in result['shadow_pending']:
            key = (str(p.get('user_id', '')), str(p.get('timestamp', '')))
            if key in real_set:
                result['matched_on_device'].append(p)
            else:
                result['missing_on_device'].append(p)

        # Summary
        result['summary'] = {
            'shadow_pending_count': len(result['shadow_pending']),
            'shadow_synced_count': len(result['shadow_synced']),
            'shadow_failed_count': len(result['shadow_failed']),
            'matched_on_device_count': len(result['matched_on_device']),
            'missing_on_device_count': len(result['missing_on_device']),
            'real_device_records_count': len(all_records),
            'note': 'Firmware X628 PRO 6.60 chan ghi ATTLOG tu xa. shadow_pending can merge thu cong vao may that.',
        }
        self.send_json(result)

    def _handle_merge_page(self):
        """Trang MERGE rieng - giao dien full-page de BS lam viec hang ngay."""
        page = '''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MERGE Workflow - AttendanceSuite</title>
<style>
:root {
  --primary: #1976d2; --primary-light: #e3f2fd;
  --success: #2e7d32; --success-light: #e8f5e9;
  --warning: #f57c00; --warning-light: #fff3e0;
  --danger: #d32f2f;  --danger-light: #ffebee;
  --bg: #f5f7fa; --card: #fff; --border: #e0e4e8; --text: #2c3e50; --text-muted: #6b7c93;
  --radius: 8px; --shadow: 0 2px 8px rgba(0,0,0,0.08);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; }
.topbar { background: var(--card); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; gap: 16px; box-shadow: var(--shadow); }
.topbar h1 { font-size: 18px; font-weight: 600; color: var(--primary); }
.topbar .subtitle { font-size: 12px; color: var(--text-muted); }
.topbar a { color: var(--primary); text-decoration: none; font-size: 13px; padding: 6px 12px; border-radius: 6px; }
.topbar a:hover { background: var(--primary-light); }
.container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; box-shadow: var(--shadow); }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow); }
.kpi .v { font-size: 28px; font-weight: 700; line-height: 1.1; }
.kpi .l { font-size: 11px; color: var(--text-muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.kpi.warn .v { color: var(--warning); }
.kpi.danger .v { color: var(--danger); }
.kpi.success .v { color: var(--success); }
.kpi.info .v { color: var(--primary); }
table { width: 100%; border-collapse: collapse; }
th { background: #f8f9fa; padding: 12px 16px; text-align: left; font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid var(--border); }
td { padding: 10px 16px; border-bottom: 1px solid var(--border); font-size: 13px; font-family: 'SF Mono', Consolas, monospace; }
tr:hover { background: #f8f9fa; }
.banner { padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; border-left: 4px solid var(--warning); background: var(--warning-light); color: #5d4037; }
.banner.danger { background: var(--danger-light); border-color: var(--danger); color: #b71c1c; }
.banner.success { background: var(--success-light); border-color: var(--success); color: #1b5e20; }
button { padding: 8px 14px; border: 1px solid transparent; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.15s; }
.btn-primary { background: var(--primary); color: white; border: none; }
.btn-primary:hover { background: #1565c0; }
.btn-success { background: var(--success); color: white; border: none; }
.btn-outline { background: white; color: var(--text); border: 1px solid var(--border); }
.btn-outline:hover { background: #f0f4f8; }
.btn-danger { background: var(--danger); color: white; border: none; }
input, select { padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; background: white; }
input:focus, select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(25,118,210,0.12); }
.section-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.section-subtitle { font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }
.toolbar-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }
.matched-row { background: #f0fdf4 !important; }
.matched-row:hover { background: #dcfce7 !important; }
.missing-row { background: #fef2f2 !important; }
.missing-row:hover { background: #fee2e2 !important; }
@media print {
  .topbar, .no-print { display: none; }
  body { background: white; }
  .card { box-shadow: none; border: 1px solid #ccc; }
}
</style>
</head>
<body>
<div class="topbar">
  <h1>🔀 MERGE Workflow</h1>
  <span class="subtitle">So sánh shadow log (pending từ xa) với log máy thật</span>
  <a href="/">← Về trang chính</a>
</div>
<div class="container">
  <div class="card no-print">
    <div class="section-title">📋 Quy trình hàng ngày</div>
    <ol style="padding-left: 24px; line-height: 1.8">
      <li><b>BS chấm từ xa</b> (qua mobile app, web dashboard, hoặc từ Secutime remote) → ghi vào <code>pending_punches.csv</code></li>
      <li><b>Service đồng bộ</b> cố gắng push vào máy thật (Secutime/ADMS/Direct ZK) - thường fail do firmware</li>
      <li><b>NV đến máy thật chấm vân tay</b> → log vào máy</li>
      <li><b>Sáng hôm sau</b>: BS mở trang này, bấm <b>"🔄 Refresh"</b> để so sánh shadow log với log máy</li>
      <li><b>Với mỗi punch trong "Missing trên máy"</b>: in danh sách, NV tự xác nhận đã chấm tay → BS bấm <b>✓ Đã merge</b></li>
    </ol>
  </div>

  <div class="card no-print">
    <div class="toolbar-row">
      <label>Ngày:</label>
      <input type="date" id="mergeDate" value="">
      <button class="btn-primary" onclick="loadMerge()">🔄 Refresh</button>
      <button class="btn-outline" onclick="window.print()">🖨 In danh sách</button>
      <button class="btn-outline" onclick="exportMergeCSV()">📥 Xuất CSV</button>
      <button class="btn-danger" onclick="clearOldPending()">🗑 Xóa cũ (>30 ngày)</button>
    </div>
  </div>

  <div class="banner danger">
    <b>⚠ GIỚI HẠN FIRMWARE</b>: X628 PRO 6.60 chặn ghi ATTLOG từ xa. Workflow này giúp theo dõi và merge tay các punch còn thiếu.
  </div>

  <div class="kpi-grid" id="kpiGrid">
    <div class="kpi info"><div class="v" id="kpiShadow">-</div><div class="l">Shadow pending (hôm nay)</div></div>
    <div class="kpi success"><div class="v" id="kpiMatched">-</div><div class="l">Đã có trên máy</div></div>
    <div class="kpi danger"><div class="v" id="kpiMissing">-</div><div class="l">CẦN merge tay</div></div>
    <div class="kpi warn"><div class="v" id="kpiRate">-</div><div class="l">Tỷ lệ sync (%)</div></div>
  </div>

  <div class="card">
    <div class="section-title">🔴 Missing trên máy <span id="missingCount" style="color: var(--danger)">(0)</span></div>
    <div class="section-subtitle">Các punch còn thiếu - in ra đưa NV xác nhận rồi bấm "Đã merge" sau khi NV chấm tay</div>
    <div style="max-height: 400px; overflow-y: auto;">
      <table>
        <thead><tr>
          <th>ID</th><th>Mã NV</th><th>Thời gian</th><th>Trạng thái</th><th>Máy dự kiến</th><th>Ghi chú</th>
          <th class="no-print">Thao tác</th>
        </tr></thead>
        <tbody id="missingTable"></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <div class="section-title">✅ Đã có trên máy <span id="matchedCount" style="color: var(--success)">(0)</span></div>
    <div class="section-subtitle">Các punch đã được ghi nhận trên thiết bị thật (không cần làm gì)</div>
    <details>
      <summary style="cursor:pointer;color:var(--text-muted)">Click để xem chi tiết</summary>
      <div style="max-height: 300px; overflow-y: auto; margin-top: 12px;">
        <table>
          <thead><tr><th>ID</th><th>Mã NV</th><th>Thời gian</th><th>Máy thật</th><th>Trạng thái</th></tr></thead>
          <tbody id="matchedTable"></tbody>
        </table>
      </div>
    </details>
  </div>

  <div class="card">
    <div class="section-title">📊 Phân bố theo máy</div>
    <div id="deviceStats"></div>
  </div>
</div>

<script>
let currentData = null;

async function loadMerge() {
  const dateStr = document.getElementById('mergeDate').value;
  const url = '/api/merge/today' + (dateStr ? '?date=' + dateStr : '');
  try {
    const r = await fetch(url);
    const data = await r.json();
    currentData = data;
    render(data);
  } catch (e) {
    alert('Loi: ' + e.message);
  }
}

function render(d) {
  document.getElementById('kpiShadow').textContent = d.summary.shadow_today_count;
  document.getElementById('kpiMatched').textContent = d.summary.matched_count;
  document.getElementById('kpiMissing').textContent = d.summary.missing_count;
  document.getElementById('kpiRate').textContent = d.summary.merge_rate + '%';
  document.getElementById('missingCount').textContent = '(' + d.missing_on_device.length + ')';
  document.getElementById('matchedCount').textContent = '(' + d.matched_on_device.length + ')';

  const mt = document.getElementById('missingTable');
  mt.innerHTML = '';
  if (d.missing_on_device.length === 0) {
    mt.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:30px">🎉 Tất cả punch đều đã có trên máy! Không cần merge.</td></tr>';
  } else {
    for (const p of d.missing_on_device) {
      mt.innerHTML += '<tr class="missing-row">' +
        '<td style="font-size:11px">' + (p.punch_id || '').slice(-6) + '</td>' +
        '<td style="color:var(--primary);font-weight:600">' + (p.user_id || '') + '</td>' +
        '<td>' + (p.timestamp || '') + '</td>' +
        '<td>' + (p.status_name || '') + '</td>' +
        '<td style="font-size:12px">' + (p.device_ip || '') + '</td>' +
        '<td style="font-size:11px;color:var(--text-muted)">' + (p.note || '') + '</td>' +
        '<td class="no-print"><button class="btn-success" style="padding:4px 10px;font-size:12px" onclick="markDone(\\'' + p.punch_id + '\\')">✓ Đã merge</button></td>' +
        '</tr>';
    }
  }

  const mat = document.getElementById('matchedTable');
  mat.innerHTML = '';
  for (const p of d.matched_on_device) {
    mat.innerHTML += '<tr class="matched-row">' +
      '<td style="font-size:11px">' + (p.punch_id || '').slice(-6) + '</td>' +
      '<td style="color:var(--primary);font-weight:600">' + (p.user_id || '') + '</td>' +
      '<td>' + (p.timestamp || '') + '</td>' +
      '<td style="font-size:12px">' + (p.device_ip || '') + '</td>' +
      '<td>' + (p.status_name || '') + '</td>' +
      '</tr>';
  }

  const ds = document.getElementById('deviceStats');
  ds.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px">';
  for (const [dev, count] of Object.entries(d.by_device || {})) {
    ds.innerHTML += '<div style="padding:10px 14px;background:#f8f9fa;border-radius:6px"><div style="font-family:monospace;font-size:12px">' + dev + '</div><div style="font-size:20px;font-weight:700">' + count + ' punch</div></div>';
  }
  if (Object.keys(d.by_device || {}).length === 0) {
    ds.innerHTML = '<div style="color:var(--text-muted);padding:20px">Không có punch pending hôm nay.</div>';
  }
  ds.innerHTML += '</div>';
}

async function markDone(punchId) {
  if (!confirm('Đánh dấu punch #' + punchId + ' đã merge xong?')) return;
  try {
    const r = await fetch('/api/merge/mark-done', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({punch_id: punchId}),
    });
    const data = await r.json();
    if (data.ok) {
      alert('Đã merge!');
      loadMerge();
    } else {
      alert('Lỗi: ' + data.error);
    }
  } catch (e) {
    alert('Lỗi: ' + e.message);
  }
}

function exportMergeCSV() {
  if (!currentData) return alert('Chưa có dữ liệu');
  let csv = 'punch_id,timestamp,user_id,status,status_name,device_ip,note\n';
  for (const p of currentData.missing_on_device) {
    csv += (p.punch_id || '') + ',' + (p.timestamp || '') + ',' + (p.user_id || '') + ',' +
           (p.status || '') + ',' + (p.status_name || '') + ',' + (p.device_ip || '') + ',' +
           (p.note || '') + '\\n';
  }
  const blob = new Blob(['\\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'merge_' + currentData.date + '.csv';
  a.click();
}

async function clearOldPending() {
  const days = prompt('Xóa các pending cũ hơn bao nhiêu ngày?', '30');
  if (!days) return;
  try {
    const r = await fetch('/api/merge/clear-old', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({days: parseInt(days)}),
    });
    const data = await r.json();
    alert(data.message);
    loadMerge();
  } catch (e) {
    alert('Lỗi: ' + e.message);
  }
}

document.getElementById('mergeDate').value = new Date().toISOString().slice(0, 10);
loadMerge();
</script>
</body>
</html>'''
        body = page.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_merge_today(self):
        """
        Trả về chi tiết các punch pending hôm nay (theo timestamp).
        Kèm:
        - match_on_device: đã có trong all_records (KHÔNG cần merge)
        - missing_on_device: chưa có trong all_records (CẦN merge tay)
        - stats theo từng device
        """
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        # Parse date param (default today)
        date_str = qs.get('date', [None])[0]
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                target_date = datetime.now().date()
        else:
            target_date = datetime.now().date()

        result = {
            'date': target_date.strftime('%Y-%m-%d'),
            'shadow_today': [],
            'matched_on_device': [],
            'missing_on_device': [],
            'by_device': {},
            'by_status': {},
        }

        # Read shadow log
        pending_path = os.path.join(SCRIPT_DIR, 'pending_punches.csv')
        shadow_rows = []
        if os.path.exists(pending_path):
            try:
                with open(pending_path, 'r', encoding='utf-8-sig', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ts = row.get('timestamp', '')
                        if ts.startswith(target_date.strftime('%Y-%m-%d')):
                            shadow_rows.append(row)
            except Exception as e:
                result['error'] = str(e)[:200]
        result['shadow_today'] = shadow_rows

        # Build real records set
        real_set = set()
        real_by_dev = {}
        for r in all_records:
            ts_str = str(r.get('timestamp', ''))
            if ts_str.startswith(target_date.strftime('%Y-%m-%d')):
                real_set.add((str(r.get('user_id', '')), ts_str))
                dev = r.get('device_ip', 'unknown')
                real_by_dev.setdefault(dev, []).append(r)

        # Compare
        for p in shadow_rows:
            key = (str(p.get('user_id', '')), str(p.get('timestamp', '')))
            if key in real_set:
                result['matched_on_device'].append(p)
            else:
                result['missing_on_device'].append(p)
            # Stats
            dev = p.get('device_ip', 'unknown')
            result['by_device'].setdefault(dev, 0)
            result['by_device'][dev] += 1
            sname = p.get('status_name', 'Unknown')
            result['by_status'].setdefault(sname, 0)
            result['by_status'][sname] += 1

        # Count by hour
        result['by_hour'] = {}
        for p in shadow_rows:
            ts = p.get('timestamp', '')
            if len(ts) >= 13:
                hr = ts[11:13]
                result['by_hour'][hr] = result['by_hour'].get(hr, 0) + 1

        result['summary'] = {
            'date': target_date.strftime('%Y-%m-%d'),
            'shadow_today_count': len(shadow_rows),
            'matched_count': len(result['matched_on_device']),
            'missing_count': len(result['missing_on_device']),
            'real_today_count': sum(len(v) for v in real_by_dev.values()),
            'merge_rate': round(100 * len(result['matched_on_device']) / max(len(shadow_rows), 1), 1),
        }
        self.send_json(result)

    def _handle_merge_mark_done(self, data):
        """
        POST: Move a pending punch to 'synced' (mark as merged manually).
        Body: {punch_id: 'xxx'}
        Move từ pending_punches.csv sang synced_punches.csv với synced_via='manual_merge'.
        Body da duoc doc boi do_POST (truyen qua tham so data).
        """
        punch_id = str(data.get('punch_id', ''))
        if not punch_id:
            self.send_json({'ok': False, 'error': 'Missing punch_id'}, status=400)
            return

        pending_path = os.path.join(SCRIPT_DIR, 'pending_punches.csv')
        synced_path = os.path.join(SCRIPT_DIR, 'synced_punches.csv')
        if not os.path.exists(pending_path):
            self.send_json({'ok': False, 'error': 'No pending file'}, status=404)
            return

        rows = read_csv(pending_path)
        target = None
        remaining = []
        for row in rows:
            if str(row.get('punch_id', '')) == punch_id:
                target = row
            else:
                remaining.append(row)
        if not target:
            self.send_json({'ok': False, 'error': 'punch_id not found: ' + punch_id}, status=404)
            return
        # Update
        target['synced_via'] = 'manual_merge'
        target['synced_at'] = datetime.now().isoformat()
        original_note = target.get('note', '')
        if not original_note:
            original_note = ''
        target['note'] = (original_note + ' | ' if original_note else '') + 'Merged manually at ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Write
        rewrite_csv(pending_path, remaining)
        append_csv(synced_path, target)
        self.send_json({
            'ok': True,
            'message': 'Marked as merged: ' + punch_id,
            'remaining_pending': len(remaining),
        })

    def _handle_merge_clear_old(self, data):
        """
        POST: Xoa cac pending cu hon X ngay (mac dinh 30).
        Body: {days: 30}
        """
        days = int(data.get('days', 30))
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')

        pending_path = os.path.join(SCRIPT_DIR, 'pending_punches.csv')
        if not os.path.exists(pending_path):
            self.send_json({'ok': False, 'error': 'No pending file'}, status=404)
            return

        rows = read_csv(pending_path)
        remaining = []
        removed = []
        for row in rows:
            ts = row.get('timestamp', '')
            if ts and ts < cutoff_str:
                removed.append(row)
            else:
                remaining.append(row)
        rewrite_csv(pending_path, remaining)
        self.send_json({
            'ok': True,
            'message': 'Removed {0} old pending, kept {1}'.format(len(removed), len(remaining)),
            'removed_count': len(removed),
            'remaining_count': len(remaining),
        })

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
            'version': '1.3.0',
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


# ============ CSV helpers (for merge workflow) ============
MERGE_CSV_FIELDS = [
    'punch_id', 'timestamp', 'user_id', 'user_name',
    'status', 'status_name', 'punch', 'method_name',
    'device_ip', 'synced_via', 'synced_at', 'note'
]


def _ensure_csv_header(path):
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=MERGE_CSV_FIELDS)
            w.writeheader()


def read_csv(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def append_csv(path, row):
    _ensure_csv_header(path)
    with open(path, 'a', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=MERGE_CSV_FIELDS, extrasaction='ignore')
        w.writerow(row)


def rewrite_csv(path, rows):
    _ensure_csv_header(path)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=MERGE_CSV_FIELDS, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _do_backup_now():
    """Auto backup ZKDB.db + config + CSVs to backups/YYYY-MM-DD/.
    Returns (ok, message, file_count).
    """
    import shutil
    from datetime import datetime
    backup_root = os.path.join(SCRIPT_DIR, 'backups')
    date_str = datetime.now().strftime('%Y-%m-%d')
    backup_dir = os.path.join(backup_root, date_str)
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime('%H%M%S')
    files_to_copy = [
        ('config.json', 'config.json'),
        ('devices.csv', 'devices.csv'),
        ('pending_punches.csv', 'pending_punches.csv'),
        ('synced_punches.csv', 'synced_punches.csv'),
        ('failed_punches.csv', 'failed_punches.csv'),
        ('manual_punches.csv', 'manual_punches.csv'),
    ]
    # Optional ZKDB.db (large, only if exists)
    zkdb_paths = [
        os.path.join(SCRIPT_DIR, 'zk_data_extracted', 'ZKDB.db'),
        os.path.join('D:\\chamcong', 'zk_data_extracted', 'ZKDB.db'),
        os.path.join('C:\\Users\\drkro\\Desktop', 'zk_data_extracted', 'ZKDB.db'),
    ]
    for zp in zkdb_paths:
        if os.path.exists(zp):
            files_to_copy.append((zp, f'ZKDB_{date_str}.db'))
            break
    count = 0
    copied = []
    for src, dst_name in files_to_copy:
        if not os.path.exists(src):
            continue
        dst = os.path.join(backup_dir, dst_name)
        try:
            shutil.copy2(src, dst)
            count += 1
            copied.append(dst_name)
        except Exception as e:
            print(f"  Backup ERR {src}: {e}")
    # Cleanup: keep only last 30 backups
    try:
        if os.path.exists(backup_root):
            all_backups = sorted([d for d in os.listdir(backup_root)
                                   if os.path.isdir(os.path.join(backup_root, d))])
            for old_dir in all_backups[:-30]:
                shutil.rmtree(os.path.join(backup_root, old_dir), ignore_errors=True)
    except Exception as e:
        print(f"  Backup cleanup ERR: {e}")
    msg = f"Backed up {count} files to {backup_dir} (ts={ts})"
    return count > 0, msg, count, copied


def _backup_scheduler():
    """Background thread: backup daily at 0h05."""
    import time
    from datetime import datetime, timedelta
    last_backup_date = None
    while True:
        try:
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            # Run backup if not done today and past 00:05
            if today != last_backup_date and (now.hour > 0 or (now.hour == 0 and now.minute >= 5)):
                ok, msg, count, files = _do_backup_now()
                if ok:
                    last_backup_date = today
                    print(f"[BACKUP {now.strftime('%H:%M:%S')}] {msg}")
                else:
                    print(f"[BACKUP {now.strftime('%H:%M:%S')}] No files to backup")
                    last_backup_date = today  # Mark anyway to retry next day
        except Exception as e:
            print(f"[BACKUP ERR] {e}")
        # Sleep 5 minutes between checks
        time.sleep(300)


# === Attach security/punch routes (v1.8+) ===
try:
    from security_routes import attach_security_routes
    attach_security_routes(Handler)
    print('[OK] Security & Manual Punch routes attached')
except ImportError as e:
    print(f'[!] security_routes.py not found: {e}')


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

    # Start auto backup scheduler (daily at 00:05)
    backup_thread = threading.Thread(target=_backup_scheduler, daemon=True)
    backup_thread.start()
    print('[OK] Auto backup scheduler started (daily 00:05)')

    # Manual backup endpoint
    print('[OK] Backup endpoint: POST /api/backup/now -> trigger manual backup')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[*] Stopping...')
        server.shutdown()


if __name__ == '__main__':
    main()
