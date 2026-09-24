/// lib/api/pc_api.dart - HTTP client toi attendance_web.py backend
/// v2.7.2+45: full v2.6.11 backend support
///   + ZK Tools (/api/zk/info, /api/zk/attlog, /api/zk/test_user, /api/zk/reboot)
///   + Inject Jobs monitor (/api/inject/jobs, /api/inject/jobs/<id>, /api/inject/history, /api/inject/devices)
///   + Security (/api/security/devices, /api/security/quick-pin-test, /api/security/device/<ip>/users)
///   + Merge (/api/merge, /api/merge/today, /api/merge/mark-done, /api/merge/clear-old)
///   + Alerts (/api/alerts/missing, /alerts page)
///   + Backup (/api/backup/status, /api/backup/now)
///   + Reports (/api/report/daily, /api/report/today, /api/report/export)
///   + Remote Punch (/api/remote-punch)
///   + Backward compat v2.6.10 (/api/attlog/* paths)
library;

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class PcApi {
  String baseUrl; // mutable
  final http.Client _client = http.Client();
  // v2.6.10: Tang timeout len 180s vi ZK commands qua Sophos VPN cham (30-90s)
  final Duration timeout;

  PcApi(this.baseUrl, {this.timeout = const Duration(seconds: 180)});

  Uri _u(String path) => Uri.parse('$baseUrl$path');

  // ============ Health / Status ============
  Future<bool> isReady() async {
    for (final path in ['/health', '/api/diag']) {
      if (await _tryHealth(path)) return true;
    }
    return false;
  }

  Future<bool> _tryHealth(String path) async {
    try {
      final resp = await _client.get(_u(path)).timeout(const Duration(seconds: 5));
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> getStatus() async {
    final resp = await _client.get(_u('/api/status')).timeout(const Duration(seconds: 10));
    return _decode(resp);
  }

  Future<Map<String, dynamic>> getDiag() async {
    final resp = await _client.get(_u('/api/diag')).timeout(const Duration(seconds: 10));
    return _decode(resp);
  }

  // ============ Devices ============
  Future<List<Device>> getDevices() async {
    final resp = await _client.get(_u('/api/devices')).timeout(const Duration(seconds: 30));
    return _parseDevices(resp);
  }

  Future<bool> saveDevices(List<Device> devices) async {
    try {
      final resp = await _client
          .post(_u('/api/devices/save'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'devices': devices
                    .map((d) => {
                          'ip': d.ip,
                          'type': d.type,
                          'note': d.note,
                          'selected': d.selected,
                        })
                    .toList(),
              }))
          .timeout(const Duration(seconds: 15));
      return _decode(resp)['ok'] == true;
    } catch (_) {
      return false;
    }
  }

  // ============ Live / Probe ============
  Future<Map<String, dynamic>> getLive() async {
    try {
      final resp = await _client.get(_u('/api/live')).timeout(const Duration(seconds: 120));
      return _decode(resp);
    } catch (e) {
      return {'error': '$e'};
    }
  }

  Future<Map<String, dynamic>> pingAll() async {
    try {
      final resp = await _client.get(_u('/api/security/scan')).timeout(const Duration(seconds: 120));
      return _decode(resp);
    } catch (e) {
      return {'error': '$e'};
    }
  }

  // ============ Log / Records ============
  Future<Map<String, dynamic>> getRecent({int limit = 200}) async {
    try {
      final resp = await _client.get(_u('/api/records')).timeout(const Duration(seconds: 30));
      final j = _decode(resp);
      var list = (j['records'] is List)
          ? j['records'] as List
          : (j['list'] is List)
              ? j['list'] as List
              : <dynamic>[];
      if (list.length > limit) list = list.sublist(0, limit);
      return {'ok': true, 'records': list, 'source': '/api/records'};
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  Future<Map<String, dynamic>> deviceAttlog(String ip, {int limit = 200}) async {
    return await getRecent(limit: limit);
  }

  Future<Map<String, dynamic>> getDeviceInfo(String ip) async {
    try {
      final resp = await _client
          .get(_u('/api/security/device/$ip/attlog-count'))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ ATTLOG Tools (v2.6.10: real backend calls + 180s timeout) ============
  Future<Map<String, dynamic>> checkUser({
    required String ip,
    required String pin,
    String? password,
  }) async {
    try {
      final resp = await _client
          .post(_u('/api/attlog/check-user'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'ip': ip,
                'pin': pin,
                if (password != null && password.isNotEmpty) 'password': password,
              }))
          .timeout(const Duration(seconds: 180));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  Future<Map<String, dynamic>> injectAttlog({
    required String ip,
    required String pin,
    required String timestamp,
    int status = 0,
    int punch = 1,
    int verifyMode = 1,
    String marker = 'APK_REAL_PUNCH',
  }) async {
    try {
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
              }))
          .timeout(const Duration(seconds: 180));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  Future<Map<String, dynamic>> deleteAttlog({
    required String ip,
    required String marker,
  }) async {
    try {
      final resp = await _client
          .post(_u('/api/attlog/delete-marker'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'ip': ip, 'marker': marker}))
          .timeout(const Duration(seconds: 180));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  Future<Map<String, dynamic>> editAttlogTime({
    required String ip,
    required String marker,
    required String newTime,
  }) async {
    try {
      final resp = await _client
          .post(_u('/api/attlog/edit-time'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'ip': ip, 'marker': marker, 'new_time': newTime}))
          .timeout(const Duration(seconds: 180));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  Future<Map<String, dynamic>> realPunch({
    required String ip,
    required String pin,
  }) async {
    try {
      final resp = await _client
          .post(_u('/api/attlog/real-punch'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'ip': ip, 'pin': pin}))
          .timeout(const Duration(seconds: 180));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ MANUAL ENTRY (v2.6.10: thêm record thủ công vào cache) ============
  Future<Map<String, dynamic>> manualAttlog({
    required String ip,
    required String userId,
    required String timestamp,
    int status = 0,
    int punch = 1,
    String note = 'MANUAL_PUNCH',
  }) async {
    try {
      final resp = await _client
          .post(_u('/api/attlog/manual'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'ip': ip,
                'user_id': userId,
                'timestamp': timestamp,
                'status': status,
                'punch': punch,
                'note': note,
              }))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  Future<Map<String, dynamic>> attlogRecent({
    required String ip,
    int limit = 50,
  }) async {
    try {
      final resp = await _client
          .post(_u('/api/attlog/recent'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'ip': ip, 'limit': limit}))
          .timeout(const Duration(seconds: 180));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// Lay ATTLOG tu /api/records (cached), filter theo IP + limit
  Future<List<Map<String, dynamic>>> getRecentAttlog({
    String? ip,
    int limit = 100,
  }) async {
    try {
      final resp = await _client.get(_u('/api/records')).timeout(const Duration(seconds: 30));
      final body = _decode(resp);
      List<dynamic> all = [];
      if (body['records'] is List) {
        all = body['records'] as List;
      } else if (body['list'] is List) {
        all = body['list'] as List;
      } else if (body['data'] is List) {
        all = body['data'] as List;
      } else if (body is List) {
        all = body as List;
      }
      var filtered = all.cast<Map<String, dynamic>>();
      if (ip != null && ip.isNotEmpty) {
        filtered = filtered.where((r) {
          final rip = (r['device_ip'] ?? r['ip'] ?? '').toString();
          return rip == ip;
        }).toList();
      }
      if (limit > 0 && filtered.length > limit) {
        filtered = filtered.sublist(0, limit);
      }
      return filtered;
    } catch (_) {
      return [];
    }
  }

  // ============ Fetch (trigger backend to pull logs from ZK devices) ============
  Future<Map<String, dynamic>> fetchLogs({required List<String> ips}) async {
    try {
      final resp = await _client
          .post(_u('/api/fetch'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'ips': ips}))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  Future<Map<String, dynamic>> cancelFetch() async {
    try {
      final resp = await _client
          .post(_u('/api/cancel'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({}))
          .timeout(const Duration(seconds: 10));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ Polling job status ============
  Future<Map<String, dynamic>> getJobStatus(String jobId) async {
    try {
      final resp = await _client.get(_u('/api/attlog/job/$jobId')).timeout(const Duration(seconds: 10));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ ZK Tools (v2.7.2+45: NEW v2.6.11 endpoints) ============
  /// GET /api/zk/info?ip=X - FW/Serial/User count/Attlog count (qua pyzk port 4370)
  Future<Map<String, dynamic>> zkInfo(String ip) async {
    try {
      final resp = await _client
          .get(_u('/api/zk/info').replace(queryParameters: {'ip': ip}))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/zk/attlog?ip=X&limit=N - doc N records gan nhat tu may that (sort desc timestamp)
  Future<Map<String, dynamic>> zkAttlog(String ip, {int limit = 50}) async {
    try {
      final resp = await _client
          .get(_u('/api/zk/attlog').replace(queryParameters: {'ip': ip, 'limit': '$limit'}))
          .timeout(const Duration(seconds: 180));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/zk/test_user?ip=X&pin=Y - check PIN co ton tai khong (get_users scan)
  Future<Map<String, dynamic>> zkTestUser(String ip, String pin) async {
    try {
      final resp = await _client
          .get(_u('/api/zk/test_user').replace(queryParameters: {'ip': ip, 'pin': pin}))
          .timeout(const Duration(seconds: 60));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// POST /api/zk/reboot?ip=X - reboot may (canh bao 30s downtime)
  Future<Map<String, dynamic>> zkReboot(String ip) async {
    try {
      final resp = await _client
          .post(_u('/api/zk/reboot').replace(queryParameters: {'ip': ip}),
              headers: {'Content-Type': 'application/json'},
              body: '{}')
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ Inject (v2.7.2+45: NEW v2.6.11 inject_routes.py) ============
  /// POST /api/inject/attlog - Inject ATTLOG records qua CVE-2023-3941
  /// (Backward compat: neu server chi co /api/attlog/inject thi fallback)
  Future<Map<String, dynamic>> injectAttlogV2({
    required String ip,
    required String pin,
    required String timestamp,
    int status = 0,
    int punch = 1,
    int verifyMode = 1,
    String marker = 'APK_REAL_PUNCH',
  }) async {
    try {
      final body = jsonEncode({
        'ip': ip,
        'pin': pin,
        'timestamp': timestamp,
        'status': status,
        'punch': punch,
        'verify_mode': verifyMode,
        'marker': marker,
      });
      // Try new path first
      try {
        final resp = await _client
            .post(_u('/api/inject/attlog'),
                headers: {'Content-Type': 'application/json'}, body: body)
            .timeout(const Duration(seconds: 180));
        if (resp.statusCode != 404) return _decode(resp);
      } catch (_) {}
      // Fallback to v2.6.10 path
      final resp = await _client
          .post(_u('/api/attlog/inject'),
              headers: {'Content-Type': 'application/json'}, body: body)
          .timeout(const Duration(seconds: 180));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/inject/devices - List devices with inject capability
  Future<Map<String, dynamic>> injectDevices() async {
    try {
      final resp = await _client.get(_u('/api/inject/devices')).timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/inject/jobs - List all running/recent inject jobs
  Future<Map<String, dynamic>> injectJobs() async {
    try {
      final resp = await _client.get(_u('/api/inject/jobs')).timeout(const Duration(seconds: 10));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/inject/jobs/<id> - Get inject job status
  Future<Map<String, dynamic>> injectJobStatus(String jobId) async {
    try {
      final resp = await _client.get(_u('/api/inject/jobs/$jobId')).timeout(const Duration(seconds: 10));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/inject/history - List past injections
  Future<Map<String, dynamic>> injectHistory({int limit = 50}) async {
    try {
      final resp = await _client
          .get(_u('/api/inject/history').replace(queryParameters: {'limit': '$limit'}))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ Security (v2.7.2+45: NEW v2.6.11 security_routes.py) ============
  /// GET /api/security/devices - Device status voi risk score
  Future<Map<String, dynamic>> securityDevices() async {
    try {
      final resp = await _client.get(_u('/api/security/devices')).timeout(const Duration(seconds: 60));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/security/device/<ip>/users - List users có password
  Future<Map<String, dynamic>> securityDeviceUsers(String ip) async {
    try {
      final resp = await _client.get(_u('/api/security/device/$ip/users')).timeout(const Duration(seconds: 60));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/security/device/<ip>/verify?pin=Y&password=Z - Verify PIN+password
  Future<Map<String, dynamic>> securityDeviceVerify({
    required String ip,
    required String pin,
    String? password,
  }) async {
    try {
      final params = <String, String>{'pin': pin};
      if (password != null && password.isNotEmpty) params['password'] = password;
      final resp = await _client
          .get(_u('/api/security/device/$ip/verify').replace(queryParameters: params))
          .timeout(const Duration(seconds: 60));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/security/quick-pin-test - Quick test 1 user (PIN only)
  Future<Map<String, dynamic>> securityQuickPinTest({
    required String ip,
    required String pin,
  }) async {
    try {
      final resp = await _client
          .get(_u('/api/security/quick-pin-test').replace(queryParameters: {'ip': ip, 'pin': pin}))
          .timeout(const Duration(seconds: 60));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ Punch (v2.7.2+45: NEW punch endpoint) ============
  /// POST /api/punch/manual - Manual punch with PIN+password verify (qua port 4370)
  Future<Map<String, dynamic>> punchManual({
    required String ip,
    required String userId,
    required String timestamp,
    int status = 0,
    int punch = 1,
    String? password,
    String note = 'APK_PUNCH',
  }) async {
    try {
      final body = jsonEncode({
        'ip': ip,
        'user_id': userId,
        'timestamp': timestamp,
        'status': status,
        'punch': punch,
        if (password != null && password.isNotEmpty) 'password': password,
        'note': note,
      });
      final resp = await _client
          .post(_u('/api/punch/manual'),
              headers: {'Content-Type': 'application/json'}, body: body)
          .timeout(const Duration(seconds: 60));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// POST /api/remote-punch - Queue punch via remote_punch_service
  Future<Map<String, dynamic>> remotePunch({
    required String userId,
    required String deviceIp,
    int status = 0,
    int punch = 0,
  }) async {
    try {
      final resp = await _client
          .post(_u('/api/remote-punch'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'user_id': userId,
                'device_ip': deviceIp,
                'status': status,
                'punch': punch,
              }))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ Merge (v2.7.2+45: NEW merge workflow) ============
  /// GET /api/merge - Get current merge state
  Future<Map<String, dynamic>> mergeGet() async {
    try {
      final resp = await _client.get(_u('/api/merge')).timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/merge/today - Get today's merge data
  Future<Map<String, dynamic>> mergeToday() async {
    try {
      final resp = await _client.get(_u('/api/merge/today')).timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// POST /api/merge/mark-done - Mark merge as done
  Future<Map<String, dynamic>> mergeMarkDone(Map<String, dynamic> data) async {
    try {
      final resp = await _client
          .post(_u('/api/merge/mark-done'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(data))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// POST /api/merge/clear-old - Clear old merge entries
  Future<Map<String, dynamic>> mergeClearOld(Map<String, dynamic> data) async {
    try {
      final resp = await _client
          .post(_u('/api/merge/clear-old'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(data))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ Alerts (v2.7.2+45: NEW) ============
  /// GET /api/alerts or /api/alerts/missing - List missing alerts
  Future<Map<String, dynamic>> alertsMissing() async {
    try {
      final resp = await _client.get(_u('/api/alerts/missing')).timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ Backup (v2.7.2+45: NEW) ============
  /// GET /api/backup/status - List existing backups
  Future<Map<String, dynamic>> backupStatus() async {
    try {
      final resp = await _client.get(_u('/api/backup/status')).timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// POST /api/backup/now - Trigger immediate backup
  Future<Map<String, dynamic>> backupNow() async {
    try {
      final resp = await _client
          .post(_u('/api/backup/now'),
              headers: {'Content-Type': 'application/json'},
              body: '{}')
          .timeout(const Duration(seconds: 600)); // Backup can take a while
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  // ============ Reports (v2.7.2+45: NEW) ============
  /// GET /api/report/daily?date=YYYY-MM-DD
  Future<Map<String, dynamic>> reportDaily({String? date}) async {
    try {
      final params = date != null ? {'date': date} : null;
      final resp = await _client
          .get(_u('/api/report/daily').replace(queryParameters: params))
          .timeout(const Duration(seconds: 60));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/report/today
  Future<Map<String, dynamic>> reportToday() async {
    try {
      final resp = await _client.get(_u('/api/report/today')).timeout(const Duration(seconds: 60));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e'};
    }
  }

  /// GET /api/report/export?date=YYYY-MM-DD - Returns Excel binary
  Future<List<int>?> reportExport({String? date}) async {
    try {
      final params = date != null ? {'date': date} : null;
      final resp = await _client
          .get(_u('/api/report/export').replace(queryParameters: params))
          .timeout(const Duration(seconds: 120));
      if (resp.statusCode == 200) return resp.bodyBytes;
      return null;
    } catch (_) {
      return null;
    }
  }

  // ============ Generic GET (v2.7.2+45: cho EndpointsScreen "Test JSON") ============
  /// Generic GET voi path + query params - tra ve JSON Map
  Future<Map<String, dynamic>> getJson(String path, {Map<String, String>? params}) async {
    try {
      final resp = await _client
          .get(_u(path).replace(queryParameters: params))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e', 'status': -1};
    }
  }

  /// Generic POST voi path + JSON body
  Future<Map<String, dynamic>> postJson(String path, Map<String, dynamic> body) async {
    try {
      final resp = await _client
          .post(_u(path),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(body))
          .timeout(const Duration(seconds: 30));
      return _decode(resp);
    } catch (e) {
      return {'ok': false, 'error': '$e', 'status': -1};
    }
  }

  // ============ Helpers ============
  Map<String, dynamic> _decode(http.Response resp) {
    if (resp.body.isEmpty) return {'ok': false, 'error': 'empty body'};
    try {
      final dynamic decoded = jsonDecode(resp.body);
      if (decoded is List) {
        return {'ok': true, 'data': decoded, 'list': decoded, 'records': decoded};
      }
      if (decoded is Map<String, dynamic>) return decoded;
      return {'ok': false, 'error': 'unexpected JSON shape'};
    } catch (e) {
      return {'ok': false, 'error': 'decode failed: $e'};
    }
  }

  List<Device> _parseDevices(http.Response resp) {
    final body = _decode(resp);
    List<dynamic> list = [];
    if (body['records'] is List) {
      list = body['records'] as List;
    } else if (body['list'] is List) {
      list = body['list'] as List;
    } else if (body['data'] is List) {
      list = body['data'] as List;
    } else if (body['devices'] is List) {
      list = body['devices'] as List;
    }
    try {
      return list.map((j) => Device.fromJson(j as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }
}
