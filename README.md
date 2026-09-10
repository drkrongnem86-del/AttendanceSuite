# 🏥 AttendanceSuite v1.3.2 - BVDK Ninh Thuận

Hệ thống **quản lý log máy chấm công vân tay ZKTeco X628 PRO** cho Bệnh viện Đa khoa Ninh Thuận.

**Tác giả gốc**: BSCKI Nguyễn Chế Thúy Diễm (`nemk`) - Khoa Cấp Cứu Lưu Ký  
**Bổ sung (v1.3.x)**: Mavis (auto-generated tools)

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
- Endpoint `POST /api/remote-punch` cho chấm công từ xa (mới ở v1.3.2)

### X628 PRO Simulator (port 8081)
- UI mô phỏng máy thật: màn LCD xanh, keypad, LED
- Chọn thao tác (In/Out/Break/OT) + phương thức (FP/Card/Pwd)
- Thử ghi vào máy thật qua 6 format ZK protocol
- Honest error reporting ("may ACK_OK nhưng KHÔNG ghi")

### Remote Punch Service (port 8082) - **MỚI v1.3.2**
- Web dashboard mobile-friendly
- **Basic Auth** (`admin / bvdk2026`)
- Tự động sync pending punches qua 3 kênh:
  1. **Secutime API** (`applySign`) - ưu tiên 1
  2. **ADMS queue** - ưu tiên 2
  3. **Direct ZK write** - fallback cuối
- Health check `/healthz` cho monitoring
- Auto-refresh stats mỗi 5s

### Cloudflare Tunnel (1-click)
- File `expose_internet.bat` - tự động tạo HTTPS public URL
- Dùng từ bất kỳ đâu không cần VPN
- **Có sẵn Basic Auth** → an toàn

### Flutter Mobile App (v1.3.2)
- Tab 1: 📊 Đọc log
- Tab 2: 🖐 Simulator
- Tab 3: ☁️ **Chấm từ xa** (mới)
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

```powershell
cd attendance_mobile
flutter pub get
flutter build apk --release
```

APK ở: `attendance_mobile/build/app/outputs/flutter-apk/app-release.apk`

Lưu ý: Cần JDK 17+ + Android SDK. Nếu build fail vì network chậm, thêm Aliyun mirror vào `android/settings.gradle` + `android/build.gradle`.

---

## 📂 Cấu trúc

```
AttendanceSuite/
├── README.md                          # File này
├── SETUP_REMOTE_PUNCH.md              # Hướng dẫn setup remote punch
├── POLISH_NOTES.md                    # Release notes v1.3.2
├── .gitignore
│
├── attendance_web.py                  # Log viewer + reports + live status (port 8080)
├── punch_simulator.py                 # X628 PRO simulator (port 8081)
├── remote_punch_service.py            # Remote punch service (port 8082) ← MỚI
│
├── devices.csv                        # 27 thiết bị
├── manual_punches.csv                 # Shadow log của simulator
├── launcher.html                      # 3-tab web UI
│
├── start_all.bat                      # Khởi động tất cả
├── stop_all.bat                       # Tắt tất cả
├── fix_firewall.bat                   # Mở firewall port 8080/8081
├── expose_internet.bat                # Cloudflare tunnel 1-click ← MỚI
├── setup_python.bat                   # Setup Python embed + pyzk
│
├── secutime_exploit.py                # Tool thử exploit Secutime API ← MỚI
├── adms_mini.py                       # Mini ADMS server (bắt command ZK) ← MỚI
├── zk_recon.py                        # Scan thiết bị toàn diện ← MỚI
│
├── test_dashboard.py                  # Test 8 cases (auth, AJAX, validation)
├── test_integration.py                # Test 6 cases (2 service integration)
│
├── build_exe.cs                       # C# build script
├── build.rsp                          # C# compiler flags
│
└── attendance_mobile/                 # Flutter Android app
    ├── lib/
    │   ├── main.dart                  # App shell + BottomNavigationBar
    │   ├── api.dart                   # HTTP client
    │   ├── settings.dart              # SharedPreferences
    │   ├── viewer_screen.dart         # Tab 1: Log viewer
    │   ├── simulator_screen.dart      # Tab 2: Simulator
    │   └── remote_punch_screen.dart   # Tab 3: Chấm từ xa ← MỚI
    ├── android/                      # Android config
    │   ├── app/
    │   │   └── release.keystore      # Keystore cho release APK ← MỚI
    │   └── key.properties             # ← MỚI
    └── pubspec.yaml                   # Version 1.3.2+6
```

---

## 🔧 Cấu hình

### Đổi default credentials
- File: `remote_punch_service.py` (line `AUTH_USER`, `AUTH_PASS`)
- Mặc định: `admin / bvdk2026`

### Đổi danh sách thiết bị
- File: `devices.csv` (IP, Type, Note, Selected)
- Type: `attendance` / `signing` / `server` / `gateway` / `virtual`

### Đổi sync interval
- File: `remote_punch_service.py` (line `SYNC_INTERVAL = 30`)
- Default: 30 giây

### Đổi Secutime config
- File: `remote_punch_service.py` (line `SECUTIME_HOST`, `SECUTIME_PORT`, `SECUTIME_USER`, `SECUTIME_PASS`)
- Default: `172.16.0.31:8098` với `admin/admin@123`

---

## 🔐 Bảo mật

- ✅ Basic Auth cho dashboard port 8082
- ✅ Validation input (user_id phải là số)
- ✅ HTTPS qua Cloudflare Tunnel
- ⚠️ Chưa có HTTPS native (chỉ HTTP trong LAN)
- ⚠️ Chưa có rate limit
- ⚠️ **NHỚ ĐỔI PASSWORD** trước khi expose internet lâu dài

---

## 📜 Lịch sử phiên bản

- **v1.0.0** (build 1) - Phiên bản đầu: Log viewer cơ bản
- **v1.1.0** (build 2) - Virtual Device + Simulator
- **v1.2.0** (build 3) - Báo cáo ngày, Excel export, Hôm nay view
- **v1.3.0** (build 4) - Live Status panel
- **v1.3.1** (build 5) - Polish Mobile app
- **v1.3.2** (build 6) - **Remote Punch Service + Mobile tab mới** ← Hiện tại

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
