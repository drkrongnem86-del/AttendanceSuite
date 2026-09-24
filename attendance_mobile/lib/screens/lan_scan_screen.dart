// lib/screens/lan_scan_screen.dart
// AttendanceSuite v2.6.7 - Tab "Quét LAN truc tiep" (khong can backend)
// TCP probe cong 4370 (ZK protocol) tren subnet hien tai
// Chi hoat dong khi phone cung subnet voi ZK devices (vi du: BV WiFi)

import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class LanScanScreen extends StatefulWidget {
  const LanScanScreen({super.key});

  @override
  State<LanScanScreen> createState() => _LanScanScreenState();
}

class _LanScanScreenState extends State<LanScanScreen> {
  final TextEditingController _startIpCtrl = TextEditingController();
  final TextEditingController _endIpCtrl = TextEditingController();
  String _myIp = '-';
  String _mySubnet = '-';
  String _status = '';
  bool _scanning = false;
  double _progress = 0;
  int _scanned = 0;
  int _total = 0;
  final List<_FoundDevice> _found = [];
  String _foundFilter = '';  // v2.6.9: filter found devices by IP substring

  @override
  void initState() {
    super.initState();
    _detectMyIp();
  }

  Future<void> _detectMyIp() async {
    try {
      final interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLoopback: false,
        includeLinkLocal: false,
      );
      for (final iface in interfaces) {
        for (final addr in iface.addresses) {
          if (!addr.address.startsWith('127.') && !addr.isLoopback) {
            setState(() {
              _myIp = addr.address;
              _mySubnet = '${_subnetBase(addr.address)}/24';
              // Default range: scan /24 from current IP
              _startIpCtrl.text = _subnetBase(addr.address) + '1';
              _endIpCtrl.text = _subnetBase(addr.address) + '254';
            });
            return;
          }
        }
      }
    } catch (e) {
      setState(() => _status = 'Loi phat hien IP: $e');
    }
  }

  String _subnetBase(String ip) {
    final parts = ip.split('.');
    if (parts.length != 4) return '192.168.1.';
    return '${parts[0]}.${parts[1]}.${parts[2]}.';
  }

  bool _stopRequested = false;  // v2.6.9: signal for stopping mid-scan

  Future<void> _scan() async {
    if (_scanning) return;
    final startIp = _startIpCtrl.text.trim();
    final endIp = _endIpCtrl.text.trim();
    if (!_isValidIp(startIp) || !_isValidIp(endIp)) {
      setState(() => _status = 'IP khong hop le');
      return;
    }
    setState(() {
      _scanning = true;
      _stopRequested = false;
      _found.clear();
      _scanned = 0;
      _progress = 0;
      _status = 'Dang quet $startIp - $endIp...';
    });

    final startN = _ipToInt(startIp);
    final endN = _ipToInt(endIp);
    final total = endN - startN + 1;
    setState(() => _total = total);

    // Scan in parallel (32 concurrent to balance speed/socket exhaustion)
    const batchSize = 32;
    for (var batchStart = startN; batchStart <= endN; batchStart += batchSize) {
      // v2.6.9: check stop signal each batch
      if (_stopRequested || !mounted) break;
      final batchEnd = (batchStart + batchSize - 1).clamp(startN, endN);
      final futures = <Future<_FoundDevice?>>[];
      for (var n = batchStart; n <= batchEnd; n++) {
        final ip = _intToIp(n);
        futures.add(_probeZk(ip));
      }
      final results = await Future.wait(futures);
      if (_stopRequested || !mounted) break;
      for (final r in results) {
        if (r != null) {
          setState(() => _found.add(r));
        }
      }
      setState(() {
        _scanned += (batchEnd - batchStart + 1);
        _progress = _scanned / total;
      });
    }

    if (_stopRequested) {
      setState(() {
        _scanning = false;
        _status = '⏹ Đã dừng: tìm thấy ${_found.length} thiết bị trong $_scanned/$_total IP';
      });
    } else {
      setState(() {
        _scanning = false;
        _status = 'Hoàn tất: ${_found.length} thiết bị ZK tìm thấy trong $_scanned IP';
      });
    }
  }

  void _stopScan() {
    if (!_scanning) return;
    setState(() {
      _stopRequested = true;
      _status = '⏹ Đang dừng quét...';
    });
  }

  Future<_FoundDevice?> _probeZk(String ip) async {
    try {
      final socket = await Socket.connect(ip, 4370,
          timeout: const Duration(milliseconds: 800));
      // ZK responds to CMD_CONNECT with session info
      // For LAN discovery, just successful TCP connect is enough
      // Try to get version via simple CMD request
      socket.destroy();
      return _FoundDevice(ip: ip, port: 4370);
    } catch (_) {
      return null;
    }
  }

  Future<void> _copyList() async {
    final text = _found.map((d) => '${d.ip}:${d.port}').join('\n');
    await Clipboard.setData(ClipboardData(text: text));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Da copy danh sach IP')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(8),
      children: [
        // Header
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: const Color(0xFF263238),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Row(children: [
            const Icon(Icons.wifi_tethering, color: Color(0xFF26A69A)),
            const SizedBox(width: 8),
            const Expanded(
              child: Text('QUET LAN TRUC TIEP',
                  style: TextStyle(
                      fontSize: 13,
                      color: Colors.white,
                      fontWeight: FontWeight.bold)),
            ),
            Text(_myIp,
                style: const TextStyle(fontSize: 11, color: Color(0xFF26A69A))),
          ]),
        ),
        const SizedBox(height: 4),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          child: Text(
            'Subnet: $_mySubnet  |  Cong quet: 4370 (ZK protocol)\n'
            'Chi hoat dong khi phone cung subnet voi ZK devices (BV WiFi)',
            style: const TextStyle(fontSize: 10, color: Colors.white60),
          ),
        ),
        const SizedBox(height: 8),

        // IP range inputs
        Row(children: [
          Expanded(
            child: TextField(
              controller: _startIpCtrl,
              enabled: !_scanning,
              decoration: const InputDecoration(
                labelText: 'Start IP',
                isDense: true,
                border: OutlineInputBorder(),
                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              ),
              style: const TextStyle(fontSize: 13, fontFamily: 'monospace'),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: TextField(
              controller: _endIpCtrl,
              enabled: !_scanning,
              decoration: const InputDecoration(
                labelText: 'End IP',
                isDense: true,
                border: OutlineInputBorder(),
                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              ),
              style: const TextStyle(fontSize: 13, fontFamily: 'monospace'),
            ),
          ),
        ]),
        const SizedBox(height: 8),

        // Quick range buttons
        Wrap(spacing: 6, children: [
          _quickBtn('172.16.0.x', '172.16.0.1', '172.16.0.254'),
          _quickBtn('172.16.200.x', '172.16.200.1', '172.16.200.254'),
          _quickBtn('192.168.1.x', '192.168.1.1', '192.168.1.254'),
        ]),
        const SizedBox(height: 8),

        // Scan button
        Row(children: [
          Expanded(
            child: ElevatedButton.icon(
              onPressed: _scanning ? _stopScan : _scan,
              style: ElevatedButton.styleFrom(
                backgroundColor: _scanning ? Colors.red.shade700 : const Color(0xFF26A69A),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 12),
              ),
              icon: Icon(_scanning ? Icons.stop_circle : Icons.search, size: 18),
              label: Text(
                  _scanning ? 'DỪNG ($_scanned/$_total)' : 'QUÉT NGAY',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
            ),
          ),
          const SizedBox(width: 6),
          ElevatedButton.icon(
            onPressed: _scanning || _found.isEmpty ? null : _copyList,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF455A64),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
            ),
            icon: const Icon(Icons.copy, size: 16),
            label: const Text('Copy', style: TextStyle(fontSize: 12)),
          ),
        ]),
        const SizedBox(height: 6),

        // Progress
        if (_scanning || _progress > 0)
          Column(children: [
            LinearProgressIndicator(
              value: _progress,
              minHeight: 4,
              backgroundColor: const Color(0xFF37474F),
              valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF26A69A)),
            ),
            const SizedBox(height: 4),
            Text('$_scanned / $_total IP da quet',
                style: const TextStyle(fontSize: 10, color: Colors.white60)),
            const SizedBox(height: 6),
          ]),

        // Status
        if (_status.isNotEmpty)
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFF455A64),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(_status,
                style: const TextStyle(fontSize: 11, color: Colors.white)),
          ),
        const SizedBox(height: 8),

        // Found devices
        if (_found.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xFF1B5E20),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Row(children: [
              const Icon(Icons.check_circle, color: Colors.white, size: 16),
              const SizedBox(width: 6),
              Text('${_found.length} ZK devices (port 4370 open)',
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 12)),
              const Spacer(),
              if (_foundFilter.isNotEmpty)
                TextButton(
                  onPressed: () => setState(() => _foundFilter = ''),
                  child: const Text('Bỏ lọc', style: TextStyle(fontSize: 10, color: Colors.white70)),
                ),
            ]),
          ),
          const SizedBox(height: 4),
          // v2.6.9: filter input
          TextField(
            decoration: const InputDecoration(
              isDense: true,
              hintText: '🔍 Lọc IP... (vd: 172.16.0)',
              border: OutlineInputBorder(),
              contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
            ),
            style: const TextStyle(fontSize: 12, fontFamily: 'monospace'),
            onChanged: (v) => setState(() => _foundFilter = v.trim()),
          ),
          const SizedBox(height: 4),
          Builder(builder: (ctx) {
            final filtered = _foundFilter.isEmpty
                ? _found
                : _found.where((d) => d.ip.contains(_foundFilter)).toList();
            if (filtered.isEmpty) {
              return Container(
                padding: const EdgeInsets.all(8),
                child: Text('Không có IP khớp "${_foundFilter}"',
                    style: const TextStyle(fontSize: 11, color: Colors.white60)),
              );
            }
            return Column(children: filtered.map((d) => _deviceRow(d)).toList());
          }),
        ] else if (!_scanning) ...[
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: const Color(0xFF37474F),
              borderRadius: BorderRadius.circular(4),
            ),
            child: const Column(children: [
              Icon(Icons.wifi_find, size: 36, color: Color(0xFF607D8B)),
              SizedBox(height: 6),
              Text('Bam QUET NGAY de tim thiet bi ZK',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontSize: 12,
                      color: Colors.white60,
                      fontWeight: FontWeight.bold)),
              SizedBox(height: 4),
              Text(
                  'Phone phai o cung subnet (vi du 172.16.x.x voi BV WiFi).\n'
                  'Neu qua Sophos VPN tu xa, Sophos filter cong 4370.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 10, color: Colors.white38)),
            ]),
          ),
        ],

        const SizedBox(height: 80),
      ],
    );
  }

  Widget _quickBtn(String label, String start, String end) {
    return ActionChip(
      label: Text(label, style: const TextStyle(fontSize: 11)),
      onPressed: _scanning
          ? null
          : () => setState(() {
                _startIpCtrl.text = start;
                _endIpCtrl.text = end;
              }),
    );
  }

  Widget _deviceRow(_FoundDevice d) {
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFF37474F),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: const Color(0xFF26A69A).withValues(alpha: 0.5)),
      ),
      child: Row(children: [
        const Icon(Icons.devices, color: Color(0xFF26A69A), size: 18),
        const SizedBox(width: 8),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${d.ip}:${d.port}',
                style: const TextStyle(
                    fontSize: 12,
                    color: Colors.white,
                    fontFamily: 'monospace',
                    fontWeight: FontWeight.bold)),
            const Text('ZK device (port 4370 open)',
                style: TextStyle(fontSize: 10, color: Colors.white60)),
          ]),
        ),
        IconButton(
          icon: const Icon(Icons.copy, size: 16, color: Colors.white60),
          onPressed: () async {
            await Clipboard.setData(ClipboardData(text: d.ip));
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Copied ${d.ip}')),
              );
            }
          },
        ),
      ]),
    );
  }

  bool _isValidIp(String ip) {
    final parts = ip.split('.');
    if (parts.length != 4) return false;
    for (final p in parts) {
      final n = int.tryParse(p);
      if (n == null || n < 0 || n > 255) return false;
    }
    return true;
  }

  int _ipToInt(String ip) {
    final parts = ip.split('.').map(int.parse).toList();
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3];
  }

  String _intToIp(int n) {
    return '${(n >> 24) & 0xFF}.${(n >> 16) & 0xFF}.${(n >> 8) & 0xFF}.${n & 0xFF}';
  }
}

class _FoundDevice {
  final String ip;
  final int port;
  _FoundDevice({required this.ip, required this.port});
}
