"""ADMS server emulator with /iclock/getrequest command queue.

When a ZK device is configured with this server's IP as ADMS server,
it will poll /iclock/getrequest. We respond with DATA UPDATE commands
to write records to ATTLOG.
"""
import http.server
import json
import socketserver
import urllib.parse
import datetime
import threading
import os
import sys
from queue import Queue

PORT = 8088

# Queue of commands to send to the next poll
_command_queue = Queue()

# Track device registrations
_devices = {}
_logs = []

def enqueue_attlog_insert(pin, ts_str, status=0, verify=1):
    """Push a DATA UPDATE ATTLOG command to the queue.

    Format per ADMS PUSH SDK spec:
      C:<CmdID>:DATA UPDATE ATTLOG <PIN>\\t<Time>\\t<Status>\\t<Verify>\\t<Workcode>\\t<Reserved1>\\t<Reserved2>
    """
    cmd_id = int(datetime.datetime.now().timestamp()) % 99999
    # Tabs separate fields per ZK ADMS spec
    line = f"C:{cmd_id}:DATA UPDATE ATTLOG PIN={pin}\t{ts_str}\t{status}\t{verify}\t0\t0\t0"
    _command_queue.put(line)
    _logs.append(f"[{datetime.datetime.now()}] ENQUEUE: {line}")
    return cmd_id

class ADMSHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Log to stderr
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")
        sys.stderr.flush()

    def _ok(self, body=""):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length).decode("utf-8", errors="replace") if length else ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        sn = query.get("SN", ["UNKNOWN"])[0]
        path = parsed.path

        if path == "/iclock/cdata" and "options" in query:
            # Device asking for configuration
            _logs.append(f"[{datetime.datetime.now()}] OPTIONS REQUEST from SN={sn}")
            # Return config that enables Realtime=1 + All TransFlags
            body = (
                f"GET OPTION FROM: {sn}\r\n"
                f"ATTLOGStamp=0\r\n"
                f"OPERLOGStamp=0\r\n"
                f"ATTPHOTOStamp=0\r\n"
                f"FPStamp=0\r\n"
                f"USERStamp=0\r\n"
                f"Realtime=1\r\n"
                f"ServerVer=3.0.1\r\n"
                f"TransInterval=1\r\n"
                f"TransFlag=TransData AttLog OpLog AttPhoto EnrollFP\r\n"
            )
            return self._ok(body)

        if path == "/iclock/getrequest":
            # Device polling for pending commands
            _logs.append(f"[{datetime.datetime.now()}] GETREQUEST from SN={sn}")
            # Drain queue
            cmds = []
            while not _command_queue.empty():
                cmds.append(_command_queue.get_nowait())
            if cmds:
                body = "\n".join(cmds) + "\r\n"
                _logs.append(f"[{datetime.datetime.now()}] SENDING {len(cmds)} commands to {sn}: {cmds}")
                return self._ok(body)
            return self._ok("OK")

        if path == "/" or path == "/iclock/registry":
            return self._ok(f"ZKTeco ADMS Emulator\r\nDevice known: SN={sn}\r\n")

        return self._ok("ZKTeco ADMS Emulator - unknown path")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        sn = query.get("SN", ["UNKNOWN"])[0]
        path = parsed.path
        body = self._read_body()

        _logs.append(f"[{datetime.datetime.now()}] POST {path} SN={sn} Body={body[:200]}")

        # Store device info
        _devices[sn] = {
            "last_seen": datetime.datetime.now().isoformat(),
            "last_path": path,
            "last_body_len": len(body),
        }

        if path == "/iclock/cdata":
            table = query.get("table", [""])[0]
            if table == "ATTLOG":
                _logs.append(f"[{datetime.datetime.now()}] ATTLOG PUSH from {sn}: {body[:200]}")
            return self._ok("OK")
        if path == "/iclock/devicecmd":
            return self._ok("OK")
        return self._ok("OK")


def main():
    print(f"ADMS server listening on 0.0.0.0:{PORT}")
    # Add some demo commands on startup
    enqueue_attlog_insert(1383, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0, 1)
    enqueue_attlog_insert(1, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0, 1)
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), ADMSHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Stopping...")
            httpd.shutdown()


if __name__ == "__main__":
    main()
