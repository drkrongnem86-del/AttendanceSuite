// screens/security_screen.dart
// Bảo mật: Scan all devices, show ports/firmware/security info
import 'package:flutter/material.dart';
import '../main.dart';
import '../models/models.dart';
import '../widgets/embedded_api.dart';

class SecurityScreen extends StatefulWidget {
  const SecurityScreen({super.key});
  @override
  State<SecurityScreen> createState() => _SecurityScreenState();
}

class _SecurityScreenState extends State<SecurityScreen> {
  late EmbeddedApi _api;
  List<Device> _devices = [];
  bool _scanning = false;
  String _status = 'Bấm "Quét tất cả" để kiểm tra';
  int _online = 0;
  int _offline = 0;
  int _webExposed = 0;

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
    super.dispose();
  }

  void _onAppStateChanged() {
    if (!mounted) return;
    final newBase = context.appState.serverUrl.isNotEmpty
        ? context.appState.serverUrl
        : 'http://127.0.0.1:8080';
    if (_api.baseUrl != newBase) {
      _api = EmbeddedApi(newBase);
      _load();
    }
  }

  Future<void> _waitForServerAndLoad() async {
    final sw = Stopwatch()..start();
    while (!context.appState.serverRunning && sw.elapsed < const Duration(seconds: 5)) {
      await Future.delayed(const Duration(milliseconds: 100));
    }
    if (!mounted) return;
    await _load();
  }

  Future<void> _load() async {
    try {
      final devs = await _api.getDevices();
      if (!mounted) return;
      setState(() => _devices = devs);
    } catch (_) {}
  }

  Future<void> _scan() async {
    setState(() {
      _scanning = true;
      _status = '🔄 Đang quét tất cả thiết bị...';
    });
    final resp = await _api.pingAll();
    final list = (resp['devices'] as List? ?? []);
    int online = 0;
    int offline = 0;
    for (final j in list) {
      if (j['online'] == true) online++;
      else offline++;
    }
    setState(() {
      _devices = list.map((j) => Device.fromJson(j as Map<String, dynamic>)).toList();
      _scanning = false;
      _online = online;
      _offline = offline;
      _webExposed = _devices.where((d) => d.ip.startsWith('172.16.254') || d.ip.startsWith('172.16.200')).length;
      _status = '✅ Quét xong: $online online, $offline offline';
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
            const Icon(Icons.security, color: Color(0xFFD32F2F), size: 22),
            const SizedBox(width: 6),
            const Text('Bảo mật thiết bị',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF263238))),
            const Spacer(),
            ElevatedButton.icon(
              onPressed: _scanning ? null : _scan,
              icon: _scanning
                ? const SizedBox(width: 14, height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.refresh, size: 14),
              label: const Text('Quét tất cả'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFD32F2F),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              ),
            ),
          ]),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: _status.startsWith('✅') ? Colors.green.shade50 : const Color(0xFFFFF3E0),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(_status, style: const TextStyle(fontSize: 11, color: Color(0xFF263238))),
          ),
          const SizedBox(height: 12),
          // Stats
          Row(children: [
            Expanded(child: _statBox('Online', '$_online', Colors.green)),
            const SizedBox(width: 6),
            Expanded(child: _statBox('Offline', '$_offline', Colors.red)),
            const SizedBox(width: 6),
            Expanded(child: _statBox('Web exposed', '$_webExposed', Colors.orange)),
          ]),
          const SizedBox(height: 12),
          ..._devices.map((d) => _deviceTile(d)),
        ],
      ),
    );
  }

  Widget _statBox(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Column(children: [
        Text(value, style: TextStyle(
          fontSize: 22, fontWeight: FontWeight.bold, color: color)),
        Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF607D8B))),
      ]),
    );
  }

  Widget _deviceTile(Device d) {
    final online = d.online;
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: const Color(0xFFE0E0E0)),
      ),
      child: Row(children: [
        Icon(
          online ? Icons.check_circle : Icons.cancel,
          color: online ? Colors.green : Colors.red,
          size: 16,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(d.ip, style: const TextStyle(fontFamily: 'monospace',
                fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF263238))),
              Text('${d.note.isEmpty ? d.type : d.note}',
                style: const TextStyle(fontSize: 10, color: Color(0xFF607D8B))),
            ],
          ),
        ),
        if (d.latencyMs > 0)
          Text('${d.latencyMs}ms',
            style: const TextStyle(fontSize: 10, fontFamily: 'monospace', color: Color(0xFF607D8B))),
        if (d.lastError != null && d.lastError!.isNotEmpty)
          const Padding(
            padding: EdgeInsets.only(left: 4),
            child: Icon(Icons.error_outline, color: Colors.orange, size: 14),
          ),
      ]),
    );
  }
}
