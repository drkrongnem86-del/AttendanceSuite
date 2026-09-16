"""Comprehensive health check of all known ZK devices + nearby subnet scan"""
import os
import sys
import socket
import requests
import urllib3
urllib3.disable_warnings()

sys.stdout.reconfigure(encoding='utf-8')

print('='*70)
print('ZK DEVICE HEALTH CHECK')
print('='*70)

# IPs known to be reachable
known_ips = [
    ('172.16.0.214', 'May 3 protocol'),
    ('172.16.0.214', 'May 3 web (might differ)'),
    ('172.16.8.139', 'May 20 protocol'),
    ('172.16.254.202', 'May 3 web UI (May 14 2018 fw)'),
    ('172.16.200.105', 'ADMS server'),
    ('172.16.0.31', 'Secutime'),
]

ports_to_check = [
    (80, 'HTTP Web UI'),
    (443, 'HTTPS Web UI'),
    (4370, 'ZK protocol'),
    (8088, 'ADMS Push'),
    (4368, 'ZK legacy TCP'),
    (8080, 'HTTP alt'),
    (8443, 'HTTPS alt'),
]

# 1. Known devices
print('\n--- Known Devices ---')
for ip, label in known_ips:
    print(f'\n{label} ({ip}):')
    for port, desc in ports_to_check:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            result = s.connect_ex((ip, port))
            if result == 0:
                print(f'  port {port:5d} OPEN ({desc})')
            s.close()
        except (socket.timeout, socket.error, OSError) as e:
            pass
        except Exception as e:
            pass

# 2. Quick subnet scan (172.16.0.x/24 + 172.16.8.x/24 + 172.16.254.x)
print('\n--- Subnet Scan (looking for ZK devices) ---')
subnets = [
    ('172.16.0', list(range(1, 255))),
    ('172.16.8', list(range(1, 255))),
    ('172.16.254', list(range(1, 255))),
]

found_devices = []

for subnet_base, hosts in subnets:
    for h in hosts:
        ip = f'{subnet_base}.{h}'
        if ip in [i for i, _ in known_ips]:
            continue
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            result = s.connect_ex((ip, 4370))  # ZK protocol port
            if result == 0:
                print(f'  ZK device at {ip}')
                found_devices.append(ip)
            s.close()
        except Exception:
            pass

print(f'\nTotal found via port 4370: {len(found_devices)} devices')

# 3. Probe each found device for web/HTTPS
print('\n--- Web Access Probe ---')
for ip in found_devices:
    for port in [80, 443, 8088]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            if s.connect_ex((ip, port)) == 0:
                if port == 80:
                    try:
                        r = requests.get(f'http://{ip}/form/DataApp?style=1', timeout=5)
                        print(f'  {ip}:80 - {r.status_code} len={len(r.content)}, head={r.content[:15]!r}')
                    except Exception as e:
                        print(f'  {ip}:80 - err {type(e).__name__}')
                elif port == 443:
                    try:
                        r = requests.get(f'https://{ip}/form/DataApp?style=1', timeout=5, verify=False)
                        print(f'  {ip}:443 - {r.status_code} len={len(r.content)}, head={r.content[:15]!r}')
                    except Exception as e:
                        print(f'  {ip}:443 - err {type(e).__name__}')
                elif port == 8088:
                    try:
                        r = requests.get(f'http://{ip}:8088/iclock/cdata?SN=test&options=all&pushver=2.4.1', timeout=5)
                        print(f'  {ip}:8088 - {r.status_code} len={len(r.content)}, head={r.content[:80]!r}')
                    except Exception as e:
                        print(f'  {ip}:8088 - err {type(e).__name__}')
            s.close()
        except Exception:
            pass

print('\n' + '='*70)
print('HEALTH CHECK COMPLETE')
print('='*70)