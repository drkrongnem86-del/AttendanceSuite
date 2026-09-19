/// lib/models/models.dart - Data models cho AttendanceSuite v2.6.0
/// Khớp với JSON shapes từ attendance_web.py backend (localhost:8080).
library;

class Device {
  final String ip;
  final String type;       // attendance | signing | server | gateway | virtual
  final String note;
  bool selected;
  bool online;
  int latencyMs;
  String? lastError;
  int logCount;
  String model;
  String firmware;
  int usersCount;
  String status;           // OK | FAIL | Processing... | -
  DateTime? pingAt;

  Device({
    required this.ip,
    this.type = 'attendance',
    this.note = '',
    this.selected = false,
    this.online = false,
    this.latencyMs = 0,
    this.lastError,
    this.logCount = 0,
    this.model = '-',
    this.firmware = '',
    this.usersCount = 0,
    this.status = '-',
    this.pingAt,
  });

  Map<String, dynamic> toJson() => {
        'ip': ip,
        'type': type,
        'note': note,
        'selected': selected,
        'online': online,
        'latency_ms': latencyMs,
        'last_error': lastError,
        'log_count': logCount,
        'model': model,
        'firmware': firmware,
        'users_count': usersCount,
        'status': status,
        'ping_at': pingAt?.toIso8601String(),
      };

  factory Device.fromJson(Map<String, dynamic> j) => Device(
        ip: j['ip'] ?? '',
        type: j['type'] ?? 'attendance',
        note: j['note'] ?? '',
        selected: j['selected'] == true,
        online: j['online'] == true,
        latencyMs: (j['latency_ms'] is num) ? (j['latency_ms'] as num).toInt() : 0,
        lastError: j['last_error'],
        logCount: (j['log_count'] is num) ? (j['log_count'] as num).toInt() : 0,
        model: j['model'] ?? '-',
        firmware: j['firmware'] ?? '',
        usersCount: (j['users_count'] is num) ? (j['users_count'] as num).toInt() : 0,
        status: j['status'] ?? '-',
        pingAt: j['ping_at'] != null ? DateTime.tryParse(j['ping_at']) : null,
      );
}

class AttLog {
  final String pin;
  final String userName;
  final String timestamp;
  final int status;
  final int punch;
  final int sensor;
  final int workCode;
  final String deviceIp;
  final String deviceName;
  final String? marker;
  final String source;

  AttLog({
    this.pin = '',
    this.userName = '',
    this.timestamp = '',
    this.status = 0,
    this.punch = 0,
    this.sensor = 0,
    this.workCode = 0,
    this.deviceIp = '',
    this.deviceName = '',
    this.marker,
    this.source = 'device',
  });

  Map<String, dynamic> toJson() => {
        'pin': pin,
        'user_name': userName,
        'timestamp': timestamp,
        'status': status,
        'punch': punch,
        'sensor': sensor,
        'work_code': workCode,
        'device_ip': deviceIp,
        'device_name': deviceName,
        'marker': marker,
        'source': source,
      };

  factory AttLog.fromJson(Map<String, dynamic> j) => AttLog(
        pin: j['pin']?.toString() ?? '',
        userName: j['user_name']?.toString() ?? j['user_id']?.toString() ?? '',
        timestamp: j['timestamp']?.toString() ?? '',
        status: (j['status'] is num) ? (j['status'] as num).toInt() : 0,
        punch: (j['punch'] is num) ? (j['punch'] as num).toInt() : 0,
        sensor: (j['sensor'] is num) ? (j['sensor'] as num).toInt() : 0,
        workCode: (j['work_code'] is num) ? (j['work_code'] as num).toInt() : 0,
        deviceIp: j['device_ip']?.toString() ?? '',
        deviceName: j['device_name']?.toString() ?? '',
        marker: j['marker']?.toString(),
        source: j['source']?.toString() ?? 'device',
      );

  DateTime? get timestampDate => DateTime.tryParse(timestamp);

  String get displayName => userName.isNotEmpty ? '$userName ($pin)' : pin;
}
