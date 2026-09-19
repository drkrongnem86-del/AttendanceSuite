// AttendanceSuite v2.6.0 - Native Flutter UI + Python backend (Chaquopy)
//
// Architecture:
//   APK contains:
//     - Python runtime (Chaquopy) at localhost:8080
//     - attendance_web.py (Python web server with all ZK endpoints)
//     - pyzk (ZK device protocol, pure Python)
//     - Native Flutter UI (this file) with BottomNavigationBar
//
// Flow:
//   1. MainActivity.kt starts Python web server in background
//   2. Flutter UI (this app) calls http://127.0.0.1:8080/api/...
//   3. Python does ZK protocol against 172.16.x.x:4370 devices
//   4. Results shown in Flutter UI

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'screens/log_screen.dart';
import 'screens/tools_screen.dart';
import 'screens/network_screen.dart';
import 'screens/settings_screen.dart';
import 'api/pc_api.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final darkMode = prefs.getBool('dark_mode') ?? true;
  runApp(AttendanceApp(darkMode: darkMode));
}

class AttendanceApp extends StatefulWidget {
  final bool darkMode;
  const AttendanceApp({super.key, required this.darkMode});

  @override
  State<AttendanceApp> createState() => _AttendanceAppState();
}

class _AttendanceAppState extends State<AttendanceApp> {
  late bool _darkMode;

  @override
  void initState() {
    super.initState();
    _darkMode = widget.darkMode;
  }

  void _setDarkMode(bool v) => setState(() => _darkMode = v);

  @override
  Widget build(BuildContext context) {
    // Theme khớp PC EXE (dark by default, teal accent)
    const seed = Color(0xFF00897B);
    return MaterialApp(
      title: 'AttendanceSuite',
      debugShowCheckedModeBanner: false,
      themeMode: _darkMode ? ThemeMode.dark : ThemeMode.light,
      theme: ThemeData.light(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.fromSeed(seedColor: seed, brightness: Brightness.light),
      ),
      darkTheme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: const Color(0xFF1F262A),  // PC EXE bg color
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
      home: HomeScreen(onThemeChanged: _setDarkMode),
    );
  }
}

class HomeScreen extends StatefulWidget {
  final ValueChanged<bool> onThemeChanged;
  const HomeScreen({super.key, required this.onThemeChanged});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;
  final PcApi _api = PcApi('http://127.0.0.1:8080');

  late final List<Widget> _tabs;
  late final List<_TabInfo> _tabInfo;

  @override
  void initState() {
    super.initState();
    _tabs = [
      LogScreen(api: _api),
      ToolsScreen(api: _api),
      NetworkScreen(api: _api),
      SettingsScreen(api: _api, onThemeChanged: widget.onThemeChanged),
    ];
    _tabInfo = const [
      _TabInfo('Log', Icons.receipt_long, 'Đọc log chấm công'),
      _TabInfo('Tools', Icons.bolt, 'ATTLOG Tools'),
      _TabInfo('Mạng', Icons.network_check, 'Network + VPN'),
      _TabInfo('Cài đặt', Icons.settings, 'Settings'),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          // Compact title bar showing current tab
          _TopBar(title: _tabInfo[_index].label, subtitle: _tabInfo[_index].desc),
          Expanded(
            child: IndexedStack(index: _index, children: _tabs),
          ),
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

class _TopBar extends StatelessWidget {
  const _TopBar({required this.title, required this.subtitle});
  final String title;
  final String subtitle;

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
      ]),
    );
  }
}
