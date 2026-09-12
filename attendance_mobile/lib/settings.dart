// Settings storage - lưu tất cả cấu hình app vào SharedPreferences
import 'package:shared_preferences/shared_preferences.dart';

class Settings {
  // ---- Server IP ----
  static const String _kServerIp = 'server_ip';
  static const String defaultServerIp = '172.16.200.105';

  static Future<String> getServerIp() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kServerIp) ?? defaultServerIp;
  }

  static Future<void> setServerIp(String ip) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kServerIp, ip);
  }

  // ---- Basic Auth (cho Remote Punch) ----
  static const String _kAuthUser = 'auth_user';
  static const String _kAuthPass = 'auth_pass';
  static const String defaultAuthUser = 'admin';
  static const String defaultAuthPass = 'bvdk2026';

  static Future<String> getAuthUser() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kAuthUser) ?? defaultAuthUser;
  }

  static Future<void> setAuthUser(String user) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kAuthUser, user);
  }

  static Future<String> getAuthPass() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kAuthPass) ?? defaultAuthPass;
  }

  static Future<void> setAuthPass(String pass) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kAuthPass, pass);
  }

  // ---- Device IPs (danh sách chấm công, hiện trong dropdown) ----
  static const String _kDeviceIps = 'device_ips';
  static const String defaultDeviceIps =
      '172.16.0.212,172.16.0.214,172.16.0.30,172.16.0.31';

  static Future<List<String>> getDeviceIps() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kDeviceIps) ?? defaultDeviceIps;
    return raw
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
  }

  static Future<void> setDeviceIps(List<String> ips) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kDeviceIps, ips.join(','));
  }

  // ---- HTTPS mode (bật nếu đi qua Cloudflare Tunnel hoặc proxy HTTPS) ----
  static const String _kUseHttps = 'use_https';

  static Future<bool> getUseHttps() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_kUseHttps) ?? false;
  }

  static Future<void> setUseHttps(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kUseHttps, value);
  }

  // ---- Reset to defaults ----
  static Future<void> resetAll() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
  }
}
