import sys
sys.path.insert(0, 'D:\\chamcong\\AttendanceSuite_Portable\\python\\Lib\\site-packages')
sys.stdout.reconfigure(encoding='utf-8')
from zk import ZK
conn = ZK('172.16.0.214', timeout=10).connect()
print('helper attrs:', [a for a in dir(conn.helper) if not a.startswith('_')])
print('tcp:', type(conn.tcp))
