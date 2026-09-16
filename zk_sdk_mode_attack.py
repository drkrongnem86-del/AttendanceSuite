"""After SDK build mode, try all undocumented write commands again."""
import struct
import time
from zk import ZK
from zk.const import CMD_OPTIONS_WRQ, CMD_OPTIONS_RRQ

HOST = '172.16.0.214'

def main():
    z = ZK(HOST, port=4370, timeout=10, verbose=False)
    c = z.connect()

    # Enable SDK mode
    print('=== Enable SDK build 1 mode ===')
    resp = c._ZK__send_command(CMD_OPTIONS_WRQ, b'SDKBuild=1\x00', 8)
    print(f'  status={resp.get("status")} code={resp.get("code")}')

    # Verify
    resp = c._ZK__send_command(CMD_OPTIONS_RRQ, b'~SDKBuild\x00', 1024)
    if resp.get('status'):
        data = c._ZK__data
        val = data.split(b'=', 1)[-1].split(b'\x00')[0]
        print(f'  ~SDKBuild = {val!r}')

    time.sleep(2)

    # Now try ATTLOG write commands again
    print('\n=== Test ATTLOG write in SDK mode ===')
    now_ts = int(time.time())
    record = struct.pack('<H', 8888)
    record += b'TESTSDK' + b'\x00' * 2
    record += b'\x00' * 15
    record += struct.pack('<B', 15)
    record += struct.pack('<I', now_ts)
    record += struct.pack('<B', 0)
    record += b'\x00' * 8

    # Read baseline
    resp = c._ZK__send_command(13, b'', 1024)
    if resp.get('status'):
        data = c._ZK__data
        if len(data) >= 5:
            baseline = struct.unpack('<I', data[1:5])[0]
            print(f'  Baseline ATTLOG: {baseline}')

    # Try write via all available mechanisms
    print()
    print('--- Test 1: CMD_QUERY_DATA (1503) with ATTLOG ---')
    for fct in [0, 1, 2]:
        wrapper = struct.pack('<bhii', 1, 13, fct, 0)
        resp = c._ZK__send_command(0x5DF, wrapper + record, 8)
        print(f'  fct={fct}: status={resp.get("status")} code={resp.get("code")}')

    print()
    print('--- Test 2: CMD_DATA (1501) direct ---')
    resp = c._ZK__send_command(1501, record, 8)
    print(f'  status={resp.get("status")} code={resp.get("code")}')

    print()
    print('--- Test 3: PREPARE_DATA + CMD_DATA + FREE_DATA flow ---')
    for size in [40, len(record), 200]:
        resp = c._ZK__send_command(1500, struct.pack('<I', size), 8)
        print(f'  PREPARE size={size}: status={resp.get("status")} code={resp.get("code")}')
        time.sleep(0.5)
        resp = c._ZK__send_command(1501, record[:size], 8)
        print(f'  DATA: status={resp.get("status")} code={resp.get("code")}')
        resp = c._ZK__send_command(1502, b'', 8)
        print(f'  FREE: status={resp.get("status")} code={resp.get("code")}')

    # Test CMD_REFRESHDATA after writes
    print()
    print('--- Test 4: CMD_REFRESHDATA (0x3F5) ---')
    resp = c._ZK__send_command(0x3F5, b'', 8)
    print(f'  status={resp.get("status")} code={resp.get("code")}')

    time.sleep(3)

    # Check if count changed
    print()
    print('=== Final ATTLOG count check ===')
    resp = c._ZK__send_command(13, b'', 1024)
    if resp.get('status'):
        data = c._ZK__data
        if len(data) >= 5:
            new_count = struct.unpack('<I', data[1:5])[0]
            print(f'  ATTLOG count: {new_count}')

    # Disable SDK mode
    print()
    print('=== Disable SDK mode ===')
    resp = c._ZK__send_command(CMD_OPTIONS_WRQ, b'SDKBuild=0\x00', 8)
    print(f'  status={resp.get("status")} code={resp.get("code")}')

    c.disconnect()


if __name__ == '__main__':
    main()
