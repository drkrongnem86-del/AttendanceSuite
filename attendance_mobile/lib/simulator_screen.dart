// X628 PRO Simulator screen
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'api.dart';

class SimulatorScreen extends StatefulWidget {
  final AttendanceApi api;
  SimulatorScreen({required this.api});

  @override
  _SimulatorScreenState createState() => _SimulatorScreenState();
}

class _SimulatorScreenState extends State<SimulatorScreen> {
  String _userIdInput = '';
  int _selectedStatus = 0;
  int _selectedPunch = 0;
  bool _isSubmitting = false;
  String _message = '';
  bool _messageIsError = false;
  Map<String, dynamic> _deviceStatus = {};
  List<ManualPunch> _history = [];

  static const _statuses = [
    {'code': 0, 'name': 'Check-In', 'vn': 'Vào ca'},
    {'code': 1, 'name': 'Check-Out', 'vn': 'Tan ca'},
    {'code': 2, 'name': 'Break-Out', 'vn': 'Ra ngoài'},
    {'code': 3, 'name': 'Break-In', 'vn': 'Vào lại'},
    {'code': 4, 'name': 'OT-In', 'vn': 'Vào OT'},
    {'code': 5, 'name': 'OT-Out', 'vn': 'Tan OT'},
  ];

  static const _punches = [
    {'code': 0, 'name': 'Vân tay', 'icon': '🖐'},
    {'code': 1, 'name': 'Thẻ', 'icon': '💳'},
    {'code': 2, 'name': 'Mật khẩu', 'icon': '🔢'},
  ];

  @override
  void initState() {
    super.initState();
    _loadDevice();
    _loadHistory();
  }

  Future<void> _loadDevice() async {
    final s = await widget.api.getSimDevice();
    setState(() => _deviceStatus = s);
  }

  Future<void> _loadHistory() async {
    final h = await widget.api.getHistory();
    setState(() => _history = h);
  }

  void _pressKey(String k) {
    if (_isSubmitting) return;
    setState(() {
      if (k == 'C') {
        _userIdInput = '';
      } else if (k == 'OK') {
        _submitPunch();
      } else {
        if (_userIdInput.length < 10) {
          _userIdInput += k;
        }
      }
    });
  }

  Future<void> _submitPunch() async {
    if (_userIdInput.isEmpty) {
      setState(() {
        _message = 'Vui lòng nhập mã nhân viên';
        _messageIsError = true;
      });
      return;
    }
    setState(() => _isSubmitting = true);
    final result = await widget.api.punch(_userIdInput, _selectedStatus, _selectedPunch);
    setState(() {
      _isSubmitting = false;
      if (result['ok'] == true) {
        _message = (result['written_to_device'] == true)
            ? '✓ Đã ghi vào máy thật'
            : '✓ Đã ghi local (máy không hỗ trợ ghi từ xa)';
        _messageIsError = false;
        _userIdInput = '';
        _loadHistory();
        _loadDevice();
      } else {
        _message = 'Lỗi: ' + (result['error']?.toString() ?? 'không rõ');
        _messageIsError = true;
      }
    });
  }

  Future<void> _deletePunch(ManualPunch p) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Xóa bản ghi?'),
        content: Text('Xóa ${p.timestamp} NV ${p.userId}?\n(Lưu ý: máy ZK không cho xóa từ xa)'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Hủy')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Xóa')),
        ],
      ),
    );
    if (confirm == true) {
      final ok = await widget.api.deletePunch(p.punchId);
      if (ok) _loadHistory();
    }
  }

  @override
  Widget build(BuildContext context) {
    final deviceConnected = _deviceStatus['connected'] == true;
    return Column(
      children: [
        // Connection status bar
        Container(
          padding: const EdgeInsets.all(8),
          color: deviceConnected ? Colors.green.shade900 : Colors.red.shade900,
          child: Row(
            children: [
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  color: deviceConnected ? Colors.greenAccent : Colors.redAccent,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  deviceConnected
                      ? '✓ Kết nối ${_deviceStatus['ip']} (${_deviceStatus['model'] ?? '?'})'
                      : '✗ Mất kết nối ${_deviceStatus['ip'] ?? 'server'}',
                  style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.refresh, color: Colors.white, size: 18),
                onPressed: () { _loadDevice(); _loadHistory(); },
              ),
            ],
          ),
        ),
        // Body
        Expanded(
          child: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Column(
                children: [
                  // Machine screen
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFF0a3d2e),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: Colors.green.shade800),
                    ),
                    child: Column(
                      children: [
                        Text(
                          DateTime.now().toString().split('.')[0],
                          style: const TextStyle(color: Color(0xFF5fff7f), fontFamily: 'monospace', fontSize: 14),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          _userIdInput.isEmpty ? '---' : _userIdInput,
                          style: const TextStyle(color: Color(0xFF5fff7f), fontFamily: 'monospace', fontSize: 24, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          _statuses[_selectedStatus]['name'] as String,
                          style: const TextStyle(color: Colors.amber, fontFamily: 'monospace', fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  // Keypad
                  GridView.count(
                    crossAxisCount: 3,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    childAspectRatio: 1.5,
                    children: [
                      for (var k in ['1', '2', '3', '4', '5', '6', '7', '8', '9'])
                        _keypadButton(k, Colors.blueGrey.shade700),
                      _keypadButton('C', Colors.orange.shade700),
                      _keypadButton('0', Colors.blueGrey.shade700),
                      _keypadButton('OK', Colors.pink.shade700),
                    ],
                  ),
                  const SizedBox(height: 12),
                  // Status (action) buttons
                  const Text('Thao tác:', style: TextStyle(color: Colors.white70, fontSize: 12)),
                  const SizedBox(height: 4),
                  GridView.count(
                    crossAxisCount: 3,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    childAspectRatio: 2,
                    children: _statuses.map((s) {
                      final selected = _selectedStatus == s['code'];
                      return GestureDetector(
                        onTap: () => setState(() => _selectedStatus = s['code'] as int),
                        child: Container(
                          margin: const EdgeInsets.all(2),
                          decoration: BoxDecoration(
                            color: selected ? Colors.cyan : Colors.blueGrey.shade800,
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: selected ? Colors.cyanAccent : Colors.transparent),
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            '${s['name']}\n(${s['vn']})',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: selected ? Colors.black : Colors.white,
                              fontSize: 11,
                              fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 8),
                  // Method (punch) buttons
                  const Text('Phương thức:', style: TextStyle(color: Colors.white70, fontSize: 12)),
                  const SizedBox(height: 4),
                  Row(
                    children: _punches.map((p) {
                      final selected = _selectedPunch == p['code'];
                      return Expanded(
                        child: GestureDetector(
                          onTap: () => setState(() => _selectedPunch = p['code'] as int),
                          child: Container(
                            margin: const EdgeInsets.all(2),
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: selected ? Colors.green : Colors.blueGrey.shade800,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Column(
                              children: [
                                Text(p['icon'] as String, style: const TextStyle(fontSize: 18)),
                                Text(
                                  p['name'] as String,
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    color: selected ? Colors.black : Colors.white,
                                    fontSize: 11,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 8),
                  // Submit
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _isSubmitting ? null : _submitPunch,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.cyan,
                        foregroundColor: Colors.black,
                        padding: const EdgeInsets.all(16),
                      ),
                      child: Text(
                        _isSubmitting ? 'Đang ghi...' : 'CHẤM CÔNG',
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                  if (_message.isNotEmpty)
                    Container(
                      margin: const EdgeInsets.only(top: 8),
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: _messageIsError ? Colors.red.shade900 : Colors.green.shade900,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        _message,
                        style: const TextStyle(color: Colors.white, fontSize: 12),
                      ),
                    ),
                  const SizedBox(height: 12),
                  // History
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'Lịch sử (${_history.length})',
                      style: const TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Container(
                    constraints: const BoxConstraints(maxHeight: 250),
                    decoration: BoxDecoration(
                      color: Colors.blueGrey.shade900,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: _history.isEmpty
                        ? const Padding(
                            padding: EdgeInsets.all(12),
                            child: Text('Chưa có lượt chấm nào', style: TextStyle(color: Colors.white60)),
                          )
                        : ListView.builder(
                            shrinkWrap: true,
                            itemCount: _history.length,
                            itemBuilder: (ctx, i) {
                              final h = _history[i];
                              return ListTile(
                                dense: true,
                                leading: Text(
                                  'NV ${h.userId}',
                                  style: const TextStyle(color: Colors.cyanAccent, fontSize: 11),
                                ),
                                title: Text(
                                  '${h.timestamp} - ${h.statusName}',
                                  style: const TextStyle(color: Colors.white, fontSize: 12),
                                ),
                                subtitle: Text(
                                  '${h.methodName} - ${h.writtenToDevice ? "✓ máy" : "local"}',
                                  style: const TextStyle(color: Colors.white60, fontSize: 10),
                                ),
                                trailing: IconButton(
                                  icon: const Icon(Icons.delete, color: Colors.redAccent, size: 18),
                                  onPressed: () => _deletePunch(h),
                                ),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _keypadButton(String label, Color color) {
    return GestureDetector(
      onTap: () => _pressKey(label),
      child: Container(
        margin: const EdgeInsets.all(2),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(4),
        ),
        alignment: Alignment.center,
        child: Text(
          label,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
        ),
      ),
    );
  }
}
