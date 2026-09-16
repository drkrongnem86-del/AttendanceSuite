"""Configure ZK device to use our ADMS server.

Uses CMD_OPTIONS_WRQ (12) to set:
- ServerAddr = our VPN IP (171.15.128.4)
- ServerPort = 8088
- Realtime = 1 (enable real-time)
- TransFlag = all

After configuration, the device should poll our ADMS server
and accept DATA UPDATE ATTLOG commands.
"""
import socket
import struct
import sys
import time

HOST = '172.16.0.214'
PORT = 4370
OUR_IP = '171.15.128.4'
OUR_PORT = 8088

# ZK protocol constants
CMD_CONNECT = 1000
CMD_EXIT = 1001
CMD_OPTIONS_WRQ = 12
CMD_OPTIONS_RRQ = 11
CMD_ACK_OK = 2000

def make_packet(command, session_id, reply_id, data=b'', checksum_extra=0):
    """Build a ZK protocol packet."""
    # Header: command(2) + checksum(2) + session_id(2) + reply_id(2) + data
    header_base = struct.pack('<HHHH', command, 0, session_id, reply_id) + data
    # checksum = sum of all bytes + checksum_extra
    checksum = (sum(header_base) + checksum_extra) & 0xFFFF
    # Rebuild with checksum
    header = struct.pack('<HHHH', command, checksum, session_id, reply_id) + data
    # Add start bit (0xF0 for command, 0xF1 for ack) - pyzk uses 0xB0+command
    # Actually pyzk uses 0xB0 + command for command packets
    prefix = bytes([0xB0, command & 0xFF])
    # Full packet: prefix + data + checksum_again? No, pyzk format:
    # byte 0: 0xB0 (start)
    # bytes 1-2: command (LE)
    # bytes 3-4: checksum (LE)
    # bytes 5-6: session_id (LE)
    # bytes 7-8: reply_id (LE)
    # bytes 9+: data
    # last 2 bytes: trailing checksum? No, just packet
    # pyzk sends it as: pack('HH', command, checksum) + pack('HH', session, reply) + data
    # Then prepends byte 0xB0 and adds bytes 0x50,0x00,0x00 at start
    # Actually the prefix is: bytes([0xB0]) + pack('<H', command)
    # Let me check pyzk source
    return None  # use pyzk instead


def connect_and_send(host, port, command, data, expect_size=1024, timeout=5):
    """Connect to ZK device, authenticate, send command, return response data."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        # Use pyzk for actual protocol
        from zk.base import ZK
        z = ZK(host, port=port, timeout=timeout, verbose=False)
        z.connect()
        try:
            # Use the private __send_command
            resp = z._ZK__send_command(command, data)
            if resp.get('status'):
                return z._ZK__data
            else:
                return None
        finally:
            z.disconnect()
    except Exception as e:
        print(f'ERR: {type(e).__name__}: {e}')
        return None
    finally:
        try: s.close()
        except: pass


def set_option(host, port, key, value):
    """Set ZK option using pyzk."""
    from zk.base import ZK
    z = ZK(host, port=port, timeout=5, verbose=False)
    z.connect()
    try:
        # Use internal __send_command with CMD_OPTIONS_WRQ
        cmd_string = f"{key}={value}".encode('utf-8') + b'\x00'
        resp = z._ZK__send_command(12, cmd_string)  # CMD_OPTIONS_WRQ = 12
        if resp.get('status'):
            print(f'  OK: {key}={value}')
            return True
        else:
            print(f'  FAIL: {key}={value}')
            return False
    finally:
        z.disconnect()


def get_option(host, port, key):
    """Read ZK option using pyzk."""
    from zk.base import ZK
    z = ZK(host, port=port, timeout=5, verbose=False)
    z.connect()
    try:
        cmd_string = key.encode('utf-8') + b'\x00'
        resp = z._ZK__send_command(11, cmd_string, 1024)  # CMD_OPTIONS_RRQ = 11
        if resp.get('status'):
            data = z._ZK__data
            val = data.split(b'=', 1)[-1].split(b'\x00')[0]
            return val.decode('utf-8', errors='replace')
        return None
    finally:
        z.disconnect()


def main():
    print(f'Connecting to {HOST}:{PORT}...')

    # First probe: what options can we read?
    print('\n=== Probing known options ===')
    for opt in ['IPAddress', 'NetMask', 'GATEIPAddress', 'ServerAddr',
                'ServerPort', 'Realtime', 'TransInterval', 'TransFlag',
                'COMKey', '~DeviceName', '~SDKBuild']:
        v = get_option(HOST, PORT, opt)
        print(f'  {opt:20s} = {v!r}')

    # Now set the ADMS options
    print('\n=== Setting ADMS options ===')
    set_option(HOST, PORT, 'ServerAddr', OUR_IP)
    set_option(HOST, PORT, 'ServerPort', str(OUR_PORT))
    set_option(HOST, PORT, 'Realtime', '1')
    set_option(HOST, PORT, 'TransFlag', 'TransData AttLog OpLog')
    set_option(HOST, PORT, 'TransInterval', '1')

    # Verify
    print('\n=== Verifying ===')
    for opt in ['ServerAddr', 'ServerPort', 'Realtime', 'TransFlag']:
        v = get_option(HOST, PORT, opt)
        print(f'  {opt:20s} = {v!r}')

    print('\nDone. Device should now poll our ADMS server at:')
    print(f'  http://{OUR_IP}:{OUR_PORT}/iclock/getrequest')


if __name__ == '__main__':
    main()
