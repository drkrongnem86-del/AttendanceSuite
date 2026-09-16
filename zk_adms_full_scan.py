"""
zk_adms_full_scan.py
====================

Sau khi biết ADMS đã enable sẵn, cần check các option về:
- ServerAddr (địa chỉ ADMS server)
- ServerPort (port ADMS server)
- DomainName (FQDN vs IP)
- EnableDomain
- HTTPS

Mục đích: tìm xem ServerAddr đang được set là gì, fix lại cho đúng.
"""

import sys
import time
import json

sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, r'D:\chamcong\AttendanceSuite_Portable\python\Lib\site-packages')

from zk import ZK, const


DEVICE_IP = '172.16.0.214'
DEVICE_PORT = 4370

def read_option(conn, key):
    try:
        cmd_response = conn._ZK__send_command(const.CMD_OPTIONS_RRQ, key.encode() + b'\x00', 1024)
        if cmd_response.get('status'):
            data = conn._ZK__data
            if b'=' in data:
                val = data.split(b'=', 1)[-1].split(b'\x00')[0]
                return val.decode('utf-8', errors='ignore')
            return data.split(b'\x00')[0].decode('utf-8', errors='ignore')
    except:
        pass
    return None


def main():
    zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=0, force_udp=False, ommit_ping=False, verbose=False)
    conn = zk.connect()
    print(f"Connected to {DEVICE_IP}")

    # Comprehensive option scan focused on ADMS/Server config
    print("\n=== ADMS / Server config scan ===")

    option_keys = [
        # Server addresses
        'ServerAddr', '~ServerAddr', 'ServerAddress', '~ServerAddress',
        'Server', '~Server', 'ServerIP', '~ServerIP',
        'ServerHost', '~ServerHost', 'HostName', '~HostName',
        'DomainName', '~DomainName', 'Domain', '~Domain',
        'EnableDomain', '~EnableDomain', 'EnableDomainName', '~EnableDomainName',
        'DomainEnable', '~DomainEnable',

        # Server port
        'ServerPort', '~ServerPort', 'Port', '~Port',
        'ListenPort', '~ListenPort',

        # Push protocol
        'PushServer', '~PushServer', 'PushServerAddr', '~PushServerAddr',
        'PushServerPort', '~PushServerPort', 'PushHost', '~PushHost',
        'PushIP', '~PushIP', 'PushURL', '~PushURL',
        'CloudServer', '~CloudServer', 'CloudServerAddr', '~CloudServerAddr',
        'CloudServerPort', '~CloudServerPort', 'CloudAddress', '~CloudAddress',
        'ADMS', '~ADMS', 'ADMSAddr', '~ADMSAddr', 'ADMSPort', '~ADMSPort',
        'ADMSURL', '~ADMSURL', 'ADMSServer', '~ADMSServer',
        'ADMSAddress', '~ADMSAddress',

        # Other cloud/PUSH
        'Cloud', '~Cloud', 'CloudAddr', '~CloudAddr',
        'CloudPort', '~CloudPort', 'CloudMode', '~CloudMode',
        'HTTPS', '~HTTPS', 'SSL', '~SSL', 'TLS', '~TLS',
        'Encrypt', '~Encrypt',

        # Comm / Push
        'CommType', '~CommType', 'CommProtocol', '~CommProtocol',
        'CommMode', '~CommMode', 'CommKey', '~CommKey',
        'CommKeyType', '~CommKeyType', 'CommunicationType', '~CommunicationType',

        # PUSH SDK
        'PushVer', '~PushVer', 'PushProtVer', '~PushProtVer',
        'PushVersion', '~PushVersion', 'PushFlag', '~PushFlag',
        'PushMode', '~PushMode', 'PushEnable', '~PushEnable',
        'PushInterval', '~PushInterval', 'PushServerType', '~PushServerType',

        # Realtime / intervals
        'Realtime', '~Realtime', 'Delay', '~Delay', 'ErrorDelay', '~ErrorDelay',
        'TransFlag', '~TransFlag', 'TransInterval', '~TransInterval',
        'TransTimes', '~TransTimes', 'TransData', '~TransData',

        # Stamps
        'Stamp', '~Stamp', 'OpStamp', '~OpStamp',
        'ATTLOGStamp', '~ATTLOGStamp', 'OPERLOGStamp', '~OPERLOGStamp',
        'BIODATAStamp', '~BIODATAStamp', 'ATTPHOTOStamp', '~ATTPHOTOStamp',

        # Server Type (we know this is 0)
        'ServerType', '~ServerType', 'ServerMode', '~ServerMode',
        'ServerEnable', '~ServerEnable', 'ServerType2', '~ServerType2',

        # HTTP / URL
        'URL', '~URL', 'WebURL', '~WebURL',
        'HttpURL', '~HttpURL', 'WebServerURL', '~WebServerURL',
        'HttpsURL', '~HttpsURL',

        # Device type
        'DeviceType', '~DeviceType', 'PushType', '~PushType',
        'AccPush', '~AccPush', 'AttPush', '~AttPush',
    ]

    found_options = {}
    for opt in option_keys:
        val = read_option(conn, opt)
        if val is not None:
            found_options[opt] = val
            print(f"  {opt} = {val}")

    # Save
    out = f"D:\\chamcong\\zk_adms_full_scan_{int(time.time())}.json"
    with open(out, 'w') as f:
        json.dump(found_options, f, indent=2, default=str)
    print(f"\n[SAVED] {out}")

    conn.disconnect()


if __name__ == '__main__':
    main()
