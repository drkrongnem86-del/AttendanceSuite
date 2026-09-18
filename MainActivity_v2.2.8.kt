package com.bvdk.attendance_mobile

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/// v2.2.8: Add VPN 3-tier MethodChannel (mirrors HIS Mobile v3.0.67 pattern)
/// - checkOpenVPNConnectInstalled: returns package name if installed, "" otherwise
/// - openOpenVPNConnect: launches OpenVPN Connect app via Intent
class MainActivity: FlutterActivity() {
    private val VPN_CHANNEL = "com.drnem.ccdk.attendance/vpn"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, VPN_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "checkOpenVPNConnectInstalled" -> {
                        val openVpnPackages = listOf(
                            "net.openvpn.connect.android",
                            "de.blinkt.openvpn"
                        )
                        var installed: String? = null
                        for (pkg in openVpnPackages) {
                            try {
                                packageManager.getPackageInfo(pkg, 0)
                                installed = pkg
                                break
                            } catch (_: Exception) {}
                        }
                        result.success(installed ?: "")
                    }
                    "openOpenVPNConnect" -> {
                        val openVpnPackages = listOf(
                            "net.openvpn.connect.android",
                            "de.blinkt.openvpn"
                        )
                        var launched = false
                        for (pkg in openVpnPackages) {
                            try {
                                packageManager.getPackageInfo(pkg, 0)
                                val intent = packageManager.getLaunchIntentForPackage(pkg)
                                if (intent != null) {
                                    startActivity(intent)
                                    launched = true
                                    result.success(true)
                                    return@setMethodCallHandler
                                }
                            } catch (_: Exception) {}
                        }
                        result.success(false)
                    }
                    else -> result.notImplemented()
                }
            }
    }
}
