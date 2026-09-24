// lib/screens/live_screen.dart
// AttendanceSuite v2.6.3 - Tab "Live Device Status" (Auto-probe moi 8 giay)
// PC EXE v2.0.13 style: bang device IP, ten, loai, trang thai, latency, log count, probe luc, loi

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../models/models.dart';
import '../api/pc_api.dart';

class LiveScreen extends StatefulWidget {
  const LiveScreen({super.key, required this.api});
  final PcApi api;

  @override
  State<LiveScreen> createState() => LiveScreenState();
}

class LiveScreenState extends State<LiveScreen> {
  List<Device> _devices = [];
  bool _probing = false;
  bool _autoEnabled = true;  // v2.6.9: track auto state explicitly
  String? _status;
  Timer? _probeTimer;
  // v2.6.5: BV v1.3.0 backend scan 27 devices mat ~30-60s qua Sophos VPN.
  // Tang interval tu 8s len 30s de khong spam backend.
  int _probeIntervalSec = 30;
  String _searchQuery = '';
  String _typeFilter = 'all'; // all | cc | ky | sv | sim
  String _statusFilter = 'all'; // all | online | offline
  DateTime? _lastProbeAt;

  @override
  void initState() {
    super.initState();
    _refresh();
    _startAutoProbe();
  }

  @override
  void dispose() {
    _probeTimer?.cancel();
    super.dispose();
  }

  void _startAutoProbe() {
    _probeTimer?.cancel();
    _autoEnabled = true;
    _probeTimer = Timer.periodic(Duration(seconds: _probeIntervalSec), (_) => _probe());
  }

  // v2.6.9: Dừng toàn bộ - bao gồm auto-probe + cancel current in-flight probe
  void _stopAll() {
    // 1. Hủy auto-probe timer
    _probeTimer?.cancel();
    _probeTimer = null;
    _autoEnabled = false;
    // 2. Note: không thể cancel HTTP request đang chạy, nhưng set _probing flag để next probe bị skip
    // Khi current request trả về, _probing sẽ tự reset về false trong finally block
    if (mounted) {
      setState(() {
        _status = '⏹ Đã dừng auto-probe (current request sẽ hoàn tất)';
      });
    }
  }

  void _startAll() {
    if (mounted) setState(() {
      _autoEnabled = true;
      _status = '▶ Đã bật auto-probe (mỗi ${_probeIntervalSec}s)';
    });
    _startAutoProbe();
  }

  Future<void> _refresh() async {
    setState(() => _status = '🔄 Đang tải...');
    try {
      final devs = await widget.api.getDevices();
      setState(() {
        _devices = devs;
        _status = null;
      });
    } catch (e) {
      setState(() => _status = '⚠️ $e');
    }
  }

  Future<void> _probe() async {
    if (_probing) return;  // skip if previous probe still running
    setState(() {
      _probing = true;
      _lastProbeAt = DateTime.now();
    });
    try {
      await widget.api.pingAll();
      final live = await widget.api.getLive();
      final List<Device> devs;
      if (live['devices'] is List) {
        devs = (live['devices'] as List)
            .map((j) => Device.fromJson(j as Map<String, dynamic>))
            .toList();
      } else {
        devs = await widget.api.getDevices();
      }
      final onlineCount = (live['online'] is num)
          ? (live['online'] as num).toInt()
          : devs.where((d) => d.online).length;
      if (!mounted) return;
      setState(() {
        _devices = devs;
        _status = '✅ Probe lúc ${DateFormat('HH:mm:ss').format(_lastProbeAt!)}: '
            '$onlineCount/${devs.length} online';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _status = '❌ Probe lỗi: $e');
    } finally {
      if (mounted) setState(() => _probing = false);
    }
  }

  void _toggleAutoProbe() {
    // v2.6.9: explicit stop/start instead of buggy toggle
    if (_autoEnabled) {
      _stopAll();
    } else {
      _startAll();
    }
  }

  List<Device> get _filtered {
    var list = _devices;
    if (_typeFilter == 'cc') list = list.where((d) => d.type == 'attendance').toList();
    if (_typeFilter == 'ky') list = list.where((d) => d.type == 'signing').toList();
    if (_typeFilter == 'sv') list = list.where((d) => d.type == 'server' || d.type == 'gateway').toList();
    if (_typeFilter == 'sim') list = list.where((d) => d.type == 'virtual').toList();
    if (_statusFilter == 'online') list = list.where((d) => d.online).toList();
    if (_statusFilter == 'offline') list = list.where((d) => !d.online).toList();
    if (_searchQuery.isNotEmpty) {
      list = list
          .where((d) => d.ip.toLowerCase().contains(_searchQuery.toLowerCase()) ||
              d.note.toLowerCase().contains(_searchQuery.toLowerCase()))
          .toList();
    }
    return list;
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filtered;
    final onlineCount = _devices.where((d) => d.online).length;
    final offlineCount = _devices.length - onlineCount;
    final lastProbeStr = _lastProbeAt != null ? DateFormat('HH:mm:ss').format(_lastProbeAt!) : '--:--:--';

    return ListView(
      padding: const EdgeInsets.all(8),
      children: [
        _header(),
        const SizedBox(height: 8),

        // ============ Top controls ============
        Row(children: [
          Expanded(
            child: ElevatedButton.icon(
              onPressed: _probing ? null : _probe,
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF1976D2),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 10),
              ),
              icon: Icon(_probing ? Icons.hourglass_top : Icons.refresh, size: 16),
              label: Text(_probing ? 'Đang probe...' : 'PROBE NGAY',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
            ),
          ),
          const SizedBox(width: 6),
          ElevatedButton.icon(
            onPressed: _toggleAutoProbe,
            style: ElevatedButton.styleFrom(
              backgroundColor: _autoEnabled ? Colors.orange.shade700 : const Color(0xFF455A64),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
            ),
            icon: Icon(_autoEnabled ? Icons.stop_circle : Icons.play_circle, size: 16),
            label: Text(_autoEnabled ? 'Dừng' : 'Auto',
                style: const TextStyle(fontSize: 11)),
          ),
        ]),
        const SizedBox(height: 8),

        // ============ Stats row ============
        Row(children: [
          Expanded(child: _statBox('${_devices.length}', 'Tổng thiết bị', const Color(0xFF1976D2))),
          const SizedBox(width: 6),
          Expanded(child: _statBox('$onlineCount', 'Online', const Color(0xFF26A69A))),
          const SizedBox(width: 6),
          Expanded(child: _statBox('$offlineCount', 'Offline', const Color(0xFFE53935))),
          const SizedBox(width: 6),
          Expanded(child: _statBox(lastProbeStr, 'Probe lúc', const Color(0xFF37474F))),
        ]),
        const SizedBox(height: 8),

        // ============ Filters ============
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: [
            _chip('Tất cả', _statusFilter == 'all', () => setState(() => _statusFilter = 'all')),
            _chip('Online', _statusFilter == 'online', () => setState(() => _statusFilter = 'online')),
            _chip('Offline', _statusFilter == 'offline', () => setState(() => _statusFilter = 'offline')),
            const SizedBox(width: 8),
            _chip('CC', _typeFilter == 'cc', () => setState(() => _typeFilter = 'cc')),
            _chip('KY', _typeFilter == 'ky', () => setState(() => _typeFilter = 'ky')),
            _chip('SV', _typeFilter == 'sv', () => setState(() => _typeFilter = 'sv')),
            _chip('SIM', _typeFilter == 'sim', () => setState(() => _typeFilter = 'sim')),
          ]),
        ),
        const SizedBox(height: 6),
        TextField(
          decoration: const InputDecoration(
            isDense: true,
            hintText: '🔍 Tìm theo IP / tên / lỗi...',
            border: OutlineInputBorder(),
            contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          ),
          style: const TextStyle(fontSize: 13),
          onChanged: (v) => setState(() => _searchQuery = v),
        ),
        const SizedBox(height: 6),

        // ============ Status banner ============
        if (_status != null)
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: const Color(0xFF37474F),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(_status!,
                style: const TextStyle(fontSize: 11, color: Colors.white)),
          ),
        const SizedBox(height: 6),

        // ============ Device table ============
        if (filtered.isEmpty)
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: const Color(0xFF37474F),
              borderRadius: BorderRadius.circular(4),
            ),
            child: const Center(
              child: Text('Chưa có thiết bị hoặc không khớp filter',
                  style: TextStyle(fontSize: 12, color: Colors.white60)),
            ),
          )
        else
          // Table header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xFF263238),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(4),
                topRight: Radius.circular(4),
              ),
            ),
            child: Row(children: const [
              SizedBox(width: 28, child: Text('#', style: TextStyle(fontSize: 10, color: Colors.white70, fontWeight: FontWeight.bold))),
              Expanded(flex: 3, child: Text('IP', style: TextStyle(fontSize: 10, color: Colors.white70, fontWeight: FontWeight.bold))),
              Expanded(flex: 3, child: Text('Tên thiết bị', style: TextStyle(fontSize: 10, color: Colors.white70, fontWeight: FontWeight.bold))),
              SizedBox(width: 32, child: Text('Loại', style: TextStyle(fontSize: 10, color: Colors.white70, fontWeight: FontWeight.bold), textAlign: TextAlign.center)),
              SizedBox(width: 64, child: Text('Trạng thái', style: TextStyle(fontSize: 10, color: Colors.white70, fontWeight: FontWeight.bold), textAlign: TextAlign.center)),
              SizedBox(width: 56, child: Text('Latency', style: TextStyle(fontSize: 10, color: Colors.white70, fontWeight: FontWeight.bold), textAlign: TextAlign.right)),
            ]),
          ),
          ...filtered.asMap().entries.map((e) => _row(e.key + 1, e.value)),
          const SizedBox(height: 80),
      ],
    );
  }

  Widget _row(int idx, Device d) {
    final color = d.online ? const Color(0xFF26A69A) : Colors.redAccent;
    return Container(
      decoration: BoxDecoration(
        color: idx.isEven ? const Color(0xFF37474F) : const Color(0xFF455A64),
        border: const Border(
          bottom: BorderSide(color: Color(0xFF263238), width: 0.5),
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      child: Row(children: [
        SizedBox(width: 28, child: Text('$idx', style: const TextStyle(fontSize: 10, color: Colors.white70, fontFamily: 'monospace'))),
        Expanded(flex: 3, child: SelectableText(d.ip,
            style: const TextStyle(fontSize: 11, color: Colors.white, fontFamily: 'monospace'))),
        Expanded(flex: 3, child: Text(d.note.isEmpty ? '-' : d.note,
            style: const TextStyle(fontSize: 10, color: Colors.white70),
            maxLines: 1, overflow: TextOverflow.ellipsis)),
        SizedBox(width: 32, child: Center(child: _typeBadge(d.type))),
        SizedBox(
          width: 64,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(2),
              border: Border.all(color: color, width: 0.5),
            ),
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(d.online ? Icons.wifi : Icons.cloud_off, size: 10, color: color),
              const SizedBox(width: 2),
              Text(d.online ? 'Online' : 'Offline',
                  style: TextStyle(fontSize: 9, color: color, fontWeight: FontWeight.bold)),
            ]),
          ),
        ),
        SizedBox(
          width: 56,
          child: Text(
            d.online ? '${d.latencyMs} ms' : '-',
            textAlign: TextAlign.right,
            style: TextStyle(fontSize: 10, color: d.online ? const Color(0xFF26A69A) : Colors.white54, fontFamily: 'monospace'),
          ),
        ),
      ]),
    );
  }

  Widget _typeBadge(String type) {
    final colors = {
      'attendance': const Color(0xFF1976D2),
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

  Widget _statBox(String value, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Column(children: [
        Text(value, style: TextStyle(fontSize: 16, color: color, fontWeight: FontWeight.bold)),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 9, color: Colors.white70)),
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

  Widget _header() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
      child: Row(children: [
        const Icon(Icons.sensors, size: 16, color: Color(0xFF26A69A)),
        const SizedBox(width: 6),
        const Text('LIVE DEVICE STATUS',
            style: TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.bold)),
        const Spacer(),
        Text('Auto-probe ${_probeIntervalSec}s ${_autoEnabled ? "▶" : "⏹"}',
            style: TextStyle(fontSize: 10, color: _autoEnabled ? const Color(0xFF26A69A) : Colors.white38)),
      ]),
    );
  }
}
