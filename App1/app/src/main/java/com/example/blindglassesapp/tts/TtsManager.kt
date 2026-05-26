package com.example.blindglassesapp.tts

import android.content.Context
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale

/**
 * 單一職責的 TTS 語音管理器。
 * 封裝 Android TextToSpeech，提供簡潔的 speak() 介面。
 * 請在 Activity.onCreate() 建立，並在 onDestroy() 呼叫 release()。
 */
class TtsManager(context: Context) {

    companion object {
        private const val TAG = "TtsManager"
    }

    private var tts: TextToSpeech? = null
    private var isReady = false

    init {
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale.TRADITIONAL_CHINESE)
                isReady = result != TextToSpeech.LANG_MISSING_DATA &&
                        result != TextToSpeech.LANG_NOT_SUPPORTED
                if (!isReady) {
                    Log.w(TAG, "繁體中文 TTS 語言套件不可用，嘗試簡體中文...")
                    val fallback = tts?.setLanguage(Locale.SIMPLIFIED_CHINESE)
                    isReady = fallback != TextToSpeech.LANG_MISSING_DATA &&
                            fallback != TextToSpeech.LANG_NOT_SUPPORTED
                }
                if (isReady) {
                    // 將語速加快以符合盲人操作習慣
                    tts?.setSpeechRate(1.2f)
                    tts?.setPitch(1.0f)
                    Log.d(TAG, "TTS 初始化成功")
                } else {
                    Log.e(TAG, "TTS 語言初始化失敗")
                }
            } else {
                Log.e(TAG, "TTS 初始化失敗，狀態碼: $status")
            }
        }
    }

    /**
     * 播報指定文字。
     * @param text 要播報的文字。
     * @param flushPrevious 是否中斷目前正在播報的內容（預設 true）。
     */
    fun speak(text: String, flushPrevious: Boolean = true) {
        if (!isReady) {
            Log.w(TAG, "TTS 尚未就緒，無法播報: $text")
            return
        }
        val queueMode = if (flushPrevious) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD
        tts?.speak(text, queueMode, null, null)
    }

    /**
     * 停止目前播報。
     */
    fun stop() {
        tts?.stop()
    }

    /**
     * 釋放資源，請在 Activity.onDestroy() 呼叫。
     */
    fun release() {
        tts?.stop()
        tts?.shutdown()
        tts = null
        isReady = false
    }
}
