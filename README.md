# AttendanceSuite v2.0.2 - Portable EXE + APK arm64

## Giới thiệu

**AttendanceSuite** - Phần mềm quản lý chấm công từ xa cho các máy chấm công vân tay ZK X628 PRO FW 6.60 tại **BVĐK Ninh Thuận**.

**Tác giả:** Dr. Nểm (Bác sĩ Cấp cứu - BVĐK Ninh Thuận)
**Bản quyền:** © 2026 Dr. Nểm - BVĐK Ninh Thuận

## Tính năng v2.0.2

### MỚI trong v2.0.2 (16/09/2026)
- ✅ **Live Device Status có Search Filter** - tìm theo IP / tên / lỗi + filter chip Online/Offline/CC/KY/SIM
- ✅ **Server/GW + Ký vân tay (KY) đã chọn được** trong Attendance Log Viewer
- ✅ **Auto-detect device IP cho Simulator** - ưu tiên VPN subnet kết nối được
- ✅ **Socket-level preflight ping** + 3 retries (fix 172.16.8.139 / May 20 race condition WinError 1005)
- ✅ **Fix "Mất kết nối undefined"** trong X628 PRO Simulator (data.ip có giá trị)
- ✅ **Fix e.message undefined** trong fetch errors + status_name crash

### 1. AttendanceSuite-v2.0.2.exe (Portable EXE - 15MB)
- ✅ Double-click → cửa sổ desktop mở ngay (pywebview + Edge WebView2)
- ✅ 2 servers chạy ngầm trong 1 process (không spawn subprocess):
  - **Viewer** :8080 - Log chấm công + báo cáo
  - **Simulator** :8081 - Mô phỏng máy X628 PRO
- ✅ 4 tabs UI: Đọc log / X628 Simulator / ATTLOG Tools / Live Status
- ✅ Filter nhanh: Hôm nay / Hôm qua / Tuần này / Tháng này / Tất cả
- ✅ ATTLOG Tools: Inject / Delete / Edit Time / Real Punch qua CVE-2023-3941
- ✅ Live Status search filter (Online/Offline/CC/KY/SIM) + search box
- ✅ Tự động kill port cũ khi khởi động (tránh lỗi trùng port)
- ✅ Single-instance lock (không cho mở 2 cửa sổ)
- ✅ Force kill port khi đóng (clean shutdown)

### 2. attendance-mobile-arm64-2.0.2+15.apk (APK arm64 - 17MB)
- ✅ Flutter mobile app cho Android arm64-v8a
- ✅ 4 tabs: Log chấm công / X628 PRO / Chấm từ xa / **ATTLOG Tools**
- ✅ ATTLOG Tools gọi EXE qua HTTP để inject/delete/edit
- ✅ Cài đè được lên mọi version trước (cùng signing cert SHA-1 `5d54b3cf...f6c5`)

## Cài đặt

### Windows EXE
1. Copy `AttendanceSuite-v2.0.2.exe` ra Desktop
2. Double-click → cửa sổ desktop mở ra
3. Không cần cài đặt, không cần Python, không cần mạng (trừ khi giao tiếp thiết bị)

### Android APK
1. Copy `attendance-mobile-arm64-2.0.2+15.apk` sang điện thoại
2. Mở bằng File Manager → "Cài đặt"
3. Cho phép "Cài đặt từ nguồn không xác định" nếu được hỏi
4. App tự nhận diện thiết bị qua VPN/Wi-Fi

## Sử dụng

### Tab 1: Đọc log chấm công
- Tick chọn máy cần đọc (CC/KY/SV/GW đều chọn được)
- Chọn ngày hoặc bấm "Hôm nay / Hôm qua / Tuần / Tháng / Tất cả"
- Bấm **"Lấy log"** → tự động fetch từ web backup (nhanh) hoặc từ thiết bị (chậm)
- "Export CSV" / "Excel" / "Báo cáo" ở góc trên

### Tab 2: X628 PRO Simulator
- Chọn máy online (chấm xanh) hoặc nhập IP thủ công
- Nhập Mã NV + Pass (nếu cần)
- Chọn thao tác (Check-In/Out, Break, OT) + phương thức (Vân tay/Thẻ/Mã số)
- Bấm **"Chấm công"** → ghi local + cố gắng ghi lên máy thật
- ⚠️ Máy X628 PRO firmware 6.60 ACK_OK nhưng KHÔNG ghi ATTLOG từ xa (đây là giới hạn firmware)

### Tab 3: ATTLOG Tools (CVE-2023-3941)
- **Real Punch**: chấm công thật qua web backup (ghi vào ZKDB.db)
- **Inject**: chèn bản ghi mới vào ATTLOG (cần reboot ~30s)
- **Delete**: xóa bản ghi theo marker (đánh dấu khi inject để cleanup)
- **Edit Time**: chỉnh sửa thời gian bản ghi đã inject
- Tất cả thao tác đều dùng CVE-2023-3941 (UPLOAD_PICTURE path traversal + UPLOAD_USERPHOTO)
- Backup tự động qua CVE-2023-4587 (unauth web backup download)

### Tab 4: Live Device Status
- Auto-probe mỗi 8 giây
- **Search filter** (input box): tìm theo IP / tên / lỗi
- **Filter chip**: Tất cả / Online / Offline / CC / KY / SIM
- Hiển thị latency (ms), log count, lỗi (nếu có)

## Lưu ý kỹ thuật

### Yêu cầu
- **Windows 10+** cho EXE (cần WebView2 - đã có sẵn trên Windows 11)
- **Android 7.0+** (API 24+) cho APK
- **Mạng VPN nội bộ BVĐK Ninh Thuận** để truy cập 24 máy chấm công
- **PIN 1 (admin)** đã được đăng ký trên máy thật

### Thiết bị đã test (verified E2E)
- **May 3** (172.16.0.214) - X628 PRO FW 6.60 Dec 9 2019 - CVE-2023-3941 EXPLOITED
- **May 20** (172.16.8.139) - WinError 1005 race fix - socket-level retry
- **Web UI** (172.16.254.202) - CVE-2023-4587 backup vulnerable
- 21/24 thiết bị khác cần VPN để truy cập

### Bảo mật
⚠️ **Tool này khai thác CVE-2023-3941 + CVE-2023-4587 trên ZK X628 PRO FW 6.60.**
Chỉ sử dụng trên thiết bị thuộc sở hữu của BVĐK Ninh Thuận.

## Lịch sử

- **v2.0.2** (16/09/2026) - Live Status search, KY/SV/GW selectable, fix Simulator undefined, socket retry
- **v2.0.1** (16/09/2026) - Quick filter buttons, online status indicator, single-instance lock
- **v2.0.0** (16/09/2026) - Production release: Portable EXE + APK + ATTLOG Tools
- **v1.3.2+6** trở về trước: Early development versions

## Liên hệ

Dr. Nểm - Khoa Cấp cứu - BVĐK Ninh Thuận
GitHub: https://github.com/drkrongnem86-del/AttendanceSuite
