// Settings storage - saves server IP for the backend
import 'package:shared_preferences/shared_preferences.dart';

class Settings {
  static const String keyServerIp = 'server_ip';

  // Default IP = LAN IP of the BVĐK Ninh Thuận computer that runs the Python server.
  // The X628 PRO device (172.16.0.212) only speaks ZK protocol on port 4370, not HTTP,
  // so the phone must point at the COMPUTER running attendance_web.py.
  static const String defaultServerIp = '172.16.200.105';

  static Future<String> getServerIp() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(keyServerIp) ?? defaultServerIp;
  }

  static Future<void> setServerIp(String ip) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(keyServerIp, ip);
  }
}
