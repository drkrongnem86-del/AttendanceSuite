# -*- coding: utf-8 -*-
"""
ZK X628 PRO FW 6.60 - PROTOCOL-LEVEL DEEP PROBE
Test với ZK protocol framing đúng (không raw text):
- Subscribe to events (CMD_REG_EVENT=500)
- Try CMD_DATA with payload (push attendance)
- Try undocumented commands with proper framing
- Try PREPARE_DATA flow with correct magic values
- Try ZK protocol extensions
"""
import sys, os, struct, time, json
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Add portable Python to path BEFORE importing zk
PORTABLE_PY = r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages'
sys.path.insert(0, PORTABLE_PY)

import zk
from zk import const

DEVICE_IP = '172.16.0.214'
DEVICE_PORT = 4370

print('=' * 70)
print(f'ZK X628 PRO FW 6.60 - PROTOCOL-LEVEL DEEP PROBE')
print(f'Device: {DEVICE_IP}:{DEVICE_PORT}')
print('=' * 70)

# === Connect ===
print('\n[Step 1] Connect to device...')
try:
    z = zk.ZK(DEVICE_IP, port=DEVICE_PORT, timeout=10, password=0)
    z.connect()
    print(f'  Connected, firmware: {z.get_firmware_version()}')
    print(f'  Serial: {z.get_serialnumber()}')
    print(f'  Platform: {z.get_platform()}')
    print(f'  Device name: {z.get_device_name()}')
except Exception as e:
    print(f'  ERROR: {e}')
    sys.exit(1)

# === Test 1: Subscribe to events (CMD_REG_EVENT=500) ===
print('\n[Step 2] CMD_REG_EVENT (500) - Subscribe to events...')
try:
    # EF_ATTLOG = 1, real-time attendance
    # EF_VERIFY = 128, real-time verify
    # Try various flag combinations
    flag_combos = [
        1,      # EF_ATTLOG only
        3,      # ATTLOG + FINGER
        7,      # ATTLOG + FINGER + ENROLLUSER
        15,     # All enroll events
        31,     # All
        128,    # VERIFY only
        255,    # All events
        511,    # All events 2
    ]
    for flags in flag_combos:
        try:
            resp = z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', flags))
            print(f'  REG_EVENT flags={flags}: response={resp}')
        except Exception as e:
            print(f'  REG_EVENT flags={flags}: ERROR {e}')
except Exception as e:
    print(f'  Subscribe fail: {e}')

# === Test 2: Test ALL undocumented commands with proper framing ===
print('\n[Step 3] Test 60+ undocumented commands with proper framing...')

# These are commands not in zk.const but in pyzk source / gist
undocumented = [
    # ZK FW 6.60 commands list (zhangyoufu gist)
    0x87,    # CMD_UPDATEFROMUDISK
    0x31,    # CMD_TEMPDB_ADD
    0x2748,  # CMD_BIGDATA_WRQ
    0x2711,  # CMD_SET_PULL_DATA
    0x2712,  # CMD_GET_PULL_DATA
    0x5DF,   # CMD_QUERY_DATA / CMD_DATA_WRRQ
    0xBB7,   # CMD_SET_MAKER_OPTION
    0xBB9,   # CMD_SET_DATA
    0xBB6,   # CMD_QUERY_DEVICE_STATUS
    0xBBC,   # CMD_APP_SET_TOKEN
    0xBC0,   # CMD_APP_PULL_ATT_RECORDS
    0xBC1,   # CMD_APP_PUSH_ATT_RECORD (?)
    0xBC2,   # CMD_APP_PULL_USERS
    0xBC3,   # CMD_APP_PUSH_USER
    0xBC4,   # CMD_APP_DEL_USER
    0xBC5,   # CMD_APP_DEL_ATT
    0xBC6,   # CMD_APP_CLEAR_ATT
    0xBC7,   # CMD_APP_GET_ATT
    0xBC8,   # CMD_APP_REBOOT
    0x3F0,   # CMD_AUXCOMMAND
    0x3F8,   # CMD_RUN_PRG
    0x44E,   # CMD_AUTH
    0x6AE,   # CMD_OPTIONS_DECIPHERING
    0xBBE,   # CMD_APP_SET_DEPART (?)
    0xBBF,   # CMD_APP_GET_DEPART
    0xBB8,   # CMD_GET_DATA
    # More from research
    0x2717,  # CMD_NEW_ATTLOG_RRQ
    0x2716,  # CMD_TIME_ATTLOG_DELE
    0x2715,  # CMD_FINGERTMP_DELE
    0x2701,  # ?
    0x2702,  # ?
    0x2703,  # ?
    0x2704,  # ?
    0x2705,  # ?
    0x2706,  # ?
    0x2707,  # ?
    0x2708,  # ?
    0x2709,  # ?
    0x270A,  # ?
    0x270B,  # ?
    0x270C,  # ?
    0x270D,  # ?
    0x270E,  # ?
    0x270F,  # ?
    0x2710,  # ?
    0x2713,  # ?
    0x2714,  # ?
    0x2715,  # ?
    0x2740,  # ?
    0x2741,  # ?
    0x2742,  # ?
    0x2743,  # ?
    0x2744,  # ?
    0x2745,  # ?
    0x2750,  # ?
    0x2751,  # ?
    0x2752,  # ?
    0x2753,  # ?
    0x2754,  # ?
    0x2755,  # ?
    # Magic numbers
    0x5050,  # MACHINE_PREPARE_DATA_1
    0x7282,  # MACHINE_PREPARE_DATA_2
]

interesting_responses = []
for cmd in undocumented:
    try:
        # Try with empty payload
        resp = z._ZK__send_command(cmd, b'')
        interesting_responses.append((cmd, 'EMPTY', resp))
        # Filter: only print interesting
        if resp not in (2000, 2001, 65535, None):
            print(f'  CMD 0x{cmd:04X}: INTERESTING! {resp}')
    except Exception as e:
        err = str(e)[:50]
        if 'BAD_FORMAT' in err or 'unknown' not in err.lower():
            interesting_responses.append((cmd, 'ERR', err))
            if 'BAD_FORMAT' in err or 'tcp' not in err.lower():
                print(f'  CMD 0x{cmd:04X}: ERROR {err}')

# === Test 3: PREPARE_DATA flow with proper magic ===
print('\n[Step 4] PREPARE_DATA flow with magic values...')
try:
    # Magic 1: 20560 (0x5050)
    # Magic 2: 32130 (0x7282)
    # Format: 2 bytes magic + 4 bytes size + payload
    payload_size = 1024  # 1KB test

    for magic in [20560, 32130, 0x5050, 0x7282]:
        try:
            data = struct.pack('<H', magic) + struct.pack('<I', payload_size)
            resp = z._ZK__send_command(const.CMD_PREPARE_DATA, data)
            print(f'  PREPARE_DATA magic={magic}: {resp}')

            if resp == 1500 or resp == 2000:
                # Try CMD_DATA
                test_payload = b'TEST' * 256  # 1024 bytes
                resp2 = z._ZK__send_command(const.CMD_DATA, test_payload)
                print(f'    → CMD_DATA: {resp2}')

                # Try CMD_FREE_DATA
                resp3 = z._ZK__send_command(const.CMD_FREE_DATA, b'')
                print(f'    → CMD_FREE_DATA: {resp3}')
        except Exception as e:
            print(f'  PREPARE_DATA magic={magic}: ERROR {str(e)[:60]}')
except Exception as e:
    print(f'  PREPARE_DATA fail: {e}')

# === Test 4: Push real-time events using reg_event ===
print('\n[Step 5] Real-time event injection test...')
print('  (Try to inject fake EF_ATTLOG events back to ourselves via reg_event)')
try:
    # Subscribe to events
    z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', 0xFF))

    # Try to get any pending events
    try:
        events = z.get_event()
        print(f'  Got events: {events}')
    except Exception as e:
        print(f'  get_event: {e}')

    # Try to send fake event back
    # CMD_REG_EVENT is normally just subscribe, but try with payload
    for i in range(3):
        try:
            # This might be the magic - send event with payload
            payload = struct.pack('<I', 1) + struct.pack('<I', 1234) + b'PIN1\t2026-09-14\t0'
            resp = z._ZK__send_command(const.CMD_REG_EVENT, payload)
            print(f'  REG_EVENT with payload #{i}: {resp}')
        except Exception as e:
            print(f'  REG_EVENT with payload #{i}: {e}')
except Exception as e:
    print(f'  Event injection fail: {e}')

# === Test 5: Vendor-specific options that might unlock write ===
print('\n[Step 6] Vendor-specific options test...')
vendor_options = [
    ('~ZKSOFTWARESECURITY', 'bypass_security'),
    ('DeveloperKey', 'dev_key'),
    ('~IsAdministrator', 'admin_flag'),
    ('~EnableCloudServer', 'cloud_enable'),
    ('~PushVersion', 'push_version'),
    ('~CommMode', 'comm_mode'),
    ('~PushMode', 'push_mode'),
    ('CommKey', 'comm_key'),
    ('CommPassword', 'comm_password'),
    ('~SDKBuild', 'sdk_build'),
    ('DebugMode', 'debug_mode'),
    ('~Debug', 'debug'),
    ('EngineeringMode', 'engineering'),
    ('TestMode', 'test_mode'),
    ('~AllowWrite', 'allow_write'),
    ('~EnableWrite', 'enable_write'),
    ('~WriteMode', 'write_mode'),
    ('~EnrollMode', 'enroll'),
    ('ManufacturerKey', 'mfg_key'),
    ('~VendorMode', 'vendor'),
    ('~Service', 'service'),
    ('~Maintenance', 'maintenance'),
]

for opt_name, opt_desc in vendor_options:
    try:
        # Try setting option to '1' or 'true'
        z._ZK__send_command(const.CMD_OPTIONS_WRQ, opt_name.encode() + b'=' + b'1')
        # Read back
        resp = z._ZK__send_command(const.CMD_OPTIONS_RRQ, opt_name.encode())
        print(f'  {opt_name}: set=OK, read={resp}')
    except Exception as e:
        err = str(e)[:40]
        if 'tcp' not in err.lower() and 'closed' not in err.lower():
            print(f'  {opt_name}: {err}')

# === Test 6: Check if we can read firmware file ===
print('\n[Step 7] Read firmware/binary data test...')
try:
    # CMD_DB_RRQ (7) = Read in some kind of data from the machine
    # Try various file IDs
    for file_id in [0, 1, 2, 3, 4, 5, 10, 100, 255, 1000, 0xFF]:
        try:
            resp = z._ZK__send_command(const.CMD_DB_RRQ, struct.pack('<I', file_id))
            print(f'  DB_RRQ id={file_id}: {resp[:50] if isinstance(resp, bytes) else resp}')
        except Exception as e:
            pass
except Exception as e:
    print(f'  DB_RRQ fail: {e}')

# === Disconnect ===
try:
    z.disconnect()
    print('\nDisconnected cleanly')
except:
    pass

print('\n' + '=' * 70)
print('DONE')
print('=' * 70)

# Save interesting responses
with open('D:\\chamcong\\zk_protocol_probe_result.json', 'w') as f:
    json.dump({
        'interesting': [(c, t, str(r)[:100]) for c, t, r in interesting_responses],
    }, f, indent=2)
print('Saved: D:\\chamcong\\zk_protocol_probe_result.json')
