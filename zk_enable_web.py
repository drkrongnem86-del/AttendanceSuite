# -*- coding: utf-8 -*-
"""
ZK X628 PRO - ENABLE WEB SERVER + TRY CVE-2022-42953
Test enable web server qua ZK protocol options.
"""
import sys, os, struct, time, socket
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

print('=' * 70)
print(f'ZK X628 PRO - ENABLE WEB SERVER')
print('=' * 70)

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'Connected: FW={z.get_firmware_version()}')

# Try various options to enable web server
web_options = [
    'WebEnabled',
    '~WebEnabled',
    'WebServer',
    '~WebServer',
    '~EnableWebServer',
    'EnableWeb',
    '~EnableWeb',
    'WebUI',
    '~WebUI',
    '~EnableUI',
    'EnableWebUI',
    'HttpServer',
    '~HttpServer',
    '~HTTPD',
    'WebService',
    '~WebService',
    'EnableWebService',
    'WebPort',
    '~WebPort',
    'WebSSLEnabled',
    '~WebSSLEnabled',
    'EnableCommWeb',
    'EnableWebComm',
    'WebInterface',
    'WebUIEnabled',
    'EnableCommProtocol',
    'EnableHTTP',
]

# Set each option, then check if HTTP server appears
for opt in web_options:
    try:
        # Try setting = 1
        resp = z._ZK__send_command(const.CMD_OPTIONS_WRQ, (opt + '=1').encode())
        # Read back
        resp2 = z._ZK__send_command(const.CMD_OPTIONS_RRQ, opt.encode())
        code2 = resp2.get('code') if isinstance(resp2, dict) else resp2
        if code2 == 1500 or (code2 not in (4999, 65535, 2001) and code2 != 2000):
            print(f'  {opt}=1: SET={resp}, READ={resp2}')
    except Exception as e:
        err = str(e)[:30]
        if 'tcp' not in err.lower():
            print(f'  {opt}=1: {err}')

# Also try with various values
print('\n[2] Try specific web port options...')
port_options = [
    ('WebPort', '80'),
    ('~WebPort', '80'),
    ('WebPort', '8080'),
    ('~WebPort', '8080'),
    ('HTTP_PORT', '80'),
    ('~HTTP_PORT', '80'),
]
for opt, val in port_options:
    try:
        resp = z._ZK__send_command(const.CMD_OPTIONS_WRQ, (opt + '=' + val).encode())
        resp2 = z._ZK__send_command(const.CMD_OPTIONS_RRQ, opt.encode())
        code2 = resp2.get('code') if isinstance(resp2, dict) else resp2
        if code2 not in (4999, 65535):
            print(f'  {opt}={val}: SET={resp}, READ={resp2}')
    except Exception as e:
        pass

# Try restart to see if web server comes up
print('\n[3] Restart device to apply web server options...')
try:
    resp = z._ZK__send_command(const.CMD_RESTART, b'')
    print(f'  RESTART: {resp}')
except Exception as e:
    print(f'  RESTART: {e}')

# Wait for restart
print('  Waiting 60s for device restart...')
time.sleep(60)

# Reconnect
print('\n[4] Reconnect + check for web ports...')
try:
    z.disconnect()
except:
    pass

z2 = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
try:
    z2.connect()
    print(f'  Reconnected')

    # Check ports
    web_check_ports = [80, 443, 8080, 8443, 8000, 8088, 8888, 9999, 5000]
    for port in web_check_ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((DEVICE_IP, port))
            s.send(f'GET /form/DataApp?style=1 HTTP/1.0\r\nHost: {DEVICE_IP}\r\n\r\n'.encode())
            data = s.recv(4096)
            s.close()
            if data:
                print(f'  TCP/{port}: {data[:100]!r}')
        except Exception as e:
            pass
except Exception as e:
    print(f'  Reconnect failed: {e}')

z2.disconnect()

# Try on second device too (May 20)
print('\n[5] Same test on May 20 (172.16.8.139)...')
DEVICE_IP2 = '172.16.8.139'
z3 = zk.ZK(DEVICE_IP2, port=4370, timeout=10, password=0)
try:
    z3.connect()
    print(f'  Connected: FW={z3.get_firmware_version()}')

    # Set web options
    for opt in ['~WebServer=1', '~WebEnabled=1', 'WebUIEnabled=1', '~EnableUI=1']:
        try:
            z3._ZK__send_command(const.CMD_OPTIONS_WRQ, opt.encode())
        except:
            pass

    # Restart
    try:
        z3._ZK__send_command(const.CMD_RESTART, b'')
    except:
        pass

    print('  Waiting 30s...')
    time.sleep(30)

    z3.disconnect()
except Exception as e:
    print(f'  May 20 failed: {e}')

# Check May 20 ports after restart
print('\n  Check May 20 ports...')
for port in [80, 443, 8080, 8443, 8000, 8088, 9999, 5000]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((DEVICE_IP2, port))
        s.send(f'GET /form/DataApp?style=1 HTTP/1.0\r\nHost: {DEVICE_IP2}\r\n\r\n'.encode())
        data = s.recv(4096)
        s.close()
        if data:
            print(f'  May20 TCP/{port}: {data[:100]!r}')
    except:
        pass

print('\nDONE')
