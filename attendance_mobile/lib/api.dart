// AttendanceSuite API client
// Talks to the Python backend (attendance_web.py + punch_simulator.py)

import 'dart:convert';
import 'package:http/http.dart' as http;

class AttendanceApi {
  final String baseUrl;
  final http.Client _client = http.Client();

  AttendanceApi(this.baseUrl);

  String get viewerUrl => '$baseUrl';
  String get simulatorUrl => '$baseUrl';  // assumes proxy/launcher on same port
  String get viewerApi => baseUrl;
  String get simulatorApi => '$baseUrl:8081';

  // Health check
  Future<bool> ping() async {
    try {
      final resp = await _client
          .get(Uri.parse('$baseUrl/api/status'))
          .timeout(const Duration(seconds: 5));
      return resp.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  // Diagnostic info from server (returns reachable URLs, primary IP, etc.)
  Future<Map<String, dynamic>> getDiag() async {
    try {
      final resp = await _client
          .get(Uri.parse('$baseUrl/api/diag'))
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode == 200) {
        return json.decode(resp.body) as Map<String, dynamic>;
      }
    } catch (e) {
      // ignore
    }
    return {};
  }

  // Get list of devices
  Future<List<Device>> getDevices() async {
    try {
      final resp = await _client.get(Uri.parse('$baseUrl/api/devices'));
      if (resp.statusCode == 200) {
        final data = json.decode(resp.body) as List;
        return data.map((d) => Device.fromJson(d)).toList();
      }
    } catch (e) {
      // ignore
    }
    return [];
  }

  // Trigger fetch
  Future<Map<String, dynamic>> fetchLogs(List<String> ips, String from, String to) async {
    try {
      final resp = await _client.post(
        Uri.parse('$baseUrl/api/fetch'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'ips': ips,
          'dateFrom': from,
          'dateTo': to,
        }),
      ).timeout(const Duration(seconds: 30));
      return json.decode(resp.body) as Map<String, dynamic>;
    } catch (e) {
      return {'ok': false, 'error': e.toString()};
    }
  }

  // Get status
  Future<Map<String, dynamic>> getStatus() async {
    try {
      final resp = await _client.get(Uri.parse('$baseUrl/api/status'));
      if (resp.statusCode == 200) {
        return json.decode(resp.body) as Map<String, dynamic>;
      }
    } catch (e) {
      // ignore
    }
    return {};
  }

  // Cancel fetch
  Future<bool> cancel() async {
    try {
      final resp = await _client.post(Uri.parse('$baseUrl/api/cancel'));
      return resp.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  // Get records
  Future<List<Record>> getRecords() async {
    try {
      final resp = await _client.get(Uri.parse('$baseUrl/api/records'));
      if (resp.statusCode == 200) {
        final data = json.decode(resp.body) as List;
        return data.map((r) => Record.fromJson(r)).toList();
      }
    } catch (e) {
      // ignore
    }
    return [];
  }

  // ===== Simulator API (port 8081) =====

  Future<Map<String, dynamic>> getSimDevice() async {
    try {
      final resp = await _client.get(Uri.parse('$simulatorApi/api/device'));
      if (resp.statusCode == 200) {
        return json.decode(resp.body) as Map<String, dynamic>;
      }
    } catch (e) {}
    return {};
  }

  Future<Map<String, dynamic>> punch(String userId, int status, int punch) async {
    try {
      final resp = await _client.post(
        Uri.parse('$simulatorApi/api/punch'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'userId': userId, 'status': status, 'punch': punch}),
      ).timeout(const Duration(seconds: 15));
      return json.decode(resp.body) as Map<String, dynamic>;
    } catch (e) {
      return {'ok': false, 'error': e.toString()};
    }
  }

  Future<List<ManualPunch>> getHistory() async {
    try {
      final resp = await _client.get(Uri.parse('$simulatorApi/api/history'));
      if (resp.statusCode == 200) {
        final data = json.decode(resp.body) as Map<String, dynamic>;
        final list = data['history'] as List;
        return list.map((p) => ManualPunch.fromJson(p)).toList();
      }
    } catch (e) {}
    return [];
  }

  Future<bool> deletePunch(int punchId) async {
    try {
      final resp = await _client.post(
        Uri.parse('$simulatorApi/api/delete'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'punch_id': punchId}),
      );
      return resp.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  // ===== Remote punch (cham cong tu xa qua /api/remote-punch) =====

  /// Cham cong tu xa - ghi vao pending queue, service se sync.
  /// [status]: 0=Check-In, 1=Check-Out, 2=Break-Out, 3=Break-In, 4=OT-In, 5=OT-Out
  Future<Map<String, dynamic>> remotePunch(String userId, int status,
      {String? deviceIp}) async {
    try {
      final body = json.encode({
        'user_id': userId,
        'status': status,
        if (deviceIp != null) 'device_ip': deviceIp,
      });
      final resp = await _client
          .post(
            Uri.parse('$baseUrl/api/remote-punch'),
            headers: {
              'Content-Type': 'application/json',
              // Basic auth (admin/bvdk2026) - can sua theo config
              'Authorization': 'Basic ' + base64Url.encode(utf8.encode('admin:bvdk2026')).replaceAll('=', ''),
            },
            body: body,
          )
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200 || resp.statusCode == 303) {
        return json.decode(resp.body) as Map<String, dynamic>;
      }
      return {'ok': false, 'error': 'HTTP ${resp.statusCode}'};
    } catch (e) {
      return {'ok': false, 'error': e.toString()};
    }
  }
}

class Device {
  final String ip;
  final String type;
  final String note;
  final String status;
  final int? logCount;
  final String? model;

  Device({
    required this.ip,
    required this.type,
    required this.note,
    required this.status,
    this.logCount,
    this.model,
  });

  factory Device.fromJson(Map<String, dynamic> j) {
    return Device(
      ip: j['ip'] ?? '',
      type: j['type'] ?? 'unknown',
      note: j['note'] ?? '',
      status: j['status'] ?? '',
      logCount: j['log_count'],
      model: j['model'],
    );
  }
}

class Record {
  final String deviceIp;
  final String userId;
  final String date;
  final String time;
  final int status;
  final int punch;
  final int uid;
  final String timestamp;
  final String? deviceType;

  Record({
    required this.deviceIp,
    required this.userId,
    required this.date,
    required this.time,
    required this.status,
    required this.punch,
    required this.uid,
    required this.timestamp,
    this.deviceType,
  });

  factory Record.fromJson(Map<String, dynamic> j) {
    return Record(
      deviceIp: j['device_ip'] ?? '',
      userId: j['user_id'] ?? '',
      date: j['date'] ?? '',
      time: j['time'] ?? '',
      status: j['status'] ?? 0,
      punch: j['punch'] ?? 0,
      uid: j['uid'] ?? 0,
      timestamp: j['timestamp'] ?? '',
      deviceType: j['device_type'],
    );
  }

  String get statusName => const {
        0: 'Check-In',
        1: 'Check-Out',
        2: 'Break-Out',
        3: 'Break-In',
        4: 'OT-In',
        5: 'OT-Out',
      }[status] ??
      'Status-$status';

  String get punchName => const {
        0: 'Vân tay',
        1: 'Thẻ',
        2: 'Mật khẩu',
      }[punch] ??
      'Khác';
}

class ManualPunch {
  final int punchId;
  final String timestamp;
  final String userId;
  final String statusName;
  final String methodName;
  final bool writtenToDevice;

  ManualPunch({
    required this.punchId,
    required this.timestamp,
    required this.userId,
    required this.statusName,
    required this.methodName,
    required this.writtenToDevice,
  });

  factory ManualPunch.fromJson(Map<String, dynamic> j) {
    return ManualPunch(
      punchId: j['punch_id'] ?? 0,
      timestamp: j['timestamp'] ?? '',
      userId: j['user_id'] ?? '',
      statusName: j['status_name'] ?? '',
      methodName: j['method_name'] ?? '',
      writtenToDevice: j['written_to_device'] == 'True',
    );
  }
}
