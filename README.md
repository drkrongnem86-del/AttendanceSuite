# AttendanceSuite - BVĐK Ninh Thuận

> Hệ thống chấm công tự động cho Bệnh viện Đa khoa Ninh Thuận
> Mobile (Flutter Android/iOS) + Backend Python (Windows EXE) + ZK device integration

## 📦 Latest Release

| Component | Version | Size | Cert SHA-1 |
|-----------|---------|------|------------|
| **APK** (arm64) | v2.7.4+47 | 29.34 MB | `5d54b3cf...F6C5` |
| **EXE** (Backend) | v2.6.11 | 8.79 MB | N/A |
| **AAB** (Play Store) | v2.7.4+47 | ~29 MB | `5d54b3cf...F6C5` |

[Xem tất cả releases →](https://github.com/drkrongnem86-del/AttendanceSuite/releases)

## 🏗️ Project Structure

```
AttendanceSuite/
├── attendance_mobile/        # Flutter Android/iOS app
│   ├── lib/
│   │   ├── api/pc_api.dart          # HTTP client (37+ endpoints)
│   │   ├── screens/                 # 7 tabs (Log, Live, LAN, Tools, API, Mạng, Cài đặt)
│   │   ├── data/                    # VPN + credentials
│   │   └── main.dart
│   ├── android/                     # Android config (keystore ở đây)
│   ├── ios/
│   ├── assets/vpn/                  # Sophos VPN config
│   └── pubspec.yaml                 # version: 2.7.4+47
│
├── attendance_backend/        # Python backend (PyInstaller → EXE)
│   ├── attendance_web.py            # Main HTTP server (BaseHTTPRequestHandler)
│   ├── inject_routes.py             # CVE-2023-3941 ATTLOG injection
│   ├── security_routes.py           # Security scan + PIN verify
│   ├── templates/                   # HTML pages (10 routes)
│   ├── zk/                          # pyzk library files (bundled)
│   ├── devices.csv                  # 27 attendance devices config
│   ├── config.json
│   ├── requirements.txt             # Python deps (pyzk, pyinstaller)
│   └── build.spec                   # PyInstaller spec
│
├── attendance_installer/      # Silent installer cho Windows PC
│   ├── install.bat                  # Cài Windows Service
│   ├── test_run.bat                 # Test EXE local
│   ├── update_backend.bat           # Update code without reinstall
│   ├── stop_test.bat
│   └── uninstall.bat
│
├── releases/                  # Latest binaries (push cho fresh install)
│   ├── attendance-mobile-arm64-v2.7.4+47.apk
│   └── AttendanceSuite-v2.6.11.exe
│
├── docs/                      # Documentation
│   ├── screenshots/
│   └── *.md
│
├── .github/
│   └── workflows/
│       └── build.yml          # 4-job CI/CD: APK + AAB + IPA + EXE
│
├── version.json               # Auto-updated bởi GitHub Actions
├── README.md                  # This file
└── .gitignore
```

## 🚀 Features

### Mobile App (Flutter)
- **Đọc log chấm công** từ 27 máy X628 PRO qua Sophos VPN
- **Live Status** (ping/latency 30 thiết bị, auto-probe)
- **LAN scan** trực tiếp khi cùng WiFi BV (port 4370)
- **ATTLOG Tools + ZK Tools**:
  - ZK Info (FW/Serial/User count)
  - ZK ATTLOG (real device data qua pyzk port 4370)
  - Test PIN (check user exists)
  - Reboot device (30s downtime)
- **Inject ATTLOG** qua CVE-2023-3941 + Jobs monitor + History
- **Quick Actions**: Security Scan, Merge, Alerts, Backup, Reports
- **Tab API**: index 37 endpoints với Test JSON + Copy curl + Open in Browser
- **VPN Sophos BV Ninh Thuận** (native openvpn_flutter)
- **Manual ATTLOG entry** (không cần máy thật)
- **Auto-detect backend** với quick switch 3 URLs (banner)
- **Configurable Server URL** (default CCDK-M6 BV)

### Backend (Python + PyInstaller)
- **HTTP server** thuần stdlib (BaseHTTPRequestHandler)
- **37 endpoints**:
  - HTML Pages (10): /, /launcher.html, /attlog-tools, /inject, /security, /punch, /merge, /alerts, /api/live/page, /all-links
  - GET APIs (17): /api/diag, /api/status, /api/devices, /api/records, /api/live, /api/zk/info, /api/zk/attlog, /api/inject/jobs, /api/merge, /api/alerts/missing, ...
  - POST APIs (10): /api/fetch, /api/remote-punch, /api/punch/manual, /api/inject/attlog, /api/zk/reboot, /api/backup/now, ...
- **ZK device integration** qua pyzk (port 4370)
- **ATTLOG injection** qua CVE-2023-3941 (UPLOAD_PICTURE path traversal)
- **Auto-installer** Windows Service (NSSM, auto-start, hidden)
- **PyInstaller onefile EXE** (~9 MB, no Python required)

## 🔨 Build Workflow (.github/workflows/build.yml)

Trigger: `git tag v*.*.*` hoặc manual `workflow_dispatch`

### 4 Jobs song song:
| Job | Runner | Output | Time |
|-----|--------|--------|------|
| `build-apk` | windows-latest | `app-release.apk` (arm64) | ~3-7 min |
| `build-aab` | windows-latest | `app-release.aab` (universal) | ~3-7 min |
| `build-ipa` | macos-latest | `Runner.ipa` (optional, thiếu Apple certs thì skip) | ~5-10 min |
| `build-exe` | windows-latest | `AttendanceSuite-v*.exe` (PyInstaller) | ~2-5 min |

Sau đó:
- `create-release` → Tạo GitHub Release với APK + AAB + IPA + EXE đính kèm
- `update-version-json` → Auto-update `version.json` cho in-app updater

### Setup GitHub Secrets (optional - để APK sign đúng cert):
```
ANDROID_KEYSTORE_BASE64    # paste từ release.keystore (base64)
ANDROID_KEYSTORE_PASSWORD  # bvdk@2026
ANDROID_KEY_PASSWORD       # bvdk@2026
ANDROID_KEY_ALIAS           # te-c0a93129-73ca-4337-bc61-75be6178951b
```

Encode keystore:
```bash
certutil -encode attendance_mobile/android/app/release.keystore release.keystore.b64
# Copy nội dung file .b64 vào Secret
```

Nếu KHÔNG add secrets → APK build bằng debug keystore → user phải **GỠ APP CŨ** trước khi cài.

## 📱 Install APK

### Quick install (cùng cert SHA-1):
```bash
adb install -r attendance-mobile-arm64-v2.7.4+47.apk
```
Không cần gỡ app cũ - cài đè tự động.

### First install:
1. Download APK từ [Releases](https://github.com/drkrongnem86-del/AttendanceSuite/releases)
2. Mở file trên điện thoại Android
3. Cho phép "Install from unknown sources"
4. Bấm Install

## 🖥️ Install Backend EXE

### Quick test (không cài service):
```cmd
cd C:\AttendanceSuite
AttendanceSuite-v2.6.11.exe
```
Mở browser: http://localhost:8080/

### Silent install (Windows Service):
1. Copy `AttendanceSuite-v2.6.11.exe` vào PC BV
2. Right-click → "Run as administrator"
3. Backend sẽ:
   - Kill processes giữ port 8080
   - Cài Windows Service "AttendanceSuiteBV"
   - Auto-start, hidden, restart on fail
   - Mở firewall ports 8080/8081/8082

## 🔧 Local Dev

### Backend:
```bash
cd attendance_backend
pip install -r requirements.txt
python attendance_web.py
# Mở http://localhost:8080/
```

### Mobile:
```bash
cd attendance_mobile
flutter pub get
flutter run                                  # debug
flutter build apk --release --target-platform=android-arm64
```

## 📚 Tech Stack

- **Mobile**: Flutter 3.41+ / Dart 3.5+ / Material 3
- **Backend**: Python 3.11+ (stdlib HTTP) + pyzk 0.9
- **Packaging**: PyInstaller 6.3 (onefile EXE, ~9 MB)
- **Service**: NSSM (Windows Service wrapper)
- **VPN**: openvpn_flutter (Sophos BV)
- **CI/CD**: GitHub Actions (Windows + macOS runners)
- **Signing**: Release keystore (cert SHA-1 `5d54b3cf...F6C5`)

## 📋 Version History

| Version | Date | Highlights |
|---------|------|------------|
| v2.7.4+47 | 2026-09-24 | Auto-detect backend + quick switch URL |
| v2.7.3+46 | 2026-09-24 | Open in Browser cho endpoints |
| v2.7.2+45 | 2026-09-24 | Full v2.6.11 backend integration + EndpointsScreen |
| v2.7.1+44 | 2026-09-24 | Log auto-switch filter + 3 new filters |
| v2.7.0+43 | 2026-09-23 | 180s timeout cho ZK commands qua VPN |
| v2.6.9+42 | 2026-09-23 | All tabs fixed, Web IP removed |
| v2.6.8+41 | 2026-09-23 | Default CCDK-M6 + configurable Server URL |
| v2.6.7+40 | 2026-09-22 | LAN Scan improvements |
| v2.6.6+39 | 2026-09-22 | Live Device Status |
| v2.6.5+38 | 2026-09-22 | Backend integration |
| v2.6.4+37 | 2026-09-19 | Fix Python "not ready" - add /health |
| v2.6.3+36 | 2026-09-19 | Live Device Status tab + About dialog |
| v2.6.2+35 | 2026-09-19 | Log bulk select + Theme chooser |
| v2.6.1+34 | 2026-09-19 | Native Flutter UI + VPN Sophos BV |

## ⚠️ Security Notice

Module ATTLOG Tools khai thác **CVE-2023-3941** (UPLOAD_PICTURE path traversal) và **CVE-2023-4587** (unauth backup download) trên ZK X628 PRO FW 6.60.

**Chỉ sử dụng trên thiết bị thuộc sở hữu của BVĐK Ninh Thuận.**

## 📝 License

© 2026 BVĐK Ninh Thuận - Dr. Nểm (Bác sĩ Cấp Cứu)

Internal use only. Không phân phối ra ngoài bệnh viện.
