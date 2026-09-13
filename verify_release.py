"""Verify v1.9.0+12 GitHub Release assets."""
import subprocess, json, http.client

out = subprocess.check_output(
    ["git", "credential", "fill"],
    input=b"protocol=https\nhost=github.com\n\n",
    timeout=10,
)
token = ""
for line in out.decode().splitlines():
    if line.startswith("password="):
        token = line.split("=", 1)[1].strip()
        break

conn = http.client.HTTPSConnection("api.github.com", timeout=30)
conn.request(
    "GET",
    "/repos/drkrongnem86-del/AttendanceSuite/releases/tags/v1.9.0%2B12",
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "AttendanceSuite-verify",
    },
)
resp = conn.getresponse()
raw = resp.read()
print(f"Status: {resp.status}")
print(f"Raw response: {raw[:500]!r}")
if resp.status != 200:
    print("FAILED - check response above")
    exit(1)
data = json.loads(raw)
import sys
sys.stdout.reconfigure(encoding='utf-8')
print(f"Release: {data['name']}")
print(f"Body preview:")
print(data["body"][:600])
print()
print(f"Assets ({len(data['assets'])}):")
for a in data["assets"]:
    print(f"  - {a['name']} ({a['size']/1024/1024:.2f} MB)")
    print(f"    Download: {a['browser_download_url']}")
print()
print(f"Release URL: {data['html_url']}")
