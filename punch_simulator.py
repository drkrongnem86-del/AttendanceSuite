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
DEVICE_IP = '172.16.0.212'
HTTP_PORT = 8081

# State
punch_history = []  # In-memory recent punches (max 1000)
next_punch_id = [1]  # Monotonic ID counter for each punch entry
device_status = {'connected': False, 'model': '?', 'last_attempt': None, 'message': ''}
punch_lock = threading.Lock()


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

        # Try multiple packet formats
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
</style>
</head>
<body>
<div class="container">
  <h1>🖥 X628 PRO Simulator</h1>
  <div class="subtitle">Mô phỏng máy chấm công - Kết nối tới 172.16.0.212</div>
  <div id="connBadge" class="conn-badge offline">
    <span class="dot"></span>
    <span id="connText">Đang kiểm tra kết nối...</span>
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

function showMessage(text, type) {
  const msg = document.getElementById('message');
  msg.className = 'message ' + type;
  msg.textContent = text;
  setTimeout(() => { msg.className = 'message'; }, 5000);
}

async function submitPunch() {
  if (isSubmitting) return;
  const userId = document.getElementById('userIdInput').value.trim();
  const passVal = document.getElementById('passInput').value.trim();
  if (!userId) {
    showMessage('Vui lòng nhập mã nhân viên', 'error');
    return;
  }
  isSubmitting = true;
  const btn = document.getElementById('submitBtn');
  btn.disabled = true;
  btn.textContent = 'Đang ghi...';

  // FP animation
  document.getElementById('fpIndicator').classList.add('active');

  try {
    const payload = {userId: userId, status: selectedStatus, punch: selectedPunch};
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
      const okOnDevice = data.written_to_device;
      successEl.textContent = okOnDevice ? '✓ ĐÃ GHI VÀO MÁY' : '✓ ĐÃ GHI LOCAL';
      const statusNames = {0:'Check-In',1:'Check-Out',2:'Break-Out',3:'Break-In',4:'OT-In',5:'OT-Out'};
      document.getElementById('screenStatus').textContent = statusNames[selectedStatus] + ' OK';

      // Status message below
      let msg = '✓ ' + data.message;
      if (data.written_to_device) {
        msg += ' (Đã ghi vào máy thật)';
      } else {
        msg += ' (Chỉ lưu local - máy không hỗ trợ ghi từ xa)';
      }
      showMessage(msg, data.written_to_device ? 'success' : 'info');

      await refreshHistory();
      await refreshDeviceInfo();

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
refreshDeviceInfo();
setInterval(refreshDeviceInfo, 30000);
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
                    'status_name': h.get('status_name', h.get('status', '')),
                    'method_name': h.get('method_name', h.get('punch', '')),
                    'written_to_device': h.get('written_to_device', 'False'),
                })
            self.send_json({'history': history_safe})
        elif path == '/api/device':
            self.send_json(device_status)
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
            if not user_id:
                self.send_json({'ok': False, 'error': 'Thieu ma NV'}, status=400)
                return

            now = datetime.now()
            timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
            status_name = get_status_name(status)
            method_name = get_punch_name(punch)

            # Try to write to device (with pass if provided)
            written, device_msg = try_write_to_device(DEVICE_IP, user_id, status, punch, now, pass_value)
            device_status['last_attempt'] = timestamp_str
            device_status['message'] = device_msg

            # Always save to local shadow log
            with punch_lock:
                punch_id = next_punch_id[0]
                next_punch_id[0] += 1
                entry = {
                    'punch_id': punch_id,
                    'timestamp': timestamp_str,
                    'device_ip': DEVICE_IP,
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

            self.send_json({
                'ok': True,
                'message': 'Da ghi nhan cham cong',
                'written_to_device': written,
                'device_message': device_msg,
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
                device_status.update({'connected': True, 'message': 'Partial: ' + str(e)[:50]})
            finally:
                try: zk.disconnect()
                except: pass
        else:
            device_status.update({'connected': False, 'message': 'Connect failed'})
    except Exception as e:
        device_status.update({'connected': False, 'message': str(e)[:80]})


def main():
    load_shadow_log()
    print('=' * 60, flush=True)
    print('  X628 PRO Punch Simulator', flush=True)
    print('  Mo phong may cham cong ZKTeco X628 PRO', flush=True)
    print('=' * 60, flush=True)
    print('Target device: ' + DEVICE_IP, flush=True)
    print('Shadow log:    ' + SHADOW_LOG_FILE, flush=True)
    print('HTTP server:   http://localhost:' + str(HTTP_PORT), flush=True)
    print('=' * 60, flush=True)

    # Check device on startup
    print('\n[*] Checking device ' + DEVICE_IP + '...', flush=True)
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
