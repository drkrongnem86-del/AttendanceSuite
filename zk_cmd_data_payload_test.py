# -*- coding: utf-8 -*-
"""
ZK X628 PRO - CMD_DATA PAYLOAD SIZE TEST
Gửi payload sizes khác nhau (20, 50, 100, 500, 1016 bytes) qua CMD_DATA consumer
và ghi lại đầy đủ: TX length, RX code, RX length, conn state, ATTLOG count.

Key: Trước đó CMD 0x59 trả ACK 1501 + data 1016+ bytes khi size đúng 1016.
Thử các sizes khác xem có khác biệt không.
"""
import sys, struct, time, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
import zk
from zk import const
from datetime import datetime

DEVICE_IP = '172.16.0.214'

def encode_time(t):
    return ((t.year % 100) * 12 * 31 + (t.month - 1) * 31 + t.day - 1) * (24 * 60 * 60) + (t.hour * 60 + t.minute) * 60 + t.second

# Test sizes
TEST_SIZES = [4, 8, 16, 20, 40, 50, 100, 500, 1000, 1016, 2000]

# Build different payload patterns
def make_pattern_A(size):
    """Pattern A: Just zeros"""
    return b'\x00' * size

def make_pattern_B(size):
    """Pattern B: All 0xFF"""
    return b'\xff' * size

def make_pattern_C(size):
    """Pattern C: 1 ATTLOG record (40 bytes) padded"""
    ts = encode_time(datetime(2026, 9, 15, 10, 0, 0))
    # Pad name to 24 bytes
    name_bytes = (b'PIN1383\x00' + b'\x00' * 17)[:24]
    base_record = struct.pack('<H24sB4sB8s',
                               1383,
                               name_bytes,
                               48,  # status='0' ASCII
                               struct.pack('<I', ts),
                               15,  # punch=finger
                               b'\x00'*8)
    if size <= 40:
        return base_record[:size]
    return base_record + b'\x00' * (size - 40)

def make_pattern_D(size):
    """Pattern D: TSV header + N records"""
    ts = encode_time(datetime(2026, 9, 15, 10, 30, 0))
    base = b'PIN=1383\tTIME=2026-09-15 10:30:00\tSTATUS=0\tPUNCH=15\tEXTRA='
    # Pad with zeros to desired size
    if size <= len(base):
        return base[:size]
    return base + b'\x00' * (size - len(base))

PATTERNS = {
    'A_zeros': make_pattern_A,
    'B_ff': make_pattern_B,
    'C_attlog_40': make_pattern_C,
    'D_tsv': make_pattern_D,
}

results = []

def run_test(pattern_name, payload, size_label):
    """Run a single test and record all details"""
    print(f'\n--- Test: {pattern_name} ({size_label} = {len(payload)} bytes) ---')
    z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)

    record = {
        'pattern': pattern_name,
        'tx_length': len(payload),
        'rx_code': None,
        'rx_length': None,
        'conn_state': 'init',
        'attlog_count_before': None,
        'attlog_count_after': None,
    }

    try:
        # Connect
        z.connect()
        record['conn_state'] = 'connected'

        # Get baseline
        z.read_sizes()
        record['attlog_count_before'] = z.records

        # Subscribe events (so RTLOG/RTLOG_RRQ-style commands work)
        reg_resp = z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', 0xFF))

        # PREPARE_DATA with size = payload size
        prep = z._ZK__send_command(const.CMD_PREPARE_DATA, struct.pack('I', len(payload)))
        print(f'  PREPARE_DATA: {prep}')

        # CMD_DATA
        try:
            data_resp = z._ZK__send_command(const.CMD_DATA, payload)
            if isinstance(data_resp, dict):
                record['rx_code'] = data_resp.get('code')
                # Get response data length
                rx_data = z._ZK__data
                record['rx_length'] = len(rx_data) if rx_data else 0
            else:
                record['rx_code'] = data_resp
                record['rx_length'] = 0
            print(f'  CMD_DATA RX: code={record["rx_code"]}, len={record["rx_length"]}')
        except Exception as e:
            record['conn_state'] = 'cmd_data_error'
            print(f'  CMD_DATA ERROR: {str(e)[:60]}')

        # FREE_DATA
        try:
            z.free_data()
        except Exception as e:
            print(f'  FREE_DATA: {str(e)[:40]}')

        # Wait
        time.sleep(1)

        # Read ATTLOG count
        try:
            z.read_sizes()
            record['attlog_count_after'] = z.records
            print(f'  ATTLOG: {record["attlog_count_before"]} → {record["attlog_count_after"]}')
            if record['attlog_count_after'] != record['attlog_count_before']:
                delta = record['attlog_count_after'] - record['attlog_count_before']
                print(f'  🔥🔥🔥 ATTLOG CHANGED! delta={delta}')
                record['conn_state'] = 'attlog_changed'
        except Exception as e:
            record['conn_state'] = 'read_attlog_failed'
            print(f'  Read ATTLOG fail: {str(e)[:50]}')

        # Disconnect
        try:
            z.disconnect()
            record['conn_state'] = 'disconnected_clean' if record['conn_state'] not in ('attlog_changed',) else record['conn_state']
        except Exception as e:
            record['conn_state'] = 'disconnect_fail'
            print(f'  Disconnect: {str(e)[:40]}')

    except Exception as e:
        record['conn_state'] = 'connect_fail'
        print(f'  CONNECT ERROR: {str(e)[:60]}')

    results.append(record)
    return record

print('=' * 70)
print(f'ZK X628 PRO - CMD_DATA PAYLOAD SIZE TEST')
print(f'Target: {DEVICE_IP}')
print(f'Sizes: {TEST_SIZES}')
print(f'Patterns: {list(PATTERNS.keys())}')
print('=' * 70)

# Test each pattern with each size
for pattern_name, pattern_fn in PATTERNS.items():
    for size in TEST_SIZES:
        payload = pattern_fn(size)
        run_test(pattern_name, payload, f'{size}B')
        time.sleep(0.5)  # small delay between tests

# Print summary
print('\n' + '=' * 70)
print('SUMMARY')
print('=' * 70)
print(f'{"Pattern":<15} {"Size":<6} {"TX":<5} {"RX code":<10} {"RX len":<6} {"ConnState":<20} {"Before":<8} {"After":<8}')
print('-' * 100)
for r in results:
    print(f'{r["pattern"]:<15} {r["tx_length"]:<6} {r["tx_length"]:<5} {str(r["rx_code"]):<10} {str(r["rx_length"]):<6} {r["conn_state"]:<20} {str(r["attlog_count_before"]):<8} {str(r["attlog_count_after"]):<8}')

# Save results
with open('D:\\chamcong\\zk_cmd_data_payload_test.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nSaved: D:\\chamcong\\zk_cmd_data_payload_test.json')

# Check if any test changed ATTLOG count
changed = [r for r in results if r['attlog_count_after'] != r['attlog_count_before']]
if changed:
    print(f'\n🔥 {len(changed)} test(s) changed ATTLOG count!')
    for r in changed:
        print(f'  {r["pattern"]} {r["tx_length"]}B: {r["attlog_count_before"]} → {r["attlog_count_after"]}')
else:
    print(f'\nNo ATTLOG count change in any test.')
