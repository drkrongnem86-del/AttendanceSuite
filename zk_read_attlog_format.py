"""Read ATTLOG records manually using pyzk.read_with_buffer - see real format."""
import struct
import time
from zk import ZK
from zk.const import CMD_ATTLOG_RRQ

HOST = '172.16.0.214'

def main():
    z = ZK(HOST, port=4370, timeout=10, verbose=False)
    c = z.connect()

    # Use pyzk's read_with_buffer but limit
    # Actually we need to disable device first per protocol
    c.disable_device()

    try:
        # Send CMD_DATA_WRRQ (1503) with ATTLOG_RRQ
        # Read just enough to get 1-2 records
        from struct import pack
        cmd_str = pack('<bhii', 1, CMD_ATTLOG_RRQ, 0, 0)

        # Send and read response (single shot for testing)
        buf = c._ZK__create_header(1503, cmd_str, c._ZK__session_id, c._ZK__reply_id)
        top = c._ZK__create_tcp_top(buf)
        c._ZK__sock.send(top)

        # Read just first packet (limited size)
        c._ZK__sock.settimeout(5)
        data = c._ZK__sock.recv(1024)

        # Parse response
        print(f'Raw response ({len(data)} bytes): {data.hex()}')
        print(f'As text: {data!r}')

        # Strip TCP header (first 8 bytes)
        if len(data) > 8:
            inner = data[8:]
            print(f'\nInner data ({len(inner)} bytes): {inner.hex()}')
            # Per adrobinoga, ATTLOG header is:
            # bytes 0-3: total size (LE uint32)
            # bytes 4+: records (40 bytes each)
            if len(inner) >= 4:
                total_size = struct.unpack('<I', inner[:4])[0]
                print(f'Total size: {total_size}')
                records = inner[4:]
                print(f'Records bytes: {len(records)}')

                # Parse first 2 records (40 bytes each)
                if len(records) >= 40:
                    r1 = records[:40]
                    print(f'\nRecord 1 ({len(r1)} bytes):')
                    print(f'  UID (2B): {r1[0:2].hex()}')
                    print(f'  user_id (9B): {r1[2:11].hex()} = {r1[2:11]!r}')
                    print(f'  padding (15B): {r1[11:26].hex()}')
                    print(f'  verify (1B): {r1[26:27].hex()}')
                    print(f'  timestamp (4B): {r1[27:31].hex()}')
                    ts = struct.unpack('<I', r1[27:31])[0]
                    print(f'    ts = {ts} = {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))}')
                    print(f'  state (1B): {r1[31:32].hex()}')
                    print(f'  more (8B): {r1[32:40].hex()}')

                if len(records) >= 80:
                    r2 = records[40:80]
                    print(f'\nRecord 2 ({len(r2)} bytes):')
                    print(f'  UID (2B): {r2[0:2].hex()}')
                    print(f'  user_id (9B): {r2[2:11].hex()} = {r2[2:11]!r}')
                    print(f'  verify (1B): {r2[26:27].hex()}')
                    print(f'  timestamp (4B): {r2[27:31].hex()}')
                    ts2 = struct.unpack('<I', r2[27:31])[0]
                    print(f'    ts = {ts2} = {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts2))}')

                # Now BUILD a write payload using real format and try
                print()
                print('=== Try WRITE with REAL format ===')
                real_record = r1  # Use first real record as template
                # Modify timestamp to NOW + change UID to something unique
                new_ts = int(time.time())
                modified = real_record[:27] + struct.pack('<I', new_ts) + real_record[31:]
                # Change UID to high unique value
                modified = struct.pack('<H', 99999) + modified[2:]
                print(f'Modified record ({len(modified)} bytes):')
                print(f'  UID: {modified[0:2].hex()}')
                print(f'  user_id: {modified[2:11].hex()}')
                print(f'  verify: {modified[26:27].hex()}')
                print(f'  new ts: {struct.unpack("<I", modified[27:31])[0]} = {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(new_ts))}')

                # Build write payload with header
                total_size = len(modified)
                write_payload = struct.pack('<I', total_size) + modified
                print(f'\nWrite payload ({len(write_payload)} bytes): {write_payload.hex()}')

                # Send via CMD_DATA_WRRQ (1503)
                print('\nSending write via CMD_DATA_WRRQ (1503)...')
                try:
                    buf = c._ZK__create_header(1503, write_payload, c._ZK__session_id, c._ZK__reply_id)
                    top = c._ZK__create_tcp_top(buf)
                    c._ZK__sock.send(top)
                    time.sleep(1)
                    resp = c._ZK__sock.recv(1024)
                    print(f'Response ({len(resp)} bytes): {resp.hex()}')
                    # Parse TCP header
                    if len(resp) >= 8:
                        cmd = struct.unpack('<H', resp[8:10])[0]
                        print(f'  cmd code: {cmd} (0x{cmd:x})')
                except Exception as e:
                    print(f'ERR: {e}')

                # Read ATTLOG to see if count changed
                print()
                print('Reading ATTLOG count after write...')
                time.sleep(2)
                try:
                    resp = c._ZK__send_command(13, b'', 1024)
                    data = c._ZK__data
                    if len(data) >= 5:
                        count = struct.unpack('<I', data[1:5])[0]
                        print(f'ATTLOG count after write: {count}')
                except Exception as e:
                    print(f'ERR reading count: {e}')
    finally:
        c.enable_device()
        c.disconnect()


if __name__ == '__main__':
    main()
