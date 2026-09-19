/// lib/api/pc_api.dart - HTTP client tới attendance_web.py (localhost:8080)
/// Backend Python chạy nền qua Chaquopy, mọi ZK protocol xử lý ở server.
library;

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class PcApi {
  final String baseUrl;
  final http.Client _client = http.Client();
  final Duration timeout;

  PcApi(this.baseUrl, {this.timeout = const Duration(seconds: 30)});

  Uri _u(String path) => Uri.parse('$baseUrl$path');

  /// Health check - app lúc khởi động gọi cái này để biết Python server ready
  /// v2.6.4: Thử nhiều endpoints để tăng độ robust
  Future<bool> isReady() async {
    // Thử /health truoc (v2.6.4+)
    if (await _tryHealth('/health')) return true;
    // Fallback: thử /api/diag (server co the la version cu, khong co /health)
    if (await _tryHealth('/api/diag')) return true;
    // Fallback cuoi: thử /api/status
    if (await _tryHealth('/api/status')) return true;
    return false;
  }

  Future<bool> _tryHealth(String path) async {
    try {
      final resp = await _client.get(_u(path)).timeout(const Duration(seconds: 3));
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ============ Status / Diagnostics ============
  Future<Map<String, dynamic>> getStatus() async {
    final resp = await _client.get(_u('/api/status')).timeout(timeout);
    return _decode(resp);
  }

  Future<Map<String, dynamic>> getDiag() async {
    final resp = await _client.get(_u('/api/diag')).timeout(timeout);
    return _decode(resp);
  }

  // ============ Devices ============
  Future<List<Device>> getDevices() async {
    final resp = await _client.get(_u('/api/devices')).timeout(timeout);
    final data = _decode(resp);
    if (data['devices'] is List) {
      return (data['devices'] as List)
          .map((j) => Device.fromJson(j as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  Future<bool> saveDevices(List<Device> devices) async {
    final resp = await _client
        .post(_u('/api/devices/save'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'devices': devices.map((d) => d.toJson()).toList()}))
        .timeout(timeout);
    final data = _decode(resp);
    return data['ok'] == true;
  }

  // ============ Live / Ping ============
  Future<Map<String, dynamic>> getLive() async {
    final resp = await _client.get(_u('/api/live')).timeout(timeout);
    return _decode(resp);
  }

  Future<Map<String, dynamic>> pingAll() async {
    final resp = await _client.post(_u('/api/attlog/ping-all')).timeout(timeout);
    return _decode(resp);
  }

  Future<Map<String, dynamic>> getDeviceInfo(String ip) async {
    final resp = await _client
        .post(_u('/api/attlog/device-info'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'ip': ip}))
        .timeout(timeout);
    return _decode(resp);
  }

  // ============ ATTLOG ============
  Future<Map<String, dynamic>> getRecent({int limit = 50}) async {
    final resp = await _client
        .get(_u('/api/attlog/recent?limit=$limit'))
        .timeout(timeout);
    return _decode(resp);
  }

  Future<Map<String, dynamic>> deviceAttlog(String ip, {int limit = 200}) async {
    final resp = await _client
        .post(_u('/api/attlog/device-attlog'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'ip': ip, 'limit': limit}))
        .timeout(const Duration(seconds: 60));
    return _decode(resp);
  }

  Future<Map<String, dynamic>> checkUser({
    required String ip,
    required String pin,
    String? password,
  }) async {
    final resp = await _client
        .post(_u('/api/attlog/check-user'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'ip': ip,
              'pin': pin,
              'password': password,
            }))
        .timeout(const Duration(seconds: 30));
    return _decode(resp);
  }

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
    final resp = await _client
        .post(_u('/api/attlog/inject'),
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
            }))
        .timeout(const Duration(seconds: 180));
    return _decode(resp);
  }

  Map<String, dynamic> _decode(http.Response resp) {
    if (resp.body.isEmpty) return {'ok': false, 'error': 'empty body'};
    try {
      return jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (e) {
      return {'ok': false, 'error': 'decode failed: $e'};
    }
  }
}
