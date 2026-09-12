@echo off
REM Tat tat ca AttendanceSuite + Remote Punch services
taskkill /FI "WINDOWTITLE eq Viewer*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Simulator*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq RemotePunch*" /T /F >nul 2>&1
echo [OK] Da tat tat ca service.
timeout /t 2 /nobreak > nul
