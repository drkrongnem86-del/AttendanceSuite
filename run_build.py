"""Run Flutter APK build for new AttendanceSuite v1.5.7+10 source."""
import subprocess, os, sys, time

os.chdir(r'D:\chamcong\11\AttendanceSuite\attendance_mobile')

env = os.environ.copy()
env['JAVA_HOME'] = r'D:\chamcong\java_tmp\jdk-17.0.13+11'
env['PATH'] = env['JAVA_HOME'] + r'\bin;' + env['PATH']

log_path = r'D:\chamcong\11\AttendanceSuite\apk_build_v157.log'

with open(log_path, 'w', encoding='utf-8', buffering=1) as logf:
    logf.write(f"=== Build started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    logf.write(f"JAVA_HOME={env['JAVA_HOME']}\n")
    logf.write(f"cwd={os.getcwd()}\n\n")
    logf.flush()

    proc = subprocess.Popen(
        [r'C:\Users\Nem\flutter\bin\flutter.bat', 'build', 'apk', '--release',
         '--target-platform=android-arm64', '--android-skip-build-dependency-validation'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1
    )

    last_heartbeat = time.time()
    line_count = 0
    while True:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            if time.time() - last_heartbeat > 30:
                with open(log_path, 'a', encoding='utf-8') as hb:
                    hb.write(f"[heartbeat {time.strftime('%H:%M:%S')}] alive pid={proc.pid}\n")
                last_heartbeat = time.time()
            time.sleep(2)
            continue

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(line)
            f.flush()
        line_count += 1
        last_heartbeat = time.time()

    return_code = proc.wait()
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"\n=== Build finished at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        f.write(f"Return code: {return_code}\n")
        f.write(f"Total lines: {line_count}\n")

    print(f"Build done. rc={return_code}, lines={line_count}")
    print(f"Log: {log_path}")
    sys.exit(return_code)
