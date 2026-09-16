# -*- coding: utf-8 -*-
import sys, struct, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
import zk
from zk import const

DEVICE_IP = '172.16.0.214'

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print('Connected')

# Subscribe
print('\n[1] Subscribe events...')
resp = z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', 0xFF))
print(f'  REG_EVENT 0xFF: {resp}')

# Read RTLOG immediately
print('\n[2] RTLOG right after subscription...')
resp = z._ZK__send_command(0x5A, b'', response_size=8192)
data = z._ZK__data
print(f'  Code: {resp}, data_len: {len(data) if data else 0}')
if data and len(data) > 4:
    total = struct.unpack('<I', data[:4])[0]
    print(f'  Total: {total}')
    print(f'  First 200 bytes: {data[4:204].hex()}')

# Try various write commands related to RTLOG
print('\n[3] Test commands 0x58-0x68...')
for cmd in range(0x58, 0x69):
    try:
        resp = z._ZK__send_command(cmd, b'', response_size=1024)
        code = resp.get('code') if isinstance(resp, dict) else resp
        data = z._ZK__data
        if data and len(data) > 0:
            print(f'  CMD 0x{cmd:04X}: code={code} data_len={len(data)}')
        else:
            print(f'  CMD 0x{cmd:04X}: code={code}')
    except Exception as e:
        print(f'  CMD 0x{cmd:04X}: {str(e)[:30]}')

# Test specific WRITE candidates
print('\n[4] Test some undocumented write candidates...')
undocumented = [
    0x31,  # CMD_TEMPDB_ADD (already tested - all 65535)
    0x33,  # CMD_GET_DATA_LAYOUT
    0x34,  # CMD_UPDATE_USERS
    0x35,  # CMD_UPDATE_TEMP
    0x3D,  # CMD_STARTENROLL (could trigger enroll state)
    0x77,  # CMD_HASH_DATA (needs payload)
    0x84,  # CMD_SSRUSERTEMP_WRQ
    0x85,  # CMD_SSRDELETE_USER
]
for cmd in undocumented:
    try:
        # Test with simple payload
        for payload in [b'', b'\x01\x00\x00\x00', b'1']:
            try:
                resp = z._ZK__send_command(cmd, payload)
                code = resp.get('code') if isinstance(resp, dict) else resp
                if code not in (65535,):
                    print(f'  CMD 0x{cmd:04X} {payload!r}: code={code}')
            except Exception as e:
                pass
    except Exception as e:
        pass

z.disconnect()
print('\nDone')
