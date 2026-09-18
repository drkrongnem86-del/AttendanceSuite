// AttendanceSuite - Mobile app for BVĐK Ninh Thuận
// Self-contained: includes embedded HTTP server + VPN + ZK client

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:network_info_plus/network_info_plus.dart';
import 'screens/log_screen.dart';
import 'screens/x628_screen.dart';
import 'screens/remote_punch_screen.dart';
import 'screens/pin_pwd_screen.dart';
import 'screens/security_screen.dart';
import 'screens/settings_screen.dart';
import 'vpn/vpn_manager.dart';
import 'server/embedded_server.dart';

void main() {
  runApp(const AttendanceApp());
}

/// Global app state (singleton-ish - kept on app root)
class AppState extends ChangeNotifier {
  // Embedded server
  EmbeddedServer server = EmbeddedServer(port: 8080);
  bool serverRunning = false;
  String serverUrl = '';
  String localIp = '127.0.0.1';
  int serverPort = 8080;
  // List of all accessible IPs (wifi + VPN tunnels + others)
  List<String> accessibleIps = [];

  // VPN
  VpnManager vpn = VpnManager();
  bool vpnReady = false;
  String? vpnError;

  /// Best IP to show in status (prefers VPN tunnel IPs since user wants LAN/VPN access)
  String get displayIp {
    if (accessibleIps.isEmpty) return localIp;
    // Prefer non-127, non-loopback, prefer 172.x or 10.x (typical VPN ranges)
    for (final ip in accessibleIps) {
      if (ip.startsWith('172.') || ip.startsWith('10.')) return ip;
    }
    return accessibleIps.first;
  }

  /// Display URL (LAN-accessible, NOT localhost)
  String get displayUrl => 'http://$displayIp:$serverPort';

  /// All accessible URLs
  List<String> get accessibleUrls =>
      accessibleIps.map((ip) => 'http://$ip:$serverPort').toList();

  Future<void> init() async {
    // Load settings
    final prefs = await SharedPreferences.getInstance();
    final savedPort = prefs.getInt('server_port') ?? 8080;
    serverPort = savedPort;

    // Try starting embedded server
    server = EmbeddedServer(port: serverPort);
    try {
      await server.start();
      serverRunning = true;
      // CRITICAL: read actual port from server (might differ if fallback to ephemeral)
      final actualPort = server.serverPort;
      if (actualPort > 0) serverPort = actualPort;
      serverUrl = 'http://127.0.0.1:$serverPort';
    } catch (e) {
      // Fallback: ephemeral port
      try {
        server = EmbeddedServer(port: 0);
        await server.start();
        serverRunning = true;
        final actualPort = server.serverPort;
        if (actualPort > 0) serverPort = actualPort;
        serverUrl = 'http://127.0.0.1:$serverPort';
      } catch (e2) {
        serverRunning = false;
        vpnError = 'Server start failed: $e2';
      }
    }

    // Discover ALL network interfaces (wifi, mobile, VPN tunnels)
    await _discoverIps();

    // Init VPN
    try {
      vpn.onStatusChanged = () {
        // Re-discover IPs when VPN connects/disconnects (tunnel interface appears)
        _discoverIps().then((_) => notifyListeners());
      };
      await vpn.init();
      vpnReady = true;
    } catch (e) {
      vpnReady = false;
    }

    notifyListeners();
  }

  Future<void> _discoverIps() async {
    final ips = <String>[];
    try {
      final networkInfo = NetworkInfo();
      final wifiIP = await networkInfo.getWifiIP();
      if (wifiIP != null && wifiIP.isNotEmpty) {
        ips.add(wifiIP);
      }
    } catch (_) {}
    // Also scan NetworkInterface for VPN interfaces
    try {
      final interfaces = await NetworkInterface.list();
      for (final iface in interfaces) {
        for (final addr in iface.addresses) {
          if (addr.type == InternetAddressType.IPv4 &&
              !addr.address.startsWith('127.') &&
              !ips.contains(addr.address)) {
            ips.add(addr.address);
          }
        }
      }
    } catch (_) {}
    accessibleIps = ips;
    if (ips.isNotEmpty) {
      localIp = displayIp;
      serverUrl = displayUrl;
    }
  }

  Future<void> restartServer() async {
    try {
      await server.stop();
      server = EmbeddedServer(port: serverPort);
      await server.start();
      serverRunning = true;
      await _discoverIps();
      serverUrl = displayUrl;
      notifyListeners();
    } catch (e) {
      vpnError = 'Restart failed: $e';
      notifyListeners();
    }
  }
}

class AttendanceApp extends StatefulWidget {
  const AttendanceApp({super.key});
  @override
  State<AttendanceApp> createState() => _AttendanceAppState();
}

class _AttendanceAppState extends State<AttendanceApp> {
  late final AppState _state;
  
  @override
  void initState() {
    super.initState();
    _state = AppState();
    _state.init().then((_) {
      if (mounted) setState(() {});
    });
  }
  
  @override
  Widget build(BuildContext context) {
    return _AppStateInherited(state: _state, child: MaterialApp(
      title: 'AttendanceSuite',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.light,
        primaryColor: const Color(0xFF00695C),
        scaffoldBackgroundColor: const Color(0xFFF5F7FA),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF00897B),
          brightness: Brightness.light,
        ).copyWith(
          primary: const Color(0xFF00695C),
          secondary: const Color(0xFF26A69A),
          surface: Colors.white,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF00695C),
          foregroundColor: Colors.white,
          elevation: 2,
        ),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    ));
  }
}

class _AppStateInherited extends InheritedNotifier<AppState> {
  final AppState state;
  const _AppStateInherited({required this.state, required Widget child}) : super(notifier: state, child: child);
  
  static _AppStateInherited of(BuildContext context) {
    final w = context.dependOnInheritedWidgetOfExactType<_AppStateInherited>();
    if (w == null) throw Exception('No AppStateInherited found in context');
    return w;
  }
}

/// Helper to read app state in any widget
extension AppStateContext on BuildContext {
  AppState get appState => _AppStateInherited.of(this).state;
  int get homeTabIndex {
    final h = findAncestorStateOfType<_HomeScreenState>();
    return h?._tabIndex ?? 0;
  }
  void setHomeTab(int i) {
    final h = findAncestorStateOfType<_HomeScreenState>();
    h?.setState(() => h._tabIndex = i);
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _tabIndex = 0;
  
  static const _tabs = <Widget>[
    LogScreen(),
    X628Screen(),
    RemotePunchScreen(),
    PinPwdScreen(),
    SecurityScreen(),
    SettingsScreen(),
  ];
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            const _TopBar(),
            Expanded(child: IndexedStack(index: _tabIndex, children: _tabs)),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tabIndex,
        onDestinationSelected: (i) => setState(() => _tabIndex = i),
        height: 64,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.receipt_long), label: 'Log'),
          NavigationDestination(icon: Icon(Icons.fingerprint), label: 'X628'),
          NavigationDestination(icon: Icon(Icons.cloud_upload), label: 'Từ xa'),
          NavigationDestination(icon: Icon(Icons.lock), label: 'PIN+PWD'),
          NavigationDestination(icon: Icon(Icons.security), label: 'Bảo mật'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Cài đặt'),
        ],
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar();

  void _showConnStatus(BuildContext context) {
    final state = context.appState;
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(children: [
          Icon(Icons.wifi_tethering, color: Colors.green),
          SizedBox(width: 8),
          Text('Trạng thái kết nối'),
        ]),
        content: StatefulBuilder(builder: (ctx, setSt) {
          final vpn = state.vpn.status;
          return SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _row('Server:', state.serverRunning ? '✅ Đang chạy' : '❌ Chưa chạy'),
                _row('Display URL:', state.displayUrl, color: Colors.greenAccent),
                _row('Local IP:', state.localIp),
                _row('Port:', '${state.serverPort}'),
                if (state.accessibleIps.isNotEmpty)
                  _row('Tất cả IP:', state.accessibleIps.join('\n')),
                _row('VPN:', vpn.connected ? '🟢 Đã kết nối' : '🔴 Chưa kết nối'),
                _row('Devices:', '${state.server.devices.length}'),
                _row('Embedded:', state.serverRunning ? 'YES (in-app)' : 'NO'),
                if (vpn.lastError != null) _row('VPN Err:', vpn.lastError!, color: Colors.red),
                if (state.vpnError != null) _row('Last err:', state.vpnError!, color: Colors.red),
                const Divider(),
                const Text(
                  '💡 Copy URL ở trên để truy cập từ thiết bị khác.\n'
                  'Server chạy ngay trong app, không cần Windows.\n'
                  'VPN Sophos: user=nemk, pass=Cnttbvnt@321 → 113.176.81.193:8443',
                  style: TextStyle(fontSize: 11, color: Colors.white70),
                ),
              ],
            ),
          );
        }),
        actions: [
          TextButton(
            onPressed: () async {
              await state.restartServer();
              if (ctx.mounted) {
                Navigator.pop(ctx);
                _showConnStatus(context);
              }
            },
            child: const Text('Refresh IPs'),
          ),
          TextButton(
            onPressed: () async {
              await state.restartServer();
              if (ctx.mounted) Navigator.pop(ctx);
            },
            child: const Text('Restart Server'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Đóng'),
          ),
        ],
      ),
    );
  }

  Widget _row(String k, String v, {Color? color}) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(width: 110, child: Text(k, style: const TextStyle(color: Colors.white60, fontSize: 12))),
      Expanded(child: Text(v, style: TextStyle(color: color ?? Colors.white, fontSize: 12, fontWeight: FontWeight.w500))),
    ]),
  );

  Future<void> _toggleVpn(BuildContext context) async {
    final state = context.appState;
    final vpn = state.vpn;
    if (vpn.status.connected) {
      await vpn.disconnect();
    } else {
      final ok = await vpn.connectDefault();
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ok
              ? '⏳ Đang kết nối VPN Sophos (user=nemk)...'
              : '❌ VPN lỗi: ${vpn.status.lastError ?? "xem trạng thái"}'),
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.appState;
    final vpnConnected = state.vpn.status.connected;

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF00695C),
        border: Border(bottom: BorderSide(color: Color(0xFF004D40), width: 1)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Row 1: title + ON/OFF chip
          Row(children: [
            const Icon(Icons.medical_services, color: Colors.white, size: 18),
            const SizedBox(width: 4),
            Expanded(
              child: Text('AttendanceSuite v${state.server.version}',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: state.serverRunning ? Colors.greenAccent : Colors.redAccent,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                state.serverRunning ? 'ON' : 'OFF',
                style: const TextStyle(color: Colors.black87, fontSize: 10, fontWeight: FontWeight.bold),
              ),
            ),
          ]),
          // Row 2: server URL (full width, tappable for details)
          InkWell(
            onTap: () => _showConnStatus(context),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(children: [
                const Icon(Icons.cloud, color: Colors.white70, size: 14),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    state.serverUrl.isEmpty ? 'Server: chưa khởi động' : state.displayUrl,
                    style: TextStyle(
                      color: state.serverRunning ? Colors.white : Colors.white60,
                      fontSize: 11,
                      fontWeight: FontWeight.w500,
                    ),
                    maxLines: 1, overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (state.accessibleIps.length > 1) ...[
                  const SizedBox(width: 4),
                  Text(
                    '(${state.accessibleIps.length} IP)',
                    style: const TextStyle(color: Colors.white54, fontSize: 9),
                  ),
                ],
              ]),
            ),
          ),
          // Row 3: action icons - consolidated (4 buttons + popup menu)
          Row(children: [
            _miniBtn(Icons.refresh, 'Restart', () => context.appState.restartServer()),
            _miniBtn(
              vpnConnected ? Icons.vpn_lock : Icons.vpn_key,
              vpnConnected ? 'Ngắt VPN' : 'Kết nối VPN Sophos',
              () => _toggleVpn(context),
              color: vpnConnected ? Colors.greenAccent : Colors.orangeAccent,
            ),
            _miniBtn(Icons.info_outline, 'Trạng thái',
              () => _showConnStatus(context),
              color: Colors.white70),
            // Popup menu for less-frequent actions
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert, color: Colors.white, size: 18),
              tooltip: 'Thêm',
              color: const Color(0xFF263238),
              onSelected: (v) async {
                switch (v) {
                  case 'refresh_ips':
                    await state._discoverIps();
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Đã refresh IP'), duration: Duration(seconds: 1)),
                      );
                    }
                    break;
                  case 'restart':
                    await state.restartServer();
                    break;
                  case 'vpn_settings':
                    context.setHomeTab(5);
                    break;
                  case 'exit':
                    try { await state.server.stop(); } catch (_) {}
                    await SystemNavigator.pop();
                    break;
                }
              },
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'refresh_ips', child: Text('🔄 Refresh IPs', style: TextStyle(color: Colors.white))),
                PopupMenuItem(value: 'restart', child: Text('♻️ Restart Server', style: TextStyle(color: Colors.white))),
                PopupMenuItem(value: 'vpn_settings', child: Text('⚙️ VPN Settings', style: TextStyle(color: Colors.white))),
                PopupMenuDivider(),
                PopupMenuItem(value: 'exit', child: Text('⏻ Thoát ứng dụng', style: TextStyle(color: Colors.redAccent))),
              ],
            ),
            const Spacer(),
            _miniBtn(Icons.power_settings_new, 'Thoát', () async {
              try { await context.appState.server.stop(); } catch (_) {}
              await SystemNavigator.pop();
            }, color: Colors.redAccent),
          ]),
        ],
      ),
    );
  }

  Widget _miniBtn(IconData icon, String tooltip, VoidCallback onTap, {Color? color}) {
    return IconButton(
      icon: Icon(icon, color: color ?? Colors.white, size: 18),
      tooltip: tooltip,
      onPressed: onTap,
      padding: const EdgeInsets.all(2),
      constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
    );
  }
}
