// AttendanceSuite v2.6.3 - Native Flutter UI + Python backend (Chaquopy) + Sophos VPN
// v2.6.3: Them tab Live Device Status + About dialog

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'screens/log_screen.dart';
import 'screens/live_screen.dart';
import 'screens/lan_scan_screen.dart';
import 'screens/tools_screen.dart';
import 'screens/network_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/endpoints_screen.dart';
import 'api/pc_api.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final themeMode = prefs.getString('theme_mode') ?? 'dark';
  final initialDark = themeMode == 'dark' || themeMode == 'system';
  runApp(AttendanceApp(
    themeModePref: themeMode,
    initialDark: initialDark,
  ));
}

class AttendanceApp extends StatefulWidget {
  final String themeModePref;
  final bool initialDark;
  const AttendanceApp({super.key, required this.themeModePref, required this.initialDark});

  @override
  State<AttendanceApp> createState() => _AttendanceAppState();
}

class _AttendanceAppState extends State<AttendanceApp> {
  late String _themeModePref;

  @override
  void initState() {
    super.initState();
    _themeModePref = widget.themeModePref;
  }

  void _setThemeMode(String v) {
    setState(() => _themeModePref = v);
  }

  ThemeMode get _mode {
    switch (_themeModePref) {
      case 'light': return ThemeMode.light;
      case 'dark': return ThemeMode.dark;
      case 'system':
      default: return ThemeMode.system;
    }
  }

  @override
  Widget build(BuildContext context) {
    const seed = Color(0xFF00897B);
    return MaterialApp(
      title: 'AttendanceSuite',
      debugShowCheckedModeBanner: false,
      themeMode: _mode,
      theme: ThemeData.light(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.fromSeed(seedColor: seed, brightness: Brightness.light),
      ),
      darkTheme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: const Color(0xFF1F262A),
        cardColor: const Color(0xFF37474F),
        colorScheme: ColorScheme.fromSeed(
          seedColor: seed,
          brightness: Brightness.dark,
        ),
        textTheme: const TextTheme(
          bodyLarge: TextStyle(color: Colors.white),
          bodyMedium: TextStyle(color: Colors.white),
          bodySmall: TextStyle(color: Colors.white70),
          titleLarge: TextStyle(color: Colors.white),
          titleMedium: TextStyle(color: Colors.white),
          titleSmall: TextStyle(color: Colors.white),
        ),
      ),
      home: HomeScreen(
        onThemeModeChanged: _setThemeMode,
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  final ValueChanged<String> onThemeModeChanged;
  const HomeScreen({super.key, required this.onThemeModeChanged});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;
  // v2.6.8: Default backend = CCDK-M6 BV (172.16.200.105)
  // URL doc tu SharedPreferences 'server_url' neu co, fallback default
  // User co the doi trong Settings (real-time, khong can restart app)
  String _serverUrl = 'http://172.16.200.105:8080';
  final PcApi _api = PcApi('http://172.16.200.105:8080');

  @override
  void initState() {
    super.initState();
    _loadServerUrl();
    _buildTabs();
  }

  Future<void> _loadServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString('server_url');
    if (saved != null && saved.isNotEmpty) {
      setState(() {
        _serverUrl = saved;
        _api.baseUrl = saved;
      });
    }
  }

  void _onServerUrlChanged(String newUrl) {
    setState(() {
      _serverUrl = newUrl;
      _api.baseUrl = newUrl;
    });
    // Rebuild tabs de moi screen dung instance moi
    _buildTabs();
  }

  List<Widget> _tabs = [];
  List<_TabInfo> _tabInfo = const [];

  void _buildTabs() {
    _tabs = [
      LogScreen(
        api: _api,
        onStateReady: (state) => _logState = state,
      ),
      LiveScreen(api: _api),
      LanScanScreen(),
      ToolsScreen(api: _api),
      EndpointsScreen(api: _api),
      NetworkScreen(api: _api),
      SettingsScreen(
        api: _api,
        currentServerUrl: _serverUrl,
        onServerUrlChanged: _onServerUrlChanged,
        onThemeChanged: (isDark) {
          widget.onThemeModeChanged(isDark ? 'dark' : 'light');
        },
      ),
    ];
    _tabInfo = const [
      _TabInfo('Log', Icons.receipt_long, 'Đọc log chấm công'),
      _TabInfo('Live', Icons.sensors, 'Live Device Status'),
      _TabInfo('LAN', Icons.wifi_tethering, 'Quét LAN trực tiếp'),
      _TabInfo('Tools', Icons.bolt, 'ATTLOG + ZK Tools'),
      _TabInfo('API', Icons.api, 'All Endpoints (v2.6.11)'),
      _TabInfo('Mạng', Icons.network_check, 'Network + VPN'),
      _TabInfo('Cài đặt', Icons.settings, 'Settings'),
    ];
  }

  // Reference tới LogScreen state để LogBottomBar có thể gọi selectAll/getLogs
  LogScreenState? _logState;

  void _showAboutDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF263238),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        title: Row(children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFF26A69A).withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(Icons.info_outline, color: Color(0xFF26A69A), size: 24),
          ),
          const SizedBox(width: 10),
          const Expanded(
            child: Text('Giới thiệu AttendanceSuite',
                style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
          ),
        ]),
        content: SingleChildScrollView(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            const SizedBox(height: 4),
            const _AboutKv('Phiên bản', '2.7.4+47'),
            const _AboutKv('Ngày phát hành', '2026-09-24'),
            const _AboutKv('Tác giả', 'Dr. Nểm (Bác sĩ Cấp Cứu - BVĐK Ninh Thuận)'),
            const _AboutKv('Bản quyền', '© 2026 BVĐK Ninh Thuận'),
            const Divider(color: Color(0xFF455A64), height: 24),
            const Text('📋 Tính năng (v2.7.4+47):',
                style: TextStyle(color: Color(0xFF26A69A), fontSize: 12, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            const Text(
              '• Đọc log chấm công từ 27 máy X628 PRO\n'
              '• Live Status (ping/latency 30 thiết bị)\n'
              '• LAN scan trực tiếp (BV WiFi only)\n'
              '• ATTLOG Tools + ZK Tools (info/attlog/test PIN/reboot)\n'
              '• Inject ATTLOG qua CVE-2023-3941 + Jobs monitor\n'
              '• Quick Actions: Security Scan / Merge / Alerts / Backup / Reports\n'
              '• Tab API: index 37 endpoints với Test JSON + Copy curl\n'
              '• VPN Sophos BV Ninh Thuận (native)\n'
              '• Manual ATTLOG entry (không cần máy thật)\n'
              '• Configurable Server URL (default CCDK-M6 BV)\n'
              '• Auto-detect backend với quick switch 3 URLs (banner)',
              style: TextStyle(color: Colors.white70, fontSize: 11, height: 1.4),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.orange.shade900.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: Colors.orange.shade700, width: 0.5),
              ),
              child: const Text(
                '⚠️ Cảnh báo bảo mật:\n'
                'Module ATTLOG Tools khai thác CVE-2023-3941 (UPLOAD_PICTURE path traversal)\n'
                'và CVE-2023-4587 (unauth backup download) trên ZK X628 PRO FW 6.60.\n'
                'Chỉ sử dụng trên thiết bị thuộc sở hữu của BVĐK Ninh Thuận.',
                style: TextStyle(color: Color(0xFFFFE082), fontSize: 10, height: 1.4),
              ),
            ),
            const SizedBox(height: 12),
            const Text('🌐 Server URLs:',
                style: TextStyle(color: Color(0xFF26A69A), fontSize: 12, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            const Text(
              'http://172.16.200.105:8080 (CCDK-M6 BV - default)\n'
              'http://172.16.200.101:8080 (CCDK-M10 BV - backup)\n'
              'http://171.15.0.2:8080 (Sophos tunnel)\n'
              'http://172.16.0.254:20250 (LAN gateway)',
              style: TextStyle(color: Colors.white54, fontSize: 10, fontFamily: 'monospace'),
            ),
          ]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Đóng', style: TextStyle(color: Color(0xFF26A69A))),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isLogTab = _index == 0;
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          _TopBar(
            title: _tabInfo[_index].label,
            subtitle: _tabInfo[_index].desc,
            onAboutTap: _showAboutDialog,
          ),
          Expanded(
            child: IndexedStack(index: _index, children: _tabs),
          ),
          if (isLogTab && _logState != null) LogBottomBar(parent: _logState!),
        ]),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        backgroundColor: const Color(0xFF263238),
        indicatorColor: const Color(0xFF26A69A).withValues(alpha: 0.3),
        labelBehavior: NavigationDestinationLabelBehavior.onlyShowSelected,
        destinations: _tabInfo
            .map((t) => NavigationDestination(
                  icon: Icon(t.icon),
                  selectedIcon: Icon(t.icon, color: const Color(0xFF26A69A)),
                  label: t.label,
                ))
            .toList(),
      ),
    );
  }
}

class _TabInfo {
  final String label;
  final IconData icon;
  final String desc;
  const _TabInfo(this.label, this.icon, this.desc);
}

class _AboutKv extends StatelessWidget {
  const _AboutKv(this.k, this.v);
  final String k;
  final String v;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: 110, child: Text('$k:', style: const TextStyle(fontSize: 11, color: Colors.white60))),
        Expanded(child: Text(v, style: const TextStyle(fontSize: 11, color: Colors.white))),
      ]),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.title, required this.subtitle, this.onAboutTap});
  final String title;
  final String subtitle;
  final VoidCallback? onAboutTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: const BoxDecoration(
        color: Color(0xFF00897B),
        boxShadow: [
          BoxShadow(color: Colors.black26, blurRadius: 4, offset: Offset(0, 2)),
        ],
      ),
      child: Row(children: [
        const Icon(Icons.fingerprint, color: Colors.white, size: 20),
        const SizedBox(width: 8),
        const Text('AttendanceSuite',
            style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(width: 4),
        const Text('v2.6',
            style: TextStyle(color: Colors.white70, fontSize: 11)),
        const Spacer(),
        Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
          Text(title,
              style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
          Text(subtitle,
              style: const TextStyle(color: Colors.white70, fontSize: 10)),
        ]),
        if (onAboutTap != null) ...[
          const SizedBox(width: 6),
          IconButton(
            icon: const Icon(Icons.info_outline, color: Colors.white, size: 20),
            onPressed: onAboutTap,
            tooltip: 'Giới thiệu',
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
          ),
        ],
      ]),
    );
  }
}
