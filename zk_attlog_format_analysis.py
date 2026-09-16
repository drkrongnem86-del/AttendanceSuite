"""
Correlation analysis: Binary ATTLOG format (40 bytes from pyzk) vs SQLite schema.

This builds the writer function for inserting fake ATTLOG records via protocol.
"""
import os
import sys
import struct
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

print('='*70)
print('ZK ATTLOG FORMAT CORRELATION')
print('='*70)

# Binary format from pyzk source (40 bytes):
# +0  uid      uint16 LE (PIN)
# +2  user_id  24 bytes (zero-padded UTF-8)
# +26 status   uint8 (ASCII 48/49 = '0'/'1')
# +27 ts       uint32 LE (encoded time)
# +31 punch    uint8 (VERIFYCODE: 0/1/15)
# +32 space    8 bytes (padding)

# Encoded timestamp from pyzk source:
def encode_time(t):
    """Encode datetime to ZK 32-bit timestamp"""
    return ((t.year % 100) * 12 * 31 + (t.month - 1) * 31 + t.day - 1) * 86400 + t.hour * 3600 + t.minute * 60 + t.second


def decode_time(enc):
    """Decode ZK 32-bit timestamp to datetime"""
    sec = enc % 60
    minute = (enc // 60) % 60
    hour = (enc // 3600) % 24
    days = enc // 86400
    day_of_year = days % (12 * 31)
    year_offset = days // (12 * 31)
    year = year_offset + 2000  # assume 21st century
    month = day_of_year // 31 + 1
    day = day_of_year % 31 + 1
    try:
        return datetime(year, month, day, hour, minute, sec)
    except Exception:
        return None


# Test encode/decode roundtrip
test_dt = datetime(2026, 9, 15, 14, 30, 45)
enc = encode_time(test_dt)
dec = decode_time(enc)
print(f'\nTest roundtrip: {test_dt} -> encoded {enc} -> decoded {dec}')
print(f'  Match: {test_dt == dec}')

# Test with real data from SQLite
import sqlite3
db_path = r'D:/chamcong/zk_fw_attempts/business_extracted/000_ZKDB.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT User_PIN, Verify_Time, Verify_Type, Status FROM ATT_LOG LIMIT 5")
records = []
for row in cur.fetchall():
    records.append(row)
conn.close()

print('\nSample SQLite ATTLOG rows (May 14 2018 fw):')
for pin, vt, vtype, status in records:
    iso_time = vt  # like '2026-08-15T10:30:00'
    dt = datetime.fromisoformat(iso_time)
    enc = encode_time(dt)
    print(f'  PIN={pin}, Verify_Type={vtype}, Verify_Time={iso_time}, Status={status}')
    print(f'    -> datetime={dt}, encoded_timestamp={enc}')


# Build the protocol-level writer function
def build_attlog_record(pin, user_id, status, dt, punch=15):
    """
    Build a 40-byte ATTLOG record in device binary format.

    Args:
        pin: User PIN (int)
        user_id: User ID string (max 24 chars)
        status: 0 (in) or 1 (out)
        dt: datetime
        punch: VERIFYCODE (0=password, 1=card, 15=fingerprint, 14=admin)
    """
    rec = bytearray(40)
    # uid (2 bytes)
    struct.pack_into('<H', rec, 0, int(pin))
    # user_id (24 bytes, zero-padded)
    uid_bytes = user_id.encode('utf-8')[:24]
    rec[2:2+len(uid_bytes)] = uid_bytes
    # status (1 byte ASCII)
    rec[26] = ord('0') if status == 0 else ord('1')
    # timestamp (4 bytes LE)
    enc = encode_time(dt)
    struct.pack_into('<I', rec, 27, enc)
    # punch (1 byte)
    rec[31] = punch
    # padding already zeros
    return bytes(rec)


# Verify against real binary data from pyzk
print('\n' + '='*70)
print('WRITER FUNCTION DEMO')
print('='*70)
import struct

# Build fake record
fake = build_attlog_record(
    pin=1,
    user_id='1',
    status=0,
    dt=datetime(2026, 9, 15, 15, 0, 0),
    punch=15  # fingerprint
)
print(f'Built 40-byte record: {fake.hex()}')
print(f'  uid={struct.unpack("<H", fake[:2])[0]}')
print(f'  user_id={fake[2:26].rstrip(b"\\x00").decode()}')
print(f'  status={chr(fake[26])}')
print(f'  ts={struct.unpack("<I", fake[27:31])[0]} -> {decode_time(struct.unpack("<I", fake[27:31])[0])}')
print(f'  punch={fake[31]}')

# Save writer to a module
writer_module = '''"""
ATTLOG binary record writer for ZK FW 6.60 protocol.
40-byte format verified via pyzk source.
"""
import struct
from datetime import datetime


def encode_time(t):
    """Encode datetime to ZK 32-bit timestamp.
    Format: ((year%100) * 12 * 31 + (month-1) * 31 + (day-1)) * 86400
            + hour*3600 + minute*60 + second
    """
    return ((t.year % 100) * 12 * 31 + (t.month - 1) * 31 + t.day - 1) * 86400 + t.hour * 3600 + t.minute * 60 + t.second


def decode_time(enc):
    """Decode ZK 32-bit timestamp to datetime. Inverse of encode_time."""
    sec = enc % 60
    minute = (enc // 60) % 60
    hour = (enc // 3600) % 24
    days = enc // 86400
    day_of_year = days % (12 * 31)
    year_offset = days // (12 * 31)
    year = year_offset + 2000  # assume 21st century
    month = day_of_year // 31 + 1
    day = day_of_year % 31 + 1
    try:
        return datetime(year, month, day, hour, minute, sec)
    except Exception:
        return None


def build_attlog_record(pin, user_id, status, dt, punch=15):
    """
    Build a 40-byte ATTLOG record in device binary format.

    Args:
        pin: User PIN (int)
        user_id: User ID string (max 24 chars UTF-8)
        status: 0 (check-in) or 1 (check-out)
        dt: datetime object
        punch: VERIFYCODE (0=password, 1=card, 15=fingerprint, 14=admin)

    Returns:
        40-byte binary record
    """
    rec = bytearray(40)
    struct.pack_into('<H', rec, 0, int(pin))
    uid_bytes = user_id.encode('utf-8')[:24]
    rec[2:2+len(uid_bytes)] = uid_bytes
    rec[26] = ord('0') if status == 0 else ord('1')
    enc = encode_time(dt)
    struct.pack_into('<I', rec, 27, enc)
    rec[31] = punch
    return bytes(rec)


def parse_attlog_record(data):
    """Parse a 40-byte ATTLOG record into dict."""
    if len(data) < 40:
        return None
    pin = struct.unpack('<H', data[:2])[0]
    user_id = data[2:26].rstrip(b'\\x00').decode('utf-8', errors='replace')
    status = chr(data[26])
    ts = struct.unpack('<I', data[27:31])[0]
    punch = data[31]
    dt = decode_time(ts)
    return {'pin': pin, 'user_id': user_id, 'status': status, 'ts': ts, 'datetime': dt, 'punch': punch}
'''

out_path = 'D:/chamcong/zk_attlog_writer.py'
with open(out_path, 'w') as f:
    f.write(writer_module)
print(f'\nSaved writer module: {out_path}')

# Verify against existing USB backup format
print('\n' + '='*70)
print('CROSS-REFERENCE WITH USB BACKUP')
print('='*70)
# Get one ATT_LOG record from USB backup
import py7zr
import os
# USB backup extracted earlier
zkdb_usb_path = 'D:/chamcong/zk_fw_attempts/bs_test.dat.extracted/data/ZKDB.db'
if os.path.exists(zkdb_usb_path):
    sz = os.path.getsize(zkdb_usb_path)
    print(f'USB backup ZKDB.db: {sz} bytes')
    conn = sqlite3.connect(zkdb_usb_path)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM ATT_LOG')
    print(f'  ATT_LOG rows: {cur.fetchone()[0]}')
    cur.execute('SELECT * FROM ATT_LOG LIMIT 3')
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        print(f'  {dict(zip(cols, row))}')
    conn.close()
else:
    print(f'USB backup not found: {zkdb_usb_path}')