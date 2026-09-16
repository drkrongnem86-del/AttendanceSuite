"""Extract businessData.dat TAR from GZIP at 0xB40"""
import gzip
import io
import os
import re

INPUT = r'D:/chamcong/zk_fw_attempts/web_downloads/data_body.bin'
OUT_DIR = r'D:/chamcong/zk_fw_attempts/business_extracted'
os.makedirs(OUT_DIR, exist_ok=True)

with open(INPUT, 'rb') as f:
    data = f.read()

print(f'Total: {len(data)} bytes')

# Find GZIP blocks
gz_offsets = [m.start() for m in re.finditer(b'\x1f\x8b\x08', data)]
print(f'Found {len(gz_offsets)} GZIP blocks at: {[hex(o) for o in gz_offsets]}')

# Strings in first 4KB
print('\nStrings in first 4KB:')
for m in re.finditer(rb'[\x20-\x7e]{8,}', data[:0x4000]):
    print(f'  {m.start():#x}: {m.group().decode()}')

# Process first GZIP block
gz_off = gz_offsets[0]
print(f'\nDecompressing GZIP at {gz_off:#x}...')
bio = io.BytesIO(data[gz_off:])
with gzip.GzipFile(fileobj=bio) as gz:
    decompressed = gz.read()
print(f'Decompressed: {len(decompressed)} bytes')

# Parse as TAR
pos = 0
entries = []
while pos < len(decompressed):
    if pos + 512 > len(decompressed):
        break
    hdr = decompressed[pos:pos+512]
    if hdr[:1] == b'\x00':
        break
    name_raw = hdr[0:100].rstrip(b'\x00').decode('utf-8', errors='replace')
    if not name_raw:
        break
    try:
        file_size = int(hdr[124:136].rstrip(b'\x00'), 8)
        mode = int(hdr[100:108].rstrip(b'\x00'), 8)
    except Exception:
        break
    magic = hdr[257:263].decode('utf-8', errors='replace')
    data_start = pos + 512
    data_end = data_start + file_size
    # Pad to 512
    next_pos = data_end
    if next_pos % 512:
        next_pos = ((next_pos // 512) + 1) * 512
    entries.append({
        'name': name_raw,
        'size': file_size,
        'mode': mode,
        'magic': magic,
        'start': pos,
        'data_start': data_start,
        'data_end': data_end,
        'next_pos': next_pos,
    })
    pos = next_pos

print(f'\nTAR entries: {len(entries)}')
for i, e in enumerate(entries):
    print(f'  {i+1}. {e["name"]} (size={e["size"]}, mode={e["mode"]:#o}, magic={e["magic"]!r})')
    if 0 < e['size'] < 200:
        try:
            print(f'     Content: {decompressed[e["data_start"]:e["data_end"]].decode("utf-8", errors="replace")}')
        except Exception:
            pass
    if e['size'] > 0 and e['data_end'] <= len(decompressed):
        safe_name = e['name'].replace('/', '_').replace('\\', '_').strip() or f'entry_{i}'
        out_path = os.path.join(OUT_DIR, f'{i:03d}_{safe_name}')
        with open(out_path, 'wb') as out:
            out.write(decompressed[e['data_start']:e['data_end']])
        print(f'     -> {out_path} ({e["size"]} bytes)')

print(f'\nExtracted to: {OUT_DIR}')