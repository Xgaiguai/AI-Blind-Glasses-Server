package com.example.blindglassesapp.network

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL

class MonitorStateRepository {

    companion object {
        private const val TAG = "MonitorStateRepo"
    }

    data class ServerMonitorState(
        val isStreaming: Boolean,
        val fps: Double,
        val width: Int,
        val height: Int,
        val activeViewers: Int,
        val deviceConnected: Boolean,
        val deviceIp: String,
        val streamStartedAt: String
    )

    suspend fun fetchMonitorState(): ServerMonitorState? = withContext(Dispatchers.IO) {
        var connection: HttpURLConnection? = null
        try {
            val url = URL(FamilyEndpoints.STATE)
            connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 3000
            connection.readTimeout = 3000

            if (connection.responseCode == HttpURLConnection.HTTP_OK) {
                val text = connection.inputStream.bufferedReader().use(BufferedReader::readText)
                val json = JSONObject(text)
                return@withContext ServerMonitorState(
                    isStreaming = json.optBoolean("is_streaming", false),
                    fps = json.optDouble("fps", 0.0),
                    width = json.optInt("width", 0),
                    height = json.optInt("height", 0),
                    activeViewers = json.optInt("active_viewers", 0),
                    deviceConnected = json.optBoolean("device_connected", false),
                    deviceIp = json.optString("device_ip", "N/A"),
                    streamStartedAt = json.optString("stream_started_at", "N/A")
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get state failed: ${e.message}")
        } finally {
            connection?.disconnect()
        }
        null
    }
}
