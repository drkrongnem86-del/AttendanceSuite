"""
zk_adms_diag_scan.py
=====================

Check các option HTTPS/DomainName/CommKey/PushServer flags + test bằng cách
spin up HTTP server + xem device có request không.
"""

import sys
import time
import socket
import threading
import struct
import json

sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')

from zk import ZK, const


DEVICE_IP = '172.16.0.214'
DEVICE_PORT = 4370
ADMS_PORT = 8088


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


class ADMSProbe:
    """Listen on port 8088 for any incoming ADMS probes"""
    def __init__(self, port):
        self.port = port
        self.requests = []
        self.running = False
        self.sock = None

    def start(self):
        # Try multiple interfaces
        for bind_ip in ['0.0.0.0', '171.15.128.4']:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.bind((bind_ip, self.port))
                self.sock.listen(5)
                self.sock.settimeout(1.0)
                self.running = True
                threading.Thread(target=self._listen, args=(bind_ip,), daemon=True).start()
                print(f"[PROBE] Listening on {bind_ip}:{self.port}")
                return bind_ip
            except Exception as e:
                print(f"[PROBE] Bind {bind_ip}:{self.port} failed: {e}")
                try:
                    self.sock.close()
                except:
                    pass
                continue
        return None

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print(f"[PROBE] Stopped. Received {len(self.requests)} requests")

    def _listen(self, bind_ip):
        print(f"[PROBE-{bind_ip}] Listening thread started")
        while self.running:
            try:
                conn, addr = self.sock.accept()
                conn.settimeout(5.0)
                try:
                    data = b''
                    conn.settimeout(2.0)
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                        if b'\r\n\r\n' in data:
                            break
                except socket.timeout:
                    pass
                decoded = data.decode('utf-8', errors='ignore')
                first_line = decoded.split('\r\n')[0] if decoded else ''
                print(f"\n>>> [{bind_ip}] REQUEST from {addr}")
                print(f"    First line: {first_line[:120]}")
                if 'SN=' in first_line or 'pushver' in first_line.lower():
                    print(f"    >>> ADMS PROBE DETECTED! <<<")
                self.requests.append({
                    'time': time.time(),
                    'from': addr,
                    'raw': decoded[:500],
                })
                # Send 200 OK with ADMS option response
                resp_body = (
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
                http_resp = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"Content-Length: {len(resp_body)}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                    f"{resp_body}"
                )
                try:
                    conn.send(http_resp.encode())
                except:
                    pass
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    def get_count(self):
        return len(self.requests)


def diag_scan():
    """Diagnostic scan of remaining options"""
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=0, force_udp=False, ommit_ping=False, verbose=False)
    conn = zk.connect()

    diag_keys = [
        # HTTPS/TLS related
        'HTTPS', '~HTTPS', 'HttpType', '~HttpType', 'ProtocolType', '~ProtocolType',
        'WebHTTPS', '~WebHTTPS', 'CloudHTTPS', '~CloudHTTPS',
        'PushHTTPS', '~PushHTTPS', 'ADMSHTTPS', '~ADMSHTTPS',
        'UseSSL', '~UseSSL', 'UseTLS', '~UseTLS',

        # Domain/DNS
        'DomainName', '~DomainName', 'EnableDomain', '~EnableDomain',
        'EnableDomainName', '~EnableDomainName',
        'UseDomain', '~UseDomain', 'UseDNS', '~UseDNS',

        # CommKey
        'CommKey', '~CommKey', 'CommPwd', '~CommPwd',
        'PushKey', '~PushKey', 'PushPwd', '~PushPwd',
        'CommPassword', '~CommPassword',

        # PushServer flags
        'PushServerType', '~PushServerType',
        'PushServerMode', '~PushServerMode',
        'PushServerEnable', '~PushServerEnable',
        'PushServerAddr2', '~PushServerAddr2',

        # ServerMode family
        'ServerMode', '~ServerMode', 'ServerType2', '~ServerType2',
        'ServerType3', '~ServerType3', 'ServerType4', '~ServerType4',

        # Connection state
        'ConnStatus', '~ConnStatus', 'ConnState', '~ConnState',
        'PushStatus', '~PushStatus', 'CloudStatus', '~CloudStatus',

        # Server URL/Web
        'URL', '~URL', 'WebURL', '~WebURL', 'HttpURL', '~HttpURL',
        'WebServerURL', '~WebServerURL', 'HttpsURL', '~HttpsURL',
        'CloudURL', '~CloudURL', 'PushURL', '~PushURL',

        # Time server (used for time sync, might block if not set)
        'TimeServer', '~TimeServer', 'TimeServerAddr', '~TimeServerAddr',
        'NTPServer', '~NTPServer', 'NTPServerAddr', '~NTPServerAddr',
        'TimeServerEnable', '~TimeServerEnable',

        # Other possible server addresses
        'CommAddr', '~CommAddr', 'CommServer', '~CommServer',
        'HostServer', '~HostServer', 'MgmtServer', '~MgmtServer',

        # Push enable flags
        'IsPushEnable', '~IsPushEnable', 'PushOn', '~PushOn',
        'IsCloud', '~IsCloud', 'CloudOn', '~CloudOn',
        'IsADMS', '~IsADMS', 'ADMSOn', '~ADMSOn',

        # Device type
        'PushType', '~PushType', 'AccPush', '~AccPush',
        'AttPush', '~AttPush', 'AccPushOn', '~AccPushOn',

        # Server flag
        'ServerFlag', '~ServerFlag', 'ServerAuth', '~ServerAuth',
        'PushAuth', '~PushAuth', 'PushToken', '~PushToken',
    ]

    found = {}
    for opt in diag_keys:
        val = read_option(conn, opt)
        if val is not None:
            found[opt] = val
            print(f"  {opt} = {val}")

    out = f"D:\\chamcong\\zk_adms_diag_{int(time.time())}.json"
    with open(out, 'w') as f:
        json.dump(found, f, indent=2, default=str)
    print(f"\n[SAVED] {out}")

    conn.disconnect()
    return found


def main():
    print("=" * 60)
    print("ADMS Diagnostic Scan")
    print("=" * 60)

    # Step 1: Diagnostic scan
    print("\n--- Step 1: Diagnostic option scan ---")
    found = diag_scan()

    # Step 2: Spin up probe and wait
    print("\n--- Step 2: Starting ADMS probe on port 8088 ---")
    probe = ADMSProbe(ADMS_PORT)
    bind_ip = probe.start()
    if not bind_ip:
        print("Could not bind port 8088. Skipping probe.")
        return

    print(f"\nWaiting 60s for device to poll {bind_ip}:{ADMS_PORT}...")
    print("(Watch console for any incoming HTTP requests)")

    start = time.time()
    last_print = 0
    while time.time() - start < 60:
        if int(time.time()) - last_print >= 10:
            elapsed = int(time.time() - start)
            count = probe.get_count()
            print(f"  [{elapsed}s] Received {count} requests so far...")
            last_print = int(time.time())
        time.sleep(1)

    probe.stop()

    count = probe.get_count()
    if count == 0:
        print("\n[RESULT] Device did NOT poll our ADMS server in 60s.")
        print("Possible reasons:")
        print("  - Device cannot reach our IP 171.15.128.4 from VPN subnet")
        print("  - ServerType=0 + ServerAddr set is correct, but DNS/HTTPS issue")
        print("  - Need to also set EnableDomainName/EnableHTTPS correctly")
        print("  - Or maybe PushMode=2 needs special server setup")
    else:
        print(f"\n[RESULT] Received {count} requests!")


if __name__ == '__main__':
    main()
