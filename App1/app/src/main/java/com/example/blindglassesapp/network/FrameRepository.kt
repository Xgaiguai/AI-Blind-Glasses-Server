package com.example.blindglassesapp.network

import android.graphics.Bitmap
import android.graphics.BitmapFactory
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
import okio.ByteString
import java.util.concurrent.TimeUnit

/**
 * @param httpPollIntervalMs HTTP 輪詢 `/api/monitor/frame` 間隔；家屬規格建議 100–300ms，預設 200ms。
 */
class FrameRepository(
    private val baseUrl: String,
    private val httpPollIntervalMs: Long = 200L,
) {

    companion object {
        private const val TAG = "FrameRepository"
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    /**
     * WebSocket stream: connects to ws(s)://host/ws/viewer and emits binary JPEG frames.
     */
    fun wsFrameStream(): Flow<Bitmap?> = callbackFlow {
        val wsUrl = baseUrl
            .replace("http://", "ws://")
            .replace("https://", "wss://")
            .trimEnd('/') + "/ws/viewer"

        Log.d(TAG, "Connecting WebSocket: $wsUrl")

        val request = Request.Builder().url(wsUrl).build()
        val ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                val data = bytes.toByteArray()
                val bitmap = BitmapFactory.decodeByteArray(data, 0, data.size)
                trySend(bitmap)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "WebSocket failure: ${t.message}")
                close(t)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closed: $code $reason")
                close()
            }
        })

        awaitClose {
            ws.cancel()
        }
    }.flowOn(Dispatchers.IO)

    /**
     * HTTP polling fallback: GET /api/monitor/frame with ETag support.
     */
    fun httpFrameStream(): Flow<Bitmap?> = flow {
        var lastEtag: String? = null
        val url = baseUrl.trimEnd('/') + "/api/monitor/frame"

        while (true) {
            try {
                val reqBuilder = Request.Builder().url(url)
                lastEtag?.let { reqBuilder.header("If-None-Match", it) }
                val response = client.newCall(reqBuilder.build()).execute()

                when (response.code) {
                    200 -> {
                        lastEtag = response.header("ETag")
                        val bytes = response.body?.bytes()
                        if (bytes != null && bytes.isNotEmpty()) {
                            emit(BitmapFactory.decodeByteArray(bytes, 0, bytes.size))
                        }
                    }
                    304 -> { /* unchanged, skip */ }
                    204 -> emit(null)
                }
                response.close()
            } catch (e: Exception) {
                Log.w(TAG, "HTTP poll error: ${e.message}")
                emit(null)
            }
            delay(httpPollIntervalMs)
        }
    }.flowOn(Dispatchers.IO)
}
