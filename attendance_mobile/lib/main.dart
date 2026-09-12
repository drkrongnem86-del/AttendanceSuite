// AttendanceSuite - Mobile app for BVĐK Ninh Thuan
// Connects to the Python backend on the LAN
import 'package:flutter/material.dart';
import 'api.dart';
import 'settings.dart';
import 'viewer_screen.dart';
import 'simulator_screen.dart';
import 'remote_punch_screen.dart';
import 'updater.dart';

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
        brightness: Brightness.dark,
        primaryColor: Colors.cyan,
        scaffoldBackgroundColor: const Color(0xFF1a1a2e),
        colorScheme: ColorScheme.fromSwatch().copyWith(
          brightness: Brightness.dark,
          primary: Colors.cyan,
        ),
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
  AttendanceApi? _api;
  int _tabIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final ip = await Settings.getServerIp();
    setState(() {
      _serverIp = ip;
      _api = AttendanceApi('http://$ip:8080');
    });
    // Check for app updates sau khi load xong (khong block UI)
    _checkForUpdates();
  }

  Future<void> _checkForUpdates() async {
    // Doi 5s de UI load xong truoc
    await Future.delayed(const Duration(seconds: 5));
    if (!mounted) return;
    try {
      final info = await AppUpdater.checkForUpdate();
      if (mounted && info.isUpdateAvailable) {
        await AppUpdater.showUpdateDialog(context, info);
      }
    } catch (e) {
      // Silent - khong can thong bao loi update
    }
  }

  Future<void> _editServerIp() async {
    final controller = TextEditingController(text: _serverIp);
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Đổi IP server'),
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
      setState(() {
        _serverIp = result;
        _api = AttendanceApi('http://$_serverIp:8080');
      });
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
    return Scaffold(
      appBar: AppBar(
        title: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('🏥 AttendanceSuite - BVĐK Ninh Thuận', style: TextStyle(fontSize: 15)),
            Text('Server: $_serverIp:8080', style: const TextStyle(fontSize: 10, color: Colors.cyanAccent)),
          ],
        ),
        backgroundColor: const Color(0xFF0f1729),
        actions: [
          IconButton(
            icon: const Icon(Icons.wifi_tethering),
            tooltip: 'Diagnostic server',
            onPressed: _showDiag,
          ),
          IconButton(
            icon: const Icon(Icons.settings_ethernet),
            tooltip: 'Đổi IP: $_serverIp',
            onPressed: _editServerIp,
          ),
        ],
      ),
      body: IndexedStack(
        index: _tabIndex,
        children: [
          ViewerScreen(api: _api!, onSettings: _editServerIp),
          SimulatorScreen(api: _api!),
          RemotePunchScreen(api: _api!),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _tabIndex,
        onTap: (i) => setState(() => _tabIndex = i),
        backgroundColor: const Color(0xFF0f1729),
        selectedItemColor: Colors.cyan,
        unselectedItemColor: Colors.white60,
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
        ],
      ),
    );
  }
}
