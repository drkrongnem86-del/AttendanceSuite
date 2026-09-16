"""Extract TAR entries from GZIP-compressed ZKConfig backup"""
import gzip
import os
import struct
import sys

sys.stdout.reconfigure(encoding='utf-8')

INPUT = r'D:/chamcong/zk_fw_attempts/web_downloads/172.16.254.202_form_DataApp_style_1.bin'
OUT_DIR = r'D:/chamcong/zk_fw_attempts/zkgz_extracted'

os.makedirs(OUT_DIR, exist_ok=True)


def parse_tar(data, start=0):
    """Parse USTAR/POSIX TAR entries"""
    entries = []
    pos = start
    while pos < len(data):
        if pos + 512 > len(data):
            break

        header = data[pos:pos + 512]
        if header == b'\x00' * 512:
            # End-of-archive (two zero blocks)
            break

        name_raw = header[0:100].rstrip(b'\x00').decode('utf-8', errors='replace')
        if not name_raw:
            break

        try:
            file_size = int(header[124:136].rstrip(b'\x00'), 8)
            mode = int(header[100:108].rstrip(b'\x00'), 8)
            uid = int(header[108:116].rstrip(b'\x00'), 8)
            gid = int(header[116:124].rstrip(b'\x00'), 8)
            mtime = int(header[136:148].rstrip(b'\x00'), 8)
            typeflag = chr(header[156])
            magic = header[257:263].decode('utf-8', errors='replace')
        except Exception as e:
            print(f'Parse error at {pos:#x}: {e}')
            break

        data_start = pos + 512
        data_end = data_start + file_size
        # Align to 512
        file_data_end = data_end
        if file_data_end % 512:
            file_data_end = ((file_data_end // 512) + 1) * 512

        entries.append({
            'name': name_raw,
            'mode': mode,
            'uid': uid,
            'gid': gid,
            'mtime': mtime,
            'size': file_size,
            'type': typeflag,
            'magic': magic,
            'data_start': data_start,
            'data_end': data_end,
            'next_pos': file_data_end,
        })

        pos = file_data_end
        if typeflag == 'L':
            # Long name stored as data
            pass

    return entries


# Find GZIP blocks in input
gzip_magic = b'\x1f\x8b\x08'
pos = 0
gzip_blocks = []
while True:
    idx = INPUT if isinstance(INPUT, str) else INPUT
    with open(idx, 'rb') as f:
        data = f.read()

    p = data.find(gzip_magic, pos)
    if p < 0:
        break
    gzip_blocks.append(p)
    pos = p + 1

print(f'Found {len(gzip_blocks)} GZIP blocks at offsets: {[hex(p) for p in gzip_blocks]}')

for i, gz_off in enumerate(gzip_blocks):
    print(f'\n=== GZIP block #{i+1} at {gz_off:#x} ===')
    try:
        decompressed = gzip.decompress(data[gz_off:])
        print(f'  Decompressed: {len(decompressed)} bytes')

        # Parse as TAR
        entries = parse_tar(decompressed)
        for j, e in enumerate(entries):
            print(f'  Entry #{j+1}: name={e["name"]!r} size={e["size"]} mode={e["mode"]:#o} magic={e["magic"]!r}')

            # Save entry
            safe_name = e['name'].replace('/', '_').replace('\\', '_').strip()
            if not safe_name:
                safe_name = f'entry_{j}'
            out_path = os.path.join(OUT_DIR, f'gz{i+1}_{safe_name}')
            entry_data = decompressed[e['data_start']:e['data_end']]
            with open(out_path, 'wb') as f:
                f.write(entry_data)
            print(f'    -> {out_path} ({len(entry_data)} bytes)')
            if e['size'] < 200:
                try:
                    print(f'    Content: {entry_data.decode("utf-8", errors="replace")[:200]}')
                except Exception:
                    pass
    except Exception as e:
        print(f'  Error: {e}')

print(f'\nExtracted to: {OUT_DIR}')