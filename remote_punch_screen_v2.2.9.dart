// screens/remote_punch_screen.dart
// Từ xa: Chấm công từ xa - tạo manual punch qua embedded server
import 'package:flutter/material.dart';
import '../main.dart';
import '../models/models.dart';
import '../widgets/embedded_api.dart';

class RemotePunchScreen extends StatefulWidget {
  const RemotePunchScreen({super.key});
  @override
  State<RemotePunchScreen> createState() => _RemotePunchScreenState();
}

class _RemotePunchScreenState extends State<RemotePunchScreen> {
  late EmbeddedApi _api;
  List<Device> _devices = [];
  Device? _selected;
  final _pinCtrl = TextEditingController(text: '1');
  String _punchType = 'in';
  String _verifyMode = 'fp';
  String _status = '';
  bool _running = false;
  bool _busy = false;  // v2.2.9: also covers VPN banner button

  @override
  void initState() {
    super.initState();
    _api = EmbeddedApi(context.appState.serverUrl.isNotEmpty
        ? context.appState.serverUrl
        : 'http://127.0.0.1:8080');
    // Wait for server to be ready, then load devices with retry
    _waitForServerAndLoad();
    context.appState.addListener(_onAppStateChanged);
  }

  @override
  void dispose() {
    context.appState.removeListener(_onAppStateChanged);
    _pinCtrl.dispose();
    super.dispose();
  }

  void _onAppStateChanged() {
    // If serverUrl changed (VPN connected, IP changed, server restarted), reload
    if (!_running && mounted) {
      final newBase = context.appState.serverUrl.isNotEmpty
          ? context.appState.serverUrl
          : 'http://127.0.0.1:8080';
      if (_api.baseUrl != newBase) {
        _api = EmbeddedApi(newBase);
        _loadDevices();
      }
    }
  }

  Future<void> _waitForServerAndLoad() async {
    final sw = Stopwatch()..start();
    while (!context.appState.serverRunning && sw.elapsed < const Duration(seconds: 5)) {
      await Future.delayed(const Duration(milliseconds: 100));
    }
    if (!mounted) return;
    await _loadDevices();
  }

  Future<void> _loadDevices() async {
    try {
      final devs = await _api.getDevices();
      if (!mounted) return;
      setState(() {
        _devices = devs;
        if (_selected == null || !devs.any((d) => d.ip == _selected!.ip)) {
          _selected = devs.firstWhere(
            (d) => d.type == 'attendance' || d.type == 'virtual',
            orElse: () => devs.isNotEmpty ? devs.first : Device(ip: '-', note: '-'),
          );
        }
      });
    } catch (_) {}
  }

  /// v2.2.9: VPN status banner - tells user why devices may be unreachable
  /// and offers 1-tap VPN connect.
  Widget _buildVpnBanner(BuildContext context) {
    final vpnConnected = context.appState.vpn.status.connected;
    if (vpnConnected) {
      return Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: Colors.green.shade50,
          border: Border.all(color: Colors.green.shade300),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Row(children: const [
          Icon(Icons.vpn_lock, color: Colors.green, size: 16),
          SizedBox(width: 6),
          Expanded(
            child: Text(
              '✅ VPN Sophos đã kết nối. Thiết bị 172.16.x đang truy cập được.',
              style: TextStyle(color: Colors.green, fontSize: 11),
            ),
          ),
        ]),
      );
    }
    // VPN not connected - prominent banner
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3E0),
        border: Border.all(color: Colors.orange.shade400),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.warning_amber, color: Colors.orange, size: 16),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                '⚠️ CHƯA CÓ VPN — thiết bị 172.16.x KHÔNG truy cập được từ mobile data.',
                style: TextStyle(color: Colors.orange.shade800, fontSize: 11, fontWeight: FontWeight.bold),
              ),
            ),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _busy ? null : () async {
                  setState(() => _busy = true);
                  final res = await context.appState.vpn.connectOneTap();
                  if (!context.mounted) return;
                  setState(() => _busy = false);
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('${res.success ? "✅" : "❌"} ${res.message}'),
                      duration: const Duration(seconds: 6),
                      backgroundColor: res.success ? Colors.green.shade700 : Colors.red.shade700,
                    ),
                  );
                },
                icon: const Icon(Icons.vpn_key, size: 14),
                label: const Text('Kết nối VPN (1 chạm)'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orange.shade700,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                ),
              ),
            ),
            const SizedBox(width: 6),
            OutlinedButton(
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text(
                      'Khác EXE Windows: APK cần VPN tunnel vì điện thoại ở mobile data (171.15.x), không phải BV LAN.',
                    ),
                    duration: Duration(seconds: 5),
                  ),
                );
              },
              child: const Text('Tại sao?'),
            ),
          ]),
        ],
      ),
    );
  }

  Future<void> _doPunch() async {
    if (_selected == null) return;
    if (_pinCtrl.text.isEmpty) {
      setState(() => _status = '❌ Vui lòng nhập PIN');
      return;
    }
    setState(() {
      _running = true;
      _status = '⏳ Đang chấm công ${_selected!.ip}...';
    });
    final mode = _verifyMode == 'fp' ? 1 : (_verifyMode == 'pwd' ? 0 : (_verifyMode == 'card' ? 2 : 1));
    final punchNum = _punchType == 'in' ? 0 : 1;
    final now = DateTime.now();
    final ts =
        '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')} '
        '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}:${now.second.toString().padLeft(2, '0')}';
    try {
      final res = await _api.injectAttlog(
        ip: _selected!.ip,
        pin: _pinCtrl.text,
        timestamp: ts,
        status: 0,
        punch: punchNum,
        verifyMode: mode,
        marker: 'APK_REAL_PUNCH',
      );
      setState(() {
        _running = false;
        if (res['ok'] == true) {
          _status = '✅ ATTLOG đã ghi lên ${_selected!.ip}\n'
              'PIN=${_pinCtrl.text} | Loại=${_punchType == "in" ? "Check-In" : "Check-Out"} | '
              'Verify=${_verifyMode.toUpperCase()} | TS=$ts\n'
              'ATTLOG count: ${res['before_count']} → ${res['after_count']} (+1)\n'
              'Restart: ${res['restarted'] == true ? 'Có' : 'Không'} - Máy sẽ reboot sau ~30s';
        } else {
          _status = '❌ ${res['error'] ?? 'unknown error'}';
        }
      });
    } catch (e) {
      setState(() {
        _running = false;
        _status = '❌ Lỗi: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFFF5F7FA),
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Row(children: [
            const Icon(Icons.cloud_upload, color: Color(0xFF1976D2), size: 22),
            const SizedBox(width: 6),
            const Text('Chấm công từ xa',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF263238))),
          ]),
          const SizedBox(height: 8),
          // v2.2.9: VPN status banner - shows why devices may not be reachable
          _buildVpnBanner(context),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFE3F2FD),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFBBDEFB)),
            ),
            child: const Text(
              '✅ REAL PUNCH via CVE-2023-3941 (port 4370): Ghi ATTLOG thật lên máy ZK X628 PRO FW 6.60.\n'
              'Quy trình: Download ZKDB.db (HTTP fallback → protocol READFILE+READ_CHUNK) → INSERT row → Upload → Reboot.\n'
              '⚠️ Trong ~30s reboot, NV không chấm công được - sẽ được queue và xử lý sau.',
              style: TextStyle(fontSize: 11, color: Color(0xFF1976D2)),
            ),
          ),
          const SizedBox(height: 12),
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
                const Text('Thiết bị:', style: TextStyle(fontSize: 12, color: Color(0xFF455A64))),
                const SizedBox(height: 6),
                DropdownButton<Device>(
                  isExpanded: true,
                  value: _selected,
                  items: _devices.map((d) {
                    return DropdownMenuItem(
                      value: d,
                      child: Text('${d.ip} · ${d.note}', style: const TextStyle(fontSize: 12)),
                    );
                  }).toList(),
                  onChanged: (v) => setState(() => _selected = v),
                ),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Mã NV (PIN):', style: TextStyle(fontSize: 12, color: Color(0xFF455A64))),
                      const SizedBox(height: 4),
                      TextField(
                        controller: _pinCtrl,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          isDense: true, border: OutlineInputBorder(),
                          contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                        ),
                      ),
                    ],
                  )),
                  const SizedBox(width: 10),
                  Expanded(child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Loại chấm:', style: TextStyle(fontSize: 12, color: Color(0xFF455A64))),
                      const SizedBox(height: 4),
                      DropdownButton<String>(
                        isExpanded: true,
                        value: _punchType,
                        items: const [
                          DropdownMenuItem(value: 'in', child: Text('Check-In (Vào)')),
                          DropdownMenuItem(value: 'out', child: Text('Check-Out (Ra)')),
                        ],
                        onChanged: (v) => setState(() => _punchType = v!),
                      ),
                    ],
                  )),
                ]),
                const SizedBox(height: 10),
                const Text('Phương thức:', style: TextStyle(fontSize: 12, color: Color(0xFF455A64))),
                const SizedBox(height: 4),
                DropdownButton<String>(
                  isExpanded: true,
                  value: _verifyMode,
                  items: const [
                    DropdownMenuItem(value: 'fp', child: Text('Vân tay (FP)')),
                    DropdownMenuItem(value: 'pwd', child: Text('Mật khẩu (PWD)')),
                    DropdownMenuItem(value: 'card', child: Text('Thẻ (CARD)')),
                  ],
                  onChanged: (v) => setState(() => _verifyMode = v!),
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _running ? null : _doPunch,
                    icon: _running
                      ? const SizedBox(width: 14, height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.send, size: 16),
                    label: const Text('Chấm công từ xa'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF2E7D32),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                  ),
                ),
                if (_status.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: _status.startsWith('✅')
                        ? Colors.green.shade50
                        : (_status.startsWith('❌') ? Colors.red.shade50 : const Color(0xFFFFF3E0)),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(_status, style: const TextStyle(fontSize: 11, color: Color(0xFF263238))),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
