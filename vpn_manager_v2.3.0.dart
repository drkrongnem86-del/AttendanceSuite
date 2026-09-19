// vpn/vpn_manager.dart
// OpenVPN integration for BVĐK Ninh Thuận - Sophos SSL VPN
//
// v2.3.0: Migrate from openvpn_flutter plugin → OpenVpnClientService (Kotlin)
//
// Pattern mirrors HIS Mobile v3.0.68:
// - Native MethodChannel (com.drnem.ccdk.attendance/vpn)
// - Foreground service running VpnService (Android-standard VPN flow)
// - 1-tap connect: VpnService.prepare() → system permission dialog → service start
// - 3-tier fallback in service: native binary → Downloads OVPN → OpenVPN Connect app
// - Polling status (2s) sau khi connect để update UI real-time
//
// Server: 113.176.81.193:8443 (TCP)
// Account (built-in): nemk / Cnttbvnt@321

import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show MethodChannel, PlatformException;
import '../models/models.dart' as models;

/// Tier of last VPN attempt (for UI feedback).
enum VpnTier { native, app, manual, unknown }

class VpnManager {
  static const _channel = MethodChannel('com.drnem.ccdk.attendance/vpn');

  models.VpnStatus _status = models.VpnStatus();
  models.VpnStatus get status => _status;
  VpnTier _activeTier = VpnTier.unknown;
  VpnTier get activeTier => _activeTier;

  VoidCallback? onStatusChanged;
  Timer? _pollTimer;
  bool _connecting = false;

  /// Default credentials for Sophos SSL VPN (built-in account nemk)
  static const String DEFAULT_USERNAME = 'nemk';
  static const String DEFAULT_PASSWORD = 'Cnttbvnt@321';

  Future<void> init() async {
    if (_pollTimer != null) return;
    try {
      // Sync initial status from service
      final res = await _channel.invokeMethod<Map>('status');
      _applyStatusMap(res);
      _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) => _pollStatus());
    } catch (e) {
      debugPrint('VPN init failed: $e');
      _pollTimer ??= Timer.periodic(const Duration(seconds: 2), (_) => _pollStatus());
    }
  }

  /// v2.3.0: 1-tap connect like other apps
  ///
  /// Flow:
  ///   1. Invoke MethodChannel('connect') - service asks for VpnService permission
  ///   2. Android shows system "Allow VPN" dialog (user taps Allow once)
  ///   3. Service starts foreground + tries TIER 1/2/3
  ///   4. Polling status (2s) updates UI in real-time
  ///
  /// Returns (success, message, tier)
  Future<({bool success, String message, VpnTier tier})> connectOneTap() async {
    if (_connecting) {
      return (success: false, message: 'Đang kết nối...', tier: _activeTier);
    }
    if (_status.connected) {
      return (success: true, message: 'VPN đã kết nối', tier: _activeTier);
    }

    _connecting = true;
    _setStatus(connected: false, message: 'Đang yêu cầu quyền VPN...');

    try {
      await init();
      final result = await _channel.invokeMethod<Map>('connect', {
        'mode': 'builtin',
        'user': DEFAULT_USERNAME,
        'pass': DEFAULT_PASSWORD,
      });
      _connecting = false;

      debugPrint('VpnManager.connect result: $result');

      // Determine tier from result (native binary / app / manual)
      final tierStr = result?['tier'] as String? ?? 'native';
      _activeTier = _parseTier(tierStr);

      // After connect() returns, service is starting. Status will be polled.
      final msg = _activeTier == VpnTier.native
          ? 'Đang kết nối Sophos VPN (native)...'
          : _activeTier == VpnTier.app
              ? 'Đã mở OpenVPN Connect. Nhấn Connect trong app đó.'
              : 'Đã lưu OVPN. Import vào OpenVPN Connect.';
      _setStatus(connected: false, message: msg);

      return (success: true, message: msg, tier: _activeTier);
    } on PlatformException catch (e) {
      _connecting = false;
      if (e.code == 'PERMISSION_DENIED') {
        final msg = 'Cần cấp quyền VPN trong Settings → Networks → VPN';
        _setError(msg);
        return (success: false, message: msg, tier: _activeTier);
      }
      final msg = 'Lỗi kết nối: ${e.message ?? e.code}';
      _setError(msg);
      return (success: false, message: msg, tier: _activeTier);
    } catch (e) {
      _connecting = false;
      final msg = 'Lỗi: $e';
      _setError(msg);
      return (success: false, message: msg, tier: _activeTier);
    }
  }

  Future<void> disconnect() async {
    try {
      await _channel.invokeMethod('disconnect');
      _setStatus(connected: false, message: 'Đã ngắt VPN');
    } catch (e) {
      debugPrint('VPN disconnect error: $e');
    }
    _connecting = false;
  }

  Future<bool> isConnected() async {
    return _status.connected;
  }

  Future<bool> isPermissionGranted() async {
    try {
      final r = await _channel.invokeMethod<bool>('isPermissionGranted');
      return r ?? false;
    } on PlatformException catch (e) {
      debugPrint('isPermissionGranted failed: $e');
      return false;
    }
  }

  Future<bool> requestPermission() async {
    return isPermissionGranted();
  }

  // ═══════════════════════════════════════════════════════════
  // STATUS POLLING
  // ═══════════════════════════════════════════════════════════

  models.VpnStatus? _lastNotifiedStatus;

  Future<void> _pollStatus() async {
    try {
      final res = await _channel.invokeMethod<Map>('status');
      _applyStatusMap(res);
    } catch (e) {
      debugPrint('VPN pollStatus error: $e');
    }
  }

  void _applyStatusMap(Map? res) {
    if (res == null) return;
    final wasConnected = _status.connected;
    final isConn = res['connected'] == true;
    final isConn2 = res['connecting'] == true;
    final statusStr = res['status'] as String? ?? 'disconnected';

    _activeTier = _parseTier(res['tier'] as String? ?? '');

    if (isConn && !wasConnected) {
      // Just connected!
      _connecting = false;
      _setStatus(connected: true, message: '✅ VPN đã kết nối');
    } else if (!isConn && !isConn2 && wasConnected) {
      // Just disconnected
      _connecting = false;
      _setStatus(connected: false, message: 'Đã ngắt VPN');
    } else if (isConn2) {
      _connecting = true;
      _setStatus(connected: false, message: 'Đang kết nối VPN...');
    } else if (!isConn && !isConn2 && _status.connected) {
      _setStatus(connected: false);
    }

    _setStatus(
      connected: isConn,
      message: isConn
          ? '✅ VPN: connected (Sophos tunnel up)'
          : isConn2
              ? 'Đang kết nối VPN...'
              : 'Chưa kết nối VPN',
    );
  }

  VpnTier _parseTier(String s) {
    switch (s) {
      case 'native':
        return VpnTier.native;
      case 'app':
        return VpnTier.app;
      case 'manual':
        return VpnTier.manual;
      default:
        return VpnTier.unknown;
    }
  }

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

  /// Force a status refresh (call after VPN connect/disconnect for instant UI update)
  Future<void> refresh() async {
    await _pollStatus();
  }

  Future<void> dispose() async {
    _pollTimer?.cancel();
    _pollTimer = null;
  }
}
