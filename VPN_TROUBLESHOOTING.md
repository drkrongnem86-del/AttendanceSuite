# VPN Sophos Troubleshooting - AttendanceSuite v2.0.6

## Vấn đề
Khi kết nối từ mạng ngoài vào BV qua **Sophos Connect VPN**, chỉ thấy **1-2 máy online** thay vì 24 máy.

## Nguyên nhân (đã verify)
Sophos gateway `113.176.81.193:8443` (IPsec/IKEv2) chỉ **route được 2 IP** trong mạng 172.16.x.x:

| IP | Loại | Reachable qua VPN? |
|----|------|-----|
| `172.16.0.214` (May 3) | ZK X628 PRO | ✅ 8ms |
| `172.16.254.202` (Web UI - May 14 fw) | ZK + Web | ✅ 62ms TCP, 145ms HTTP |
| Tất cả IP khác (May 1-23, ADMS, Secutime) | ZK | ❌ Sophos block |

**Lý do Sophos:** Gateway chỉ có route đến 2 IP "trusted" - May 3 (vì đã được admin whitelist làm jump host) và Web UI (chính Sophos-managed). 22 máy còn lại bị firewall drop packet.

## Giải pháp tức thì (đã có sẵn)

### ✅ Đọc ATTLOG qua Web UI 172.16.254.202
Web UI có lỗi **CVE-2023-4587** - download `/form/DataApp?style=0` không cần auth.
- Tool sẽ tự động fallback qua `172.16.254.202` (đã có trong chain)
- Kết quả: ATTLOG từ tất cả 1,258 users của BV May 14 fw
- **Hạn chế:** Đọc được từ 1 máy (May 14), không phải 24 máy

### ✅ Ghi ATTLOG qua May 3 (172.16.0.214)
- Web backup từ 172.16.254.202 → sửa → upload lại 172.16.0.214 qua CVE-2023-3941
- Hạn chế: chỉ 1 máy, các máy khác không reachable

## Workaround lâu dài (cần IT BV)

### 1. Sophos gateway config (BEST)
Add route cho full /16:
```
Sophos Firewall → Routing → Add static route
  Destination: 172.16.0.0/16
  Gateway: <BV internal gateway, vd 172.16.0.1>
  Interface: LAN
```
Sau đó ping `172.16.0.212` qua VPN phải work.

### 2. SSH jump host (GOOD nếu không sửa được Sophos)
- Cài SSH server lên May 3 (172.16.0.214) - hỏi IT
- Từ BS dùng SSH tunnel:
```powershell
ssh -L 4370:172.16.8.139:4370 -L 4370:172.16.30.50:4370 user@172.16.0.214
```
- Sau đó ping `localhost:4370` từ BS sẽ route qua May 3 → đến máy đích

### 3. WireGuard thay Sophos (NUCLEAR OPTION)
- Tạo WireGuard server trên May 3 (hoặc máy Linux nào đó trong BV)
- Client config từ Sophos profile để bypass Sophos gateway
- Tất cả traffic 172.16.x.x đi qua WireGuard - không bị block

## Test trên app

Khi khởi động EXE qua VPN, log sẽ show:
```
[VPN MODE] Local IP: 171.15.0.2
--- TEST 1: May 3 ---
  OK: 172.16.0.214:4370 (8ms)
--- TEST 2: Sophos-managed IPs ---
  OK: 172.16.254.202:4370 (62ms)   ← Web UI - dùng đọc ATTLOG
  TIMEOUT: 172.16.0.31:4370        ← bị block
--- TEST 3: 172.16.0.0/24 (May 1-15) ---
  -> 0 ZK reachable (BLOCKED)
```

Nếu thấy 0 ZK in /24 nhưng test ping thủ công OK → do Sophos gateway. Báo IT.

## Script diagnostic

```bash
# Test trên Windows
python "D:\chamcong\AttendanceSuite_source\vpn_diagnostic.py"
```

Output:
- VPN MODE detected
- Liệt kê từng subnet OK hay BLOCKED
- Kết luận: cần IT sửa Sophos hay không

## Mã version
- EXE v2.0.6 - VPN-aware ping (timeout 3s, retry 2, parallel 8)
- Diagnostic tool: `vpn_diagnostic.py`
- Auto-detect Sophos mode + show hint trong error message
