// Settings Screen - cấu hình server IP, Basic Auth, device list, HTTPS
// v1.5.7: Hien thi version app (package_info_plus)
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'settings.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({Key? key}) : super(key: key);

  @override
  _SettingsScreenState createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _ipCtrl = TextEditingController();
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _devicesCtrl = TextEditingController();
  bool _useHttps = false;
  bool _loading = true;
  bool _showPass = false;
  String? _msg;
  // v1.5.7: App version info (lay tu package_info_plus)
  String _version = '...';
  String _buildNumber = '...';
  String _packageName = '...';

  @override
  void initState() {
    super.initState();
    _load();
    _loadVersion();
  }

  // v1.5.7: Load app version tu PackageInfo
  Future<void> _loadVersion() async {
    try {
      final info = await PackageInfo.fromPlatform();
      if (mounted) {
        setState(() {
          _version = info.version;
          _buildNumber = info.buildNumber;
          _packageName = info.packageName;
        });
      }
    } catch (e) {
      debugPrint('Load version error: $e');
    }
  }

  @override
  void dispose() {
    _ipCtrl.dispose();
    _userCtrl.dispose();
    _passCtrl.dispose();
    _devicesCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final ip = await Settings.getServerIp();
    final user = await Settings.getAuthUser();
    final pass = await Settings.getAuthPass();
    final devices = await Settings.getDeviceIps();
    final https = await Settings.getUseHttps();
    setState(() {
      _ipCtrl.text = ip;
      _userCtrl.text = user;
      _passCtrl.text = pass;
      _devicesCtrl.text = devices.join(', ');
      _useHttps = https;
      _loading = false;
    });
  }

  Future<void> _save() async {
    final ip = _ipCtrl.text.trim();
    final user = _userCtrl.text.trim();
    final pass = _passCtrl.text;
    final devicesRaw = _devicesCtrl.text.trim();
    if (ip.isEmpty) {
      _toast('IP server khong duoc trong');
      return;
    }
    if (user.isEmpty || pass.isEmpty) {
      _toast('User/pass khong duoc trong');
      return;
    }
    final devices = devicesRaw
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    if (devices.isEmpty) {
      _toast('Can it nhat 1 device IP');
      return;
    }
    await Settings.setServerIp(ip);
    await Settings.setAuthUser(user);
    await Settings.setAuthPass(pass);
    await Settings.setDeviceIps(devices);
    await Settings.setUseHttps(_useHttps);
    setState(() {
      _msg = 'Da luu thanh cong. Khoi dong lai app de ap dung HTTPS.';
    });
    _toast('Da luu');
  }

  Future<void> _reset() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reset to default?'),
        content: const Text('Sẽ xóa toàn bộ settings và về mặc định.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Hủy')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Reset')),
        ],
      ),
    );
    if (ok == true) {
      await Settings.resetAll();
      await _load();
      _toast('Đã reset về mặc định');
    }
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), duration: const Duration(seconds: 2)),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    return Scaffold(
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Banner
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [Colors.cyan.shade900, Colors.blue.shade900],
                ),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Row(
                children: [
                  Icon(Icons.settings, color: Colors.cyanAccent, size: 32),
                  SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Cài đặt',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.bold)),
                        Text('Server IP, Auth, Devices, HTTPS',
                            style: TextStyle(color: Colors.white70, fontSize: 12)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Server IP
            _section('Server (attendance_web.py)'),
            TextField(
              controller: _ipCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'IP server',
                hintText: '172.16.200.105',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.dns),
              ),
            ),
            const SizedBox(height: 6),
            SwitchListTile(
              value: _useHttps,
              onChanged: (v) => setState(() => _useHttps = v),
              title: const Text('Dùng HTTPS (qua Cloudflare Tunnel)'),
              subtitle: const Text(
                  'Bật khi đi qua tunnel/Reverse proxy có HTTPS'),
              dense: true,
            ),
            const SizedBox(height: 16),

            // Basic Auth
            _section('Basic Auth (Remote Punch dashboard)'),
            TextField(
              controller: _userCtrl,
              decoration: const InputDecoration(
                labelText: 'Username',
                hintText: 'admin',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.person),
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _passCtrl,
              obscureText: !_showPass,
              decoration: InputDecoration(
                labelText: 'Password',
                border: const OutlineInputBorder(),
                prefixIcon: const Icon(Icons.lock),
                suffixIcon: IconButton(
                  icon: Icon(_showPass
                      ? Icons.visibility_off
                      : Icons.visibility),
                  onPressed: () => setState(() => _showPass = !_showPass),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Device list
            _section('Device IPs (cho Remote Punch)'),
            TextField(
              controller: _devicesCtrl,
              maxLines: 3,
              keyboardType: TextInputType.multiline,
              decoration: const InputDecoration(
                labelText: 'Device IPs (phân cách bằng dấu phẩy)',
                hintText: '172.16.0.212, 172.16.0.214, 172.16.0.30, 172.16.0.31',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.devices),
              ),
            ),
            const SizedBox(height: 6),
            const Text(
              'Danh sách IP các máy chấm công sẽ hiện trong dropdown của tab "Chấm từ xa".',
              style: TextStyle(fontSize: 11, color: Colors.white60),
            ),
            const SizedBox(height: 24),

            // Save / Reset
            ElevatedButton.icon(
              onPressed: _save,
              icon: const Icon(Icons.save),
              label: const Text('LƯU CÀI ĐẶT'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.cyanAccent,
                foregroundColor: Colors.black,
                padding: const EdgeInsets.all(16),
                textStyle: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: _reset,
              icon: const Icon(Icons.restart_alt, color: Colors.redAccent),
              label: const Text('Reset về mặc định',
                  style: TextStyle(color: Colors.redAccent)),
            ),

            if (_msg != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.green.shade900,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(_msg!, style: const TextStyle(color: Colors.white)),
              ),
            ],

            const SizedBox(height: 24),
            const Text(
              '💡 Lưu ý:'
              '\n• IP server phải trỏ về máy tính chạy attendance_web.py'
              '\n• Nếu HTTPS bật, URL sẽ tự thêm https://'
              '\n• Reset không xóa lịch sử chấm công (chỉ xóa settings app)',
              style: TextStyle(fontSize: 11, color: Colors.white60),
            ),
            const SizedBox(height: 24),
            // v1.5.7: App version info card
            _buildVersionCard(),
          ],
        ),
      ),
    );
  }

  // v1.5.7: Card hiển thị version app + build number + package name
  Widget _buildVersionCard() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [Colors.teal.shade900, Colors.cyan.shade900],
        ),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.cyanAccent, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(Icons.info_outline, color: Colors.cyanAccent, size: 16),
              SizedBox(width: 6),
              Text(
                'Thông tin ứng dụng',
                style: TextStyle(
                  color: Colors.cyanAccent,
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          _versionRow('Version', _version),
          _versionRow('Build', _buildNumber),
          _versionRow('Package', _packageName),
          _versionRow('Server URL', '${_useHttps ? 'https' : 'http'}://${_ipCtrl.text}:8080'),
        ],
      ),
    );
  }

  Widget _versionRow(String k, String v) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          SizedBox(
            width: 90,
            child: Text(
              '$k:',
              style: const TextStyle(color: Colors.white60, fontSize: 11),
            ),
          ),
          Expanded(
            child: SelectableText(
              v,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w500,
                fontFamily: 'monospace',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _section(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8, top: 4),
      child: Text(
        title,
        style: const TextStyle(
          color: Colors.cyanAccent,
          fontSize: 13,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}
