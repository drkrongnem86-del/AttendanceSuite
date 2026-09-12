// Remote Punch Screen - chấm công từ xa qua API
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'api.dart';
import 'settings.dart';

class RemotePunchScreen extends StatefulWidget {
  final AttendanceApi api;
  RemotePunchScreen({required this.api});

  @override
  _RemotePunchScreenState createState() => _RemotePunchScreenState();
}

class _RemotePunchScreenState extends State<RemotePunchScreen> {
  String _userId = '';
  int _selectedStatus = 0;
  String? _selectedDevice;
  bool _submitting = false;
  String? _lastResult;
  bool _lastSuccess = false;
  final _userCtrl = TextEditingController();
  final List<Map<String, dynamic>> _history = [];
  List<String> _devices = [];

  static const _statuses = [
    {'code': 0, 'name': 'Check-In', 'vn': 'Vào ca', 'icon': '✅', 'color': Colors.green},
    {'code': 1, 'name': 'Check-Out', 'vn': 'Tan ca', 'icon': '🔴', 'color': Colors.red},
    {'code': 2, 'name': 'Break-Out', 'vn': 'Ra ngoài', 'icon': '☕', 'color': Colors.amber},
    {'code': 3, 'name': 'Break-In', 'vn': 'Vào lại', 'icon': '🔄', 'color': Colors.blue},
    {'code': 4, 'name': 'OT-In', 'vn': 'Vào OT', 'icon': '⏰', 'color': Colors.purple},
    {'code': 5, 'name': 'OT-Out', 'vn': 'Tan OT', 'icon': '🏁', 'color': Colors.orange},
  ];

  @override
  void initState() {
    super.initState();
    _loadDevices();
  }

  Future<void> _loadDevices() async {
    final devices = await Settings.getDeviceIps();
    setState(() {
      _devices = devices;
      _selectedDevice = devices.isNotEmpty ? devices[0] : null;
    });
  }

  @override
  void dispose() {
    _userCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final uid = _userCtrl.text.trim();
    if (uid.isEmpty) {
      setState(() {
        _lastResult = 'Vui lòng nhập mã NV';
        _lastSuccess = false;
      });
      return;
    }
    setState(() {
      _submitting = true;
      _userId = uid;
    });
    try {
      final result = await widget.api.remotePunch(
        uid, _selectedStatus, deviceIp: _selectedDevice,
      );
      final ok = result['ok'] == true;
      final msg = result['message']?.toString() ?? result['error']?.toString() ?? 'OK';
      setState(() {
        _lastResult = '${ok ? "✓" : "✗"} $msg';
        _lastSuccess = ok;
        if (ok) {
          _history.insert(0, {
            'ts': DateTime.now().toString().split('.')[0],
            'uid': uid,
            'status': _selectedStatus,
            'status_name': _statuses[_selectedStatus]['name'],
            'device': _selectedDevice,
          });
          if (_history.length > 20) _history.removeLast();
        }
      });
      if (ok) {
        _userCtrl.clear();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('✓ Đã ghi NV $uid ${_statuses[_selectedStatus]['vn']}'),
            backgroundColor: Colors.green.shade700,
            duration: const Duration(seconds: 2),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('✗ $msg'),
            backgroundColor: Colors.red.shade700,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    } finally {
      setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Banner
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF00695C), Color(0xFF26A69A)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(10),
              boxShadow: [
                BoxShadow(color: const Color(0xFF00897B).withOpacity(0.3), blurRadius: 6, offset: const Offset(0, 2)),
              ],
            ),
            child: const Row(
              children: [
                Icon(Icons.cloud_done, color: Colors.white, size: 32),
                SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Chấm công từ xa',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.bold)),
                      Text('Ghi vào pending queue, service sync tự động',
                          style: TextStyle(color: Colors.white70, fontSize: 12)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Form
          Card(
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Mã NV', style: TextStyle(color: Color(0xFF455A64), fontWeight: FontWeight.w600, fontSize: 13)),
                  const SizedBox(height: 6),
                  TextField(
                    controller: _userCtrl,
                    keyboardType: TextInputType.number,
                    maxLength: 10,
                    autofocus: true,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    style: const TextStyle(
                        color: Color(0xFF00695C),
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                        fontFamily: 'monospace'),
                    textAlign: TextAlign.center,
                    decoration: InputDecoration(
                      hintText: 'Nhập mã NV',
                      hintStyle: TextStyle(color: Colors.grey.shade400),
                      filled: true,
                      fillColor: const Color(0xFFF5F7FA),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(6),
                        borderSide: const BorderSide(color: Color(0xFFB0BEC5)),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(6),
                        borderSide: const BorderSide(color: Color(0xFF00897B), width: 2),
                      ),
                      counterText: '',
                    ),
                    onSubmitted: (_) => _submit(),
                  ),
                  const SizedBox(height: 14),
                  const Text('Thao tác', style: TextStyle(color: Color(0xFF455A64), fontWeight: FontWeight.w600, fontSize: 13)),
                  const SizedBox(height: 6),
                  GridView.count(
                    crossAxisCount: 2,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    childAspectRatio: 2.4,
                    children: _statuses.map((s) {
                      final selected = _selectedStatus == s['code'];
                      final color = s['color'] as Color;
                      return GestureDetector(
                        onTap: () => setState(() => _selectedStatus = s['code'] as int),
                        child: Container(
                          margin: const EdgeInsets.all(3),
                          decoration: BoxDecoration(
                            color: selected
                                ? color
                                : Colors.white,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: selected ? color : const Color(0xFFE0E0E0),
                              width: selected ? 2 : 1,
                            ),
                            boxShadow: selected
                                ? [BoxShadow(color: color.withOpacity(0.3), blurRadius: 4, offset: const Offset(0, 2))]
                                : null,
                          ),
                          alignment: Alignment.center,
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(s['icon'] as String,
                                  style: const TextStyle(fontSize: 20)),
                              const SizedBox(width: 6),
                              Flexible(
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      s['name'] as String,
                                      style: TextStyle(
                                        color: selected ? Colors.white : const Color(0xFF263238),
                                        fontSize: 13,
                                        fontWeight: selected ? FontWeight.bold : FontWeight.w600,
                                      ),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                    Text(
                                      s['vn'] as String,
                                      style: TextStyle(
                                        color: selected ? Colors.white70 : const Color(0xFF607D8B),
                                        fontSize: 10,
                                      ),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 14),
                  const Text('Máy chấm công', style: TextStyle(color: Color(0xFF455A64), fontWeight: FontWeight.w600, fontSize: 13)),
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF5F7FA),
                      border: Border.all(color: const Color(0xFFB0BEC5)),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: DropdownButton<String>(
                      value: _selectedDevice,
                      isExpanded: true,
                      dropdownColor: Colors.white,
                      style: const TextStyle(color: Color(0xFF263238), fontSize: 14, fontFamily: 'monospace'),
                      underline: const SizedBox(),
                      icon: const Icon(Icons.arrow_drop_down, color: Color(0xFF455A64)),
                      items: _devices
                          .map((ip) => DropdownMenuItem(
                                value: ip,
                                child: Text(ip,
                                    style: const TextStyle(
                                        fontFamily: 'monospace', fontSize: 14, color: Color(0xFF263238))),
                              ))
                          .toList(),
                      onChanged: (v) => setState(() => _selectedDevice = v),
                    ),
                  ),
                  const SizedBox(height: 18),
                  ElevatedButton.icon(
                    onPressed: _submitting ? null : _submit,
                    icon: _submitting
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.send, color: Colors.white, size: 20),
                    label: Text(
                      _submitting ? 'Đang gửi...' : 'CHẤM CÔNG',
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.bold),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF00897B),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                ],
              ),
            ),
          ),

          if (_lastResult != null) ...[
            const SizedBox(height: 12),
            Card(
              margin: EdgeInsets.zero,
              color: _lastSuccess
                  ? const Color(0xFFE8F5E9)
                  : const Color(0xFFFFEBEE),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: BorderSide(
                  color: _lastSuccess ? const Color(0xFF66BB6A) : const Color(0xFFEF5350),
                  width: 1,
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    Icon(
                      _lastSuccess ? Icons.check_circle : Icons.error,
                      color: _lastSuccess ? const Color(0xFF2E7D32) : const Color(0xFFC62828),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        _lastResult!,
                        style: TextStyle(
                          color: _lastSuccess ? const Color(0xFF1B5E20) : const Color(0xFFB71C1C),
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],

          if (_history.isNotEmpty) ...[
            const SizedBox(height: 16),
            Card(
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.history, color: Color(0xFF00695C), size: 18),
                        const SizedBox(width: 8),
                        const Text('Lịch sử (gần đây)',
                            style: TextStyle(
                                color: Color(0xFF00695C),
                                fontSize: 14,
                                fontWeight: FontWeight.bold)),
                        const Spacer(),
                        Text('${_history.length} lượt',
                            style: const TextStyle(color: Color(0xFF607D8B), fontSize: 12)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    // Bảng cuộn ngang để xem full
                    SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: DataTable(
                        headingRowHeight: 34,
                        dataRowMinHeight: 32,
                        dataRowMaxHeight: 38,
                        columnSpacing: 16,
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
                          DataColumn(label: Text('Thời gian')),
                          DataColumn(label: Text('Mã NV')),
                          DataColumn(label: Text('Trạng thái')),
                          DataColumn(label: Text('Máy')),
                        ],
                        rows: List.generate(_history.length, (i) {
                          final h = _history[i];
                          return DataRow(
                            color: WidgetStateProperty.all(
                              i.isEven ? Colors.white : const Color(0xFFF5F7FA),
                            ),
                            cells: [
                              DataCell(Text(h['ts'] as String,
                                  style: const TextStyle(fontFamily: 'monospace', fontSize: 10))),
                              DataCell(Text('NV ${h['uid']}',
                                  style: const TextStyle(
                                      fontWeight: FontWeight.bold, color: Color(0xFF00695C)))),
                              DataCell(Text(h['status_name'] as String,
                                  style: const TextStyle(color: Color(0xFF455A64), fontWeight: FontWeight.w500))),
                              DataCell(Text(h['device'] as String,
                                  style: const TextStyle(fontFamily: 'monospace', fontSize: 10, color: Color(0xFF607D8B)))),
                            ],
                          );
                        }),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],

          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFFFF8E1),
              border: Border.all(color: const Color(0xFFFFB74D)),
              borderRadius: BorderRadius.circular(6),
            ),
            child: const Row(
              children: [
                Icon(Icons.info_outline, color: Color(0xFFE65100), size: 18),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Lưu ý: Tool ghi vào pending queue trên server. Service '
                    'remote_punch_service.py sẽ tự sync qua Secutime/ADMS trong vòng '
                    '30 giây. Nếu sync fail (firmware X628 PRO chặn), vẫn lưu local.',
                    style: TextStyle(color: Color(0xFFBF360C), fontSize: 11, height: 1.4),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
