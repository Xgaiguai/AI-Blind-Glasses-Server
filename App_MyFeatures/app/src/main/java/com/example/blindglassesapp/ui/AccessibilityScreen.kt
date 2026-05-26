package com.example.blindglassesapp.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalViewConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.blindglassesapp.ble.BleConnectionState
import com.example.blindglassesapp.tts.TtsManager
import com.example.blindglassesapp.viewmodel.MainViewModel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlin.math.abs
import android.app.Activity
import android.view.WindowManager
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

enum class MenuMode {
    NONE,
    TWO_FINGER,
    THREE_FINGER
}

data class AccessibilityFeature(
    val name: String,
    val action: () -> Unit
)

/**
 * 盲人專用全螢幕手勢操作頁面。
 * 支援兩指與三指上下滑動切換功能，以及單指雙擊確認執行。
 */
@Composable
fun AccessibilityScreen(
    viewModel: MainViewModel,
    ttsManager: TtsManager,
    onBack: () -> Unit
) {
    val bleState by viewModel.bleState.collectAsState()
    val volume by viewModel.currentVolume.collectAsState()
    val isConnected = bleState is BleConnectionState.Connected

    var tapCount by remember { mutableStateOf(0) }
    var currentMenuMode by remember { mutableStateOf(MenuMode.NONE) }
    var currentFeatureIndex by remember { mutableStateOf(0) }

    val view = LocalView.current
    
    // 進入頁面時自動隱藏導覽列與狀態列（進入沉浸模式，防誤觸）
    // 同時加入 FLAG_SECURE 阻擋系統三指截圖手勢
    DisposableEffect(view) {
        val window = (view.context as? Activity)?.window
        if (window != null) {
            val insetsController = WindowCompat.getInsetsController(window, view)
            insetsController.hide(WindowInsetsCompat.Type.systemBars())
            insetsController.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            
            window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
            
            onDispose {
                insetsController.show(WindowInsetsCompat.Type.systemBars())
                window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
            }
        } else {
            onDispose { }
        }
    }

    // 進入頁面時播報說明
    LaunchedEffect(Unit) {
        if (isConnected) {
            ttsManager.speak("已進入全螢幕盲人模式。兩指下滑可切換基本功能，三指下滑切換進階功能。聽到功能後，雙擊螢幕確認。雙指點一下可暫停語音。點擊三次退出此模式。")
        } else {
            ttsManager.speak("盲人模式。眼鏡尚未連線。點擊三次螢幕即可退出。")
        }
    }

    // 定義兩指選單功能 (5個)
    val twoFingerFeatures = remember(isConnected, volume) {
        listOf(
            AccessibilityFeature("尋找眼鏡") {
                if (isConnected) {
                    val sent = viewModel.sendFindMe()
                    if (sent) ttsManager.speak("找眼鏡")
                    else ttsManager.speak("尋找失敗")
                } else ttsManager.speak("尚未連線")
            },
            AccessibilityFeature("增加音量") {
                if (isConnected) {
                    val sent = viewModel.increaseVolume()
                    if (sent) ttsManager.speak("音量 ${viewModel.currentVolume.value}")
                    else ttsManager.speak("調整失敗")
                } else ttsManager.speak("尚未連線")
            },
            AccessibilityFeature("減少音量") {
                if (isConnected) {
                    val sent = viewModel.decreaseVolume()
                    if (sent) ttsManager.speak("音量 ${viewModel.currentVolume.value}")
                    else ttsManager.speak("調整失敗")
                } else ttsManager.speak("尚未連線")
            },
            AccessibilityFeature("查詢電量") {
                ttsManager.speak("電量百分之百") // 之後可串接真實 API
            },
            AccessibilityFeature("查詢時間") {
                ttsManager.speak("現在時間") // 之後可串接系統時間
            }
        )
    }

    // 定義三指選單功能 (5個)
    val threeFingerFeatures = remember {
        listOf(
            AccessibilityFeature("環境描述") {
                ttsManager.speak("正在掃描環境") // 之後可串接相機 AI
            },
            AccessibilityFeature("路徑導航") {
                ttsManager.speak("準備導航") // 之後可串接地圖 API
            },
            AccessibilityFeature("人臉辨識") {
                ttsManager.speak("啟動人臉辨識")
            },
            AccessibilityFeature("文字閱讀") {
                ttsManager.speak("啟動文字閱讀")
            },
            AccessibilityFeature("警報模式") {
                ttsManager.speak("發出警報")
            }
        )
    }

    // 處理連續點擊次數 (等待 500ms 確認後續點擊)
    LaunchedEffect(tapCount) {
        if (tapCount > 0) {
            delay(500)
            val count = tapCount
            tapCount = 0
            
            // 單擊直接忽略（防止誤觸）
            if (count == 1) return@LaunchedEffect

            if (count == 2) {
                // 執行選單功能
                when (currentMenuMode) {
                    MenuMode.TWO_FINGER -> {
                        twoFingerFeatures.getOrNull(currentFeatureIndex)?.action?.invoke()
                    }
                    MenuMode.THREE_FINGER -> {
                        threeFingerFeatures.getOrNull(currentFeatureIndex)?.action?.invoke()
                    }
                    MenuMode.NONE -> {
                        ttsManager.speak("請先使用兩指或三指上下滑動來選擇功能")
                    }
                }
            } else if (count >= 3) {
                ttsManager.speak("已退出盲人模式")
                onBack()
            }
        }
    }

    val viewConfiguration = LocalViewConfiguration.current

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .pointerInput(Unit) {
                coroutineScope {
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        var maxPointers = 1
                        var startY = down.position.y
                        var currentY = startY
                        var isSwipe = false
                        val slop = viewConfiguration.touchSlop
                        
                        do {
                            val event = awaitPointerEvent()
                            if (event.changes.size > maxPointers) {
                                maxPointers = event.changes.size
                            }
                            
                            // 計算觸控點的平均 Y 座標以判斷整體滑動方向
                            val activeChanges = event.changes.filter { it.pressed }
                            if (activeChanges.isNotEmpty()) {
                                val avgY = activeChanges.map { it.position.y }.average().toFloat()
                                if (abs(avgY - startY) > slop) {
                                    isSwipe = true
                                    currentY = avgY
                                }
                            }
                            
                            // 消耗事件，防止事件往下傳遞
                            event.changes.forEach { it.consume() }
                        } while (event.changes.any { it.pressed })
                        
                        // 判斷手勢結果
                        if (isSwipe) {
                            tapCount = 0 // 滑動時重置點擊計數
                            val deltaY = currentY - startY
                            
                            // 僅處理兩指或三指的滑動
                            if (maxPointers == 2 || maxPointers == 3) {
                                val mode = if (maxPointers == 2) MenuMode.TWO_FINGER else MenuMode.THREE_FINGER
                                val featuresCount = if (mode == MenuMode.TWO_FINGER) twoFingerFeatures.size else threeFingerFeatures.size
                                val isSwipeDown = deltaY > 0
                                
                                var isFirstTimeInMode = false
                                
                                if (currentMenuMode != mode) {
                                    // 首次切換到該選單
                                    currentMenuMode = mode
                                    currentFeatureIndex = 0
                                    isFirstTimeInMode = true
                                } else {
                                    // 在同一個選單中切換
                                    if (isSwipeDown) {
                                        currentFeatureIndex = (currentFeatureIndex + 1) % featuresCount
                                    } else {
                                        currentFeatureIndex = (currentFeatureIndex - 1 + featuresCount) % featuresCount
                                    }
                                }
                                
                                // 取得功能名稱並播報
                                val featureName = if (mode == MenuMode.TWO_FINGER) {
                                    twoFingerFeatures[currentFeatureIndex].name
                                } else {
                                    threeFingerFeatures[currentFeatureIndex].name
                                }
                                
                                val prefix = if (isFirstTimeInMode) {
                                    if (mode == MenuMode.TWO_FINGER) "兩指選單：" else "三指選單："
                                } else ""
                                
                                ttsManager.speak("$prefix$featureName")
                            }
                        } else {
                            // 沒滑動，視為點擊
                            if (maxPointers == 1) {
                                tapCount++
                            } else if (maxPointers >= 2) {
                                // 兩指或多指點擊，立即停止語音
                                ttsManager.stop()
                            }
                        }
                    }
                }
            },
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.padding(32.dp)
        ) {
            Text(
                text = "多指輪播盲人模式",
                fontSize = 32.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(24.dp))
            
            Text(
                text = "目前選單：\n${
                    when (currentMenuMode) {
                        MenuMode.NONE -> "尚未選擇"
                        MenuMode.TWO_FINGER -> "兩指選單 (${twoFingerFeatures[currentFeatureIndex].name})"
                        MenuMode.THREE_FINGER -> "三指選單 (${threeFingerFeatures[currentFeatureIndex].name})"
                    }
                }",
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.secondary,
                textAlign = TextAlign.Center
            )
            
            Spacer(modifier = Modifier.height(32.dp))
            
            val instructionText = "兩指/三指滑動：切換功能\n單指雙擊：確認執行\n雙指點一下：暫停語音\n單指點擊 3 次：退出"
            
            Text(
                text = instructionText,
                fontSize = 20.sp,
                lineHeight = 36.sp,
                color = MaterialTheme.colorScheme.onBackground,
                textAlign = TextAlign.Center
            )
            
            if (!isConnected) {
                Spacer(modifier = Modifier.height(24.dp))
                Text(
                    text = "⚠️ 眼鏡尚未連線",
                    fontSize = 18.sp,
                    color = MaterialTheme.colorScheme.error,
                    textAlign = TextAlign.Center
                )
            }
        }
    }
}
