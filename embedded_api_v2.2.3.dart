// widgets/embedded_api.dart
// API client for the in-app embedded HTTP server
// Connects to localhost:8080 (default port)
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class EmbeddedApi {
  final String baseUrl;
  final http.Client _client = http.Client();

  EmbeddedApi(this.baseUrl);

  String get statusUrl => '$baseUrl/api/status';
  String get diagUrl => '$baseUrl/api/diag';
  String get devicesUrl => '$baseUrl/api/devices';
  String get liveUrl => '$baseUrl/api/live';
  String get livePageUrl => '$baseUrl/api/live/page';
  String get pingAllUrl => '$baseUrl/api/attlog/ping-all';
  String get deviceInfoUrl => '$baseUrl/api/attlog/device-info';
  String get recentUrl => '$baseUrl/api/attlog/recent';
  String get injectUrl => '$baseUrl/api/attlog/inject';
  String get checkUserUrl => '$baseUrl/api/attlog/check-user';
  String get deviceAttlogUrl => '$baseUrl/api/attlog/device-attlog';

  // ===== Health =====
  Future<bool> ping() async {
    try {
      final resp = await _client.get(Uri.parse(statusUrl))
          .timeout(const Duration(seconds: 3));
      return resp.statusCode == 200;
    } catch (_) { return false; }
  }

  Future<Map<String, dynamic>> getStatus() async {
    try {
      final resp = await _client.get(Uri.parse(statusUrl))
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
    } catch (_) {}
    return {};
  }

  Future<Map<String, dynamic>> getDiag() async {
    try {
      final resp = await _client.get(Uri.parse(diagUrl))
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
    } catch (_) {}
    return {};
  }

  // ===== Devices =====
  Future<List<Device>> getDevices() async {
    try {
      final resp = await _client.get(Uri.parse(devicesUrl))
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode == 200) {
        final d = jsonDecode(resp.body);
        if (d is Map && d['devices'] is List) {
          return (d['devices'] as List)
              .map((j) => Device.fromJson(j as Map<String, dynamic>))
              .toList();
        }
      }
    } catch (_) {}
    return [];
  }

  Future<bool> saveDevices(List<Device> devices) async {
    try {
      final resp = await _client.post(
        Uri.parse(devicesUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'devices': devices.map((d) => d.toJson()).toList()}),
      ).timeout(const Duration(seconds: 5));
      return resp.statusCode == 200;
    } catch (_) { return false; }
  }

  // ===== Live / Ping =====
  Future<Map<String, dynamic>> getLive() async {
    try {
      final resp = await _client.get(Uri.parse(liveUrl))
          .timeout(const Duration(seconds: 8));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
    } catch (_) {}
    return {};
  }

  Future<Map<String, dynamic>> pingAll() async {
    try {
      final resp = await _client.post(Uri.parse(pingAllUrl))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
    } catch (_) {}
    return {};
  }

  Future<Map<String, dynamic>> getDeviceInfo(String ip) async {
    try {
      final resp = await _client.post(
        Uri.parse(deviceInfoUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'ip': ip}),
      ).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
    } catch (_) {}
    return {};
  }

  // ===== ATTLOG =====
  Future<Map<String, dynamic>> getRecent({int limit = 50}) async {
    try {
      final resp = await _client.get(
        Uri.parse('$recentUrl?limit=$limit'),
      ).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
    } catch (_) {}
    return {'ok': false, 'records': [], 'count': 0};
  }

  // ===== ATTLOG inject =====
  Future<Map<String, dynamic>> injectAttlog({
    required String ip,
    required String pin,
    required String timestamp,
    int status = 0,
    int punch = 1,
    int verifyMode = 1,
    String marker = 'APK_REAL_PUNCH',
    String? webIp,
  }) async {
    try {
      final resp = await _client.post(
        Uri.parse(injectUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'ip': ip,
          'pin': pin,
          'timestamp': timestamp,
          'status': status,
          'punch': punch,
          'verify_mode': verifyMode,
          'marker': marker,
          'web_ip': webIp,
        }),
      ).timeout(const Duration(seconds: 180));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
      return {'ok': false, 'error': 'http ${resp.statusCode}: ${resp.body}'};
    } catch (e) {
      return {'ok': false, 'error': e.toString()};
    }
  }

  // ===== ATTLOG check-user =====
  Future<Map<String, dynamic>> checkUser({
    required String ip,
    required String pin,
    String? password,
  }) async {
    try {
      final resp = await _client.post(
        Uri.parse(checkUserUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'ip': ip,
          'pin': pin,
          'password': password,
        }),
      ).timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
      return {'ok': false, 'error': 'http ${resp.statusCode}'};
    } catch (e) {
      return {'ok': false, 'error': e.toString()};
    }
  }

  // ===== ATTLOG fetch device =====
  Future<Map<String, dynamic>> postDeviceAttLog(String ip, {int limit = 200}) async {
    try {
      final resp = await _client.post(
        Uri.parse(deviceAttlogUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'ip': ip, 'limit': limit}),
      ).timeout(const Duration(seconds: 30));
      if (resp.statusCode == 200) return jsonDecode(resp.body);
      return {'ok': false, 'error': 'http ${resp.statusCode}'};
    } catch (e) {
      return {'ok': false, 'error': e.toString()};
    }
  }
}
