import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
from zk import ZK, const

zk = ZK('172.16.0.214', port=4370, timeout=5, password=0, force_udp=False, ommit_ping=False, verbose=False)
conn = zk.connect()

# Reset HTTPS=0 (was bumped to 1 during testing)
cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_WRQ, b'HTTPS=0')
ok = cmd_response.get('status')
print('HTTPS=0:', 'OK' if ok else 'FAIL')

cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_WRQ, b'HTTPEnable=1')
ok = cmd_response.get('status')
print('HTTPEnable=1:', 'OK' if ok else 'FAIL')

conn.disconnect()
print('Device HTTPS restored to HTTP mode')
