// AttendanceSuite v2.6.1 - Native Flutter UI + Python backend (Chaquopy) + Sophos VPN

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
  final PcApi _api = PcApi('http://127.0.0.1:8080');

  late final List<Widget> _tabs;
  late final List<_TabInfo> _tabInfo;

  // Reference tới LogScreen state để LogBottomBar có thể gọi selectAll/getLogs
  LogScreenState? _logState;

  @override
  void initState() {
    super.initState();
    _tabs = [
      LogScreen(
        api: _api,
        onStateReady: (state) => _logState = state,
      ),
      ToolsScreen(api: _api),
      NetworkScreen(api: _api),
      SettingsScreen(
        api: _api,
        onThemeChanged: (isDark) {
          widget.onThemeModeChanged(isDark ? 'dark' : 'light');
        },
      ),
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
    final isLogTab = _index == 0;
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          _TopBar(title: _tabInfo[_index].label, subtitle: _tabInfo[_index].desc),
          Expanded(
            child: IndexedStack(index: _index, children: _tabs),
          ),
          if (isLogTab && _logState != null)
            LogBottomBar(parent: _logState!),
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
