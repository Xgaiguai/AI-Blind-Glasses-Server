package com.example.blindglassesapp.network

/** 正式站基底網址（監看頁寫死使用此常數）。 */
object FamilyEndpoints {
    const val BASE = "https://www.blind-glasses.org"

    const val FRAME = "$BASE/api/monitor/frame"
    const val STATE = "$BASE/api/monitor/state"
    const val LOCATION = "$BASE/api/family/location"
    const val STREAM = "$BASE/stream"
    const val MONITOR_PAGE = "$BASE/monitor"
    const val HEALTH = "$BASE/health"

    const val WS_VIEWER = "wss://www.blind-glasses.org/ws/viewer"
    const val WS_UI = "wss://www.blind-glasses.org/ws_ui"
}
