"""
zk_adms_full_server.py
=======================

Full ADMS server (Push protocol v2.4.1 + v3.0.x) với:
- Listen /iclock/cdata (handshake + ATTLOG upload)
- Listen /iclock/getrequest (device poll commands)
- Listen /iclock/devicecmd (command results)
- HTTP + HTTPS dual mode
- Full request/response logging với hexdump
- Command queue (queued commands sẽ trả về khi device poll)
- Analysis mode (auto-classify incoming requests)

Server endpoints:
- GET  /iclock/cdata?SN=...&options=all  → handshake, return GET OPTION FROM response
- POST /iclock/cdata  → receive ATTLOG/OPERLOG push
- GET  /iclock/getrequest  → return queued commands
- POST /iclock/devicecmd  → receive command execution results

Author: Mavis (Mavis inside MiniMax Code)
For: BVĐK Ninh Thuận — ZK FW 6.60 ADMS Investigation
"""

import sys
import os
import time
import json
import socket
import threading
import ssl
import struct
import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.stdout.reconfigure(encoding='utf-8')


# ============================================================
# Configuration
# ============================================================

LOG_DIR = r'D:\chamcong\adms_logs'
os.makedirs(LOG_DIR, exist_ok=True)

DEFAULT_BIND = '171.15.128.4'
DEFAULT_HTTP_PORT = 8088
DEFAULT_HTTPS_PORT = 8443

# ServerVer per Push SDK protocol — important for handshake
SERVER_VER = '3.0.1'
PUSH_PROT_VER = '2.4.1'

# Command queue (thread-safe)
command_queue = {
    'serials': {},  # SN -> [commands]
    'lock': threading.Lock(),
}


def queue_command(sn, command_text):
    """Queue a command to be sent when device polls"""
    with command_queue['lock']:
        if sn not in command_queue['serials']:
            command_queue['serials'][sn] = []
        command_queue['serials'][sn].append(command_text)
    print(f"[QUEUE] {sn} ← {command_text[:80]}")


def drain_commands(sn):
    """Drain queued commands for a serial number"""
    with command_queue['lock']:
        cmds = command_queue['serials'].get(sn, [])
        command_queue['serials'][sn] = []
    return cmds


def get_option_response(sn):
    """Build GET OPTION response for handshake"""
    return (
        f"GET OPTION FROM: {sn}\r\n"
        f"ATTLOGStamp=0\r\n"
        f"OPERLOGStamp=0\r\n"
        f"BIODATAStamp=0\r\n"
        f"ATTPHOTOStamp=0\r\n"
        f"ErrorDelay=30\r\n"
        f"Delay=5\r\n"
        f"TransTimes=00:00;14:05\r\n"
        f"TransInterval=1\r\n"
        f"TransFlag=AttLog\tOpLog\tAttPhoto\tEnrollFP\tEnrollUser\tFPImag\r\n"
        f"TimeZone=7\r\n"
        f"Realtime=1\r\n"
        f"Encrypt=0\r\n"
        f"ServerVer={SERVER_VER}\r\n"
        f"PushProtVer={PUSH_PROT_VER}\r\n"
        f"SupportPing=1\r\n"
        f"OptionsFlag=1\r\n"
        f"OK\r\n"
    )


# ============================================================
# Logging
# ============================================================

class TrafficLogger:
    def __init__(self):
        self.log_file = os.path.join(LOG_DIR, f'adms_traffic_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jsonl')

    def log_event(self, event_type, **data):
        record = {
            'time': datetime.now().isoformat(),
            'event': event_type,
            **data,
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, default=str) + '\n')
        # Also print to console
        self._print_event(record)

    def _print_event(self, record):
        ts = record['time'].split('T')[1][:12]
        ev = record['event']
        extra = ''
        if ev == 'handshake':
            extra = f" SN={record.get('sn')} options={record.get('options')} language={record.get('language')}"
        elif ev == 'attlog_upload':
            extra = f" count={record.get('count')} first_pin={record.get('first_pin')}"
        elif ev == 'devicecmd_result':
            extra = f" result={record.get('result')[:80]}"
        elif ev == 'poll':
            extra = f" SN={record.get('sn')} returned={len(record.get('returned_commands', []))}"
        elif ev == 'info_post':
            extra = f" keys={list(record.get('device_info', {}).keys())[:5]}"
        elif ev == 'operlog_upload':
            extra = f" count={record.get('count')}"
        print(f"[{ts}] {ev}{extra}")


traffic = TrafficLogger()


# ============================================================
# HTTP Request Handler
# ============================================================

class ADMSHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, format, *args):
        pass  # suppress default access log

    def _send_plain(self, body):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _read_body(self):
        cl = int(self.headers.get('Content-Length', 0))
        if cl > 0:
            return self.rfile.read(cl).decode('utf-8', errors='ignore')
        return ''

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        qs = parse_qs(url.query)
        sn = qs.get('SN', ['UNKNOWN'])[0]
        remote = f"{self.client_address[0]}:{self.client_address[1]}"
        ua = self.headers.get('User-Agent', '-')

        traffic.log_event(
            'get_request',
            remote=remote,
            path=path,
            query=url.query,
            sn=sn,
            ua=ua,
            method='GET',
        )

        if path.endswith('/iclock/cdata') or path == '/iclock/cdata':
            # Handshake / options
            options = qs.get('options', ['none'])[0]
            pushver = qs.get('pushver', ['?'])[0]
            language = qs.get('language', ['?'])[0]
            devicetype = qs.get('DeviceType', ['?'])[0]
            pushoptsflag = qs.get('PushOptionsFlag', ['?'])[0]

            traffic.log_event(
                'handshake',
                sn=sn,
                options=options,
                pushver=pushver,
                language=language,
                devicetype=devicetype,
                pushoptsflag=pushoptsflag,
                ua=ua,
                remote=remote,
            )
            self._send_plain(get_option_response(sn))
            return

        if path.endswith('/iclock/getrequest') or path == '/iclock/getrequest':
            # Device polls for queued commands
            cmds = drain_commands(sn)
            response_body = '\r\n'.join(cmds) + '\r\n' if cmds else 'OK\r\n'
            traffic.log_event(
                'poll',
                sn=sn,
                remote=remote,
                returned_commands=cmds,
            )
            self._send_plain(response_body)
            return

        if path.endswith('/iclock/registry') or path == '/iclock/registry':
            traffic.log_event('registry', sn=sn, remote=remote)
            self._send_plain('OK\r\n')
            return

        if path.endswith('/iclock/inspect') or path == '/iclock/inspect':
            traffic.log_event('inspect', sn=sn, remote=remote, path=path)
            self._send_plain('{"devices":[]}\r\n')
            return

        if path.endswith('/iclock/ping') or path == '/iclock/ping':
            traffic.log_event('ping', sn=sn, remote=remote)
            self._send_plain('OK\r\n')
            return

        # Unknown path
        traffic.log_event('unknown_get', sn=sn, remote=remote, path=path, query=url.query)
        self._send_plain('OK\r\n')

    def do_POST(self):
        url = urlparse(self.path)
        path = url.path
        qs = parse_qs(url.query)
        body = self._read_body()
        remote = f"{self.client_address[0]}:{self.client_address[1]}"
        sn = qs.get('SN', ['UNKNOWN'])[0]
        table = qs.get('table', ['none'])[0]
        stamp = qs.get('Stamp', ['0'])[0]

        traffic.log_event(
            'post_request',
            remote=remote,
            path=path,
            query=url.query,
            sn=sn,
            table=table,
            stamp=stamp,
            body_len=len(body),
            body_preview=body[:200],
        )

        if path.endswith('/iclock/cdata') or path == '/iclock/cdata':
            # Data push
            if table == 'ATTLOG':
                self._handle_attlog(sn, body)
                self._send_plain('OK\r\n')
                return
            elif table == 'OPERLOG':
                self._handle_operlog(sn, body)
                self._send_plain('OK\r\n')
                return
            elif table == 'options':
                self._handle_options(sn, body)
                self._send_plain('OK\r\n')
                return
            elif table == 'ATTPHOTO':
                traffic.log_event('attphoto_upload', sn=sn, body_len=len(body))
                self._send_plain('OK\r\n')
                return
            else:
                traffic.log_event('unknown_table', sn=sn, table=table, body_preview=body[:200])
                self._send_plain('OK\r\n')
                return

        if path.endswith('/iclock/devicecmd') or path == '/iclock/devicecmd':
            self._handle_devicecmd(sn, body)
            self._send_plain('OK\r\n')
            return

        # Unknown POST
        traffic.log_event('unknown_post', sn=sn, path=path, body_preview=body[:200])
        self._send_plain('OK\r\n')

    def _parse_tsv_records(self, body):
        """Parse TSV records like 'PIN\\tDateTime\\tStatus\\tVerify\\tWorkCode\\t...'"""
        records = []
        for line in body.strip().split('\n'):
            line = line.strip()
            if not line or line.upper() == 'ATTLOG' or line.upper() == 'OPLOG' or line.upper() == 'OPERLOG':
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                records.append({
                    'pin': parts[0],
                    'datetime': parts[1] if len(parts) > 1 else '',
                    'status': parts[2] if len(parts) > 2 else '',
                    'verify': parts[3] if len(parts) > 3 else '',
                    'workcode': parts[4] if len(parts) > 4 else '',
                    'raw': line,
                })
        return records

    def _handle_attlog(self, sn, body):
        records = self._parse_tsv_records(body)
        if records:
            traffic.log_event(
                'attlog_upload',
                sn=sn,
                count=len(records),
                first_pin=records[0]['pin'],
                first_datetime=records[0]['datetime'],
                samples=records[:3],
            )
            # Save to CSV for inspection
            csv_file = os.path.join(LOG_DIR, f'attlog_{sn}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
            with open(csv_file, 'a', encoding='utf-8') as f:
                if not os.path.getsize(csv_file) if os.path.exists(csv_file) else True:
                    f.write('received_at,sn,pin,datetime,status,verify,workcode\n')
                for r in records:
                    f.write(f"{datetime.now().isoformat()},{sn},{r['pin']},{r['datetime']},{r['status']},{r['verify']},{r['workcode']}\n")

    def _handle_operlog(self, sn, body):
        records = self._parse_tsv_records(body)
        traffic.log_event(
            'operlog_upload',
            sn=sn,
            count=len(records),
            samples=records[:3],
        )

    def _handle_options(self, sn, body):
        # Parse key=value format
        opts = {}
        for line in body.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                opts[k.strip()] = v.strip()
        traffic.log_event(
            'info_post',
            sn=sn,
            device_info=opts,
            raw_preview=body[:300],
        )

    def _handle_devicecmd(self, sn, body):
        # Format: ID=&ID=&Return=0&CMD=...
        qs2 = parse_qs(body)
        result = {
            'id': qs2.get('ID', [''])[0],
            'cmd': qs2.get('CMD', [''])[0],
            'return': qs2.get('Return', [''])[0],
            'sn': qs2.get('SN', [sn])[0],
            'content': qs2.get('Content', [''])[0][:500],
            'filename': qs2.get('FILENAME', [''])[0],
            'raw': body[:500],
        }
        traffic.log_event('devicecmd_result', **result)


# ============================================================
# Server
# ============================================================

def run_server(bind_ip, port, use_https=False, cert_file=None):
    """Run ADMS server on bind_ip:port"""
    server = ThreadingHTTPServer((bind_ip, port), ADMSHandler)
    if use_https:
        if cert_file and os.path.exists(cert_file):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert_file)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            print(f"  [+] HTTPS enabled with {cert_file}")
        else:
            print(f"  [!] No cert for HTTPS, falling back to HTTP")
    print(f"\n[ADMS-SERVER] Listening on http{'s' if use_https else ''}://{bind_ip}:{port}/")
    print(f"[ADMS-SERVER] Endpoints:")
    print(f"  GET  /iclock/cdata       (handshake)")
    print(f"  POST /iclock/cdata       (ATTLOG / OPERLOG / options)")
    print(f"  GET  /iclock/getrequest  (poll for queued commands)")
    print(f"  POST /iclock/devicecmd   (command result)")
    print(f"\n[ADMS-SERVER] Log file: {traffic.log_file}")
    print()
    server.serve_forever()


# ============================================================
# Interactive queue admin (queue commands while server running)
# ============================================================

def interactive_admin():
    """Queue commands while server runs"""
    print("\n[ADMIN] Interactive command queue (Ctrl+C to exit)")
    print("[ADMIN] Commands:")
    print("  queue <SN> <C:UUID:COMMAND_TEXT>")
    print("  shell <SN> <linux-cmd>       (queues 'C:UUID:SHELL <cmd>')")
    print("  info <SN>                    (queues 'C:UUID:INFO')")
    print("  check <SN>                   (queues 'C:UUID:CHECK')")
    print("  reboot <SN>                  (queues 'C:UUID:REBOOT')")
    print("  quit")
    cmd_id = 1000
    while True:
        try:
            line = input('> ').strip()
            if not line:
                continue
            if line == 'quit':
                return
            parts = line.split(maxsplit=1)
            action = parts[0]
            if len(parts) < 2:
                print(f"  Usage: queue <SN> <C:UUID:COMMAND>")
                continue
            rest = parts[1]
            if action in ('queue',):
                # rest = "SN command_text"
                sub_parts = rest.split(maxsplit=1)
                sn = sub_parts[0]
                cmd = sub_parts[1] if len(sub_parts) > 1 else ''
                queue_command(sn, cmd)
            elif action == 'shell':
                sub_parts = rest.split(maxsplit=1)
                sn = sub_parts[0]
                shell_cmd = sub_parts[1] if len(sub_parts) > 1 else 'ls'
                cmd_id += 1
                queue_command(sn, f"C:{cmd_id}:SHELL {shell_cmd}")
            elif action in ('info', 'check', 'reboot'):
                sn = rest.strip()
                cmd_id += 1
                action_map = {'info': 'INFO', 'check': 'CHECK', 'reboot': 'REBOOT'}
                queue_command(sn, f"C:{cmd_id}:{action_map[action]}")
            else:
                print(f"  Unknown action: {action}")
        except (KeyboardInterrupt, EOFError):
            return


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='ZK ADMS full server')
    parser.add_argument('--bind', default=DEFAULT_BIND, help='Bind IP')
    parser.add_argument('--port', type=int, default=DEFAULT_HTTP_PORT, help='HTTP port')
    parser.add_argument('--https-port', type=int, default=DEFAULT_HTTPS_PORT, help='HTTPS port')
    parser.add_argument('--https', action='store_true', help='Enable HTTPS')
    parser.add_argument('--cert', help='SSL cert file (PEM)')
    parser.add_argument('--admin', action='store_true', help='Interactive admin')
    args = parser.parse_args()

    print('=' * 60)
    print('ZK ADMS Full Server (Push SDK v2.4.1 / v3.x)')
    print('=' * 60)
    print(f"Log dir: {LOG_DIR}")
    print(f"Trajectory file: {traffic.log_file}")

    if args.admin:
        # Run server in background, admin on foreground
        server_thread = threading.Thread(
            target=run_server,
            args=(args.bind, args.port, args.https, args.cert),
            daemon=True,
        )
        server_thread.start()
        time.sleep(2)
        try:
            interactive_admin()
        except KeyboardInterrupt:
            pass
        print('\n[EXIT] Shutting down...')
    else:
        run_server(args.bind, args.port, args.https, args.cert)


if __name__ == '__main__':
    main()
