// VpnBenhVienScreen v3.0.93 - Native OpenVPN client (ics-openvpn)
// Quản lý: Connect/Disconnect, Account input (default ẩn pass), Auto-disconnect 5p khi background
// v3.0.93:
//   - Tài khoản mặc định: ẩn password (không cho xem, không edit)
//   - Mục "Tài khoản khác" riêng để nhập user + pass
//   - Bỏ dòng "Mặc định: ..." (lộ pass)
//   - Thông tin kết nối gọn lại
//   - Auto-disconnect 5 phút khi thoát/thu gọn app
// v3.0.96: Comment sạch - không lộ username/password
//   - WidgetsBindingObserver để track app lifecycle
import 'package:flutter/material.dart';
import 'package:attendance_mobile/core/services/vpn_benh_vien_service.dart';

class VpnBenhVienScreen extends StatefulWidget {
  const VpnBenhVienScreen({super.key});

  @override
  State<VpnBenhVienScreen> createState() => _VpnBenhVienScreenState();
}

class _VpnBenhVienScreenState extends State<VpnBenhVienScreen>
    with WidgetsBindingObserver {
  final _otherUserCtrl = TextEditingController();
  final _otherPassCtrl = TextEditingController();
  bool _showOtherPass = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadInitial();
    VpnBenhVienService.instance.addListener(_onVpnChanged);
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    VpnBenhVienService.instance.removeListener(_onVpnChanged);
    WidgetsBinding.instance.removeObserver(this);
    _otherUserCtrl.dispose();
    _otherPassCtrl.dispose();
    super.dispose();
  }

  // v3.0.93: App lifecycle - auto-disconnect khi background quá 5 phút
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final vpn = VpnBenhVienService.instance;
    if (state == AppLifecycleState.paused || state == AppLifecycleState.inactive) {
      vpn.onAppPaused();
    } else if (state == AppLifecycleState.resumed) {
      vpn.onAppResumed();
    }
  }

  void _onVpnChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _loadInitial() async {
    await VpnBenhVienService.instance.init();
    if (!mounted) return;
    setState(() {});
  }

  Future<void> _connect() async {
    if (_busy) return;
    final vpn = VpnBenhVienService.instance;
    // Nếu đang dùng "Tài khoản khác" → set credentials trước
    if (!vpn.isUsingDefaultAccount) {
      final user = _otherUserCtrl.text.trim();
      final pass = _otherPassCtrl.text;
      if (user.isEmpty || pass.isEmpty) {
        _snack('Nhập tài khoản + mật khẩu', ok: false);
        return;
      }
      await vpn.setCredentials(user, pass);
    } else {
      // Reset về default nếu cached credentials khác default
      // (an toàn: nếu user đã thử setCredentials với user khác)
      // Cờ: nếu currentUser là rỗng (do toggleAccount setCredentials('', ''))
      if (vpn.currentUser.isEmpty) {
        await vpn.resetToDefault();
      }
    }
    setState(() => _busy = true);
    final ok = await vpn.connect();
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) {
      _snack('🔐 Đang yêu cầu kết nối VPN...');
    } else {
      // v1.5.7: Hien thi loi chi tiet - se hien thi inline trong UI (khong chi snackbar)
      _snack('❌ ${vpn.lastError ?? "Lỗi không xác định"}', ok: false);
    }
  }

  Future<void> _disconnect() async {
    if (_busy) return;
    setState(() => _busy = true);
    VpnBenhVienService.instance.disconnect();
    if (!mounted) return;
    setState(() => _busy = false);
    _snack('⚠️ Đã ngắt kết nối VPN');
  }

  void _snack(String msg, {bool ok = true}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: ok ? Colors.blue : Colors.red,
        duration: Duration(seconds: ok ? 2 : 4),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final vpn = VpnBenhVienService.instance;
    final remaining = vpn.remainingAutoDisconnectSeconds;
    return Scaffold(
      backgroundColor: Colors.grey[50],
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D47A1),
        foregroundColor: Colors.white,
        title: const Row(
          children: [
            Icon(Icons.vpn_lock, color: Colors.white, size: 22),
            SizedBox(width: 8),
            Text('VPN Bệnh viện', style: TextStyle(fontSize: 16)),
          ],
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Banner auto-disconnect (nếu đang đếm)
            if (remaining != null) _buildAutoDisconnectBanner(remaining),
            if (remaining != null) const SizedBox(height: 12),

            // v1.5.7: Hien thi loi chi tiet INLINE (khong chi snackbar)
            if (vpn.lastError != null) _buildErrorBanner(vpn),
            if (vpn.lastError != null) const SizedBox(height: 12),

            // Status Card
            _buildStatusCard(vpn),
            const SizedBox(height: 16),
            // Account form
            _buildAccountForm(vpn),
            const SizedBox(height: 16),
            // Action buttons
            _buildActionButtons(vpn),
            const SizedBox(height: 16),
            // Config info (gọn)
            _buildConfigInfo(),
          ],
        ),
      ),
    );
  }

  /// v1.5.7: Error banner chi tiet hien thi INLINE
  Widget _buildErrorBanner(VpnBenhVienService vpn) {
    final stage = vpn.stage?.toString().split('.').last ?? '?';
    final raw = vpn.lastRawStage ?? '';
    final status = vpn.lastStatusMessage ?? '';
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFEBEE),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFD32F2F), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.error_outline, color: Color(0xFFD32F2F), size: 20),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  '❌ Lỗi VPN',
                  style: TextStyle(
                    color: Color(0xFFB71C1C),
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close, size: 18, color: Color(0xFFB71C1C)),
                onPressed: () => setState(() {
                  // Khong can clear vi service se tu clear khi connect thanh cong
                }),
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(4),
            ),
            child: SelectableText(
              vpn.lastError ?? '',
              style: const TextStyle(
                color: Color(0xFF263238),
                fontSize: 12,
                fontFamily: 'monospace',
              ),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _buildDebugChip('Stage', stage),
              if (raw.isNotEmpty && raw != vpn.lastError) ...[
                const SizedBox(width: 4),
                _buildDebugChip('Raw', raw.length > 30 ? '${raw.substring(0, 30)}...' : raw),
              ],
            ],
          ),
          if (status.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              'Status: $status',
              style: const TextStyle(color: Color(0xFF607D8B), fontSize: 10, fontFamily: 'monospace'),
            ),
          ],
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFFFFF3E0),
              borderRadius: BorderRadius.circular(4),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '💡 Gợi ý xử lý:',
                  style: TextStyle(
                    color: Color(0xFFE65100),
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  '• Bấm "NGẮT" rồi thử "KẾT NỐI" lại\n'
                  '• Nếu thấy dialog xin quyền VPN → bấm "OK"/"Cho phép"\n'
                  '• Kiểm tra kết nối internet (WiFi/4G)\n'
                  '• Liên hệ IT nếu user/pass bị sai',
                  style: TextStyle(color: Color(0xFFE65100), fontSize: 11),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDebugChip(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFE0E0E0),
        borderRadius: BorderRadius.circular(8),
      ),
      child: RichText(
        text: TextSpan(
          children: [
            TextSpan(
              text: '$label: ',
              style: const TextStyle(
                color: Color(0xFF455A64),
                fontSize: 10,
                fontWeight: FontWeight.bold,
              ),
            ),
            TextSpan(
              text: value,
              style: const TextStyle(
                color: Color(0xFF263238),
                fontSize: 10,
                fontFamily: 'monospace',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAutoDisconnectBanner(int remainingSeconds) {
    final mins = (remainingSeconds ~/ 60).toString().padLeft(1, '0');
    final secs = (remainingSeconds % 60).toString().padLeft(2, '0');
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFE0B2),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFFF6F00)),
      ),
      child: Row(
        children: [
          const Icon(Icons.timer, color: Color(0xFFE65100), size: 24),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '⏳ Sẽ tự ngắt VPN sau khi thoát app',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Color(0xFFE65100)),
                ),
                const SizedBox(height: 2),
                Text(
                  'Mở lại app trong $mins:$secs để hủy',
                  style: const TextStyle(fontSize: 12, color: Color(0xFF6D4C41)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusCard(VpnBenhVienService vpn) {
    Color color;
    IconData icon;
    String statusText;
    if (vpn.isConnected) {
      color = Colors.green;
      icon = Icons.verified;
      statusText = 'Đã kết nối VPN';
    } else if (vpn.isConnecting) {
      color = Colors.orange;
      icon = Icons.sync;
      statusText = 'Đang kết nối...';
    } else if (vpn.isError) {
      color = Colors.red;
      icon = Icons.error_outline;
      statusText = 'Lỗi VPN';
    } else {
      color = Colors.grey;
      icon = Icons.vpn_lock_outlined;
      statusText = 'Chưa kết nối';
    }

    return Card(
      color: color.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: color, width: 1.5),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 56, height: 56,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.15),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: color, size: 32),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Trạng thái VPN',
                    style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  Text(statusText,
                    style: TextStyle(color: color, fontSize: 20, fontWeight: FontWeight.bold)),
                  if (vpn.isConnected)
                    const Text('Tới 113.176.81.193:8443 (qua internet)',
                      style: TextStyle(color: Colors.black54, fontSize: 11)),
                  if (vpn.lastError != null && vpn.isError)
                    Text('Lỗi: ${vpn.lastError}',
                      style: const TextStyle(color: Colors.red, fontSize: 11),
                      maxLines: 2, overflow: TextOverflow.ellipsis),
                ],
              ),
            ),
            if (vpn.isConnecting)
              const SizedBox(
                width: 24, height: 24,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
          ],
        ),
      ),
    );
  }

  /// v3.0.93: Form tài khoản
  /// - Nếu dùng default nemk: hiển thị username, ẩn password (không cho xem)
  /// - Nếu dùng "Tài khoản khác": hiển thị form riêng để nhập
  Widget _buildAccountForm(VpnBenhVienService vpn) {
    final isDefault = vpn.isUsingDefaultAccount;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.account_circle, size: 18, color: Color(0xFF0D47A1)),
                SizedBox(width: 6),
                Text('Tài khoản VPN',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 12),
            if (isDefault) _buildDefaultAccountRow() else _buildOtherAccountRow(),
            const SizedBox(height: 6),
            TextButton.icon(
              icon: Icon(
                isDefault ? Icons.person_add : Icons.refresh,
                size: 16,
              ),
              label: Text(isDefault ? 'Dùng tài khoản khác' : 'Quay lại tài khoản mặc định'),
              style: TextButton.styleFrom(
                foregroundColor: const Color(0xFF0D47A1),
                padding: const EdgeInsets.symmetric(horizontal: 4),
              ),
              onPressed: () => _toggleAccount(vpn),
            ),
          ],
        ),
      ),
    );
  }

  /// Row tài khoản mặc định: hiện username, ẩn password hoàn toàn
  Widget _buildDefaultAccountRow() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFE3F2FD),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFF0D47A1).withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          const Icon(Icons.person, color: Color(0xFF0D47A1), size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('nemk',
                    style: TextStyle(
                        fontSize: 14, fontWeight: FontWeight.bold, color: Color(0xFF0D47A1))),
                Text('Tài khoản BS mặc định (pass đã lưu sẵn)',
                    style: TextStyle(fontSize: 11, color: Colors.grey.shade700)),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: const Color(0xFF0D47A1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: const Text('Mặc định',
                style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  /// Form nhập tài khoản khác
  Widget _buildOtherAccountRow() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          controller: _otherUserCtrl,
          decoration: const InputDecoration(
            labelText: 'Tên đăng nhập',
            prefixIcon: Icon(Icons.person),
            border: OutlineInputBorder(),
            isDense: true,
          ),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _otherPassCtrl,
          obscureText: !_showOtherPass,
          decoration: InputDecoration(
            labelText: 'Mật khẩu',
            prefixIcon: const Icon(Icons.lock),
            suffixIcon: IconButton(
              icon: Icon(_showOtherPass ? Icons.visibility_off : Icons.visibility),
              onPressed: () => setState(() => _showOtherPass = !_showOtherPass),
            ),
            border: const OutlineInputBorder(),
            isDense: true,
          ),
        ),
      ],
    );
  }

  Future<void> _toggleAccount(VpnBenhVienService vpn) async {
    final wantOther = vpn.isUsingDefaultAccount;
    if (wantOther) {
      // Chuyển sang "Tài khoản khác"
      setState(() {
        _otherUserCtrl.text = '';
        _otherPassCtrl.text = '';
        _showOtherPass = false;
      });
      // Đánh dấu: bằng cách lưu user rỗng
      await vpn.setCredentials('', '');
    } else {
      // Quay lại default
      await vpn.resetToDefault();
      _otherUserCtrl.clear();
      _otherPassCtrl.clear();
    }
    if (mounted) setState(() {});
  }

  Widget _buildActionButtons(VpnBenhVienService vpn) {
    final isOn = vpn.isConnected || vpn.isConnecting;
    return Row(
      children: [
        Expanded(
          child: ElevatedButton.icon(
            onPressed: (_busy || isOn) ? null : _connect,
            icon: const Icon(Icons.power_settings_new),
            label: const Text('KẾT NỐI'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.green,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: ElevatedButton.icon(
            onPressed: (_busy || !vpn.isConnected) ? null : _disconnect,
            icon: const Icon(Icons.power_off),
            label: const Text('NGẮT'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          ),
        ),
      ],
    );
  }

  /// v3.0.93: Thông tin kết nối gọn
  Widget _buildConfigInfo() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: const [
                Icon(Icons.info_outline, color: Color(0xFF0D47A1), size: 18),
                SizedBox(width: 6),
                Text('Thông tin kết nối',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 10),
            const Text(
              '• VPN tới máy chủ BV Ninh Thuận (qua internet)\n'
              '• Sau khi kết nối: truy cập HIS Pro 172.16.9.6 nội bộ\n'
              '• Auto-disconnect 5 phút khi thoát/thu gọn app\n'
              '• Tích hợp sẵn (openvpn_flutter), không cần OpenVPN Connect',
              style: TextStyle(fontSize: 12, color: Colors.black87, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }
}
