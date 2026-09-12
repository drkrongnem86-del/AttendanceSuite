#!/usr/bin/env python3
"""Create GitHub Release v1.5.7+10 + upload APK to drkrongnem86-del/AttendanceSuite.

Uses http.client.HTTPSConnection (NOT urllib) for the 19MB upload to avoid timeout.
Token from GitHub Desktop via git credential helper.
"""
import os
import subprocess
import json
import sys
import time
import http.client
import urllib.request
import urllib.error

REPO = "drkrongnem86-del/AttendanceSuite"
TAG = "v1.5.7+10"
APK_PATH = "apk/attendance-mobile-arm64-1.5.7+10.apk"
RELEASE_NAME = "v1.5.7+10 - VPN integration"
RELEASE_BODY = """# v1.5.7+10 - VPN integration + refactored architecture

## What's new

### VPN (openvpn_flutter)
- Tap "VPN Bệnh viện" to connect to BV Ninh Thuận OpenVPN server
- 2 profiles available: `nemk_vpn.ovpn` + `his_vpn.ovpn` (in assets/vpn/)
- Auto-disconnect after 5 min app paused
- Credentials loaded via XOR-encoded `Credentials.vpnNemkPassword` (no plaintext in APK)

### Project structure
- `lib/core/` (security + services)
- `lib/presentation/screens/` (UI)
- `lib/main.dart` imports `vpn_screen.dart` + `vpn_benh_vien_service.dart`

### Permissions
- `BIND_VPN_SERVICE`
- `FOREGROUND_SERVICE`
- `POST_NOTIFICATIONS`
- `android:extractNativeLibs="true"` (required by openvpn_flutter)

### Build
- Stack: AGP 8.11.1 + Kotlin 2.2.20 + Gradle 8.14 + JDK 17 full + Flutter 3.41.7
- Target: arm64-v8a only (Samsung A17)
- Application ID: com.bvdk.attendance_mobile

## Verify
```powershell
Get-FileHash -Path "apk/attendance-mobile-arm64-1.5.7+10.apk" -Algorithm SHA256
```
Expected SHA-256: `7897931FB0375C0515CA3C8CC32F923321BD8CC6801D27497F1FCDE7DC6D653B`

## Auto-update
v1.3.3+7 (and later) on phones will detect this release automatically within 24h
(check `lib/updater.dart`).
"""


def get_github_token():
    """Get token from git credential helper (GitHub Desktop saves it)."""
    p = subprocess.Popen(
        ["git", "credential", "fill"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, _ = p.communicate("protocol=https\nhost=github.com\n\n", timeout=10)
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"Could not parse token from git credential helper. Output:\n{out}")


def api_request(method, path, token, body=None, content_type="application/json"):
    """Make GitHub API request via http.client (urllib times out on large POST)."""
    conn = http.client.HTTPSConnection("api.github.com", timeout=60)
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if body is not None and content_type == "application/json":
        body = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, json.loads(data) if data else {}


def upload_apk(release_id, token):
    """Upload APK as release asset. Uses longer timeout for 19MB upload."""
    if not os.path.exists(APK_PATH):
        print(f"ERROR: APK not found at {APK_PATH}")
        sys.exit(1)

    apk_size = os.path.getsize(APK_PATH)
    apk_name = os.path.basename(APK_PATH)
    print(f"Uploading {apk_name} ({apk_size / 1024 / 1024:.2f} MB)...")

    boundary = "----AttendanceSuiteFormBoundary7MA4YWxkTrZu0gW"

    # Build multipart body
    with open(APK_PATH, "rb") as f:
        apk_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="name"\r\n\r\n'
        f"{apk_name}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="label"\r\n\r\n'
        f"{apk_name}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="data"; filename="{apk_name}"\r\n'
        f"Content-Type: application/vnd.android.package-archive\r\n\r\n"
    ).encode("utf-8") + apk_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    print(f"Body size: {len(body) / 1024 / 1024:.2f} MB")

    # Use uploads.github.com with 600s timeout (urllib times out at default)
    conn = http.client.HTTPSConnection("uploads.github.com", timeout=600)
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
    }
    path = f"/repos/{REPO}/releases/{release_id}/assets?name={apk_name}"

    start = time.time()
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    elapsed = time.time() - start
    conn.close()

    print(f"Upload took {elapsed:.1f}s, status: {resp.status}")
    if resp.status >= 300:
        print(f"ERROR response: {data.decode('utf-8', errors='replace')[:500]}")
        sys.exit(1)
    print("Upload OK")


def main():
    token = get_github_token()
    print(f"Got token (length {len(token)})\n")

    # 1) Check if release already exists
    print(f"[1/3] Check if release for {TAG} exists...")
    status, _ = api_request("GET", f"/repos/{REPO}/releases/tags/{TAG}", token)
    if status == 200:
        print(f"Release {TAG} already exists - reusing")
        # Get release id
        status, release = api_request("GET", f"/repos/{REPO}/releases/tags/{TAG}", token)
        release_id = release["id"]
        # Check existing assets
        for asset in release.get("assets", []):
            if asset["name"] == os.path.basename(APK_PATH):
                print(f"APK already uploaded (asset id {asset['id']}) - deleting first")
                api_request("DELETE", f"/repos/{REPO}/releases/assets/{asset['id']}", token)
    else:
        # 2) Create release
        print(f"[2/3] Creating release {TAG}...")
        status, release = api_request(
            "POST",
            f"/repos/{REPO}/releases",
            token,
            body={
                "tag_name": TAG,
                "target_commitish": "release/v1.5.7+10",
                "name": RELEASE_NAME,
                "body": RELEASE_BODY,
                "draft": False,
                "prerelease": False,
            },
        )
        if status >= 300:
            print(f"ERROR creating release: {status}")
            print(json.dumps(release, indent=2))
            sys.exit(1)
        release_id = release["id"]
        print(f"Release created (id {release_id})")
        print(f"URL: {release['html_url']}")

    # 3) Upload APK
    print(f"[3/3] Uploading APK...")
    upload_apk(release_id, token)

    print()
    print("=" * 60)
    print(f"DONE: https://github.com/{REPO}/releases/tag/{TAG}")
    print("=" * 60)


if __name__ == "__main__":
    main()
