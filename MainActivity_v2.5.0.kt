package com.bvdk.attendance_mobile

import android.os.Bundle
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import io.flutter.embedding.android.FlutterActivity

/// v2.5.0: Chaquopy Python in Android
/// - onCreate: khởi tạo Chaquopy platform + start attendance_web server nền
/// - Flutter WebView (lib/main.dart) sẽ load http://127.0.0.1:8080/ để xem UI Python
class MainActivity : FlutterActivity() {
    companion object {
        private const val TAG = "AttendanceMainActivity"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startPythonServer()
    }

    private fun startPythonServer() {
        try {
            // Init Chaquopy Android platform (gọi 1 lần trước khi dùng Python)
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(this))
            }
            val py = Python.getInstance()
            val module = py.getModule("launcher")
            // Gọi start_server() không block, returns True/False
            val result = module.callAttr("start_server", 8080)
            Log.i(TAG, "Python server start result: $result")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Python server: ${e.message}", e)
        }
    }
}
