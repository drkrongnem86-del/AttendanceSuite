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
    const canSelect = (d.type === 'attendance');
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
  allDevices.forEach(function(d) { if (d.type === 'attendance') d.selected = sel; });
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
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
