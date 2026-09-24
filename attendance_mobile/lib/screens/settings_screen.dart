// lib/screens/settings_screen.dart
// AttendanceSuite v2.6.1 - Tab "Cài đặt"
// v2.6.1: Thêm theme chooser (Sáng/Tối/Theo hệ thống)

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../api/pc_api.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.api,
    required this.onThemeChanged,
    required this.currentServerUrl,
    required this.onServerUrlChanged,
  });
  final PcApi api;
  final ValueChanged<bool> onThemeChanged;
  final String currentServerUrl;
  final ValueChanged<String> onServerUrlChanged;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String _themeMode = 'dark'; // 'dark' | 'light' | 'system'
  int _autoRefreshSec = 5;
  String _vpnUser = 'nemk';
  String _vpnServer = '113.176.81.193:8443';
  String _serverUrl = 'http://172.16.200.105:8080';

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _themeMode = prefs.getString('theme_mode') ?? 'dark';
      _autoRefreshSec = prefs.getInt('auto_refresh_sec') ?? 5;
      _vpnUser = prefs.getString('vpn_user') ?? 'nemk';
      _vpnServer = prefs.getString('vpn_server') ?? '113.176.81.193:8443';
      _serverUrl = prefs.getString('server_url') ?? widget.currentServerUrl;
    });
  }

  Future<void> _setThemeMode(String v) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('theme_mode', v);
    setState(() => _themeMode = v);
    // True = dark mode on, False = light (chỉ áp dụng khi mode=dark/light)
    if (v == 'dark') widget.onThemeChanged(true);
    if (v == 'light') widget.onThemeChanged(false);
    // system: notify parent cần re-render (handled bằng cách null callback)
  }

  Future<void> _setAutoRefresh(int v) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('auto_refresh_sec', v);
    setState(() => _autoRefreshSec = v);
  }

  Future<void> _setVpnUser(String v) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('vpn_user', v);
    setState(() => _vpnUser = v);
  }

  Future<void> _setVpnServer(String v) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('vpn_server', v);
    setState(() => _vpnServer = v);
  }

  Future<void> _setServerUrl(String v) async {
    final prefs = await SharedPreferences.getInstance();
    final clean = v.trim();
    if (clean.isEmpty) return;
    await prefs.setString('server_url', clean);
    setState(() => _serverUrl = clean);
    widget.onServerUrlChanged(clean);
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(8),
      children: [
        _header(),
        const SizedBox(height: 8),

        // ============ Theme chooser ============
        _section('Giao diện', icon: Icons.color_lens, children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: const Text('Chọn giao diện:', style: TextStyle(color: Colors.white70, fontSize: 12)),
          ),
          Row(children: [
            Expanded(
              child: _themeChoice('Tối', Icons.dark_mode, 'dark', _themeMode == 'dark', () => _setThemeMode('dark')),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: _themeChoice('Sáng', Icons.light_mode, 'light', _themeMode == 'light', () => _setThemeMode('light')),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: _themeChoice('Hệ thống', Icons.settings_brightness, 'system', _themeMode == 'system', () => _setThemeMode('system')),
            ),
          ]),
          const SizedBox(height: 6),
          if (_themeMode != 'system')
            const Text('• Đang dùng dark/light cố định (không theo hệ thống)',
                style: TextStyle(fontSize: 10, color: Colors.white54))
          else
            const Text('• Sẽ theo theme thiết bị (restart app để áp dụng)',
                style: TextStyle(fontSize: 10, color: Colors.white54)),
        ]),

        const SizedBox(height: 12),

        // ============ Network / VPN Settings ============
        _section('Network & VPN', icon: Icons.cloud, children: [
          // v2.6.8: Server URL cho backend (default CCDK-M6)
          ListTile(
            dense: true,
            title: const Text('Backend Server URL', style: TextStyle(color: Colors.white)),
            subtitle: const Text('URL backend attendance_web.py (CCDK-M6 BV)',
                style: TextStyle(color: Colors.white60, fontSize: 11)),
            trailing: SizedBox(
              width: 200,
              child: TextFormField(
                key: const ValueKey('server_url_field'),
                initialValue: _serverUrl,
                style: const TextStyle(fontSize: 12, color: Colors.white, fontFamily: 'monospace'),
                onChanged: _setServerUrl,
                onFieldSubmitted: _setServerUrl,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  border: OutlineInputBorder(),
                  hintText: 'http://ip:8080',
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              _serverUrl.startsWith('http://172.16.200.105')
                  ? '• ✅ CCDK-M6 (default, đã cài thành công)'
                  : '• ⚠️ Đang dùng URL tùy chỉnh: $_serverUrl',
              style: const TextStyle(fontSize: 10, color: Colors.white54),
            ),
          ),
          const Divider(color: Color(0xFF455A64)),
          ListTile(
            dense: true,
            title: const Text('Auto-refresh interval (giây)', style: TextStyle(color: Colors.white)),
            subtitle: Slider(
              value: _autoRefreshSec.toDouble(),
              min: 1,
              max: 60,
              divisions: 60,
              label: '$_autoRefreshSec s',
              onChanged: (v) => _setAutoRefresh(v.toInt()),
              activeColor: const Color(0xFF26A69A),
            ),
            trailing: Text('${_autoRefreshSec}s',
                style: const TextStyle(color: Color(0xFF26A69A), fontWeight: FontWeight.bold, fontSize: 16)),
          ),
          const Divider(color: Color(0xFF455A64)),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: Text('VPN BỆNH VIỆN (Sophos 113.176.81.193:8443)',
                style: TextStyle(color: Color(0xFF26A69A), fontSize: 11, fontWeight: FontWeight.bold)),
          ),
          ListTile(
            dense: true,
            title: const Text('Username VPN', style: TextStyle(color: Colors.white)),
            trailing: SizedBox(
              width: 150,
              child: TextFormField(
                initialValue: _vpnUser,
                style: const TextStyle(fontSize: 12, color: Colors.white, fontFamily: 'monospace'),
                onChanged: _setVpnUser,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  border: OutlineInputBorder(),
                ),
              ),
            ),
          ),
          ListTile(
            dense: true,
            title: const Text('Server:Port VPN', style: TextStyle(color: Colors.white)),
            trailing: SizedBox(
              width: 180,
              child: TextFormField(
                initialValue: _vpnServer,
                style: const TextStyle(fontSize: 12, color: Colors.white, fontFamily: 'monospace'),
                onChanged: _setVpnServer,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  border: OutlineInputBorder(),
                ),
              ),
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: Text('• Mật khẩu nhập trực tiếp trong tab Network (để bảo mật)',
                style: TextStyle(fontSize: 10, color: Colors.white54, fontStyle: FontStyle.italic)),
          ),
        ]),

        const SizedBox(height: 12),

        // ============ About ============
        _section('Thông tin', icon: Icons.info_outline, children: [
          _kv('Phiên bản', '2.6.8+41 (LAN Scan + Server URL)'),
          _kv('Kiến trúc', 'Python web server + Flutter UI'),
          _kv('Python', '3.12 (Chaquopy 17.0.0)'),
          _kv('ZK protocol', 'pyzk 0.5.x (pure Python)'),
          _kv('Sophos VPN', 'openvpn_flutter 1.3.4 (native)'),
          _kv('Repository', 'github.com/drkrongnem86-del/AttendanceSuite'),
          _kv('Tác giả', 'Dr. Nểm - BVĐK Ninh Thuận'),
          _kv('Copyright', '© 2026 BVĐK Ninh Thuận'),
        ]),

        const SizedBox(height: 12),

        // ============ Status check ============
        _section('Kiểm tra', icon: Icons.medical_services, children: [
          ListTile(
            dense: true,
            title: Text('BV Backend ($_serverUrl)', style: const TextStyle(color: Colors.white)),
            subtitle: Text(
              _serverUrl.contains('172.16.200.105')
                  ? 'CCDK-M6 (default - qua Sophos VPN)'
                  : 'URL tùy chỉnh',
              style: const TextStyle(color: Colors.white60, fontSize: 11),
            ),
            trailing: const Icon(Icons.check_circle, color: Color(0xFF26A69A)),
            onTap: () async {
              final ready = await widget.api.isReady();
              if (!mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(ready ? '✅ Python OK' : '❌ Python not ready'),
                  backgroundColor: ready ? Colors.green.shade700 : Colors.red.shade700,
                ),
              );
            },
          ),
        ]),

        const SizedBox(height: 80),
      ],
    );
  }

  Widget _themeChoice(String label, IconData icon, String key, bool selected, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFF26A69A) : const Color(0xFF37474F),
          borderRadius: BorderRadius.circular(6),
          border: selected ? Border.all(color: const Color(0xFF26A69A), width: 2) : null,
        ),
        child: Column(children: [
          Icon(icon, color: selected ? Colors.black : Colors.white70, size: 22),
          const SizedBox(height: 4),
          Text(label,
              style: TextStyle(
                  fontSize: 11,
                  color: selected ? Colors.black : Colors.white,
                  fontWeight: selected ? FontWeight.bold : FontWeight.normal)),
        ]),
      ),
    );
  }

  Widget _header() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
      child: Row(children: [
        const Icon(Icons.settings, size: 16, color: Color(0xFF26A69A)),
        const SizedBox(width: 6),
        const Text('CÀI ĐẶT',
            style: TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.bold)),
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
          Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Color(0xFF26A69A))),
        ]),
        const SizedBox(height: 6),
        ...children,
      ]),
    );
  }

  Widget _kv(String k, String v) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: 110, child: Text('$k:', style: const TextStyle(fontSize: 11, color: Colors.white60))),
        Expanded(
            child: Text(v,
                style: const TextStyle(fontSize: 11, color: Colors.white, fontFamily: 'monospace'))),
      ]),
    );
  }
}
