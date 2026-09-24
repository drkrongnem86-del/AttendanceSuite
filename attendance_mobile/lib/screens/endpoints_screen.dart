// lib/screens/endpoints_screen.dart
// AttendanceSuite v2.7.3+46 - All Endpoints screen
// Mirror cua backend /all-links HTML page - list toan bo HTML pages va API endpoints
// voi method badge + description + Test JSON (GET) / Copy curl (POST) / Open in Browser

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/pc_api.dart';

class _EndpointInfo {
  final String method; // 'HTML' | 'GET' | 'POST'
  final String path;
  final String title;
  final String desc;
  final String? sampleBody; // JSON body example cho POST
  final Map<String, String>? sampleParams; // query params example cho GET

  const _EndpointInfo({
    required this.method,
    required this.path,
    required this.title,
    required this.desc,
    this.sampleBody,
    this.sampleParams,
  });
}

class EndpointsScreen extends StatefulWidget {
  const EndpointsScreen({super.key, required this.api});
  final PcApi api;

  @override
  State<EndpointsScreen> createState() => _EndpointsScreenState();
}

class _EndpointsScreenState extends State<EndpointsScreen> {
  final _searchCtl = TextEditingController();
  String _filter = '';

  // ============ HTML PAGES (10) ============
  static const _htmlPages = <_EndpointInfo>[
    _EndpointInfo(method: 'HTML', path: '/', title: 'Viewer chính',
        desc: 'Trang index - đọc log chấm công, bảng dữ liệu các máy ZK'),
    _EndpointInfo(method: 'HTML', path: '/launcher.html', title: 'Launcher (8 tabs)',
        desc: 'Tab launcher - viewer / simulator / live / security / punch / inject / attlog-tools / all-links'),
    _EndpointInfo(method: 'HTML', path: '/all-links', title: 'All Endpoints ⭐ v2.6.11',
        desc: 'Index tất cả HTML pages và API endpoints - search box, Test JSON, Copy curl'),
    _EndpointInfo(method: 'HTML', path: '/attlog-tools', title: 'ATTLOG Tools ⭐ v2.6.11',
        desc: 'Tool đọc ATTLOG thật từ máy qua port 4370 - FW/Serial/User count/PIN test/inject workflow'),
    _EndpointInfo(method: 'HTML', path: '/inject', title: 'Inject ATTLOG 🔴 v1.9.2',
        desc: 'Inject ATTLOG qua CVE-2023-3941 - download ZKDB.db, modify, upload, reboot'),
    _EndpointInfo(method: 'HTML', path: '/security', title: 'Bảo mật ⭐ v1.8',
        desc: 'Security dashboard - scan 24 máy, risk score, users có password'),
    _EndpointInfo(method: 'HTML', path: '/punch', title: 'Chấm công PIN+PWD ⭐ v1.8',
        desc: 'Manual punch UI - verify PIN+password qua port 4370'),
    _EndpointInfo(method: 'HTML', path: '/merge', title: 'Merge Workflow',
        desc: 'Merge data từ các máy - mark-done, clear-old'),
    _EndpointInfo(method: 'HTML', path: '/alerts', title: 'Alerts',
        desc: 'Cảnh báo thiếu chấm công theo ca'),
    _EndpointInfo(method: 'HTML', path: '/api/live/page', title: 'Live Status Page',
        desc: 'Live device status UI - ping/latency/probe time'),
  ];

  // ============ GET APIs (17+) ============
  static const _getApis = <_EndpointInfo>[
    _EndpointInfo(method: 'GET', path: '/api/diag', title: 'Diag',
        desc: 'Server info: version, mode (LAN/VPN), local_ip, devices count',
        sampleParams: {}),
    _EndpointInfo(method: 'GET', path: '/api/status', title: 'Fetch status',
        desc: 'Background fetch job status - running/progress/done'),
    _EndpointInfo(method: 'GET', path: '/api/devices', title: 'Devices',
        desc: 'Danh sách 30 thiết bị (27 attendance + gateway + server)'),
    _EndpointInfo(method: 'GET', path: '/api/records', title: 'Records cache',
        desc: 'Tất cả ATTLOG records cached - 674K+ records thường trực'),
    _EndpointInfo(method: 'GET', path: '/api/live', title: 'Live status',
        desc: 'Ping/latency/probe time cho tất cả thiết bị (30-60s qua VPN)'),
    _EndpointInfo(method: 'GET', path: '/api/security/scan', title: 'Security scan',
        desc: 'Scan tất cả máy - 60-120s qua VPN - trả về risk score'),
    _EndpointInfo(method: 'GET', path: '/api/security/devices', title: 'Security devices ⭐',
        desc: 'Devices với risk score (NEW v2.6.11)'),
    _EndpointInfo(method: 'GET', path: '/api/security/device/{ip}/users', title: 'Device users ⭐',
        desc: 'List users có password trên thiết bị (NEW v2.6.11)',
        sampleParams: {}),
    _EndpointInfo(method: 'GET', path: '/api/security/device/{ip}/verify', title: 'Verify PIN+PWD ⭐',
        desc: 'Verify PIN+password qua port 4370 (NEW v2.6.11)',
        sampleParams: {'pin': '1', 'password': '1234'}),
    _EndpointInfo(method: 'GET', path: '/api/security/quick-pin-test', title: 'Quick PIN test ⭐',
        desc: 'Test 1 user nhanh (NEW v2.6.11)',
        sampleParams: {'ip': '172.16.0.30', 'pin': '1'}),
    _EndpointInfo(method: 'GET', path: '/api/zk/info', title: 'ZK Info ⭐ v2.6.11',
        desc: 'FW/Serial/User count/Attlog count qua pyzk (port 4370)',
        sampleParams: {'ip': '172.16.0.30'}),
    _EndpointInfo(method: 'GET', path: '/api/zk/attlog', title: 'ZK ATTLOG ⭐ v2.6.11',
        desc: 'Đọc ATTLOG thật từ máy - sort desc timestamp (30-180s qua VPN)',
        sampleParams: {'ip': '172.16.0.30', 'limit': '50'}),
    _EndpointInfo(method: 'GET', path: '/api/zk/test_user', title: 'ZK Test PIN ⭐ v2.6.11',
        desc: 'Check PIN có tồn tại không (get_users scan)',
        sampleParams: {'ip': '172.16.0.30', 'pin': '1'}),
    _EndpointInfo(method: 'GET', path: '/api/inject/devices', title: 'Inject devices ⭐',
        desc: 'List devices có inject capability (NEW v2.6.11)'),
    _EndpointInfo(method: 'GET', path: '/api/inject/jobs', title: 'Inject jobs ⭐',
        desc: 'List all running/recent inject jobs (NEW v2.6.11)'),
    _EndpointInfo(method: 'GET', path: '/api/inject/jobs/{id}', title: 'Inject job status ⭐',
        desc: 'Get 1 job status - progress/done/error (NEW v2.6.11)'),
    _EndpointInfo(method: 'GET', path: '/api/inject/history', title: 'Inject history ⭐',
        desc: 'Past injections list (NEW v2.6.11)',
        sampleParams: {'limit': '50'}),
    _EndpointInfo(method: 'GET', path: '/api/merge', title: 'Merge state',
        desc: 'Current merge state - pending entries'),
    _EndpointInfo(method: 'GET', path: '/api/merge/today', title: 'Merge today',
        desc: 'Today merge data'),
    _EndpointInfo(method: 'GET', path: '/api/alerts/missing', title: 'Alerts missing',
        desc: 'Cảnh báo thiếu chấm công'),
    _EndpointInfo(method: 'GET', path: '/api/backup/status', title: 'Backup status',
        desc: 'List existing backups - date/files/size'),
    _EndpointInfo(method: 'GET', path: '/api/report/daily', title: 'Report daily',
        desc: 'Báo cáo chấm công theo ngày',
        sampleParams: {'date': '2026-09-24'}),
    _EndpointInfo(method: 'GET', path: '/api/report/today', title: 'Report today',
        desc: 'Báo cáo hôm nay'),
  ];

  // ============ POST APIs (10+) ============
  static const _postApis = <_EndpointInfo>[
    _EndpointInfo(method: 'POST', path: '/api/fetch', title: 'Trigger fetch',
        desc: 'Trigger backend pull logs từ ZK devices (timeout 60-180s qua VPN)',
        sampleBody: '{"ips": ["172.16.0.30", "172.16.0.31"]}'),
    _EndpointInfo(method: 'POST', path: '/api/cancel', title: 'Cancel fetch',
        desc: 'Cancel running fetch job',
        sampleBody: '{}'),
    _EndpointInfo(method: 'POST', path: '/api/remote-punch', title: 'Remote punch',
        desc: 'Queue punch via remote_punch_service (Secutime sync)',
        sampleBody: '{"user_id": "1", "device_ip": "172.16.0.31", "status": 0, "punch": 0}'),
    _EndpointInfo(method: 'POST', path: '/api/punch/manual', title: 'Punch manual',
        desc: 'Manual punch với PIN+password verify',
        sampleBody: '{"ip": "172.16.0.30", "user_id": "1", "timestamp": "2026-09-24 14:30:00", "status": 0, "punch": 1}'),
    _EndpointInfo(method: 'POST', path: '/api/inject/attlog', title: 'Inject ATTLOG ⭐ v2.6.11',
        desc: 'Inject ATTLOG qua CVE-2023-3941 (returns job_id, async polling)',
        sampleBody: '{"ip": "172.16.0.30", "pin": "1", "timestamp": "2026-09-24 14:30:00", "status": 0, "punch": 1, "verify_mode": 1, "marker": "APK_REAL_PUNCH"}'),
    _EndpointInfo(method: 'POST', path: '/api/zk/reboot', title: 'ZK Reboot ⭐ v2.6.11',
        desc: 'Reboot máy qua port 4370 (cảnh báo 30s downtime)',
        sampleBody: '{}'),
    _EndpointInfo(method: 'POST', path: '/api/merge/mark-done', title: 'Merge mark done',
        desc: 'Mark merge entries as done',
        sampleBody: '{"entries": [{"id": 1}, {"id": 2}]}'),
    _EndpointInfo(method: 'POST', path: '/api/merge/clear-old', title: 'Merge clear old',
        desc: 'Clear merge entries cũ (>7 days)',
        sampleBody: '{"days": 7}'),
    _EndpointInfo(method: 'POST', path: '/api/devices/save', title: 'Save devices',
        desc: 'Lưu devices state (selected/note/type)',
        sampleBody: '{"devices": [{"ip": "172.16.0.30", "selected": true, "type": "attendance", "note": "Khoa CC"}]}'),
    _EndpointInfo(method: 'POST', path: '/api/backup/now', title: 'Backup now',
        desc: 'Trigger immediate backup (có thể mất vài phút)',
        sampleBody: '{}'),
  ];

  List<_EndpointInfo> _filtered(List<_EndpointInfo> list) {
    if (_filter.isEmpty) return list;
    final f = _filter.toLowerCase();
    return list.where((e) =>
        e.path.toLowerCase().contains(f) ||
        e.title.toLowerCase().contains(f) ||
        e.desc.toLowerCase().contains(f)).toList();
  }

  Color _methodColor(String method) {
    switch (method) {
      case 'HTML': return const Color(0xFF6750A4);
      case 'GET': return const Color(0xFF1976D2);
      case 'POST': return const Color(0xFFE65100);
      default: return Colors.grey;
    }
  }

  Future<void> _testGet(_EndpointInfo e) async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator(color: Color(0xFF26A69A))),
    );
    final result = await widget.api.getJson(_resolvePath(e), params: _resolveParams(e));
    if (!mounted) return;
    Navigator.pop(context);
    _showJsonDialog('GET ${e.path}', result);
  }

  /// Resolve placeholders ({ip}, {id}) trong path thanh gia tri mac dinh
  String _resolvePath(_EndpointInfo e) {
    var path = e.path;
    if (path.contains('{ip}')) {
      path = path.replaceAll('{ip}', '172.16.0.30');
    }
    if (path.contains('{id}')) {
      path = path.replaceAll('{id}', 'latest');
    }
    return path;
  }

  Map<String, String>? _resolveParams(_EndpointInfo e) {
    if (e.sampleParams == null) return null;
    final p = Map<String, String>.from(e.sampleParams!);
    // Nếu chưa có ip param mà path có {ip}, thêm ip
    if (!p.containsKey('ip')) p['ip'] = '172.16.0.30';
    return p;
  }

  /// Build full URL cho endpoint (path + query params)
  Uri _buildUrl(_EndpointInfo e) {
    final path = _resolvePath(e);
    final params = _resolveParams(e);
    final base = '${widget.api.baseUrl}$path';
    return Uri.parse(base).replace(queryParameters: params);
  }

  /// Open endpoint in external browser (Chrome on Android)
  Future<void> _openInBrowser(_EndpointInfo e) async {
    final url = _buildUrl(e);
    try {
      final ok = await launchUrl(
        url,
        mode: LaunchMode.externalApplication,
      );
      if (!ok && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Không mở được browser cho: $url', style: const TextStyle(fontSize: 11)),
          backgroundColor: const Color(0xFFD32F2F),
          duration: const Duration(seconds: 2),
        ));
      }
    } catch (err) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Lỗi: $err', style: const TextStyle(fontSize: 11)),
        backgroundColor: const Color(0xFFD32F2F),
        duration: const Duration(seconds: 2),
      ));
    }
  }

  /// POST cũng có thể mở được URL (browser sẽ hiện JSON 405/200) - hữu ích để test
  Future<void> _openPostInBrowser(_EndpointInfo e) async {
    final url = _buildUrl(e);
    await launchUrl(url, mode: LaunchMode.externalApplication);
  }

  void _showJsonDialog(String title, Map<String, dynamic> result) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF263238),
        title: Row(children: [
          const Icon(Icons.data_object, color: Color(0xFF26A69A), size: 20),
          const SizedBox(width: 8),
          Expanded(child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 14))),
        ]),
        content: SizedBox(
          width: double.maxFinite,
          height: 400,
          child: SingleChildScrollView(
            child: SelectableText(
              _formatJson(result),
              style: const TextStyle(color: Color(0xFFB2DFDB), fontSize: 11, fontFamily: 'monospace', height: 1.4),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              Clipboard.setData(ClipboardData(text: _formatJson(result)));
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                content: Text('Đã copy JSON', style: TextStyle(fontSize: 12)),
                backgroundColor: Color(0xFF00897B),
                duration: Duration(seconds: 1),
              ));
            },
            child: const Text('Copy', style: TextStyle(color: Color(0xFF26A69A))),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Đóng', style: TextStyle(color: Color(0xFF26A69A))),
          ),
        ],
      ),
    );
  }

  String _formatJson(Map<String, dynamic> json) {
    try {
      // Pretty print with 2-space indent
      const encoder = JsonEncoderPretty();
      return encoder.convert(json);
    } catch (_) {
      return json.toString();
    }
  }

  Future<void> _copyCurl(_EndpointInfo e) async {
    final body = e.sampleBody ?? '{}';
    final curl = 'curl -X POST "${widget.api.baseUrl}${e.path}" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'$body\'';
    await Clipboard.setData(ClipboardData(text: curl));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text('Đã copy curl: ${e.path}', style: const TextStyle(fontSize: 12)),
      backgroundColor: const Color(0xFF00897B),
      duration: const Duration(seconds: 2),
    ));
  }

  Widget _card(_EndpointInfo e) {
    final color = _methodColor(e.method);
    return Card(
      color: const Color(0xFF37474F),
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(4)),
              child: Text(e.method, style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold)),
            ),
            const SizedBox(width: 8),
            Expanded(child: Text(e.path, style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold, fontFamily: 'monospace'))),
          ]),
          const SizedBox(height: 4),
          Text(e.title, style: const TextStyle(color: Color(0xFF26A69A), fontSize: 12, fontWeight: FontWeight.bold)),
          const SizedBox(height: 2),
          Text(e.desc, style: const TextStyle(color: Colors.white70, fontSize: 11, height: 1.3)),
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 4, children: [
            // ============ Method-specific actions ============
            if (e.method == 'GET' && !e.path.contains('{')) ...[
              OutlinedButton.icon(
                onPressed: () => _testGet(e),
                icon: const Icon(Icons.play_arrow, size: 14),
                label: const Text('Test JSON', style: TextStyle(fontSize: 11)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF26A69A),
                  side: const BorderSide(color: Color(0xFF26A69A), width: 0.5),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  minimumSize: const Size(0, 28),
                ),
              ),
            ],
            if (e.method == 'POST') OutlinedButton.icon(
              onPressed: () => _copyCurl(e),
              icon: const Icon(Icons.copy, size: 14),
              label: const Text('Copy curl', style: TextStyle(fontSize: 11)),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFFE65100),
                side: const BorderSide(color: Color(0xFFE65100), width: 0.5),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                minimumSize: const Size(0, 28),
              ),
            ),
            if (e.method == 'HTML') OutlinedButton.icon(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: '${widget.api.baseUrl}${e.path}'));
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text('Đã copy URL: ${e.path}', style: const TextStyle(fontSize: 11)),
                  backgroundColor: const Color(0xFF00897B),
                  duration: const Duration(seconds: 1),
                ));
              },
              icon: const Icon(Icons.link, size: 14),
              label: const Text('Copy URL', style: TextStyle(fontSize: 11)),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF6750A4),
                side: const BorderSide(color: Color(0xFF6750A4), width: 0.5),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                minimumSize: const Size(0, 28),
              ),
            ),
            // ============ Universal: Open in Browser (Chrome) ============
            OutlinedButton.icon(
              onPressed: () => e.method == 'POST' ? _openPostInBrowser(e) : _openInBrowser(e),
              icon: const Icon(Icons.open_in_browser, size: 14),
              label: Text(e.method == 'POST' ? 'Mở URL' : 'Mở Chrome', style: const TextStyle(fontSize: 11)),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF1976D2),
                side: const BorderSide(color: Color(0xFF1976D2), width: 0.5),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                minimumSize: const Size(0, 28),
              ),
            ),
          ]),
        ]),
      ),
    );
  }

  Widget _section(String title, IconData icon, Color color, List<_EndpointInfo> list) {
    final filtered = _filtered(list);
    if (filtered.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
        child: Row(children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 6),
          Text(title, style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.bold)),
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.2), borderRadius: BorderRadius.circular(8)),
            child: Text('${filtered.length}', style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.bold)),
          ),
        ]),
      ),
      ...filtered.map(_card),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      // Search box
      Padding(
        padding: const EdgeInsets.fromLTRB(8, 8, 8, 4),
        child: TextField(
          controller: _searchCtl,
          style: const TextStyle(color: Colors.white, fontSize: 13),
          decoration: InputDecoration(
            prefixIcon: const Icon(Icons.search, color: Colors.white54, size: 18),
            hintText: 'Search endpoint, path, title...',
            hintStyle: const TextStyle(color: Colors.white38, fontSize: 12),
            isDense: true,
            contentPadding: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
            filled: true,
            fillColor: const Color(0xFF37474F),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide.none),
            suffixIcon: _filter.isNotEmpty
                ? IconButton(
                    icon: const Icon(Icons.clear, color: Colors.white54, size: 16),
                    onPressed: () { _searchCtl.clear(); setState(() => _filter = ''); },
                  )
                : null,
          ),
          onChanged: (v) => setState(() => _filter = v.trim()),
        ),
      ),
      // Server info banner
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        child: Row(children: [
          const Icon(Icons.cloud, color: Color(0xFF26A69A), size: 14),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              widget.api.baseUrl,
              style: const TextStyle(color: Colors.white70, fontSize: 11, fontFamily: 'monospace'),
            ),
          ),
        ]),
      ),
      // Sections
      Expanded(
        child: ListView(
          padding: const EdgeInsets.only(bottom: 16),
          children: [
            _section('HTML Pages', Icons.web, const Color(0xFF6750A4), _htmlPages),
            _section('GET APIs', Icons.download, const Color(0xFF1976D2), _getApis),
            _section('POST APIs', Icons.upload, const Color(0xFFE65100), _postApis),
          ],
        ),
      ),
    ]);
  }
}

/// Simple JSON pretty-printer to avoid pulling in `dart:convert.encoder` indenter
class JsonEncoderPretty {
  const JsonEncoderPretty();
  String convert(dynamic value, [int indent = 0]) {
    final pad = '  ' * indent;
    if (value == null) return 'null';
    if (value is num || value is bool) return value.toString();
    if (value is String) return '"${_escape(value)}"';
    if (value is List) {
      if (value.isEmpty) return '[]';
      final items = value.map((v) => '$pad  ${convert(v, indent + 1)}').join(',\n');
      return '[\n$items\n$pad]';
    }
    if (value is Map) {
      if (value.isEmpty) return '{}';
      final items = value.entries.map((e) => '$pad  "${_escape(e.key.toString())}": ${convert(e.value, indent + 1)}').join(',\n');
      return '{\n$items\n$pad}';
    }
    return '"${_escape(value.toString())}"';
  }

  String _escape(String s) => s.replaceAll('\\', '\\\\').replaceAll('"', '\\"').replaceAll('\n', '\\n').replaceAll('\r', '\\r').replaceAll('\t', '\\t');
}
