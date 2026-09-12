@echo off
REM ====================================================================
REM Install 3 AttendanceSuite services with auto-restart via NSSM
REM - AttendanceViewer  (port 8080)
REM - AttendanceSim     (port 8081)
REM - AttendanceRemote  (port 8082)
REM
REM Required: NSSM (https://nssm.cc/download) - extract nssm.exe to PATH or this folder
REM
REM Usage:
REM   1. Download NSSM (nssm-2.24.zip) from https://nssm.cc/download
REM   2. Extract nssm.exe (win64) to this folder or %WINDIR%\System32
REM   3. Run as Administrator: install_services.bat
REM
REM To uninstall: uninstall_services.bat
REM ====================================================================

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

REM ---- Detect Python + scripts ----
set PYTHON=%~dp0AttendanceSuite_Portable\python\python.exe
if not exist "%PYTHON%" (
    set PYTHON=python.exe
    echo [INFO] AttendanceSuite_Portable not found, using system Python
)

set VIEWER_SCRIPT=%~dp0attendance_web.py
set SIMULATOR_SCRIPT=%~dp0punch_simulator.py
set REMOTE_SCRIPT=%~dp0remote_punch_service.py

if not exist "%VIEWER_SCRIPT%"   ( echo [LOI] Khong tim thay %VIEWER_SCRIPT%   & pause & exit /b 1 )
if not exist "%SIMULATOR_SCRIPT%" ( echo [LOI] Khong tim thay %SIMULATOR_SCRIPT% & pause & exit /b 1 )
if not exist "%REMOTE_SCRIPT%"   ( echo [LOI] Khong tim thay %REMOTE_SCRIPT%   & pause & exit /b 1 )

REM ---- Detect NSSM ----
set NSSM=nssm.exe
where nssm >nul 2>&1
if errorlevel 1 (
    if not exist "%~dp0nssm.exe" (
        echo [LOI] Khong tim thay nssm.exe trong PATH hoac thu muc nay.
        echo        Tai NSSM tu: https://nssm.cc/download
        echo        Giai nen nssm.exe (win64) vao thu muc nay hoac %%WINDIR%%\System32
        pause
        exit /b 1
    )
    set NSSM=%~dp0nssm.exe
)

REM ---- Kiem tra quyen Admin ----
net session >nul 2>&1
if errorlevel 1 (
    echo [LOI] Can quyen Administrator. Click phai - Run as Administrator.
    pause
    exit /b 1
)

REM ---- Log dir ----
if not exist "%~dp0logs" mkdir "%~dp0logs"

echo ======================================================================
echo  INSTALL 3 SERVICES - BVDK NINH THUAN
echo  Python: %PYTHON%
echo  NSSM:   %NSSM%
echo ======================================================================
echo.

REM ---- Helper function: install 1 service ----
:install_service
set SVC_NAME=%~1
set SVC_DESC=%~2
set SCRIPT_PATH=%~3
set PORT=%~4
echo [%SVC_NAME%] Dang cai dat...

REM Neu service da ton tai -> stop + remove truoc
sc query "%SVC_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo   Service da ton tai, go bo cu truoc...
    "%NSSM%" stop "%SVC_NAME%" >nul 2>&1
    timeout /t 2 /nobreak > nul
    "%NSSM%" remove "%SVC_NAME%" confirm
)

REM Install
"%NSSM%" install "%SVC_NAME%" "%PYTHON%" "\"%SCRIPT_PATH%\""
if errorlevel 1 ( echo   [LOI] Install that bai & goto :error )

REM AppDirectory
"%NSSM%" set "%SVC_NAME%" AppDirectory "%~dp0"

REM Stdout/stderr log
"%NSSM%" set "%SVC_NAME%" AppStdout "%~dp0logs\%SVC_NAME%.out.log"
"%NSSM%" set "%SVC_NAME%" AppStderr "%~dp0logs\%SVC_NAME%.err.log"
"%NSSM%" set "%SVC_NAME%" AppStdoutCreationDisposition 4
"%NSSM%" set "%SVC_NAME%" AppStderrCreationDisposition 4
"%NSSM%" set "%SVC_NAME%" AppRotateFiles 1
"%NSSM%" set "%SVC_NAME%" AppRotateBytes 10485760

REM Auto-restart on crash
"%NSSM%" set "%SVC_NAME%" AppExit Default Restart
"%NSSM%" set "%SVC_NAME%" AppRestartDelay 5000

REM Start type: auto (khoi dong cung Windows)
"%NSSM%" set "%SVC_NAME%" Start SERVICE_AUTO_START

REM Display name + description
"%NSSM%" set "%SVC_NAME%" DisplayName "%SVC_DESC%"
"%NSSM%" set "%SVC_NAME%" Description "%SVC_DESC% - Port %PORT%"

REM Start service
"%NSSM%" start "%SVC_NAME%"
if errorlevel 1 ( echo   [CANH BAO] Start that bai, kiem tra log & goto :error )

echo   [OK] %SVC_NAME% da cai xong, dang chay.
echo.
exit /b 0

:error
echo.
echo [LOI] Mot service cai dat that bai. Kiem tra log: %~dp0logs\
pause
exit /b 1


REM ---- Main install ----
call :install_service "AttendanceViewer"  "Attendance Log Viewer (port 8080)"  "%VIEWER_SCRIPT%"   8080
call :install_service "AttendanceSim"     "X628 PRO Simulator (port 8081)"      "%SIMULATOR_SCRIPT%" 8081
call :install_service "AttendanceRemote"  "Remote Punch Service (port 8082)"    "%REMOTE_SCRIPT%"   8082

echo ======================================================================
echo  DA CAI XONG 3 SERVICES.
echo  - AttendanceViewer  (port 8080)
echo  - AttendanceSim     (port 8081)
echo  - AttendanceRemote  (port 8082)
echo.
echo  Log files: %~dp0logs\
echo  Services Manager: services.msc (tim theo ten "Attendance*")
echo.
echo  Commands:
echo    sc query AttendanceViewer
echo    nssm restart AttendanceRemote
echo    nssm stop AttendanceSim
echo ======================================================================
echo.
pause
