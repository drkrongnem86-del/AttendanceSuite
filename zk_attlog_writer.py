"""
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
    user_id = data[2:26].rstrip(b'\x00').decode('utf-8', errors='replace')
    status = chr(data[26])
    ts = struct.unpack('<I', data[27:31])[0]
    punch = data[31]
    dt = decode_time(ts)
    return {'pin': pin, 'user_id': user_id, 'status': status, 'ts': ts, 'datetime': dt, 'punch': punch}
