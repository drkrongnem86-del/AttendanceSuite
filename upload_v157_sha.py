#!/usr/bin/env python3
"""Update apk-sha256.txt in v1.5.7+10 release with correct SHA + filename."""
import subprocess
import http.client
import json
import sys

REPO = "drkrongnem86-del/AttendanceSuite"
TAG = "v1.5.7+10"
APK_SHA = "7897931FB0375C0515CA3C8CC32F923321BD8CC6801D27497F1FCDE7DC6D653B"
APK_NAME = "attendance-mobile-arm64-1.5.7+10.apk"


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


def github_get(path, token):
    conn = http.client.HTTPSConnection("api.github.com", timeout=30)
    conn.request("GET", path, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
    })
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    if resp.status >= 300:
        raise RuntimeError(f"GET {path} -> {resp.status}: {raw[:300]}")
    return json.loads(raw) if raw else {}


def github_delete(path, token):
    conn = http.client.HTTPSConnection("api.github.com", timeout=30)
    conn.request("DELETE", path, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-upload",
    })
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status


def upload_octet_stream(path, body_bytes, token):
    conn = http.client.HTTPSConnection("uploads.github.com", timeout=30)
    conn.request(
        "POST",
        path,
        body=body_bytes,
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/octet-stream",
            "Accept": "application/vnd.github+json",
            "User-Agent": "AttendanceSuite-upload",
        },
    )
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    if resp.status >= 300:
        raise RuntimeError(f"POST {path} -> {resp.status}: {raw[:300]}")
    return resp.status, raw


def main():
    token = get_github_token()
    print(f"Got token (length {len(token)})")

    # Get release
    release = github_get(f"/repos/{REPO}/releases/tags/{TAG}", token)
    release_id = release["id"]
    print(f"Release id: {release_id}")

    # Delete old apk-sha256.txt
    for asset in release.get("assets", []):
        if asset["name"] == "apk-sha256.txt":
            print(f"Deleting old apk-sha256.txt (id {asset['id']})")
            dstatus = github_delete(f"/repos/{REPO}/releases/assets/{asset['id']}", token)
            print(f"  Status: {dstatus}")

    # Upload new apk-sha256.txt (raw bytes)
    content = f"{APK_SHA}  {APK_NAME}\n"
    print(f"Uploading new apk-sha256.txt: {content.strip()}")
    status, _ = upload_octet_stream(
        f"/repos/{REPO}/releases/{release_id}/assets?name=apk-sha256.txt",
        content.encode("utf-8"),
        token,
    )
    print(f"Upload status: {status}")
    print("DONE")


if __name__ == "__main__":
    main()
