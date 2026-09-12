#!/usr/bin/env python3
"""Re-upload APK using raw bytes (no multipart wrapper).

Trying application/octet-stream - GitHub should just store the bytes as-is.
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
    conn.close()
    return resp.status, json.loads(data) if data else {}


def delete_asset(asset_id, token):
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


def upload_apk_raw(release_id, token):
    """Upload APK as raw bytes - no multipart wrapper.

    This is the simpler approach: POST raw APK bytes with Content-Type set.
    GitHub's release asset API supports this.
    """
    apk_size = os.path.getsize(APK_PATH)
    apk_name = os.path.basename(APK_PATH)
    print(f"Uploading {apk_name} ({apk_size / 1024 / 1024:.2f} MB) as RAW BYTES...")

    with open(APK_PATH, "rb") as f:
        apk_data = f.read()

    print(f"Sending {len(apk_data)} raw bytes")

    # Raw upload - use uploads.github.com but with octet-stream
    conn = http.client.HTTPSConnection("uploads.github.com", timeout=600)
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/octet-stream",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
    }
    path = f"/repos/{REPO}/releases/{release_id}/assets?name={apk_name}"

    start = time.time()
    conn.request("POST", path, body=apk_data, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    elapsed = time.time() - start
    conn.close()

    print(f"Upload took {elapsed:.1f}s, status: {resp.status}")
    if resp.status >= 300:
        print(f"ERROR response: {data.decode('utf-8', errors='replace')[:1000]}")
        sys.exit(1)
    print("Upload OK")


def main():
    token = get_github_token()
    print(f"Got token (length {len(token)})\n")

    print(f"[1/3] Get release {TAG}...")
    status, release = api_request("GET", f"/repos/{REPO}/releases/tags/{TAG}", token)
    if status != 200:
        print(f"ERROR: status {status}")
        sys.exit(1)
    release_id = release["id"]
    print(f"Release id: {release_id}")

    print(f"\n[2/3] Delete existing APK assets...")
    for asset in release.get("assets", []):
        if asset["name"].endswith(".apk"):
            print(f"  Deleting {asset['name']} (id {asset['id']})...")
            dstatus = delete_asset(asset["id"], token)
            print(f"  Status: {dstatus}")
    print("Waiting 5s...")
    time.sleep(5)

    print(f"\n[3/3] Upload raw APK bytes...")
    upload_apk_raw(release_id, token)

    print()
    print("=" * 60)
    print(f"DONE: https://github.com/{REPO}/releases/tag/{TAG}")
    print("=" * 60)


if __name__ == "__main__":
    main()
