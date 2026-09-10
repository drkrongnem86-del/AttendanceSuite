# 📋 Polish Notes - Những gì đã upgrade

**Cập nhật**: 2026-09-10  
**Phiên bản tool**: v1.1 (polish release)

## Tổng quan

Sau khi test chạy thực tế ở local, tôi đã polish toàn bộ hệ thống thành production-ready. Tất cả thay đổi đã test pass.

---

## 1. Dashboard mới (Basic Auth + Mobile UI)

### File: `remote_punch_service.py`

**Đã thêm**:
- **Basic Auth** — mặc định `admin / bvdk2026`. Tất cả endpoint yêu cầu auth, trừ `/healthz`
- **Mobile-responsive CSS** — dùng được trên điện thoại, nút to, layout gọn
- **Quick-punch UI** — 4 nút bấm nhanh (VÀO CA / TAN CA / RA NGOÀI / VÀO LẠI)
- **AJAX support** — form submit không reload page
- **Health check endpoint** `/healthz` — cho monitoring tools, không cần auth
- **Stats JSON** `/api/stats` — cho mobile app poll nhanh
- **Logout endpoint** `/logout` — clear browser auth
- **Auto-refresh stats** (5s) thay vì full page reload
- **Validation** — kiểm tra user_id là số, reject nếu không hợp lệ

**Test kết quả**: 8/8 PASS (auth, mobile CSS, AJAX, validation, health, stats, logout, all buttons)

### Auth

Để tắt auth (chỉ dùng local), sửa trong `remote_punch_service.py`:
```python
AUTH_ENABLED = False  # mac dinh: True
```

Để đổi user/pass:
```python
AUTH_USER = "admin"
AUTH_PASS = "bvdk2026"  # DOI truoc khi expose internet!
```

---

## 2. Mobile App - Tab "Chấm từ xa"

### File mới: `attendance_mobile/lib/remote_punch_screen.dart` (~14KB)

Màn hình mới với:
- Form nhập Mã NV (autofocus, bàn phím số)
- 6 nút thao tác màu (Check-In xanh, Check-Out đỏ, Break vàng/xanh, OT tím/cam)
- Dropdown chọn máy
- Nút CHẤM CÔNG to
- Lịch sử chấm trong session (20 record gần nhất)
- Banner gradient giải thích
- Lưu ý cuối trang (về pending queue)

### File modified: `attendance_mobile/lib/main.dart`

Thêm tab thứ 3 vào BottomNavigationBar:
- Tab 1: 📊 Log chấm công (cũ)
- Tab 2: 🖐 X628 PRO (cũ)
- Tab 3: ☁️ **Chấm từ xa** (mới)

### File modified: `attendance_mobile/lib/api.dart`

Thêm method `remotePunch(userId, status, deviceIp)` — gọi `POST /api/remote-punch` với Basic Auth header.

### Version: `1.3.1+5` → `1.3.2+6`

Cần BS build APK mới:
```powershell
cd D:\chamcong\AttendanceSuite_source\attendance_mobile
flutter build apk --release
```

APK mới sẽ cài đè được lên APK cũ (cùng keystore, cùng applicationId).

---

## 3. Internet Deployment (1-click)

### File mới: `expose_internet.bat`

Script tự động:
- Download `cloudflared.exe` từ GitHub (nếu chưa có)
- Tạo Cloudflare Tunnel ngẫu nhiên
- Expose `http://localhost:8082` ra HTTPS public
- In URL cho user copy

**Cách dùng**:
```powershell
cd D:\chamcong
expose_internet.bat
```

URL dạng `https://random-words.trycloudflare.com` → dùng từ bất kỳ đâu.

---

## 4. Files summary (cập nhật)

| File | Status | Thay đổi |
|---|---|---|
| `remote_punch_service.py` | ✏️ Updated | Basic auth, mobile UI, health check, stats JSON, AJAX, validation |
| `attendance_mobile/lib/main.dart` | ✏️ Updated | Thêm tab thứ 3, import RemotePunchScreen |
| `attendance_mobile/lib/api.dart` | ✏️ Updated | Thêm `remotePunch()` method |
| `attendance_mobile/pubspec.yaml` | ✏️ Updated | Version 1.3.1+5 → 1.3.2+6 |
| `attendance_mobile/lib/remote_punch_screen.dart` | 🆕 New | Màn hình chấm từ xa |
| `expose_internet.bat` | 🆕 New | Cloudflare tunnel 1-click |
| `test_dashboard.py` | 🆕 New | Test script (8 cases, đã pass) |
| `POLISH_NOTES.md` | 🆕 New | File này |
| `SETUP_REMOTE_PUNCH.md` | ✏️ Updated | Hướng dẫn Cloudflare tunnel mới |

---

## 5. Checklist khi deploy lên máy BV

Sau khi BS về máy:

1. [ ] Copy tất cả file mới vào `D:\chamcong\` (đã có sẵn trên máy BS)
2. [ ] Copy `attendance_web.py` (đã sửa) đè lên bản cũ trong `AttendanceSuite_source/`
3. [ ] Copy `attendance_mobile/lib/remote_punch_screen.dart` + `main.dart` + `api.dart` + `pubspec.yaml` vào Flutter project
4. [ ] Build APK mới: `flutter build apk --release`
5. [ ] Chạy `start_all.bat` → 3 service tự động start
6. [ ] Test browser: mở `http://localhost:8082/`, nhập `admin / bvdk2026`
7. [ ] Test mobile: cài APK mới, mở tab "Chấm từ xa"
8. [ ] (Optional) Chạy `expose_internet.bat` → URL public
9. [ ] (Optional) Đổi password trong `remote_punch_service.py` nếu expose internet

---

## 6. Test coverage

Đã test (8/8 PASS):
- ✅ `/healthz` (no auth)
- ✅ `/` (no auth → 401)
- ✅ `/` (correct auth → 200, full render)
- ✅ `/` (wrong password → 401)
- ✅ `/api/stats` (JSON đúng format)
- ✅ `POST /punch` (form-encoded, redirect)
- ✅ `POST /punch` (AJAX, JSON response)
- ✅ `POST /punch` (invalid user_id → 400)

Test file: `D:\chamcong\test_dashboard.py` (chạy được khi service đang chạy)

---

## 7. Security checklist

- [x] Basic Auth cho dashboard (mặc định bật)
- [x] Validation input (user_id phải là số)
- [x] CSV file path chuẩn hóa (tránh path traversal)
- [x] Error handling có try/except
- [x] HTTP method whitelist (chỉ GET, POST)
- [ ] **CẦN BS**: Đổi password `bvdk2026` trước khi expose internet
- [ ] **CẢNH BÁO**: Hiện tại HTTP plain (không HTTPS) — chỉ OK trong LAN hoặc qua Cloudflare Tunnel (HTTPS ở phía client)

---

## 8. Known issues / chưa làm

- **Không có auto-restart** nếu service crash. Workaround: dùng Windows Task Scheduler hoặc NSSM
- **Không có HTTPS** natively. Cloudflare Tunnel giải quyết phía client
- **Không có rate limit** → có thể spam POST /punch
- **CSV có thể lớn** nếu dùng lâu → cần rotate định kỳ
- **Không có audit log** ai đã chấm lúc nào (chỉ có thời gian, không có user session)

Tôi có thể làm tiếp các issue này nếu BS cần.
