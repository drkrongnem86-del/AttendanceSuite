# AttendanceSuite v2.1.0 - Self-Contained APK + VPN

## Giới thiệu

**AttendanceSuite** - Phần mềm quản lý chấm công từ xa cho các máy chấm công vân tay ZK X628 PRO FW 6.60 tại **BVĐK Ninh Thuận**.

**Tác giả:** Dr. Nểm (Bác sĩ Cấp cứu - BVĐK Ninh Thuận)
**Bản quyền:** © 2026 Dr. Nểm - BVĐK Ninh Thuận

## 🚀 v2.1.0 - APK Self-Hosted + VPN (NEW!)

### Cải tiến chính
- ✅ **APK tự host server** trong app (shelf HTTP server chạy trên port 8080, không cần Windows EXE)
- ✅ **VPN Bệnh viện tích hợp sẵn** (openvpn_flutter) - kết nối 172.16.x.x không cần OpenVPN Connect
- ✅ **ZK protocol client trong Dart** - kết nối trực tiếp port 4370 từ phone
- ✅ **Giao diện mới** với top bar icons + bottom nav 6 tabs + chấm xanh online status
- ✅ **Auto-detect server URL** - ưu tiên 127.0.0.1 (embedded), fallback network IP
- ✅ **Live Status + search filter** - tìm theo IP/tên/lỗi + filter chip Online/Offline/CC/KY/SIM

### Yêu cầu
- **Android 7.0+** (API 24+)
- **arm64-v8a** (Samsung A17 hoặc tương đương)
- ~45 MB cho APK có sẵn OpenVPN library

### Cài đặt
1. Copy `attendance-mobile-arm64-2.1.0+16.apk` sang điện thoại
2. Mở bằng File Manager → "Cài đặt"
3. Cho phép "Cài đặt từ nguồn không xác định"
4. Cài đè được lên v2.0.x (cùng signing cert SHA-1 `5d54b3cf...`)

### Sử dụng APK standalone (không cần Windows)

#### Tab 1: Log (Đọc log chấm công)
- Server URL hiển thị ở top bar (mặc định `http://127.0.0.1:8080`)
- **Bấm icon 🩺** trên top bar để xem trạng thái kết nối (server/VPN/devices)
- Chọn ngày / chips: Hôm nay / Hôm qua / 7 ngày / 30 ngày
- Tick thiết bị bên trái → **LẤY LOG** → app tự fetch qua embedded server

#### Tab 6: Cài đặt (VPN + Server)
- **🔌 Server embedded**: hiển thị trạng thái + restart
- **🌐 VPN Bệnh viện**:
  - Username mặc định: `nemk`
  - **Paste file .ovpn** từ BV vào mục "Cấu hình nâng cao"
  - **KẾT NỐI** → app tự động bật VPN, sau đó có thể truy cập 172.16.x.x
  - **NGẮT** → tắt VPN
- **Thông tin**: phiên bản, tác giả, GitHub

### Cấu hình file .ovpn

App cần file `.ovpn` của BV Ninh Thuận. Cách lấy:

1. Từ máy tính có OpenVPN Connect: vào Settings → Profile → Export .ovpn
2. Copy nội dung file .ovpn (bao gồm certificates)
3. Trong app: Tab Cài đặt → VPN → Mở "⚙️ Cấu hình nâng cao" → Paste nội dung .ovpn
4. Lưu → KẾT NỐI

Nếu chưa có file .ovpn, có thể dùng cách khác: nhờ IT BV cấp file VPN qua email.

### Các tính năng khác (vẫn còn)
- ✅ X628 PRO Simulator (Tab 2)
- ✅ Chấm từ xa (Tab 3) - qua web backup
- ✅ PIN+Password workflow (Tab 4) - BYPASS FW 6.60
- ✅ Bảo mật / ATTLOG Tools (Tab 5)

### Vẫn dùng Windows EXE nếu muốn (v2.0.2)
- EXE chạy trên máy tính, phone kết nối vào `http://<PC_IP>:8080`
- Dùng khi cần giao diện lớn hơn hoặc test nhanh

## Lịch sử

- **v2.1.0+16** (16/09/2026) - Self-hosted APK + VPN
- **v2.0.2+15** (16/09/2026) - EXE + APK + Windows backend
- **v2.0.1+14** (16/09/2026) - Initial production release
- **v1.9.0+12** trở về trước: Early development

## Liên hệ

Dr. Nểm - Khoa Cấp cứu - BVĐK Ninh Thuận
GitHub: https://github.com/drkrongnem86-del/AttendanceSuite
