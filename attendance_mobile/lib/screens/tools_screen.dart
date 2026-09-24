// lib/screens/tools_screen.dart
// AttendanceSuite v2.7.2+45 - Tab "Tools" (ATTLOG Tools + ZK Tools + Inject Jobs + Quick Actions)
// v2.7.2+45: Add ZK Tools section (info/attlog/test_user/reboot via /api/zk/*)
//            Add Inject Jobs monitor (/api/inject/jobs, /api/inject/history)
//            Add quick-action buttons: Security Scan, Merge, Alerts, Backup, Reports
//            Keep v2.6.9 ATTLOG Tools + Recent view working

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/models.dart';
import '../api/pc_api.dart';

class ToolsScreen extends StatefulWidget {
  const ToolsScreen({super.key, required this.api});
  final PcApi api;

  @override
  State<ToolsScreen> createState() => _ToolsScreenState();
}

class _ToolsScreenState extends State<ToolsScreen> {
  String? _status;
  bool _running = false;

  // Quét thiết bị
  List<Device> _devices = [];
  String _selectedIp = '';

  // Chấm công thật
  final _ipCtrl = TextEditingController();
  final _pinCtrl = TextEditingController();
  DateTime _date = DateTime.now();
  TimeOfDay _time = TimeOfDay.now();
  int _punchType = 1;  // 1=card, 15=fingerprint
  int _statusIn = 0;   // 0=IN, 1=OUT

  // ATTLOG Recent view (v2.6.9)
  List<Map<String, dynamic>> _recentAttlog = [];
  int _recentLimit = 50;
  String _recentFilterIp = '';
  String _recentSearch = '';

  // ============ ZK Tools (v2.7.2+45 NEW) ============
  Map<String, dynamic>? _zkInfo;
  List<Map<String, dynamic>> _zkAttlog = [];
  String? _zkStatus;
  bool _zkLoading = false;
  int _zkAttlogLimit = 50;

  // ============ Inject Jobs monitor (v2.7.2+45 NEW) ============
  List<Map<String, dynamic>> _injectJobs = [];
  List<Map<String, dynamic>> _injectHistory = [];
  String? _injectStatus;
  bool _injectLoading = false;

  @override
  void initState() {
    super.initState();
    _ipCtrl.text = '';
    _pinCtrl.text = '';
    _loadDevices();
  }

  @override
  void dispose() {
    _ipCtrl.dispose();
    _pinCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadDevices() async {
    try {
      final devs = await widget.api.getDevices();
      setState(() => _devices = devs);
    } catch (_) {}
  }

  Future<void> _doScan() async {
    setState(() {
      _running = true;
      _status = '🔍 Đang quét thiết bị...';
    });
    try {
      await widget.api.pingAll();
      final live = await widget.api.getLive();
      final devs = (live['devices'] is List)
          ? (live['devices'] as List)
              .map((j) => Device.fromJson(j as Map<String, dynamic>))
              .toList()
          : await widget.api.getDevices();
      setState(() {
        _devices = devs;
        if (_selectedIp.isEmpty && devs.isNotEmpty) {
          _selectedIp = devs.first.ip;
          _ipCtrl.text = _selectedIp;
        }
        final oc = (live['online'] is num) ? (live['online'] as num).toInt() : devs.where((d) => d.online).length;
        _status = '✅ Quét xong: $oc/${devs.length} thiết bị online';
      });
    } catch (e) {
      setState(() => _status = '❌ $e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  Future<void> _doInject() async {
    if (_ipCtrl.text.isEmpty || _pinCtrl.text.isEmpty) {
      setState(() => _status = '⚠️ Nhập IP và PIN');
      return;
    }
    final dt = DateTime(_date.year, _date.month, _date.day, _time.hour, _time.minute);
    final ts = '${dt.year.toString().padLeft(4, '0')}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
        '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}:00';
    setState(() {
      _running = true;
      _status = '💉 Đang inject ATTLOG cho ${_ipCtrl.text} PIN=${_pinCtrl.text} @ $ts... (có thể mất 30-60s)';
    });
    try {
      final result = await widget.api.injectAttlog(
        ip: _ipCtrl.text,
        pin: _pinCtrl.text,
        timestamp: ts,
        status: _statusIn,
        punch: _punchType,
        verifyMode: 1,
        marker: 'APK_REAL_PUNCH',
      );
      if (result['ok'] == true) {
        setState(() => _status = '✅ INJECT THÀNH CÔNG!\n'
            'PIN: ${_pinCtrl.text} @ $ts → ${_ipCtrl.text}\n'
            '${result['message'] ?? ''}');
        // Auto refresh recent attlog
        await _loadRecentAttlog();
      } else {
        setState(() => _status = '❌ ${result['error'] ?? 'Unknown error'}');
      }
    } catch (e) {
      setState(() => _status = '❌ $e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  Future<void> _doCheckUser() async {
    if (_ipCtrl.text.isEmpty || _pinCtrl.text.isEmpty) {
      setState(() => _status = '⚠️ Nhập IP và PIN');
      return;
    }
    setState(() {
      _running = true;
      _status = '🔎 Đang kiểm tra user ${_pinCtrl.text} trên ${_ipCtrl.text}...';
    });
    try {
      final result = await widget.api.checkUser(ip: _ipCtrl.text, pin: _pinCtrl.text);
      if (result['ok'] == true) {
        final user = result['user'] ?? result['found'] ?? result;
        setState(() => _status = '✅ User tồn tại trên ${_ipCtrl.text}: $user');
      } else {
        setState(() => _status = '❌ ${result['error'] ?? 'User không tồn tại trên thiết bị'}');
      }
    } catch (e) {
      setState(() => _status = '❌ $e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  Future<void> _doRealPunch() async {
    if (_ipCtrl.text.isEmpty || _pinCtrl.text.isEmpty) {
      setState(() => _status = '⚠️ Nhập IP và PIN');
      return;
    }
    setState(() {
      _running = true;
      _status = '🟢 Đang REAL PUNCH ${_pinCtrl.text} → ${_ipCtrl.text}...';
    });
    try {
      final result = await widget.api.realPunch(ip: _ipCtrl.text, pin: _pinCtrl.text);
      if (result['ok'] == true) {
        setState(() => _status = '✅ REAL PUNCH OK\n'
            'PIN: ${_pinCtrl.text} → ${_ipCtrl.text}\n'
            '${result['message'] ?? ''}');
        await _loadRecentAttlog();
      } else {
        setState(() => _status = '❌ ${result['error'] ?? 'Real punch lỗi'}');
      }
    } catch (e) {
      setState(() => _status = '❌ $e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  // ============ Recent ATTLOG ============
  Future<void> _loadRecentAttlog() async {
    setState(() => _status = '📥 Đang tải ATTLOG gần nhất ($_recentLimit records)...');
    try {
      final list = await widget.api.getRecentAttlog(
        ip: _recentFilterIp.isEmpty ? null : _recentFilterIp,
        limit: _recentLimit,
      );
      setState(() {
        _recentAttlog = list;
        _status = '✅ Đã tải ${list.length} ATTLOG records (limit=$_recentLimit)';
      });
    } catch (e) {
      setState(() => _status = '❌ $e');
    }
  }

  List<Map<String, dynamic>> get _filteredRecent {
    var list = _recentAttlog;
    if (_recentSearch.isNotEmpty) {
      final q = _recentSearch.toLowerCase();
      list = list.where((r) {
        return (r['user_id']?.toString().toLowerCase().contains(q) ?? false) ||
            (r['uid']?.toString().toLowerCase().contains(q) ?? false) ||
            (r['device_ip']?.toString().toLowerCase().contains(q) ?? false) ||
            (r['timestamp']?.toString().toLowerCase().contains(q) ?? false);
      }).toList();
    }
    return list;
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(context: context, initialTime: _time);
    if (picked != null) setState(() => _time = picked);
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(8),
      children: [
        _header(),
        const SizedBox(height: 8),

        // ============ Device selection ============
        _section('1. Chọn thiết bị', expanded: true, children: [
          Row(children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _running ? null : _doScan,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF1976D2),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
                icon: const Icon(Icons.refresh, size: 16),
                label: const Text('Quét thiết bị', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ),
          ]),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            initialValue: _selectedIp.isEmpty ? null : _selectedIp,
            decoration: InputDecoration(
              labelText: 'Thiết bị (${_devices.length})',
              border: const OutlineInputBorder(),
              isDense: true,
              suffixIcon: _running
                  ? const Padding(
                      padding: EdgeInsets.all(10),
                      child: SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(strokeWidth: 2)),
                    )
                  : null,
            ),
            items: _devices
                .map((d) => DropdownMenuItem(
                    value: d.ip,
                    child: Text('${d.ip}  ${d.note.isEmpty ? "" : "(${d.note})"} ${d.online ? "🟢" : "🔴"}',
                        overflow: TextOverflow.ellipsis)))
                .toList(),
            onChanged: (v) {
              setState(() {
                _selectedIp = v ?? '';
                _ipCtrl.text = _selectedIp;
              });
            },
          ),
        ]),

        const SizedBox(height: 12),

        // ============ Inject ATTLOG (v2.6.9: no Web IP) ============
        _section('2. Chấm công thật (ghi ATTLOG lên máy)', expanded: true, children: [
          _info('Cảnh báo: ATTLOG có marker là "APK_REAL_PUNCH". Đây là tool debug, không nên dùng để chấm công giả.'),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _ipCtrl,
                decoration: const InputDecoration(labelText: 'IP thiết bị', border: OutlineInputBorder(), isDense: true, hintText: '172.16.0.212'),
                style: const TextStyle(fontSize: 13, fontFamily: 'monospace'),
              ),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: TextField(
                controller: _pinCtrl,
                decoration: const InputDecoration(labelText: 'PIN (mã NV)', border: OutlineInputBorder(), isDense: true),
                keyboardType: TextInputType.number,
                style: const TextStyle(fontSize: 13),
              ),
            ),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _pickDate,
                icon: const Icon(Icons.calendar_today, size: 14),
                label: Text('${_date.day.toString().padLeft(2, '0')}/${_date.month.toString().padLeft(2, '0')}/${_date.year}',
                    style: const TextStyle(fontSize: 13)),
              ),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _pickTime,
                icon: const Icon(Icons.access_time, size: 14),
                label: Text('${_time.hour.toString().padLeft(2, '0')}:${_time.minute.toString().padLeft(2, '0')}',
                    style: const TextStyle(fontSize: 13)),
              ),
            ),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            Expanded(
              child: DropdownButtonFormField<int>(
                initialValue: _statusIn,
                decoration: const InputDecoration(labelText: 'Trạng thái', border: OutlineInputBorder(), isDense: true),
                items: const [
                  DropdownMenuItem(value: 0, child: Text('Vào (IN)')),
                  DropdownMenuItem(value: 1, child: Text('Ra (OUT)')),
                ],
                onChanged: (v) => setState(() => _statusIn = v ?? 0),
              ),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: DropdownButtonFormField<int>(
                initialValue: _punchType,
                decoration: const InputDecoration(labelText: 'Loại', border: OutlineInputBorder(), isDense: true),
                items: const [
                  DropdownMenuItem(value: 1, child: Text('Thẻ (card)')),
                  DropdownMenuItem(value: 15, child: Text('Vân tay (FP)')),
                  DropdownMenuItem(value: 0, child: Text('Mật khẩu')),
                ],
                onChanged: (v) => setState(() => _punchType = v ?? 1),
              ),
            ),
          ]),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _running ? null : _doCheckUser,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF455A64),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
                icon: const Icon(Icons.search, size: 16),
                label: const Text('Check user'),
              ),
            ),
            const SizedBox(width: 6),
            Expanded(
              flex: 2,
              child: ElevatedButton.icon(
                onPressed: _running ? null : _doInject,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFD32F2F),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
                icon: const Icon(Icons.electrical_services, size: 16),
                label: Text(_running ? 'Đang inject...' : 'INJECT ATTLOG',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
              ),
            ),
          ]),
          const SizedBox(height: 6),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _running ? null : _doRealPunch,
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF26A69A),
                side: const BorderSide(color: Color(0xFF26A69A)),
                padding: const EdgeInsets.symmetric(vertical: 10),
              ),
              icon: const Icon(Icons.flash_on, size: 16),
              label: const Text('REAL PUNCH (chấm công giờ hiện tại)'),
            ),
          ),
        ]),

        const SizedBox(height: 12),

        // ============ Recent ATTLOG view (v2.6.9 NEW) ============
        _section('3. ATTLOG gần nhất (xem log thật)', expanded: true, children: [
          Row(children: [
            Expanded(
              child: DropdownButtonFormField<int>(
                initialValue: _recentLimit,
                decoration: const InputDecoration(labelText: 'Số records', border: OutlineInputBorder(), isDense: true),
                items: const [
                  DropdownMenuItem(value: 20, child: Text('20')),
                  DropdownMenuItem(value: 50, child: Text('50')),
                  DropdownMenuItem(value: 100, child: Text('100')),
                  DropdownMenuItem(value: 1000, child: Text('1000')),
                  DropdownMenuItem(value: 99999, child: Text('All (~674K)')),
                ],
                onChanged: (v) {
                  setState(() => _recentLimit = v ?? 50);
                  _loadRecentAttlog();
                },
              ),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: DropdownButtonFormField<String>(
                initialValue: _recentFilterIp.isEmpty ? null : _recentFilterIp,
                decoration: const InputDecoration(labelText: 'Lọc theo IP', border: OutlineInputBorder(), isDense: true),
                items: [
                  const DropdownMenuItem(value: '', child: Text('Tất cả')),
                  ..._devices.map((d) => DropdownMenuItem(value: d.ip, child: Text(d.ip, overflow: TextOverflow.ellipsis))),
                ],
                onChanged: (v) {
                  setState(() => _recentFilterIp = v ?? '');
                  _loadRecentAttlog();
                },
              ),
            ),
            const SizedBox(width: 6),
            ElevatedButton.icon(
              onPressed: _loadRecentAttlog,
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF1976D2),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
              ),
              icon: const Icon(Icons.refresh, size: 14),
              label: const Text('Tải', style: TextStyle(fontSize: 11)),
            ),
          ]),
          const SizedBox(height: 6),
          TextField(
            decoration: const InputDecoration(
              labelText: '🔍 Tìm UID / user_id / IP / thời gian',
              isDense: true,
              border: OutlineInputBorder(),
            ),
            style: const TextStyle(fontSize: 12),
            onChanged: (v) => setState(() => _recentSearch = v),
          ),
          const SizedBox(height: 6),
          if (_filteredRecent.isEmpty)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: const Color(0xFF37474F), borderRadius: BorderRadius.circular(4)),
              child: const Center(
                child: Text('Chưa có dữ liệu. Bấm Tải để lấy ATTLOG gần nhất từ backend.',
                    style: TextStyle(fontSize: 11, color: Colors.white60)),
              ),
            )
          else
            Container(
              constraints: const BoxConstraints(maxHeight: 400),
              decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: _filteredRecent.length,
                itemBuilder: (ctx, i) => _attlogRow(i + 1, _filteredRecent[i]),
              ),
            ),
        ]),

        const SizedBox(height: 12),

        // ============ ZK Tools (v2.7.2+45 NEW) ============
        _section('⭐ 4. ZK Tools - đọc máy thật qua port 4370 (v2.6.11)',
            expanded: false, children: [
          _info('Đọc thông tin trực tiếp từ máy chấm công qua pyzk (port 4370). Khác với /api/records cache, đây là data thật từ thiết bị.'),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: (_zkLoading || _ipCtrl.text.isEmpty) ? null : _doZkInfo,
                icon: const Icon(Icons.info_outline, size: 14),
                label: const Text('Info', style: TextStyle(fontSize: 12)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF6750A4),
                  side: const BorderSide(color: Color(0xFF6750A4)),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
            const SizedBox(width: 4),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: (_zkLoading || _ipCtrl.text.isEmpty) ? null : _doZkAttlog,
                icon: const Icon(Icons.receipt_long, size: 14),
                label: const Text('ATTLOG', style: TextStyle(fontSize: 12)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF1976D2),
                  side: const BorderSide(color: Color(0xFF1976D2)),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
            const SizedBox(width: 4),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: (_zkLoading || _ipCtrl.text.isEmpty || _pinCtrl.text.isEmpty) ? null : _doZkTestUser,
                icon: const Icon(Icons.person_search, size: 14),
                label: const Text('Test PIN', style: TextStyle(fontSize: 12)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF00897B),
                  side: const BorderSide(color: Color(0xFF00897B)),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
            const SizedBox(width: 4),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: (_zkLoading || _ipCtrl.text.isEmpty) ? null : _doZkReboot,
                icon: const Icon(Icons.restart_alt, size: 14, color: Color(0xFFD32F2F)),
                label: const Text('Reboot', style: TextStyle(fontSize: 12, color: Color(0xFFD32F2F))),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFFD32F2F),
                  side: const BorderSide(color: Color(0xFFD32F2F)),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
          ]),
          const SizedBox(height: 8),
          if (_zkLoading) const LinearProgressIndicator(minHeight: 2, color: Color(0xFF26A69A)),
          if (_zkInfo != null) ...[
            const SizedBox(height: 6),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: const Color(0xFF1B5E20).withValues(alpha: 0.3), borderRadius: BorderRadius.circular(4)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('📡 ${_zkInfo!['ip'] ?? '?'}', style: const TextStyle(color: Color(0xFF26A69A), fontSize: 13, fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                Text('FW: ${_zkInfo!['firmware'] ?? '?'}', style: const TextStyle(color: Colors.white70, fontSize: 11)),
                Text('Serial: ${_zkInfo!['serial'] ?? '?'}', style: const TextStyle(color: Colors.white70, fontSize: 11)),
                Text('Users: ${_zkInfo!['user_count'] ?? '?'}', style: const TextStyle(color: Colors.white70, fontSize: 11)),
                Text('Fingers: ${_zkInfo!['finger_count'] ?? '?'}', style: const TextStyle(color: Colors.white70, fontSize: 11)),
                Text('Records: ${_zkInfo!['attlog_count'] ?? '?'}', style: const TextStyle(color: Colors.white70, fontSize: 11)),
                Text('Platform: ${_zkInfo!['platform'] ?? '?'}', style: const TextStyle(color: Colors.white70, fontSize: 11)),
              ]),
            ),
          ],
          if (_zkAttlog.isNotEmpty) ...[
            const SizedBox(height: 6),
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
              constraints: const BoxConstraints(maxHeight: 200),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: _zkAttlog.length,
                itemBuilder: (ctx, i) {
                  final r = _zkAttlog[i];
                  final ts = r['timestamp'] ?? '';
                  final uid = r['user_id'] ?? r['uid'] ?? '?';
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text('$ts  UID=$uid  P${r['punch'] ?? '?'}  S${r['status'] ?? '?'}',
                        style: const TextStyle(color: Colors.white, fontSize: 10, fontFamily: 'monospace')),
                  );
                },
              ),
            ),
          ],
          if (_zkStatus != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(_zkStatus!, style: const TextStyle(color: Colors.white70, fontSize: 11)),
            ),
        ]),

        const SizedBox(height: 12),

        // ============ Inject Jobs monitor (v2.7.2+45 NEW) ============
        _section('⭐ 5. Inject Jobs - theo dõi job inject (v2.6.11)',
            expanded: false, children: [
          Row(children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _injectLoading ? null : _loadInjectJobs,
                icon: const Icon(Icons.list, size: 14),
                label: const Text('Jobs', style: TextStyle(fontSize: 11)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF1976D2),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _injectLoading ? null : _loadInjectHistory,
                icon: const Icon(Icons.history, size: 14),
                label: const Text('History', style: TextStyle(fontSize: 11)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFE65100),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
          ]),
          const SizedBox(height: 6),
          if (_injectLoading) const LinearProgressIndicator(minHeight: 2, color: Color(0xFFE65100)),
          if (_injectJobs.isNotEmpty) ...[
            const SizedBox(height: 6),
            Container(
              constraints: const BoxConstraints(maxHeight: 200),
              decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: _injectJobs.length,
                itemBuilder: (ctx, i) {
                  final j = _injectJobs[i];
                  final status = (j['status'] ?? '').toString();
                  final color = status == 'done' ? const Color(0xFF66BB6A)
                      : status == 'running' ? const Color(0xFF1976D2)
                      : status == 'error' ? const Color(0xFFD32F2F)
                      : Colors.white60;
                  return ListTile(
                    dense: true,
                    leading: Icon(Icons.bolt, color: color, size: 18),
                    title: Text('${j['job_id'] ?? j['id'] ?? '?'}', style: const TextStyle(color: Colors.white, fontSize: 11, fontFamily: 'monospace')),
                    subtitle: Text('${j['ip'] ?? '?'} • ${status} • ${j['progress'] ?? ''}',
                        style: TextStyle(color: color, fontSize: 10)),
                    trailing: Text(j['created_at']?.toString().substring(0, 16) ?? '',
                        style: const TextStyle(color: Colors.white38, fontSize: 9)),
                  );
                },
              ),
            ),
          ],
          if (_injectHistory.isNotEmpty) ...[
            const SizedBox(height: 6),
            Container(
              constraints: const BoxConstraints(maxHeight: 200),
              decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: _injectHistory.length,
                itemBuilder: (ctx, i) {
                  final h = _injectHistory[i];
                  return ListTile(
                    dense: true,
                    leading: const Icon(Icons.history, color: Color(0xFFE65100), size: 16),
                    title: Text('${h['ip'] ?? '?'} • PIN ${h['pin'] ?? '?'}',
                        style: const TextStyle(color: Colors.white, fontSize: 11)),
                    subtitle: Text('${h['marker'] ?? ''} • ${h['timestamp'] ?? ''}',
                        style: const TextStyle(color: Colors.white60, fontSize: 10)),
                  );
                },
              ),
            ),
          ],
          if (_injectStatus != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(_injectStatus!, style: const TextStyle(color: Colors.white70, fontSize: 11)),
            ),
        ]),

        const SizedBox(height: 12),

        // ============ Quick Actions (v2.7.2+45 NEW) ============
        _section('⭐ 6. Quick Actions - báo cáo + alerts + backup + merge',
            expanded: false, children: [
          Wrap(spacing: 6, runSpacing: 6, children: [
            _quickAction(Icons.security, 'Security Scan', 'Scan 24 máy (60-120s VPN)', _doQuickSecurityScan, const Color(0xFF1976D2)),
            _quickAction(Icons.merge_type, 'Merge Today', 'Xem merge data hôm nay', _doQuickMerge, const Color(0xFF6750A4)),
            _quickAction(Icons.warning_amber, 'Alerts Missing', 'NV chưa chấm công hôm nay', _doQuickAlerts, const Color(0xFFE65100)),
            _quickAction(Icons.backup, 'Backup Now', 'Trigger backup ngay (1-5 phút)', _doQuickBackup, const Color(0xFF00897B)),
            _quickAction(Icons.summarize, 'Report Today', 'Báo cáo chấm công hôm nay', _doQuickReportToday, const Color(0xFF7B1FA2)),
            _quickAction(Icons.file_download, 'Report Export', 'Export Excel hôm nay', _doQuickReportExport, const Color(0xFF455A64)),
            _quickAction(Icons.list_alt, 'Inject Devices', 'List máy có inject capability', _doQuickInjectDevices, const Color(0xFFD32F2F)),
            _quickAction(Icons.verified_user, 'Sec Devices', 'Devices với risk score', _doQuickSecurityDevices, const Color(0xFF00897B)),
          ]),
          if (_status != null && _status!.contains('Quick'))
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
                child: Text(_status!, style: const TextStyle(color: Colors.white70, fontSize: 11, fontFamily: 'monospace')),
              ),
            ),
        ]),

        const SizedBox(height: 12),

        if (_status != null)
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: _status!.startsWith('❌') || _status!.startsWith('⚠️')
                  ? Colors.red.shade900.withValues(alpha: 0.5)
                  : const Color(0xFF1B5E20).withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(_status!, style: const TextStyle(color: Colors.white, fontSize: 13)),
          ),

        const SizedBox(height: 80),
      ],
    );
  }

  Widget _attlogRow(int idx, Map<String, dynamic> r) {
    final ts = r['timestamp'] ?? r['date'] ?? '';
    final uid = r['user_id'] ?? r['uid'] ?? '?';
    final ip = r['device_ip'] ?? r['ip'] ?? '';
    final status = r['status'] ?? '';
    return Container(
      decoration: BoxDecoration(
        color: idx.isEven ? const Color(0xFF37474F) : const Color(0xFF455A64),
        border: const Border(bottom: BorderSide(color: Color(0xFF263238), width: 0.5)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Row(children: [
        SizedBox(width: 32, child: Text('$idx', style: const TextStyle(fontSize: 10, color: Colors.white70))),
        Expanded(
          flex: 3,
          child: Text(uid.toString(),
              style: const TextStyle(fontSize: 11, color: Colors.white, fontFamily: 'monospace', fontWeight: FontWeight.bold)),
        ),
        Expanded(
          flex: 4,
          child: Text(ts.toString(),
              style: const TextStyle(fontSize: 10, color: Colors.white70, fontFamily: 'monospace')),
        ),
        Expanded(
          flex: 3,
          child: Text(ip.toString(),
              style: const TextStyle(fontSize: 10, color: Color(0xFF26A69A), fontFamily: 'monospace')),
        ),
        SizedBox(
          width: 36,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
              decoration: BoxDecoration(
                color: (status == 1 || status == '1' || status == 'IN')
                    ? const Color(0xFF26A69A).withValues(alpha: 0.3)
                    : Colors.orange.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2),
              ),
              child: Text(status.toString(),
                  style: const TextStyle(fontSize: 9, color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ),
        ),
      ]),
    );
  }

  Widget _header() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
      child: const Row(children: [
        Icon(Icons.bolt, size: 16, color: Color(0xFFE53935)),
        SizedBox(width: 6),
        Text('ATTLOG TOOLS - v2.6.9',
            style: TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.bold)),
      ]),
    );
  }

  Widget _section(String title, {required bool expanded, required List<Widget> children}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(color: const Color(0xFF37474F), borderRadius: BorderRadius.circular(4)),
      padding: const EdgeInsets.all(10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Color(0xFF26A69A))),
        const SizedBox(height: 6),
        ...children,
      ]),
    );
  }

  Widget _info(String text) {
    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(color: const Color(0xFFFFA000).withValues(alpha: 0.2), borderRadius: BorderRadius.circular(3)),
      child: Text(text, style: const TextStyle(fontSize: 11, color: Color(0xFFFFE082))),
    );
  }

  // ============ ZK Tools methods (v2.7.2+45 NEW) ============
  Future<void> _doZkInfo() async {
    final ip = _ipCtrl.text.trim();
    if (ip.isEmpty) return;
    setState(() { _zkLoading = true; _zkStatus = '🔄 Đang đọc ZK info...'; });
    final r = await widget.api.zkInfo(ip);
    if (!mounted) return;
    setState(() {
      _zkLoading = false;
      if (r['ok'] == true) {
        _zkInfo = r;
        _zkStatus = '✅ ZK info OK: ${r['user_count'] ?? '?'} users, ${r['attlog_count'] ?? '?'} records';
      } else {
        _zkStatus = '❌ Lỗi: ${r['error'] ?? 'unknown'}';
      }
    });
  }

  Future<void> _doZkAttlog() async {
    final ip = _ipCtrl.text.trim();
    if (ip.isEmpty) return;
    setState(() { _zkLoading = true; _zkStatus = '🔄 Đang đọc ZK ATTLOG từ máy (timeout 180s)...'; });
    final r = await widget.api.zkAttlog(ip, limit: _zkAttlogLimit);
    if (!mounted) return;
    final records = (r['records'] is List) ? List<Map<String, dynamic>>.from(r['records']) : <Map<String, dynamic>>[];
    setState(() {
      _zkLoading = false;
      _zkAttlog = records;
      _zkStatus = records.isEmpty
          ? '❌ Không có record. Lỗi: ${r['error'] ?? 'unknown'}'
          : '✅ ZK ATTLOG: ${records.length} records (sort desc timestamp)';
    });
  }

  Future<void> _doZkTestUser() async {
    final ip = _ipCtrl.text.trim();
    final pin = _pinCtrl.text.trim();
    if (ip.isEmpty || pin.isEmpty) return;
    setState(() { _zkLoading = true; _zkStatus = '🔄 Test PIN $pin...'; });
    final r = await widget.api.zkTestUser(ip, pin);
    if (!mounted) return;
    setState(() {
      _zkLoading = false;
      if (r['ok'] == true) {
        _zkStatus = r['exists'] == true
            ? '✅ PIN $pin tồn tại: ${r['user_name'] ?? '?'}'
            : '⚠️ PIN $pin không tồn tại';
      } else {
        _zkStatus = '❌ Lỗi: ${r['error'] ?? 'unknown'}';
      }
    });
  }

  Future<void> _doZkReboot() async {
    final ip = _ipCtrl.text.trim();
    if (ip.isEmpty) return;
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF263238),
        title: const Row(children: [
          Icon(Icons.warning, color: Color(0xFFD32F2F)),
          SizedBox(width: 8),
          Text('Reboot máy?', style: TextStyle(color: Colors.white, fontSize: 16)),
        ]),
        content: Text(
          'Bạn sắp reboot thiết bị $ip.\n\n'
          '⚠️ Máy sẽ offline ~30 giây.\n'
          '⚠️ Các ATTLOG chưa sync sẽ bị mất.\n\n'
          'Chắc chắn?',
          style: const TextStyle(color: Colors.white70, fontSize: 13, height: 1.4),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Hủy', style: TextStyle(color: Colors.white60))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('REBOOT', style: TextStyle(color: Color(0xFFD32F2F), fontWeight: FontWeight.bold))),
        ],
      ),
    );
    if (confirm != true) return;
    setState(() { _zkLoading = true; _zkStatus = '🔄 Đang gửi reboot command...'; });
    final r = await widget.api.zkReboot(ip);
    if (!mounted) return;
    setState(() {
      _zkLoading = false;
      _zkStatus = r['ok'] == true
          ? '✅ Đã gửi reboot. Máy sẽ online sau ~30s'
          : '❌ Lỗi: ${r['error'] ?? 'unknown'}';
    });
  }

  // ============ Inject Jobs methods (v2.7.2+45 NEW) ============
  Future<void> _loadInjectJobs() async {
    setState(() { _injectLoading = true; _injectStatus = '🔄 Loading inject jobs...'; });
    final r = await widget.api.injectJobs();
    if (!mounted) return;
    final jobs = (r['jobs'] is List) ? List<Map<String, dynamic>>.from(r['jobs']) : <Map<String, dynamic>>[];
    setState(() {
      _injectLoading = false;
      _injectJobs = jobs;
      _injectStatus = jobs.isEmpty ? '⚠️ Không có job nào' : '✅ ${jobs.length} jobs';
    });
  }

  Future<void> _loadInjectHistory() async {
    setState(() { _injectLoading = true; _injectStatus = '🔄 Loading inject history...'; });
    final r = await widget.api.injectHistory(limit: 50);
    if (!mounted) return;
    final hist = (r['history'] is List) ? List<Map<String, dynamic>>.from(r['history']) : <Map<String, dynamic>>[];
    setState(() {
      _injectLoading = false;
      _injectHistory = hist;
      _injectStatus = hist.isEmpty ? '⚠️ Không có history' : '✅ ${hist.length} past injections';
    });
  }

  // ============ Quick Actions (v2.7.2+45 NEW) ============
  Widget _quickAction(IconData icon, String label, String tooltip, Future<void> Function() onTap, Color color) {
    return Tooltip(
      message: tooltip,
      child: ElevatedButton.icon(
        onPressed: _running ? null : () async {
          setState(() => _running = true);
          try { await onTap(); } finally { if (mounted) setState(() => _running = false); }
        },
        icon: Icon(icon, size: 14),
        label: Text(label, style: const TextStyle(fontSize: 11)),
        style: ElevatedButton.styleFrom(
          backgroundColor: color,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        ),
      ),
    );
  }

  Future<void> _doQuickSecurityScan() async {
    final r = await widget.api.pingAll();
    if (!mounted) return;
    setState(() {
      _status = 'Quick: Security scan\n${_summarize(r)}';
    });
  }

  Future<void> _doQuickMerge() async {
    final r = await widget.api.mergeToday();
    if (!mounted) return;
    setState(() {
      _status = 'Quick: Merge today\n${_summarize(r)}';
    });
  }

  Future<void> _doQuickAlerts() async {
    final r = await widget.api.alertsMissing();
    if (!mounted) return;
    setState(() {
      _status = 'Quick: Alerts missing\n${_summarize(r)}';
    });
  }

  Future<void> _doQuickBackup() async {
    setState(() => _status = 'Quick: Backup đang chạy...');
    final r = await widget.api.backupNow();
    if (!mounted) return;
    setState(() {
      _status = 'Quick: Backup\n${_summarize(r)}';
    });
  }

  Future<void> _doQuickReportToday() async {
    final r = await widget.api.reportToday();
    if (!mounted) return;
    setState(() {
      _status = 'Quick: Report today\n${_summarize(r)}';
    });
  }

  Future<void> _doQuickReportExport() async {
    setState(() => _status = 'Quick: Exporting Excel...');
    final bytes = await widget.api.reportExport();
    if (!mounted) return;
    if (bytes == null || bytes.isEmpty) {
      setState(() => _status = '❌ Quick: Export failed');
      return;
    }
    setState(() => _status = '✅ Quick: Report exported (${(bytes.length / 1024).toStringAsFixed(1)} KB)');
  }

  Future<void> _doQuickInjectDevices() async {
    final r = await widget.api.injectDevices();
    if (!mounted) return;
    setState(() {
      _status = 'Quick: Inject devices\n${_summarize(r)}';
    });
  }

  Future<void> _doQuickSecurityDevices() async {
    final r = await widget.api.securityDevices();
    if (!mounted) return;
    setState(() {
      _status = 'Quick: Security devices\n${_summarize(r)}';
    });
  }

  String _summarize(Map<String, dynamic> r) {
    if (r['ok'] == false) return '❌ ${r['error'] ?? 'unknown'}';
    // Drop noisy fields
    final copy = Map<String, dynamic>.from(r);
    copy.remove('ok');
    copy.remove('error');
    // Truncate long lists
    if (copy['records'] is List && (copy['records'] as List).length > 5) {
      copy['records'] = '${(copy['records'] as List).length} items (showing first 5): ${(copy['records'] as List).take(5)}';
    }
    if (copy['devices'] is List && (copy['devices'] as List).length > 5) {
      copy['devices'] = '${(copy['devices'] as List).length} items (showing first 5): ${(copy['devices'] as List).take(5)}';
    }
    return const JsonEncoderMini().convert(copy);
  }
}

/// Inline mini JSON pretty-printer to avoid dart:convert dependency in tools
class JsonEncoderMini {
  const JsonEncoderMini();
  String convert(dynamic v, [int depth = 0]) {
    if (depth > 2) return '...';
    if (v == null) return 'null';
    if (v is num || v is bool) return v.toString();
    if (v is String) return v.length > 60 ? '"${v.substring(0, 60)}..."' : '"$v"';
    if (v is List) {
      if (v.isEmpty) return '[]';
      return '[${v.take(3).map((e) => convert(e, depth + 1)).join(', ')}${v.length > 3 ? ', ...' : ''}]';
    }
    if (v is Map) {
      if (v.isEmpty) return '{}';
      return '{${v.entries.take(5).map((e) => '"${e.key}": ${convert(e.value, depth + 1)}').join(', ')}${v.length > 5 ? ', ...' : ''}}';
    }
    return v.toString();
  }
}
