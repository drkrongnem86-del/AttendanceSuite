"""
security_routes.py - Security & PIN+Password routes cho AttendanceSuite
Tích hợp vào attendance_web.py thông qua import

Features:
  - /security page - Security dashboard
  - /api/security/scan - Auto-scan 24 máy
  - /api/security/devices - Device status với risk
  - /api/security/device/<ip>/users - List users có password
  - /api/security/device/<ip>/verify - Verify PIN+password
  - /api/security/quick-pin-test - Quick test 1 user
  - /punch page - Manual punch UI
  - /api/punch/manual - Manual punch (verify PIN+password)
  - /api/punch/log - Manual punches log
"""
import os
import csv
import socket
import json
import time
import urllib.request
import http.cookiejar
import sqlite3
import io
import gzip
from datetime import datetime
from http.server import BaseHTTPRequestHandler

DEVICES_FILE = os.path.join(os.path.dirname(__file__), 'devices.csv')
MANUAL_PUNCHES_CSV = os.path.join(os.path.dirname(__file__), 'manual_punches.csv')


def _read_devices():
    devices = []
    try:
        with open(DEVICES_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) >= 4 and row[1] == 'attendance' and not row[0].startswith('virtual'):
                    devices.append({
                        'ip': row[0],
                        'note': row[2],
                        'selected': row[3] == '1',
                    })
    except Exception:
        pass
    return devices


def _scan_port(host, port, timeout=1.5):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        r = s.connect_ex((host, port))
        s.close()
        return r == 0
    except:
        return False


def _download_zkdb(host):
    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        opener.open(f"http://{host}/", timeout=2).read()
        resp = opener.open(f"http://{host}/form/DataApp?style=0", timeout=10)
        data = resp.read()
        if len(data) < 1000:
            return None
        gzip_off = data.find(b'\x1f\x8b\x08', 100)
        if gzip_off < 0:
            return None
        with gzip.GzipFile(fileobj=io.BytesIO(data[gzip_off:])) as gz:
            zkdb = gz.read()
        if zkdb[:8] == b'ZKDB.db\x00':
            zkdb = zkdb[512:]
        return zkdb
    except:
        return None


def _analyze_zkdb(zkdb_data):
    try:
        tmp = os.path.join(os.path.dirname(__file__), '..', 'zk_data_extracted', 'scan_temp.db')
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        with open(tmp, 'wb') as f:
            f.write(zkdb_data)
        conn = sqlite3.connect(tmp)
        conn.text_factory = lambda b: b.decode('cp1252', errors='replace') if isinstance(b, bytes) else b
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM USER_INFO')
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM USER_INFO WHERE Password IS NOT NULL AND Password != ''")
        pwd = cur.fetchone()[0]
        cur.execute('SELECT Verify_Type, COUNT(*) FROM ATT_LOG GROUP BY Verify_Type')
        vt = {v: c for v, c in cur.fetchall()}
        conn.close()
        os.unlink(tmp)
        return {'total_users': total, 'users_with_pwd': pwd, 'verify_types': vt}
    except:
        return None


def _pyzk_connect(ip, comm_key=0, timeout=3):
    from zk import ZK
    zk = ZK(ip, port=4370, timeout=timeout, password=comm_key)
    return zk.connect()


def attach_security_routes(handler_class):
    """Patch handler_class để thêm security/punch routes"""

    # === API: /api/security/scan ===
    def _handle_security_scan(self):
        devices = _read_devices()
        results = []
        for dev in devices:
            ip = dev['ip']
            r = {
                'ip': ip,
                'note': dev['note'],
                'port_4370': _scan_port(ip, 4370),
                'port_23_telnet': _scan_port(ip, 23),
                'port_80_http': _scan_port(ip, 80),
                'comm_key_default': False,
                'fw_version': None,
                'total_users': None,
                'users_with_pwd': None,
                'can_pin_pwd': False,
                'error': None,
            }
            if r['port_4370']:
                try:
                    conn = _pyzk_connect(ip, timeout=3)
                    r['comm_key_default'] = True
                    r['fw_version'] = conn.get_firmware_version()
                    users = conn.get_users()
                    r['total_users'] = len(users)
                    r['users_with_pwd'] = sum(1 for u in users if u.password and u.password != '')
                    r['can_pin_pwd'] = r['users_with_pwd'] > 0
                    conn.disconnect()
                except Exception as e:
                    r['error'] = str(e)[:100]
            results.append(r)
        self.send_json({'devices': results, 'timestamp': datetime.now().isoformat()})

    # === Page: /security ===
    def _handle_security_page(self):
        page = '''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>Security Dashboard - AttendanceSuite</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f5f7fa; color: #222; padding: 20px; }
.container { max-width: 1400px; margin: 0 auto; }
.header { background: linear-gradient(135deg, #d32f2f, #b71c1c); color: white; padding: 24px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(211,47,55,0.3); }
.header h1 { font-size: 28px; margin-bottom: 8px; }
.header p { opacity: 0.9; font-size: 14px; }
.btn { background: white; color: #d32f2f; padding: 10px 20px; border-radius: 6px; border: none; cursor: pointer; font-weight: 600; margin-right: 8px; }
.btn:hover { background: #ffe; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
.stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 4px solid #d32f2f; }
.stat-card .value { font-size: 32px; font-weight: 700; color: #d32f2f; }
.stat-card .label { font-size: 13px; color: #666; margin-top: 4px; }
.stat-card.warn { border-left-color: #ff9800; }
.stat-card.warn .value { color: #ff9800; }
.stat-card.ok { border-left-color: #10b981; }
.stat-card.ok .value { color: #10b981; }
table { width: 100%; background: white; border-collapse: collapse; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-radius: 8px; overflow: hidden; }
th { background: #f8f9fa; padding: 12px; text-align: left; font-weight: 600; color: #555; font-size: 13px; }
td { padding: 12px; border-top: 1px solid #eee; font-size: 14px; }
tr:hover { background: #f8f9fa; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.badge-danger { background: #fee; color: #c62828; }
.badge-warn { background: #fff3cd; color: #e65100; }
.badge-ok { background: #e8f5e9; color: #2e7d32; }
.badge-off { background: #f5f5f5; color: #757575; }
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>🔒 Security Dashboard</h1>
<p>Auto-scan 24 máy ZK - phát hiện Comm Key default, Telnet open, NV có password</p>
</div>

<button class="btn" onclick="loadScan()">🔄 Refresh Scan</button>
<a href="/" class="btn" style="background:#d32f2f;color:white;text-decoration:none;">← Về trang chính</a>
<a href="/punch" class="btn" style="background:#10b981;color:white;text-decoration:none;">📱 Chấm công thủ công</a>

<div id="stats" class="stats" style="margin-top: 20px;">
<div class="stat-card"><div class="value">-</div><div class="label">Đang quét...</div></div>
</div>

<table id="device-table" style="margin-top: 20px;">
<thead>
<tr><th>IP</th><th>Note</th><th>FW</th><th>Users</th><th>w/PWD</th><th>PIN+PWD?</th><th>Comm Key</th><th>Telnet</th><th>HTTP</th></tr>
</thead>
<tbody><tr><td colspan="9" style="text-align:center; padding: 40px;">Đang quét...</td></tr></tbody>
</table>

<div style="margin-top: 20px; padding: 16px; background: #fff3cd; border-left: 4px solid #ff9800; border-radius: 4px;">
<h3>⚠️ Khuyến nghị khẩn cấp</h3>
<ol style="margin-left: 20px; margin-top: 8px;">
<li><strong>Đổi Comm Key</strong> trên các máy có Comm Key = 0 (vào menu: Comm. → Comm Key)</li>
<li><strong>Tắt Telnet</strong> (Menu → Comm. → Telnet → Disable)</li>
<li><strong>Đổi password NV</strong> từ default ('1', '123', '123456') sang cá nhân</li>
<li><strong>Dùng PIN+password</strong> để chấm công nếu không tiện vân tay/khuôn mặt</li>
</ol>
</div>
</div>

<script>
async function loadScan() {
    const tbody = document.querySelector('#device-table tbody');
    const stats = document.getElementById('stats');
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:40px;">⏳ Đang quét 24 máy...</td></tr>';
    stats.innerHTML = '<div class="stat-card"><div class="value">⏳</div><div class="label">Scanning...</div></div>';
    try {
        const r = await fetch('/api/security/scan');
        const data = await r.json();
        const devs = data.devices || [];
        const total = devs.length;
        const online = devs.filter(d => d.port_4370).length;
        const riskCommKey = devs.filter(d => d.comm_key_default).length;
        const telnetOpen = devs.filter(d => d.port_23_telnet).length;
        const pinPwd = devs.filter(d => d.can_pin_pwd).length;

        stats.innerHTML = `
            <div class="stat-card"><div class="value">${total}</div><div class="label">Tổng số máy</div></div>
            <div class="stat-card ${online === total ? 'ok' : 'warn'}"><div class="value">${online}</div><div class="label">Online</div></div>
            <div class="stat-card warn"><div class="value">${riskCommKey}</div><div class="label">⚠️ Comm Key = 0</div></div>
            <div class="stat-card warn"><div class="value">${telnetOpen}</div><div class="label">⚠️ Telnet OPEN</div></div>
            <div class="stat-card ok"><div class="value">${pinPwd}</div><div class="label">✅ PIN+Password OK</div></div>
        `;

        tbody.innerHTML = devs.map(d => `
            <tr>
                <td><code>${d.ip}</code></td>
                <td>${d.note || '-'}</td>
                <td>${d.fw_version ? d.fw_version.substring(0, 20) : '<span class="badge badge-off">DOWN</span>'}</td>
                <td>${d.total_users || '-'}</td>
                <td>${d.users_with_pwd != null ? d.users_with_pwd : '-'}</td>
                <td>${d.can_pin_pwd ? '<span class="badge badge-ok">CÓ</span>' : '<span class="badge badge-off">-</span>'}</td>
                <td>${d.comm_key_default ? '<span class="badge badge-danger">= 0 RISK</span>' : '<span class="badge badge-ok">OK</span>'}</td>
                <td>${d.port_23_telnet ? '<span class="badge badge-warn">OPEN</span>' : '<span class="badge badge-ok">OFF</span>'}</td>
                <td>${d.port_80_http ? '<span class="badge badge-ok">OK</span>' : '<span class="badge badge-off">OFF</span>'}</td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="9" style="color:red; text-align:center;">Lỗi: ${e}</td></tr>`;
    }
}
loadScan();
setInterval(loadScan, 30000);  // auto refresh 30s
</script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(page.encode('utf-8'))

    # === API: /api/security/device/<ip>/verify ===
    def _handle_security_verify(self, ip, pin, password):
        try:
            conn = _pyzk_connect(ip)
            users = conn.get_users()
            user_dict = {u.user_id: u for u in users}
            if str(pin) not in user_dict:
                conn.disconnect()
                self.send_json({'match': False, 'reason': 'PIN not found'})
                return
            user = user_dict[str(pin)]
            match = user.password == str(password)
            result = {
                'match': match,
                'pin': str(pin),
                'name': user.name,
                'db_password': user.password,
                'input_password': str(password),
                'privilege': user.privilege,
                'can_cham_cong': match,
                'instructions': [
                    '1. Đứng trước máy ZK ' + ip,
                    '2. Nhấn Menu (M)',
                    '3. Verification Mode → Password',
                    '4. Nhập PIN = ' + str(pin) + ' → OK',
                    '5. Nhập Password = ' + str(password) + ' → OK',
                    '6. Máy sẽ ghi ATTLOG với Verify_Type = 0 (Password)',
                ] if match else ['Password KHÔNG khớp - không thể chấm công bằng PIN+password']
            }
            conn.disconnect()
            self.send_json(result)
        except Exception as e:
            self.send_json({'match': False, 'error': str(e)}, status=500)

    # === API: /api/security/device/<ip>/attlog-count ===
    def _handle_attlog_count(self, ip):
        """Đọc ATTLOG count từ ZK device - để BS check trên app xem ATTLOG đã ghi chưa.

        Workflow:
        1. BS verify PIN+password → log vào manual_punches.csv
        2. NV nhập PIN+password trên máy ZK → máy ghi ATTLOG
        3. BS mở app, bấm "Verify ATTLOG" → app đọc count từ ZK
        4. So sánh với count trước đó → biết ATTLOG đã ghi hay chưa

        Dùng `read_sizes()` (1 packet) thay vì `get_attendance()` (download full list - 49K+ records)
        """
        try:
            conn = _pyzk_connect(ip, timeout=10)
            # read_sizes() chỉ cần 1 packet 1024 byte - rất nhanh
            conn.read_sizes()
            count = conn.records
            rec_cap = conn.rec_cap
            users = conn.users
            users_cap = conn.users_cap

            conn.disconnect()
            self.send_json({
                'ok': True,
                'ip': ip,
                'attlog_count': count,
                'attlog_capacity': rec_cap,
                'users_count': users,
                'users_capacity': users_cap,
                'timestamp': datetime.now().isoformat(),
                'note': 'Đếm từ ZK device (read_sizes - nhanh, không download full ATTLOG)',
            })
        except Exception as e:
            self.send_json({'ok': False, 'ip': ip, 'error': str(e)}, status=500)

    # === API: /api/punch/reachable - Quick TCP probe port 4370 for all devices ===
    def _handle_punch_reachable(self):
        """Quick TCP probe port 4370 in parallel - returns reachable devices.
        Dùng để filter dropdown chỉ hiển thị máy reachable từ subnet hiện tại.
        Không gọi pyzk (chỉ socket.connect_ex port 4370 với timeout 1s) -> nhanh (~3s cho 22 máy).
        """
        import concurrent.futures as cf
        devices = _read_devices()

        def _probe(dev):
            ip = dev['ip']
            t0 = time.time()
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.5)
                ok = s.connect_ex((ip, 4370)) == 0
                s.close()
                ms = round((time.time() - t0) * 1000)
                return {**dev, 'reachable': ok, 'ping_ms': ms if ok else None}
            except Exception as e:
                return {**dev, 'reachable': False, 'ping_ms': None, 'error': str(e)[:50]}

        # Parallel probe - 22 devices in ~3s instead of 33s sequential
        with cf.ThreadPoolExecutor(max_workers=22) as ex:
            results = list(ex.map(_probe, devices))

        results.sort(key=lambda r: (not r['reachable'], r['note'] or r['ip']))
        reachable = sum(1 for r in results if r['reachable'])
        self.send_json({
            'ok': True,
            'reachable_count': reachable,
            'total': len(results),
            'devices': results,
            'timestamp': datetime.now().isoformat(),
        })

    # === API: /api/punch/manual ===
    def _handle_punch_manual(self, data):
        ip = data.get('ip', '').strip()
        pin = str(data.get('pin', '')).strip()
        password = str(data.get('password', '')).strip()
        punch_type = data.get('type', 'in')  # 'in' or 'out'

        if not ip or not pin or not password:
            self.send_json({'ok': False, 'error': 'Missing IP/PIN/password'}, status=400)
            return

        try:
            # Verify password via pyzk
            conn = _pyzk_connect(ip, timeout=5)
            users = conn.get_users()
            user_dict = {u.user_id: u for u in users}
            if str(pin) not in user_dict:
                conn.disconnect()
                self.send_json({'ok': False, 'error': f'PIN {pin} không tồn tại trên máy {ip}'}, status=400)
                return
            user = user_dict[str(pin)]
            if user.password != str(password):
                conn.disconnect()
                self.send_json({'ok': False, 'error': f'Password sai. DB: {user.password!r}, Input: {password!r}'}, status=400)
                return

            # Password OK - log to manual_punches.csv
            os.makedirs(os.path.dirname(MANUAL_PUNCHES_CSV), exist_ok=True)
            file_exists = os.path.isfile(MANUAL_PUNCHES_CSV)

            with open(MANUAL_PUNCHES_CSV, 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'device_ip', 'pin', 'name', 'type', 'status'])
                writer.writerow([
                    datetime.now().isoformat(),
                    ip,
                    pin,
                    user.name,
                    punch_type,
                    'verified',
                ])

            # Disconnect pyzk
            conn.disconnect()

            self.send_json({
                'ok': True,
                'verified': True,
                'pin': pin,
                'name': user.name,
                'device_ip': ip,
                'punch_type': punch_type,
                'timestamp': datetime.now().isoformat(),
                'message': f'✅ Đã verify PIN+password thành công! Bây giờ NV đứng trước máy {ip} nhập PIN={pin} + password để chấm công chính thức.',
                'instructions': [
                    f'1. Đứng trước máy ZK {ip}',
                    '2. Nhấn Menu (M)',
                    '3. Verification Mode → Password',
                    f'4. Nhập PIN = {pin} → OK',
                    f'5. Nhập Password = {password} → OK',
                    '6. Máy ghi ATTLOG chính thức',
                ],
            })
        except Exception as e:
            self.send_json({'ok': False, 'error': str(e)}, status=500)

    # === API: /api/punch/log ===
    def _handle_punch_log(self, limit=50):
        """Đọc recent manual punches từ manual_punches.csv - cho BS xem log trên web."""
        try:
            limit = max(1, min(int(limit), 500))
            rows = []
            if os.path.isfile(MANUAL_PUNCHES_CSV):
                with open(MANUAL_PUNCHES_CSV, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    all_rows = list(reader)
                    # Last N rows
                    rows = all_rows[-limit:]
                    rows.reverse()  # newest first
            self.send_json({
                'ok': True,
                'count': len(rows),
                'log': rows,
                'csv_path': MANUAL_PUNCHES_CSV,
                'timestamp': datetime.now().isoformat(),
            })
        except Exception as e:
            self.send_json({'ok': False, 'error': str(e)}, status=500)

    # === Page: /punch ===
    def _handle_punch_page(self):
        devices = _read_devices()
        options = '\n'.join(f'<option value="{d["ip"]}">{d["ip"]} ({d["note"]})</option>' for d in devices)
        page = f'''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>Chấm công thủ công - AttendanceSuite v1.8</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f5f7fa; color: #222; padding: 20px; }}
.container {{ max-width: 900px; margin: 0 auto; }}
.card {{ background: white; padding: 24px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); margin-bottom: 20px; }}
h1 {{ color: #00695c; margin-bottom: 12px; font-size: 24px; }}
h2 {{ color: #00695c; margin-bottom: 12px; font-size: 18px; }}
.nav {{ background: white; padding: 12px 20px; border-radius: 8px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
.nav a {{ color: #00695c; text-decoration: none; margin-right: 16px; font-weight: 600; }}
.nav a:hover {{ text-decoration: underline; }}
.nav a.active {{ color: #d32f2f; }}
label {{ display: block; margin-top: 12px; font-weight: 600; color: #555; font-size: 13px; }}
input, select {{ width: 100%; padding: 10px; margin-top: 4px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }}
.btn-row {{ display: flex; gap: 10px; margin-top: 16px; }}
.btn {{ flex: 1; padding: 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 15px; font-weight: 600; color: white; }}
.btn-in {{ background: #10b981; }}
.btn-in:hover {{ background: #059669; }}
.btn-out {{ background: #f59e0b; }}
.btn-out:hover {{ background: #d97706; }}
.btn-check {{ background: #3b82f6; }}
.btn-check:hover {{ background: #2563eb; }}
.btn-refresh {{ background: #6b7280; padding: 6px 12px; font-size: 13px; }}
.result {{ margin-top: 16px; padding: 14px; border-radius: 6px; display: none; }}
.result.ok {{ background: #e8f5e9; color: #2e7d32; border-left: 4px solid #10b981; }}
.result.fail {{ background: #fee; color: #c62828; border-left: 4px solid #d32f2f; }}
.result.info {{ background: #e3f2fd; color: #1565c0; border-left: 4px solid #3b82f6; }}
ol {{ margin-left: 20px; margin-top: 8px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }}
th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #eee; }}
th {{ background: #f5f7fa; font-weight: 600; color: #555; }}
.status-verified {{ color: #2e7d32; font-weight: 600; }}
.attlog-status {{ font-size: 16px; font-weight: 600; }}
.attlog-ok {{ color: #2e7d32; }}
.attlog-warn {{ color: #f59e0b; }}
.attlog-err {{ color: #c62828; }}
</style>
</head>
<body>
<div class="container">

<div class="nav">
<a href="/">🏠 Trang chính</a>
<a href="/security">🔒 Security Dashboard</a>
<a href="/punch" class="active">📱 Chấm công</a>
<a href="/alerts">⚠️ NV quên chấm</a>
</div>

<div class="card">
<h1>📱 Chấm công thủ công (PIN+Password)</h1>
<p style="color:#666; font-size:13px;">Verify PIN+Password từ xa qua pyzk. Sau khi verify OK, NV đứng trước máy ZK nhập PIN+Password để ghi ATTLOG chính thức.</p>

<div style="display:flex; align-items:center; gap:12px; margin-bottom:8px; flex-wrap:wrap;">
<span id="reachableBadge" style="padding:4px 10px; background:#f5f7fa; border-radius:4px; font-size:13px;">
🔄 Đang quét thiết bị...
</span>
<button class="btn btn-refresh" onclick="scanReachable()" style="flex:0;">🔍 Quét lại</button>
<label style="margin:0; display:flex; align-items:center; gap:4px; font-size:13px;">
<input type="checkbox" id="showAllChk" onchange="renderDeviceDropdown()" style="width:auto; margin:0;">
Hiện cả máy không reachable
</label>
</div>

<label>Máy ZK:</label>
<select id="ip">{options}</select>

<label>PIN (mã nhân viên):</label>
<input type="text" id="pin" placeholder="vd: 1383" autocomplete="off">

<label>Password:</label>
<input type="password" id="password" placeholder="vd: 1 hoặc 123456" autocomplete="off">

<div class="btn-row">
<button class="btn btn-in" onclick="punch('in')">🟢 CHECK-IN</button>
<button class="btn btn-out" onclick="punch('out')">🟡 CHECK-OUT</button>
</div>

<div id="result" class="result"></div>
</div>

<div class="card">
<h2>📊 Verify ATTLOG trên máy ZK</h2>
<p style="color:#666; font-size:13px;">Sau khi NV đứng trước máy nhập PIN+Password, bấm nút dưới để kiểm tra ATTLOG đã ghi chưa (so với baseline).</p>

<div class="btn-row">
<button class="btn btn-check" onclick="checkAttlog()">🔍 Check ATTLOG Count</button>
<button class="btn btn-refresh" onclick="resetBaseline()">🗑 Reset baseline</button>
</div>
<div id="attlogResult" class="result"></div>
</div>

<div class="card">
<h2>📜 Log chấm công thủ công (manual_punches.csv)</h2>
<button class="btn btn-refresh" onclick="loadLog()">🔄 Refresh log</button>
<div id="logTable"></div>
</div>

</div>

<script>
let logRefreshTimer = null;

// ===== Scan reachable devices =====
let reachableDevices = [];  // Array of {{ip, note, reachable, ping_ms}}
async function scanReachable() {{
    const badge = document.getElementById('reachableBadge');
    badge.innerHTML = '🔄 Đang quét 22 máy ZK (parallel TCP probe)...';
    badge.style.background = '#e3f2fd';
    try {{
        const r = await fetch('/api/punch/reachable');
        const data = await r.json();
        reachableDevices = data.devices || [];
        const ok = data.reachable_count;
        const total = data.total;
        if (ok === 0) {{
            badge.innerHTML = `❌ 0/${{total}} máy reachable. Kiểm tra VPN/subnet!`;
            badge.style.background = '#fee';
        }} else if (ok === total) {{
            badge.innerHTML = `✅ ${{ok}}/${{total}} máy reachable (tất cả OK)`;
            badge.style.background = '#e8f5e9';
        }} else {{
            badge.innerHTML = `⚠️ ${{ok}}/${{total}} máy reachable (còn lại không từ subnet này)`;
            badge.style.background = '#fff3cd';
        }}
        renderDeviceDropdown();
    }} catch (e) {{
        badge.innerHTML = '❌ Lỗi scan: ' + e;
        badge.style.background = '#fee';
    }}
}}

function renderDeviceDropdown() {{
    const sel = document.getElementById('ip');
    const showAll = document.getElementById('showAllChk').checked;
    const currentVal = sel.value;
    const list = showAll ? reachableDevices : reachableDevices.filter(d => d.reachable);
    if (list.length === 0) {{
        sel.innerHTML = '<option value="">(không có máy nào reachable)</option>';
        return;
    }}
    sel.innerHTML = list.map(d => {{
        const status = d.reachable ? '🟢' : '🔴';
        const ping = d.ping_ms != null ? ` (${{d.ping_ms}}ms)` : '';
        return `<option value="${{d.ip}}">${{status}} ${{d.ip}} (${{d.note}})${{ping}}</option>`;
    }}).join('');
    // Try to preserve previous selection if still in list
    if (list.find(d => d.ip === currentVal)) {{
        sel.value = currentVal;
    }}
}}

// ===== Punch (verify PIN+password) =====
async function punch(type) {{
    const ip = document.getElementById('ip').value;
    const pin = document.getElementById('pin').value.trim();
    const password = document.getElementById('password').value.trim();
    const result = document.getElementById('result');
    if (!ip || !pin || !password) {{
        result.className = 'result fail';
        result.style.display = 'block';
        result.innerHTML = '❌ Vui lòng nhập đầy đủ thông tin';
        return;
    }}
    // Pre-check reachable
    const dev = reachableDevices.find(d => d.ip === ip);
    if (dev && !dev.reachable) {{
        result.className = 'result fail';
        result.style.display = 'block';
        const reachableList = reachableDevices.filter(d => d.reachable).map(d => d.ip).join(', ');
        result.innerHTML = `❌ Máy <strong>${{ip}}</strong> không reachable từ subnet hiện tại!<br>
            🔧 Khả năng: cần VPN, máy offline, hoặc firewall chặn port 4370.<br>
            ✅ Các máy reachable: <code>${{reachableList || '(none)'}}</code><br>
            💡 Tick "Hiện cả máy không reachable" nếu muốn test máy khác.`;
        return;
    }}
    result.className = 'result info';
    result.style.display = 'block';
    result.innerHTML = '⏳ Đang verify PIN+password trên máy ' + ip + '...';
    try {{
        const r = await fetch('/api/punch/manual', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{ip, pin, password, type}}),
        }});
        const data = await r.json();
        if (data.ok) {{
            // Auto-capture baseline ATTLOG count
            let baseline = '?';
            try {{
                const r2 = await fetch('/api/security/device/' + ip + '/attlog-count');
                const d2 = await r2.json();
                if (d2.ok) {{
                    baseline = d2.attlog_count;
                    // Lưu baseline vào localStorage theo IP
                    const key = 'attlog_baseline_' + ip;
                    localStorage.setItem(key, JSON.stringify({{count: baseline, time: new Date().toISOString(), pin, name: data.name}}));
                }}
            }} catch (e) {{ console.warn('baseline capture failed', e); }}

            result.className = 'result ok';
            let html = `<strong>✅ ${{data.message}}</strong>`;
            html += `<div style="margin-top:10px; padding:8px; background:#fff3cd; border-radius:4px; font-size:13px;">
                📌 <strong>Baseline ATTLOG:</strong> ${{baseline}} records (lưu lại - sẽ so sánh khi NV chấm công trên máy)
            </div>`;
            if (data.instructions) {{
                html += '<ol>';
                data.instructions.forEach(i => html += `<li>${{i}}</li>`);
                html += '</ol>';
            }}
            html += '<br><em>💡 Sau khi NV đã nhập PIN+password trên máy, bấm "Check ATTLOG" để xem ATTLOG đã tăng chưa.</em>';
            result.innerHTML = html;
            // Auto-load log after success
            setTimeout(loadLog, 1000);
        }} else {{
            result.className = 'result fail';
            let errMsg = data.error || 'Unknown error';
            if (errMsg.includes("can't reach device") || errMsg.includes("timed out") || errMsg.includes("Network")) {{
                const reachableList = reachableDevices.filter(d => d.reachable).map(d => d.ip).join(', ');
                errMsg += `<br>💡 <strong>Chọn máy reachable:</strong> <code>${{reachableList || 'Bấm Quét lại'}}</code>`;
            }}
            result.innerHTML = `❌ ${{errMsg}}`;
        }}
    }} catch (e) {{
        result.className = 'result fail';
        result.innerHTML = '❌ Lỗi: ' + e;
    }}
}}

// ===== Check ATTLOG count từ ZK (so với baseline) =====
async function checkAttlog() {{
    const ip = document.getElementById('ip').value;
    const result = document.getElementById('attlogResult');
    if (!ip) {{
        result.className = 'result fail';
        result.style.display = 'block';
        result.innerHTML = '❌ Chọn máy ZK trước';
        return;
    }}
    // Pre-check reachable
    const dev = reachableDevices.find(d => d.ip === ip);
    if (dev && !dev.reachable) {{
        result.className = 'result fail';
        result.style.display = 'block';
        const reachableList = reachableDevices.filter(d => d.reachable).map(d => d.ip).join(', ');
        result.innerHTML = `❌ Máy <strong>${{ip}}</strong> không reachable!<br>✅ Máy reachable: <code>${{reachableList || '(none)'}}</code>`;
        return;
    }}
    result.className = 'result info';
    result.style.display = 'block';
    result.innerHTML = '⏳ Đang đọc ATTLOG count từ ' + ip + '...';
    try {{
        const r = await fetch('/api/security/device/' + ip + '/attlog-count');
        const data = await r.json();
        if (data.ok) {{
            const c = data.attlog_count;
            const cap = data.attlog_capacity;
            const pct = cap > 0 ? ((c / cap) * 100).toFixed(1) : 0;
            const warnClass = pct > 90 ? 'attlog-err' : (pct > 70 ? 'attlog-warn' : 'attlog-ok');

            // Lấy baseline từ localStorage
            const key = 'attlog_baseline_' + ip;
            const baseStr = localStorage.getItem(key);
            let baselineInfo = '';
            let deltaHtml = '';
            if (baseStr) {{
                try {{
                    const base = JSON.parse(baseStr);
                    const delta = c - base.count;
                    const deltaClass = delta > 0 ? 'attlog-ok' : (delta === 0 ? 'attlog-warn' : 'attlog-err');
                    const deltaIcon = delta > 0 ? '✅' : (delta === 0 ? '⚠️' : '❌');
                    const deltaMsg = delta > 0
                        ? `<strong>ĐÃ GHI ATTLOG</strong> - NV đã chấm công thành công trên máy!`
                        : (delta === 0
                            ? `<strong>CHƯA GHI</strong> - NV chưa nhập PIN+password trên máy (hoặc máy chưa sync)`
                            : `<strong>GIẢM!</strong> - Có thể máy đã rollover hoặc sync với server`);
                    baselineInfo = `
                        <div style="margin-top:8px; padding:8px; background:#f5f7fa; border-radius:4px; font-size:13px;">
                            📌 <strong>Baseline:</strong> ${{base.count}} records (PIN ${{base.pin}} - ${{base.name}} lúc ${{new Date(base.time).toLocaleString('vi-VN')}})
                        </div>
                    `;
                    deltaHtml = `
                        <div class="attlog-status ${{deltaClass}}" style="margin-top:8px;">
                            ${{deltaIcon}} Delta: <strong>${{delta > 0 ? '+' : ''}}${{delta}}</strong> records - ${{deltaMsg}}
                        </div>
                    `;
                }} catch (e) {{ console.warn(e); }}
            }} else {{
                baselineInfo = `
                    <div style="margin-top:8px; padding:8px; background:#fff3cd; border-radius:4px; font-size:13px;">
                        ℹ️ Chưa có baseline. Hãy bấm CHECK-IN/CHECK-OUT trước để tự động capture baseline.
                    </div>
                `;
            }}

            result.className = 'result ok';
            result.innerHTML = `
<div class="attlog-status ${{warnClass}}">
📊 ATTLOG hiện tại: ${{c}} / ${{cap}} records (${{pct}}%)
</div>
${{baselineInfo}}
${{deltaHtml}}
<div style="font-size:12px;color:#888;margin-top:8px;">
Users: ${{data.users_count}} / ${{data.users_capacity}} | Check lúc: ${{new Date(data.timestamp).toLocaleString('vi-VN')}}<br>
<em>${{data.note || ''}}</em>
</div>
            `;
        }} else {{
            result.className = 'result fail';
            let errMsg = data.error || 'unknown';
            if (errMsg.includes("can't reach") || errMsg.includes("timed out") || errMsg.includes("Network")) {{
                const reachableList = reachableDevices.filter(d => d.reachable).map(d => d.ip).join(', ');
                errMsg += `<br>💡 <strong>Chọn máy reachable:</strong> <code>${{reachableList || 'Bấm Quét lại'}}</code>`;
            }}
            result.innerHTML = '❌ Lỗi: ' + errMsg;
        }}
    }} catch (e) {{
        result.className = 'result fail';
        result.innerHTML = '❌ Lỗi kết nối: ' + e;
    }}
}}

// Reset baseline button
function resetBaseline() {{
    const ip = document.getElementById('ip').value;
    if (!ip) {{
        alert('Chọn máy ZK trước');
        return;
    }}
    const key = 'attlog_baseline_' + ip;
    localStorage.removeItem(key);
    document.getElementById('attlogResult').innerHTML = '<p style="color:#888;">✅ Đã reset baseline cho ' + ip + '. Bấm CHECK-IN/CHECK-OUT để capture baseline mới.</p>';
}}

// ===== Load manual_punches.csv =====
async function loadLog() {{
    const tbl = document.getElementById('logTable');
    try {{
        const r = await fetch('/api/punch/log');
        const data = await r.json();
        if (data.ok && data.log && data.log.length > 0) {{
            let html = '<table><thead><tr>';
            html += '<th>Thời gian</th><th>Máy</th><th>PIN</th><th>Tên NV</th><th>Loại</th><th>Trạng thái</th>';
            html += '</tr></thead><tbody>';
            data.log.forEach(r => {{
                html += '<tr>';
                html += '<td>' + new Date(r.timestamp).toLocaleString('vi-VN') + '</td>';
                html += '<td>' + r.device_ip + '</td>';
                html += '<td>' + r.pin + '</td>';
                html += '<td>' + r.name + '</td>';
                html += '<td>' + r.type + '</td>';
                html += '<td class="status-verified">✅ ' + r.status + '</td>';
                html += '</tr>';
            }});
            html += '</tbody></table>';
            html += '<p style="color:#888;font-size:12px;margin-top:8px;">Hiển thị ' + data.log.length + ' records (cột timestamp là local time)</p>';
            tbl.innerHTML = html;
        }} else {{
            tbl.innerHTML = '<p style="color:#888;text-align:center;padding:20px;">Chưa có log chấm công thủ công nào.</p>';
        }}
    }} catch (e) {{
        tbl.innerHTML = '<p style="color:#c62828;">❌ Lỗi load log: ' + e + '</p>';
    }}
}}

// Auto-load log on page open + refresh every 10s
window.addEventListener('DOMContentLoaded', () => {{
    loadLog();
    logRefreshTimer = setInterval(loadLog, 10000);
    // Auto-scan reachable devices on page load
    scanReachable();
}});
</script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(page.encode('utf-8'))

    # Attach methods to handler class
    handler_class._handle_security_scan = _handle_security_scan
    handler_class._handle_security_page = _handle_security_page
    handler_class._handle_security_verify = _handle_security_verify
    handler_class._handle_punch_manual = _handle_punch_manual
    handler_class._handle_punch_page = _handle_punch_page
    handler_class._handle_punch_log = _handle_punch_log
    handler_class._handle_attlog_count = _handle_attlog_count
    handler_class._handle_punch_reachable = _handle_punch_reachable
