import os
import gzip
import re
import struct

OUT_DIR = r'D:\chamcong\zk_fw_attempts\web_downloads'
fpath = os.path.join(OUT_DIR, 'GET_STYLE0_data.dat')

with open(fpath, 'rb') as f:
    data = f.read()

# Find all GZIP positions
gzip_positions = []
i = 0
while True:
    i = data.find(b'\x1f\x8b', i)
    if i == -1:
        break
    gzip_positions.append(i)
    i += 1

print(f'Found {len(gzip_positions)} GZIP signatures at: {gzip_positions}')
print()

# Extract each one
extract_dir = os.path.join(OUT_DIR, 'extracted_gzips')
os.makedirs(extract_dir, exist_ok=True)

for idx, pos in enumerate(gzip_positions):
    # Find end of gzip data (look for next gzip or end of file)
    if idx + 1 < len(gzip_positions):
        end_search = gzip_positions[idx + 1]
    else:
        end_search = len(data)

    chunk = data[pos:end_search]
    print(f'[{idx+1}/{len(gzip_positions)}] GZIP at offset {pos}, max {len(chunk)} bytes')

    # Try to extract
    out_path = os.path.join(extract_dir, f'chunk_{idx:02d}_offset_{pos}.bin')
    try:
        # Try gzip decompression
        decompressed = gzip.decompress(chunk)
        print(f'  Decompressed: {len(decompressed)} bytes')

        # Save both
        out_gz = os.path.join(extract_dir, f'chunk_{idx:02d}_offset_{pos}.gz')
        with open(out_gz, 'wb') as f:
            f.write(chunk[:min(len(chunk), 1024*1024)])
        out_dec = os.path.join(extract_dir, f'chunk_{idx:02d}_offset_{pos}.decompressed')
        with open(out_dec, 'wb') as f:
            f.write(decompressed)
        print(f'  Saved: {out_gz} + {out_dec}')

        # Try to identify content
        if decompressed[:15] == b'SQLite format 3':
            print('  [SQLite database!]')
        else:
            print(f'  First 32 bytes: {decompressed[:32].hex()}')
            strs = re.findall(rb'[\x20-\x7e]{4,}', decompressed[:200])
            if strs:
                print(f'  Strings: {strs[:5]}')
    except Exception as e:
        print(f'  Gzip decompress failed: {type(e).__name__}: {str(e)[:100]}')
        # Maybe it's not full gzip - just header
        # Try first 32 bytes only
        print(f'  First 16 bytes: {chunk[:16].hex()}')

print()
print('=== Total extracted ===')
total = 0
for f in os.listdir(extract_dir):
    full = os.path.join(extract_dir, f)
    size = os.path.getsize(full)
    total += size
    print(f'  {f}: {size} bytes')
print(f'Total: {total} bytes ({total/1024/1024:.2f} MB)')
