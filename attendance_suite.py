"""AttendanceSuite Launcher - main entry point.

Starts all 3 services (Viewer, Simulator, Remote Punch) and provides
a simple console UI for managing them. Designed to be packaged as
a single .exe via PyInstaller.
"""
import os
import sys
import time
import threading
import subprocess
import webbrowser
from pathlib import Path


# Khi chạy từ PyInstaller EXE:
#   - sys.executable = path toi EXE
#   - sys._MEIPASS = temp folder chua bundled Python + scripts
# Khi chạy từ .py:
#   - __file__ = path toi script
#   - Scripts nam cung folder
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = Path(sys.executable).parent.resolve()  # Thu muc chua EXE
    BUNDLE_DIR = Path(sys._MEIPASS)                    # Noi chua bundled files
    # Trong onedir mode, services files se o SCRIPT_DIR (vi chung la data files)
    # Trong onefile mode, services files o BUNDLE_DIR (sys._MEIPASS)
    # Ta copy tu bundle ra SCRIPT_DIR neu can
    import shutil
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    for f in ['attendance_web.py', 'punch_simulator.py', 'remote_punch_service.py',
              'config.json', 'devices.csv', 'launcher.html']:
        src = BUNDLE_DIR / f
        dst = SCRIPT_DIR / f
        if src.exists() and not dst.exists():
            shutil.copy2(str(src), str(dst))
    PYTHON_EXE = sys.executable
else:
    SCRIPT_DIR = Path(__file__).parent.resolve()
    PYTHON_EXE = sys.executable

SERVICE_DIR = SCRIPT_DIR

SERVICES = [
    {
        'name': 'Viewer',
        'script': 'attendance_web.py',
        'port': 8080,
        'desc': 'Log Viewer + Reports + Live Status',
    },
    {
        'name': 'Simulator',
        'script': 'punch_simulator.py',
        'port': 8081,
        'desc': 'X628 PRO Simulator (UI + manual punch)',
    },
    {
        'name': 'Remote',
        'script': 'remote_punch_service.py',
        'port': 8082,
        'desc': 'Remote Punch Service (Basic Auth + sync)',
    },
]


class ServiceManager:
    def __init__(self):
        self.processes = {}  # name -> subprocess.Popen
        self.log_handles = {}  # name -> file handle
        self.log_dir = SCRIPT_DIR / 'logs'
        self.log_dir.mkdir(exist_ok=True)
        self.python_exe = self._find_python()

    def _find_python(self):
        """Tim python.exe de chay services."""
        import shutil
        for c in [
            SCRIPT_DIR / 'python' / 'python.exe',
            SCRIPT_DIR / 'python.exe',
            SCRIPT_DIR / 'AttendanceSuite_Portable' / 'python' / 'python.exe',
            SCRIPT_DIR.parent / 'AttendanceSuite_Portable' / 'python' / 'python.exe',
        ]:
            if c.exists():
                return str(c)
        py = shutil.which('python') or shutil.which('python3') or shutil.which('py')
        if py:
            return py
        return 'python'

    def start_all(self):
        print('=' * 70)
        print('  AttendanceSuite Launcher v1.4.0 - BVDK Ninh Thuan')
        print('=' * 70)
        for svc in SERVICES:
            self.start(svc['name'])
            time.sleep(1.5)  # Wait between starts
        print()
        print('All services started. Available URLs:')
        print('  - Log Viewer:       http://localhost:8080/')
        print('  - Simulator:        http://localhost:8081/')
        print('  - Remote Punch:     http://localhost:8082/  (admin/bvdk2026)')
        print('  - MERGE Workflow:   http://localhost:8080/merge')
        print()
        time.sleep(2)
        try:
            webbrowser.open('http://localhost:8080/launcher.html')
        except Exception:
            pass
        print('Press Ctrl+C to stop all services.')
        print('Services running in this window. Close this window to stop.')

    def start(self, name):
        svc = next((s for s in SERVICES if s['name'] == name), None)
        if not svc:
            print(f'Unknown service: {name}')
            return
        if name in self.processes and self.processes[name].poll() is None:
            print(f'[{name}] already running')
            return

        script_path = SCRIPT_DIR / svc['script']
        if not script_path.exists():
            print(f'[{name}] ERROR: {script_path} not found')
            return

        log_path = self.log_dir / f'{name.lower()}.out.log'
        err_path = self.log_dir / f'{name.lower()}.err.log'
        log_file = open(log_path, 'a', encoding='utf-8')
        err_file = open(err_path, 'a', encoding='utf-8')
        log_file.write(f'\n=== Started at {time.strftime("%Y-%m-%d %H:%M:%S")} ===\n')
        log_file.flush()

        try:
            proc = subprocess.Popen(
                [self.python_exe, str(script_path)],
                stdout=log_file,
                stderr=err_file,
                cwd=str(SCRIPT_DIR),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
            self.processes[name] = proc
            self.log_handles[name] = (log_file, err_file)
            print(f'[{name}] Started (PID={proc.pid}, port={svc["port"]}, log={log_path})')
        except Exception as e:
            print(f'[{name}] Failed to start: {e}')

    def stop_all(self):
        print('\nStopping all services...')
        for name in list(self.processes.keys()):
            self.stop(name)
        print('All services stopped.')

    def stop(self, name):
        if name not in self.processes:
            return
        proc = self.processes[name]
        if proc.poll() is not None:
            return  # Already stopped
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f'[{name}] Stopped')
        except Exception as e:
            print(f'[{name}] Error stopping: {e}')
        # Close log handles
        for h in self.log_handles.get(name, []):
            try:
                h.close()
            except Exception:
                pass

    def status(self):
        print('\n=== Service Status ===')
        for svc in SERVICES:
            name = svc['name']
            proc = self.processes.get(name)
            if proc and proc.poll() is None:
                print(f'  [{name}] RUNNING (PID={proc.pid}, port={svc["port"]})')
            else:
                print(f'  [{name}] STOPPED')
        print()

    def open_browser(self, port=8080):
        url = f'http://localhost:{port}/'
        try:
            webbrowser.open(url)
            print(f'Opened browser: {url}')
        except Exception as e:
            print(f'Failed to open browser: {e}')


def signal_handler(sig, frame):
    print('\nCtrl+C detected. Stopping...')
    manager.stop_all()
    sys.exit(0)


def main():
    import signal
    signal.signal(signal.SIGINT, signal_handler)

    global manager
    manager = ServiceManager()

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == 'start':
            manager.start_all()
            try:
                # Keep main thread alive
                while True:
                    time.sleep(60)
                    manager.status()
            except KeyboardInterrupt:
                manager.stop_all()
        elif cmd == 'stop':
            manager.stop_all()
        elif cmd == 'status':
            manager.status()
        elif cmd == 'open':
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
            manager.open_browser(port)
        else:
            print(f'Unknown command: {cmd}')
            print('Usage: attendance_suite.py [start|stop|status|open [port]]')
    else:
        # Interactive mode (default)
        manager.start_all()
        try:
            while True:
                time.sleep(60)
                manager.status()
        except KeyboardInterrupt:
            manager.stop_all()


if __name__ == '__main__':
    main()
