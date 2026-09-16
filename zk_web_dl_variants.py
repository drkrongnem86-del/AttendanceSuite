import requests
import urllib3
urllib3.disable_warnings()
import os

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
os.makedirs(OUT_DIR, exist_ok=True)

urls_to_try = [
    ('POST', 'http://172.16.254.202/form/DataApp?style=1', {}),
    ('POST_BODY_PIN', 'http://172.16.254.202/form/DataApp?style=1', {'PIN': '1', 'Password': 'admin'}),
    ('POST_BODY_SN', 'http://172.16.254.202/form/DataApp?style=1', {'SN': '3324224660202'}),
    ('POST_BODY_DOWNLOAD', 'http://172.16.254.202/form/DataApp?style=1', {'action': 'download'}),
    ('GET_AUTH_891401', 'http://admin:891401@172.16.254.202/form/DataApp?style=1', None),
    ('GET_AUTH_admin', 'http://admin:admin@172.16.254.202/form/DataApp?style=1', None),
    ('GET_AUTH_root', 'http://root:root@172.16.254.202/form/DataApp?style=1', None),
    # With Range header (try to get a specific portion)
    ('GET_RANGE', 'http://172.16.254.202/form/DataApp?style=1', None),
    # Different style values
    ('GET_STYLE0', 'http://172.16.254.202/form/DataApp?style=0', None),
    ('GET_STYLE2', 'http://172.16.254.202/form/DataApp?style=2', None),
    ('GET_STYLE5', 'http://172.16.254.202/form/DataApp?style=5', None),
]

for method, url, data in urls_to_try:
    print(method, url[:80])
    try:
        if method == 'POST_BODY_PIN':
            r = requests.post(url, data=data, timeout=30, verify=False)
        elif method == 'POST_BODY_SN':
            r = requests.post(url, data=data, timeout=30, verify=False)
        elif method == 'POST_BODY_DOWNLOAD':
            r = requests.post(url, data=data, timeout=30, verify=False)
        elif method.startswith('POST'):
            r = requests.post(url, timeout=30, verify=False)
        elif method == 'GET_RANGE':
            r = requests.get(url, timeout=30, verify=False, headers={'Range': 'bytes=0-100000'})
        elif method == 'GET_AUTH_891401':
            r = requests.get(url, timeout=30, verify=False)
        elif method == 'GET_AUTH_admin':
            r = requests.get(url, timeout=30, verify=False)
        elif method == 'GET_AUTH_root':
            r = requests.get(url, timeout=30, verify=False)
        else:
            r = requests.get(url, timeout=60, verify=False)

        print('  Status:', r.status_code, 'Size:', len(r.content), 'bytes')
        ct = r.headers.get('Content-Type', '?')
        cd = r.headers.get('Content-Disposition', '?')
        print('  CT:', ct)
        print('  CD:', cd)
        if 'attachment' in cd or len(r.content) > 1000:
            if 'filename=' in cd:
                fname = cd.split('filename=')[1].strip().strip('"').strip("'")
            else:
                fname = method + '.bin'
            out = os.path.join(OUT_DIR, method + '_' + fname)
            with open(out, 'wb') as f:
                f.write(r.content)
            print('  Saved:', out, '(', len(r.content), 'bytes )')
            if len(r.content) > 6495:
                print('  *** LARGER than previous (', len(r.content), 'vs 6495) ***')
            elif len(r.content) < 6495:
                print('  Different size from previous (', len(r.content), 'vs 6495)')
    except Exception as e:
        print('  Error:', type(e).__name__, str(e)[:100])
