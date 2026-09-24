// lib/screens/network_screen.dart
// AttendanceSuite v2.6.0 - Tab "Network" - IP check, ping ZK, VPN Sophos BV

import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import '../api/pc_api.dart';
import '../data/vpn_service.dart';
import '../data/vpn_credentials.dart';

class NetworkScreen extends StatefulWidget {
  const NetworkScreen({super.key, required this.api});
  final PcApi api;

  @override
  State<NetworkScreen> createState() => _NetworkScreenState();
}

class _NetworkScreenState extends State<NetworkScreen> {
  String? _status;
  bool _loading = false;
  String _mode = 'LAN';
  String _localIp = '-';
  List<String> _interfaces = [];
  List<String> _reachableUrls = [];

  // VPN state
  String _vpnStatus = 'Chưa kết nối';
  String _vpnStage = 'idle';
  bool _vpnBusy = false;
  bool _vpnConnected = false;
  String _ovpnContent = '';
  DateTime? _vpnConnectedAt;
  final _userCtrl = TextEditingController(text: VpnCredentials.username);
  final _passCtrl = TextEditingController(text: VpnCredentials.password);

  // Ping
  final _pingIpCtrl = TextEditingController(text: '172.16.0.31');
  String? _pingResult;

  @override
  void initState() {
    super.initState();
    _refresh();
    _loadOvpn();
    VpnService.initialize();
  }

  @override
  void dispose() {
    _pingIpCtrl.dispose();
    _userCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadOvpn() async {
    try {
      final content = await rootBundle.loadString('assets/vpn/sophos-nemk.ovpn');
      if (!mounted) return;
      setState(() => _ovpnContent = content);
    } catch (e) {
      debugPrint('Load OVPN error: $e');
    }
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _status = null;
    });
    try {
      final d = await widget.api.getDiag();
      setState(() {
        _mode = (d['mode'] as String? ?? ((d['is_vpn'] == true) ? 'VPN' : 'LAN')).toString();
        _localIp = d['local_ip']?.toString() ?? d['primary_ip']?.toString() ?? '-';
        _interfaces = ((d['interfaces'] as List?)?.cast<String>()) ?? [];
        _reachableUrls = ((d['reachable_urls'] as List?)?.cast<String>()) ?? [];
      });
    } catch (e) {
      setState(() => _status = '⚠️ Python chưa sẵn sàng: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _ping(String ip) async {
    setState(() => _pingResult = 'Đang ping $ip...');
    try {
      // Try ZK port 4370 first, fallback ICMP
      final sw = Stopwatch()..start();
      try {
        final socket = await Socket.connect(ip, 4370, timeout: const Duration(seconds: 3));
        sw.stop();
        socket.destroy();
        setState(() => _pingResult = '✅ $ip:4370 OK (${sw.elapsedMilliseconds}ms - ZK port mở)');
        return;
      } on SocketException {
        // ZK port closed, try general socket
      }
      // Try port 80 as fallback
      try {
        final socket = await Socket.connect(ip, 80, timeout: const Duration(seconds: 3));
        sw.stop();
        socket.destroy();
        setState(() => _pingResult = '✅ $ip:80 OK (${sw.elapsedMilliseconds}ms)');
      } catch (_) {
        setState(() => _pingResult = '❌ $ip KHÔNG reachable (timeout)');
      }
    } catch (e) {
      setState(() => _pingResult = '❌ $e');
    }
  }

  Future<void> _vpnConnect() async {
    if (_vpnBusy) return;
    setState(() {
      _vpnBusy = true;
      _vpnStatus = 'Đang kết nối VPN...';
    });
    try {
      if (_ovpnContent.isEmpty) await _loadOvpn();
      if (_ovpnContent.isEmpty) {
        setState(() {
          _vpnStatus = '❌ Không load được file OVPN';
          _vpnBusy = false;
        });
        return;
      }
      final ok = await VpnService.start(
        config: _ovpnContent,
        name: VpnCredentials.profileName,
        username: _userCtrl.text.trim(),
        password: _passCtrl.text,
        onStatusChange: (status, stage) {
          if (!mounted) return;
          setState(() {
            _vpnStatus = status;
            _vpnStage = stage;
            _vpnConnected = stage.toLowerCase().contains('connected');
            if (_vpnConnected) {
              _vpnBusy = false;
              _vpnConnectedAt = DateTime.now();
            }
            if (stage.toLowerCase().contains('error') ||
                stage.toLowerCase().contains('failed') ||
                stage.toLowerCase().contains('disconnect')) {
              _vpnBusy = false;
            }
          });
        },
      );
      if (!ok) {
        setState(() {
          _vpnStatus = '❌ Không bật được VPN';
          _vpnBusy = false;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _vpnStatus = '❌ Lỗi: $e';
        _vpnBusy = false;
      });
    }
  }

  Future<void> _vpnDisconnect() async {
    setState(() {
      _vpnBusy = true;
      _vpnStatus = 'Đang ngắt VPN...';
    });
    await VpnService.stop();
    if (!mounted) return;
    setState(() {
      _vpnStatus = '⚪ Đã ngắt';
      _vpnStage = 'idle';
      _vpnConnected = false;
      _vpnBusy = false;
    });
  }

  Color _vpnColor() {
    if (_vpnConnected) return Colors.greenAccent;
    final s = _vpnStage.toLowerCase();
    if (s.contains('connect') || s.contains('authentic') || s.contains('prepare') ||
        s.contains('assign') || s.contains('resolve') || s.contains('wait_connection')) {
      return Colors.orangeAccent;
    }
    if (s.contains('error') || s.contains('failed')) return Colors.redAccent;
    if (s == 'idle') return Colors.white54;
    return Colors.grey;
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(8),
        children: [
          _header(),
          const SizedBox(height: 8),
          if (_status != null) _statusBox(_status!),

          // ============ Connection mode banner ============
          _modeBanner(),
          const SizedBox(height: 10),

          // ============ VPN Sophos BV ============
          _vpnCard(),
          const SizedBox(height: 10),

          // ============ Local IP + Interfaces ============
          _section('IP & Network Interfaces', icon: Icons.lan, children: [
            _kvRow('Local IP', _localIp, mono: true),
            _kvRow('Server URL', widget.api.baseUrl, mono: true),
            const SizedBox(height: 6),
            const Text('Network Interfaces:', style: TextStyle(fontSize: 11, color: Colors.white60)),
            const SizedBox(height: 4),
            if (_interfaces.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 2),
                child: Text('  (đang tải...)', style: TextStyle(fontSize: 11, color: Colors.white60)),
              )
            else
              ..._interfaces.map((ip) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 1),
                    child: Row(children: [
                      const Text('  • ', style: TextStyle(fontSize: 11, color: Color(0xFF26A69A))),
                      Expanded(child: SelectableText(ip,
                          style: const TextStyle(fontSize: 11, color: Colors.white, fontFamily: 'monospace'))),
                    ]),
                  )),
          ]),
          const SizedBox(height: 10),

          // ============ Reachable URLs ============
          if (_reachableUrls.isNotEmpty)
            _section('Server URLs (Python đã bind)', icon: Icons.cloud_done, children: [
              ..._reachableUrls.map((url) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(children: [
                      const Icon(Icons.link, size: 12, color: Color(0xFF26A69A)),
                      const SizedBox(width: 6),
                      Expanded(child: SelectableText(url,
                          style: const TextStyle(fontSize: 11, color: Color(0xFF26A69A), fontFamily: 'monospace'))),
                    ]),
                  )),
            ]),

          // ============ Ping test ============
          _section('Ping thiết bị (ZK port 4370)', icon: Icons.network_check, children: [
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _pingIpCtrl,
                  style: const TextStyle(fontSize: 13, color: Colors.white, fontFamily: 'monospace'),
                  decoration: const InputDecoration(
                    labelText: 'IP',
                    border: OutlineInputBorder(),
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                  ),
                ),
              ),
              const SizedBox(width: 6),
              ElevatedButton.icon(
                onPressed: () => _ping(_pingIpCtrl.text),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF1976D2),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                ),
                icon: const Icon(Icons.network_check, size: 16),
                label: const Text('Ping', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ]),
            if (_pingResult != null) ...[
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFF37474F),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(_pingResult!,
                    style: const TextStyle(fontSize: 12, color: Colors.white, fontFamily: 'monospace')),
              ),
            ],
          ]),
          const SizedBox(height: 10),

          // ============ Tips cho Sophos VPN ============
          _section('💡 Gợi ý kết nối BV', icon: Icons.lightbulb_outline, children: [
            _bullet('Cùng WiFi BV: phone scan thẳng thiết bị 172.16.x.x'),
            _bullet('Qua VPN Sophos: bấm KẾT NỐI VPN ở trên (native, không cần app ngoài)'),
            _bullet('⚠️ VPN BV chỉ route 171.15.x.x - KHÔNG tự route 172.16.x.x'),
            _bullet('Nếu VPN active mà vẫn không thấy thiết bị → check Sophos gateway có push route 172.16.0.0/16 không'),
            _bullet('Workaround: VPN ON → đợi 5-10s tunnel ổn → bấm QUÉT lại'),
          ]),

          const SizedBox(height: 80),
        ],
      ),
    );
  }

  Widget _modeBanner() {
    final isVpn = _mode.toUpperCase() == 'VPN';
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: isVpn ? const Color(0xFFE65100).withValues(alpha: 0.3) : const Color(0xFF1B5E20).withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: isVpn ? Colors.orange : Colors.greenAccent, width: 0.5),
      ),
      child: Row(children: [
        Icon(
          isVpn ? Icons.vpn_lock : Icons.wifi,
          color: isVpn ? Colors.orangeAccent : Colors.greenAccent,
          size: 22,
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Mode: ${_mode.toUpperCase()}',
                style: const TextStyle(fontSize: 14, color: Colors.white, fontWeight: FontWeight.bold)),
            Text(
              isVpn
                  ? '⚠️ Qua VPN tunnel (Sophos / OpenVPN)'
                  : '✅ Trực tiếp LAN (cùng WiFi BV)',
              style: const TextStyle(fontSize: 10, color: Colors.white70),
            ),
          ]),
        ),
      ]),
    );
  }

  Widget _vpnCard() {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF37474F),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: _vpnColor().withValues(alpha: 0.5), width: 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Header
        Row(children: [
          Icon(Icons.vpn_lock, color: _vpnColor(), size: 18),
          const SizedBox(width: 6),
          const Text('VPN BỆNH VIỆN (SOPHOS)',
              style: TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.bold)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: _vpnColor().withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(2),
            ),
            child: Text(
              _vpnConnected ? 'ĐÃ KẾT NỐI' : (_vpnBusy ? 'ĐANG...' : 'NGẮT'),
              style: TextStyle(fontSize: 10, color: _vpnColor(), fontWeight: FontWeight.bold),
            ),
          ),
        ]),
        const SizedBox(height: 6),
        // Status text
        Text(_vpnStatus,
            style: TextStyle(fontSize: 11, color: _vpnColor()),
            maxLines: 2, overflow: TextOverflow.ellipsis),
        if (_vpnConnectedAt != null)
          Text('Kết nối lúc ${_fmtTime(_vpnConnectedAt!)}',
              style: const TextStyle(fontSize: 10, color: Colors.white54)),
        Text('Stage: $_vpnStage',
            style: const TextStyle(fontSize: 10, color: Colors.white38, fontFamily: 'monospace')),
        const SizedBox(height: 8),
        // Username/Password
        Row(children: [
          Expanded(
            child: TextField(
              controller: _userCtrl,
              style: const TextStyle(fontSize: 12, color: Colors.white, fontFamily: 'monospace'),
              decoration: const InputDecoration(
                labelText: 'Username',
                isDense: true,
                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                border: OutlineInputBorder(),
                labelStyle: TextStyle(fontSize: 11),
              ),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: TextField(
              controller: _passCtrl,
              obscureText: true,
              style: const TextStyle(fontSize: 12, color: Colors.white, fontFamily: 'monospace'),
              decoration: const InputDecoration(
                labelText: 'Password',
                isDense: true,
                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                border: OutlineInputBorder(),
                labelStyle: TextStyle(fontSize: 11),
              ),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        // Connect/Disconnect
        SizedBox(
          width: double.infinity,
          height: 40,
          child: FilledButton.icon(
            onPressed: _vpnBusy ? null : (_vpnConnected ? _vpnDisconnect : _vpnConnect),
            icon: Icon(_vpnConnected ? Icons.stop_circle : Icons.play_circle_fill, size: 20),
            label: Text(
              _vpnBusy ? 'ĐANG XỬ LÝ...' : (_vpnConnected ? 'NGẮT VPN' : 'KẾT NỐI VPN'),
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
            ),
            style: FilledButton.styleFrom(
              backgroundColor: _vpnConnected ? Colors.red.shade700 : const Color(0xFF26A69A),
              foregroundColor: Colors.white,
            ),
          ),
        ),
        const SizedBox(height: 6),
        const Text('• Server: 113.176.81.193:8443  • Profile: sophos-nemk.ovpn',
            style: TextStyle(fontSize: 10, color: Colors.white54, fontFamily: 'monospace')),
      ]),
    );
  }

  String _fmtTime(DateTime t) {
    return '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}:${t.second.toString().padLeft(2, '0')}';
  }

  Widget _statusBox(String status) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(color: const Color(0xFF455A64), borderRadius: BorderRadius.circular(4)),
      child: Text(status, style: const TextStyle(fontSize: 11, color: Colors.white)),
    );
  }

  Widget _header() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
      child: Row(children: [
        const Icon(Icons.network_check, size: 16, color: Color(0xFF26A69A)),
        const SizedBox(width: 6),
        const Text('NETWORK & IP',
            style: TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.bold)),
        const Spacer(),
        IconButton(
          icon: const Icon(Icons.refresh, size: 18),
          color: Colors.white,
          onPressed: _loading ? null : _refresh,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
        ),
      ]),
    );
  }

  Widget _section(String title, {IconData? icon, required List<Widget> children}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: const Color(0xFF37474F), borderRadius: BorderRadius.circular(4)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: const Color(0xFF26A69A)),
            const SizedBox(width: 6),
          ],
          Text(title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Color(0xFF26A69A))),
        ]),
        const SizedBox(height: 6),
        ...children,
      ]),
    );
  }

  Widget _kvRow(String k, String v, {bool mono = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: 100, child: Text('$k:', style: const TextStyle(fontSize: 12, color: Colors.white60))),
        Expanded(child: SelectableText(v,
            style: TextStyle(fontSize: 12, color: Colors.white, fontFamily: mono ? 'monospace' : null))),
      ]),
    );
  }

  Widget _bullet(String text) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('• ', style: TextStyle(fontSize: 11, color: Color(0xFF26A69A))),
        Expanded(child: Text(text, style: const TextStyle(fontSize: 11, color: Colors.white))),
      ]),
    );
  }
}
