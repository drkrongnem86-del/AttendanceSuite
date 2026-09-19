// lib/screens/log_screen.dart
// AttendanceSuite v2.6.0 - Tab "Đọc log chấm công" (Lấy log từ máy chấm công)
// Style khớp với AttendanceSuite v2.0.13 PC EXE (dark theme, device list, log list)

import 'dart:async';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../api/pc_api.dart';
import 'package:intl/intl.dart';

class LogScreen extends StatefulWidget {
  const LogScreen({super.key, required this.api});
  final PcApi api;

  @override
  State<LogScreen> createState() => _LogScreenState();
}

class _LogScreenState extends State<LogScreen> {
  List<Device> _devices = [];
  List<AttLog> _logs = [];
  String? _status;
  bool _loading = false;
  String _mode = 'LAN';  // LAN | VPN
  String _localIp = '-';
  String _quickFilter = 'today';  // today | yesterday | week | month | all
  String _deviceTypeFilter = 'all'; // all | attendance | signing
  String _logDeviceFilter = 'all'; // IP filter
  String _searchQuery = '';
  Timer? _progressTimer;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void dispose() {
    _progressTimer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _status = null;
    });
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
      });
    } catch (e) {
      setState(() => _status = '⚠️ Python server chưa sẵn sàng: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _scanDevices() async {
    setState(() {
      _loading = true;
      _status = '🔍 Đang quét thiết bị...';
    });
    // Poll status every 2s để hiển thị tiến độ
    _progressTimer?.cancel();
    _progressTimer = Timer.periodic(const Duration(seconds: 2), (t) async {
      try {
        final s = await widget.api.getStatus();
        if (s['devices_count'] != null) {
          setState(() {
            // Trigger UI rebuild nhẹ
          });
        }
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
      setState(() => _loading = false);
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
      setState(() => _loading = false);
    }
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

    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(8),
        children: [
          // ============ Top row: title + status ============
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xFF263238),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Row(children: [
              const Icon(Icons.receipt_long, size: 16, color: Color(0xFF26A69A)),
              const SizedBox(width: 6),
              const Expanded(
                child: Text('ATTENDANCE LOG VIEWER',
                    style: TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.bold)),
              ),
              Text('Mode: $_mode',
                  style: TextStyle(
                      fontSize: 10,
                      color: _mode == 'VPN' ? Colors.orangeAccent : Colors.greenAccent,
                      fontWeight: FontWeight.bold)),
              const SizedBox(width: 8),
              IconButton(
                icon: const Icon(Icons.refresh, size: 18),
                color: Colors.white,
                onPressed: _loading ? null : _refresh,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
              ),
            ]),
          ),
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
              _chip('This Week', _quickFilter == 'week', () => setState(() => _quickFilter = 'week')),
              _chip('This Month', _quickFilter == 'month', () => setState(() => _quickFilter = 'month')),
              _chip('All', _quickFilter == 'all', () => setState(() => _quickFilter = 'all')),
              const SizedBox(width: 8),
              _chip('Export CSV', false, () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Export CSV - đang phát triển')),
                );
              }),
              _chip('Report', false, () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Báo cáo - đang phát triển')),
                );
              }),
              _chip('Excel', false, () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Excel - đang phát triển')),
                );
              }),
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
                const Icon(Icons.circle, size: 8, color: Color(0xFF26A69A)),
                const SizedBox(width: 4),
                Text('${_devices.where((d) => d.online).length}/${_devices.length}',
                    style: const TextStyle(fontSize: 11, color: Colors.white)),
              ]),
            ),
          ]),
          const SizedBox(height: 6),

          // ============ Device section ============
          _sectionHeader('DANH SACH THIET BI',
              subtitle:
                  '${_devices.length} thiết bị (${counts['attendance'] ?? 0} chấm công, ${counts['signing'] ?? 0} ký, ${_devices.where((d) => d.selected).length} chọn)'),
          // Filters for device list
          SizedBox(
            height: 28,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                _miniChip('Tất cả', _deviceTypeFilter == 'all', () => setState(() => _deviceTypeFilter = 'all')),
                _miniChip('CC only', _deviceTypeFilter == 'cc_only', () => setState(() => _deviceTypeFilter = 'cc_only')),
                _miniChip('Chỉ chấm công', _deviceTypeFilter == 'attendance', () => setState(() => _deviceTypeFilter = 'attendance')),
                _miniChip('Ký vân tay', _deviceTypeFilter == 'signing', () => setState(() => _deviceTypeFilter = 'signing')),
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
                _searchQuery = '';
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
                child: Text('Chưa có log. Bấm QUÉT hoặc chọn thiết bị để lấy log.',
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
