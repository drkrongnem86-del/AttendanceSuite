"""Probe device for restore UI endpoints"""
import requests

urls = [
    '/form/Device?act=11',
    '/form/Device?act=20',
    '/form/Device',
    '/form/Device?action=Restore',
    '/form/SystemMaintenance',
    '/form/Maintenance',
    '/form/Reboot',
    '/form/System',
    '/form/Setting',
    '/form/Restore',
    '/form/SaveFile',
    '/iWsService',
    '/form/iWsService',
    '/device.cgi',
    '/cgi-bin/Restore',
]

for url in urls:
    try:
        r = requests.get(f'http://172.16.254.202{url}', timeout=8)
        is_html = b'<' in r.content[:5]
        print(f'GET {url}: status={r.status_code}, len={len(r.content)}, html={is_html}')
        if r.status_code == 200 and is_html:
            import re
            actions = re.findall(rb'action="?([^\s"\'>]+)', r.content)
            inputs = re.findall(rb'<input[^>]*name="?([^\s"\'>]+)', r.content)
            forms = re.findall(rb'<form[^>]+>', r.content)
            print(f'  actions: {actions[:5]}')
            print(f'  input names: {inputs[:15]}')
            print(f'  forms: {len(forms)}')
    except Exception as e:
        print(f'GET {url}: err {type(e).__name__}')