// Remote Punch Screen - chấm công từ xa qua API
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'api.dart';

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

  static const _statuses = [
    {'code': 0, 'name': 'Check-In', 'vn': 'Vào ca', 'icon': '✅', 'color': Colors.green},
    {'code': 1, 'name': 'Check-Out', 'vn': 'Tan ca', 'icon': '🔴', 'color': Colors.red},
    {'code': 2, 'name': 'Break-Out', 'vn': 'Ra ngoài', 'icon': '☕', 'color': Colors.amber},
    {'code': 3, 'name': 'Break-In', 'vn': 'Vào lại', 'icon': '🔄', 'color': Colors.blue},
    {'code': 4, 'name': 'OT-In', 'vn': 'Vào OT', 'icon': '⏰', 'color': Colors.purple},
    {'code': 5, 'name': 'OT-Out', 'vn': 'Tan OT', 'icon': '🏁', 'color': Colors.orange},
  ];

  static const _devices = [
    '172.16.0.212', // May 1
    '172.16.0.214', // May 3
    '172.16.0.30',  // Gateway
    '172.16.0.31',  // Secutime
  ];

  @override
  void initState() {
    super.initState();
    _selectedDevice = _devices[0];
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
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [Colors.cyan.shade900, Colors.blue.shade900],
              ),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Row(
              children: [
                Icon(Icons.cloud_done, color: Colors.cyanAccent, size: 32),
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
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.blueGrey.shade900,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('Mã NV', style: TextStyle(color: Colors.white70)),
                const SizedBox(height: 4),
                TextField(
                  controller: _userCtrl,
                  keyboardType: TextInputType.number,
                  maxLength: 10,
                  autofocus: true,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  style: const TextStyle(
                      color: Colors.cyanAccent,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      fontFamily: 'monospace'),
                  textAlign: TextAlign.center,
                  decoration: InputDecoration(
                    hintText: 'Nhập mã NV',
                    hintStyle: TextStyle(color: Colors.white24),
                    filled: true,
                    fillColor: Colors.black26,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(6),
                    ),
                    counterText: '',
                  ),
                  onSubmitted: (_) => _submit(),
                ),
                const SizedBox(height: 12),
                const Text('Thao tác', style: TextStyle(color: Colors.white70)),
                const SizedBox(height: 4),
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  childAspectRatio: 2.2,
                  children: _statuses.map((s) {
                    final selected = _selectedStatus == s['code'];
                    return GestureDetector(
                      onTap: () => setState(() => _selectedStatus = s['code'] as int),
                      child: Container(
                        margin: const EdgeInsets.all(3),
                        decoration: BoxDecoration(
                          color: selected
                              ? (s['color'] as Color)
                              : Colors.blueGrey.shade800,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                            color: selected ? Colors.cyanAccent : Colors.transparent,
                            width: 2,
                          ),
                        ),
                        alignment: Alignment.center,
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(s['icon'] as String,
                                style: const TextStyle(fontSize: 18)),
                            Text(
                              '${s['name']}\n(${s['vn']})',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: selected ? Colors.black : Colors.white,
                                fontSize: 11,
                                fontWeight: selected
                                    ? FontWeight.bold
                                    : FontWeight.normal,
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 12),
                const Text('Máy chấm công',
                    style: TextStyle(color: Colors.white70)),
                const SizedBox(height: 4),
                DropdownButton<String>(
                  value: _selectedDevice,
                  isExpanded: true,
                  dropdownColor: Colors.blueGrey.shade800,
                  style: const TextStyle(color: Colors.white),
                  items: _devices
                      .map((ip) => DropdownMenuItem(
                            value: ip,
                            child: Text(ip,
                                style: const TextStyle(
                                    fontFamily: 'monospace', fontSize: 13)),
                          ))
                      .toList(),
                  onChanged: (v) => setState(() => _selectedDevice = v),
                ),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: _submitting ? null : _submit,
                  icon: _submitting
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.black))
                      : const Icon(Icons.send, color: Colors.black),
                  label: Text(
                    _submitting ? 'Đang gửi...' : 'CHẤM CÔNG',
                    style: const TextStyle(
                        color: Colors.black,
                        fontSize: 16,
                        fontWeight: FontWeight.bold),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.cyanAccent,
                    padding: const EdgeInsets.all(16),
                  ),
                ),
              ],
            ),
          ),

          if (_lastResult != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: _lastSuccess
                    ? Colors.green.shade900
                    : Colors.red.shade900,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                _lastResult!,
                style: const TextStyle(color: Colors.white, fontSize: 13),
              ),
            ),
          ],

          if (_history.isNotEmpty) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.blueGrey.shade900,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Lịch sử (gần đây)',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  ...(_history.map((h) => Container(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        decoration: BoxDecoration(
                          border: Border(
                            bottom: BorderSide(
                                color: Colors.white12, width: 0.5),
                          ),
                        ),
                        child: Row(
                          children: [
                            Text(h['ts'] as String,
                                style: const TextStyle(
                                    color: Colors.white60, fontSize: 11)),
                            const SizedBox(width: 8),
                            Text('NV ${h['uid']}',
                                style: const TextStyle(
                                    color: Colors.cyanAccent,
                                    fontSize: 12,
                                    fontWeight: FontWeight.bold)),
                            const Spacer(),
                            Text(h['status_name'] as String,
                                style: const TextStyle(
                                    color: Colors.amber, fontSize: 12)),
                            const SizedBox(width: 8),
                            Text(h['device'] as String,
                                style: const TextStyle(
                                    color: Colors.white38,
                                    fontSize: 10,
                                    fontFamily: 'monospace')),
                          ],
                        ),
                      ))),
                ],
              ),
            ),
          ],

          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: Colors.amber.shade900.withOpacity(0.3),
              borderRadius: BorderRadius.circular(6),
            ),
            child: const Text(
              '💡 Lưu ý: Tool này ghi vào pending queue trên server. Service '
              'remote_punch_service.py sẽ tự sync qua Secutime/ADMS trong vòng '
              '30 giây. Nếu sync fail (firmware X628 PRO chặn), vẫn lưu local.',
              style: TextStyle(color: Colors.amber, fontSize: 11),
            ),
          ),
        ],
      ),
    );
  }
}
