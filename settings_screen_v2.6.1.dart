// lib/screens/settings_screen.dart
// AttendanceSuite v2.6.0 - Tab "Cài đặt" - theme, devices, app info

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../api/pc_api.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.api, required this.onThemeChanged});
  final PcApi api;
  final ValueChanged<bool> onThemeChanged;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _darkMode = true;
  int _autoRefreshSec = 5;
  String _webIpFallback = '172.16.254.202';

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _darkMode = prefs.getBool('dark_mode') ?? true;
      _autoRefreshSec = prefs.getInt('auto_refresh_sec') ?? 5;
      _webIpFallback = prefs.getString('web_ip_fallback') ?? '172.16.254.202';
    });
  }

  Future<void> _setDarkMode(bool v) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('dark_mode', v);
    setState(() => _darkMode = v);
    widget.onThemeChanged(v);
  }

  Future<void> _setAutoRefresh(int v) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('auto_refresh_sec', v);
    setState(() => _autoRefreshSec = v);
  }

  Future<void> _setWebIp(String v) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('web_ip_fallback', v);
    setState(() => _webIpFallback = v);
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(8),
      children: [
        _header(),
        const SizedBox(height: 8),

        // ============ Theme ============
        _section('Giao diện', children: [
          SwitchListTile(
            dense: true,
            title: const Text('Dark mode', style: TextStyle(color: Colors.white)),
            subtitle: const Text('Giao diện tối (PC EXE style)', style: TextStyle(color: Colors.white60, fontSize: 11)),
            value: _darkMode,
            activeThumbColor: const Color(0xFF26A69A),
            onChanged: _setDarkMode,
          ),
        ]),

        const SizedBox(height: 12),

        // ============ Network ============
        _section('Network', children: [
          ListTile(
            dense: true,
            title: const Text('Auto-refresh interval (giây)', style: TextStyle(color: Colors.white)),
            subtitle: Slider(
              value: _autoRefreshSec.toDouble(),
              min: 1,
              max: 60,
              divisions: 60,
              label: '${_autoRefreshSec}s',
              onChanged: (v) => _setAutoRefresh(v.toInt()),
              activeColor: const Color(0xFF26A69A),
            ),
            trailing: Text('${_autoRefreshSec}s',
                style: const TextStyle(color: Color(0xFF26A69A), fontWeight: FontWeight.bold, fontSize: 16)),
          ),
          ListTile(
            dense: true,
            title: const Text('Web IP fallback cho ATTLOG', style: TextStyle(color: Colors.white)),
            subtitle: const Text('IP máy chủ web ZK (vd: 172.16.254.202)',
                style: TextStyle(color: Colors.white60, fontSize: 11)),
            trailing: SizedBox(
              width: 150,
              child: TextFormField(
                initialValue: _webIpFallback,
                style: const TextStyle(fontSize: 12, color: Colors.white),
                onChanged: _setWebIp,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  border: OutlineInputBorder(),
                ),
              ),
            ),
          ),
        ]),

        const SizedBox(height: 12),

        // ============ About ============
        _section('Thông tin', children: [
          _kv('Phiên bản', '2.6.1+34 (UI + VPN)'),
          _kv('Kiến trúc', 'Python web server + Flutter UI'),
          _kv('Python', '3.12 (Chaquopy 17.0.0)'),
          _kv('ZK protocol', 'pyzk 0.5.x (pure Python)'),
          _kv('Sophos VPN', 'openvpn_flutter 1.3.4 (native)'),
          _kv('VPN server', 'user=nemk → 113.176.81.193:8443'),
          _kv('Repository', 'github.com/drkrongnem86-del/AttendanceSuite'),
          _kv('Tác giả', 'Dr. Nểm - BVĐK Ninh Thuận'),
          _kv('Copyright', '© 2026 BVĐK Ninh Thuận'),
        ]),

        const SizedBox(height: 12),

        // ============ Status check ============
        _section('Kiểm tra', children: [
          ListTile(
            dense: true,
            title: const Text('Python web server', style: TextStyle(color: Colors.white)),
            subtitle: const Text('Đang chạy http://127.0.0.1:8080', style: TextStyle(color: Colors.white60, fontSize: 11)),
            trailing: const Icon(Icons.check_circle, color: Color(0xFF26A69A)),
            onTap: () async {
              final ready = await widget.api.isReady();
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(ready ? '✅ Python OK' : '❌ Python not ready'),
                  backgroundColor: ready ? Colors.green.shade700 : Colors.red.shade700,
                ),
              );
            },
          ),
          ListTile(
            dense: true,
            title: const Text('Khởi động lại server', style: TextStyle(color: Colors.white)),
            subtitle: const Text('Restart Python web server nếu bị lỗi', style: TextStyle(color: Colors.white60, fontSize: 11)),
            trailing: const Icon(Icons.restart_alt, color: Colors.orangeAccent),
            onTap: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Restart server: tính năng đang phát triển. Restart app để fresh start.')),
              );
            },
          ),
        ]),

        const SizedBox(height: 80),
      ],
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

  Widget _section(String title, {required List<Widget> children}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: const Color(0xFF37474F), borderRadius: BorderRadius.circular(4)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Color(0xFF26A69A))),
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
