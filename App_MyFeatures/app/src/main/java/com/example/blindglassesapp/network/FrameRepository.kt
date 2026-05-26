package com.example.blindglassesapp.network

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL

class FrameRepository {

    companion object {
        private const val TAG = "FrameRepository"
    }

    /**
     * 從 API 拉取最新一幀 Bitmap
     */
    suspend fun fetchLatestFrame(): Bitmap? = withContext(Dispatchers.IO) {
        var connection: HttpURLConnection? = null
        var inputStream: InputStream? = null
        try {
            val url = URL(FamilyEndpoints.FRAME)
            connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 3000
            connection.readTimeout = 3000
            connection.doInput = true

            val responseCode = connection.responseCode
            if (responseCode == HttpURLConnection.HTTP_OK) {
                inputStream = connection.inputStream
                return@withContext BitmapFactory.decodeStream(inputStream)
            } else {
                Log.e(TAG, "Http error: $responseCode")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Fetch frame crash: ${e.message}")
        } finally {
            inputStream?.close()
            connection?.disconnect()
        }
        null
    }
}
