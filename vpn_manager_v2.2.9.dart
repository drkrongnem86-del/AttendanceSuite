// vpn/vpn_manager.dart
// OpenVPN integration for BVĐK Ninh Thuận - Sophos SSL VPN
//
// v2.2.9: Simplified 1-tap connect with auto-fallback chain
// - TIER 1: openvpn_flutter (timeout 6s)
// - TIER 2: Auto-launch OpenVPN Connect app (if installed)
// - TIER 3: Save OVPN file to app docs + show path
// Inspired by HIS Mobile v3.0.67+ pattern.

import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle, MethodChannel, PlatformException;
import 'package:openvpn_flutter/openvpn_flutter.dart' as ovpn;
import 'package:path_provider/path_provider.dart';
import '../models/models.dart' as models;

/// Tier of last VPN attempt (for UI feedback).
enum VpnTier { native, app, manual, unknown }

class VpnManager {
  static const _channel = MethodChannel('com.drnem.ccdk.attendance/vpn');

  ovpn.OpenVPN? _engine;
  models.VpnStatus _status = models.VpnStatus();
  models.VpnStatus get status => _status;
  VpnTier _activeTier = VpnTier.unknown;
  VpnTier get activeTier => _activeTier;
  String? _ovpnFilePath;
  String? get ovpnFilePath => _ovpnFilePath;

  VoidCallback? onStatusChanged;
  Timer? _pollTimer;

  /// Default credentials for Sophos SSL VPN (built-in account nemk)
  static const String DEFAULT_USERNAME = 'nemk';
  static const String DEFAULT_PASSWORD = 'Cnttbvnt@321';

  /// Asset path of the embedded Sophos .ovpn config (with CA + cert + key)
  static const String DEFAULT_OVPN_ASSET = 'assets/vpn/sophos-nemk.ovpn';

  static String? _cachedOvpnConfig;
  static Future<String> loadDefaultOvpnConfig() async {
    if (_cachedOvpnConfig != null) return _cachedOvpnConfig!;
    try {
      _cachedOvpnConfig = await rootBundle.loadString(DEFAULT_OVPN_ASSET);
      return _cachedOvpnConfig!;
    } catch (e) {
      debugPrint('Failed to load $DEFAULT_OVPN_ASSET: $e');
      return _fallbackConfig();
    }
  }

  static String _fallbackConfig() => '''
client
dev tun
proto tcp
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA256
cipher AES-128-CBC
verb 3
mute 20
remote 113.176.81.193 8443 tcp-client
''';

  static bool isRealConfig(String config) {
    return config.contains('Appliance_Certificate_33zqRGP37jmlP7t') ||
        (config.contains('<ca>') && config.contains('<cert>') && config.contains('<key>'));
  }

  Future<void> init() async {
    if (_engine != null) return;
    try {
      _engine = ovpn.OpenVPN(
        onVpnStatusChanged: _onVpnStatusChanged,
        onVpnStageChanged: _onVpnStageChanged,
      );
      await _engine!.initialize(
        localizedDescription: 'AttendanceSuite VPN - BVĐK Ninh Thuận',
      );
      _pollTimer ??= Timer.periodic(const Duration(seconds: 1), (_) => _notifyIfChanged());
    } catch (e) {
      debugPrint('VPN init failed: $e');
    }
  }

  /// v2.2.9: Simplified 1-tap connect with auto-fallback.
  /// Returns (success, message, tier).
  ///
  /// Chain:
  ///   TIER 1 (6s timeout): openvpn_flutter
  ///   TIER 2: Open OpenVPN Connect app via MethodChannel
  ///   TIER 3: Write OVPN to app docs (manual import)
  Future<({bool success, String message, VpnTier tier})> connectOneTap() async {
    final cfg = await loadDefaultOvpnConfig();
    if (!isRealConfig(cfg)) {
      final msg = 'OVPN config không hợp lệ (thiếu CA/cert/key).';
      _setError(msg);
      return (success: false, message: msg, tier: VpnTier.unknown);
    }

    // ===== TIER 1: openvpn_flutter (6s timeout) =====
    try {
      final ok = await connect(
        ovpnConfig: cfg,
        username: DEFAULT_USERNAME,
        password: DEFAULT_PASSWORD,
        certIsRequired: true,
      ).timeout(const Duration(seconds: 6), onTimeout: () => false);
      if (ok) {
        _activeTier = VpnTier.native;
        final msg = 'Đang kết nối Sophos VPN (native)...';
        _setStatus(connected: false, message: msg);
        return (success: true, message: msg, tier: VpnTier.native);
      }
    } catch (e) {
      debugPrint('TIER 1 failed: $e');
    }

    // ===== TIER 2: Open OpenVPN Connect app =====
    try {
      final installed = await checkOpenVPNConnectInstalled();
      if (installed.isNotEmpty) {
        final launched = await openOpenVPNConnect();
        if (launched) {
          _activeTier = VpnTier.app;
          final msg = 'Đã mở OpenVPN Connect ($installed).\nNhấn Connect trong app đó, sau đó quay lại đây.';
          _setStatus(connected: false, message: msg);
          return (success: true, message: msg, tier: VpnTier.app);
        }
      }
    } catch (e) {
      debugPrint('TIER 2 failed: $e');
    }

    // ===== TIER 3: Write OVPN to app docs =====
    try {
      final path = await writeOvpnToAppDocs(cfg);
      _ovpnFilePath = path;
      _activeTier = VpnTier.manual;
      final msg = 'Đã lưu OVPN tại:\n$path\n\nCài OpenVPN Connect từ Play Store, import file này để kết nối.';
      _setStatus(connected: false, message: msg);
      return (success: true, message: msg, tier: VpnTier.manual);
    } catch (e) {
      debugPrint('TIER 3 failed: $e');
      final msg = 'Cả 3 tier đều thất bại. Cài OpenVPN Connect từ Play Store rồi thử lại.\nLỗi: $e';
      _setError(msg);
      return (success: false, message: msg, tier: VpnTier.unknown);
    }
  }

  Future<bool> connect({
    String? ovpnConfig,
    String? username,
    String? password,
    bool certIsRequired = true,
  }) async {
    try {
      if (_engine == null) await init();
      if (ovpnConfig == null || ovpnConfig.isEmpty) {
        ovpnConfig = await loadDefaultOvpnConfig();
      }
      await _engine!.connect(
        ovpnConfig,
        'BVĐK Ninh Thuận - Sophos SSL VPN',
        username: username ?? DEFAULT_USERNAME,
        password: password ?? DEFAULT_PASSWORD,
        certIsRequired: certIsRequired,
      );
      _setStatus(connected: false);
      return true;
    } catch (e) {
      _setError('connect failed: $e');
      return false;
    }
  }

  Future<void> disconnect() async {
    try {
      _engine?.disconnect();
    } catch (e) {
      debugPrint('VPN disconnect error: $e');
    }
    _activeTier = VpnTier.unknown;
  }

  Future<bool> isConnected() async {
    if (_engine == null) return false;
    return await _engine!.isConnected();
  }

  Future<bool> requestPermission() async {
    if (_engine == null) await init();
    return await _engine!.requestPermissionAndroid();
  }

  // ===== TIER 2: OpenVPN Connect app via MethodChannel =====
  Future<String> checkOpenVPNConnectInstalled() async {
    try {
      final r = await _channel.invokeMethod<String>('checkOpenVPNConnectInstalled');
      return r ?? '';
    } on PlatformException catch (e) {
      debugPrint('checkOpenVPNConnectInstalled failed: $e');
      return '';
    }
  }

  Future<bool> openOpenVPNConnect() async {
    try {
      final r = await _channel.invokeMethod<bool>('openOpenVPNConnect');
      return r ?? false;
    } on PlatformException catch (e) {
      debugPrint('openOpenVPNConnect failed: $e');
      return false;
    }
  }

  // ===== TIER 3: Write OVPN to app docs =====
  Future<String> writeOvpnToAppDocs(String cfg) async {
    final dir = await getApplicationDocumentsDirectory();
    final path = '${dir.path}/sophos-nemk.ovpn';
    final f = File(path);
    await f.writeAsString(cfg, flush: true);
    return path;
  }

  // ===== Status helpers =====
  void _setStatus({required bool connected, String? message}) {
    _status = _status.copyWith(
      connected: connected,
      lastError: message,
    );
    _notifyIfChanged();
  }

  void _setError(String err) {
    _status = _status.copyWith(connected: false, lastError: err);
    _notifyIfChanged();
  }

  models.VpnStatus? _lastNotifiedStatus;
  void _notifyIfChanged() {
    if (onStatusChanged == null) return;
    final cur = _status;
    if (_lastNotifiedStatus == null ||
        _lastNotifiedStatus!.connected != cur.connected ||
        _lastNotifiedStatus!.lastError != cur.lastError ||
        _lastNotifiedStatus!.connectedAt != cur.connectedAt) {
      _lastNotifiedStatus = cur;
      onStatusChanged!();
    }
  }

  void _onVpnStatusChanged(ovpn.VpnStatus? status) {
    if (status == null) return;
    final connected = status.connectedOn != null;
    _status = _status.copyWith(
      connected: connected,
      connectedAt: status.connectedOn,
      lastError: null,
    );
    _notifyIfChanged();
  }

  void _onVpnStageChanged(ovpn.VPNStage? stage, String? rawStage) {
    if (kDebugMode) debugPrint('VPN stage: $stage ($rawStage)');
    if (stage == ovpn.VPNStage.error || stage == ovpn.VPNStage.denied) {
      _status = _status.copyWith(lastError: 'Stage: $stage ($rawStage)');
    }
    if (stage == ovpn.VPNStage.connected) {
      _status = _status.copyWith(connected: true, connectedAt: DateTime.now(), lastError: null);
      _activeTier = VpnTier.native;
    }
    if (stage == ovpn.VPNStage.disconnected) {
      _status = _status.copyWith(connected: false);
    }
    _notifyIfChanged();
  }

  Future<void> dispose() async {
    _pollTimer?.cancel();
    _pollTimer = null;
    try { _engine?.disconnect(); } catch (_) {}
    _engine = null;
  }
}
