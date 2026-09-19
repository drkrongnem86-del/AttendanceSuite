package com.bvdk.attendance_mobile

import android.content.Intent
import android.net.VpnService
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/// v2.3.0: Migrate from openvpn_flutter plugin to OpenVpnClientService (VpnService foreground service)
/// Inspired by HIS Mobile v3.0.68+ pattern
///
/// MethodChannel: com.drnem.ccdk.attendance/vpn
/// Methods:
///   - connect(mode, user, pass): start foreground service, request VPN permission if needed
///   - disconnect(): stop foreground service
///   - status(): returns {connected, connecting, status}
///   - isPermissionGranted(): returns bool
///   - checkOpenVPNConnectInstalled(): legacy - kept for backwards compat
///   - openOpenVPNConnect(): legacy - kept for backwards compat
class MainActivity: FlutterActivity() {
    private val VPN_CHANNEL = "com.drnem.ccdk.attendance/vpn"

    // VPN permission flow state
    private var vpnPendingResult: MethodChannel.Result? = null
    private var vpnPendingAction: String? = null
    private var pendingVpnMode: String = "builtin"
    private var pendingVpnUser: String = ""
    private var pendingVpnPass: String = ""

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, VPN_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "connect" -> {
                        val mode = call.argument<String>("mode") ?: "builtin"
                        val user = call.argument<String>("user") ?: ""
                        val pass = call.argument<String>("pass") ?: ""

                        pendingVpnMode = mode
                        pendingVpnUser = user
                        pendingVpnPass = pass

                        // Check VPN permission via VpnService.prepare()
                        val intent = VpnService.prepare(this)
                        if (intent != null) {
                            // Need to request permission via system dialog
                            try {
                                vpnPendingResult = result
                                vpnPendingAction = "connect"
                                startActivityForResult(intent, 1001)
                            } catch (e: Exception) {
                                result.error("PERMISSION_DENIED", "VPN permission denied: ${e.message}", null)
                            }
                        } else {
                            // Permission already granted - start service directly
                            startVpnConnection(mode, user, pass)
                            result.success(mapOf("status" to "connecting"))
                        }
                    }
                    "disconnect" -> {
                        stopVpnConnection()
                        result.success(mapOf("status" to "disconnected"))
                    }
                    "status" -> {
                        val isConn = OpenVpnClientService.isConnected
                        val isConn2 = OpenVpnClientService.isConnecting
                        result.success(mapOf(
                            "connected" to isConn,
                            "connecting" to isConn2,
                            "status" to when {
                                isConn -> "connected"
                                isConn2 -> "connecting"
                                else -> "disconnected"
                            }
                        ))
                    }
                    "isPermissionGranted" -> {
                        val intent = VpnService.prepare(this)
                        result.success(intent == null)
                    }
                    "checkOpenVPNConnectInstalled" -> {
                        // Legacy - kept for backwards compat
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
                        // Legacy - kept for backwards compat
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

    /// Handle VPN permission grant result
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == 1001) {
            val pr = vpnPendingResult
            vpnPendingResult = null
            vpnPendingAction = null
            if (pr != null) {
                if (resultCode == RESULT_OK) {
                    startVpnConnection(pendingVpnMode, pendingVpnUser, pendingVpnPass)
                    pr.success(mapOf("status" to "connecting"))
                } else {
                    pr.error("PERMISSION_DENIED", "VPN permission was denied", null)
                }
            }
        }
    }

    private fun startVpnConnection(mode: String, user: String, pass: String) {
        val intent = Intent(this, OpenVpnClientService::class.java).apply {
            action = OpenVpnClientService.ACTION_CONNECT
            putExtra(OpenVpnClientService.EXTRA_MODE, mode)
            putExtra(OpenVpnClientService.EXTRA_USER, user)
            putExtra(OpenVpnClientService.EXTRA_PASS, pass)
        }
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    private fun stopVpnConnection() {
        val intent = Intent(this, OpenVpnClientService::class.java).apply {
            action = OpenVpnClientService.ACTION_DISCONNECT
        }
        startService(intent)
    }
}
