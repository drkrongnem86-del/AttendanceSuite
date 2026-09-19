// lib/screens/log_screen.dart
// AttendanceSuite v2.6.1 - Tab "Đọc log chấm công"
// Style khớp với AttendanceSuite v2.0.13 PC EXE (dark theme, device list, log list)
// v2.6.1: Thêm bulk-select (1/tất cả/bỏ chọn), nút Xem log nổi bật, retry Python.

import 'dart:async';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../api/pc_api.dart';
import 'package:intl/intl.dart';

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
  String _searchQuery = '';
  Timer? _progressTimer;
  bool _pythonReady = false;

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
        _mode = (diag['mode'] as String? ?? ((diag['is_vpn'] == true) ? 'VPN' : 'LAN')).toUpperCase();
        _localIp = diag['local_ip']?.toString() ?? '-';
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
      _status = '🔍 Đang quét thiết bị...';
    });
    _progressTimer?.cancel();
    _progressTimer = Timer.periodic(const Duration(seconds: 2), (t) async {
      try {
        await widget.api.getStatus();
      } catch (_) {}
    });
    try {
      final result = await widget.api.pingAll();
      final devs = await widget.api.getDevices();
      setState(() {
        _devices = devs;
        _mode = (result['mode']?.toString() ?? 'LAN').toUpperCase();
        _localIp = result['local_ip']?.toString() ?? _localIp;
        _status = '✅ Quét xong: ${result['online_count'] ?? 0}/${devs.length} thiết bị online '
            '(mode: ${result['mode']}, ${result['duration_ms']}ms)';
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
      _status = '📥 Đang lấy log từ ${devs.length} thiết bị...';
    });
    final allLogs = <AttLog>[];
    int okCount = 0;
    for (final d in devs) {
      try {
        final result = await widget.api.deviceAttlog(d.ip, limit: 200);
        if (result['ok'] == true) {
          final records = (result['records'] as List?)
                  ?.map((j) => AttLog.fromJson(j as Map<String, dynamic>))
                  .toList() ??
              [];
          allLogs.addAll(records);
          okCount++;
        }
      } catch (_) {}
    }
    allLogs.sort((a, b) => b.timestamp.compareTo(a.timestamp));
    if (!mounted) return;
    setState(() {
      _logs = allLogs;
      _status = '✅ Lấy log từ $okCount/${devs.length} thiết bị: ${allLogs.length} records';
      _loading = false;
    });
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
          // Log filters
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
            const SizedBox(width: 6),
            ElevatedButton(
              onPressed: () {
                _logDeviceFilter = 'all';
                setState(() {});
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF455A64),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              ),
              child: const Text('Clear', style: TextStyle(fontSize: 12)),
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
            ...ls.take(50).map((l) => _logRow(l)),
          const SizedBox(height: 80),
        ],
      ),
    );
  }

  Widget _pythonBanner() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: _pythonReady ? const Color(0xFF1B5E20) : const Color(0xFF455A64),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(children: [
        Icon(
          _pythonReady ? Icons.check_circle : Icons.error,
          size: 14,
          color: _pythonReady ? Colors.greenAccent : Colors.orangeAccent,
        ),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            _pythonReady
                ? 'Python OK • Mode: $_mode • IP: $_localIp • ${_devices.length} thiết bị'
                : 'Python chưa sẵn sàng (127.0.0.1:8080)',
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

