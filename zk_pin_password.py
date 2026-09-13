"""
zk_pin_password.py - Test và verify PIN+password trên máy ZK
Workflow:
  1. Nhập IP máy, PIN, password
  2. Kết nối pyzk (comm key 0)
  3. Đọc user từ DB, check password
  4. Report kết quả: OK / FAIL
  5. Nếu OK → hướng dẫn NV đứng trước máy chấm

Cú pháp:
  python zk_pin_password.py <ip> <pin> <password>
  python zk_pin_password.py <ip> --list-users  # List all users with password
  python zk_pin_password.py <ip> --list-password-users  # List only users with password
  python zk_pin_password.py <ip> --inject <pin> <password>  # Tạo user test
"""
import sys
import argparse
import time
import csv
from zk import ZK
from datetime import datetime

DEFAULT_DEVICES_CSV = r"D:\chamcong\devices.csv"


def get_zk_connection(ip, comm_key=0, timeout=5):
    """Kết nối tới máy ZK"""
    zk = ZK(ip, port=4370, timeout=timeout, password=comm_key)
    return zk.connect()


def list_users(ip, only_with_password=True):
    """List users từ máy ZK"""
    print(f"\n=== Kết nối tới {ip} ===")
    conn = get_zk_connection(ip)
    print(f"  FW: {conn.get_firmware_version()}")
    print(f"  Serial: {conn.get_serialnumber()}")

    users = conn.get_users()
    print(f"  Total users: {len(users)}")
    pwd_users = [u for u in users if u.password and u.password != '']
    print(f"  Users với password: {len(pwd_users)}")

    if only_with_password:
        users_to_show = pwd_users
    else:
        users_to_show = users

    print(f"\n  {'PIN':<8} {'Name':<25} {'Password':<10} {'Privilege':<10} {'UID':<8}")
    print(f"  {'-'*8} {'-'*25} {'-'*10} {'-'*10} {'-'*8}")
    for u in users_to_show[:50]:
        pin = u.user_id or 'N/A'
        name = (u.name or '')[:24]
        pwd = (u.password or '')[:8]
        priv = u.privilege
        uid = u.uid
        print(f"  {pin:<8} {name:<25} {pwd:<10} {priv:<10} {uid:<8}")

    if len(users_to_show) > 50:
        print(f"  ... and {len(users_to_show) - 50} more")

    conn.disconnect()
    return users


def verify_pin_password(ip, pin, password):
    """Verify PIN + password trên máy ZK"""
    print(f"\n=== Test PIN+password trên {ip} ===")
    print(f"  PIN: {pin}")
    print(f"  Password: {password!r}")

    conn = get_zk_connection(ip)

    # Get all users
    users = conn.get_users()
    user_dict = {u.user_id: u for u in users}

    # Find user
    if str(pin) not in user_dict:
        print(f"  ❌ FAIL: PIN {pin} không tồn tại trên máy")
        print(f"     Available PINs: {list(user_dict.keys())[:20]}")
        conn.disconnect()
        return False

    user = user_dict[str(pin)]
    print(f"  Found: PIN={user.user_id} name={user.name!r} privilege={user.privilege}")
    print(f"  DB password: {user.password!r}")

    # Compare
    if not user.password or user.password == '':
        print(f"  ❌ FAIL: User này chưa có password trong DB")
        print(f"     → Cần tạo password trước (qua menu hoặc pyzk set_user)")
        conn.disconnect()
        return False

    if user.password == str(password):
        print(f"  ✅ MATCH: Password đúng!")
        print(f"\n  💡 HƯỚNG DẪN CHO NV:")
        print(f"     1. Đứng trước máy ZK")
        print(f"     2. Nhấn Menu (M) → Verification Mode → Password")
        print(f"        HOẶC thẳng nhập PIN + password")
        print(f"     3. Nhập: PIN = {user.user_id} → OK")
        print(f"     4. Nhập: Password = {password} → OK")
        print(f"     5. Máy sẽ ghi ATTLOG với Verify_Type=0 (Password)")
        conn.disconnect()
        return True
    else:
        print(f"  ❌ MISMATCH: Password KHÔNG khớp")
        print(f"     DB:   {user.password!r}")
        print(f"     Input: {password!r}")
        conn.disconnect()
        return False


def inject_user_with_password(ip, pin, name, password, privilege=0):
    """Tạo user mới với password qua pyzk"""
    print(f"\n=== Inject user mới trên {ip} ===")
    conn = get_zk_connection(ip)

    try:
        conn.set_user(uid=int(pin), name=name, privilege=privilege, password=str(password))
        print(f"  ✅ Created PIN={pin} name={name!r} pwd={password!r} priv={privilege}")

        # Verify
        users = conn.get_users()
        user = next((u for u in users if u.user_id == str(pin)), None)
        if user:
            print(f"  Verify: {user.name!r} password={user.password!r}")
    except Exception as e:
        print(f"  ❌ FAIL: {e}")

    conn.disconnect()


def update_user_password(ip, pin, new_password):
    """Update password cho user hiện tại"""
    print(f"\n=== Update password cho PIN {pin} trên {ip} ===")
    conn = get_zk_connection(ip)

    users = conn.get_users()
    user = next((u for u in users if u.user_id == str(pin)), None)

    if not user:
        print(f"  ❌ PIN {pin} không tồn tại")
        conn.disconnect()
        return

    try:
        conn.set_user(uid=int(pin), name=user.name, privilege=user.privilege, password=str(new_password))
        print(f"  ✅ Updated: PIN={pin} password={new_password!r}")
    except Exception as e:
        print(f"  ❌ FAIL: {e}")

    conn.disconnect()


def bulk_set_password(ip, password='1', limit=100):
    """Set password='1' cho tất cả users (workaround)"""
    print(f"\n=== Bulk set password='{password}' cho tất cả users trên {ip} ===")
    conn = get_zk_connection(ip)

    users = conn.get_users()
    no_pwd = [u for u in users if not u.password or u.password == '']
    print(f"  Users chưa có password: {len(no_pwd)}")

    count = 0
    for u in no_pwd[:limit]:
        try:
            conn.set_user(uid=u.uid, name=u.name, privilege=u.privilege, password=password)
            count += 1
        except Exception as e:
            print(f"    PIN {u.user_id} FAIL: {e}")

    print(f"  ✅ Set password cho {count}/{len(no_pwd[:limit])} users")
    conn.disconnect()


def main():
    parser = argparse.ArgumentParser(description="ZK PIN+Password test tool")
    parser.add_argument('ip', help='IP máy ZK')
    parser.add_argument('pin', nargs='?', help='PIN nhân viên')
    parser.add_argument('password', nargs='?', help='Password')

    parser.add_argument('--list-users', action='store_true', help='List all users')
    parser.add_argument('--list-password-users', action='store_true', help='List users with password')
    parser.add_argument('--inject', nargs=3, metavar=('PIN', 'NAME', 'PASSWORD'),
                        help='Inject user with password')
    parser.add_argument('--update-password', nargs=2, metavar=('PIN', 'PASSWORD'),
                        help='Update password for user')
    parser.add_argument('--bulk-set', metavar='PASSWORD',
                        help='Bulk set password cho users chưa có')
    parser.add_argument('--comm-key', type=int, default=0, help='Comm Key (default 0)')

    args = parser.parse_args()

    try:
        if args.list_users:
            list_users(args.ip, only_with_password=False)
        elif args.list_password_users:
            list_users(args.ip, only_with_password=True)
        elif args.inject:
            pin, name, pwd = args.inject
            inject_user_with_password(args.ip, pin, name, pwd)
        elif args.update_password:
            pin, pwd = args.update_password
            update_user_password(args.ip, pin, pwd)
        elif args.bulk_set:
            bulk_set_password(args.ip, args.bulk_set)
        elif args.pin and args.password:
            verify_pin_password(args.ip, args.pin, args.password)
        else:
            parser.print_help()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
