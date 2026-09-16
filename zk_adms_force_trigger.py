"""
zk_adms_force_trigger.py
========================

Comprehensive brute-force test of all option combinations to try to trigger
ADMS daemon startup on X628 PRO. Tests:

1. All ServerType values (0/1/2/3)
2. All HTTPS settings
3. Different ports (8088 / 80 / 443 / 8080 / 8888)
4. CloudEnable / PushMode variants
5. After every combination → CMD_RESTART + listen 90s
6. Records which combination (if any) triggers device polling

This is the FINAL attempt at remote ADMS enable. If nothing works, the only
remaining path is physical menu UI enable (Branch 1 manual).

Author: Mavis (Mavis inside MiniMax Code)
Date: 2026-09-15
"""

import sys
import time
import socket
import threading
import struct
import json
import os
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')

from zk import ZK, const


DEVICE_IP = '172.16.0.214'
OUR_VPN_IP = '171.15.128.4'
LOG_DIR = r'D:\chamcong\adms_logs'
os.makedirs(LOG_DIR, exist_ok=True)


# ============================================================
# Listener that records ALL incoming traffic
# ============================================================

class FullListener:
    def __init__(self, bind_ip, port):
        self.bind_ip = bind_ip
        self.port = port
        self.events = []
        self.running = False
        self.sock = None
        self.lock = threading.Lock()

    def start(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.bind_ip, self.port))
            self.sock.listen(5)
            self.sock.settimeout(1.0)
            self.running = True
            threading.Thread(target=self._loop, daemon=True).start()
            return True
        except Exception as e:
            print(f"  [LISTEN] Bind failed: {e}")
            return False

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

    def _loop(self):
        while self.running:
            try:
                conn, addr = self.sock.accept()
                conn.settimeout(3.0)
                data = b''
                try:
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                        if b'\r\n\r\n' in data or len(data) > 8192:
                            break
                except socket.timeout:
                    pass
                with self.lock:
                    self.events.append({
                        'time': time.time(),
                        'from': f"{addr[0]}:{addr[1]}",
                        'raw_first_300': data[:300].decode('utf-8', errors='ignore'),
                    })
                # Try to send ADMS option response
                resp = (
                    "GET OPTION FROM: X628PRO\r\n"
                    "ATTLOGStamp=0\r\n"
                    "OPERLOGStamp=0\r\n"
                    "BIODATAStamp=0\r\n"
                    "ATTPHOTOStamp=0\r\n"
                    "ErrorDelay=30\r\n"
                    "Delay=5\r\n"
                    "TransInterval=1\r\n"
                    "TransFlag=AttLog\tOpLog\r\n"
                    "TimeZone=7\r\n"
                    "Realtime=1\r\n"
                    "Encrypt=0\r\n"
                    "ServerVer=2.4.1\r\n"
                    "PushProtVer=2.4.1\r\n"
                    "OK\r\n"
                )
                http = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"Content-Length: {len(resp)}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                    f"{resp}"
                )
                try:
                    conn.send(http.encode())
                except:
                    pass
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    def count(self):
        with self.lock:
            return len(self.events)


# ============================================================
# ZK helper functions
# ============================================================

def connect(timeout=10):
    zk = ZK(DEVICE_IP, port=4370, timeout=timeout, password=0, force_udp=False, ommit_ping=False, verbose=False)
    return zk.connect()


def read_option(conn, key):
    try:
        cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_RRQ, key.encode() + b'\x00', 1024)
        if cmd_response.get('status'):
            data = conn._ZK__data
            if b'=' in data:
                val = data.split(b'=', 1)[-1].split(b'\x00')[0]
                return val.decode('utf-8', errors='ignore')
            return data.split(b'\x00')[0].decode('utf-8', errors='ignore')
    except:
        pass
    return None


def write_option(conn, key, value):
    try:
        command_string = f"{key}={value}".encode()
        cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_WRQ, command_string)
        return cmd_response.get('status', False)
    except Exception as e:
        return False


def restart_device(conn):
    try:
        conn._ZK__send_command(const.CMD_RESTART, b'')
        return True
    except:
        return False


def wait_for_device(ip, max_wait=60):
    """Wait for device to come back online after restart"""
    print(f"  Waiting for device to come back online...")
    for i in range(max_wait):
        time.sleep(2)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            sock.connect((ip, 4370))
            sock.close()
            print(f"  Device online after {(i+1)*2}s")
            return True
        except:
            continue
    print(f"  Device did NOT come back online after {max_wait*2}s")
    return False


# ============================================================
# Test matrix
# ============================================================

# Each test: (description, options_to_set, port_to_listen_on)
TEST_MATRIX = [
    # Test 1: HTTPS = No (was unknown) + port 80
    ("HTTPS=No + Port 80",
     {'HTTPS': '0', 'HttpEnable': '0', 'ServerPort': '80', 'ServerAddr': OUR_VPN_IP},
     80),

    # Test 2: HTTPS = Yes + port 443
    ("HTTPS=Yes + Port 443",
     {'HTTPS': '1', 'HttpEnable': '1', 'ServerPort': '443', 'ServerAddr': OUR_VPN_IP},
     443),

    # Test 3: HTTPS = No + port 8080
    ("HTTPS=No + Port 8080",
     {'HTTPS': '0', 'HttpEnable': '0', 'ServerPort': '8080', 'ServerAddr': OUR_VPN_IP},
     8080),

    # Test 4: Try with ServerType = 1
    ("ServerType=1 + 8088",
     {'ServerType': '1', 'ServerMode': '1', 'CloudEnable': '1'},
     8088),

    # Test 5: ServerType = 2
    ("ServerType=2 + 8088",
     {'ServerType': '2', 'ServerMode': '1', 'CloudEnable': '1'},
     8088),

    # Test 6: ServerType = 3
    ("ServerType=3 + 8088",
     {'ServerType': '3', 'ServerMode': '1', 'CloudEnable': '1'},
     8088),

    # Test 7: ServerMode 1/2/3 with HTTPS=No
    ("ServerMode=2 + HTTPS=No + 8088",
     {'ServerMode': '2', 'ServerType': '0', 'HTTPS': '0'},
     8088),

    # Test 8: PushMode=1
    ("PushMode=1 + HTTPS=No",
     {'PushMode': '1', 'HTTPS': '0', 'CloudEnable': '1'},
     8088),

    # Test 9: CloudServer=1 with various sub-keys
    ("CloudServer=1 + CloudServerType=0",
     {'CloudServer': '1', 'CloudServerType': '0', 'ServerType': '0'},
     8088),

    # Test 10: ADMSEnable=1 (force)
    ("ADMSEnable=1 + ServerEnable=1",
     {'ADMSEnable': '1', 'ServerEnable': '1', 'ADMSMode': '1'},
     8088),
]


# ============================================================
# Main test runner
# ============================================================

def main():
    print("=" * 70)
    print("ADMS Force-Trigger Test — Comprehensive Brute Force")
    print(f"Device: {DEVICE_IP} | Our VPN: {OUR_VPN_IP}")
    print("=" * 70)

    # Initial snapshot
    print("\n[1] Initial device state")
    try:
        conn = connect()
        snap_before = {
            'ServerType': read_option(conn, 'ServerType'),
            'ServerAddr': read_option(conn, 'ServerAddr'),
            'ServerPort': read_option(conn, 'ServerPort'),
            'HTTPS': read_option(conn, 'HTTPS'),
            'CommType': read_option(conn, 'CommType'),
            'PushMode': read_option(conn, 'PushMode'),
            'PushVersion': read_option(conn, 'PushVersion'),
            'Realtime': read_option(conn, 'Realtime'),
            'TransFlag': read_option(conn, 'TransFlag'),
            'CommPwd': read_option(conn, 'CommPwd'),
            'CloudEnable': read_option(conn, 'CloudEnable'),
            'CloudServer': read_option(conn, 'CloudServer'),
            'CloudServerType': read_option(conn, 'CloudServerType'),
            'ADMSEnable': read_option(conn, 'ADMSEnable'),
        }
        print(json.dumps(snap_before, indent=2, default=str))
        conn.disconnect()
    except Exception as e:
        print(f"Cannot connect initially: {e}")
        return

    results = []

    for test_num, (desc, options, port) in enumerate(TEST_MATRIX, 1):
        print(f"\n[TEST {test_num}/{len(TEST_MATRIX)}] {desc}")
        print(f"  Options: {options}")
        print(f"  Port: {port}")

        # Start listener
        listener = FullListener(OUR_VPN_IP, port)
        if not listener.start():
            print(f"  Cannot bind port {port} - skipping")
            continue

        # Connect and set options
        try:
            conn = connect(timeout=8)
        except Exception as e:
            print(f"  Cannot connect to device: {e}")
            listener.stop()
            continue

        # Apply options
        for k, v in options.items():
            ok = write_option(conn, k, v)
            print(f"  Set {k}={v}: {'OK' if ok else 'FAIL'}")

        # Verify
        verify = {}
        for k in options.keys():
            verify[k] = read_option(conn, k)

        print(f"  Verified: {json.dumps(verify, default=str)}")

        # Restart device
        print(f"  Restarting device...")
        restart_device(conn)
        try:
            conn.disconnect()
        except:
            pass

        # Wait for device
        if not wait_for_device(DEVICE_IP, max_wait=40):
            print(f"  Device didn't come back. Aborting test {test_num}")
            listener.stop()
            continue

        # Listen for 90 seconds
        print(f"  Listening 90s for any incoming traffic...")
        start = time.time()
        last_count = 0
        while time.time() - start < 90:
            time.sleep(5)
            cur_count = listener.count()
            if cur_count != last_count:
                elapsed = int(time.time() - start)
                print(f"    [{elapsed}s] Received {cur_count} request(s) so far")
                last_count = cur_count
            # Heartbeat
            if int(time.time() - start) % 30 == 0 and int(time.time() - start) > 0:
                elapsed = int(time.time() - start)
                if elapsed % 30 == 0 and elapsed > 0:
                    print(f"    [{elapsed}s] Still listening...")

        final_count = listener.count()
        listener.stop()

        result = {
            'test': test_num,
            'description': desc,
            'options_set': options,
            'verified': verify,
            'port': port,
            'requests_received': final_count,
            'events': listener.events[:5] if final_count > 0 else [],
        }
        results.append(result)
        print(f"  RESULT: {final_count} requests received in 90s")

        if final_count > 0:
            print(f"  *** ADMS TRIGGERED! ***")
            for ev in listener.events[:3]:
                print(f"    From {ev['from']}: {ev['raw_first_300'][:100]}")

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    triggered = [r for r in results if r['requests_received'] > 0]
    print(f"\nTotal tests: {len(results)}")
    print(f"Tests that triggered traffic: {len(triggered)}")
    if triggered:
        print(f"\nSUCCESS: {triggered[0]['description']} worked!")
    else:
        print(f"\nNO test triggered ADMS. ADMS daemon needs physical menu UI enable.")

    # Save report
    out = os.path.join(LOG_DIR, f"adms_force_trigger_test_{int(time.time())}.json")
    with open(out, 'w') as f:
        json.dump({
            'device': DEVICE_IP,
            'snap_before': snap_before,
            'results': results,
            'triggered_count': len(triggered),
            'conclusion': 'ADMS enabled' if triggered else 'No remote enable possible',
        }, f, indent=2, default=str)
    print(f"\nFull report saved: {out}")


if __name__ == '__main__':
    main()
