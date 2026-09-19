// vpn/vpn_manager.dart
// VPN Bệnh viện - Sophos SSL VPN
//
// v2.3.1: REVERT to HIS Mobile v3.0.76 pattern (openvpn_flutter plugin)
// Lý do: User đã dùng HIS Mobile VPN thành công, muốn cùng pattern ở app này.
// openvpn_flutter plugin cần MainActivity.onActivityResult với
//   OpenVPNFlutterPlugin.connectWhileGranted(true|false) để handle VPN permission.
//
// Ưu điểm so với v2.3.0 (custom VpnService):
// - Plugin đã được battle-tested ở HIS Mobile trên nhiều thiết bị
// - Permission flow đúng chuẩn Android (system dialog + auto-resume)
// - Background notification native
// - Không cần native binary extraction
//
// Default credentials: nemk / Cnttbvnt@321 (XOR-encoded trong Credentials)

import 'dart:async';
import 'package:flutter/foundation.dart' show ChangeNotifier, debugPrint, VoidCallback;
import 'package:flutter/services.dart' show rootBundle;
import 'package:openvpn_flutter/openvpn_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/security/credentials.dart';
import '../models/models.dart' as models;

/// Tier of last VPN attempt (for UI feedback in main.dart).
enum VpnTier { native, app, manual, unknown }

class VpnManager extends ChangeNotifier {
  // Allow both `VpnManager()` (used by main.dart) and `VpnManager.instance` (singleton)
  VpnManager();
  static final VpnManager instance = VpnManager();

  // Default credentials - load sẵn cho user mặc định
  static const String DEFAULT_USERNAME = 'nemk';
  static final String DEFAULT_PASSWORD = Credentials.vpnNemkPassword;
  static const String _kConfigAsset = 'assets/vpn/sophos-nemk.ovpn';
  static const String _kConfigName = 'sslvpn-nemk-client-config.ovpn';

  // Storage keys
  static const String _kStoredUser = 'vpn_bv_user';
  static const String _kStoredPass = 'vpn_bv_pass';

  // OpenVPN engine từ openvpn_flutter package (giống HIS Mobile v3.0.76)
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

  /// VPNStage.connected: đã kết nối thật
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

  String get currentUser => _cachedUser ?? DEFAULT_USERNAME;
  String get currentPass => _cachedPass ?? DEFAULT_PASSWORD;

  bool get isUsingDefaultAccount {
    return (_cachedUser ?? DEFAULT_USERNAME) == DEFAULT_USERNAME &&
        (_cachedPass ?? DEFAULT_PASSWORD) == DEFAULT_PASSWORD;
  }

  String get maskedPassword {
    final p = currentPass;
    if (p.isEmpty) return '';
    return '*' * p.length;
  }

  /// v2.3.1: Initialize engine - phải gọi 1 lần trước khi connect
  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _cachedUser = prefs.getString(_kStoredUser);
    _cachedPass = prefs.getString(_kStoredPass);
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

  // ═══════════════════════════════════════════════════════════
  // LEGACY INTERFACE (for main.dart + screens)
  // Maps HIS Mobile's openvpn_flutter states → our old VpnStatus
  // ═══════════════════════════════════════════════════════════

  VpnTier _activeTier = VpnTier.native; // openvpn_flutter IS native

  /// Synthesized VpnStatus for backwards compat with main.dart / UI
  models.VpnStatus get status {
    return models.VpnStatus(
      connected: isConnected,
      lastError: _lastError,
      connectedAt: isConnected ? DateTime.now() : null,
    );
  }

  VpnTier get activeTier => _activeTier;

  /// Legacy callback (main.dart uses this to re-discover IPs)
  VoidCallback? onStatusChanged;
  void _notifyLegacyStatus() {
    try {
      onStatusChanged?.call();
    } catch (_) {}
  }

  /// v2.3.1: Kết nối VPN với credentials hiện tại
  ///
  /// Flow (giống HIS Mobile v3.0.76):
  /// 1. Plugin calls VpnService.prepare() → system "Allow VPN" dialog
  /// 2. User taps Allow → MainActivity.onActivityResult(24) → connectWhileGranted(true)
  /// 3. Plugin auto-connects with provided credentials
  Future<({bool success, String message, VpnTier tier})> connectOneTap() async {
    if (_busy) {
      return (success: false, message: 'Đang kết nối...', tier: VpnTier.native);
    }
    if (isConnected) {
      return (success: true, message: 'VPN đã kết nối', tier: VpnTier.native);
    }
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
      return (success: true, message: 'Đang kết nối Sophos VPN...', tier: VpnTier.native);
    } catch (e) {
      _lastError = e.toString();
      _busy = false;
      notifyListeners();
      debugPrint('VpnManager: connect error: $e');
      return (success: false, message: 'Lỗi kết nối: $e', tier: VpnTier.native);
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

  Future<bool> isConnectedAsync() async => isConnected;

  Future<bool> isPermissionGranted() async {
    // openvpn_flutter handles permission via VpnService.prepare()
    // No API to pre-check; just return true and let connect() handle it
    return true;
  }

  Future<bool> requestPermission() async => isPermissionGranted();

  /// Lưu credentials mới (khi user đổi user/pass)
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

  @override
  void dispose() {
    _busy = false;
    super.dispose();
  }
}
