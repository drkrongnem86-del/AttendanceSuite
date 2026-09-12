# AttendanceSuite v1.5.7 Release

**Build date**: 11/09/2026
**APK SHA256**: 220a08f15142482b82ea91d1a2b547995c7229bea3c138a660082ce7f3d95215
**APK size**: 33.32 MB

## Highlights

- **VPN Benh vien** (native OpenVPN client via openvpn_flutter)
- **VPN error capture chi tiet** (rawStage tu ics-openvpn)
- **Device panel fullscreen toggle** (vuot trai xem chi tiet log)
- **Auto-refresh X628 PRO** connection moi 5s
- **Version hien thi trong Settings** (package_info_plus)
- **Bug fix**: check_device_info() inner exception set connected=False (was True)

## Files trong archive

- `dist/attendance_mobile-release.apk` - APK v1.5.7+10 (signed)
- `dist/AttendanceSuite.exe` - Windows launcher (PyInstaller)
- `attendance_web.py`, `punch_simulator.py`, `remote_punch_service.py` - Python services
- `attendance_mobile/` - Flutter source code (lib/, android/, pubspec.yaml)
- `config.json`, `devices.csv` - Runtime config
- `*.bat`, `*.ps1` - Windows helper scripts
- `README.md`, `CHANGELOG.md`, `POLISH_NOTES.md`, `SETUP_REMOTE_PUNCH.md` - Docs
- `.github/workflows/` - CI/CD (build-apk.yml, lint.yml)

## Cai nhanh

```powershell
# 1. Setup Python + pyzk
setup_python.bat

# 2. Start tat ca service
start_all.bat

# 3. Cai APK len dien thoai
adb install dist\attendance_mobile-release.apk
```

## GitHub Actions

- Push len main -> build APK (artifact)
- Push tag v* -> tao Release voi APK dinh kem

## Lien he

- BVĐK Ninh Thuan - Khoa Cap Cuu Luu Ky (HSCCL)
- BS: BSCKI Nguyen Che Thuy Diem (`nemk`)
