@echo off
REM ============================================================
REM Fix Windows Firewall - cho phep port 8080 va 8081
REM Chay voi quyen Administrator
REM ============================================================

echo ============================================
echo FIX FIREWALL - AttendanceSuite
echo ============================================
echo.

REM Check admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Can chay voi quyen Administrator!
    echo Nhan chuot phai vao file nay ^> "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo [OK] Dang chay voi quyen Administrator
echo.

REM Add inbound rules for ports 8080 and 8081
echo [1/4] Them rule cho port 8080 (viewer)...
netsh advfirewall firewall add rule name="AttendanceSuite Viewer 8080" dir=in action=allow protocol=TCP localport=8080 >nul 2>&1
if %errorlevel% equ 0 (echo       OK - port 8080) else (echo       WARNING: Co the rule da ton tai)

echo [2/4] Them rule cho port 8081 (simulator)...
netsh advfirewall firewall add rule name="AttendanceSuite Simulator 8081" dir=in action=allow protocol=TCP localport=8081 >nul 2>&1
if %errorlevel% equ 0 (echo       OK - port 8081) else (echo       WARNING: Co the rule da ton tai)

REM Allow python.exe
echo [3/4] Cho phep python.exe trong firewall...
set PYTHON_EXE=%~dp0python\python.exe
if exist "%PYTHON_EXE%" (
    netsh advfirewall firewall add rule name="AttendanceSuite Python" dir=in action=allow program="%PYTHON_EXE%" >nul 2>&1
    if %errorlevel% equ 0 (echo       OK - python.exe) else (echo       WARNING: rule co the da ton tai)
) else (
    echo       python.exe khong tim thay o %PYTHON_EXE%
)

REM Show IP addresses
echo.
echo [4/4] Dia chi IP cua may nay (dien thoai can ket noi toi):
echo ----------------------------------------------------------------
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4"') do (
    for /f "tokens=*" %%i in ("%%a") do echo       %%i
)
echo ----------------------------------------------------------------
echo.
echo HOAN TAT!
echo.
echo Bay gio ban co the:
echo   - Chay AttendanceSuite.exe
echo   - Mo dien thoai, app AttendanceSuite
echo   - Bam nut "Diagnostic" (wifi_tethering icon) de test ket noi
echo   - Neu can doi IP: bam nut "ethernet" icon
echo.
pause
