"""Try FW 6.60 undocumented WRITE commands via ZK protocol.

Targets:
- CMD_UPDATEFROMUDISK = 0x87  - trigger USB restore
- CMD_QUERY_DATA = 0x5DF (=1503) - "Read/Write a large data set"
- CMD_TEMPDB_ADD = 0x31 - temp DB add
- CMD_BIGDATA_WRQ = 0x2748 - big data write request
"""
import sys
import time
from zk import ZK
from zk.base import ZK as ZKBase
from struct import pack

HOST = '172.16.0.214'
PIN = '1'
PWD = '891401'

def try_command(zk_obj, cmd_hex, cmd_name, payload=b'', expected_payload_size=8):
    """Try sending a raw command to the device."""
    print(f'\n🔧 Trying {cmd_name} (0x{cmd_hex:04x}) payload={payload.hex() if payload else "(empty)"}')
    try:
        resp = zk_obj._ZK__send_command(cmd_hex, payload, expected_payload_size)
        status = resp.get('status')
        code = resp.get('code')
        print(f'   Status: {status}, Code: {code} (0x{code:04x})')
        # Try to read response data
        try:
            data = zk_obj._ZK__data
            print(f'   Response data: {data!r}')
        except:
            pass
        return status, code
    except Exception as e:
        print(f'   ERR: {type(e).__name__}: {e}')
        return None, None


def main():
    print('=' * 70)
    print(f'  Testing undocumented FW 6.60 WRITE commands')
    print(f'  Device: {HOST}')
    print('=' * 70)

    z = ZK(HOST, port=4370, timeout=10, verbose=False)
    try:
        c = z.connect()
    except Exception as e:
        print(f'❌ Cannot connect: {e}')
        return

    try:
        print('\n✅ Connected. Testing commands...\n')

        # 1. CMD_UPDATEFROMUDISK = 0x87
        # This triggers USB restore - device scans USB and restores
        try_command(c, 0x87, 'CMD_UPDATEFROMUDISK')

        # 2. CMD_QUERY_DATA = 0x5DF (= 1503)
        # Try with various payloads - maybe write mode
        for fct, ext, name in [(1, 0, 'FCT_ATTLOG read'), (2, 0, 'FCT_OPLOG'), (5, 0, 'DELETE'),
                                (1, 1, 'FCT_ATTLOG ext=1')]:
            payload = pack('<bhii', 1, 0x0D, fct, ext)  # 0x0D = CMD_ATTLOG_RRQ
            try_command(c, 0x5DF, f'CMD_QUERY_DATA {name}', payload)

        # 3. CMD_TEMPDB_ADD = 0x31
        # Maybe temp DB can hold records
        for ts in [b'2026-09-14 12:00:00']:
            payload = ts + b'\x00'
            try_command(c, 0x31, 'CMD_TEMPDB_ADD with ts', payload)

        # 4. CMD_BIGDATA_WRQ = 0x2748
        try_command(c, 0x2748, 'CMD_BIGDATA_WRQ empty')
        try_command(c, 0x2748, 'CMD_BIGDATA_WRQ with ts', b'2026-09-14 12:00:00')

        # 5. CMD_UPDATE_USERS = 0x34 - might write users
        try_command(c, 0x34, 'CMD_UPDATE_USERS empty')

        # 6. CMD_SET_TIME = 0xCA - change time
        # If we change device time, maybe user can punch with old time
        # This is "time manipulation attack"
        try_command(c, 0xCA, 'CMD_SET_TIME empty')

        # 7. CMD_USERTEMP_WRQ = 0x0A - write user template
        # Maybe write user with ATT_LOG data disguised as template?
        try_command(c, 0x0A, 'CMD_USERTEMP_WRQ empty')

        # 8. CMD_SET_PULL_DATA = 0x2711
        try_command(c, 0x2711, 'CMD_SET_PULL_DATA')

        # 9. CMD_NEW_TIME_WRQ = 0x2718 - new time write
        try_command(c, 0x2718, 'CMD_NEW_TIME_WRQ')

        # 10. CMD_SET_DATA = 0xBB9
        try_command(c, 0xBB9, 'CMD_SET_DATA')

        # 11. CMD_UPDATEFILE = 0x6A4
        try_command(c, 0x6A4, 'CMD_UPDATEFILE')

        # 12. CMD_SSRUSERTEMP_WRQ = 0x84 - SSR user template write
        try_command(c, 0x84, 'CMD_SSRUSERTEMP_WRQ')

        print('\n' + '=' * 70)
        print('  Summary: Tested', 12, 'commands. Look for status=True with no error.')
        print('=' * 70)

    finally:
        c.disconnect()


if __name__ == '__main__':
    main()
