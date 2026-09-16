"""
Restore X628 PRO to safe state after 10-tests chaos
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
from zk import ZK, const

DEVICE_IP = '172.16.0.214'

zk = ZK(DEVICE_IP, port=4370, timeout=5, password=0, force_udp=False, ommit_ping=False, verbose=False)
conn = zk.connect()
print('Connected. Restoring safe state...')

# Don't change things that were correct, only reset the chaos
restores = [
    ('ServerMode', '0'),
    ('CloudEnable', '0'),
    ('ADMSMode', '1'),  # keep ADMSMode=1 (original had ADMSEnable=1 implicitly)
    ('HTTPS', '1'),  # leave HTTPS enable as-is
    ('ServerPort', '8088'),  # restore port
    ('ServerAddr', '171.15.128.4'),  # restore our IP
    ('ServerType', '0'),  # ADMS type
    ('PushMode', '2'),
]

for k, v in restores:
    try:
        cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_WRQ, (k + '=' + v).encode())
        ok = cmd_response.get('status')
        msg = 'OK' if ok else 'FAIL'
        print(f'  Restore {k}={v}: {msg}')
    except Exception as e:
        print(f'  Restore {k}={v}: ERROR ({e})')

# Verify final state
print('Final state:')
keys = ['ServerType', 'ServerAddr', 'ServerPort', 'HTTPS', 'CommType', 'PushMode', 'CommPwd']
for k in keys:
    try:
        cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_RRQ, k.encode() + b'\x00', 1024)
        if cmd_response.get('status'):
            data = conn._ZK__data
            val = data.split(b'=', 1)[-1].split(b'\x00')[0].decode('utf-8', errors='ignore') if b'=' in data else data.split(b'\x00')[0].decode('utf-8', errors='ignore')
            print(f'  {k} = {val}')
    except:
        pass

conn.disconnect()
print('\nDone. Device state restored.')
