// screens/log_screen.dart
// Log page: list devices + fetch ATTLOG from embedded server
// Style: light teal theme, matches the desktop UX
import 'package:flutter/material.dart';
import '../main.dart';
import '../models/models.dart';
import '../widgets/embedded_api.dart';

class LogScreen extends StatefulWidget {
  const LogScreen({super.key});
  @override
  State<LogScreen> createState() => _LogScreenState();
}

class _LogScreenState extends State<LogScreen> {
  late EmbeddedApi _api;
  List<Device> _devices = [];
  List<AttLog> _records = [];
  final Set<String> _selectedIps = {};
  bool _loading = false;
  bool _fetching = false;
  String _statusText = 'Sẵn sàng';
  String _deviceSearch = '';
  String _pinSearch = '';

  // Date range chips
  static const _dateRanges = [
    {'label': 'Hôm nay', 'days': 0},
    {'label': 'Hôm qua', 'days': 1, 'yesterday': true},
    {'label': '7 ngày', 'days': 6},
    {'label': '30 ngày', 'days': 29},
  ];
  int _dateRangeIndex = 2; // default: 7 ngày
  String _fromDate = '';
  String _toDate = '';

  @override
  void initState() {
    super.initState();
    _api = EmbeddedApi(context.appState.serverUrl.isNotEmpty
        ? context.appState.serverUrl
        : 'http://127.0.0.1:8080');
    _applyDateRange();
    _waitForServerAndLoad();
    context.appState.addListener(_onAppStateChanged);
  }

  @override
  void dispose() {
    context.appState.removeListener(_onAppStateChanged);
    super.dispose();
  }

  void _onAppStateChanged() {
    if (!mounted) return;
    final newBase = context.appState.serverUrl.isNotEmpty
        ? context.appState.serverUrl
        : 'http://127.0.0.1:8080';
    if (_api.baseUrl != newBase) {
      _api = EmbeddedApi(newBase);
      _loadDevices();
    }
  }

  Future<void> _waitForServerAndLoad() async {
    final sw = Stopwatch()..start();
    while (!context.appState.serverRunning && sw.elapsed < const Duration(seconds: 5)) {
      await Future.delayed(const Duration(milliseconds: 100));
    }
    if (!mounted) return;
    await _loadDevices();
  }

  void _applyDateRange() {
    final now = DateTime.now();
    final r = _dateRanges[_dateRangeIndex];
    if (r['yesterday'] == true) {
      final y = now.subtract(const Duration(days: 1));
      _fromDate = _formatDate(y);
      _toDate = _formatDate(y);
    } else {
      final days = r['days'] as int;
      final start = now.subtract(Duration(days: days));
      _fromDate = _formatDate(start);
      _toDate = _formatDate(now);
    }
  }

  String _formatDate(DateTime d) {
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  Future<void> _loadDevices() async {
    setState(() => _loading = true);
    final devs = await _api.getDevices();
    setState(() {
      _devices = devs;
      _loading = false;
    });
  }

  /// Scan all devices: TCP ping + retrieve real device name via ZK protocol
  /// (`cmdGetDeviceName` for attendance type). Updates _devices with online/latency.
  /// Falls back silently if ZK protocol fails (offline / VPN not connected).
  Future<void> _scanDevices() async {
    setState(() {
      _loading = true;
      _statusText = '🔄 Đang quét thiết bị...';
    });
    try {
      final resp = await _api.pingAll();
      if (!mounted) return;
      final list = (resp['devices'] as List? ?? []).cast<Map<String, dynamic>>();
      if (list.isEmpty) {
        setState(() {
          _loading = false;
          _statusText = '⚠️ Quét xong: 0 thiết bị. Kiểm tra VPN / mạng LAN.';
        });
        return;
      }
      setState(() {
        _devices = list.map((j) => Device.fromJson(j)).toList();
        // Auto-select attendance + server (not gateway) on first scan
        if (_selectedIps.isEmpty) {
          _selectedIps
            ..clear()
            ..addAll(_devices
                .where((d) => d.type == 'attendance' || d.type == 'server')
                .map((d) => d.ip));
        }
        final online = _devices.where((d) => d.online).length;
        _loading = false;
        _statusText = '✅ Quét xong: ${_devices.length} thiết bị ($online online)';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _statusText = '❌ Lỗi quét: $e';
      });
    }
  }

  Future<void> _fetchLogs() async {
    if (_selectedIps.isEmpty) {
      _showSnack('Chưa chọn máy nào', isError: true);
      return;
    }
    setState(() {
      _fetching = true;
      _statusText = '⏳ Đang đọc ATTLOG từ ${_selectedIps.length} máy...';
    });
    final all = <AttLog>[];
    int okCount = 0;
    // Query each selected device via embedded server endpoint
    // The embedded server runs queries via ZK protocol (zk_client.dart)
    for (final ip in _selectedIps) {
      try {
        final resp = await _api.postDeviceAttLog(ip, limit: 200);
        if (resp['ok'] == true) {
          okCount++;
          for (final j in (resp['records'] as List? ?? [])) {
            all.add(AttLog.fromJson(j as Map<String, dynamic>));
          }
        }
      } catch (_) {}
    }
    setState(() {
      _fetching = false;
      _records = all;
      _statusText = okCount > 0
          ? '✅ OK: $okCount/${_selectedIps.length} máy, ${all.length} records'
          : '⚠️ 0/${_selectedIps.length} máy OK. Đảm bảo VPN đã bật và máy online.';

      // Refresh recent on embedded server cache
      if (okCount > 0) _showSnack('Đã tải ${all.length} records từ $okCount máy');
    });
  }

  List<Device> _filteredDevices() {
    if (_deviceSearch.isEmpty) return _devices;
    final s = _deviceSearch.toLowerCase();
    return _devices.where((d) =>
      d.ip.toLowerCase().contains(s) ||
      d.note.toLowerCase().contains(s) ||
      d.type.toLowerCase().contains(s)
    ).toList();
  }

  List<AttLog> _filteredRecords() {
    return _records.where((r) {
      if (_pinSearch.isNotEmpty &&
          !r.pin.contains(_pinSearch) &&
          !r.userName.toLowerCase().contains(_pinSearch.toLowerCase())) {
        return false;
      }
      return true;
    }).toList();
  }

  void _showSnack(String text, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(text),
      backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700,
      duration: const Duration(seconds: 2),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFFF5F7FA),
      child: Column(
        children: [
          _buildDateBar(),
          _buildStatusBar(),
          Expanded(child: Row(
            children: [
              SizedBox(
                width: 200,
                child: _buildDevicePanel(),
              ),
              Expanded(child: _buildRecordsPanel()),
            ],
          )),
        ],
      ),
    );
  }

  Widget _buildDateBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
      color: const Color(0xFFE0F2F1),
      child: Column(
        children: [
          SizedBox(
            height: 38,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: List.generate(_dateRanges.length, (i) {
                final selected = _dateRangeIndex == i;
                return Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: ChoiceChip(
                    label: Text(
                      _dateRanges[i]['label'] as String,
                      style: TextStyle(
                        color: selected ? Colors.white : const Color(0xFF455A64),
                        fontWeight: selected ? FontWeight.bold : FontWeight.w500,
                        fontSize: 13,
                      ),
                    ),
                    selected: selected,
                    selectedColor: const Color(0xFF00695C),
                    backgroundColor: Colors.white,
                    side: BorderSide(
                      color: selected ? const Color(0xFF00695C) : const Color(0xFFB0BEC5),
                    ),
                    onSelected: (_) {
                      setState(() {
                        _dateRangeIndex = i;
                        _applyDateRange();
                      });
                    },
                  ),
                );
              }),
            ),
          ),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: _dateBox('Từ ngày', _fromDate)),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 4),
              child: Icon(Icons.arrow_forward, color: Color(0xFF607D8B), size: 18),
            ),
            Expanded(child: _dateBox('Đến ngày', _toDate)),
            const SizedBox(width: 6),
            ElevatedButton.icon(
              onPressed: (_fetching || _loading) ? null : _scanDevices,
              icon: _loading
                ? const SizedBox(width: 14, height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.wifi_tethering, size: 18, color: Colors.white),
              label: const Text('QUÉT', style: TextStyle(color: Colors.white)),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF1976D2),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              ),
            ),
            const SizedBox(width: 6),
            ElevatedButton.icon(
              onPressed: _fetching ? null : _fetchLogs,
              icon: _fetching
                ? const SizedBox(width: 14, height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.refresh, size: 18, color: Colors.white),
              label: const Text('LẤY LOG', style: TextStyle(color: Colors.white)),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF2E7D32),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              ),
            ),
          ]),
        ],
      ),
    );
  }

  Widget _dateBox(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFFB0BEC5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: Color(0xFF607D8B), fontSize: 10)),
          Text(value, style: const TextStyle(
            color: Color(0xFF263238), fontSize: 13, fontWeight: FontWeight.bold,
          )),
        ],
      ),
    );
  }

  Widget _buildStatusBar() {
    if (_statusText.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      color: const Color(0xFFF5F7FA),
      child: Text(
        _statusText,
        style: const TextStyle(color: Color(0xFF455A64), fontSize: 11),
      ),
    );
  }

  Widget _buildDevicePanel() {
    return Container(
      color: const Color(0xFFFAFAFA),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.fromLTRB(8, 8, 8, 6),
            decoration: const BoxDecoration(
              color: Color(0xFF00695C),
              border: Border(bottom: BorderSide(color: Color(0xFF004D40), width: 1)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(children: [
                  Icon(Icons.devices, color: Colors.white, size: 16),
                  SizedBox(width: 6),
                  Text('THIẾT BỊ',
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
                ]),
                const SizedBox(height: 6),
                TextField(
                  decoration: InputDecoration(
                    hintText: 'Tìm IP...',
                    isDense: true,
                    filled: true,
                    fillColor: Colors.white,
                    prefixIcon: const Icon(Icons.search, size: 16, color: Color(0xFF607D8B)),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(4),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                    hintStyle: const TextStyle(fontSize: 11),
                  ),
                  style: const TextStyle(color: Color(0xFF263238), fontSize: 12),
                  onChanged: (v) => setState(() => _deviceSearch = v),
                ),
                const SizedBox(height: 4),
                Row(children: [
                  Expanded(
                    child: TextButton.icon(
                      onPressed: _toggleAllDevices,
                      icon: const Icon(Icons.select_all, size: 14, color: Colors.white),
                      label: Text(
                        _allSelected() ? 'Bỏ chọn' : 'Chọn tất cả',
                        style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w600),
                      ),
                      style: TextButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 4),
                        minimumSize: const Size(0, 28),
                        backgroundColor: Colors.white.withOpacity(0.15),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                      ),
                    ),
                  ),
                  const SizedBox(width: 4),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.25),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '${_selectedIps.length}',
                      style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                    ),
                  ),
                ]),
              ],
            ),
          ),
          Expanded(
            child: _loading
              ? const Center(child: CircularProgressIndicator(color: Color(0xFF00897B)))
              : _filteredDevices().isEmpty
                ? Center(child: Text(
                    _devices.isEmpty ? 'Chưa tải thiết bị' : 'Không tìm thấy',
                    style: const TextStyle(color: Color(0xFF607D8B), fontSize: 12),
                  ))
                : ListView.builder(
                    itemCount: _filteredDevices().length,
                    itemBuilder: (ctx, i) {
                      final d = _filteredDevices()[i];
                      final selected = _selectedIps.contains(d.ip);
                      final online = d.online;
                      return Container(
                        decoration: BoxDecoration(
                          color: selected
                              ? const Color(0xFFB2DFDB)
                              : (online ? const Color(0xFFE8F5E9) : null),
                          border: const Border(
                            bottom: BorderSide(color: Color(0xFFEEEEEE), width: 0.5),
                          ),
                        ),
                        child: CheckboxListTile(
                          dense: true,
                          value: selected,
                          controlAffinity: ListTileControlAffinity.leading,
                          title: Row(children: [
                            Icon(
                              online ? Icons.check_circle : Icons.cancel,
                              color: online ? Colors.green : Colors.red,
                              size: 12,
                            ),
                            const SizedBox(width: 4),
                            Expanded(
                              child: Text(
                                d.ip,
                                style: TextStyle(
                                  color: const Color(0xFF263238),
                                  fontSize: 12,
                                  fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                                  fontFamily: 'monospace',
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            if (d.latencyMs > 0)
                              Text('${d.latencyMs}ms',
                                  style: const TextStyle(
                                    fontSize: 9, color: Color(0xFF607D8B),
                                    fontFamily: 'monospace',
                                  )),
                          ]),
                          subtitle: Text(
                            '${_typeLabel(d.type)} · ${d.note.isNotEmpty ? d.note : (online ? "online" : "offline")}',
                            style: TextStyle(
                              color: online ? const Color(0xFF2E7D32) : const Color(0xFF607D8B),
                              fontSize: 10,
                              fontWeight: online ? FontWeight.w500 : FontWeight.normal,
                            ),
                          ),
                          onChanged: (v) {
                            setState(() {
                              if (v == true) {
                                _selectedIps.add(d.ip);
                              } else {
                                _selectedIps.remove(d.ip);
                              }
                            });
                          },
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecordsPanel() {
    final filtered = _filteredRecords();
    return Container(
      color: Colors.white,
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            color: const Color(0xFFF5F7FA),
            child: Row(
              children: [
                const Icon(Icons.list_alt, size: 18, color: Color(0xFF00695C)),
                const SizedBox(width: 6),
                Text('LOG CHẤM CÔNG (${filtered.length})',
                  style: const TextStyle(color: Color(0xFF00695C), fontWeight: FontWeight.bold, fontSize: 12)),
                const Spacer(),
                SizedBox(
                  width: 180,
                  child: TextField(
                    decoration: InputDecoration(
                      hintText: 'Tìm PIN hoặc tên...',
                      isDense: true,
                      filled: true,
                      fillColor: Colors.white,
                      prefixIcon: const Icon(Icons.search, size: 14, color: Color(0xFF607D8B)),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(4),
                        borderSide: BorderSide.none,
                      ),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                      hintStyle: const TextStyle(fontSize: 11),
                    ),
                    style: const TextStyle(fontSize: 12),
                    onChanged: (v) => setState(() => _pinSearch = v),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: filtered.isEmpty
              ? const Center(child: Text(
                  'Chưa có log. Bấm "LẤY LOG" để tải.',
                  style: TextStyle(color: Color(0xFF607D8B), fontSize: 13),
                ))
              : ListView.builder(
                  itemCount: filtered.length,
                  itemBuilder: (ctx, i) {
                    final r = filtered[i];
                    return _recordTile(r);
                  },
                ),
          ),
        ],
      ),
    );
  }

  Widget _recordTile(AttLog r) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE), width: 0.5)),
      ),
      child: Row(children: [
        Container(
          width: 32, height: 32,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: r.status == 0
              ? const Color(0xFF66BB6A).withOpacity(0.15)
              : const Color(0xFFFFB74D).withOpacity(0.15),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Text(
            r.status == 0 ? 'IN' : (r.status == 1 ? 'OUT' : '#${r.status}'),
            style: TextStyle(
              color: r.status == 0 ? const Color(0xFF2E7D32) : const Color(0xFFE65100),
              fontWeight: FontWeight.bold,
              fontSize: 10,
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                r.userName.isNotEmpty ? r.userName : r.pin,
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xFF263238)),
                maxLines: 1, overflow: TextOverflow.ellipsis,
              ),
              Text(
                r.pin,
                style: const TextStyle(fontSize: 10, color: Color(0xFF607D8B), fontFamily: 'monospace'),
              ),
            ],
          ),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(r.timestamp, style: const TextStyle(fontSize: 12, color: Color(0xFF263238))),
            const SizedBox(height: 2),
            Text(
              '${_verifyLabel(r.punch)} · ${r.deviceIp}',
              style: const TextStyle(fontSize: 10, color: Color(0xFF607D8B), fontFamily: 'monospace'),
            ),
          ],
        ),
      ]),
    );
  }

  String _typeLabel(String t) {
    switch (t) {
      case 'attendance': return 'CC';
      case 'server': return 'SV';
      case 'gateway': return 'GW';
      case 'virtual': return 'SIM';
      default: return t.toUpperCase();
    }
  }

  String _verifyLabel(int v) {
    switch (v) {
      case 0: return 'PWD';
      case 1: return 'FP';
      case 15: return 'CARD';
      default: return '#$v';
    }
  }

  bool _allSelected() {
    final attend = _devices.where((d) => d.type != 'virtual').toList();
    if (attend.isEmpty) return false;
    return _selectedIps.containsAll(attend.map((d) => d.ip));
  }

  void _toggleAllDevices() {
    setState(() {
      if (_allSelected()) {
        _selectedIps.clear();
      } else {
        _selectedIps
          ..clear()
          ..addAll(_devices
              .where((d) => d.type != 'virtual')
              .map((d) => d.ip));
      }
    });
  }
}
