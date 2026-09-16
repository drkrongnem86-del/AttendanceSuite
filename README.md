# AttendanceSuite v2.0.1 - Portable EXE + APK arm64

## Giới thiệu

**AttendanceSuite** - Phần mềm quản lý chấm công từ xa cho các máy chấm công vân tay ZK X628 PRO FW 6.60 tại **BVĐK Ninh Thuận**.

**Tác giả:** Dr. Nểm (Bác sĩ Cấp cứu - BVĐK Ninh Thuận)
**Bản quyền:** © 2026 Dr. Nểm - BVĐK Ninh Thuận

## Tính năng

### 1. AttendanceSuite.exe (Portable EXE - 12MB)
- ✅ Double-click → cửa sổ desktop mở ngay (pywebview + Edge WebView2)
- ✅ 3 servers chạy ngầm trong 1 process (không spawn subprocess):
  - **Viewer** :8080 - Log chấm công + báo cáo
  - **Simulator** :8081 - Mô phỏng máy X628 PRO
  - **ATTLOG Tools API** :8080 - Inject/Delete/Edit ATTLOG (CVE-2023-3941)
- ✅ 4 tabs UI: Đọc log / X628 Simulator / ATTLOG Tools / Live Status
- ✅ Filter nhanh: Hôm nay / Hôm qua / Tuần này / Tháng này / Tất cả
- ✅ Chấm công thật ghi lên ATTLOG qua web backup (CVE-2023-4587) + path traversal (CVE-2023-3941)
- ✅ Xóa log theo marker (chọn lọc)
- ✅ Chỉnh sửa thời gian ATTLOG
- ✅ Tự động kill port cũ khi khởi động (tránh lỗi trùng port)
- ✅ Single-instance lock (không cho mở 2 cửa sổ)
- ✅ Force kill port khi đóng (clean shutdown)

### 2. attendance-mobile-arm64-2.0.1+14.apk (APK arm64 - 17MB)
- ✅ Flutter mobile app cho Android arm64-v8a
- ✅ 4 tabs: Log chấm công / X628 PRO / Chấm từ xa / **ATTLOG Tools**
- ✅ ATTLOG Tools gọi EXE qua HTTP để inject/delete/edit
- ✅ Signed SHA-1: `5d54b3cf8cac8f87fb841f11f6cda9a654c8f6c5`

## Hướng dẫn sử dụng nhanh

### EXE
1. Copy `AttendanceSuite-v2.0.1.exe` ra desktop
2. Double-click → cửa sổ mở ngay
3. Click tab **ATTLOG Tools** → bấm 🔄 Refresh → chọn máy (chấm xanh = online)
4. Nhập PIN + Status → bấm **Chấm công** → đợi ~30s reboot

### APK
1. Cài APK lên Samsung A17 (arm64)
2. Mở app → cài đặt IP của máy chạy EXE (vd: 192.168.1.101:8080)
3. Tab **ATTLOG Tools** → chọn máy → chấm công

## Cấu trúc repo

```
TH/
├── README.md                         # File này
├── AttendanceSuite-v2.0.1.exe       # Portable EXE (chạy trên Windows 10/11)
├── attendance-mobile-arm64-2.0.1+14.apk  # APK cho Samsung A17
├── docs/                              # Tài liệu nghiên cứu ZK
│   ├── ZK_ATTLOG_WRITE_EXHAUSTIVE_RESEARCH_2026.md
│   ├── ZK_CVE_2023_3941_REMOTE_ATTLOG_WRITE_CONFIRMED.md
│   ├── ZK_RESEARCH_INDEX.md
│   ├── K-ZkTeco-2023-001..006.md     # CVE advisories
│   ├── X628_PRO_ADMS_ENABLE_GUIDE.md
│   ├── X628_PRO_FLASH_DUMP_PREP.md
│   └── ...
└── tools/                             # ZK research tools
    ├── zk_remote_attlog_write.py      # Production ATTLOG injection tool
    ├── zk_arbitrary_read.py            # CVE-2023-3940
    ├── zk_patch_binwalk*.py            # Binwalk patches for Windows
    └── ... (100+ scripts)
```

## CVE được sử dụng

- **CVE-2023-3941** (CVSS 10.0) - UPLOAD_PICTURE path traversal → arbitrary file write
- **CVE-2023-3940** (CVSS 7.5) - READFILE path traversal → arbitrary file read
- **CVE-2023-4587** (CVSS 9.8) - Unauthenticated backup download
- **CVE-2023-3939** (CVSS 10.0) - Command injection (NOT exploitable trên X628 PRO FW 6.60)

## ZK Devices test thành công

- May 3 (172.16.0.214) - X628 PRO FW 6.60 Dec 9 2019 - ZLM60_TFT platform
- Web UI (172.16.254.202) - FW 6.60 May 14 2018

## Yêu cầu hệ thống

- **EXE**: Windows 10/11 + Edge WebView2 (có sẵn)
- **APK**: Android 8.0+ (arm64-v8a)
- **Network**: Cùng LAN/VPN với máy chấm công ZK (port 4370 cho giao thức, port 80 cho web backup)
