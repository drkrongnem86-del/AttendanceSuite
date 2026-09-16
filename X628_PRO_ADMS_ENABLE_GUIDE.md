# X628 PRO — Hướng dẫn bật ADMS để quan sát traffic

**Mục đích**: Bật ADMS trên máy chấm công X628 PRO tại bệnh viện để quan sát toàn bộ chu trình giao tiếp với ADMS server, tìm xem có đường server → device nào cho phép INSERT ATTLOG không.

**Risk level**: 🟢 THẤP (chỉ enable ADMS, không xóa dữ liệu, dễ rollback)

---

## A. CHUẨN BỊ

### 1. Thiết bị cần

- Máy chấm công X628 PRO (đang hoạt động bình thường)
- Một máy tính có IP trong cùng mạng với máy chấm công (hiện là **171.15.128.4**)
- Internet nối được vào máy BS (đang có VPN tới BV Ninh Thuận)

### 2. Thông tin cần biết

| Thông tin | Giá trị |
|---|---|
| Serial thiết bị | `3324224660202` (May 3) |
| IP hiện tại | `172.16.0.214` (May 3) — đứng ngay trước máy |
| CommKey (CommPwd) | `admin` |
| ADMS server IP | `171.15.128.4` (máy BS) |
| ADMS server port | `8088` |

### 3. Trước khi bật

- **Backup dữ liệu**: Vào `Menu → Data Mgt → Download AttLog` lưu vào USB
- Ghi lại **ATTLOG count hiện tại** (vào `Menu → Data Mgt → Storage Mgmt` hoặc đọc từ web)
- Chắc chắn máy tính BS có IP `171.15.128.4` và ping được ra internet

---

## B. CÁC BƯỚC BẬT ADMS TRÊN X628 PRO

### Bước 1: Vào menu Communication

Từ màn hình chính của máy chấm công:

```
Nhấn [M/OK] → Communication → OK
```

### Bước 2: Tìm Cloud Server Setting (hoặc ADMS)

Tùy firmware version, có thể thấy một trong các đường dẫn:

**Option A** (firmware cũ):
```
Communication → Cloud Server Setting → OK
```

**Option B** (firmware mới):
```
Communication → ADMS → OK
```

**Option C** (một số model):
```
Communication → Ethernet → Cloud Server / Server Mode → OK
```

### Bước 3: Bật Enable

Trong menu ADMS / Cloud Server Setting:

| Field | Giá trị cần đặt |
|---|---|
| **Enable / Server Mode** | `Yes` hoặc `ADMS` |
| **Server Address** | `171.15.128.4` (IP của máy BS) |
| **Server Port** | `8088` |
| **Enable Domain Name** | `No` (vì dùng IP trực tiếp) |
| **HTTPS** | `No` |
| **Comm Key (nếu có)** | `admin` |

Nhấn `OK` để lưu.

### Bước 4: Verify Device Type (nếu cần)

Nếu máy hỏi "Device Type" (một số firmware PUSH-only):

```
Menu → System → Device Type Settings
  → Communication Protocol: PUSH Protocol
  → Device Type: T&A PUSH (cho chấm công)
```

> ⚠️ **CẢNH BÁO**: ZK FAQ nói "When you change device type, data store in device will be deleted". Nếu đã đúng T&A PUSH → KHÔNG ĐỔI. Chỉ đổi nếu thấy CommType ≠ ADMS.

### Bước 5: Quan sát máy

Sau khi lưu cấu hình, máy sẽ:
1. Tự động khởi động lại 1 lần (~30-60 giây)
2. Sau khi khởi động xong, **sẽ tự động POST `/iclock/cdata?SN=...&options=all`** lên server của BS

Nếu máy **KHÔNG thấy POST** tới server sau 2 phút:
- Kiểm tra firewall trên máy BS có block port 8088 không
- Thử tắt tường lửa Windows tạm thời
- Kiểm tra máy BS có ping được 172.16.0.214 không

---

## C. TRÊN MÁY BS — CHẠY ADMS SERVER

### Cách 1: Quick capture (không cần admin)

Mở PowerShell tại `D:\chamcong\`:

```powershell
cd D:\chamcong
$env:PYTHONIOENCODING="utf-8"
& D:\chamcong\AttendanceSuite_Portable\python\python.exe D:\chamcong\zk_adms_full_server.py
```

Server sẽ:
- Lắng nghe trên `171.15.128.4:8088`
- Log mọi request tới `D:\chamcong\adms_logs\adms_traffic_YYYYMMDD_HHMMSS.jsonl`
- In log ra console với timestamps

### Cách 2: Capture + Queue Commands (khi đã có traffic)

```powershell
& D:\chamcong\AttendanceSuite_Portable\python\python.exe D:\chamcong\zk_adms_full_server.py --admin
```

Sau khi server chạy, BS gõ vào cửa sổ:

```
> shell 3324224660202 ls /
> shell 3324224660202 ls /mnt/mtdblock/data/
> shell 3324224660202 sqlite3 /mnt/mtdblock/data/ZKDB.db ".tables"
> shell 3324224660202 sqlite3 /mnt/mtdblock/data/ZKDB.db "SELECT count(*) FROM ATT_LOG"
> info 3324224660202
> check 3324224660202
> quit
```

Mỗi command được queue, khi device poll `GET /iclock/getrequest` sẽ nhận và thực thi ngay.

---

## D. SAU KHI CÓ TRAFFIC

### Điều cần quan sát

1. **Handshake request**:
   ```
   GET /iclock/cdata?SN=3324224660202&options=all&pushver=2.4.1&language=83&DeviceType=att&PushOptionsFlag=1
   ```
   → Xác nhận thiết bị đang dùng protocol v2.4.1

2. **Device info push**:
   ```
   POST /iclock/cdata?SN=...&table=options
   Body: DeviceName=X628 PRO,FirmVer=Ver 6.60 Dec 9 2019,...
   ```

3. **ATTLOG upload**:
   ```
   POST /iclock/cdata?SN=...&table=ATTLOG&Stamp=9999
   Body: 1383\t2026-09-15 09:00:00\t0\t15\t0\t0\n
   ```
   → Xem có bao nhiêu records được push

4. **Poll for commands**:
   ```
   GET /iclock/getrequest?SN=...
   ```
   → Đây là endpoint quan trọng — device hỏi "có command nào cho tôi không?"

5. **Command results**:
   ```
   POST /iclock/devicecmd?SN=...
   Body: ID=101&Return=0&CMD=SHELL&Content=...
   ```
   → Trả về output của SHELL command

### Tìm gì trong captures?

| Cái tìm | URL/command | Mục đích |
|---|---|---|
| ✅ SHELL command | `C:UUID:SHELL <cmd>` | Chạy Linux command trên thiết bị |
| ✅ SET OPTIONS | `C:UUID:SET OPTIONS <key>=<value>` | Set option ẩn |
| ✅ DATA UPDATE ATTLOG | `C:UUID:DATA UPDATE ATTLOG ...` | **INSERT ATTLOG (nếu tồn tại)** |
| ❌ UNKNOWN COMMAND | `C:UUID:FOO BAR` | Vendor-specific, có thể INSERT ATTLOG |

---

## E. ROLLBACK

Sau khi capture xong (dù thành công hay thất bại), để trả thiết bị về trạng thái ban đầu:

```
Menu → Communication → Cloud Server Setting
  → Enable: No
  → Save
```

Hoặc nếu muốn trỏ sang server khác (vd BioTime production):

```
Menu → Communication → ADMS
  → Server Address: 172.16.200.105 (production ADMS)
  → Server Port: 8080
  → Save
```

> ⚠️ **Lưu ý**: ATTLOG count KHÔNG bị ảnh hưởng bởi việc enable/disable ADMS. Dữ liệu an toàn.

---

## F. CHECKLIST NHANH

- [ ] BS đã backup ATTLOG qua USB trước khi bắt đầu
- [ ] Ghi lại ATTLOG count hiện tại (để so sánh sau)
- [ ] Máy BS đã chạy `zk_adms_full_server.py` trên port 8088
- [ ] Máy tính BS đã tắt firewall tạm thời (hoặc allow port 8088)
- [ ] BS đang đứng trước máy X628 PRO
- [ ] Mở Menu → Communication → Cloud Server Setting
- [ ] Enable = Yes, Server Address = 171.15.128.4, Port = 8088
- [ ] Save và quan sát máy + log trên server
- [ ] Nếu có traffic → gõ `shell <SN> ls /` trong admin mode
- [ ] Sau khi xong → rollback về trạng thái ban đầu

---

## G. NẾU KHÔNG CÓ TRAFFIC

Nếu máy lưu cấu hình nhưng KHÔNG gửi request tới server:

1. **Kiểm tra kết nối** từ máy chấm công tới máy BS:
   - Trên máy chấm công: `Menu → System → Network Test` (nếu có) hoặc mở `Comm → Ethernet`
   - Trên máy BS: `ping 172.16.0.214` và `netstat -ano | findstr :8088`

2. **Đổi HTTPS = Yes** nếu trước đó = No (hoặc ngược lại)
   - Một số firmware PUSH 2.4.1+ mặc định HTTPS

3. **Đổi Server Port** thành `80` (default cho nhiều ADMS server)
   - Nếu port 8088 bị block ở tường lửa

4. **Thử Server Address = domain name** (không phải IP):
   - Trên máy BS, có thể trỏ domain về 171.15.128.4
   - Hoặc dùng local proxy
   - Trong Cài đặt → Enable Domain Name = Yes → Server Address = `http://171.15.128.4`

5. **Restore factory và config lại** (chỉ khi cần):
   - `Menu → System → Restore to Factory Settings`
   - **CẢNH BÁO: Xóa hết users + ATTLOG** — CHỈ làm khi đã backup

---

## H. KẾT QUẢ MONG ĐỢI

Sau khi làm đúng:

✅ **Best case**: Có traffic + SHELL command hoạt động → có thể `sqlite3 INSERT INTO ATT_LOG` để fake punch
✅ **Good case**: Có traffic + phát hiện command ẩn nào đó INSERT được ATTLOG  
✅ **OK case**: Có traffic + không tìm được command INSERT, nhưng confirm được ADMS protocol hoạt động đúng
❌ **Bad case**: Không có traffic → issue network/firewall, cần kiểm tra thêm

Dù kết quả nào, chúng ta sẽ có data thực tế để quyết định tiếp Branch 2 (firmware RE) hay không.

---

**Liên hệ**: Báo lại cho BS ngay khi bật xong — mình sẽ quan sát log real-time từ máy BS.
