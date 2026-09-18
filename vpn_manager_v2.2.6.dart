// vpn/vpn_manager.dart
// OpenVPN integration for BVĐK Ninh Thuận - Sophos SSL VPN
// Uses openvpn_flutter package

import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:openvpn_flutter/openvpn_flutter.dart' as ovpn;
import '../models/models.dart' as models;

/// Default OpenVPN config for BV Ninh Thuận (Sophos SSL VPN, server: nemk)
/// Built from the official Sophos SSL VPN client config (Sept 2026).
/// Server: 113.176.81.193:8443 (TCP), cert embedded.
class VpnManager {
  ovpn.OpenVPN? _engine;
  models.VpnStatus _status = models.VpnStatus();
  models.VpnStatus get status => _status;

  /// Called when VPN status changes so the UI (AppState) can re-render.
  VoidCallback? onStatusChanged;

  /// Polling fallback: AppState installs a 1s timer that pings vpn and re-renders
  /// if state changed (cheap check). Reduces risk of missed callbacks.
  Timer? _pollTimer;

  /// Default credentials for Sophos SSL VPN
  static const String DEFAULT_USERNAME = 'nemk';
  static const String DEFAULT_PASSWORD = 'Cnttbvnt@321';

  /// Asset path of the embedded Sophos .ovpn config
  static const String DEFAULT_OVPN_ASSET = 'assets/vpn/sophos-nemk.ovpn';

  /// Read the .ovpn config from app assets (auto-included via pubspec.yaml).
  /// Cached after first read for performance.
  static String? _cachedOvpnConfig;
  static Future<String> loadDefaultOvpnConfig() async {
    if (_cachedOvpnConfig != null) return _cachedOvpnConfig!;
    try {
      final s = await rootBundle.loadString(DEFAULT_OVPN_ASSET);
      _cachedOvpnConfig = s;
      return s;
    } catch (e) {
      debugPrint('Failed to load $DEFAULT_OVPN_ASSET: $e');
      // Fallback: inline placeholder so app still launches if asset missing
      return _fallbackConfig();
    }
  }

  /// Last-resort placeholder if asset is missing.
  /// Real config is `sophos-nemk.ovpn` under assets/vpn/.
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

  /// Returns true if the .ovpn config has real Sophos CA/cert/key embedded
  /// (not the placeholder).
  static bool isRealConfig(String config) {
    return config.contains('Appliance_Certificate_33zqRGP37jmlP7t') ||
           (config.contains('<ca>') &&
            config.contains('<cert>') &&
            config.contains('<key>'));
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
      // Start 1s polling fallback so UI re-renders even if openvpn_flutter
      // callbacks are dropped (some firmware versions have flaky callbacks).
      _pollTimer ??= Timer.periodic(const Duration(seconds: 1), (_) {
        _notifyIfChanged();
      });
    } catch (e) {
      _status = _status.copyWith(lastError: 'init failed: $e');
      debugPrint('VPN init failed: $e');
    }
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

  Future<void> dispose() async {
    _pollTimer?.cancel();
    _pollTimer = null;
    try { _engine?.disconnect(); } catch (_) {}
    _engine = null;
  }

  /// Connect using default Sophos credentials + asset config.
  /// Returns true on success (callback sets actual connected state).
  Future<bool> connectDefault() async {
    final cfg = await loadDefaultOvpnConfig();
    if (!isRealConfig(cfg)) {
      _status = _status.copyWith(
        connected: false,
        lastError: 'OVPN config không hợp lệ (thiếu CA/cert/key).',
      );
      return false;
    }
    return connect(
      ovpnConfig: cfg,
      username: DEFAULT_USERNAME,
      password: DEFAULT_PASSWORD,
      certIsRequired: true,
    );
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
      if (ovpnConfig.isEmpty) {
        _status = _status.copyWith(
          connected: false,
          lastError: 'Thiếu file .ovpn config.',
        );
        return false;
      }
      await _engine!.connect(
        ovpnConfig,
        'BVĐK Ninh Thuận - Sophos SSL VPN',
        username: username ?? DEFAULT_USERNAME,
        password: password ?? DEFAULT_PASSWORD,
        certIsRequired: certIsRequired,
      );
      _status = _status.copyWith(connected: false); // Real state set by callback
      return true;
    } catch (e) {
      _status = _status.copyWith(connected: false, lastError: 'connect failed: $e');
      return false;
    }
  }

  Future<void> disconnect() async {
    try {
      _engine?.disconnect();
    } catch (e) {
      debugPrint('VPN disconnect error: $e');
    }
  }

  Future<bool> isConnected() async {
    if (_engine == null) return false;
    return await _engine!.isConnected();
  }

  Future<bool> requestPermission() async {
    if (_engine == null) await init();
    return await _engine!.requestPermissionAndroid();
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
    if (kDebugMode) {
      debugPrint('VPN stage: $stage ($rawStage)');
    }
    if (stage == ovpn.VPNStage.error || stage == ovpn.VPNStage.denied) {
      _status = _status.copyWith(lastError: 'Stage: $stage ($rawStage)');
    }
    if (stage == ovpn.VPNStage.connected) {
      _status = _status.copyWith(
        connected: true,
        connectedAt: DateTime.now(),
        lastError: null,
      );
    }
    if (stage == ovpn.VPNStage.disconnected) {
      _status = _status.copyWith(connected: false);
    }
    _notifyIfChanged();
  }
}
