"""Test if writing a user via CMD_DATA_WRRQ triggers anything."""
import struct
from zk import ZK

HOST = '172.16.0.214'

def main():
    z = ZK(HOST, port=4370, timeout=10, verbose=False)
    c = z.connect()

    # Build user write payload - per pyzk source: uid(2) + userid(24) + name(24) + cardno(4) + pwd(8) + admin(1)
    uid = struct.pack('<H', 9999)
    userid = b'TEST9999' + b'\x00' * 16
    name = b'Test User' + b'\x00' * 15
    cardno = struct.pack('<I', 0)
    pwd = b'1234' + b'\x00' * 4
    admin = struct.pack('<B', 0)  # 0=regular user
    payload = uid + userid + name + cardno + pwd + admin
    print(f'User write payload: {len(payload)} bytes')

    # Try CMD_USER_WRQ (8) directly
    print('\n=== Test CMD_USER_WRQ (8) direct ===')
    resp = c._ZM__send_command(8, payload) if hasattr(c, '_ZM__send_command') else c._ZK__send_command(8, payload, 8)
    print(f'  status={resp.get("status")} code={resp.get("code")}')
    if resp.get('status'):
        # Verify user was written
        users = c.get_users()
        for u in users:
            if u.user_id == 'TEST9999':
                print(f'  ✓ User created: {u.name} priv={u.privilege}')
                break

    # Now try sending this same payload via CMD_DATA_WRRQ with fct variations
    print('\n=== Test CMD_DATA_WRRQ (1503) with fct=1 to force write ===')
    for fct in [0, 1, 2]:
        wrapper = struct.pack('<bhii', 1, 8, fct, 0)  # cmd=8 USER_WRQ
        resp = c._ZK__send_command(0x5DF, wrapper + payload, 8)
        print(f'  fct={fct}: status={resp.get("status")} code={resp.get("code")}')

    # Try CMD_OPTIONS_WRQ with magic key
    print('\n=== Test magic option write ===')
    magic_options = [
        '~WriteEnable=1',
        'WriteEnable=1',
        '~WriteEnabled=1',
        '~DebugMode=1',
        '~DevMode=1',
        '~SecretMode=1',
        'Unlock=1',
        '~Unlock=1',
        'EnableService=1',
        '~EnableService=1',
    ]
    for opt in magic_options:
        resp = c._ZK__send_command(12, (opt + '\x00').encode(), 8)
        st = resp.get('status')
        if st:
            print(f'  {opt:30s}: OK')

    c.disconnect()


if __name__ == '__main__':
    main()
