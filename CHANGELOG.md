# AttendanceSuite Changelog

## v2.7.5 (2026-09-24)
- Backend: Thêm 2 loại EXE build trong GitHub Actions
  - Backend EXE (`AttendanceSuite-v{VERSION}.exe`): silent HTTP server (headless, kiosk, scheduled)
  - Launcher EXE (`AttendanceSuite-v{VERSION}-Launcher.exe`): v2.0.13 style với pywebview native window + threading
- Launcher mới wrap attendance_web.py (v2.6.11) in-process, mở native window tới `launcher.html`
- Workflow mới: `build-exe-backend` + `build-exe-launcher` (spec file `build_attendance_suite.spec`)
- Requirements: thêm `pywebview>=4.0`, `pystray>=0.19`, `Pillow>=10.0`, `pythonnet>=3.0`
- APK: bump version lên 2.7.5+48 (cosmetic, không đổi code mobile)

## v2.7.4 (2026-09-24)
- APK v2.7.4+47: Auto-detect backend (3 URLs: CCDK-M6 / CCDK-M10 / Sophos tunnel) + quick switch banner
- Không còn hardcode URL trong banner (dùng `widget.api.baseUrl`)
