package com.bvdk.attendance_mobile

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.net.VpnService
import android.os.Build
import android.os.Environment
import android.os.ParcelFileDescriptor
import android.provider.MediaStore
import android.util.Log
import androidx.core.content.FileProvider
import java.io.*
import kotlin.concurrent.thread

/**
 * v2.3.0: OpenVPN Client Service - migrate from openvpn_flutter plugin
 *
 * Inspired by HIS Mobile v3.0.68 pattern:
 * - TIER 1: Native openvpn binary (if available in assets/vpn/)
 * - TIER 2: Export to Downloads via MediaStore + FileProvider + ACTION_VIEW
 * - TIER 3: Try OpenVPN Connect app directly
 *
 * Reads OVPN from assets/vpn/sophos-nemk.ovpn (real hospital config)
 * Injects: inline <auth-user-pass> + route 172.16.0.0/16 for BV LAN access
 *
 * Server: 113.176.81.193:8443 (TCP)
 * Account: nemk / Cnttbvnt@321 (built-in default)
 */
class OpenVpnClientService : VpnService() {
    companion object {
        const val TAG = "OpenVpnClient"
        const val ACTION_CONNECT = "com.bvdk.attendance_mobile.CONNECT"
        const val ACTION_DISCONNECT = "com.bvdk.attendance_mobile.DISCONNECT"

        const val EXTRA_MODE = "vpn_mode"
        const val EXTRA_USER = "vpn_user"
        const val EXTRA_PASS = "vpn_pass"

        const val MODE_BUILTIN = "builtin"
        const val MODE_CUSTOM = "custom"

        const val NOTIFICATION_ID = 1001
        const val CHANNEL_ID = "attendance_vpn"

        var isConnected = false
            private set
        var isConnecting = false
            private set
        var instance: OpenVpnClientService? = null
            private set

        private const val VPN_SERVER = "113.176.81.193"
        private const val VPN_PORT = "8443"
        private const val BUILTIN_USER = "nemk"
        private const val BUILTIN_PASS = "Cnttbvnt@321"

        // VPN file provider authority (must match AndroidManifest.xml)
        const val FILEPROVIDER_AUTHORITY = "com.bvdk.attendance_mobile.vpn.fileprovider"

        // OVPN asset path (real Sophos config with CA + cert + key)
        private const val OVPN_ASSET = "vpn/sophos-nemk.ovpn"
    }

    private var vpnMode = MODE_BUILTIN
    private var vpnUser = BUILTIN_USER
    private var vpnPass = BUILTIN_PASS

    private var openvpnProcess: Process? = null
    private var running = false
    private var workDir: File? = null

    private var lastExportedPath: String? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        makeChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                vpnMode = intent.getStringExtra(EXTRA_MODE) ?: MODE_BUILTIN
                vpnUser = intent.getStringExtra(EXTRA_USER) ?: BUILTIN_USER
                vpnPass = intent.getStringExtra(EXTRA_PASS) ?: BUILTIN_PASS

                if (vpnMode == MODE_BUILTIN || vpnUser.isNullOrBlank()) {
                    vpnUser = BUILTIN_USER
                    vpnPass = BUILTIN_PASS
                    vpnMode = MODE_BUILTIN
                }

                isConnecting = true
                isConnected = false
                lastExportedPath = null
                startForeground(NOTIFICATION_ID, makeNotif("Đang kết nối VPN..."))
                thread { connect() }
            }
            ACTION_DISCONNECT -> {
                disconnect()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        disconnect()
        instance = null
        super.onDestroy()
    }

    private fun makeChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                CHANNEL_ID, "AttendanceSuite VPN",
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Kết nối VPN BV Ninh Thuận" }
            getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
    }

    private fun makeNotif(t: String) = android.app.Notification.Builder(this, CHANNEL_ID)
        .setContentTitle("AttendanceSuite VPN")
        .setContentText(t)
        .setSmallIcon(android.R.drawable.ic_lock_lock)
        .setOngoing(true)
        .setPriority(android.app.Notification.PRIORITY_LOW)
        .build()

    private fun notify(t: String) {
        try {
            getSystemService(NotificationManager::class.java)
                .notify(NOTIFICATION_ID, makeNotif(t))
        } catch (_: Exception) {}
    }

    // ═══════════════════════════════════════════════════════════
    // MAIN CONNECTION FLOW
    // ═══════════════════════════════════════════════════════════

    private fun connect() {
        var ok = false
        try {
            running = true
            Log.d(TAG, "v2.3.0 VPN connect - mode: $vpnMode, user: $vpnUser")
            notify("Chuẩn bị VPN...")

            workDir = getDir("vpn", Context.MODE_PRIVATE)
            Log.d(TAG, "Work dir: ${workDir!!.absolutePath}")

            // TIER 1: Try native openvpn binary (if available in assets/vpn/)
            val binFile = File(workDir, "openvpn")
            if (extractBinary(binFile)) {
                Log.d(TAG, "✅ Found openvpn binary, trying native connection...")
                notify("Kết nối native...")
                val ovpnFile = File(workDir, "attendance_vpn.ovpn")
                val credFile = File(workDir, "vpn_pass.txt")
                writeOvpnConfigNative(ovpnFile)
                writeCredentials(credFile)
                ok = startOpenVpn(ovpnFile)
                if (ok) return
            }

            // TIER 2: Export to Downloads via MediaStore + FileProvider + ACTION_VIEW
            Log.d(TAG, "⚡ No binary, exporting OVPN to Downloads via MediaStore...")
            notify("Tạo file cấu hình VPN...")

            val exportedFile = exportOvpnToDownloads()
            if (exportedFile != null) {
                lastExportedPath = exportedFile.absolutePath
                notify("Đã lưu sophos-nemk-vpn.ovpn vào Downloads!")

                val uri = FileProvider.getUriForFile(
                    this,
                    FILEPROVIDER_AUTHORITY,
                    exportedFile
                )
                Log.d(TAG, "✅ OVPN exported: ${exportedFile.absolutePath}")
                Log.d(TAG, "✅ FileProvider URI: $uri")

                val opened = promptUserOpenOvpn(uri, exportedFile.name)
                if (opened) {
                    notify("✅ Đã mở file OVPN! Chọn 'OpenVPN Connect' để kết nối.")
                    isConnecting = false
                    isConnected = false
                    return
                }
            }

            // TIER 3: Try OpenVPN Connect app directly
            Log.d(TAG, "📱 Trying OpenVPN Connect app directly...")
            notify("Mở OpenVPN Connect...")
            ok = tryLaunchOpenVPNConnectApp()
            if (ok) {
                notify("OpenVPN Connect đã được mở. Nhấn Connect trong app đó!")
                isConnecting = false
                isConnected = false
                return
            }

            notify("❌ Không tìm thấy OpenVPN. Vui lòng cài OpenVPN Connect từ CH Play.")
            Log.e(TAG, "Failed all tiers - no VPN app available")

        } catch (e: Exception) {
            Log.e(TAG, "❌ ${e.message}")
            e.printStackTrace()
            notify("Lỗi: ${e.message}")
        }

        if (!ok) {
            disconnect()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun disconnect() {
        running = false
        isConnected = false
        isConnecting = false
        try { openvpnProcess?.destroy() } catch (_: Exception) {}
        openvpnProcess = null
        Log.d(TAG, "Disconnected")
    }

    // ═══════════════════════════════════════════════════════════
    // TIER 1: NATIVE OPENVPN BINARY
    // ═══════════════════════════════════════════════════════════

    private fun extractBinary(dest: File): Boolean {
        return try {
            if (dest.exists() && dest.canExecute() && dest.length() > 10240) {
                Log.d(TAG, "Binary already extracted: ${dest.absolutePath} (${dest.length()} bytes)")
                return true
            }

            val assetMgr = assets
            val entries = try { assetMgr.list("vpn")?.toList() ?: emptyList() } catch (_: Exception) { emptyList() }
            Log.d(TAG, "Assets vpn/ entries: ${entries.joinToString()}")

            val binaryNames = listOf(
                "pie_openvpn.arm64-v8a", "openvpn.arm64-v8a",
                "openvpn.arm64", "pie_openvpn.aarch64", "openvpn.aarch64", "openvpn"
            )
            val binaryAsset = entries.find { entry ->
                binaryNames.any { name -> entry == name || entry.contains(name.replace(".arm64", "").replace(".aarch64", "")) }
            } ?: entries.find {
                (it.contains("arm64") || it.contains("aarch64") || it.contains("openvpn")) &&
                !it.endsWith(".ovpn") && !it.endsWith(".txt")
            }

            if (binaryAsset != null) {
                assetMgr.open("vpn/$binaryAsset").use { inp ->
                    inp.copyTo(dest.outputStream())
                }
                dest.setExecutable(true)
                Log.d(TAG, "Extracted binary: $binaryAsset (${dest.length()} bytes)")

                if (dest.length() < 10240) {
                    Log.w(TAG, "Binary too small (${dest.length()} bytes), treating as stub")
                    dest.delete()
                    return false
                }
                return dest.canExecute()
            }

            // System paths fallback (copy from another VPN app that has it)
            val systemPaths = listOf(
                "/data/data/net.openvpn.connect.android/cache/openvpn",
                "/data/data/de.blinkt.openvpn/cache/openvpn",
                "/system/bin/openvpn", "/system/xbin/openvpn", "/vendor/bin/openvpn"
            )
            for (p in systemPaths) {
                val f = File(p)
                if (f.exists() && f.canExecute() && f.length() > 10240) {
                    f.inputStream().use { inp -> inp.copyTo(dest.outputStream()) }
                    dest.setExecutable(true)
                    Log.d(TAG, "Copied from system: $p (${f.length()} bytes)")
                    return dest.canExecute()
                }
            }

            Log.w(TAG, "No valid openvpn binary found")
            false
        } catch (e: Exception) {
            Log.e(TAG, "Extract binary error: ${e.message}")
            false
        }
    }

    private fun startOpenVpn(configFile: File): Boolean {
        val binPaths = listOf(
            File(workDir, "openvpn").absolutePath,
            "/data/data/net.openvpn.connect.android/cache/openvpn",
            "/data/data/de.blinkt.openvpn/cache/openvpn",
            "/system/bin/openvpn", "/system/xbin/openvpn", "/vendor/bin/openvpn"
        )

        var binPath: String? = null
        for (p in binPaths) {
            val f = File(p)
            if (f.exists() && f.canExecute() && f.length() > 10240) {
                binPath = p
                Log.d(TAG, "Using openvpn: $p (${f.length()} bytes)")
                break
            }
        }

        if (binPath == null) {
            Log.w(TAG, "No valid openvpn binary found")
            return false
        }

        val args = listOf(
            binPath, "--config", configFile.absolutePath,
            "--cd", workDir!!.absolutePath,
            "--log", File(workDir, "openvpn.log").absolutePath,
            "--verb", "4"
        )

        val pb = ProcessBuilder(args)
        pb.directory(workDir)
        pb.redirectErrorStream(true)

        try {
            openvpnProcess = pb.start()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start openvpn: ${e.message}")
            return false
        }

        thread {
            val reader = BufferedReader(InputStreamReader(openvpnProcess!!.inputStream))
            var line: String?
            var connectSuccess = false
            var connectFailed = false
            var lineCount = 0

            while (running && openvpnProcess!!.isAlive) {
                try {
                    line = reader.readLine()
                    if (line == null) break
                    lineCount++
                    if (lineCount <= 50) Log.d(TAG, "[ovpn] $line")

                    if (line.contains("Initialization Sequence Completed")) {
                        if (!connectSuccess) {
                            connectSuccess = true
                            isConnected = true
                            isConnecting = false
                            notify("✅ VPN đã kết nối!")
                            Log.d(TAG, "✅ VPN Connected!")
                            updateNotification("✅ VPN: Connected")
                        }
                    }

                    if (line.contains("FAILED") || line.contains("AUTHENTICATION FAILED") ||
                        line.contains("Connection refused") || line.contains("UNREACHABLE")) {
                        if (!connectFailed) {
                            connectFailed = true
                            isConnecting = false
                            isConnected = false
                            notify("❌ VPN thất bại: ${line.take(80)}")
                            Log.e(TAG, "❌ VPN failed: $line")
                            disconnect()
                        }
                    }

                    if (lineCount > 500) break
                } catch (_: Exception) { break }
            }

            if (!connectSuccess) {
                isConnecting = false
                isConnected = false
                notify("VPN: Không kết nối được")
            }
        }

        Thread.sleep(15000)
        return isConnected
    }

    // ═══════════════════════════════════════════════════════════
    // OVPN CONFIG BUILDERS (read asset + inject credentials + routes)
    // ═══════════════════════════════════════════════════════════

    /**
     * Read the real Sophos OVPN config from assets and add route 172.16.0.0/16
     */
    private fun readAssetOvpn(): String {
        return try {
            assets.open(OVPN_ASSET).bufferedReader().use { it.readText() }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to read $OVPN_ASSET: ${e.message}")
            // Fallback minimal config (no certs - should never happen)
            """client
dev tun
proto tcp
nobind
remote $VPN_SERVER $VPN_PORT
"""
        }
    }

    /**
     * Inject inline auth-user-pass credentials + BV LAN route
     * Used for TIER 2 (OpenVPN Connect import from Downloads)
     */
    private fun buildInlineOvpnForDownloads(): String {
        val base = readAssetOvpn()
        var modified = base

        // Replace `auth-user-pass` (no filename = prompts user) with inline credentials
        modified = modified.replace(Regex("(?m)^auth-user-pass\\s*$"), "")

        // Add route 172.16.0.0/16 if not present (so ZK devices are reachable)
        if (!modified.contains("route 172.16.0.0")) {
            modified = modified.replace(
                Regex("(?m)^route-delay\\s+4\\s*$"),
                "route 172.16.0.0 255.255.0.0\nroute-delay 4"
            )
        }

        // Append inline credentials block (OpenVPN Connect reads this for auto-import)
        val credBlock = "\n<auth-user-pass>\n$vpnUser\n$vpnPass\n</auth-user-pass>\n"
        return modified + credBlock
    }

    /**
     * Write OVPN for native binary with external auth-user-pass file
     * Used for TIER 1 (running openvpn binary directly)
     */
    private fun writeOvpnConfigNative(dest: File) {
        val base = readAssetOvpn()
        var modified = base

        // Point auth-user-pass to external credentials file
        if (modified.contains(Regex("(?m)^auth-user-pass\\s*$"))) {
            modified = modified.replace(
                Regex("(?m)^auth-user-pass\\s*$"),
                "auth-user-pass vpn_pass.txt"
            )
        } else if (!modified.contains("auth-user-pass vpn_pass.txt")) {
            // No auth-user-pass line at all - inject one before </key>
            modified = modified.replace("</key>", "</key>\nauth-user-pass vpn_pass.txt\n")
        }

        // Add route 172.16.0.0/16 if not present
        if (!modified.contains("route 172.16.0.0")) {
            modified = modified.replace(
                Regex("(?m)^route-delay\\s+4\\s*$"),
                "route 172.16.0.0 255.255.0.0\nroute-delay 4"
            )
        }

        dest.writeText(modified)
        Log.d(TAG, "OVPN native config written: ${dest.absolutePath}")
    }

    private fun writeCredentials(dest: File) {
        dest.writeText("$vpnUser\n$vpnPass\n")
        dest.setReadable(true, false)
        Log.d(TAG, "Credentials written: user=$vpnUser")
    }

    // ═══════════════════════════════════════════════════════════
    // TIER 2: WRITE TO SYSTEM DOWNLOADS VIA MEDIASTORE
    // ═══════════════════════════════════════════════════════════

    private fun exportOvpnToDownloads(): File? {
        val fileName = "sophos-nemk-vpn.ovpn"
        val mimeType = "application/x-openvpn-profile"

        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val contentValues = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                    put(MediaStore.Downloads.MIME_TYPE, mimeType)
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }

                val resolver = contentResolver
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, contentValues)
                    ?: throw Exception("MediaStore insert returned null")

                resolver.openOutputStream(uri)?.use { outputStream ->
                    val ovpnContent = buildInlineOvpnForDownloads()
                    outputStream.write(ovpnContent.toByteArray(Charsets.UTF_8))
                    outputStream.flush()
                } ?: throw Exception("Could not open output stream")

                contentValues.clear()
                contentValues.put(MediaStore.Downloads.IS_PENDING, 0)
                resolver.update(uri, contentValues, null, null)

                Log.d(TAG, "✅ MediaStore write SUCCESS: $uri")

                // Copy to app's external files dir for FileProvider access
                val externalDir = File(getExternalFilesDir(null), "vpn")
                externalDir.mkdirs()
                val localFile = File(externalDir, fileName)
                localFile.writeText(buildInlineOvpnForDownloads())
                Log.d(TAG, "✅ Copied to FileProvider dir: ${localFile.absolutePath}")
                localFile

            } else {
                @Suppress("DEPRECATION")
                val downloadsDir = File(
                    Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                    "AttendanceSuite_VPN"
                )
                downloadsDir.mkdirs()
                val destFile = File(downloadsDir, fileName)
                destFile.writeText(buildInlineOvpnForDownloads())
                Log.d(TAG, "✅ Written to Downloads: ${destFile.absolutePath}")
                destFile
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ MediaStore/Downloads write failed: ${e.message}")
            e.printStackTrace()
            // Fallback: write to app's external files
            try {
                val fallbackDir = File(getExternalFilesDir(null), "Downloads")
                fallbackDir.mkdirs()
                val fallbackFile = File(fallbackDir, fileName)
                fallbackFile.writeText(buildInlineOvpnForDownloads())
                Log.d(TAG, "✅ Fallback write: ${fallbackFile.absolutePath}")
                fallbackFile
            } catch (e2: Exception) {
                Log.e(TAG, "Fallback also failed: ${e2.message}")
                null
            }
        }
    }

    /**
     * Open OVPN file via ACTION_VIEW with FileProvider URI
     */
    private fun promptUserOpenOvpn(uri: Uri, fileName: String): Boolean {
        return try {
            Log.d(TAG, "Opening OVPN via FileProvider URI: $uri")

            val mimeTypes = listOf(
                "application/x-openvpn-profile",
                "application/x-openvpn",
                "application/octet-stream",
                "*/*"
            )

            for (mime in mimeTypes) {
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, mime)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    addFlags(Intent.FLAG_ACTIVITY_NO_HISTORY)
                    putExtra(Intent.EXTRA_TEXT, "Chọn OpenVPN Connect để kết nối VPN BV")
                }

                if (intent.resolveActivity(packageManager) != null) {
                    startActivity(intent)
                    Log.d(TAG, "✅ Opened picker with MIME: $mime")
                    return true
                }
            }

            // Fallback: open Downloads folder
            val openDownloads = Intent(Intent.ACTION_VIEW).apply {
                data = Uri.parse("content://media/internal/downloads")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            if (openDownloads.resolveActivity(packageManager) != null) {
                startActivity(openDownloads)
                Log.d(TAG, "✅ Opened Downloads")
                return true
            }

            Log.w(TAG, "No activity found to open OVPN file")
            false

        } catch (e: Exception) {
            Log.e(TAG, "promptUserOpenOvpn failed: ${e.message}")
            e.printStackTrace()
            false
        }
    }

    // ═══════════════════════════════════════════════════════════
    // TIER 3: TRY OPENVPN CONNECT APP DIRECTLY
    // ═══════════════════════════════════════════════════════════

    private fun tryLaunchOpenVPNConnectApp(): Boolean {
        val packages = listOf(
            "net.openvpn.connect.android" to "OpenVPN Connect",
            "de.blinkt.openvpn" to "Blinkt OpenVPN"
        )

        for ((pkg, name) in packages) {
            try {
                packageManager.getPackageInfo(pkg, 0)
                Log.d(TAG, "Found VPN app: $name ($pkg)")

                val externalDir = File(getExternalFilesDir(null), "vpn")
                externalDir.mkdirs()
                val ovpnFile = File(externalDir, "attendance_vpn.ovpn")
                ovpnFile.writeText(buildInlineOvpnForDownloads())

                val uri = FileProvider.getUriForFile(this, FILEPROVIDER_AUTHORITY, ovpnFile)

                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setPackage(pkg)
                    setDataAndType(uri, "application/x-openvpn-profile")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }

                if (intent.resolveActivity(packageManager) != null) {
                    startActivity(intent)
                    Log.d(TAG, "✅ Launched $name with OVPN profile")
                    return true
                }

            } catch (e: Exception) {
                Log.d(TAG, "VPN app not installed: $pkg")
            }
        }

        return false
    }

    private fun updateNotification(t: String) {
        try {
            getSystemService(NotificationManager::class.java)
                .notify(NOTIFICATION_ID, makeNotif(t))
        } catch (_: Exception) {}
    }
}
