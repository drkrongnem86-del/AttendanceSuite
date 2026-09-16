"""Probe ZK webserver login flow"""
import re
import requests
import urllib3
urllib3.disable_warnings()

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0'})

# Step 1: Get login page
print('Step 1: Get /csl/login...')
r = session.get('http://172.16.254.202/csl/login', timeout=10)
print(f'  Status: {r.status_code}')
print(f'  Cookies: {dict(r.cookies)}')
print(f'  Body length: {len(r.content)}')

# Find forms
forms = re.findall(rb'<form[^>]+>', r.content)
print(f'  Forms: {len(forms)}')
for f in forms:
    print(f'    {f}')

inputs = re.findall(rb'<input[^>]+(?:name|Type|type)="?([a-zA-Z_]+)"?', r.content)
print(f'  Inputs: {set(inputs)}')

with open('D:/chamcong/zk_fw_attempts/csl_login.html', 'wb') as f:
    f.write(r.content)
print(f'  Saved HTML to csl_login.html ({len(r.content)} bytes)')