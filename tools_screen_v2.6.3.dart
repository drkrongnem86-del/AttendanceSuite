// lib/screens/tools_screen.dart
// AttendanceSuite v2.6.0 - Tab "ATTLOG Tools" (CVE-2023-3941 - inject ATTLOG)

import 'dart:async';
import 'package:flutter/material.dart';
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
  String _selectedWebIp = '172.16.254.202';

  // Chấm công thật
  final _ipCtrl = TextEditingController();
  final _pinCtrl = TextEditingController();
  final _webIpCtrl = TextEditingController(text: '172.16.254.202');
  DateTime _date = DateTime.now();
  TimeOfDay _time = TimeOfDay.now();
  int _punchType = 1;  // 1=card, 15=fingerprint
  int _statusIn = 0;   // 0=IN, 1=OUT

  @override
  void initState() {
    super.initState();
    _ipCtrl.text = '';
    _pinCtrl.text = '';
    _webIpCtrl.text = _selectedWebIp;
    _loadDevices();
  }

  @override
  void dispose() {
    _ipCtrl.dispose();
    _pinCtrl.dispose();
    _webIpCtrl.dispose();
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
      _status = '🔍 Quét thiết bị...';
    });
    try {
      final result = await widget.api.pingAll();
      final devs = await widget.api.getDevices();
      setState(() {
        _devices = devs;
        if (_selectedIp.isEmpty && devs.isNotEmpty) {
          _selectedIp = devs.first.ip;
          _ipCtrl.text = _selectedIp;
        }
        _status = '✅ Quét xong: ${result['online_count']}/${devs.length} thiết bị online';
      });
    } catch (e) {
      setState(() => _status = '❌ $e');
    } finally {
      setState(() => _running = false);
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
      _status = '💉 Đang inject ATTLOG cho ${_ipCtrl.text}... (có thể mất 30-60s)';
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
        webIp: _webIpCtrl.text.isEmpty ? null : _webIpCtrl.text,
      );
      if (result['ok'] == true) {
        setState(() => _status = '✅ INJECT THÀNH CÔNG!\n'
            'PIN: ${_pinCtrl.text} @ $ts → ${_ipCtrl.text}\n'
            '${result['message'] ?? 'OK'}');
      } else {
        setState(() => _status = '❌ ${result['error'] ?? 'Unknown error'}\n${result['hint'] ?? ''}');
      }
    } catch (e) {
      setState(() => _status = '❌ $e');
    } finally {
      setState(() => _running = false);
    }
  }

  Future<void> _doCheckUser() async {
    if (_ipCtrl.text.isEmpty || _pinCtrl.text.isEmpty) {
      setState(() => _status = '⚠️ Nhập IP và PIN');
      return;
    }
    setState(() {
      _running = true;
      _status = '🔎 Đang kiểm tra user...';
    });
    try {
      final result = await widget.api.checkUser(ip: _ipCtrl.text, pin: _pinCtrl.text);
      if (result['ok'] == true) {
        setState(() => _status = '✅ User tồn tại: ${result['user'] ?? result['found']}');
      } else {
        setState(() => _status = '❌ ${result['error'] ?? 'User không tồn tại'}');
      }
    } catch (e) {
      setState(() => _status = '❌ $e');
    } finally {
      setState(() => _running = false);
    }
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
                label: const Text('Refresh', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ),
          ]),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            initialValue: _selectedIp.isEmpty ? null : _selectedIp,
            decoration: InputDecoration(
              labelText: 'Thiết bị',
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
          const SizedBox(height: 6),
          TextField(
            controller: _webIpCtrl,
            decoration: const InputDecoration(
              labelText: 'Web IP fallback',
              hintText: '172.16.254.202',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            style: const TextStyle(fontSize: 13),
          ),
        ]),

        const SizedBox(height: 12),

        // ============ Inject ATTLOG ============
        _section('2. Chấm công thật (ghi ATTLOG lên máy)', expanded: true, children: [
          _info('Cảnh báo: ATTLOG có marker là "APK_REAL_PUNCH". Đây là tool debug, không nên dùng để chấm công giả.'),
          const SizedBox(height: 8),
          TextField(
            controller: _pinCtrl,
            decoration: const InputDecoration(labelText: 'PIN (mã NV)', border: OutlineInputBorder(), isDense: true),
            keyboardType: TextInputType.number,
            style: const TextStyle(fontSize: 13),
          ),
          const SizedBox(height: 6),
          // Date + Time pickers
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _pickDate,
                icon: const Icon(Icons.calendar_today, size: 14),
                label: Text('${_date.day}/${_date.month}/${_date.year}',
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

  Widget _header() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(color: const Color(0xFF263238), borderRadius: BorderRadius.circular(4)),
      child: const Row(children: [
        Icon(Icons.bolt, size: 16, color: Color(0xFFE53935)),
        SizedBox(width: 6),
        Text('ATTLOG TOOLS - v2.6.0 (CVE-2023-3941)',
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
}
