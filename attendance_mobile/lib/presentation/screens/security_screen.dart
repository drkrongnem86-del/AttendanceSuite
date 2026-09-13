// Security Dashboard - v1.8.0
// Quét tất cả máy ZK, phát hiện Comm Key default, Telnet, users có password
import 'package:flutter/material.dart';
import '../../api.dart';

class SecurityScreen extends StatefulWidget {
  final AttendanceApi api;
  const SecurityScreen({Key? key, required this.api}) : super(key: key);

  @override
  _SecurityScreenState createState() => _SecurityScreenState();
}

class _SecurityScreenState extends State<SecurityScreen>
    with AutomaticKeepAliveClientMixin {
  Map<String, dynamic>? _scanResult;
  bool _loading = false;
  String? _error;
  DateTime? _lastScan;

  @override
  bool get wantKeepAlive => true;

  Future<void> _runScan() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final result = await widget.api.securityScan();
    if (!mounted) return;
    setState(() {
      _scanResult = result;
      _loading = false;
      _lastScan = DateTime.now();
      if (result.containsKey('error')) {
        _error = result['error'].toString();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return RefreshIndicator(
      onRefresh: _runScan,
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          // Header
          Card(
            color: const Color(0xFFE3F2FD),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  const Icon(Icons.security, color: Color(0xFF1565C0), size: 28),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Security Dashboard',
                          style: TextStyle(
                              fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                        Text(
                          _lastScan == null
                              ? 'Chưa quét - kéo xuống để refresh'
                              : 'Quét lúc ${_lastScan!.hour.toString().padLeft(2, '0')}:${_lastScan!.minute.toString().padLeft(2, '0')}:${_lastScan!.second.toString().padLeft(2, '0')}',
                          style: const TextStyle(fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  if (_loading)
                    const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  else
                    IconButton(
                      icon: const Icon(Icons.refresh),
                      onPressed: _runScan,
                      tooltip: 'Refresh Scan',
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),

          if (_error != null)
            Card(
              color: const Color(0xFFFFEBEE),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    const Icon(Icons.error, color: Color(0xFFC62828)),
                    const SizedBox(width: 8),
                    Expanded(child: Text('Lỗi: $_error')),
                  ],
                ),
              ),
            ),

          if (_scanResult == null && !_loading)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Column(
                  children: [
                    Icon(Icons.shield_outlined, size: 48, color: Colors.grey),
                    SizedBox(height: 8),
                    Text(
                      'Bấm 🔄 để quét 24 máy ZK.\nSẽ phát hiện Comm Key default, Telnet, NV có password.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey),
                    ),
                  ],
                ),
              ),
            ),

          if (_scanResult != null && _scanResult!['devices'] != null) ...[
            _buildSummaryStats(_scanResult!['devices'] as List),
            const SizedBox(height: 8),
            ...(_scanResult!['devices'] as List)
                .map((d) => _buildDeviceCard(d as Map<String, dynamic>)),
          ],
        ],
      ),
    );
  }

  Widget _buildSummaryStats(List devices) {
    int online = 0, commKey0 = 0, telnetOpen = 0, canPinPwd = 0;
    for (final d in devices) {
      if (d['online'] == true) online++;
      if (d['comm_key_default'] == true) commKey0++;
      if (d['port_23_telnet'] == true) telnetOpen++;
      if (d['can_pin_pwd'] == true) canPinPwd++;
    }
    return Card(
      color: const Color(0xFFFFF3E0),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('📊 Tổng quan',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              children: [
                _statBox('Online', '$online/${devices.length}', Colors.green),
                _statBox('Comm Key=0', '$commKey0', Colors.orange),
                _statBox('Telnet', '$telnetOpen', Colors.red),
                _statBox('PIN+PWD OK', '$canPinPwd', Colors.blue),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _statBox(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        border: Border.all(color: color, width: 1.5),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        children: [
          Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: color)),
          Text(label, style: const TextStyle(fontSize: 11)),
        ],
      ),
    );
  }

  Widget _buildDeviceCard(Map<String, dynamic> d) {
    final ip = d['ip'] ?? '?';
    final note = d['note'] ?? '';
    final fw = d['fw_version'] ?? '';
    final users = d['total_users'] ?? 0;
    final usersPwd = d['users_with_pwd'] ?? 0;
    final commKeyDefault = d['comm_key_default'] == true;
    final telnetOpen = d['port_23_telnet'] == true;
    final canPinPwd = d['can_pin_pwd'] == true;
    final online = d['online'] == true;

    Color statusColor;
    IconData statusIcon;
    String statusText;
    if (!online) {
      statusColor = Colors.grey;
      statusIcon = Icons.power_off;
      statusText = 'OFFLINE';
    } else if (commKeyDefault || telnetOpen) {
      statusColor = Colors.red;
      statusIcon = Icons.warning;
      statusText = 'NGUY HIỂM';
    } else if (canPinPwd) {
      statusColor = Colors.green;
      statusIcon = Icons.check_circle;
      statusText = 'AN TOÀN';
    } else {
      statusColor = Colors.orange;
      statusIcon = Icons.info;
      statusText = 'OK';
    }

    return Card(
      child: ListTile(
        leading: Icon(statusIcon, color: statusColor, size: 32),
        title: Row(
          children: [
            Expanded(child: Text(ip, style: const TextStyle(fontWeight: FontWeight.bold))),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: statusColor.withOpacity(0.15),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(statusText,
                  style: TextStyle(fontSize: 10, color: statusColor, fontWeight: FontWeight.bold)),
            ),
          ],
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (note.isNotEmpty) Text(note, style: const TextStyle(fontSize: 12)),
            if (fw.isNotEmpty) Text('FW: $fw', style: const TextStyle(fontSize: 11, color: Colors.grey)),
            if (users > 0) Text('$users users, $usersPwd có password',
                style: const TextStyle(fontSize: 11)),
            if (commKeyDefault)
              const Text('⚠️ Comm Key = 0 (default)',
                  style: TextStyle(fontSize: 11, color: Colors.red)),
            if (telnetOpen)
              const Text('⚠️ Telnet OPEN',
                  style: TextStyle(fontSize: 11, color: Colors.red)),
          ],
        ),
        isThreeLine: true,
      ),
    );
  }
}
