"""Upload v1.9.0+12 APK + EXE to GitHub Release."""
import os, sys, subprocess, json, time, http.client

REPO = "drkrongnem86-del/AttendanceSuite"
TAG = "v1.9.0+12"
NAME = "AttendanceSuite v1.9.0 - Delta +1 THẬT (BS-confirmed) + Real ATTLOG tracking"

APK_PATH = "apk/attendance-mobile-arm64-1.9.0+12.apk"
SHA_PATH = "apk/apk-sha256.txt"
EXE_PATH = "apk/AttendanceSuite-v1.9.0.exe"


def get_github_token():
    p = subprocess.Popen(
        ["git", "credential", "fill"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    out, _ = p.communicate("protocol=https\nhost=github.com\n\n", timeout=10)
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"Could not parse token. Output:\n{out}")


def api_request(method, path, token, body=None, content_type=None):
    conn = http.client.HTTPSConnection("api.github.com", timeout=60)
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
    }
    if body is not None and content_type:
        body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        headers["Content-Type"] = content_type
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    return resp.status, json.loads(data) if data else {}


def upload_asset(release_id, token, file_path, content_type="application/octet-stream"):
    name = os.path.basename(file_path)
    size = os.path.getsize(file_path)
    print(f"Uploading {name} ({size / 1024 / 1024:.2f} MB)...")
    with open(file_path, "rb") as f:
        data = f.read()

    conn = http.client.HTTPSConnection("uploads.github.com", timeout=600)
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": content_type,
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
    }
    path = f"/repos/{REPO}/releases/{release_id}/assets?name={name}"

    start = time.time()
    conn.request("POST", path, body=data, headers=headers)
    resp = conn.getresponse()
    rdata = resp.read()
    print(f"  Status: {resp.status} in {time.time() - start:.1f}s")
    if resp.status >= 400:
        print(f"  Error: {rdata[:500]}")
        return None
    return json.loads(rdata)


def main():
    token = get_github_token()
    print(f"Token OK: {token[:8]}...")

    # Get or create release
    status, existing = api_request("GET", f"/repos/{REPO}/releases/tags/{TAG}", token)
    if status == 200:
        release_id = existing["id"]
        print(f"Found existing release: id={release_id}")
        # Update release name + body to latest
        release_body = {
            "tag_name": TAG,
            "target_commitish": "main",
            "name": NAME,
            "body": "## v1.9.0+12 - Delta +1 THẬT (BS-confirmed) + Real ATTLOG\n\n"
                    "- **Delta +1 THẬT (BS-confirmed)**: Hiển thị rõ +1 là REAL (BS verify qua pyzk, không fake)\n"
                    "- **Delta hệ thống vs Delta máy thật**: 2 chỉ số riêng biệt\n"
                    "- **Real Delta**: ATTLOG baseline từ máy thật (không fake)\n"
                    "- **BYPASS FW 6.60**: BS verify OK = ghi nhận chấm công\n"
                    "- **Filter reachable devices**: Parallel TCP probe 24 thiết bị\n"
                    "- **Auto-poll ATTLOG**: 5s/lần × 24 lần sau verify\n"
                    "- **Log viewer**: Filter theo IP, stats (Total/Today/IN/OUT/BS-confirmed), auto-refresh toggle\n"
                    "- **PIN not found hints**: Sample 8 NV có password + admin hint\n\n"
                    "### Workflow verified end-to-end:\n"
                    "1. Mở http://localhost:8080/punch\n"
                    "2. Chọn máy (May 3 / May 20) + PIN + password → CHECK-IN\n"
                    "3. Verify OK → log vào manual_punches.csv + Delta hệ thống +1 (THẬT) + Done!\n\n"
                    "### Tested trên thiết bị thật:\n"
                    "- May 3 (172.16.0.214): PIN 1383 (THUYNTT4) pwd='1' → 200 bypass=true, baseline 99335\n"
                    "- May 20 (172.16.8.139): PIN 1 (admin) pwd='891401' → 200 bypass=true\n"
                    "- ATTLOG trên máy KHÔNG tăng sau verify (FW 6.60 chặn remote write) - Delta máy thật = 0\n"
                    "- Delta hệ thống +1 = REAL vì BS-confirmed (record đã ghi vào CSV)\n\n"
                    "### Files:\n"
                    "- `attendance-mobile-arm64-1.9.0+12.apk` - 18.4 MB\n"
                    "- `AttendanceSuite-v1.9.0.exe` - 6.5 MB (PyInstaller onedir)\n"
                    "- `apk-sha256.txt` - SHA256 hashes\n",
        }
        api_request("PATCH", f"/repos/{REPO}/releases/{release_id}", token, release_body, "application/json")
    else:
        # Create release
        release_body = {
            "tag_name": TAG,
            "target_commitish": "main",
            "name": NAME,
            "body": "## v1.9.0+12\n\n"
                    "- **Delta +1 THẬT (BS-confirmed)**: Hiển thị rõ +1 là REAL (BS verify qua pyzk, không fake)\n"
                    "- **Delta hệ thống vs Delta máy thật**: 2 chỉ số riêng biệt\n"
                    "- **Real Delta**: ATTLOG baseline từ máy thật (không fake)\n"
                    "- **BYPASS FW 6.60**: BS verify OK = ghi nhận chấm công\n"
                    "- **Filter reachable devices**: Parallel TCP probe 24 thiết bị\n"
                    "- **Auto-poll ATTLOG**: 5s/lần × 24 lần sau verify\n"
                    "- **Log viewer**: Filter theo IP, stats (Total/Today/IN/OUT/BS-confirmed), auto-refresh toggle\n"
                    "- **PIN not found hints**: Sample 8 NV có password + admin hint\n\n"
                    "Tested:\n"
                    "- May 3 PIN 1383 / pass 1 → 200 bypass=true\n"
                    "- May 20 PIN 1 / pass 891401 → 200 bypass=true\n"
                    "- Real baseline 99334 (May 3) / 7131 (May 20)",
            "draft": False,
            "prerelease": False,
        }
        status, release = api_request("POST", "/repos/" + REPO + "/releases", token, release_body, "application/json")
        if status >= 400:
            print(f"Create release failed: {release}")
            sys.exit(1)
        release_id = release["id"]
        print(f"Created release: id={release_id}")

    # Upload APK
    if os.path.exists(APK_PATH):
        upload_asset(release_id, token, APK_PATH)
    if os.path.exists(SHA_PATH):
        upload_asset(release_id, token, SHA_PATH, content_type="text/plain")
    if os.path.exists(EXE_PATH):
        upload_asset(release_id, token, EXE_PATH)

    print("DONE")


if __name__ == "__main__":
    main()
