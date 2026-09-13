@echo off
REM zk_quickstart.bat - Quick start cho BS test PIN+password workflow
REM Run từ D:\chamcong\tools\

echo ======================================================================
echo   ZK PIN+PASSWORD Quick Start - BVĐK Ninh Thuận
echo   Ngày: %DATE% %TIME%
echo ======================================================================
echo.

set PYTHONIOENCODING=utf-8

echo [1/5] Scan tất cả 24 máy ZK - tìm máy có NV với password...
echo ----------------------------------------------------------------------
python zk_security_scan.py
echo.

echo [2/5] Test verify PIN+password trên máy 172.16.0.200 (đã có Verify_Type=0)...
echo ----------------------------------------------------------------------
python zk_pin_password.py 172.16.0.200 1383 1
echo.

echo [3/5] Test verify Admin PIN trên máy mới 172.16.254.202...
echo ----------------------------------------------------------------------
python zk_pin_password.py 172.16.254.202 1 891401
echo.

echo [4/5] List users có password trên máy 172.16.254.202...
echo ----------------------------------------------------------------------
python zk_pin_password.py 172.16.254.202 --list-password-users
echo.

echo [5/5] Hướng dẫn tiếp theo:
echo ----------------------------------------------------------------------
echo   1. BS đứng trước máy ZK, test PIN+password thực tế
echo   2. Nếu work → áp dụng cho tất cả 22 máy có NV có password
echo   3. Bulk set password cho users chưa có:
echo        python zk_pin_password.py 172.16.0.200 --bulk-set 1
echo.
echo ======================================================================
echo   DONE - Xem kết quả ở trên
echo ======================================================================
pause
