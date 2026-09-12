#!/usr/bin/env python3
"""Re-upload APK to release v1.5.7+10 (clean version, single file part).

Bug in previous version: extra form fields (name, label) caused GitHub to
store the WHOLE multipart body (526 bytes of headers + the file).
Fix: single file part only. Filename via query param, NOT form field.
"""
import os
import subprocess
import json
import sys
import time
import http.client

REPO = "drkrongnem86-del/AttendanceSuite"
TAG = "v1.5.7+10"
APK_PATH = "apk/attendance-mobile-arm64-1.5.7+10.apk"


def get_github_token():
    """Get token from git credential helper (GitHub Desktop)."""
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
    raise RuntimeError(f"Could not parse token. Output:\n{out}")


def api_request(method, path, token):
    """Make GitHub API request via http.client."""
    conn = http.client.HTTPSConnection("api.github.com", timeout=60)
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    conn.request(method, path, body=None, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, json.loads(data) if data else {}


def delete_asset(asset_id, token):
    """Delete a release asset."""
    conn = http.client.HTTPSConnection("api.github.com", timeout=30)
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
    }
    conn.request("DELETE", f"/repos/{REPO}/releases/assets/{asset_id}", headers=headers)
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status


def upload_apk(release_id, token):
    """Upload APK as release asset. ONLY the file part - no extra form fields.

    Filename is in query string, NOT in body.
    """
    if not os.path.exists(APK_PATH):
        print(f"ERROR: APK not found at {APK_PATH}")
        sys.exit(1)

    apk_size = os.path.getsize(APK_PATH)
    apk_name = os.path.basename(APK_PATH)
    print(f"Uploading {apk_name} ({apk_size / 1024 / 1024:.2f} MB)...")

    with open(APK_PATH, "rb") as f:
        apk_data = f.read()

    boundary = "----AttendanceSuiteFileBoundary8NXQmkTrZu0gW"

    # ONLY the file part - no extra form fields
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: attachment; filename="{apk_name}"\r\n'
        f"Content-Type: application/vnd.android.package-archive\r\n\r\n"
    ).encode("utf-8") + apk_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    print(f"Body size: {len(body) / 1024 / 1024:.2f} MB (overhead: {len(body) - len(apk_data)} bytes)")

    # Use uploads.github.com with 600s timeout
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

    # 1) Get release + delete existing APK assets
    print(f"[1/4] Get release {TAG}...")
    status, release = api_request("GET", f"/repos/{REPO}/releases/tags/{TAG}", token)
    if status != 200:
        print(f"ERROR: status {status}")
        sys.exit(1)
    release_id = release["id"]
    print(f"Release id: {release_id}")

    print(f"\n[2/4] Delete existing APK assets...")
    deleted = 0
    for asset in release.get("assets", []):
        if asset["name"].endswith(".apk"):
            print(f"  Deleting {asset['name']} (id {asset['id']})...")
            dstatus = delete_asset(asset["id"], token)
            print(f"  Status: {dstatus}")
            if dstatus < 300:
                deleted += 1
    print(f"Deleted {deleted} APK(s)")

    print(f"\n[3/4] Wait 5s for GitHub to process deletes...")
    time.sleep(5)

    print(f"\n[4/4] Upload clean APK...")
    upload_apk(release_id, token)

    print()
    print("=" * 60)
    print(f"DONE: https://github.com/{REPO}/releases/tag/{TAG}")
    print("=" * 60)


if __name__ == "__main__":
    main()
