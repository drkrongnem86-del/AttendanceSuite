# -*- coding: utf-8 -*-
"""
adms_mini.py - Mini ADMS server gia lap, bat command tu may ZK.

Khi may ZK duoc cau hinh push len server nay (Comm. > Cloud Server Setting):
  - May se goi GET /iclock/getrequest?SN=xxx
  - Server tra loi voi command (USER ADD, DATA UPDATE, REBOOT, etc.)
  - May execute va POST /iclock/devicecmd

Muc dich: bat command nao may ZK chap nhan, thu queue command ghi log.

Chay: python adms_mini.py [port]   (default 8080)
Sau do: tren 1 may ZK bat ky, Comm. > Cloud Server Setting >
  Server Address: <IP may nay>
  Server Port: <port>
  Enable ADMS: Yes
"""
import sys
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime


# State
command_queue = {}  # SN -> list of pending commands
device_registry = {}  # SN -> {last_seen, ip, info}
log_file = None


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if log_file:
        log_file.write(line + "\n")
        log_file.flush()


def queue_cmd(sn, cmd):
    """Them command vao queue cho 1 device."""
    if sn not in command_queue:
        command_queue[sn] = []
    cid = len(command_queue[sn]) + 1
    full_cmd = f"C:{cid}:{cmd}"
    command_queue[sn].append((cid, full_cmd))
    log(f"  Queued for {sn}: {full_cmd}")
    return cid


class ADMSHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default

    def _send_text(self, text, code=200):
        if isinstance(text, str):
            text = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(text)))
        self.end_headers()
        self.wfile.write(text)

    def do_GET(self):
        # /iclock/getrequest?SN=xxx - device poll for commands
        if "/iclock/getrequest" in self.path:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sn = qs.get("SN", ["UNKNOWN"])[0]
            device_registry[sn] = {
                "last_seen": datetime.now().isoformat(),
                "ip": self.client_address[0],
            }
            pending = command_queue.get(sn, [])
            if pending:
                # Tra ve command dau tien
                cid, cmd = pending.pop(0)
                log(f"[{sn}] POLL -> {cmd}")
                self._send_text(cmd)
            else:
                # Khong co command -> tra OK
                log(f"[{sn}] POLL -> OK (no cmd)")
                self._send_text("OK")

        # /iclock/ping?SN=xxx - keepalive
        elif "/iclock/ping" in self.path:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sn = qs.get("SN", ["UNKNOWN"])[0]
            log(f"[{sn}] PING")
            device_registry[sn] = {
                "last_seen": datetime.now().isoformat(),
                "ip": self.client_address[0],
            }
            self._send_text("OK")

        # /iclock/cdata?SN=xxx&options=all - handshake
        elif "/iclock/cdata" in self.path:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sn = qs.get("SN", ["UNKNOWN"])[0]
            log(f"[{sn}] HANDSHAKE: {self.path}")
            device_registry[sn] = {
                "last_seen": datetime.now().isoformat(),
                "ip": self.client_address[0],
            }
            # Tra ve config theo ADMS spec
            cfg = (
                f"GET OPTION FROM: {sn}\n"
                f"ATTLOGStamp=0\n"
                f"OPERLOGStamp=0\n"
                f"ATTPHOTOStamp=0\n"
                f"ErrorDelay=30\n"
                f"Delay=5\n"
                f"TransTimes=00:00;14:05\n"
                f"TransInterval=1\n"
                f"TransFlag=AttLog\tOpLog\tAttPhoto\tEnrollFP\tFPImag\n"
                f"TimeZone=7\n"
                f"Realtime=1\n"
                f"Encrypt=0\n"
            )
            self._send_text(cfg)

        # /iclock/registry?SN=xxx
        elif "/iclock/registry" in self.path:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sn = qs.get("SN", ["UNKNOWN"])[0]
            log(f"[{sn}] REGISTRY: {self.path}")
            device_registry[sn] = {
                "last_seen": datetime.now().isoformat(),
                "ip": self.client_address[0],
            }
            self._send_text("OK")

        # /admin - simple status page
        elif self.path == "/" or self.path == "/admin":
            html = f"""<html><head><title>ADMS Mini Server</title></head><body>
<h1>ADMS Mini Server</h1>
<p>Started: {datetime.now().isoformat()}</p>
<h2>Devices ({len(device_registry)})</h2>
<pre>{json.dumps(device_registry, indent=2, ensure_ascii=False)}</pre>
<h2>Pending Commands</h2>
<pre>{json.dumps(command_queue, indent=2, ensure_ascii=False)}</pre>
<h2>Queue a command (POST):</h2>
<p>POST /queue?SN=xxx&cmd=REBOOT</p>
<p>POST /queue?SN=xxx&cmd=USER ADD PIN=123 Name=Test</p>
<p>POST /queue?SN=xxx&cmd=DATA UPDATE USERINFO PIN=123\tName=Test\tCard=0</p>
</body></html>"""
            self._send_text(html)
        else:
            self._send_text("OK")

    def do_POST(self):
        # /iclock/cdata - receive data
        if "/iclock/cdata" in self.path:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sn = qs.get("SN", ["UNKNOWN"])[0]
            table = qs.get("table", [""])[0]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            body_txt = body.decode(errors='ignore')
            log(f"[{sn}] POST {table} ({len(body)} bytes)")
            if body_txt:
                log(f"  Content: {body_txt[:500]}")
            # Save full payload
            with open(f"adms_received_{sn}_{table or 'data'}.txt", "a",
                      encoding="utf-8") as f:
                f.write(f"--- {datetime.now().isoformat()} ---\n")
                f.write(body_txt)
                f.write("\n\n")
            self._send_text("OK")

        # /iclock/devicecmd - command result
        elif "/iclock/devicecmd" in self.path:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sn = qs.get("SN", ["UNKNOWN"])[0]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            log(f"[{sn}] DEVICE CMD RESULT: {body.decode(errors='ignore')[:300]}")
            self._send_text("OK")

        # /queue - queue a command (admin only, no auth)
        elif self.path.startswith("/queue"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sn = qs.get("SN", [""])[0]
            cmd = qs.get("cmd", [""])[0]
            if sn and cmd:
                cid = queue_cmd(sn, cmd)
                self._send_text(f"OK: queued C:{cid}:{cmd} for {sn}")
            else:
                self._send_text("ERROR: need SN and cmd params")

        else:
            self._send_text("OK")


def main():
    global log_file
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    log_file = open("adms_server.log", "a", encoding="utf-8")

    print("=" * 70)
    print(f"ADMS MINI SERVER - Port {port}")
    print("=" * 70)
    print(f"Log file: adms_server.log")
    print(f"\nCach su dung:")
    print(f"  1. Tren may ZK: Comm. > Cloud Server Setting")
    print(f"     Server Address: <IP may nay>")
    print(f"     Server Port: {port}")
    print(f"     Enable ADMS: Yes")
    print(f"  2. May ZK se poll {urlparse('').scheme}://<IP>:{port}/iclock/getrequest")
    print(f"  3. Xem status: http://localhost:{port}/")
    print(f"  4. Queue command:")
    print(f"     curl -X POST 'http://localhost:{port}/queue?SN=ABC123&cmd=REBOOT'")
    print(f"     curl -X POST 'http://localhost:{port}/queue?SN=ABC123&cmd=USER%20ADD%20PIN%3D123%20Name%3DTest'")
    print(f"\nCtrl+C de thoat\n")

    server = HTTPServer(("0.0.0.0", port), ADMSHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Stopped by user")
        server.shutdown()


# Fix: import urlparse
from urllib.parse import urlparse

if __name__ == "__main__":
    main()
