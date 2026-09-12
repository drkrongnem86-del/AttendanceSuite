// X628 PRO Simulator screen
// v1.5.7: Auto-refresh connection moi 5s (BS phan anh "x628 pro con mat ket noi")
import 'dart:async';
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
  // v1.5.7: Auto-refresh connection status
  Timer? _refreshTimer;
  String _pingStatus = '';  // Thong tin ping moi nhat

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
    // v1.5.7: Auto-refresh connection status moi 5s
    _refreshTimer = Timer.periodic(const Duration(seconds: 5), (_) => _autoRefresh());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  // v1.5.7: Auto-refresh (chi refresh khi user khong dang tuong tac)
  Future<void> _autoRefresh() async {
    if (!mounted || _isSubmitting) return;
    final s = await widget.api.getSimDevice();
    if (!mounted) return;
    setState(() {
      _deviceStatus = s;
      // Capture ping status cho debug
      if (s.isNotEmpty) {
        _pingStatus = '${s['connected'] == true ? "✓" : "✗"} ${s['ip'] ?? "?"} '
            '(${DateTime.now().toString().substring(11, 19)})';
      } else {
        _pingStatus = '✗ Server không phản hồi (${DateTime.now().toString().substring(11, 19)})';
      }
    });
    // Auto reload history moi 30s
    if (DateTime.now().second < 5) {
      _loadHistory();
    }
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
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      deviceConnected
                          ? '✓ Kết nối ${_deviceStatus['ip']} (${_deviceStatus['model'] ?? '?'})'
                          : '✗ Mất kết nối ${_deviceStatus['ip'] ?? 'server'}',
                      style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold),
                    ),
                    if (_pingStatus.isNotEmpty)
                      Text(
                        'Auto-refresh 5s: $_pingStatus',
                        style: const TextStyle(color: Colors.white70, fontSize: 10, fontFamily: 'monospace'),
                      ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.refresh, color: Colors.white, size: 18),
                tooltip: 'Refresh ngay',
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
                  const Text('Thao tác:', style: TextStyle(color: Color(0xFF455A64), fontSize: 12, fontWeight: FontWeight.w600)),
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
                            color: selected ? const Color(0xFF00897B) : Colors.white,
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(
                              color: selected ? const Color(0xFF00695C) : const Color(0xFFB0BEC5),
                              width: selected ? 2 : 1,
                            ),
                            boxShadow: selected
                                ? [BoxShadow(color: const Color(0xFF00897B).withOpacity(0.3), blurRadius: 4, offset: const Offset(0, 2))]
                                : null,
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            '${s['name']}\n(${s['vn']})',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: selected ? Colors.white : const Color(0xFF263238),
                              fontSize: 11,
                              fontWeight: selected ? FontWeight.bold : FontWeight.w500,
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 10),
                  // Method (punch) buttons
                  const Text('Phương thức:', style: TextStyle(color: Color(0xFF455A64), fontSize: 12, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  Row(
                    children: _punches.map((p) {
                      final selected = _selectedPunch == p['code'];
                      return Expanded(
                        child: GestureDetector(
                          onTap: () => setState(() => _selectedPunch = p['code'] as int),
                          child: Container(
                            margin: const EdgeInsets.all(2),
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: selected ? const Color(0xFF2E7D32) : Colors.white,
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: selected ? const Color(0xFF1B5E20) : const Color(0xFFB0BEC5),
                                width: selected ? 2 : 1,
                              ),
                              boxShadow: selected
                                  ? [BoxShadow(color: const Color(0xFF2E7D32).withOpacity(0.3), blurRadius: 4, offset: const Offset(0, 2))]
                                  : null,
                            ),
                            child: Column(
                              children: [
                                Text(p['icon'] as String, style: const TextStyle(fontSize: 20)),
                                Text(
                                  p['name'] as String,
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    color: selected ? Colors.white : const Color(0xFF263238),
                                    fontSize: 11,
                                    fontWeight: selected ? FontWeight.bold : FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 10),
                  // Submit
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: _isSubmitting ? null : _submitPunch,
                      icon: _isSubmitting
                          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                          : const Icon(Icons.fingerprint, color: Colors.white, size: 20),
                      label: Text(
                        _isSubmitting ? 'Đang ghi...' : 'CHẤM CÔNG',
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF00897B),
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                  ),
                  if (_message.isNotEmpty)
                    Container(
                      margin: const EdgeInsets.only(top: 10),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: _messageIsError ? const Color(0xFFFFEBEE) : const Color(0xFFE8F5E9),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: _messageIsError ? const Color(0xFFEF5350) : const Color(0xFF66BB6A),
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            _messageIsError ? Icons.error_outline : Icons.check_circle,
                            color: _messageIsError ? const Color(0xFFC62828) : const Color(0xFF2E7D32),
                            size: 20,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _message,
                              style: TextStyle(
                                color: _messageIsError ? const Color(0xFFB71C1C) : const Color(0xFF1B5E20),
                                fontSize: 12,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 14),
                  // History
                  Row(
                    children: [
                      const Icon(Icons.history, color: Color(0xFF00695C), size: 18),
                      const SizedBox(width: 6),
                      Text(
                        'Lịch sử (${_history.length})',
                        style: const TextStyle(color: Color(0xFF00695C), fontSize: 14, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  if (_history.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF5F7FA),
                        border: Border.all(color: const Color(0xFFB0BEC5)),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: const Center(
                        child: Text('Chưa có lượt chấm nào', style: TextStyle(color: Color(0xFF607D8B), fontStyle: FontStyle.italic)),
                      ),
                    )
                  else
                    Card(
                      margin: EdgeInsets.zero,
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxHeight: 280),
                        child: SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: SingleChildScrollView(
                            child: DataTable(
                              headingRowHeight: 36,
                              dataRowMinHeight: 32,
                              dataRowMaxHeight: 36,
                              columnSpacing: 14,
                              headingTextStyle: const TextStyle(
                                color: Color(0xFF00695C),
                                fontWeight: FontWeight.bold,
                                fontSize: 12,
                              ),
                              dataTextStyle: const TextStyle(
                                color: Color(0xFF263238),
                                fontSize: 11,
                              ),
                              headingRowColor: WidgetStateProperty.all(const Color(0xFFE0F2F1)),
                              border: TableBorder(
                                horizontalInside: BorderSide(color: Colors.grey.shade300, width: 0.5),
                                verticalInside: BorderSide(color: Colors.grey.shade300, width: 0.5),
                                top: const BorderSide(color: Color(0xFFB0BEC5)),
                                bottom: const BorderSide(color: Color(0xFFB0BEC5)),
                                left: const BorderSide(color: Color(0xFFB0BEC5)),
                                right: const BorderSide(color: Color(0xFFB0BEC5)),
                              ),
                              columns: const [
                                DataColumn(label: Text('Mã NV')),
                                DataColumn(label: Text('Thời gian')),
                                DataColumn(label: Text('Trạng thái')),
                                DataColumn(label: Text('Punch')),
                                DataColumn(label: Text('Ghi')),
                                DataColumn(label: Text('Xóa')),
                              ],
                              rows: List.generate(_history.length, (i) {
                                final h = _history[i];
                                return DataRow(
                                  color: WidgetStateProperty.all(
                                    i.isEven ? Colors.white : const Color(0xFFF5F7FA),
                                  ),
                                  cells: [
                                    DataCell(Text('NV ${h.userId}',
                                        style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF00695C)))),
                                    DataCell(Text(h.timestamp,
                                        style: const TextStyle(fontFamily: 'monospace', fontSize: 10))),
                                    DataCell(Text(h.statusName,
                                        style: const TextStyle(color: Color(0xFF455A64), fontWeight: FontWeight.w500))),
                                    DataCell(Text(h.methodName,
                                        style: const TextStyle(color: Color(0xFF455A64)))),
                                    DataCell(Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: (h.writtenToDevice ? Colors.green : Colors.orange).withOpacity(0.15),
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: h.writtenToDevice ? const Color(0xFF2E7D32) : const Color(0xFFEF6C00),
                                          width: 0.5,
                                        ),
                                      ),
                                      child: Text(
                                        h.writtenToDevice ? 'máy' : 'local',
                                        style: TextStyle(
                                          color: h.writtenToDevice ? const Color(0xFF1B5E20) : const Color(0xFFE65100),
                                          fontSize: 10,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    )),
                                    DataCell(IconButton(
                                      icon: const Icon(Icons.delete, color: Color(0xFFD32F2F), size: 18),
                                      onPressed: () => _deletePunch(h),
                                      padding: EdgeInsets.zero,
                                      constraints: const BoxConstraints(),
                                    )),
                                  ],
                                );
                              }),
                            ),
                          ),
                        ),
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
