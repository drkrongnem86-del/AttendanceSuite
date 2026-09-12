# 🏥 AttendanceSuite v1.4.0 - BVDK Ninh Thuận

Hệ thống **quản lý log máy chấm công vân tay ZKTeco X628 PRO** cho Bệnh viện Đa khoa Ninh Thuận.

**Tác giả gốc**: BSCKI Nguyễn Chế Thúy Diễm (`nemk`) - Khoa Cấp Cứu Lưu Ký  
**Bổ sung (v1.3.x → v1.4.0)**: Mavis (auto-generated tools)

---

## 📋 Tính năng

### Web Dashboard (port 8080)
- Đọc log từ **27 máy chấm công** qua ZK protocol
- Phân biệt **CC** (chấm công) vs **KY** (ký vân tay) vs **SV** (server) vs **GW** (gateway)
- Báo cáo ngày (pair In/Out, tính giờ làm)
- Báo cáo hôm nay (ai đang làm / đã về)
- Export Excel `.xls` (SpreadsheetML 2003)
- **Live Status** (probe 27 thiết bị mỗi 8 giây)
- **Diagnostic** cho mobile (xem IP server từ xa)
- Endpoint `POST /api/remote-punch` cho chấm công từ xa

### X628 PRO Simulator (port 8081)
- UI mô phỏng máy thật: màn LCD xanh, keypad, LED
- Chọn thao tác (In/Out/Break/OT) + phương thức (FP/Card/Pwd)
- Thử ghi vào máy thật qua 6 format ZK protocol
- Honest error reporting ("may ACK_OK nhưng KHÔNG ghi")

### Remote Punch Service (port 8082) - v1.4.0 hardening
- Web dashboard mobile-friendly
- **Basic Auth** (`admin / bvdk2026`) - password config trong `config.json`
- Tự động sync pending punches qua 3 kênh:
  1. **Secutime API** (`applySign`) - ưu tiên 1
  2. **ADMS queue** - ưu tiên 2
  3. **Direct ZK write** - fallback cuối
- Health check `/healthz` cho monitoring
- Auto-refresh stats mỗi 5s

#### 🆕 v1.4.0 features mới
- **`config.json`** - toàn bộ cấu hình (auth, sync, rate limit, devices)
- **Rate limit** 10 req/60s per IP (chống spam) → HTTP 429
- **Audit log** `audit.log` (truy vết) + endpoint `/api/audit?tail=N`
- **CORS** headers (cho mobile qua Cloudflare Tunnel) + OPTIONS preflight
- **CSV rotation** (10MB → rename, giữ 30 file gần nhất)
- **Auto-restart** qua NSSM (`install_services.bat` as Admin)
- Endpoint `/api/config` xem config (passwords masked)

### Cloudflare Tunnel (1-click)
- File `expose_internet.bat` - tự động tạo HTTPS public URL
- Dùng từ bất kỳ đâu không cần VPN
- **Có sẵn Basic Auth** → an toàn

### Flutter Mobile App (v1.4.0+7)
- Tab 1: 📊 Đọc log
- Tab 2: 🖐 Simulator
- Tab 3: ☁️ **Chấm từ xa**
- Tab 4: ⚙️ **Cài đặt** (mới) - đổi IP, user/pass, devices, HTTPS
- 6 nút thao tác màu, autofocus NV, lịch sử session

---

## 🚀 Quick start

### 1. Cài Python + pyzk (1 lần)

Nếu chưa có `AttendanceSuite_Portable/`:
```powershell
setup_python.bat
```

Nếu đã có sẵn `AttendanceSuite_Portable/` (Python 3.12 embed + pyzk bundle), bỏ qua bước này.

### 2. Start tất cả service

```powershell
start_all.bat
```

Sẽ mở:
- **http://localhost:8080** - Log Viewer
- **http://localhost:8081** - Simulator  
- **http://localhost:8082** - Remote Punch Dashboard (login: `admin` / `bvdk2026`)

### 3. Expose Internet (optional)

```powershell
expose_internet.bat
```

Sẽ in URL `https://xxx.trycloudflare.com` - mở từ bất kỳ đâu.

### 4. Build APK Android

**Cách 1 — GitHub Actions (khuyến nghị, nhanh)**:

Push code lên GitHub → workflow `.github/workflows/build-apk.yml` tự động build APK arm64.

- Push lên `main` → APK ở tab **Actions** → **build-apk** → artifact `attendance-mobile-arm64-X.Y.Z+N`
- Push tag `v1.3.3` → tự động tạo GitHub Release với APK đính kèm

**Cách 2 — Local** (cần JDK 17 + Android SDK):

```powershell
cd attendance_mobile
flutter pub get
flutter build apk --release --target-platform=android-arm64 --split-per-abi
```

APK ở: `attendance_mobile/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk`

Lưu ý: Build local thường fail ở `kotlin-compiler-embeddable-1.8.22.jar` (96MB) do mạng đến `repo.maven.apache.org` chậm. Workflow GitHub dùng Aliyun mirror nên build nhanh & ổn định.

---

## 🤖 GitHub Actions

Workflow `.github/workflows/build-apk.yml` tự động build APK arm64.

**Trigger**:
- Push lên `main` → build + upload artifact
- Push tag `v*` (vd `v1.3.3`) → build + tạo GitHub Release
- Manual: tab Actions → Run workflow

**Cần setup 2 GitHub Secrets** (1 lần):
- Vào `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
- `ANDROID_KEYSTORE_B64`: base64 của `android/app/release.keystore`
- `ANDROID_KEY_PROPS_B64`: base64 của `android/key.properties`

Generate secrets trên máy local:
```powershell
$ks = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes("attendance_mobile\android\app\release.keystore"))
$kprops = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content "attendance_mobile\android\key.properties" -Raw)))
Write-Host "KEYSTORE_B64=$ks"
Write-Host "KEY_PROPS_B64=$kprops"
```

Nếu chưa setup secrets → workflow vẫn chạy nhưng APK sẽ được sign bằng debug keystore (không cài đè được lên release-signed cũ). Workflow in `::warning::` thay vì fail.

**Lint workflow** (`.github/workflows/lint.yml`): chạy Python compile-check + Flutter analyze mỗi PR. Nhanh (~3 min) để gate merge.

---

## 📂 Cấu trúc (v1.4.0)

```
AttendanceSuite/
├── README.md                          # File này
├── SETUP_REMOTE_PUNCH.md              # Hướng dẫn setup remote punch
├── POLISH_NOTES.md                    # Release notes v1.4.0
├── .gitignore
│
├── attendance_web.py                  # Log viewer + reports + live status (port 8080)
├── punch_simulator.py                 # X628 PRO simulator (port 8081)
├── remote_punch_service.py            # Remote punch service (port 8082) + security hardening
│
├── config.json                        # Toàn bộ cấu hình runtime ← MỚI v1.4.0
├── devices.csv                        # 27 thiết bị
├── manual_punches.csv                 # Shadow log của simulator
├── launcher.html                      # 3-tab web UI
│
├── start_all.bat                      # Khởi động tất cả
├── stop_all.bat                       # Tắt tất cả
├── fix_firewall.bat                   # Mở firewall port 8080/8081
├── expose_internet.bat                # Cloudflare tunnel 1-click
├── setup_python.bat                   # Setup Python embed + pyzk
├── install_services.bat               # NSSM auto-install 3 service ← MỚI v1.4.0
├── uninstall_services.bat             # NSSM uninstall 3 service ← MỚI v1.4.0
│
├── secutime_exploit.py                # Tool thử exploit Secutime API
├── adms_mini.py                       # Mini ADMS server (bắt command ZK)
├── zk_recon.py                        # Scan thiết bị toàn diện
│
├── test_dashboard.py                  # Test 8 cases (auth, AJAX, validation)
├── test_integration.py                # Test 6 cases (2 service integration)
├── test_v140.py                       # Test 12 cases (config, rate limit, audit, CORS) ← MỚI v1.4.0
│
├── build_exe.cs                       # C# build script
├── build.rsp                          # C# compiler flags
│
└── attendance_mobile/                 # Flutter Android app
    ├── lib/
    │   ├── main.dart                  # App shell + 4 tabs
    │   ├── api.dart                   # HTTP client (Basic Auth từ Settings)
    │   ├── settings.dart              # SharedPreferences (IP, auth, devices, HTTPS)
    │   ├── viewer_screen.dart         # Tab 1: Log viewer
    │   ├── simulator_screen.dart      # Tab 2: Simulator
    │   ├── remote_punch_screen.dart   # Tab 3: Chấm từ xa
    │   └── settings_screen.dart       # Tab 4: Cài đặt (auth, devices, HTTPS) ← MỚI v1.4.0
    ├── android/                      # Android config
    │   ├── app/
    │   │   └── release.keystore      # Keystore cho release APK
    │   └── key.properties
    └── pubspec.yaml                   # Version 1.4.0+7

.github/
├── workflows/
│   ├── build-apk.yml                 # Build APK arm64
│   └── lint.yml                      # Python + Flutter lint
└── scripts/
    └── init.gradle                   # Aliyun mirror cho Gradle
```

---

## 🔧 Cấu hình (v1.4.0+)

### Đổi qua `config.json` (khuyến nghị)
Tất cả cấu hình runtime nằm trong `config.json`. Sửa file này rồi restart service.

```json
{
  "auth": { "user": "admin", "pass": "..." },
  "secutime": { "host": "...", "port": 8098, "user": "...", "pass": "..." },
  "adms": { "host": "...", "port": 8080 },
  "sync": { "interval_seconds": 30, "channels": {...} },
  "rate_limit": { "max_requests": 10, "window_seconds": 60, "enabled": true },
  "csv_rotation": { "max_size_mb": 10, "keep_files": 30, "enabled": true },
  "audit": { "enabled": true, "max_size_mb": 5 },
  "device_ips": ["..."]
}
```

### Đổi danh sách thiết bị
- File: `devices.csv` (IP, Type, Note, Selected)
- Type: `attendance` / `signing` / `server` / `gateway` / `virtual`

### Mobile app settings (UI)
Trong app, vào tab "Cài đặt" → đổi IP, user/pass, devices, HTTPS. Lưu vào SharedPreferences.

### Auto-restart service
- Tải NSSM từ https://nssm.cc, giải nén `nssm.exe`
- Chạy `install_services.bat` (as Admin) → 3 service auto-install + auto-restart on crash

---

## 🔐 Bảo mật (v1.4.0)

- ✅ Basic Auth cho dashboard port 8082 (user/pass trong `config.json`)
- ✅ Validation input (user_id phải là số, device_ip whitelist regex)
- ✅ HTTPS qua Cloudflare Tunnel
- ✅ **Rate limit** 10 req/60s per IP (HTTP 429)
- ✅ **Audit log** mọi auth fail + punch + rate limit (xem qua `/api/audit`)
- ✅ **CORS** headers (cho mobile qua tunnel/domain khác)
- ✅ **CSV rotation** tự động (10MB → archive)
- ✅ **Auto-restart** qua NSSM
- ⚠️ Chưa có HTTPS native (chỉ HTTP trong LAN)
- ⚠️ **NHỚ ĐỔI `auth.pass` trong `config.json`** trước khi expose internet lâu dài

---

## 📜 Lịch sử phiên bản

- **v1.0.0** (build 1) - Phiên bản đầu: Log viewer cơ bản
- **v1.1.0** (build 2) - Virtual Device + Simulator
- **v1.2.0** (build 3) - Báo cáo ngày, Excel export, Hôm nay view
- **v1.3.0** (build 4) - Live Status panel
- **v1.3.1** (build 5) - Polish Mobile app
- **v1.3.2** (build 6) - Remote Punch Service + Mobile tab mới
- **v1.4.0** (build 7) - **Security & Stability hardening** ← Hiện tại
  - `config.json`, rate limit, audit log, CORS, CSV rotation
  - NSSM auto-restart, Mobile Settings UI

---

## 📞 Liên hệ

- **BVĐK Ninh Thuận** - Khoa Cấp Cứu Lưu Ký (HSCCL)
- **Bác sĩ**: BSCKI Nguyễn Chế Thúy Diễm (`nemk`)
- **IP local**: 172.16.200.105

---

## 🙏 Credits

- Tác giả gốc: BS Diễm (viết core, hiểu ZK protocol sâu)
- Bổ sung: Mavis (auto-generated tools, polish, integration)
- ZK Protocol: https://github.com/fananimi/pyzk
- ADMS Protocol docs: https://easytimehr.com/docs/developer-adms
- Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
