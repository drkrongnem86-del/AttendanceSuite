// AttendanceSuite - Mobile app for BVĐK Ninh Thuan
// Connects to the Python backend on the LAN
// v1.5.6: Thêm nút Thoát app + VPN Bệnh viện (cạnh Diagnostic)
import 'dart:io' show exit;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show SystemNavigator;
import 'api.dart';
import 'settings.dart';
import 'viewer_screen.dart';
import 'simulator_screen.dart';
import 'remote_punch_screen.dart';
import 'settings_screen.dart';
import 'presentation/screens/vpn_screen.dart';
import 'core/services/vpn_benh_vien_service.dart';

void main() {
  runApp(const AttendanceApp());
}

class AttendanceApp extends StatelessWidget {
  const AttendanceApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AttendanceSuite',
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.light,
        primaryColor: const Color(0xFF00695C),       // teal 800
        scaffoldBackgroundColor: const Color(0xFFF5F7FA),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF00897B),       // teal 600
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
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF00897B),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
            textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          ),
        ),
        bottomNavigationBarTheme: const BottomNavigationBarThemeData(
          backgroundColor: Colors.white,
          selectedItemColor: Color(0xFF00695C),
          unselectedItemColor: Color(0xFF607D8B),
          selectedLabelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          unselectedLabelStyle: TextStyle(fontSize: 11),
        ),
        cardTheme: CardThemeData(
          color: Colors.white,
          elevation: 1.5,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: const BorderSide(color: Color(0xFFE0E0E0), width: 0.5),
          ),
        ),
        dividerColor: const Color(0xFFE0E0E0),
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _serverIp = Settings.defaultServerIp;
  bool _useHttps = false;
  AttendanceApi? _api;
  int _tabIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadSettings();
    // v1.5.6: Init VPN service + listen thay đổi trạng thái
    VpnBenhVienService.instance.init().then((_) {
      if (mounted) setState(() {});
    });
    VpnBenhVienService.instance.addListener(_onVpnChanged);
  }

  @override
  void dispose() {
    VpnBenhVienService.instance.removeListener(_onVpnChanged);
    super.dispose();
  }

  void _onVpnChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _loadSettings() async {
    final ip = await Settings.getServerIp();
    final https = await Settings.getUseHttps();
    setState(() {
      _serverIp = ip;
      _useHttps = https;
      _api = AttendanceApi('${https ? 'https' : 'http'}://$ip:8080');
    });
  }

  Future<void> _editServerIp() async {
    // Quick legacy dialog - chi doi IP, cac setting khac xem tab "Cai dat"
    final controller = TextEditingController(text: _serverIp);
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Đổi IP server (nhanh)'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('IP của máy tính chạy attendance_web.py\n(KHÔNG phải IP máy chấm công)',
              style: TextStyle(fontSize: 12, color: Colors.white70)),
            const SizedBox(height: 10),
            TextField(
              controller: controller,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'IP server',
                hintText: 'vd: 172.16.200.105',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Hiện đang: $_serverIp',
              style: const TextStyle(fontSize: 11, color: Colors.cyanAccent),
            ),
            const SizedBox(height: 8),
            const Text(
              'Tip: Vào tab "Cài đặt" để đổi user/pass, devices, HTTPS.',
              style: TextStyle(fontSize: 11, color: Colors.white60),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, null), child: const Text('Hủy')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('Lưu'),
          ),
        ],
      ),
    );
    if (result != null && result.isNotEmpty) {
      await Settings.setServerIp(result);
      await _loadSettings();
    }
  }

  Future<void> _openSettings() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const SettingsScreen()),
    );
    await _loadSettings();
  }

  // v1.5.6: Mở màn hình VPN Bệnh viện
  Future<void> _openVpn() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const VpnBenhVienScreen()),
    );
  }

  // v1.5.6: Thoát app (xác nhận trước khi thoát)
  Future<void> _exitApp() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.exit_to_app, color: Color(0xFFD32F2F)),
            SizedBox(width: 8),
            Text('Thoát app?'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Bạn có chắc muốn thoát AttendanceSuite?'),
            const SizedBox(height: 8),
            if (VpnBenhVienService.instance.isConnected) Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFFFFE0B2),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Row(
                children: [
                  Icon(Icons.vpn_lock, size: 16, color: Color(0xFFE65100)),
                  SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'VPN đang kết nối - sẽ tự ngắt sau 5p nếu không mở lại app',
                      style: TextStyle(fontSize: 11, color: Color(0xFFE65100)),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Hủy')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Thoát', style: TextStyle(color: Color(0xFFD32F2F), fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
    if (confirm == true) {
      // Đóng VPN nếu đang kết nối (best-effort)
      if (VpnBenhVienService.instance.isConnected) {
        VpnBenhVienService.instance.disconnect();
      }
      // Thoát app (Android: systemNavigatorPop, iOS: không cho thoát)
      try {
        // ignore: deprecated_member_use
        exit(0);
      } catch (_) {
        // Fallback nếu không được (iOS)
        // ignore: deprecated_member_use
        SystemNavigator.pop();
      }
    }
  }

  Future<void> _showDiag() async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => const Center(child: CircularProgressIndicator()),
    );
    final diag = await _api!.getDiag();
    Navigator.of(context, rootNavigator: true).pop();
    if (!mounted) return;
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('🔍 Server Diagnostic'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _diagRow('Server', '${diag['server']} v${diag['version']}'),
              _diagRow('Host', '${diag['host']}'),
              _diagRow('Primary IP', '${diag['primary_ip'] ?? '-'}'),
              _diagRow('Devices', '${diag['device_count']}'),
              _diagRow('Records', '${diag['record_count']}'),
              const SizedBox(height: 10),
              const Text('Địa chỉ có thể dùng:',
                style: TextStyle(fontWeight: FontWeight.bold, color: Colors.cyanAccent)),
              const SizedBox(height: 4),
              ...((diag['reachable_urls'] as List?) ?? []).map((u) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 1),
                child: Text('• $u', style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
              )),
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(color: Colors.amber.shade900, borderRadius: BorderRadius.circular(4)),
                child: const Text(
                  '⚠ Nếu điện thoại không kết nối được:\n'
                  '1. Cùng mạng WiFi/LAN với máy server\n'
                  '2. Tắt VPN trên điện thoại\n'
                  '3. Windows Firewall cho phép port 8080',
                  style: TextStyle(fontSize: 11, color: Colors.white),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Đóng')),
        ],
      ),
    );
  }

  Widget _diagRow(String k, String v) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          SizedBox(width: 100, child: Text('$k:', style: const TextStyle(color: Colors.white60, fontSize: 12))),
          Expanded(child: Text(v, style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold))),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_api == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    final protocol = _useHttps ? 'https' : 'http';
    final vpn = VpnBenhVienService.instance;
    return Scaffold(
      appBar: AppBar(
        title: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('🏥 AttendanceSuite - BVĐK Ninh Thuận',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
            Text('Server: $protocol://$_serverIp:8080',
                style: const TextStyle(fontSize: 10, color: Colors.white70)),
          ],
        ),
        backgroundColor: const Color(0xFF00695C),
        foregroundColor: Colors.white,
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          // v1.5.6: Server Diagnostic (giữ nguyên)
          IconButton(
            icon: const Icon(Icons.wifi_tethering),
            tooltip: 'Diagnostic server',
            onPressed: _showDiag,
          ),
          // v1.5.6: VPN Bệnh viện (cạnh Diagnostic)
          IconButton(
            icon: Icon(
              vpn.isConnected
                ? Icons.vpn_lock
                : (vpn.isConnecting ? Icons.sync : Icons.vpn_lock_outlined),
              color: vpn.isConnected ? Colors.greenAccent : Colors.white,
            ),
            tooltip: vpn.isConnected
              ? 'VPN: Đã kết nối'
              : (vpn.isConnecting ? 'VPN: Đang kết nối...' : 'VPN Bệnh viện'),
            onPressed: _openVpn,
          ),
          IconButton(
            icon: const Icon(Icons.settings_ethernet),
            tooltip: 'Đổi IP nhanh: $_serverIp',
            onPressed: _editServerIp,
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: 'Cài đặt (Auth, HTTPS, Devices)',
            onPressed: _openSettings,
          ),
          // v1.5.6: Thoát app (nút cuối cùng)
          IconButton(
            icon: const Icon(Icons.power_settings_new),
            tooltip: 'Thoát app',
            onPressed: _exitApp,
          ),
        ],
      ),
      body: IndexedStack(
        index: _tabIndex,
        children: [
          ViewerScreen(api: _api!, onSettings: _editServerIp),
          SimulatorScreen(api: _api!),
          RemotePunchScreen(api: _api!),
          const SettingsScreen(),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _tabIndex,
        onTap: (i) => setState(() => _tabIndex = i),
        type: BottomNavigationBarType.fixed,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.list_alt),
            label: 'Log chấm công',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.fingerprint),
            label: 'X628 PRO',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.cloud_upload),
            label: 'Chấm từ xa',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.settings),
            label: 'Cài đặt',
          ),
        ],
      ),
    );
  }
}
