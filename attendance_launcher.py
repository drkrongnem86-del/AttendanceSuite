#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AttendanceSuite v2.0.12 - Single-File Desktop Launcher
=====================================================
In-process threading launcher. No subprocess.Popen - eliminates port conflicts.
Single-click EXE -> native pywebview window opens.

(c) 2026 Dr. Nem - BVDK Ninh Thuan
"""
import sys, os, threading, time, socket, atexit, signal, traceback, importlib.util
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

VERSION = '2.0.13'
APP_NAME = 'AttendanceSuite'
COPYRIGHT = '(c) 2026 Dr. Nem - BVDK Ninh Thuan'

# Paths - handle PyInstaller frozen mode
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = sys._MEIPASS
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def is_port_in_use(port, host='127.0.0.1'):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def kill_port(port):
    """Force-kill anything listening on the given port (Windows)."""
    if sys.platform != 'win32':
        return
    try:
        out = subprocess.check_output(
            ['netstat', '-ano', '-p', 'tcp'],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode('ascii', errors='replace')
        for line in out.splitlines():
            if f':{port} ' in line and 'LISTENING' in line:
                pid = line.split()[-1]
                if pid.isdigit():
                    print(f'[Launcher] Killing PID {pid} on :{port}', flush=True)
                    subprocess.run(['taskkill', '/F', '/PID', pid],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1)
    except Exception as e:
        print(f'[Launcher] kill_port({port}) err: {e}', flush=True)


# Single-instance lock file
import subprocess
LOCK_FILE = os.path.join(os.environ.get('TEMP', '/tmp'), '_attendance_suite_v2.lock')
LOCK_FD = None

def acquire_single_instance():
    global LOCK_FD
    try:
        LOCK_FD = open(LOCK_FILE, 'w')
        LOCK_FD.write(str(os.getpid()))
        LOCK_FD.flush()
        try:
            import msvcrt
            msvcrt.locking(LOCK_FD.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            LOCK_FD.close()
            LOCK_FD = None
            return False
        return True
    except Exception:
        return False


def release_single_instance():
    global LOCK_FD
    try:
        if LOCK_FD: LOCK_FD.close()
        if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)
    except Exception:
        pass


def wait_port(host, port, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_port_in_use(port, host):
            return True
        time.sleep(0.3)
    return False


def run_server_thread(script_name, port, name):
    """Run a server script in a background thread (in-process, no subprocess)."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    if not os.path.exists(script_path):
        print(f'[Launcher] {name}: {script_name} not found at {script_path}', flush=True)
        return None
    def runner():
        try:
            # Switch sys.argv to script path so the script's __main__ block runs
            old_argv = sys.argv[:]
            sys.argv = [script_name]
            print(f'[Launcher] Starting {name} in-process from {script_path}...', flush=True)
            with open(script_path, 'r', encoding='utf-8') as f:
                code = f.read()
            exec(compile(code, script_path, 'exec'), {'__name__': '__main__', '__file__': script_path})
        except Exception as e:
            import traceback as tb
            print(f'[Launcher] {name} crashed: {e}', flush=True)
            tb.print_exc()
        finally:
            sys.argv = old_argv
    t = threading.Thread(target=runner, name=f'Server-{name}', daemon=True)
    t.start()
    return t


atexit.register(release_single_instance)


def main():
    print(f'=== {APP_NAME} v{VERSION} ===', flush=True)
    print(COPYRIGHT, flush=True)
    print(f'Script dir: {SCRIPT_DIR}', flush=True)
    print(f'Frozen: {getattr(sys, "frozen", False)}', flush=True)

    # Single-instance check
    if not acquire_single_instance():
        show_error('AttendanceSuite da dang chay',
                   'App da duoc khoi dong roi. Dong cua so cu hoac kiem tra task manager.')
        return 2

    # Pre-check ports - if old EXE left them, kill it
    for port in (8080, 8081):
        if is_port_in_use(port):
            print(f'[Launcher] Port {port} in use, killing old process...', flush=True)
            kill_port(port)
            time.sleep(2)
            if is_port_in_use(port):
                show_error(f'Port {port} dang bi chiem',
                           f'Khong the giai phong port {port}. Dong app khac hoac khoi dong lai Windows.')
                release_single_instance()
                return 3

    # Start both servers in background threads
    viewer_thread = run_server_thread('attendance_web.py', 8080, 'Viewer+ATTLOG')
    sim_thread = run_server_thread('punch_simulator.py', 8081, 'Simulator')

    if not viewer_thread:
        show_error('Khong the khoi dong Viewer', 'attendance_web.py not found')
        release_single_instance()
        return 4

    # Wait for both ports
    print('[Launcher] Waiting for servers...', flush=True)
    if not wait_port('127.0.0.1', 8080, timeout=20):
        show_error('Khong the khoi dong Viewer', 'attendance_web.py did not bind :8080 within 20s')
        release_single_instance()
        return 5
    print('[Launcher] Viewer ready on :8080', flush=True)
    if not wait_port('127.0.0.1', 8081, timeout=35):
        print('[Launcher] Simulator failed to start (timeout)', flush=True)
        # Continue anyway - Simulator is optional
    else:
        print('[Launcher] Simulator ready on :8081', flush=True)

    # Open pywebview window
    try:
        import webview
    except ImportError:
        show_error('pywebview khong cai dat', 'pip install pywebview')
        release_single_instance()
        return 6

    window = webview.create_window(
        f'{APP_NAME} v{VERSION} - BVĐK Ninh Thuận',
        url='http://localhost:8080/launcher.html',
        width=1280, height=800,
        min_size=(960, 640),
        resizable=True,
        confirm_close=False,
        text_select=True,
        background_color='#1a1a2e'
    )

    def on_closing():
        print('[Launcher] Window closing, killing servers...', flush=True)
        # Force-kill both ports (frees them immediately)
        for p in (8080, 8081):
            kill_port(p)
        release_single_instance()
        # Force exit all threads by exiting process
        os._exit(0)

    window.events.closing += on_closing
    try:
        webview.start()
    finally:
        print('[Launcher] webview ended', flush=True)
        for p in (8080, 8081):
            kill_port(p)
        release_single_instance()
        os._exit(0)


def show_error(title, msg):
    try:
        import webview
        html = f'''<!DOCTYPE html><html><body style="background:#1a1a2e;color:#ff8888;font-family:Segoe UI;padding:40px;">
        <h2>{title}</h2>
        <pre style="white-space:pre-wrap;color:#e0e0e0;">{msg}</pre>
        <p style="color:#888;">{COPYRIGHT}</p>
        </body></html>'''
        w = webview.create_window(title, html=html, width=600, height=300)
        webview.start()
    except Exception:
        print(f'ERROR: {title}\n{msg}', flush=True)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        try: input('Press Enter to close...')
        except: pass
        sys.exit(99)
