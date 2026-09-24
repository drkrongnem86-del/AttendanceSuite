// lib/screens/log_screen.dart
// AttendanceSuite v2.7.4+47 - Tab "Đọc log chấm công"
// Style khớp với AttendanceSuite v2.0.13 PC EXE (dark theme, device list, log list)
// v2.7.4+47: Auto-detect backend, quick switch URL (3 candidates), show real URL
// v2.7.1: bulk-select, nút Xem log nổi bật
// v2.6.1: bulk-select, retry Python

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/models.dart';
import '../api/pc_api.dart';
import 'package:intl/intl.dart';

/// v2.7.4+47: 3 candidate backend URLs - user tap 1 phat de switch
const _kCandidateUrls = <_UrlCandidate>[
  _UrlCandidate('CCDK-M6 BV (mặc định)', 'http://172.16.200.105:8080'),
  _UrlCandidate('CCDK-M10 BV (backup)', 'http://172.16.200.101:8080'),
  _UrlCandidate('Sophos tunnel home', 'http://171.15.0.2:8080'),
];

class _UrlCandidate {
  final String label;
  final String url;
  const _UrlCandidate(this.label, this.url);
}

class LogScreen extends StatefulWidget {
  const LogScreen({super.key, required this.api, this.onStateReady});
  final PcApi api;
  final ValueChanged<LogScreenState>? onStateReady;

  @override
  State<LogScreen> createState() => LogScreenState();
}

class LogScreenState extends State<LogScreen> {
  List<Device> _devices = [];
  List<AttLog> _logs = [];
  String? _status;
  bool _loading = false;
  String _mode = 'LAN';
  String _localIp = '-';
  String _quickFilter = 'today';
  String _deviceTypeFilter = 'all';
  String _logDeviceFilter = 'all';
  String _logUserFilter = '';       // v2.7.1: filter by user_id/PIN
  String _logStatusFilter = 'all';   // v2.7.1: all | in | out
  String _logPunchFilter = 'all';    // v2.7.1: all | card | fp
  String _searchQuery = '';
  Timer? _progressTimer;
  bool _pythonReady = false;

  // v2.7.4+47: URL switcher state
  final Map<String, bool> _urlStatus = {};  // url -> online?
  bool _scanningUrls = false;

  @override
  void initState() {
    super.initState();
    _refresh();
    // Expose state cho parent (HomeScreen) để LogBottomBar có thể gọi
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.onStateReady?.call(this);
    });
  }

  @override
  void dispose() {
    _progressTimer?.cancel();
    super.dispose();
  }

  Future<void> _checkPython() async {
    final ready = await widget.api.isReady();
    if (!mounted) return;
    setState(() => _pythonReady = ready);
    // v2.7.4+47: nếu offline thì quét 3 candidate URLs song song
    if (!ready) {
      await _scanCandidateUrls();
    }
  }

  /// v2.7.4+47: Quét song song 3 candidate URLs, lưu status
  Future<void> _scanCandidateUrls() async {
    if (_scanningUrls) return;
    setState(() => _scanningUrls = true);
    final results = <String, bool>{};
    await Future.wait(_kCandidateUrls.map((c) async {
      final old = widget.api.baseUrl;
      widget.api.baseUrl = c.url;
      final ok = await widget.api.isReady();
      results[c.url] = ok;
      widget.api.baseUrl = old; // restore
    }));
    if (!mounted) return;
    setState(() {
      _scanningUrls = false;
      _urlStatus
        ..clear()
        ..addAll(results);
    });
  }

  /// v2.7.4+47: Switch URL sang candidate khác + save SharedPreferences
  Future<void> _switchUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_url', url);
    if (!mounted) return;
    setState(() {
      widget.api.baseUrl = url;
    });
    await _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _status = '🔄 Đang tải...';
    });
    await _checkPython();
    if (!_pythonReady) {
      setState(() {
        _loading = false;
        _status = '⚠️ Python server chưa sẵn sàng (đợi 2-3s rồi bấm RETRY)\n'
            'Nếu vẫn lỗi: restart app hoặc check logcat';
      });
      return;
    }
    try {
      final diag = await widget.api.getDiag();
      final devs = await widget.api.getDevices();
      final recent = await widget.api.getRecent(limit: 200);
      setState(() {
        // v2.6.5: BV v1.3.0 /api/diag tra primary_ip (khong co local_ip)
        _mode = (diag['mode'] as String? ?? ((diag['is_vpn'] == true) ? 'VPN' : 'LAN')).toUpperCase();
        _localIp = diag['primary_ip']?.toString() ?? diag['local_ip']?.toString() ?? '-';
        _devices = devs;
        _logs = (recent['records'] as List?)
                ?.map((j) => AttLog.fromJson(j as Map<String, dynamic>))
                .toList() ??
            [];
        _status = null;
      });
    } catch (e) {
      setState(() => _status = '⚠️ Python server lỗi: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _scanDevices() async {
    setState(() {
      _loading = true;
      _status = '🔍 Đang quét thiết bị (mỗi thiết bị ~2-3s)...';
    });
    _progressTimer?.cancel();
    _progressTimer = Timer.periodic(const Duration(seconds: 2), (t) async {
      try {
        await widget.api.getStatus();
      } catch (_) {}
    });
    try {
      // pingAll() goi /api/security/scan - backend v1.3.0 se cap nhat
      // devices.csv voi ping_ok/ping_ms moi cho moi device.
      final scanResult = await widget.api.pingAll();
      // Re-fetch devices de lay ping_ok vua update.
      final devs = await widget.api.getDevices();
      final onlineCount = devs.where((d) => d.online).length;
      // v2.6.5: security/scan response la {devices: [...]}, khong co mode/local_ip/duration_ms
      // Lay tu scanResult neu co, nguoc lai giu gia tri cu.
      setState(() {
        _devices = devs;
        _mode = (scanResult['mode']?.toString() ?? _mode).toUpperCase();
        _localIp = scanResult['local_ip']?.toString() ?? scanResult['primary_ip']?.toString() ?? _localIp;
        _status = '✅ Quét xong: $onlineCount/${devs.length} thiết bị online';
      });
    } catch (e) {
      setState(() => _status = '❌ Quét lỗi: $e');
    } finally {
      _progressTimer?.cancel();
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _getLogsForDevices(List<Device> devs) async {
    if (devs.isEmpty) {
      setState(() => _status = '⚠️ Chưa chọn thiết bị nào');
      return;
    }
    setState(() {
      _loading = true;
      _status = '📥 Đang fetch ATTLOG từ ${devs.length} thiết bị (gọi backend /api/fetch)...';
    });
    try {
      final ips = devs.map((d) => d.ip).toList();
      final fetchRes = await widget.api.fetchLogs(ips: ips);
      if (fetchRes['ok'] != true) {
        setState(() {
          _loading = false;
          _status = '❌ Fetch lỗi: ${fetchRes['error'] ?? fetchRes['message'] ?? 'unknown'}';
        });
        return;
      }
      // Poll status cho đến khi xong (max 5 phút cho 27 devices)
      var progress = 0;
      var total = devs.length;
      var okCount = 0;
      for (var i = 0; i < 60; i++) {
        await Future.delayed(const Duration(seconds: 5));
        if (!mounted) return;
        try {
          final status = await widget.api.getStatus();
          progress = (status['progress'] as int?) ?? progress;
          total = (status['total'] as int?) ?? total;
          final running = status['running'] == true;
          setState(() => _status = '📥 Đang fetch: $progress/$total (lần ${i + 1}/60)...');
          if (!running && progress >= total) {
            okCount = progress;
            break;
          }
        } catch (_) {}
      }
      // Sau khi fetch xong, đọc records từ /api/records (cached)
      final recent = await widget.api.getRecent(limit: 500);
      final records = (recent['records'] as List?)
              ?.map((j) => AttLog.fromJson(j as Map<String, dynamic>))
              .toList() ??
          [];
      records.sort((a, b) => b.timestamp.compareTo(a.timestamp));
      if (!mounted) return;
      setState(() {
        _logs = records;
        // v2.7.1: Auto-switch filter to 'all' sau khi fetch (de user thay log)
        _quickFilter = 'all';
        _logDeviceFilter = 'all';
        _logUserFilter = '';
        _logStatusFilter = 'all';
        _logPunchFilter = 'all';
        _status = '✅ Fetch xong: $okCount/$total thiết bị, ${records.length} records (hiển thị "Tất cả")';
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _status = '❌ $e';
      });
    }
  }

  Future<void> _getLogsForDevice(Device d) async {
    setState(() {
      _loading = true;
      _status = '📥 Đang lấy log từ ${d.ip}...';
      _logDeviceFilter = d.ip;
    });
    try {
      final result = await widget.api.deviceAttlog(d.ip, limit: 200);
      if (result['ok'] == true) {
        final records = (result['records'] as List?)
                ?.map((j) => AttLog.fromJson(j as Map<String, dynamic>))
                .toList() ??
            [];
        records.sort((a, b) => b.timestamp.compareTo(a.timestamp));
        setState(() {
          _logs = records;
          _status = '✅ Lấy log từ ${d.ip}: ${records.length} records';
        });
      } else {
        setState(() => _status = '⚠️ ${result['error'] ?? 'Không có log'}');
      }
    } catch (e) {
      setState(() => _status = '❌ Lỗi: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  // Bulk select helpers
  void _selectOne(Device d) {
    setState(() {
      for (final dev in _devices) {
        dev.selected = (dev.ip == d.ip);
      }
    });
  }

  void _selectAll() {
    setState(() {
      for (final d in _devices) {
        d.selected = true;
      }
    });
  }

  void _deselectAll() {
    setState(() {
      for (final d in _devices) {
        d.selected = false;
      }
    });
  }

  Future<void> _saveSelection() async {
    final selected = _devices.where((d) => d.selected).toList();
    setState(() => _status = '💾 Lưu ${selected.length} thiết bị...');
    try {
      final ok = await widget.api.saveDevices(_devices);
      setState(() => _status = ok ? '✅ Đã lưu ${selected.length} thiết bị'
          : '❌ Lưu thất bại');
    } catch (e) {
      setState(() => _status = '❌ $e');
    }
  }

  // ============ PUBLIC API (cho LogBottomBar từ HomeScreen) ============
  int get selectedCount => _devices.where((d) => d.selected).length;
  bool get isLoading => _loading;
  void selectAll() => _selectAll();
  void deselectAll() => _deselectAll();
  Future<void> saveSelection() => _saveSelection();
  Future<void> fetchLogsForSelected() async {
    final selected = _devices.where((d) => d.selected).toList();
    await _getLogsForDevices(selected);
  }

  // Filter
  List<Device> get _filteredDevices {
    var list = _devices;
    if (_deviceTypeFilter == 'attendance') {
      list = list.where((d) => d.type == 'attendance').toList();
    } else if (_deviceTypeFilter == 'signing') {
      list = list.where((d) => d.type == 'signing').toList();
    } else if (_deviceTypeFilter == 'server') {
      list = list.where((d) => d.type == 'server' || d.type == 'gateway').toList();
    } else if (_deviceTypeFilter == 'cc_only') {
      list = list.where((d) => d.type == 'attendance' && d.selected).toList();
    }
    if (_searchQuery.isNotEmpty) {
      list = list
          .where((d) =>
              d.ip.toLowerCase().contains(_searchQuery.toLowerCase()) ||
              d.note.toLowerCase().contains(_searchQuery.toLowerCase()))
          .toList();
    }
    return list;
  }

  List<AttLog> get _filteredLogs {
    var list = _logs;
    if (_logDeviceFilter != 'all') {
      list = list.where((l) => l.deviceIp == _logDeviceFilter).toList();
    }
    // v2.7.1: User/pin search filter
    if (_logUserFilter.isNotEmpty) {
      final q = _logUserFilter.toLowerCase();
      list = list.where((l) =>
          l.pin.toLowerCase().contains(q) ||
          l.displayName.toLowerCase().contains(q) ||
          (l.marker ?? '').toLowerCase().contains(q)).toList();
    }
    // v2.7.1: Status filter (IN/OUT/All)
    if (_logStatusFilter == 'in') {
      list = list.where((l) => l.status == 0 || l.status == 1).toList();
    } else if (_logStatusFilter == 'out') {
      list = list.where((l) => l.status == 2 || l.status == 3).toList();
    }
    // v2.7.1: Punch filter (Card/FP/All)
    if (_logPunchFilter == 'card') {
      list = list.where((l) => l.punch == 1 || l.punch == 14 || l.punch == 15).toList();
    } else if (_logPunchFilter == 'fp') {
      list = list.where((l) => l.punch == 1 || l.punch == 4 || l.punch == 15).toList();
    }
    // Time filter (today/yesterday/week/month/all)
    if (_quickFilter == 'today') {
      final today = DateTime.now();
      list = list.where((l) {
        final d = l.timestampDate;
        if (d == null) return false;
        return d.year == today.year && d.month == today.month && d.day == today.day;
      }).toList();
    } else if (_quickFilter == 'yesterday') {
      final y = DateTime.now().subtract(const Duration(days: 1));
      list = list.where((l) {
        final d = l.timestampDate;
        if (d == null) return false;
        return d.year == y.year && d.month == y.month && d.day == y.day;
      }).toList();
    } else if (_quickFilter == 'week') {
      final now = DateTime.now();
      final start = now.subtract(Duration(days: now.weekday - 1));
      list = list.where((l) {
        final d = l.timestampDate;
        if (d == null) return false;
        return d.isAfter(start.subtract(const Duration(days: 1)));
      }).toList();
    } else if (_quickFilter == 'month') {
      final now = DateTime.now();
      list = list.where((l) {
        final d = l.timestampDate;
        if (d == null) return false;
        return d.year == now.year && d.month == now.month;
      }).toList();
    }
    return list;
  }

  Map<String, int> get _deviceCounts {
    final m = <String, int>{'attendance': 0, 'signing': 0, 'server': 0, 'gateway': 0};
    for (final d in _devices) {
      m[d.type] = (m[d.type] ?? 0) + 1;
    }
    return m;
  }

  @override
  Widget build(BuildContext context) {
    final cs = _filteredDevices;
    final ls = _filteredLogs;
    final counts = _deviceCounts;
    final selectedCount = _devices.where((d) => d.selected).length;

    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(8),
        children: [
          // ============ Status banner with Python retry ============
          _pythonBanner(),
          if (_status != null && _status!.isNotEmpty)
            Container(
              margin: const EdgeInsets.only(top: 4, bottom: 4),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF455A64),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(_status!,
                  style: const TextStyle(fontSize: 11, color: Colors.white)),
            ),

          // ============ Filter row: Chip filters ============
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(children: [
              _chip('Today', _quickFilter == 'today', () => setState(() => _quickFilter = 'today')),
              _chip('Yesterday', _quickFilter == 'yesterday', () => setState(() => _quickFilter = 'yesterday')),
              _chip('Week', _quickFilter == 'week', () => setState(() => _quickFilter = 'week')),
              _chip('Month', _quickFilter == 'month', () => setState(() => _quickFilter = 'month')),
              _chip('All', _quickFilter == 'all', () => setState(() => _quickFilter = 'all')),
            ]),
          ),
          const SizedBox(height: 6),

          // ============ Action row: Scan + Status ============
          Row(children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _loading ? null : _scanDevices,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF26A69A),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
                icon: const Icon(Icons.wifi_find, size: 16),
                label: Text(_loading ? 'Đang quét...' : 'QUÉT THIẾT BỊ',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF37474F),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.circle, size: 8,
                    color: _pythonReady ? const Color(0xFF26A69A) : Colors.redAccent),
                const SizedBox(width: 4),
                Text('${_devices.where((d) => d.online).length}/${_devices.length}',
                    style: const TextStyle(fontSize: 11, color: Colors.white)),
              ]),
            ),
          ]),
          const SizedBox(height: 6),

          // ============ Device section ============
          _sectionHeader('DANH SÁCH THIẾT BỊ',
              subtitle:
                  '${_devices.length} thiết bị (${counts['attendance'] ?? 0} chấm công, ${counts['signing'] ?? 0} ký, $selectedCount chọn)'),
          // Filters for device list
          SizedBox(
            height: 28,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                _miniChip('Tất cả', _deviceTypeFilter == 'all', () => setState(() => _deviceTypeFilter = 'all')),
                _miniChip('CC đã chọn', _deviceTypeFilter == 'cc_only', () => setState(() => _deviceTypeFilter = 'cc_only')),
                _miniChip('CC', _deviceTypeFilter == 'attendance', () => setState(() => _deviceTypeFilter = 'attendance')),
                _miniChip('KY', _deviceTypeFilter == 'signing', () => setState(() => _deviceTypeFilter = 'signing')),
                _miniChip('SV/GW', _deviceTypeFilter == 'server', () => setState(() => _deviceTypeFilter = 'server')),
              ],
            ),
          ),
          // Search box
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: TextField(
              decoration: const InputDecoration(
                isDense: true,
                hintText: 'Tìm theo IP hoặc tên...',
                prefixIcon: Icon(Icons.search, size: 18),
                border: OutlineInputBorder(),
                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              ),
              style: const TextStyle(fontSize: 13),
              onChanged: (v) => setState(() => _searchQuery = v),
            ),
          ),
          // Device list
          ...cs.map((d) => _deviceRow(d)),
          if (cs.isEmpty)
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF37474F),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: const Color(0xFF455A64), width: 0.5),
              ),
              child: const Column(children: [
                Icon(Icons.devices_other, size: 36, color: Color(0xFF607D8B)),
                SizedBox(height: 6),
                Text('Chưa có thiết bị',
                    style: TextStyle(fontSize: 13, color: Colors.white70, fontWeight: FontWeight.bold)),
                SizedBox(height: 4),
                Text(
                  'Bấm nút QUÉT THIẾT BỊ ở trên để tìm máy chấm công.\n'
                  '• Cùng WiFi BV: phone tự thấy 172.16.x.x\n'
                  '• Ngoài BV: bật VPN BỆNH VIỆN ở tab Network trước',
                  style: TextStyle(fontSize: 11, color: Colors.white60),
                  textAlign: TextAlign.center,
                ),
              ]),
            ),

          const SizedBox(height: 12),
          // ============ Logs section ============
          _sectionHeader('LOG CHẤM CÔNG',
              subtitle: '${ls.length} records (mode: $_quickFilter)'),
          // v2.7.1: Log filters - device + user + status + punch + clear all
          // Row 1: Device dropdown
          Row(children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                initialValue: _logDeviceFilter,
                isDense: true,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  border: OutlineInputBorder(),
                ),
                items: [
                  const DropdownMenuItem(value: 'all', child: Text('-- Tất cả thiết bị --', style: TextStyle(fontSize: 12))),
                  ..._devices.map((d) => DropdownMenuItem(
                      value: d.ip, child: Text('${d.ip} (${d.note})', style: const TextStyle(fontSize: 11)))),
                ],
                onChanged: (v) => setState(() => _logDeviceFilter = v ?? 'all'),
              ),
            ),
          ]),
          const SizedBox(height: 4),
          // Row 2: User/PIN search + Status + Punch
          Row(children: [
            Expanded(
              flex: 2,
              child: TextField(
                decoration: const InputDecoration(
                  isDense: true,
                  hintText: 'Tìm user_id/PIN',
                  prefixIcon: Icon(Icons.person_search, size: 16),
                  border: OutlineInputBorder(),
                  contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                ),
                style: const TextStyle(fontSize: 12),
                onChanged: (v) => setState(() => _logUserFilter = v.trim()),
              ),
            ),
            const SizedBox(width: 4),
            Expanded(
              child: DropdownButtonFormField<String>(
                initialValue: _logStatusFilter,
                isDense: true,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                  border: OutlineInputBorder(),
                ),
                items: const [
                  DropdownMenuItem(value: 'all', child: Text('IN+OUT', style: TextStyle(fontSize: 11))),
                  DropdownMenuItem(value: 'in', child: Text('IN', style: TextStyle(fontSize: 11))),
                  DropdownMenuItem(value: 'out', child: Text('OUT', style: TextStyle(fontSize: 11))),
                ],
                onChanged: (v) => setState(() => _logStatusFilter = v ?? 'all'),
              ),
            ),
            const SizedBox(width: 4),
            Expanded(
              child: DropdownButtonFormField<String>(
                initialValue: _logPunchFilter,
                isDense: true,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                  border: OutlineInputBorder(),
                ),
                items: const [
                  DropdownMenuItem(value: 'all', child: Text('Mọi loại', style: TextStyle(fontSize: 11))),
                  DropdownMenuItem(value: 'card', child: Text('Card', style: TextStyle(fontSize: 11))),
                  DropdownMenuItem(value: 'fp', child: Text('Vân tay', style: TextStyle(fontSize: 11))),
                ],
                onChanged: (v) => setState(() => _logPunchFilter = v ?? 'all'),
              ),
            ),
            const SizedBox(width: 4),
            ElevatedButton(
              onPressed: () {
                setState(() {
                  _logDeviceFilter = 'all';
                  _logUserFilter = '';
                  _logStatusFilter = 'all';
                  _logPunchFilter = 'all';
                });
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF455A64),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              ),
              child: const Text('Clear', style: TextStyle(fontSize: 11)),
            ),
          ]),
          const SizedBox(height: 6),
          // Log list
          if (ls.isEmpty)
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF37474F),
                borderRadius: BorderRadius.circular(4),
              ),
              child: const Center(
                child: Text('Chưa có log. Bấm XEM LOG trên danh sách thiết bị.',
                    style: TextStyle(fontSize: 12, color: Colors.white60)),
              ),
            )
          else
            ...ls.take(200).map((l) => _logRow(l)),
          const SizedBox(height: 80),
        ],
      ),
    );
  }

  Widget _pythonBanner() {
    final url = widget.api.baseUrl;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: _pythonReady ? const Color(0xFF1B5E20) : const Color(0xFF455A64),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(
            _pythonReady ? Icons.check_circle : Icons.error,
            size: 14,
            color: _pythonReady ? Colors.greenAccent : Colors.orangeAccent,
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              _pythonReady
                  ? 'Backend OK • Mode: $_mode • IP: $_localIp • ${_devices.length} thiết bị'
                  : 'Backend chưa sẵn sàng ($url)',
              style: const TextStyle(fontSize: 11, color: Colors.white, fontWeight: FontWeight.bold),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          TextButton.icon(
            onPressed: _loading ? null : _refresh,
            style: TextButton.styleFrom(
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 6),
              minimumSize: const Size(60, 28),
            ),
            icon: const Icon(Icons.refresh, size: 14),
            label: const Text('Retry', style: TextStyle(fontSize: 11)),
          ),
        ]),
        // v2.7.4+47: Khi offline, hiển thị quick switch 3 candidate URLs
        if (!_pythonReady) ...[
          const SizedBox(height: 4),
          if (_scanningUrls)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(children: [
                const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFFFFB74D))),
                const SizedBox(width: 6),
                Text('Đang quét ${_kCandidateUrls.length} URLs...',
                    style: const TextStyle(fontSize: 10, color: Colors.white70)),
              ]),
            )
          else
            ..._kCandidateUrls.map((c) => _urlSwitchRow(c)),
        ],
      ]),
    );
  }

  /// v2.7.4+47: 1 row trong banner list - hiển thị 1 candidate URL + status + tap to switch
  Widget _urlSwitchRow(_UrlCandidate c) {
    final online = _urlStatus[c.url];
    final isCurrent = widget.api.baseUrl == c.url;
    return InkWell(
      onTap: () => _switchUrl(c.url),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 2),
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 3),
        decoration: BoxDecoration(
          color: isCurrent ? const Color(0xFF37474F) : Colors.transparent,
          borderRadius: BorderRadius.circular(3),
        ),
        child: Row(children: [
          Icon(
            online == null ? Icons.circle_outlined : (online ? Icons.check_circle : Icons.cancel),
            size: 12,
            color: online == null
                ? Colors.white38
                : (online ? Colors.greenAccent : Colors.redAccent),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              '${c.label}  •  ${c.url}',
              style: TextStyle(
                fontSize: 10,
                color: Colors.white,
                fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (isCurrent)
            const Padding(
              padding: EdgeInsets.only(left: 4),
              child: Text('đang dùng', style: TextStyle(fontSize: 9, color: Color(0xFFFFB74D), fontStyle: FontStyle.italic)),
            ),
        ]),
      ),
    );
  }

  Widget _sectionHeader(String title, {String? subtitle}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.bold,
                color: Color(0xFF26A69A))),
        if (subtitle != null)
          Text(subtitle, style: const TextStyle(fontSize: 10, color: Colors.white60)),
      ]),
    );
  }

  Widget _chip(String label, bool selected, VoidCallback onTap) {
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFF26A69A) : const Color(0xFF37474F),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(label,
              style: TextStyle(
                  fontSize: 11,
                  color: selected ? Colors.black : Colors.white,
                  fontWeight: selected ? FontWeight.bold : FontWeight.normal)),
        ),
      ),
    );
  }

  Widget _miniChip(String label, bool selected, VoidCallback onTap) {
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFF1976D2) : Colors.transparent,
            border: Border.all(color: const Color(0xFF455A64)),
            borderRadius: BorderRadius.circular(3),
          ),
          child: Text(label,
              style: TextStyle(
                  fontSize: 10,
                  color: selected ? Colors.white : Colors.white70,
                  fontWeight: selected ? FontWeight.bold : FontWeight.normal)),
        ),
      ),
    );
  }

  Widget _deviceRow(Device d) {
    final color = d.online ? const Color(0xFF26A69A) : (d.online == false ? Colors.redAccent : Colors.grey);
    return InkWell(
      onTap: () => _getLogsForDevice(d),
      onLongPress: () => _selectOne(d),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 2),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
        decoration: BoxDecoration(
          color: const Color(0xFF37474F),
          borderRadius: BorderRadius.circular(3),
          border: d.selected ? Border.all(color: const Color(0xFF26A69A)) : null,
        ),
        child: Row(children: [
          Checkbox(
            value: d.selected,
            onChanged: (v) {
              d.selected = v ?? false;
              setState(() {});
            },
            visualDensity: VisualDensity.compact,
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
          ),
          Container(
            width: 4,
            height: 32,
            decoration: BoxDecoration(
                color: color, borderRadius: BorderRadius.circular(2)),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                _typeBadge(d.type),
                const SizedBox(width: 4),
                Expanded(
                  child: Text('${d.ip}',
                      style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.bold,
                          color: Colors.white)),
                ),
              ]),
              Text('${d.note} • ${d.model.isEmpty ? "-" : d.model}',
                  style: const TextStyle(fontSize: 10, color: Colors.white60),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ]),
          ),
          // Inline "Xem log" button per device
          TextButton.icon(
            onPressed: () => _getLogsForDevice(d),
            style: TextButton.styleFrom(
              foregroundColor: const Color(0xFF26A69A),
              padding: const EdgeInsets.symmetric(horizontal: 4),
              minimumSize: const Size(56, 28),
            ),
            icon: const Icon(Icons.download, size: 12),
            label: const Text('Xem', style: TextStyle(fontSize: 10)),
          ),
          if (d.online)
            Text('${d.latencyMs}ms',
                style: const TextStyle(fontSize: 10, color: Color(0xFF26A69A)))
          else
            const Icon(Icons.cloud_off, size: 14, color: Colors.redAccent),
        ]),
      ),
    );
  }

  Widget _typeBadge(String type) {
    final colors = {
      'attendance': const Color(0xFF107C10),
      'signing': const Color(0xFF9B00D4),
      'server': const Color(0xFF607D8B),
      'gateway': const Color(0xFF607D8B),
      'virtual': const Color(0xFFFF8800),
    };
    final labels = {
      'attendance': 'CC',
      'signing': 'KY',
      'server': 'SV',
      'gateway': 'GW',
      'virtual': 'SIM',
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
      decoration: BoxDecoration(
        color: colors[type] ?? Colors.grey,
        borderRadius: BorderRadius.circular(2),
      ),
      child: Text(labels[type] ?? '?',
          style: const TextStyle(fontSize: 9, color: Colors.white, fontWeight: FontWeight.bold)),
    );
  }

  Widget _logRow(AttLog l) {
    final dt = l.timestampDate;
    final timeStr = dt != null ? DateFormat('HH:mm:ss dd/MM').format(dt) : '-';
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 1),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      decoration: BoxDecoration(
        color: (l.status == 0) ? const Color(0xFF1B5E20).withValues(alpha: 0.3) : const Color(0xFFB71C1C).withValues(alpha: 0.3),
        border: Border.all(color: const Color(0xFF455A64), width: 0.5),
        borderRadius: BorderRadius.circular(2),
      ),
      child: Row(children: [
        SizedBox(
          width: 80,
          child: Text(timeStr,
              style: const TextStyle(fontSize: 10, color: Colors.white70, fontFamily: 'monospace')),
        ),
        SizedBox(
          width: 50,
          child: Text(l.pin,
              style: const TextStyle(fontSize: 11, color: Colors.white, fontWeight: FontWeight.bold)),
        ),
        Expanded(
          child: Text(l.displayName,
              style: const TextStyle(fontSize: 11, color: Colors.white),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
          decoration: BoxDecoration(
            color: (l.status == 0) ? const Color(0xFF26A69A) : const Color(0xFFE91E63),
            borderRadius: BorderRadius.circular(2),
          ),
          child: Text(l.status == 0 ? 'IN' : 'OUT',
              style: const TextStyle(fontSize: 9, color: Colors.white, fontWeight: FontWeight.bold)),
        ),
      ]),
    );
  }
}

/// Floating bottom panel that shows bulk selection + XEM LOG button.
/// Always visible above the bottom nav so user can quickly select & fetch logs.
class LogBottomBar extends StatefulWidget {
  const LogBottomBar({super.key, required this.parent});
  final LogScreenState parent;

  @override
  State<LogBottomBar> createState() => _LogBottomBarState();
}

class _LogBottomBarState extends State<LogBottomBar> {
  @override
  Widget build(BuildContext context) {
    final p = widget.parent;
    final selectedCount = p.selectedCount;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF263238),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.3), blurRadius: 4, offset: const Offset(0, -2))],
      ),
      child: SafeArea(
        top: false,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          // Row 1: select helpers
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => p.selectAll(),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: Color(0xFF455A64)),
                  padding: const EdgeInsets.symmetric(vertical: 6),
                ),
                icon: const Icon(Icons.select_all, size: 14),
                label: const Text('Chọn tất cả', style: TextStyle(fontSize: 11)),
              ),
            ),
            const SizedBox(width: 4),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => p.deselectAll(),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: Color(0xFF455A64)),
                  padding: const EdgeInsets.symmetric(vertical: 6),
                ),
                icon: const Icon(Icons.deselect, size: 14),
                label: const Text('Bỏ chọn', style: TextStyle(fontSize: 11)),
              ),
            ),
            const SizedBox(width: 4),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => p.saveSelection(),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: Color(0xFF455A64)),
                  padding: const EdgeInsets.symmetric(vertical: 6),
                ),
                icon: const Icon(Icons.save, size: 14),
                label: const Text('Lưu', style: TextStyle(fontSize: 11)),
              ),
            ),
          ]),
          const SizedBox(height: 6),
          // Row 2: XEM LOG big button
          SizedBox(
            width: double.infinity,
            height: 44,
            child: ElevatedButton.icon(
              onPressed: (p.isLoading || selectedCount == 0)
                  ? null
                  : () => p.fetchLogsForSelected(),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF26A69A),
                foregroundColor: Colors.white,
                disabledBackgroundColor: const Color(0xFF455A64),
              ),
              icon: const Icon(Icons.download, size: 18),
              label: Text(
                selectedCount == 0
                    ? 'XEM LOG — chọn ít nhất 1 thiết bị'
                    : 'XEM LOG ($selectedCount thiết bị)',
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

