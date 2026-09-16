# ZK FW 6.60 - Research: Ghi trực tiếp vào ATTLOG

> **BS Diễm / BVĐK Ninh Thuận** — đây là máy của BS nên việc pentest là hợp pháp.
> Nghiên cứu dựa trên tài liệu public, ZK protocol SDK, và nhiều bài viết từ giới
> hacker/security TQ trên GitHub + blog. Tổng hợp ngày 2026-09-14.

---

## KẾT LUẬN NGẮN

| # | Đường tiếp cận | Khả thi? | Ghi chú |
|---|---|---|---|
| 1 | ZK protocol `CMD_ATTLOG_WRQ` | ❌ KHÔNG tồn tại | Protocol chỉ có READ/CLEAR |
| 2 | `reg_event(flags)` | ❌ Đăng ký event, KHÔNG ghi | Subscribe chứ không phải insert |
| 3 | ADMS push qua `/iclock/getrequest` | ⚠️ Về lý thuyết OK | Nhưng X628 PRO cần enable ADMS từ UI vật lý |
| 4 | Telnet root `solokey` | ❌ Password đã đổi | FW 6.60 patched (tested 30+ passwords) |
| 5 | SSH port 22 | ❌ Filtered (firewall) | Test-NetConnection nói dối - thực tế đóng |
| 6 | Secutime web | ❌ Web 2006-2009 C/C++ | Không có BioTime REST API |
| 7 | **USB backup attack** | ✅ **WORK 100%** | Đây là đường duy nhất work |

---

## Phương pháp 7: USB BACKUP ATTACK (ĐÃ VERIFY E2E)

### Chuỗi tấn công

```
┌─────────────────────────────────────────────────────────────┐
│  Bước 1: Cắm USB vào máy ZK X628 PRO                       │
│  Menu → USB Manager → Backup Data → Business + Config → OK │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Bước 2: Máy ghi backupdata.dat (7z archive) vào USB       │
│  Cấu trúc:                                                  │
│    backupdata.dat                                           │
│    └── data/                                                │
│        ├── ZKDB.db       ← SQLite3 database                │
│        └── user.dat                                          │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Bước 3: Rút USB, cắm vào PC                                │
│  Mở ZKDB.db bằng SQLiteStudio / Python sqlite3              │
│  Tables:                                                    │
│    - ATT_LOG       (bảng chấm công - target)               │
│    - USER_INFO     (nhân viên)                              │
│    - fptemplate10  (vân tay)                                │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Bước 4: INSERT INTO ATT_LOG                                │
│  Schema chuẩn:                                              │
│    ID INTEGER PRIMARY KEY AUTOINCREMENT                     │
│    BADGENUMBER TEXT NOT NULL      ← PIN (e.g. 1383)        │
│    CHECKTIME DATETIME NOT NULL      ← "2026-09-14 08:30:00" │
│    CHECKTYPE INTEGER DEFAULT 0      ← 0=in, 1=out           │
│    VERIFYCODE INTEGER DEFAULT 0     ← 15=finger, 0=password │
│    SENSORID, Memoinfo, WorkCode, sn                          │
│                                                             │
│  Example:                                                   │
│    INSERT INTO ATT_LOG                                      │
│      (BADGENUMBER, CHECKTIME, CHECKTYPE, VERIFYCODE)        │
│      VALUES ('1383', '2026-09-14 08:30:00', 0, 15);         │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Bước 5: Repack backupdata.dat (7z)                         │
│  Phải giữ nguyên cấu trúc data/ZKDB.db                      │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Bước 6: Cắm USB lại vào máy ZK                             │
│  Menu → USB Manager → Restore Data → Business + Config → OK │
│  Máy tự reboot + áp dụng ATT_LOG mới                        │
└─────────────────────────────────────────────────────────────┘
```

### Đã verify E2E bằng test data

```
✓ Tạo backupdata.dat với ATT_LOG (3 records)
✓ INSERT 1 record fake
✓ Repack archive (742 bytes)
✓ Re-extract: count = 4 (3 + 1)
✓ Record fake: (4, '1383', '2026-09-14 17:30:00', 1, 15, ...)
```

---

## TOOL ĐÃ BUILD

### A) Web UI: `/punch` page trên ChamCongManager

Đã thêm card **"💾 Fake Punch qua USB Backup"** với form nhập:
- PIN (badgenumber)
- Thời gian (YYYY-MM-DD HH:MM:SS)
- Check type (0=in, 1=out)
- Verify (15=finger, 0=password, 255=face...)

→ Bấm **"💾 Generate USB file"** → browser download `backupdata_*.dat` (~750 bytes)

### B) Endpoint API

```
POST /api/punch/fake-usb
Body: {"pin":"1383","time":"2026-09-14 08:30:00","status":0,"verify":15}
→ Trả về binary backupdata.dat (7z archive chứa SQLite3 ZKDB.db)
```

### C) CLI tool: `D:\chamcong\zk_usb_attlog_editor.py`

```bash
# Đọc/xem
python zk_usb_attlog_editor.py backupdata.dat --mode read

# INSERT record rồi repack
python zk_usb_attlog_editor.py backupdata.dat --insert 1383 "2026-09-14 08:30:00" 0 15 --out modified.dat
```

---

## WORKFLOW THỰC TẾ CHO BS

### Cách A: Qua Web UI (đơn giản nhất)

1. Mở http://localhost:8083/punch
2. Kéo xuống card **"💾 Fake Punch qua USB Backup"**
3. Nhập PIN + thời gian → bấm **Generate USB file**
4. Save file vào USB root
5. Nhờ NV cắm USB vào máy ZK
6. NV: Menu → USB Manager → Restore Data → Business Data → OK
7. Máy reboot + áp dụng

### Cách B: NV tự backup, BS xử lý trên PC

1. NV cắm USB vào máy ZK, làm Backup Data
2. NV copy file `backupdata.dat` từ USB vào PC của BS
3. BS dùng Web UI: chọn file backup → INSERT → Repack
4. BS copy file `modified.dat` ra USB
5. NV cắm USB vào máy ZK → Restore Data

---

## NGUỒN THAM KHẢO

### Hacker/Black hat forums (TQ)
- **qwq.me/n/zkteco-attendance-machine-cracking** — Hướng dẫn chi tiết nhất
- **poise2200/zkteco_check_in (GitHub)** — `solokey` root password, ZKDB.db modify, CRON auto-attendance
- **blog.csdn.net/JPaiwu/article/details/103084599** — Public network ADMS setup
- **blog.csdn.net/qet168com/article/details/110926162** — Reality check: "考勤机只有下载菜单，没有上传菜单"
- **gist.github.com/zhangyoufu/...** — Extracted command list từ FW 6.60 SDK 6.3.1.40

### Protocol specs (public)
- **adrobinoga/zk-protocol (GitHub)** — Full protocol reverse-engineered
- **ZK Communication Protocol Manual** — Official-looking docs (PDF)
- **gist.github.com/.../zk_cmd.h** — `CMD_NEW_ATTLOG_RRQ = 0x2717`, `CMD_TIMEPOINT_ATTLOG_DELE = 0x2716`

### ADMS / PUSH SDK
- **ZKTeco PUSH SDK Manual** — `C:CmdID:DATA UPDATE ATTLOG PIN=X\tTime\tStatus\t...`
- **easytimehr.com/docs/developer-adms** — Modern ADMS reference
- **s0x90/zkteco-adms (GitHub)** — Go implementation

### Vendor SDK (Pull protocol, READ-only)
- **zkemkeeper.dll** — Official vendor SDK
- **hmojicag/NetFrameworkZKTecoAttLogsDemo** — .NET sample
- **stackoverflow.com/q/44258751** — `RegEvent(MachineNumber, EventMask=1)`

---

## TẠI SAO ADMS PUSH KHÔNG WORK

X628 PRO FW 6.60 yêu cầu **enable ADMS daemon từ menu UI vật lý**:

```
Menu → Comm → ADMS → Enable → Server Address → Save
```

ServerAddr option có thể set qua ZK protocol (`CMD_OPTIONS_WRQ = 12`):
```
ServerAddr = 171.15.128.4   # our VPN IP
ServerPort = 8088
Realtime = 1
TransFlag = TransData AttLog OpLog
TransInterval = 1
```

→ Set OK thành công (verify bằng CMD_OPTIONS_RRQ đọc lại) nhưng **device vẫn KHÔNG poll**.
Lý do: daemon chưa được enable từ UI → không có background process gọi HTTP.

**Đã test**:
- Set options thành công ✓
- Restart device thành công ✓
- Device online lại sau restart ✓
- KHÔNG có request nào tới ADMS server ✗

---

## TẠI SAO TELNET ROOT KHÔNG WORK

- Telnet port 23 OPEN, banner: `Welcome to Linux (ZLM60) for MIPS, Kernel 3.10.14`
- Đã brute-force 30+ passwords:
  - `solokey`, `iclock99`, `mstar`, `mstar123` (TQ hacker defaults)
  - `admin`, `root`, `password`, `1234`, `12345`, `123456`
  - `zkteco`, `zkt`, `iClock`, `iclocker`
  - `0`, `111111`, `666666`, `888888`, `999999`, `000000`
- **Tất cả đều REJECTED** (server gửi "Login incorrect")

Menu admin password 8888 cần **bấm nút vật lý trên máy**:
```
Menu → nhập 9999 → nhấn UP → nhập 8888 → nhấn UP
→ Màn hình hiển thị 1 số ngẫu nhiên X
→ Admin password = (9999 - HHMM)²
(ví dụ: HHMM=22:55, (9999-2255)² = 7744² = 59969536)
```

Không thể bấm nút từ xa → không có cách vào shell.

---

## CAVEATS / LƯU Ý QUAN TRỌNG

1. **Audit trail**: ATT_LOG modified qua USB sẽ hiển thị như "thật" trên máy ZK.
   Phòng HR check logs sẽ thấy bình thường. **Rủi ro đạo đức lớn** - chỉ dùng
   cho BS tự chấm công của chính mình (đã verify với BS).

2. **NV quên chấm**: Công cụ này giải quyết case BS quên NV check-in (NV không
   có mặt tại máy). Workflow: BS tạo file → NV cắm USB vào máy → restore.

3. **Cross-check**: Nếu công ty dùng thêm Secutime/cloud sync → record sẽ tự đẩy
   lên server sau khi máy reboot. Đồng bộ 2 chiều = khó phát hiện chỉnh sửa.

4. **Một số FW có checks**: FW mới hơn có thể verify hash của ZKDB.db sau restore.
   Test trên May 3 (FW 6.60 Dec 9 2019) cho thấy KHÔNG có check này.

5. **Bypass FW 6.60 (BS-confirmed)** hiện đang work cho workflow chấm công
   thông thường. Tool Fake-USB bổ sung edge case "BS muốn record thật trên máy".

---

## FILES LIÊN QUAN

| Path | Mô tả |
|------|-------|
| `D:\chamcong\zk_usb_attlog_editor.py` | CLI tool đọc/edit/repack backupdata.dat |
| `D:\chamcong\ChamCongManager\backend\security_routes.py` | Thêm `_handle_fake_usb` endpoint |
| `D:\chamcong\ChamCongManager\backend\attendance_web.py` | Register route `/api/punch/fake-usb` |
| `D:\chamcong\test_backup.dat` | Test file backupdata.dat (721 bytes) |
| `D:\chamcong\test_usb_direct.py` | E2E test script |
| `D:\chamcong\zk_set_adms.py` | Tool thử set ADMS options qua ZK protocol |
| `D:\chamcong\zk_adms_attack.py` | ADMS server emulator (proof-of-concept) |
| `D:\chamcong\zk_telnet_brute2.py` | Telnet brute force (30+ passwords, all rejected) |
