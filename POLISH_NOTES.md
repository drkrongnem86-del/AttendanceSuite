# 📋 Polish Notes - Lịch sử các bản polish

**Cập nhật**: 2026-09-11  
**Phiên bản tool**: v1.4.0 (build 7)

---

## Tổng quan

Bản v1.4.0 tập trung vào **bảo mật + vận hành ổn định + workflow MERGE thực tế**:
- Tách config ra file `config.json` (không sửa code mỗi lần đổi)
- Thêm **rate limit** (chống spam) + **audit log** (truy vết)
- Thêm **CORS** (cho mobile app qua Cloudflare Tunnel)
- Thêm **CSV rotation** (tránh file phình to)
- **Auto-restart** qua NSSM (Windows Service)
- Mobile app: **Settings UI** mới (đổi user/pass, devices, HTTPS)
- **Redesign UI light theme** (sáng sủa, gọn gàng, dễ xem log)
- **MERGE workflow hoàn chỉnh** (trang `/merge` + 3 endpoint mới)
- **AttendanceSuite.exe** launcher (1.9 MB + bundled deps)
- **Flutter web build** (mobile app chạy trên browser, không cần APK)

---

## v1.4.0 (build 7) - Security + UI + MERGE + EXE

### Tính năng mới (đã làm trong session này)

#### 1. Redesign UI light theme
- **Bảng màu sáng**: trắng/xám nhạt thay vì dark theme cũ
- **CSS variables** (primary, success, danger, etc.) - dễ customize
- **Topbar sticky** với logo + subtitle + connection badge
- **Buttons với icons** (⬇ Lấy log, ⏹ Dừng, 📊 Báo cáo...)
- **Pill badges** cho live status (online/offline/pending)
- **Color-coded rows**: matched (xanh) / missing (đỏ) cho MERGE
- **Print-friendly** (CSS @media print)

#### 2. MERGE workflow hoàn chỉnh (`/merge` page)
- **Trang riêng** `http://localhost:8080/merge` - full-page UI
- **4 endpoint mới**:
  - `GET /api/merge/today?date=YYYY-MM-DD` - trả về shadow + matched + missing + stats
  - `GET /api/merge` - tổng quan toàn bộ shadow log
  - `POST /api/merge/mark-done` - đánh dấu punch đã merge (chuyển pending → synced)
  - `POST /api/merge/clear-old` - xóa pending cũ > N ngày
- **KPI cards**: Shadow/Matched/Missing/Merge rate
- **Phân bố theo máy** (by_device, by_hour, by_status)
- **Workflow hàng ngày** in-page: 5 bước từ chấm từ xa → merge tay

#### 3. AttendanceSuite.exe launcher (PyInstaller)
- **1.9 MB EXE** + 15 MB `_internal/` (bundled Python + pyzk)
- Tự động start 3 services + mở browser
- Tìm Python từ: portable, system PATH, hoặc dùng AttendanceSuite_Portable
- Logs tại `logs/`
- Stop bằng Ctrl+C hoặc đóng cửa sổ

#### 4. Flutter web build (bonus)
- Folder `attendance_mobile/build/web/` (~40 MB) - chạy mobile app trên browser
- Không cần cài Android SDK
- Mở `web_mobile/index.html` trong browser hoặc serve qua HTTP

#### 5. Discovery về firmware ZK (đã verify)
- Test **22 máy**, 3 model (X628 PRO, 4000TID-C, RJ800), 5 firmware versions (2015→2022)
- **0/22 máy** cho phép ghi ATTLOG từ xa
- `set_user` WORK (ghi USER table) - nhưng không giúp được ATTLOG
- **Workflow MERGE là giải pháp thực tế duy nhất** (tránh mua phần mềm mới)

---

## v1.4.0 (build 7) - Security & Stability hardening

### File mới

| File | Mục đích |
|---|---|
| `config.json` | Toàn bộ cấu hình runtime (auth, sync, rate limit, audit, devices) |
| `install_services.bat` | Cài 3 service (Viewer/Sim/Remote) qua NSSM với auto-restart |
| `uninstall_services.bat` | Gỡ 3 service |
| `test_v140.py` | Test 12 cases cho features mới |
| `attendance_mobile/lib/settings_screen.dart` | UI Settings (auth, devices, HTTPS) |

### File sửa

| File | Thay đổi |
|---|---|
| `remote_punch_service.py` | Config loader, rate limit, audit log, CORS, CSV rotation, 3 endpoint mới (/api/audit, /api/config, OPTIONS), audit cho tất cả auth failures |
| `attendance_mobile/lib/settings.dart` | Thêm auth user/pass, device list, HTTPS flag |
| `attendance_mobile/lib/api.dart` | `remotePunch()` dùng credentials từ Settings (không hardcode) |
| `attendance_mobile/lib/remote_punch_screen.dart` | Device list load từ Settings (không hardcode) |
| `attendance_mobile/lib/main.dart` | Thêm tab thứ 4 "Cài đặt", load HTTPS từ Settings |
| `attendance_mobile/pubspec.yaml` | Version 1.3.2+6 → 1.4.0+7 |

### Cấu hình mới (`config.json`)

```json
{
  "auth": { "enabled": true, "user": "admin", "pass": "bvdk2026" },
  "secutime": { "host": "172.16.0.31", "port": 8098, "user": "admin", "pass": "admin@123" },
  "adms": { "host": "172.16.200.105", "port": 8080 },
  "sync": { "interval_seconds": 30, "channels": {"secutime": true, "adms": true, "direct_zk": true} },
  "rate_limit": { "max_requests": 10, "window_seconds": 60, "enabled": true },
  "csv_rotation": { "max_size_mb": 10, "keep_files": 30, "enabled": true },
  "audit": { "enabled": true, "log_file": "audit.log", "max_size_mb": 5 },
  "server": { "port": 8082, "bind": "0.0.0.0" },
  "device_ips": ["172.16.0.212", "172.16.0.214", "172.16.0.30", "172.16.0.31"]
}
```

> **Sau khi deploy, BS NHỚ đổi `auth.pass` thành password mạnh hơn trước khi expose internet!**

### Tính năng mới

#### 1. Rate limit (chống spam)
- Default: **10 requests / 60s per IP** (config được trong `config.json`)
- Áp dụng cho: `GET /api/*`, `POST /punch`, `POST /api/remote-punch`
- KHÔNG áp dụng cho: `/healthz`, `/logout` (để monitoring tools và logout 1 lần)
- Response khi vượt: HTTP 429 + `Retry-After` header + JSON `{error, retry_after}`

#### 2. Audit log (truy vết)
- Mỗi request quan trọng (auth fail, rate limit, punch, config read) đều ghi vào `audit.log`
- Format: `timestamp | ip=X | user=Y | action=Z | details=W | result=ok|denied`
- Auto-rotate khi file > 5MB
- Xem online: `GET /api/audit?tail=50` (cần auth)

#### 3. CORS (cho mobile app + browser)
- Tất cả response có headers: `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers`
- Preflight `OPTIONS` trả về 204 ngay
- Cho phép mobile app gọi từ domain khác (vd: qua Cloudflare Tunnel)

#### 4. CSV rotation
- Khi `pending_punches.csv` / `synced_punches.csv` / `failed_punches.csv` vượt `max_size_mb` (default 10MB)
- Tự động rename: `pending_punches.csv.20260911_143022`
- Giữ tối đa `keep_files` archives (default 30)
- Apply cho `pending_punches.csv` qua `append_csv()`

#### 5. Auto-restart qua NSSM
- File `install_services.bat` cài 3 service Windows với auto-restart on crash
- Yêu cầu: NSSM (tải từ https://nssm.cc, giải nén `nssm.exe` vào PATH)
- App restart delay: 5s sau khi crash
- Logs: `logs/Attendance*.out.log` + `.err.log`, tự rotate 10MB

#### 6. Mobile app - Settings UI
- Tab mới "Cài đặt" trong BottomNavigationBar
- Đổi được: Server IP, Username, Password, Device IPs, HTTPS toggle
- Lưu vào SharedPreferences → tự áp dụng khi restart app
- Reset về mặc định (xóa tất cả settings)

### Endpoints mới

| Endpoint | Method | Auth | Mục đích |
|---|---|---|---|
| `/healthz` | GET | ❌ | Health check (đã có version 1.4.0) |
| `/api/stats` | GET | ✅ | Đã có, thêm field `channels_active` |
| `/api/audit?tail=N` | GET | ✅ | Xem audit log (mới) |
| `/api/config` | GET | ✅ | Xem config (passwords masked) (mới) |
| `OPTIONS /*` | - | ❌ | CORS preflight → 204 (mới) |

### Test coverage (12/12 PASS)

Đã test (12/12 PASS):
- ✅ `t1: /healthz` returns version 1.4.0
- ✅ `t2: /api/stats` includes `channels_active`
- ✅ `t3: /api/config` masks passwords
- ✅ `t4: /api/config` no auth → 401 (response body OK)
- ✅ `t5: OPTIONS` preflight → 204 + CORS headers
- ✅ `t6: GET` responses include CORS headers
- ✅ `t7: /api/audit` no auth → 401 (response body OK)
- ✅ `t8: /api/audit` returns entries (auth failures + successes)
- ✅ `t9: rate limit` triggers after N requests (X-Forwarded-For isolation)
- ✅ `t10: POST /punch` bad device_ip → 400
- ✅ `t11: POST /punch` happy path → 200
- ✅ `t12: audit` records auth_failed

Run: `python test_v140.py` (cần service đang chạy ở port 8082)

---

## v1.3.2 (build 6) - Remote Punch Service (trước đó)

### Tính năng đã có (từ v1.3.2)

#### 1. Dashboard với Basic Auth + Mobile UI
- `remote_punch_service.py` (port 8082)
- Basic Auth `admin / bvdk2026`
- Quick-punch UI: 4 nút (VÀO CA / TAN CA / RA NGOÀI / VÀO LẠI)
- AJAX, validation, health check, stats JSON, logout, auto-refresh

#### 2. Mobile App - Tab "Chấm từ xa"
- `attendance_mobile/lib/remote_punch_screen.dart`
- Form nhập Mã NV (autofocus, bàn phím số) + 6 nút thao tác
- Dropdown chọn máy
- Lịch sử 20 record gần nhất

#### 3. Internet Deployment (1-click)
- `expose_internet.bat` - Cloudflare Tunnel 1-click

---

## Checklist deploy lên máy BV (v1.4.0)

1. [ ] Copy các file mới vào `D:\chamcong\`:
   - `config.json` ← MỚI
   - `install_services.bat`, `uninstall_services.bat` ← MỚI
   - `test_v140.py` ← MỚI
   - `remote_punch_service.py` ← SỬA (giữ version mới)
2. [ ] Sửa `config.json`: đổi `auth.pass` thành password mạnh
3. [ ] (Optional) Tải NSSM từ https://nssm.cc/download, giải nén `nssm.exe` (win64) vào PATH
4. [ ] Chạy `install_services.bat` (as Admin) → 3 service auto-install + auto-start
5. [ ] Verify: `services.msc` thấy 3 service "Attendance*" đang chạy
6. [ ] Chạy `python test_v140.py` → 12/12 PASS
7. [ ] Mở browser `http://localhost:8082/` → đăng nhập → thấy dashboard
8. [ ] Cài APK mới lên điện thoại → vào tab "Cài đặt" → nhập password mới + tick HTTPS nếu dùng tunnel
9. [ ] Test thử chấm công từ mobile

---

## Còn lại (chưa làm, có thể làm tiếp)

- [ ] HTTPS natively (cần self-signed cert hoặc Let's Encrypt)
- [ ] LDAP/SSO cho auth
- [ ] Multi-user (track ai đăng nhập, gán quyền)
- [ ] Prometheus metrics `/metrics`
- [ ] Docker compose
