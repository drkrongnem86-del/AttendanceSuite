"""Quick port check without f-string issues"""
import socket
for port in [443, 8443, 8088, 80]:
    s = socket.socket()
    s.settimeout(3)
    r = s.connect_ex(('172.16.254.202', port))
    status = 'OPEN' if r == 0 else 'closed'
    print(f'Port {port}: {status}')
    s.close()