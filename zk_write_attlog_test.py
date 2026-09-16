"""E2E test: write ATTLOG via ZK protocol, verify count increased."""
import struct
import time
from zk import ZK

HOST = '172.16.0.214'

def read_count(c):
    """Read ATTLOG count via ZK protocol."""
    sizes = c.read_sizes()
    if isinstance(sizes, dict):
        return sizes.get('records', 0)
    return 0


def write_attlog_record(c, uid=1, user_id='1', verify_type=15, ts=None, status=0):
    """Write ATTLOG record via CMD_DATA_WRRQ."""
    if ts is None:
        ts = int(time.time())
    payload = struct.pack('<I', uid)  # 4 bytes UID
    payload += user_id.encode('ascii') + b'\x00' * (25 - len(user_id))  # 25 bytes userid
    payload += b'\x00' * 15  # 15 bytes padding
    payload += struct.pack('<B', verify_type)  # 1 byte verify type
    payload += struct.pack('<I', ts)  # 4 bytes record time (epoch)
    payload += struct.pack('<B', status)  # 1 byte status
    # Total = 4+25+15+1+4+1 = 50 bytes
    return payload


def main():
    print('=' * 70)
    print(f'  E2E ATTLOG WRITE TEST')
    print(f'  Device: {HOST}')
    print('=' * 70)

    z = ZK(HOST, port=4370, timeout=10, verbose=False)
    c = z.connect()
    print('\n✅ Connected')

    # 1. Read baseline
    baseline = read_count(c)
    print(f'\n📊 ATTLOG baseline: {baseline}')

    # 2. Try writing ATTLOG records
    print('\n📝 Attempting ATTLOG writes...')
    now_ts = int(time.time())
    test_records = [
        ('PIN 1 admin finger verify=14', dict(uid=999, user_id='1', verify_type=14, ts=now_ts, status=0)),
        ('PIN 2 verify=15', dict(uid=1000, user_id='2', verify_type=15, ts=now_ts+1, status=0)),
        ('PIN 1383 verify=15', dict(uid=1001, user_id='1383', verify_type=15, ts=now_ts+2, status=1)),  # out
    ]
    for name, args in test_records:
        payload = write_attlog_record(c, **args)
        print(f'\n   Write {name}:')
        print(f'     Payload ({len(payload)} bytes): {payload.hex()}')
        try:
            resp = c._ZK__send_command(0x5DF, payload, 8)  # CMD_QUERY_DATA = 0x5DF (also known as CMD_DATA_WRRQ = 1503)
            print(f'     Response: status={resp.get("status")}, code={resp.get("code")}')
        except Exception as e:
            print(f'     ERR: {type(e).__name__}: {e}')

    # 3. Wait and re-read count
    print('\n⏳ Waiting 3 seconds for device to process...')
    time.sleep(3)

    new_count = read_count(c)
    delta = new_count - baseline
    print(f'\n📊 ATTLOG count after writes: {new_count} (baseline={baseline}, delta={delta})')

    if delta > 0:
        print(f'\n🎉🎉🎉 SUCCESS! ATTLOG count TĂNG {delta} record(s)!')
        print(f'   → ZK protocol ghi ATTLOG TRỰC TIẾP THÀNH CÔNG!')
        print(f'   → KHÔNG CẦN USB, KHÔNG CẦN NV!')
    elif delta < 0:
        print(f'\n⚠️  Count GIẢM {delta} (có thể ATTLOG bị clear)')
    else:
        print(f'\n❌ Count không đổi. Có thể write payload không đúng format.')

    # 4. Try reading actual attendance to see if our records are there
    print('\n📖 Trying to read actual ATTLOG records...')
    try:
        # read_with_buffer can fail on big files, use new buffer API
        # Let's use the regular get_attendance (limited)
        # Or just count via sizes
        records = c.read_sizes()
        if isinstance(records, dict):
            print(f'   Sizes: {records}')
    except Exception as e:
        print(f'   ERR reading records: {e}')

    # 5. Test SET_PULL_DATA + GET_PULL_DATA workflow
    print('\n--- SET_PULL_DATA workflow test ---')
    test_data = b'ATTLOG\t1\t2026-09-14 12:00:00\t0\t15\t0\t0'
    resp = c._ZK__send_command(0x2711, test_data, 8)
    print(f'   SET_PULL_DATA: status={resp.get("status")}, code={resp.get("code")}')
    time.sleep(1)
    new_count2 = read_count(c)
    delta2 = new_count2 - new_count
    print(f'   Count after SET_PULL_DATA: {new_count2} (delta={delta2})')

    print('\n' + '=' * 70)
    if delta > 0 or delta2 > 0:
        print('  🎉 ATTLOG WRITE WORKED VIA ZK PROTOCOL!')
    else:
        print('  ATTLOG write did not increase count')
    print('=' * 70)

    try: c.disconnect()
    except: pass


if __name__ == '__main__':
    main()
