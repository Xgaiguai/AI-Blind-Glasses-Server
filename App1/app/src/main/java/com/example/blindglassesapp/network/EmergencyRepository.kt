package com.example.blindglassesapp.network

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * 緊急求助網路呼叫層。
 * 負責向伺服器 POST /api/family/emergency 發送求助請求，
 * 伺服器會透過 LINE Bot 推播通知家屬並附帶 GPS 位置。
 */
class EmergencyRepository {

    companion object {
        private const val TAG = "EmergencyRepository"
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    /**
     * 發送緊急求助到伺服器。
     * @param note 附加說明（例如觸發來源）
     * @return true 表示伺服器成功接收並已嘗試推播家屬
     */
    suspend fun sendEmergency(note: String = "app_sos_button"): Boolean =
        withContext(Dispatchers.IO) {
            try {
                val body = JSONObject().apply {
                    put("note", note)
                }.toString().toRequestBody(JSON_MEDIA_TYPE)

                val request = Request.Builder()
                    .url(FamilyEndpoints.EMERGENCY)
                    .post(body)
                    .build()

                val response = client.newCall(request).execute()
                val responseBody = response.body?.string().orEmpty()
                response.close()

                if (response.isSuccessful) {
                    val json = JSONObject(responseBody)
                    val ok = json.optBoolean("ok", false)
                    Log.i(TAG, "Emergency sent: ok=$ok, sent=${json.optBoolean("sent")}")
                    ok
                } else {
                    Log.w(TAG, "Emergency failed: HTTP ${response.code}")
                    false
                }
            } catch (e: Exception) {
                Log.e(TAG, "Emergency request error: ${e.message}", e)
                false
            }
        }
}
