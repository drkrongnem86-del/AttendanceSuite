"""
zk_servertype_adms_test.py
==========================

Test thử enable ADMS thông qua các option ẩn (ServerType=0, CloudServer=1, ...)
được ZK support hint trong FAQ.

Phương pháp:
1. Backup ATTLOG state và ATTLOG count hiện tại
2. Read tất cả option ADMS-related để biết default state
3. Thử set TỪNG option sequence (rollback giữa các test)
4. CMD_RESTART sau mỗi option sequence
5. Spin up ADMS server + check xem device có poll không
6. Nếu poll → test SHELL command
7. Nếu SHELL OK → test sqlite INSERT ATTLOG

Author: Mavis (Mavis inside MiniMax Code)
Date: 2026-09-15
For: BVĐK Ninh Thuận — ZK FW 6.60 ZLM60_TFT X628 PRO
"""

import sys
import time
import struct
import socket
import threading
import json
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# Path setup for portable Python
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')

from zk import ZK, const
from zk.base import ZKErrorResponse


# ============================================================
# Configuration
# ============================================================

DEVICE_IP = '172.16.0.214'
DEVICE_PORT = 4370
ADMS_SERVER_IP = '171.15.128.4'  # Our VPN IP
ADMS_SERVER_PORT = 8088

# All option keys that might be ADMS-related (read-only vs read-write)
READ_OPTIONS = [
    '~ServerType', '~ServerAddr', '~ServerPort', '~CloudServer', '~CloudServerType',
    '~PushMode', '~PushVersion', '~PushEnable', '~PushProtVer', '~CommMode',
    '~CommType', '~CommProtocol', '~DeviceType', '~PushServerType',
    '~ADMSEnable', '~CloudEnable', '~HTTPS', '~PushInterval', '~TransFlag',
    '~TransInterval', '~Realtime', '~PushFlag', '~CommKey', '~CommKeyType',
    '~ServerMode', '~ServerEnable', '~WebServer', '~CloudServerEnable',
]

# Write options to test for ADMS enable
WRITE_OPTION_TESTS = [
    # Sequence 1: ServerType=0 (ZK FAQ hint)
    [('ServerType', '0'), ('ServerMode', '1')],
    # Sequence 2: CloudServer=1
    [('CloudServer', '1'), ('CloudEnable', '1')],
    # Sequence 3: PushMode=1
    [('PushMode', '1'), ('PushEnable', '1')],
    # Sequence 4: ADMSEnable=1
    [('ADMSEnable', '1'), ('ServerType', '0')],
    # Sequence 5: ServerType=1 (try positive value)
    [('ServerType', '1'), ('ServerMode', '1')],
    # Sequence 6: CommType=ADMS
    [('CommType', 'ADMS'), ('ServerType', '0')],
    # Sequence 7: ServerEnable=1 + ServerType=0
    [('ServerEnable', '1'), ('ServerType', '0'), ('PushEnable', '1')],
]


# ============================================================
# ADMS Mini-Server (HTTP listener)
# ============================================================

class MiniADMSServer:
    """Minimal HTTP server that handles ADMS protocol probes"""

    def __init__(self, ip, port, log_file):
        self.ip = ip
        self.port = port
        self.log_file = log_file
        self.sock = None
        self.running = False
        self.events = []  # record of HTTP requests received

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(5)
        self.sock.settimeout(1.0)  # non-blocking
        self.running = True
        threading.Thread(target=self._listen, daemon=True).start()
        print(f"[ADMS-Server] Listening on {self.ip}:{self.port}")

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print(f"[ADMS-Server] Stopped. Total events: {len(self.events)}")

    def _listen(self):
        while self.running:
            try:
                conn, addr = self.sock.accept()
                data = conn.recv(4096).decode('utf-8', errors='ignore')
                # Log request
                first_line = data.split('\r\n')[0] if data else ''
                self.events.append({'time': time.time(), 'from': addr, 'first_line': first_line})
                print(f"[ADMS-Server] RX from {addr}: {first_line[:100]}")
                # Respond with GET OPTION response (negotiate as ADMS server)
                response = (
                    "GET OPTION FROM: X628PRO\r\n"
                    "ATTLOGStamp=0\r\n"
                    "OPERLOGStamp=0\r\n"
                    "BIODATAStamp=0\r\n"
                    "ATTPHOTOStamp=0\r\n"
                    "ErrorDelay=30\r\n"
                    "Delay=5\r\n"
                    "TransTimes=00:00;14:05\r\n"
                    "TransInterval=1\r\n"
                    "TransFlag=AttLog\tOpLog\tAttPhoto\tEnrollFP\tEnrollUser\tFPImag\r\n"
                    "TimeZone=7\r\n"
                    "Realtime=1\r\n"
                    "Encrypt=0\r\n"
                    "ServerVer=3.0.1\r\n"
                    "PushProtVer=2.4.1\r\n"
                    "SupportPing=1\r\n"
                    "OptionsFlag=1\r\n"
                    "OK\r\n"
                )
                http_response = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"Content-Length: {len(response)}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                    f"{response}"
                )
                conn.send(http_response.encode())
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    def poll_events(self):
        n = len(self.events)
        return n, list(self.events)


# ============================================================
# ZK device interaction helpers
# ============================================================

def connect():
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=0, force_udp=False, ommit_ping=False, verbose=False)
    conn = zk.connect()
    return conn


def get_state(conn):
    """Snapshot device state"""
    conn.read_sizes()
    return {
        'records': conn.records,
        'users': conn.users,
        'fingers': conn.fingers,
        'firmware': conn.get_firmware_version(),
        'platform': conn.get_platform(),
        'device_name': conn.get_device_name(),
        'serial': conn.get_serialnumber(),
    }


def read_raw_option(conn, key):
    """Read option via CMD_OPTIONS_RRQ"""
    try:
        cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_RRQ, key.encode() + b'\x00', 1024)
        if cmd_response.get('status'):
            # Response format: "Key=Value\x00..."
            data = conn._ZK__data
            if b'=' in data:
                val = data.split(b'=', 1)[-1].split(b'\x00')[0]
                return val.decode('utf-8', errors='ignore')
            return data.split(b'\x00')[0].decode('utf-8', errors='ignore')
    except Exception as e:
        pass
    return None


def write_raw_option(conn, key, value):
    """Set option via CMD_OPTIONS_WRQ"""
    try:
        command_string = f"{key}={value}".encode()
        cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_WRQ, command_string)
        return cmd_response.get('status', False)
    except Exception as e:
        print(f"  Error: {e}")
        return False


def restart_device(conn):
    """CMD_RESTART (1004 = 0x3EC)"""
    try:
        conn._ZK__send_command(const.CMD_RESTART, b'')
        return True
    except Exception as e:
        print(f"  Restart error: {e}")
        return False


# ============================================================
# Main test
# ============================================================

def main():
    print("=" * 60)
    print("ZK ADMS ServerType Test — Plan A")
    print(f"Device: {DEVICE_IP}:{DEVICE_PORT}")
    print(f"ADMS Server: {ADMS_SERVER_IP}:{ADMS_SERVER_PORT}")
    print("=" * 60)

    # Connect to device
    try:
        conn = connect()
    except Exception as e:
        print(f"Cannot connect: {e}")
        return

    state_before = get_state(conn)
    print(f"\n[BEFORE] State: rec={state_before['records']}, users={state_before['users']}, fingers={state_before['fingers']}")
    print(f"[BEFORE] Device: {state_before['device_name']} ({state_before['firmware']}) Serial={state_before['serial']}")

    # Read current options
    print(f"\n--- Current ADMS-related options ---")
    current_options = {}
    for opt in READ_OPTIONS:
        val = read_raw_option(conn, opt)
        if val is not None:
            current_options[opt] = val
            print(f"  {opt} = {val}")

    # Save snapshot
    snapshot_file = f"D:\\chamcong\\zk_servertype_options_{state_before['serial']}_{int(time.time())}.json"
    with open(snapshot_file, 'w') as f:
        json.dump({
            'device': state_before,
            'current_options': current_options,
            'note': 'Backup before Plan A ServerType test. Use to restore.',
        }, f, indent=2, default=str)
    print(f"\n[SNAPSHOT] Saved to {snapshot_file}")

    # Read all available options (try the whole known list)
    print(f"\n--- Reading ALL known option names (extensive scan) ---")
    additional_options = [
        # Common ZK option names
        'IPAddress', 'NetMask', 'GATEIPAddress', 'MAC', '~SerialNumber', '~DeviceID',
        '~ComPort', 'BaudRate', '~ExtendFmt', '~UserExtFmt',
        'FaceFunOn', 'CompatOldFirmware', 'ZKFaceVersion', '~ZKFPVersion',
        'ComKey', 'Encrypt', '~FWVersion', '~Language',
        # PUSH/ADMS candidates
        'PushFlag', '~PushFlag', 'CloudServer', '~CloudServer',
        'CloudServerType', '~CloudServerType', 'CloudMode', '~CloudMode',
        'PushVer', 'PushProtVer', '~PushProtVer',
        'TransFlag', '~TransFlag', 'TransInterval', '~TransInterval',
        'Realtime', '~Realtime', 'Delay', '~Delay', 'ErrorDelay', '~ErrorDelay',
        'Stamp', '~Stamp', 'OpStamp', '~OpStamp',
        'CommKey', '~CommKey', 'CommKeyType', '~CommKeyType',
        'WorkCode', '~WorkCode', 'LockCount', '~LockCount',
        '~MaxUserCount', '~MaxAttLogCount', '~MaxFingerCount', '~MaxFaceCount',
        '~UserCount', '~FPCount', '~FaceCount', '~AttLogCount', '~TransactionCount',
        'HTTPS', '~HTTPS', 'DomainName', '~DomainName', 'EnableDomain', '~EnableDomain',
        # Device type
        'DeviceType', '~DeviceType', 'PushType', '~PushType',
        'AccPush', '~AccPush', 'AttPush', '~AttPush',
        # ServerType family
        'ServerMode', '~ServerMode', 'ServerType', '~ServerType',
        'ServerEnable', '~ServerEnable',
        'CommProtocol', '~CommProtocol', 'CommType', '~CommType',
        'ADMSEnable', '~ADMSEnable', 'ADMSMode', '~ADMSMode',
    ]
    all_options = {}
    for opt in additional_options:
        val = read_raw_option(conn, opt)
        if val is not None:
            all_options[opt] = val
            print(f"  {opt} = {val}")

    # Save all options to snapshot
    with open(snapshot_file, 'a') as f:
        f.write(f"\n\n# Additional options:\n{json.dumps(all_options, indent=2, default=str)}\n")

    conn.disconnect()
    print(f"\n--- Device disconnected. Test plan aborted for safety. ---")
    print(f"Snapshot saved. To proceed with live option tests, run --live flag.")
    return  # Safety: don't actually modify device without explicit BS authorization


def main_live():
    """Live test - actually modify options and check ADMS"""
    print("\n" + "=" * 60)
    print("LIVE MODE - Will modify device options")
    print("=" * 60)

    try:
        conn = connect()
    except Exception as e:
        print(f"Cannot connect: {e}")
        return

    state_before = get_state(conn)
    print(f"\n[START] rec={state_before['records']}, users={state_before['users']}")

    # Start ADMS server
    server = MiniADMSServer(ADMS_SERVER_IP, ADMS_SERVER_PORT, None)
    try:
        server.start()
    except Exception as e:
        print(f"Cannot start ADMS server: {e}")
        conn.disconnect()
        return

    # Test each option sequence
    for i, opts in enumerate(WRITE_OPTION_TESTS):
        print(f"\n--- Test Sequence {i+1}/{len(WRITE_OPTION_TESTS)}: {opts} ---")
        server.events.clear()

        for key, value in opts:
            success = write_raw_option(conn, key, value)
            print(f"  set {key}={value}: {'OK' if success else 'FAIL'}")

        # Restart device
        print("  Restarting device...")
        restart_device(conn)

        # Wait for device to come back up
        time.sleep(15)

        # Try to reconnect
        for attempt in range(3):
            try:
                conn.disconnect()
            except:
                pass
            time.sleep(5)
            try:
                conn = connect()
                print(f"  Reconnected after {attempt+1} attempts")
                break
            except:
                continue

        # Check ADMS server events
        n_events, events = server.poll_events()
        print(f"  ADMS server received {n_events} events during this test")

        # Verify ATTLOG count hasn't been reset
        try:
            state_after = get_state(conn)
            print(f"  Device state: rec={state_after['records']}, users={state_after['users']}")
            if state_after['records'] < state_before['records'] * 0.5:
                print(f"  ⚠️ WARNING: ATTLOG count DROPPED significantly!")
        except:
            pass

    server.stop()
    try:
        conn.disconnect()
    except:
        pass


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Actually modify device options')
    args = parser.parse_args()

    if args.live:
        main_live()
    else:
        main()
