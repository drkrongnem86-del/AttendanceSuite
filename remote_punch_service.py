# -*- coding: utf-8 -*-
"""
remote_punch_service.py
========================
He thong cham cong tu xa cho BVĐK Ninh Thuan.

Workflow:
  1. BS Diem bam cham cong tren dien thoai (qua VPN, truy cap attendance_web.py)
  2. Web ghi vao pending_punches.csv (local)
  3. Service nay tu dong sync pending -> cac kenh:
     a. Secutime API (applySign) - chinh thuc, kha nang thanh cong cao
     b. ADMS queue command - neu cau hinh
     c. Direct ZK write - last resort
  4. Log thanh cong se chuyen tu pending -> synced (tranh trung lap)

Cai dat:
  1. Copy file nay vao D:\\chamcong\\
  2. Sua config ben duoi
  3. Chay: python remote_punch_service.py
  4. Hoac install Windows Service bang nssm:
     nssm install RemotePunch "D:\\chamcong\\AttendanceSuite_Portable\\python\\python.exe" "D:\\chamcong\\remote_punch_service.py"
"""
import os
import sys
import json
import time
import csv
import socket
import threading
import urllib.request
import urllib.error
import urllib.parse
import ssl
import struct
import queue
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

socket.setdefaulttimeout(5.0)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


# ============ CONFIG ============
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING_FILE = os.path.join(SCRIPT_DIR, "pending_punches.csv")
SYNCED_FILE = os.path.join(SCRIPT_DIR, "synced_punches.csv")
FAILED_FILE = os.path.join(SCRIPT_DIR, "failed_punches.csv")
STATE_FILE = os.path.join(SCRIPT_DIR, "sync_state.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "remote_punch_service.log")

SECUTIME_HOST = "172.16.0.31"  # Secutime server
SECUTIME_PORT = 8098
SECUTIME_USER = "admin"
SECUTIME_PASS = "admin@123"

ADMS_HOST = "172.16.200.105"  # May BS chay service
ADMS_PORT = 8080

DEVICE_IPS = [
    "172.16.0.212",  # May 1 (default)
    "172.16.0.214",  # May 3 (online theo screenshot)
    "172.16.0.30",   # Gateway (online)
    "172.16.0.31",   # Secutime (online)
]

SYNC_INTERVAL = 30  # seconds

# Basic auth (BS nen doi truoc khi deploy internet)
AUTH_USER = "admin"
AUTH_PASS = "bvdk2026"  # Default - DOI truoc khi expose ra internet!
AUTH_ENABLED = True  # Set False de tat auth (chi dung local)

# Field names for CSV
CSV_FIELDS = [
    "punch_id", "timestamp", "user_id", "user_name",
    "status", "status_name", "punch", "method_name",
    "device_ip", "synced_via", "synced_at", "note"
]


# ============ STATE ============
state_lock = threading.Lock()
sync_state = {
    "running": False,
    "last_sync": None,
    "last_success": None,
    "pending_count": 0,
    "synced_count": 0,
    "failed_count": 0,
    "channels": {
        "secutime": {"enabled": True, "last_ok": None, "last_fail": None, "consecutive_fail": 0},
        "adms": {"enabled": True, "last_ok": None, "last_fail": None, "consecutive_fail": 0},
        "direct_zk": {"enabled": True, "last_ok": None, "last_fail": None, "consecutive_fail": 0},
    },
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    # Safe print - thay the ky tu loi bang ? neu console khong encode duoc
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        safe = line.encode("ascii", "replace").decode("ascii")
        print(safe, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass


def load_state():
    global sync_state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                sync_state.update(json.load(f))
        except:
            pass


def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(sync_state, f, indent=2, ensure_ascii=False)
    except:
        pass


# ============ CSV HELPERS ============
def ensure_csv(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


def append_csv(path, row):
    ensure_csv(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writerow(row)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rewrite_csv(path, rows):
    ensure_csv(path)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ============ SYNC CHANNELS ============
def sync_via_secutime(punch):
    """
    Sync 1 punch qua Secutime API (CVSecurity applySign hoac BioTime transaction).
    """
    import http.client
    try:
        conn = http.client.HTTPConnection(SECUTIME_HOST, SECUTIME_PORT, timeout=8)
        # Thu nhieu payload format
        payloads = [
            # CVSecurity applySign
            {
                "endpoint": f"/api/attApply/applySign?access_token=",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "personPin": int(punch["user_id"]),
                    "remark": f"remote_punch_{punch['punch_id']}",
                    "signDatetime": punch["timestamp"],
                }),
            },
            # BioTime transaction
            {
                "endpoint": f"/iclock/api/transactions/?access_token=",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "emp_code": punch["user_id"],
                    "punch_time": punch["timestamp"],
                    "punch_state": punch["status"],
                    "verify_type": punch["punch"],
                }),
            },
        ]

        for pl in payloads:
            try:
                conn.request(pl["method"], pl["endpoint"], body=pl["body"],
                              headers=pl["headers"])
                resp = conn.getresponse()
                body = resp.read().decode(errors='ignore')
                if resp.status in (200, 201):
                    log(f"  [Secutime] OK via {pl['method']} {pl['endpoint'][:50]}: {body[:100]}")
                    return True, f"Secutime-{pl['method']}-{resp.status}"
                # Neu 401/403, can token. Thu tiep voi auth.
            except Exception as e:
                log(f"  [Secutime] Error: {str(e)[:100]}")
                continue

        conn.close()
        return False, "All Secutime payloads returned non-OK"
    except Exception as e:
        return False, f"Secutime connection error: {str(e)[:100]}"


def sync_via_adms(punch):
    """
    Sync qua ADMS queue (neu may ZK duoc config push len server nay).
    """
    try:
        url = f"http://{ADMS_HOST}:{ADMS_PORT}/queue"
        # ADMS khong co lenh ghi ATTLOG truc tiep. Thu lenh USER ADD voi ten dac biet
        # Lam marker de sau do detect.
        sn = punch.get("device_ip", "unknown")
        # Queued command
        cmd = f"DATA UPDATE USERINFO PIN={punch['user_id']}\\tName=REMOTE_{punch['timestamp']}"
        params = urllib.parse.urlencode({"SN": sn, "cmd": cmd})
        req = urllib.request.Request(
            f"{url}?{params}", method="POST",
            data=b"", headers={"Content-Type": "text/plain"}
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            body = r.read().decode(errors='ignore')
        log(f"  [ADMS] Queued for {sn}: {body[:100]}")
        return True, f"ADMS-queued"
    except Exception as e:
        return False, f"ADMS error: {str(e)[:100]}"


def sync_via_direct_zk(punch):
    """
    Thu ghi truc tiep vao may ZK qua ZK protocol.
    Day la fallback cuoi cung - thuong se fail voi X628 firmware 6.60.
    """
    try:
        sys.path.insert(0, os.path.join(SCRIPT_DIR, "AttendanceSuite_Portable",
                                        "python", "Lib", "site-packages"))
        from zk import ZK
        from zk import const as zk_const

        device_ip = punch.get("device_ip", "172.16.0.212")
        zk = ZK(device_ip, port=4370, timeout=5, ommit_ping=True, verbose=False)
        if not zk.connect():
            return False, "Cannot connect to ZK device"

        try:
            user_id_int = int(punch["user_id"])
        except:
            return False, f"Invalid user_id: {punch['user_id']}"

        # Encode timestamp
        ts = datetime.strptime(punch["timestamp"], "%Y-%m-%d %H:%M:%S")
        encoded_ts = zk._ZK__encode_time(ts)
        status = int(punch.get("status", 0))
        punch_code = int(punch.get("punch", 0))

        # Try 3 formats
        attempts = [
            ("Format-1", struct.pack('<IIBB', user_id_int, encoded_ts, status, punch_code)),
            ("Format-2", struct.pack('<HBB', 0, status, punch_code) + struct.pack('<II', encoded_ts, user_id_int)),
        ]

        any_ok = False
        for name, payload in attempts:
            try:
                resp = zk._ZK__send_command(zk_const.CMD_REG_EVENT, payload.ljust(16, b'\x00'), response_size=8)
                if resp and resp.get("status") and resp.get("code") == zk_const.CMD_ACK_OK:
                    any_ok = True
            except:
                pass

        zk.disconnect()
        if any_ok:
            return True, "Direct-ZK-ACK-OK (verify needed)"
        return False, "Direct ZK rejected all formats"
    except Exception as e:
        return False, f"Direct ZK error: {str(e)[:100]}"


# ============ SYNC LOOP ============
sync_channels = [
    ("secutime", sync_via_secutime),
    ("adms", sync_via_adms),
    ("direct_zk", sync_via_direct_zk),
]


def sync_pending():
    """Main sync loop: doc pending, thử từng kênh, ghi synced/failed."""
    with state_lock:
        sync_state["running"] = True
        sync_state["last_sync"] = datetime.now().isoformat()
    save_state()

    pending = read_csv(PENDING_FILE)
    if not pending:
        with state_lock:
            sync_state["running"] = False
            sync_state["pending_count"] = 0
        return

    log(f"[*] Found {len(pending)} pending punches to sync")
    synced = []
    still_pending = []
    failed = []

    for punch in pending:
        punch_id = punch.get("punch_id", "")
        log(f"  Punch #{punch_id} NV {punch.get('user_id')} {punch.get('timestamp')}")

        success = False
        for ch_name, ch_func in sync_channels:
            with state_lock:
                if not sync_state["channels"][ch_name]["enabled"]:
                    continue
            try:
                ok, msg = ch_func(punch)
            except Exception as e:
                ok, msg = False, f"Exception: {str(e)[:80]}"

            with state_lock:
                if ok:
                    sync_state["channels"][ch_name]["last_ok"] = datetime.now().isoformat()
                    sync_state["channels"][ch_name]["consecutive_fail"] = 0
                else:
                    sync_state["channels"][ch_name]["last_fail"] = datetime.now().isoformat()
                    sync_state["channels"][ch_name]["consecutive_fail"] += 1

            if ok:
                punch["synced_via"] = ch_name
                punch["synced_at"] = datetime.now().isoformat()
                punch["note"] = msg
                synced.append(punch)
                log(f"    -> Synced via {ch_name}: {msg[:80]}")
                success = True
                break

        if not success:
            log(f"    -> All channels failed, keep pending")
            still_pending.append(punch)
            failed.append(punch)

    # Rewrite CSVs - CHI rewrite khi co thay doi (tranh mat data khi sync fail)
    if still_pending != pending:
        rewrite_csv(PENDING_FILE, still_pending)
    for s in synced:
        append_csv(SYNCED_FILE, s)
    for f in failed:
        append_csv(FAILED_FILE, f)

    with state_lock:
        sync_state["pending_count"] = len(still_pending)
        sync_state["synced_count"] = sync_state.get("synced_count", 0) + len(synced)
        sync_state["failed_count"] = sync_state.get("failed_count", 0) + len(failed)
        sync_state["last_success"] = datetime.now().isoformat() if synced else sync_state.get("last_success")
        sync_state["running"] = False
    save_state()

    log(f"[OK] Synced {len(synced)}, still pending {len(still_pending)}, failed {len(failed)}")


def sync_loop():
    """Background thread: sync every SYNC_INTERVAL seconds."""
    while True:
        try:
            sync_pending()
        except Exception as e:
            log(f"[ERR] Sync loop: {e}")
        time.sleep(SYNC_INTERVAL)


# ============ HTTP DASHBOARD (for monitoring) ============
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Cham Cong - BVDK Ninh Thuan</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 12px; line-height: 1.4; }
h1 { color: #00d4ff; font-size: 20px; margin-bottom: 4px; }
h2 { color: #00d4ff; font-size: 16px; margin: 16px 0 8px; }
.subtitle { color: #94a3b8; font-size: 12px; margin-bottom: 12px; }
.stat-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.stat { background: #1e293b; padding: 10px 14px; border-radius: 8px; flex: 1; min-width: 90px; }
.stat .v { font-size: 24px; font-weight: 700; color: #5fff7f; }
.stat .l { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.stat.warn .v { color: #ffd700; }
.stat.err .v { color: #ff8888; }
.ch { background: #1e293b; padding: 10px 12px; border-radius: 6px; margin: 6px 0; font-size: 12px; }
.ch.ok { border-left: 3px solid #10b981; }
.ch.fail { border-left: 3px solid #ef4444; }
.ch b { color: #00d4ff; }

/* Quick punch - mobile friendly */
.quick-punch { background: #1e293b; padding: 14px; border-radius: 10px; margin: 12px 0; }
.quick-punch label { display: block; margin-bottom: 6px; font-size: 13px; color: #94a3b8; }
.quick-punch input, .quick-punch select { width: 100%; padding: 10px; margin: 4px 0; border: 0; border-radius: 6px; background: #0f172a; color: #e2e8f0; font-size: 15px; }
.btn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
.btn { padding: 12px 8px; border: 0; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; }
.btn-primary { background: #10b981; color: white; }
.btn-primary:hover { background: #0e6e0e; }
.btn-secondary { background: #007acc; color: white; }
.btn-secondary:hover { background: #005fa3; }
.btn-danger { background: #ef4444; color: white; }
.btn-danger:hover { background: #c50f1f; }
.btn-quick { background: #6366f1; color: white; padding: 14px; font-size: 16px; }
.btn-quick:active { transform: scale(0.97); }

table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; margin: 8px 0; font-size: 12px; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #334155; }
th { background: #334155; color: #f1f5f9; font-size: 11px; text-transform: uppercase; }
tr:hover { background: #334155; }

.meta { color: #94a3b8; font-size: 11px; margin: 4px 0; }
.tag { display: inline-block; padding: 1px 6px; border-radius: 8px; font-size: 10px; font-weight: 600; }
.tag-ok { background: #064e3b; color: #6ee7b7; }
.tag-fail { background: #7f1d1d; color: #fca5a5; }
.tag-pending { background: #1e3a8a; color: #93c5fd; }
.logout { float: right; font-size: 11px; color: #94a3b8; text-decoration: none; padding: 4px 8px; }
.logout:hover { color: #ff8888; }
hr { border: 0; border-top: 1px solid #334155; margin: 12px 0; }

/* Mobile: nut to hon */
@media (max-width: 600px) {
  body { padding: 8px; }
  .stat .v { font-size: 20px; }
  .btn { padding: 14px 8px; font-size: 15px; }
  th, td { padding: 4px 6px; font-size: 11px; }
  .hide-mobile { display: none; }
}
</style>
</head>
<body>
<h1>Cham Cong Tu Xa
<a class="logout" href="/logout">[Dang xuat]</a>
</h1>
<p class="subtitle">BVDK Ninh Thuan - HSCCL $user_display</p>

<div class="stat-row">
  <div class="stat"><div class="v">$pending</div><div class="l">Dang cho</div></div>
  <div class="stat"><div class="v">$synced</div><div class="l">OK</div></div>
  <div class="stat $failed_class"><div class="v">$failed</div><div class="l">Fail</div></div>
</div>
<p class="meta">Last sync: $last_sync | Running: $running</p>

<hr>
<h2>Cham Cong Nhanh (1 cham)</h2>
<div class="quick-punch">
  <form method="POST" action="/punch" id="quickForm">
    <label>Ma NV (so, 1-10 ky tu):</label>
    <input type="tel" name="user_id" required maxlength="10" placeholder="vd: 421" autocomplete="off" autofocus>

    <label>Thao tac:</label>
    <div class="btn-row">
      <button class="btn btn-primary" type="button" onclick="setStatus(0)">VAO CA</button>
      <button class="btn btn-danger" type="button" onclick="setStatus(1)">TAN CA</button>
      <button class="btn btn-secondary" type="button" onclick="setStatus(2)">RA NGOAI</button>
      <button class="btn btn-secondary" type="button" onclick="setStatus(3)">VAO LAI</button>
    </div>
    <input type="hidden" name="status" id="statusInput" value="0">

    <label style="margin-top:8px">May cham cong:</label>
    <select name="device_ip">
      $device_options
    </select>

    <div class="btn-row" style="margin-top:10px">
      <button class="btn btn-quick" type="submit">CHAM CONG</button>
    </div>
  </form>
</div>

<script>
function setStatus(s) {
  document.getElementById('statusInput').value = s;
  document.querySelectorAll('.btn-primary, .btn-secondary, .btn-danger').forEach(b => b.style.outline = '');
  event.target.style.outline = '3px solid #00d4ff';
}
// Auto-focus va auto-submit bang Enter
document.getElementById('quickForm').addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.name === 'user_id') {
    e.preventDefault();
    e.target.form.requestSubmit();
  }
});
// Auto-refresh chi phan stats, khong phai ca page
setInterval(async () => {
  try {
    const r = await fetch('/api/stats');
    const d = await r.json();
    document.querySelectorAll('.stat .v')[0].textContent = d.pending_count;
    document.querySelectorAll('.stat .v')[1].textContent = d.synced_count;
    document.querySelectorAll('.stat .v')[2].textContent = d.failed_count;
  } catch (e) {}
}, 5000);
</script>

<hr>
<h2>Ken sync</h2>
$channels

<hr>
<h2>Pending ($pending_count)</h2>
$pending_table

<hr>
<h2>Synced gan day (10)</h2>
$synced_table

<hr>
<p class="meta">Build: 2026-09-10 v1.0 | Auto-refresh 5s</p>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _check_auth(self):
        """Check Basic Auth. Returns True neu OK, False neu can nhap lai."""
        if not AUTH_ENABLED:
            return True
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False
        try:
            import base64
            creds = base64.b64decode(auth_header[6:]).decode("utf-8")
            user, pwd = creds.split(":", 1)
            return user == AUTH_USER and pwd == AUTH_PASS
        except Exception:
            return False

    def _send_auth_required(self):
        """Tra ve 401 + WWW-Authenticate header."""
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Remote Punch Service"')
        self.send_header("Content-Type", "text/html; charset=utf-8")
        body = b"<h1>401 - Can dang nhap</h1><p>Nhap user/pass de truy cap.</p>"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Health check - khong can auth (cho monitoring tools)
        if self.path == "/healthz" or self.path == "/api/health":
            self._send_json({"ok": True, "ts": datetime.now().isoformat()})
            return
        # Stats JSON - can auth
        if self.path == "/api/stats":
            if not self._check_auth():
                self._send_auth_required()
                return
            with state_lock:
                pending = read_csv(PENDING_FILE)
            self._send_json({
                "pending_count": len(pending),
                "synced_count": sync_state.get("synced_count", 0),
                "failed_count": sync_state.get("failed_count", 0),
                "running": sync_state.get("running", False),
                "last_sync": sync_state.get("last_sync"),
            })
            return
        # Logout
        if self.path == "/logout":
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Remote Punch Service"')
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = b"<h1>Dang xuat OK</h1><p>Dong tab nay.</p>"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # Main dashboard
        if self.path == "/" or self.path.startswith("/?"):
            if not self._check_auth():
                self._send_auth_required()
                return
            with state_lock:
                pending = read_csv(PENDING_FILE)
                synced = read_csv(SYNCED_FILE)[-10:]
                st = dict(sync_state)

            ch_html = ""
            for name, info in st["channels"].items():
                cls = "ok" if (info.get("last_ok") and
                               (not info.get("last_fail") or info["last_ok"] > info["last_fail"])) else "fail"
                ch_html += f'''<div class="ch {cls}">
                  <b>{name}</b> - enabled: {info['enabled']}<br>
                  Last OK: {info.get('last_ok', 'never')}<br>
                  Last fail: {info.get('last_fail', 'never')}<br>
                  Consecutive fails: {info.get('consecutive_fail', 0)}
                </div>'''

            pending_table = "<table><tr><th>ID</th><th>Time</th><th>NV</th><th>TT</th><th>May</th></tr>"
            for p in pending:
                pending_table += f"<tr><td>{p.get('punch_id', '')[-6:]}</td><td>{p.get('timestamp', '')}</td><td>{p.get('user_id', '')}</td><td>{p.get('status_name', '')}</td><td>{p.get('device_ip', '')}</td></tr>"
            if not pending:
                pending_table += '<tr><td colspan="5" style="text-align:center;color:#94a3b8">Trong</td></tr>'
            pending_table += "</table>"

            synced_table = "<table><tr><th>ID</th><th>Time</th><th>NV</th><th>Qua</th><th>Luc</th></tr>"
            for s in reversed(synced):
                synced_table += f"<tr><td>{s.get('punch_id', '')[-6:]}</td><td>{s.get('timestamp', '')}</td><td>{s.get('user_id', '')}</td><td><span class='tag tag-ok'>{s.get('synced_via', '')}</span></td><td>{s.get('synced_at', '')[-8:] if s.get('synced_at') else ''}</td></tr>"
            if not synced:
                synced_table += '<tr><td colspan="5" style="text-align:center;color:#94a3b8">Chua co</td></tr>'
            synced_table += "</table>"

            # Build device options
            device_options = ""
            for ip in DEVICE_IPS:
                note = ""
                for d in (st.get("devices") or []):
                    if d.get("ip") == ip:
                        note = f" ({d.get('log_count', 0)} logs)"
                        break
                device_options += f'<option value="{ip}">{ip}{note}</option>'

            failed = st.get("failed_count", 0)
            failed_class = "err" if failed > 0 else ""

            user_display = f"| user: {AUTH_USER}" if AUTH_ENABLED else ""

            html = (DASHBOARD_HTML
                    .replace("$pending", str(len(pending)))
                    .replace("$synced", str(st.get("synced_count", 0)))
                    .replace("$failed", str(failed))
                    .replace("$failed_class", failed_class)
                    .replace("$running", "YES" if st.get("running") else "no")
                    .replace("$last_sync", str(st.get("last_sync", "never")))
                    .replace("$user_display", user_display)
                    .replace("$channels", ch_html)
                    .replace("$pending_count", str(len(pending)))
                    .replace("$pending_table", pending_table)
                    .replace("$synced_table", synced_table)
                    .replace("$device_options", device_options))
            self._send_html(html)
        else:
            self._send_html("404", code=404)

    def do_POST(self):
        if not self._check_auth():
            self._send_auth_required()
            return
        if self.path == "/punch":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = urllib.parse.parse_qs(body)
            user_id = params.get("user_id", [""])[0].strip()
            status = params.get("status", ["0"])[0]
            device_ip = params.get("device_ip", [DEVICE_IPS[0]])[0]

            if not user_id:
                self._send_html("Thieu ma NV", code=400)
                return

            # Validate
            try:
                int(user_id)
            except ValueError:
                self._send_html(f"Ma NV khong hop le: {user_id}", code=400)
                return

            punch_id = int(time.time() * 1000)
            statuses = {0: "Check-In", 1: "Check-Out", 2: "Break-Out",
                        3: "Break-In", 4: "OT-In", 5: "OT-Out"}
            row = {
                "punch_id": str(punch_id),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "user_name": f"NV {user_id}",
                "status": status,
                "status_name": statuses.get(int(status), "Unknown"),
                "punch": "0",
                "method_name": "Remote",
                "device_ip": device_ip,
                "synced_via": "",
                "synced_at": "",
                "note": "from dashboard",
            }
            append_csv(PENDING_FILE, row)
            log(f"[+] New pending punch #{punch_id} for NV {user_id}")
            # Neu AJAX request -> JSON
            if self.headers.get("X-Requested-With") == "XMLHttpRequest":
                self._send_json({"ok": True, "punch_id": punch_id,
                                 "message": f"Queued #{punch_id}"})
            else:
                # Redirect back to dashboard
                self.send_response(303)
                self.send_header("Location", "/?ok=1&punch=" + str(punch_id))
                self.end_headers()
        else:
            self._send_html("404", code=404)

    def _send_html(self, html, code=200):
        if isinstance(html, str):
            html = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ============ MAIN ============
def main():
    log("=" * 70)
    log("REMOTE PUNCH SERVICE - BVĐK Ninh Thuan")
    log("=" * 70)
    log(f"Pending file: {PENDING_FILE}")
    log(f"Sync interval: {SYNC_INTERVAL}s")
    log(f"Secutime: {SECUTIME_HOST}:{SECUTIME_PORT}")
    log(f"ADMS: {ADMS_HOST}:{ADMS_PORT}")

    ensure_csv(PENDING_FILE)
    ensure_csv(SYNCED_FILE)
    ensure_csv(FAILED_FILE)
    load_state()

    # Start sync loop in background
    t = threading.Thread(target=sync_loop, daemon=True)
    t.start()
    log("[*] Sync loop started")

    # Start HTTP dashboard
    port = 8082
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    log(f"[*] Dashboard at http://localhost:{port}/")
    log(f"[*] Open browser de theo doi, them punch, etc.")
    log("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Stopped by user")
        server.shutdown()


if __name__ == "__main__":
    main()
