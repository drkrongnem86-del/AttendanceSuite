"""launcher.py - Khởi động attendance_web.py trong background thread cho Android

Khi Android app khởi động, MainActivity.kt sẽ gọi start_server() qua Chaquopy.
attendance_web.main() sẽ bind 0.0.0.0:8080 và serve HTML UI cho WebView.
"""

import os
import sys
import threading
import traceback


def start_server(port=8080):
    """Khởi động attendance_web HTTP server trong daemon thread.
    Trả về True nếu start thành công, False nếu lỗi.
    attendance_web.main() bind cứng port 8080 (xem trong attendance_web.py line 2636).
    """
    try:
        # Chaquopy bundle Python files từ src/main/python/, nên import trực tiếp được
        import attendance_web
    except ImportError as e:
        print(f"[launcher.py] FAILED to import attendance_web: {e}")
        traceback.print_exc()
        return False

    def _serve():
        try:
            print(f"[launcher.py] Starting attendance_web on port {port}...")
            attendance_web.main()
        except Exception as e:
            print(f"[launcher.py] Server crashed: {e}")
            traceback.print_exc()

    # Chạy server trong daemon thread để không block UI thread
    t = threading.Thread(target=_serve, daemon=True, name="attendance-web-server")
    t.start()
    print(f"[launcher.py] Server thread started: {t.name}")
    return True


if __name__ == '__main__':
    # Khi launch trực tiếp từ Android (qua Chaquopy), MainActivity sẽ gọi start_server()
    print("[launcher.py] Direct launch - calling start_server()")
    start_server()

