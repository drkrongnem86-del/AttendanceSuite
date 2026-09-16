"""
zk_firmware_extract.py
=======================

Try to extract firmware binary from X628 PRO via:
1. CMD_READFILE (0x6A6) — ZK protocol command for file download
2. CMD_DATA_WRRQ — alternative file read
3. CMD_OPTIONS_DECIPHERING (0x6AE) — encrypted file option
4. Web UI 172.16.254.202 — separate web interface (may have FW download)
5. Various known firmware paths on the device

BEFORE/AFTER logging for safe testing.
"""

import sys
import time
import socket
import struct
import json
import os
import requests
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')

from zk import ZK, const


DEVICE_PROTOCOL_IP = '172.16.0.214'
DEVICE_WEB_IP = '172.16.254.202'
LOG_DIR = r'D:\chamcong\zk_fw_attempts'
os.makedirs(LOG_DIR, exist_ok=True)


def log_event(event_type, **data):
    record = {
        'time': datetime.now().isoformat(),
        'event': event_type,
        **data,
    }
    log_file = os.path.join(LOG_DIR, 'fw_extract_log.jsonl')
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, default=str) + '\n')
    return record


def connect_protocol(timeout=5):
    zk = ZK(DEVICE_PROTOCOL_IP, port=4370, timeout=timeout, password=0, force_udp=False, ommit_ping=False, verbose=False)
    return zk.connect()


def snapshot_state(conn):
    """Capture device state BEFORE"""
    conn.read_sizes()
    state = {
        'records': conn.records,
        'users': conn.users,
        'fingers': conn.fingers,
        'firmware': conn.get_firmware_version(),
        'platform': conn.get_platform(),
        'device_name': conn.get_device_name(),
        'serial': conn.get_serialnumber(),
    }
    # Read key options
    for k in ['ServerType', 'ServerAddr', 'ServerPort', 'HTTPS', 'CommType', 'PushMode', 'CommPwd', 'ADMSMode']:
        try:
            cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_RRQ, k.encode() + b'\x00', 1024)
            if cmd_response.get('status'):
                data = conn._ZK__data
                val = data.split(b'=', 1)[-1].split(b'\x00')[0].decode('utf-8', errors='ignore') if b'=' in data else data.split(b'\x00')[0].decode('utf-8', errors='ignore')
                state[k] = val
        except:
            pass
    return state


def try_readfile(conn, filename):
    """Try CMD_READFILE (0x6A6)"""
    try:
        cmd_response = conn._ZK__send_command(const.CMD_READFILE, filename.encode() + b'\x00', 65536)
        if cmd_response.get('status'):
            data = conn._ZK__data
            if len(data) > 8:
                return data[8:]  # skip header
        return None
    except Exception as e:
        return None


def try_updatefile(conn, filename):
    """Try CMD_UPDATEFILE (0x6A4) - for upload but may indicate file existence"""
    try:
        cmd_response = conn._ZK__send_command(const.CMD_UPDATEFILE, filename.encode() + b'\x00', 1024)
        return cmd_response.get('status', False)
    except:
        return None


def try_options_deciphering(conn):
    """Try CMD_OPTIONS_DECIPHERING (0x6AE) - decrypt options"""
    try:
        cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_DECIPHERING, b'', 1024)
        if cmd_response.get('status'):
            data = conn._ZK__data
            return data[8:].hex() if len(data) > 8 else None
        return None
    except:
        return None


def try_query_data(conn, table='ATTLOG'):
    """Try CMD_QUERY_DATA (0x5DF)"""
    try:
        cmd_response = conn._ZK__send_command(const.CMD_QUERY_DATA, table.encode() + b'\x00', 1024)
        return cmd_response.get('status', False)
    except:
        return None


def main():
    print('=' * 70)
    print('ZK Firmware Extract — Phase 1: Protocol-based attempts')
    print('=' * 70)

    # Connect
    try:
        conn = connect_protocol()
    except Exception as e:
        print(f'Cannot connect to {DEVICE_PROTOCOL_IP}: {e}')
        return

    # BEFORE snapshot
    print('\n[BEFORE] State snapshot...')
    before = snapshot_state(conn)
    print(json.dumps(before, indent=2, default=str))
    log_event('before_snapshot', state=before)

    # Test 1: CMD_READFILE with various firmware paths
    print('\n[TEST 1] CMD_READFILE on various paths')
    firmware_paths = [
        '/mnt/mtdblock/firmware.bin',
        '/mnt/mtdblock/firmware',
        '/firmware/firmware.bin',
        '/firmware.bin',
        '/mnt/mtdblock/data/firmware.bin',
        '/mnt/mtdblock/data/firmware',
        '/firmware',
        '/firmware.img',
        '/mnt/mtdblock/img/firmware.bin',
        '/mnt/mtdblock/img/firmware',
        '/usr/data/firmware.bin',
        '/data/firmware.bin',
        '/var/firmware.bin',
        '/tmp/firmware.bin',
        '/home/firmware.bin',
        'firmware.bin',
        'firmware',
        'fw.bin',
        'fw',
        # SQLite database paths (in case fw is stored as SQLite blob)
        '/mnt/mtdblock/data/ZKDB.db',
        '/data/ZKDB.db',
        'ZKDB.db',
        '/data/data.db',
        '/userdata/user.db',
        # Common ZK paths
        '/mnt/mtdblock/config/config.ini',
        '/mnt/mtdblock/config.ini',
        '/config.ini',
        '/mnt/mtdblock/data/config.ini',
    ]

    readfile_results = []
    for path in firmware_paths:
        data = try_readfile(conn, path)
        if data and len(data) > 0:
            print(f'  [HIT] {path} -> {len(data)} bytes')
            # Save first KB to file
            sample = data[:min(2048, len(data))]
            sample_file = os.path.join(LOG_DIR, f'readfile_{path.replace("/", "_")}_sample.bin')
            with open(sample_file, 'wb') as f:
                f.write(sample)
            readfile_results.append({'path': path, 'size': len(data), 'sample_file': sample_file})
            log_event('readfile_hit', path=path, size=len(data))
        else:
            print(f'  [---] {path}')

    if not readfile_results:
        print('  No files readable via CMD_READFILE')

    # Test 2: CMD_UPDATEFILE (check if file exists - upload probe)
    print('\n[TEST 2] CMD_UPDATEFILE probe (file existence check)')
    updatefile_results = []
    for path in firmware_paths[:10]:  # just test first 10
        ok = try_updatefile(conn, path)
        if ok:
            print(f'  [EXISTS?] {path}')
            updatefile_results.append(path)
            log_event('updatefile_exists', path=path)

    # Test 3: CMD_OPTIONS_DECIPHERING
    print('\n[TEST 3] CMD_OPTIONS_DECIPHERING')
    deciph = try_options_deciphering(conn)
    if deciph:
        print(f'  [DATA] {len(deciph)} hex chars: {deciph[:200]}...')
        log_event('decipher_data', size=len(deciph), data_preview=deciph[:200])
    else:
        print('  No data or rejected')

    # Test 4: CMD_QUERY_DATA on various tables
    print('\n[TEST 4] CMD_QUERY_DATA on tables')
    tables = ['ATTLOG', 'OPERLOG', 'USERINFO', 'FINGERTMP', 'FACE', 'BIODATA', 'USERPIC', 'SMS', 'BIODATA']
    for table in tables:
        ok = try_query_data(conn, table)
        print(f'  {table}: {"OK" if ok else "FAIL"}')

    # AFTER snapshot
    print('\n[AFTER] State snapshot...')
    after = snapshot_state(conn)
    print(json.dumps(after, indent=2, default=str))
    log_event('after_snapshot', state=after)

    # Compare BEFORE/AFTER
    if before['records'] == after['records']:
        print(f'\n[SAFE] ATTLOG count unchanged: {before["records"]}')
    else:
        print(f'\n[WARNING] ATTLOG count changed: {before["records"]} -> {after["records"]}')

    conn.disconnect()

    # Test 5: Web UI probe
    print('\n' + '=' * 70)
    print('Phase 2: Web UI 172.16.254.202 endpoint scan')
    print('=' * 70)

    web_paths = [
        '/',
        '/index.html',
        '/cgi-bin/',
        '/cgi-bin/firmware',
        '/cgi-bin/firmware.cgi',
        '/cgi-bin/getfirmware',
        '/firmware',
        '/firmware.bin',
        '/fw.bin',
        '/api/',
        '/api/firmware',
        '/api/v1/firmware',
        '/api/v1/device/firmware',
        '/download',
        '/download/firmware',
        '/fwupdate',
        '/fwupdate.ashx',
        '/firmware_update',
        '/update',
        '/Device.cgf',
        '/Device.dat',
        '/Person.cgf',
        '/Person.dat',
        '/AttLog.cgf',
        '/AttLog.dat',
        '/ZKDB.db',
        '/form/DataApp?style=1',
        '/form/DataApp?style=0',
    ]

    print(f'\n[TEST 5] HTTP probe on {DEVICE_WEB_IP}')
    web_results = []
    for path in web_paths:
        for proto in ['http', 'https']:
            url = f'{proto}://{DEVICE_WEB_IP}{path}'
            try:
                r = requests.get(url, timeout=3, verify=False)
                print(f'  [{r.status_code}] {url} ({len(r.content)} bytes)')
                if r.status_code in [200, 401, 403] and len(r.content) > 100:
                    web_results.append({'url': url, 'status': r.status_code, 'size': len(r.content), 'content_preview': r.text[:200]})
                    log_event('web_hit', url=url, status=r.status_code, size=len(r.content))
            except requests.exceptions.RequestException as e:
                if 'timed out' in str(e) or 'Connection refused' in str(e) or 'ConnectTimeout' in str(e):
                    pass  # skip timeouts/refused
                else:
                    print(f'  [ERR ] {url}: {type(e).__name__}')
            except Exception as e:
                pass

    if not web_results:
        print('  No interesting web responses')

    # Save full report
    report = {
        'timestamp': datetime.now().isoformat(),
        'before': before,
        'after': after,
        'readfile_results': readfile_results,
        'updatefile_results': updatefile_results,
        'decipher_data': deciph,
        'web_results': web_results,
    }
    out = os.path.join(LOG_DIR, f'fw_extract_report_{int(time.time())}.json')
    with open(out, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f'\nFull report saved: {out}')


if __name__ == '__main__':
    main()
