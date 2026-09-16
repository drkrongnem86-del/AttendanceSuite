"""Deep test of CMD_QUERY_DATA + CMD_SET_PULL_DATA/CMD_GET_PULL_DATA pair.

These might be the "Read/Write a large data set" commands.
"""
import socket
import struct
import time

HOST = '172.16.0.214'

def main():
    print('=' * 70)
    print(f'  Deep test: CMD_QUERY_DATA / SET_PULL_DATA / GET_PULL_DATA')
    print(f'  Device: {HOST}')
    print('=' * 70)

    from zk import ZK
    z = ZK(HOST, port=4370, timeout=10, verbose=False)
    c = z.connect()
    print('\n✅ Connected\n')

    # 1. Try CMD_GET_PULL_DATA (0x2712) with various payloads
    print('--- CMD_GET_PULL_DATA (0x2712) ---')
    for payload in [b'', b'\x00', b'ATTLOG', b'OPERLOG', b'1', struct.pack('<i', 1)]:
        try:
            resp = c._ZK__send_command(0x2712, payload, 8)
            print(f'   payload={payload!r:30s} status={resp.get("status")} code={resp.get("code")}')
        except Exception as e:
            print(f'   payload={payload!r:30s} ERR: {e}')

    # 2. Try CMD_SET_PULL_DATA (0x2711) - maybe write
    print('\n--- CMD_SET_PULL_DATA (0x2711) with various payloads ---')
    test_payloads = [
        ('empty', b''),
        ('null', b'\x00'),
        ('PKT', b'PKT\x00\x00\x00\x01'),
        ('TEXT_ATTLOG', b'ATTLOG\t1\t2026-09-14 12:00:00\t0\t15\t0\t0\t0'),
        ('PIN', b'1\t2026-09-14 12:00:00\t0\t15'),
        ('DATA 1501', struct.pack('<H', 1501) + b'ATTLOG\t1\t2026-09-14 12:00:00'),
    ]
    for name, payload in test_payloads:
        try:
            resp = c._ZK__send_command(0x2711, payload, 8)
            print(f'   {name:20s} status={resp.get("status")} code={resp.get("code")}')
        except Exception as e:
            print(f'   {name:20s} ERR: {e}')

    # 3. Try CMD_QUERY_DATA with read_with_buffer for ATTLOG
    print('\n--- CMD_QUERY_DATA (0x5DF) - try to read ATTLOG buffer ---')
    try:
        # Use pyzk's read_with_buffer - it knows how to handle the protocol
        result = c.read_with_buffer(0x0D)  # 0x0D = CMD_ATTLOG_RRQ
        print(f'   Got {len(result)} records')
        if result:
            print(f'   First record: {result[0]}')
            print(f'   Last record: {result[-1]}')
    except Exception as e:
        print(f'   ERR: {e}')

    # 4. Try CMD_DATA_WRRQ (1503) directly with various payloads
    print('\n--- CMD_DATA_WRRQ (1503/0x5DF) - write attempt ---')
    write_payloads = [
        # Maybe write format is different - try CMD_DATA (1501) which is actual data
        ('CMD_DATA 1501 empty', struct.pack('<H', 1501) + b''),
        # Full ATTLOG record binary (40 bytes per record)
        ('full ATTLOG record', (
            struct.pack('<I', 1) +  # UID
            b'1' + b'\x00' * 24 +  # UserID padded
            b'\x00' * 15 +  # padding
            struct.pack('<B', 15) +  # verify type = 15 (finger)
            struct.pack('<I', int(time.time())) +  # record time (4 bytes)
            struct.pack('<B', 0)  # verify state
        )),
        # TSV format like ADMS uses
        ('TSV ATTLOG', b'1\t2026-09-14 12:00:00\t0\t15\t0'),
    ]
    for name, payload in write_payloads:
        try:
            resp = c._ZK__send_command(0x5DF, payload, 8)
            print(f'   {name:30s} status={resp.get("status")} code={resp.get("code")}')
        except Exception as e:
            print(f'   {name:30s} ERR: {e}')

    # 5. Try USER_WRQ with extended data
    print('\n--- CMD_USER_WRQ (0x08) - test writing user with ATTLOG data ---')
    user_payload = struct.pack('<H', 1)  # uid
    user_payload += b'PIN1' + b'\x00' * 5  # userid
    user_payload += b'Admin' + b'\x00' * 11  # name
    user_payload += b'\x00' * 4  # password
    user_payload += struct.pack('<H', 14)  # privilege=14 (admin)
    try:
        resp = c._ZK__send_command(0x08, user_payload, 8)
        print(f'   User write status={resp.get("status")} code={resp.get("code")}')
    except Exception as e:
        print(f'   ERR: {e}')

    # 6. Try WRITE_MIFARE
    print('\n--- CMD_WRITE_MIFARE (0x4C) - try writing to internal storage ---')
    test_data = b'\x01' + b'ATTLOG_TEST' + b'\x00' * 100
    try:
        resp = c._ZK__send_command(0x4C, test_data, 8)
        print(f'   Write status={resp.get("status")} code={resp.get("code")}')
    except Exception as e:
        print(f'   ERR: {e}')

    print('\n' + '=' * 70)
    print('  Done')
    print('=' * 70)

    try: c.disconnect()
    except: pass


if __name__ == '__main__':
    main()
