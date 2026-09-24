# launcher.py - Khoi dong attendance_web.py trong background thread cho Android
# v2.6.3: Them diagnostic logging (ghi vao file de doc qua FileProvider neu can)

import os
import sys
import threading
import traceback
import time


def _log(msg):
    """Log ra stderr + ghi file (de debug khi Python crash khoi dong)."""
    line = f"[launcher.py] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        # Ghi log file trong app private dir (/data/data/com.bvdk.attendance_mobile/files/)
        # De debug neu can, co the doc qua adb run-as
        log_dir = os.path.join(os.path.expanduser("~"), "..", "..", "..", "data", "data", "com.bvdk.attendance_mobile", "files")
        if os.path.exists(log_dir):
            log_file = os.path.join(log_dir, "python_startup.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {line}\n")
    except Exception:
        pass


def start_server(port=8080):
    """Khoi dong attendance_web HTTP server trong daemon thread.
    Tra ve True neu start thanh cong, False neu loi.
    """
    _log(f"start_server(port={port}) - Python {sys.version_info[:3]}")
    _log(f"SCRIPT_DIR = {os.path.dirname(os.path.abspath(__file__))}")

    try:
        import attendance_web
        _log("attendance_web imported OK")
    except ImportError as e:
        _log(f"FAILED to import attendance_web: {e}")
        _log(traceback.format_exc())
        return False
    except Exception as e:
        _log(f"Error importing attendance_web: {e}")
        _log(traceback.format_exc())
        return False

    def _serve():
        try:
            _log(f"Calling attendance_web.main() (will bind 0.0.0.0:{port})...")
            attendance_web.main()
        except Exception as e:
            _log(f"Server crashed: {e}")
            _log(traceback.format_exc())

    t = threading.Thread(target=_serve, daemon=True, name="attendance-web-server")
    t.start()
    _log(f"Server thread started: {t.name}, alive={t.is_alive()}")
    # Cho server 0.5s de bind port truoc khi return
    time.sleep(0.5)
    return True


if __name__ == "__main__":
    # Khi launch truc tiep tu Android (qua Chaquopy), MainActivity se goi start_server()
    start_server()
