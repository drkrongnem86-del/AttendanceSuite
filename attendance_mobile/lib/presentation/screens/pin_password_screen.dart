// PIN+Password Screen - v1.8.0
// Workflow chấm công bằng PIN + password - VERIFY từ xa qua pyzk
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../api.dart';

class PinPasswordScreen extends StatefulWidget {
  final AttendanceApi api;
  const PinPasswordScreen({Key? key, required this.api}) : super(key: key);

  @override
  _PinPasswordScreenState createState() => _PinPasswordScreenState();
}

class _PinPasswordScreenState extends State<PinPasswordScreen>
    with AutomaticKeepAliveClientMixin {
  List<Device> _devices = [];
  Device? _selectedDevice;
  final _pinController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loadingDevices = false;
  bool _verifying = false;
  Map<String, dynamic>? _verifyResult;
  String? _error;

  // ATTLOG verification state
  int? _attlogBaseline; // count trước khi NV punch
  Map<String, dynamic>? _attlogNow; // count sau khi check
  bool _checkingAttlog = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _loadDevices();
  }

  @override
  void dispose() {
    _pinController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _loadDevices() async {
    setState(() => _loadingDevices = true);
    final devices = await widget.api.getDevices();
    if (!mounted) return;
    // Filter chỉ attendance devices
    final attendanceDevices = devices.where((d) => d.type == 'attendance').toList();
    setState(() {
      _devices = attendanceDevices;
      _loadingDevices = false;
      _selectedDevice = attendanceDevices.isNotEmpty ? attendanceDevices.first : null;
    });
  }

  Future<void> _doManualPunch(String punchType) async {
    if (_selectedDevice == null) {
      _showSnack('Vui lòng chọn máy ZK');
      return;
    }
    final pin = _pinController.text.trim();
    final password = _passwordController.text;
    if (pin.isEmpty) {
      _showSnack('Nhập PIN (mã NV)');
      return;
    }
    if (password.isEmpty) {
      _showSnack('Nhập password');
      return;
    }

    setState(() {
      _verifying = true;
      _verifyResult = null;
      _error = null;
    });

    final result =
        await widget.api.manualPunch(_selectedDevice!.ip, pin, password, punchType);
    if (!mounted) return;
    setState(() {
      _verifying = false;
      _verifyResult = result;
      if (result['ok'] != true) {
        _error = result['error'] ?? 'Lỗi không xác định';
      }
    });

    // Haptic feedback khi thành công
    if (result['ok'] == true && result['verified'] == true) {
      HapticFeedback.heavyImpact();
      // Tự động set baseline = count hiện tại để so sánh sau
      _captureBaseline();
    } else {
      HapticFeedback.lightImpact();
    }
  }

  /// Đọc ATTLOG count hiện tại từ ZK để set baseline
  Future<void> _captureBaseline() async {
    if (_selectedDevice == null) return;
    final result = await widget.api.getAttlogCount(_selectedDevice!.ip);
    if (!mounted) return;
    if (result['ok'] == true) {
      setState(() {
        _attlogBaseline = result['attlog_count'] as int?;
        _attlogNow = null;
      });
    }
  }

  /// Check ATTLOG count hiện tại + so sánh với baseline
  Future<void> _checkAttlogNow() async {
    if (_selectedDevice == null) return;
    setState(() => _checkingAttlog = true);
    final result = await widget.api.getAttlogCount(_selectedDevice!.ip);
    if (!mounted) return;
    setState(() {
      _checkingAttlog = false;
      _attlogNow = result;
    });
  }

  void _showSnack(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), duration: const Duration(seconds: 2)),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          Card(
            color: const Color(0xFFE8F5E9),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  const Icon(Icons.pin, color: Color(0xFF2E7D32), size: 28),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Chấm công PIN + Password',
                          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                        Text(
                          'Workflow verify từ xa - NV đứng trước máy nhập',
                          style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // Device dropdown
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.devices, size: 18),
                      const SizedBox(width: 6),
                      const Text('Chọn máy ZK:',
                          style: TextStyle(fontWeight: FontWeight.bold)),
                      const Spacer(),
                      if (_loadingDevices)
                        const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2))
                      else
                        IconButton(
                          icon: const Icon(Icons.refresh, size: 18),
                          onPressed: _loadDevices,
                          tooltip: 'Reload',
                        ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  if (_devices.isEmpty && !_loadingDevices)
                    const Text('Không có máy attendance',
                        style: TextStyle(color: Colors.grey))
                  else
                    DropdownButton<Device>(
                      isExpanded: true,
                      value: _selectedDevice,
                      items: _devices
                          .map((d) => DropdownMenuItem(
                                value: d,
                                child: Text(
                                    '${d.ip} - ${d.note.isNotEmpty ? d.note : "(no name)"}'),
                              ))
                          .toList(),
                      onChanged: (d) {
                        setState(() {
                          _selectedDevice = d;
                          _verifyResult = null;
                          _error = null;
                        });
                      },
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // PIN + Password inputs
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Nhập thông tin NV:',
                      style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _pinController,
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    decoration: const InputDecoration(
                      labelText: 'PIN (mã NV)',
                      hintText: 'VD: 1383',
                      prefixIcon: Icon(Icons.numbers),
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _passwordController,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'Password',
                      hintText: 'VD: 1',
                      prefixIcon: Icon(Icons.lock_outline),
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _doManualPunch('check_in'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // Punch buttons
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  icon: const Icon(Icons.login),
                  label: const Text('CHECK-IN'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF2E7D32),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: _verifying ? null : () => _doManualPunch('check_in'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton.icon(
                  icon: const Icon(Icons.logout),
                  label: const Text('CHECK-OUT'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFFE65100),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: _verifying ? null : () => _doManualPunch('check_out'),
                ),
              ),
            ],
          ),

          if (_verifying) ...[
            const SizedBox(height: 16),
            const Center(
              child: Column(
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 8),
                  Text('Đang verify PIN+password trên máy ZK...'),
                ],
              ),
            ),
          ],

          if (_error != null) ...[
            const SizedBox(height: 16),
            Card(
              color: const Color(0xFFFFEBEE),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    const Icon(Icons.error, color: Colors.red),
                    const SizedBox(width: 8),
                    Expanded(child: Text('❌ $_error')),
                  ],
                ),
              ),
            ),
          ],

          if (_verifyResult != null && _verifyResult!['ok'] == true) ...[
            const SizedBox(height: 16),
            _buildSuccessCard(_verifyResult!),
            const SizedBox(height: 12),
            _buildAttlogCheckCard(),
          ],
        ],
      ),
    );
  }

  Widget _buildSuccessCard(Map<String, dynamic> r) {
    final instructions = (r['instructions'] as List?)?.cast<String>() ?? [];
    return Card(
      color: const Color(0xFFE8F5E9),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.check_circle, color: Color(0xFF2E7D32)),
                SizedBox(width: 8),
                Text('✅ Verified thành công!',
                    style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF2E7D32))),
              ],
            ),
            const SizedBox(height: 8),
            Text('NV: ${r['name']} (PIN ${r['pin']})'),
            Text('Máy: ${r['device_ip']}'),
            const SizedBox(height: 12),
            const Text('📋 Hướng dẫn cho NV:',
                style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            ...instructions.asMap().entries.map((e) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text('${e.key + 1}. ${e.value}',
                      style: const TextStyle(fontSize: 13)),
                )),
          ],
        ),
      ),
    );
  }

  /// Card kiểm tra ATTLOG đã ghi chưa (sau khi NV punch tại máy)
  Widget _buildAttlogCheckCard() {
    final now = _attlogNow;
    final baseline = _attlogBaseline;
    int? delta;
    if (now != null && now['ok'] == true && baseline != null) {
      delta = (now['attlog_count'] as int) - baseline;
    }

    Color statusColor;
    String statusText;
    IconData statusIcon;
    if (delta == null) {
      statusColor = Colors.grey;
      statusText = 'Chưa có dữ liệu';
      statusIcon = Icons.help_outline;
    } else if (delta > 0) {
      statusColor = const Color(0xFF2E7D32);
      statusText = '✅ ĐÃ GHI ATTLOG! (+$delta records)';
      statusIcon = Icons.verified;
    } else if (delta == 0) {
      statusColor = Colors.orange;
      statusText = '⚠️ ATTLOG chưa tăng - NV chưa punch trên máy?';
      statusIcon = Icons.warning;
    } else {
      statusColor = Colors.red;
      statusText = '❌ ATTLOG giảm (không bình thường)';
      statusIcon = Icons.error;
    }

    return Card(
      color: statusColor.withOpacity(0.08),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.fact_check_outlined, color: statusColor),
                const SizedBox(width: 8),
                const Text('Verify ATTLOG trên máy ZK',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                if (_checkingAttlog)
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                else
                  IconButton(
                    icon: const Icon(Icons.refresh),
                    onPressed: _checkAttlogNow,
                    tooltip: 'Check ATTLOG count',
                  ),
              ],
            ),
            const SizedBox(height: 8),
            if (baseline != null)
              _statRow('Trước khi NV punch', '$baseline'),
            if (now != null && now['ok'] == true)
              _statRow('Hiện tại', '${now['attlog_count']}',
                  subtitle: 'capacity ${now['attlog_capacity']}'),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              decoration: BoxDecoration(
                color: statusColor.withOpacity(0.15),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(
                children: [
                  Icon(statusIcon, color: statusColor, size: 18),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(statusText,
                        style: TextStyle(
                            fontSize: 13, color: statusColor, fontWeight: FontWeight.bold)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '💡 NV cần đứng trước máy ZK nhập PIN+password. Sau đó bấm 🔄 để kiểm tra.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statRow(String label, String value, {String? subtitle}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Text('$label: ', style: const TextStyle(fontWeight: FontWeight.bold)),
          Text(value, style: const TextStyle(fontFamily: 'monospace', fontSize: 15)),
          if (subtitle != null) ...[
            const SizedBox(width: 6),
            Text('($subtitle)', style: const TextStyle(fontSize: 11, color: Colors.grey)),
          ],
        ],
      ),
    );
  }
}
