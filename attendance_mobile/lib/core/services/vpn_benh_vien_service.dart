// VpnBenhVienService v3.0.76 - Native OpenVPN client (ics-openvpn via openvpn_flutter)
// Quản lý kết nối VPN thật, không qua external app.
// v3.0.96: Default password lấy từ Credentials (XOR-encoded) - KHÔNG có plaintext
// User có thể đổi user/pass khác qua UI (Settings → VPN Bệnh viện).
// Password được mask kiểu ***** khi hiển thị trên UI (lưu SharedPrefs vẫn là plain text).
// v3.0.93:
//   - onAppPaused(): bắt đầu đếm 5 phút (timer)
//   - onAppResumed(): nếu còn < 5p thì hủy timer, quá 5p thì tự ngắt VPN
//   - startAppPausedTimer(Duration): cấu hình thời gian auto-disconnect
import 'dart:async';
import 'package:flutter/foundation.dart' show debugPrint, ChangeNotifier;
import 'package:flutter/services.dart' show rootBundle;
import 'package:attendance_mobile/core/security/credentials.dart';
import 'package:openvpn_flutter/openvpn_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

class VpnBenhVienService extends ChangeNotifier {
  VpnBenhVienService._();
  static final VpnBenhVienService instance = VpnBenhVienService._();

  // Default credentials - load sẵn cho user mặc định
  // v3.0.96: Password lấy từ Credentials (XOR-encoded) - KHÔNG có plaintext
  static const String _kDefaultUser = 'nemk';
  static final String _kDefaultPass = Credentials.vpnNemkPassword;
  static const String _kConfigAsset = 'assets/vpn/nemk_vpn.ovpn';
  static const String _kConfigName = 'sslvpn-nemk-client-config.ovpn';

  // Storage keys
  static const String _kStoredUser = 'vpn_bv_user';
  static const String _kStoredPass = 'vpn_bv_pass';
  static const String _kStoredAutoDisconnect = 'vpn_bv_auto_disconnect_sec';

  // v3.0.93: Default 5 phút auto-disconnect khi app ở background
  static const Duration _kDefaultAutoDisconnect = Duration(minutes: 5);

  // v3.0.76: Real OpenVPN engine từ openvpn_flutter package
  late final OpenVPN _engine = OpenVPN(
    onVpnStatusChanged: _onVpnStatusChanged,
    onVpnStageChanged: _onVpnStageChanged,
  );
  bool _initialized = false;

  // State - dùng VPNStage enum từ openvpn_flutter
  VPNStage? _stage;
  VpnStatus? _vpnStatus;
  String? _lastError;
  String? _lastRawStage;  // v1.5.7: Capture raw stage de debug chi tiet
  String? _lastStatusMessage;  // v1.5.7: Capture status message
  bool _busy = false;

  VPNStage? get stage => _stage;
  VpnStatus? get vpnStatus => _vpnStatus;
  String? get lastError => _lastError;
  String? get lastRawStage => _lastRawStage;  // v1.5.7: expose raw stage
  String? get lastStatusMessage => _lastStatusMessage;  // v1.5.7: expose status message

  /// v3.0.76: Trạng thái VPN thật (dựa trên VPNStage)
  /// VPNStage.connected: đã kết nối thật
  /// VPNStage.connecting/authenticating/...: đang kết nối
  /// VPNStage.disconnected: đã ngắt
  /// VPNStage.error/denied: lỗi
  bool get isConnected => _stage == VPNStage.connected;
  bool get isConnecting =>
      _stage == VPNStage.connecting ||
      _stage == VPNStage.authenticating ||
      _stage == VPNStage.authentication ||
      _stage == VPNStage.prepare ||
      _stage == VPNStage.wait_connection ||
      _stage == VPNStage.tcp_connect ||
      _stage == VPNStage.udp_connect ||
      _stage == VPNStage.assign_ip ||
      _stage == VPNStage.resolve ||
      _stage == VPNStage.get_config ||
      _stage == VPNStage.vpn_generate_config;
  bool get isDisconnected => _stage == VPNStage.disconnected || _stage == null;
  bool get isError => _stage == VPNStage.error || _stage == VPNStage.denied;

  String get statusLabel {
    if (_lastError != null) return 'Lỗi: $_lastError';
    final s = _stage;
    if (s == null) return 'Chưa khởi tạo';
    switch (s) {
      case VPNStage.connected: return 'Đã kết nối';
      case VPNStage.disconnected: return 'Chưa kết nối';
      case VPNStage.connecting: return 'Đang kết nối...';
      case VPNStage.authenticating: return 'Đang xác thực...';
      case VPNStage.authentication: return 'Đang xác thực...';
      case VPNStage.prepare: return 'Đang chuẩn bị...';
      case VPNStage.disconnecting: return 'Đang ngắt kết nối...';
      case VPNStage.error: return 'Lỗi VPN';
      case VPNStage.denied: return 'Bị từ chối (cấp quyền VPN?)';
      case VPNStage.exiting: return 'Đang thoát...';
      default: return s.toString().split('.').last;
    }
  }

  // Cached credentials
  String? _cachedUser;
  String? _cachedPass;

  // v3.0.93: Auto-disconnect timer (khi app ở background quá lâu)
  Timer? _autoDisconnectTimer;
  DateTime? _pausedAt;
  Duration _autoDisconnectAfter = _kDefaultAutoDisconnect;
  bool _wasConnectedBeforePause = false;

  String get currentUser => _cachedUser ?? _kDefaultUser;
  String get currentPass => _cachedPass ?? _kDefaultPass;

  /// v3.0.93: True nếu user/pass là default (không hiển thị password trên UI)
  bool get isUsingDefaultAccount {
    return (_cachedUser ?? _kDefaultUser) == _kDefaultUser &&
        (_cachedPass ?? _kDefaultPass) == _kDefaultPass;
  }

  /// v3.0.76: Mask password cho UI hiển thị
  String get maskedPassword {
    final p = currentPass;
    if (p.isEmpty) return '';
    return '*' * p.length;
  }

  /// v3.0.93: Auto-disconnect duration (mặc định 5 phút)
  Duration get autoDisconnectAfter => _autoDisconnectAfter;

  /// v3.0.93: True nếu đang đếm giờ auto-disconnect
  bool get isAutoDisconnectPending => _autoDisconnectTimer != null;

  /// v3.0.93: Số giây còn lại trước khi tự ngắt (null nếu không đếm)
  int? get remainingAutoDisconnectSeconds {
    if (_pausedAt == null) return null;
    final elapsed = DateTime.now().difference(_pausedAt!);
    final remaining = _autoDisconnectAfter - elapsed;
    if (remaining.isNegative) return 0;
    return remaining.inSeconds;
  }

  /// v3.0.76: Initialize engine - phải gọi 1 lần trước khi connect
  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _cachedUser = prefs.getString(_kStoredUser);
    _cachedPass = prefs.getString(_kStoredPass);
    // v3.0.93: Load auto-disconnect duration từ prefs
    final autoDisconnectSec = prefs.getInt(_kStoredAutoDisconnect);
    if (autoDisconnectSec != null && autoDisconnectSec > 0) {
      _autoDisconnectAfter = Duration(seconds: autoDisconnectSec);
    }
    if (_initialized) {
      notifyListeners();
      return;
    }
    try {
      await _engine.initialize(
        localizedDescription: 'HIS Mobile VPN - Bệnh viện',
      );
      _initialized = true;
      // Lấy stage hiện tại (nếu VPN đang chạy từ trước)
      final curStage = await _engine.stage();
      _stage = curStage;
      debugPrint('VpnBenhVienService: OpenVPN engine initialized, stage=$curStage');
    } catch (e) {
      debugPrint('VpnBenhVienService: init error: $e');
    }
    notifyListeners();
  }

  void _onVpnStatusChanged(VpnStatus? status) {
    debugPrint('VPN status: $status');
    _vpnStatus = status;
    // v1.5.7: Capture status message (co the chua thong tin loi)
    if (status != null) {
      _lastStatusMessage = 'Duration: ${status.duration ?? "?"}, '
          'In: ${status.byteIn ?? "?"}, Out: ${status.byteOut ?? "?"}';
    }
    notifyListeners();
  }

  void _onVpnStageChanged(VPNStage stage, String rawStage) {
    debugPrint('VPN stage: $stage, raw: $rawStage');
    _stage = stage;
    _lastRawStage = rawStage;
    // v1.5.7: Capture error message chi tiet hon, phan biet cac loai loi
    if (stage == VPNStage.error) {
      // rawStage thuong chua error message that tu ics-openvpn
      final errMsg = rawStage.isNotEmpty ? rawStage : 'Unknown VPN error';
      _lastError = errMsg;
    } else if (stage == VPNStage.denied) {
      _lastError = 'Quyền VPN bị từ chối - mở Settings > Apps > AttendanceSuite > Permissions > VPN và bật lên';
    } else if (stage == VPNStage.disconnected && _busy) {
      // Mat ket noi bat ngo khi dang connect
      _lastError = 'Mất kết nối VPN (raw: $rawStage)';
    } else if (stage == VPNStage.connected) {
      _lastError = null;
    }
    if (stage == VPNStage.connected || stage == VPNStage.disconnected) {
      _busy = false;
    }
    notifyListeners();
  }

  /// v3.0.76: Kết nối VPN với credentials hiện tại
  Future<bool> connect() async {
    if (_busy) return false;
    if (isConnected) return true;
    _busy = true;
    _lastError = null;
    _lastRawStage = null;
    notifyListeners();
    try {
      await init();
      final config = await rootBundle.loadString(_kConfigAsset);
      if (config.trim().isEmpty) {
        _lastError = 'File .ovpn rỗng - kiểm tra assets/vpn/';
        _busy = false;
        notifyListeners();
        return false;
      }
      await _engine.connect(
        config,
        _kConfigName,
        username: currentUser,
        password: currentPass,
        bypassPackages: const [],
        certIsRequired: false,
      );
      return true;
    } catch (e, stack) {
      // v1.5.7: Capture stack trace + error type de debug
      _lastError = 'Exception: ${e.toString()}\n(${e.runtimeType})';
      _lastRawStage = stack.toString().split('\n').first;
      _busy = false;
      notifyListeners();
      debugPrint('VpnBenhVienService: connect error: $e');
      debugPrint('Stack: $stack');
      return false;
    }
  }

  /// v3.0.76: Ngắt kết nối VPN
  void disconnect() {
    try {
      _engine.disconnect();
    } catch (e) {
      debugPrint('VpnBenhVienService: disconnect error: $e');
    }
    _busy = false;
    notifyListeners();
  }

  /// v3.0.76: Lưu credentials mới (khi user đổi user/pass)
  Future<void> setCredentials(String user, String pass) async {
    _cachedUser = user;
    _cachedPass = pass;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kStoredUser, user);
      await prefs.setString(_kStoredPass, pass);
    } catch (e) {
      debugPrint('VpnBenhVienService: setCredentials error: $e');
    }
    notifyListeners();
  }

  /// v3.0.76: Reset về default credentials (xóa stored)
  Future<void> resetToDefault() async {
    _cachedUser = null;
    _cachedPass = null;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_kStoredUser);
      await prefs.remove(_kStoredPass);
    } catch (e) {
      debugPrint('VpnBenhVienService: resetToDefault error: $e');
    }
    notifyListeners();
  }

  // ========== v3.0.93: Auto-disconnect sau khi app ở background ==========

  /// App vừa vào background (paused) - bắt đầu đếm giờ auto-disconnect
  void onAppPaused() {
    if (!isConnected) {
      _wasConnectedBeforePause = false;
      return;
    }
    _wasConnectedBeforePause = true;
    _pausedAt = DateTime.now();
    _autoDisconnectTimer?.cancel();
    _autoDisconnectTimer = Timer(_autoDisconnectAfter, () {
      debugPrint('VpnBenhVienService: auto-disconnect after ${_autoDisconnectAfter.inMinutes} min in background');
      if (isConnected) {
        disconnect();
        _lastError = 'Auto-disconnect: app ở background quá ${_autoDisconnectAfter.inMinutes} phút';
      }
      _autoDisconnectTimer = null;
      _pausedAt = null;
      notifyListeners();
    });
    debugPrint('VpnBenhVienService: app paused, auto-disconnect in ${_autoDisconnectAfter.inMinutes} min');
    notifyListeners();
  }

  /// App vừa resume (foreground lại) - hủy timer nếu chưa quá hạn
  void onAppResumed() {
    if (_autoDisconnectTimer != null) {
      _autoDisconnectTimer!.cancel();
      _autoDisconnectTimer = null;
      _pausedAt = null;
      _wasConnectedBeforePause = false;
      debugPrint('VpnBenhVienService: app resumed, cancelled auto-disconnect');
      notifyListeners();
    }
  }

  /// Cập nhật thời gian auto-disconnect (phút, 0 = tắt)
  Future<void> setAutoDisconnectMinutes(int minutes) async {
    if (minutes < 0) minutes = 0;
    _autoDisconnectAfter = Duration(minutes: minutes);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt(_kStoredAutoDisconnect, minutes * 60);
    } catch (e) {
      debugPrint('VpnBenhVienService: setAutoDisconnectMinutes error: $e');
    }
    notifyListeners();
  }
}
