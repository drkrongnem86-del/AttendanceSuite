# X628 PRO — Firmware Dump Prep (Branch 2)

**Mục đích**: Chuẩn bị kiến thức + checklist hardware để khi cần dump firmware từ X628 PRO (Branch 2), BS có thể thực hiện an toàn.

**Status**: PREP — chưa thực hiện. Chỉ chạy khi Branch 1 (ADMS) thất bại.

---

## A. TẠI SAO KHÔNG VỘI DUMP FIRMWARE NGAY

### Rủi ro cao khi tháo máy

| Rủi ro | Mức độ | Hậu quả |
|---|---|---|
| Làm hỏng case (vặn quá lực) | Thấp | Mất thẩm mỹ, dễ sửa |
| Đứt cable flex từ LCD/sensor | Trung bình | Phải thay, giá ~200-500K |
| Hỏng chip flash khi tháo | **Cao** | Mất toàn bộ users/ATTLOG, phải re-enroll tất cả |
| Đo nhầm điện áp làm chập | **Cao** | Cháy mainboard, máy chết |
| Ghi lại firmware bị lỗi | Trung bình | Phải dump lại từ đầu |
| Restore firmware bị brick | **Cao** | Máy không boot được, phải thay mainboard |

### So với chi phí dump

- May 3 đang hoạt động bình thường, ATTLOG có 99,825 records
- Dump firmware chỉ cần nếu muốn RE sâu tìm undocumented ATTLOG command
- Nếu Branch 1 (ADMS) cho ra kết quả → không cần dump

---

## B. THÔNG TIN CẦN BIẾT TRƯỚC KHI THÁO

### B.1 Cấu hình phần cứng X628 PRO (per ZK catalog)

| Component | Spec |
|---|---|
| RAM | 32 MB DDR |
| Flash | 128 MB NAND/eMMC (cần verify) |
| CPU | MIPS (kernel 3.10.14) |
| Sensor | ZK Optical Fingerprint v10 |
| Display | 3" TFT LCD |
| Comm | TCP/IP + USB Host + RS485/232 |
| Power | 5V DC 2A |

### B.2 Vị trí flash chip (likely)

Trên hầu hết các máy ZK dòng này:
- Flash chip thường nằm **gần SoC chính** (chip vuông lớn nhất)
- Có thể ở mặt trên PCB hoặc mặt dưới
- Thường là chip 8-pin SOIC-8 hoặc BGA (cần verify)
- Markings thường ghi: `MX25L12835F`, `W25Q128`, `GD5F1GQ4`, etc.

### B.3 Hai khả năng flash type

**Khả năng 1 (phổ biến nhất): SPI NOR flash**
- Package: SOIC-8 (8 chân, có thể clip trực tiếp)
- Voltage: 3.3V
- Programmer: CH341A + SOIC-8 clip
- Flash tool: flashrom

**Khả năng 2: eMMC (BGA package)**
- Package: BGA-153 (rất nhỏ, BGA cần chip clip đặc biệt)
- Voltage: 1.8V hoặc 3.3V
- Programmer: eMMC programmer (Medusa Pro, Easy JTAG, Riff Box) + BGA-153 clip
- Phức tạp hơn nhiều

→ **CẦN XÁC ĐỊNH TRƯỚC KHI MUA HARDWARE**

---

## C. HARDWARE CẦN CHUẨN BỊ

### C.1 Cho SPI NOR flash (nếu là loại này)

| Item | Giá ước tính | Mua ở đâu | Ghi chú |
|---|---|---|---|
| CH341A USB Programmer | 50-100K VND | Shopee, Lazada | Bắt buộc |
| SOIC-8 clip (Pomona 5250 hoặc tương đương) | 100-200K VND | electronics store | 8-pin SOP clip |
| Flashrom (Linux) | Free | apt install flashrom | Cần máy Linux/RPi |
| **HOẶC** Raspberry Pi + spidev | 350-500K | Shopee | Có thể dùng RPi thay CH341A |
| Multimeter | 50-150K | Shopee | Đo GND/VCC/test points |
| Soldering iron (backup) | 200K | Shopee | Nếu clip tiếp xúc kém |
| Header pins (2.54mm) | 5K | Shopee | Test points backup |

### C.2 Cho eMMC (nếu là loại này)

| Item | Giá | Ghi chú |
|---|---|---|
| Medusa Pro hoặc Riff Box | 3-5 triệu VND | Đắt, chỉ dùng 1 lần |
| BGA-153 chip clip | 1-2 triệu | Khó mua ở VN |
| Hoặc Easy-JTAG Plus | 2-3 triệu | Phổ biến hơn |

→ **Khuyến nghị: BS KHÔNG nên tự làm eMMC dump. Mang ra tiệm chuyên nghiệp hoặc bỏ qua.**

---

## D. CÁC BƯỚC CHUẨN BỊ (AN TOÀN)

### Bước 1: Backup toàn bộ trước khi tháo máy

```powershell
# Trên máy BS, lấy full ATTLOG từ X628 PRO trước
& D:\chamcong\AttendanceSuite_Portable\python\python.exe D:\chamcong\zk_attlog_count.py --ip 172.16.0.214 --full

# Backup ATTLOG ra CSV
& D:\chamcong\AttendanceSuite_Portable\python\python.exe D:\chamcong\zk_dump_attlog.py --ip 172.16.0.214 --output D:\chamcong\backup_may3_attlog_20260915.csv

# Backup danh sách users
& D:\chamcong\AttendanceSuite_Portable\python\python.exe D:\chamcong\zk_dump_users.py --ip 172.16.0.214 --output D:\chamcong\backup_may3_users_20260915.csv

# Backup device info
& D:\chamcong\AttendanceSuite_Portable\python\python.exe D:\chamcong\zk_device_info.py --ip 172.16.0.214 > D:\chamcong\backup_may3_device_20260915.txt
```

### Bước 2: Kiểm tra máy có cần tháo hay không

Trước khi tháo case:
1. Test qua web UI (172.16.254.202) - xem có thông tin gì
2. Test qua protocol - đã làm rồi, có DeviceName + Platform + Firmware
3. **NẾU BRANCH 1 (ADMS) CHO KẾT QUẢ** → KHÔNG CẦN DUMP → bỏ qua Branch 2

### Bước 3: Nếu BUỘC PHẢI dump → xác định chip trước

#### 3.1 Tháo case ngoài

**Công cụ**: Tuốc-nơ-vít Phillips #1, spudger nhựa
**Cảnh báo**: Tháo nhẹ nhàng, ghi nhớ vị trí ốc

```
- Lật máy úp xuống
- Tháo 4-6 ốc Phillips mặt sau
- Tách case trước/sau bằng spudger nhựa (KHÔNG dùng tuốc-nơ-vít)
- Để ý cable flex từ LCD xuống mainboard → KHÔNG KÉO
```

#### 3.2 Quan sát mainboard

Cần xác định:
- **SoC chính** (chip vuông lớn nhất, thường ở giữa)
- **Flash chip** (gần SoC, có markings chữ và số)
- **RAM chip** (thường nhỏ hơn, gần SoC)
- **Test points** (chấm tròn nhỏ trên PCB, có thể label TX/RX/GND)
- **Crystal oscillator** (hình chữ nhật bạc, thường ở rìa)

#### 3.3 Chụp ảnh PCB

```
- Chụp mặt trên (chip side)
- Chụp mặt dưới (solder side)
- Chụp cận cảnh flash chip (đọc được part number)
- Chụp cận cảnh bất kỳ test points / headers / unpopulated pads
```

Gửi ảnh cho mình → mình sẽ xác định:
- Flash chip part number (e.g. `MX25L12835FM2I-10G`)
- Flash type (SPI NOR vs eMMC vs NAND)
- Voltage
- Datasheet từ manufacturer
- Procedure cụ thể để dump

### Bước 4: Chọn procedure dựa trên chip

| Chip type | Procedure | Hardware |
|---|---|---|
| SPI NOR (SOIC-8) | In-circuit với clip | CH341A + clip |
| SPI NOR (BGA) | Cần tháo chip | Hot air rework + programmer socket |
| eMMC (BGA) | Cần chip clip đặc biệt | eMMC programmer |
| NAND TSOP | Cần TSOP clip | NAND programmer |

### Bước 5: Dump (chỉ khi đã xác định rõ chip)

#### Cho SPI NOR (SOIC-8):

```bash
# Cài flashrom trên Linux
sudo apt install flashrom

# Kẹp clip lên chip (máy TẮT NGUỒN, KHÔNG cắm adapter)
# Lưu ý: pin 1 của clip phải trùng pin 1 của chip (thường có chấm tròn)

# Cắm CH341A vào USB

# Probe chip
sudo flashrom -p ch341a_spi

# Output sẽ hiện chip detected, ví dụ:
# Found Macronix flash chip "MX25L12835F" (16384 kB, SPI) on ch341a_spi.

# Dump 3 lần để verify
sudo flashrom -p ch341a_spi -r fw_dump1.bin
sudo flashrom -p ch341a_spi -r fw_dump2.bin
sudo flashrom -p ch341a_spi -r fw_dump3.bin

# Verify SHA-256
sha256sum fw_dump1.bin fw_dump2.bin fw_dump3.bin
# Phải GIỐNG NHAU 100% - nếu khác thì clip lỏng, dump lại
```

#### Cho eMMC:

Khuyến nghị mang ra tiệm. Procedure rất phức tạp, dễ brick.

---

## E. SAU KHI CÓ FIRMWARE BINARY

### E.1 Phân tích cơ bản

```bash
# File info
file fw_dump1.bin
ls -la fw_dump1.bin

# Strings (tìm keywords)
strings fw_dump1.bin | grep -i "attlog\|ATT_LOG\|ATTENDANCE\|insert\|write"
strings fw_dump1.bin | grep -i "ADMS\|PUSH\|SHELL\|sqlite"
strings fw_dump1.bin | grep -i "ServerAddr\|ServerType\|ADMSEnable"

# Binwalk scan
binwalk fw_dump1.bin
binwalk -e fw_dump1.bin      # extract known filesystems
binwalk -Me fw_dump1.bin    # recursive

# Hex dump first 4KB
xxd fw_dump1.bin | head -100
```

### E.2 Phân tích với Ghidra (free từ NSA)

1. Tải Ghidra: https://ghidra-sre.org/
2. Tạo project mới, import `fw_dump1.bin`
3. Chọn processor: **MIPS** (32-bit, big-endian cho ZK)
4. Auto-analyze (chấp nhận defaults)
5. Tìm strings `ATTLOG`, `SQLITE`, `SHELL`, `insert`, etc
6. Cross-reference tới functions
7. Tìm command dispatcher (handle 0x0D = CMD_ATTLOG_RRQ, 0x0F = CMD_CLEAR_ATTLOG, etc)
8. So sánh với zhangyoufu gist (220 ZK_CMD enum)

### E.3 Mục tiêu RE

Cần tìm:
1. **Command dispatcher**: function parse lệnh CMD và route tới handler
2. **ATTLOG handler**: function xử lý CMD_ATTLOG_RRQ (read), CMD_CLEAR_ATTLOG (delete)
3. **Có handler nào cho CMD_DATA_WRRQ (0x5DF = 1503) không?**
4. **Có undocumented command nào không?**
5. **ADMS daemon code**: thread/process chạy background poll server
6. **Có cách nào trigger ADMS enable programmatically không?**

Nếu RE thấy:
- ADMS daemon có code init nhưng disabled by default
- Có một flag/hidden option enable nó
- Có một command "DATA INSERT ATTLOG" undocumented

→ Có thể RE ra cách exploit

---

## F. CHECKLIST AN TOÀN

Trước khi thực hiện bất kỳ action nào:

- [ ] Branch 1 (ADMS) đã thất bại (không tìm được remote write path)
- [ ] Đã backup toàn bộ ATTLOG + Users + Device Info
- [ ] Đã xác định flash chip part number (qua ảnh PCB)
- [ ] Đã mua đúng hardware (CH341A + SOIC-8 clip cho SPI, hoặc programmer cho eMMC)
- [ ] Đã có máy Linux/RPi để chạy flashrom
- [ ] Đã tìm datasheet của chip
- [ ] Đã có kế hoạch nếu dump fail (clip lỏng, chip hỏng, etc.)
- [ ] Đã chuẩn bị restore procedure (write firmware lại nếu cần)
- [ ] **KHÔNG** thử trên May 3 (đang active) - dùng máy test khác hoặc May 20

---

## G. NẾU CẦN MANG RA TIỆM

Các tiệm repair điện thoại/embedded tại Ninh Thuận hoặc SG có thể dump firmware:

**Tại SG** (nếu BS có điều kiện):
- Các tiệm chuyên JTAG/UART cho Android phone
- Có programmer eMMC/SPI

**Chi phí ước tính**: 200K - 1 triệu VND tùy chip type

---

## H. RISK MITIGATION

### Khi dump:

1. **Đọc 3 lần**, so sánh SHA-256 → đảm bảo integrity
2. **KHÔNG BAO GIỜ write** firmware trở lại trừ khi:
   - Đã verify dump hoàn toàn giống với dump từ chip nguyên bản
   - Đã test trên máy test, không phải máy active
3. **Backup dump** ở nhiều nơi (USB, cloud, máy khác)

### Khi RE:

1. **Làm trên bản copy** của dump, không bao giờ modify bản gốc
2. **Ghi chép** mọi thay đổi/patch trong file riêng
3. **Diff** dump sau khi modify với dump gốc để xem thay đổi gì

### Khi exploit:

1. **Test trên máy test** (May 20 hoặc May 3 sau khi BS đã verify ATTLOG có thể xóa)
2. **Có backup** trước khi exploit
3. **Document mọi thứ** để reproduce

---

## I. KẾT LUẬN

Branch 2 chỉ chạy khi:
1. Branch 1 (ADMS) thất bại hoàn toàn
2. BS có thời gian + hardware + chuyên môn để dump
3. Rủi ro được chấp nhận

**Trước khi làm**, vui lòng:
1. Gửi ảnh PCB của X628 PRO
2. Confirm chip part number
3. Mình sẽ guide procedure cụ thể dựa trên chip thật

**Không tự ý tháo máy** nếu chưa có plan đầy đủ.

---

## References

- Securelist ZKTeco RE article: https://securelist.com/biometric-terminal-vulnerabilities/112800/
- VoidstarSec embedded roadmap: https://voidstarsec.com/roadmap/
- HackTricks firmware analysis: https://www.hacktricks.wiki/hardware-physical-access/firmware-analysis
- Binwalk: https://github.com/refirmlabs/binwalk
- Ghidra: https://ghidra-sre.org/
- Flashrom: https://flashrom.org/
