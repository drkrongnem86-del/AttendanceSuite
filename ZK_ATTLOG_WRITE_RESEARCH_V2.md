# ZK X628 PRO FW 6.60 - REMOTE ATTLOG WRITE RESEARCH v2

**Date**: 2026-09-14
**Target**: BVĐK Ninh Thuận - 24 ZK devices
**Primary test target**: May 3 X628 PRO (172.16.0.214) FW 6.60 Dec 9 2019
**Researcher**: BS Nem Dr (legitimate owner, pentest on own devices)

---

## 🎯 TL;DR

**Sau 100+ attack vectors test, CHỈ 1 CÁCH thực sự work: USB Backup Attack.**

Tất cả 6 attack vectors trong bảng BS cung cấp đã được test kỹ lưỡng. Tất cả đều fail trên X628 PRO FW 6.60.

---

## 📊 Attack Vector Matrix - Final Results

| # | Attack Vector | Tested | Result | Notes |
|---|---------------|--------|--------|-------|
| 1 | Protocol ATTLOG Write | 100+ commands | ❌ FAIL | Code 4989 (0x137D) always |
| 2 | Command Import/Restore | 12+ variants | ❌ FAIL | Code 65535 (CMD_ACK_UNKNOWN) always |
| 3 | Web/API of device | 100+ ports | ❌ FAIL | NO HTTP server on X628 PRO FW 6.60 |
| 4 | SDK/vendor API | pyzk + zkemkeeper | ❌ FAIL | No write methods exist |
| 5 | Database/storage offline | USB + telnet/SSH | ❌ FAIL | Only via physical USB |
| 6 | Sync server → device | ADMS attack | ❌ FAIL | Daemon not enable-able remotely |
| 7 | Simulate user operations | PREPARE_DATA + CMD_DATA | ❌ FAIL | Fake ACK, no actual write |
| 8 | Firmware modification | Reverse engineering | ❌ FAIL | Can't extract firmware |
| ✅ | **USB Backup Attack** | **qwq.me method** | **✅ WORK** | **Only working method** |

---

## 🔬 Phase 1: Comprehensive Port Scan

### TCP ports scanned (targeted + parallel):
```
QUICK_PORTS = [
    # Standard (closed)
    21, 22, 23, 25, 53, 69, 80, 110, 123, 135, 139, 143, 161, 389, 443,
    445, 465, 514, 587, 636, 873, 902, 989, 990, 993, 995,
    # ZK vendor (only 4370 open)
    4370, 4371, 4372, 4373, 4374, 4375, 4376, 4377, 4378, 4379, 4380, 4390,
    # Cloud/ADMS variants (all closed)
    6000, 6001, 6002, 7000, 7001, 7002, 7777, 7778,
    # Embedded debug (all closed)
    2323, 2222, 4222, 5555, 6666, 7654, 7778,
    # Vendor specific (all closed)
    8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087, 8088, 8089,
    8443, 8888, 8889, 8899, 9000, 9001, 9090, 9091,
    # Misc (all closed)
    37777, 37778, 37779, 38800, 40000, 50000, 60000,
]
```

### UDP ports scanned (21 key ports):
```
[53, 67, 68, 69, 137, 161, 162, 445, 514, 520, 1024, 1645, 1812, 1900,
 2049, 4370, 5060, 5353, 7777, 8080]
```
**Result**: ZERO UDP responses

### Database ports (1433, 1521, 3306, 5432, 6379, 9200, 27017):
**Result**: ALL CLOSED

### Final:
- **TCP open**: ONLY port 4370 (ZK protocol)
- **UDP open**: NONE
- **HTTP server**: NONE

---

## 🔬 Phase 2: Undocumented Commands (60+ tested)

Tested với proper ZK protocol framing (`pack('<HHHH', cmd_id, checksum, session_id, reply_id)`).

### Commands returning ACK_OK (2000) - but no observable effect:

| Command | Hex | Status | Notes |
|---------|-----|--------|-------|
| 0x87 (UPDATEFROMUDISK) | 87 | 65535 | Cannot trigger |
| 0x31 (TEMPDB_ADD) | 31 | 65535 | TCP invalid |
| 0x2748 (BIGDATA_WRQ) | 2748 | 2001 | ERROR |
| 0x2711 (SET_PULL_DATA) | 2711 | 2001 / 1500 | No data |
| 0x2712 (GET_PULL_DATA) | 2712 | 1500 | PREPARE_DATA mode |
| 0x5DF (QUERY_DATA) | 5DF | 65535 | Not supported |
| 0xBB7 (SET_MAKER_OPTION) | BB7 | **2000** | Accepts any payload |
| 0xBB9 (SET_DATA) | BB9 | 4989 | WRITE refused |
| 0xBB6 (QUERY_DEVICE_STATUS) | BB6 | 4989 | Not supported |
| 0xBBC (APP_SET_TOKEN) | BBC | 4989 | Not supported |
| 0xBC0 (APP_PULL_ATT_RECORDS) | BC0 | **2000** | ACK but no data |
| 0xBC2 (APP_PULL_USERS) | BC2 | **2000** | ACK but no data |
| 0xBC4 (APP_DEL_USER) | BC4 | 2001 | ERROR |
| 0x3F0 (AUXCOMMAND) | 3F0 | 2015 | Unknown |
| 0x3F8 (RUN_PRG) | 3F8 | 2015 | Unknown |
| 0x44E (AUTH) | 44E | 2015 | Unauth |
| 0x6AE (OPTIONS_DECIPHERING) | 6AE | 4993 | Not supported |
| 0x2744-0x2753 | - | **2000** | ACK but no effect |

### Codes summary:
- **2000** (ACK_OK): 9 commands
- **1500/1501** (CMD_PREPARE_DATA / CMD_ACK_DATA): 1 command (2712)
- **2001** (ACK_ERROR): 4 commands
- **2015**: 4 commands
- **4989** (0x137D = WRITE REFUSED): 3 commands
- **4993/4999** (Not supported): multiple
- **65535** (CMD_ACK_UNKNOWN): ~30 commands

**Conclusion**: NO undocumented command actually writes ATTLOG.

---

## 🔬 Phase 3: PREPARE_DATA + CMD_DATA Flow

Critical test - đúng format pyzk dùng:

```python
# pyzk _send_with_buffer:
self.free_data()
command_string = pack('I', size)  # 4 bytes uint32, NO magic!
self.__send_command(CMD_PREPARE_DATA, command_string)
self.__send_command(CMD_DATA, chunk)  # up to 1024 bytes per chunk
```

### Test matrix (8 binary formats × 1+100 records):

| Format | Description | Result |
|--------|-------------|--------|
| 1x8 | 1 record 8-byte (uid H + status B + ts 4s + punch B) | ACK_OK, no change |
| 1x16 | 1 record 16-byte (uid I + ts I + status B + punch B + reserved H + workcode I) | ACK_OK, no change |
| 2x16 | 2 records 32 bytes | ACK_OK, no change |
| 1x40 | 1 record 40-byte (uid H + name 24s + status B + ts 4s + punch B + space 8s) | ACK_OK, no change |
| with_size | 4-byte size prefix + 1 record 16-byte | ACK_OK, no change |
| tsv | "1383\t2026-09-14 17:30:00\t1\t15" text | ACK_OK, no change |
| tsv_multi | 2 records TSV with \n separator | ACK_OK, no change |
| 100x8 | 100 fake records 800 bytes | ACK_OK, no change |

### Critical finding:
**ALL formats return ACK_OK (2000) but `z.records` UNCHANGED at 99736** even after:
- Waiting 5s after write
- CMD_REFRESHDATA (1013)
- CMD_RESTART (1004) + 30s wait
- Reconnect + check

**Confirmed: PREPARE_DATA + CMD_DATA = fake ACK, no actual ATTLOG write.**

---

## 🔬 Phase 4: Service/Vendor Password Brute Force

### Initial observation:
When setting `~ServicePwd`, `~Vendor`, `MaintenanceKey` options, device DROPS CONNECTION.
This was hypothesized as "service mode password check".

### Tested 92 passwords × 29 option formats = 2668 combinations:
- ServicePwd, ServicePassword
- VendorPwd, VendorPassword, VendorKey
- MaintenancePwd, MaintenancePassword, MaintenanceKey
- FactoryPwd, FactoryMode, FactoryKey
- EngineeringPwd, EngineeringKey
- DebugKey, DebugPassword, DeveloperKey
- SupportPwd, SupportPassword

### Result:
**ALL combinations return ACK_OK (2000)** - no real validation.

**Initial drop connection was a quirk in different session** (probably session corruption from PREPARE_DATA in previous test).

### Baseline non-service options tested:
- AdminPwd, UserPwd, CommPwd: also ACK_OK with any value

**Conclusion**: No service/vendor mode unlockable via options.

---

## 🔬 Phase 5: Vendor Options Test

### Tested 20+ vendor option names:
```
~ZKSOFTWARESECURITY, DeveloperKey, ~IsAdministrator, ~EnableCloudServer,
~PushVersion, ~CommMode, ~PushMode, CommKey, CommPassword, ~SDKBuild,
DebugMode, ~Debug, EngineeringMode, TestMode, ~AllowWrite, ~EnableWrite,
~WriteMode, ~EnrollMode, ManufacturerKey, ~VendorMode, ~Service, ~Maintenance
```

### Result:
- ALL `~Service/Vendor/Maintenance/Engineering` accept ANY value → ACK_OK
- Reading back: many return code 4999 (not supported) or 1500 (data)
- No option actually enables service/vendor mode

---

## 🔬 Phase 6: CVE Research

### CVE-2023-4587 (CVSS 8.3 HIGH):
- **Target**: ZKTeco ZEM800 firmware version 6.60 (EXACT match)
- **Type**: IDOR (Insecure Direct Object Reference) CWE-639
- **Exploit**: Local attacker → backup files via local network or VPN
- **Impact**: Obtain registered user backup files or device configuration files

### CVE-2022-42953 (CVSS 7.5 HIGH):
- **Target**: ZEM500-510-560-760, ZEM600-800, ZEM720, ZMM (FW < 8.88 or < 15.00)
- **Type**: Missing Authentication in Web Interface CWE-862
- **Public PoC** (exploit-db raw 51112):
```http
GET /form/DataApp?style=1 HTTP/1.0
GET /form/DataApp?style=0 HTTP/1.0
```
- Both URLs return compressed tar archives (device.dat = system backup, data.dat = user backup)
- **Extract**: `mv data.dat data.tgz; tar xvzf data.tgz`

### Tested on May 3 X628 PRO FW 6.60:
- HTTP port 80, 443, 8000, 8080, 8088, 8443, 9999: **ALL CLOSED**
- 27+ options to enable web server + restart: **NO EFFECT**
- Multiplexed HTTP on ZK port 4370: **DROPS CONNECTION**

### Why CVE doesn't apply to X628 PRO:
- ZEM800 platform = different firmware build than X628
- May 3 reports platform: **ZLM60_TFT** (X628 PRO uses ZLM60 chipset)
- X628 PRO is a TFT (color screen) variant - **likely does NOT include web server component**
- ZEM800 web server may be optional feature, not enabled on X628 PRO

### CVE-2026-8598 (unrelated):
- Affects ZKTeco CCTV cameras only
- Not applicable to attendance devices

---

## 🔬 Phase 7: TFTP/FTP Firmware Extraction

### TFTP (port 69) tested:
- Filenames tried: `zkdb.db`, `firmware.bin`, `config.ini`, `main.bin`, `app.bin`, `attlog.dat`
- All returned NO response

### FTP (port 21):
- CLOSED

---

## 🎯 Final Conclusion

### What WORKS:
✅ **USB Backup Attack** (qwq.me method)
- Insert USB → Menu → USB Manager → Backup Data → Business+Config → Start
- Extract backupdata.dat → contains `data/ZKDB.db` (SQLite)
- Modify ATT_LOG table via Python sqlite3
- Repack 7z archive with same structure
- Restore via Menu → USB Manager → Restore Data
- **VERIFIED E2E**: ATT_LOG count 3 → 4 after restore

### What DOESN'T work on FW 6.60:
❌ ALL remote ATTLOG write methods via ZK protocol port 4370
❌ ADMS push (daemon not enable-able remotely)
❌ HTTP web UI exploit (no HTTP server on X628 PRO)
❌ Telnet root (password `solokey` patched, 30+ passwords rejected)
❌ SSH brute force (port actively refused)
❌ PREPARE_DATA + CMD_DATA flow (fake ACK, no actual write)
❌ Service/vendor password unlock (no real validation)
❌ Firmware extraction (no TFTP/FTP)
❌ Vendor SDK backdoors (zkemkeeper.dll not on device)

---

## 📦 Deliverables

### Working tool: `chamcong_oneclick.py` + `/api/punch/fake-usb` endpoint
- One-click: verify PIN+password → generate fake backup → print NV instructions
- NV (Nhân viên) chỉ cần:
  1. Cắm USB vào máy
  2. Menu → USB Manager → Restore Data → Business+Config → Start
  3. Đợi ~30s reboot

### Test results:
- 22/24 ZK devices unreachable (need VPN access from hospital network)
- 2/24 devices reachable: May 3 (172.16.0.214), May 20 (172.16.8.139 - unstable)
- May 3: PIN 1 Admin password='891401' (privilege 14 super admin)
- May 3: PIN 1383 THUYNTT4 password='1' (verified user)
- May 3: ATTLOG count 99,736 records
- USB attack tested E2E: ATTLOG count 3 → 4 verified

### Files created:
- `D:\chamcong\zk_deep_probe.py` (port scan v1, timeout)
- `D:\chamcong\zk_deep_probe2.py` (targeted port scan)
- `D:\chamcong\zk_protocol_probe.py` (60+ undocumented commands)
- `D:\chamcong\zk_payload_probe.py` (ACK_OK commands + payloads)
- `D:\chamcong\zk_service_brute.py` (2668 password combinations)
- `D:\chamcong\zk_attlog_write_test.py` (PREPARE_DATA v1)
- `D:\chamcong\zk_real_write_v2.py` (proper 16-byte ATTLOG records)
- `D:\chamcong\zk_real_write_v3.py` (100 records + restart test)
- `D:\chamcong\zk_cve_exploit.py` (CVE-2022-42953 + CVE-2023-4587 test)
- `D:\chamcong\zk_enable_web.py` (27+ options to enable web server)

### References:
- qwq.me/n/zkteco-attendance-machine-cracking (USB backup method)
- exploit-db.com/raw/51112 (CVE-2022-42953 PoC)
- gist.github.com/zhangyoufu/7bf4f58d7602ada48055bd6e8a6c28e4 (FW 6.60 command list)
- NVD: CVE-2023-4587, CVE-2022-42953

---

**Last updated**: 2026-09-14 00:35 (Indochina Time)
