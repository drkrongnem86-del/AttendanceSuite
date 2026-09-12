# -*- coding: utf-8 -*-
"""
X628 PRO Punch Simulator
Mo phong may cham cong X628 PRO - nhap ma NV, chon thao tac, ghi log.

Version: 1.1.0 (build 2)
- Add "Pass" field for User ID + Password verification mode
- Connection status badge
- Per-punch delete with honest device-delete report
- Auto-reset UI after success
- Multi-format write attempts to device

Luu y quan trong:
- May X628 PRO KHONG ho tro ghi attendance log qua giao thuc ZK chuan (UDP 4370)
- Tool nay ghi vao local file (shadow log) - dam bao luon luon hoat dong
- Co gang ghi vao may that qua nhieu format - tuy thuoc firmware

Su dung:
- Truy cap http://localhost:8081 trong browser
- Nhap ma NV (1-10 so), neu muon them pass (1-8 so)
- Chon thao tac (In/Out/Break/OT), chon phuong thuc (FP/Card/Pwd)
- Bam "Cham cong" -> ghi log local
- Xem lai trong "Lich su cham cong" (local shadow log)
"""

import os
import sys
import json
import csv
import struct
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Them path den pyzk
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python', 'Lib', 'site-packages'))
from zk import ZK
from zk import const as zk_const

SHADOW_LOG_FILE = os.path.join(os.path.dirname(__file__), 'manual_punches.csv')
DEVICE_IP = '172.16.0.212'  # default fallback
HTTP_PORT = 8081
DEVICES_CSV = os.path.join(os.path.dirname(__file__), 'devices.csv')

# State
punch_history = []  # In-memory recent punches (max 1000)
next_punch_id = [1]  # Monotonic ID counter for each punch entry
device_status = {'connected': False, 'model': '?', 'last_attempt': None, 'message': ''}
devices = []  # [{ip, type, note, selected}] - loaded from devices.csv
device_statuses = {}  # {ip: {connected, model, firmware, users_count, records_count, message, last_check}}
devices_lock = threading.Lock()
punch_lock = threading.Lock()


def load_devices():
    """Load all devices from devices.csv. Returns list of dicts."""
    global devices
    result = []
    if not os.path.exists(DEVICES_CSV):
        print('[!] devices.csv not found, using only default', flush=True)
        return result
    try:
        with open(DEVICES_CSV, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ip = (row.get('IP') or row.get('ip') or '').strip()
                if not ip:
                    continue
                typ = (row.get('Type') or row.get('type') or 'attendance').strip()
                note = (row.get('Note') or row.get('note') or '').strip()
                sel = (row.get('Selected') or row.get('selected') or '0').strip()
                try:
                    sel_int = int(sel)
                except:
                    sel_int = 0
                result.append({'ip': ip, 'type': typ, 'note': note, 'selected': sel_int == 1})
        devices = result
        print('[+] Loaded ' + str(len(devices)) + ' devices from devices.csv', flush=True)
    except Exception as e:
        print('[!] Load devices error: ' + str(e), flush=True)
    return result


def ping_device(ip, timeout=4):
    """Try to connect to a ZK device, return status dict."""
    status = {'connected': False, 'model': '?', 'firmware': '?', 'users_count': 0,
              'records_count': 0, 'message': 'Not checked', 'last_check': None}
    try:
        zk = ZK(ip, port=4370, timeout=timeout, ommit_ping=True, verbose=False)
        if zk.connect():
            try:
                status['model'] = str(zk.get_device_name() or '?')
                status['firmware'] = str(zk.get_firmware_version() or '?')
                users = zk.get_users()
                status['users_count'] = len(users) if users else 0
                zk.read_sizes()
                status['records_count'] = int(zk.records or 0)
                status['connected'] = True
                status['message'] = 'OK'
            except Exception as e:
                status['connected'] = True
                status['message'] = 'Partial: ' + str(e)[:50]
            finally:
                try: zk.disconnect()
                except: pass
        else:
            status['message'] = 'Connect failed (timeout or refused)'
    except Exception as e:
        status['message'] = str(e)[:80]
    status['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return status


def device_pinger_loop():
    """Background loop: ping all attendance devices every 20s."""
    while True:
        try:
            targets = [d['ip'] for d in devices if d.get('type') in ('attendance', 'attendance-gateway')]
            for ip in targets:
                st = ping_device(ip, timeout=3)
                with devices_lock:
                    device_statuses[ip] = st
                # v1.5.7: Neu IP la primary device -> cap nhat device_status luon
                if ip == DEVICE_IP:
                    with devices_lock:
                        device_status.update({
                            'connected': st.get('connected', False),
                            'ip': ip,
                            'model': st.get('model', '?'),
                            'firmware': st.get('firmware', '?'),
                            'users_count': st.get('users_count', 0),
                            'records_count': st.get('records_count', 0),
                            'message': st.get('message', ''),
                            'last_check': st.get('last_check'),
                        })
        except Exception as e:
            print('[pinger] error: ' + str(e), flush=True)
        time.sleep(20)


def load_shadow_log():
    """Load existing manual punches from CSV. Assigns punch_id to each entry."""
    global next_punch_id
    if not os.path.exists(SHADOW_LOG_FILE):
        return
    try:
        # Use utf-8-sig to handle BOM from previous writes
        with open(SHADOW_LOG_FILE, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Assign a fresh punch_id to each loaded entry
                row['punch_id'] = next_punch_id[0]
                next_punch_id[0] += 1
                # Backfill human-readable names from raw codes (for entries saved by older versions)
                try:
                    if 'status' in row and row['status'].isdigit():
                        row['status_name'] = get_status_name(int(row['status']))
                    if 'punch' in row and row['punch'].isdigit():
                        row['method_name'] = get_punch_name(int(row['punch']))
                except:
                    pass
                punch_history.append(row)
        print('Loaded ' + str(len(punch_history)) + ' entries from shadow log', flush=True)
    except Exception as e:
        print('Load shadow log error: ' + str(e), flush=True)


def save_shadow_log_entry(entry):
    """Append one entry to shadow log CSV"""
    file_exists = os.path.exists(SHADOW_LOG_FILE)
    fieldnames = ['timestamp', 'device_ip', 'user_id', 'user_name', 'status', 'punch', 'method_name', 'written_to_device', 'note']
    # Filter entry to only known fields (drop status_name etc.)
    safe_entry = {k: v for k, v in entry.items() if k in fieldnames}
    try:
        with open(SHADOW_LOG_FILE, 'a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(safe_entry)
            f.flush()
    except Exception as e:
        print('Save shadow log error: ' + str(e), flush=True)


def rewrite_shadow_log():
    """Rewrite shadow log CSV from current punch_history"""
    fieldnames = ['timestamp', 'device_ip', 'user_id', 'user_name', 'status', 'punch', 'method_name', 'written_to_device', 'note']
    try:
        with open(SHADOW_LOG_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for h in punch_history:
                safe_entry = {k: v for k, v in h.items() if k in fieldnames}
                writer.writerow(safe_entry)
            f.flush()
        return True, 'OK'
    except Exception as e:
        return False, str(e)


def try_delete_from_device(device_ip, user_id, timestamp_str):
    """
    Try to delete a specific attendance record from the ZK device.
    Note: ZK protocol does NOT support per-record delete. Only CMD_CLEAR_ATTLOG
    exists which clears ALL attendance logs (DANGEROUS - we won't use it).
    Returns (success, message).
    """
    # The only "delete" command in ZK protocol is CMD_CLEAR_ATTLOG (15) which wipes
    # ALL attendance records. We will NOT execute it (too dangerous).
    # Instead, we honestly report that device-side delete is not supported.
    return False, 'May ZK khong ho tro xoa 1 ban ghi rieng le (chi xoa het bang CMD_CLEAR_ATTLOG - qua nguy hiem). Chi xoa local.'


def get_status_name(status_code):
    return {
        0: 'Check-In',
        1: 'Check-Out',
        2: 'Break-Out',
        3: 'Break-In',
        4: 'OT-In',
        5: 'OT-Out',
    }.get(status_code, 'Status-' + str(status_code))


def get_punch_name(punch_code):
    return {
        0: 'Vân tay',
        1: 'Thẻ',
        2: 'Mật khẩu',
    }.get(punch_code, 'Khác')


def try_write_to_device(device_ip, user_id, status, punch_code, timestamp_dt, pass_value=None):
    """
    Attempt to write attendance to ZK device using multiple approaches.
    If pass_value is provided, include it in the packet (for User ID + Password mode).

    Returns (success: bool, message: str).
    Tries:
    1. CMD_REG_EVENT (500) with multiple packet formats
    2. CMD_DATA_WRRQ (1503) with FCT_ATTLOG payload (raw 40-byte record)
    3. Direct UDP socket with crafted packets
    """
    zk = None
    try:
        zk = ZK(device_ip, port=4370, timeout=10, ommit_ping=True, verbose=False)
        if not zk.connect():
            return False, 'Khong ket noi duoc may'

        # Step 1: Verify user exists
        users = zk.get_users()
        user_found = None
        for u in users:
            if str(u.user_id) == str(user_id):
                user_found = u
                break

        if not user_found:
            zk.disconnect()
            return False, 'Ma NV ' + str(user_id) + ' chua dang ky trong may'

        # Step 2: Read count BEFORE
        try:
            zk.read_sizes()
            count_before = zk.records
        except:
            count_before = None

        ts_int = int(timestamp_dt.timestamp())
        uid_int = int(user_id)

        # Try multiple packet formats (v1.4.0: 8 methods, da test ky 7/9/2026)
        # Phat hien moi:
        #   - CMD_REFRESHDATA (1013), CMD_FREE_DATA (1502): ACK_OK nhung chi la "ack announce", khong ghi
        #   - CMD_DATA (1501): "TCP packet invalid" - that bai ngay
        #   - UDP mode: timeout (X628 PRO chi nhan TCP)
        #   - set_user WORK: ghi vao USER table OK
        #   - ATTLOG write: khong the bypass
        attempts = []

        # Format 1: Original - <IIBB with padding
        attempts.append(('CMD_REG_EVENT basic', lambda: zk._ZK__send_command(
            zk_const.CMD_REG_EVENT,
            struct.pack('<IIBB', uid_int, ts_int, status, punch_code).ljust(16, b'\x00'),
            response_size=8
        )))

        # Format 2: <HBB ts user
        attempts.append(('CMD_REG_EVENT alt', lambda: zk._ZK__send_command(
            zk_const.CMD_REG_EVENT,
            struct.pack('<HBB', 0, status, punch_code) + struct.pack('<II', ts_int, uid_int),
            response_size=8
        )))

        # Format 3: 40-byte attendance record via CMD_REG_EVENT
        # This is the actual record format from ZK
        user_id_bytes = user_id.encode('ascii').ljust(24, b'\x00')[:24]
        ts_bytes = struct.pack('<I', ts_int)
        record_40 = struct.pack('<H', 0) + user_id_bytes + struct.pack('<B', status) + ts_bytes + struct.pack('<B', punch_code) + b'\x00' * 8
        attempts.append(('CMD_REG_EVENT 40-byte record', lambda: zk._ZK__send_command(
            zk_const.CMD_REG_EVENT,
            record_40.ljust(40, b'\x00'),
            response_size=8
        )))

        # Format 4: 40-byte record wrapped in CMD_DATA_WRRQ
        inner_cmd = struct.pack('<bhii', 1, zk_const.CMD_ATTLOG_RRQ, 0, 0)
        attempts.append(('CMD_DATA_WRRQ+FCT_ATTLOG write', lambda: zk._ZK__send_command(
            zk_const.CMD_DATA_WRRQ,
            inner_cmd + record_40.ljust(40, b'\x00'),
            response_size=8
        )))

        # Format 5: 40-byte record with CMD_USERTEMP_WRQ
        attempts.append(('CMD_USERTEMP_WRQ', lambda: zk._ZK__send_command(
            zk_const.CMD_USERTEMP_WRQ,
            record_40.ljust(40, b'\x00'),
            response_size=8
        )))

        # Format 6: CMD_OPTIONS_WRQ
        attempts.append(('CMD_OPTIONS_WRQ', lambda: zk._ZK__send_command(
            zk_const.CMD_OPTIONS_WRQ,
            record_40.ljust(40, b'\x00'),
            response_size=8
        )))

        ack_ok_any = False
        tried_methods = []
        for method_name, attempt_fn in attempts:
            try:
                resp = attempt_fn()
                if resp and resp.get('status') and resp.get('code') == zk_const.CMD_ACK_OK:
                    tried_methods.append(method_name)
                    ack_ok_any = True
            except:
                pass

        # Step 4: Verify by re-reading count
        if ack_ok_any and count_before is not None:
            try:
                # Disconnect and reconnect for clean state
                zk.disconnect()
                zk = ZK(device_ip, port=4370, timeout=10, ommit_ping=True, verbose=False)
                if zk.connect():
                    zk.read_sizes()
                    count_after = zk.records
                    if count_after > count_before:
                        zk.disconnect()
                        return True, 'Da ghi vao may that (records: ' + str(count_before) + ' -> ' + str(count_after) + ') qua ' + ', '.join(tried_methods)
                    else:
                        zk.disconnect()
                        return False, 'Da thu ' + str(len(attempts)) + ' cach, may ACK_OK nhung KHONG ghi (records van ' + str(count_after) + '). ZK firmware that su khong cho ghi tu xa. Da luu local.'
            except Exception as e:
                pass

        try: zk.disconnect()
        except: pass
        return False, 'May khong ho tro ghi attendance tu xa (da thu ' + str(len(attempts)) + ' format). Da luu local shadow log.'

    except Exception as e:
        try:
            if zk: zk.disconnect()
        except: pass
        return False, 'Connection error: ' + str(e)[:80]


HTML_PAGE = r'''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>X628 PRO Simulator - May cham cong ao</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', Tahoma, sans-serif;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  min-height: 100vh;
  color: #e0e0e0;
  padding: 20px;
}
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #00d4ff; margin-bottom: 8px; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 14px; }
.row { display: flex; gap: 20px; flex-wrap: wrap; }
.col { flex: 1; min-width: 320px; }
.panel {
  background: #0f1729;
  border: 1px solid #2a3a5a;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}
.panel h2 {
  color: #00d4ff;
  font-size: 16px;
  margin-bottom: 15px;
  border-bottom: 1px solid #2a3a5a;
  padding-bottom: 8px;
}

/* X628 PRO Machine Simulation */
.machine {
  background: linear-gradient(180deg, #2a2a2a 0%, #1a1a1a 100%);
  border-radius: 12px;
  padding: 20px;
  width: 360px;
  margin: 0 auto;
  box-shadow: 0 8px 24px rgba(0,0,0,0.6);
  border: 2px solid #444;
}
.machine-screen {
  background: #0a3d2e;
  border: 2px solid #555;
  border-radius: 6px;
  padding: 15px;
  font-family: 'Courier New', monospace;
  color: #5fff7f;
  font-size: 18px;
  text-align: center;
  min-height: 100px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  margin-bottom: 15px;
  box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
}
.machine-screen .time { font-size: 14px; color: #5fff7f; opacity: 0.8; }
.machine-screen .user { font-size: 24px; font-weight: bold; margin: 8px 0; }
.machine-screen .status { font-size: 14px; color: #ffd700; }

.machine-fp {
  width: 80px; height: 80px;
  background: radial-gradient(circle, #555 30%, #222 70%);
  border-radius: 50%;
  margin: 10px auto;
  border: 3px solid #666;
  position: relative;
}
.machine-fp.active {
  background: radial-gradient(circle, #00ff88 30%, #008844 70%);
  box-shadow: 0 0 20px #00ff88;
}
.machine-fp::after {
  content: '🖐';
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  font-size: 30px;
  opacity: 0.6;
}

.keypad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-top: 15px;
}
.key {
  background: #3a3a3a;
  border: 1px solid #555;
  color: #fff;
  padding: 12px;
  font-size: 18px;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
  text-align: center;
  transition: all 0.1s;
}
.key:hover { background: #4a4a4a; }
.key:active { background: #00d4ff; color: #000; }
.key.action { background: #b8336a; }
.key.action:hover { background: #d4447a; }
.key.clear { background: #cc6600; }
.key.clear:hover { background: #ee7700; }

.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px;
  background: #1a1a1a;
  border-radius: 4px;
  font-size: 12px;
}
.led {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #333;
}
.led.green { background: #00ff00; box-shadow: 0 0 8px #00ff00; }
.led.red { background: #ff0000; box-shadow: 0 0 8px #ff0000; }
.led.yellow { background: #ffd700; box-shadow: 0 0 8px #ffd700; }

/* Action buttons */
.action-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-top: 15px;
}
.action-btn {
  padding: 10px;
  border: 1px solid #555;
  background: #1a3a5a;
  color: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.1s;
}
.action-btn:hover { background: #2a4a6a; }
.action-btn.selected {
  background: #00d4ff;
  color: #000;
  border-color: #00d4ff;
}

/* Method buttons */
.method-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-top: 10px;
}
.method-btn {
  padding: 8px;
  border: 1px solid #555;
  background: #2a2a2a;
  color: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.method-btn.selected {
  background: #00ff88;
  color: #000;
}

/* Submit button */
.submit-btn {
  width: 100%;
  padding: 15px;
  background: linear-gradient(135deg, #00d4ff 0%, #0084ff 100%);
  color: #000;
  border: none;
  border-radius: 4px;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  margin-top: 15px;
}
.submit-btn:hover { opacity: 0.9; }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* History */
.history {
  max-height: 400px;
  overflow-y: auto;
  font-size: 13px;
}
.history-item {
  padding: 8px;
  border-bottom: 1px solid #2a3a5a;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.history-item .time { color: #888; font-family: monospace; }
.history-item .info { color: #00d4ff; }
.history-item .status { padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.status-check-in { background: #1a5a1a; color: #5fff7f; }
.status-check-out { background: #5a1a1a; color: #ff8888; }
.status-break-out { background: #5a4a1a; color: #ffd700; }
.status-break-in { background: #1a4a5a; color: #88ddff; }
.status-ot { background: #4a1a5a; color: #dd88ff; }

/* Connection status badge */
.conn-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: bold;
  margin-bottom: 12px;
}
.conn-badge.online { background: #1a4a1a; color: #5fff7f; border: 1px solid #2a6a2a; }
.conn-badge.offline { background: #4a1a1a; color: #ff8888; border: 1px solid #6a2a2a; }
.conn-badge .dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}
.conn-badge.online .dot { background: #5fff7f; }
.conn-badge.offline .dot { background: #ff8888; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Success line on machine screen */
.machine-screen .success-line {
  color: #00ff00;
  font-weight: bold;
  font-size: 16px;
  margin-top: 4px;
  text-shadow: 0 0 8px #00ff00;
}

/* Delete button on history items */
.del-btn {
  background: #5a1a1a;
  color: #ff8888;
  border: 1px solid #6a2a2a;
  border-radius: 3px;
  padding: 2px 8px;
  font-size: 12px;
  cursor: pointer;
  margin-left: 6px;
  transition: all 0.1s;
}
.del-btn:hover { background: #7a1a1a; color: #ffaaaa; }
.del-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.clear-all-btn {
  background: #6a2a1a;
  color: #ffaa88;
  border: 1px solid #8a3a2a;
  border-radius: 4px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  float: right;
}
.clear-all-btn:hover { background: #8a3a2a; }

.flash {
  animation: flash 0.5s;
}
@keyframes flash {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.message {
  padding: 10px;
  border-radius: 4px;
  margin-top: 10px;
  font-size: 13px;
  display: none;
}
.message.success { background: #1a4a1a; color: #5fff7f; display: block; }
.message.error { background: #4a1a1a; color: #ff8888; display: block; }
.message.info { background: #1a3a4a; color: #88ddff; display: block; }

input.user-input {
  width: 100%;
  padding: 12px;
  background: #1a1a1a;
  border: 1px solid #555;
  color: #00ff88;
  font-family: 'Courier New', monospace;
  font-size: 24px;
  text-align: center;
  border-radius: 4px;
  margin-bottom: 10px;
  letter-spacing: 4px;
}
input.user-input:focus { outline: none; border-color: #00d4ff; }

/* Device multi-select panel */
.device-panel {
  background: #0f1729;
  border: 1px solid #2a3a5a;
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 15px;
}
.device-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #2a3a5a;
}
.device-panel-header h2 {
  color: #00d4ff;
  font-size: 15px;
  margin: 0;
}
.device-summary {
  font-size: 12px;
  color: #888;
}
.device-summary .ok { color: #5fff7f; font-weight: bold; }
.device-summary .bad { color: #ff8888; font-weight: bold; }
.device-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
  max-height: 260px;
  overflow-y: auto;
  padding-right: 4px;
}
.device-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
  position: relative;
}
.device-item:hover { background: #2a2a2a; border-color: #555; }
.device-item.selected {
  background: #1a3a5a;
  border-color: #00d4ff;
  box-shadow: 0 0 6px rgba(0,212,255,0.3);
}
.device-item.disabled {
  opacity: 0.45;
  cursor: not-allowed;
  background: #0a0a0a;
}
.device-item.disabled:hover { background: #0a0a0a; border-color: #333; }
.device-item input[type="checkbox"] {
  margin: 0;
  cursor: pointer;
}
.device-led {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #555;
  flex-shrink: 0;
  box-shadow: 0 0 0 transparent;
  transition: all 0.2s;
}
.device-led.online {
  background: #00ff00;
  box-shadow: 0 0 6px #00ff00;
  animation: pulse-led 2s infinite;
}
.device-led.offline {
  background: #ff4444;
  box-shadow: 0 0 4px #ff4444;
}
.device-led.checking {
  background: #ffd700;
  animation: pulse-led 1s infinite;
}
@keyframes pulse-led {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.device-text {
  flex: 1;
  min-width: 0;
}
.device-ip {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: #00d4ff;
  font-weight: bold;
}
.device-note {
  font-size: 11px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.device-item.selected .device-ip { color: #fff; }
.device-item.offline-line .device-ip { color: #888; }
.device-actions {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #2a3a5a;
  font-size: 12px;
}
.device-actions a {
  color: #00d4ff;
  cursor: pointer;
  text-decoration: underline;
}
.device-actions a:hover { color: #5fff7f; }
</style>
</head>
<body>
<div class="container">
  <h1>🖥 X628 PRO Simulator <span style="font-size:13px;color:#888">(multi-device v1.5.0)</span></h1>
  <div class="subtitle">Mô phỏng máy chấm công - chọn 1 hoặc nhiều máy để chấm</div>
  <div id="connBadge" class="conn-badge offline">
    <span class="dot"></span>
    <span id="connText">Đang tải danh sách máy...</span>
  </div>

  <div class="row">
    <div class="col">
      <div class="machine">
        <div class="machine-screen" id="screen">
          <div class="time" id="screenTime">--:--:--</div>
          <div class="user" id="screenUser">---</div>
          <div class="status" id="screenStatus">San sang</div>
          <div class="success-line" id="screenSuccess" style="display:none">✓ THÀNH CÔNG</div>
        </div>
        <div class="machine-fp" id="fpIndicator"></div>
        <input type="text" id="userIdInput" class="user-input" maxlength="10" placeholder="Mã NV" autocomplete="off">
        <input type="text" id="passInput" class="user-input" maxlength="8" placeholder="Pass (mặc định 1)" autocomplete="off" style="font-size:14px;padding:8px;margin-top:4px">
        <div class="keypad">
          <div class="key" onclick="pressKey('1')">1</div>
          <div class="key" onclick="pressKey('2')">2</div>
          <div class="key" onclick="pressKey('3')">3</div>
          <div class="key" onclick="pressKey('4')">4</div>
          <div class="key" onclick="pressKey('5')">5</div>
          <div class="key" onclick="pressKey('6')">6</div>
          <div class="key" onclick="pressKey('7')">7</div>
          <div class="key" onclick="pressKey('8')">8</div>
          <div class="key" onclick="pressKey('9')">9</div>
          <div class="key clear" onclick="pressKey('C')">CLR</div>
          <div class="key" onclick="pressKey('0')">0</div>
          <div class="key action" onclick="pressKey('OK')">OK</div>
        </div>
        <div class="status-bar">
          <div class="led green" id="ledPower"></div>
          <span>Power</span>
          <div class="led yellow" id="ledStatus"></div>
          <span id="statusText">Ready</span>
        </div>
      </div>
    </div>

    <div class="col">
      <div class="panel">
        <h2>⚙ Thao tác & Phương thức</h2>
        <div><strong>Chọn thao tác:</strong></div>
        <div class="action-grid">
          <div class="action-btn" data-status="0" onclick="selectAction(0)">Check-In (Vào ca)</div>
          <div class="action-btn" data-status="1" onclick="selectAction(1)">Check-Out (Tan ca)</div>
          <div class="action-btn" data-status="2" onclick="selectAction(2)">Break-Out (Ra ngoài)</div>
          <div class="action-btn" data-status="3" onclick="selectAction(3)">Break-In (Vào lại)</div>
          <div class="action-btn" data-status="4" onclick="selectAction(4)">OT-In (Vào OT)</div>
          <div class="action-btn" data-status="5" onclick="selectAction(5)">OT-Out (Tan OT)</div>
        </div>
        <div style="margin-top:15px"><strong>Phương thức:</strong></div>
        <div class="method-grid">
          <div class="method-btn" data-punch="0" onclick="selectPunch(0)">🖐 Vân tay</div>
          <div class="method-btn" data-punch="1" onclick="selectPunch(1)">💳 Thẻ</div>
          <div class="method-btn" data-punch="2" onclick="selectPunch(2)">🔢 Mã số</div>
        </div>
        <button class="submit-btn" id="submitBtn" onclick="submitPunch()">CHẤM CÔNG</button>
        <div class="message" id="message"></div>
      </div>
    </div>

    <div class="col">
      <div class="panel">
        <h2>📋 Lịch sử chấm công (local)</h2>
        <div class="history" id="history">
          <div style="color:#888;text-align:center;padding:20px">Chưa có lượt chấm nào</div>
        </div>
      </div>
    </div>
  </div>

  <div class="device-panel">
    <div class="device-panel-header">
      <h2>🖧 Chọn máy chấm công <span style="font-size:11px;color:#888">(có thể chọn nhiều)</span></h2>
      <div class="device-summary" id="deviceSummary">Đang tải...</div>
    </div>
    <div class="device-list" id="deviceList">
      <div style="color:#888;text-align:center;padding:20px;grid-column:1/-1">Đang tải danh sách máy...</div>
    </div>
    <div class="device-actions">
      <a onclick="selectAllDevices()">✓ Chọn tất cả</a>
      <a onclick="selectNoneDevices()">✗ Bỏ chọn</a>
      <a onclick="selectOnlyOnline()">🟢 Chỉ chọn online</a>
      <a onclick="refreshDevices()">🔄 Refresh</a>
      <span style="margin-left:auto;color:#666">Auto-refresh mỗi 10s</span>
    </div>
  </div>

  <div class="panel">
    <h2>ℹ Thông tin</h2>
    <div id="deviceInfo" style="font-size:13px;line-height:1.8">
      Đang kết nối...
    </div>
    <div style="margin-top:10px;font-size:12px;color:#888">
      ⚠ <strong>Lưu ý:</strong> Máy ZKTeco <strong>KHÔNG hỗ trợ</strong> ghi log chấm công từ xa qua giao thức ZK chuẩn.
      Tool này sẽ cố gắng ghi vào máy thật (qua lệnh nội bộ CMD_REG_EVENT), đồng thời <strong>luôn lưu local</strong> vào file
      <code>manual_punches.csv</code>. Khi máy thật ghi nhận, có thể merge với log thiết bị để đối chiếu.
    </div>
  </div>
</div>

<script>
let selectedStatus = 0;
let selectedPunch = 0;
let isSubmitting = false;
let allDevices = [];
let selectedDeviceIps = new Set();

// Update clock
function updateClock() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  const mo = String(now.getMonth() + 1).padStart(2, '0');
  const yy = now.getFullYear();
  document.getElementById('screenTime').textContent = `${yy}-${mo}-${dd} ${hh}:${mm}:${ss}`;
}
setInterval(updateClock, 1000);
updateClock();

async function loadDevices() {
  try {
    const resp = await fetch('/api/devices');
    const data = await resp.json();
    allDevices = data.devices || [];
    renderDeviceList();
    updateDeviceSummary(data);
  } catch (e) {
    document.getElementById('deviceList').innerHTML = '<div style="color:#ff8888;padding:20px;grid-column:1/-1">Lỗi tải danh sách máy: ' + e.message + '</div>';
  }
}

function renderDeviceList() {
  const list = document.getElementById('deviceList');
  if (allDevices.length === 0) {
    list.innerHTML = '<div style="color:#888;padding:20px;grid-column:1/-1">Không có máy nào trong devices.csv</div>';
    return;
  }
  // Auto-select devices that have selected=1 in CSV on first load
  if (selectedDeviceIps.size === 0) {
    for (const d of allDevices) {
      if (d.selected) selectedDeviceIps.add(d.ip);
    }
  }
  list.innerHTML = allDevices.map(d => {
    const isSel = selectedDeviceIps.has(d.ip);
    const ledClass = d.online ? 'online' : 'offline';
    const note = d.note || d.model || '';
    const offlineCls = d.online ? '' : 'offline-line';
    const checked = isSel ? 'checked' : '';
    return `<div class="device-item ${isSel ? 'selected' : ''} ${offlineCls}" onclick="toggleDevice('${d.ip}')">
      <input type="checkbox" ${checked} onclick="event.stopPropagation(); toggleDevice('${d.ip}')">
      <span class="device-led ${ledClass}" title="${d.online ? 'Online: ' + d.model : 'Offline: ' + d.message}"></span>
      <div class="device-text">
        <div class="device-ip">${d.ip}</div>
        <div class="device-note" title="${note}">${note}</div>
      </div>
    </div>`;
  }).join('');
}

function updateDeviceSummary(data) {
  const el = document.getElementById('deviceSummary');
  const badge = document.getElementById('connBadge');
  const connText = document.getElementById('connText');
  const total = data.total || 0;
  const online = data.online || 0;
  const offline = data.offline || 0;
  const selected = selectedDeviceIps.size;
  el.innerHTML = `<span class="ok">${online} online</span> / <span class="bad">${offline} offline</span> &middot; đã chọn <strong style="color:#00d4ff">${selected}</strong>/${total}`;
  if (selected > 0 && online > 0) {
    const selIps = Array.from(selectedDeviceIps).join(', ');
    badge.className = 'conn-badge online';
    connText.textContent = '✓ Sẵn sàng ghi vào ' + selected + ' máy: ' + selIps;
  } else if (selected > 0) {
    badge.className = 'conn-badge offline';
    connText.textContent = '⚠ ' + selected + ' máy được chọn nhưng tất cả offline - sẽ chỉ lưu local';
  } else {
    badge.className = 'conn-badge offline';
    connText.textContent = '⚠ Chưa chọn máy nào';
  }
}

function toggleDevice(ip) {
  if (selectedDeviceIps.has(ip)) selectedDeviceIps.delete(ip);
  else selectedDeviceIps.add(ip);
  renderDeviceList();
  updateDeviceSummary({total: allDevices.length, online: allDevices.filter(d => d.online).length, offline: allDevices.filter(d => !d.online).length});
}

function selectAllDevices() {
  selectedDeviceIps = new Set(allDevices.map(d => d.ip));
  renderDeviceList();
  updateDeviceSummary({total: allDevices.length, online: allDevices.filter(d => d.online).length, offline: allDevices.filter(d => !d.online).length});
}

function selectNoneDevices() {
  selectedDeviceIps.clear();
  renderDeviceList();
  updateDeviceSummary({total: allDevices.length, online: allDevices.filter(d => d.online).length, offline: allDevices.filter(d => !d.online).length});
}

function selectOnlyOnline() {
  selectedDeviceIps = new Set(allDevices.filter(d => d.online).map(d => d.ip));
  renderDeviceList();
  updateDeviceSummary({total: allDevices.length, online: allDevices.filter(d => d.online).length, offline: allDevices.filter(d => !d.online).length});
}

async function refreshDevices() {
  const btn = document.querySelector('.device-actions a[onclick="refreshDevices()"]');
  if (btn) { btn.textContent = '⏳ Đang ping...'; btn.style.pointerEvents = 'none'; }
  try {
    await fetch('/api/devices/refresh', {method: 'POST'});
    // Wait briefly for pinger thread to update, then reload
    await new Promise(r => setTimeout(r, 2000));
    await loadDevices();
  } finally {
    if (btn) { btn.textContent = '🔄 Refresh'; btn.style.pointerEvents = 'auto'; }
  }
}

function pressKey(k) {
  if (isSubmitting) return;
  // When userId is empty, fill Mã NV; when filled, fill Pass
  const userInput = document.getElementById('userIdInput');
  const passInput = document.getElementById('passInput');
  if (k === 'C') {
    if (passInput.value) passInput.value = '';
    else userInput.value = '';
  } else if (k === 'OK') {
    submitPunch();
  } else {
    if (userInput.value === '') {
      // Fill Mã NV
      if (userInput.value.length < 10) userInput.value += k;
    } else if (passInput.value === '') {
      // Fill Pass
      if (passInput.value.length < 8) passInput.value += k;
    } else {
      // Both filled - ignore
    }
  }
  // Update screen
  const u = userInput.value || '---';
  const p = passInput.value ? ' / pass: ' + passInput.value : '';
  document.getElementById('screenUser').textContent = u + p;
  flashScreen();
}

function selectAction(s) {
  selectedStatus = s;
  document.querySelectorAll('.action-btn').forEach(b => b.classList.remove('selected'));
  document.querySelector('.action-btn[data-status="' + s + '"]').classList.add('selected');
  const names = {0:'Check-In',1:'Check-Out',2:'Break-Out',3:'Break-In',4:'OT-In',5:'OT-Out'};
  document.getElementById('screenStatus').textContent = names[s];
}

function selectPunch(p) {
  selectedPunch = p;
  document.querySelectorAll('.method-btn').forEach(b => b.classList.remove('selected'));
  document.querySelector('.method-btn[data-punch="' + p + '"]').classList.add('selected');
}

function flashScreen() {
  const screen = document.getElementById('screen');
  screen.classList.add('flash');
  setTimeout(() => screen.classList.remove('flash'), 200);
}

function showMessage(text, type, duration) {
  const msg = document.getElementById('message');
  msg.className = 'message ' + type;
  msg.style.whiteSpace = 'pre-line';
  msg.textContent = text;
  const dur = duration || 5000;
  setTimeout(() => { msg.className = 'message'; msg.style.whiteSpace = ''; }, dur);
}

async function submitPunch() {
  if (isSubmitting) return;
  const userId = document.getElementById('userIdInput').value.trim();
  const passVal = document.getElementById('passInput').value.trim();
  if (!userId) {
    showMessage('Vui lòng nhập mã nhân viên', 'error');
    return;
  }
  if (selectedDeviceIps.size === 0) {
    showMessage('Vui lòng chọn ít nhất 1 máy chấm công ở panel "Chọn máy"', 'error');
    return;
  }
  isSubmitting = true;
  const btn = document.getElementById('submitBtn');
  btn.disabled = true;
  btn.textContent = 'Đang ghi...';

  // FP animation
  document.getElementById('fpIndicator').classList.add('active');

  try {
    const payload = {
      userId: userId,
      status: selectedStatus,
      punch: selectedPunch,
      device_ips: Array.from(selectedDeviceIps)
    };
    if (passVal) payload.pass = passVal;
    const resp = await fetch('/api/punch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (data.ok) {
      // Show "THANH CONG" line on machine screen
      const successEl = document.getElementById('screenSuccess');
      successEl.style.display = 'block';
      const nWritten = data.n_written || 0;
      const nTotal = data.n_devices || 0;
      successEl.textContent = (nWritten > 0 ? '✓ ' : '⚠ ') + nWritten + '/' + nTotal + ' MÁY';
      const statusNames = {0:'Check-In',1:'Check-Out',2:'Break-Out',3:'Break-In',4:'OT-In',5:'OT-Out'};
      document.getElementById('screenStatus').textContent = statusNames[selectedStatus] + ' OK';

      // Build per-device message
      const statusNames2 = {0:'In',1:'Out',2:'BrkOut',3:'BrkIn',4:'OT-In',5:'OT-Out'};
      let perLine = (data.per_device || []).map(p =>
        p.written ? '✓' : '✗') .join(' ');
      let msg = '✓ ' + data.message;
      if (data.written_to_device) {
        msg += ' (' + nWritten + '/' + nTotal + ' máy ghi nhận)';
      } else {
        msg += ' (Chỉ lưu local - máy không hỗ trợ ghi từ xa)';
      }
      msg += '\n' + perLine + ' ' + (data.per_device || []).map(p => p.ip).join('  ');
      showMessage(msg, data.written_to_device ? 'success' : 'info', 7000);

      await refreshHistory();
      await loadDevices();

      // Reset UI after 2.5 seconds
      setTimeout(() => {
        document.getElementById('userIdInput').value = '';
        document.getElementById('passInput').value = '';
        document.getElementById('screenUser').textContent = '---';
        document.getElementById('screenStatus').textContent = 'San sang';
        document.getElementById('screenSuccess').style.display = 'none';
      }, 2500);
    } else {
      showMessage('✗ Lỗi: ' + (data.error || 'Không rõ'), 'error');
    }
  } catch (e) {
    showMessage('✗ Lỗi kết nối: ' + e.message, 'error');
  } finally {
    isSubmitting = false;
    btn.disabled = false;
    btn.textContent = 'CHẤM CÔNG';
    setTimeout(() => document.getElementById('fpIndicator').classList.remove('active'), 1000);
  }
}

async function deletePunch(punchId, btn) {
  if (!confirm('Xóa bản ghi này khỏi local log?\n(Lưu ý: máy ZK không cho xóa từng bản ghi từ xa)')) return;
  btn.disabled = true;
  btn.textContent = '...';
  try {
    const resp = await fetch('/api/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({punch_id: punchId})
    });
    const data = await resp.json();
    if (data.ok) {
      let note = 'Đã xóa khỏi local log';
      if (data.was_on_device === 'True') {
        note += '\n' + data.device_delete;
      }
      alert(note);
      await refreshHistory();
    } else {
      alert('Lỗi: ' + (data.error || 'Không rõ'));
      btn.disabled = false;
      btn.textContent = '🗑';
    }
  } catch (e) {
    alert('Lỗi kết nối: ' + e.message);
    btn.disabled = false;
    btn.textContent = '🗑';
  }
}

// clearAllHistory removed - only per-row delete is allowed to prevent accidents

async function refreshHistory() {
  try {
    const resp = await fetch('/api/history');
    const data = await resp.json();
    const hist = document.getElementById('history');
    if (!data.history || data.history.length === 0) {
      hist.innerHTML = '<div style="color:#888;text-align:center;padding:20px">Chưa có lượt chấm nào</div>';
      return;
    }
    const reversed = data.history.slice().reverse();
    hist.innerHTML = reversed.map(h => {
      const statusClass = 'status-' + h.status_name.toLowerCase().replace(/[^a-z]/g, '-');
      const wasOnDevice = h.written_to_device === 'True';
      return `<div class="history-item">
        <div>
          <span class="time">${h.timestamp}</span>
          <span class="info">NV ${h.user_id}</span>
        </div>
        <div>
          <span class="status ${statusClass}">${h.status_name}</span>
          <span style="color:#888;margin-left:8px">${h.method_name}</span>
          ${wasOnDevice ? '<span style="color:#5fff7f">✓ máy</span>' : '<span style="color:#888">local</span>'}
          <button class="del-btn" onclick="deletePunch(${h.punch_id}, this)" title="Xóa khỏi local log">🗑</button>
        </div>
      </div>`;
    }).join('');
  } catch (e) {}
}

async function refreshDeviceInfo() {
  try {
    const resp = await fetch('/api/device');
    const data = await resp.json();
    const el = document.getElementById('deviceInfo');
    const badge = document.getElementById('connBadge');
    const connText = document.getElementById('connText');
    if (data.connected) {
      el.innerHTML = `<strong>✓ Đã kết nối ${data.ip}</strong><br>
        Model: <code>${data.model}</code><br>
        Firmware: <code>${data.firmware}</code><br>
        Số user đã đăng ký: <code>${data.users_count}</code><br>
        Số log hiện có: <code>${data.records_count}</code>`;
      badge.className = 'conn-badge online';
      connText.textContent = '✓ Đang kết nối ' + data.ip + ' (' + (data.model || '?') + ')';
    } else {
      el.innerHTML = `<strong>✗ Không kết nối được ${data.ip}</strong><br>
        Lý do: <code>${data.message || 'Không rõ'}</code>`;
      badge.className = 'conn-badge offline';
      connText.textContent = '✗ Mất kết nối ' + data.ip;
    }
  } catch (e) {
    const badge = document.getElementById('connBadge');
    const connText = document.getElementById('connText');
    badge.className = 'conn-badge offline';
    connText.textContent = '✗ Lỗi kết nối server';
  }
}

// Default selection
selectAction(0);
selectPunch(0);
refreshHistory();
loadDevices();
setInterval(loadDevices, 10000);  // Refresh device list + status every 10s
</script>
</body>
</html>'''


class PunchHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress log

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/' or path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif path == '/api/history':
            history_safe = []
            for h in punch_history[-100:]:
                history_safe.append({
                    'punch_id': h.get('punch_id', 0),
                    'timestamp': h.get('timestamp', ''),
                    'user_id': h.get('user_id', ''),
                    'device_ip': h.get('device_ip', ''),
                    'status_name': h.get('status_name', h.get('status', '')),
                    'method_name': h.get('method_name', h.get('punch', '')),
                    'written_to_device': h.get('written_to_device', 'False'),
                })
            self.send_json({'history': history_safe})
        elif path == '/api/device':
            self.send_json(device_status)
        elif path == '/api/devices':
            # List all devices + their live status
            with devices_lock:
                out = []
                online_count = 0
                for d in devices:
                    ip = d['ip']
                    st = device_statuses.get(ip, {
                        'connected': False, 'message': 'Chua kiem tra', 'last_check': None,
                        'model': '?', 'firmware': '?', 'users_count': 0, 'records_count': 0
                    })
                    if st.get('connected'):
                        online_count += 1
                    out.append({
                        'ip': ip,
                        'type': d.get('type', 'attendance'),
                        'note': d.get('note', ''),
                        'selected': d.get('selected', False),
                        'online': st.get('connected', False),
                        'model': st.get('model', '?'),
                        'firmware': st.get('firmware', '?'),
                        'users_count': st.get('users_count', 0),
                        'records_count': st.get('records_count', 0),
                        'message': st.get('message', ''),
                        'last_check': st.get('last_check', ''),
                    })
                self.send_json({
                    'devices': out,
                    'total': len(out),
                    'online': online_count,
                    'offline': len(out) - online_count,
                })
        elif path == '/api/devices/refresh':
            # Force re-ping now
            def _refresh():
                for d in devices:
                    if d.get('type') in ('attendance', 'attendance-gateway'):
                        st = ping_device(d['ip'], timeout=3)
                        with devices_lock:
                            device_statuses[d['ip']] = st
            threading.Thread(target=_refresh, daemon=True).start()
            self.send_json({'ok': True, 'message': 'Da yeu cau refresh'})
        elif path == '/api/health':
            # Quick health check: re-verify device connection
            threading.Thread(target=check_device_info, daemon=True).start()
            self.send_json(device_status)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length else b''
        body = None
        for enc in ('utf-8', 'utf-8-sig', 'latin-1'):
            try:
                body = raw.decode(enc)
                break
            except:
                continue
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}

        if path == '/api/punch':
            user_id = data.get('userId', '').strip()
            status = int(data.get('status', 0))
            punch = int(data.get('punch', 0))
            pass_value = data.get('pass', None)  # Optional - for "User ID + Password" mode
            # Accept either device_ips (list) or single device_ip (back-compat)
            device_ips_in = data.get('device_ips', None)
            if not device_ips_in:
                legacy_ip = data.get('device_ip', DEVICE_IP)
                if isinstance(legacy_ip, list):
                    device_ips_in = legacy_ip
                else:
                    device_ips_in = [legacy_ip]
            if not isinstance(device_ips_in, list):
                device_ips_in = [str(device_ips_in)]
            device_ips_in = [str(x).strip() for x in device_ips_in if str(x).strip()]
            if not device_ips_in:
                self.send_json({'ok': False, 'error': 'Chua chon may cham cong'}, status=400)
                return
            # Dedupe but keep order
            seen = set()
            device_ips = []
            for x in device_ips_in:
                if x not in seen:
                    seen.add(x)
                    device_ips.append(x)
            if not user_id:
                self.send_json({'ok': False, 'error': 'Thieu ma NV'}, status=400)
                return

            now = datetime.now()
            timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
            status_name = get_status_name(status)
            method_name = get_punch_name(punch)

            # Multi-device write: try each IP, record each separately
            per_device = []
            any_written = False
            with punch_lock:
                for ip in device_ips:
                    written, device_msg = try_write_to_device(ip, user_id, status, punch, now, pass_value)
                    if written:
                        any_written = True
                    punch_id = next_punch_id[0]
                    next_punch_id[0] += 1
                    entry = {
                        'punch_id': punch_id,
                        'timestamp': timestamp_str,
                        'device_ip': ip,
                        'user_id': user_id,
                        'user_name': 'NV ' + user_id,
                        'status': str(status),
                        'punch': str(punch),
                        'status_name': status_name,
                        'method_name': method_name,
                        'written_to_device': str(written),
                        'note': device_msg[:100],
                    }
                    punch_history.append(entry)
                    if len(punch_history) > 1000:
                        punch_history.pop(0)
                    save_shadow_log_entry(entry)
                    per_device.append({
                        'ip': ip,
                        'written': written,
                        'message': device_msg[:120],
                    })
                device_status['last_attempt'] = timestamp_str
                device_status['message'] = ('OK on ' if any_written else 'Local only on ') + ','.join(device_ips)

            n_ok = sum(1 for x in per_device if x['written'])
            n_total = len(per_device)
            self.send_json({
                'ok': True,
                'message': 'Da ghi vao ' + str(n_total) + ' may (' + str(n_ok) + ' thanh cong)',
                'written_to_device': any_written,
                'n_devices': n_total,
                'n_written': n_ok,
                'per_device': per_device,
            })
            return
        elif path == '/api/delete':
            punch_id = data.get('punch_id')
            if punch_id is None:
                self.send_json({'ok': False, 'error': 'Thieu punch_id'}, status=400)
                return
            try:
                punch_id = int(punch_id)
            except:
                self.send_json({'ok': False, 'error': 'punch_id khong hop le'}, status=400)
                return

            # Find entry
            target_entry = None
            target_idx = -1
            with punch_lock:
                for i, h in enumerate(punch_history):
                    if h.get('punch_id') == punch_id:
                        target_entry = h
                        target_idx = i
                        break
                if target_entry is None:
                    self.send_json({'ok': False, 'error': 'Khong tim thay ban ghi'}, status=404)
                    return

                # Try to delete from device (best-effort, will likely fail for ZK)
                device_msg = ''
                if target_entry.get('written_to_device') == 'True':
                    dev_ok, dev_msg = try_delete_from_device(
                        target_entry.get('device_ip', DEVICE_IP),
                        target_entry.get('user_id', ''),
                        target_entry.get('timestamp', '')
                    )
                    device_msg = dev_msg
                else:
                    device_msg = 'Ban ghi chi o local, khong can xoa tren may.'

                # Remove from in-memory list
                punch_history.pop(target_idx)

                # Rewrite CSV
                ok, csv_msg = rewrite_shadow_log()

                self.send_json({
                    'ok': True,
                    'message': 'Da xoa ban ghi khoi local log',
                    'device_delete': device_msg,
                    'csv_rewrite': csv_msg,
                    'was_on_device': target_entry.get('written_to_device', 'False'),
                })
            return
        elif path == '/api/clear_all':
            # Disabled - per user request, only individual delete is allowed
            self.send_json({'ok': False, 'error': 'Xoa het da bi tat. Chi ho tro xoa tung ban ghi.'}, status=403)
            return
        else:
            self.send_json({'ok': False, 'error': 'Unknown API'}, status=404)

    def send_json(self, obj, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode('utf-8'))


def check_device_info():
    """Try to get device info on startup"""
    try:
        zk = ZK(DEVICE_IP, port=4370, timeout=8, ommit_ping=True, verbose=False)
        if zk.connect():
            try:
                fw = zk.get_firmware_version()
                name = zk.get_device_name()
                users = zk.get_users()
                zk.read_sizes()
                records = zk.records
                device_status.update({
                    'connected': True,
                    'ip': DEVICE_IP,
                    'model': name,
                    'firmware': fw,
                    'users_count': len(users),
                    'records_count': records,
                    'message': 'OK',
                })
            except Exception as e:
                # v1.5.7: FIX - inner exception should set connected=False (was True before, BUG)
                device_status.update({'connected': False, 'message': 'Lỗi đọc thông tin: ' + str(e)[:50]})
            finally:
                try: zk.disconnect()
                except: pass
        else:
            device_status.update({'connected': False, 'message': 'Connect failed'})
    except Exception as e:
        device_status.update({'connected': False, 'message': str(e)[:80]})


def main():
    load_shadow_log()
    load_devices()
    print('=' * 60, flush=True)
    print('  X628 PRO Punch Simulator (v1.5.0 multi-device)', flush=True)
    print('  Mo phong may cham cong ZKTeco X628 PRO', flush=True)
    print('=' * 60, flush=True)
    print('Devices loaded: ' + str(len(devices)) + ' (from devices.csv)', flush=True)
    print('Shadow log:     ' + SHADOW_LOG_FILE, flush=True)
    print('HTTP server:    http://localhost:' + str(HTTP_PORT), flush=True)
    print('=' * 60, flush=True)

    # Start background pinger (polls every 20s)
    pinger = threading.Thread(target=device_pinger_loop, daemon=True)
    pinger.start()
    print('[*] Background pinger started (every 20s)', flush=True)

    # Quick first ping so UI shows status immediately
    def _first_ping():
        for d in devices:
            if d.get('type') in ('attendance', 'attendance-gateway'):
                st = ping_device(d['ip'], timeout=3)
                with devices_lock:
                    device_statuses[d['ip']] = st
    threading.Thread(target=_first_ping, daemon=True).start()

    # Check primary device on startup (backward compat)
    print('\n[*] Checking primary device ' + DEVICE_IP + '...', flush=True)
    check_device_info()
    if device_status.get('connected'):
        print('[+] Connected: ' + str(device_status.get('model')) +
              ' (FW: ' + str(device_status.get('firmware')) + ')', flush=True)
        print('    Users: ' + str(device_status.get('users_count')) +
              ', Records: ' + str(device_status.get('records_count')), flush=True)
    else:
        print('[!] Cannot connect: ' + str(device_status.get('message')), flush=True)

    print('\n[*] Opening browser at http://localhost:' + str(HTTP_PORT), flush=True)
    print('    Bam Ctrl+C de dung', flush=True)

    server = HTTPServer(('0.0.0.0', HTTP_PORT), PunchHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[*] Stopped by user', flush=True)
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
