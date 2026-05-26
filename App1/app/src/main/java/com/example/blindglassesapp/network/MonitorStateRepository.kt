package com.example.blindglassesapp.network

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/** 監看頁由 `/api/monitor/state`（或 `ws_ui`）解析出的精簡欄位。 */
data class MonitorUiSnapshot(
    val motionLabel: String,
    val mapUrl: String?,
    val latitude: Double?,
    val longitude: Double?,
)

/** 依伺服器基底網址輪詢／訂閱監控狀態（與即時影像同一台主機）。 */
class MonitorStateRepository(baseUrl: String) {

    companion object {
        private const val TAG = "MonitorStateRepository"
        private const val HTTP_STATE_POLL_MS = 750L
    }

    private val origin = baseUrl.trimEnd('/')
    private val wsUiUrl =
        origin.replace("http://", "ws://").replace("https://", "wss://") + "/ws_ui"
    private val stateUrl = "$origin/api/monitor/state"
    private val healthUrl = "$origin/health"

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    fun wsUiStateFlow(): Flow<MonitorUiSnapshot> = callbackFlow {
        Log.d(TAG, "Connecting ws_ui: $wsUiUrl")
        val request = Request.Builder().url(wsUiUrl).build()
        val ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                trySend(parseMonitorStateJson(text))
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "ws_ui failure: ${t.message}")
                close(t)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "ws_ui closed: $code $reason")
                close()
            }
        })
        awaitClose { ws.cancel() }
    }.flowOn(Dispatchers.IO)

    fun httpStatePollFlow(): Flow<MonitorUiSnapshot> = flow {
        while (true) {
            try {
                val response = client.newCall(Request.Builder().url(stateUrl).build()).execute()
                val body = response.body?.string().orEmpty()
                response.close()
                if (response.isSuccessful && body.isNotBlank()) {
                    emit(parseMonitorStateJson(body))
                } else {
                    emit(MonitorUiSnapshot("狀態未知", null, null, null))
                }
            } catch (e: Exception) {
                Log.w(TAG, "HTTP state poll: ${e.message}")
                emit(MonitorUiSnapshot("狀態未知", null, null, null))
            }
            delay(HTTP_STATE_POLL_MS)
        }
    }.flowOn(Dispatchers.IO)

    fun checkHealth(): Boolean {
        return try {
            val response = client.newCall(Request.Builder().url(healthUrl).build()).execute()
            val ok = response.isSuccessful
            val body = response.body?.string().orEmpty()
            response.close()
            ok && body.contains("ok")
        } catch (e: Exception) {
            Log.w(TAG, "health check: ${e.message}")
            false
        }
    }

    private fun parseMonitorStateJson(jsonStr: String): MonitorUiSnapshot {
        return try {
            val root = JSONObject(jsonStr)
            val fusion = root.optJSONObject("fusion")
            val motionLabel = when {
                fusion == null -> "狀態未知"
                fusion.optString("motion_state", "") == "moving" -> "移動中"
                fusion.optString("motion_state", "") == "stopped" -> "已停止"
                fusion.has("is_moving") -> if (fusion.optBoolean("is_moving")) "移動中" else "已停止"
                else -> "狀態未知"
            }
            val family = root.optJSONObject("family")
            val lastGps = family?.optJSONObject("last_gps")
            val mapUrl = lastGps?.optString("map_url", null)?.takeIf { it.isNotBlank() }
            val lat: Double? = lastGps?.let { g ->
                val v = g.optDouble("lat", Double.NaN)
                if (v.isNaN()) null else v
            }
            val lng: Double? = lastGps?.let { g ->
                val v = g.optDouble("lng", Double.NaN)
                if (v.isNaN()) null else v
            }
            MonitorUiSnapshot(
                motionLabel = motionLabel,
                mapUrl = mapUrl,
                latitude = lat,
                longitude = lng,
            )
        } catch (e: Exception) {
            Log.w(TAG, "parse JSON: ${e.message}")
            MonitorUiSnapshot("狀態未知", null, null, null)
        }
    }
}
