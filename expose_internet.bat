@echo off
REM ====================================================================
REM Expose Remote Punch Service ra Internet (Cloudflare Tunnel)
REM Khong can dang ky Cloudflare account - URL random moi lan chay
REM Muc dich: BS cham cong tu bat ky dau qua HTTPS
REM ====================================================================

setlocal EnableExtensions
cd /d "%~dp0"

set CLOUDFLARED=%~dp0cloudflared.exe
set URL_FILE=%~dp0tunnel_url.txt

REM 1. Kiem tra cloudflared.exe
if not exist "%CLOUDFLARED%" (
    echo [1/3] Dang download cloudflared...
    powershell -NoProfile -Command ^
        "try { Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CLOUDFLARED%' -UseBasicParsing } catch { Write-Host 'Download failed, vui long tai thu cong tu github.com/cloudflare/cloudflared' -ForegroundColor Red; exit 1 }"
    if not exist "%CLOUDFLARED%" (
        echo [LOI] Khong download duoc cloudflared
        echo Hay tai thu cong tu: https://github.com/cloudflare/cloudflared/releases/latest
        pause
        exit /b 1
    )
    echo [OK] Da download cloudflared
) else (
    echo [1/3] cloudflared.exe da co san
)

REM 2. Check service da chay chua
echo [2/3] Kiem tra service...
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:8082/healthz' -UseBasicParsing -TimeoutSec 2).StatusCode } catch { Write-Host 'NO'; exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [LOI] Service chua chay! Hay chay start_all.bat truoc.
    echo Sau do chay lai expose_internet.bat
    pause
    exit /b 1
)
echo [OK] Service dang chay

REM 3. Chay tunnel
echo [3/3] Dang tao Cloudflare Tunnel...
echo.
echo ======================================================================
echo  URL PUBLIC SE XUAT HIEN DUOI DAY. COPY DE DUNG TU XA.
echo  URL chi ton tai trong phien nay, restart se doi URL moi.
echo  Auth: admin / bvdk2026
echo ======================================================================
echo.

REM Chay cloudflared va capture URL
"%CLOUDFLARED%" tunnel --no-autoupdate --url http://localhost:8082 2>&1 | tee "%URL_FILE%"
