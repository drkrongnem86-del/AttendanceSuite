# AttendanceSuite APK Build #17 - SUCCESS (LOCAL)
- Date: 2026-09-12 12:01:52
- Commit: 3f8e177 (feat/mobile: v1.3.3+7 - auto-update + UI polish)
- Build method: LOCAL Flutter build (after GH Actions #14 failed)
- Reference: https://github.com/drkrongnem86-del/his_mobile (v3.0.184+326 working stack)
- Flutter: 3.41.7
- Java: Temurin 17.0.13+11 (full JDK, downloaded from adoptium)
- AGP: 8.11.1 (bumped from 8.1.1)
- Kotlin: 2.2.20 (bumped from 1.9.22)
- Gradle: 8.14 (bumped from 8.7)
- shared_preferences_android: 2.4.7 (pinned for Dart ^3.5.4 compat)
- url_launcher: 6.3.2 (default) + url_launcher_android: 6.3.30 (latest)

## Why local build (not GH Actions)?
- GH Build APK #14 (commit 3f8e177) **FAILED** with `androidx.browser:1.9.0` requires AGP 8.9.1+
- Local was faster to iterate + debug (could fix issues in real-time)
- Used his_mobile's known-working stack: AGP 8.11.1 + Kotlin 2.2.20 + Gradle 8.14

## APK
- Path: D:\chamcong\AttendanceSuite\apk\attendance-mobile-arm64-1.3.3+7.apk
- Source: D:\chamcong\AttendanceSuite\attendance_mobile\build\app\outputs\flutter-apk\app-release.apk
- Size: 18120888 bytes (17.28 MB)
- SHA-256: 9AF90D0B35489B78B5E971F489D57AE96B4833D5A6AA8C009AAE8CA719F767F6
- ABI: arm64-v8a only
- Signed: release.keystore (alias te-c0a93129-73ca-4337-bc61-75be6178951b)

## v1.3.3 features (since v1.3.2+6)
- Auto-update from GitHub Releases (`lib/updater.dart`, 24h cache)
- Haptic feedback (light/medium/heavy) on remote punch
- Better SnackBar (floating, rounded) with error messages
- `url_launcher: ^6.3.0` for "Mở Release" button
- `_checkForUpdates()` runs 5s after startup, non-blocking

## Keystore (UNCHANGED - same as v1.3.2+6)
- File: D:\chamcong\AttendanceSuite\attendance_mobile\android\app\release.keystore
- SHA-256: D7C57B9D263360A25CC87483B4F630FD6F331D710BFB699ED8083B842DCB3F1A
- Cert SHA-1: 5D54B3CF8CAC8F87FB841F11F6CDA9A654C8F6C5
- Alias: te-c0a93129-73ca-4337-bc61-75be6178951b
- Password: bvdk@2026
- CN=BVDK Ninh Thuan, OU=HSCCL, O=BVDK

## Verification: APK signature matches previous build
- v1.3.2+6 SHA-256: 6CF79ACAD0921C9BFF449AF63BF8ABA525E6C39C727E7EB1FF9AA07CA1610312 (17.35 MB)
- v1.3.3+7 SHA-256: 9AF90D0B35489B78B5E971F489D57AE96B4833D5A6AA8C009AAE8CA719F767F6 (17.28 MB)
- Note: APK content SHA differs (new features) but **signing cert is the same** (release.keystore).
  This means v1.3.3+7 will install OVER v1.3.2+6 without uninstall first.

## Next steps
1. [x] Build APK locally → SUCCESS (17.28 MB)
2. [x] Copy to apk/ folder
3. [x] Verify SHA-256
4. [ ] Create GitHub Release tag v1.3.3 with this APK (for auto-update feature)
5. [ ] Commit build files (run_build.py, check_jobs.py) - or delete if temporary
6. [ ] Update GH Actions workflow to match new stack (AGP 8.11.1 + Kotlin 2.2.20 + Gradle 8.14)
