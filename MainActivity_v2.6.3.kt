package com.bvdk.attendance_mobile

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.widget.Toast
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import io.flutter.embedding.android.FlutterActivity

/// v2.6.3: Khoi tao Chaquopy + start attendance_web server.
/// Co logging chi tiet de debug neu Python khong start duoc.
class MainActivity : FlutterActivity() {
    companion object {
        private const val TAG = "AttendanceMain"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startPythonServer()
    }

    private fun startPythonServer() {
        Log.i(TAG, "=== startPythonServer begin ===")
        try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(this))
                Log.i(TAG, "Python.start() OK")
            } else {
                Log.i(TAG, "Python already started")
            }
            val py = Python.getInstance()
            val module = py.getModule("launcher")
            Log.i(TAG, "Got launcher module")
            val result = module.callAttr("start_server", 8080)
            Log.i(TAG, "start_server result: $result")
            // Toast thong bao cho user
            Handler(Looper.getMainLooper()).post {
                Toast.makeText(
                    this@MainActivity,
                    if (result.toBoolean()) "✅ Python OK" else "❌ Python FAILED - check logcat",
                    Toast.LENGTH_SHORT
                ).show()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Python: ${e.message}", e)
            Handler(Looper.getMainLooper()).post {
                Toast.makeText(
                    this@MainActivity,
                    "❌ Python exception: ${e.javaClass.simpleName}",
                    Toast.LENGTH_LONG
                ).show()
            }
        }
        Log.i(TAG, "=== startPythonServer end ===")
    }
}
