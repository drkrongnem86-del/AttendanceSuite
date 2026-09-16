"""Inspect ZK login HTML for form structure"""
import re

with open(r'D:/chamcong/zk_fw_attempts/csl_login.html', 'rb') as f:
    data = f.read()

# Find all form elements
print('=== Forms ===')
for m in re.finditer(rb'<form[^>]*>', data):
    print(f'  {m.group().decode()}')

# Find all input elements
print('\n=== Inputs ===')
for m in list(re.finditer(rb'<input[^>]+>', data))[:30]:
    s = m.group().decode()
    print(f'  {s[:120]}')

# Find all button elements
print('\n=== Buttons ===')
for m in list(re.finditer(rb'<button[^>]*>', data))[:10]:
    print(f'  {m.group().decode()[:120]}')

# Find script references
print('\n=== Scripts ===')
for m in list(re.finditer(rb'<script[^>]*src=[\"\\\'](.*?)[\"\\\']', data))[:10]:
    print(f'  {m.group(1).decode()}')

# Find login-related URLs in JS
print('\n=== Login URLs in JS ===')
urls = re.findall(rb'[\"\\\'](/[^\\\"\\\']*?(?:login|auth|user|restore|backup|upload)[^\"\\\']*?)[\"\\\']', data)
for u in urls[:20]:
    print(f'  {u.decode()}')

# Find form action patterns
print('\n=== Action attributes ===')
for m in list(re.finditer(rb'action=[\"\\\']([^\"\\\']+)[\"\\\']', data))[:10]:
    print(f'  {m.group(1).decode()}')