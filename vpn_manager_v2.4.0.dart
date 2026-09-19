// vpn/vpn_manager.dart
// v2.4.0: COPY NGUYÊN XI từ HIS Mobile v3.0.76+93+96
// (chỉ đổi import path cho AttendanceSuite)
//
// Quản lý kết nối VPN thật qua openvpn_flutter plugin.
// User có thể đổi user/pass qua UI (Settings → VPN Bệnh viện).
// Password mặc định lấy từ Credentials (XOR-encoded) - KHÔNG có plaintext.
//
// v3.0.93: Auto-disconnect sau 5 phút khi app ở background (gọi qua
// WidgetsBindingObserver.didChangeAppLifecycleState → onAppPaused/onAppResumed).

import 'dart:async';
import 'package:flutter/foundation.dart' show debugPrint, ChangeNotifier, VoidCallback;
import 'package:flutter/services.dart' show rootBundle;
import 'package:openvpn_flutter/openvpn_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/security/credentials.dart';
import '../models/models.dart' as models;

class VpnManager extends ChangeNotifier {
  // Allow both `VpnManager()` (used by main.dart) and `VpnManager.instance` (singleton)
  VpnManager();
  static final VpnManager instance = VpnManager();

  // Default credentials - load sẵn cho user mặc định
  static const String DEFAULT_USERNAME = 'nemk';
  static final String DEFAULT_PASSWORD = Credentials.vpnNemkPassword;
  static const String _kConfigAsset = 'assets/vpn/nemk_vpn.ovpn';
  static const String _kConfigName = 'sslvpn-nemk-client-config.ovpn';

  // Storage keys
  static const String _kStoredUser = 'vpn_bv_user';
  static const String _kStoredPass = 'vpn_bv_pass';
  static const String _kStoredAutoDisconnect = 'vpn_bv_auto_disconnect_sec';

  // v2.4.0: Default TẮT auto-disconnect (Duration.zero = disabled)
  // Lý do: HIS Mobile default 5 phút quá ngắn, user complain "VPN tự tắt"
  //         khi chuyển tab/check thông báo → VPN bị ngắt giữa chừng.
  // User có thể bật lại trong Settings nếu cần (15p / 30p / 1h / 4h).
  static const Duration _kDefaultAutoDisconnect = Duration.zero;

  // v3.0.76: Real OpenVPN engine từ openvpn_flutter package
  late final OpenVPN _engine = OpenVPN(
    onVpnStatusChanged: _onVpnStatusChanged,
    onVpnStageChanged: _onVpnStageChanged,
  );
  bool _initialized = false;

  // State
  VPNStage? _stage;
  VpnStatus? _vpnStatus;
  String? _lastError;
  bool _busy = false;

  VPNStage? get stage => _stage;
  VpnStatus? get vpnStatus => _vpnStatus;
  String? get lastError => _lastError;

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
      case VPNStage.connected:
        return 'Đã kết nối';
      case VPNStage.disconnected:
        return 'Chưa kết nối';
      case VPNStage.connecting:
        return 'Đang kết nối...';
      case VPNStage.authenticating:
      case VPNStage.authentication:
        return 'Đang xác thực...';
      case VPNStage.prepare:
        return 'Đang chuẩn bị...';
      case VPNStage.disconnecting:
        return 'Đang ngắt kết nối...';
      case VPNStage.error:
        return 'Lỗi VPN';
      case VPNStage.denied:
        return 'Bị từ chối (cấp quyền VPN?)';
      case VPNStage.exiting:
        return 'Đang thoát...';
      default:
        return s.toString().split('.').last;
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

  String get currentUser => _cachedUser ?? DEFAULT_USERNAME;
  String get currentPass => _cachedPass ?? DEFAULT_PASSWORD;

  /// True nếu user/pass là default
  bool get isUsingDefaultAccount {
    return (_cachedUser ?? DEFAULT_USERNAME) == DEFAULT_USERNAME &&
        (_cachedPass ?? DEFAULT_PASSWORD) == DEFAULT_PASSWORD;
  }

  /// Mask password cho UI hiển thị
  String get maskedPassword {
    final p = currentPass;
    if (p.isEmpty) return '';
    return '*' * p.length;
  }

  Duration get autoDisconnectAfter => _autoDisconnectAfter;

  bool get isAutoDisconnectPending => _autoDisconnectTimer != null;

  int? get remainingAutoDisconnectSeconds {
    if (_pausedAt == null) return null;
    final elapsed = DateTime.now().difference(_pausedAt!);
    final remaining = _autoDisconnectAfter - elapsed;
    if (remaining.isNegative) return 0;
    return remaining.inSeconds;
  }

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
        localizedDescription: 'AttendanceSuite VPN - BVĐK Ninh Thuận',
      );
      _initialized = true;
      final curStage = await _engine.stage();
      _stage = curStage;
      debugPrint('VpnManager: OpenVPN engine initialized, stage=$curStage');
    } catch (e) {
      debugPrint('VpnManager: init error: $e');
    }
    notifyListeners();
  }

  void _onVpnStatusChanged(VpnStatus? status) {
    debugPrint('VPN status: $status');
    _vpnStatus = status;
    _notifyLegacyStatus();
    notifyListeners();
  }

  void _onVpnStageChanged(VPNStage stage, String rawStage) {
    debugPrint('VPN stage: $stage, raw: $rawStage');
    _stage = stage;
    if (stage == VPNStage.error || stage == VPNStage.denied) {
      _lastError = 'VPN stage: ${stage.toString().split('.').last} (raw: $rawStage)';
    } else {
      _lastError = null;
    }
    if (stage == VPNStage.connected || stage == VPNStage.disconnected) {
      _busy = false;
    }
    _notifyLegacyStatus();
    notifyListeners();
  }

  /// v2.4.0: 1-tap connect (compatible with main.dart's connectOneTap())
  Future<({bool success, String message, VpnTier tier})> connectOneTap() async {
    final ok = await connect();
    if (!ok) {
      return (success: false, message: _lastError ?? 'Không thể kết nối VPN', tier: VpnTier.native);
    }
    return (success: true, message: 'Đang kết nối Sophos VPN...', tier: VpnTier.native);
  }

  /// Kết nối VPN với credentials hiện tại
  Future<bool> connect() async {
    if (_busy) return false;
    if (isConnected) return true;
    _busy = true;
    _lastError = null;
    notifyListeners();
    try {
      await init();
      final config = await rootBundle.loadString(_kConfigAsset);
      await _engine.connect(
        config,
        _kConfigName,
        username: currentUser,
        password: currentPass,
        bypassPackages: const [],
        certIsRequired: false,
      );
      return true;
    } catch (e) {
      _lastError = e.toString();
      _busy = false;
      notifyListeners();
      debugPrint('VpnManager: connect error: $e');
      return false;
    }
  }

  Future<void> disconnect() async {
    try {
      _engine.disconnect();
    } catch (e) {
      debugPrint('VpnManager: disconnect error: $e');
    }
    _busy = false;
    notifyListeners();
  }

  /// Lưu credentials mới
  Future<void> setCredentials(String user, String pass) async {
    _cachedUser = user;
    _cachedPass = pass;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kStoredUser, user);
      await prefs.setString(_kStoredPass, pass);
    } catch (e) {
      debugPrint('VpnManager: setCredentials error: $e');
    }
    notifyListeners();
  }

  Future<void> resetToDefault() async {
    _cachedUser = null;
    _cachedPass = null;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_kStoredUser);
      await prefs.remove(_kStoredPass);
    } catch (e) {
      debugPrint('VpnManager: resetToDefault error: $e');
    }
    notifyListeners();
  }

  // ========== Auto-disconnect sau khi app ở background ==========

  /// App vừa vào background (paused) - bắt đầu đếm giờ auto-disconnect
  void onAppPaused() {
    // v2.4.0: Nếu auto-disconnect bị tắt (Duration.zero) thì không làm gì
    if (_autoDisconnectAfter == Duration.zero) {
      return;
    }
    if (!isConnected) {
      _wasConnectedBeforePause = false;
      return;
    }
    _wasConnectedBeforePause = true;
    _pausedAt = DateTime.now();
    _autoDisconnectTimer?.cancel();
    _autoDisconnectTimer = Timer(_autoDisconnectAfter, () {
      debugPrint('VpnManager: auto-disconnect after ${_autoDisconnectAfter.inMinutes} min in background');
      if (isConnected) {
        disconnect();
        _lastError = 'Auto-disconnect: app ở background quá ${_autoDisconnectAfter.inMinutes} phút';
      }
      _autoDisconnectTimer = null;
      _pausedAt = null;
      notifyListeners();
    });
    debugPrint('VpnManager: app paused, auto-disconnect in ${_autoDisconnectAfter.inMinutes} min');
    notifyListeners();
  }

  /// App vừa resume (foreground lại) - hủy timer
  void onAppResumed() {
    if (_autoDisconnectTimer != null) {
      _autoDisconnectTimer!.cancel();
      _autoDisconnectTimer = null;
      _pausedAt = null;
      _wasConnectedBeforePause = false;
      debugPrint('VpnManager: app resumed, cancelled auto-disconnect');
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
      debugPrint('VpnManager: setAutoDisconnectMinutes error: $e');
    }
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════
  // LEGACY INTERFACE (for main.dart compatibility)
  // ═══════════════════════════════════════════════════════════

  /// Synthesized VpnStatus for backwards compat with main.dart / UI
  models.VpnStatus get status {
    return models.VpnStatus(
      connected: isConnected,
      lastError: _lastError,
      connectedAt: isConnected ? DateTime.now() : null,
    );
  }

  /// Legacy callback (main.dart uses this to re-discover IPs)
  VoidCallback? onStatusChanged;
  void _notifyLegacyStatus() {
    try {
      onStatusChanged?.call();
    } catch (_) {}
  }

  /// Tier (always native for openvpn_flutter)
  VpnTier get activeTier => VpnTier.native;
}

/// Tier enum (kept for backwards compat with main.dart)
enum VpnTier { native, app, manual, unknown }
