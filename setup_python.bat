@echo off
REM ====================================================================
REM Setup Python Embedded + pyzk cho AttendanceSuite
REM Download Python 3.12 embed + cai pyzk (thay the cho AttendanceSuite_Portable)
REM ====================================================================

setlocal
cd /d "%~dp0"

set PYTHON_DIR=%~dp0AttendanceSuite_Portable\python
set PYTHON_EXE=%PYTHON_DIR%\python.exe
set PYTHON_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip
set PYZK_URL=https://files.pythonhosted.org/packages/source/z/zk/zk-0.9.tar.gz

REM 1. Tao folder
if not exist "%PYTHON_DIR%" mkdir "%PYTHON_DIR%"

REM 2. Download Python embed (neu chua co)
if not exist "%PYTHON_EXE%" (
    echo [1/3] Downloading Python 3.12 embed (~10MB)...
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_DIR%\python.zip' -UseBasicParsing } catch { exit 1 }"
    if errorlevel 1 (
        echo [LOI] Download Python fail. Vui long download thu cong va giai nen vao %PYTHON_DIR%
        pause
        exit /b 1
    )
    echo [2/3] Giai nen Python...
    powershell -NoProfile -Command "Expand-Archive -Path '%PYTHON_DIR%\python.zip' -DestinationPath '%PYTHON_DIR%' -Force; Remove-Item '%PYTHON_DIR%\python.zip'"
    echo [OK] Da cai Python
) else (
    echo [1/3] Python da co san
)

REM 3. Cai pyzk + cac thu vien can thiet
echo [3/3] Cai dat pyzk...
"%PYTHON_EXE%" -m pip install --no-warn-script-location zk==0.9
if errorlevel 1 (
    echo [LOI] Cai pyzk fail. Vui long chay: %PYTHON_EXE% -m pip install zk==0.9
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo [OK] Setup hoan tat!
echo   Python: %PYTHON_EXE%
echo   Thu vien: pyzk (zktest), future, libfuturize
echo.
echo Bay gio co the chay: start_all.bat
echo ======================================================================
pause
