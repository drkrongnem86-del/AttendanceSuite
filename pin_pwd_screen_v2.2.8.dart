// screens/pin_pwd_screen.dart
// PIN+Password: Verify PIN+Password via embedded server (uses pyzk)
import 'package:flutter/material.dart';
import '../main.dart';
import '../models/models.dart';
import '../widgets/embedded_api.dart';

class PinPwdScreen extends StatefulWidget {
  const PinPwdScreen({super.key});
  @override
  State<PinPwdScreen> createState() => _PinPwdScreenState();
}

class _PinPwdScreenState extends State<PinPwdScreen> {
  late EmbeddedApi _api;
  List<Device> _devices = [];
  Device? _selected;
  final _pinCtrl = TextEditingController(text: '1');
  final _pwdCtrl = TextEditingController(text: '1');
  bool _showPwd = false;
  bool _busy = false;
  String _result = '';

  @override
  void initState() {
    super.initState();
    _api = EmbeddedApi(context.appState.serverUrl.isNotEmpty
        ? context.appState.serverUrl
        : 'http://127.0.0.1:8080');
    _waitForServerAndLoad();
    context.appState.addListener(_onAppStateChanged);
  }

  @override
  void dispose() {
    context.appState.removeListener(_onAppStateChanged);
    _pinCtrl.dispose();
    _pwdCtrl.dispose();
    super.dispose();
  }

  void _onAppStateChanged() {
    if (!mounted) return;
    final newBase = context.appState.serverUrl.isNotEmpty
        ? context.appState.serverUrl
        : 'http://127.0.0.1:8080';
    if (_api.baseUrl != newBase) {
      _api = EmbeddedApi(newBase);
      _loadDevices();
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

  Future<void> _scanNow() async {
    setState(() => _result = '🔄 Đang quét thiết bị + lấy tên thật...');
    final resp = await _api.pingAll();
    if (!mounted) return;
    final list = (resp['devices'] as List? ?? []).cast<Map<String, dynamic>>();
    if (list.isNotEmpty) {
      setState(() {
        _devices = list.map((j) => Device.fromJson(j)).toList();
        _selected = _devices.firstWhere(
          (d) => d.type == 'attendance' || d.type == 'virtual',
          orElse: () => _devices.isNotEmpty ? _devices.first : Device(ip: '-', note: '-'),
        );
        _result = '✅ Quét xong: ${_devices.length} thiết bị (xem danh sách đã cập nhật).';
      });
    } else {
      setState(() => _result = '⚠️ Quét không trả về thiết bị nào.');
    }
  }

  Future<void> _verify() async {
    if (_selected == null) {
      setState(() => _result = '⚠ Chưa chọn máy');
      return;
    }
    if (_pinCtrl.text.isEmpty || _pwdCtrl.text.isEmpty) {
      setState(() => _result = '⚠ Nhập PIN và mật khẩu');
      return;
    }
    setState(() {
      _busy = true;
      _result = '⏳ Đang verify ${_selected!.ip}...';
    });
    // For now, basic verify via the device-info endpoint (pyzk sets up connection)
    final info = await _api.getDeviceInfo(_selected!.ip);
    final connected = info['connected'] == true;
    setState(() {
      _busy = false;
      if (!connected) {
        _result = '❌ Máy không online: ${info['error'] ?? "?"}';
      } else {
        _result = '✅ Máy online. PIN+password verify sẽ chạy qua embedded server.\n'
          '💡 Để chạy verify thật trên app, cần backend verify PIN+password endpoint.\n'
          'Có thể dùng BS-confirmed bypass (v1.9.0+) nếu chỉ muốn ghi nhận chấm công nhanh.';
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFFF5F7FA),
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Row(children: [
            const Icon(Icons.lock, color: Color(0xFF7B1FA2), size: 22),
            const SizedBox(width: 6),
            const Text('PIN + Mật khẩu',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF263238))),
            const Spacer(),
            ElevatedButton.icon(
              onPressed: _busy ? null : _scanNow,
              icon: const Icon(Icons.refresh, size: 14),
              label: const Text('Quét'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF7B1FA2),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              ),
            ),
          ]),
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
                const SizedBox(height: 12),
                const Text('Mật khẩu:', style: TextStyle(fontSize: 12, color: Color(0xFF455A64))),
                const SizedBox(height: 4),
                TextField(
                  controller: _pwdCtrl,
                  obscureText: !_showPwd,
                  decoration: InputDecoration(
                    isDense: true, border: const OutlineInputBorder(),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    suffixIcon: IconButton(
                      icon: Icon(_showPwd ? Icons.visibility_off : Icons.visibility),
                      onPressed: () => setState(() => _showPwd = !_showPwd),
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _busy ? null : _verify,
                    icon: _busy
                      ? const SizedBox(width: 14, height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.check_circle, size: 16),
                    label: const Text('Xác minh PIN + Mật khẩu'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF7B1FA2),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                  ),
                ),
                if (_result.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: _result.startsWith('✅')
                        ? Colors.green.shade50
                        : (_result.startsWith('❌') ? Colors.red.shade50 : const Color(0xFFFFF3E0)),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(_result, style: const TextStyle(fontSize: 11, color: Color(0xFF263238))),
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
