# Branch 2 Discovery — CVE-2023-4587 on X628 PRO FW 6.60

**Date**: 2026-09-15 12:30
**Tester**: Mavis (autonomous via protocol)
**Device**: May 3 (172.16.0.214, Serial 3324224660202)
**Web UI**: 172.16.254.202

---

## 🎯 MAJOR FINDING

**CVE-2023-4587 (Missing Authentication in ZKTeco Web Interface) CONFIRMED for X628 PRO FW 6.60**

Earlier research said CVE doesn't apply to ZLM60_TFT platform. **WRONG.** The web UI at 172.16.254.202 DOES respond to unauthenticated backup requests.

### Endpoints (no auth required)

| Endpoint | Response | Size |
|---|---|---|
| `GET /form/DataApp?style=1` | `device_<serial>.dat` (config only) | 6,497 bytes |
| `GET /form/DataApp?style=0` | `data.dat` (full backup) | 3,889,617 bytes |
| `GET /form/DataApp?style=2` | `data.dat` | 3,889,620 bytes |
| `GET /form/DataApp?style=5` | `data.dat` | 3,889,620 bytes |

**Verified**: POST, GET, with/without auth, Range header — all return same data. **No authentication required.**

### Files downloaded

| File | Path |
|---|---|
| Small config | `D:\chamcong\zk_fw_attempts\web_downloads\GET_AUTH_891401_device_5418194560548.dat` (6,497 bytes) |
| Full backup | `D:\chamcong\zk_fw_attempts\web_downloads\GET_STYLE0_data.dat` (3,889,617 bytes) |

---

## Format Comparison

### USB backup format (still works, FW 6.60):
```
file: 7z archive (verified with py7zr)
├── data/
│   └── ZKDB.db (SQLite database)
│       ├── ATT_LOG (10 cols)
│       ├── USER_INFO (7 cols)
│       └── sqlite_sequence
```

**Extracted successfully**: `D:\chamcong\test_backup.dat.extracted\data\ZKDB.db` (20,480 bytes)
- ATT_LOG: 1 record (test data)
- USER_INFO: 1 user

### Web backup format (FW 6.60):
```
file: "ZK format 1.0.0.0" header (256 bytes)
  ├── "businessData.dat" filename reference (offset 1056)
  ├── "2026-09-15T12:26:47" timestamp
  ├── "Back up with webserver" description
  └── ENCRYPTED BODY (3.7 MB) — NOT standard archive
```

**Decryption attempts (all FAILED):**
- ❌ Not a ZIP/TAR/GZIP/BZ2/XZ/7Z file
- ❌ XOR with last 16 bytes of file
- ❌ XOR with file_size (LE 4 bytes)
- ❌ XOR with file_size (LE 8 bytes)
- ❌ XOR with serial number (`3324224660202`)
- ❌ XOR with CommPwd (`admin`)
- ❌ XOR with combined keys
- ❌ Single-byte XOR brute force
- ❌ py7zr with various passwords

**Conclusion**: ZK uses **proprietary encryption** for FW 6.60 web backups (newer than redteam-pentesting.de advisory's TAR.GZ format).

---

## What This Means

### ✅ Confirmed
- X628 PRO FW 6.60 **HAS** web server + vulnerable to CVE-2023-4587
- Backup data is **obtainable** via web (3.7 MB encrypted file)
- Decryption key/algorithm **unknown** to us

### ⚠️ Important
- Web backup is **DIFFERENT format** from USB backup (which is 7z with our custom encryption)
- USB backup → 7z + ZKDB.db → SQLite → readable (already have tool)
- Web backup → ZK proprietary encrypted → NOT directly readable

### 🎯 For INSERT ATTLOG Goal
- USB workflow (`chamcong_oneclick.py`) **still works** and gives full database access
- Web backup doesn't add new capability for ATTLOG insertion
- But web backup IS useful for:
  - Firmware binary analysis (if we ever decrypt it)
  - Understanding ZK encryption for FW RE
  - Proving device vulnerable to known CVEs

---

## Network Reachability

The web UI is at `172.16.254.202` (separate IP from protocol IP `172.16.0.214`):
- Device has **2 network interfaces** OR **2 different VLAN segments**
- Both reachable from our VPN
- May indicate production uses different subnet for web vs protocol traffic

---

## Artifacts

### Scripts created
- `D:\chamcong\zk_firmware_extract.py` — Phase 1: Protocol attempts (CMD_READFILE etc.)
- `D:\chamcong\zk_dump_web_backup.py` — Download device_5418194560548.dat
- `D:\chamcong\zk_web_dl_variants.py` — Try multiple auth methods
- `D:\chamcong\zk_parse_dat_backup.py` — Initial parsing
- `D:\chamcong\zk_decode_dat_v2.py` — Try archive formats
- `D:\chamcong\zk_extract_gzips.py` — Try GZIP extraction
- `D:\chamcong\zk_xor_decrypt.py` — XOR brute force v1
- `D:\chamcong\zk_xor_proper.py` — XOR brute force v2
- `D:\chamcong\zk_extract_dat_tar.py` — Try tar/gz/bz2/xz/zstd/7z
- `D:\chamcong\zk_decrypt_small.py` — Try decrypt small config file
- `D:\chamcong\zk_inspect_zkdb.py` — Inspect USB backup SQLite

### Data downloaded
- `D:\chamcong\zk_fw_attempts\web_downloads\` (multiple .dat files, .bin XOR variants)

### Reports
- `D:\chamcong\zk_fw_attempts\fw_extract_log.jsonl` — Per-event log
- `D:\chamcong\zk_fw_attempts\fw_extract_report_*.json` — Per-test JSON

---

## Action Plan Updates

### ❌ Branch 2 status
- Web backup file obtained BUT not decryptable
- Need firmware binary for actual RE
- No public X628 PRO firmware available (ZK download requires Silver+ member login)

### ✅ Branch 1 status
- Web backup is NOT a viable path for ATTLOG insertion (encrypted)
- USB backup is the working path (already confirmed E2E)

### 🎯 New Branch 2 idea
If BS has physical access to May 3:
- Open the device case
- Take photos of PCB
- Identify flash chip (SOIC-8 SPI vs BGA eMMC)
- Decide: CH341A + clip (cheap) or professional dump
- Use `X628_PRO_FLASH_DUMP_PREP.md` for guidance

---

## Verdict

> **Web backup extraction = SUCCESS (file obtained) but DECRYPTION = FAILED**
>
> We now have evidence that ZK FW 6.60 webserver exposes backup data without auth, but the backup format is encrypted with proprietary ZK algorithm that we don't have the key for.
>
> For ATTLOG insertion purpose: **USB backup attack (Branch 1) remains the only working solution.**

---

**References**:
- Redteam Pentesting Advisory (original CVE): https://www.redteam-pentesting.de/en/advisories/rt-sa-2021-003/
- CVE-2023-4587: Missing Authentication in ZKTeco ZEM/ZMM Web Interface
- CVE-2022-42953: Related Missing Auth CVE

**Note**: Earlier research was WRONG about "X628 PRO has no HTTP server". The webserver IS there but on a separate IP (172.16.254.202). This changes our threat model significantly for FW 6.60 devices.
