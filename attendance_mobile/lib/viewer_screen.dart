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
  // v1.5.6: Filter riêng cho danh sách thiết bị
  String _deviceSearchText = '';
  // v1.5.7: Toggle ẩn/hiện device panel để xem log full màn hình
  bool _showDevicePanel = true;

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

  // v1.5.6: Filter danh sách thiết bị theo search text
  List<Device> _filteredDevices() {
    if (_deviceSearchText.isEmpty) return _devices;
    final s = _deviceSearchText.toLowerCase();
    return _devices.where((d) =>
      d.ip.toLowerCase().contains(s) ||
      d.type.toLowerCase().contains(s)
    ).toList();
  }

  // v1.5.6: Chọn/bỏ chọn tất cả thiết bị attendance
  void _selectAllDevices() {
    setState(() {
      _selectedIps = _devices
          .where((d) => d.type == 'attendance')
          .map((d) => d.ip)
          .toSet();
    });
  }

  void _deselectAllDevices() {
    setState(() {
      _selectedIps = {};
    });
  }

  void _toggleAllDevices() {
    final attendanceIps = _devices
        .where((d) => d.type == 'attendance')
        .map((d) => d.ip)
        .toSet();
    final allSelected = _selectedIps.containsAll(attendanceIps) &&
        attendanceIps.isNotEmpty;
    if (allSelected) {
      _deselectAllDevices();
    } else {
      _selectAllDevices();
    }
  }

  @override
  Widget build(BuildContext context) {
    final isCustom = _dateRanges[_dateRangeIndex]['days'] == -1;
    return Column(
      children: [
        // Date range tabs + controls bar
        Container(
          padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
          color: const Color(0xFFE0F2F1),
          child: Column(
            children: [
              // Tab-style date range picker
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
              // Date display row (tappable if custom mode)
              Row(
                children: [
                  Expanded(
                    child: InkWell(
                      onTap: isCustom ? () => _pickCustomDate(isFrom: true) : null,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                            color: isCustom ? const Color(0xFF00897B) : const Color(0xFFB0BEC5),
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Từ ngày', style: TextStyle(color: Color(0xFF607D8B), fontSize: 10)),
                            Text(
                              _fromDate.isEmpty ? '...' : _fromDate,
                              style: const TextStyle(color: Color(0xFF263238), fontSize: 13, fontWeight: FontWeight.bold),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 4),
                    child: Icon(Icons.arrow_forward, color: Color(0xFF607D8B), size: 18),
                  ),
                  Expanded(
                    child: InkWell(
                      onTap: isCustom ? () => _pickCustomDate(isFrom: false) : null,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                            color: isCustom ? const Color(0xFF00897B) : const Color(0xFFB0BEC5),
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Đến ngày', style: TextStyle(color: Color(0xFF607D8B), fontSize: 10)),
                            Text(
                              _toDate.isEmpty ? '...' : _toDate,
                              style: const TextStyle(color: Color(0xFF263238), fontSize: 13, fontWeight: FontWeight.bold),
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
                      icon: const Icon(Icons.stop, size: 18, color: Colors.white),
                      label: const Text('DỪNG', style: TextStyle(color: Colors.white)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFFD32F2F),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      ),
                    )
                  else
                    ElevatedButton.icon(
                      onPressed: _startFetch,
                      icon: const Icon(Icons.refresh, size: 18, color: Colors.white),
                      label: const Text('LẤY LOG', style: TextStyle(color: Colors.white)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2E7D32),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      ),
                    ),
                  const SizedBox(width: 4),
                  IconButton(
                    icon: const Icon(Icons.settings, size: 20, color: Color(0xFF455A64)),
                    onPressed: widget.onSettings,
                    tooltip: 'Đổi IP server',
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
              ),
              if (_isRunning || _progress > 0)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: LinearProgressIndicator(
                    value: _progress,
                    backgroundColor: const Color(0xFFB2DFDB),
                    color: const Color(0xFF00897B),
                  ),
                ),
              if (_statusText.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    '$_statusText ($_progressCount/$_progressTotal)',
                    style: const TextStyle(color: Color(0xFF455A64), fontSize: 12, fontWeight: FontWeight.w500),
                  ),
                ),
            ],
          ),
        ),
        // Devices + Filters + Records
        Expanded(
          child: Row(
            children: [
              // Left: device list (an/hien theo toggle)
              if (_showDevicePanel) Container(
                width: 200,
                color: const Color(0xFFFAFAFA),
                child: Column(
                  children: [
                    // v1.5.6: Header có search + nút chọn tất cả/bỏ chọn
                    Container(
                      padding: const EdgeInsets.fromLTRB(8, 8, 8, 6),
                      decoration: const BoxDecoration(
                        color: Color(0xFF00695C),
                        border: Border(bottom: BorderSide(color: Color(0xFF004D40), width: 1)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Row(
                            children: [
                              Icon(Icons.devices, color: Colors.white, size: 16),
                              SizedBox(width: 6),
                              Text('THIẾT BỊ',
                                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
                            ],
                          ),
                          const SizedBox(height: 6),
                          // Search filter cho devices
                          TextField(
                            decoration: InputDecoration(
                              hintText: 'Tìm IP...',
                              isDense: true,
                              filled: true,
                              fillColor: Colors.white,
                              prefixIcon: const Icon(Icons.search, size: 16, color: Color(0xFF607D8B)),
                              suffixIcon: _deviceSearchText.isNotEmpty
                                ? IconButton(
                                    icon: const Icon(Icons.clear, size: 14, color: Color(0xFF607D8B)),
                                    onPressed: () => setState(() => _deviceSearchText = ''),
                                    padding: EdgeInsets.zero,
                                    constraints: const BoxConstraints(),
                                  )
                                : null,
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(4),
                                borderSide: BorderSide.none,
                              ),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                              hintStyle: const TextStyle(fontSize: 11),
                            ),
                            style: const TextStyle(color: Color(0xFF263238), fontSize: 12),
                            onChanged: (v) => setState(() => _deviceSearchText = v),
                          ),
                          const SizedBox(height: 4),
                          // Nút Chọn tất cả / Bỏ chọn
                          Row(
                            children: [
                              Expanded(
                                child: TextButton.icon(
                                  onPressed: _toggleAllDevices,
                                  icon: Icon(
                                    Icons.select_all,
                                    size: 14,
                                    color: Colors.white,
                                  ),
                                  label: Text(
                                    _selectedIps.length == _devices.where((d) => d.type == 'attendance').length && _devices.isNotEmpty
                                      ? 'Bỏ chọn'
                                      : 'Chọn tất cả',
                                    style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w600),
                                  ),
                                  style: TextButton.styleFrom(
                                    padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 0),
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
                            ],
                          ),
                        ],
                      ),
                    ),
                    Expanded(
                      child: _loading
                          ? const Center(child: CircularProgressIndicator(color: Color(0xFF00897B)))
                          : Builder(
                              builder: (context) {
                                final visible = _filteredDevices();
                                if (visible.isEmpty) {
                                  return Center(
                                    child: Padding(
                                      padding: const EdgeInsets.all(16),
                                      child: Text(
                                        _devices.isEmpty
                                          ? 'Chưa tải thiết bị'
                                          : 'Không tìm thấy thiết bị',
                                        style: const TextStyle(color: Color(0xFF607D8B), fontSize: 12),
                                        textAlign: TextAlign.center,
                                      ),
                                    ),
                                  );
                                }
                                return ListView(
                                  children: visible.map((d) {
                                    final selected = _selectedIps.contains(d.ip);
                                    return Container(
                                      decoration: BoxDecoration(
                                        color: selected ? const Color(0xFFB2DFDB) : Colors.transparent,
                                        border: const Border(
                                          bottom: BorderSide(color: Color(0xFFEEEEEE), width: 0.5),
                                        ),
                                      ),
                                      child: CheckboxListTile(
                                        dense: true,
                                        value: selected,
                                        controlAffinity: ListTileControlAffinity.leading,
                                        title: Text(d.ip,
                                            style: TextStyle(
                                              color: const Color(0xFF263238),
                                              fontSize: 12,
                                              fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                                              fontFamily: 'monospace',
                                            )),
                                        subtitle: Text(
                                          d.type == 'attendance' ? 'Chấm công' : (d.type == 'signing' ? 'Ký số' : d.type),
                                          style: const TextStyle(color: Color(0xFF607D8B), fontSize: 10),
                                        ),
                                        activeColor: const Color(0xFF00897B),
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
                                  }).toList(),
                                );
                              },
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
                      color: const Color(0xFFE0F2F1),
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: [
                            SizedBox(
                              width: 120,
                              child: TextField(
                                decoration: InputDecoration(
                                  hintText: 'Mã NV / IP',
                                  isDense: true,
                                  filled: true,
                                  fillColor: Colors.white,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(4),
                                    borderSide: const BorderSide(color: Color(0xFFB0BEC5)),
                                  ),
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                                ),
                                style: const TextStyle(color: Color(0xFF263238), fontSize: 12),
                                onChanged: (v) => setState(() => _searchText = v),
                              ),
                            ),
                            const SizedBox(width: 6),
                            DropdownButton<String>(
                              value: _statusFilter.isEmpty ? null : _statusFilter,
                              hint: const Text('Trạng thái', style: TextStyle(color: Color(0xFF455A64))),
                              dropdownColor: Colors.white,
                              style: const TextStyle(color: Color(0xFF263238)),
                              underline: Container(height: 1, color: const Color(0xFFB0BEC5)),
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
                              hint: const Text('Punch', style: TextStyle(color: Color(0xFF455A64))),
                              dropdownColor: Colors.white,
                              style: const TextStyle(color: Color(0xFF263238)),
                              underline: Container(height: 1, color: const Color(0xFFB0BEC5)),
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
                                decoration: InputDecoration(
                                  hintText: 'HH:MM:SS',
                                  isDense: true,
                                  filled: true,
                                  fillColor: Colors.white,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                                ),
                                style: const TextStyle(color: Color(0xFF263238), fontSize: 12),
                                onChanged: (v) => setState(() => _timeFromFilter = v),
                              ),
                            ),
                            const Text(' - ', style: TextStyle(color: Color(0xFF455A64))),
                            SizedBox(
                              width: 80,
                              child: TextField(
                                decoration: InputDecoration(
                                  hintText: 'HH:MM:SS',
                                  isDense: true,
                                  filled: true,
                                  fillColor: Colors.white,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                                ),
                                style: const TextStyle(color: Color(0xFF263238), fontSize: 12),
                                onChanged: (v) => setState(() => _timeToFilter = v),
                              ),
                            ),
                            const SizedBox(width: 6),
                            TextButton.icon(
                              onPressed: () {
                                setState(() {
                                  _searchText = '';
                                  _statusFilter = '';
                                  _punchFilter = '';
                                  _timeFromFilter = '';
                                  _timeToFilter = '';
                                });
                              },
                              icon: const Icon(Icons.clear, size: 16, color: Color(0xFFD84315)),
                              label: const Text('Xóa filter', style: TextStyle(color: Color(0xFFD84315))),
                            ),
                          ],
                        ),
                      ),
                    ),
                    // Records table - horizontal scroll enabled
                    Expanded(
                      child: _records.isEmpty
                          ? const Center(
                              child: Text(
                                'Chưa có log. Bấm "LẤY LOG" để tải.',
                                style: TextStyle(color: Color(0xFF607D8B), fontSize: 14),
                              ),
                            )
                          : _buildRecordsTable(),
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

  // Bang log voi horizontal scroll - cuon trai/phai de xem full
  Widget _buildRecordsTable() {
    final records = _filteredRecords();
    return Column(
      children: [
        // v1.5.7: Hint bar - vuốt trái để xem chi tiết + nút toggle ẩn/hiện device panel
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          color: const Color(0xFFE0F2F1),
          child: Row(
            children: [
              const Icon(Icons.swap_horiz, size: 14, color: Color(0xFF00695C)),
              const SizedBox(width: 6),
              Text(
                'Vuốt trái để xem chi tiết (${records.length} bản ghi)',
                style: const TextStyle(color: Color(0xFF00695C), fontSize: 11, fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              IconButton(
                icon: Icon(
                  _showDevicePanel ? Icons.fullscreen_exit : Icons.fullscreen,
                  size: 18,
                  color: const Color(0xFF00695C),
                ),
                tooltip: _showDevicePanel ? 'Ẩn danh sách thiết bị (xem log full)' : 'Hiện danh sách thiết bị',
                onPressed: () => setState(() => _showDevicePanel = !_showDevicePanel),
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
              const SizedBox(width: 6),
              const Icon(Icons.swipe_left, size: 14, color: Color(0xFF607D8B)),
            ],
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            scrollDirection: Axis.vertical,
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                headingRowHeight: 38,
                dataRowMinHeight: 36,
                dataRowMaxHeight: 42,
                columnSpacing: 22,
                headingTextStyle: const TextStyle(
                  color: Color(0xFF00695C),
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                ),
                dataTextStyle: const TextStyle(
                  color: Color(0xFF263238),
                  fontSize: 12,
                ),
                headingRowColor: WidgetStateProperty.all(const Color(0xFFB2DFDB)),
                border: TableBorder(
                  horizontalInside: BorderSide(color: Colors.grey.shade300, width: 0.5),
                  verticalInside: BorderSide(color: Colors.grey.shade300, width: 0.5),
                  top: const BorderSide(color: Color(0xFFB0BEC5), width: 1),
                  bottom: const BorderSide(color: Color(0xFFB0BEC5), width: 1),
                  left: const BorderSide(color: Color(0xFFB0BEC5), width: 1),
                  right: const BorderSide(color: Color(0xFFB0BEC5), width: 1),
                ),
                columns: const [
                  DataColumn(label: Text('#'), numeric: true),
                  DataColumn(label: Text('Thời gian')),
                  DataColumn(label: Text('Mã NV')),
                  DataColumn(label: Text('Máy (IP)')),
                  DataColumn(label: Text('Trạng thái')),
                  DataColumn(label: Text('Punch')),
                  DataColumn(label: Text('Ghi chú')),
                ],
                rows: List.generate(records.length, (i) {
                  final r = records[i];
                  final statusColor = _getStatusColor(r.status.toString());
                  return DataRow(
                    color: WidgetStateProperty.all(
                      i.isEven ? Colors.white : const Color(0xFFF5F7FA),
                    ),
                    cells: [
                      DataCell(Text('${i + 1}',
                          style: const TextStyle(color: Color(0xFF607D8B)))),
                      DataCell(Text('${r.date}\n${r.time}',
                          style: const TextStyle(fontFamily: 'monospace', fontSize: 11))),
                      DataCell(Text('NV ${r.userId}',
                          style: const TextStyle(
                              fontWeight: FontWeight.bold, color: Color(0xFF00695C)))),
                      DataCell(Text(r.deviceIp,
                          style: const TextStyle(fontFamily: 'monospace', fontSize: 11))),
                      DataCell(Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: statusColor.withOpacity(0.18),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: statusColor, width: 1),
                        ),
                        child: Text(r.statusName,
                            style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.w600)),
                      )),
                      DataCell(Text(r.punchName,
                          style: const TextStyle(color: Color(0xFF455A64)))),
                      DataCell(Text(r.timestamp,
                          style: const TextStyle(color: Color(0xFF607D8B), fontSize: 10, fontFamily: 'monospace'),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis)),
                    ],
                  );
                }),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case '0': return const Color(0xFF2E7D32); // Check-In green
      case '1': return const Color(0xFFC62828); // Check-Out red
      case '2': return const Color(0xFFEF6C00); // Break-Out orange
      case '3': return const Color(0xFF1976D2); // Break-In blue
      case '4': return const Color(0xFF7B1FA2); // OT-In purple
      case '5': return const Color(0xFFD84315); // OT-Out deep orange
      default: return const Color(0xFF455A64);
    }
  }
}
