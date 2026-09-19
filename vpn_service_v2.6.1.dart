// vpn_service.dart - Native OpenVPN client cho AttendanceSuite v2.6.0
// Pattern giống HIS Mobile / camera_viewer dùng openvpn_flutter.
// Dùng cho Sophos VPN BV Ninh Thuận (113.176.81.193:8443).
import 'package:flutter/foundation.dart';
import 'package:openvpn_flutter/openvpn_flutter.dart';

typedef VpnStatusCallback = void Function(String status, String stage);

class VpnService {
  static OpenVPN? _openvpn;
  static String _lastStatus = 'disconnected';
  static String _lastStage = 'idle';
  static VpnStatusCallback? _callback;

  static OpenVPN _getVpn() {
    _openvpn ??= OpenVPN(
      onVpnStatusChanged: (status) {
        _lastStatus = status.toString();
        debugPrint('VPN status: $status');
        _callback?.call(_lastStatus, _lastStage);
      },
      onVpnStageChanged: (stage, raw) {
        _lastStage = '$stage';
        debugPrint('VPN stage: $stage ($raw)');
        _callback?.call(_lastStatus, _lastStage);
      },
    );
    return _openvpn!;
  }

  /// Khởi tạo với groupIdentifier khớp AndroidManifest (nếu cần).
  static Future<void> initialize() async {
    final vpn = _getVpn();
    vpn.initialize(
      groupIdentifier: 'group.com.bvdk.attendance_mobile',
      providerBundleIdentifier: 'com.bvdk.attendance_mobile',
      localizedDescription: 'AttendanceSuite - VPN BV Ninh Thuan',
    );
  }

  static Future<bool> start({
    required String config,
    required String name,
    String username = '',
    String password = '',
    VpnStatusCallback? onStatusChange,
  }) async {
    try {
      _callback = onStatusChange;
      final vpn = _getVpn();
      vpn.connect(
        config,
        name,
        username: username,
        password: password,
        bypassPackages: const [],
        certIsRequired: true,
      );
      return true;
    } catch (e) {
      debugPrint('VPN start error: $e');
      return false;
    }
  }

  static Future<void> stop() async {
    try {
      _openvpn?.disconnect();
      _callback = null;
    } catch (e) {
      debugPrint('VPN stop error: $e');
    }
  }

  static bool get isConnected {
    final stage = _lastStage.toLowerCase();
    return stage.contains('connected') || stage.contains('connecting') ||
        stage.contains('authentic') || stage.contains('prepare') ||
        stage.contains('wait_connection') || stage.contains('tcp_connect') ||
        stage.contains('udp_connect') || stage.contains('assign_ip') ||
        stage.contains('resolve');
  }

  static String get lastStatus => _lastStatus;
  static String get lastStage => _lastStage;
}
