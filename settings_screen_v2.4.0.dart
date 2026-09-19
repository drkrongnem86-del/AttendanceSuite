// screens/settings_screen.dart
// Settings tab - LIGHT theme, embedded server status, VPN Bệnh viện, PC-Relay
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../main.dart';
import '../vpn/vpn_manager.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});
  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String _ovpnConfig = '';
  String _vpnPassword = '';
  bool _obscurePwd = true;
  // v2.4.0: PC-Relay controls
  final TextEditingController _relayUrlCtrl = TextEditingController();
  bool _useRelay = false;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  @override
  void dispose() {
    _relayUrlCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _ovpnConfig = prefs.getString('vpn_ovpn_config') ?? '';
      _vpnPassword = prefs.getString('vpn_password') ?? '';
      // v2.4.0: Load relay config
      _relayUrlCtrl.text = prefs.getString('relay_server_url') ?? '';
      _useRelay = prefs.getBool('relay_enabled') ?? false;
    });
  }

  Future<void> _saveSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('vpn_ovpn_config', _ovpnConfig);
    await prefs.setString('vpn_password', _vpnPassword);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã lưu'), duration: Duration(seconds: 1)),
      );
    }
  }

  Future<void> _connectVpn() async {
    final state = context.appState;
    // v2.3.0: Use MethodChannel-based connectOneTap (VpnService foreground)
    final res = await state.vpn.connectOneTap();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(res.message),
      backgroundColor: res.success ? Colors.green : Colors.red,
      duration: Duration(seconds: 3),
    ));
    setState(() {});
  }

  Future<void> _disconnectVpn() async {
    await context.appState.vpn.disconnect();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final state = context.appState;
    final vpnStatus = state.vpn.status;

    return Container(
      color: const Color(0xFFF5F7FA),
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          // ===== Server embedded (light theme card) =====
          Row(children: [
            const Icon(Icons.medical_services, color: Color(0xFF00695C), size: 20),
            const SizedBox(width: 6),
            const Text('Server embedded',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF263238))),
          ]),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE0E0E0)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _infoRow('Status', state.serverRunning ? '🟢 Đang chạy' : '🔴 Chưa chạy'),
                _infoRow('URL', state.serverUrl),
                _infoRow('Local IP', state.localIp),
                _infoRow('Port', '${state.serverPort}'),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: () async {
                        await state.restartServer();
                        if (mounted) setState(() {});
                      },
                      icon: const Icon(Icons.refresh, size: 14),
                      label: const Text('Restart'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF00897B),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 8),
                      ),
                    ),
                  ),
                ]),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ===== VPN Bệnh viện =====
          Row(children: [
            const Icon(Icons.vpn_lock, color: Color(0xFF1976D2), size: 20),
            const SizedBox(width: 6),
            const Text('VPN Bệnh viện',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF263238))),
          ]),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE0E0E0)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // VPN status
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: vpnStatus.connected ? Colors.green.shade50 : const Color(0xFFFAFAFA),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(children: [
                    Icon(
                      vpnStatus.connected ? Icons.lock_open : Icons.lock,
                      color: vpnStatus.connected ? Colors.green.shade700 : const Color(0xFF90A4AE),
                      size: 24,
                    ),
                    const SizedBox(width: 8),
                    const Text('Trạng thái VPN',
                      style: TextStyle(fontSize: 13, color: Color(0xFF455A64))),
                    const Spacer(),
                    Text(
                      vpnStatus.connected ? 'Đã kết nối' : 'Chưa kết nối',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: vpnStatus.connected ? Colors.green.shade700 : const Color(0xFF90A4AE),
                      ),
                    ),
                  ]),
                ),
                const SizedBox(height: 12),
                // VPN account card
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE3F2FD),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: const Color(0xFFBBDEFB)),
                  ),
                  child: Row(children: [
                    const Icon(Icons.person, color: Color(0xFF1976D2), size: 24),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(VpnManager.DEFAULT_USERNAME,
                            style: const TextStyle(fontSize: 14,
                              fontWeight: FontWeight.bold, color: Color(0xFF263238))),
                          const Text('Tài khoản BS mặc định (pass đã lưu sẵn)',
                            style: TextStyle(fontSize: 10, color: Color(0xFF607D8B))),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1976D2),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Text('Mặc định',
                        style: TextStyle(fontSize: 10, color: Colors.white)),
                    ),
                  ]),
                ),
                const SizedBox(height: 8),
                Row(children: [
                  const Icon(Icons.person_add, color: Color(0xFF1976D2), size: 16),
                  const SizedBox(width: 4),
                  Text('Dùng tài khoản khác',
                    style: const TextStyle(fontSize: 12, color: Color(0xFF1976D2))),
                ]),
                const SizedBox(height: 12),

                // Connect/Disconnect
                Row(children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: vpnStatus.connected ? null : _connectVpn,
                      icon: const Icon(Icons.power, size: 16),
                      label: const Text('KẾT NỐI',
                        style: TextStyle(fontWeight: FontWeight.bold)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: vpnStatus.connected
                          ? const Color(0xFFBDBDBD)
                          : const Color(0xFF2E7D32),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: !vpnStatus.connected ? null : _disconnectVpn,
                      icon: const Icon(Icons.power_off, size: 16),
                      label: const Text('NGẮT',
                        style: TextStyle(fontWeight: FontWeight.bold)),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF1976D2),
                        side: const BorderSide(color: Color(0xFF1976D2)),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                ]),
                const SizedBox(height: 12),
                // Connection info
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE3F2FD),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: const [
                      Text('ℹ Thông tin kết nối',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Color(0xFF263238))),
                      SizedBox(height: 6),
                      Text('• VPN tới máy chủ BV Ninh Thuận (qua internet)',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                      Text('• Sau khi kết nối: truy cập HIS Pro 172.16.9.6 nội bộ',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                      Text('• Auto-disconnect TẮT mặc định (v2.4.0: VPN không tự tắt khi rời app)',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                      Text('• v2.4.0: Copy HIS Mobile openvpn_flutter pattern, không custom service',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                      Text('• Bypass Sophos: bật PC-Relay trỏ tới PC EXE',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                    ],
                  ),
                ),
                if (vpnStatus.lastError != null) ...[
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: Colors.red.shade50,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: Colors.red.shade200),
                    ),
                    child: Text('Lỗi: ${vpnStatus.lastError}',
                      style: const TextStyle(color: Color(0xFFC62828), fontSize: 11)),
                  ),
                ],
                const SizedBox(height: 12),

                // Advanced config
                ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  childrenPadding: const EdgeInsets.all(8),
                  title: const Text('⚙️ Cấu hình nâng cao (.ovpn file)',
                    style: TextStyle(fontSize: 13, color: Color(0xFF263238))),
                  children: [
                    TextField(
                      maxLines: 6,
                      decoration: const InputDecoration(
                        labelText: 'Paste nội dung file .ovpn từ BV (có certs)',
                        border: OutlineInputBorder(),
                      ),
                      style: const TextStyle(fontSize: 10, fontFamily: 'monospace'),
                      controller: TextEditingController(text: _ovpnConfig),
                      onChanged: (v) => _ovpnConfig = v,
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      decoration: InputDecoration(
                        labelText: 'Mật khẩu VPN',
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          icon: Icon(_obscurePwd ? Icons.visibility_off : Icons.visibility),
                          onPressed: () => setState(() => _obscurePwd = !_obscurePwd),
                        ),
                      ),
                      obscureText: _obscurePwd,
                      controller: TextEditingController(text: _vpnPassword),
                      onChanged: (v) => _vpnPassword = v,
                    ),
                    const SizedBox(height: 8),
                    Row(children: [
                      OutlinedButton.icon(
                        onPressed: _saveSettings,
                        icon: const Icon(Icons.save, size: 14),
                        label: const Text('Lưu'),
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton.icon(
                        onPressed: () => setState(() => _ovpnConfig = ''),
                        icon: const Icon(Icons.delete, size: 14),
                        label: const Text('Xóa'),
                      ),
                    ]),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ===== PC-Relay (bypass Sophos VPN) - v2.4.0 =====
          Row(children: [
            const Icon(Icons.cast_for_education, color: Color(0xFF00897B), size: 20),
            const SizedBox(width: 6),
            const Text('PC-Relay (bypass Sophos)',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF263238))),
          ]),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE0E0E0)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: _useRelay ? Colors.green.shade50 : const Color(0xFFFAFAFA),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(children: [
                    Icon(
                      _useRelay ? Icons.link : Icons.link_off,
                      color: _useRelay ? Colors.green.shade700 : const Color(0xFF90A4AE),
                      size: 24,
                    ),
                    const SizedBox(width: 8),
                    const Text('Relay mode',
                      style: TextStyle(fontSize: 13, color: Color(0xFF455A64))),
                    const Spacer(),
                    Switch(
                      value: _useRelay,
                      activeColor: Colors.green,
                      onChanged: (v) async {
                        final state = context.appState;
                        await state.setRelayConfig(enabled: v);
                        setState(() => _useRelay = v);
                        if (!mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(v
                              ? '🟢 Đã bật relay → ${_relayUrlCtrl.text.isNotEmpty ? _relayUrlCtrl.text : "(chưa có URL)"}'
                              : '⚪ Đã tắt relay'),
                            duration: const Duration(seconds: 3),
                          ),
                        );
                      },
                    ),
                  ]),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _relayUrlCtrl,
                  decoration: const InputDecoration(
                    labelText: 'PC EXE URL',
                    hintText: 'http://192.168.1.100:8080',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                  style: const TextStyle(fontSize: 13),
                  onChanged: (_) {},
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: () async {
                        final state = context.appState;
                        final url = _relayUrlCtrl.text.trim();
                        if (url.isEmpty) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Nhập URL trước')),
                          );
                          return;
                        }
                        // Lưu + bật luôn
                        await state.setRelayConfig(url: url, enabled: true);
                        setState(() => _useRelay = true);
                        final r = await state.testRelay(url);
                        if (!mounted) return;
                        if (r['ok'] == true) {
                          final data = r['data'] as Map<String, dynamic>;
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('✅ Kết nối tới $url OK\n'
                                'Version: ${data['version'] ?? '?'}, Devices: ${data['devices_count'] ?? '?'}'),
                              duration: const Duration(seconds: 4),
                              backgroundColor: Colors.green.shade700,
                            ),
                          );
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('❌ Không kết nối được $url\n${r['error']}'),
                              duration: const Duration(seconds: 5),
                              backgroundColor: Colors.red.shade700,
                            ),
                          );
                        }
                      },
                      icon: const Icon(Icons.save, size: 14),
                      label: const Text('Lưu + Test'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF00897B),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 10),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () async {
                        final state = context.appState;
                        final r = await state.autoDiscoverRelay();
                        if (!mounted) return;
                        if (r['ok'] == true) {
                          final url = r['url'] as String;
                          await state.setRelayConfig(url: url, enabled: true);
                          setState(() {
                            _relayUrlCtrl.text = url;
                            _useRelay = true;
                          });
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('🔍 Tìm thấy PC EXE: $url'),
                              duration: const Duration(seconds: 4),
                              backgroundColor: Colors.green.shade700,
                            ),
                          );
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('❌ ${r['error']}'),
                              duration: const Duration(seconds: 4),
                              backgroundColor: Colors.orange.shade700,
                            ),
                          );
                        }
                      },
                      icon: const Icon(Icons.search, size: 14),
                      label: const Text('Auto-discover'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF00897B),
                        side: const BorderSide(color: Color(0xFF00897B)),
                        padding: const EdgeInsets.symmetric(vertical: 10),
                      ),
                    ),
                  ),
                ]),
                const SizedBox(height: 12),
                const Text('Known BV PCs (chạm để chọn nhanh):',
                  style: TextStyle(fontSize: 11, color: Color(0xFF607D8B))),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6, runSpacing: 6,
                  children: context.appState.knownBvPcs
                    .map((u) => ActionChip(
                      label: Text(u.replaceFirst('http://', ''),
                        style: const TextStyle(fontSize: 10)),
                      onPressed: () {
                        setState(() => _relayUrlCtrl.text = u);
                      },
                      backgroundColor: const Color(0xFFE0F2F1),
                      side: const BorderSide(color: Color(0xFFB2DFDB)),
                    ))
                    .toList(),
                ),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE0F2F1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('ℹ PC-Relay là gì?',
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Color(0xFF00695C))),
                      SizedBox(height: 4),
                      Text('• Bật để phone PROXY các request sang PC chạy EXE',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                      Text('• PC có VPN sẵn → reach được thiết bị 172.16.x.x',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                      Text('• Không cần bật VPN trên phone (bypass Sophos)',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                      Text('• Auto-discover quét các IP BV quen thuộc',
                          style: TextStyle(fontSize: 11, color: Color(0xFF455A64))),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ===== Info =====
          Row(children: [
            const Icon(Icons.info, color: Color(0xFF455A64), size: 20),
            const SizedBox(width: 6),
            const Text('Thông tin',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF263238))),
          ]),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE0E0E0)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                _InfoRowStatic('Phiên bản', '2.4.0+31 (v2.4.0)'),
                _InfoRowStatic('Tác giả', 'Dr. Nểm - BVĐK Ninh Thuận'),
                _InfoRowStatic('Copyright', '© 2026 Dr. Nểm'),
                _InfoRowStatic('GitHub', 'github.com/drkrongnem86-del/AttendanceSuite'),
                _InfoRowStatic('Kiến trúc', 'Self-hosted Dart HTTP server (no Windows needed)'),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Widget _infoRow(String k, String v) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(width: 90,
        child: Text(k, style: const TextStyle(color: Color(0xFF607D8B), fontSize: 12))),
      Expanded(child: Text(v, style: const TextStyle(
        fontSize: 12, fontWeight: FontWeight.w500, color: Color(0xFF263238)))),
    ]),
  );
}

class _InfoRowStatic extends StatelessWidget {
  final String label;
  final String value;
  const _InfoRowStatic(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: 90,
          child: Text(label, style: const TextStyle(color: Color(0xFF607D8B), fontSize: 12))),
        Expanded(child: Text(value, style: const TextStyle(
          fontSize: 12, fontWeight: FontWeight.w500, color: Color(0xFF263238)))),
      ]),
    );
  }
}
