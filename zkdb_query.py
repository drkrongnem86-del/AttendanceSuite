#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zkdb_query.py - Tool query ZKDB.db (SQLite) cho BVĐK Ninh Thuận.

ATT_LOG schema (49k records):
  ID, User_PIN, Verify_Type (1=FP, 3=face), Verify_Time (ISO datetime),
  Status (0=check-in, 1=check-out, 5=break), Work_Code_ID, Sensor_NO,
  Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG

USER schema (1,255 users):
  PIN, Name, Password, Privilege (14=Admin), Card, Group, etc.

Commands:
  python zkdb_query.py info                                       # Tổng quan DB
  python zkdb_query.py users                                      # Danh sách NV
  python zkdb_query.py report --month 2026-09                     # Báo cáo tháng
  python zkdb_query.py report --month 2026-09 --user 47           # Chi tiết 1 NV
  python zkdb_query.py report --month 2026-09 --export excel      # Xuất Excel
  python zkdb_query.py compare --hr users_hr.csv                   # So sánh với HR
  python zkdb_query.py missing --date 2026-09-12                  # NV không chấm
  python zkdb_query.py top --limit 10                              # Top users theo số ngày chấm

Usage mặc định: tìm ZKDB.db trong D:\\chamcong\\zk_data_extracted\\ZKDB.db
Override: --db <path>
"""
import sys
import os
import io
import sqlite3
import csv
import json
import argparse
from collections import defaultdict
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DEFAULT_DB_PATHS = [
    r'D:\chamcong\zk_data_extracted\ZKDB.db',
    r'C:\Users\drkro\Desktop\zk_data_extracted\ZKDB.db',
    r'.\ZKDB.db',
]


def _safe_decode(b):
    """Decode bytes với multiple encodings (utf-8, cp1252, latin-1, utf-16)."""
    if b is None:
        return ''
    if isinstance(b, str):
        return b
    for enc in ['utf-8', 'cp1252', 'latin-1', 'utf-16-le', 'utf-16-be']:
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return b.hex()[:32]  # Fallback: hex preview


def find_db():
    """Tìm ZKDB.db ở các vị trí mặc định."""
    for p in DEFAULT_DB_PATHS:
        if os.path.exists(p):
            return p
    return None


def connect(db_path):
    """Mở connection + setup encoding cho non-UTF-8 names."""
    if not os.path.exists(db_path):
        print(f"❌ Không tìm thấy DB: {db_path}")
        sys.exit(1)
    print(f"📂 DB: {db_path} ({os.path.getsize(db_path):,} bytes)")
    conn = sqlite3.connect(db_path)
    # ZKDB.db có Name chứa bytes CP1252/VNI, set text_factory để auto decode
    conn.text_factory = lambda b: b.decode('cp1252', errors='replace') if isinstance(b, bytes) else b
    return conn


def cmd_info(conn):
    """Tổng quan: số tables, records per table."""
    print("\n=== THÔNG TIN TỔNG QUAN ===")
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in c.fetchall()]
    print(f"Tổng số bảng: {len(tables)}")
    print()
    # Top tables by row count
    c.execute("""
        SELECT name FROM sqlite_master WHERE type='table'
        ORDER BY name
    """)
    summary = []
    for (name,) in c.fetchall():
        try:
            c.execute(f'SELECT COUNT(*) FROM "{name}"')
            n = c.fetchone()[0]
            summary.append((name, n))
        except:
            summary.append((name, '?'))
    summary.sort(key=lambda x: -x[1] if isinstance(x[1], int) else 0)
    print(f"{'Table':<30} {'Rows':>10}")
    print("-" * 42)
    for name, n in summary[:15]:
        nstr = f'{n:,}' if isinstance(n, int) else n
        print(f"{name:<30} {nstr:>10}")


def cmd_users(conn, only_active=True):
    """Danh sách nhân viên từ bảng USER."""
    print("\n=== DANH SÁCH NHÂN VIÊN ===")
    c = conn.cursor()
    # Try multiple table names (USER or USER_INFO)
    for table in ['USER_INFO', 'USER']:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            if c.fetchone()[0] > 0:
                break
        except:
            continue
    c.execute(f"PRAGMA table_info({table})")
    cols = [c2[1] for c2 in c.fetchall()]
    print(f"Columns: {cols}")
    # Query thường (table USER_INFO có User_PIN, table USER có PIN)
    pin_col = 'User_PIN' if table == 'USER_INFO' else 'PIN'
    sql = f"SELECT {pin_col}, Name, Privilege FROM {table}"
    if only_active:
        sql += f" WHERE {pin_col} IS NOT NULL AND {pin_col} != ''"
    sql += f" ORDER BY CAST({pin_col} AS INTEGER)"
    c.execute(sql)
    rows = c.fetchall()
    print(f"\n{'PIN':<8} {'Privilege':<10} {'Name'}")
    print("-" * 60)
    for pin, name, priv in rows[:50]:
        pin = _safe_decode(pin)
        name = _safe_decode(name)
        priv_name = {0: 'User', 2: 'Enroller', 14: 'Admin'}.get(priv, str(priv))
        print(f"{pin:<8} {priv_name:<10} {name}")
    print(f"\n... tổng {len(rows)} users (hiển thị 50 đầu)")
    # Unique privilege levels
    c.execute(f"SELECT Privilege, COUNT(*) FROM {table} GROUP BY Privilege")
    print("\nPhân bố privilege:")
    for priv, cnt in c.fetchall():
        priv_name = {0: 'User', 2: 'Enroller', 14: 'Admin'}.get(priv, str(priv))
        print(f"  {priv_name}: {cnt}")


def _calc_hours(recs):
    """Tính giờ làm từ list records (đã sort theo thời gian)."""
    pairs = []
    last_in = None
    for r in sorted(recs, key=lambda x: x['time']):
        if r['status'] == 0:
            last_in = r
        elif r['status'] == 1 and last_in:
            try:
                t1 = datetime.strptime(last_in['time'], '%H:%M:%S')
                t2 = datetime.strptime(r['time'], '%H:%M:%S')
                delta = (t2 - t1).total_seconds() / 3600.0
                if delta < 0:
                    delta += 24
                pairs.append((last_in, r, round(delta, 2)))
                last_in = None
            except:
                pass
    total = sum(p[2] for p in pairs)
    return pairs, round(total, 2)


def cmd_report(conn, month=None, user_pin=None, export=None):
    """Báo cáo tháng - theo user, theo ngày."""
    if not month:
        month = datetime.now().strftime('%Y-%m')
    year, mon = map(int, month.split('-'))
    print(f"\n=== BÁO CÁO THÁNG {month} ===")

    c = conn.cursor()
    # Query ATT_LOG trong tháng
    sql = """
        SELECT ID, User_PIN, Verify_Type, Verify_Time, Status
        FROM ATT_LOG
        WHERE substr(Verify_Time, 1, 7) = ?
    """
    params = [month]
    if user_pin:
        sql += " AND User_PIN = ?"
        params.append(user_pin)
    sql += " ORDER BY Verify_Time"
    c.execute(sql, params)
    rows = c.fetchall()

    if not rows:
        print(f"Không có record nào trong tháng {month}")
        return

    # Build records
    records = []
    for r in rows:
        try:
            dt = datetime.fromisoformat(r[3])
            records.append({
                'id': r[0],
                'pin': r[1],
                'verify_type': r[2],
                'datetime': r[3],
                'date': dt.strftime('%Y-%m-%d'),
                'time': dt.strftime('%H:%M:%S'),
                'status': r[4],
                'status_name': {0: 'Check-In', 1: 'Check-Out', 5: 'Break'}.get(r[4], f'Status{r[4]}'),
            })
        except:
            pass

    # Group by user
    by_user = defaultdict(list)
    for rec in records:
        by_user[rec['pin']].append(rec)

    # User names (try both USER and USER_INFO - different column names)
    user_names = {}
    for t, col in [('USER_INFO', 'User_PIN'), ('USER', 'PIN')]:
        try:
            c.execute(f"SELECT {col}, Name FROM {t}")
            for pin, name in c.fetchall():
                user_names[_safe_decode(pin)] = _safe_decode(name)
        except Exception as e:
            print(f"  (skip {t}: {e})")
            pass

    # Build report
    print(f"\n{'PIN':<6} {'Name':<25} {'Days':<6} {'Punches':<8} {'Hours':<8} {'Status'}")
    print("-" * 80)
    total_punches = 0
    total_hours = 0
    total_days = set()
    for pin in sorted(by_user.keys(), key=lambda x: (x or '').zfill(10)):
        recs = by_user[pin]
        # Group by date
        by_date = defaultdict(list)
        for r in recs:
            by_date[r['date']].append(r)
        days = len(by_date)
        # Sum hours per day
        day_hours = []
        for date, d_recs in by_date.items():
            _, hours = _calc_hours(d_recs)
            day_hours.append(hours)
        total_h = sum(day_hours)
        # Status
        full_days = sum(1 for h in day_hours if h >= 4)
        incomplete_days = days - full_days
        name = user_names.get(pin, '?')
        status = 'OK' if incomplete_days == 0 else f'{incomplete_days} thiếu'
        print(f"{pin:<6} {name[:24]:<25} {days:<6} {len(recs):<8} {total_h:<8.2f} {status}")
        total_punches += len(recs)
        total_hours += total_h
        total_days.update(by_date.keys())

    print(f"\nTổng: {len(by_user)} users, {len(total_days)} ngày, "
          f"{total_punches:,} punches, {total_hours:,.2f} giờ")

    # Export
    if export == 'excel':
        _export_excel(records, user_names, month)
    elif export == 'csv':
        _export_csv(records, user_names, month)


def _export_excel(records, user_names, month):
    """Xuất Excel-compatible HTML."""
    rows = ['<tr><th>PIN</th><th>Tên</th><th>Ngày</th><th>Giờ</th><th>Trạng thái</th><th>Verify</th></tr>']
    for r in records:
        rows.append(
            f'<tr><td>{r["pin"]}</td><td>{user_names.get(r["pin"], "?")}</td>'
            f'<td>{r["date"]}</td><td>{r["time"]}</td>'
            f'<td>{r["status_name"]}</td><td>{r["verify_type"]}</td></tr>'
        )
    html = (
        '<html xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:x="urn:schemas-microsoft-com:office:excel"><head>'
        '<meta charset="utf-8"><style>table{border-collapse:collapse} '
        'th,td{border:1px solid #999;padding:3px 6px} th{background:#ddd}</style>'
        f'</head><body><h2>Báo cáo chấm công {month} - BVĐK Ninh Thuận</h2>'
        f'<table>{"".join(rows)}</table></body></html>'
    )
    out = f'chamcong_{month.replace("-","")}.xls'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"📊 Đã xuất: {out} ({os.path.getsize(out):,} bytes)")


def _export_csv(records, user_names, month):
    out = f'chamcong_{month.replace("-","")}.csv'
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['PIN', 'Tên', 'Ngày', 'Giờ', 'Trạng thái', 'Verify'])
        for r in records:
            w.writerow([r['pin'], user_names.get(r['pin'], '?'),
                        r['date'], r['time'], r['status_name'], r['verify_type']])
    print(f"📄 Đã xuất: {out} ({os.path.getsize(out):,} bytes)")


def cmd_compare(conn, hr_csv, month=None):
    """So sánh danh sách NV chấm công với danh sách HR."""
    if not month:
        month = datetime.now().strftime('%Y-%m')
    print(f"\n=== SO SÁNH VỚI HR ({hr_csv}) - tháng {month} ===")
    # Read HR list (PIN column expected)
    hr_pins = set()
    hr_names = {}
    try:
        with open(hr_csv, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for r in reader:
                pin = r.get('PIN') or r.get('pin') or r.get('MaNV') or r.get('Mã NV')
                name = r.get('Name') or r.get('name') or r.get('Ten') or r.get('Tên') or ''
                if pin:
                    hr_pins.add(str(pin).strip())
                    hr_names[str(pin).strip()] = name
        print(f"HR có {len(hr_pins)} NV")
    except Exception as e:
        print(f"❌ Đọc HR file lỗi: {e}")
        return
    # Get users with attendance in month
    c = conn.cursor()
    c.execute("SELECT DISTINCT User_PIN FROM ATT_LOG WHERE substr(Verify_Time, 1, 7) = ?", [month])
    att_pins = set(r[0] for r in c.fetchall())
    print(f"Trong ATT_LOG tháng {month}: {len(att_pins)} NV")
    # Cross-check
    only_in_hr = hr_pins - att_pins
    only_in_zk = att_pins - hr_pins
    print(f"\n{'='*70}")
    print(f"⚠️  Có trong HR nhưng KHÔNG chấm công tháng {month}: {len(only_in_hr)} NV")
    if only_in_hr:
        for pin in sorted(only_in_hr, key=lambda x: x.zfill(10)):
            print(f"  - PIN {pin}: {hr_names.get(pin, '?')}")
    print(f"\n⚠️  Chấm công nhưng KHÔNG có trong HR (có thể là thực tập/khá): {len(only_in_zk)} NV")
    if only_in_zk:
        for pin in sorted(only_in_zk, key=lambda x: x.zfill(10))[:20]:
            print(f"  - PIN {pin}")
        if len(only_in_zk) > 20:
            print(f"  ... và {len(only_in_zk)-20} NV khác")


def cmd_missing(conn, date=None):
    """NV không có chấm công trong ngày cụ thể."""
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    print(f"\n=== NV KHÔNG CHẤM CÔNG NGÀY {date} ===")
    c = conn.cursor()
    # Get all users (try both tables - USER_INFO has User_PIN, USER has PIN)
    all_users = {}
    for t, col in [('USER_INFO', 'User_PIN'), ('USER', 'PIN')]:
        try:
            c.execute(f"SELECT {col}, Name FROM {t} WHERE {col} IS NOT NULL AND {col} != ''")
            for pin, name in c.fetchall():
                all_users[_safe_decode(pin)] = _safe_decode(name)
        except:
            pass
    # Get who punched on date
    c.execute("SELECT DISTINCT User_PIN FROM ATT_LOG WHERE substr(Verify_Time, 1, 10) = ?", [date])
    punched = set(_safe_decode(r[0]) for r in c.fetchall())
    missing = set(all_users.keys()) - punched
    print(f"Tổng NV trong DB: {len(all_users)}")
    print(f"NV đã chấm ngày {date}: {len(punched)}")
    print(f"NV KHÔNG chấm: {len(missing)}")
    if missing:
        print(f"\n{'PIN':<8} {'Tên'}")
        print("-" * 50)
        for pin in sorted(missing, key=lambda x: x.zfill(10)):
            print(f"{pin:<8} {all_users[pin]}")


def cmd_top(conn, limit=10, month=None):
    """Top NV theo số giờ làm / số ngày chấm."""
    if not month:
        month = datetime.now().strftime('%Y-%m')
    print(f"\n=== TOP {limit} NV CHẤM CÔNG NHIỀU NHẤT - tháng {month} ===")
    c = conn.cursor()
    c.execute("""
        SELECT User_PIN, COUNT(DISTINCT substr(Verify_Time, 1, 10)) as days,
               COUNT(*) as punches
        FROM ATT_LOG
        WHERE substr(Verify_Time, 1, 7) = ?
        GROUP BY User_PIN
        ORDER BY punches DESC
        LIMIT ?
    """, [month, limit])
    top_rows = c.fetchall()  # Fetch FIRST before running another query
    print(f"{'PIN':<8} {'Days':<8} {'Punches':<10} {'Name'}")
    print("-" * 60)
    # Names (try both tables - USER_INFO has User_PIN, USER has PIN)
    names = {}
    for t, col in [('USER_INFO', 'User_PIN'), ('USER', 'PIN')]:
        try:
            c.execute(f"SELECT {col}, Name FROM {t}")
            for pin, name in c.fetchall():
                names[_safe_decode(pin)] = _safe_decode(name)
        except:
            pass
    for pin, days, punches in top_rows:
        print(f"{pin:<8} {days:<8} {punches:<10} {names.get(pin, '?')}")


def main():
    parser = argparse.ArgumentParser(
        description='ZKDB.db query tool - truy vấn dữ liệu chấm công',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  %(prog)s info
  %(prog)s users
  %(prog)s report --month 2026-09
  %(prog)s report --month 2026-09 --user 47
  %(prog)s report --month 2026-09 --export excel
  %(prog)s compare --hr users_hr.csv --month 2026-09
  %(prog)s missing --date 2026-09-12
  %(prog)s top --limit 10
        """
    )
    parser.add_argument('--db', help='Đường dẫn ZKDB.db (mặc định: tự tìm)')
    parser.add_argument('cmd', choices=['info', 'users', 'report', 'compare',
                                          'missing', 'top'],
                        help='Lệnh thực hiện')
    parser.add_argument('--month', help='Tháng YYYY-MM (cho report/compare/top)')
    parser.add_argument('--date', help='Ngày YYYY-MM-DD (cho missing)')
    parser.add_argument('--user', help='PIN nhân viên (cho report)')
    parser.add_argument('--hr', help='File CSV HR master list (cho compare)')
    parser.add_argument('--export', choices=['csv', 'excel'],
                        help='Xuất file (cho report)')
    parser.add_argument('--limit', type=int, default=10, help='Số dòng (cho top)')
    args = parser.parse_args()

    db = args.db or find_db()
    conn = connect(db)

    if args.cmd == 'info':
        cmd_info(conn)
    elif args.cmd == 'users':
        cmd_users(conn)
    elif args.cmd == 'report':
        cmd_report(conn, args.month, args.user, args.export)
    elif args.cmd == 'compare':
        if not args.hr:
            print("❌ Cần --hr <file.csv> cho lệnh compare")
            sys.exit(1)
        cmd_compare(conn, args.hr, args.month)
    elif args.cmd == 'missing':
        cmd_missing(conn, args.date)
    elif args.cmd == 'top':
        cmd_top(conn, args.limit, args.month)

    conn.close()
    print("\n✅ Done")


if __name__ == '__main__':
    main()
