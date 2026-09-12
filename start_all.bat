@echo off
REM ====================================================================
REM AttendanceSuite v1.3.0 + Remote Punch - All-in-One Launcher
REM BVDK Ninh Thuan - Khoa Cap Cuu Luu Ky
REM Tac gia: Mavis (auto-generated)
REM ====================================================================

setlocal
cd /d "%~dp0"

set PYTHON=%~dp0AttendanceSuite_Portable\python\python.exe
set VIEWER=%~dp0AttendanceSuite_source\attendance_web.py
set SIMULATOR=%~dp0AttendanceSuite_source\punch_simulator.py
set REMOTE=%~dp0remote_punch_service.py

if not exist "%PYTHON%" (
    echo [LOI] Khong tim thay Python tai %PYTHON%
    pause
    exit /b 1
)

echo ======================================================================
echo  ATTENDANCESUITE + REMOTE PUNCH - BVDK NINH THUAN
echo ======================================================================
echo  App 1 (Doc log may cham cong):       http://localhost:8080
echo  App 2 (X628 PRO Simulator):          http://localhost:8081
echo  App 3 (Remote Punch Dashboard):     http://localhost:8082
echo  Mobile (API remote-punch):           POST http://localhost:8080/api/remote-punch
echo ======================================================================
echo.

REM Tat service cu neu dang chay
taskkill /FI "WINDOWTITLE eq Viewer*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Simulator*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq RemotePunch*" /T /F >nul 2>&1
timeout /t 2 /nobreak > nul

REM Start Viewer (port 8080)
start "Viewer" /MIN "%PYTHON%" "%VIEWER%"
echo [+] Da khoi dong Viewer (port 8080)
timeout /t 2 /nobreak > nul

REM Start Simulator (port 8081)
start "Simulator" /MIN "%PYTHON%" "%SIMULATOR%"
echo [+] Da khoi dong Simulator (port 8081)
timeout /t 2 /nobreak > nul

REM Start Remote Punch Service (port 8082)
start "RemotePunch" /MIN "%PYTHON%" "%REMOTE%"
echo [+] Da khoi dong Remote Punch Service (port 8082)
timeout /t 2 /nobreak > nul

REM Mo browser
start "" "http://localhost:8080/launcher.html"
echo [+] Da mo browser
echo.
echo Cac service dang chay ngam. Bam phim bat ky de dong cua so nay.
echo.
echo De dung tat ca service, chay: stop_all.bat
pause > nul
