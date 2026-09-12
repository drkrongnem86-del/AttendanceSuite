@echo off
REM ====================================================================
REM Uninstall 3 AttendanceSuite services (NSSM)
REM Usage: Run as Administrator
REM ====================================================================

setlocal EnableExtensions
cd /d "%~dp0"

set NSSM=nssm.exe
where nssm >nul 2>&1
if errorlevel 1 (
    if not exist "%~dp0nssm.exe" (
        echo [LOI] Khong tim thay nssm.exe
        pause
        exit /b 1
    )
    set NSSM=%~dp0nssm.exe
)

net session >nul 2>&1
if errorlevel 1 (
    echo [LOI] Can quyen Administrator.
    pause
    exit /b 1
)

echo ======================================================================
echo  UNINSTALL 3 SERVICES
echo ======================================================================
echo.

for %%S in (AttendanceViewer AttendanceSim AttendanceRemote) do (
    sc query "%%S" >nul 2>&1
    if not errorlevel 1 (
        echo [%%S] Dang stop + remove...
        "%NSSM%" stop "%%S"
        timeout /t 2 /nobreak > nul
        "%NSSM%" remove "%%S" confirm
        echo   [OK] %%S da go.
    ) else (
        echo [%%S] Khong ton tai, skip.
    )
)

echo.
echo ======================================================================
echo  DA GO XONG.
echo  Neu muon restart manual: start_all.bat
echo ======================================================================
pause
