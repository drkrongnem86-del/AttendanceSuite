// Log Viewer screen - shows devices and lets user fetch attendance logs
import 'package:flutter/material.dart';
import 'api.dart';

class ViewerScreen extends StatefulWidget {
  final AttendanceApi api;
  final VoidCallback onSettings;

  ViewerScreen({required this.api, required this.onSettings});

  @override
  _ViewerScreenState createState() => _ViewerScreenState();
}

class _ViewerScreenState extends State<ViewerScreen> {
  List<Device> _devices = [];
  List<Record> _records = [];
  Set<String> _selectedIps = {};
  bool _loading = false;
  String _statusText = 'Sẵn sàng';
  double _progress = 0.0;
  int _progressCount = 0;
  int _progressTotal = 0;
  bool _isRunning = false;
  String _fromDate = '';
  String _toDate = '';

  // Tab-based date range selector
  int _dateRangeIndex = 2; // default: 7 ngày
  static const _dateRanges = [
    {'label': 'Hôm nay', 'days': 0},
    {'label': 'Hôm qua', 'days': 1, 'yesterday': true},
    {'label': '7 ngày', 'days': 6},
    {'label': '30 ngày', 'days': 29},
    {'label': 'Tùy chỉnh', 'days': -1},
  ];

  // Filter UI
  String _searchText = '';
  String _statusFilter = '';
  String _punchFilter = '';
  String _timeFromFilter = '';
  String _timeToFilter = '';

  @override
  void initState() {
    super.initState();
    _applyDateRange();
    _loadDevices();
  }

  void _applyDateRange() {
    final now = DateTime.now();
    final range = _dateRanges[_dateRangeIndex];
    if (range['days'] == -1) {
      // Custom mode - don't change dates
      return;
    }
    if (range['yesterday'] == true) {
      final y = now.subtract(const Duration(days: 1));
      _fromDate = _formatDate(y);
      _toDate = _formatDate(y);
    } else {
      final days = range['days'] as int;
      final start = now.subtract(Duration(days: days));
      _fromDate = _formatDate(start);
      _toDate = _formatDate(now);
    }
  }

  String _formatDate(DateTime d) {
    return '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  }

  Future<void> _pickCustomDate({required bool isFrom}) async {
    final initial = isFrom
        ? DateTime.tryParse(_fromDate) ?? DateTime.now()
        : DateTime.tryParse(_toDate) ?? DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2020),
      lastDate: DateTime.now().add(const Duration(days: 1)),
      builder: (context, child) => Theme(
        data: ThemeData.dark().copyWith(
          colorScheme: const ColorScheme.dark(primary: Colors.cyan, onPrimary: Colors.black, surface: Color(0xFF1a1a2e), onSurface: Colors.white),
        ),
        child: child!,
      ),
    );
    if (picked != null) {
      setState(() {
        if (isFrom) {
          _fromDate = _formatDate(picked);
        } else {
          _toDate = _formatDate(picked);
        }
      });
    }
  }

  Future<void> _loadDevices() async {
    setState(() => _loading = true);
    final devices = await widget.api.getDevices();
    setState(() {
      _devices = devices;
      // Default: select all attendance devices
      _selectedIps = devices
          .where((d) => d.type == 'attendance')
          .map((d) => d.ip)
          .toSet();
      _loading = false;
    });
  }

  Future<void> _loadRecords() async {
    final records = await widget.api.getRecords();
    setState(() => _records = records);
  }

  Future<void> _startFetch() async {
    if (_selectedIps.isEmpty) {
      _showMsg('Chưa chọn máy nào', isError: true);
      return;
    }
    setState(() {
      _isRunning = true;
      _progress = 0.0;
      _progressCount = 0;
      _progressTotal = _selectedIps.length;
    });
    final result = await widget.api.fetchLogs(
      _selectedIps.toList(),
      _fromDate,
      _toDate,
    );
    if (result['ok'] == true) {
      // Poll status until done
      _pollStatus();
    } else {
      setState(() {
        _isRunning = false;
        _statusText = 'Lỗi: ' + (result['error']?.toString() ?? 'không rõ');
      });
    }
  }

  void _pollStatus() async {
    while (mounted && _isRunning) {
      await Future.delayed(const Duration(seconds: 1));
      final status = await widget.api.getStatus();
      if (!mounted) return;
      setState(() {
        _isRunning = status['running'] == true;
        _progressCount = status['progress'] ?? 0;
        _progressTotal = status['total'] ?? _progressTotal;
        _progress = _progressTotal > 0 ? _progressCount / _progressTotal : 0;
        _statusText = status['message']?.toString() ?? '';
      });
      if (!_isRunning) {
        _showMsg(_statusText, isError: !_statusText.contains('Hoàn tất'));
        await _loadRecords();
        break;
      }
    }
  }

  Future<void> _cancel() async {
    await widget.api.cancel();
    setState(() {
      _isRunning = false;
      _statusText = 'Đã yêu cầu dừng';
    });
  }

  void _showMsg(String text, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(text),
        backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700,
        duration: const Duration(seconds: 3),
      ),
    );
  }

  List<Record> _filteredRecords() {
    return _records.where((r) {
      if (_selectedIps.isNotEmpty && !_selectedIps.contains(r.deviceIp)) return false;
      if (_statusFilter.isNotEmpty) {
        final statusMap = {
          '0': 'Check-In', '1': 'Check-Out', '2': 'Break-Out',
          '3': 'Break-In', '4': 'OT-In', '5': 'OT-Out',
        };
        if (r.statusName != statusMap[_statusFilter]) return false;
      }
      if (_punchFilter.isNotEmpty) {
        if (r.punch.toString() != _punchFilter) return false;
      }
      if (_searchText.isNotEmpty) {
        final s = _searchText.toLowerCase();
        if (!r.userId.toLowerCase().contains(s) &&
            !r.deviceIp.toLowerCase().contains(s)) return false;
      }
      if (_timeFromFilter.isNotEmpty && r.time.compareTo(_timeFromFilter) < 0) return false;
      if (_timeToFilter.isNotEmpty && r.time.compareTo(_timeToFilter) > 0) return false;
      return true;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final isCustom = _dateRanges[_dateRangeIndex]['days'] == -1;
    return Column(
      children: [
        // Date range tabs + controls bar
        Container(
          padding: const EdgeInsets.fromLTRB(8, 6, 8, 8),
          color: Colors.blueGrey.shade900,
          child: Column(
            children: [
              // Tab-style date range picker
              SizedBox(
                height: 36,
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
                            color: selected ? Colors.black : Colors.white,
                            fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                            fontSize: 13,
                          ),
                        ),
                        selected: selected,
                        selectedColor: Colors.cyanAccent,
                        backgroundColor: Colors.white12,
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
              const SizedBox(height: 6),
              // Date display row (tappable if custom mode)
              Row(
                children: [
                  Expanded(
                    child: InkWell(
                      onTap: isCustom ? () => _pickCustomDate(isFrom: true) : null,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white10,
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(color: isCustom ? Colors.cyanAccent : Colors.transparent),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Từ ngày', style: TextStyle(color: Colors.white60, fontSize: 10)),
                            Text(
                              _fromDate.isEmpty ? '...' : _fromDate,
                              style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 6),
                    child: Icon(Icons.arrow_forward, color: Colors.white60, size: 18),
                  ),
                  Expanded(
                    child: InkWell(
                      onTap: isCustom ? () => _pickCustomDate(isFrom: false) : null,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white10,
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(color: isCustom ? Colors.cyanAccent : Colors.transparent),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Đến ngày', style: TextStyle(color: Colors.white60, fontSize: 10)),
                            Text(
                              _toDate.isEmpty ? '...' : _toDate,
                              style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  if (_isRunning)
                    ElevatedButton.icon(
                      onPressed: _cancel,
                      icon: const Icon(Icons.stop, size: 18),
                      label: const Text('DỪNG'),
                      style: ElevatedButton.styleFrom(backgroundColor: Colors.red, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8)),
                    )
                  else
                    ElevatedButton.icon(
                      onPressed: _startFetch,
                      icon: const Icon(Icons.refresh, size: 18),
                      label: const Text('LẤY LOG'),
                      style: ElevatedButton.styleFrom(backgroundColor: Colors.green, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8)),
                    ),
                  const SizedBox(width: 4),
                  IconButton(
                    icon: const Icon(Icons.settings, size: 20),
                    onPressed: widget.onSettings,
                    tooltip: 'Đổi IP server',
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
              ),
              if (_isRunning || _progress > 0)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: LinearProgressIndicator(
                    value: _progress,
                    backgroundColor: Colors.white24,
                  ),
                ),
              if (_statusText.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    '$_statusText ($_progressCount/$_progressTotal)',
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ),
            ],
          ),
        ),
        // Devices + Filters + Records
        Expanded(
          child: Row(
            children: [
              // Left: device list
              Container(
                width: 200,
                color: Colors.blueGrey.shade800,
                child: Column(
                  children: [
                    const Padding(
                      padding: EdgeInsets.all(8.0),
                      child: Text('THIẾT BỊ', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                    ),
                    Expanded(
                      child: _loading
                          ? const Center(child: CircularProgressIndicator())
                          : ListView(
                              children: _devices.map((d) {
                                final selected = _selectedIps.contains(d.ip);
                                return CheckboxListTile(
                                  dense: true,
                                  value: selected,
                                  title: Text(d.ip, style: const TextStyle(color: Colors.white, fontSize: 12)),
                                  subtitle: Text(
                                    d.type == 'attendance' ? 'CC' : (d.type == 'signing' ? 'KY' : d.type),
                                    style: const TextStyle(color: Colors.white60, fontSize: 10),
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
                                );
                              }).toList(),
                            ),
                    ),
                  ],
                ),
              ),
              // Right: filters + records
              Expanded(
                child: Column(
                  children: [
                    // Filter bar
                    Container(
                      padding: const EdgeInsets.all(6),
                      color: Colors.blueGrey.shade700,
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: [
                            SizedBox(
                              width: 120,
                              child: TextField(
                                decoration: const InputDecoration(
                                  hintText: 'Mã NV / IP',
                                  isDense: true,
                                  filled: true,
                                  fillColor: Colors.white10,
                                  border: OutlineInputBorder(),
                                ),
                                style: const TextStyle(color: Colors.white, fontSize: 12),
                                onChanged: (v) => setState(() => _searchText = v),
                              ),
                            ),
                            const SizedBox(width: 6),
                            DropdownButton<String>(
                              value: _statusFilter.isEmpty ? null : _statusFilter,
                              hint: const Text('Trạng thái', style: TextStyle(color: Colors.white70)),
                              dropdownColor: Colors.blueGrey,
                              style: const TextStyle(color: Colors.white),
                              items: const [
                                DropdownMenuItem(value: '', child: Text('Tất cả')),
                                DropdownMenuItem(value: '0', child: Text('Check-In')),
                                DropdownMenuItem(value: '1', child: Text('Check-Out')),
                                DropdownMenuItem(value: '2', child: Text('Break-Out')),
                                DropdownMenuItem(value: '3', child: Text('Break-In')),
                                DropdownMenuItem(value: '4', child: Text('OT-In')),
                                DropdownMenuItem(value: '5', child: Text('OT-Out')),
                              ],
                              onChanged: (v) => setState(() => _statusFilter = v ?? ''),
                            ),
                            const SizedBox(width: 6),
                            DropdownButton<String>(
                              value: _punchFilter.isEmpty ? null : _punchFilter,
                              hint: const Text('Punch', style: TextStyle(color: Colors.white70)),
                              dropdownColor: Colors.blueGrey,
                              style: const TextStyle(color: Colors.white),
                              items: const [
                                DropdownMenuItem(value: '', child: Text('Tất cả')),
                                DropdownMenuItem(value: '0', child: Text('Vân tay')),
                                DropdownMenuItem(value: '1', child: Text('Thẻ')),
                                DropdownMenuItem(value: '2', child: Text('Mật khẩu')),
                              ],
                              onChanged: (v) => setState(() => _punchFilter = v ?? ''),
                            ),
                            const SizedBox(width: 6),
                            SizedBox(
                              width: 80,
                              child: TextField(
                                decoration: const InputDecoration(
                                  hintText: 'HH:MM:SS',
                                  isDense: true,
                                  filled: true,
                                  fillColor: Colors.white10,
                                  border: OutlineInputBorder(),
                                ),
                                style: const TextStyle(color: Colors.white, fontSize: 12),
                                onChanged: (v) => setState(() => _timeFromFilter = v),
                              ),
                            ),
                            const Text(' - ', style: TextStyle(color: Colors.white70)),
                            SizedBox(
                              width: 80,
                              child: TextField(
                                decoration: const InputDecoration(
                                  hintText: 'HH:MM:SS',
                                  isDense: true,
                                  filled: true,
                                  fillColor: Colors.white10,
                                  border: OutlineInputBorder(),
                                ),
                                style: const TextStyle(color: Colors.white, fontSize: 12),
                                onChanged: (v) => setState(() => _timeToFilter = v),
                              ),
                            ),
                            const SizedBox(width: 6),
                            TextButton(
                              onPressed: () {
                                setState(() {
                                  _searchText = '';
                                  _statusFilter = '';
                                  _punchFilter = '';
                                  _timeFromFilter = '';
                                  _timeToFilter = '';
                                });
                              },
                              child: const Text('Xóa filter', style: TextStyle(color: Colors.amber)),
                            ),
                          ],
                        ),
                      ),
                    ),
                    // Records table
                    Expanded(
                      child: _records.isEmpty
                          ? const Center(
                              child: Text(
                                'Chưa có log. Bấm "LẤY LOG" để tải.',
                                style: TextStyle(color: Colors.white70),
                              ),
                            )
                          : ListView.builder(
                              itemCount: _filteredRecords().length,
                              itemBuilder: (context, i) {
                                final r = _filteredRecords()[i];
                                return ListTile(
                                  dense: true,
                                  leading: Text(
                                    r.deviceIp,
                                    style: const TextStyle(color: Colors.cyanAccent, fontSize: 11),
                                  ),
                                  title: Text(
                                    'NV ${r.userId}',
                                    style: const TextStyle(color: Colors.white, fontSize: 13),
                                  ),
                                  subtitle: Text(
                                    '${r.date} ${r.time}',
                                    style: const TextStyle(color: Colors.white60, fontSize: 11),
                                  ),
                                  trailing: Text(
                                    '${r.statusName}\n${r.punchName}',
                                    textAlign: TextAlign.right,
                                    style: const TextStyle(color: Colors.white70, fontSize: 11),
                                  ),
                                );
                              },
                            ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
