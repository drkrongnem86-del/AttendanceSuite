"""Try ATTLOG write with proper read-then-write symmetry.

The read protocol:
1. CMD_ATTLOG_RRQ (13) -> device responds with header + data

Try the write protocol:
1. CMD_DATA_WRRQ (1503) with header bytes + ATTLOG record
2. Device writes the record
"""
import struct
import time
from zk import ZK
from zk.const import CMD_ATTLOG_RRQ

HOST = '172.16.0.214'

def read_attlog_count(c):
    """Read ATTLOG count via CMD_ATTLOG_RRQ header."""
    resp = c._ZK__send_command(CMD_ATTLOG_RRQ, b'', 1024)
    if not resp.get('status'):
        return None, None
    data = c._ZK__data
    # Header: byte 0 = 0x00 or status, then count in next 4 bytes
    if len(data) >= 5:
        count = struct.unpack('<I', data[1:5])[0]
        capacity = struct.unpack('<I', data[5:9])[0] if len(data) >= 9 else 0
        return count, capacity
    return None, None


def main():
    print('=' * 70)
    print(f'  ATTLOG Write Test - Read/Write symmetry')
    print(f'  Device: {HOST}')
    print('=' * 70)

    z = ZK(HOST, port=4370, timeout=10, verbose=False)
    c = z.connect()

    baseline, baseline_cap = read_attlog_count(c)
    print(f'\n📊 Baseline ATTLOG: {baseline} records (capacity {baseline_cap})')

    # Per adrobinoga: ATTLOG header in protocol is
    # bytes 0-3: total size (little-endian uint32)
    # bytes 4+: actual records (40 bytes each)
    # Record format (40 bytes):
    #   UID(2) + user_id(9) + 15 zero + verify(1) + timestamp(4) + state(1) + 8 zero = 40

    # Build 1 ATTLOG record
    now_ts = int(time.time())
    record = struct.pack('<H', 9999)  # UID
    record += b'1' + b'\x00' * 8  # user_id
    record += b'\x00' * 15  # padding
    record += struct.pack('<B', 15)  # verify type
    record += struct.pack('<I', now_ts)  # timestamp
    record += struct.pack('<B', 0)  # state
    record += b'\x00' * 8  # padding

    print(f'\nRecord ({len(record)} bytes): {record.hex()}')

    # Try write with full header (size + records)
    print('\n=== Test 1: Write with header + 1 record ===')
    header = struct.pack('<I', len(record))  # total size
    full_payload = header + record
    try:
        resp = c._ZK__send_command(0x5DF, full_payload, 8)
        print(f'  Write status={resp.get("status")} code={resp.get("code")}')
    except Exception as e:
        print(f'  ERR: {e}')

    time.sleep(2)
    new_count, _ = read_attlog_count(c)
    delta = (new_count - baseline) if (new_count and baseline) else 0
    print(f'  Count after: {new_count} (delta={delta})')

    # Test 2: Write 3 records (more like a normal payload)
    print('\n=== Test 2: Write 3 records ===')
    records = b''
    for i in range(3):
        rec = struct.pack('<H', 9990+i)
        rec += str(i+1).encode() + b'\x00' * 8
        rec += b'\x00' * 15
        rec += struct.pack('<B', 15)
        rec += struct.pack('<I', now_ts + i)
        rec += struct.pack('<B', 0)
        rec += b'\x00' * 8
        records += rec
    header = struct.pack('<I', len(records))
    payload = header + records
    try:
        resp = c._ZK__send_command(0x5DF, payload, 8)
        print(f'  Write status={resp.get("status")} code={resp.get("code")}')
    except Exception as e:
        print(f'  ERR: {e}')

    time.sleep(2)
    new_count, _ = read_attlog_count(c)
    delta = (new_count - baseline) if (new_count and baseline) else 0
    print(f'  Count after: {new_count} (delta={delta})')

    # Test 3: Write via PREPARE_DATA → CMD_DATA → FREE_DATA
    print('\n=== Test 3: Write via PREPARE_DATA flow ===')
    try:
        # PREPARE with total size including header
        total = 4 + len(records)
        resp = c._ZK__send_command(0x5DC, struct.pack('<I', total), 8)  # CMD_PREPARE_DATA
        print(f'  PREPARE_DATA: status={resp.get("status")} code={resp.get("code")}')
        # Wait for device to be ready (response CMD_DATA = 1501)
        time.sleep(0.5)
        # Send CMD_DATA with payload
        resp = c._ZK__send_command(0x5DD, payload, 8)
        print(f'  CMD_DATA: status={resp.get("status")} code={resp.get("code")}')
        # Free
        resp = c._ZK__send_command(0x5DE, b'', 8)
        print(f'  FREE_DATA: status={resp.get("status")} code={resp.get("code")}')
    except Exception as e:
        print(f'  ERR: {e}')

    time.sleep(3)
    new_count, _ = read_attlog_count(c)
    delta = (new_count - baseline) if (new_count and baseline) else 0
    print(f'  Count after: {new_count} (delta={delta})')

    if delta > 0:
        print(f'\n🎉🎉🎉 ATTLOG WRITE WORKED via PREPARE_DATA flow! +{delta}')
    elif delta < 0:
        print(f'\n⚠️  ATTLOG cleared')

    # Test 4: Maybe CMD_ATTLOG_RRQ with WRITE mode
    # The CMD_ATTLOG_RRQ might have a write variant
    print('\n=== Test 4: CMD_ATTLOG_RRQ (13) with various payloads ===')
    for payload, name in [
        (header + record, 'header+rec'),
        (record, 'just record'),
        (b'\x01' + record, 'fct=1 + record'),
        (b'\x02' + record, 'fct=2 + record'),
        (struct.pack('<B', 1) + struct.pack('<H', CMD_ATTLOG_RRQ) + struct.pack('<H', 1) + struct.pack('<I', 1) + record, 'full WRQ header'),
    ]:
        try:
            resp = c._ZK__send_command(13, payload, 8)
            print(f'  {name:25s} status={resp.get("status")} code={resp.get("code")}')
        except Exception as e:
            print(f'  {name:25s} ERR {type(e).__name__}: {str(e)[:50]}')

    time.sleep(3)
    final_count, _ = read_attlog_count(c)
    delta = (final_count - baseline) if (final_count and baseline) else 0
    print(f'\n📊 Final count: {final_count} (total delta={delta})')

    if delta > 0:
        print(f'🎉 ATTLOG WRITE WORKED! +{delta} records!')
    else:
        print('❌ All write attempts failed. Protocol does not support remote ATTLOG write.')

    print('\n' + '=' * 70)
    c.disconnect()


if __name__ == '__main__':
    main()
