# -*- coding: utf-8 -*-
"""
ZK X628 PRO - RTLOG with subscription
Subscribe to events first, then read RTLOG.
Also try STARTVERIFY + CAPTUREFINGER to trigger events.
"""
import sys, struct, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')
import zk
from zk import const

DEVICE_IP = '172.16.0.214'

z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
z.connect()
print(f'Connected')

# Subscribe to events first
print('\n[1] Subscribe to events...')
resp = z._ZK__send_command(const.CMD_REG_EVENT, struct.pack('<I', 0xFF))
print(f'  REG_EVENT 0xFF: {resp}')

# Read RTLOG right away
print('\n[2] CMD_RTLOG_RRQ after subscription...')
resp = z._ZK__send_command(0x5A, b'', response_size=8192)
data = z._ZK__data
print(f'  Code: {resp}, data_len: {len(data) if data else 0}')
if data and len(data) > 4:
    total = struct.unpack('<I', data[:4])[0]
    print(f'  Total: {total}')
    print(f'  First 100: {data[4:104].hex()}')

# Trigger verify
print('\n[3] CMD_STARTVERIFY (60)...')
try:
    payload = struct.pack('<II', 1383, 1)  # uid=1383, fp_idx=1
    resp = z._ZK__send_command(const.CMD_STARTVERIFY, payload, response_size=1024)
    print(f'  STARTVERIFY: {resp}')
    data = z._ZK__data
    if data:
        print(f'  data[:100]={data[:100].hex()}')
except Exception as e:
    print(f'  ERROR: {e}')

time.sleep(2)

# Read RTLOG
print('\n[4] RTLOG after STARTVERIFY...')
resp = z._ZK__send_command(0x5A, b'', response_size=8192)
data = z._ZK__data
print(f'  Code: {resp}, data_len: {len(data) if data else 0}')
if data and len(data) > 4:
    print(f'  First 200: {data[4:204].hex()}')

# Try free events queue
try:
    # Maybe read queued events
    print('\n[5] Try reading events with cmd_response in different way...')
    for cmd in [0x5A, const.CMD_REG_EVENT, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60, 0x61, 0x62]:
        try:
            resp = z._ZK__send_command(cmd, b'', response_size=1024)
            code = resp.get('code') if isinstance(resp, dict) else resp
            data = z._ZK__data
            if data and len(data) > 4:
                total = struct.unpack('<I', data[:4])[0]
                print(f'  CMD 0x{cmd:04X}: code={code} data_len={len(data)} total={total}')
        except Exception as e:
            try:
                z.disconnect()
            except:
                pass
            z = zk.ZK(DEVICE_IP, port=4370, timeout=10, password=0)
            try:
                z.connect()
            except:
                pass

z.disconnect()
print('Done')
