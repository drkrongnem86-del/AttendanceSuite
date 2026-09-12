"""Check if GitHub stored the multipart headers in the APK file.

Reconstruct the multipart body and check its SHA-256 against the downloaded one.
"""
import os
import hashlib

APK_PATH = "apk/attendance-mobile-arm64-1.5.7+10.apk"
boundary = "----AttendanceSuiteFormBoundary7MA4YWxkTrZu0gW"
apk_name = os.path.basename(APK_PATH)

with open(APK_PATH, "rb") as f:
    apk_data = f.read()

# Build multipart body the same way as upload script
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

print(f"Local APK size  : {len(apk_data)} bytes")
print(f"Multipart size  : {len(body)} bytes")
print(f"Header overhead : {len(body) - len(apk_data)} bytes")
print()

print(f"Local APK SHA-256     : {hashlib.sha256(apk_data).hexdigest()}")
print(f"Multipart body SHA-256: {hashlib.sha256(body).hexdigest()}")
print(f"GitHub stored SHA-256 : A53EE3719CA9CF480DA42C0E69A5642524FB4C77BE7D247A4771F83D7AFA1691")
print(f"Expected SHA-256      : 7897931FB0375C0515CA3C8CC32F923321BD8CC6801D27497F1FCDE7DC6D653B")
print()

# Save the multipart body for inspection
out = "verify_multipart.bin"
with open(out, "wb") as f:
    f.write(body)
print(f"Saved multipart body to {out} ({len(body)} bytes)")
