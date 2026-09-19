package com.bvdk.attendance_mobile

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import id.laskarmedia.openvpn_flutter.OpenVPNFlutterPlugin

/// v2.3.1: REVERT to HIS Mobile v3.0.76 pattern
/// Add OpenVPNFlutterPlugin.connectWhileGranted() callback in onActivityResult
/// to properly handle VpnService permission grant from system dialog.
class MainActivity : FlutterActivity() {

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // No additional MethodChannel needed - openvpn_flutter has its own
    }

    /// v3.0.76: Báo cho openvpn_flutter biết user đã trả lời VPN permission prompt
    /// Khi VpnService.prepare() hiển thị system dialog "Allow VPN?" và user tap OK/Cancel,
    /// Android gọi onActivityResult với requestCode = 24 (theo openvpn_flutter).
    /// connectWhileGranted(true) → plugin tiếp tục kết nối với credentials đã pass vào.
    /// connectWhileGranted(false) → plugin hủy.
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        OpenVPNFlutterPlugin.connectWhileGranted(requestCode == 24 && resultCode == RESULT_OK)
        super.onActivityResult(requestCode, resultCode, data)
    }
}
