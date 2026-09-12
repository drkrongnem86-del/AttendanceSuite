"""ADMS Responder: gia lap server ADMS, doi thiet bi poll, roi push command ghi log.

ZK ADMS protocol:
1. Device poll: GET /iclock/getrequest?SN=xxx
2. Server tra loi: command (vi du: 'C:1:UPDATE USERINFO PIN=421 Name=TEST')
3. Device thuc thi va POST /iclock/devicecmd?SN=xxx
4. Lap lai

Command co the push qua ADMS:
- DATA UPDATE USERINFO PIN=X Name=Y  (them user)
- DATA DEL USERINFO PIN=X
- INFO ...
- CONTROL DEVICE REBOOT
- CONTROL DEVICE POWEROFF
- CHECK

Test: xem thiet bi co poll server nao khong, va command nao duoc chap nhan.
"""
import http.server
import urllib.parse
import sys
import time
import threading

# Theo doi cac SN da poll
POLLED_DEVICES = {}
RECEIVED_COMMANDS = []

class ADMSHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # suppress default

    def _send_text(self, text, code=200):
        if isinstance(text, str):
            text = text.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(text)))
        self.end_headers()
        self.wfile.write(text)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        sn = qs.get('SN', ['UNKNOWN'])[0]
        print(f'[POLL] SN={sn} from {self.client_address[0]} path={self.path}')

        POLLED_DEVICES[sn] = {
            'last_poll': time.time(),
            'ip': self.client_address[0],
        }

        if '/iclock/getrequest' in self.path:
            # Check if there's a command to push
            cmd_to_push = None
            for cmd in RECEIVED_COMMANDS:
                if cmd.get('sn') == sn and not cmd.get('delivered'):
                    cmd['delivered'] = True
                    cmd_to_push = cmd
                    break

            if cmd_to_push:
                cmd_id = cmd_to_push.get('id', 1)
                cmd_text = cmd_to_push.get('text', '')
                full = f'C:{cmd_id}:{cmd_text}'
                print(f'  -> Push: {full[:100]}')
                self._send_text(full)
            else:
                # No command - return OK
                self._send_text('OK')
        else:
            self._send_text('OK')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        sn = qs.get('SN', ['UNKNOWN'])[0]
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='ignore')
        print(f'[POST] SN={sn} body={body[:200]}')
        POLLED_DEVICES[sn] = {'last_poll': time.time(), 'ip': self.client_address[0]}
        self._send_text('OK')


def queue_command(sn, cmd_text):
    """Them command vao queue (server se push khi device poll)."""
    cmd_id = len(RECEIVED_COMMANDS) + 1
    RECEIVED_COMMANDS.append({
        'id': cmd_id,
        'sn': sn,
        'text': cmd_text,
        'delivered': False,
    })
    print(f'Queued cmd for {sn}: {cmd_text}')


# Start server
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8089
server = http.server.HTTPServer(('0.0.0.0', port), ADMSHandler)
print(f'ADMS responder listening on port {port}')

# Pre-queue commands
import os
sn = '3324224660214'  # From earlier test
# Try various command patterns
# queue_command(sn, 'INFO SerialNumber')
# queue_command(sn, 'CHECK')
# queue_command(sn, 'CONTROL DEVICE REBOOT')
# queue_command(sn, 'DATA UPDATE USERINFO PIN=9999 Name=REMOTE_PUNCH Card=0')
# queue_command(sn, 'DATA UPDATE FINGERTMP PIN=9999 FID=0 TEMP=base64data')

def run_server():
    server.serve_forever()

t = threading.Thread(target=run_server, daemon=True)
t.start()

# Wait 30s for device to poll, then exit
print('Waiting 30s for device to poll...')
for i in range(30):
    time.sleep(1)
    if POLLED_DEVICES:
        print(f'  [{i+1}s] {len(POLLLED_DEVICES) if False else len(POLLED_DEVICES)} devices polled: {list(POLLLED_DEVICES.keys()) if False else list(POLLED_DEVICES.keys())}')
        if any(time.time() - d['last_poll'] < 5 for d in POLLED_DEVICES.values()):
            print('  Recent poll! Will keep listening...')
            # Don't exit
            continue
        if i > 15:
            break

# Report
print('\n=== Result ===')
print(f'Devices polled: {len(POLLED_DEVICES)}')
for sn, info in POLLED_DEVICES.items():
    age = time.time() - info['last_poll']
    print(f'  {sn}: last_poll={age:.1f}s ago, ip={info["ip"]}')
